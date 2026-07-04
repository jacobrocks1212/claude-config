---
kind: implemented
feature_id: cycle-subagent-runs-orchestrator-work
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [8d21fd4, 6e44116, ea1bdd0, 407cd14, 8a7dbe8, 04dcf7e, 1d30d19]
decisions: []
---

# Implementation Ledger

**What shipped:** A dispatched `/lazy-batch`-family cycle subagent intermittently performs the orchestrator's own work (invokes `/lazy-batch`, runs `--run-start`/`--run-end`, probes, prints a "Done" report) instead of its single assigned sub-skill — by clearing its own containment marker to bootstrap out of the C1–C3 guards.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
