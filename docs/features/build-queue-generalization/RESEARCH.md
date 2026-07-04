# Research — Generalize Build-Queue Beyond Cognito

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

**The system being generalized (read in full for this research):**

- `user/scripts/build-queue.ps1` — the FIFO wrapper. Hard-coded repo identity:
  `[ValidateSet('msbuild','mstest','nxbuild','nxtest')]` on `-Op` (line 29). Everything else is
  already repo-agnostic: seq allocation under `seq.counter.lock`, ticket write, the poll/claim
  loop with `Set-LockFileAtomic` atomic provisional lock and `Test-ShouldReclaimLock`
  confirmed-dead reclaim, detached runner spawn, live tail, results read-merge-write, and the
  `Format-BuildQueueBanner` last-line emission. The worktree is resolved generically
  (`git rev-parse --show-toplevel`, lines 76-79).
- `user/scripts/build-queue-runner.ps1` — hard-coded repo identity in the op-kind inference:
  `$isBuildOp = $execLeaf -match 'build-filtered\.ps1$'` / `$isTestOp = $execLeaf -match
  'test-filtered\.ps1$'` (lines 84-85; note `client-build-filtered.ps1` also suffix-matches, so
  the nx ops ride the same paths today). All hygiene calls fire unconditionally for the inferred
  kind — there is no profile concept.
- `user/scripts/build-queue-hygiene.ps1` — the dot-sourced module where per-ecosystem behavior
  lives: `Reset-CompilerServer` (occupancy-gated VBCSCompiler recycle), `Remove-PoisonedArtifacts`
  (per-project bin/obj MZ-header DLL sweep via `Get-ProjectDlls`), `Stop-DllLockers` (Restart
  Manager reap, VBCSCompiler-exempt), `Test-BuildLogFailure` (MSBuild failure signatures:
  `Build FAILED`, `MSB3027`, `MSB3021`, `<N> Error(s)`), plus the ecosystem-neutral pieces
  (`Read-WithRetry`, `Test-BuildProducedNoOutput`, Job-Object lifecycle, `Get-BuildQueueOccupancy`,
  `Format-BuildQueueBanner`, `Get-HygieneHighlight`). The module doc-comment carries the two HARD
  requirements (fail-OPEN; no global process kills) the generalization must not weaken.
- `user/hooks/build-queue-enforce.sh` — repo identity in `_is_cognito_worktree` (git remote match
  on `cognitoforms/cognito`) and the hard-coded deny regex family (`_DOTNET_BUILD_RE`,
  `_DOTNET_TEST_RE`, `_NX_BUILD_TEST_RE`, `_FILTERED_SCRIPT_*_RE`) with `_CMD_START` segment
  anchoring, per-occurrence safe-variant suppression, leading-anchored `_BYPASS_RE`, and the
  `_WRAPPER_RE` exemption. The hook's Python is stdlib-only and already the natural place for a
  JSON manifest read.
- `user/hooks/long-build-ownership-guard.sh` + `lazy_core.spawn_detached` (~L8298) /
  `run_transient_build` (~L8385) / `promote_artifact_atomically` (~L8473) — the takeover contract
  D5 arbitrates with. The guard's `_LONG_BUILD_RE` matches only the bare binary at a command-start
  position, which is what makes the "route the takeover through the wrapper" composition free of
  ping-pong (the wrapper form never re-matches).
- `repos/cognito-forms/.claude/skills/{msbuild,mstest,nxbuild,nxtest}/SKILL.md` — the thin-caller
  shape and the banner-trust prose to replicate for AlgoBooth siblings.
- Tests: `user/scripts/build-queue-hygiene.Tests.ps1` (Pester; 76+ cases incl. per-project sweep
  fixtures) and `user/scripts/test_hooks.py` (pytest; ~121 tests, pipes PreToolUse JSON into the
  hooks — the answer to the "where do hook unit tests live" question the older bug specs carried
  as open).

**Hardening history (constraints, not suggestions):**

- `docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash` — Locked Decision 1 (the
  VBCSCompiler stop is the ONE sanctioned name-targeted kill), Locked Decision 2 (all other
  reaping is Job-Object-membership only; never widen to name globs), Locked Decision 3 (targeted
  poison sweep, not blanket clean). The profile registry (SPEC D3) exists to keep these
  reviewable in one closed place.
