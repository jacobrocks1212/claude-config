# Build-Queue ETA + Priority Lanes — Feature Specification

> `results/<seq>.json` already records per-op durations; use the history to predict per-op ETAs in `build-queue-status.ps1`, and add a fast lane so a 20-second filtered test run isn't stuck behind a full solution build.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The queue is strict FIFO with no wait-time visibility: an agent (or the operator) queueing a small
test op behind a long build has no ETA, and cheap ops pay worst-case latency. Waiters poll
`build-queue-status.ps1` blind.

## Direction (deliberately not locked)

- **ETA:** rolling per-op duration stats from historical `results/<seq>.json` (data already on
  disk); surfaced in the status view and the wrapper's enqueue message.
- **Lanes:** a bounded fast lane for ops with small historical duration (or explicitly-flagged
  ops), with starvation protection for the main lane — semantics must stay deterministic and
  simple enough to reason about under the existing lock/reclaim machinery.
- **No fidelity regressions:** lane changes must not disturb the hygiene/occupancy gating
  (`Get-BuildQueueOccupancy`, recycle skip) that the recent bug fixes hardened.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: lane admission rule (duration
> percentile vs. explicit op class); whether preemption is ever allowed (likely no); ETA display
> in the skills' banner contract. Solutions above are directional, not locked.
