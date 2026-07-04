# Generalize Build-Queue Beyond Cognito — Feature Specification

> The machine-global FIFO build serializer (`build-queue.ps1` wrapper + self-releasing runner +
> hygiene module + outcome banner + enforcement hook) is hard-wired to one repo: a four-op
> `ValidateSet`, a `cognitoforms/cognito` git-remote scope gate, and .NET-specific hygiene
> (VBCSCompiler recycle, per-project DLL quarantine). AlgoBooth has the exact same problem class
> (`tauri build` / `cargo build --release` long builds, today handled by a separate
> orchestrator-takeover contract with no queueing, no hygiene, no banner). This feature extracts a
> per-repo **ops manifest** (`.claude/skill-config/build-queue-ops.json`) declaring op names →
> filtered-script commands + hygiene profile + deny patterns, makes the wrapper/runner/hook
> manifest-driven, and defines the arbitration between the queue and the
> `LONG-BUILD-OWNERSHIP-TAKEOVER` orchestrator-takeover contract so the two compose instead of
> ping-ponging a build between owners.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented contracts being
> generalized**, not sibling specs:
> - The `build-queue.ps1` wrapper / `build-queue-runner.ps1` / `build-queue-hygiene.ps1` family
>   (`user/scripts/`) — seq allocation, ticket/`active.lock` lifecycle, atomic provisional lock
>   write, confirmed-dead reclaim, self-releasing detached runner, `results/<seq>.json` schema.
> - `user/hooks/build-queue-enforce.sh` — the git-remote-scoped deny hook (segment-start
>   matching, safe-variant suppression, `BUILD_QUEUE_BYPASS=1`, wrapper exemption, fail-OPEN).
> - The four Cognito skills (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest` under
>   `repos/cognito-forms/.claude/skills/`) — thin callers of the wrapper.
> - The `Format-BuildQueueBanner` authoritative-last-line outcome-banner contract
>   (`build-queue-hygiene.ps1`), which the skills instruct agents to trust.
> - The `long-build-ownership-guard.sh` + `lazy_core.run_transient_build` /
>   `promote_artifact_atomically` orchestrator-takeover contract
>   (`long-build-and-runtime-ownership`, Complete) — this feature must compose with it, not
>   fight it.

---

## Executive Summary

Four sibling bug investigations (`build-queue-no-artifact-or-process-hygiene-on-crash`,
`build-queue-recycle-kills-concurrent-worktree-build`,
`build-queue-false-green-on-silent-build-failure`,
`build-queue-outcome-opacity-and-inspect-deny`) hardened the Cognito build queue into the most
battle-tested execution primitive in the harness: atomic lock writes, occupancy-gated compiler
recycle, per-project poisoned-artifact quarantine, fidelity-verified results, and an authoritative
one-line outcome banner. None of that value is reusable outside Cognito, because repo identity is
baked in at three layers: the wrapper's `-Op` `ValidateSet('msbuild','mstest','nxbuild','nxtest')`
(`user/scripts/build-queue.ps1:29`), the enforcement hook's `cognitoforms/cognito` remote match
(`user/hooks/build-queue-enforce.sh` `_is_cognito_worktree`), and the hygiene module's .NET-shaped
sweeps (`Reset-CompilerServer`, `Remove-PoisonedArtifacts`, `Test-BuildLogFailure` MSBuild
signatures). Meanwhile AlgoBooth solves the same "one heavy build at a time on this machine"
problem with a parallel mechanism — the `long-build-ownership-guard.sh` deny +
`run_transient_build` orchestrator takeover — that has detachment and atomic promotion but no
serialization, no hygiene, and no banner.

The solution is a per-repo **ops manifest** at `.claude/skill-config/build-queue-ops.json`
(authored in `repos/<name>/.claude/skill-config/`, symlinked per `manifest.psd1` like every other
skill-config file). The manifest declares each op's name, exec script, op kind (build/test),
hygiene profile, and raw-invocation deny patterns. The wrapper resolves `-Op` against the
manifest, the runner selects a hygiene profile from a registry in `build-queue-hygiene.ps1`
instead of inferring .NET behavior from the exec-script filename, and the enforcement hook builds
its deny set from the manifest of the repo it is standing in — replacing the remote-match special
case while keeping every load-bearing property (fail-OPEN, segment-start matching, bypass token,
wrapper exemption). Cognito's manifest reproduces today's behavior byte-for-byte; AlgoBooth's
registers `tauri-build` / `cargo-release` ops with a Rust/Tauri hygiene profile.

Mission criterion: **effective** — every heavy build on the machine gets the same certified
outcome evidence (banner + `results/<seq>.json` fidelity fields) instead of ad-hoc per-repo
mechanisms; and **efficient** — the hardening already paid for once is reused, and off-queue
transient builds (the recycle bug's Vector B) stop being invisible to serialization.

## Design Decisions

### D1. Ops-manifest file format and location

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The manifest is an operator-authored per-repo file that three consumers must
  parse: the PowerShell wrapper/runner, the bash-embedded-Python enforcement hook, and (later) the
  ETA/lanes feature. The stub left "markdown vs JSON" open. Format and path are operator-visible
  (the operator writes this file when onboarding a repo).
- **Options:**
  - **A — JSON at `.claude/skill-config/build-queue-ops.json`:** one schema, parsed with
    `ConvertFrom-Json` (PowerShell) and stdlib `json` (the hook's Python). Pros: zero bespoke
    parsing, identical semantics in both languages, trivially validatable, matches the queue's
    existing JSON state files (`tickets/`, `results/`). Cons: less pleasant to hand-edit than
    markdown; a new extension in a `skill-config/` dir that is otherwise `.md`/`.txt`/`.yml`.
  - **B — Markdown table at `.claude/skill-config/build-queue-ops.md`:** matches the
    skill-config house style (`quality-gates.md`, `commit-policy.md`). Pros: human-friendly,
    renders on GitHub. Cons: needs a bespoke table parser written twice (PowerShell + Python)
    that must stay in lockstep — exactly the coupled-parser drift class the harness avoids; a
    malformed row degrades silently.
  - **C — PSD1:** native to PowerShell. Cons: the hook's Python cannot parse PSD1 without a
    hand-rolled reader; rejected on the same two-parser grounds as B.
- **Recommendation:** A — JSON. The enforcement hook is fail-OPEN, so a parse divergence between
  two bespoke parsers would silently widen or narrow the deny surface with no error signal; a
  single standard format eliminates that class. The existing skill-config precedent for
  non-markdown machine-read config already exists (`ado-doc-integration.yml`,
  `capabilities.txt`).
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D2. Manifest schema (per-op entry shape)

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What fields each op entry carries, given the format from D1.
- **Options:**
  - **A — Minimal five-field entry:**
    ```json
    {
      "version": 1,
      "ops": {
        "msbuild": {
          "exec": ".claude/scripts/build-filtered.ps1",
          "kind": "build",
          "hygiene": "dotnet",
          "skill": "/msbuild",
          "deny": ["dotnet build"]
        }
      }
    }
    ```
    `exec` is repo-root-relative (the skills already resolve `$REPO_ROOT` via
    `git rev-parse --show-toplevel`); `kind ∈ {build, test}` replaces the runner's
    filename-suffix classification (`$execLeaf -match 'build-filtered\.ps1$'`,
    `build-queue-runner.ps1:84-85`); `hygiene` names a registry profile (D3); `skill` is the
    redirect target the deny message names; `deny` lists the raw-invocation patterns the hook
    compiles onto its existing `_CMD_START` segment anchor.
  - **B — Rich entry with timeout hints, banner expectations, per-op env:** more knobs up front.
- **Recommendation:** A. Every field maps to an existing hard-coded surface being replaced; B
  adds speculative knobs with no current consumer (timeouts live in the skills' Bash `timeout`
  guidance today; the banner shape is owned by `Format-BuildQueueBanner`, not per-op config).
  The ETA/lanes sibling adds a `lane` field later as an additive schema bump — `version` exists
  for exactly that.
- **Resolution:** Auto-accepted A; field layout of an internal config contract with no
  operator-visible behavior beyond what D1/D4/D5 already surface.

### D3. Hygiene profiles as a registry, not filename inference

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Today the runner infers "build op" vs "test op" from the exec-script leaf name
  and runs .NET hygiene unconditionally: `Stop-DllLockers` pre-build, Job-Object reap,
  `Test-BuildLogFailure`/`Test-BuildProducedNoOutput` exit-0 overrides, occupancy-gated
  `Reset-CompilerServer`, `Remove-PoisonedArtifacts` on failure. A Rust/Tauri repo needs a
  different set (no compiler-server recycle, no MZ-header DLL sweep). How is the per-op hygiene
  set selected?
- **Options:**
  - **A — Named profile registry in `build-queue-hygiene.ps1`:** a `Get-HygieneProfile -Name`
    function returning a capability record (e.g.
    `@{ recycle_compiler_server = $true; poison_sweep = 'dotnet-dll'; log_failure_signatures =
    'msbuild'; reap_dll_lockers = $true }`); the runner branches on the record, never on the
    repo or filename. Profiles shipped in v1: `dotnet` (exactly today's behavior),
    `rust-tauri` (Job-Object reap + generic no-output/log-signature checks over `error[E`/
    `error:` cargo signatures + optional `target/` staging cleanup; **no** name-targeted kill of
    any process — Locked Decision 2 of `build-queue-no-artifact-or-process-hygiene-on-crash`
    forbids new name-glob kills, and Locked Decision 1's VBCSCompiler exception stays scoped to
    the `dotnet` profile), and `none` (Job-Object reap + banner only).
  - **B — Per-op hygiene flags inline in the manifest:** maximum flexibility, but the manifest
    becomes able to compose unsafe combinations (e.g. enabling the compiler-server recycle in a
    repo whose occupancy the gate has never been tested against), and the safety analysis done
    in the recycle bug applies to profiles, not free flag sets.
- **Recommendation:** A. The hygiene functions carry hard safety invariants (occupancy-gated
  recycle, fail-open sweeps, the one sanctioned name-targeted kill); a closed registry keeps
  those invariants reviewable in one file, exactly like `lazy_core._HOST_CAPABILITY_REGISTRY`
  keeps host-capability probes closed. The manifest selects a profile id; it never composes
  hygiene primitives.
- **Resolution:** Auto-accepted A; which sweeps run between builds is invisible implementation
  as long as the Cognito profile is byte-identical and the safety invariants hold.

### D4. Enforcement scope gate: manifest presence replaces the remote match

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** `build-queue-enforce.sh` today fires only when
  `git config --get remote.origin.url` matches `cognitoforms/cognito` and denies a hard-coded
  token set. Which repos get gated, and by what deny set, once the manifest exists?
- **Options:**
  - **A — Manifest presence is the sole scope gate:** the hook resolves the payload `cwd`'s git
    toplevel, looks for `.claude/skill-config/build-queue-ops.json`, and (a) absent → allow
    everything (fail-OPEN, byte-identical to a non-Cognito repo today); (b) present → compile
    the manifest's per-op `deny` patterns onto the existing `_CMD_START` segment anchor and
    deny with a redirect naming the op's `skill`. The Cognito remote match is deleted in the
    same change that lands Cognito's manifest (symlinked into all four worktrees via the
    `cognito-forms-B/C/D` aliases in `manifest.psd1`, so scope coverage is unchanged).
  - **B — Manifest-driven deny set, remote-match retained as a Cognito belt-and-suspenders:**
    same as A, plus: when the remote matches `cognitoforms/cognito` but the manifest is
    missing/unreadable, fall back to today's hard-coded deny set. Pros: an accidental symlink
    break (setup.ps1 drift, a fresh worktree before `bootstrap -Target Repos`) cannot silently
    disarm the only enforcement protecting the copy-lock/recycle invariants. Cons: two code
    paths; the legacy set must be kept in sync until deliberately retired.
  - **C — Central registry in `~/.claude` instead of per-repo manifests:** one file mapping
    repo paths → ops. Rejected: breaks the per-repo skill-config convention, breaks worktree
    aliasing for free, and makes repo onboarding a two-file edit.
- **Recommendation:** B. The queue exists because off-queue builds cause real damage
  (`build-queue-recycle-kills-concurrent-worktree-build` Vector B); a silently-disarmed hook is
  the worst failure mode of this migration, and the fallback costs ~15 lines. Retire the
  fallback in a later cleanup once the manifest has survived a few weeks of live worktrees. All
  invariants preserved verbatim: leading-anchored `BUILD_QUEUE_BYPASS=1`, `_WRAPPER_RE`
  exemption for `build-queue.ps1`, per-occurrence safe-variant suppression, segment-start
  anchoring (the invoke-vs-reference discrimination from
  `build-queue-outcome-opacity-and-inspect-deny`), deny-via-JSON, fail-OPEN with the
  `hook-error.json` breadcrumb.
- **Resolution:** OPEN — recommendation is B; awaiting operator confirmation (this decides
  which repos are gated and how enforcement can degrade).

### D5. Arbitration with the orchestrator-takeover contract (transient builds and the queue)

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** `long-build-ownership-guard.sh` (request-time, marker-free) denies a subagent's
  exact `tauri build` / `cargo build --release` / `npm run build` with the
  `LONG-BUILD-OWNERSHIP-TAKEOVER` signature; the orchestrator then re-launches via
  `lazy_core.run_transient_build` + `promote_artifact_atomically` (the Transient Build
  contract). If AlgoBooth registers those same builds as queue ops, two deny hooks cover one
  command and the orchestrator's re-launch could itself be denied by the generalized enforce
  hook — a ping-pong between two owners. Who owns a long build in a queue-governed repo?
- **Options:**
  - **A — Transient builds route THROUGH the queue:** the takeover path stays exactly as shipped
    (guard denies the subagent; orchestrator takes over), but the orchestrator's re-launch
    command becomes the queue wrapper invocation (`build-queue.ps1 -Op tauri-build ...`) run
    via `run_transient_build`'s detached spawn. No ping-pong by construction: the enforce
    hook's `_WRAPPER_RE` exemption already allows any command carrying `build-queue.ps1`, and
    the long-build guard never matches the wrapper form (its `_LONG_BUILD_RE` requires the bare
    binary at a command-start position). The queue contributes serialization + hygiene +
    banner; the transient contract contributes detachment + atomic artifact promotion. Ordering
    invariant: `long-build-ownership-guard.sh` stays registered BEFORE `build-queue-enforce.sh`
    in the `settings.json` PreToolUse chain so a subagent's raw `tauri build` always surfaces
    the takeover signature (ownership is the more fundamental correction; queue routing is the
    orchestrator's job after takeover).
  - **B — Two disjoint lanes:** long-build tokens are reserved to the ownership guard and MUST
    NOT appear in any manifest `deny` list (validated at manifest load); the queue governs only
    filtered-script ops. Pros: no interaction to reason about. Cons: AlgoBooth's heaviest
    builds stay off-queue — invisible to serialization and to the ETA/lanes sibling, and the
    recycle bug's Vector-B lesson ("off-queue builds are invisible to occupancy") recurs
    machine-wide by design.
  - **C — Queue absorbs the ownership guard:** delete `long-build-ownership-guard.sh` and let
    the enforce hook's redirect carry the takeover semantics. Rejected: the ownership guard is
    request-time and repo-agnostic (fires with no manifest present); folding it in couples
    subagent-ownership containment to manifest presence and regresses
    `long-build-and-runtime-ownership` M5.
  - **D — No new AlgoBooth build ops in v1:** generalize the wrapper/hook/hygiene mechanics and
    onboard only ops that are NOT long-build-guarded (e.g. a future AlgoBooth test op), leaving
    `tauri build`/`cargo build --release` purely under the transient contract until the
    composition is proven live. Pros: zero interaction risk in v1; the generalization still
    ships. Cons: defers the main AlgoBooth payoff.
  - **Recommendation:** A — one machine-global serializer, and the two contracts compose at a
  single, already-existing seam (the wrapper exemption). The subagent-visible behavior is
  unchanged (same takeover deny), the orchestrator gains the banner + `results/<seq>.json`
  evidence for long builds, and `Get-BuildQueueOccupancy` finally sees AlgoBooth builds — so a
  Cognito build finishing while a Tauri build runs correctly skips the compiler recycle. D is
  the fallback if live-fire testing exposes friction between `run_transient_build`'s awaiting
  and the wrapper's tail loop.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (this shapes how
  the autonomous pipeline runs AlgoBooth's long builds).

### D6. Cross-repo queue fairness

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** With multiple repos enqueuing, does one repo's burst starve another? Should the
  queue gain per-repo weighting?
- **Options:**
  - **A — Keep strict machine-global FIFO, document the property:** arrival order via the
    existing `seq.counter`, regardless of repo.
  - **B — Per-repo round-robin or weighted fairness:** new scheduling state, new reclaim
    interactions.
- **Recommendation:** A. This is a single-operator workstation; bursts come from one operator's
  own sessions, and the proven lock/reclaim machinery (`Test-ShouldReclaimLock` confirmed-dead
  gating, atomic provisional lock) reasons about a totally-ordered seq space. Latency shaping is
  the ETA/lanes sibling's job (`build-queue-eta-priority-lanes`), which layers admission order
  over the same single slot rather than changing fairness semantics here.
- **Resolution:** Auto-accepted A; no operator-visible change — FIFO is today's behavior,
  now stated as a documented property instead of an accident of scope.

### D7. v1 platform scope (PowerShell dependency on non-Windows hosts)

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** The queue is Windows-workstation-shaped end to end: `powershell.exe` detached
  processes, Windows Job Objects, Restart Manager P/Invoke, `\WindowsApps`-era pid semantics.
  The stub asks what happens on non-Windows hosts (cloud sessions, WSL).
- **Options:**
  - **A — Workstation-only v1, cloud exempt, stated honestly:** the manifest may exist in a
    repo checked out in a cloud session, but nothing routes through the queue there: the
    skills' wrapper invocation fails fast when `powershell.exe` is absent, the cloud pipeline
    variants (`/lazy-cloud`, `/lazy-batch-cloud`) already defer build/runtime work by design,
    and the enforce hook's deny set may simply never be armed off-workstation (a
    platform check beside the scope gate: no `powershell.exe` on PATH → allow). Document the
    boundary in the root `CLAUDE.md` build-queue rows.
  - **B — Port the wrapper to PowerShell 7 (`pwsh`) for cross-platform:** substantial rework of
    Job-Object/Restart-Manager hygiene (Windows-only APIs) for a host class that does not run
    heavy local builds today.
- **Recommendation:** A. Every consumer of the queue is a Windows workstation session; cloud
  sessions cannot run Cognito or Tauri release builds at all. B is speculative portability with
  a large hygiene-rewrite cost and no current consumer. Whether the hook should be
  silently inert or loudly inert off-workstation is the one operator-visible nuance — recommend
  silently inert (fail-OPEN family behavior).
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (v1 scope
  boundary).

### D8. Skill migration path (Cognito four + AlgoBooth siblings)

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How the thin skills change. Today each skill hard-codes both the op name and the
  exec path (`/mstest` runs `build-queue.ps1 -Op mstest -Exec "$REPO_ROOT/.claude/scripts/
  test-filtered.ps1"` — `repos/cognito-forms/.claude/skills/mstest/SKILL.md:30`).
- **Options:**
  - **A — Wrapper resolves `-Exec` from the manifest; skills pass only `-Op`:** `-Exec` becomes
    optional and, when omitted, is resolved from the manifest entry's `exec` (repo-relative,
    joined to the wrapper's already-computed `$worktree`). An explicit `-Exec` still overrides
    (back-compat; the four skills keep working unmodified during rollout, then drop their
    `-Exec` in a follow-up edit). AlgoBooth gets sibling skills under
    `repos/algobooth/.claude/skills/` named by its manifest ops (per D5's resolution), created
    with the same thin shape: construct command, run with a generous timeout, trust the banner,
    never `cat` the runner or `results/`.
  - **B — Skills read the manifest themselves:** duplicates manifest parsing into skill prose
    executed by an LLM — the opposite of script-owned determinism.
- **Recommendation:** A. One parser (the wrapper), zero behavior change for Cognito (same skill
  names, same banner contract, same `ValidateSet` semantics now sourced from the manifest with
  a clear error naming the repo's registered ops on a miss), and AlgoBooth onboarding becomes
  manifest + skills + `manifest.psd1` entry — exactly the "Adding a repo" shape
  `repos/CLAUDE.md` already documents.
- **Resolution:** Auto-accepted A; invocation plumbing with no operator-visible change for
  existing skills.

## User Experience

The "users" are the operator's interactive sessions and the autonomous pipeline's agents.

**Cognito (must be indistinguishable from today).** `/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`
behave byte-identically: same enqueue line, same live tail, same authoritative last-line banner
(`build-queue: seq=<N> op=<op> RESULT=<PASS|FAIL|NO-TESTS-MATCHED> ... (result_fidelity=...)`),
same deny messages from raw invocations, same `BUILD_QUEUE_BYPASS=1` escape.

**AlgoBooth (new).** Under the D5-A recommendation, a cycle subagent that runs a raw
`tauri build` still gets the `LONG-BUILD-OWNERSHIP-TAKEOVER` deny; the orchestrator's takeover
then routes through the queue:

```
build-queue: enqueued as seq=812 (op=tauri-build)
build-queue: waiting to claim slot...
build-queue: build started (pid=..., seq=812, log=...)
...build output tail...
build-queue: seq=812 op=tauri-build RESULT=PASS (result_fidelity=n/a)
```

An agent in an AlgoBooth worktree that tries a raw manifested op gets the manifest-driven deny
naming the correct skill (same message shape as the Cognito denies, `skill` field from D2).

**Onboarding a repo (operator workflow).** Create
`repos/<name>/.claude/skill-config/build-queue-ops.json` + thin skills in claude-config, add the
`manifest.psd1` entry, run `.\setup.ps1 bootstrap -Target Repos`. No wrapper/hook/hygiene edits.

**Failure modes.** Unknown `-Op` for the repo → wrapper exits 1 naming the manifest path and the
registered ops. Missing/unreadable manifest → wrapper refuses (an op cannot be resolved), the
hook allows (fail-OPEN; plus the D4-B Cognito legacy fallback). Non-Windows host → skills fail
fast on missing `powershell.exe`; the hook stays inert (per D7 resolution).

## Technical Design

```
repos/<name>/.claude/skill-config/build-queue-ops.json      (authored in claude-config, symlinked)
        │                                   │
        ▼ (ConvertFrom-Json)                ▼ (python json, via git-toplevel of payload cwd)
 build-queue.ps1 ──spawns──▶ build-queue-runner.ps1     build-queue-enforce.sh
  -Op resolved against       -OpKind <build|test>        deny set compiled from ops[*].deny
  manifest ops; -Exec        -Hygiene <profile-id>       onto the existing _CMD_START anchor;
  defaulted from ops[op]     replaces leaf-name          scope gate = manifest presence
        │                    inference; profile          (+ D4-B cognito legacy fallback)
        ▼                    registry in hygiene module
 ~/.claude/state/build-queue/{seq.counter,tickets/,active.lock,logs/,results/}   (UNCHANGED)
```

- **Manifest reader (PowerShell).** A `Get-BuildQueueOpsManifest -Worktree <root>` helper in
  `build-queue-hygiene.ps1` (the shared dot-sourced module): read
  `<root>/.claude/skill-config/build-queue-ops.json`, `ConvertFrom-Json`, validate `version` and
  required per-op fields, fail-open to `$null` (callers decide — the wrapper refuses on `$null`
  when `-Exec` was omitted; hygiene selection falls back to the `dotnet` profile for the four
  legacy op names and `none` otherwise). The wrapper already computes `$worktree` via
  `git rev-parse --show-toplevel` (`build-queue.ps1:76-79`).
- **Wrapper changes (`build-queue.ps1`).** Replace the static `ValidateSet` with runtime
  validation against the manifest (plus the four legacy names accepted for back-compat when no
  manifest exists — preserving current Cognito behavior even before its manifest lands). Thread
  two new runner params: `-OpKind` and `-Hygiene`. Everything else — seq allocation, ticket
  write, poll/claim loop, `Set-LockFileAtomic` provisional write, `Test-ShouldReclaimLock`
  confirmed-dead reclaim, live tail, read-merge-write of `results/<seq>.json`, occupancy-gated
  release recycle, `Format-BuildQueueBanner` last line — is untouched.
- **Runner changes (`build-queue-runner.ps1`).** `$isBuildOp`/`$isTestOp` come from `-OpKind`
  when supplied, falling back to the existing leaf-name regexes (`build-filtered\.ps1$` /
  `test-filtered\.ps1$`) so a legacy invocation is byte-identical. Hygiene calls dispatch on the
  profile record from `Get-HygieneProfile -Name $Hygiene`: `Stop-DllLockers` only when
  `reap_dll_lockers`; `Reset-CompilerServer` only when `recycle_compiler_server` (still
  occupancy-gated via `Get-BuildQueueOccupancy` — the gate is orthogonal to profiles and never
  bypassed); `Remove-PoisonedArtifacts` only for the `dotnet-dll` sweep kind; log-failure
  signature set selected per profile (`msbuild` signatures vs a `cargo` set:
  `error[E`, `^error:`, `warning: unused` never — signatures are failure-only). The
  `Test-BuildProducedNoOutput` positive classifier is profile-independent (a no-output exit-0
  build is a lie in any ecosystem) and stays wired for all `kind: build` ops.
- **Hygiene module (`build-queue-hygiene.ps1`).** Add `Get-HygieneProfile` (closed registry per
  D3) and the `rust-tauri`/`none` profiles. HARD invariants carried forward unchanged: fail-OPEN
  everywhere (`Get-SafeValue` idiom), no new name-targeted kills (Locked Decision 2), the
  VBCSCompiler exception stays the single sanctioned name-kill and is reachable only from the
  `dotnet` profile (Locked Decision 1), Job-Object reap remains unconditional for every op.
- **Enforcement hook (`build-queue-enforce.sh`).** The embedded Python gains a manifest loader:
  resolve the payload `cwd`'s git toplevel (one `git rev-parse` subprocess, mirroring the
  existing `git config` call it replaces), read the manifest, and compile each op's `deny`
  entries as `_CMD_START + re.escape-ish token pattern` — reusing the existing safe-variant
  suppression and the anchored `_FILTERED_SCRIPT_*` shapes for script-path denies. Preserved
  verbatim: `_BYPASS_RE` (leading-anchored), `_WRAPPER_RE` exemption, deny-via-JSON,
  `hook-error.json` breadcrumb, fail-OPEN on every error path. The known accepted blind spot (a
  command that `cd`s into another repo mid-command is judged by the dispatch-time cwd) is
  inherited, not widened. Regression cases land beside the existing suites in
  `user/scripts/test_hooks.py` (the established home for hook pytest coverage — it already
  pipes PreToolUse JSON into both `build-queue-enforce.sh` and `long-build-ownership-guard.sh`).
- **Takeover composition (per D5-A).** `long-build-ownership-guard.sh` is unchanged and ordered
  before `build-queue-enforce.sh` in `user/settings.json`. The orchestrator-side takeover prose
  (the `run_transient_build` call site) is updated so that, in a repo whose manifest registers
  the build, the spawned command is the queue wrapper invocation; `promote_artifact_atomically`
  still owns artifact promotion after the wrapper exits 0. No `lazy_core` signature changes —
  `run_transient_build` already takes an arbitrary command.
- **House invariants.** All state writes keep the existing atomic temp-then-`File.Replace`
  idioms (`Set-LockFileAtomic`, the results read-merge-write); the hook stays fail-OPEN with
  deny-via-JSON; no Python pipeline-state is touched (this feature is PowerShell/bash surface
  only, so `lazy_core._atomic_write` / coupled-pair parity are not in play); the manifest is
  read-only input to every consumer — nothing ever writes it at runtime.

## Implementation Phases

- **Phase 1 — Manifest contract + wrapper/runner generalization (no behavior change).**
  `Get-BuildQueueOpsManifest`, wrapper runtime op validation with legacy-four fallback,
  `-OpKind`/`-Hygiene` threading with leaf-name fallback. Cognito's
  `build-queue-ops.json` authored (four ops, `hygiene: dotnet`, current deny tokens) +
  `manifest.psd1` coverage via the existing skill-config symlink. Proven done: Pester
  (`build-queue-hygiene.Tests.ps1` extended) green; a live `/mstest` in a Cognito worktree
  produces a byte-identical banner and `results/<seq>.json`.
- **Phase 2 — Hygiene profile registry.** `Get-HygieneProfile` + `rust-tauri`/`none` profiles;
  runner dispatches on the profile record. Proven done: Pester cases pin (a) `dotnet` profile ≡
  current call pattern, (b) `rust-tauri` never calls `Reset-CompilerServer`/
  `Remove-PoisonedArtifacts`/`Stop-DllLockers`, (c) `Test-BuildProducedNoOutput` still fires for
  every `kind: build`.
- **Phase 3 — Enforcement generalization.** Manifest-driven deny set + presence scope gate +
  (per D4 resolution) the Cognito legacy fallback; remote-match special case removed. Proven
  done: `python3 -m pytest user/scripts/test_hooks.py` green with new cases — existing Cognito
  deny/allow matrix unchanged, a manifested AlgoBooth-style repo denies its registered raw ops,
  a manifest-less repo allows everything, an unreadable manifest allows (+ breadcrumb).
- **Phase 4 — AlgoBooth onboarding + takeover arbitration (per D5 resolution).** AlgoBooth
  manifest + sibling skills + orchestrator takeover routing through the wrapper;
  `settings.json` hook-order assertion. Proven done: hook-order pytest case; a live workstation
  `tauri build` takeover run producing a queue banner + result JSON while
  `promote_artifact_atomically` still gates the artifact swap (operator-verified once, like the
  live cold-boot smoke convention).
- **Phase 5 — Documentation sync.** Root `CLAUDE.md` build-queue rows, `user/hooks/CLAUDE.md`,
  `repos/CLAUDE.md` onboarding note, skill prose (drop `-Exec` per D8). Proven done:
  `lint-skills.py` green; doc rows name the manifest as the source of truth.

Estimate: ~4 sessions (Phases 1-2 one, Phase 3 one, Phase 4 one, Phase 5 folds into 4).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Cognito byte-identical | `/mstest` in a Cognito worktree post-migration | Same banner shape, same `results/<seq>.json` fields, same deny messages | Live run + Pester + `test_hooks.py` matrix |
| Manifest drives op table | `build-queue.ps1 -Op bogus` in a manifested repo | Exit 1 naming the manifest path + registered ops | Wrapper stderr |
| Hygiene profile isolation | `rust-tauri`-profiled op completes | No `Reset-CompilerServer`/DLL sweep invoked; Job-Object reap still runs | Pester call-pattern assertions |
| Occupancy gate survives profiles | `dotnet` op finishes while another live seq exists | `recycle_skipped_reason: concurrent-build-active` recorded | `results/<seq>.json` hygiene block |
| Enforcement fail-OPEN | Manifest unreadable / no python / non-git cwd | Command allowed; `hook-error.json` breadcrumb on internal error | `test_hooks.py` |
| No takeover ping-pong | Subagent raw `tauri build` in manifested AlgoBooth | One `LONG-BUILD-OWNERSHIP-TAKEOVER` deny; orchestrator wrapper invocation allowed (wrapper exemption) | `test_hooks.py` ordered-chain case |
| Bypass + wrapper exemptions intact | `BUILD_QUEUE_BYPASS=1 dotnet build`; wrapper invocation carrying `-Exec *-filtered.ps1` | Both allowed | `test_hooks.py` existing cases stay green |

## Open Questions

- **D1 — Manifest format/location:** JSON at `.claude/skill-config/build-queue-ops.json` vs a
  markdown table. Standing recommendation: JSON (one standard parser in each language; a
  two-bespoke-parser markdown table risks silent deny-surface drift under fail-OPEN).
- **D4 — Enforcement scope gate:** manifest presence as the sole gate vs manifest presence plus
  a Cognito remote-match legacy fallback for a broken/missing manifest. Standing recommendation:
  keep the fallback (a silently-disarmed hook re-opens the recycle bug's Vector B), retire later.
- **D5 — Transient-build arbitration:** route orchestrator-takeover long builds THROUGH the
  queue as manifested ops (one serializer, hygiene + banner + occupancy visibility) vs keeping
  two disjoint lanes vs deferring AlgoBooth build ops from v1. Standing recommendation: route
  through the queue (option A), with option D (defer) as the fallback if live-fire friction
  appears.
- **D7 — v1 platform scope:** workstation-only with cloud/non-Windows explicitly exempt and the
  hook silently inert off-Windows. Standing recommendation: yes — every queue consumer is a
  Windows workstation session; a `pwsh` port has no current consumer.
- **Deferred empirical checks (implementation-time, not decisions):** confirm
  `run_transient_build` composes cleanly with the wrapper's foreground tail (D5-A live-fire,
  Phase 4); confirm the cargo log-failure signature set against a real failing
  `cargo build --release` log before pinning it in the `rust-tauri` profile; verify the
  skill-config symlink exists in all four Cognito worktrees before deleting the remote-match
  (Phase 3 pre-flight).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the four build-queue bug hardenings (invariants that
  must not regress) and CI-system ops-registry prior art (per-repo pipeline manifests, closed
  hygiene/profile registries).
- `docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md` — Locked Decisions
  1-3 (VBCSCompiler single sanctioned name-kill; no name-glob kills; targeted poison sweep).
- `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build/SPEC.md` — occupancy gating,
  atomic provisional lock, Vector-B off-queue invisibility (the motivation for D5-A).
- `docs/bugs/build-queue-outcome-opacity-and-inspect-deny/SPEC.md` — banner contract +
  invoke-vs-reference segment anchoring the generalized hook must preserve.
- `docs/features/long-build-and-runtime-ownership/SPEC.md` — LD4/LD5 (takeover guard, one spawn
  primitive, two supervisory contracts) that D5 composes with.
- `user/scripts/build-queue.ps1`, `build-queue-runner.ps1`, `build-queue-hygiene.ps1`,
  `build-queue-status.ps1`; `user/hooks/build-queue-enforce.sh`,
  `long-build-ownership-guard.sh`; `user/scripts/test_hooks.py`,
  `build-queue-hygiene.Tests.ps1`.
