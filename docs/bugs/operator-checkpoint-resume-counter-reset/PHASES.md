# Implementation Phases — Operator checkpoint-resume should reset cycle counters

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness state-machine defect in `lazy-state.py`/`lazy_core.py`; verified entirely by the in-file `--test` smoke harnesses + `test_lazy_core.py`. No AlgoBooth app surface, no Tauri/MCP-reachable behavior (per docs/features/mcp-testing/SPEC.md: pure build/script tooling is outside MCP reach).

## Provenance

This bug is a **missing conditional**, not a broken counter (SPEC `## Proven Findings`). The 2026-06-14 "mid-run counter reset" fix made checkpoint counter carry-over **unconditional**, conflating two resume semantics:

- **operator-authorized checkpoint** (deliberate `/lazy-batch <N>` re-invoke) → operator wants a **fresh** `0/0` budget.
- **automatic reliability pause** (cloud ≥2 guard denials, etc.) → monotonic **carry-forward** must be preserved so an auto-resume cannot silently exceed the authorized `max_cycles`.

The discriminator (`args.operator_authorized` at checkpoint-write time) already exists and is reliable — it is simply not persisted into the checkpoint JSON nor consulted at restore. The fix threads it through and branches on it. The SKILL prose (`/lazy-batch` Step 1f / Step 5) already documents the fresh-budget intent and must be reconciled to be accurate per-resume-class.

**Scope-class decisions taken in-cycle (D7 completeness-first):**
- ⚖ policy: provenance-branch placement → inside `restore_checkpoint_counters` (SPEC recommendation; keeps the decision in one helper shared with `bug-state.py`).
- ⚖ policy: cloud operator-pause flag threading → thread the mechanism + document, don't silently drop (Phase 4 carries the cloud reconciliation; the cloud *reliability* pause stays carry-forward — consistent with VERIFIED symptom #3).

**Coupling note:** `restore_checkpoint_counters` / `write_run_checkpoint` live in `lazy_core.py`, shared by `bug-state.py`. The provenance-conditional reset applies to the bug pipeline for free; `bug-state.py --test` must stay green. The SKILL prose reconciliation touches the coupled pair `/lazy-batch` ↔ `/lazy-batch-cloud`.

---

### Phase 1: Persist checkpoint provenance (`operator_authorized` in the checkpoint payload)

**Scope:** Record whether a checkpoint was operator-authorized at write time, so the resume path can later branch on it. This is the producer half of the fix — no behavior changes yet (restore still carries forward unconditionally until Phase 2), so it lands as a safe, isolated additive schema change.

