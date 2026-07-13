# Implementation Phases — Cycle-containment hook allows background sub-subagent dispatch → cycle deadlock

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this fix is a shell
hook change verified via subprocess **pipe tests** in `user/scripts/test_hooks.py` (the repo's
established hook-verification harness).

## Validated Assumptions

- **The fix was already landed** (commit `a43808ee`, 2026-07-12) by the HOOKS-lane operator during
  the same live `/lazy-bug-batch` run that observed the deadlock (SPEC "Verified Symptom" cites
  the run directly). This PHASES.md is authored **retroactively** as the receipt this bug's
  investigation-spec-to-fix lifecycle was missing; no new code changes in this pass — confirmed by
  reading the current `user/hooks/lazy-cycle-containment.sh` and `user/scripts/test_hooks.py`
  against the SPEC's Fix Scope and finding every deliverable already present and green.

---

### Phase 1: Deny background Agent/Task dispatch from a contained cycle subagent

**Status:** Complete (landed pre-existing, commit `a43808ee`)

**Scope:** Per the SPEC's Fix Scope — in `lazy-cycle-containment.sh`'s inline Python `main()`,
before the `tool_name != "Bash"` fall-through that allows every non-Bash/non-Skill tool call, add a
check: when `is_subagent` (agent_id present) AND `tool_name in ("Agent", "Task")` AND `tool_input`
carries a truthy `run_in_background` → deny with a corrective message (stable signature
`background-dispatch`). Foreground dispatch and main-thread background dispatch stay allowed.

**TDD:** yes (already applied at landing time — commit message cites the new pipe-tests were
authored alongside the guard).

**Deliverables:**
- [x] `_is_truthy_background(val)` helper (`user/hooks/lazy-cycle-containment.sh:443`) — recognizes
  `True` and the JSON-string forms `"true"`/`"1"` (case-insensitive), everything else falsy.
- [x] Deny branch (`user/hooks/lazy-cycle-containment.sh:571-572`, inside the subagent Agent/Task
  handling ahead of the 2026-07-09 foreground-allow carve-out): `if _is_truthy_background(ti.get("run_in_background")): _deny(BACKGROUND_CORRECTIVE, "background-dispatch")`.
- [x] `BACKGROUND_CORRECTIVE` reason text (`:187-199`) names the deadlock mechanism and directs
  re-dispatch WITHOUT `run_in_background`.
- [x] Foreground (`run_in_background` absent/falsy) subagent Agent/Task dispatch continues to
  ALLOW — regression-guarded so the 2026-07-09 Explore-fan-out allowance
  (`adhoc-containment-denies-mandated-explore-fanout`) is not re-broken.
- [x] Main-thread (`agent_id` absent) background dispatch continues to ALLOW — the deny keys on
  `agent_id`, not on the background flag alone (the main thread can receive child messages; the
  deadlock is subagent-parent-specific).
- [x] `test_hooks.py` pipe-tests: `test_containment_denies_background_subagent_dispatch` (deny),
  `test_containment_allows_foreground_subagent_dispatch` (allow, regression guard for the
  2026-07-09 carve-out), `test_containment_allows_main_thread_background_dispatch` (allow).

**Implementation Notes (retroactive receipt, 2026-07-12/13):** Verified on disk against the SPEC's
Fix Scope line-by-line — every deliverable present at the cited line numbers, byte-identical to
the SPEC's described mechanism. Re-ran the three named tests in isolation
(`python -m pytest user/scripts/test_hooks.py -k "background_subagent or foreground_subagent or main_thread_background" -q`
→ **3 passed**) and the full suite (`python -m pytest user/scripts/test_hooks.py -q` →
**217 passed**). No code changed in this pass — this phase's Status reflects the pre-existing
landed state, not new work.

**Minimum Verifiable Behavior:** A subagent (`agent_id` present) Agent/Task dispatch with
`run_in_background: true` piped through `lazy-cycle-containment.sh` while a cycle marker is present
yields `permissionDecision: deny` with signature `background-dispatch`; the same dispatch with
`run_in_background` absent/false yields allow; the same dispatch from the main thread (`agent_id`
absent) with `run_in_background: true` yields allow.

**Runtime Verification** *(checked by the pipe tests — the hook's runtime IS the subprocess pipe):*
- [x] <!-- verification-only --> Subagent + background → deny. **Verified:**
  `test_containment_denies_background_subagent_dispatch` GREEN.
- [x] <!-- verification-only --> Subagent + foreground → allow (regression guard). **Verified:**
  `test_containment_allows_foreground_subagent_dispatch` GREEN.
- [x] <!-- verification-only --> Main-thread + background → allow. **Verified:**
  `test_containment_allows_main_thread_background_dispatch` GREEN.

**MCP Integration Test Assertions:** N/A — no app runtime surface; the hook's runtime observable is
the subprocess pipe decision, asserted directly by the Phase-1 pipe tests above.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/hooks/lazy-cycle-containment.sh` — deny branch + helper (verified present:
  `_is_truthy_background` at `:443`, deny call at `:571-572`, corrective text at `:187-199`).
- `user/scripts/test_hooks.py` — 3 pipe-tests (verified present, all green).

**Testing Strategy:** Pure pipe testing — drive the hook as a subprocess with a crafted stdin JSON
payload (agent_id + run_in_background combinations) and assert the parsed decision, matching every
other hook test in this file.

**Integration Notes for Next Phase:** N/A — terminal phase; no downstream phase depends on this
one. The 2026-07-09 Explore-fan-out allowance (recursive synchronous Agent/Task dispatch) remains
intact and regression-guarded by this phase's own tests.
