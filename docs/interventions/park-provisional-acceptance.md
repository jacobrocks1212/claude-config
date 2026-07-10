---
kind: intervention
intervention_id: park-provisional-acceptance
pipeline: feature
provenance: gated
shipped_date: '2026-07-09'
shipped_commit: 4015bb78d134885ff012f4d284b3b73642ae00c1
commit_set: 4015bb78d134885ff012f4d284b3b73642ae00c1
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
  - user/scripts/lazy-parity-manifest.json
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core.py
  - user/skills/_components/completion-integrity-gate.md
  - user/skills/lazy-batch-parallel/SKILL.md
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  commit_set:
  - 4015bb7
  - 239a1a9
  pair_scope:
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
  - repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md
  degraded_revert_note: null
  status: open
---

# Intervention: park-provisional-acceptance

Hypothesis: shipping `park-provisional-acceptance` (feature pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