**Deliverables:**
- [x] `lazy_core.write_run_checkpoint`: add an `operator_authorized: bool = False` parameter; persist it as a top-level `operator_authorized` field in the checkpoint dict (default `False` — backward-compatible with pre-fix checkpoint files that lack the field).
- [x] `lazy-state.py` checkpoint-write site (`--run-end --reason checkpoint`, ~`:6369`): pass `bool(args.operator_authorized)` through to `write_run_checkpoint`. `args.operator_authorized` is already in scope (parsed `:6018`, used in the attended stop-gate `:6305`).
- [x] Tests: `test_lazy_core.py` — assert `write_run_checkpoint(..., operator_authorized=True)` writes `operator_authorized: True`; default omitted-arg writes `False`; round-trips through `consume_run_checkpoint`.

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` passes a new assertion that a checkpoint written with `operator_authorized=True` reads back `True`, and a default-arg write reads back `False`.

**Prerequisites:** None (first phase).

**Implementation Notes (2026-06-17):**
- Added `operator_authorized: bool = False` param to `lazy_core.write_run_checkpoint`; persisted as a top-level `operator_authorized` field (coerced via `bool()`), sibling of `counters`/`reason`/`next_route`/`ts`.
- Threaded `operator_authorized=bool(args.operator_authorized)` into the `lazy-state.py` `--run-end --reason checkpoint` write site (`:6369`). `args.operator_authorized` was already parsed and in scope.
- Tests (test-first, confirmed RED before impl): `test_write_run_checkpoint_persists_operator_authorized` (unit round-trip True/default-False) + `test_run_end_checkpoint_threads_operator_authorized` (subprocess: `--operator-authorized` → True, omitted → False).
- Files modified: `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`, `user/scripts/test_lazy_core.py`.
- No behavior change yet — restore still carries forward unconditionally until Phase 2. Default `False` keeps pre-fix checkpoint files falsy.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `write_run_checkpoint` signature + payload (`:8368-8394`).
- `user/scripts/lazy-state.py` — checkpoint-write call site (`:6358-6371`).
- `user/scripts/test_lazy_core.py` — new round-trip assertions.

**Testing Strategy:** Pure unit assertions on the checkpoint dict via the existing hermetic `LAZY_STATE_DIR`-overridden temp-dir pattern in `test_lazy_core.py`. No marker/run-machine interaction needed — Phase 1 only proves the field is persisted and defaults safely.

**Integration Notes for Next Phase:**
- The field name is exactly `operator_authorized` (top-level in the checkpoint dict, sibling of `counters`/`reason`/`next_route`/`ts`) — Phase 2's restore branch reads `checkpoint.get("operator_authorized")`.
- Default `False` is load-bearing: pre-fix checkpoint files (no field) and automatic reliability pauses both fall through to the carry-forward path Phase 2 preserves.

---

### Phase 2: Branch the restore on provenance (operator-authorized → fresh `0/0`)

**Scope:** The consumer half — the actual behavior change. In `restore_checkpoint_counters`, skip the counter carry-forward when the checkpoint was operator-authorized, leaving the marker's by-design `0/0` fresh-budget start. Keep the current carry-forward behavior when the field is falsy/absent (automatic reliability pause; also preserves pre-fix-file backward compatibility).

**Deliverables:**
- [ ] `lazy_core.restore_checkpoint_counters` (`:8427`): after confirming a usable `counters` dict + active marker, read `checkpoint.get("operator_authorized")`. When **truthy** → return without overwriting `forward_cycles`/`meta_cycles` (the marker keeps its just-written `0/0`); the resume is a fresh authorized budget. When **falsy/absent** → existing behavior (overwrite from `counters`, reset `last_advance_consume_count` to 0).
- [ ] Update the helper's docstring to document the two-branch semantics (operator-authorized → fresh budget; automatic pause → monotonic carry-forward), superseding the current "ALWAYS carry forward" prose.
- [ ] `lazy-state.py` `--run-start` consume site (`:6210-6226`): inline comment update so the carry-forward block notes it now only fires for non-authorized resumes (no logic change here — the branch lives in the helper per the placement decision).
- [ ] Tests — `lazy-state.py --test` + `test_lazy_core.py` fixtures:
  - operator-authorized checkpoint → `--run-start` resume resets to `forward_cycles=0`, `meta_cycles=0`.
  - non-authorized checkpoint → `--run-start` resume restores the paused counts (the existing monotonic-carry fixture stays green).
  - pre-fix checkpoint file (no `operator_authorized` field) → restores (backward-compat).
- [ ] Regenerate the byte-pinned baseline `tests/baselines/lazy-state-test-baseline.txt` ONLY if a new fixture changes `--test` output, via the `_normalize_smoke_output` helper (never by hand).

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` passes a new fixture asserting that after a `--run-end --reason checkpoint --operator-authorized` followed by `--run-start`, the marker / echoed output shows `forward_cycles: 0` and `meta_cycles: 0`; the non-authorized fixture still shows the carried counts.

**Prerequisites:**
- Phase 1: the `operator_authorized` field must be persisted in the checkpoint payload for the restore branch to read.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `restore_checkpoint_counters` provenance branch + docstring (`:8427-8495`).
- `user/scripts/lazy-state.py` — `--run-start` consume-site comment (`:6210-6226`); possible new `--test` fixture.
- `user/scripts/test_lazy_core.py` — restore-branch unit fixtures.
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerate iff fixture output changes.

**Testing Strategy:** Hermetic temp-dir fixtures drive a full write-checkpoint → consume → restore cycle under `LAZY_STATE_DIR` override. Both branches (authorized reset, non-authorized carry) plus the legacy-file backward-compat case are asserted. The pre-existing monotonic-carry fixture is the regression guard for the non-authorized path.

**Integration Notes for Next Phase:**
- The branch lives ENTIRELY in `lazy_core.restore_checkpoint_counters` — `bug-state.py` inherits it for free by importing `lazy_core`. Phase 3 only needs to confirm `bug-state.py --test` stays green; no `bug-state.py` source edit is expected.
- "Truthy" check (`if checkpoint.get("operator_authorized"):`) makes both `False` and a missing field take the carry-forward path uniformly.

---

### Phase 3: Confirm bug-pipeline parity (`bug-state.py` inherits the branch)

**Scope:** Verify the shared-helper change does not regress the bug pipeline and that the provenance branch behaves identically there. No new `bug-state.py` source logic is expected — this phase is a guard, with a fixture added only if the bug pipeline exercises a checkpoint resume path the feature fixtures don't already cover.

