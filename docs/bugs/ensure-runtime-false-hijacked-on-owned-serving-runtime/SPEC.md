# ensure-runtime falsely reports HIJACKED on a self-booted, serving runtime — Investigation Spec

> `lazy-state.py --ensure-runtime` returns the terminal `HIJACKED` fail-safe for a runtime that is provably this run's own (health 200 + MCP tools present), because the runtime lock's recorded `controller_session_id` and the threaded `live_session_id` come from different sources and diverge. The recorded recovery (`dev:kill` + fresh boot) does not cure it — the next cycle re-stamps a divergent identity and re-reports HIJACKED.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-24
**Placement:** docs/bugs/ensure-runtime-false-hijacked-on-owned-serving-runtime
**Related:** `docs/bugs/_archive/single-slot-marker-ownership-race-disarms-owning-run` (foreign session *stamps* the slot — distinct), `docs/bugs/_archive/ensure-runtime-legacy-mode-optimistic-ready-verdict`, `docs/bugs/_archive/ensure-runtime-recovery-starves-cold-compile`, AlgoBooth memory `hijacked-runtime-after-mcp-test-cycle.md`, spun-off `statepush-mirror-readiness-dimension`

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause class identified, fix direction chosen; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

<!-- "Verified" here = confirmed directly from the AlgoBooth session logs the user pointed me at
     (~/.claude/projects/C--Users-Jacob-repos-AlgoBooth, grep HIJACKED) — the logs ARE the evidence
     source for this bug, not user recollection. Severity + fix direction confirmed with the user. -->

1. **[VERIFIED]** Across the 2026-06-23 and 2026-06-24 AlgoBooth `/lazy-batch` runs, `lazy-state.py --ensure-runtime` returns `state: HIJACKED` with `ownership_verified: false` **but** `health_code: 200` **and** `mcp_tools_present: true` — i.e. the runtime is serving *this app's* MCP tools, not a foreign hostile process. — confirmed in session logs `d36dd6ba…`, `bc52885a…`, `29440957…`.
2. **[VERIFIED]** It recurs **every** mcp-test cycle ("runtime HIJACKED **again** (post-cycle ownership divergence)"), and the recorded recovery `dev:kill` + fresh boot does **not** cure it — the orchestrator's own log narration states a reboot re-stamps a divergent controller identity and the next `--ensure-runtime` re-reports HIJACKED. — confirmed in `d36dd6ba…` ("that wouldn't fix the recurrence… it's an ownership-bookkeeping false-positive, not a serving fault").
3. **[VERIFIED]** The orchestrator currently works around it by hand-reasoning ("verify the runtime is genuinely serving, then dispatch against it directly") rather than honoring the terminal HIJACKED → `BLOCKED.md`. The false-positive is therefore absorbed by per-cycle operator/LLM reasoning + wasted kill/cold-compile boots, not a hard pipeline halt. — confirmed across all three logs.
4. **[SUSPECTED]** The genuine-foreign HIJACKED path (a real unowned port-holder) is unaffected and must remain a strict, never-SIGKILL fail-safe (LD3). — not exercised in these runs; preserved by construction in the fix scope.

## Reproduction Steps

1. Run `/lazy-batch` on AlgoBooth (Bash-driven orchestrator — drives via Bash, not the inject hook).
2. Reach the `Step 1d.0` mcp-test runtime gate, which calls `lazy-state.py --ensure-runtime` once per cycle.
3. The runtime is up and serving (the orchestrator booted it this single session): `/health` → 200, MCP tools present.

**Expected:** `--ensure-runtime` returns `READY` (or a soft owned-unverified READY) and the cycle dispatches mcp-test against the live runtime.
**Actual:** Returns terminal `HIJACKED` (`ownership_verified: false`) with `health_code: 200` + `mcp_tools_present: true`; absent the operator workaround this becomes `BLOCKED.md (blocker_kind: mcp-runtime-unready)`.
**Consistency:** Consistent — fires every cycle once the lock/session divergence exists; uncured by the recorded `dev:kill` + reboot recovery.

