# Completion-coherence gate is blind to the canonical descope marker — Investigation Spec

> The mid-feature bypass (`remaining_unchecked_are_verification_only`) and `--verify-ledger`
> both recognize the canonical `_DESCOPED_MARKER` (`<!-- descoped -->`, row- or header-scope)
> and treat a deliberately-DROPPED-in-place unchecked row as non-blocking. But the
> `apply_pseudo __mark_complete__` / `__mark_fixed__` completion-coherence gate
> (`_phase_completion_plan`) checked ONLY the verification-only marker and counted every
> descoped row as a "genuine incomplete deliverable", refusing the receipt with a nonzero
> status. A feature that legitimately deferred a whole phase by SPEC decision therefore
> **deadlocked at the finish line**: `--verify-ledger` returned `ok:true` but
> `--apply-pseudo __mark_complete__` refused.

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** 6ec23c18
**Priority:** P1
**Last updated:** 2026-07-13
**Related:** `docs/bugs/_archive/verification-only-bypass-blind-to-descoped-rows/` (established the mid-feature descope carve-out); `docs/bugs/_archive/descoped-row-recognition-needs-canonical-marker/` (introduced the canonical `_DESCOPED_MARKER` constant + row/header-scope semantics this gate must mirror); `docs/specs/turn-routing-enforcement/` (owns the hardening stage that surfaced this). Sibling of the completion-coherence-gate-reconciliation feature (which reconciled the verification-only axis at completion time; this closes the descope axis it left open).

## Verified Symptom

Live claude-config `/lazy-batch` run, item `state-cli-contract-registry`, this session (2026-07-13). `docs/features/state-cli-contract-registry/PHASES.md` Phase 4 (`state_cli.py` extraction) was DEFERRED, not attempted — per SPEC Locked Decision 5 ("deferred, not provisionally accepted … not a fork requiring operator ratification"). Its 4 deliverable rows each carry the canonical row-scope marker `<!-- descoped -->`, and the `**Deliverables:**` header carries it header-scope. Phase 4 has NO `**Status:**` line.

Reproduced directly against the shipped code (pre-fix):

```
remaining_unchecked_are_verification_only(phases_text): True
_phase_completion_plan(parse_phases(phases_text)) refusals:
  ['### Phase 4: state_cli extraction — DEFERRED, not attempted: 2 unchecked box(es)']
```

`--verify-ledger` passes (its `deliverables_done` reuses `remaining_unchecked_are_verification_only`, which honors the descope marker) but `--apply-pseudo __mark_complete__` refuses on the SAME PHASES.md — an unrecoverable no-progress loop for a legitimately-deferred phase.

## Root Cause

**Classification: `script-defect`** (`user/scripts/lazy_core.py`).

Two functions decide "is this unchecked row owed work?" and they had diverged:

- `remaining_unchecked_are_verification_only` (~L2483–2550, mid-feature bypass) recognizes the descope marker on THREE paths — row-scope `_DESCOPED_MARKER in line`, header-scope `section_has_descope_marker`, and the legacy struck-through `_row_is_descoped_in_place` shim — and treats such rows exactly like Superseded-phase rows (exempt, `saw_descoped_unchecked`).
- `_phase_completion_plan` (~L2972–3049, completion gate inside `__mark_complete__`/`__mark_fixed__`) refused on `ph["unchecked"] > 0` with **no descope awareness at all**. `parse_phases` produced only a bare `unchecked` count (descoped rows indistinguishable from genuine ones), so the gate could not tell a deliberately-dropped row from an unfinished deliverable.

The verification-only axis had already been reconciled at completion time (evidence-gated auto-tick), but the descope axis was never taught to the completion gate — so the descope marker worked everywhere EXCEPT the one seam that ships the feature.

## Fix Scope

Mirror the mid-feature descope recognition into the completion gate, single-source in `lazy_core`:

1. `parse_phases` gains an additive per-phase `unchecked_descoped` count — a strict subset of `unchecked` (which stays byte-identical for every existing caller). A row counts as descoped when it carries the row-scope `_DESCOPED_MARKER`, sits under a header-scope descope marker (bold subsection header or non-phase heading carrying the marker; scope reset at each phase heading and closed by a marker-less verification/deliverables header — the descope axis of the scope machinery already proven in `remaining_unchecked_are_verification_only`), OR matches the legacy `_row_is_descoped_in_place` shim.
2. `_phase_completion_plan` gates on `effective_unchecked = unchecked − unchecked_descoped` for BOTH the blocking-refusal check AND the auto-flip `all_checked` predicate — so a fully-descoped phase (a) does not refuse and (b) auto-flips a non-terminal status to Complete just like an all-ticked phase, instead of tripping the status-straggler refusal.
3. Regression coverage: `test_lazy_core.py` fixtures for the repro (header+row-scope, no Status), header-scope-only, the mixed genuine+descoped case (must STILL refuse the genuine box — no over-exemption), the descoped-phase-with-non-terminal-status flip, and the `__mark_fixed__` mirror.

**Design fork considered, resolved NOT a fork.** Whether whole-phase deferral should ALSO be expressible via `**Status:** Superseded` — it already is, and is unaffected (`_phase_completion_plan` already `continue`s on Superseded). The descope-marker form is a SEPARATE, already-canonical mechanism for row-level / partial-phase deferral where the phase is not fully superseded; both forms already coexist in the mid-feature gate. Teaching the completion gate the descope form it was already supposed to honor is a mechanical defect fix, not an operator-owned design decision — no NEEDS_INPUT.

**Downstream lockstep note (out of scope, no regression).** AlgoBooth's `check-docs-consistency.ts` counts physical `- [x]` state and would flag a descoped `- [ ]` row under a Complete SPEC. This is not a regression: before this fix, an AlgoBooth feature with descoped rows could never reach `Complete` (it deadlocked identically), so no completed AlgoBooth PHASES.md has ever carried a descoped `- [ ]` row. claude-config (where the repro lives) does not run that checker. If a future AlgoBooth feature uses descoped-to-complete, teaching its TS checker the `<!-- descoped -->` annotation is a separate AlgoBooth-side follow-up — this agent never edits target-repo source.
