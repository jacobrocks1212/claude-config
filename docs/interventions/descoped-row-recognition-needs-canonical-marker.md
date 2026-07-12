---
kind: intervention
intervention_id: descoped-row-recognition-needs-canonical-marker
pipeline: bug
provenance: gated
shipped_date: '2026-07-12'
shipped_commit: 94754958707772fd3f91b42fa083cad1c8a9be62
commit_set: 94754958707772fd3f91b42fa083cad1c8a9be62
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-12T16:53:25Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-12'
  window_runs: 10
  surfaces:
  - user/scripts/bug-state.py
  - user/scripts/lazy_core.py
  commit_set:
  - ca3e2b1
  - 7f15112
  - f74f821
  - 879613d
  - 12d8106
  - '3247540'
  - 498a5f0
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: descoped-row-recognition-needs-canonical-marker

Hypothesis: shipping `descoped-row-recognition-needs-canonical-marker` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