## Evidence Collected

### Source Code (Subagent E — done inline)

- **HIJACKED decision sites** — `user/scripts/lazy_core.py`:
  - `_classify_runtime` / `_route_non_serving` (≈7449-7536): no lock + `code==200` ⇒ HIJACKED; lock present but `verify_runtime_ownership` false + a **live** lock PID (`kernel_start_time_fn(pid)` not None) ⇒ HIJACKED strict fail-safe (no restart/kill). A dead lock PID ⇒ DEAD (recover).
  - `verify_runtime_ownership` (8483-8514): returns True iff **both** `lock['controller_session_id'] == live_session_id` **and** recorded `start_time == kernel start_time(pid)`. "200 on /health is NOT proof of ownership."
- **Identity-engage gate** — `ensure_runtime` (7158-7165): `identity_engaged = live_session_id is not None or read_lock is not None or kernel_start_time_fn is not None`. Production `--ensure-runtime` threads **only** `live_session_id`, so identity engages (and the M4 HIJACKED path is reachable) **iff the run marker's session is non-null**.
- **Lock writer** — on a recovery re-probe the lock's `controller_session_id` is written from `recover_identity()` (`_await_compile_serving` 7663; `_recover_runtime` 7829), but in the production `--ensure-runtime` call `recover_identity` defaults to **None** (7176), so `ensure_runtime` does not rewrite the lock — the `.runtime.lock.json` `controller_session_id` is written by a *different* code path/session than the marker `session_id` threaded as `live_session_id`. **This source asymmetry is the root-cause class.**
- **Producer of `live_session_id`** — `user/scripts/lazy-state.py` (9285-9322): reads `live_session_id` from `read_run_marker().get("session_id")`, falling back to None.

### Runtime Evidence (Subagent D — session logs)

- `~/.claude/projects/C--Users-Jacob-repos-AlgoBooth/{d36dd6ba…,bc52885a…,29440957…}.jsonl` — repeated `HIJACKED (ownership_verified: false)` with `health_code: 200` + `mcp_tools_present: true`; orchestrator narration explicitly classifies it a "pure ownership-bookkeeping false-positive (null `session_id`)" and notes the reboot recovery does not cure recurrence.

### Git History (Subagent B)

- Recent `lazy_core.py` history is dominated by the ensure-runtime hardening lineage (legacy-mode optimistic verdict, cold-compile starvation, pre-Vite sidecar build, single-slot marker race). This is the **next** ensure-runtime/ownership defect in that lineage; none of the archived bugs covers the *self-booted-serving-but-unverified* false-positive.

### Related Documentation (Subagent C)

- `user/scripts/CLAUDE.md` → `--ensure-runtime` contract: "divergent live owner answering /health ⇒ HIJACKED… HIJACKED is a strict FAIL-SAFE — the foreign process is NEVER SIGKILLed (LD3)." The contract assumes a HIJACKED runtime is *foreign*; this bug is the case where it is *ours* but ownership can't be verified.
- AlgoBooth memory `hijacked-runtime-after-mcp-test-cycle.md` documents the *symptom recovery* (dev:kill + reboot) but the logs prove that recovery does not cure the recurrence — the memory is a workaround, not a fix.

## Theories

### Theory 1: Lock-identity vs threaded-session source asymmetry (root-cause class) — **Likely**
- **Hypothesis:** The runtime lock's `controller_session_id` and the `live_session_id` threaded into `verify_runtime_ownership` are produced by different paths and do not match for a Bash-driven, single-session orchestrator (the inject hook that would bind them is not in the loop). With a live lock PID, the mismatch yields the HIJACKED fail-safe even though the runtime is this run's own and serving.
- **Supporting evidence:** `verify_runtime_ownership` requires session equality; production `--ensure-runtime` never rewrites the lock (`recover_identity=None`); logs show `ownership_verified: false` with 200 + MCP-present, recurring across reboots.
- **Contradicting evidence:** None observed; the genuine-foreign case is simply not what these runs hit.
- **Status:** Likely. **Open verification (which side diverges):** is the marker `session_id` null (⇒ identity should *not* engage, pointing at the legacy path also emitting HIJACKED), or is it bound but ≠ the lock's recorded `controller_session_id`? Resolve by capturing, at a live recurrence: the full `--ensure-runtime` verdict JSON, `.runtime.lock.json` contents, and the run-marker `session_id`.

