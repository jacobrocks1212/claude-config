---
kind: intervention
intervention_id: containment-hook-inline-python-exceeds-windows-cmdline-limit
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: 84847b478be9c30f37a71aa84d64f178133ec406
commit_set: 84847b478be9c30f37a71aa84d64f178133ec406
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T16:50:52Z'
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
  - user/hooks/build-queue-enforce.sh
  - user/hooks/lazy-cycle-containment.sh
  - user/scripts/bug-state.py
  commit_set:
  - fb87bff
  - 04ecf96
  - 8fc6f1b
  - 4df6c46
  - 53eb47e
  - 74b8d26
  - '8218388'
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: containment-hook-inline-python-exceeds-windows-cmdline-limit

Hypothesis: shipping `containment-hook-inline-python-exceeds-windows-cmdline-limit` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
