---
kind: implemented
feature_id: mobile-queue-control
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [dfeb343, fdad013, 7197ed8, a01c5ad, 6afce4c, 51bc4cb, 603d1bf, 6c582d3, 18172e3,
  cb30631, 9b04cbe]
decisions: []
---

# Implementation Ledger

**What shipped:** An auto-generated, always-current, **read-only** markdown document — one per lazy-enabled repo — that renders the repo's lazy feature + bug queue (with per-item drill-in) on **GitHub mobile**. Generated purely from on-disk lazy state and kept up to date as the pipeline progresses. **Reads happen on GitHub mobile; writes (reorder / remove / enqueue) stay in chat** via the existing `--reorder-queue` / `--enqueue-adhoc` CLI — nothing new is built for writes.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
