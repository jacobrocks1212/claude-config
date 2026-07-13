---
kind: intervention
intervention_id: long-build-and-build-queue-matcher-bypasses
pipeline: bug
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: f2e75f041ec6f33738e53cdfd6c6002e88422ba0
commit_set: f2e75f041ec6f33738e53cdfd6c6002e88422ba0
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-13T16:07:03Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
---

# Intervention: long-build-and-build-queue-matcher-bypasses

Hypothesis: shipping `long-build-and-build-queue-matcher-bypasses` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
