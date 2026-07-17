---
kind: intervention
intervention_id: completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo
pipeline: bug
provenance: gated
shipped_date: '2026-07-14'
shipped_commit: 9abe05eef79d1f9b493f992ee3adfe3f7413c859
commit_set: 9abe05eef79d1f9b493f992ee3adfe3f7413c859
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
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/docmodel.py
  - user/scripts/lazy_core/gates.py
  - user/scripts/lazy_core/pseudo.py
  commit_set:
  - b1dc9c5
  pair_scope: []
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo

Hypothesis: shipping `completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-17

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 5 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.
