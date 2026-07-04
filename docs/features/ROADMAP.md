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

- Code↔Doc Provenance Linkage / Implementation Ledger (`code-doc-provenance-linkage`) — at `__mark_complete__`/`__mark_fixed__`, distill each item into a small durable `IMPLEMENTED.md` (what shipped, which Locked Decisions, why) and record the touched-file set into a per-repo reverse index (file → slugs); skills consult the index before editing so the docs corpus becomes working memory instead of a write-only archive. In scope: an operator-invocable manual linking path (same producer, commit-range/PR-addressed) for teammate work that never flows through the pipeline. Operator must-have.
- Operator Paging on Pipeline Halts (`operator-halt-notifications`) — `NEEDS_INPUT.md`/`BLOCKED.md` halts sit silent until the operator checks in; push the decision (options inline) to the phone from the state scripts' halt writers, answerable from mobile.
- CI for claude-config Itself (`claude-config-ci`) — no `.github/workflows/` exists; run the pytest suites, skill lint, parity audit, bash hook harness, and Pester/PSScriptAnalyzer on every push so the harness's own integrity gates are un-skippable.
~~- Doc-Drift Linter (`doc-drift-linter`) — mechanically cross-check CLAUDE.md's hooks/scripts/coupled-pair tables against `settings.json`, the filesystem, and `lazy-parity-manifest.json`; the `worktree-claude-doc-drift` class, generalized.~~  ✅ COMPLETE

### Self-evolution cluster (operator-requested 2026-07-04)

> The harness must continuously evolve — but with instruments and epistemic guardrails, so
> improvements are measured (not narrated) and the self-improvement loop cannot overfit, weaken
> its own gates, or grade itself with tautological metrics. Substrate → semantics → hypothesis →
~~> guardrail: `harness-telemetry-ledger` (promoted from Tier 2 — raw-event substrate) →~~  ✅ COMPLETE
> `friction-kpi-registry` → `intervention-efficacy-tracking` → `anti-overfit-design-gate`, with
> `harness-change-canary-rollback` (Tier 2) as the self-healing consumer.

~~- Harness Telemetry Ledger + Trends (`harness-telemetry-ledger`) — state scripts emit a per-cycle JSONL ledger (cycles-per-feature, gate refusals, halt dwell, wall-time); `pipeline_visualizer` gains a trends view so hardening changes are measured, not vibes. *(Promoted from Tier 2 2026-07-04 — measurement substrate for this cluster.)*~~  ✅ COMPLETE
- Friction KPI Registry + Scorecards (`friction-kpi-registry`) — every friction-reduction system (build-queue, containment, halt handling, and anything designed later) declares canonical KPIs (signal sources, direction-of-goodness, baseline) in a machine-readable registry; scorecards trend per-system health and flag regressions; a `/spec`-time gate makes measurability a precondition for locking any future friction-reduction feature's baseline.
- Intervention Efficacy Tracking (`intervention-efficacy-tracking`) — every harness change registers its hypothesis (targeted friction signal, baseline, expected direction, review-by date) at ship time; a post-window evaluator writes CONFIRMED/REFUTED/INCONCLUSIVE verdicts against telemetry; REFUTED auto-enqueues a reconsideration item, closing the observe→measure loop the retro system currently leaves open.
- Anti-Overfit + Tautology Design Gate (`anti-overfit-design-gate`) — mechanical + adversarial review gate on harness self-modifications: overfit-smell detection (incident-literal rules), tautological-metric detection (a system graded by a signal it controls or suppresses), gate-weakening detection (loosened thresholds/exemptions demand operator sign-off), and a complexity budget; verdicts are recorded so the gate itself stays auditable.

## Tier 2 — proposed (repo-exploration stubs 2026-07-04)

- Harness-Change Canary + Rollback (`harness-change-canary-rollback`) — shipped control-surface changes enter an observation window; KPI regression or fresh incident clusters on the change's surface auto-enqueue an evidence-backed revert-or-redesign item, with revertibility metadata (change → commits via the provenance ledger) recorded at ship time. Flag-and-enqueue, never silent auto-revert.
- First-Class Dependency DAG in queue.json (`queue-dependency-dag`) — promote ROADMAP-prose hard-deps to an enforced `deps: [...]` queue field so skip-ahead can jump around dependency chains safely; prerequisite readiness signal for parallel execution.
- Cross-Repo Fleet Home Page (`cross-repo-fleet-view`) — multi-repo landing view in `pipeline_visualizer` aggregating every repo's queues, run markers, and halts into one control plane.
~~- Scheduled Autonomous Runs (`scheduled-autonomous-runs`) — cron-triggered `/lazy-batch-cloud` drains the queue nightly; `LAZY_QUEUE.md` + halt notifications are the morning report; existing arbitration keeps scheduled runs from clobbering live ones.~~  ✅ COMPLETE
- Generalize Build-Queue Beyond Cognito (`build-queue-generalization`) — config-driven per-repo ops manifest + hygiene profiles so AlgoBooth's `tauri build`/`cargo build --release` class rides the same machine-global serializer.
- Build-Queue ETA + Priority Lanes (`build-queue-eta-priority-lanes`) — predict per-op ETAs from historical `results/<seq>.json` durations and add a starvation-safe fast lane for small ops.
~~- Auto-Promotion Pipeline for Toolify Candidates (`toolify-auto-promotion`) — auto-draft pre-Gemini stubs (miner evidence attached) for above-bar `toolify-miner.py` candidates; track acceptance rate to tune the bar; operator baseline-lock gate preserved.~~  ✅ COMPLETE
~~- Skill Usage Miner + Dead-Weight Audit (`skill-usage-miner`) — mine session logs for per-skill invocation frequency; flag never-invoked skills for `archived/` and high-frequency prose skills for toolification; sweep stray non-skill files (e.g. `sh.exe.stackdump`).~~  ✅ COMPLETE
~~- Incident Auto-Capture → Bug Stubs (`incident-auto-capture`) — cluster hook `hook-error.json` breadcrumbs + repeated deny signatures and auto-enqueue `--type bug` stubs, closing the observe→harden loop between retros.~~  ✅ COMPLETE
~~- Cross-Platform Setup (`cross-platform-setup`) — stdlib-Python `setup.py bootstrap|check|repair` over a portable manifest so Linux/cloud containers can materialize the symlink layout; ends the recurring windows-portability rediscovery.~~  ✅ COMPLETE

## Tier 3 — proposed (repo-exploration stubs 2026-07-04, high-ambition)

- Sanctioned Parallel-Worktree Batch Execution (`parallel-worktree-batch-execution`) — a coordinator that shards dependency-independent queue items across worktrees (per-item branch + marker arbitration extending the ownership model, containment unchanged); the biggest throughput multiplier available.
- Native Android App for Pipeline Steering (`native-android-pipeline-steering`) — mobile client over the `mobile-queue-control`/fleet-view foundations with a sanctioned write path (resolve NEEDS_INPUT, reorder, enqueue) via committed files the pipeline already understands; PWA-vs-native is an open decision.