**Deliverables:**
- [ ] Run `python user/scripts/bug-state.py --test`; confirm green against `tests/baselines/bug-state-test-baseline.txt`.
- [ ] If `bug-state.py` has (or should have) a checkpoint resume fixture, add an operator-authorized-reset assertion mirroring Phase 2's; otherwise record a one-line note in the plan that the bug pipeline shares the feature fixtures' coverage via `lazy_core` and needs no separate fixture.
- [ ] Run `python user/scripts/lazy_parity_audit.py` to confirm the two state machines stay in parity after the shared-helper edit.

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --test` exits 0 with output matching the committed baseline (regenerated through `_normalize_smoke_output` only if a fixture was added).

**Prerequisites:**
- Phase 2: the `restore_checkpoint_counters` branch must be in place — this phase verifies its bug-side inheritance.

**Files likely modified:**
- `user/scripts/bug-state.py` — only if a bug-side checkpoint fixture is added (likely none).
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerate iff a fixture was added.

**Testing Strategy:** Run the bug-state smoke harness + parity audit. The shared helper guarantees identical branch logic; this phase's job is to prove no regression, not to re-implement the branch.

**Integration Notes for Next Phase:**
- All three state-machine gates (`lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`) plus `lazy_parity_audit.py` must be green before the prose reconciliation in Phase 4 — code is the source of truth; the prose is reconciled to match it, not vice versa.

---

### Phase 4: Reconcile the SKILL prose (coupled pair) to the two resume semantics

**Scope:** The harness's documented contract currently contradicts the (now-corrected) code. Make `/lazy-batch` Step 1f / Step 5 accurate: a fresh budget on an operator-authorized re-invoke, monotonic carry-forward on an automatic reliability resume. Mirror into `/lazy-batch-cloud` per the coupling rule, and document the cloud operator-pause threading decision.

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md` Step 1f (~`:827`) and Step 5 (~`:1291`): replace the "previous session's cycle count is gone / does NOT preserve cycle accounting" prose with the accurate two-class statement — operator-authorized checkpoint resume starts fresh `0/0`; automatic reliability pause carries counters forward (monotonic, cannot exceed authorized `max_cycles`).
- [ ] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`: mirror the same two-class statement per the coupled-pair rule; in the cloud checkpoint-write description (~`:989`), document that cloud **reliability** checkpoints stay carry-forward (no `--operator-authorized`), and state the decision for a cloud **operator-pause** checkpoint (whether it passes `--operator-authorized` to reset). If it should reset, thread `--operator-authorized` into the cloud `--run-end --reason checkpoint` command; if deferred, leave a one-line documented note with the rationale. (⚖ scope-class — Phase 1's mechanism already supports either choice; this phase records and, if chosen, wires it.)
- [ ] Update each skill's State Machine Summary / resume-semantics block at the bottom so the dispatch description reflects the two-class behavior (per the coupled-pair contract in the repo CLAUDE.md).
- [ ] Run `python user/scripts/project-skills.py` and spot-check the projected `/lazy-batch` + `/lazy-batch-cloud` output so the prose change resolves cleanly in both `_default/` and the algobooth per-repo projection.
- [ ] Run `python user/scripts/lint-skills.py` (and `--check-projected --check-capabilities`) to confirm no broken injections / drift from the prose edits.

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py --check-projected --check-capabilities` exits clean after the edits, and a manual diff of `/lazy-batch` vs `/lazy-batch-cloud` confirms the resume-semantics prose is mirrored (only the intended cloud-specific divergence differs).

**Prerequisites:**
- Phase 2 + Phase 3: the code must be correct and tests green before the prose is reconciled to it — never reconcile prose to unverified code.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — Step 1f, Step 5, State Machine Summary.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — mirrored prose + cloud checkpoint-write decision; State Machine Summary.
- (conditional) cloud `--run-end --reason checkpoint` command line, iff the cloud operator-pause-resets decision is to wire it.

**Testing Strategy:** Skill-lint + projection spot-check (these are prose/skill files, not runtime code). The coupled-pair diff is the manual gate — confirm the only divergence between the two skills' resume-semantics prose is the documented cloud-specific one.

**Integration Notes for Next Phase:**
- This is the terminal implementation phase. When its work lands, the top-level PHASES `**Status:**` moves to `In-progress` (implementation done, validation pending) — the `__mark_fixed__` flip to `Fixed` is owned exclusively by the orchestrator's validation-tail gate, never set here.
