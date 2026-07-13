---
kind: intervention
intervention_id: phases-slice-scoped-reads
pipeline: feature
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: 54de5622f0a28cc64abff63eab139966aae545ed
commit_set: 54de5622f0a28cc64abff63eab139966aae545ed
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
  - user/hooks/execute-plan-compact-reorient.sh
  - user/hooks/lazy-cycle-containment.sh
  - user/scripts/lazy_core.py
  - user/skills/harden-harness/SKILL.md
  - user/skills/lazy-batch-parallel/SKILL.md
  - user/skills/lazy-batch-retro/SKILL.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - user/skills/lazy-bug-status/SKILL.md
  - user/skills/lazy-bug/SKILL.md
  - user/skills/lazy/SKILL.md
  commit_set:
  - 1a3dffd
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  - user/skills/lazy/SKILL.md
  - user/skills/lazy-bug/SKILL.md
  - repos/algobooth/.claude/skills/lazy-cloud/SKILL.md
  - user/skills/lazy-status/SKILL.md
  - user/skills/lazy-bug-status/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: phases-slice-scoped-reads

Hypothesis: shipping `phases-slice-scoped-reads` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
