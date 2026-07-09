---
kind: fixed
feature_id: pr-review-postprocess-dedup-scope-filter-silent-drops
date: 2026-07-09
provenance: operator-directed-interactive
validated_via: subagent-orchestration (see notes; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

pr-review-postprocess-dedup-scope-filter-silent-drops marked fixed on 2026-07-09 by the interactive subagent orchestration Jacob directed
("orchestrate the implementation ... update the SPECs when done"). This receipt was written by
the orchestrator, not the pipeline's __mark_fixed__ gate -- provenance is deliberately
operator-directed-interactive, and the notes below carry the honest evidence ladder.

## Notes

Dedup step 3: same-issue-only collapse (cross-lane co-located keeps Opus-beats-sweep; same-lane collapses only on normalized-title match). Scope filter normalizes both sides (slashes/./case). Payload gains scope_filtered_count + per-finding drops[] (steps 2/3/5); --summary extended (scope_filtered=N lane_zeroed=[...]). VERIFIED offline: committed regression tests (distinct same-line findings both survive; true duplicate still collapses; path variant matches; out-of-scope lands in drops[]).
