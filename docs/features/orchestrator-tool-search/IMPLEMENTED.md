---
kind: implemented
feature_id: orchestrator-tool-search
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: ['4268129', 57d1dc0, b96296b, 0acffa4, d0ec434, d13e416]
decisions: []
---

# Implementation Ledger

**What shipped:** A thin `--tool-search` CLI the `/lazy-batch` orchestrator invokes when it hits an abnormal situation needing a specific action/tool — ranked matches over the existing tool inventories; a miss auto-dispatches a backgrounded `/harden-harness` to build the tool and, when the operation is correctness-load-bearing, holds the run until it ships.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
