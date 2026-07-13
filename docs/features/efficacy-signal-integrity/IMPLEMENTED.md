---
kind: implemented
feature_id: efficacy-signal-integrity
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 81dd24d, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** The measurement plane of the self-improving harness, layered on the two 2026-07-11 capture/scope bug fixes: (a) sub-signal targets (`event:gate-refusal/<signature>`) so co-shipped hardening rounds measure disjoint signals instead of being confounder-capped INCONCLUSIVE by construction; (b) a canary staleness alarm so 19 open canaries cannot silently mass-expire into `closed-clean (no-data)`; (c) scorecard freshness + per-row signal VANTAGE so NO-DATA distinguishes "wrong repo/machine to observe this" from "signal genuinely absent", and the scorecard regenerates where its registry actually lives.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
