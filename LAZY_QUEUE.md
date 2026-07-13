# Lazy Queue — .   (idle)

## Features (9)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [coupled-pair-generation](docs/features/coupled-pair-generation/SPEC.md) | Plan | T1 |
| | status: Plan · phase 3/4 · next: plan · The five coupled skill pairs (`lazy-batch`→{`lazy-bug-batch`, `lazy-batch-cloud`}, `lazy`→{`lazy-bug`, `lazy-cloud`}, `lazy-status`→`lazy-bug-status`) are maintained by hand-duplication plus a regex-presence parity audit: of the manifest's 129 audited heading entries, 112 (~87%) are `restated` — manually duplicated prose, ~306KB across the two derived whales alone — and every canonical edit is a 3-way edit (canonical + derived + 748-line manifest). | | |
| 2 | [lazy-core-package-decomposition](docs/features/lazy-core-package-decomposition/SPEC.md) | Plan | T1 |
| | status: Plan · next: plan · `lazy_core.py` is a 17,686-line single-module monolith with 169 commits since 2026-05-01 — the hottest file in the repo — so every intervention, however local, canaries against one file, and the PreToolUse hooks (`lazy_guard.py`/`lazy_inject.py`) pay a full-module import (~107 ms warm, ~705 ms cold) on every fire. | | |
| 3 | [anti-overfit-design-gate](docs/features/anti-overfit-design-gate/SPEC.md) | Implement | T2 |
| | status: Implement · phase 2/4 · next: execute plan · A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single incidents, weaken its own gates, and grade itself with metrics it controls. | | |
| 4 | [shared-hook-lib](docs/features/shared-hook-lib/SPEC.md) | Research | T2 |
| | status: Research · next: research · Extract the ~470 duplicated scaffolding lines (~20% of the 2,411-line `user/hooks/` plane) into a shared, fail-open-guarded pair — `hook-prelude.sh` (sourced bash: python resolution, SCRIPT_DIR derivation, no-python fallback breadcrumb) and `hook_lib.py` (allow/deny emitters, `_append_hook_event`, `_breadcrumb`, the shared `_ENV_PREFIX`/`_CMD_START` anchor regexes) — then migrate the seven python-bearing hooks one at a time, re-running the full 157-test `test_hooks.py` suite after each. | | |
| 5 | [cycle-prompt-environment-dialect](docs/features/cycle-prompt-environment-dialect/SPEC.md) | Implement | T2 |
| | status: Implement · phase 2/4 · next: execute plan · Add a compact (<2KB), host-conditional environment-dialect section to the emitted cycle prompt (`_components/lazy-batch-prompts/cycle-base-prompt.md`) so cycle SUBAGENTS stop paying the transcript-mined Windows/environment error tax: Git-Bash trailing-backslash quoting failures (267 across 82 sessions), Bash-`/tmp`-vs-Windows-python mismatches (~119, still recurring despite a MEMORY.md note — memory notes don't reach subagents), WSL-guessed `sys.path` imports (~36), `/mnt/c` paths on Git Bash (~25), `json.load`-on-empty-stdin tracebacks from the taught marker-probe idiom (94), and oversized-PHASES.md Read failures (114) that `phases-slice.py` already exists to prevent but the cycle prompt never mandates. | | |
| 6 | [lazy-batch-skill-deflation](docs/features/lazy-batch-skill-deflation/SPEC.md) | Implement | T2 |
| | status: Implement · phase 2/5 · next: execute plan · `user/skills/lazy-batch/SKILL.md` is 251,832 B / 1,597 lines (re-measured 2026-07-11) and growing ~30KB/week: 160KB (06-13) → 188KB (06-16) → 224KB (06-24) → 252KB (07-11), +57% in four weeks across 126 commits. | | |
| 7 | [bug-queue-aging-backpressure](docs/features/bug-queue-aging-backpressure/SPEC.md) | Validate | T2 |
| | status: Validate · phase 3/3 · next: run mcp-test · The harness bug backlog only accumulates. | | |
| 8 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⬡ Needs-input | T3 |
| | status: Needs-input · next: answer needs-input · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 9 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | Research | T3 |
| | status: Research · next: research · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (6)

| # | item | state | sev | aging |
|---|------|-------|------|------|
| 1 | [adhoc-incident-hook-deny-19343d-r3](docs/bugs/adhoc-incident-hook-deny-19343d-r3/SPEC.md) | Spec | — |  |
| | status: Spec · next: spec | | | |
| 2 | [long-build-and-build-queue-matcher-bypasses](docs/bugs/long-build-and-build-queue-matcher-bypasses/SPEC.md) | Plan | P2 |  |
| | status: Plan · phase 2/3 · next: plan · Empirically verified matcher-coverage gaps in two request-time guards: the long-build ownership guard allows every runner-prefixed / path-prefixed / string-wrapped form of the builds it exists to redirect (`npx tauri build`, `npm run tauri build` — the canonical Tauri invocation — `cargo tauri build`, absolute-path `cargo build --release`, `bash -c "..."`), and the build-queue enforce hook's wrapper allowlist is an **unanchored substring** checked before the deny scan, so any command merely *mentioning* `build-queue.ps1` bypasses the entire deny surface. | | | |
| 3 | [meta-dispatch-not-by-reference-and-ack-overpriced](docs/bugs/meta-dispatch-not-by-reference-and-ack-overpriced/SPEC.md) | Plan | P2 |  |
| | status: Plan · next: plan · The `@@lazy-ref` by-reference mechanism originally covered only CYCLE prompts, forcing the orchestrator to hand-transcribe multi-KB `--emit-dispatch` META prompts byte-exactly (12 "not script-emitted" + 4 "transcription slip" denials in one run). | | | |
| 4 | [build-queue-no-artifact-or-process-hygiene-on-crash](docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md) | ⛔ Blocked | — | 2026-06-30 |
| | status: Blocked · phase 0/5 · next: resolve blocker · A crashed or killed build leaves orphaned compiler/test child processes and a truncated 0-byte output artifact behind. | | | |
| 5 | [build-queue-copy-lock-stale-dll-false-success](docs/bugs/build-queue-copy-lock-stale-dll-false-success/SPEC.md) | ⛔ Blocked | — | 2026-07-01 |
| | status: Blocked · phase 1/4 · next: resolve blocker · An MSB3027 copy-lock failure (obj/ rebuilt fresh, copy to bin/Debug blocked by a leftover locker) makes MSBuild log "Build FAILED" while still exiting 0. | | | |
| 6 | [build-queue-timeout-kill-reaps-detached-runner](docs/bugs/build-queue-timeout-kill-reaps-detached-runner/SPEC.md) | Plan | — | 2026-07-10 |
| | status: Plan · next: plan · A foreground `build-queue.ps1` call that hits its Bash-tool timeout is tree-killed (exit 143), and the kill takes the supposedly-detached runner with it. | | | |

## Needs attention

- ⬡ claude-config-ci — needs-input
- ⛔ build-queue-no-artifact-or-process-hygiene-on-crash — blocked
- ⛔ build-queue-copy-lock-stale-dll-false-success — blocked
