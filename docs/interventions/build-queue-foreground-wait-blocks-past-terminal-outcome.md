---
kind: intervention
intervention_id: build-queue-foreground-wait-blocks-past-terminal-outcome
pipeline: bug
provenance: gated
shipped_date: '2026-07-13'
shipped_commit: 87b0579db10c89fcb70554f45f1a45b78ccec061
commit_set: 87b0579db10c89fcb70554f45f1a45b78ccec061
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
  opened: '2026-07-13'
  window_runs: 10
  surfaces:
  - user/scripts/build-queue-foreground-outcome.Tests.ps1
  - user/scripts/build-queue-hygiene.ps1
  - user/scripts/build-queue-runner.ps1
  - user/scripts/build-queue.ps1
  commit_set:
  - 87b0579
  - e643de0
  - a0b97bf
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: build-queue-foreground-wait-blocks-past-terminal-outcome

Hypothesis: shipping `build-queue-foreground-wait-blocks-past-terminal-outcome` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
