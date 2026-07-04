---
kind: implemented
feature_id: operator-checkpoint-resume-counter-reset
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [9ece294, 48215c5, 5428b48, f943bcc, 42b327d, 7a10b4a, 116cdab, 2a31690, 91e76cf,
  15ce2bf]
decisions: []
---

# Implementation Ledger

**What shipped:** When an operator concludes a `/lazy-batch` run by an **operator-authorized checkpoint**, clears context, and re-invokes `/lazy-batch <N>`, the resumed run currently *restores* the paused `forward_cycles`/`meta_cycles` instead of starting a fresh budget. The operator wants them reset to 0 in this case.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
