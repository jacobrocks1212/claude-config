---
kind: intervention
intervention_id: build-queue-false-green-on-silent-build-failure
pipeline: bug
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: 544c41ea21dd7722d88367e01c973acb2ef31ccc
commit_set: 544c41ea21dd7722d88367e01c973acb2ef31ccc
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-04T14:38:18Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
---

# Intervention: build-queue-false-green-on-silent-build-failure

Hypothesis: shipping `build-queue-false-green-on-silent-build-failure` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
