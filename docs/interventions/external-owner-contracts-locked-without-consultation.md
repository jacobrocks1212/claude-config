---
kind: intervention
intervention_id: external-owner-contracts-locked-without-consultation
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: e1eac3df4260da1e15d955ae0a2880ce0d3c9e6d
commit_set: e1eac3df4260da1e15d955ae0a2880ce0d3c9e6d
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T04:13:16Z'
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
  - user/scripts/lazy_core/depdag.py
  - user/scripts/lazy_core/docmodel.py
  commit_set:
  - 7d8160f
  - 981191a
  - 2b97f91
  - aaf0336
  - 444e838
  - 4f6fca7
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: external-owner-contracts-locked-without-consultation

Hypothesis: shipping `external-owner-contracts-locked-without-consultation` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
