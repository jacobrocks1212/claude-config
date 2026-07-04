---
kind: implemented
feature_id: bug-state-scoped-query-loses-deferred-bug-identity
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [3d9e790, 4da82a8, 4331cdb, 4eec486, 7aa1910]
decisions: []
---

# Implementation Ledger

**What shipped:** `bug-state.py --bug-id <deferred-bug>` ignores the scope and returns the GLOBAL `all-remaining-deferred` terminal with `feature_id: null`, and `curated_stage.py` has no mapping for that terminal. So the `pipeline_visualizer.probe` (and `lazy-queue-doc.py` on top of it) gets no id/stage for an operator-deferred bug, and renders it as a broken `[unknown](docs/bugs/unknown/SPEC.md)` row instead of the intended `⏸ Deferred` row with a working SPEC link.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
