# Lazy Queue — .   (run active 🔒)

## Features (2)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⏸ Deferred | T3 |
| | status: Deferred · next: deferred · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 2 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | ⏸ Deferred | T3 |
| | status: Deferred · next: deferred · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (20)

| # | item | state | sev | aging |
|---|------|-------|------|------|
| 1 | [merged-head-oracle-per-signal-supplement-churn](docs/bugs/merged-head-oracle-per-signal-supplement-churn/SPEC.md) | Validate | — | 2026-07-19 |
| | status: Validate · phase 3/3 · next: run mcp-test · The merged-head actionability oracle re-adds a per-signal `DEFERRED.md` file-predicate every recurrence (R56/R57/R101/R102) because the FEATURE `compute_state` has no operator-defer branch, so the oracle's `is_dispatchable` re-inference is structurally blind to operator-deferred features. | | | |
| 2 | [adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move](docs/bugs/adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 3 | [adhoc-process-friction-detector-counts-concurrent-session-commits](docs/bugs/_archive/adhoc-process-friction-detector-counts-concurrent-session-commits/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 4 | [decision-2-6-uncovered-row-reroute-to-mcp-test](docs/bugs/decision-2-6-uncovered-row-reroute-to-mcp-test/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 5 | [decision-11-dispatch-time-forward-advance](docs/bugs/decision-11-dispatch-time-forward-advance/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 6 | [adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose](docs/bugs/adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 7 | [canary-revert-harden-2026-07-r54](docs/bugs/canary-revert-harden-2026-07-r54/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 8 | [canary-revert-harden-2026-07-r53](docs/bugs/canary-revert-harden-2026-07-r53/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 9 | [canary-revert-harden-2026-07-r52](docs/bugs/canary-revert-harden-2026-07-r52/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 10 | [canary-revert-harden-2026-07-r48](docs/bugs/canary-revert-harden-2026-07-r48/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 11 | [adhoc-unify-merged-head-coordinator-exemptions](docs/bugs/adhoc-unify-merged-head-coordinator-exemptions/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 12 | [adhoc-parity-audit-blind-to-compute-state-routing-branches](docs/bugs/adhoc-parity-audit-blind-to-compute-state-routing-branches/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 13 | [adhoc-plan-bug-no-guard-for-fixed-annotated-specs](docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 14 | [adhoc-containment-hook-e2big-fails-open-windows-native](docs/bugs/adhoc-containment-hook-e2big-fails-open-windows-native/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 15 | [canary-revert-harden-2026-07-r64](docs/bugs/canary-revert-harden-2026-07-r64/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 16 | [canary-revert-harden-2026-07-r44](docs/bugs/canary-revert-harden-2026-07-r44/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 17 | [canary-revert-harden-2026-07-r32](docs/bugs/canary-revert-harden-2026-07-r32/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 18 | [canary-revert-harden-2026-07-r31](docs/bugs/canary-revert-harden-2026-07-r31/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 19 | [adhoc-incident-hook-deny-19343d-r3](docs/bugs/adhoc-incident-hook-deny-19343d-r3/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 20 | [build-queue-timeout-kill-reaps-detached-runner](docs/bugs/build-queue-timeout-kill-reaps-detached-runner/SPEC.md) | Plan | — | 2026-07-10 |
| | status: Plan · next: plan · A foreground `build-queue.ps1` call that hits its Bash-tool timeout is tree-killed (exit 143), and the kill takes the supposedly-detached runner with it. | | | |
