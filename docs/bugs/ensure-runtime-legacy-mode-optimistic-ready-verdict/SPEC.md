# `--ensure-runtime` Legacy-Mode Optimistic READY Verdict — Investigation Spec

> `ensure_runtime` returns `state: READY` with `health_code: 0` (both ports down) whenever it falls to legacy mode (unbound run marker), so `/lazy-batch` Step 1d.0 dispatches an `mcp-test` agent against a dead runtime — wasted work the orchestrator then has to recover by taking over the cold compile itself.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-22
**Placement:** docs/bugs/ensure-runtime-legacy-mode-optimistic-ready-verdict
**Related:**
- `docs/bugs/_archive/ensure-runtime-recovery-starves-cold-compile/` — the **inverse** failure (false *BLOCKED* — starved a cold compile by kill-restarting). Fixed the M4 two-port discriminator; this bug is the false-*READY* sibling that lives in the **legacy** path the two-port fix never touched.
- `docs/features/long-build-and-runtime-ownership/` — the LD3 verdict contract + orchestrator-owned cold-compile takeover that the orchestrator fell back to *after* the wasted dispatch.
- `docs/bugs/single-slot-marker-ownership-race-disarms-owning-run/` — the "born owner-bound vs. bind-on-first-ALLOW" marker mechanics that decide whether `live_session_id` is set at Step 1d.0 (the legacy-mode trigger).

---

## Verified Symptoms

1. **[VERIFIED — session log `966720e4`, 17:33:10Z]** `python3 lazy-state.py --ensure-runtime --repo-root "C:\Users\Jacob\repos\AlgoBooth"` returned, verbatim:
   ```json
   { "status": "booted", "state": "READY", "ownership_verified": false,
     "mcp_tools_present": true, "health_code": 0, "terminal_blocker": null }
   ```
   `state: READY` paired with `health_code: 0` is the optimistic verdict. `ownership_verified: false` is the legacy-mode fingerprint (M4 mode sets it `true` on a verified owner and never pairs READY with a non-200 health code).
2. **[VERIFIED — same session]** The orchestrator dispatched the `mcp-test` Sonnet subagent at 17:33:38Z (28s after the optimistic verdict), trusting `state: READY`.
3. **[VERIFIED — subagent `agent-aaf244177cc69a39e`]** The dispatched agent probed `:3333` (`Test-NetConnection` → False, `curl /health` → no response), spent ~4 min, and returned the `NEEDS_RUNTIME` signal — pure wasted work against a dead runtime.
4. **[VERIFIED — orchestrator narration, 17:36:15Z]** "The `--ensure-runtime` verdict was optimistic — both ports were actually down (`health_code: 0`). I've booted the runtime myself (orchestrator-owned). Now waiting on the cold compile to serve `:3333`." The orchestrator-owned takeover + re-dispatch landed at 17:41:48Z.
5. **[VERIFIED — code]** `mcp_tools_present: true` is *also* vacuously misleading: `_mcp_tool_in_payload(payload, "")` returns `True` for the empty default `mcp_tool_name`, so it asserts nothing about a runtime with `health_code: 0`.

## Reproduction Steps

