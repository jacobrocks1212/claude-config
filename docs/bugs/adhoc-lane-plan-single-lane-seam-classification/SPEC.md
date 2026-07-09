# Lane-plan template cannot express Sequenced single-lane (no typegen seam) — Investigation Spec

> The cognito-lanes plan template forced a per-phase Seam classification of `Parallel` or
> `Sequenced` (plus a batch-table `Parallel?` column), but a backend-only single-lane phase
> (e.g. track-submissions fabric-reporting Phase 1, re-planned in the 2026-07-09 v3 sandbox run)
> is `Sequenced` by the Cognito.Core/Model seam rule while having NO frontend lane — so the L.2
> typegen seam never runs mid-phase and the classification misleads the executor into looking
> for a seam step or a phantom frontend lane.

**Status:** Fixed
**Severity:** P3
**Discovered:** 2026-07-09 (the sandbox planner improvised a plan-specific note stating the seam is not run)
**Placement:** docs/bugs/adhoc-lane-plan-single-lane-seam-classification
**Related:** `repos/cognito-forms/.claude/skills/write-plan-cognito/{SKILL.md,execution-contract-cognito-lanes.md}`; `docs/bugs/adhoc-write-plan-cognito-planner-contract-read` (same run)

---

## Root cause

The Step 2.5 seam-classification enum was two-valued (`Parallel` | `Sequenced`) with the seam
rule keyed purely on generated-contract *touch*, not on lane *count* — a one-lane phase touching
`Cognito.Core/Model/` had no honest value to pick.

## Fix (shipped) — all in write-plan-cognito, additive/back-compat

- **SKILL.md Step 2.5:** new third classification value **`Single-lane (no seam)`** — one-lane
  phase (backend-only or frontend-only); L.2 never runs mid-phase; any `server-types/**` diff is
  reconciled at the part-end Tier 2 full `/msbuild`; batches `Solo` by construction; includes the
  back-compat note (older v3 plans express this as `Sequenced` + a plan-specific note — treated
  identically, no contract-version bump). The "when unsure, classify Sequenced" tiebreak is now
  explicitly scoped to two-lane phases.
- **SKILL.md Step 3 templates:** Execution Schedule `Seam` column, per-phase
  `**Seam classification:**` line, and the batch-structure table now carry the third value
  (single-lane phases: exactly one `Solo` batch — no seam row, no batch 2).
- **execution-contract-cognito-lanes.md Step L.2:** matching executor-side note — a
  `Single-lane (no seam)` phase skips L.2 entirely (no frontend lane to dispatch, no mid-phase
  typegen); part-end reconciliation covers any server-types diff; older `Sequenced`+note plans
  treated identically. Contract version stays cognito-lanes-v3 (additive).

## Verification

- `python user/scripts/project-skills.py` + `lint-skills.py` — clean.
- Existing v3 plans remain valid: no template field removed or renamed; executors of pre-change
  plans hit only the unchanged `Sequenced` path (the L.2 note explicitly grandfathers the
  Sequenced-with-note expression of a single-lane phase).
