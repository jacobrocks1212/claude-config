---
kind: bug-investigation
bug_id: verify-ledger-deliverables-done-fails-pre-decomposition-feature
severity: P2
discovered: 2026-07-20
status: Fixed
written_by: harden-harness
---

# `verify_ledger.deliverables_done` hard-fails every PRE-DECOMPOSITION feature (PHASES.md absent), asymmetrically with its own sibling `plan_complete`

**Status:** Fixed (root cause proven by live repro; fix shipped OUT-OF-PIPELINE at `5529a973`
**Fixed:** 2026-07-20
**Fix commit:** 7ff09734
under a `harden(script):` commit — see `FIXED.md`). This is the durable investigation record
cited by hardening Round 118.

**Root-cause class:** `script-defect` — an incomplete application of the
`harness-hardening-retro-fixes` Phase 3 *absent-by-design* carve-out. Phase 3 taught
`verify_ledger` that a MISSING artifact on a feature that never needed one is
**not-applicable**, not failing — but applied that lesson to `plan_complete` ONLY. The
sibling `deliverables_done` check, in the same function, retained the unconditional
`False`-on-absent behavior, so the two checks now disagree about the SAME feature state.

## Symptom (verified live, 2026-07-20)

Observed on `inspector-track-dashboard` (AlgoBooth,
`docs/features/ui/secondary-ui-v2/domains/inspector-track-dashboard/`) during a run whose
cycle marker carried `sub_skill: plan-feature` and whose only plan on disk is a
`/realign-spec` output (`plans/realign-2026-07-20.md`). The feature is a scope stub: it has
`SPEC.md` + `RESEARCH*.md` and has NOT been decomposed, so `PHASES.md` cannot exist yet.

Reproduced verbatim against shipped `HEAD` (`0bb0b53a`):

```
$ python3 ~/.claude/scripts/lazy-state.py --verify-ledger \
    docs/features/ui/secondary-ui-v2/domains/inspector-track-dashboard
{
  "ok": false,
  "failing_check": "deliverables_done",
  "checks": {
    "clean_tree": true,
    "head_matches_origin": true,
    "plan_complete": true,
    "deliverables_done": false
  },
  "deliverables_source": "phases-feature-level",
  "failing_detail": {
    "deliverables_done": { "rows": [], "total": 0, "note": "PHASES.md absent" }
  }
}
```

Read the payload carefully — it is self-indicting:

- `clean_tree`, `head_matches_origin` and `plan_complete` **all pass**. The cycle is
  genuinely clean; there is no residue, no unpushed commit, no incomplete plan.
- `plan_complete: true` is produced by the Phase-3 **absent-by-design** carve-out
  (`gates.py:1757-1763`) — the gate has ALREADY decided that this exact feature state
  ("no implementation plan, none required") is not-applicable rather than failing.
- `deliverables_done: false` carries `rows: []`, `total: 0`. There are **zero** offending
  deliverables. The check fails on the ABSENCE of the surface it reads, not on any
  unfinished work found in it.

The turn-end TERMINAL VERIFY GATE (`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`
§3, both `@section turn-end` blocks) directs the cycle subagent to "RECONCILE the named check
in-turn and RE-RUN until `ok:true`. Only an `ok:true` verdict authorizes return." The named
check here is unreconcilable: the ONLY way to make `deliverables_done` true is to create a
`PHASES.md`, i.e. to **decompose the feature** — work the cycle was not dispatched to do, and
which `@section status-honesty` forbids fabricating. So the cycle is wedged between an
unsatisfiable gate and a scope violation. This hard-fails **every** pre-decomposition cycle
(realign / spec / research-ingest) on a scope-stub feature, not just this instance.

## Root cause (proven)

`lazy_core/gates.py::verify_ledger`, feature-level branch of check 4:

```python
    else:
        # Feature-level (no plan_path): the whole feature's PHASES.md.
        if not phases_file.exists():
            # No PHASES.md means we have no evidence of phases being completed.
            deliverables_done = False
```
(`user/scripts/lazy_core/gates.py:1829-1833`)

Compare the sibling check 3, twenty lines earlier, which handles the structurally identical
question correctly:

```python
        if not plan_complete and len(incomplete_plans) == 0 and not any_complete:
            if not _implementation_plans_exist(spec_path):
                plan_complete = True
                _diag("plan_complete: no implementation plan required (absent-by-design)")
```
(`user/scripts/lazy_core/gates.py:1757-1763`)

