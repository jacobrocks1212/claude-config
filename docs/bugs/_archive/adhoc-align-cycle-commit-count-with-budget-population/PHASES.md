# Implementation Phases — Align the unexpected-commits count numerator with the budget denominator's commit population

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; verified via
`test_lazy_core.py` (pytest) alone.

---

### Phase 1: Shared `_CYCLE_COMMIT_NOISE_ALLOWANCE` cushion on the registry-derived budget branch

**Status:** Complete

**Scope:** Add ONE small, uniform cushion constant (`_CYCLE_COMMIT_NOISE_ALLOWANCE = 1`) applied
INSIDE `detect_cycle_bracket_friction`'s branch-(3) registry-derived budget computation ONLY
(Option A from the SPEC's design fork) — on top of `_CYCLE_COMMIT_MULTI` /
`_MULTI_COMMIT_CEILING_OVERRIDE` / `_CYCLE_COMMIT_BUDGET_DEFAULT` alike (both the multi-commit and
single-commit-default cases). `execute-plan`'s own `budget_override` path
(`_execute_plan_commit_budget`, its work-scaled + bookend-cushioned model) is explicitly left
UNTOUCHED — the SPEC's own boundary (out of scope: `_MULTI_COMMIT_DISPATCH_SKILLS` membership,
any skill's MAGNITUDE override, the `--no-merges` numerator exclusion, the meta-cycle exemption,
the branch-divergence signal).

**TDD:** yes — regressions for a member skill (budget 4, 5 non-merge commits incl. 1 incidental →
clean; 6+ → still trips) and a single-commit-default skill (budget 1 → 1 + allowance).

**Deliverables:**
- [x] `_CYCLE_COMMIT_NOISE_ALLOWANCE = 1` constant added to `lazy_core.py`, co-located near `_CYCLE_COMMIT_MULTI`/`_CYCLE_COMMIT_BUDGET_DEFAULT`, with a comment documenting provenance (this SPEC) mirroring the `_EXECUTE_PLAN_PHASE_BUDGET_SLACK`/`_EXECUTE_PLAN_BOOKEND_COMMITS` comment style.
- [x] `detect_cycle_bracket_friction` branch (3) applies `budget = base_budget + _CYCLE_COMMIT_NOISE_ALLOWANCE` where `base_budget` is the (now frontmatter-derived, per the sibling bug) multi-commit-or-default value.
- [x] `execute-plan`'s `budget_override` branch (the `isinstance(budget_override, int) and budget_override > 0` check, computed by `_execute_plan_commit_budget`) is BYTE-IDENTICAL — untouched by this change (it short-circuits before branch 3 is reached).
- [x] Existing regression tests re-audited for the new term: boundary assertions that previously asserted "over budget at ceiling+1" for a registry-derived (non-execute-plan) skill were bumped by the allowance (`test_detect_friction_mcp_test_cycle_multi_commit_within_budget`'s `spec`-at-boundary control moved from 4→5 commits; `test_detect_friction_registry_known_skill_budgeted_without_literal_row`'s unregistered-skill control moved from 2→3 commits) so each still demonstrates a genuine runaway trips.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k "detect_friction or multi_commit" -q` is green; the full suite is green.

**Runtime Verification:**
- [x] <!-- verification-only --> A registry-derived multi-commit skill (`mcp-test`, ceiling 4) tolerates ONE incidental commit beyond its documented worst case (5 total) without a false `unexpected-commits`; 6+ still trips. **Verified:** `test_detect_friction_mcp_test_cycle_multi_commit_within_budget` — GREEN.
- [x] <!-- verification-only --> A single-commit-default (unregistered) skill tolerates the +1 allowance (2 commits clean) but 3+ still trips — genuine-runaway detection intact. **Verified:** `test_detect_friction_registry_known_skill_budgeted_without_literal_row` part (2) — GREEN.
- [x] <!-- verification-only --> `execute-plan`'s own work-scaled + bookend-cushioned `budget_override` model is unaffected — no double-cushioning. **Verified:** `test_execute_plan_commit_budget*` fixtures unchanged and green (no edits made to `_execute_plan_commit_budget` or its tests).

**MCP Integration Test Assertions:** N/A — no app runtime surface; pytest is the verification tier.

**Prerequisites:** `adhoc-derive-multi-commit-budget-from-dispatch-sites` (same code region — landed first per operator sequencing instruction; this phase's edit sits directly on top of that bug's `skill_declares_multi_commit`-derived `base_budget`).

**Files likely modified:** `user/scripts/lazy_core.py` (new constant + branch-3 arithmetic), `user/scripts/test_lazy_core.py` (boundary-assertion bumps, shared with the sibling bug's test rewrites since both land in the same test functions).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug. Not a checkbox — done out-of-pipeline
this round per `docs/bugs/CLAUDE.md` ("Fixing a bug OUT-OF-PIPELINE").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

Implemented + closed out 2026-07-12 in the same STATE-lane pass as the sibling
`adhoc-derive-multi-commit-budget-from-dispatch-sites` (landed on top of it, same code region, per
operator sequencing instruction). Full suite: `python -m pytest user/scripts/test_lazy_core.py -q`
→ 1064 passed; `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py
--test` both green; `python user/scripts/lazy_parity_audit.py --repo-root .` exit 0; `python
user/scripts/doc-drift-lint.py --repo-root .` exit 0.
