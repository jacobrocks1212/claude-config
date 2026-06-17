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
