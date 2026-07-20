---
kind: fixed
feature_id: cycle-budget-counters-double-count-on-probes-and-inject-hook
date: 2026-07-18
provenance: backfilled-unverified
validated_via: fix slug-attributed at 5 code sites (lazy-state.py:12797,13316,13971; bug-state.py:8582,9544 - coupled pair) and documented as the shipped mechanism in lazy-batch SKILL.md HARD CONSTRAINT 8 ("THE SCRIPT is the sole budget-counting authority; --repeat-count probe and inject hook are BUDGET-NEUTRAL"); exercised LIVE all of the 2026-07-18 run (script-advanced counters at --cycle-end, repeated same-turn probes never inflated the budget); NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

cycle-budget-counters-double-count-on-probes-and-inject-hook marked Fixed on 2026-07-18 by
the /lazy-batch-parallel orchestrator applying the docs/bugs/CLAUDE.md out-of-pipeline
reconciliation contract (9th unreconciled fixed-out-of-pipeline SPEC found this run). Receipt
written by the orchestrator, not the pipeline's __mark_fixed__ gate - provenance is
deliberately backfilled-unverified.

## Notes

The fix shipped out-of-pipeline: budget counting moved wholly into the state scripts (advance
at --cycle-end keyed on the cycle marker's --kind, and at --apply-pseudo), with --repeat-count
probes and the per-turn inject hook made budget-neutral (they advance only loop-detection
streaks, further debounced by the registry consume-count delta). The orchestrator's own
governing prose (HARD CONSTRAINT 8, Step 1a) documents the shipped behavior and this run
executed under it end-to-end - repeated same-turn emit probes (used throughout for prompt
capture) never moved [fwd/60]. Guard-detection residual (plan-bug Step 0.4 fixed-annotation
gate) is tracked as docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs.
