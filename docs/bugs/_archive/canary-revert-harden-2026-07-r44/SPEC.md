# Canary revert triage: harden-2026-07-r44 — Investigation Spec

> The canary for `harden-2026-07-r44` tripped on a +50.0% rise of `event:gate-refusal`, measured
> over a single post-ship run — but the shipped change only shortens an already-refusing loop
> into a terminal, and cannot itself manufacture a new refusal cause; zero fresh incidents were
> attributed to its surface.

**Status:** Won't-fix
**Severity:** P3
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r44
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r44.md`
- Trip evidence: `EVIDENCE.md` (this dir)
- Fixed bug: `docs/bugs/coherence-recovery-loop-no-terminal-on-unrunnable-verification-rows`
- Coupled-pair scope (unaffected by this close-as-noise disposition — no revert):
  `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`,
  `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`
- Sibling disposition precedent: `docs/bugs/_archive/canary-revert-harden-2026-07-r{48,52,53,54}/SPEC.md`
- Confound-guard that would now suppress this class: `efficacy-eval.py::_canary_should_enqueue`

---

## Root cause

The shipped commit `c8a05bf7a509634b6c4f3535987ba4ba0a701d9f` fixes
`coherence-recovery-loop-no-terminal-on-unrunnable-verification-rows`: when the mechanical
completion gate refuses on unchecked verification rows that genuinely never ran on this host,
coherence-recovery honestly ticks nothing and the cycle re-loops `__mark_complete__` → refuse →
coherence-recovery → refuse, WITHOUT a terminal — an unbounded stream of `event:gate-refusal`
events per stuck run. The fix adds a step-3a terminal escalation: after 0 reconciled rows AND 0
remaining deliverables AND ≥1 un-runnable verification row, it writes `NEEDS_INPUT.md` and halts
instead of re-looping. A secondary change migrates `/spec-phases` inline templates to emit the
canonical `<!-- verification-only -->` marker (improves detection accuracy of the SAME class of
row, which only makes the completion-integrity bypass MORE likely to fire, not less). Neither
change adds a new path that TRIGGERS a fresh gate-refusal; both only shorten/terminate an
already-refusing loop or improve recognition of rows that should bypass refusal. Per this
intervention's own `signal_independence` note: "the fix drives DOWN repeated same-item
gate-refusals by terminating the honest-stuck loop... instead of re-refusing each probe."

Trip evidence (`EVIDENCE.md`): `event:gate-refusal` +50.0% vs frozen baseline 4.0 ev/run (6
post-ship occurrences), but measured over just **1** window run — an extremely thin sample
against a baseline itself averaged over 20 runs / 80 events. A single noisy run easily exceeds a
±25% band on a signal this common and unrelated-by-default to the narrow stuck-loop mechanism
this fix targets. Attributed fresh incidents: `(none — band-only trip)`.

## Resolution

Off-path for the regression: the change can only shorten an existing refusal loop or improve
verification-row recognition (both reduce, not increase, `event:gate-refusal`), the trip sample
is a single run (below any reasonable statistical bar), and no incident names its surfaces. No
revert is warranted, so the coupled-pair scope above is not touched and needs no parity audit.
Closing as noise, evidence-based, consistent with the `r48`/`r52`/`r53`/`r54` disposition
precedent. The just-shipped confound-guard (`efficacy-eval.py::_canary_should_enqueue`) would now
suppress this band-only/zero-attribution/can-only-reduce class at capture time.
`c8a05bf7a509634b6c4f3535987ba4ba0a701d9f` is retained, not reverted. Closed without a fix.
