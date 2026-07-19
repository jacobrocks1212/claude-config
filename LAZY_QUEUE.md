# Lazy Queue — .   (run active 🔒)

## Features (2)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⏸ Deferred | T3 |
| | status: Deferred · next: deferred · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 2 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | ⏸ Deferred | T3 |
| | status: Deferred · next: deferred · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (19)

| # | item | state | sev | aging |
|---|------|-------|------|------|
| 1 | [merged-head-oracle-per-signal-supplement-churn](docs/bugs/merged-head-oracle-per-signal-supplement-churn/SPEC.md) | ⬡ Needs-input | — | 2026-07-19 |
| | status: Needs-input · phase 3/3 · next: answer needs-input · The merged-head actionability oracle re-adds a per-signal `DEFERRED.md` file-predicate every recurrence (R56/R57/R101/R102) because the FEATURE `compute_state` has no operator-defer branch, so the oracle's `is_dispatchable` re-inference is structurally blind to operator-deferred features. | | | |
| 2 | [adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move](docs/bugs/adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move/SPEC.md) | ⬡ Needs-input | — | 2026-07-18 |
| | status: Needs-input · next: answer needs-input · `detect_gate_weakening`'s per-file net-count reconciliation flags a false-positive `hit` when a behavior-preserving refactor MOVES a gate-refusal construct out of one file into a shared sibling within the same change. | | | |
| 3 | [decision-2-6-uncovered-row-reroute-to-mcp-test](docs/bugs/decision-2-6-uncovered-row-reroute-to-mcp-test/SPEC.md) | ⬡ Needs-input | — | 2026-07-18 |
| | status: Needs-input · next: answer needs-input · A completion cycle that reaches Step 10 with `VALIDATED.md` present but a matrix-incomplete PHASES.md unconditionally dispatches `__mark_complete__`, which the completion-coherence gate then refuses — with NO re-route back to `mcp-test` to finish (or author) the missing coverage. | | | |
| 4 | [decision-11-dispatch-time-forward-advance](docs/bugs/decision-11-dispatch-time-forward-advance/SPEC.md) | ⬡ Needs-input | — | 2026-07-18 |
| | status: Needs-input · phase 1/1 · next: answer needs-input · Implement turn-routing-enforcement NEEDS_INPUT decision 11: `forward_cycles` must advance at the real dispatch bracket, never on the every-turn inject-hook `--repeat-count` probe. | | | |
| 5 | [adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose](docs/bugs/_archive/adhoc-harness-gate-false-positives-on-generated-docs-and-phases-prose/SPEC.md) | Implement | — | 2026-07-18 |
| | status: Implement · phase 0/2 · next: execute plan · harness-gate.py runs its structural detectors over EVERY file in the diff range, so off-manifest generated docs (LAZY_QUEUE.md), PHASES.md prose rows, and unrelated bug/feature SPEC.md files swept into a range produce `gate_weakening=hit` / `overfit=flag` false positives — forcing redundant operator sign-off on plane-strengthening changes. | | | |
| 6 | [canary-revert-harden-2026-07-r54](docs/bugs/_archive/canary-revert-harden-2026-07-r54/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 7 | [canary-revert-harden-2026-07-r53](docs/bugs/_archive/canary-revert-harden-2026-07-r53/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 8 | [canary-revert-harden-2026-07-r52](docs/bugs/_archive/canary-revert-harden-2026-07-r52/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 9 | [canary-revert-harden-2026-07-r48](docs/bugs/_archive/canary-revert-harden-2026-07-r48/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 10 | [adhoc-unify-merged-head-coordinator-exemptions](docs/bugs/adhoc-unify-merged-head-coordinator-exemptions/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 11 | [adhoc-parity-audit-blind-to-compute-state-routing-branches](docs/bugs/adhoc-parity-audit-blind-to-compute-state-routing-branches/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 12 | [adhoc-plan-bug-no-guard-for-fixed-annotated-specs](docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 13 | [adhoc-containment-hook-e2big-fails-open-windows-native](docs/bugs/adhoc-containment-hook-e2big-fails-open-windows-native/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 14 | [canary-revert-harden-2026-07-r64](docs/bugs/_archive/canary-revert-harden-2026-07-r64/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 15 | [canary-revert-harden-2026-07-r44](docs/bugs/_archive/canary-revert-harden-2026-07-r44/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 16 | [canary-revert-harden-2026-07-r32](docs/bugs/_archive/canary-revert-harden-2026-07-r32/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 17 | [canary-revert-harden-2026-07-r31](docs/bugs/_archive/canary-revert-harden-2026-07-r31/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 18 | [adhoc-incident-hook-deny-19343d-r3](docs/bugs/adhoc-incident-hook-deny-19343d-r3/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 19 | [build-queue-timeout-kill-reaps-detached-runner](docs/bugs/build-queue-timeout-kill-reaps-detached-runner/SPEC.md) | Plan | — | 2026-07-10 |
| | status: Plan · next: plan · A foreground `build-queue.ps1` call that hits its Bash-tool timeout is tree-killed (exit 143), and the kill takes the supposedly-detached runner with it. | | | |

## Needs attention

- ⬡ merged-head-oracle-per-signal-supplement-churn — needs-input
- ⬡ adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move — needs-input
- ⬡ decision-2-6-uncovered-row-reroute-to-mcp-test — needs-input
- ⬡ decision-11-dispatch-time-forward-advance — needs-input
