# Canary revert triage: harden-2026-07-r97 — Investigation Spec

> The canary for `harden-2026-07-r97` tripped on a +75.0% band-only rise of `event:halt`, but the
> shipped change is a pure exclusion fix that can only *reduce* halts on its own path, and zero
> fresh incidents were attributed to its surface — a confounded, close-as-noise trip.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r97
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r97.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `04ecf9632dc96a0f8b8e476609b071e820399d2b` fixes
`adhoc-bug-pickup-routes-superseded-specs`: `_find_open_bug_dirs` in `user/scripts/bug-state.py`
previously had no skip case for a resolved-but-unarchived `Superseded` bug dir, so such a dir was
auto-discovered as open work, entered `merged_worklist`, became the merged head, and triggered a
universal `merged-head-diverged` withhold — wedging the run with `event:halt`. The fix adds ONE
new `continue` skip case (`BUG_STATUS_SUPERSEDED`), mirroring the feature-side loader's existing
Superseded skip. The diff is purely additive/narrowing: it only ever REMOVES a dir from the
worklist, never adds one, so it structurally cannot cause a NEW halt — it can only reduce the
specific merged-head-diverged wedge it targets.

Trip evidence (`EVIDENCE.md`): `event:halt` +75.0% vs frozen baseline 1.0 ev/run (7 post-ship
occurrences over 4 window runs), band ±25%. Attributed fresh incidents: `(none — band-only
trip)`. Three sibling hardening commits (r93, r92, and this one) shipped on the same day
(2026-07-18) targeting the same `event:halt` signal — a highly confounded window in which any
aggregate movement is mechanically attributed to every open canary sharing the signal, not
necessarily caused by any one of them.

## Resolution

Off-path for the regression: the change can only reduce `event:halt`, and no incident names its
surface (`user/scripts/bug-state.py`). Closing as noise, evidence-based, consistent with the
`r48`/`r52`/`r53`/`r54` disposition precedent from this same triage session. The just-shipped
confound-guard (`efficacy-eval.py::_canary_should_enqueue`) would now suppress exactly this
band-only/zero-attribution/can-only-reduce class at capture time, so this disposition also
validates that guard's design. `04ecf9632dc96a0f8b8e476609b071e820399d2b` is retained, not
reverted. Closed without a fix.
