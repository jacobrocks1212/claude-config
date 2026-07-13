# Implementation Phases — Loop-detector counters advance on probes/denials and leak across runs

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure state-script counter/ledger fix, verified via
`pytest user/scripts/test_lazy_core.py` + both state scripts' in-file `--test` smoke harnesses. No
Tauri/MCP app surface in this repo.

## Validated Assumptions

- Symptoms 1-3 (probe/deny/resolution debounce) are ALREADY FIXED at HEAD per the SPEC's Root
  Cause characterization (F1/F2 consume-debounce, `--repeat-count-peek`, `de39d3a` ordered-advance,
  `14d90bd` resolution-reset) — re-confirmed on disk during planning; this PHASES only implements
  the two REMAINING gaps (A: meta-class consumption, B: cross-run/cross-restart lifetime scoping).
- `forward_cycles`/`meta_cycles` checkpoint ACCOUNTING is explicitly OUT OF SCOPE (D3, resolved) —
  owned by `operator-checkpoint-resume-counter-reset` (Fixed) and the queued
  `adhoc-align-cycle-commit-count-with-budget-population`. Nothing in this PHASES touches those
  counters.

## Cross-feature Integration Notes

- `docs/bugs/plan-bug-reuses-investigate-step-inflates-loop-detector` is a SIBLING bug (separately
  Fixed) whose fix is orthogonal to Residual gap A — no interaction; both were verified
  independently green together (full `test_lazy_core.py` suite, both `--test` harnesses).
- `bug-state.py` shares `update_repeat_counts`, `consumed_emission_count`, `pending_hardening`, etc.
  via `lazy_core.py` — this is a SHARED-HELPER fix (D1/D2/D3 all land in `lazy_core.py`), so no
  bug-state.py-specific code changes are required; the coupled-pair parity audit + both `--test`
  harnesses confirm no bug-pipeline-only call site regresses.

---

### Phase 1: Residual gap A — cycle-class-only consumption oracle (D1: oracle refinement)

**Status:** Complete

**TDD:** yes — new RED-then-GREEN fixtures proving a META-class consume (`hardening`,
`investigation`, …) between two identical same-step/same-tuple probes no longer defeats the F1/F2
debounce, while a genuine CYCLE-class consume still trips it (d8 design constraint preserved).

**Deliverables:**
- [x] `lazy_core.consumed_emission_count(cls: str | None = None)`: optional `cls` filter — when
  given, counts only consumed registry entries whose `class` field equals `cls`. Every OTHER
  existing caller (the forward/meta-cycle watermark machinery in `advance_run_counters`, etc.)
  keeps calling it with no argument — byte-identical unfiltered behavior, unaffected by this fix.
- [x] `update_repeat_counts`'s F1/F2 oracle read (the single `current_consume_count =
  consumed_emission_count(...)` call, marker- and repo-scoped) now passes `cls="cycle"` — a
  mid-step META dispatch consumes a registry nonce but no longer changes the oracle's count, so the
  debounce correctly treats it as "no forward dispatch landed" and HOLDS the streak.
- [x] Fixtures: `test_gap_a_meta_class_consume_does_not_defeat_step_debounce` (step_repeat_count),
  `test_gap_a_meta_class_consume_does_not_defeat_dispatch_tuple_debounce` (repeat_count — same
  shared oracle), `test_gap_a_cycle_class_consume_still_trips_despite_intervening_meta` (negative
  fixture: a genuine cycle-class dispatch still trips even alongside an intervening meta consume —
  the d8 HEAD-blindness / genuine-oscillation-still-trips constraint is untouched).

**Implementation Notes (2026-07-12):** `consumed_emission_count` gained an optional `cls` kwarg
(default `None` = unfiltered, preserving every non-oracle caller's behavior byte-for-byte); the
`update_repeat_counts` oracle call site is the ONLY caller passing `cls="cycle"`. No other call
site (`advance_run_counters`'s watermark logic, the ring-cap-eviction-tolerant forward/meta gate,
etc.) was touched — those are a separate, already-documented non-monotonic-census mechanism
unrelated to this streak debounce. Files: `user/scripts/lazy_core.py`,
`user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** the three new fixtures pass; the full existing debounce battery
(`test_update_repeat_counts_debounce_*`, `test_f1_repeat_count_debounce_*`) is unaffected (all still
use `_record_consume` = cls="cycle", so filtering to cycle-only is byte-identical for them).

