# Implementation Phases — `__mark_complete__` partial-apply crash window with an unrecoverable receipt-only noop

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Fixed

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface. The fix is a pure state-script change in `user/scripts/lazy_core.py` (`apply_pseudo`'s `__mark_complete__`/`__mark_fixed__` branch), verified by the repo's established pytest harness (`user/scripts/test_lazy_core.py`) plus the in-file `--test` smoke harnesses of `lazy-state.py`/`bug-state.py`. There is no `mcp-tool-catalog.md` in this repo, so the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The crash window is code-proven, not field-observed** — the SPEC's "Verified Defect" is a line-level trace of the live tree. The Phase-1 fixture materializes the exact partial state (receipt written, `**Status:** In-progress`, `VALIDATED.md` present, queue entry present, ROADMAP unstruck) by writing those files directly, then drives the REAL `apply_pseudo` — the reproduction IS the regression test (no crash injection needed; the partial disk state is the observable the loop routes on).
- **Every tail step (5–10) is already individually idempotent** (SPEC Fix Scope + `apply_pseudo` code read): SPEC/PHASES status is a `re.sub(count=1)` no-op once terminal; sentinel deletes are exists-guarded; the queue trim only rewrites when an entry was removed; `_strike_roadmap_row` skips already-struck rows; provenance/intervention are fail-open. So RESUME = "re-run the tail" converges without any new transactional/journal layer (SPEC D2).
- **The shared branch fixes both pipelines for free** — `__mark_complete__` and `__mark_fixed__` are the SAME branch of `apply_pseudo` in `lazy_core.py` (shared by `lazy-state.py` + `bug-state.py`). A single restructure covers both; the only per-pipeline divergence (feature-only queue-trim + ROADMAP-strike) is already gated on `not is_fixed` and is mirrored in the audit's post-condition set. No per-script mirror edit is owed (the fix is entirely in the shared layer); `lazy_parity_audit.py` does not audit `apply_pseudo` internals.

## Cross-feature Integration Notes

There is no `**Depends on:**` block in the SPEC (only `**Related:**`), so no upstream PHASES.md look-back applies. The `completion-coherence-gate-reconciliation` feature (Complete) is cross-linked with **zero fix-scope overlap** (it reconciled the gate's refusal RULE + per-write atomicity; this bug is the complementary sequence-level crash-consistency gap). `archive_fixed`'s existing resume-not-noop posture (`lazy_core.py`, step-1 gate detects a prior partial run and resumes) is the in-file precedent this fix mirrors into the receipt branch.

---

### Phase 1: Replace the receipt-only noop with a post-condition audit + idempotent-tail RESUME (both pipelines)

**Scope:** In `lazy_core.apply_pseudo`'s `__mark_complete__`/`__mark_fixed__` branch, replace the receipt-existence-only idempotency check with a **post-condition audit**: a receipted dir noops ONLY when every externally-observable completion post-condition holds (SPEC status terminal, PHASES status terminal, cleanup sentinels absent, and — feature path — queue entry trimmed + ROADMAP row struck). Any missing post-condition → **RESUME**: skip the gates + receipt write + intervention capture (steps 1–4) and re-execute only the idempotent tail (steps 5–10: SPEC/PHASES flip, sentinel delete, queue trim, ROADMAP strike, provenance), surfacing `resumed: true` + the re-applied artifacts. The shared branch fixes `__mark_complete__` and `__mark_fixed__` together. This is the load-bearing behavioral phase — after it, the crash-window partial state auto-repairs to fully-applied instead of looping forever.

**TDD:** yes. Write the failing crash-window resume tests FIRST (they fail against the current receipt-only noop: today the partial-state fixture returns `noop=True` / zero writes, leaving `**Status:** In-progress`), then restructure `apply_pseudo` green.

**Status:** Complete

**Deliverables:**
- [x] New read-only helper `_completion_postconditions_missing(spec_path, repo_root, feature_id, status_value, is_fixed)` in `lazy_core.py` returning the list of unsatisfied post-conditions (empty ⇒ genuinely done). Checks: first `**Status:**` line of SPEC.md/PHASES.md equals `status_value` (a file with NO status line counts as satisfied — the flip is a no-op there); `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` absent; feature path only — queue.json entry absent (reusing the trim's `_resolve_under_repo`/spec_dir/id match keys) + ROADMAP row struck (read-only mirror of `_strike_roadmap_row`'s match + `_ROADMAP_COMPLETE_TOKEN` idempotency test).
- [x] `apply_pseudo` branch: the receipt-noop block computes `receipt_present` + (when present) `missing_postconditions`; all satisfied → `_noop()` (preserved genuinely-done behavior, incl. re-completing-never-re-refuses; still sits BEFORE the retro-staleness/provisional/coherence gates exactly where the noop sat). Any missing → set `resuming = True` + `_diag(...)` breadcrumb naming the missing post-conditions.
- [x] Steps 1–4 (retro-staleness, provisional, auto-tick, coherence gate, receipt write, intervention capture) are SKIPPED when `resuming` (guarded so a resume never re-refuses on a gate that already passed pre-receipt and never clobbers the original receipt/provenance). `validated_via` + MCP counts derive without the receipt write; `wrote` starts empty on resume.
- [x] Result dict carries `resumed: <bool>` (False on the normal path and on a genuinely-done noop; True on a resume). Re-applied artifacts are surfaced via the existing `wrote`/`deleted` lists.
- [x] Tests (`user/scripts/test_lazy_core.py`): crash-window RESUME for `__mark_complete__` (receipt + In-progress SPEC + VALIDATED + queue entry + unstruck ROADMAP → resume converges: SPEC→Complete, VALIDATED deleted, queue trimmed, ROADMAP struck, `resumed=True`, `noop=False`; second call is a clean `noop=True`) and the `__mark_fixed__` mirror (FIXED.md receipt + In-progress SPEC + VALIDATED → resume converges: SPEC→Fixed, VALIDATED deleted, `resumed=True`; second call noop). Genuinely-done fixture → clean noop with `resumed=False`.
- [x] Existing receipt-only-noop tests updated to the new contract (their old "receipt + VALIDATED present ⇒ noop" fixtures were exactly the partial state the fix now RESUMES): `test_apply_pseudo_mark_complete_idempotent`, `test_apply_pseudo_mark_complete_queue_trim_behind_receipt_noop`, `test_apply_pseudo_mark_complete_receipted_noop_beats_stale_retro` reworked to assert the new resume/genuinely-done behavior (no re-refusal preserved).
- [x] Walk-level assertion in `lazy-state.py`'s in-file `--test` harness: after a resume repairs the partial dir to `**Status:** Complete` + receipt, `compute_state` no longer routes `sub_skill: __mark_complete__` against it (convergence — the loop is broken).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py` is GREEN and the new crash-window tests fail RED-for-the-right-reason against the pre-fix branch (partial-state fixture → `noop=True`, `**Status:** In-progress` unchanged). `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` GREEN (walk-level convergence + no parity regression). Concretely: an `apply_pseudo("__mark_complete__")` against a dir with a valid `COMPLETED.md` receipt but `**Status:** In-progress` + a present `VALIDATED.md` now flips the status to Complete, deletes `VALIDATED.md`, and returns `resumed=True` (today it returns `noop=True` with zero writes).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in this repo; the observable is the `apply_pseudo` return dict + on-disk convergence, asserted directly by the pytest fixtures above.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — new `_completion_postconditions_missing` helper (near `_strike_roadmap_row`); `apply_pseudo`'s `__mark_complete__`/`__mark_fixed__` branch restructured (receipt-noop → audit + resume-guarded steps 1–4).
- `user/scripts/test_lazy_core.py` — new crash-window resume tests (both pipelines) + genuinely-done noop test; three existing receipt-noop tests updated to the new contract. Reuse `_write_validated_md`, `_write_spec_md`, `_write_features_queue`, `write_completed_receipt`.
- `user/scripts/lazy-state.py` — one walk-level convergence fixture added to the in-file `--test` list (repaired dir no longer routes to `__mark_complete__`).

**Testing Strategy:** Pure fixture testing over the real `apply_pseudo` (no new subprocess harness) — materialize the crash state by writing files directly, drive `apply_pseudo`, assert the converged disk state + return dict. RED-for-the-right-reason is provable by running the new resume tests against the un-restructured branch first. Walk-level convergence via `lazy-state.py --test`.

**Integration Notes for Next Phase:** The `resumed` result key is new and additive (absent-callers unaffected; JSON-dumpable). Phase 2 documents the sequence-resume contract in prose.

---

### Phase 2: Document the sequence-resume contract

**Scope:** Record the inverse of the receipt-gate invariant — "a receipt with a non-terminal Status is a resumable partial completion, repaired by re-running `__mark_complete__`/`__mark_fixed__`" — in `user/scripts/CLAUDE.md`'s high-signal invariants (the contract doc for this directory). The `docs/features/CLAUDE.md` receipt-gate paragraph edit named in SPEC Fix Scope item 5 is OUT of this wave's file-ownership scope (reported as a follow-up, not edited here).

**TDD:** no (prose contract note; the gate is the existing `doc-drift-lint.py`, which covers the script TABLE — unchanged here — not this prose).

**Status:** Complete

**Deliverables:**
- [x] `user/scripts/CLAUDE.md`: add a short high-signal invariant noting the sequence-resume contract on the `__mark_complete__`/`__mark_fixed__` branch (receipt-present + any missing post-condition ⇒ RESUME the idempotent tail, not noop).
- [x] `docs/features/CLAUDE.md` inverse-rule edit reported as a needed follow-up (not in this wave's touch scope).

**Minimum Verifiable Behavior:** `python user/scripts/doc-drift-lint.py --repo-root .` exits 0 (the script table is unchanged; the added prose is out of the linter's structured-claim scope).

**Runtime Verification** *(checked by the doc-drift linter — no app runtime):*
- [x] <!-- verification-only --> `doc-drift-lint.py --repo-root .` exit 0 after the prose note (`doc-drift-lint: 5 checks, 0 drift findings, 2 exempted divergences`).

**MCP Integration Test Assertions:** N/A — documentation phase, no runtime-observable behavior.

**Prerequisites:**
- Phase 1: the resume behavior the note describes must be landed.

**Files likely modified:**
- `user/scripts/CLAUDE.md` — high-signal invariant note.

**Testing Strategy:** Run `doc-drift-lint.py --repo-root .`; confirm exit 0.

**Integration Notes for Next Phase:** None — final phase.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to `Fixed`, writes the `FIXED.md` receipt, and archives the bug once both phases' verification passes. This is NOT a checkbox in either phase.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
