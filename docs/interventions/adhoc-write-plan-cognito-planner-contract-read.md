---
kind: intervention
intervention_id: adhoc-write-plan-cognito-planner-contract-read
pipeline: bug
provenance: gated
shipped_date: '2026-07-09'
shipped_commit: 7108b2e8db9d0639c82e09029eec1040c3518ab9
commit_set: 7108b2e8db9d0639c82e09029eec1040c3518ab9
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
canary:
  opened: '2026-07-09'
  window_runs: 10
  surfaces:
  - user/scripts/build-queue-runner.ps1
  commit_set:
  - 7108b2e8db9d0639c82e09029eec1040c3518ab9
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-write-plan-cognito-planner-contract-read

Hypothesis: shipping `adhoc-write-plan-cognito-planner-contract-read` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
