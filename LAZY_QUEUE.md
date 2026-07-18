# Lazy Queue — .   (run active 🔒)

## Features (5)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [merged-head-actionability-oracle](docs/features/merged-head-actionability-oracle/SPEC.md) | Research | T0 |
| | status: Research · next: research · Replace the ever-growing category-enumerated merged-head exclude set with a single per-item "would `compute_state` dispatch this item right now?" oracle, so the NEXT non-dispatchable category cannot re-introduce a merged-head-diverged stall. | | |
| 2 | [subagent-wedge-backstop-hook](docs/features/subagent-wedge-backstop-hook/SPEC.md) | Research | T1 |
| | status: Research · phase 0/1 · next: research · A `SubagentStop` hook that mechanically catches a GENUINELY-WEDGED dispatched subagent — one that tries to stop/return with pending plan work still incomplete — and blocks its premature stop once, forcing it to commit + complete (or write `BLOCKED.md`) instead of returning dead and stranding the pipeline. | | |
| 3 | [shared-hook-lib](docs/features/shared-hook-lib/SPEC.md) | Research | T2 |
| | status: Research · next: research · Extract the ~470 duplicated scaffolding lines (~20% of the 2,411-line `user/hooks/` plane) into a shared, fail-open-guarded pair — `hook-prelude.sh` (sourced bash: python resolution, SCRIPT_DIR derivation, no-python fallback breadcrumb) and `hook_lib.py` (allow/deny emitters, `_append_hook_event`, `_breadcrumb`, the shared `_ENV_PREFIX`/`_CMD_START` anchor regexes) — then migrate the seven python-bearing hooks one at a time, re-running the full 157-test `test_hooks.py` suite after each. | | |
| 4 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⬡ Needs-input | T3 |
| | status: Needs-input · next: answer needs-input · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 5 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | Research | T3 |
| | status: Research · next: research · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (17)

| # | item | state | sev | aging |
|---|------|-------|------|------|
| 1 | [canary-revert-harden-2026-07-r54](docs/bugs/canary-revert-harden-2026-07-r54/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 2 | [canary-revert-harden-2026-07-r53](docs/bugs/canary-revert-harden-2026-07-r53/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 3 | [canary-revert-harden-2026-07-r52](docs/bugs/canary-revert-harden-2026-07-r52/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 4 | [canary-revert-harden-2026-07-r48](docs/bugs/canary-revert-harden-2026-07-r48/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 5 | [adhoc-unify-merged-head-coordinator-exemptions](docs/bugs/adhoc-unify-merged-head-coordinator-exemptions/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 6 | [adhoc-parity-audit-blind-to-compute-state-routing-branches](docs/bugs/adhoc-parity-audit-blind-to-compute-state-routing-branches/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 7 | [adhoc-bug-pickup-routes-superseded-specs](docs/bugs/adhoc-bug-pickup-routes-superseded-specs/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 8 | [adhoc-plan-bug-no-guard-for-fixed-annotated-specs](docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 9 | [adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker](docs/bugs/adhoc-lazy-core-tests-not-isolated-from-live-cycle-marker/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 10 | [adhoc-cli-surface-registry-stale-set-independent](docs/bugs/adhoc-cli-surface-registry-stale-set-independent/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 11 | [adhoc-containment-hook-e2big-fails-open-windows-native](docs/bugs/adhoc-containment-hook-e2big-fails-open-windows-native/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 12 | [canary-revert-harden-2026-07-r64](docs/bugs/canary-revert-harden-2026-07-r64/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 13 | [canary-revert-harden-2026-07-r44](docs/bugs/canary-revert-harden-2026-07-r44/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 14 | [canary-revert-harden-2026-07-r32](docs/bugs/canary-revert-harden-2026-07-r32/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 15 | [canary-revert-harden-2026-07-r31](docs/bugs/canary-revert-harden-2026-07-r31/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 16 | [adhoc-incident-hook-deny-19343d-r3](docs/bugs/adhoc-incident-hook-deny-19343d-r3/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 17 | [build-queue-timeout-kill-reaps-detached-runner](docs/bugs/build-queue-timeout-kill-reaps-detached-runner/SPEC.md) | Plan | — | 2026-07-10 |
| | status: Plan · next: plan · A foreground `build-queue.ps1` call that hits its Bash-tool timeout is tree-killed (exit 143), and the kill takes the supposedly-detached runner with it. | | | |

## Needs attention

- ⬡ claude-config-ci — needs-input
