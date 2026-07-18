---
kind: fixed
feature_id: research-gated-head-buried-by-skip-ahead-and-merged-fallthrough
date: 2026-07-18
provenance: backfilled-unverified
validated_via: fix slug-attributed at 4 code sites in lazy-state.py (191, 314, 1747, 1872 - the research_gated_heads surfacing + route_overridden_by research-gated-head re-emit) and documented as shipped behavior in lazy-batch SKILL.md Step 1's "Research-gated head surfacing" box; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

research-gated-head-buried-by-skip-ahead-and-merged-fallthrough marked Fixed on 2026-07-18
by the /lazy-batch-parallel orchestrator applying the docs/bugs/CLAUDE.md out-of-pipeline
reconciliation contract (12th unreconciled fixed-out-of-pipeline SPEC found this run).
Receipt written by the orchestrator, not the pipeline's __mark_fixed__ gate - provenance is
deliberately backfilled-unverified.

## Notes

The fix shipped out-of-pipeline: a feature --emit-prompt probe that skip-ahead advanced past
a research-gated head OUTRANKING the would-be dispatch re-emits as that head's
terminal_reason: needs-research with route_overridden_by: research-gated-head, so an
operator-resolvable research gate is surfaced instead of silently buried; a lower-priority
research head stays unsurfaced (no over-halt). Slug-attributed in place; the orchestrator
contract box in lazy-batch SKILL.md Step 1 documents it as the shipped routing.
