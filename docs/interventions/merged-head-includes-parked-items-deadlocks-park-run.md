---
kind: intervention
intervention_id: merged-head-includes-parked-items-deadlocks-park-run
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 29ab9c8f8f1bf894806c2363d6f540d8b3280789
commit_set: 29ab9c8f8f1bf894806c2363d6f540d8b3280789
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T04:13:24Z'
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
  - user/skills/harden-harness/SKILL.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - 9466bc7
  - 70c5479
  - 562d042
  - 38144ad
  - 02727b3
  - a7864bc
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: merged-head-includes-parked-items-deadlocks-park-run

Hypothesis: shipping `merged-head-includes-parked-items-deadlocks-park-run` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
