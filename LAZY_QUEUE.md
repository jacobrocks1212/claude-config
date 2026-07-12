# Lazy Queue — claude-config   (run active 🔒)

## Features (19)

| # | item | state | tier |
|---|------|-------|------|
| 1 | [friction-kpi-registry](docs/features/friction-kpi-registry/SPEC.md) | Spec | T1 |
| | status: Spec · phase 4/4 · next: spec · Every friction-reduction system (build-queue, containment hooks, halt handling, and anything designed later) declares its canonical KPIs — what friction it exists to reduce, the concrete signal sources, direction-of-goodness, baseline, and regression band — in a machine-readable, committed registry. | | |
| 2 | [parallel-worktree-batch-execution](docs/features/parallel-worktree-batch-execution/SPEC.md) | Spec | T1 |
| | status: Spec · phase 5/6 · next: spec · One repo = one lane today: every arbitration layer built so far (`refuse_run_start_clobber`, single-slot marker ownership, per-repo keyed state dirs, the containment hooks) exists to refuse *accidental* concurrency, and there is no sanctioned path to *deliberate* concurrency. | | |
| 3 | [harness-change-canary-rollback](docs/features/harness-change-canary-rollback/SPEC.md) | Validate | T1 |
| | status: Validate · phase 3/4 · next: run mcp-test · Self-healing for the self-improvement loop: a shipped control-surface change enters a canary observation window during which its targeted signal and its surface's fresh incident streams are watched every run — more aggressively than steady-state review cadence. | | |
| 4 | [state-cli-contract-registry](docs/features/state-cli-contract-registry/SPEC.md) | Research | T1 |
| | status: Research · next: research · The state-script CLI surface (86 flags on `lazy-state.py`, 75 on `bug-state.py`, plus the smaller pipeline tools) has no machine-readable contract: nothing lints skill/component prose against the real argparse surface, so agents invoke flags that don't exist (~46 transcript-mined argparse usage errors across ~25 sessions, including 10 invocations of a `surface_resolver.py --route-mcp-test-tier` flag that exists nowhere in the tree), and the only defenses are prose Gotcha blocks in `user/scripts/CLAUDE.md`. | | |
| 5 | [mechanize-prose-only-orchestrator-contracts](docs/features/mechanize-prose-only-orchestrator-contracts/SPEC.md) | Research | T1 |
| | status: Research · next: research · Convert the four highest-risk `/lazy-batch` contracts that exist only as SKILL.md prose into mechanical enforcement points: (a) the guard pins the script-selected `model` tier onto every registered Agent dispatch instead of trusting the orchestrator to copy `cycle_model`; (b) the §1d.5 post-cycle input-audit becomes a state-recorded obligation that withholds the next cycle until discharged; (c) mid-run AskUserQuestion answers become a script-owned decision record that the emitted apply-resolution prompt embeds mechanically; (d) script-side push notification extends beyond halts to parks, budget events, and flushes. | | |
| 6 | [coupled-pair-generation](docs/features/coupled-pair-generation/SPEC.md) | Research | T1 |
| | status: Research · next: research · The five coupled skill pairs (`lazy-batch`→{`lazy-bug-batch`, `lazy-batch-cloud`}, `lazy`→{`lazy-bug`, `lazy-cloud`}, `lazy-status`→`lazy-bug-status`) are maintained by hand-duplication plus a regex-presence parity audit: of the manifest's 129 audited heading entries, 112 (~87%) are `restated` — manually duplicated prose, ~306KB across the two derived whales alone — and every canonical edit is a 3-way edit (canonical + derived + 748-line manifest). | | |
| 7 | [lazy-core-package-decomposition](docs/features/lazy-core-package-decomposition/SPEC.md) | Research | T1 |
| | status: Research · next: research · `lazy_core.py` is a 17,686-line single-module monolith with 169 commits since 2026-05-01 — the hottest file in the repo — so every intervention, however local, canaries against one file, and the PreToolUse hooks (`lazy_guard.py`/`lazy_inject.py`) pay a full-module import (~107 ms warm, ~705 ms cold) on every fire. | | |
| 8 | [anti-overfit-design-gate](docs/features/anti-overfit-design-gate/SPEC.md) | ⬡ Needs-input | T2 |
| | status: Needs-input · next: answer needs-input · A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single incidents, weaken its own gates, and grade itself with metrics it controls. | | |
| 9 | [unknown](docs/features/unknown/SPEC.md) | Pending | T2 |
| | status: Pending · next: queue | | |
| 10 | [unknown](docs/features/unknown/SPEC.md) | Pending | T2 |
| | status: Pending · next: queue | | |
| 11 | [shared-hook-lib](docs/features/shared-hook-lib/SPEC.md) | Research | T2 |
| | status: Research · next: research · Extract the ~470 duplicated scaffolding lines (~20% of the 2,411-line `user/hooks/` plane) into a shared, fail-open-guarded pair — `hook-prelude.sh` (sourced bash: python resolution, SCRIPT_DIR derivation, no-python fallback breadcrumb) and `hook_lib.py` (allow/deny emitters, `_append_hook_event`, `_breadcrumb`, the shared `_ENV_PREFIX`/`_CMD_START` anchor regexes) — then migrate the seven python-bearing hooks one at a time, re-running the full 157-test `test_hooks.py` suite after each. | | |
| 12 | [skill-config-schema-and-reference-lint](docs/features/skill-config-schema-and-reference-lint/SPEC.md) | Research | T2 |
| | status: Research · next: research · No schema or required-file contract exists for `repos/<name>/.claude/skill-config/` (algobooth: 21 files; cognito-forms: 16; cognito-docs: none) — missing-file semantics are per-reference prose conventions, with no way to distinguish intended-absent from broken. | | |
| 13 | [cycle-prompt-environment-dialect](docs/features/cycle-prompt-environment-dialect/SPEC.md) | Research | T2 |
| | status: Research · next: research · Add a compact (<2KB), host-conditional environment-dialect section to the emitted cycle prompt (`_components/lazy-batch-prompts/cycle-base-prompt.md`) so cycle SUBAGENTS stop paying the transcript-mined Windows/environment error tax: Git-Bash trailing-backslash quoting failures (267 across 82 sessions), Bash-`/tmp`-vs-Windows-python mismatches (~119, still recurring despite a MEMORY.md note — memory notes don't reach subagents), WSL-guessed `sys.path` imports (~36), `/mnt/c` paths on Git Bash (~25), `json.load`-on-empty-stdin tracebacks from the taught marker-probe idiom (94), and oversized-PHASES.md Read failures (114) that `phases-slice.py` already exists to prevent but the cycle prompt never mandates. | | |
| 14 | [plan-structure-authoring-gate](docs/features/plan-structure-authoring-gate/SPEC.md) | Research | T2 |
| | status: Research · next: research · Add emit-time structural validation to plan-part and PHASES.md authoring: when `/write-plan` or `/spec-phases` write these files, a deterministic validator refuses structural defects the harness itself currently permits — missing per-WU `- [ ] WU-N` checklists, verification rows outside a recognized Runtime Verification subsection, unfilled template/boilerplate rows counted as work, and plan-part series that contradict declared dependency order. | | |
| 15 | [efficacy-signal-integrity](docs/features/efficacy-signal-integrity/SPEC.md) | Research | T2 |
| | status: Research · next: research · The measurement plane of the self-improving harness, layered on the two 2026-07-11 capture/scope bug fixes: (a) sub-signal targets (`event:gate-refusal/<signature>`) so co-shipped hardening rounds measure disjoint signals instead of being confounder-capped INCONCLUSIVE by construction; (b) a canary staleness alarm so 19 open canaries cannot silently mass-expire into `closed-clean (no-data)`; (c) scorecard freshness + per-row signal VANTAGE so NO-DATA distinguishes "wrong repo/machine to observe this" from "signal genuinely absent", and the scorecard regenerates where its registry actually lives. | | |
| 16 | [lazy-batch-skill-deflation](docs/features/lazy-batch-skill-deflation/SPEC.md) | Research | T2 |
| | status: Research · next: research · `user/skills/lazy-batch/SKILL.md` is 251,832 B / 1,597 lines (re-measured 2026-07-11) and growing ~30KB/week: 160KB (06-13) → 188KB (06-16) → 224KB (06-24) → 252KB (07-11), +57% in four weeks across 126 commits. | | |
| 17 | [bug-queue-aging-backpressure](docs/features/bug-queue-aging-backpressure/SPEC.md) | Research | T2 |
| | status: Research · next: research · The harness bug backlog only accumulates. | | |
| 18 | [claude-config-ci](docs/features/claude-config-ci/SPEC.md) | ⬡ Needs-input | T3 |
| | status: Needs-input · next: answer needs-input · The harness ships ~18 pytest suites, `lint-skills.py`, the parity audit, the doc-drift linter, a skill-projection check, and a Pester/PSScriptAnalyzer PowerShell family — but no `.github/workflows/`, so those integrity gates only run when someone remembers to run them locally. | | |
| 19 | [native-android-pipeline-steering](docs/features/native-android-pipeline-steering/SPEC.md) | Research | T3 |
| | status: Research · next: research · A real mobile client on the `mobile-queue-control` foundation: browse every lazy-enabled repo's queues, drill into SPECs and halt sentinels, and — the point — **write back** from the phone: answer `NEEDS_INPUT.md` decisions, resolve `BLOCKED.md` halts, and reorder/enqueue the queue. | | |

## Bugs (29)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [run-end-gate-refusals-no-telemetry-event](docs/bugs/run-end-gate-refusals-no-telemetry-event/SPEC.md) | Validate | low |
| | status: Validate · phase 1/1 · next: run mcp-test · The state scripts' `--run-end` gates refuse (exit 1, marker kept) — unacked-hardening-debt, the new efficacy-flush-missing gate, and checkpoint-authorization — WITHOUT emitting a telemetry event, so those refusals are invisible to the efficacy loop that measures harness health. | | |
| 2 | [live-settings-split-brain-disarms-enforcement-plane](docs/bugs/live-settings-split-brain-disarms-enforcement-plane/SPEC.md) | Spec | P0 |
| | status: Spec · next: spec · The live `~/.claude/settings.json` on this laptop is an untracked plain file registering ONLY the two turn-routing hooks, while the tracked `user/settings.json` registers the ~10 OTHER enforcement hooks and has NEVER carried the dispatch guard. | | |
| 3 | [interventions-telemetry-repo-scope-split-brain](docs/bugs/interventions-telemetry-repo-scope-split-brain/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · Intervention records live in claude-config (`docs/interventions/`, 25 records), but the telemetry that must grade them lives in the TARGET repo's keyed state dir (AlgoBooth: 1,248 events / 32 runs). | | |
| 4 | [hardening-intervention-records-unmeasurable-or-missing](docs/bugs/hardening-intervention-records-unmeasurable-or-missing/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · The `/harden-harness` Step-4 capture contract produces records the evaluator can never grade: two records name telemetry event types that do not exist in the emit vocabulary (accepted silently — `record_intervention` validates nothing), 17 of 25 records are `target_signal: undeclared`, and round-vs-record coverage is prose-only self-attestation — a round's "Intervention record: none" exemption line is checked by no one. | | |
| 5 | [legacy-tool-input-env-hooks-dead](docs/bugs/legacy-tool-input-env-hooks-dead/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · `block-terminal-kill.sh` and `block-work-repo-git-push.sh` — both registered in the tracked `user/settings.json` PreToolUse Bash chain — read `$TOOL_INPUT_command`, an environment variable the hook interface never populates (the interface is stdin JSON). | | |
| 6 | [powershell-tool-bypasses-bash-matched-guards](docs/bugs/powershell-tool-bypasses-bash-matched-guards/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · Every command guard is matched on tool `"Bash"` only, and the three inline second layers early-allow any non-Bash tool. | | |
| 7 | [guard-fail-open-leaves-no-trace](docs/bugs/guard-fail-open-leaves-no-trace/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · Every PreToolUse hook fails open by documented contract (a non-zero exit is a hard harness error), but fail-open **observability** is inconsistent-to-absent: the no-python path is silent across the entire guard plane, one bash-side breadcrumb writer targets an unset variable and has never worked, two enforcement hooks have no error-path trace at all, and the severest failure class (python unavailable) is exactly the one the python-side appenders cannot record. | | |
| 8 | [long-build-and-build-queue-matcher-bypasses](docs/bugs/long-build-and-build-queue-matcher-bypasses/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · Empirically verified matcher-coverage gaps in two request-time guards: the long-build ownership guard allows every runner-prefixed / path-prefixed / string-wrapped form of the builds it exists to redirect (`npx tauri build`, `npm run tauri build` — the canonical Tauri invocation — `cargo tauri build`, absolute-path `cargo build --release`, `bash -c "..."`), and the build-queue enforce hook's wrapper allowlist is an **unanchored substring** checked before the deny scan, so any command merely *mentioning* `build-queue.ps1` bypasses the entire deny surface. | | |
| 9 | [mark-complete-partial-apply-noop-unrecoverable](docs/bugs/mark-complete-partial-apply-noop-unrecoverable/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · `apply_pseudo`'s `__mark_complete__`/`__mark_fixed__` branch performs a multi-file write sequence (receipt → SPEC flip → PHASES flip → sentinel cleanup → queue trim → ROADMAP strike) where each write is individually atomic but the SEQUENCE is not — and the branch-entry idempotency check noops on RECEIPT-EXISTS ALONE. | | |
| 10 | [production-sentinel-writes-bypass-atomic-write](docs/bugs/production-sentinel-writes-bypass-atomic-write/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · `user/scripts/CLAUDE.md` states all queue/marker/sentinel writes go through `lazy_core._atomic_write` — but both state scripts write production BLOCKED.md / NEEDS_INPUT.md / brief / ROADMAP files via bare `path.write_text()`. | | |
| 11 | [stale-runtime-health-200-false-blocked](docs/bugs/stale-runtime-health-200-false-blocked/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · The Step-9 dispatch bar is `GET /health == 200`, but the running Tauri binary + sidecar bundle routinely predates the code under test — so `/mcp-test` reports genuine-looking failures against a pre-fix binary, burns `retry_count` on non-defects, and forces the orchestrator to hand-invent restart rituals. | | |
| 12 | [mcp-validation-peels-one-seam-per-loop](docs/bugs/mcp-validation-peels-one-seam-per-loop/SPEC.md) | Spec | P1 |
| | status: Spec · next: spec · When `/mcp-test` fails, the only route back to validation is BLOCKED → blocked-resolve → add-phase → write-plan → execute-plan → mcp-test — a 4–6-Opus-dispatch loop (usually plus a multi-minute Rust rebuild) — and because full seam enumeration is mandated only at `retry_count >= 2` while every corrective phase is scoped to the single observed failure, each re-validation discovers only the NEXT broken seam. | | |
| 13 | [completion-gate-refusal-opacity](docs/bugs/completion-gate-refusal-opacity/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · `__mark_complete__`'s precondition gate (`--verify-ledger`) refuses with only a boolean `failing_check` name — `deliverables_done` without the unchecked rows, `clean_tree` without the dirty files, `head_matches_origin` without the shas — so agents use the gate itself as discovery, probing repeatedly per feature (184 gate-refusal tool errors across 48+ mined sessions). | | |
| 14 | [loop-detector-false-positives-probes-and-cross-run-state](docs/bugs/loop-detector-false-positives-probes-and-cross-run-state/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · The `repeat_count` / `step_repeat_count` loop tripwires false-fired on benign churn (probes, denied dispatches, resolved blockers) and their state — plus the deny ledger — survives `--run-end`, so a fresh run can open with a false-loop T6 warning and a mandatory hardening dispatch for a PRIOR-RUN denial. | | |
| 15 | [meta-dispatch-not-by-reference-and-ack-overpriced](docs/bugs/meta-dispatch-not-by-reference-and-ack-overpriced/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · The `@@lazy-ref` by-reference mechanism originally covered only CYCLE prompts, forcing the orchestrator to hand-transcribe multi-KB `--emit-dispatch` META prompts byte-exactly (12 "not script-emitted" + 4 "transcription slip" denials in one run). | | |
| 16 | [fixed-bugs-unarchived-fsck](docs/bugs/fixed-bugs-unarchived-fsck/SPEC.md) | Spec | P2 |
| | status: Spec · next: spec · 18 directories under `docs/bugs/` carry `**Status:** Fixed` but sit OUTSIDE `docs/bugs/_archive/`. | | |
| 17 | [skills-plane-hygiene-debris](docs/bugs/skills-plane-hygiene-debris/SPEC.md) | Spec | P3 |
| | status: Spec · next: spec · The skills plane has accumulated hygiene debris that nothing gates: two git-tracked `sh.exe.stackdump` crash dumps (no `*.stackdump` gitignore), three `_components/` files referenced by nothing, and emit-mapping rows in the lazy status/wrapper skills that still present the retro step as a live pipeline emission eight-plus weeks after the operator unwired it. | | |
| 18 | [coord-lock-no-stale-reclaim](docs/bugs/coord-lock-no-stale-reclaim/SPEC.md) | Spec | P3 |
| | status: Spec · next: spec · `lazy_coord.acquire_lock` is an `os.mkdir` spin lock with a ~10s timeout — but the lock directory carries NO holder metadata (no pid, no timestamp) and there is NO reclamation path. | | |
| 19 | [test-filtered-stale-check-hardcodes-bin-debug](docs/bugs/test-filtered-stale-check-hardcodes-bin-debug/SPEC.md) | Validate | — |
| | status: Validate · phase 0/1 · next: run mcp-test · The Phase-3 stale-DLL guard assumes every test project outputs to `bin\Debug\`, so it fires exit-4 "stale" on *every* `/mstest -TestDll "Cognito.Forms.UnitTests"` run — a false positive no rebuild can clear, which drives agents to bypass the sanctioned test path with hand-rolled `--no-build` scratchpad runners. | | |
| 20 | [unknown](docs/bugs/unknown/SPEC.md) | Pending | — |
| | status: Pending · next: queue | | |
| 21 | [unknown](docs/bugs/unknown/SPEC.md) | Pending | — |
| | status: Pending · next: queue | | |
| 22 | [build-queue-orphaned-result-on-wrapper-kill](docs/bugs/build-queue-orphaned-result-on-wrapper-kill/SPEC.md) | Validate | — |
| | status: Validate · phase 0/2 · next: run mcp-test · The queue wrapper writes `results/<seq>.json` and releases `active.lock` only after the detached build it is *tailing* exits. | | |
| 23 | [crlf-hook-blanket-enforce-mixed-eol](docs/bugs/crlf-hook-blanket-enforce-mixed-eol/SPEC.md) | Spec | — |
| | status: Spec · next: spec · `normalize-crlf.ps1` enforces a single blanket convention (CRLF on every non-`.sh` file) on the Cognito Forms repo, but the repo's *committed* EOL is mixed: `.cs` is CRLF, `NotificationTemplates/**/*.html` is LF. | | |
| 24 | [unknown](docs/bugs/unknown/SPEC.md) | Pending | — |
| | status: Pending · next: queue | | |
| 25 | [build-queue-outcome-opacity-and-inspect-deny](docs/bugs/build-queue-outcome-opacity-and-inspect-deny/SPEC.md) | Validate | — |
| | status: Validate · phase 2/4 · next: run mcp-test · Agents routinely can't tell what a `/msbuild` `/mstest` `/nxbuild` `/nxtest` invocation actually did — pass, fail, zero-match, or broken log capture all surface as the same `exit_code=0` with suppressed output — so they try to inspect the runner script / results JSON / logs to disambiguate. | | |
| 26 | [adhoc-align-cycle-commit-count-with-budget-population](docs/bugs/adhoc-align-cycle-commit-count-with-budget-population/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 27 | [adhoc-derive-multi-commit-budget-from-dispatch-sites](docs/bugs/adhoc-derive-multi-commit-budget-from-dispatch-sites/SPEC.md) | Spec | — |
| | status: Spec · next: spec | | |
| 28 | [build-queue-no-artifact-or-process-hygiene-on-crash](docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash/SPEC.md) | ⛔ Blocked | — |
| | status: Blocked · phase 0/5 · next: resolve blocker · A crashed or killed build leaves orphaned compiler/test child processes and a truncated 0-byte output artifact behind. | | |
| 29 | [build-queue-copy-lock-stale-dll-false-success](docs/bugs/build-queue-copy-lock-stale-dll-false-success/SPEC.md) | ⛔ Blocked | — |
| | status: Blocked · phase 1/4 · next: resolve blocker · An MSB3027 copy-lock failure (obj/ rebuilt fresh, copy to bin/Debug blocked by a leftover locker) makes MSBuild log "Build FAILED" while still exiting 0. | | |

## Needs attention

- ⬡ anti-overfit-design-gate — needs-input
- ⬡ claude-config-ci — needs-input
- ⛔ build-queue-no-artifact-or-process-hygiene-on-crash — blocked
- ⛔ build-queue-copy-lock-stale-dll-false-success — blocked
