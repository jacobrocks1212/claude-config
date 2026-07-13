# Implementation Phases — apply-pseudo fixtures not isolated from a live cycle marker

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure state-script test-hermeticity fix, verified via the in-file
`--test` smoke harness run under both a clean state dir and a synthetic genuinely-live cycle
marker. No Tauri/MCP app surface in this repo.

## Validated Assumptions

- The SPEC's Root Cause already proved the ORIGINAL claimed mechanism (`SystemExit` escaping an
  `except Exception`) is FALSE at HEAD — the runner already uses `except SystemExit as exc:` at
  every in-process call site that can raise it. The only REAL residual finding is the missing
  `LAZY_STATE_DIR` isolation on one (now two — see Implementation Notes) fixture(s).
- Re-confirmed during this pass: `bug-state.py`'s `--test` harness has NO in-process direct call to
  `lazy_core.apply_pseudo` (its only exercise of `--apply-pseudo` is via `subprocess.run`, whose
  child exit code is captured normally) — no bug-state.py change needed, per the SPEC.

---

### Phase 1: Isolate the affected in-process `apply_pseudo` fixture(s) in `lazy-state.py`

**Status:** Complete

**TDD:** yes — reproduced the SPEC's exact hermetic repro (`LAZY_STATE_DIR=<scratch>` seeded with a
fake `lazy-cycle-active.json`) BEFORE the fix (RED: 1 spurious FAIL) and after (GREEN: exit 0).

**Deliverables:**
- [x] `apply-pseudo-provisional-refusal` fixture (`lazy-state.py` ~9818-9855): wrap the
  `lazy_core.apply_pseudo(pp_root, "__mark_complete__", pp_prov_dir)` call in a save/restore
  `LAZY_STATE_DIR` bracket pointed at a private `tempfile.TemporaryDirectory()`, mirroring the
  sibling save/restore pattern used elsewhere in this file (e.g. ~lines 7057/7253). Restored in a
  `finally`.
- [x] **Extension found during close-out verification (not in the original SPEC — a second
  instance of the identical defect class):** the `resume-partial-apply-walk-convergence` fixture
  (`lazy-state.py` ~9917-9923, part of the `mark-complete-partial-apply-noop-unrecoverable` fix
  that landed AFTER this bug's SPEC was authored) makes an equally unisolated in-process
  `lazy_core.apply_pseudo(...)` call. Re-running the SPEC's exact hermetic repro against HEAD
  surfaced this SECOND spurious `FAIL` under a live cycle marker — same root cause, same fix
  shape. Isolated identically (its own private `LAZY_STATE_DIR` bracket around the one
  `apply_pseudo` call).
- [x] No change to `bug-state.py` (verified: no direct in-process `lazy_core.apply_pseudo(` call
  in its `--test` harness).
- [x] `refuse_if_cycle_active`, `apply_pseudo`, and the general `except SystemExit` pattern
  UNCHANGED (both already correct per the SPEC's Root Cause) — this is a pure test-hermeticity fix,
  no production-code path touched.

**Implementation Notes (2026-07-12):** Fixed both now-known instances (the SPEC's originally-named
fixture plus the one discovered during close-out verification). Files: `user/scripts/lazy-state.py`
only.

**Minimum Verifiable Behavior:** `LAZY_STATE_DIR=<scratch dir seeded with a fake
lazy-cycle-active.json> python user/scripts/lazy-state.py --test` exits 0 with `All smoke tests
passed.` (previously: exit 1, `FAILURES:` naming the affected fixture(s)).

**Runtime Verification** *(the hermetic --test harness itself IS the runtime — no separate app
runtime in this repo)*:
- [x] <!-- verification-only --> RED-then-GREEN reproduction: **Verified 2026-07-12.** Before the
  fix, seeding a synthetic live cycle marker (`{"feature_id": "repro-feat", "started_at":
  "2026-07-12T00:00:00Z"}` at `$LAZY_STATE_DIR/lazy-cycle-active.json`) and running
  `python user/scripts/lazy-state.py --test` produced exit 1 with `FAILURES: -
  [resume-partial-apply-walk-convergence] SystemExit: 3` (the SPEC's originally-named fixture had
  already been fixed in the same edit pass, isolating it first). After isolating BOTH fixtures, the
  identical synthetic-live-marker run exits 0, `All smoke tests passed.`
- [x] <!-- verification-only --> Clean-dir regression: `LAZY_STATE_DIR=<empty temp dir> python
  user/scripts/lazy-state.py --test` and `... bug-state.py --test` both still exit 0 (no behavior
  change on the unaffected path). **Verified 2026-07-12.**

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP; the state
script's own `--test` exit code and stdout ARE the observable surface, asserted directly above.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — the two fixture isolation brackets (this pass).

**Testing Strategy:** The SPEC's own hermetic repro commands (Verification commands section),
plus the full `pytest user/scripts/test_lazy_core.py -q` suite for regression confidence (this fix
touches only the `--test` harness, not `lazy_core.py`, so no pytest fixtures are expected to change
behavior — confirmed unaffected).

**Integration Notes for Next Phase:** None — final phase. `__mark_fixed__` is gate-owned in the
normal flow; this close-out pass writes `FIXED.md` directly per the operator's close-out
instruction (provenance: operator-directed-interactive).

**Completion (gate-owned in the normal flow; done directly here per operator instruction):** SPEC.md
/ PHASES.md `**Status:**` flipped to `Fixed`; `FIXED.md` receipt written; bug dir archived.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

None — implemented directly during this close-out pass (a compact, low-severity, single-phase
test-hermeticity fix; no separate planning round warranted).
