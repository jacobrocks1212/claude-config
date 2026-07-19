---
kind: implemented
feature_id: adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [a1fc408, a1f98e4, 4985c82, 74dbcbb, dba3fb6, 760d1cc, beef5fe, f0a2795]
decisions: []
---

# Implementation Ledger

**What shipped:** `detect_gate_weakening`'s per-file net-count reconciliation flags a false-positive `hit` when a behavior-preserving refactor MOVES a gate-refusal construct out of one file into a shared sibling within the same change.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