- `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build` — occupancy-gated recycle +
  atomic provisional lock + confirmed-dead reclaim; and the Vector-B finding that off-queue
  builds are invisible to occupancy, which is the strongest argument for SPEC D5-A (routing
  AlgoBooth long builds through the queue makes them occupancy-visible).
- `docs/bugs/build-queue-false-green-on-silent-build-failure` — `Get-ProjectDlls` per-project
  widening, `Read-WithRetry` flush-safe reads, `Test-BuildProducedNoOutput` (kept
  profile-independent in the SPEC: a no-output exit-0 build lies in any ecosystem).
- `docs/bugs/build-queue-outcome-opacity-and-inspect-deny` — the banner contract + the
  invoke-vs-reference `_CMD_START` anchoring; the generalized deny compiler must compile manifest
  tokens onto the same anchor or the false-positive class returns.
- `docs/bugs/build-queue-enforce-cd-prefix-bypass` — why deny is unanchored-across-segments but
  anchored-within-segment; also the still-open bypass-token ergonomics gap (leading-anchored
  `BUILD_QUEUE_BYPASS=1`), which this feature inherits deliberately (not widened, not fixed here).

**House patterns reused:** per-repo `skill-config/` overrides with symlink write-through
(`repos/CLAUDE.md`); closed registries for safety-bearing capability maps
(`lazy_core._HOST_CAPABILITY_REGISTRY` precedent for `Get-HygieneProfile`); fail-OPEN +
deny-via-JSON hook contract (`user/hooks/CLAUDE.md`); "Adding a repo" onboarding flow
(`manifest.psd1` + `setup.ps1 bootstrap -Target Repos`).

## External prior art & concepts

Training-knowledge, not live research:

- **Per-repo pipeline manifests.** GitHub Actions workflows, GitLab `.gitlab-ci.yml`, Buildkite
  pipelines: the ops a repo exposes are declared in a repo-local machine-readable file consumed
  by a generic runner. The SPEC's manifest is the same shape at workstation scale. All three use
  YAML/JSON, not prose tables — supporting D1's JSON recommendation for anything a machine
  enforces.
- **Concurrency groups / single-slot serialization.** GitHub Actions `concurrency.group` and
  Buildkite concurrency gates serialize expensive jobs machine/org-wide while leaving the job
  definition per-repo — the same split as machine-global state dir + per-repo manifest.
- **Toolchain-scoped hygiene.** Bazel's toolchain/`constraint_value` model and Nix's per-derivation
  isolation both express "what cleanup/isolation applies" as a closed, named selection rather
  than free-form flags — the D3 registry-over-flags argument. ccache/sccache docs likewise treat
  compiler-server lifecycle (the VBCSCompiler analog) as a per-toolchain concern.
- **Command-position matching in guards.** shellcheck-style token analysis and sudo's
  command-matching both distinguish an invoked binary from a mentioned path; the repo's
  `_CMD_START` anchor is the lightweight equivalent and is already regression-tested.

## Alternatives analysis

- **Manifest format (D1).** JSON vs markdown vs PSD1. The deciding factor is the two-language
  consumer set under a fail-OPEN hook: a bespoke markdown parser in PowerShell AND Python must
  agree forever, and any drift silently changes the deny surface with no error (fail-OPEN
  swallows it). JSON gives one standard parser per language and precedent in the queue's own
  state files. Markdown's only advantage (hand-editability) is minor for a file edited at repo
  onboarding time.
- **Enforcement scope gate (D4).** Manifest-presence-only is the cleanest end state, but the
  migration window matters: the hook is the only thing standing between a raw `dotnet build` and
  the copy-lock/recycle failure classes, and a broken symlink (fresh worktree before
  `setup.ps1 bootstrap`) would silently disarm it. The legacy remote-match fallback for Cognito
  costs ~15 lines and converts "silent disarm" into "unchanged legacy behavior". Central
  registry (option C) was rejected: it breaks the per-repo convention and the free worktree
  aliasing that `manifest.psd1` gives Cognito's B/C/D worktrees.
