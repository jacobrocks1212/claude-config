---
kind: intervention
intervention_id: subagent-wedge-backstop-hook
pipeline: feature
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 5f3a4870cf9f330131fbe1ed9a299ab5e44304ae
commit_set: 5f3a4870cf9f330131fbe1ed9a299ab5e44304ae
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T16:50:52Z'
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
  - user/hooks/CLAUDE.md
  - user/hooks/subagent-wedge-backstop.sh
  - user/settings.json
  commit_set:
  - 464c924
  - d6e9465
  - 127d102
  - 72df8fe
  - 5f15d5a
  pair_scope: []
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: subagent-wedge-backstop-hook

Hypothesis: shipping `subagent-wedge-backstop-hook` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-20

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 916 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.
