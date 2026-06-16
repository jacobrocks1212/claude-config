# Roadmap

The lazy-pipeline-managed feature queue for **claude-config**. Each row tracks one feature; a
strikethrough row marked `COMPLETE` is what the state machine treats as done (alongside the
feature's `COMPLETED.md` receipt). `docs/features/` is the lazy-managed home; `docs/specs/` remains
the historical / manually-authored spec archive (not under pipeline management).

## Tier 1

- ~~Lazy Pipeline Visualizer (`lazy-pipeline-visualizer`) — live local web control-plane for the lazy feature + bug pipelines (queues, worktree fleet, traversal graph).~~ **COMPLETE** (2026-06-15 — gated receipt; pytest 575/575 + live-boot reachability smoke; MCP gate operator-exempt via SKIP_MCP_TEST.md).
