# Implementation Phases — plan-bug reuses the STEP_INVESTIGATE label

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure state-script routing-label fix, verified via the
in-file `--test` smoke harness (`bug-state.py --test`) and `pytest user/scripts/test_lazy_core.py`.
No Tauri/MCP app surface in this repo.

## Validated Assumptions

- The feature pipeline's existing distinct-step precedent (`lazy-state.py:3158`,
  `current_step="Step 6: plan feature (phases + plan)"`) is the proven pattern to mirror — already
  cited in the SPEC's Root Cause.

## Cross-feature Integration Notes

- **Related:** `docs/bugs/loop-detector-false-positives-probes-and-cross-run-state/` — Residual gap
  A (meta-class consumption) is a CONTRIBUTING but separately-owned factor; not re-scoped here.

---

### Phase 1: Give `plan-bug` its own `current_step` (STEP_PLAN_BUG)

**Status:** Complete

**TDD:** yes — the `concluded-investigation-plan-bug` fixture in `bug-state.py`'s in-file `--test`
harness pins the expected `current_step == STEP_PLAN_BUG` (was RED against the reused
`STEP_INVESTIGATE` label; GREEN after the fix).

**Deliverables:**
- [x] `bug-state.py`: `STEP_PLAN_BUG = "Step 5: plan bug from concluded investigation"` constant
  added; the `Concluded`-no-`PHASES.md` `plan-bug` dispatch (was `bug-state.py:1434`) now uses
  `current_step=STEP_PLAN_BUG` instead of the reused `STEP_INVESTIGATE`. `spec-bug` keeps
  `STEP_INVESTIGATE` unchanged.
- [x] `concluded-investigation-plan-bug` fixture assertion + comment updated to expect
  `STEP_PLAN_BUG`.
- [x] `pipeline_visualizer/curated_stage.py`: `_BUG_STEP_TO_STAGE` explicit entry
  (`"Step 5: plan bug from concluded investigation": "Plan"`) + the `("Step 5:", "Plan")` bug
  prefix rule.
- [x] `tests/baselines/bug-state-test-baseline.txt` regenerated (the
  `concluded-investigation-plan-bug` row now reads `Step 5: plan bug from concluded
  investigation`) via the sanctioned `_normalize_smoke_output` path.

**Implementation Notes:** Landed in commit `879613d1` ("harden(script): give plan-bug a distinct
current_step (STEP_PLAN_BUG)"), authored during the same hardening round that produced this bug's
SPEC (`f74f8213`). This close-out pass verified the fix on disk and green, authored this PHASES.md
(none existed), and flips Status → Fixed + writes `FIXED.md`. No code changed in this pass.

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --test` → `All smoke tests
passed.` (the `concluded-investigation-plan-bug` and `concluded-investigation-guard-still-spec-bug`
fixtures both PASS, proving the Concluded marker is the exclusive trigger and the distinct label
holds).

**Runtime Verification** *(state-script smoke harness — no app runtime in this repo)*:
- [x] <!-- verification-only --> `bug-state.py --test` fixture `concluded-investigation-plan-bug`:
  a Concluded-investigation bug with no `PHASES.md` dispatches `sub_skill=plan-bug` under
  `current_step=STEP_PLAN_BUG` (distinct from `spec-bug`'s `STEP_INVESTIGATE`). **Verified
  2026-07-12** (this close-out pass): `python user/scripts/bug-state.py --test` → `All smoke tests
  passed.` (isolated `LAZY_STATE_DIR`).
- [x] <!-- verification-only --> `concluded-investigation-guard-still-spec-bug` (regression guard):
  an Investigating (not yet Concluded) bug still dispatches `spec-bug` / `STEP_INVESTIGATE` — the
  Concluded marker remains the exclusive trigger. **Verified 2026-07-12** — same run, PASS.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP; the state
script's routing output IS the observable surface, asserted directly by the `--test` fixtures.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/bug-state.py` — `STEP_PLAN_BUG` constant + dispatch site + fixture (landed
  `879613d1`).
- `user/scripts/pipeline_visualizer/curated_stage.py` — stage mapping (landed `879613d1`).
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated row (landed `879613d1`).

**Testing Strategy:** `python user/scripts/bug-state.py --test` (in-file smoke harness) +
`python -m pytest user/scripts/test_lazy_core.py -q` (coupled-pair parity — no bug-state-specific
counter logic lives in `lazy_core.py` for this fix; `update_repeat_counts` itself is untouched by
this bug, only the STEP LABEL passed into it changes).

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate is
orchestrator/gate-owned; this close-out pass writes `FIXED.md` directly per the operator's
close-out instruction (provenance: operator-directed-interactive, since the code fix predates and
is independent of the standard pipeline gate).

**Completion (gate-owned in the normal flow; done directly here per operator instruction):** SPEC.md
/ PHASES.md `**Status:**` flipped to `Fixed`; `FIXED.md` receipt written; bug dir archived.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

None — this PHASES.md was authored retroactively during close-out, after the fix (commit
`879613d1`) had already landed and passed gates.
