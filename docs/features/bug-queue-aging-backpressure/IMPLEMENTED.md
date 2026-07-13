---
kind: implemented
feature_id: bug-queue-aging-backpressure
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 337e41d, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** The harness bug backlog only accumulates. Inflow has mechanical caps (incident-scan's `ENQUEUE_CAP = 2`, the run-end refusal on unacked hardening debt) but outflow has NO forcing function: hand-pinned `severity: null` queue entries sort to merged priority 99 — "after every feature" — forever, `_SEVERITY_DEFAULT = 99` makes absent severity a permanent tail, and Concluded-but-never-fixed investigations pile up (23 on disk as of 2026-07-11). This feature adds age-driven backpressure: aged bugs escalate in the merged view (or are drained by a per-N-runs quota), hand-pinned deprioritizations expire instead of living forever, and queue age becomes visible in `LAZY_QUEUE.md`.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