**Runtime Verification** *(pytest characterization — no app runtime in this repo)*:
- [x] <!-- verification-only --> A hardening-class consume between two identical same-step probes
  holds `step_repeat_count` at 1. **Verified 2026-07-12:**
  `test_gap_a_meta_class_consume_does_not_defeat_step_debounce` PASS.
- [x] <!-- verification-only --> The same for `repeat_count` (dispatch-tuple). **Verified
  2026-07-12:** `test_gap_a_meta_class_consume_does_not_defeat_dispatch_tuple_debounce` PASS.
- [x] <!-- verification-only --> A genuine cycle-class consume (even alongside an intervening meta
  consume) still trips the counter 1 → 2. **Verified 2026-07-12:**
  `test_gap_a_cycle_class_consume_still_trips_despite_intervening_meta` PASS.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP; the counter
values ARE the observable surface, asserted directly by the pytest fixtures above.

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `consumed_emission_count` cls filter + oracle call site.
- `user/scripts/test_lazy_core.py` — 3 new fixtures + `_TESTS` registration.

---

### Phase 2: Residual gap B (streaks) — run-lifetime scoping of the persisted signature file

**Status:** Complete

**TDD:** yes — new fixtures proving a streak stamped under one run's identity is NOT inherited by a
different run for the SAME repo (the crashed-run-leaks-into-next-run symptom), while a legacy
record with no recorded run identity at all falls through to the pre-existing (non-reset) behavior
— same legacy-tolerance discipline as the `head`/`step_*`/`consume_count` migrations.

**Deliverables:**
- [x] `update_repeat_counts` reads an additional OPTIONAL `run_started_at` key from the persisted
  signature file (same `_MISSING`-sentinel legacy-tolerant pattern as `head`/`consume_count`).
- [x] When a live marker for THIS repo is present (the same repo-scoping the F1/F2 oracle already
  uses) AND the persisted record ALSO carries a recorded `run_started_at` that is DIFFERENT from
  the live marker's `started_at`, the record is treated as belonging to a run that is no longer
  live: `prior_sig_list`/`prior_step_sig_list` are overridden to `None`, so BOTH counters restart at
  a fresh streak (1) exactly like a changed signature — no special-casing needed downstream.
- [x] A record with NO `run_started_at` key at all (predates this fix, or was written with no live
  marker) is deliberately NOT treated as foreign — absence is never proof, matching the
  `consume_count`/`head` precedent elsewhere in this function. This was the RED-discovered
  constraint during implementation: an earlier, stronger draft ("absent identity ⇒ always reset")
  broke the pre-existing `test_update_repeat_counts_debounce_legacy_file_without_consume_key` /
  `test_f1_repeat_count_debounce_legacy_file_without_consume_key` migration-tolerance fixtures —
  reverted to the weaker, PROVABLE-mismatch-only condition.
- [x] The record persists its own `run_started_at` ONLY on a marked probe (mirrors `consume_count`'s
  legacy-tolerant write discipline — the no-marker path stays byte-identical).
- [x] Fixtures: `test_gap_b_cross_run_streak_resets_on_different_run_identity` (the crash-leak
  symptom, fixed), `test_gap_b_same_run_streak_still_accumulates` (regression: the SAME live marker
  across two probes must still accumulate normally),
  `test_gap_b_legacy_record_without_run_identity_is_not_treated_as_foreign` (the legacy-tolerance
  guard).

