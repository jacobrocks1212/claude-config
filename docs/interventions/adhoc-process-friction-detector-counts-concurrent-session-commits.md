---
kind: intervention
intervention_id: adhoc-process-friction-detector-counts-concurrent-session-commits
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: 3e75616c02f0531751bec6596a3134629e18a126
commit_set: 3e75616c02f0531751bec6596a3134629e18a126
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-19T02:40:26Z'
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
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/gates.py
  - user/scripts/lazy_core/ledgers.py
  - user/scripts/lazy_core/markers.py
  commit_set:
  - c951f67
  - 14840da
  - 5212ce0
  - ad5600d
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-process-friction-detector-counts-concurrent-session-commits

Hypothesis: shipping `adhoc-process-friction-detector-counts-concurrent-session-commits` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
