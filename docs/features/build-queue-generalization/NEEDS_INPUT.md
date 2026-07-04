---
kind: needs-input
feature_id: build-queue-generalization
written_by: spec
decisions:
  - Ops-manifest file format and location
  - Enforcement scope gate — manifest presence vs presence-plus-Cognito-fallback
  - Transient long-build arbitration with the orchestrator-takeover contract
  - v1 platform scope (PowerShell dependency on non-Windows hosts)
date: 2026-07-04
next_skill: spec
class: product
---

# /spec --batch — Needs Input

The build-queue-generalization SPEC baseline is drafted and research is integrated
(`RESEARCH_SUMMARY.md`). Four product-behavior decisions gate finalization — each has a strong
standing recommendation, but each changes what the operator authors, how enforcement can degrade,
how the autonomous pipeline runs long builds, or the v1 scope boundary, so the operator retains
final authority. The four mechanical-internal decisions (D2 schema shape, D3 hygiene-profile
registry, D6 FIFO fairness, D8 skill migration path) were auto-accepted at their single defensible
option and are NOT surfaced here.

## Decision Context

### 1. Ops-manifest file format and location

**Problem:** The whole feature turns on a new per-repo file the operator authors when onboarding a
repo to the build queue: a manifest declaring each build/test "op" (its filtered-script command,
whether it is a build or a test, which hygiene profile applies, and which raw command strings the
enforcement hook should deny). Three separate consumers must parse this file — the PowerShell
wrapper/runner, the bash-embedded-Python enforcement hook, and (later) an ETA/lanes sibling
feature. The original stub left "markdown vs JSON" open. Because the operator hand-writes this file
and its extension/shape is visible in `.claude/skill-config/`, the choice is operator-facing.

