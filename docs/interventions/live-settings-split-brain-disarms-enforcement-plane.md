---
kind: intervention
intervention_id: live-settings-split-brain-disarms-enforcement-plane
pipeline: bug
provenance: gated
shipped_date: '2026-07-12'
shipped_commit: 9948a55ff4853a0009890f3042a83ad747185a8a
commit_set: 9948a55ff4853a0009890f3042a83ad747185a8a
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
  - user/hooks/lazy-cycle-containment.sh
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core.py
  - user/settings.json
  commit_set:
  - f0c33cb
  - fa244ed
  - 0f44611
  - 1b23a9b
  - 271dbf7
  - 30ebf73
  - 308fa60
  - 01ae5e4
  - a43808e
  - 3404c9e
  - 4edd224
  - 004336f
  - 2132b3b
  - 6c03084
  - 719c98a
  - 6770f44
  - 0628422
  - 6012c72
  - 8df3f35
  - 9948a55
  pair_scope: []
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: live-settings-split-brain-disarms-enforcement-plane

Hypothesis: shipping `live-settings-split-brain-disarms-enforcement-plane` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-17

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 106 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.
