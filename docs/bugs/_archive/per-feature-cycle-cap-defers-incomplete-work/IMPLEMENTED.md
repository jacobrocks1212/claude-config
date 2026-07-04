---
kind: implemented
feature_id: per-feature-cycle-cap-defers-incomplete-work
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [7ae810c, a8f9307, fe9679d, de0bf5a, '8665408', acb8c85]
decisions: []
---

# Implementation Ledger

**What shipped:** The per-feature budget guard (`L_task` ceiling) is **default-on**: it trips on a per-feature forward-cycle count and defers (then evicts) a feature to the queue tail mid-progress. The operator rejects this behavior outright — a half-done feature parked at the tail is worse than letting it finish. Make the guard **opt-in** (off by default; armed only via `--per-feature-cycle-cap <N>`); rely on the whole-run `max_cycles` ceiling as the sole default budget.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
