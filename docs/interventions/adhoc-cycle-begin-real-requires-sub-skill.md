---
kind: intervention
intervention_id: adhoc-cycle-begin-real-requires-sub-skill
pipeline: bug
provenance: gated
shipped_date: '2026-07-06'
shipped_commit: e516be563454e308b10fdf470ba4d14e368604e5
commit_set: e516be563454e308b10fdf470ba4d14e368604e5
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
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  commit_set:
  - 35bdb2d
  - 8eddf7b
  - e84207d
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-cycle-begin-real-requires-sub-skill

Hypothesis: shipping `adhoc-cycle-begin-real-requires-sub-skill` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
