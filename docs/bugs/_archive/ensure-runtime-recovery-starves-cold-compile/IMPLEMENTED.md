---
kind: implemented
feature_id: ensure-runtime-recovery-starves-cold-compile
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [9cae7e8, 58e1553, d17dbc0, 31a3baa, d965c93, 56b4e23, 6ea7a7d, d36b88f, 490335f,
  9535e60, b862ed6, '1653757']
decisions: []
---

# Implementation Ledger

**What shipped:** The M4 runtime recovery loop (`_recover_runtime`, ≤5 kill+restart with 1·2·4·8·16s backoff) kill-restarts a runtime that is only "DEAD" because its **cold Rust compile hasn't finished yet**. Each `restart()` (`npm run dev:restart` = `kill-dev && tauri dev`) kills the in-flight compile, so it never completes; all 5 attempts fail and the orchestrator writes a **false** `BLOCKED.md blocker_kind: mcp-runtime-unready`, halting the pipeline.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