- **Takeover arbitration (D5).** The queue and the transient contract each own a property the
  other lacks (serialization+hygiene+banner vs detachment+atomic promotion). Composition (A)
  gets both by making the wrapper the command `run_transient_build` spawns; the wrapper
  exemption in the enforce hook plus the guard's bare-binary matcher mean neither hook fires on
  the composed invocation — the ping-pong is structurally impossible rather than
  convention-avoided. Two lanes (B) re-creates Vector-B invisibility for AlgoBooth's heaviest
  builds. Absorbing the guard into the queue (C) couples subagent containment to manifest
  presence — a regression of `long-build-and-runtime-ownership` M5, whose guard deliberately
  fires everywhere. Deferral (D) is the honest fallback if the live-fire check finds the
  wrapper's foreground tail fighting `run_transient_build`'s awaiting; it is sequencing, not
  design, which is why the SPEC keeps A as the recommendation with D named as fallback.
- **Fairness (D6).** Weighted/round-robin scheduling would touch the claim loop and the reclaim
  arbiter — the two most safety-audited code paths in the family — for a starvation scenario a
  single operator cannot realistically produce. FIFO-and-document wins on risk alone; latency
  concerns route to the ETA/lanes sibling, which changes admission order without touching
  reclaim.
- **Platform scope (D7).** The hygiene layer is Windows API (Job Objects, Restart Manager);
  a `pwsh` cross-platform port would have to stub or re-implement all of it for hosts (cloud)
  that never run these builds. Honest workstation-only scoping matches how the cloud pipeline
  variants already defer build/device work.

## Pitfalls & risks

- **Silent Cognito behavior drift.** The whole migration is only acceptable if the four skills
  are byte-identical. Mitigation: Phase 1 lands the manifest path with legacy fallbacks and a
  live `/mstest` verification; the Pester + `test_hooks.py` matrices pin the deny/allow and
  hygiene call patterns before the remote-match is deleted.
- **Deny-surface drift via manifest authoring.** A repo author can write an over-broad `deny`
  token (e.g. `cargo`) that blocks safe commands. Mitigation: tokens compile onto `_CMD_START`
  (invocation-position only), and the manifest loader rejects tokens matching a safe-list
  (mirroring `_DOTNET_SAFE_RE` suppression); worst case remains `BUILD_QUEUE_BYPASS=1`.
- **Hygiene-profile misassignment.** Pointing a .NET repo at `none` silently loses quarantine.
  Mitigation: profile selection is per-op in a reviewed, committed manifest; the `dotnet`
  fallback for the four legacy op names keeps Cognito safe even with a missing manifest.
- **Takeover live-fire friction (D5-A).** `run_transient_build` awaits its spawned command;
  the wrapper both waits in the claim loop and tails the log — a long queue wait could look like
  a hung build to the orchestrator's task tracking. Mitigation: the enqueue/position lines are
  emitted immediately (heartbeat), and Phase 4 includes a one-time operator-verified live run
  (same convention as the manual cold-boot smoke in `user/scripts/CLAUDE.md`).
- **Dead-weight risk.** If AlgoBooth onboarding stalls (D5-D fallback), the generalization must
  still pay for itself: it does, narrowly — the manifest kills three hard-coded surfaces and
  makes the enforcement testable per-repo — but the SPEC keeps AlgoBooth onboarding in-scope
  (Phase 4) so the feature is falsifiable: success = a second repo's ops running through the
  queue with profile-correct hygiene and zero Cognito regressions.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 manifest format/location | JSON at `.claude/skill-config/build-queue-ops.json` | High |
| D2 schema | Minimal five-field per-op entry + `version` | High |
| D3 hygiene selection | Closed profile registry in `build-queue-hygiene.ps1` | High |
| D4 enforcement scope | Manifest presence + Cognito remote-match legacy fallback | Medium-high |
| D5 takeover arbitration | Route transient builds through the queue (fallback: defer AlgoBooth build ops) | Medium |
| D6 fairness | Keep machine-global FIFO, document | High |
| D7 platform scope | Workstation-only v1; cloud/non-Windows exempt, hook inert | High |
| D8 skill migration | Wrapper resolves `-Exec` from manifest; explicit `-Exec` overrides | High |
