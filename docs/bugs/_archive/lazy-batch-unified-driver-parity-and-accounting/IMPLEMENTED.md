---
kind: implemented
feature_id: lazy-batch-unified-driver-parity-and-accounting
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [7bdb6f2, 092a0d7, 6e18dad, 0cc2dd4, 644c592, b74d6b3]
decisions: []
---

# Implementation Ledger

**What shipped:** Three harness defects surfaced in the 2026-06-17 `/lazy-batch` run on `claude-config`: (1) the run-marker cycle counters undercount because pseudo-skill cycles produce no advance signal; (2) the unified driver never archives/trims fixed bugs (it omits the `--archive-fixed` call `/lazy-bug-batch` chains); (3) `/lazy-batch` fails to pick up an on-disk bug that is absent from `queue.json` the way `/lazy-bug-batch` does — defeated by ordering-only merged heads masked by stale untrimmed entries, plus a silent exception-swallow in the merged bug-load bridge.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
