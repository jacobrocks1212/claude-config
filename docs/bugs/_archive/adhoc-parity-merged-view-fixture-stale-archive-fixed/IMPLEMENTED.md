---
kind: implemented
feature_id: adhoc-parity-merged-view-fixture-stale-archive-fixed
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [eb37fe2, 5fde0a6, 9d6db64, eb9bb20, 99ee57f, c150107, 030d205]
decisions: []
---

# Implementation Ledger

**What shipped:** Two merged-view dispatch parity unit tests use stale hermetic "full" SKILL.md fixture text that omits the `--archive-fixed` predicate now required by `_MERGED_VIEW_PREDICATES`, turning `pytest user/scripts/ -q` red.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
