---
kind: intervention
intervention_id: workstation-recursive-subagent-dispatch
pipeline: feature
provenance: gated
shipped_date: '2026-07-09'
shipped_commit: 5ff570bf758cc7c4d77acf3edf5b89a52f41d637
commit_set: 5ff570bf758cc7c4d77acf3edf5b89a52f41d637
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-04T14:38:18Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
canary:
  opened: '2026-07-09'
  window_runs: 10
  surfaces:
  - user/skills/lazy-batch-parallel/SKILL.md
  - user/skills/lazy-batch-retro/SKILL.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - 5ff570b
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: workstation-recursive-subagent-dispatch

Hypothesis: shipping `workstation-recursive-subagent-dispatch` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
