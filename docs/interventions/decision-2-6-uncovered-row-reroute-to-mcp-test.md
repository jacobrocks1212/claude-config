---
kind: intervention
intervention_id: decision-2-6-uncovered-row-reroute-to-mcp-test
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: 4f6b280f1c31232589c6c465a006ea3291e30cd2
commit_set: 4f6b280f1c31232589c6c465a006ea3291e30cd2
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-19T14:30:33Z'
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
  - user/hooks/lazy-cycle-containment.sh
  - user/hooks/subagent-wedge-backstop.sh
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/docmodel.py
  - user/scripts/lazy_core/gates.py
  commit_set:
  - 5ae3202
  - 3e70cda
  - 14ef508
  - 5312b9d
  - 84a2d71
  - c2bca4d
  - 7e2f54b
  - 5e1e587
  - 7e3bb22
  - b661477
  - 57b07fe
  - 9ce3b8f
  - aa056e8
  - 92ea330
  - 43a1b79
  - 91e811f
  - 193cb99
  - 4f6b280
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: decision-2-6-uncovered-row-reroute-to-mcp-test

Hypothesis: shipping `decision-2-6-uncovered-row-reroute-to-mcp-test` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
