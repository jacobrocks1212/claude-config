---
kind: fixed
feature_id: merged-head-diverged-stalls-on-gated-head
date: 2026-07-18
provenance: backfilled-unverified
validated_via: fix slug-attributed at 3 code sites (lazy-state.py:14058, bug-state.py:9606 coupled mirror, lazy_core/dispatch.py:441 docstring) - the deferred-head exclusion in the merged-head-diverged withhold; behavior exercised LIVE this run (device/operator-deferred and parked heads were excluded from divergence withholds; the residual research-skip + cross-script facets were separately fixed by Rounds 91-92); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

merged-head-diverged-stalls-on-gated-head marked Fixed on 2026-07-18 by the
/lazy-batch-parallel orchestrator applying the docs/bugs/CLAUDE.md out-of-pipeline
reconciliation contract (10th unreconciled fixed-out-of-pipeline SPEC found this run).
Receipt written by the orchestrator, not the pipeline's __mark_fixed__ gate - provenance
is deliberately backfilled-unverified.

## Notes

The fix shipped out-of-pipeline: the merged-head-diverged withhold's exclude set gained the
probe-skipped ids (device_deferred_features / operator_deferred) so a deferred gated head no
longer stalls dispatch, mirrored across both state scripts. Successor facets discovered and
fixed during THIS run: research-skipped heads (Round 91, baf07a6d) and the cross-script
flag-gating split-brain (Round 92, 981191ae); the generalization is queued as
docs/features/merged-head-actionability-oracle. This SPEC's own facet is on disk and was
exercised live tonight.
