---
kind: implemented
feature_id: budget-guard-defers-near-complete-feature
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [4ca39d8, 2280ad6, 69c059e, d80363e, 4ca47ba, 299e9a3, a8d18fb, 98c0d1f, ce8f88b,
  aca98ae, a106246]
decisions: []
---

# Implementation Ledger

**What shipped:** The per-feature budget guard trips on a raw forward-cycle count with no proximity-to-completion signal, so a feature that did legitimate corrective work (not monopolization) gets deferred to the live-queue tail one `/mcp-test` cycle from `VALIDATED.md`, leaving it parked and a rebuilt runtime idle.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
