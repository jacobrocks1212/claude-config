# Canary revert triage: harden-2026-07-r64 — Investigation Spec

> The canary for `harden-2026-07-r64` tripped on a +325.0% band-only rise of `event:halt`, but
> the shipped change strictly WIDENS an exclude set that prevents a driver-stall withhold — it
> can only *reduce* halts on its own path, and zero fresh incidents were attributed to its
> surface.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r64
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r64.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Fixed bug: `docs/bugs/merged-head-diverged-stalls-on-gated-head`
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `3add529d6a8cd29a62aca708cf2c956ea70b0b87` fixes
`merged-head-diverged-stalls-on-gated-head`: the unified `/lazy-batch(-cloud)` merged-head
divergence check built its exclude set from a NARROW file predicate, while the per-pipeline
skip-ahead is BROADER (research-pending/BLOCKED gated heads, host/device-deferred, dep-gated). A
gated head therefore diverged from the workable item the probe had already chosen, and
`merged_head_override` WITHHELD the route (null `cycle_prompt` — an `event:halt`), stalling
forward progress even though a workable item existed. The fix adds a new pure helper
(`lazy_core.dispatch.probe_skipped_ids`) that folds the probe's OWN same-cycle skip lists into the
merged-head exclude set. Traced the diff directly (`git show 3add529d`): the change is 100%
additive (new function + call sites; zero deletions across `bug-state.py`, `lazy-state.py`,
`lazy_core/dispatch.py`), and the new exclude set is built ONLY from lists the probe already
computed for its own skip-ahead — it can only exclude MORE heads from the withhold check, never
fewer, so it structurally cannot cause a NEW stall.

Trip evidence (`EVIDENCE.md`): `event:halt` +325.0% vs frozen baseline 1.0 ev/run (34 post-ship
occurrences over 8 window runs), band ±25%. Attributed fresh incidents: `(none — band-only
trip)`. `signal_independence` is `self-emitted`, describing the stall this fix removes as itself
a halt source — a fix that eliminates a halt-emitting withhold cannot be the cause of MORE
halts on that same path.

## Resolution

Off-path for the regression: the change is a pure, tested, additive widening of an exclude set
that only ever removes withholds (can only reduce `event:halt`), and no incident names its
surfaces (`bug-state.py`, `lazy-state.py`, `lazy_core/dispatch.py`). The large percentage move is
consistent with a high-volume confounded window (the run's `event:halt` baseline here is a thin
4-run sample), not with this specific fix. Closing as noise, evidence-based, consistent with the
`r48`/`r52`/`r53`/`r54` disposition precedent. The just-shipped confound-guard
(`efficacy-eval.py::_canary_should_enqueue`) would now suppress this
band-only/zero-attribution/can-only-reduce class at capture time.
`3add529d6a8cd29a62aca708cf2c956ea70b0b87` is retained, not reverted. Closed without a fix.
