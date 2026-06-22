# Derive cycle-commit budget from a single source of truth — Implementation Phases

**Status:** Fixed
**MCP runtime:** not-required — claude-config is a docs/scripts harness repo with no Tauri app, no MCP HTTP server, and no audio/UI surface; this fix touches lazy_core.py / its docs only. Validation is the hermetic Python --test smoke harness. (Per docs/features/mcp-testing/SPEC.md untestable classes: build tooling / non-app script with no runtime app integration.)
**Spec:** docs/bugs/_archive/adhoc-derive-cycle-commit-budget/SPEC.md
**Bug:** adhoc-derive-cycle-commit-budget

> Replace the reactive hand-maintained `_CYCLE_COMMIT_BUDGET` literal allow-list in
> `lazy_core.py` (silent budget-1 default → recurring `unexpected-commits` false-positive
> on any unenumerated multi-commit sub_skill) with a budget DERIVED from a single
> dispatch-skill registry, so a newly-added multi-commit sub_skill cannot silently
> default to 1. Fix targets ONLY branch (3) of `detect_cycle_bracket_friction`'s budget
> read (`lazy_core.py:9191`); the `kind=="meta"` exemption (Round 19) and the Round-20
> `budget_override` phase-scaling path stay intact.

## Implementation Notes

- **Single landing site.** `_CYCLE_COMMIT_BUDGET` and `detect_cycle_bracket_friction`
  live in the SHARED `lazy_core.py`, consumed by both `lazy-state.py` and `bug-state.py`.
  The fix lands ONCE in `lazy_core` and serves both pipelines. No coupled-pair mirror;
  `lazy_parity_audit.py` must stay green.
- **D7 scope-class decisions (both Open Questions resolved in-cycle — internal data-shape
  only, identical product behavior):**
  - ⚖ policy: budget-shape granularity → `lazy_core`-owned registry, membership ⇒ multi-commit ceiling
  - ⚖ policy: feature-side literal consolidation → single `lazy_core` SSOT both scripts derive from
  Both Open Questions diverge only in internal data shape (no user-visible / route behavior
  difference — the product behavior "no silent budget-1 for a registered multi-commit skill"
  is identical), so they are resolved here under D7 toward the MOST COMPLETE path: a
  `lazy_core`-owned registry that is the single source of truth for the multi-commit skill
  set, eliminating BOTH the reactive literal table AND the `lazy-state.py` / `bug-state.py`
  naming asymmetry the SPEC flags.
- **Class boundary (from SPEC Proven Findings → Fix scope):**
  - **IN:** branch (3) of the budget read at `lazy_core.py:9191-9192` — the literal-table
    lookup for a dispatched sub_skill that legitimately commits more than once.
  - **OUT:** the `budget_override` path (`lazy_core.py:9183-9189`, Round 20 phase-scaled
    execute-plan) and the `kind=="meta"` exemption (`lazy_core.py:9180-9181`, Round 19).
    Both stay byte-identical.
  - **No new behavior** beyond making the budget self-derived. A genuine runaway (commits
    beyond the derived multi-commit ceiling) must STILL trip `unexpected-commits`.
- **Uniform ceiling preserved.** Every current row uses the uniform ceiling `3`
  (`_CYCLE_COMMIT_BUDGET_DEFAULT = 1`). The derived budget keeps the same numbers:
  registry membership ⇒ multi-commit ceiling (3); absent ⇒ default (1). No threshold
  change — only the SOURCE of the per-skill number changes from a literal row to registry
  membership.
- **Registry SSOT shape.** Introduce a `lazy_core`-owned frozenset/dict of the dispatched
  multi-commit skill identities (the same string names already used at the `bug-state.py`
  `SKILL_*` constants :159-166 and the `lazy-state.py` bare-literal dispatch sites). The
  derived budget reads: name ∈ registry → `_CYCLE_COMMIT_MULTI` (3); else
  `_CYCLE_COMMIT_BUDGET_DEFAULT` (1). The pseudo-skills `__mark_complete__` / `__mark_fixed__`
  are multi-commit and MUST be members (they are dispatch identities the friction detector
  keys on, even though they are not Agent-dispatched skills).
