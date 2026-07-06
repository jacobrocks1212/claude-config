---
kind: intervention
intervention_id: build-queue-enforce-cd-prefix-bypass
pipeline: bug
provenance: gated
shipped_date: '2026-07-06'
shipped_commit: 06647a22fc2d6c70d7ca7fb0bde3cbf1bed882e6
commit_set: 06647a22fc2d6c70d7ca7fb0bde3cbf1bed882e6
target_signal: undeclared
expected_direction: undeclared
signal_independence: undeclared
baseline:
  status: not-computable
  reason: undeclared
  last_run_id: '2026-07-06T03:03:19Z'
review_after_runs: 20
min_sample: 5
band_pct: 20
review_count: 0
status: open
escalated: false
reconsideration_enqueued: null
---

# Intervention: build-queue-enforce-cd-prefix-bypass

Hypothesis: shipping `build-queue-enforce-cd-prefix-bypass` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
