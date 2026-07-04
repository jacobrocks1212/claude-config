---
kind: implemented
feature_id: mark-complete-skips-roadmap-strike-and-followups-queue-trim
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [57c36fe, a5bdc14, 6c3584f, 57f9d15, f3f15ba, a82d6f5]
decisions: []
---

# Implementation Ledger

**What shipped:** When a feature completes, the `__mark_complete__` pseudo-action did not strike through the corresponding ROADMAP row (the operator hand-edited ROADMAP 5× in one run) and its automatic queue-trim silently missed ids ending in `-followups` because it matched on directory basename rather than the resolved spec_dir / full queue id. **Root cause confirmed — and the fix is ALREADY ON DISK** (commit `1b81210`, `unified-pipeline-orchestrator` Phase 5 WU-3), with dedicated regression tests passing.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
