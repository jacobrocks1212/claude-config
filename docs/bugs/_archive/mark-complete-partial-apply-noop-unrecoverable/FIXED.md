---
kind: fixed
feature_id: mark-complete-partial-apply-noop-unrecoverable
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: state-script-test-suite (test_lazy_core.py pytest + lazy-state.py/bug-state.py --test smoke harnesses; NOT pipeline-gated)
auto_ticked_rows: 0
---

# Completion Receipt

`mark-complete-partial-apply-noop-unrecoverable` marked **Fixed** on 2026-07-12 by the
state-script-lane bug-fix subagent Jacob directed (implement-directly-from-PHASES; bugs skip
`/write-plan`). This receipt was written by the implementing subagent, not the pipeline's
`__mark_fixed__` gate — provenance is `operator-directed-interactive`.

## Root cause (one sentence)

`apply_pseudo`'s `__mark_complete__`/`__mark_fixed__` idempotency check noop'd on
receipt-existence ALONE, but the receipt is the FIRST externally-observable post-condition
written — so a crash between the receipt write and the SPEC status flip left a receipt-present +
`Status: In-progress` dir that the receipt-only noop could never repair, looping the pipeline
forever.

## Fix

Replaced the receipt-only noop with a full post-condition audit
(`_completion_postconditions_missing`): a receipted dir noops ONLY when every completion
post-condition holds (SPEC status terminal, PHASES status terminal, cleanup sentinels absent, and
— feature path — queue entry trimmed + ROADMAP row struck); any missing post-condition triggers a
**RESUME** that skips the gates + receipt write + intervention capture (steps 1–4) and re-applies
only the idempotent tail (steps 5–10) to converge, surfacing `resumed: true`. The fix lives in the
**shared** `lazy_core.apply_pseudo` branch, so it repairs BOTH pipelines
(`__mark_complete__` / `__mark_fixed__`) from a single change — mirroring `archive_fixed`'s
existing resume-not-noop posture. No journal/transaction layer (SPEC D2); receipt-first ordering
kept (SPEC D3).

## Symptom-reproduction evidence (red → green)

`test_apply_pseudo_mark_complete_resumes_partial_apply` (in `user/scripts/test_lazy_core.py`)
materializes the EXACT crash state — a valid `COMPLETED.md` receipt, `**Status:** In-progress`,
a lingering `VALIDATED.md`, an untrimmed queue entry, and an unstruck ROADMAP row — then drives
the real `apply_pseudo`:

- **RED (pre-fix behavior, documented in the test):** the receipt-existence-only noop returned
  `noop=True` with zero writes, leaving `Status: In-progress` → the state machine re-routed to
  `__mark_complete__` on every probe (unrecoverable loop).
- **GREEN (post-fix):** `apply_pseudo` returns `resumed=True`, flips SPEC→Complete + PHASES→Complete,
  deletes `VALIDATED.md`, trims the queue entry, strikes the ROADMAP row, and
  `_completion_postconditions_missing(...) == []` afterward (converged). A second invocation is a
  clean `noop`.

The unrecoverable-loop repair is proven end-to-end at the walk level by the
`resume-partial-apply-walk-convergence` sub-test in `lazy-state.py --test`: `compute_state` routes
`__mark_complete__` against the partial dir, `apply_pseudo` RESUMES, and `compute_state` then no
longer routes `__mark_complete__` (the same Step-10 route is not computed twice — the loop is
broken). The `__mark_fixed__` bug-pipeline mirror is covered by
`test_apply_pseudo_mark_fixed_resumes_partial_apply`.

## Gate evidence

- `python -m pytest user/scripts/test_lazy_core.py` (clean `LAZY_STATE_DIR`): **1005 passed, 12
  failed** — all 12 failures are pre-existing run-end/checkpoint/marker tests hitting the
  `interventions-telemetry-repo-scope-split-brain` efficacy-flush gate, provably independent of this
  change (the entire `lazy_core.py` diff is confined to `apply_pseudo` + three new pure-read helpers
  inserted after `_strike_roadmap_row`; run-end/checkpoint/marker code is byte-identical to HEAD).
  All apply_pseudo/mark_complete/mark_fixed/coherence/baseline/no-orphaned tests pass (86/86 in the
  targeted verification run).
- `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test`: **all
  smoke tests passed** (incl. the new walk-level convergence sub-test + updated baseline).
- `python user/scripts/lazy_parity_audit.py --repo-root .`: exit 0.
- `python user/scripts/doc-drift-lint.py --repo-root .`: exit 0 (5 checks, 0 drift findings).

## Deferred / reported (out of this wave's file-ownership scope)

- `docs/features/CLAUDE.md` receipt-gate paragraph should gain the INVERSE rule (SPEC Fix Scope
  item 5): "a receipt with a non-terminal Status is a resumable partial completion, repaired by
  re-running `__mark_complete__`/`__mark_fixed__`." NOT edited here (not in the state-script lane's
  touch scope); the `user/scripts/CLAUDE.md` high-signal-invariants note WAS added.
