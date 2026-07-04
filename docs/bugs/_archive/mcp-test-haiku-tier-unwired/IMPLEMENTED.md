---
kind: implemented
feature_id: mcp-test-haiku-tier-unwired
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [aa6e36d, 671c999]
decisions: []
---

# Implementation Ledger

**What shipped:** `/lazy-batch` dispatches every happy-path `/mcp-test` cycle on **Opus**, even though the skill was "switched to haiku." The switch landed only as description prose; the dispatch-model selector has no haiku branch.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
