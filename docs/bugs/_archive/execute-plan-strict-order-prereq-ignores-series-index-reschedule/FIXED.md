---
kind: fixed
feature_id: execute-plan-strict-order-prereq-ignores-series-index-reschedule
date: 2026-07-19
provenance: backfilled-unverified
validated_via: pytest tests/test_lazy_core/ 1312/1312; test_hooks.py 284/284; lazy-state.py --test + bug-state.py --test; harness-gate.py in_scope:false; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

`execute-plan-strict-order-prereq-ignores-series-index-reschedule` marked Fixed on 2026-07-19 during
hardening Round 110 (observed-friction harden dispatch, item in flight `hydra-overlay`,
operator-authorized). Receipt written by the /lazy-batch orchestrator during the Round-110 reconcile
handback — OUT-OF-PIPELINE (a `harden(...)` commit, not the bug pipeline's `__mark_fixed__` gate) —
provenance is deliberately `backfilled-unverified`.

## Notes

Fixed in commit `9ce3b8f1`: the /execute-plan strict-order `Plan series` prerequisite audit (rule
1a.6a) now orders sibling parts by plan-frontmatter `series_index` — a part P is a prerequisite of
the dispatched part D iff series_index(P) < series_index(D), with raw-part-number fallback when
series_index is absent. Mirrored in cycle-base-prompt.md (workstation+cloud) + a producer note in
write-plan/SKILL.md. Regression test `test_rescheduled_high_series_index_part_not_prerequisite_of_lower`
encodes the hydra-overlay scenario (part-10 series_index:15 is not a prerequisite of part-12).
