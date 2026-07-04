---
kind: implemented
feature_id: host-capability-declaration-for-gated-features
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [48d5d30, 41e5e6b, 763c63b, 4fbc3a8, a3e6784, 9aeb0cd, 1fb5faf, 656ad8f, 921d695,
  b5c4ebe, 6c6d6d5, '1068823']
decisions: []
---

# Implementation Ledger

**What shipped:** Let a feature declare the host capabilities (binary toolchains, audio/GPU devices) its runtime validation requires, and have the state script proactively defer/skip features whose capabilities are absent on the current host — instead of each one churning through BLOCKED/SKIP/AskUserQuestion at the Step-9 mcp-test boundary.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
