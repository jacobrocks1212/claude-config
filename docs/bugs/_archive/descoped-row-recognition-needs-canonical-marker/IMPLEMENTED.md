---
kind: implemented
feature_id: descoped-row-recognition-needs-canonical-marker
date: 2026-07-12
provenance: pipeline-gated
derivation: commit-brackets
commits: [ca3e2b1, 7f15112, f74f821, 879613d, 12d8106, '3247540', 498a5f0]
decisions: []
---

# Implementation Ledger

**What shipped:** `remaining_unchecked_are_verification_only()` recognizes a deliberately-dropped PHASES deliverable only when it is struck through AND tagged with one of THREE hardcoded free-text keywords (`DROPPED`/`DESCOPED`/`WON'T-FIX`). That keyword set is an over-fit shim on a symbol whose "not-to-be-done row unrecognized" class has recurred 4+ times; the durable fix mirrors the `_VERIFICATION_ONLY_MARKER` precedent — producers emit a CANONICAL STRUCTURAL descope marker and the free-text form becomes a deprecation shim.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
