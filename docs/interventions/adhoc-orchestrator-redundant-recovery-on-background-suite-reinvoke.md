---
kind: intervention
intervention_id: adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: fbd4433246b9c9bd7b9fd542bde6fb95e5c3ce14
commit_set: fbd4433246b9c9bd7b9fd542bde6fb95e5c3ce14
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-19T14:30:33Z'
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
  - user/hooks/cycle-subagent-bg-gate-guard.sh
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/markers.py
  - user/settings.json
  - user/skills/_components/sentinel-frontmatter.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - '3451039'
  - f56959d
  - 7dbcaf9
  - aef06e3
  - 08bcfbd
  - 8dded98
  - '1118807'
  - 18bd635
  - 641cd85
  - 43d4ac9
  - fbd4433
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke

Hypothesis: shipping `adhoc-orchestrator-redundant-recovery-on-background-suite-reinvoke` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
