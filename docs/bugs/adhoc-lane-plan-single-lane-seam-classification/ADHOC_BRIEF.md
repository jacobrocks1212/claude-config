---
kind: adhoc-brief
bug_id: adhoc-lane-plan-single-lane-seam-classification
enqueued_by: lazy-adhoc
date: 2026-07-09
---

# Ad-hoc bug: Lane-plan template cannot express Sequenced single-lane (no typegen seam)

The cognito-lanes plan template forces a per-phase Seam classification of Parallel or Sequenced plus a batch-table Parallel? column, but a backend-only single-lane phase (e.g. the track-submissions fabric-reporting Phase 1 re-planned in the 2026-07-09 v3 sandbox run) is Sequenced by the Cognito.Core/Model seam rule while having NO frontend lane, so the L.2 typegen seam never runs mid-phase and the classification is misleading. The planner improvised a Plan-specific note stating the seam is not run. Add an explicit Single-lane (no seam) classification value (or equivalent) to the per-phase template in write-plan-cognito SKILL.md plus a matching note in the lane contract L.2 so executors do not go looking for a seam step or dispatch a phantom frontend lane; keep v3 plans without the new value executing unchanged.