- **Regression-test the class, not just the rows.** Add a `test_lazy_core.py` regression
  asserting that a registry-known multi-commit skill is budgeted as multi-commit WITHOUT a
  literal row, AND that adding a NEW name to the registry (or a fixture simulating it)
  budgets it as multi-commit automatically. Keep every existing
  `test_detect_friction_*_within_budget` and `test_execute_plan_commit_budget_*` green.
- **Gate set (HARD — run all four, all must stay green):**
  `python3 user/scripts/lazy-state.py --test`, `python3 user/scripts/bug-state.py --test`,
  `python3 user/scripts/test_lazy_core.py`, and `python3 user/scripts/lazy_parity_audit.py`.

## Phase 1: Derive the cycle-commit budget from a single registry SSOT

Replace the reactive literal `_CYCLE_COMMIT_BUDGET` table's role as the source of per-skill
budgets with a derivation from a `lazy_core`-owned dispatch-skill registry, so an
unenumerated multi-commit sub_skill can no longer silently default to budget 1.

**Status:** Complete

- [x] Introduce a `lazy_core`-owned SSOT for the multi-commit dispatch-skill set — a module
      constant (e.g. `_MULTI_COMMIT_DISPATCH_SKILLS: frozenset[str]`) naming every dispatch
      identity whose cycle legitimately commits more than once: the real skills
      (`execute-plan`, `retro-feature`, `mcp-test`, `write-plan`, `plan-feature`, `plan-bug`)
      AND the forward-advancing terminal pseudo-skills (`__mark_complete__`, `__mark_fixed__`).
      Carry a single block comment documenting that this is the SSOT the budget derives from
      (replacing the five per-row reactive provenance comments) and that ADDING a new
      multi-commit dispatch skill means adding it HERE, co-located with the dispatch-skill
      identity — never a separate budget row.
- [x] Replace `detect_cycle_bracket_friction` branch (3) (`lazy_core.py:9191-9192`) so the
      budget is DERIVED: `budget = _CYCLE_COMMIT_MULTI if (sub_skill or "") in <registry>
      else _CYCLE_COMMIT_BUDGET_DEFAULT`. Keep `_CYCLE_COMMIT_BUDGET_DEFAULT = 1` and the
      uniform multi-commit ceiling (3). Leave branches (1) `kind=="meta"` exemption and (2)
      `budget_override` positive-int supersede UNTOUCHED and ordered as-is.
- [x] Remove the hand-maintained `_CYCLE_COMMIT_BUDGET` literal dict (and its five reactive
      provenance comment blocks) now that membership derives the budget — OR retain a derived
      mapping built FROM the registry if any other reader references `_CYCLE_COMMIT_BUDGET` by
      name (grep `find_symbol_usages` / `Grep` for `_CYCLE_COMMIT_BUDGET` first; if a sole
      consumer is branch 3, delete the literal; if other consumers exist, rebuild the dict
      from the registry so the literal table is no longer hand-appended).
- [x] Confirm the derivation serves BOTH pipelines unchanged: `bug-state.py` routes its own
      `mcp-test` / `__mark_fixed__` / `plan-bug` cycles through this shared
      `detect_cycle_bracket_friction`; no `bug-state.py` or `lazy-state.py` edit is required
      (the names are already what the dispatch sites pass). Note in the code comment that the
      `lazy-state.py` bare-literal dispatch sites and the `bug-state.py` `SKILL_*` constants
      pass the SAME strings the registry enumerates.

## Phase 2: Regression-prove the class is closed and all gates green

Add a regression that proves a registry-known multi-commit skill is budgeted without a
literal row (closing the missing-row defect CLASS, not just re-pinning the current rows), and
verify the full gate set stays green.

**Status:** Complete

- [x] Add `test_detect_friction_registry_known_skill_budgeted_without_literal_row` to
      `test_lazy_core.py`: assert a multi-commit dispatch skill in the registry is budgeted as
      multi-commit (e.g. 2-3 commits → no friction) via the DERIVATION, with no literal table
      row backing it; and that a skill ABSENT from the registry still defaults to 1 (a
      2-commit unregistered skill → `unexpected-commits`, preserving genuine-runaway
      detection). Register the new test in the module's test-runner list (alongside the
      existing `test_detect_friction_*` entries near line 20625).
