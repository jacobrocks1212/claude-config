---
kind: fixed
feature_id: merged-head-excludes-parked-not-operator-deferred-deadlocks
date: 2026-07-18
provenance: backfilled-unverified
validated_via: harden-round fix commit 84e656ec (generalized nondispatchable_item_ids resolver) + SPEC regression fixtures passing 6/6 (re-verified in this run's cycle-2 dispatch); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

merged-head-excludes-parked-not-operator-deferred-deadlocks marked Fixed on 2026-07-18 by
the /lazy-batch-parallel orchestrator honoring the harden-harness Round 90 reconciliation
handback (docs/bugs/CLAUDE.md "Fixing a bug OUT-OF-PIPELINE" contract, wired into the
harness by commit 38144ada). This receipt was written by the orchestrator, not the
pipeline's `__mark_fixed__` gate — provenance is deliberately `backfilled-unverified`
(honest debt, never silenced).

## Notes

The SPEC's entire fix scope shipped out-of-pipeline via commit `84e656ec` (harden Round 57,
hardening-log `bf29ed77`): the predicate `spec_dir_operator_deferred`
(`lazy_core/docmodel.py`), the generalized resolver `nondispatchable_item_ids`
(`lazy_core/depdag.py` — ORs park + operator-defer), and both state-script callers are all
present in-tree; the SPEC's regression fixtures (a/c/no-op) pass 6/6, re-verified by this
run's cycle-2 `plan-bug` dispatch. That cycle's NEEDS_INPUT.md (decision: disposition of an
already-fixed bug, recommended reconcile via `--archive-fixed` citing `84e656ec`) is
resolved by this reconciliation — the recommended option was taken; the sentinel rides
into the archive as historical record.
