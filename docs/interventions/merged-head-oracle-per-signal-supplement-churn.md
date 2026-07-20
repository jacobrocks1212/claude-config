---
kind: intervention
intervention_id: merged-head-oracle-per-signal-supplement-churn
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: 6e51c72b6b829d3d7c3c1e621bb15095fbd931a8
commit_set: 6e51c72b6b829d3d7c3c1e621bb15095fbd931a8
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
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/depdag.py
  - user/scripts/lazy_core/dispatch.py
  - user/scripts/lazy_core/docmodel.py
  commit_set:
  - 0f6f801
  - 1904e35
  - 1fe889e
  - e2e2773
  - 461d42d
  - 7f8b39a
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: merged-head-oracle-per-signal-supplement-churn

Hypothesis: shipping `merged-head-oracle-per-signal-supplement-churn` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
