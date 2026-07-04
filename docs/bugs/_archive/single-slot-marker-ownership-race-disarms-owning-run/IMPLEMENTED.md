---
kind: implemented
feature_id: single-slot-marker-ownership-race-disarms-owning-run
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [5086b6d, 64b20d6, 6ca2ace, 3b36646, 6e1b5b7, '7835196']
decisions: []
---

# Implementation Ledger

**What shipped:** A run marker's owner is a SINGLE mutable `session_id` slot, stamped first-writer-wins by an allow-time bind. The slot is now well-protected against OVERWRITE (clobber-refused, idempotent re-bind), but it carries NO fencing token and the owning run has NO detect/re-arm path: if the slot is ever stamped with the WRONG session (a pre-allow bind race, or a non-orchestrator allow), the TRUE owner's own dispatches read "owned by someone else → `read_run_marker` returns None → fast-path ALLOW" — silently disarming the guard mid-run with no signal.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
