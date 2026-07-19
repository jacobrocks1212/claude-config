---
kind: intervention
intervention_id: adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: f0a27950f98120c3f4cf918e09c7468001c59558
commit_set: f0a27950f98120c3f4cf918e09c7468001c59558
target_signal: undeclared
expected_direction: undeclared
signal_independence: independent
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
  - user/scripts/lazy_core/depdag.py
  - user/scripts/lazy_core/dispatch.py
  - user/scripts/lazy_core/docmodel.py
  commit_set:
  - a1fc408
  - a1f98e4
  - 4985c82
  - 74dbcbb
  - dba3fb6
  - 760d1cc
  - beef5fe
  - f0a2795
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move

Hypothesis: shipping `adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Signal independence: independent — the discriminating signal is the rate of `GATE_VERDICT.md` `overfit`/`gate_weakening` flags later overridden by the operator as false-positives specifically on cross-file construct moves (an independent observable recorded in the GATE_VERDICT/override ledger across future changes), not a metric this change itself emits or suppresses.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
