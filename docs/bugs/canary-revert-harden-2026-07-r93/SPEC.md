# Canary revert triage: harden-2026-07-r93 — Investigation Spec

> The canary for `harden-2026-07-r93` tripped on a +40.0% band-only rise of `event:halt`, but the
> shipped change only WIDENS a bypass that skips a write-plan infinite-loop halt — it can only
> *reduce* halts on its own path, and zero fresh incidents were attributed to its surface.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r93
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r93.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Fixed bug: `docs/bugs/bug-state-verification-only-remainder-loops-write-plan`
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `0258a5b8c69174e2fe7bdfb7133f566bdb4ff644` fixes
`bug-state-verification-only-remainder-loops-write-plan`: `compute_state`'s Step-7 plan-needed
predicate in `user/scripts/bug-state.py` required `_has_any_complete_plan` before bypassing
write-plan for a verification-only PHASES remainder, so a bug fixed OUT-OF-PIPELINE (impl rows
`[x]`, no `plans/` dir) with a sole verification-only unchecked row fell to write-plan, which
`/write-plan` Step 1c.5 refuses — an infinite write-plan loop, each iteration a halt-adjacent
no-forward-progress cycle. The fix splits the bypass into a `cloud_bypass` (unchanged legacy
condition) and a new, strictly WIDER `workstation_bypass` (drops the `_has_any_complete_plan`
requirement when the remainder is verification-only). The legacy case is a documented subset of
the new one — the diff only adds routes AWAY from the write-plan halt path, never toward it, so
it structurally cannot cause a NEW halt.

Trip evidence (`EVIDENCE.md`): `event:halt` +40.0% vs frozen baseline 1.0 ev/run (7 post-ship
occurrences over 5 window runs), band ±25%. Attributed fresh incidents: `(none — band-only
trip)`. This intervention's own `signal_independence` field explicitly notes the halt terminal is
emitted by loop-detection/no-route logic downstream of this fix, not by the fix itself. Two
sibling hardening commits (r97, r92) shipped in the same 2026-07-18 window, also targeting
`event:halt` — a heavily confounded window.

## Resolution

Off-path for the regression: the change only widens an exclusion (can only reduce `event:halt`),
and no incident names its surface (`user/scripts/bug-state.py`). Closing as noise,
evidence-based, consistent with the `r48`/`r52`/`r53`/`r54` disposition precedent. The just-shipped
confound-guard (`efficacy-eval.py::_canary_should_enqueue`) would now suppress this
band-only/zero-attribution/can-only-reduce class at capture time.
`0258a5b8c69174e2fe7bdfb7133f566bdb4ff644` is retained, not reverted. Closed without a fix.
