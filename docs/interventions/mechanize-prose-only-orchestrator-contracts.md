---
kind: intervention
intervention_id: mechanize-prose-only-orchestrator-contracts
pipeline: feature
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: c8719f746e67f501da196c90f4feccf8009883ef
commit_set: c8719f746e67f501da196c90f4feccf8009883ef
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
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core.py
  - user/scripts/lazy_guard.py
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - d8f0822
  - 8f9adcc
  - 7678b5f
  - fe6fcd3
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: closed-clean
---

# Intervention: mechanize-prose-only-orchestrator-contracts

Hypothesis: shipping `mechanize-prose-only-orchestrator-contracts` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.

## Canary 2026-07-17

- window: closed after 10/10 observed post-ship run(s) (matured: True)
- signal movement: band-not-evaluable (target undeclared)
- incidents attributed: none
- unattributed in-window incidents: 32 (listed, never counted)
- handoff: the efficacy review proceeds on its own longer cadence — a clean canary does NOT pre-judge the efficacy verdict, and the watcher stops waking this record.
