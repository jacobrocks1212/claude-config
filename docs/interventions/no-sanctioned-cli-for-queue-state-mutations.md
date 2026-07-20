---
kind: intervention
intervention_id: no-sanctioned-cli-for-queue-state-mutations
pipeline: bug
provenance: gated
shipped_date: '2026-07-18'
shipped_commit: b43cf70eac4c7e44fb40729a56a59a5c3378f389
commit_set: b43cf70eac4c7e44fb40729a56a59a5c3378f389
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-18T04:13:16Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
---

# Intervention: no-sanctioned-cli-for-queue-state-mutations

Hypothesis: shipping `no-sanctioned-cli-for-queue-state-mutations` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
