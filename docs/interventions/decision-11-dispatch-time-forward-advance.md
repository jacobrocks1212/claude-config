---
kind: intervention
intervention_id: decision-11-dispatch-time-forward-advance
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: be4c7f767c4a74085f37075cd809661eac0273ad
commit_set: be4c7f767c4a74085f37075cd809661eac0273ad
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-19T14:30:33Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-19'
  window_runs: 10
  surfaces:
  - user/scripts/lazy_core/markers.py
  commit_set:
  - 2d68e34
  - bbb5803
  - f205c2d
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: decision-11-dispatch-time-forward-advance

Hypothesis: shipping `decision-11-dispatch-time-forward-advance` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
