---
kind: implemented
feature_id: byref-dispatch-undercounts-forward-cycles
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [fa2d785, 674e0df, bd67ebe, 2716c83, 09f3893, '8149351', 7ac54f3, a2469a4, 750d725,
  ec9688e]
decisions: []
---

# Implementation Ledger

**What shipped:** In real `/lazy-batch` runs, the only forward-advance trigger that fires for real-skill (by-reference) dispatch cycles — `advance_run_counters` — reads a NON-MONOTONIC dispatch oracle (`consumed_emission_count()`). Two mechanisms (the `advance_meta_cycle` watermark `+1`-absorb, and ring-cap eviction of consumed registry entries) freeze or regress that oracle below the persisted watermark, so `forward_cycles` stalls while real cycles keep running and the deterministic max-cycles cap never fires.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
