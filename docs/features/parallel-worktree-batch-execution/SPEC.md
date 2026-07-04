# Sanctioned Parallel-Worktree Batch Execution — Feature Specification

> The concurrent-walker refusal correctly bans *unarbitrated* second walkers, but the flip side is one repo = one lane. A coordinator that shards dependency-independent queue items across worktrees (per-item branch + marker arbitration) would be the single biggest throughput multiplier in the system.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock; `queue-dependency-dag` is the obvious readiness-signal prerequisite)

---

## Problem

Queue items that share no files or dependencies still execute strictly serially per repo. All the
arbitration machinery built so far (`refuse_run_start_clobber`, single-slot marker ownership,
per-repo keyed state) exists to *prevent* accidental concurrency — there is no sanctioned path to
*deliberate* concurrency.

## Direction (deliberately not locked)

- **Coordinator:** an orchestrator-level sharder that claims N independent ready items (readiness
  from the `queue-dependency-dag` proposal), assigns each a worktree + branch + its own scoped
  run marker, and merges/serializes completion (queue.json/ROADMAP writes are the contended
  resource — single-writer discipline required).
- **Arbitration, not bypass:** extends the existing marker-ownership model (perhaps marker-per-
  item-lane under one parent run) rather than weakening `refuse_run_start_clobber`.
- **Containment unchanged:** each lane's cycle subagent stays under the existing containment
  hooks; the coordinator is the only new privileged actor.
- **Merge policy:** per-item branches land back on the work branch with deterministic ordering;
  conflicts demote an item back to serial.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: independence criterion (dep-DAG
> only vs. file-overlap prediction); lane count/budget split; failure isolation (one lane's
> BLOCKED must not halt siblings); build-queue interaction on shared hosts. Solutions above are
> directional, not locked. High ambition — expect multi-phase.
