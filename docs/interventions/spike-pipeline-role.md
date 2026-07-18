---
kind: intervention
intervention_id: spike-pipeline-role
pipeline: feature
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 8a62db7bf0c7d52b3fbdde82f44696cb31b50f80
commit_set: 8a62db7bf0c7d52b3fbdde82f44696cb31b50f80
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T15:42:21Z'
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
  - user/scripts/bug-state.py
  - user/scripts/lazy-parity-manifest.json
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/docmodel.py
  - user/scripts/lazy_core/gates.py
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - a775412
  - 908fb4c
  - 1268aa6
  - 4cee96e
  - 5f8ab04
  - fcb6a6d
  - 2fc8d8f
  - 00fdbe8
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: spike-pipeline-role

Hypothesis: shipping `spike-pipeline-role` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