### Theory 2: Recovery re-stamps a divergent identity (why reboot doesn't cure it) — **Likely**
- **Hypothesis:** `dev:kill` + fresh boot rewrites `.runtime.lock.json` with a controller identity that still doesn't match the threaded session, so the next cycle re-diverges → HIJACKED again.
- **Supporting evidence:** Orchestrator narration states exactly this; recurrence survives reboot every cycle.
- **Status:** Likely; same live-capture confirms it.

## Proven Findings

- The HIJACKED verdict in these runs is a **false positive on a runtime this run is genuinely serving** (`health 200` + `mcp_tools_present true`), not a foreign port-holder — confirmed from logs. The defect is in the **ownership-verifiability** layer (lock-identity vs threaded-session source asymmetry), not in liveness/health.
- The recorded `dev:kill` + reboot recovery does **not** cure recurrence — confirmed from logs.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| M4 ownership classifier | `user/scripts/lazy_core.py` (`_classify_runtime` / `_route_non_serving` ≈7449-7536; `verify_runtime_ownership` 8483-8514; legacy `_route_legacy_non_serving`) | **Primary fix site.** Introduce a *soft owned-unverified READY*: when ownership cannot be verified BUT `health_code==200` AND `mcp_tools_present` AND the lock's recorded PID is the **live serving process** (kernel start_time matches the recorded lock start_time — i.e. only the *session* component diverges, not the process), classify a non-terminal READY (`ownership_verified: false`, proceed) instead of terminal HIJACKED. The **genuine-foreign** HIJACKED (no matching lock PID, or a divergent live PID/start_time) stays the strict never-SIGKILL fail-safe (LD3). |
| ensure-runtime handler | `user/scripts/lazy-state.py` (9285-9322) | Verify whether the marker `session_id` is null vs bound in the Bash-driven loop (determines whether the legacy path also needs the soft-READY guard). |
| Consumer routing | `/lazy-batch` Step 1d.0 prose / `cycle-base-prompt` | Soft owned-unverified READY must route as "proceed to dispatch" — eliminating the per-cycle hand-reasoning workaround and the wasted kill/cold-boot. |
| Tests | `user/scripts/test_lazy_core.py` (+ `lazy-state.py --test`) | Add a hermetic fixture: lock present, `verify_runtime_ownership` false on the *session* component only, live matching PID, probe 200 + MCP present ⇒ soft READY (proceed); a divergent-PID/foreign case ⇒ HIJACKED unchanged. Coupling: `--ensure-runtime` is feature-pipeline-only — no `bug-state.py` mirror owed (confirm against `lazy_parity_audit.py`). |

## Open Questions

- **Which side diverges?** Marker `session_id` null (identity not engaged → legacy path emits HIJACKED) vs bound-but-unequal to the lock's `controller_session_id`. The chosen fix (soft owned-unverified READY keyed on live-PID match + serving) is robust to either answer, but the live capture pins where the guard must live (M4 path only, or M4 + legacy).
- **Lock writer of record.** Which path stamps `.runtime.lock.json`'s `controller_session_id` in the production loop (since `ensure_runtime`'s `recover_identity` is None)? Confirms whether a binding fix (Theory-2 alternative) is even reachable, or whether soft-READY is the only practical lever.
- **Boot-stamp interaction.** Confirm soft-READY does not mask a *genuinely* stale binary (the stale_check / cold-compile paths must still run before the soft-READY verdict).
