---
kind: fixed
feature_id: adhoc-align-cycle-commit-count-with-budget-population
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: pytest (test_lazy_core.py) + both state scripts' --test smoke harnesses; NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

adhoc-align-cycle-commit-count-with-budget-population marked Fixed on 2026-07-12 during an
operator-directed multi-item STATE-lane close-out pass. This receipt was written by the
orchestrating subagent, not the pipeline's `__mark_fixed__` gate — provenance is deliberately
`operator-directed-interactive`.

## Notes

Implemented per the SPEC's own recommended fix, Option A: a single shared
`_CYCLE_COMMIT_NOISE_ALLOWANCE = 1` cushion added inside `detect_cycle_bracket_friction`'s
registry-derived budget branch ONLY — on top of both the multi-commit ceiling
(`_CYCLE_COMMIT_MULTI` / `_MULTI_COMMIT_CEILING_OVERRIDE`) and the single-commit default
(`_CYCLE_COMMIT_BUDGET_DEFAULT`) alike. `execute-plan`'s own work-scaled + bookend-cushioned
`budget_override` model (`_execute_plan_commit_budget`) is untouched, exactly per the SPEC's
explicit scope boundary. Landed on top of the sibling bug
`adhoc-derive-multi-commit-budget-from-dispatch-sites` (same code region, same session, sequenced
sibling-second per operator instruction) — the noise allowance applies to the frontmatter-derived
`base_budget` that sibling bug introduced.

Verification: `python -m pytest user/scripts/test_lazy_core.py -q` → 1064 passed. `python
user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` — all smoke
tests passed. `python user/scripts/lazy_parity_audit.py --repo-root .` → exit 0. `python
user/scripts/doc-drift-lint.py --repo-root .` → exit 0 (2 pre-existing, unrelated exemptions).
Existing boundary-assertion tests that pinned the OLD (uncushioned) registry-branch ceilings were
bumped by the +1 allowance to keep demonstrating a genuine runaway still trips (see the sibling
bug's PHASES.md Phase 1 for the exact assertions moved).
