---
kind: intervention
intervention_id: skip-mcp-test-frontmatter-unquoted-colon
pipeline: bug
provenance: gated
shipped_date: '2026-07-06'
shipped_commit: 4b2bb66c7370588fe5990d91fd8509aca4fe4bbc
commit_set: 4b2bb66c7370588fe5990d91fd8509aca4fe4bbc
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
canary:
  opened: '2026-07-06'
  window_runs: 10
  surfaces:
  - user/scripts/lazy_core.py
  commit_set:
  - 4b2bb66
  - 46bb6cb
  - 4601fbb
  - d650926
  - f9e30b7
  - 3b736ac
  - 501ac8c
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: skip-mcp-test-frontmatter-unquoted-colon

Hypothesis: shipping `skip-mcp-test-frontmatter-unquoted-colon` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
