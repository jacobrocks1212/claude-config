---
kind: implemented
feature_id: park-mode-halts-on-blocked
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [b19f6ed, 110ed29, 1f33a4b, f50ee57, 5ef9ce1, '7841852', 926107b, 4528eba, 0ff44a7,
  5509e81, 34dbf24, 017bf67]
decisions: []
---

# Implementation Ledger

**What shipped:** `--park` mode parks `NEEDS_INPUT.md` features and advances the queue, but a `BLOCKED.md` feature is still selected and returns `terminal_reason="blocked"`, forcing the orchestrator into Step 1h resolution instead of deferring it. In an (unattended) park run that is an interruption — park mode should park the blocked feature and move on.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
