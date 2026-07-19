---
kind: intervention
intervention_id: concurrent-worktree-agent-coordination
pipeline: feature
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: a98faf8cf6764991577dc84294d4a946f2656cee
commit_set: a98faf8cf6764991577dc84294d4a946f2656cee
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-19T02:40:26Z'
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
  - user/hooks/subagent-wedge-backstop.sh
  - user/scripts/lazy-state.py
  - user/scripts/lazy_coord.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/docmodel.py
  - user/scripts/lazy_core/ledgers.py
  - user/scripts/lazy_core/markers.py
  - user/scripts/lazy_core/runtimeplane.py
  - user/skills/_components/sentinel-frontmatter.md
  - user/skills/lazy-batch-parallel/SKILL.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - e4c9ada
  - b361574
  - 4fe5f60
  - 2b3fc2a
  - b066f1b
  - bd0948b
  - e48bb50
  - 56c37dd
  - e7c2b89
  - 15fe485
  - 0d2a9ce
  - 0952a44
  - bc36d13
  - f79c1a1
  - c522d2a
  - 0cd9a25
  - 987d01b
  - 2c80ac6
  - 35b385d
  - 968bc8c
  - bacf500
  - '6505330'
  - 8163d3b
  - ff06ed8
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  - user/skills/lazy/SKILL.md
  - repos/algobooth/.claude/skills/lazy-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: concurrent-worktree-agent-coordination

Hypothesis: shipping `concurrent-worktree-agent-coordination` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
