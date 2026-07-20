---
kind: intervention
intervention_id: adhoc-incident-hook-deny-057921
pipeline: bug
provenance: gated
shipped_date: '2026-07-19'
shipped_commit: 46d085ca4ab1319231161675bd40039698d38c39
commit_set: 46d085ca4ab1319231161675bd40039698d38c39
target_signal: undeclared
expected_direction: undeclared
signal_independence: independent
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
  - user/hooks/CLAUDE.md
  - user/hooks/lazy-cycle-containment.sh
  commit_set:
  - 2dab06d
  - 231432d
  - 3fc7668
  - f3998d7
  - 46d085c
  pair_scope: []
  degraded_revert_note: null
  status: open
---

# Intervention: adhoc-incident-hook-deny-057921

Hypothesis: shipping `adhoc-incident-hook-deny-057921` (bug pipeline) moves `undeclared` in direction `undeclared` within 20 post-ship runs.

Signal independence: independent — the `INCIDENT.md` incident_key deny-recurrence count in the deny ledger (`claude-config|hook-deny|lazy-cycle-containment|second-feature-commit`), an independent ledger observable this change does not itself emit or suppress. Expected: the false-deny signature (pathspec-scoped commit denied for a foreign concurrent-lane staged path) drops to zero recurrence, while the genuine bare/`-a` catch is unaffected (no new signature needed to observe the negative case — its absence over subsequent concurrent-completion bursts is the confirming signal).

Reviews are appended below by `user/scripts/efficacy-eval.py` (`## Review <date>` sections). Do not hand-edit the frontmatter — the evaluator is its sole post-capture writer.
