---
kind: intervention
intervention_id: build-queue-hygiene-dot-source-discarded-in-child-scope
pipeline: bug
provenance: gated
shipped_date: '2026-07-06'
shipped_commit: 2d9f8ae306237935901f4460bff699cecd06821d
commit_set: 2d9f8ae306237935901f4460bff699cecd06821d
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
  opened: '2026-07-06'
  window_runs: 10
  surfaces:
  - user/scripts/build-queue-runner.ps1
  - user/scripts/build-queue-status.ps1
  - user/scripts/build-queue.ps1
  commit_set:
  - 2d9f8ae306237935901f4460bff699cecd06821d
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: build-queue-hygiene-dot-source-discarded-in-child-scope

Hypothesis: shipping `build-queue-hygiene-dot-source-discarded-in-child-scope` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
