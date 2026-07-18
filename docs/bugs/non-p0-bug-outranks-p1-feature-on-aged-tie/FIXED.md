---
kind: fixed
feature_id: non-p0-bug-outranks-p1-feature-on-aged-tie
date: 2026-07-18
provenance: backfilled-unverified
validated_via: fix slug-attributed at 3 code sites (lazy_core/depdag.py:764,816 - the rank-1 age-escalation floor / feature-before-bug tie-break in merged_priority; bug-state.py:9627 coupled mirror); the documented merged-ordering behavior ("bug-beats-feature only for genuine P0") is the root CLAUDE.md's stated contract and drove this run's merged heads; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

non-p0-bug-outranks-p1-feature-on-aged-tie marked Fixed on 2026-07-18 by the
/lazy-batch-parallel orchestrator applying the docs/bugs/CLAUDE.md out-of-pipeline
reconciliation contract (11th unreconciled fixed-out-of-pipeline SPEC found this run).
Receipt written by the orchestrator, not the pipeline's __mark_fixed__ gate - provenance
is deliberately backfilled-unverified.

## Notes

The fix shipped out-of-pipeline in lazy_core.depdag.merged_priority (dated 2026-07-17 in the
code comments): the age-escalation floor caps an aged bug at rank 1 so only a genuine P0 bug
precedes a P1 feature on ties, with the feature-before-bug tie-break — exactly this SPEC's fix
scope, slug-attributed in place. Guard-detection residual for the general class is tracked as
docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs; the ordering generalization is
docs/features/merged-head-actionability-oracle.