**Implementation Notes (2026-07-12):** Chose the "stamp + compare" design (SPEC's first option)
over "delete the signature file in `delete_run_marker`" (SPEC's alternative) because stamping is
robust to a genuine CRASH (no `--run-end` ever runs, so a delete-at-run-end hook never fires for
exactly the leaking case) — the comparison happens lazily at the NEXT run's first probe instead of
requiring a clean shutdown. `delete_run_marker` was left unmodified. Files:
`user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** the three new fixtures pass; the full existing streak/debounce
battery is unaffected.

**Runtime Verification** *(pytest characterization — no app runtime in this repo)*:
- [x] <!-- verification-only --> A streak from run A (`started_at=T1`) is NOT inherited by run B
  (`started_at=T2`, same repo) — run B's first probe on the identical tuple sees a fresh streak
  (1/1), not an inherited count. **Verified 2026-07-12:**
  `test_gap_b_cross_run_streak_resets_on_different_run_identity` PASS.
- [x] <!-- verification-only --> Two probes under the SAME live marker still accumulate normally.
  **Verified 2026-07-12:** `test_gap_b_same_run_streak_still_accumulates` PASS.
- [x] <!-- verification-only --> A legacy record with no `run_started_at` key is NOT treated as
  foreign (increments as before). **Verified 2026-07-12:**
  `test_gap_b_legacy_record_without_run_identity_is_not_treated_as_foreign` PASS.
- [x] <!-- verification-only --> Pre-existing legacy-migration fixtures unaffected. **Verified
  2026-07-12:** `test_update_repeat_counts_debounce_legacy_file_without_consume_key` /
  `test_f1_repeat_count_debounce_legacy_file_without_consume_key` both PASS (initially broken by a
  stronger draft of this fix, then fixed by narrowing the reset condition — see Implementation
  Notes).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP.

**Prerequisites:** None (independent of Phase 1's oracle-filter change — both touch
`update_repeat_counts` but different, non-overlapping branches).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `update_repeat_counts` read/compare/persist additions.
- `user/scripts/test_lazy_core.py` — 3 new fixtures + `_TESTS` registration, plus
  `_write_marker_in_at` test helper (writes a marker at an explicit real-ish epoch so two calls
  produce distinct `started_at` identities).

---

### Phase 3: Residual gap B (deny ledger) — run-scoping of the routed hardening debt

**Status:** Complete

**TDD:** yes — new fixtures proving a prior run's unacked denial no longer forces the NEXT run's
`--run-end`/probe-withholding gates, while still being visible informationally and to the
unfiltered/retro total.

**Deliverables:**
- [x] `append_deny_ledger_entry` / `append_friction_ledger_entry` stamp every new entry with
  `run_started_at` (the live run marker's `started_at`, via the existing non-destructive
  `_raw_marker_started_at()` helper — `None` when no marker is live, e.g. a manual/no-marker deny).
- [x] `pending_hardening(*, current_run_only: bool = True)` / `pending_denial_reasons(*,
  current_run_only: bool = True)`: when a live marker exists, count/list only unacked entries whose
  `run_started_at` matches it. When NO live marker exists, both fall back to the UNFILTERED total —
  byte-identical to every existing no-marker caller/test (there is no established run identity to
  scope against). `current_run_only=False` gives the informational/retro total.
- [x] `oldest_unacked_deny(*, current_run_only: bool = True)`: same scoping, so the entry bound into
  the hardening-dispatch command always matches what actually drove `pending_hardening() > 0` for
  THIS run.
- [x] New `prior_run_pending_hardening()` helper — the informational counterpart: count of unacked
  entries whose `run_started_at` is present and differs from the live marker's. Surfaced in BOTH
  `lazy-state.py` and `bug-state.py`'s deny-ledger probe enrichment as
  `state["prior_run_pending_hardening"]` (only when > 0) — a T6 informational line, never blocking
  (never withholds the route, never gates `--run-end`).
- [x] The `--run-end` gate and the `--emit-prompt` probe-withholding logic in BOTH state scripts
  needed NO code change: they already call `pending_hardening()`/`oldest_unacked_deny()` with
  default args at a point where a live marker is present, so the new run-scoping applies
  automatically (D2 — demote-to-informational, per the SPEC's recommended disposition; entries
  remain in the ledger file for retro/incident mining, never hard-cleared).
- [x] Fixtures: `test_deny_ledger_entries_stamped_with_run_identity`,
  `test_pending_hardening_excludes_prior_run_debt` (the symptom-4 fix, end-to-end),
  `test_oldest_unacked_deny_scopes_to_current_run`,
  `test_pending_hardening_no_marker_fallback_stays_unfiltered` (no-marker regression).

**Implementation Notes (2026-07-12):** All existing `pending_hardening()`/`pending_denial_reasons()`
call sites in both state scripts (the `--run-end` gate, the `--emit-prompt` withholding branch, the
probe enrichment) already run with a live marker present, so the new `current_run_only=True`
default applies transparently — zero call-site changes needed beyond adding the new informational
surfacing. `ack_oldest_deny()`/`ack_all_unacked_denies()` (the ACK path) were deliberately left
UNCHANGED — the SPEC's Fix Scope names only the read-side gates (`pending_hardening`,
`pending_denial_reasons`, the withholding/run-end gates), not the ack mechanics; an
operator-authorized `--ack-unhardened` override still clears ALL unacked entries regardless of run
(unchanged, correct — it is a deliberate blanket override). Files: `user/scripts/lazy_core.py`,
`user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** the four new fixtures pass; the full existing deny-ledger/run-end
battery (`test_run_end_refuses_on_unacked_deny`, `test_deny_ledger_write_read_pending`, etc.) is
unaffected — every existing test writes/reads entries under a marker present at BOTH the append and
the check, so the run identity always matches.

**Runtime Verification** *(pytest characterization — no app runtime in this repo)*:
- [x] <!-- verification-only --> A crashed run's leftover unacked denial does not force the next
  run's `pending_hardening()`/`pending_denial_reasons()` mandatory debt, but IS surfaced via
  `prior_run_pending_hardening()` and the unfiltered total. **Verified 2026-07-12:**
  `test_pending_hardening_excludes_prior_run_debt` PASS.
- [x] <!-- verification-only --> `oldest_unacked_deny()` skips a prior-run entry by default.
  **Verified 2026-07-12:** `test_oldest_unacked_deny_scopes_to_current_run` PASS.
- [x] <!-- verification-only --> No-marker fallback stays unfiltered (byte-identical to every
  existing no-marker test). **Verified 2026-07-12:**
  `test_pending_hardening_no_marker_fallback_stays_unfiltered` PASS.
- [x] <!-- verification-only --> Every existing deny-ledger/run-end fixture (subprocess `--run-end`
  refusal/override/ack tests) unaffected. **Verified 2026-07-12:** full
  `pytest user/scripts/test_lazy_core.py -q` → 1040 passed (1030 pre-existing + 10 new fixtures
  across Phases 1-3), 0 failed.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP.

**Prerequisites:** None (independent of Phases 1-2 — different data structure, the deny-ledger
JSONL rather than the OS-temp signature file).

**Files likely modified:**
- `user/scripts/lazy_core.py` — entry stamping, scoped `pending_hardening`/`pending_denial_reasons`/
  `oldest_unacked_deny`, new `prior_run_pending_hardening`.
- `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` — informational
  `prior_run_pending_hardening` surfacing at the existing deny-ledger enrichment block (coupled-pair
  mirror).
- `user/scripts/test_lazy_core.py` — 4 new fixtures + `_TESTS` registration.

---

### Phase 4: Coupled-pair parity + full-suite gate

**Status:** Complete

**TDD:** no (a verification-only gate phase — no new production code).

**Deliverables:**
- [x] `python3 user/scripts/lazy_parity_audit.py --repo-root .` exit 0 (all changes land in the
  SHARED `lazy_core.py`; the two informational-surfacing call sites added to `lazy-state.py` /
  `bug-state.py` are byte-parallel, verified by direct diff of the two edits).
- [x] `python user/scripts/lazy-state.py --test` and `python user/scripts/bug-state.py --test` both
  green (isolated `LAZY_STATE_DIR`).
- [x] `python -m pytest user/scripts/test_lazy_core.py -q` full suite green: 1040 passed (1030
  baseline + 10 new fixtures across Phases 1-3).
- [x] `python user/scripts/doc-drift-lint.py --repo-root .` exit 0.

**Implementation Notes (2026-07-12):** No coupled-pair mirror was needed beyond the informational
surfacing block (item 3 of Phase 3's deliverables) — `update_repeat_counts`,
`consumed_emission_count`, `pending_hardening`, `pending_denial_reasons`, `oldest_unacked_deny`, and
`prior_run_pending_hardening` are ALL shared `lazy_core.py` functions consumed identically by both
state scripts; no bug-state.py-specific call site required a change.

**Minimum Verifiable Behavior:** all four gate commands above exit 0/pass.

**Runtime Verification:** N/A — a gate-only phase; the commands themselves ARE the verification,
run and confirmed in this pass.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phases 1-3 complete.

**Files likely modified:** None (verification-only).

**Integration Notes for Next Phase:** None — final phase. `__mark_fixed__` is gate-owned in the
normal flow; this close-out pass writes `FIXED.md` directly per the operator's close-out
instruction (provenance: operator-directed-interactive).

**Completion (gate-owned in the normal flow; done directly here per operator instruction):** SPEC.md
/ PHASES.md `**Status:**` flipped to `Fixed`; `FIXED.md` receipt written; bug dir archived.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

None — implemented directly during this dispatched close-out session. Honesty note on process:
the fix code and its fixtures were authored together (not strict red-then-green test-first) except
for Phase 2's legacy-tolerance narrowing, which WAS genuinely RED-discovered — an initial stronger
draft of the cross-run reset condition broke two PRE-EXISTING fixtures
(`test_update_repeat_counts_debounce_legacy_file_without_consume_key`,
`test_f1_repeat_count_debounce_legacy_file_without_consume_key`), which drove narrowing the
condition to the provable-mismatch-only form recorded above. Every new fixture was independently
run and confirmed passing against the shipped fix; the full suite (1040 tests) was run clean
before close-out.
