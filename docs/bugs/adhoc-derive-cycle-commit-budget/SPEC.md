# Derive cycle-commit budget from a single source of truth — Investigation Spec

> The hand-maintained `_CYCLE_COMMIT_BUDGET` allow-list in `lazy_core.py` silently defaults any unenumerated multi-commit sub_skill to budget 1, false-positiving `unexpected-commits` at `--cycle-end`. The missing-row defect class has recurred five times; replace the reactive literal table with a budget derived from the orchestrator dispatch-skill registry so a newly-added multi-commit sub_skill cannot silently default to 1.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-22
**Placement:** docs/bugs/adhoc-derive-cycle-commit-budget
**Related:** `docs/bugs/per-feature-cycle-cap-defers-incomplete-work/` (sibling friction-detector spin-off); harden-harness Round 31 (2026-06-22, commit 8039dbc, origin of this item); `user/scripts/lazy_core.py` `detect_cycle_bracket_friction` / `_CYCLE_COMMIT_BUDGET`

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- Batch-mode investigation: symptoms confirmed from the recurrence record in the
     ADHOC_BRIEF, the source code, and the five in-source provenance comments — not via
     interactive AskUserQuestion (no human in batch). All marked PROVEN from on-disk evidence. -->

1. **[PROVEN]** A dispatched sub_skill whose cycle legitimately commits more than once, but which is ABSENT from `_CYCLE_COMMIT_BUDGET`, defaults to `_CYCLE_COMMIT_BUDGET_DEFAULT = 1` and is reported as `unexpected-commits` process-friction at `--cycle-end` — confirmed by `lazy_core.py:9191-9194` (`_CYCLE_COMMIT_BUDGET.get(sub_skill or "", _CYCLE_COMMIT_BUDGET_DEFAULT)` then `if commits_since > budget`).
2. **[PROVEN]** This is a RECURRING missing-row defect class with five rounds of reactive literal-row appends, each landed AFTER a production false-positive — Round 15 (`execute-plan`), Rounds 16/17 (`__mark_complete__` / `__mark_fixed__`), a later round (`mcp-test`), and 2026-06-22 d2-sample-import-ui (`write-plan` / `plan-feature` / `plan-bug`) — confirmed by the five dated provenance comments at `lazy_core.py:8940-9005`.
3. **[PROVEN]** The reactive pattern is over-fit: each comment cites a concrete `begin_head_sha=…, sub_skill='…', budget=1` recurrence as its justification (e.g. `lazy_core.py:8988` `08d33d580cfe / write-plan / budget=1`, `lazy_core.py:8957` `a28085bb938e / mcp-test`), i.e. the row was added in response to the false-positive, not ahead of it.

## Reproduction Steps

1. Add a new dispatched sub_skill to `lazy-state.py` / `bug-state.py` (a `sub_skill="<new>"` dispatch site) whose cycle legitimately makes 2+ commits.
2. Forget to add a matching literal row to `_CYCLE_COMMIT_BUDGET` in `lazy_core.py`.
3. Run a `/lazy-batch` (or `/lazy-bug-batch`) cycle that dispatches the new sub_skill; let the cycle make its 2+ legitimate commits.
4. At `--cycle-end`, `cycle_end_friction_check` → `detect_cycle_bracket_friction` reads `budget = 1` for the unenumerated skill.

**Expected:** the friction detector knows the new sub_skill's commit shape from the same registry the dispatch sites already draw the name from — no separate hand-maintained budget row required.
**Actual:** `commits_since (2+) > budget (1)` → an `unexpected-commits` `process-friction` ledger entry, which `pending_hardening()` then counts as harness debt and the `--emit-prompt` probe withholds the forward route on — a self-announced false runaway.
**Consistency:** Deterministic — fires every time on any unenumerated multi-commit sub_skill (confirmed five times across distinct skills).

## Evidence Collected

### Source Code

- `lazy_core.py:8939-9005` — `_CYCLE_COMMIT_BUDGET_DEFAULT = 1` and the hand-maintained `_CYCLE_COMMIT_BUDGET: dict[str, int]`. Current rows: `execute-plan:3`, `retro-feature:3`, `mcp-test:3`, `__mark_complete__:3`, `__mark_fixed__:3`, `write-plan:3`, `plan-feature:3`, `plan-bug:3`. Each carries a multi-line provenance comment naming the recurrence that forced its addition.
- `lazy_core.py:9180-9206` — `detect_cycle_bracket_friction` budget read. Order: (1) `marker.get("kind") == "meta"` → exempt (return None, Round 19 — IN-SCOPE-OUT, leave intact); (2) `budget_override` positive int supersedes (Round 20 phase-scaled execute-plan path — IN-SCOPE-OUT, leave intact); (3) else `_CYCLE_COMMIT_BUDGET.get(sub_skill or "", DEFAULT)`. **The fix targets branch (3) only.**
- `lazy_core.py:9014-…` — `_execute_plan_commit_budget` computes the Round-20 `budget_override` from plan frontmatter; orthogonal to the table and OUT of scope.
- **`bug-state.py:159-166` — the existing dispatch-skill registry.** A `SKILL_*` constant block already names every dispatched skill: `SKILL_INVESTIGATE="spec-bug"`, `SKILL_PLAN_BUG="plan-bug"`, `SKILL_SPEC_PHASES="spec-phases"`, `SKILL_WRITE_PLAN="write-plan"`, `SKILL_EXECUTE_PLAN="execute-plan"`, `SKILL_RETRO="retro-feature"`, `SKILL_MCP_TEST="mcp-test"`, `SKILL_MARK_FIXED="__mark_fixed__"`. Every `bug-state.py` dispatch site already uses `sub_skill=SKILL_*` (lines 1183/1189/1217/1226/1255/1358/1389/1416). **This is the "single source of truth" the brief points at.**
- `lazy-state.py` dispatch sites (lines 2813/2871/2986/3052/3159/3193) — use BARE string literals (`sub_skill="plan-feature"`, `"write-plan"`, `"execute-plan"`, `"mcp-test"`), NOT a `SKILL_*` constant block. This asymmetry is incidental: the *names* are the same strings the budget table is keyed by, so the registry — wherever it is consolidated — is the natural SSOT for budgets.

