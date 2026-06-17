# Implementation Phases — Operator checkpoint-resume should reset cycle counters

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress
<!-- Implementation complete (Phases 1-4 landed, 2026-06-17); validation pending. The flip to Fixed + the FIXED.md receipt are owned EXCLUSIVELY by the orchestrator's __mark_fixed__ validation-tail gate — never set here. -->


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
- [x] `lazy_core.restore_checkpoint_counters` (`:8427`): after confirming a usable `counters` dict + active marker, read `checkpoint.get("operator_authorized")`. When **truthy** → return without overwriting `forward_cycles`/`meta_cycles` (the marker keeps its just-written `0/0`); the resume is a fresh authorized budget. When **falsy/absent** → existing behavior (overwrite from `counters`, reset `last_advance_consume_count` to 0).
- [x] Update the helper's docstring to document the two-branch semantics (operator-authorized → fresh budget; automatic pause → monotonic carry-forward), superseding the current "ALWAYS carry forward" prose.
- [x] `lazy-state.py` `--run-start` consume site (`:6210-6226`): inline comment update so the carry-forward block notes it now only fires for non-authorized resumes (no logic change here — the branch lives in the helper per the placement decision).
- [x] Tests — `test_lazy_core.py` fixtures (unit + subprocess e2e):
  - operator-authorized checkpoint → `--run-start` resume resets to `forward_cycles=0`, `meta_cycles=0`.
  - non-authorized checkpoint → `--run-start` resume restores the paused counts (the existing monotonic-carry fixture stays green).
  - pre-fix checkpoint file (no `operator_authorized` field) → restores (backward-compat).
- [x] No `lazy-state.py --test` in-file fixture added → baseline `tests/baselines/lazy-state-test-baseline.txt` unchanged (coverage lives in `test_lazy_core.py`). Confirmed `lazy-state.py --test` stays green.

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` passes `test_operator_authorized_checkpoint_resume_resets_e2e` (after `--run-end --reason checkpoint --operator-authorized` + `--run-start`, marker shows `forward_cycles: 0` / `meta_cycles: 0`); the non-authorized `test_checkpoint_resume_preserves_counters_e2e` still shows the carried counts.

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

**Implementation Notes (2026-06-17):**
- Added the provenance branch in `lazy_core.restore_checkpoint_counters`: after confirming usable `counters` + active marker, `if checkpoint.get("operator_authorized"): return None` (no-op → marker keeps its just-written `0/0`). Falsy/absent falls through to the unchanged carry-forward path.
- Rewrote the helper docstring to the two-class semantics (operator-authorized → fresh budget; automatic/legacy → monotonic carry-forward), superseding the "ALWAYS carry forward" prose. Noted the authorized resume is a NEW authorized run, not a within-run reset (no HARD CONSTRAINT 8 violation).
- Updated the `lazy-state.py` `--run-start` consume-site comment (comment-only; the branch lives in the helper).
- Tests (test-first, RED confirmed before impl): `test_restore_checkpoint_counters_operator_authorized_resets` + `test_restore_checkpoint_counters_legacy_file_carries_forward` (unit) + `test_operator_authorized_checkpoint_resume_resets_e2e` (subprocess). The non-authorized `test_checkpoint_resume_preserves_counters_e2e` regression guard stays GREEN.
- Files modified: `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`, `user/scripts/test_lazy_core.py`. No baseline regenerated (no in-file `--test` fixture added).

---

### Phase 3: Confirm bug-pipeline parity (`bug-state.py` inherits the branch)

**Scope:** Verify the shared-helper change does not regress the bug pipeline and that the provenance branch behaves identically there. No new `bug-state.py` source logic is expected — this phase is a guard, with a fixture added only if the bug pipeline exercises a checkpoint resume path the feature fixtures don't already cover.

**Deliverables:**
- [x] Run `python user/scripts/bug-state.py --test`; confirm green against `tests/baselines/bug-state-test-baseline.txt`. → green (exit 0, baseline unchanged).
- [x] No separate bug-side fixture added: the provenance branch lives entirely in `lazy_core.restore_checkpoint_counters`, which `bug-state.py` inherits by importing `lazy_core`. The helper-level coverage in `test_lazy_core.py` (Phase 2) certifies the shared logic for BOTH pipelines — there is no bug-pipeline-specific checkpoint-resume path the feature fixtures don't already exercise. No `bug-state.py` source edit, no baseline regeneration.
- [x] Run `python user/scripts/lazy_parity_audit.py --repo-root .` → parity holds (exit 0) after the shared-helper edit.

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --test` exits 0 with output matching the committed baseline (no fixture added → baseline unchanged).

**Prerequisites:**
- Phase 2: the `restore_checkpoint_counters` branch must be in place — this phase verifies its bug-side inheritance.

**Files likely modified:**
- `user/scripts/bug-state.py` — only if a bug-side checkpoint fixture is added (likely none).
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerate iff a fixture was added.

**Testing Strategy:** Run the bug-state smoke harness + parity audit. The shared helper guarantees identical branch logic; this phase's job is to prove no regression, not to re-implement the branch.

