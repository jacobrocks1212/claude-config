---
kind: implemented
feature_id: env-transient-counts-against-validation-retry-budget
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [d4e115c, 1fc0b3e, 33ef519, 70ceac3, 40e77e6, 4b18f97]
decisions: []
---

# Implementation Ledger

**What shipped:** During a `/lazy-batch` run on AlgoBooth, an orchestrator-caused environment transient — a stale Windows named-pipe handle / zombie node process left behind by a `dev:restart` — prevented the dev sidecar from booting. Because the runtime never came up, every MCP assertion went pending and the failure surfaced as a *validation BLOCKED at retry 5*, inflating the feature's validation-escalation count even though no code was wrong. The validation-retry accounting does not distinguish a self-inflicted environment transient from a genuine code failure.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
