---
kind: implemented
feature_id: research-gate-ignores-existing-phases
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [7d8ee6a, 8f1f429, f9792d7, 5f70300, efe2bed, 017bf67]
decisions: []
---

# Implementation Ledger

**What shipped:** `lazy-state.py`'s Step 5 research gate decides solely on RESEARCH*.md presence and never inspects PHASES.md, so a feature whose phases are already implemented gets routed to `needs-research` — wasting a full Gemini research prompt + ingest round-trip on work that is already done.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
