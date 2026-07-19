# Canary revert triage: harden-2026-07-r31 — Investigation Spec

> The canary for `harden-2026-07-r31` tripped on a +987.5% band-only rise of `event:halt`, but
> the shipped change only lets an operator-directed receipt-exempt close ENACT instead of
> re-looping into a halt — it can only *reduce* halts on its own path, and zero fresh incidents
> were attributed to its surface.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r31
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r31.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Sibling stub (identical trip numbers, same window): `docs/bugs/canary-revert-harden-2026-07-r32`
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `fc5f5371f0992184f3d32374393a3296237f899e` fixes a missing-contract defect:
the `apply-resolution` needs-input path had no way to enact an operator-directed receipt-EXEMPT
terminal close, because its constraint conflated the receipt-gated `Fixed` with the
receipt-exempt `Won't-fix` (a single `forbidden_status='Fixed or Won\'t-fix'` ban). A
"close as working-as-designed" resolution could therefore only neutralize the sentinel, never
set `Status: Won't-fix` — so the bug looped back into `spec-bug` and re-halted (`event:halt`) on
every subsequent probe instead of terminating. The fix splits the compound constraint into
additive `receipt_gated_status` (still banned without a receipt) and `receipt_exempt_status`
(now permitted for an operator-directed close); `forbidden_status` behavior for other templates
is unchanged. This only ADDS a legal terminal exit from a loop that previously had none — it
cannot itself trigger a new halt.

Trip evidence (`EVIDENCE.md`): `event:halt` +987.5% vs frozen baseline 1.3333 ev/run (29
post-ship occurrences over 2 window runs). Attributed fresh incidents: `(none — band-only
trip)`. This intervention's OWN `signal_independence` field explicitly names the confound:
*"halt is a broad proxy: the eliminated needs-input re-halt loop is one contributor to halt-event
volume; a decrease is consistent with the fix but confounded by unrelated halt sources
(blocked/needs-research), so the evaluator may cap at INCONCLUSIVE (confounded)."* The trip
numbers here are byte-identical to sibling `canary-revert-harden-2026-07-r32` (same baseline
1.3333, same post value 14.5, same window — both opened/tripped on the same days) — strong
evidence the aggregate spike is a single shared event attributed mechanically to every open
same-signal canary in that window, not two independent regressions.

## Resolution

Off-path for the regression: the change only adds a missing terminal exit from a pre-existing
re-halt loop (can only reduce `event:halt`), no incident names its surface
(`user/scripts/lazy_core.py`), and the intervention's own authoring already flagged the signal as
heavily confounded. The identical trip numbers shared with `r32` further confirm a shared
confound rather than two distinct causes. Closing as noise, evidence-based, consistent with the
`r48`/`r52`/`r53`/`r54` disposition precedent. The just-shipped confound-guard
(`efficacy-eval.py::_canary_should_enqueue`) would now suppress this
band-only/zero-attribution/can-only-reduce class at capture time.
`fc5f5371f0992184f3d32374393a3296237f899e` is retained, not reverted. Closed without a fix.
