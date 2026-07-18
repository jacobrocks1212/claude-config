---
kind: intervention
intervention_id: adhoc-audit-obligation-fires-on-zero-commit-failed-cycle
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 773ec58f4a6012decf0c59f56e5d30c487358b2c
commit_set: 773ec58f4a6012decf0c59f56e5d30c487358b2c
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T15:42:21Z'
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
  - user/scripts/lazy-state.py
  - user/scripts/lazy_coord.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/ledgers.py
  - user/scripts/lazy_core/markers.py
  - user/skills/lazy-batch-parallel/SKILL.md
  commit_set:
  - b0889c6
  - 86c4f41
  - 33e301e
  - 719ec33
  - 53ce28f
  - 86ff644
  - ea3b700
  - 17af268
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-audit-obligation-fires-on-zero-commit-failed-cycle

Hypothesis: shipping `adhoc-audit-obligation-fires-on-zero-commit-failed-cycle` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
