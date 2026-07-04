---
kind: implemented
feature_id: no-sanctioned-queue-reorder-command
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [b81b5eb, feab67c, 6c6fc6e, d5673e9, 2f88af1]
decisions: []
---

# Implementation Ledger

**What shipped:** When the operator directs a queue reorder (e.g., move features to the tail), there is no sanctioned queue-reorder command in `lazy-state.py` / `bug-state.py`, and HARD CONSTRAINT 1 bars the orchestrator from editing `queue.json` directly. So the orchestrator turns a simple deterministic state mutation into a sentinel write (BLOCKED.md) plus a fully dispatched apply-resolution subagent — a whole meta-cycle to accomplish a reorder. This is a standing capability gap between HARD CONSTRAINT 1 and the absent reorder primitive.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
