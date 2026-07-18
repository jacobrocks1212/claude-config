# Bug: blocked-resolution add-phase strands the originating In-progress plan → router re-loop

**Status:** Fixed
**Discovered:** 2026-07-17 — observed mid-run on a live `/lazy-batch` run (item in flight: `hydra-overlay`, plan part 8)
**Fixed:** 2026-07-18
**Fix commit:** 33cafa01
**Root-cause class:** missing-contract
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `_components/blocked-resolution.md`; `_components/completeness-policy.md`; hardening-log Round 32 (2026-07)

## Symptom (verified)

The Step 1h blocked-resolution "Add a phase to resolve the blocker" path authored a new
corrective phase and struck the superseded deliverables in `PHASES.md`, then neutralized
`BLOCKED.md`. But it did NOT reconcile the ORIGINATING In-progress plan (`plans/…-part-8.md`)
whose `## Work Units` checkboxes for those superseded deliverables stayed plain unchecked
`- [ ] WU-N`. The very next probe re-routed `/execute-plan` back to the superseded plan
part, which would re-attempt the architecturally-impossible WUs and re-block — an infinite
route-loop. Cleared only by a manual recovery cycle that struck the plan-body WU checkboxes
and flipped the plan status to Complete.

## Reconstructed route

1. Worker (apply-resolution subagent) enacts "Add a phase" via `/add-phase`:
   authors a corrective phase in `PHASES.md`, strikes the now-superseded deliverables in
   `PHASES.md`, neutralizes `BLOCKED.md`. Contract: `dispatch-apply-resolution.md`
   `@section blocked-steps` (the "Add a phase to resolve the blocker" branch); mirrored in
   the reference block of `_components/blocked-resolution.md`.
2. Next probe → `lazy-state.py` Step 7a. `find_implementation_plans`
   (`lazy_core.docmodel`) returns every plan whose frontmatter `status` != `Complete`.
   The originating part-8 plan is still `In-progress` with unchecked `- [ ] WU-N` rows for
   the superseded deliverables (`_plan_wu_checkbox_counts` in `lazy_core.gates` counts them
   as unchecked → real remaining work).
3. Step 7a prioritizes finishing that In-progress plan → re-dispatches `/execute-plan`
   against the superseded part → re-attempts architecturally-impossible WUs → re-blocks.
   Loop.

The divergence: the "Add a phase" contract reconciles `PHASES.md` (the human deliverable
view) but has NO step reconciling the ORIGINATING plan (the MACHINE routing source of
truth per the `_PLAN_WU_CHECKBOX_RE` / `find_implementation_plans` mechanics).

## Root cause

missing-contract: `dispatch-apply-resolution.md`'s blocked "Add a phase" path (and the
`blocked-resolution.md` reference mirror) was never given a contract step to reconcile an
originating In-progress plan whose WUs the new corrective phase supersedes. The router
treats an In-progress plan with unchecked WUs as unfinished work and re-routes to it.

## Fix scope (contract/prose only — no script change)

`user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md` +
`user/skills/_components/blocked-resolution.md` (its reference mirror), "Add a phase to
resolve the blocker" branch: add a mandatory RECONCILE-ORIGINATING-PLAN step —

- IF the new corrective phase supersedes deliverables that belong to an originating
  In-progress plan (`plans/*.md`, `status: In-progress`, unchecked `- [ ] WU-N` rows for
  those deliverables): in that plan's `## Work Units` checklist, strike each superseded WU
  row with the canonical descoped marker —
  `- [ ] ~~WU-N — <title>~~ **SUPERSEDED** <!-- descoped -->` (SSOT
  `lazy_core:_DESCOPED_MARKER`). The strikethrough breaks the `_PLAN_WU_CHECKBOX_RE`
  anchor so the row is no longer counted as unchecked (verified:
  `_plan_wu_checkbox_counts` returns `unchecked=0` for the struck form).
- THEN, if the ONLY non-struck WU rows remaining are already `[x]` landed (every remaining
  WU is landed or superseded), flip the plan's frontmatter `status:` to `Complete` so
  `find_implementation_plans` filters it out and the router advances to the new corrective
  phase.

Verification that contract-only is sufficient (no script change): `find_implementation_plans`
already skips `status: Complete` plans; `_plan_wu_checkbox_counts` already drops
strikethrough-broken rows from the unchecked count. The loop existed purely because the
authoring contract never instructed the worker to perform this reconciliation.

## Near-neighbor note

The `ratify-redirect` path (`@section ratify-redirect-steps`) also authors a corrective
phase, but it re-aligns surfaces to a redirected choice rather than striking originating
deliverables, so it does not strand plan WUs the same way. Fix is scoped to the blocked
"Add a phase" path where the loop is proven; the reconcile step is worded conditionally
("IF the new phase supersedes originating-plan WUs") so it self-applies to any future
supersession path without over-reaching.
