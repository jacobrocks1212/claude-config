---
kind: intervention
intervention_id: adhoc-cycle-return-omits-decision-classification-ledger
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: b66b6e735a5f48004169fa2a38ea2c6e289f2cea
commit_set: b66b6e735a5f48004169fa2a38ea2c6e289f2cea
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
  - user/hooks/subagent-wedge-backstop.sh
  commit_set:
  - cbe3386
  - 4a12e21
  - f01afdd
  - 24d48e4
  - ea0f8b9
  - 7a95ec4
  - 66fac32
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-cycle-return-omits-decision-classification-ledger

Hypothesis: shipping `adhoc-cycle-return-omits-decision-classification-ledger` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
