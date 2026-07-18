---
kind: intervention
intervention_id: merged-head-actionability-oracle
pipeline: feature
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 9cf95a3cce2cc51c0e0659fadd5b87757f188082
commit_set: 9cf95a3cce2cc51c0e0659fadd5b87757f188082
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T18:21:25Z'
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
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/depdag.py
  - user/scripts/lazy_core/dispatch.py
  - user/scripts/lazy_core/docmodel.py
  commit_set:
  - d473691
  - a4a9c1a
  - ac389f6
  - f8bc122
  - c051f03
  - 9d4be13
  - 68eeb7e
  - ff7873e
  - b37f40f
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: merged-head-actionability-oracle

Hypothesis: shipping `merged-head-actionability-oracle` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
