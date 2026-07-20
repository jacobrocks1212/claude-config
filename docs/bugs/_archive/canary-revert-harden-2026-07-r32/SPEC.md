# Canary revert triage: harden-2026-07-r32 — Investigation Spec

> The canary for `harden-2026-07-r32` tripped on a +987.5% band-only rise of `event:halt`, but
> the shipped change only gives `plan-bug` its own oscillation label to prevent a FALSE
> LOOP-DETECTED tripwire — it can only *reduce* halts on its own path, and zero fresh incidents
> were attributed to its surface.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r32
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r32.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Sibling stub (identical trip numbers, same window): `docs/bugs/canary-revert-harden-2026-07-r31`
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `879613d1c02afd20f2235fc832885cd46d7e42d7` fixes a false-oscillation defect:
`bug-state.py` dispatched `plan-bug` under the reused `STEP_INVESTIGATE` label, so the
`step_repeat_count` oscillation counter (keyed on `(feature_id, current_step)`, sub_skill-blind)
counted a genuine `spec-bug → plan-bug` forward-routing transition as same-step oscillation,
accumulating toward the `>=3` `LOOP-DETECTED` tripwire and its escalation to an `event:halt` on
legitimate first-`plan-bug` dispatches. The fix adds a distinct `STEP_PLAN_BUG` constant so the
counter no longer conflates the two steps — a pure additive labeling fix with no code path that
could newly TRIGGER a halt; it only prevents a false trigger.

Trip evidence (`EVIDENCE.md`): `event:halt` +987.5% vs frozen baseline 1.3333 ev/run (29
post-ship occurrences over 2 window runs). Attributed fresh incidents: `(none — band-only
trip)`. This intervention's OWN `signal_independence` field is unusually explicit about the
confound: *"the direct false-loop signal is not ledgered; halt is a broad, heavily-confounded
proxy... most halts are unrelated (blocked/needs-input/needs-research), so the evaluator will
likely cap at INCONCLUSIVE (confounded)."* The trip numbers here are byte-identical to sibling
`canary-revert-harden-2026-07-r31` (same baseline 1.3333, same post value 14.5, same window —
both opened/tripped on the same days) — strong evidence the aggregate spike is a single shared
event attributed mechanically to every open same-signal canary in that window, not two
independent regressions.

## Resolution

Off-path for the regression: the change is a pure oscillation-label fix that can only prevent a
false halt trigger (can only reduce `event:halt`), no incident names its surface
(`user/scripts/bug-state.py`), and the intervention's own authoring already flagged the signal as
heavily confounded. The identical trip numbers shared with `r31` further confirm a shared
confound rather than two distinct causes. Closing as noise, evidence-based, consistent with the
`r48`/`r52`/`r53`/`r54` disposition precedent. The just-shipped confound-guard
(`efficacy-eval.py::_canary_should_enqueue`) would now suppress this
band-only/zero-attribution/can-only-reduce class at capture time.
`879613d1c02afd20f2235fc832885cd46d7e42d7` is retained, not reverted. Closed without a fix.
