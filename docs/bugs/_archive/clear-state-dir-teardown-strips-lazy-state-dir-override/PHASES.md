# Implementation Phases — `_clear_state_dir()` teardown strips the process-level `LAZY_STATE_DIR` override

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a hermetic
test-harness defect verified via `test_lazy_core.py` (pytest) alone.

**Close-out note (2026-07-12):** the Fix Scope was found ALREADY LANDED at HEAD prior to this
close-out pass (`38b1b248 harden(test): _clear_state_dir restores process-launch LAZY_STATE_DIR
override`). This PHASES.md documents the pre-landed state against the SPEC's Fix Scope; no new
code was written in this pass.

---

### Phase 1: Capture-and-restore the process-launch `LAZY_STATE_DIR` value

**Status:** Complete (pre-landed, `38b1b248`)

**Scope:** Capture the process-launch `LAZY_STATE_DIR` value once at module import
(`_ORIGINAL_LAZY_STATE_DIR`); `_clear_state_dir()` restores that value when non-None, else pops —
byte-identical to today when no override is set (every existing hermetic test unaffected).

**Deliverables:**
- [x] `_ORIGINAL_LAZY_STATE_DIR = _os_env.environ.get("LAZY_STATE_DIR")` captured at module import (`user/scripts/test_lazy_core.py:14515` at time of this audit).
- [x] `_clear_state_dir()` restores `_ORIGINAL_LAZY_STATE_DIR` when non-None, else pops exactly as before (`:14518-14531`).
- [x] `_set_state_dir()` unchanged (still an unconditional set to the per-test temp dir) — only the teardown restore behavior changed, per Fix Scope.
- [x] Registered regression test present and green, asserting the restore-not-strip behavior hermetically (save/restore the module global + env around itself).

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k clear_state_dir -q` is green; the full suite (`python -m pytest user/scripts/test_lazy_core.py -q`) is unaffected (byte-identical behavior for every test that never sets a process-level override).

**Runtime Verification:**
- [x] <!-- verification-only --> With a process-level `LAZY_STATE_DIR` override present at import, `_clear_state_dir()` restores that override rather than deleting it, surviving every subsequent test's teardown. **Verified (pre-landed):** the registered restore-not-strip regression test — GREEN.
- [x] <!-- verification-only --> With no process-level override present (the normal CI/local case), `_clear_state_dir()` pops exactly as before — zero behavior change for the overwhelming majority of runs. **Verified (pre-landed):** the full `test_lazy_core.py` suite (1063 tests) passes unchanged.

**MCP Integration Test Assertions:** N/A — test-harness-only fix, no production code path, no app runtime surface.

**Prerequisites:** None (single-phase bug).

**Files likely modified:** `user/scripts/test_lazy_core.py` (pre-landed; no edits made in this pass).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug. Not a checkbox — done out-of-pipeline
this round per `docs/bugs/CLAUDE.md` ("Fixing a bug OUT-OF-PIPELINE").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

Close-out audit (2026-07-12): confirmed landed at HEAD via direct code read
(`user/scripts/test_lazy_core.py:14500-14532`) — `_ORIGINAL_LAZY_STATE_DIR` capture + restore-not-
strip `_clear_state_dir()`, exactly matching the SPEC's Fix Scope. Full suite:
`python -m pytest user/scripts/test_lazy_core.py -q` → 1063 passed.
