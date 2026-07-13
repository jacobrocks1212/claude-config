# Implementation Phases — Guard fail-open leaves no breadcrumb

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; these are shell
hooks verified via subprocess **pipe tests** in `user/scripts/test_hooks.py` (the repo's
established hook-verification harness). No `mcp-tool-catalog.md` in this repo, so the
planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **Windows CreateProcess resolves a bare `"bash"` token via `System32` (the WSL launcher)
  regardless of the child env's `PATH`** — confirmed empirically while building the no-python
  pipe tests: `subprocess.run(["bash", ...], env={"PATH": ""})` still found a live `python3`
  (WSL's own, independent PATH), silently defeating the no-python simulation. The fully-resolved
  Git Bash executable (`_BASH_EXE` / `_run_bash`, already the repo's established test helper)
  does NOT have this problem — `PATH=""` there correctly makes `command -v python3` fail. Every
  no-python pipe test in this plan drives hooks via `_run_bash`, never a bare `"bash"` subprocess
  invocation.
- **`incident-scan.py` already tolerates an integer `ts`** (`isinstance(ts, (int, float))`,
  verified by grep) — the pure-bash fallback writer's `date +%s` second-granularity timestamp
  (SPEC D1) needs no downstream change.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. Items 4 (fail-open heartbeat / dead-plane alarm) and 5
(hook-timeout-kill tracing) of the SPEC's Fix Scope are **descoped from this plan** — see the
Decision note in Phase 1.

---

### Phase 1: Pure-bash fallback breadcrumb (all 7 hooks) + fix the dead `$STATE_DIR` bug + sentinel-pair catch-all breadcrumbs

**Scope:** Close SPEC symptoms (a), (b), and (c) — the three CONFIRMED defects. Every
python-bearing hook's no-python branch writes a `hook-error.json` breadcrumb + a
`hook-events.jsonl` line using ONLY bash builtins/printf (no python required, since python being
absent is exactly the failure this must survive). Fix `lazy-cycle-containment.sh`'s dead
`$STATE_DIR` reference (unset in bash scope; the bash-scope var is `$LCC_BASE_DIR`). Give
`block-noncanonical-blocker-write.sh` and `block-sentinel-write-on-stray-branch.sh` the same
`_breadcrumb(exc)`-on-catch-all their siblings (`long-build-ownership-guard.sh`,
`build-queue-enforce.sh`) already have.

**TDD:** yes. New pipe tests for the no-python path (forcing `PATH=""` via `_run_bash`) and the
two sentinel hooks' malformed-JSON catch-all, written and run RED-for-the-right-reason against
the pre-fix hooks first (confirmed manually via ad-hoc subprocess pipes before landing the
pytest legs), then green after the fix.

**Status:** Complete

**Deliverables:**
- [x] `lazy-cycle-containment.sh`, `block-noncanonical-blocker-write.sh`,
      `block-sentinel-write-on-stray-branch.sh`, `long-build-ownership-guard.sh`,
      `build-queue-enforce.sh`, `lazy-dispatch-guard.sh`, `lazy-route-inject.sh`: no-python branch
      writes `hook-error.json` (`{"hook","error","at"}`) + appends one
      `{"ts","kind":"error","hook","repo_root":"","signature":"","detail"}` line to
      `hook-events.jsonl`, both under `${LAZY_STATE_DIR:-$HOME/.claude/state}`, using only
      `date`/`mkdir`/`printf` with `2>/dev/null || true` on every write (breadcrumb failure must
      never turn `exit 0` into a deny or a non-zero exit). Kept as an identical copied block
      across all 7 hooks (interim per SPEC D4 — no shared-hook-lib feature exists in this repo yet).
- [x] `lazy-cycle-containment.sh` no-python breadcrumb targets `$LCC_BASE_DIR` (was the unset
      `$STATE_DIR`, which exists only inside the hook's inline Python body).
- [x] `block-noncanonical-blocker-write.sh` / `block-sentinel-write-on-stray-branch.sh`: add a
      module-level `STATE_DIR` + a `_breadcrumb(err, cwd="")` function (mirroring
      `long-build-ownership-guard.sh`'s shape), and wire it into the top-level
      `except Exception as exc: _breadcrumb(exc); sys.exit(0)` catch-all (was a bare
      `except Exception: sys.exit(0)`).
- [x] `user/scripts/test_hooks.py`: `_no_python_env(state_dir)` helper (empties `PATH`, pins
      `LAZY_STATE_DIR`); `test_all_python_bearing_hooks_breadcrumb_on_no_python` sweeps all 7 hooks
      (exit 0, no deny, breadcrumb + one event, hook field matches); a dedicated regression pin
      `test_containment_no_python_breadcrumb_lands_in_override_dir_not_root`; catch-all tests
      `test_noncanonical_catch_all_writes_breadcrumb_and_event` /
      `test_straybranch_catch_all_writes_breadcrumb_and_event` (malformed JSON → breadcrumb + one
      `kind:error` event, mirroring the existing `test_events_longbuild_error_appends_error_event`
      pattern). Registered in `_TESTS` for the standalone runner.

**Decision — items 4 & 5 of the SPEC's Fix Scope are DESCOPED from this bug's Fixed status:**
- **Item 4 (fail-open heartbeat / dead-plane alarm, SPEC D2 "decide at planning: inject-banner vs
  `--probe` vs both"):** genuinely undecided in the SPEC itself, AND its natural implementation
  surface (`lazy-state.py --probe` / `lazy_inject.py`) is a STATE-lane script change outside this
  fix's HOOKS-lane scope. After Phase 1, symptom (a) — "the entire guard plane is dead with zero
  trace" — no longer holds: `incident-scan.py` already reads both `hook-error.json` and
  `hook-events.jsonl` (confirmed by grep of its `ts` handling), so the corpse this bug was about is
  now discoverable on the next scan. The heartbeat is an *additional* real-time alarm, not required
  to close the SPEC's own verified symptoms. Recommend a follow-up STATE-lane bug/enhancement.
- **Item 5 (hook-timeout-kill tracing, gated on the SPEC's own "UNVERIFIED — flagged" symptom (e)):**
  per SPEC D3, an out-of-scope decision must be "documented as a known limitation, not silently
  dropped" — done in `user/hooks/CLAUDE.md`'s Fail-OPEN section (this phase). Verifying symptom (e)
  would require staging a deliberately slow hook against the live 5s harness timeout, which is
  outside what a pipe-test subprocess can exercise.

Both are recorded as residuals in `FIXED.md`, not as blockers to closing the bug — the SPEC's own
D4 explicitly says "do not let the systemic feature block the instance fixes."

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_hooks.py -q` is fully green
(203 passed, up from 199), and the 4 new tests are RED-for-the-right-reason against the pre-fix
hooks (manually confirmed: the no-python path produced no breadcrumb file at all before the fix;
the two sentinel hooks' catch-all produced no breadcrumb/event on malformed JSON before the fix).

**Runtime Verification** *(checked by the pipe tests — the hooks' runtime IS the subprocess pipe)*:
- [x] <!-- verification-only --> Every one of the 7 python-bearing hooks, run with `PATH=""` via
  the properly-resolved Git Bash executable, exits 0, emits no deny, and leaves both a
  `hook-error.json` breadcrumb (correct `hook` field) and one `kind:error` `hook-events.jsonl`
  line in the `LAZY_STATE_DIR` override dir. **Verified 2026-07-12:**
  `test_all_python_bearing_hooks_breadcrumb_on_no_python` — GREEN.
- [x] <!-- verification-only --> `lazy-cycle-containment.sh`'s no-python breadcrumb lands in the
  `LAZY_STATE_DIR` override dir, not an unset/root path. **Verified 2026-07-12:**
  `test_containment_no_python_breadcrumb_lands_in_override_dir_not_root` — GREEN.
- [x] <!-- verification-only --> A malformed-JSON payload to `block-noncanonical-blocker-write.sh`
  / `block-sentinel-write-on-stray-branch.sh` fails open AND now leaves a breadcrumb + event.
  **Verified 2026-07-12:** `test_noncanonical_catch_all_writes_breadcrumb_and_event`,
  `test_straybranch_catch_all_writes_breadcrumb_and_event` — GREEN. Full suite:
  `python -m pytest user/scripts/test_hooks.py -q` → 203 passed.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP in this repo;
the hooks' runtime observable is the subprocess pipe decision, asserted directly above.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh`, `user/hooks/block-noncanonical-blocker-write.sh`,
  `user/hooks/block-sentinel-write-on-stray-branch.sh`, `user/hooks/long-build-ownership-guard.sh`,
  `user/hooks/build-queue-enforce.sh`, `user/hooks/lazy-dispatch-guard.sh`,
  `user/hooks/lazy-route-inject.sh`
- `user/scripts/test_hooks.py`
- `user/hooks/CLAUDE.md` — documented known-limitation note for item 5 (timeout-kill tracing)

**Testing Strategy:** Pure pipe testing via `_run_bash` (the properly-resolved Git Bash exe, not a
bare `"bash"` token — see Validated Assumptions). RED-for-the-right-reason confirmed via ad-hoc
manual subprocess pipes against the pre-fix hooks before writing the pytest legs.

**Integration Notes for Next Phase:** None — final phase. `FIXED.md` written directly
(`provenance: operator-directed-interactive`), not by the pipeline's `__mark_fixed__` gate — this
bug was fixed via direct operator-directed session work, mirroring
`docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_
