---
kind: implemented
feature_id: adhoc-ensure-runtime-test-injects-signal-under-test
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [1f57880, 6753d00, d76276f, 827d3f8, afaf9ef, 0cc547c, d698e02, 9b481f5]
decisions: []
---

# Implementation Ledger

**What shipped:** The `ensure_runtime` cold-boot/runtime-recovery "production-binding" tests in `test_lazy_core.py` reach green by injecting a hand-set stand-in for the very OS-level signal whose production derivation is under test — so a defect in that derivation ships behind a green test (a recurring false-green; three rounds).

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
