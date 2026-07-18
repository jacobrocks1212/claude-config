---
kind: intervention
intervention_id: dispatched-harden-record-intervention-refused-by-containment
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 7a5d5d1089b5c599c95bf8991ede027c95278ee7
commit_set: 7a5d5d1089b5c599c95bf8991ede027c95278ee7
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T04:13:16Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-18'
  window_runs: 10
  surfaces:
  - user/scripts/bug-state.py
  commit_set:
  - '4630491'
  - 5b0d1a0
  - 0258a5b
  - c3ac184
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: dispatched-harden-record-intervention-refused-by-containment

Hypothesis: shipping `dispatched-harden-record-intervention-refused-by-containment` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
