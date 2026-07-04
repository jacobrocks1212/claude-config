---
kind: implemented
feature_id: noncanonical-blocker-filename-invisible-to-state-machine
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [6f25374, 36d7e80, 66b11bb, d46a470, ab8bf1d, 0e60ba1, 0b9abd4]
decisions: []
---

# Implementation Ledger

**What shipped:** In a real `/lazy-batch` run, a cycle-subagent wrote its blocker file under a descriptive, date-suffixed name instead of the canonical `BLOCKED.md`. Because `lazy-state.py` keys halt detection on the exact filename `BLOCKED.md`, the halt was invisible and the state machine re-routed straight back to the same wall — an infinite-loop trigger that was only caught by chance.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
