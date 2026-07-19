# Canary revert triage: harden-2026-07-r92 — Investigation Spec

> The canary for `harden-2026-07-r92` tripped on a +40.0% band-only rise of `event:halt`, but the
> shipped change removes a flag-gate that was inertly suppressing a cross-script deadlock
> exclusion on the bug side — it can only *reduce* halts on its own path, and zero fresh
> incidents were attributed to its surface.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r92
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r92.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `981191ae005a8a5e72898b488031b0815352b200` fixes the "6th facet of the
merged-head exclude-set class" (cross-script split-brain deadlock): the research-pending
exclusion in `nondispatchable_item_ids` was gated on `skip_needs_research`, a flag only
`lazy-state.py` threads — `bug-state.py` has no such flag, so the gate made the exclusion inert
on the bug side. The two scripts computed DIFFERENT merged heads for the same on-disk state (the
feature side excluded the research head, the bug side did not), and neither dispatched: a
cross-script split-brain deadlock (`event:halt`). The fix drops the `skip_needs_research and`
gate so the exclusion is unconditional on both scripts. Dropping a conditional gate on an
EXCLUSION only ever widens the exclude set — it structurally cannot introduce a new dispatch
withhold, only remove one.

Trip evidence (`EVIDENCE.md`): `event:halt` +40.0% vs frozen baseline 1.0 ev/run (7 post-ship
occurrences over 5 window runs), band ±25% — numbers identical to sibling `r93`'s trip (same
2026-07-18 window, same signal), reinforcing that this is a shared confounded aggregate rather
than two independent regressions. Attributed fresh incidents: `(none — band-only trip)`. This
intervention's own `signal_independence` field is explicitly `mixed`, describing the fix as
driving down only a SUBSET of halts (research-skip-run cross-script no-route stalls).

## Resolution

Off-path for the regression: the change only removes a dead conditional on an exclusion (can
only reduce `event:halt`), and no incident names its surfaces (`lazy_core/depdag.py`,
`lazy_core/docmodel.py`). The identical band numbers shared with sibling `r93` in the same
window is itself evidence of a shared confound, not two independent causes. Closing as noise,
evidence-based, consistent with the `r48`/`r52`/`r53`/`r54` disposition precedent. The
just-shipped confound-guard (`efficacy-eval.py::_canary_should_enqueue`) would now suppress this
band-only/zero-attribution/can-only-reduce class at capture time.
`981191ae005a8a5e72898b488031b0815352b200` is retained, not reverted. Closed without a fix.
