---
kind: intervention
intervention_id: adhoc-unify-merged-head-coordinator-exemptions
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: 37834b124e8660d4ef901e8d686699f9ac826749
commit_set: 37834b124e8660d4ef901e8d686699f9ac826749
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
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/dispatch.py
  commit_set:
  - 4f92bd4
  - ef6ee26
  - '8868056'
  - 7b1c05d
  - a0d0a47
  - 58a7a3e
  - '2370190'
  - 37834b1
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-unify-merged-head-coordinator-exemptions

Hypothesis: shipping `adhoc-unify-merged-head-coordinator-exemptions` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
