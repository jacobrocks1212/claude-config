# Research Summary — Generalize Build-Queue Beyond Cognito

> Distillation of `RESEARCH.md` (internal desk research; Gemini deep research intentionally
> skipped by operator directive 2026-07-04) against the baseline SPEC. This file gates the
> downstream workflow (`/spec-phases` → `/plan-feature`).

## Key findings relevant to the baseline

- **The queue is already ~90% repo-agnostic.** Repo identity is baked in at exactly three seams:
  the wrapper's `-Op` `ValidateSet('msbuild','mstest','nxbuild','nxtest')`
  (`build-queue.ps1:29`), the runner's filename-suffix op-kind inference
  (`$execLeaf -match 'build-filtered\.ps1$'`, `build-queue-runner.ps1:84-85`), and the enforce
  hook's `cognitoforms/cognito` git-remote match (`_is_cognito_worktree`). Everything else — seq
  allocation, atomic provisional lock, confirmed-dead reclaim, detached runner, live tail, results
  read-merge-write, `Format-BuildQueueBanner` — is generic already. This narrows the change to a
  per-repo manifest + three seam edits, not a rewrite.
- **The hardening history is a constraint set, not a menu.** Four sibling bug fixes locked
  invariants the generalization must NOT regress: the VBCSCompiler stop is the ONE sanctioned
  name-targeted kill (LD1 of `build-queue-no-artifact-or-process-hygiene-on-crash`); all other
  reaping is Job-Object-membership only, never name globs (LD2); poison sweeps are targeted, not
  blanket (LD3); recycle is occupancy-gated (`build-queue-recycle-kills-concurrent-worktree-build`);
  `Test-BuildProducedNoOutput` is ecosystem-independent (a no-output exit-0 build lies everywhere).
- **Off-queue builds are invisible to occupancy (Vector B).** The recycle bug proved a build that
  does not route through the queue cannot be seen by `Get-BuildQueueOccupancy` — the strongest
  argument that AlgoBooth's `tauri build` / `cargo build --release` should route THROUGH the queue
  (SPEC D5-A) rather than stay under the separate takeover contract in its own lane.

## Prior art we should adopt

- **Per-repo pipeline manifests (GitHub Actions / GitLab CI / Buildkite).** All three declare a
  repo's ops in a repo-local machine-readable file consumed by a generic runner, and all three use
  YAML/JSON — never prose tables — for anything a machine enforces. Directly supports SPEC D1's
  JSON recommendation over a markdown table (which would need two bespoke parsers that must agree
  forever under a fail-OPEN hook).
- **Concurrency groups / single-slot serialization** (Actions `concurrency.group`, Buildkite
  gates): expensive jobs serialize machine/org-wide while the job definition stays per-repo — the
  exact split this feature wants (machine-global state dir + per-repo manifest).
- **Closed, named hygiene selection** (Bazel toolchains, Nix per-derivation isolation,
  ccache/sccache per-toolchain compiler-server lifecycle): express "what cleanup applies" as a
  closed named selection, not free-form flags. Supports SPEC D3's closed profile registry over
  inline per-op hygiene flags (which could compose unsafe combinations).
- **Command-position matching in guards** (shellcheck token analysis, sudo command matching):
  distinguish an invoked binary from a mentioned path — the repo's existing `_CMD_START` anchor is
  the lightweight equivalent the generalized deny compiler must keep compiling onto.

## Pitfalls / concerns to address

- **Silent Cognito behavior drift** — the migration is only acceptable if the four skills are
  byte-identical. Mitigation: Phase 1 lands the manifest with legacy fallbacks + a live `/mstest`
  verification; Pester + `test_hooks.py` matrices pin deny/allow and hygiene call patterns BEFORE
  the remote-match is deleted.
- **Deny-surface drift via manifest authoring** — an over-broad `deny` token (e.g. bare `cargo`)
  could block safe commands. Mitigation: tokens compile onto `_CMD_START` (invocation-position
  only) + a safe-list rejection in the loader; `BUILD_QUEUE_BYPASS=1` remains the escape.
- **Silently-disarmed hook during migration** — a broken skill-config symlink (fresh worktree
  before `setup.ps1 bootstrap`) would leave a manifest-presence-only gate inert, re-opening the
  recycle bug's Vector B. This is the motivation for SPEC D4-B's Cognito remote-match legacy
  fallback (~15 lines, retired later).
- **Takeover live-fire friction (D5-A)** — `run_transient_build` awaits its spawned command while
  the wrapper both waits in the claim loop and tails; a long queue wait could look like a hung
  build to orchestrator task tracking. Mitigation: enqueue/position lines emit immediately
  (heartbeat) + a one-time operator-verified live run in Phase 4; D5-D (defer AlgoBooth build ops)
  is the honest fallback if friction appears.

## Baseline decisions the research bears on

Research **confirmed** the baseline architecture (manifest + seam edits) and every mechanical
recommendation (D2 minimal schema, D3 closed registry, D6 FIFO, D8 wrapper-resolves-`-Exec`). It
surfaced **no new decisions** beyond the four the stub already flagged OPEN — but those four are
genuine product-behavior calls the operator must confirm before planning, so they are surfaced via
`NEEDS_INPUT.md` this cycle:

| SPEC decision | Research signal | Standing recommendation | Confidence |
|---------------|-----------------|-------------------------|------------|
| D1 manifest format/location | CI systems all use JSON/YAML for machine-enforced config | JSON at `.claude/skill-config/build-queue-ops.json` | High |
| D4 enforcement scope gate | silent-disarm is the worst failure mode of the migration | manifest presence + Cognito legacy fallback | Medium-high |
| D5 transient-build arbitration | Vector-B: off-queue builds invisible to occupancy | route through the queue (fallback: defer AlgoBooth ops) | Medium |
| D7 v1 platform scope | hygiene layer is Windows API; no cloud consumer runs these builds | workstation-only v1, hook inert off-Windows | High |

D2/D3/D6/D8 remain auto-accepted (mechanical-internal, single defensible option, no operator-visible
behavior change). See `NEEDS_INPUT.md` for the full decision context on D1/D4/D5/D7.
