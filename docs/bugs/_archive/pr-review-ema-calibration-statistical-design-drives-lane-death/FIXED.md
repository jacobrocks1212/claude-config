---
kind: fixed
feature_id: pr-review-ema-calibration-statistical-design-drives-lane-death
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

pr-review-ema-calibration-statistical-design-drives-lane-death marked fixed on 2026-07-09 by the interactive subagent orchestration Jacob directed
("orchestrate the implementation ... update the SPECs when done"). This receipt was written by
the orchestrator, not the pipeline's __mark_fixed__ gate -- provenance is deliberately
operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

Per-PR aggregation (one EMA step per lane|rule per run), clamp in applyEma via new shared scripts/weight-constants.ts (WEIGHT_FLOOR 0.35 / WEIGHT_CEIL 1.0), annealed alpha with nested {weight, data_points} schema (legacy scalar accepted), source_weights exposed in /weights, calibrate-weights.ts archived, prose EMA retired from learn-from-pr/calibrate (both shell the helper). VERIFIED offline: 8-dismissal repro -> one bounded step (0.9->0.675, not ~0.09); clamp floors at 0.35; zero-disposition run byte-identical; comment preservation proven. CONSTANTS CHOSEN WITHOUT SPEC LOCK (flag): floor 0.35, alpha = min(ema_alpha, max(0.05, 1/(n+1))).
