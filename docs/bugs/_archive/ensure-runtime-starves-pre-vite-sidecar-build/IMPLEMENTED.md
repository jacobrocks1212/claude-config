---
kind: implemented
feature_id: ensure-runtime-starves-pre-vite-sidecar-build
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [24e79e6, f579df8, 143ff11, e5f0056, 9cae7e8]
decisions: []
---

# Implementation Ledger

**What shipped:** `lazy-state.py --ensure-runtime` kill-restarts a cold AlgoBooth dev runtime into a false `mcp-runtime-unready` BLOCKED, because the cold-compile discriminator's only "still booting" signal is Vite (`:1420`) being up — which is false during the multi-minute `BeforeDevCommand` (`npm run sidecar:build && vite`) phase, when BOTH ports are down and the boot is misclassified `dead`.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
