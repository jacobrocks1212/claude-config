---
kind: intervention
intervention_id: anti-overfit-design-gate
pipeline: feature
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: 8845b069986f95d8e84af380d52318587ab483e5
commit_set: 8845b069986f95d8e84af380d52318587ab483e5
target_signal: kpi:anti-overfit-gate.gate-weakening-unreviewed-reaching-main
expected_direction: decrease
signal_independence: independent
baseline:
  status: not-computable
  reason: non-event-target
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
  - user/skills/_components/sentinel-frontmatter.md
  - user/skills/harden-harness/SKILL.md
  commit_set:
  - 03993c0
  - 2cf3289
  - 7bf8c9b
  - 501ac8c
  - dde89ea
  - '9243257'
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: anti-overfit-design-gate

Hypothesis: shipping `anti-overfit-design-gate` (feature pipeline) moves `kpi:anti-overfit-gate.gate-weakening-unreviewed-reaching-main` in direction `decrease` within 20 post-ship runs.

Signal independence: independent — gate-weakening incidents reaching `main` unreviewed are produced by `intervention-efficacy-tracking` REFUTED verdicts and `/lazy-batch-retro` findings, NOT by the gate itself. The gate cannot suppress its own target signal (a change the gate wrongly passed that efficacy later REFUTES indicts the gate's verdict — the definition of a signal it does not control).

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
