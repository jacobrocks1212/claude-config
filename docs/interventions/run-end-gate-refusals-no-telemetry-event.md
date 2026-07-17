---
kind: intervention
intervention_id: run-end-gate-refusals-no-telemetry-event
pipeline: bug
provenance: gated
shipped_date: '2026-07-12'
shipped_commit: 6229a2535d3089fd52fbd62cc9e9bceda4d6a74c
commit_set: 6229a2535d3089fd52fbd62cc9e9bceda4d6a74c
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-12T05:39:34Z'
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
  - user/scripts/lazy-state.py
  commit_set:
  - 50cb29d
  pair_scope: []
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: run-end-gate-refusals-no-telemetry-event

Hypothesis: shipping `run-end-gate-refusals-no-telemetry-event` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-17

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 106 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.
