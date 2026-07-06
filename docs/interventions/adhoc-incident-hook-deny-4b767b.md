---
kind: intervention
intervention_id: adhoc-incident-hook-deny-4b767b
pipeline: bug
provenance: gated
shipped_date: '2026-07-06'
shipped_commit: 19d26e128b895607abbddd639fbd5668a12dea6f
commit_set: 19d26e128b895607abbddd639fbd5668a12dea6f
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-06T03:03:19Z'
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
  - user/hooks/lazy-cycle-containment.sh
  commit_set:
  - bb8a486
  - 303989c
  - c982b94
  - d4204e6
  - 19d26e1
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-incident-hook-deny-4b767b

Hypothesis: shipping `adhoc-incident-hook-deny-4b767b` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