### Git History

- Origin: harden-harness Round 31 (2026-06-22), commit `8039dbc` ("harden(script): add write-plan/plan-feature/plan-bug commit-budget rows") — the most recent reactive append; commit `1ec139c` front-enqueued THIS bug as the structural follow-up; commit `7bfd593` recorded the round.

### Related Documentation

- `user/scripts/CLAUDE.md` "Process-friction detector" + "Cycle-counter advance" sections — document the friction-detector machinery and the `pending_hardening()` self-announce loop the false-positive feeds.
- A `process-friction` ledger entry behaves identically to a guard validate-deny: it raises `pending_hardening()`, withholds the forward route, and refuses `--run-end` — so a false-positive is not benign, it stalls the run until reconciled.

## Theories

### Theory 1: Reactive literal allow-list with a silent budget-1 default is the whole defect
- **Hypothesis:** Because the table is keyed by sub_skill name with a fall-through default of 1, ANY new multi-commit sub_skill not manually enumerated mis-classifies as a runaway. The only fix that closes the *class* is to derive the budget from the same registry the dispatch sites already use, removing the manual-append step entirely.
- **Supporting evidence:** Five dated recurrences, each a manual append after a production false-positive (Symptoms 2-3). The names in the table are exactly the dispatched sub_skill names. `bug-state.py` already maintains a `SKILL_*` registry of those names.
- **Contradicting evidence:** None. The `kind==meta` exemption (Round 19) and `budget_override` (Round 20) handle the genuinely-variable-commit cases and are explicitly OUT of scope; only the literal-table branch remains reactive.
- **Status:** Confirmed.

## Proven Findings

- **Root cause:** `_CYCLE_COMMIT_BUDGET` is a hand-maintained dict with a budget-1 default; it is NOT derived from any registry, so each newly-dispatched multi-commit sub_skill silently mis-budgets until a human appends a literal row after observing the false-positive.
- **The SSOT exists already:** `bug-state.py:159-166` `SKILL_*` constants ARE the dispatch-skill registry. `lazy-state.py` uses the same names as bare literals. A derived budget should map each dispatch-skill identity to its commit shape (single-commit default vs. multi-commit), so registry-membership — not manual table maintenance — determines the budget.
- **Fix scope (class boundary):**
  - **IN:** branch (3) of the budget read at `lazy_core.py:9191-9192` — the literal-table lookup for a dispatched sub_skill that legitimately commits more than once. Replace the reactive literal table with a budget derived from per-skill metadata / the dispatch-skill registry so a new multi-commit sub_skill cannot default to 1.
  - **OUT:** the `budget_override` path (`lazy_core.py:9183-9189`, Round 20 phase-scaled execute-plan) and the `kind=="meta"` exemption (`lazy_core.py:9180-9181`, Round 19) — both stay intact.
  - **No new behavior** beyond making the budget table self-populating/derived. Genuine runaways (commits beyond the derived multi-commit ceiling) must still trip.
- **Coupling:** `_CYCLE_COMMIT_BUDGET` and `detect_cycle_bracket_friction` live in the SHARED `lazy_core.py`, consumed by both `lazy-state.py` and `bug-state.py`. The fix lands once in `lazy_core` and serves both pipelines (no coupled-pair mirror; `lazy_parity_audit.py` stays green). Keep `lazy-state.py --test`, `bug-state.py --test`, and `test_lazy_core.py` green.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Commit-budget table | `user/scripts/lazy_core.py` (`_CYCLE_COMMIT_BUDGET`, `_CYCLE_COMMIT_BUDGET_DEFAULT`, `detect_cycle_bracket_friction` branch 3 at :9191) | Replace literal allow-list with a registry/metadata-derived budget |
| Dispatch-skill registry (SSOT source) | `user/scripts/bug-state.py` (`SKILL_*` block :159-166); `user/scripts/lazy-state.py` (bare-literal dispatch sites) | The naming surface the derived budget keys off; possible consolidation of feature-side literals into the same registry shape |
| Friction-detector tests | `user/scripts/test_lazy_core.py` (`test_detect_friction_*_within_budget`, `test_execute_plan_commit_budget_*`) | Must stay green; add a regression asserting a registry-known multi-commit skill is budgeted without a literal row |

## Open Questions

- **Budget-shape granularity (planning-time):** the current table uses a uniform ceiling of `3` for every multi-commit skill. Should the derived budget keep a single uniform multi-commit ceiling (registry membership ⇒ multi-commit ⇒ 3; absent ⇒ 1), or carry a per-skill `commits: single|multi` metadata flag on the registry entry? Both close the missing-row class identically (the product behavior — no silent budget-1 — is the same); the choice is internal data-shape only (scope-class, resolvable in `/plan-bug` under D7). Recommended: a per-skill metadata flag on the registry so the budget is co-located with the dispatch-skill definition.
- **Feature-side literal consolidation (planning-time):** whether `lazy-state.py`'s bare-literal dispatch sites should adopt the `bug-state.py` `SKILL_*` constant shape as part of this fix, or whether the derived budget reads a `lazy_core`-owned registry both scripts import. Internal-only; resolvable at planning.