- [x] Confirm every existing friction/budget test stays green unchanged:
      `test_detect_friction_mcp_test_cycle_multi_commit_within_budget`,
      `test_detect_friction_mark_complete_meta_cycle_multi_commit_within_budget`,
      `test_detect_friction_planning_cycle_multi_commit_within_budget`,
      `test_detect_friction_over_budget_commits`,
      `test_execute_plan_commit_budget_scales_with_phase_count` /
      `..._with_wu_count` (the Round-20 `budget_override` path is OUT of scope and must be
      byte-unaffected).
- [x] Run the full gate set and confirm all green:
      `python3 user/scripts/lazy-state.py --test`,
      `python3 user/scripts/bug-state.py --test`,
      `python3 user/scripts/test_lazy_core.py`,
      `python3 user/scripts/lazy_parity_audit.py`. The two `--test` baselines
      (`tests/baselines/*-test-baseline.txt`) must be unaffected (no state-machine route
      change); if either drifts, the change leaked beyond branch 3 — investigate, do not
      regenerate the baseline by hand.

## Implementation Notes — Phases 1 & 2 (2026-06-22, inline bug-pipeline execution)

**Work completed (test-first, all inline — zero Agent() calls):**
- **WU-1:** Added `lazy_core._MULTI_COMMIT_DISPATCH_SKILLS: frozenset[str]` (the SSOT
  naming the 8 multi-commit dispatch identities: `execute-plan`, `retro-feature`,
  `mcp-test`, `write-plan`, `plan-feature`, `plan-bug`, `__mark_complete__`,
  `__mark_fixed__`) plus the named ceiling `_CYCLE_COMMIT_MULTI = 3`. One block comment
  consolidates the five reactive per-row provenance comments and documents the
  add-here-not-a-budget-row contract + the both-pipelines SSOT relationship.
- **WU-2:** `detect_cycle_bracket_friction` branch (3) now DERIVES the budget:
  `_CYCLE_COMMIT_MULTI if (sub_skill or "") in _MULTI_COMMIT_DISPATCH_SKILLS else
  _CYCLE_COMMIT_BUDGET_DEFAULT`. Branch (1) `kind=="meta"` and branch (2) `budget_override`
  left byte-identical and in order. The hand-maintained `_CYCLE_COMMIT_BUDGET` literal dict
  was REMOVED — grep confirmed branch (3) was its SOLE consumer
  (`grep -rn "_CYCLE_COMMIT_BUDGET\b" user/scripts/` → only `lazy_core.py`), so the safe
  delete path applied (no rebuild-from-registry needed).
- **WU-3:** Added `test_multi_commit_dispatch_skills_registry_membership` (locks the
  registry contents + the two named constants) and
  `test_detect_friction_registry_known_skill_budgeted_without_literal_row` (class-closure:
  loops the registry asserting membership ⇒ multi-commit budget with no literal row; an
  unregistered skill still defaults to 1 and trips at 2 commits). Both registered in the
  module test-runner list. All existing `test_detect_friction_*` / `test_execute_plan_commit_budget_*`
  tests pass unchanged.

**Integration / both-pipelines confirmation:** the change lands ONCE in the shared
`lazy_core.py`; `lazy-state.py --test` and `bug-state.py --test` both pass against the
committed baselines (no state-machine route change, baselines unaffected), and
`lazy_parity_audit.py` is green (no unintended divergence). No `bug-state.py` / `lazy-state.py`
edit was required — the dispatch sites already pass the same string identities the registry
enumerates.

**Pitfalls:** none. The OUT-of-scope branches (`budget_override`, `kind=="meta"`) were
verified byte-identical. `frozenset[str]` subscript syntax is fine on the project's Python.

**Files modified:** `user/scripts/lazy_core.py` (registry SSOT + branch-3 derivation, literal
dict removed), `user/scripts/test_lazy_core.py` (2 new tests + runner registrations),
`user/scripts/CLAUDE.md` (budget-source note).

**Gate set (all green):** `lazy-state.py --test`, `bug-state.py --test`,
`test_lazy_core.py` (769/769), `lazy_parity_audit.py --repo-root . ` (exit 0).
