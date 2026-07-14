# Roadmap

The lazy-pipeline-managed feature queue for **claude-config**. Each row tracks one feature; a
strikethrough row marked `COMPLETE` is what the state machine treats as done (alongside the
feature's `COMPLETED.md` receipt). `docs/features/` is the lazy-managed home; `docs/specs/` remains
the historical / manually-authored spec archive (not under pipeline management).

## Tier 1

- ~~Multi-Repo Concurrent Runs (`multi-repo-concurrent-runs`) — scope the lazy run-marker per `repo_root` so a lazy-batch run in one repo neither blocks nor is blocked by a run in another; `--run-end` clears its own marker; same-repo second run refused. Closes the stale-marker-arms-guard-globally class.~~ **COMPLETE** (2026-06-16 — gated receipt; per-repo state-dir chokepoint at `claude_state_dir()`; pytest test_lazy_core 412 + test_hooks 69 + test_pipeline_visualizer 65 + test_lazy_parity 23 + smoke/lint green; MCP skip-exempt `standalone — no app integration`; **live-validated** isolating a concurrent AlgoBooth run).
~~- Unified Pipeline Orchestrator + Toolification Framework (`unified-pipeline-orchestrator`) — one batch run drains features + bugs from a merged work-list (one skill, two state scripts, priority order with bugs breaking ties); toolify framework mines session logs and ships `--ensure-runtime` / `--gate-coverage` / enhanced `__mark_complete__` as first consumers. _Enqueued 2nd; no deps; no-research._~~  ✅ COMPLETE
~~- Harness-Hardening Retro Fixes + Anti-Overfit (`harness-hardening-retro-fixes`) — anti-overfit reflex for `/harden-harness` (fix instance now + spin off generalized `/spec`/`/spec-bug` on over-fit smell; auto-identify toolify candidates → `/spec-bug`); verification-detector structural canonical marker; `plan_complete` false-alarm fix; mcp-test haiku-tier re-scope; dead-coverage guard. _Enqueued 3rd; hard-deps `unified-pipeline-orchestrator`; no-research._~~  ✅ COMPLETE
- ~~Lazy Pipeline Visualizer (`lazy-pipeline-visualizer`) — live local web control-plane for the lazy feature + bug pipelines (queues, worktree fleet, traversal graph).~~ **COMPLETE** (2026-06-15 — gated receipt; pytest 575/575 + live-boot reachability smoke; MCP gate operator-exempt via SKIP_MCP_TEST.md).
- ~~Lazy Cycle Containment (`lazy-cycle-containment`) — make "one dispatch = one cycle" a mechanical, in-flight boundary (cycle-subagent marker + PreToolUse deny + state-script refuse-by-construction + cycle-prompt stop) so a dispatched cycle subagent cannot run off and execute a whole batch.~~ **COMPLETE** (2026-06-16 — gated receipt; pytest 476/476 + bash hook harness 48/48 + projection/skill lint clean; MCP gate skip-exempt via SKIP_MCP_TEST.md, `standalone — no app integration`).

## Tier 1 — proposed (session-audit stubs 2026-06-19)

> Pre-Gemini stubs from the `/lazy-batch` session-log audit (AlgoBooth, 19 sessions over the last 2 weeks). Each carries the `> Draft (pre-Gemini)` trailer + `"stub": true`, so the pipeline routes it to `/spec` (Step 4.5) to shape the baseline interactively. Solutions are deliberately NOT baked.

~~- Completion / Coherence Gate Reconciliation (`completion-coherence-gate-reconciliation`) — three completion gates (`apply_pseudo`, `check-docs-consistency.ts`, `lazy_core`) disagree on the MCP-verification carve-out, so fully-validated features get refused at the finish line and nearly every completion needs an extra coherence-recovery meta-cycle. Operator-flagged; highest-frequency friction in the corpus.~~  ✅ COMPLETE
~~- Feature Budget Guard + Skip-Ahead (`feature-budget-guard-and-skip-ahead`) — one stubborn feature can consume an entire batch budget, and a blocked/research-gated head item strands the whole independent queue behind it.~~  ✅ COMPLETE
~~- Long-Build + Runtime Ownership (`long-build-and-runtime-ownership`) — long builds and the dev/MCP runtime die at the subagent turn boundary, forcing hand-rolled rebuild→health-poll loops and orphaned cycles.~~  ✅ COMPLETE

## Tier 2 — proposed (session-audit stubs 2026-06-19)

~~- Host-Capability Declaration for Gated Features (`host-capability-declaration-for-gated-features`) — features gated on absent host capabilities (C++ toolchains, audio devices) churn through BLOCKED/SKIP/AskUserQuestion instead of skipping proactively.~~  ✅ COMPLETE
~~- Lazy Queue Status Doc (GitHub-Mobile Readable) — (ad-hoc, enqueued 2026-06-22)~~  ✅ COMPLETE

## Tier 1 — proposed (repo-exploration stubs 2026-07-04)

> Pre-Gemini stubs from the repo-exploration proposal session 2026-07-04 (operator-curated
> candidate list). Each carries `**Status:** Draft (pre-Gemini)` + `"stub": true`, so the pipeline
> routes it to `/spec` (Step 4.5) to shape the baseline interactively. Solutions are deliberately
> NOT baked. (The `cd`-prefix bypass candidate was dropped — already tracked and Concluded in
> `docs/bugs/build-queue-enforce-cd-prefix-bypass`.)

~~- Code↔Doc Provenance Linkage / Implementation Ledger (`code-doc-provenance-linkage`) — at `__mark_complete__`/`__mark_fixed__`, distill each item into a small durable `IMPLEMENTED.md` (what shipped, which Locked Decisions, why) and record the touched-file set into a per-repo reverse index (file → slugs); skills consult the index before editing so the docs corpus becomes working memory instead of a write-only archive. In scope: an operator-invocable manual linking path (same producer, commit-range/PR-addressed) for teammate work that never flows through the pipeline. Operator must-have.~~  ✅ COMPLETE
~~- Operator Paging on Pipeline Halts (`operator-halt-notifications`) — `NEEDS_INPUT.md`/`BLOCKED.md` halts sit silent until the operator checks in; push the decision (options inline) to the phone from the state scripts' halt writers, answerable from mobile.~~  ✅ COMPLETE
- CI for claude-config Itself (`claude-config-ci`) — no `.github/workflows/` exists; run the pytest suites, skill lint, parity audit, bash hook harness, and Pester/PSScriptAnalyzer on every push so the harness's own integrity gates are un-skippable.
~~- Doc-Drift Linter (`doc-drift-linter`) — mechanically cross-check CLAUDE.md's hooks/scripts/coupled-pair tables against `settings.json`, the filesystem, and `lazy-parity-manifest.json`; the `worktree-claude-doc-drift` class, generalized.~~  ✅ COMPLETE

### Self-evolution cluster (operator-requested 2026-07-04)

> The harness must continuously evolve — but with instruments and epistemic guardrails, so
> improvements are measured (not narrated) and the self-improvement loop cannot overfit, weaken
> its own gates, or grade itself with tautological metrics. Substrate → semantics → hypothesis →
~~> guardrail: `harness-telemetry-ledger` (promoted from Tier 2 — raw-event substrate) →~~  ✅ COMPLETE
~~> `friction-kpi-registry` → `intervention-efficacy-tracking` → `anti-overfit-design-gate`, with~~  ✅ COMPLETE
~~> `harness-change-canary-rollback` (Tier 2) as the self-healing consumer.~~  ✅ COMPLETE

~~- Harness Telemetry Ledger + Trends (`harness-telemetry-ledger`) — state scripts emit a per-cycle JSONL ledger (cycles-per-feature, gate refusals, halt dwell, wall-time); `pipeline_visualizer` gains a trends view so hardening changes are measured, not vibes. *(Promoted from Tier 2 2026-07-04 — measurement substrate for this cluster.)*~~  ✅ COMPLETE
- ~~Friction KPI Registry + Scorecards (`friction-kpi-registry`) — every friction-reduction system (build-queue, containment, halt handling, and anything designed later) declares canonical KPIs (signal sources, direction-of-goodness, baseline) in a machine-readable registry; scorecards trend per-system health and flag regressions; a `/spec`-time gate makes measurability a precondition for locking any future friction-reduction feature's baseline.~~ ✅ COMPLETE
~~- Intervention Efficacy Tracking (`intervention-efficacy-tracking`) — every harness change registers its hypothesis (targeted friction signal, baseline, expected direction, review-by date) at ship time; a post-window evaluator writes CONFIRMED/REFUTED/INCONCLUSIVE verdicts against telemetry; REFUTED auto-enqueues a reconsideration item, closing the observe→measure loop the retro system currently leaves open.~~  ✅ COMPLETE
~~- Anti-Overfit + Tautology Design Gate (`anti-overfit-design-gate`) — mechanical + adversarial review gate on harness self-modifications: overfit-smell detection (incident-literal rules), tautological-metric detection (a system graded by a signal it controls or suppresses), gate-weakening detection (loosened thresholds/exemptions demand operator sign-off), and a complexity budget; verdicts are recorded so the gate itself stays auditable.~~  ✅ COMPLETE

## Tier 2 — proposed (repo-exploration stubs 2026-07-04)

~~- Harness-Change Canary + Rollback (`harness-change-canary-rollback`) — shipped control-surface changes enter an observation window; KPI regression or fresh incident clusters on the change's surface auto-enqueue an evidence-backed revert-or-redesign item, with revertibility metadata (change → commits via the provenance ledger) recorded at ship time. Flag-and-enqueue, never silent auto-revert.~~  ✅ COMPLETE
~~- First-Class Dependency DAG in queue.json (`queue-dependency-dag`) — promote ROADMAP-prose hard-deps to an enforced `deps: [...]` queue field so skip-ahead can jump around dependency chains safely; prerequisite readiness signal for parallel execution.~~  ✅ COMPLETE
~~- Cross-Repo Fleet Home Page (`cross-repo-fleet-view`) — multi-repo landing view in `pipeline_visualizer` aggregating every repo's queues, run markers, and halts into one control plane.~~  ✅ COMPLETE
~~- Scheduled Autonomous Runs (`scheduled-autonomous-runs`) — cron-triggered `/lazy-batch-cloud` drains the queue nightly; `LAZY_QUEUE.md` + halt notifications are the morning report; existing arbitration keeps scheduled runs from clobbering live ones.~~  ✅ COMPLETE
- Generalize Build-Queue Beyond Cognito (`build-queue-generalization`) — config-driven per-repo ops manifest + hygiene profiles so AlgoBooth's `tauri build`/`cargo build --release` class rides the same machine-global serializer.
- Build-Queue ETA + Priority Lanes (`build-queue-eta-priority-lanes`) — predict per-op ETAs from historical `results/<seq>.json` durations and add a starvation-safe fast lane for small ops.
~~- Auto-Promotion Pipeline for Toolify Candidates (`toolify-auto-promotion`) — auto-draft pre-Gemini stubs (miner evidence attached) for above-bar `toolify-miner.py` candidates; track acceptance rate to tune the bar; operator baseline-lock gate preserved.~~  ✅ COMPLETE
~~- Skill Usage Miner + Dead-Weight Audit (`skill-usage-miner`) — mine session logs for per-skill invocation frequency; flag never-invoked skills for `archived/` and high-frequency prose skills for toolification; sweep stray non-skill files (e.g. `sh.exe.stackdump`).~~  ✅ COMPLETE
~~- Incident Auto-Capture → Bug Stubs (`incident-auto-capture`) — cluster hook `hook-error.json` breadcrumbs + repeated deny signatures and auto-enqueue `--type bug` stubs, closing the observe→harden loop between retros.~~  ✅ COMPLETE
~~- Cross-Platform Setup (`cross-platform-setup`) — stdlib-Python `setup.py bootstrap|check|repair` over a portable manifest so Linux/cloud containers can materialize the symlink layout; ends the recurring windows-portability rediscovery.~~  ✅ COMPLETE
~~- Park-Provisional Acceptance (`park-provisional-acceptance`) — a third decision tier between the D2 two-key mechanical auto-accept and the product-class park: under `--park --park-provisional`, low-divergence (divergence two-key graded) recommended options are provisionally accepted at park time so the feature keeps implementing overnight; `NEEDS_INPUT_PROVISIONAL.md` + a triple-layer completion backstop guarantee operator ratify-or-redirect before completion, with redirects scoped by the recorded `decision_commit`. *(Added 2026-07-09, implemented same-session.)*~~  ✅ COMPLETE

~~- Workstation Recursive Sub-Subagent Dispatch (`workstation-recursive-subagent-dispatch`) — lift the cycle-subagent inline-override on workstation so the dispatched skill's own sub-subagent orchestration (test-agent/impl-agent split, research fan-outs) is authoritative again, restoring the structural TDD guarantee; cloud keeps the inline override; retro grading self-heals by prompt marker. *(Added 2026-07-09, implemented same-session.)*~~  ✅ COMPLETE

~~- Stub-Origin Provisional Exclusion (`stub-origin-provisional-exclusion`) — special-case stub-origin decisions in the provisional tier: baseline-gating forks from a park-mode stub-spec `/spec` round (or a `/spec-bug` pre-conclusion halt) carry `stub_origin: true` and are never provisionally accepted — the operator always confirms a baseline before anything is built on it. *(Added 2026-07-09, implemented same-session.)*~~  ✅ COMPLETE

## Tier 3 — proposed (repo-exploration stubs 2026-07-04, high-ambition)

~~- Sanctioned Parallel-Worktree Batch Execution (`parallel-worktree-batch-execution`) — a coordinator that shards dependency-independent queue items across worktrees (per-item branch + marker arbitration extending the ownership model, containment unchanged); the biggest throughput multiplier available.~~ ✅ COMPLETE
- Native Android App for Pipeline Steering (`native-android-pipeline-steering`) — mobile client over the `mobile-queue-control`/fleet-view foundations with a sanctioned write path (resolve NEEDS_INPUT, reorder, enqueue) via committed files the pipeline already understands; PWA-vs-native is an open decision.

## Proposed (harness deep-dive + session-mining specs 2026-07-11)

> Full Draft SPECs (not pre-Gemini stubs) authored 2026-07-11 from a structured deep-dive of the
> harness's four planes (state-machine core, skills plane, enforcement plane, self-improvement
> loop) cross-grounded in mined evidence from 202 sessions (156 AlgoBooth + 46 claude-config;
> ~3,500 tool errors clustered, the 71h lazy-batch marathon deep-read, and the operator-correction
> corpus). Seventeen companion investigation specs landed in `docs/bugs/` the same day — several
> features below name them as hard deps. Picked up by queue autodiscovery.

