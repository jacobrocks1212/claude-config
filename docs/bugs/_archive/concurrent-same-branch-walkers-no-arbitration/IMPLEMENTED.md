---
kind: implemented
feature_id: concurrent-same-branch-walkers-no-arbitration
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [5f19093, e552e3e, 8c67038, be3777e, df6672b, d5365ce]
decisions: []
---

# Implementation Ledger

**What shipped:** When two autonomous `/lazy-batch` queue-walkers run against the same repo/branch (same git account), the second walker's `--run-start` silently overwrites the first's live run marker instead of being refused — because `refuse_run_start_clobber` allows ALL same-pipeline overwrites (it cannot distinguish a sanctioned checkpoint-resume from a genuinely-concurrent second walker). With no deterministic arbitration, collisions on feature selection and push ordering surface mid-run and escalate to the operator, and overlapping edits fall to manual multi-commit merges.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
