# Lazy Queue — .   (idle)

## Features (8)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [friction-kpi-registry](docs/features/friction-kpi-registry/SPEC.md) | Spec | T1 |
| | status: Spec · phase 4/4 · next: spec · Every friction-reduction system (build-queue, containment hooks, halt handling, and anything designed later) declares its canonical KPIs — what friction it exists to reduce, the concrete signal sources, direction-of-goodness, baseline, and regression band — in a machine-readable, committed registry. | | |
| 2 | [parallel-worktree-batch-execution](docs/features/parallel-worktree-batch-execution/SPEC.md) | Spec | T1 |
| | status: Spec · phase 5/6 · next: spec · One repo = one lane today: every arbitration layer built so far (`refuse_run_start_clobber`, single-slot marker ownership, per-repo keyed state dirs, the containment hooks) exists to refuse *accidental* concurrency, and there is no sanctioned path to *deliberate* concurrency. | | |
| 3 | [harness-change-canary-rollback](docs/features/harness-change-canary-rollback/SPEC.md) | Validate | T1 |
| | status: Validate · phase 3/4 · next: run mcp-test · Self-healing for the self-improvement loop: a shipped control-surface change enters a canary observation window during which its targeted signal and its surface's fresh incident streams are watched every run — more aggressively than steady-state review cadence. | | |
| 4 | [anti-overfit-design-gate](docs/features/anti-overfit-design-gate/SPEC.md) | ⬡ Needs-input | T2 |
| | status: Needs-input · next: answer needs-input · A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single incidents, weaken its own gates, and grade itself with metrics it controls. | | |
| 5 | [unknown](docs/features/unknown/SPEC.md) | Pending | T2 |
| | status: Pending · next: queue | | |
| 6 | [unknown](docs/features/unknown/SPEC.md) | Pending | T2 |
| | status: Pending · next: queue | | |
| 7 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⬡ Needs-input | T3 |
| | status: Needs-input · next: answer needs-input · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 8 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | Research | T3 |
| | status: Research · next: research · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (11)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [test-filtered-stale-check-hardcodes-bin-debug](docs/bugs/test-filtered-stale-check-hardcodes-bin-debug/SPEC.md) | Validate | — |
| | status: Validate · phase 0/1 · next: run mcp-test · The Phase-3 stale-DLL guard assumes every test project outputs to `bin\Debug\`, so it fires exit-4 "stale" on *every* `/mstest -TestDll "Cognito.Forms.UnitTests"` run — a false positive no rebuild can clear, which drives agents to bypass the sanctioned test path with hand-rolled `--no-build` scratchpad runners. | | |
| 2 | [unknown](docs/bugs/unknown/SPEC.md) | Pending | — |
| | status: Pending · next: queue | | |
| 3 | [unknown](docs/bugs/unknown/SPEC.md) | Pending | — |
| | status: Pending · next: queue | | |
| 4 | [build-queue-orphaned-result-on-wrapper-kill](docs/bugs/build-queue-orphaned-result-on-wrapper-kill/SPEC.md) | Validate | — |
| | status: Validate · phase 0/2 · next: run mcp-test · The queue wrapper writes `results/<seq>.json` and releases `active.lock` only after the detached build it is *tailing* exits. | | |
| 5 | [crlf-hook-blanket-enforce-mixed-eol](docs/bugs/crlf-hook-blanket-enforce-mixed-eol/SPEC.md) | Spec | — |
| | status: Spec · next: spec · `normalize-crlf.ps1` enforces a single blanket convention (CRLF on every non-`.sh` file) on the Cognito Forms repo, but the repo's *committed* EOL is mixed: `.cs` is CRLF, `NotificationTemplates/**/*.html` is LF. | | |
| 6 | [unknown](docs/bugs/unknown/SPEC.md) | Pending | — |
| | status: Pending · next: queue | | |
| 7 | [build-queue-outcome-opacity-and-inspect-deny](docs/bugs/build-queue-outcome-opacity-and-inspect-deny/SPEC.md) | Validate | — |
| | status: Validate · phase 2/4 · next: run mcp-test · Agents routinely can't tell what a `/msbuild` `/mstest` `/nxbuild` `/nxtest` invocation actually did — pass, fail, zero-match, or broken log capture all surface as the same `exit_code=0` with suppressed output — so they try to inspect the runner script / results JSON / logs to disambiguate. | | |
| 8 | [adhoc-align-cycle-commit-count-with-budget-population](docs/bugs/adhoc-align-cycle-commit-count-with-budget-population/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 9 | [adhoc-derive-multi-commit-budget-from-dispatch-sites](docs/bugs/adhoc-derive-multi-commit-budget-from-dispatch-sites/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 10 | [build-queue-no-artifact-or-process-hygiene-on-crash](docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md) | ⛔ Blocked | — |
| | status: Blocked · phase 0/5 · next: resolve blocker · A crashed or killed build leaves orphaned compiler/test child processes and a truncated 0-byte output artifact behind. | | |
| 11 | [build-queue-copy-lock-stale-dll-false-success](docs/bugs/build-queue-copy-lock-stale-dll-false-success/SPEC.md) | ⛔ Blocked | — |
| | status: Blocked · phase 1/4 · next: resolve blocker · An MSB3027 copy-lock failure (obj/ rebuilt fresh, copy to bin/Debug blocked by a leftover locker) makes MSBuild log "Build FAILED" while still exiting 0. | | |

## Needs attention

- ⬡ anti-overfit-design-gate — needs-input
- ⬡ claude-config-ci — needs-input
- ⛔ build-queue-no-artifact-or-process-hygiene-on-crash — blocked
- ⛔ build-queue-copy-lock-stale-dll-false-success — blocked
