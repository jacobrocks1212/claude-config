---
kind: intervention
intervention_id: lazy-core-package-decomposition
pipeline: feature
provenance: gated
shipped_date: '2026-07-14'
shipped_commit: f00ceaf950c81517b1bb534fb332429be2a8b6a5
commit_set: f00ceaf950c81517b1bb534fb332429be2a8b6a5
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
  opened: '2026-07-14'
  window_runs: 10
  surfaces:
  - user/scripts/lazy_core/docmodel.py
  commit_set:
  - f00ceaf
  - fdbe299
  - 21e4e80
  - 2b45e39
  - 57645f0
  - 9888ecf
  - 733b21f
  - '4222398'
  - 2bd9152
  - 5bc648b
  - c0124ff
  - 3411b45
  - 54b8859
  - 7678b5f
  - fe6fcd3
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: lazy-core-package-decomposition

Hypothesis: shipping `lazy-core-package-decomposition` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
