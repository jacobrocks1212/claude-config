# Lazy Queue — claude-config   (run active 🔒)

## Features (2)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⏸ Deferred | T3 |
| | status: Deferred · next: deferred · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 2 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | ⏸ Deferred | T3 |
| | status: Deferred · next: deferred · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (6)

| # | item | state | sev | aging |
|---|------|-------|------|------|
| 1 | [coupled-overlay-drift-gate-not-in-mandatory-gates](docs/bugs/coupled-overlay-drift-gate-not-in-mandatory-gates/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 2 | [adhoc-incident-friction-4cb10b](docs/bugs/adhoc-incident-friction-4cb10b/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 3 | [adhoc-plan-bug-no-guard-for-fixed-annotated-specs](docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs/SPEC.md) | Validate | — | 2026-07-18 |
| | status: Validate · phase 3/3 · next: run mcp-test · `/plan-bug`'s Step 0.4 status gate (and `bug-state.py`'s Concluded→plan-bug routing) key ONLY on the literal `**Status:**` line, so a `Concluded` SPEC whose fix already landed out-of-pipeline burns a full plan-bug dispatch re-planning work that is already done. | | | |
| 4 | [adhoc-containment-hook-e2big-fails-open-windows-native](docs/bugs/adhoc-containment-hook-e2big-fails-open-windows-native/SPEC.md) | ⬡ Needs-input | — | 2026-07-18 |
| | status: Needs-input · next: answer needs-input · The containment hook's ~32KB inline Python body, when handed to the interpreter via `python3 -c "$_LCC_PY"`, exceeds Windows CreateProcess's 32,767-char command-line limit (E2BIG), so the process fails to spawn and the hook falls through to its unconditional `exit 0` — silently disarming the lazy cycle-containment plane on Windows-native hosts. | | | |
| 5 | [adhoc-incident-hook-deny-19343d-r3](docs/bugs/adhoc-incident-hook-deny-19343d-r3/SPEC.md) | ⬡ Needs-input | — | 2026-07-19 |
| | status: Needs-input · next: answer needs-input | | | |
| 6 | [build-queue-timeout-kill-reaps-detached-runner](docs/bugs/build-queue-timeout-kill-reaps-detached-runner/SPEC.md) | Implement | — | 2026-07-10 |
| | status: Implement · phase 0/2 · next: execute plan · A foreground `build-queue.ps1` call that hits its Bash-tool timeout is tree-killed (exit 143), and the kill takes the supposedly-detached runner with it. | | | |

## Needs attention

- ⬡ adhoc-containment-hook-e2big-fails-open-windows-native — needs-input
- ⬡ adhoc-incident-hook-deny-19343d-r3 — needs-input