~~- State-Script CLI Contract: Registry + Shared Surface (`state-cli-contract-registry`) — P1 — generate a committed `cli-surface.json` from the live ArgumentParsers and lint every skill/component `--flag` mention against it (kills the invented/drifted-flag error class); hoist the ~72 name-identical flags + twin-duplicated helpers of `lazy-state.py`/`bug-state.py` into a parameterized shared CLI builder so twin parity becomes structural instead of regex-audited.~~  ✅ COMPLETE
- lazy_core Package Decomposition (`lazy-core-package-decomposition`) — P1 — split the 17.7K-line `lazy_core.py` monolith (and its 32K-line flat test file) into a facade package along verified seams (docmodel, dep DAG, gates, dispatch, runtime, marker plane last), preserving byte-compatible `lazy_core.*` imports for the 20 importers and the regex-over-source auditors; includes the hooks' fast-import path and a ruff/pyflakes gate on `user/scripts/`. Hard-dep: the two crash-consistency bug fixes.
~~- Coupled-Pair Generation (`coupled-pair-generation`) — P1 — stop hand-mirroring the 5 coupled skill pairs (112 of 129 audited headings are manual restatements, ~300KB derived prose): generate derived SKILL.md files from the canonical + the manifest's existing token substitutions + divergence overlays; the parity audit demotes to a freshness verifier.~~  ✅ COMPLETE
~~- Mechanize Prose-Only Orchestrator Contracts (`mechanize-prose-only-orchestrator-contracts`) — P1 — convert the four highest-risk unenforced /lazy-batch contracts to mechanical enforcement: guard-pinned `model:` on dispatches, run-marker-recorded input-audit obligations, script-owned decision write-back records, script-side park/budget notifications.~~  ✅ COMPLETE
~~- lazy-batch Skill Deflation (`lazy-batch-skill-deflation`) — P2 — cut the 252KB orchestrator skill's ~65-85KB of driftable script-behavior narration down to verdict-routing rules, relocate incident narratives, and add a size/long-line lint ratchet (soft-dep: coupled-pair-generation).~~  ✅ COMPLETE
~~- skill-config Schema + Reference Lint (`skill-config-schema-and-reference-lint`) — P2 — per-repo declared-files manifest with intended-absent markers, JSON-schema validation for load-bearing configs (`build-queue-ops.json`), and a lint sweeping every `.claude/skill-config/` mention; quick win: the missing algobooth `commit-policy.md` behind the corpus's #1 tool-error cluster (377 failed Reads). (implemented 2026-07-12; ratification pending) (2026-07-12 — gated receipt; pytest 29/29 + live `lint-skill-config.py`/`lint-skills.py`/`project-skills.py`/`kpi-scorecard.py --lint` green; MCP skip-exempt `standalone — no app integration`; D1/D4 provisionally accepted pending ratification — see NEEDS_INPUT_PROVISIONAL.md).~~  ✅ COMPLETE
- Shared Hook Lib (`shared-hook-lib`) — P2 — collapse the ~470 duplicated lines across the 7 python-bearing hooks (event append, payload parse, deny emit, anchor regexes) into `hook-prelude.sh` + `hook_lib.py`; drift there has already caused real bugs (dead breadcrumb path, missing fail-open traces).
~~- Plan-Structure Authoring Gate (`plan-structure-authoring-gate`) — P2 — emit-time structural validation for authored plans/PHASES (per-WU checkboxes, Runtime Verification subsection placement, template-row rejection, validated series-index invariant) so plan-format defects are refused at authoring instead of consuming recovery meta-cycles (~7% of marathon dispatches).~~  ✅ COMPLETE
~~- Cycle-Prompt Environment Dialect (`cycle-prompt-environment-dialect`) — P2 — a compact host-conditional dialect block in the cycle base prompt (Git-Bash path quoting, stdin-pipe python, tolerant marker probes, phases-slice mandate) targeting the ~600 mined Windows/environment tool errors that memory notes structurally cannot reach (subagents never see MEMORY.md).~~  ✅ COMPLETE
~~- Efficacy Signal Integrity (`efficacy-signal-integrity`) — P2 — make the intervention-efficacy loop actually able to grade: gate-refusal sub-signal targets (six current records confound each other by construction), an open-canary staleness alarm, and scorecard freshness + signal-vantage declarations. Hard-dep: the interventions-telemetry split-brain bug fix.~~  ✅ COMPLETE
~~- Bug-Queue Aging Backpressure (`bug-queue-aging-backpressure`) — P2 — the harness bug backlog has inflow caps but no outflow forcing function (oldest open bug 17 days, 23 Concluded-unfixed, null-severity pins permanent): age-escalation in the merged-view sort, expiry on hand-pinned deprioritizations, queue-age surfaced in LAZY_QUEUE.md.~~  ✅ COMPLETE
- Generalized build/test runner skill system (claude-config battery + AlgoBooth qg ops; Cognito pattern preserved) — (ad-hoc, enqueued 2026-07-13)
