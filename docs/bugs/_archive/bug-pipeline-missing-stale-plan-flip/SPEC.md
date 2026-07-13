---
kind: investigation-spec
bug_id: bug-pipeline-missing-stale-plan-flip
---

# Bug pipeline loops execute-plan on a stale (all-WUs-ticked, frontmatter-not-Complete) plan part — Investigation Spec

> The feature pipeline (`lazy-state.py`) has a workstation `__flip_plan_complete_stale__` pseudo-action that flips a Ready/In-progress plan whose every in-scope WU is already `[x]` to Complete inline (one deterministic step) instead of burning an `/execute-plan` Opus cycle whose only job is the frontmatter flip. The bug pipeline (`bug-state.py`) never got the mirror: its Step 7a dispatches `/execute-plan` unconditionally on the head plan. When a bug plan part is stale, the bug pipeline loops `/execute-plan` — each cycle re-verifies already-done work, and if a subagent turn ends before flipping the frontmatter (backgrounded gate, or it treats WUs-committed as done) the loop persists. The `lazy-bug-batch` SKILL already documents handling this pseudo-skill "emitted by `bug-state.py` at Step 7a", so the orchestrator handler exists — only the state-script emit is missing.

**Status:** Fixed
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/bug-pipeline-missing-stale-plan-flip
**Related:** `feat(lazy-hardening)` Phase 3 Batch 2 (`89ac83e3`, added `__flip_plan_complete_stale__` to `lazy-state.py`); `harden(script)` `328d1462` (empty-PHASES-scope vacuous-flip guard, feature side); the coupled-pair `/lazy-batch` ↔ `/lazy-bug-batch` contract; hardening dispatch trigger `process-friction` on item `hardening-intervention-records-unmeasurable-or-missing`

---

## Verified Symptoms

1. **[VERIFIED — code-traced]** `bug-state.py::compute_state` Step 7a (`user/scripts/bug-state.py:1486-1494`) selects `plan = plans[0]` and returns `sub_skill=execute-plan` with NO stale-plan guard. The feature analog (`user/scripts/lazy-state.py:3234-3323`) runs the `finalize_stale` evaluation (`_plan_phase_set` → `_unchecked_wus_in_plan_scope` / `_all_wus_in_plan_scope` / `_phases_text_scoped_to` / `remaining_unchecked_are_verification_only`, with a per-WU-checkbox fallback for empty-PHASES-scope plans) and emits `__flip_plan_complete_stale__` when the plan's referenced work is all done.
2. **[VERIFIED — prose-traced]** `user/skills/lazy-bug-batch/SKILL.md:455-461` documents `__flip_plan_complete_stale__` as "emitted by `bug-state.py` at Step 7a (cloud and workstation)" with a full inline-apply handler (edit the plan `status:` line → Complete, meta cycle). The orchestrator is ready to apply a route the state script never produces — a prose/emit divergence.
3. **[REPORTED — run telemetry]** The hardening dispatch observed `step_repeat=3` looping `/execute-plan` on the bug item `hardening-intervention-records-unmeasurable-or-missing` (which lives in `docs/bugs/`), costing ~3 cycles.

## Reproduction Steps

1. In a bug dir under `docs/bugs/<slug>/`, create `PHASES.md` with two phases where Phase 1 is fully `[x]` and Phase 2 still has an unchecked implementation row (so overall `unchecked > 0` and Step 7a is entered).
2. Add `plans/all-phases-<slug>-part-1.md` scoped `phases: [1]` with `status: In-progress` (never flipped after Phase 1 finished).
3. Run `python3 user/scripts/bug-state.py --repo-root <repo>`.

**Observed (pre-fix):** `sub_skill: execute-plan` — a full Opus cycle whose only work is flipping the plan frontmatter.
**Expected (post-fix):** `sub_skill: __flip_plan_complete_stale__`, `sub_skill_args: <plan path>` — the deterministic inline flip the orchestrator already knows how to apply.

## Root Cause

**Class: missing-emit-section** (coupled-pair mirror gap). The `__flip_plan_complete_stale__` dispatch class exists in the shared orchestrator contract and in `lazy-state.py`, but `bug-state.py`'s Step 7a has no emit path for it. All the deciding helpers are already in `lazy_core.py` (shared): `_plan_phase_set`, `_unchecked_wus_in_plan_scope`, `_all_wus_in_plan_scope`, `_phases_text_scoped_to`, `_plan_wu_checkbox_counts`, `_plan_unchecked_wus_are_verification_only`, `remaining_unchecked_are_verification_only`. Only the workstation stale-flip is owed (the cloud-saturation gate `_plan_cloud_saturated` is `lazy-state.py`-local and feature/cloud-specific — out of scope for the bug mirror; bug-state.py has no cloud-saturated flip today).

## Fix Scope

- Mirror the workstation stale-flip block into `bug-state.py` Step 7a between `plan = plans[0]` and the `execute-plan` return: emit `__flip_plan_complete_stale__` with `sub_skill_args=str(plan)` and the same `current_step` string when `finalize_stale`.
- Import the six `lazy_core` helpers not yet imported by `bug-state.py`.
- Add a `--test` fixture asserting the emit (positive) — the existing "mid-fix" fixture (plan scope has genuine unchecked WUs) is the discriminating negative control that must stay `execute-plan`.
- Regenerate the `bug-state-test-baseline.txt` byte-pin through `_normalize_smoke_output`; keep `lazy_parity_audit.py` exit 0.