The asymmetry is the defect. Both checks read an artifact that a pre-decomposition feature
legitimately does not have. Check 3 distinguishes **absent-by-design** (the artifact was never
required) from **incomplete** (the artifact exists but is not done) and passes the former.
Check 4 collapses both into `False`.

The docstring's stated justification — *"No PHASES.md means we have no evidence of phases
being completed"* (`gates.py:1617-1618`) — is sound for a feature that HAS been planned and
whose PHASES.md went missing. It is wrong for a feature that has never been decomposed, where
there are no phases to have evidence about. The predicate that separates those two worlds
already exists and is already imported into this module: `_implementation_plans_exist`
(`lazy_core/docmodel.py:930-955`), whose own docstring says it exists precisely "to distinguish
*absent-by-design* … from *incomplete*".

**Why this is not a gate-weakening.** The corrected branch fires ONLY when BOTH artifacts are
absent — no `PHASES.md` **and** no implementation plan — which is exactly the state in which
`plan_complete` already returns True. Every other state is byte-identical:

| feature state | before | after |
|---|---|---|
| `PHASES.md` present (any content) | unchanged | unchanged |
| `PHASES.md` absent, implementation plan EXISTS | `False` | `False` (regression guard) |
| `PHASES.md` absent, no implementation plan (pre-decomposition) | `False` | `True` + diagnostic |
| plan-scoped (`--plan`), incl. the legacy phases-fallback | unchanged | unchanged |

The change removes no gate, softens no threshold, and bypasses no check. It reclassifies one
vacuous verdict (`total: 0` offending rows) from vacuous-FALSE to vacuous-TRUE, narrowly, and
announces itself via a `_diag` breadcrumb plus a distinct `deliverables_source` value so the
carve-out is never silent.

**Residual completion risk, assessed.** Could this let a feature reach `__mark_complete__` with
no PHASES.md at all? The completion path's coherence gate is
`docmodel.py::_phase_completion_plan`, which iterates the PARSED phases; with no PHASES.md it
sees zero phases and already produces zero refusals. So `deliverables_done` was never the
control that prevented that, and `plan_complete` already passes for the same feature. The
control that actually keeps an un-implemented feature out of completion is the ROUTING layer
(a spec-only feature routes to decomposition/planning, never to completion). This change does
not touch routing.

## Fix scope

1. `user/scripts/lazy_core/gates.py::verify_ledger` — in the feature-level branch of check 4,
   gate the `False` on `_implementation_plans_exist(spec_path)`. When no implementation plan
   exists either, set `deliverables_done = True`, emit a `_diag` breadcrumb mirroring the
   Phase-3 wording, and set `deliverables_source` to a distinct
   `"not-applicable (pre-decomposition — no PHASES.md, no implementation plan)"` value so the
   carve-out is visible to operators, retro grading and incident mining.
2. Update the `verify_ledger` docstring (check-4 prose + the `deliverables_source` legend) so
   the documented contract matches the code, and cross-reference the Phase-3 precedent.
3. Regression tests in `tests/test_lazy_core/test_gates.py`, registered in that file's
   `_TESTS` list (the orphan guard `test_no_orphaned_test_functions` enforces registration):
   - pre-decomposition feature (no PHASES.md, realign-only plan) → `ok: true`, all four checks
     true, `deliverables_source` names the not-applicable path;
   - **regression guard** — no PHASES.md but an implementation plan present →
     `deliverables_done` still `False` (proves the carve-out is not a blanket pass).

## Decision class

The fix changes COMPLETION-GATE semantics, which `/harden-harness` Step 3 reserves for the
operator. It is not a gate-weakening carve-out and not `structural`, so it takes the
**park-provisional** disposition: implement the recommended option, author a `NEEDS_INPUT.md`
recording the fork, and provisionalize it so the choice is ratification-pending rather than
silently baked in. Fork recorded at
`docs/specs/turn-routing-enforcement/NEEDS_INPUT_2026-07-20-verify-ledger-pre-decomposition-deliverables.md`.

## Related (out of scope for this bug — recorded so it is not lost)

`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #16 (harden Round 51) was marked
**"[RESOLVED 2026-07-18 → scope verify-ledger substep to completion-capable skills]"**, but the
resolution was **never implemented**: both `@section turn-end` directives in
`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (lines 616 and 669) still
read `skills=all`. That unimplemented resolution is the SECOND layer of this same friction —
had it landed, a non-completion cycle would not run the completion gate at all. It is a
distinct work item (it forks the load-bearing completion-capable skill LIST) and is surfaced
in Round 118's return rather than absorbed here. Note the two fixes are complementary, not
redundant: even a completion-capable cycle should not fail on a not-applicable check.
