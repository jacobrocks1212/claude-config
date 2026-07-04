---
kind: implemented
feature_id: mcp-tooling-not-predetermined-at-planning
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [930665b, 273dd95, 63e72f7, c70efde]
decisions: []
---

# Implementation Ledger

**What shipped:** The lazy feature pipeline never enumerates the MCP tool surface a feature's own `/mcp-test` scenario will call, so a missing tool is only discovered at Step 9 (pipeline end) — after full planning and implementation — forcing a corrective add-phase or `adhoc-mcp-*` spin-off and 3–6 wasted Step-9 cycles.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
