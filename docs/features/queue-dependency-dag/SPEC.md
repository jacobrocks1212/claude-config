# First-Class Dependency DAG in queue.json — Feature Specification

> Hard-deps live only in ROADMAP prose ("hard-deps `unified-pipeline-orchestrator`"); make `deps: [...]` a queue-entry field the state scripts enforce, so skip-ahead (`feature-budget-guard-and-skip-ahead`) can jump *around* dependency chains safely instead of only around blocked heads.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

Dependency knowledge exists (ROADMAP prose, SPEC `**Depends on:**` blocks) but is invisible to the
state machine: ordering is the only enforcement, so a reorder or skip-ahead can dispatch an item
before its dependency completes, and independent items can't be identified mechanically for
future parallel execution.

## Direction (deliberately not locked)

- **Schema:** optional `deps: ["<id>", ...]` on queue entries (both pipelines; parity-guarded);
  absent → today's behavior, byte-identical.
- **Enforcement:** `compute_state()` treats an item with an incomplete dep as not-ready — the same
  readiness predicate shape skip-ahead already uses; cycle detection at queue load.
- **Feeder:** `/spec-phases` or mark-complete could sync SPEC dep-blocks → queue field so prose
  and machine state don't drift.
- **Downstream consumer:** the parallel-worktree proposal needs exactly this readiness signal.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: dep kinds (hard vs. composes vs.
> soft — SPECs already use these labels); cross-pipeline deps (feature ↔ bug); drift detection
> between SPEC prose and queue field. Solutions above are directional, not locked.
