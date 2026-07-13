---
kind: needs-input
feature_id: plan-structure-authoring-gate
decisions:
  - id: D1-RESIDENCY
    summary: Structural-check functions live in validate-plan.py this round, not hoisted into lazy_core.py (D1's literal recommendation) — a lazy_core.py edit is out of this session's lane scope.
  - id: D3-SCOPE
    summary: /write-plan-cloud excluded from the finalization-gate injection (its output format explicitly bans the checkboxes these rules assume); write-plan-cognito also deferred (laptop-validated skill).
  - id: D4-NOT-DONE
    summary: The pickup backstop (state-script in-process validation at plan pickup) is not implemented — requires lazy_core.py/lazy-state.py/bug-state.py edits, out of this session's lane scope.
divergence: product
audit_divergence: SPEC D1/D4 assume a single implementer with lazy_core.py in scope; this session's SKILLS-lane/STATE-lane split means the "thin CLI shell over lazy_core functions" and "in-process pickup backstop" halves of the design are not yet built. D3's "all five [skills] inherit it" is satisfied for four; the fifth (write-plan-cloud) is a documented incompatibility, not an omission.
written_by: plan-structure-authoring-gate-implementer
---

# Provisional decisions — plan-structure-authoring-gate

Recorded under the overnight park-provisional protocol (never halt). The SKILLS-lane scope
(Phases 1-3: the `validate-plan.py --structural` validator, its full six-rule set, and skill
wiring into `/write-plan` + `/spec-phases` + `/spec-phases-batch`) is fully implemented and
gate-green. This feature is **NOT marked Complete** pending the operator decisions below —
Phase 4 (the state-script pickup backstop) remains open, and two SPEC recommendations were
adapted rather than followed literally, both recorded here for ratification.

## Decision Context

### D1-RESIDENCY — where do the structural-check functions actually live?

**Problem:** SPEC D1 recommends "a thin CLI shell over functions that live in `lazy_core`" so
`bug-state.py`/`lazy-state.py` can call the same checks in-process for the D4 backstop without
shelling out. This session's briefing scoped me to `user/skills/**` + `user/scripts/
validate-plan.py` (+ its test) only — `user/scripts/lazy_core.py` and the state scripts were
explicitly reserved for a separate, concurrently-active STATE lane. I could not hoist the check
functions into `lazy_core.py` without violating that boundary (concurrent-writer risk on a file
another lane owns tonight).

**What I did instead:** implemented all six rule functions directly in `validate-plan.py`,
importing (never editing) `lazy_core`'s existing exception-free parsers/constants
(`_plan_wu_checkbox_counts`, `remaining_unchecked_are_verification_only`,
`_VERIFICATION_ONLY_MARKER`, `_VERIFICATION_SECTION_RE`, `_DELIVERABLES_SECTION_RE`,
`_PLAN_PART_RE`) for parity, and reimplementing (as exception-safe, non-`_die()`-calling
siblings) the frontmatter-adjacent helpers that would otherwise risk an uncontrolled process
exit mid-scan (`_parse_plan_frontmatter`/`parse_sentinel` call `_die()` → `sys.exit(2)` on
malformed YAML — fine for their existing callers, wrong for a validator that must report every
finding in one pass). D1's "one entry point, two modes" surface IS delivered exactly as
recommended; only the "functions live in lazy_core" clause is deferred.

**Options:**
- **(a) Hoist now [not chosen — lane boundary].** Move the rule functions into `lazy_core.py`
  so `lazy-state.py`/`bug-state.py` can call them in-process with zero subprocess cost. Correct
  per D1's literal text, but is a `lazy_core.py` edit — the STATE lane's file.
- **(b) Keep in `validate-plan.py`; Phase 4 shells out via subprocess [what's on disk now].**
  `lazy-state.py`/`bug-state.py` call `subprocess.run(["python3", "validate-plan.py",
  "--structural", path])` at the plan-pickup probe and parse its exit code + stdout. Simpler,
  zero `lazy_core.py` edit needed for the check logic itself (though the probe wiring itself is
  still a state-script edit), and the checks are pure-text so subprocess overhead is negligible
  (sub-10ms per real-corpus file measured this session). Slightly less "clean" than (a) — two
  processes instead of one — but avoids the hoist as a SEPARATE decision from the probe wiring.
- **(c) Hoist later, as the STATE lane's own follow-up.** The STATE lane, when it picks up Phase
  4, decides (a) vs (b) itself with the actual D4 wiring in front of it — likely the more
  practical sequencing, since the STATE lane will already be editing `lazy_core.py`/the state
  scripts for the probe change regardless.

**Recommendation:** (c), practically resolving to (b) unless the STATE lane's Phase 4 work finds
a reason to prefer (a) (e.g. wanting zero subprocess cost inside a tight probe loop — unlikely to
matter given the checks are pure-text and plan-pickup is a rare, not hot-path, event).

### D3-SCOPE — the fifth (and sixth) skill SPEC D3 named

**Problem:** SPEC D3 says the shared component is injected "so `/write-plan`,
`/write-plan-cloud`, `/plan-feature`, `/plan-bug`, and `/spec-phases(-batch)` all inherit it."
Reading `write-plan-cloud/SKILL.md` in full showed its own Step 4 Self-Containment Audit item 7
**explicitly bans** the checkbox format rules 1/2/3 assume ("No progress checkboxes... The
cloud agent doesn't tick boxes"). `/plan-feature`/`/plan-bug` turned out to need NO separate
injection (pure dispatch wrappers). A sixth planner not named in D3 —
`repos/cognito-forms/.claude/skills/write-plan-cognito/` — also produces lazy-pipeline-shaped
plans and arguably should inherit the gate too, but this session's operating brief defers
prose edits there to a work-laptop session (its live behavior is Cognito-runtime-validated only
there).

**What I did instead:** wired the component into `/write-plan`, `/spec-phases`, and
`/spec-phases-batch` (the three that actually author plan/PHASES content); confirmed
`/plan-feature`/`/plan-bug` inherit for free by dispatch; excluded `/write-plan-cloud` by path
convention (its `plans/cloud-*.md` output already classifies out-of-scope in the validator);
left `write-plan-cognito` untouched this session.

**Options:**
- **(a) Exclude write-plan-cloud permanently [chosen].** Its output format is categorically
  incompatible with rules 1/2/3 as designed — wiring it there would either force a format change
  onto write-plan-cloud (a much larger, separate decision affecting the Cognito cloud-agent
  workflow) or require a divergent, cloud-plan-specific rule subset. Neither is in this SPEC's
  scope.
- **(b) Wire write-plan-cognito now, as a purely structural/testable change.** The component
  injection itself is mechanical (one `!cat` line); but the brief for this session explicitly
  defers `write-plan-cognito` prose edits to the work laptop since its live validation only
  happens there. Not done this session.
- **(c) Leave write-plan-cognito unwired indefinitely.** Rejected as a permanent stance — it
  produces the same lazy-pipeline-shaped plan-part artifacts (per `lean-plan-files`'s pointer-
  based plan contract) and would benefit from the same authoring-time refusal.

**Recommendation:** (a) for `write-plan-cloud` (permanent, mechanical necessity); (b) as a
near-term follow-up for `write-plan-cognito`, done on the work laptop in a session that can
verify the injection against a live Cognito plan.

### D4-NOT-DONE — the pickup backstop is unimplemented

**Problem:** SPEC D4 recommends validating at plan pickup (`lazy-state.py`/`bug-state.py`, the
probe that first routes `/execute-plan` onto a plan part) so a structurally invalid plan
authored OUTSIDE these skills (hand-written, cloud-generated) is also caught. This requires
editing `lazy_core.py`/the state scripts, explicitly reserved for the concurrently-active STATE
lane this session.

**Options:**
- **(a) Implement it anyway, accepting the lane-boundary risk.** Rejected — the operating
  brief's "one writer per file" rule exists precisely to prevent two concurrent agents from
  silently clobbering each other's edits to `lazy_core.py`/the state scripts.
- **(b) Leave Phase 4 open, feature stays Draft/In-progress [chosen].** Ship Phases 1-3 (fully
  gate-green, independently valuable — the finalization-time refusal already closes the two most
  common defect classes from the mined incidents) now; Phase 4 (the defense-in-depth backstop
  for plans authored outside these skills) is a clean, well-specified follow-up for whichever
  session next owns `lazy_core.py`/the state scripts.
- **(c) Descope Phase 4 from the feature entirely.** Rejected — SPEC D4 explicitly recommends it
  and the mined-incident evidence (hand-written/cloud-generated plans bypassing the skill-level
  gate) is real; it should stay a tracked open phase, not be quietly dropped.

**Recommendation:** (b). Phases 1-3 deliver the majority of the mined-incident value (the WU
checklist / verification placement / template-row / gate-owned-row classes were all authored
BY these skills, so the skill-level gate catches them at the source); Phase 4 is real defense-
in-depth for the smaller "plan authored outside the skills" surface and is correctly sequenced
as the next session's work once the STATE lane is free.

## Resolution

resolved_by: auto-provisional
decision_commit: c9162482028410a92b4692c552a8bba2f0c1f74a

- **D1-RESIDENCY — Choice:** (c)/(b) — check functions stay in `validate-plan.py`; Phase 4's
  STATE-lane implementer decides the in-process-hoist-vs-subprocess-shell-out question when it
  picks up the actual pickup-probe wiring.
- **D3-SCOPE — Choice:** (a) for `write-plan-cloud` (permanent exclusion, mechanical
  incompatibility); (b) for `write-plan-cognito` (near-term work-laptop follow-up, not done this
  session).
- **D4-NOT-DONE — Choice:** (b) — Phase 4 stays open; feature stays `In-progress`
  (`PHASES.md`) / `Draft` (`SPEC.md`), no `COMPLETED.md`, no Status flip to Complete, pending
  operator ratification of the above and a follow-up STATE-lane session for Phase 4.
