---
kind: implemented
feature_id: adhoc-derive-cycle-commit-budget
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [5636fe3, 86af25c, 54a998d, 05b2736, f0c6c3c, 128d960, 5bf780d, baff5c2, e765721,
  b1c53e3, 07111c6]
decisions: []
---

# Implementation Ledger

**What shipped:** The hand-maintained `_CYCLE_COMMIT_BUDGET` allow-list in `lazy_core.py` silently defaults any unenumerated multi-commit sub_skill to budget 1, false-positiving `unexpected-commits` at `--cycle-end`. The missing-row defect class has recurred five times; replace the reactive literal table with a budget derived from the orchestrator dispatch-skill registry so a newly-added multi-commit sub_skill cannot silently default to 1.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
