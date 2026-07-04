---
kind: implemented
feature_id: adhoc-checkpoint-resume-field-complete-continuity
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [5cf3908, 67e48c4, 4df50e1, 844d0b4, 2cf5680, 37f5ed2]
decisions: []
---

# Implementation Ledger

**What shipped:** A sanctioned same-run checkpoint resume re-mints ALL run-scoped marker state on the resuming `--run-start`; every continuity field must be carried back individually by `restore_checkpoint_counters`. Each missing field has been patched reactively (whack-a-mole). Durable fix: make resume continuity field-complete BY CONSTRUCTION via an enumerated allow-list of carry vs. reset marker fields.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
