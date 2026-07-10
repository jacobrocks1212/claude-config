---
kind: intervention
intervention_id: stub-origin-provisional-exclusion
pipeline: feature
provenance: gated
shipped_date: '2026-07-09'
shipped_commit: bba6fca59f51c854af6419b1796f7caa165dcf94
commit_set: bba6fca59f51c854af6419b1796f7caa165dcf94
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
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core.py
  - user/skills/lazy-batch/SKILL.md
  commit_set:
  - bba6fca
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: stub-origin-provisional-exclusion

Hypothesis: shipping `stub-origin-provisional-exclusion` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
