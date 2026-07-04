---
kind: implemented
feature_id: queue-dependency-dag
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [0263f6b, 6562c4e, 248de27, 64da7c6, 778f77c, 32b8208, db5a565, 2c38924, eefd57b,
  5bd4cae]
decisions: []
---

# Implementation Ledger

**What shipped:** Dependency knowledge today lives in prose (SPEC `**Depends on:**` blocks, ROADMAP hard-dep notes) and is consulted by the state machine in exactly one place — the skip-ahead branch. This feature makes `deps: [...]` an optional, machine-enforced queue-entry field on BOTH pipelines: an item whose declared dependency is not Complete is held as not-ready by `compute_state()` (the same readiness-predicate shape skip-ahead already uses), cycles and dangling ids are caught deterministically, a script-owned feeder syncs SPEC dep-blocks into the queue field so prose and machine state cannot silently drift, and the readiness signal becomes the foundation the `parallel-worktree-batch-execution` coordinator shards on. Entries without `deps` behave byte-identically to today.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: COMPLETED.md (provenance: gated).**