**Integration Notes for Next Phase:**
- All three state-machine gates (`lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`) plus `lazy_parity_audit.py` must be green before the prose reconciliation in Phase 4 — code is the source of truth; the prose is reconciled to match it, not vice versa.

**Implementation Notes (2026-06-17):**
- Verification-only phase — no source edit. `bug-state.py --test` green (baseline unchanged); `lazy_parity_audit.py --repo-root .` exit 0. The bug pipeline inherits the Phase-2 branch for free via the `lazy_core` import; helper-level coverage in `test_lazy_core.py` certifies both pipelines, so no separate bug-side checkpoint fixture is warranted. Code (Phases 1-3) is verified green and is the source of truth for the Phase-4 prose reconciliation.

---

### Phase 4: Reconcile the SKILL prose (coupled pair) to the two resume semantics

**Scope:** The harness's documented contract currently contradicts the (now-corrected) code. Make `/lazy-batch` Step 1f / Step 5 accurate: a fresh budget on an operator-authorized re-invoke, monotonic carry-forward on an automatic reliability resume. Mirror into `/lazy-batch-cloud` per the coupling rule, and document the cloud operator-pause threading decision.

**Deliverables:**
- [x] `user/skills/lazy-batch/SKILL.md` Step 1f and Step 5: replaced the "previous session's cycle count is gone / does NOT preserve cycle accounting" prose with the accurate two-class statement — operator-authorized checkpoint resume starts fresh `0/0`; automatic reliability pause carries counters forward (monotonic, cannot exceed authorized `max_cycles`). Also refined the Notes "no persistence layer" line (checkpoints DO persist counters across one resume) to the two-class framing.
- [x] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`: mirrored the two-class statement; documented at the unattended-checkpoint arm that cloud checkpoints stay carry-forward (NO `--operator-authorized`) for BOTH triggers (≥2 denials AND operator-pause) — rationale recorded: a cloud checkpoint is an automatic mid-run pause of the same logical run, not a fresh authorized budget. Decision: DEFER threading the flag in cloud (Phase-1 mechanism supports it later if a cloud checkpoint-backed fresh resume is ever wanted). ⚖ scope-class: omitting the flag is the no-behavior-change default (cloud emitted no flag pre-fix either).
- [x] Updated each skill's State Machine Summary with a checkpoint-resume two-class bullet, and added a "Checkpoint-resume counter semantics" row to the cloud "Differences from /lazy-batch" table (cloud-always-carry-forward is the documented divergence).
- [x] Ran `python user/scripts/project-skills.py` → 80 skills, no errors (single repo: claude-config; no separate algobooth checkout — cloud skill is repo-scoped here).
- [x] Ran `python user/scripts/lint-skills.py` and `--check-projected --check-capabilities` → both clean.

**Minimum Verifiable Behavior:** `python user/scripts/lint-skills.py --check-projected --check-capabilities` exits clean after the edits; the resume-semantics prose is mirrored across the pair with the one documented cloud divergence (always carry-forward) tabulated in the Differences table.

**Prerequisites:**
- Phase 2 + Phase 3: the code must be correct and tests green before the prose is reconciled to it — never reconcile prose to unverified code.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — Step 1f, Step 5, State Machine Summary.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — mirrored prose + cloud checkpoint-write decision; State Machine Summary.
- (conditional) cloud `--run-end --reason checkpoint` command line, iff the cloud operator-pause-resets decision is to wire it.

**Testing Strategy:** Skill-lint + projection spot-check (these are prose/skill files, not runtime code). The coupled-pair diff is the manual gate — confirm the only divergence between the two skills' resume-semantics prose is the documented cloud-specific one.

**Integration Notes for Next Phase:**
- This is the terminal implementation phase. When its work lands, the top-level PHASES `**Status:**` moves to `In-progress` (implementation done, validation pending) — the `__mark_fixed__` flip to `Fixed` is owned exclusively by the orchestrator's validation-tail gate, never set here.

**Implementation Notes (2026-06-17):**
- `/lazy-batch` Step 1f + Step 5 + Notes + State Machine Summary now state the two resume classes accurately (operator-authorized → fresh `0/0`; automatic reliability → monotonic carry-forward).
- `/lazy-batch-cloud` mirrored: "Cycle accounting at resume" two-class block, the unattended-checkpoint-arm provenance note (cloud stays carry-forward; flag-threading deferred), State Machine Summary bullet, and a new Differences-table row.
- Cloud operator-pause decision (SPEC Open Question): DEFERRED threading `--operator-authorized` in cloud — a cloud checkpoint is an automatic same-run pause, carry-forward is correct (VERIFIED symptom #3); a cloud fresh budget = a brand-new `/lazy-batch-cloud <N>` with no checkpoint. ⚖ scope-class, no behavior change.
- Gates: `project-skills.py` clean (80 skills, no errors); `lint-skills.py` + `--check-projected --check-capabilities` both clean.
- Files modified: `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.
