---
kind: fixed
feature_id: dispatch-probe-and-inject-bypass-merged-head
date: 2026-07-18
provenance: backfilled-unverified
validated_via: harden-round fix commit 1af48e1d (route dispatch-bound probe + inject hook by merged head) + downstream regression coverage in test_dispatch.py; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

dispatch-probe-and-inject-bypass-merged-head marked Fixed on 2026-07-18 by the
/lazy-batch-parallel orchestrator honoring the harden-harness Round 90 reconciliation
handback (docs/bugs/CLAUDE.md "Fixing a bug OUT-OF-PIPELINE" contract, wired into the
harness by commit 38144ada). This receipt was written by the orchestrator, not the
pipeline's `__mark_fixed__` gate — provenance is deliberately `backfilled-unverified`
(honest debt, never silenced).

## Notes

The SPEC's entire fix scope shipped out-of-pipeline via commit `1af48e1d` ("route
dispatch-bound probe + inject hook by merged head"): all 5 fix-scope items are present
in-tree and attributed to this slug in code comments, with two follow-up bugs already
built on top (`merged-head-includes-parked-items-deadlocks-park-run`,
`merged-head-excludes-parked-not-operator-deferred-deadlocks`). Verified live this run:
the cycle-1 `plan-bug` dispatch's Root-Cause Trace Gate (SEAM A) passed with citations
against the serving code, and this orchestrator's own cycle-1/2 probes exercised the
fixed `route_overridden_by: merged-head-diverged` behavior end-to-end. The cycle-1
NEEDS_INPUT.md (decision: reconcile-as-Fixed, recommended `--archive-fixed` +
`--link-provenance --commits 1af48e1d`) is resolved by this reconciliation — the
recommended option was taken; the sentinel rides into the archive as historical record.