**Options:**
- **A — JSON at `.claude/skill-config/build-queue-ops.json` (Recommended)** — one schema parsed
  with `ConvertFrom-Json` (PowerShell) and stdlib `json` (the hook's Python): zero bespoke parsing,
  identical semantics in both languages, trivially validatable, and it matches the queue's existing
  JSON state files. Cost: a `.json` file in a `skill-config/` dir that is otherwise `.md`/`.txt`,
  and slightly less pleasant to hand-edit than markdown. Reversible (format is an onboarding-time
  choice, low blast radius).
- **B — Markdown table at `build-queue-ops.md`** — matches the skill-config house style
  (`quality-gates.md`, `commit-policy.md`) and renders on GitHub. Cost: needs a bespoke table
  parser written TWICE (PowerShell + Python) that must stay in lockstep; a malformed row degrades
  silently, and because the enforce hook is fail-OPEN, a parser divergence would silently widen or
  narrow the deny surface with no error signal — exactly the coupled-parser drift class the harness
  avoids.
- **C — PSD1 (PowerShell-native data file)** — natural for the wrapper, but the hook's Python
  cannot parse PSD1 without a hand-rolled reader, so it inherits option B's two-parser problem.

**Recommendation:** A — JSON. A single standard format eliminates the two-bespoke-parser drift
class under a fail-OPEN hook, and non-markdown machine-read config already has skill-config
precedent (`capabilities.txt`, `ado-doc-integration.yml`).

### 2. Enforcement scope gate — manifest presence vs presence-plus-Cognito-fallback

**Problem:** Today `build-queue-enforce.sh` (the PreToolUse hook that denies raw `dotnet build`
etc. and redirects to the queue skills) fires ONLY when the repo's git remote matches
`cognitoforms/cognito`. Once the manifest exists, the natural rule is "gate any repo that has a
manifest." But the hook is the only thing standing between a raw heavy build and the copy-lock /
compiler-recycle failure classes those sibling bugs fixed — and a broken skill-config symlink (a
fresh worktree before `setup.ps1 bootstrap -Target Repos`) would leave a manifest-presence-only
gate silently disarmed. This decides which repos are gated and how enforcement degrades when the
manifest is missing/unreadable.

**Options:**
- **A — Manifest presence + Cognito remote-match legacy fallback (Recommended)** — the hook gates
  any repo whose `.claude/skill-config/build-queue-ops.json` is present (compiling that manifest's
  deny patterns), AND additionally, when the remote matches `cognitoforms/cognito` but the manifest
  is missing/unreadable, falls back to today's hard-coded Cognito deny set. Cost: two code paths;
  the legacy set must be kept in sync until deliberately retired (planned as a later cleanup once
  the manifest has survived a few weeks of live worktrees). Benefit: an accidental symlink break
  cannot silently disarm the only enforcement protecting the copy-lock/recycle invariants — it
  degrades to unchanged legacy behavior, not to nothing.
- **B — Manifest presence is the sole gate** — cleaner end state (one code path; the Cognito
  remote-match is deleted the moment Cognito's manifest lands). Cost: during the migration window a
  broken symlink silently re-opens the recycle bug's Vector B (a raw off-queue build with no
  enforcement), the worst failure mode of this migration, with no error signal because the hook is
  fail-OPEN.
- **C — Central `~/.claude` registry of repo→ops instead of per-repo manifests** — rejected in the
  SPEC: breaks the per-repo skill-config convention, breaks worktree aliasing for free, and makes
  repo onboarding a two-file edit.

**Recommendation:** A — keep the ~15-line Cognito fallback. A silently-disarmed hook is this
migration's worst failure mode; the fallback converts "silent disarm" into "unchanged legacy
behavior" cheaply and is retired later once the manifest is proven live.

### 3. Transient long-build arbitration with the orchestrator-takeover contract

**Problem:** AlgoBooth's heaviest builds (`tauri build`, `cargo build --release`) are today handled
by a SEPARATE mechanism from the queue: `long-build-ownership-guard.sh` denies a subagent's raw
invocation with a `LONG-BUILD-OWNERSHIP-TAKEOVER` signal, and the orchestrator re-launches the
build itself (detached, with atomic artifact promotion) — but with no serialization, no hygiene,
and no outcome banner. If AlgoBooth registers those same builds as queue ops, two deny hooks now
cover one command and the orchestrator's re-launch could itself be denied by the generalized
enforce hook — a ping-pong between two owners. This decides who owns a long build in a
queue-governed repo, and therefore whether the autonomous pipeline's AlgoBooth long builds get the
queue's serialization + hygiene + banner + occupancy-visibility.

**Options:**
- **A — Route transient builds THROUGH the queue (Recommended)** — the takeover path is unchanged
  (guard denies the subagent; orchestrator takes over), but the orchestrator's re-launch command
  becomes the queue wrapper invocation, spawned via the existing detached-build primitive. No
  ping-pong by construction: the enforce hook already exempts any command carrying the wrapper, and
  the long-build guard only matches the bare binary at command-start (never the wrapper form).
  Ordering invariant: the ownership guard stays registered BEFORE the enforce hook so a raw
  `tauri build` always surfaces the takeover signal first. Benefit: one machine-global serializer;
  AlgoBooth long builds gain banner + result-JSON evidence AND become visible to
  `Get-BuildQueueOccupancy` (so a Cognito build finishing while a Tauri build runs correctly skips
  the compiler recycle). Cost/risk: `run_transient_build` awaits its spawned command while the
  wrapper also waits in its claim loop and tails — a long queue wait could look like a hung build to
  task tracking; mitigated by immediate enqueue/position heartbeat lines + a one-time live
  verification (Phase 4).
- **B — Two disjoint lanes** — long-build tokens are reserved to the ownership guard and forbidden
  from any manifest deny list (validated at load); the queue governs only filtered-script ops.
  Benefit: no interaction to reason about. Cost: AlgoBooth's heaviest builds stay off-queue —
  invisible to serialization and occupancy, re-creating the recycle bug's Vector-B lesson by design.
- **C — Queue absorbs the ownership guard** (delete the guard, fold takeover into the enforce
  redirect) — rejected: the guard is request-time and repo-agnostic (fires with NO manifest
  present); folding it in couples subagent-ownership containment to manifest presence and regresses
  the long-build-ownership feature.
- **D — No new AlgoBooth build ops in v1** — generalize the mechanics and onboard only ops that are
  NOT long-build-guarded, leaving `tauri build` / `cargo build --release` under the transient
  contract until composition is proven live. Benefit: zero interaction risk in v1; the
  generalization still ships. Cost: defers the main AlgoBooth payoff. This is the SPEC's named
  fallback if A shows live-fire friction.

**Recommendation:** A — one machine-global serializer, composing at the single already-existing seam
(the wrapper exemption), with D as the fallback if live-fire testing exposes friction between the
takeover's awaiting and the wrapper's tail loop.

### 4. v1 platform scope (PowerShell dependency on non-Windows hosts)

**Problem:** The queue is Windows-workstation-shaped end to end — `powershell.exe` detached
processes, Windows Job Objects, Restart Manager P/Invoke, Windows pid semantics. The stub asks what
happens on non-Windows hosts (cloud sessions, WSL). This decides the v1 scope boundary and one
operator-visible nuance: whether the enforcement hook is silently or loudly inert off-Windows.

**Options:**
- **A — Workstation-only v1; cloud/non-Windows explicitly exempt, hook silently inert (Recommended)**
  — the manifest may exist in a repo checked out in a cloud session, but nothing routes through the
  queue there: the skills' wrapper invocation fails fast when `powershell.exe` is absent, the cloud
  pipeline variants already defer build/runtime work by design, and the enforce hook adds a platform
  check beside its scope gate (no `powershell.exe` on PATH → allow, i.e. silently inert — consistent
  with the hook's fail-OPEN family behavior). The boundary is documented in the root `CLAUDE.md`
  build-queue rows. Cost: none for any current consumer (no cloud/WSL host runs Cognito or Tauri
  release builds).
- **B — Port the wrapper to PowerShell 7 (`pwsh`) for cross-platform** — substantial rework of the
  Job-Object / Restart-Manager hygiene (Windows-only APIs) for a host class that runs no heavy local
  builds today. Speculative portability with a large hygiene-rewrite cost and no current consumer.

**Recommendation:** A — workstation-only v1 with the hook silently inert off-Windows. Every queue
consumer is a Windows workstation session; a `pwsh` port has no current consumer. The one
operator-visible nuance (silently vs loudly inert) resolves to silently inert to match the
fail-OPEN family.
