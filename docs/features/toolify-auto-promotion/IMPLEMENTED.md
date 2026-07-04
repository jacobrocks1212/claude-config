---
kind: implemented
feature_id: toolify-auto-promotion
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [7b28024, e2b10bf, 0dd26e7, 89cd14a, 054d417, 7175e96, 381677b, b982d4c, 1f5717d,
  950a057]
decisions: []
---

# Implementation Ledger

**What shipped:** `toolify-miner.py` proposes ranked, evidence-backed toolification candidates, but every promotion is hand-authored today, so above-bar candidates rot in a report. This feature ships a **materializer**: a deterministic script step that converts one above-bar miner candidate into a stub feature SPEC (with the miner's occurrence/token evidence embedded) plus a queue entry via the existing script-owned enqueue path — routed through the same `/spec` Step 4.5 interactive baseline-lock as any other stub, so auto-drafting never becomes auto-approval. A central promotion ledger records promoted/declined outcomes per candidate signature, deduplicates re-promotion, and feeds a report-only acceptance-rate view so the bar's thresholds can be tuned deliberately from real data.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