1. Start a `/lazy-batch N` run on AlgoBooth (workstation) where the **first forward cycle's** `sub_skill` is `mcp-test` (the queue head is past planning, awaiting MCP validation), with the dev runtime down.
2. Step 0.55 writes the run marker via `--run-start` **without** `--session-id` → marker born `session_id: None` (bind-pending; binds only on the first dispatch's guard-ALLOW).
3. Step 1d.0 runs `--ensure-runtime` **before** the first dispatch, so the marker is still unbound → handler resolves `live_session_id = None` → `ensure_runtime` runs **legacy mode**.
4. Runtime is down (`probe()` → `code 0`); legacy mode fires `restart()` and re-probes; the cold Rust compile has not finished, so the re-probe is still `code 0`.

**Expected:** the verdict reflects reality — not-serving ⇒ `state ∈ {DEAD, BLOCKED}` (or the orchestrator owns the cold compile and polls to health 200) **before** any `mcp-test` agent is dispatched.
**Actual:** legacy mode unconditionally sets `status = "booted"` → `state: READY` with `health_code: 0`; Step 1d.0 routes on `state` alone and dispatches the agent against a dead runtime.
**Consistency:** Deterministic whenever legacy mode is reached with the runtime not yet serving (first-cycle `mcp-test` with an unbound marker and a cold/dead runtime).

## Evidence Collected

### Source Code

**`user/scripts/lazy_core.py:6810-6833` — the optimistic legacy path (root cause):**
```python
# ---- Legacy mode: pre-M4 boot/stale/ready flow ---------------------------
code, payload = probe()
if code != 200:
    # Runtime DOWN → boot it.
    restart()
    code, payload = probe()
    status = "booted"            # ← UNCONDITIONAL, ignores the re-probe code
elif stale_check():
    ...
return {
    "status": status,
    "state": _LEGACY_STATUS_TO_STATE.get(status, "READY"),  # "booted" → "READY"
    "ownership_verified": False,
    "mcp_tools_present": _mcp_tool_in_payload(payload, tool_name),  # vacuously True
    "health_code": code,         # ← carries the honest 0, but state already lies
    "terminal_blocker": None,
}
```
`status = "booted"` is set regardless of whether the post-`restart()` re-probe reached 200. `_LEGACY_STATUS_TO_STATE["booted"] == "READY"` (`lazy_core.py:6513-6517`). So a dead runtime yields `state: READY, health_code: 0`. (M4 mode at `:6946-7057` correctly routes a non-200 code through `_route_non_serving` → compiling-wait / bounded recovery → READY-only-on-200 or BLOCKED — it has no optimistic path.)

**`user/scripts/lazy_core.py:6772-6779` — the mode selector:**
```python
identity_engaged = (
    live_session_id is not None
    or read_lock is not None
    or kernel_start_time_fn is not None
)
```
**`user/scripts/lazy-state.py:~9093-9112` — the handler only threads `live_session_id` (from the marker's `session_id`), never `read_lock`/`kernel_start_time_fn`:**
```python
live_session_id = None
_marker = lazy_core.read_run_marker()
if isinstance(_marker, dict):
    live_session_id = _marker.get("session_id")   # None when marker is bind-pending
result = lazy_core.ensure_runtime(Path(args.repo_root), live_session_id=live_session_id)
```
So an **unbound marker** (`session_id: None`) collapses all three identity signals to falsy ⇒ legacy mode.

**`user/skills/lazy-batch/SKILL.md:318-320` — `--run-start` does not thread `--session-id`:**
```bash
python3 ~/.claude/scripts/lazy-state.py \
  --run-start --max-cycles {max_cycles} \
  --repo-root {cwd}
```
`SKILL.md:331`: "`session_id` (bound on first hook firing)" — confirming the marker is born unbound and binds later, so Step 1d.0 on a first-cycle `mcp-test` sees `session_id: None`.

**Consumer — `user/skills/lazy-batch/SKILL.md` Step 1d.0:** routes on the verdict's `state` field only (READY/STALE/DEAD→READY proceed to dispatch; HIJACKED/BLOCKED halt). It performs **no `health_code == 200` cross-check**, so an optimistic `state: READY` is trusted unconditionally.

### Runtime Evidence
Session `966720e4-b079-4473-9caa-98fd65623864.jsonl` (+ subagents `agent-aaf244177cc69a39e`, `agent-a4f2833669e03220b`). Timeline:

| Time (Z) | Event |
|----------|-------|
| 17:33:10 | `--ensure-runtime` → `{state: READY, health_code: 0, ownership_verified: false}` |
| 17:33:38 | `mcp-test` agent dispatched on the optimistic verdict |
| 17:34–17:38 | agent probes dead `:3333`, returns `NEEDS_RUNTIME` (wasted work) |
| 17:36:15 | orchestrator recognizes the optimism, boots runtime itself (orchestrator-owned) |
| 17:41:48 | re-dispatch after the runtime actually reaches health 200 |

### Git History
No recent change caused this — it is a **latent legacy-path gap** untouched by the M4/two-port work (`ensure-runtime-recovery-starves-cold-compile`, Fixed 2026-06-21), which only hardened the *M4* path against the inverse (false-BLOCKED) failure.

## Theories

### Theory 1: Legacy mode unconditionally reports READY (root cause)
- **Hypothesis:** `ensure_runtime` legacy mode sets `status = "booted"` → `state: READY` after a `restart()` attempt regardless of the re-probe result, so a still-dead runtime returns `state: READY, health_code: 0`.
- **Supporting evidence:** verbatim verdict (`ownership_verified: false` ⇒ legacy mode); code at `lazy_core.py:6810-6833`.
- **Contradicting evidence:** none.
- **Status:** **Confirmed.**

### Theory 2: Unbound marker forces legacy mode mid-run (the trigger)
- **Hypothesis:** Step 1d.0 runs before the first dispatch binds `session_id`, so `live_session_id` is `None` and the handler — which threads only `live_session_id` — engages legacy mode even though a run marker and a `.runtime.lock.json` exist.
- **Supporting evidence:** `--run-start` omits `--session-id` (`SKILL.md:318-320`); "bound on first hook firing" (`SKILL.md:331`); first cycle is `mcp-test` (`fwd 1/20`); handler passes no `read_lock`/`kernel_start_time_fn`.
- **Contradicting evidence:** none.
- **Status:** **Confirmed.**

### Theory 3: Consumer trusts `state` without a health cross-check (amplifier)
- **Hypothesis:** Step 1d.0 routes on `state` alone; a `health_code == 200` precondition would have caught the optimistic verdict regardless of the producer bug.
- **Supporting evidence:** Step 1d.0 prose routes on `state`; the verdict carries the honest `health_code: 0` that the consumer ignores.
- **Status:** **Confirmed** (a real defense-in-depth gap, independent of the root cause).

## Proven Findings

- The verdict was an **optimistic legacy-mode READY** (`ownership_verified: false`, `state: READY`, `health_code: 0`) — confirmed verbatim from the session log. Theory 1 (root cause) + Theory 2 (trigger) + Theory 3 (consumer amplifier) are all confirmed.
- The bug is **latent and deterministic**, not a regression: legacy mode is reachable any time `live_session_id` is `None` (interactive use, or an unbound marker at a pre-first-dispatch `mcp-test` Step 1d.0).
- Cost is **bounded/self-healing** (orchestrator recovers via owned cold-compile takeover), hence **P2** — but it burns a full cycle + a Sonnet agent + cold-compile latency every time it fires.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Runtime gate (producer) | `user/scripts/lazy_core.py:6810-6833` (`ensure_runtime` legacy path) | **Root cause** — unconditional `booted`→`READY`; must derive `state` from the actual re-probe `code` (non-200 ⇒ DEAD/BLOCKED). |
| Runtime gate (mode selection) | `user/scripts/lazy-state.py` `--ensure-runtime` handler (~9093-9112) | Threads only `live_session_id`; could also bind `read_lock`/`kernel_start_time_fn` so a present-but-unbound marker still engages M4 identity instead of falling to legacy. |
| Consumer (dispatch gate) | `user/skills/lazy-batch/SKILL.md` Step 1d.0 | **Defense-in-depth** — add `state == READY AND health_code == 200` precondition before dispatch; on a miss, orchestrator owns the boot first. |
| Run-start wiring (trigger) | `user/skills/lazy-batch/SKILL.md:318-320` (+ paired `lazy-batch-cloud`, `lazy-bug-batch`) | Marker born unbound; threading `--session-id` (if the orchestrator can obtain it) would remove the legacy-mode trigger. Feasibility uncertain — see Open Questions. |
| Tests | `lazy_core.py --test` smoke harness | Needs a fixture pinning legacy-mode-down ⇒ non-READY, and an M4-vs-legacy parity assertion. |

## Recommended Fix Scope (for `/plan-bug`)

Primary + defense-in-depth, both small and hermetically testable:

1. **Kill legacy-mode optimism (root cause).** In `ensure_runtime`'s legacy branch, after `restart()` + re-probe, derive `state`/`status` from the actual `code`: `code == 200` ⇒ `booted`/`READY`; `code != 200` ⇒ a non-dispatch state (`DEAD`, or `BLOCKED` with a `terminal_blocker`). Never return `READY` with a non-200 `health_code`. This makes the verdict honest **regardless of mode**.
2. **Consumer health cross-check (defense-in-depth).** Step 1d.0 requires `state == READY AND health_code == 200` before dispatching `mcp-test`; otherwise route to the orchestrator-owned cold-compile takeover (the path it already fell back to at 17:36:15Z) **before** any dispatch.

Deliberately **deferred / decide at planning** (see Open Questions): threading `--session-id` at `--run-start`, and binding `read_lock`/`kernel_start_time_fn` in the handler to engage M4 on an unbound marker.

## Open Questions

- Can the orchestrator obtain its own `session_id` at Step 0.55 to thread `--session-id` into `--run-start`? If not, the "remove the trigger" route is infeasible and the producer + consumer fixes carry the load.
- Should the handler bind `read_lock`/`kernel_start_time_fn` so that a **present-but-unbound** marker still engages M4 identity (lock + kernel start_time are verifiable without a `session_id`)? This would shrink the legacy path to genuinely-no-run (interactive) cases only — but interactive `--ensure-runtime` would then need an explicit legacy opt-in.
- Should `mcp_tools_present` stop being vacuously `true` when `mcp_tool_name` is empty *and* `health_code != 200` (report `false` for a non-serving runtime)? Cosmetic vs. the routing fix, but it currently misleads.
- Is the fix feature-pipeline-only (`lazy-state.py` + `lazy_core`), or does any `bug-state.py` parity mirror apply? (`--ensure-runtime` is feature-pipeline-only today — confirm no coupled-pair CLI is owed.)
