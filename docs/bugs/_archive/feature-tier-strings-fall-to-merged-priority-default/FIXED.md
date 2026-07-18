---
kind: fixed
feature_id: feature-tier-strings-fall-to-merged-priority-default
date: 2026-07-18
provenance: backfilled-unverified
validated_via: fix slug-attributed at 3 code sites in lazy_core/depdag.py (756 _MERGED_SEVERITY_RANK coercion comment, 794 unresolvable-tier fallback, 973 multi-enum feature parsing); merged ordering exercised live throughout the 2026-07-18 run; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

feature-tier-strings-fall-to-merged-priority-default marked Fixed on 2026-07-18 by the
/lazy-batch-parallel orchestrator applying the docs/bugs/CLAUDE.md out-of-pipeline
reconciliation contract (12th unreconciled fixed-out-of-pipeline SPEC found this run).
Receipt written by the orchestrator, not the pipeline's __mark_fixed__ gate - provenance is
deliberately backfilled-unverified.

## Notes

The fix shipped out-of-pipeline in lazy_core.depdag.merged_priority's tier parsing: string /
multi-enum tier values are coerced onto the merged severity rank scale instead of falling
through to MERGED_PRIORITY_DEFAULT (which sorted real features dead-last), with the
unresolvable-tier fallback documented in place. Slug-attributed at all three touch sites.
Guard-detection residual for the fixed-unreconciled class is tracked as
docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs.
