# Lazy Queue — .   (run active 🔒)

## Features (8)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [friction-kpi-registry](docs/features/friction-kpi-registry/SPEC.md) | Validate | T1 |
| | status: Validate · phase 4/4 · next: run mcp-test · Every friction-reduction system (build-queue, containment hooks, halt handling, and anything designed later) declares its canonical KPIs — what friction it exists to reduce, the concrete signal sources, direction-of-goodness, baseline, and regression band — in a machine-readable, committed registry. | | |
| 2 | [parallel-worktree-batch-execution](docs/features/parallel-worktree-batch-execution/SPEC.md) | Validate | T1 |
| | status: Validate · phase 5/6 · next: run mcp-test · One repo = one lane today: every arbitration layer built so far (`refuse_run_start_clobber`, single-slot marker ownership, per-repo keyed state dirs, the containment hooks) exists to refuse *accidental* concurrency, and there is no sanctioned path to *deliberate* concurrency. | | |
| 3 | [harness-change-canary-rollback](docs/features/harness-change-canary-rollback/SPEC.md) | Research | T1 |
| | status: Research · next: research · Self-healing for the self-improvement loop: a shipped control-surface change enters a canary observation window during which its targeted signal and its surface's fresh incident streams are watched every run — more aggressively than steady-state review cadence. | | |
| 4 | [anti-overfit-design-gate](docs/features/anti-overfit-design-gate/SPEC.md) | Research | T2 |
| | status: Research · next: research · A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single incidents, weaken its own gates, and grade itself with metrics it controls. | | |
| 5 | [build-queue-generalization](docs/features/build-queue-generalization/SPEC.md) | Research | T2 |
| | status: Research · next: research · The machine-global FIFO build serializer (`build-queue.ps1` wrapper + self-releasing runner + hygiene module + outcome banner + enforcement hook) is hard-wired to one repo: a four-op `ValidateSet`, a `cognitoforms/cognito` git-remote scope gate, and .NET-specific hygiene (VBCSCompiler recycle, per-project DLL quarantine). | | |
| 6 | [build-queue-eta-priority-lanes](docs/features/build-queue-eta-priority-lanes/SPEC.md) | Research | T2 |
| | status: Research · next: research · Waiters on the machine-global build queue poll blind: the enqueue line and `build-queue-status.ps1` show position and elapsed wait, but no prediction of when a queued op will start or finish, and a 20-second filtered test run pays worst-case latency behind a full solution build. | | |
| 7 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | Spec | T3 |
| | status: Spec · next: spec · The repo has ~10 pytest suites, `lint-skills.py`, the parity audit, and a bash hook harness — and no `.github/workflows/`, so the harness's own integrity gates only run when someone remembers. | | |
| 8 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | Research | T3 |
| | status: Research · next: research · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (14)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [adhoc-cycle-begin-real-requires-sub-skill](docs/bugs/adhoc-cycle-begin-real-requires-sub-skill/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 2 | [skip-mcp-test-frontmatter-unquoted-colon](docs/bugs/skip-mcp-test-frontmatter-unquoted-colon/SPEC.md) | Validate | P0 |
| | status: Validate · next: run mcp-test · A `SKIP_MCP_TEST.md` waiver whose YAML frontmatter carries an **unquoted colon-space inside a value** (e.g. | | |
| 3 | [build-queue-enforce-cd-prefix-bypass](docs/bugs/build-queue-enforce-cd-prefix-bypass/SPEC.md) | Spec | — |
| | status: Spec · next: spec · The `build-queue-enforce.sh` PreToolUse hook fails open whenever a heavy build is chained behind a leading command (`cd "…" && dotnet build …`), because its deny regexes are anchored to the start of the command. | | |
| 4 | [build-queue-no-artifact-or-process-hygiene-on-crash](docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md) | Implement | — |
| | status: Implement · phase 0/5 · next: execute plan · A crashed or killed build leaves orphaned compiler/test child processes and a truncated 0-byte output artifact behind. | | |
| 5 | [build-queue-copy-lock-stale-dll-false-success](docs/bugs/build-queue-copy-lock-stale-dll-false-success/SPEC.md) | Implement | — |
| | status: Implement · phase 1/4 · next: execute plan · An MSB3027 copy-lock failure (obj/ rebuilt fresh, copy to bin/Debug blocked by a leftover locker) makes MSBuild log "Build FAILED" while still exiting 0. | | |
| 6 | [test-filtered-stale-check-hardcodes-bin-debug](docs/bugs/test-filtered-stale-check-hardcodes-bin-debug/SPEC.md) | Validate | — |
| | status: Validate · phase 0/1 · next: run mcp-test · The Phase-3 stale-DLL guard assumes every test project outputs to `bin\Debug\`, so it fires exit-4 "stale" on *every* `/mstest -TestDll "Cognito.Forms.UnitTests"` run — a false positive no rebuild can clear, which drives agents to bypass the sanctioned test path with hand-rolled `--no-build` scratchpad runners. | | |
| 7 | [build-queue-recycle-kills-concurrent-worktree-build](docs/bugs/build-queue-recycle-kills-concurrent-worktree-build/SPEC.md) | Implement | — |
| | status: Implement · phase 0/4 · next: execute plan · The crash-hygiene fix recycles VBCSCompiler machine-wide after **every** build, on the stated invariant that "the queue serializes builds, so no concurrent build's compiler server is ever killed." That invariant is violable in two ways — the stale-lock reclaim can admit a second concurrent build on a transiently-unreadable `active.lock`, and off-queue **bypass** builds run invisibly to serialization — so a build finishing in worktree A can `Stop-Process -Force` the VBCSCompiler that worktree B's build is actively using, producing MSB4166 / a partial compile / a `Build FAILED`-but-exit-0 → a stale or never-updated test DLL in worktree B. | | |
| 8 | [write-plan-plans-bypass-build-queue-skills](docs/bugs/write-plan-plans-bypass-build-queue-skills/SPEC.md) | Spec | — |
| | status: Spec · next: spec · The Cognito Forms variant of `/write-plan` bakes **raw** `dotnet build` / `dotnet test` / `npx nx test` commands into the plans it generates (both the orchestrator's in-loop gate steps and the dispatched lane agents' verification commands). | | |
| 9 | [build-queue-orphaned-result-on-wrapper-kill](docs/bugs/build-queue-orphaned-result-on-wrapper-kill/SPEC.md) | Validate | — |
| | status: Validate · phase 0/2 · next: run mcp-test · The queue wrapper writes `results/<seq>.json` and releases `active.lock` only after the detached build it is *tailing* exits. | | |
| 10 | [crlf-hook-blanket-enforce-mixed-eol](docs/bugs/crlf-hook-blanket-enforce-mixed-eol/SPEC.md) | Spec | — |
| | status: Spec · next: spec · `normalize-crlf.ps1` enforces a single blanket convention (CRLF on every non-`.sh` file) on the Cognito Forms repo, but the repo's *committed* EOL is mixed: `.cs` is CRLF, `NotificationTemplates/**/*.html` is LF. | | |
| 11 | [worktree-claude-doc-drift](docs/bugs/worktree-claude-doc-drift/SPEC.md) | Validate | — |
| | status: Validate · phase 3/3 · next: run mcp-test · Per-repo Claude docs are inconsistent across the Cognito Forms git worktrees: personal subdir `CLAUDE.local.md` files exist only in the main worktree, and team-owned tracked docs vary by branch — because the claude-config symlink manifest covers neither. | | |
| 12 | [build-queue-outcome-opacity-and-inspect-deny](docs/bugs/build-queue-outcome-opacity-and-inspect-deny/SPEC.md) | Validate | — |
| | status: Validate · phase 2/4 · next: run mcp-test · Agents routinely can't tell what a `/msbuild` `/mstest` `/nxbuild` `/nxtest` invocation actually did — pass, fail, zero-match, or broken log capture all surface as the same `exit_code=0` with suppressed output — so they try to inspect the runner script / results JSON / logs to disambiguate. | | |
| 13 | [adhoc-align-cycle-commit-count-with-budget-population](docs/bugs/adhoc-align-cycle-commit-count-with-budget-population/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 14 | [adhoc-derive-multi-commit-budget-from-dispatch-sites](docs/bugs/adhoc-derive-multi-commit-budget-from-dispatch-sites/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
