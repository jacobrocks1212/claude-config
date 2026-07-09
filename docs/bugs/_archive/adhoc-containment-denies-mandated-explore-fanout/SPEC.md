# Containment hook denied mandated Explore fan-out in subagent runs — Investigation Spec

> The `lazy-cycle-containment.sh` D4 arming-free `agent_id` trip blanket-denied `Agent`/`Task`
> dispatch from ANY subagent, making the touchpoint-audit-gate's mandatory Explore fan-out
> structurally unsatisfiable in every subagent-context planning run.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-09 (live, sandboxed `/write-plan-cognito` Opus subagent — both Explore dispatches denied with no cycle marker present; fell back to inline Read/Grep)
**Fixed:** 2026-07-09
**Fix commit:** 7108b2e
**Placement:** docs/bugs/adhoc-containment-denies-mandated-explore-fanout
**Related:** `docs/features/lazy-cycle-containment/SPEC.md` (2026-07-09 amendment); `user/skills/_components/touchpoint-audit-gate.md`; `docs/bugs/_archive/hardening-blind-to-process-friction` (D4 origin)

---

## Root cause (traced)

- The D4 "arming-free agent_id trip" in `user/hooks/lazy-cycle-containment.sh` denied `tool_name in ("Agent","Task")` for any payload carrying `agent_id` — i.e. every subagent, marker or no marker.
- The design assumed the harness forbids recursive subagent dispatch, so the deny was "explicit intent + future-proofing". That premise is FALSE: the harness DOES allow nested dispatch (verified live 2026-07-09 — the subagent's `Agent` tool_use reached the PreToolUse layer, and after removal a probe subagent's nested Explore dispatch succeeded end-to-end).
- Consequence: any skill mandating read-only Explore fan-out (touchpoint-audit-gate Step B) run inside a subagent was forced to violate its own MANDATORY gate.

## Fix (shipped)

**Session 1 (2026-07-09, operator-directed, pre-filing):**
- Removed the `Agent`/`Task` recursion deny from `user/hooks/lazy-cycle-containment.sh` (all other containment retained: `/lazy*` Skill deny, nested-batch deny, LOOP_FORMATION_FLAGS routing/lifecycle, dev:kill/restart, marker-gated commit tripwires).
- Dropped the `Agent` matcher group from `user/settings.json`; updated the root `CLAUDE.md` hooks row.
- Inverted the three recursion tests in `user/scripts/test_hooks.py` to allow-assertions (regression guards); re-pointed the deny-events test to the retained `skill-lazy-family` signature. 130/131 green (sole failure `test_pipe_tests_wsl` — environmental WSL timeout).

**Session 2 (this fix — the filed remaining scope):**
- Swept every live doc/prose surface still claiming the recursion deny or the harness limit:
  - `user/scripts/lazy_core.py` CYCLE_REFUSED_OPS C2/C3 lockstep comment — narrowed C2 deny-set enumeration.
  - `user/scripts/CLAUDE.md` C3 refuse-by-construction line — same enumeration fix.
  - Coupled-trio containment-summary bullets (`lazy-batch` §machinery, `lazy-bug-batch`, `lazy-batch-cloud`) — "recursive `Agent`" removed from the C2 deny list, dated pointer added.
  - `lazy-batch` "Cycle-subagent execution model" paragraph + `lazy-bug-batch` mirror — the inline override is now stated as deliberate POLICY (context economy + single-writer containment), not a harness limit; the stale "tool unavailable" empirical claim is dated and corrected.
  - `_components/lazy-batch-prompts/cycle-base-prompt.md` inline-override + cloud-override sections — reworded from "does NOT have the `Agent` tool / any call fails" (false) to an explicit policy prohibition ("do not rely on the tool being absent or on a hook denying it").
  - `lazy-batch-retro` workstation inline-override grading branch — same policy-first correction.
  - `docs/features/lazy-cycle-containment/SPEC.md` — dated 2026-07-09 amendment at both recursion-deny claims.
  - `docs/features/long-build-and-runtime-ownership/SPEC.md` — enforcement-seam enumeration corrected.
- Reconciled the touchpoint-audit-gate exit check with dispatch-unavailable contexts: new Step B **Fallback — dispatch unavailable** (inline verification with the same per-file briefing, marked `verified: inline (dispatch unavailable)`), and the exit-check box now accepts Explore-agent OR marked-inline verification (never from memory).
- **Deliberately left unmodified (historical records):** `docs/bugs/_archive/hardening-blind-to-process-friction/` (archived), `docs/features/*/plans/*` and `RESEARCH_PROMPT.md` (frozen execution/prompt artifacts), `docs/specs/lazy-validation-readiness/PHASES.md`, the cognito-pr-review spot-check PHASES deviation note (records what happened at the time).

## Verification

- `python -m py_compile user/scripts/lazy_core.py` — OK.
- `python user/scripts/lazy_parity_audit.py --repo-root .` — exit 0 (coupled lazy/lazy-bug pairs still in parity after the mirrored edits).
- `python user/scripts/doc-drift-lint.py --repo-root .` — 4 checks, 0 drift findings, 1 pre-existing exempted divergence.
- `python user/scripts/project-skills.py` + `lint-skills.py` — projections re-expanded; no broken/embedded `!cat` patterns.
- Session-1 evidence: `test_hooks.py` 130/131; live nested-Explore probe returned successfully.
