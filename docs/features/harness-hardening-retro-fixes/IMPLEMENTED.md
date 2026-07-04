---
kind: implemented
feature_id: harness-hardening-retro-fixes
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [07f1c11, 54ee7be, 33d27b7, 46e2e90, 244cbd0, 5c6fc83, 34aa088, ac4a653, 5aa6962,
  a29f670, 715b4da]
decisions: []
---

# Implementation Ledger

**What shipped:** Fix the concrete findings from the 2026-06-16 lazy-batch retro, and give `/harden-harness` an anti-overfit reflex: fix the instance now, but spin off a generalized `/spec`/`/spec-bug` when it detects it is patching a symptom of a broader class.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
