---
kind: implemented
feature_id: ensure-runtime-false-hijacked-on-owned-serving-runtime
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [ee0717f, fa4d185, 5819dea, 3bd420f, a919f07, fe8d2ae, 5a9f232, d08de8c, 0638b62]
decisions: []
---

# Implementation Ledger

**What shipped:** `lazy-state.py --ensure-runtime` returns the terminal `HIJACKED` fail-safe for a runtime that is provably this run's own (health 200 + MCP tools present), because the runtime lock's recorded `controller_session_id` and the threaded `live_session_id` come from different sources and diverge. The recorded recovery (`dev:kill` + fresh boot) does not cure it — the next cycle re-stamps a divergent identity and re-reports HIJACKED.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
