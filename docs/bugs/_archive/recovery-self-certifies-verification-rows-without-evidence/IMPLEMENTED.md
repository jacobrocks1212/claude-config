---
kind: implemented
feature_id: recovery-self-certifies-verification-rows-without-evidence
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [2c9f4fc, '8727905', 8fa668e, 5bbe94c, 8e55a73]
decisions: []
---

# Implementation Ledger

**What shipped:** When a `/lazy-batch` run enters a ledger-recovery or LOOP-DETECTED path, the recovery subagent could tick runtime-verification checkboxes and author validation/skip receipts (VALIDATED.md, SKIP_MCP_TEST.md) without on-disk evidence. **Investigation finding: both side-doors were already closed by two prior fixes (commits `dfbcfa0`, `3f6253f`); the observed incidents predate the landed guards.** Residual scope is a regression test that pins both guards on disk so they can't silently regress.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
