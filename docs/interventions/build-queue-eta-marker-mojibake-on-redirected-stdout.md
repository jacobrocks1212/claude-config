---
kind: intervention
intervention_id: build-queue-eta-marker-mojibake-on-redirected-stdout
pipeline: bug
provenance: gated
shipped_date: '2026-07-10'
shipped_commit: 801aec123f3e2d589d0d029e35302dccd931a0f4
commit_set: 801aec123f3e2d589d0d029e35302dccd931a0f4
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
  opened: '2026-07-10'
  window_runs: 10
  surfaces:
  - user/hooks/CLAUDE.md
  - user/hooks/build-queue-enforce.sh
  - user/hooks/long-build-ownership-guard.sh
  - user/scripts/build-queue-hygiene.Tests.ps1
  - user/scripts/build-queue-hygiene.ps1
  - user/scripts/build-queue-runner.ps1
  - user/scripts/build-queue-status.ps1
  - user/scripts/build-queue.ps1
  commit_set:
  - 801aec123f3e2d589d0d029e35302dccd931a0f4
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: build-queue-eta-marker-mojibake-on-redirected-stdout

Hypothesis: shipping `build-queue-eta-marker-mojibake-on-redirected-stdout` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
