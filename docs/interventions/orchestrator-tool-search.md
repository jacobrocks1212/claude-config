---
kind: intervention
intervention_id: orchestrator-tool-search
pipeline: feature
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: d13e416e75abdb4128cd44aa65831f26b0676076
commit_set: d13e416e75abdb4128cd44aa65831f26b0676076
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-19T23:13:50Z'
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
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - '4268129'
  - 57d1dc0
  - b96296b
  - 0acffa4
  - d0ec434
  - d13e416
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: orchestrator-tool-search

Hypothesis: shipping `orchestrator-tool-search` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
