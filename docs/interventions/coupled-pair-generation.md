---
kind: intervention
intervention_id: coupled-pair-generation
pipeline: feature
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: 8845b069986f95d8e84af380d52318587ab483e5
commit_set: 8845b069986f95d8e84af380d52318587ab483e5
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-13T16:07:03Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-13'
  window_runs: 10
  surfaces:
  - user/scripts/lazy-parity-manifest.json
  commit_set:
  - 03993c0
  - 7f7705b
  - 7678b5f
  - fe6fcd3
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: coupled-pair-generation

Hypothesis: shipping `coupled-pair-generation` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
