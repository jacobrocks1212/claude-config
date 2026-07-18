---
kind: intervention
intervention_id: test-only-production-seams
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: d99f7959e9f1011bb96ebbc6088a8fd841dea57a
commit_set: d99f7959e9f1011bb96ebbc6088a8fd841dea57a
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
---

# Intervention: test-only-production-seams

Hypothesis: shipping `test-only-production-seams` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
