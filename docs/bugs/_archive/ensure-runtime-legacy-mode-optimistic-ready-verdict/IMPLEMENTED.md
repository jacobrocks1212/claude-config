---
kind: implemented
feature_id: ensure-runtime-legacy-mode-optimistic-ready-verdict
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [fc7c071, 55abfc3, 5daac4b, f56d920, 3d8e282, b589ef9]
decisions: []
---

# Implementation Ledger

**What shipped:** `ensure_runtime` returns `state: READY` with `health_code: 0` (both ports down) whenever it falls to legacy mode (unbound run marker), so `/lazy-batch` Step 1d.0 dispatches an `mcp-test` agent against a dead runtime — wasted work the orchestrator then has to recover by taking over the cold compile itself.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
