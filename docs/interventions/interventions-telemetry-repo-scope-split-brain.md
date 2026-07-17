---
kind: intervention
intervention_id: interventions-telemetry-repo-scope-split-brain
pipeline: bug
provenance: gated
shipped_date: '2026-07-12'
shipped_commit: c0b39e35705a2042553f34d9cb034925083d8888
commit_set: c0b39e35705a2042553f34d9cb034925083d8888
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
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core.py
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - fba244b
  - 5c2b13e
  - fba2399
  - 12b9d17
  - ed8d1b4
  - d1e4e6b
  - 6f72599
  - b34109c
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: interventions-telemetry-repo-scope-split-brain

Hypothesis: shipping `interventions-telemetry-repo-scope-split-brain` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-17

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 106 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.
