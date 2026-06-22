# Implementation Phases — `--ensure-runtime` Legacy-Mode Optimistic READY Verdict

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP dev runtime (the `--ensure-runtime` subcommand targets AlgoBooth's runtime, not this repo's). The deliverables are pure-Python state-script logic over INJECTED probe/restart callables plus SKILL.md prose; the entire surface is structurally outside MCP reach (build/script-tooling class per `docs/features/mcp-testing/SPEC.md`). Validation is the hermetic `test_lazy_core.py` + the `lazy-state.py --test` / `bug-state.py --test` smoke baselines — no live runtime, no MCP server.

## Validated Assumptions

All load-bearing assumptions are **code-provable** (Runtime Assumption Validation Gate skip reason): the legacy-mode control flow is pure Python over injected `probe`/`restart`/`stale_check` callables — the test harness injects them, so the re-probe code, the state-mapping, and the routing are fully determinable from source and exercised hermetically without any live runtime, network, or clock. No runtime-coupled assumption exists. The **MCP tool-existence audit no-ops**: claude-config declares no `.claude/skill-config/mcp-tool-catalog.md`, so there is no MCP tool surface to predetermine. The **SPEC-example capability audit** confirmed the SPEC's code snippets consume only symbols that exist and are reachable today — `_LEGACY_STATUS_TO_STATE` (`lazy_core.py:6513`), `_classify_compile_state` (`:6432`), `_route_non_serving` (the M4-local closure `:6949`), `_runtime_verdict` (`:6836`), `_mcp_tool_in_payload` (`:6480`) — no rejected/`unimplemented!`/`todo!` path among them.

## Touchpoint Audit (verified against the codebase)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `ensure_runtime` legacy branch (`:6810-6833`); `_LEGACY_STATUS_TO_STATE` (`:6513`); `_classify_compile_state` (`:6432`); `_route_non_serving` (M4-local closure `:6949`); `_recover_runtime`; `_runtime_verdict` (`:6836`); `_default_frontend_probe`; `_mcp_tool_in_payload` (`:6480`) | refactor | **Root cause.** In the legacy branch's `if code != 200:` arm, the post-`restart()` re-probe `code` must drive `state`/`status` instead of the unconditional `status = "booted"`. REUSE the M4 honest-routing shape: classify the re-probe via `_classify_compile_state(code, frontend_up)` and route a non-serving result through the SAME bounded-recovery/patient-wait helpers the M4 path uses, so a still-dead re-probe yields `DEAD`→recovery→(READY-on-200 \| BLOCKED), never `READY` with a non-200 `health_code`. Do NOT invent a new state map. |
| `user/scripts/lazy-state.py` | yes | `--ensure-runtime` handler (`:9093-9115`) — threads only `live_session_id` from the marker | **no change (deferred)** | SPEC Open Question: binding `read_lock`/`kernel_start_time_fn` on an unbound marker (to engage M4 on a present-but-unbound marker) is DEFERRED — the producer fix makes the verdict honest in BOTH modes, so this handler needs no edit. |
| `user/skills/lazy-batch/SKILL.md` | yes | Step 1d.0 routing block (`:598-619`) — routes on `state` alone; no `health_code` cross-check | edit | **Defense-in-depth.** Add a `state == READY AND health_code == 200` precondition before dispatching `mcp-test`; a `READY` paired with a non-200 `health_code` is treated as not-ready → the orchestrator owns the boot (the path it already documents) before any dispatch. |
| `user/scripts/test_lazy_core.py` | yes | `test_ensure_runtime_down_returns_booted` (`:18511`) only exercises the RECOVERED case (re-probe → 200) | add tests | Add a legacy-down-**still-non-200** fixture asserting a non-READY DEAD-class verdict, and an M4-vs-legacy parity assertion that NEITHER mode ever returns `state: READY` with `health_code != 200`. The existing recovered-case test stays green (re-probe→200 still → READY). |

**No `bug-state.py` parity mirror is owed.** `--ensure-runtime` is feature-pipeline-only (`lazy-state.py` CLI + shared `lazy_core` helper); `bug-state.py` has no `--ensure-runtime` handler and `lazy_parity_audit.py` does not audit it (SPEC Open Question 4, confirmed in `user/scripts/CLAUDE.md`). The fix lives entirely in `lazy_core.ensure_runtime`'s legacy branch + its consumer + tests.

### Phase 1: Kill legacy-mode optimism — derive the verdict from the re-probe code (root cause)

**Scope:** Rewrite `ensure_runtime`'s legacy branch so the post-`restart()` re-probe `code` drives the returned `state`/`status`, eliminating the unconditional `status = "booted"`. A still-dead runtime (re-probe non-200, frontend down) routes through the same bounded-recovery shape the M4 path uses and yields a DEAD-class verdict (recovering to READY only on a healthy re-probe, else BLOCKED); a `compiling` runtime (frontend up) patiently waits; a healthy re-probe (200) keeps today's `booted`→`READY`. The invariant: **the legacy branch never returns `state: READY` with a non-200 `health_code`** — the verdict is honest regardless of mode.

This is the SPEC's Recommended Fix item 1 and Theory 1 (Confirmed root cause).

**Deliverables:**
- [ ] `ensure_runtime` legacy branch (`lazy_core.py:6810-6833`) no longer sets `status = "booted"` unconditionally after the down-path `restart()` + re-probe; the returned `state`/`status` are derived from the actual re-probe `code` (and, where the config carries the `:1420` frontend keys, the two-port `_classify_compile_state` discriminator), reusing the existing M4 honest-routing helpers (`_route_non_serving` / `_recover_runtime` / `_runtime_verdict`) rather than a new hand-rolled map.
- [ ] A re-probe that returns 200 still yields `status: "booted"` / `state: "READY"` (today's recovered behavior preserved — `_LEGACY_STATUS_TO_STATE["booted"] == "READY"`).
- [ ] The `stale` and `ready` legacy arms (`:6817-6824`) keep their current honest behavior (a `ready`/`stale-rebuilt` arm already implies a 200 health code); only the DOWN arm's optimism is removed. (If the `stale-rebuilt` re-probe can also fail, apply the same re-probe-code-derived honesty there — but never weaken the 200 paths.)
- [ ] `mcp_tools_present` is no longer vacuously `true` for a non-serving runtime: when `mcp_tool_name` is empty AND `health_code != 200`, report `false` (SPEC Open Question 3 — resolved in-cycle as a cheap honesty fix; ⚖ policy disclosed in the return). A 200 health code with no configured tool name keeps the vacuous-`true` default (no assertion configured).
- [ ] Tests: a new `test_lazy_core.py` fixture — legacy mode (no marker / `live_session_id=None`), runtime down, re-probe STILL non-200 with frontend down → `state` is a DEAD-class non-READY verdict and `health_code` is the honest non-200; `restart()` was attempted (bounded). RED before the fix: the current code returns `state: "READY"` here.
- [ ] Tests: an M4-vs-legacy parity assertion — for the same down-then-still-down probe sequence, neither the M4 path (with a lock + `live_session_id`) nor the legacy path (no identity) ever returns `state: "READY"` with `health_code != 200`.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_core.py --test` (or `pytest user/scripts/test_lazy_core.py -k ensure_runtime`) passes including the new legacy-down-still-non-200 fixture, which asserts a non-READY verdict with a non-200 `health_code` — i.e. the optimistic `state: READY, health_code: 0` from the SPEC's verified symptom is no longer producible.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this repo. The verdict is unit-asserted hermetically via injected `probe`/`restart` callables; there is no MCP-reachable surface (claude-config has no dev runtime).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — rewrite the legacy down-arm of `ensure_runtime` to derive state from the re-probe code; tighten `mcp_tools_present` for a non-serving runtime.
- `user/scripts/test_lazy_core.py` — add the legacy-down-still-non-200 fixture + the M4-vs-legacy parity assertion.

**Testing Strategy:** Hermetic unit fixtures inject a `probe` callable whose first call returns `(0, None)` and whose post-`restart()` call STILL returns `(0, None)` (down), with `frontend_probe` bound to `lambda: False` (no :1420) — asserting the verdict is DEAD-class non-READY. A second fixture pins the recovered case (re-probe → 200) to READY to prove the 200 path is untouched. A parity fixture runs the same probe sequence through both identity-engaged (M4) and identity-absent (legacy) entry points and asserts the shared "never READY with non-200" invariant. Run the full smoke set per the Coupling Rule: `lazy_core.py --test` (in-file harness), `lazy-state.py --test`, `bug-state.py --test`, and `pytest test_lazy_core.py` — and confirm the byte-pinned baselines in `tests/baselines/` still match (regenerate ONLY via `_normalize_smoke_output` if a fixture line legitimately changed).

**Integration Notes for Next Phase:**
- After this phase the verdict is honest at the SOURCE: `state: READY` now implies `health_code == 200` from the legacy path too. Phase 2's consumer cross-check (`state == READY AND health_code == 200`) therefore becomes belt-and-suspenders rather than the sole guard — but it is still authored, because it also catches any future producer regression and any residual `mcp_tools_present: false`.
- The reused helpers (`_route_non_serving`, `_recover_runtime`) already own the cold-compile patient-wait and the ≤5×backoff bounded recovery; the legacy branch inherits both by routing through them, so a cold compile reached via the legacy (unbound-marker) path now waits patiently exactly as the M4 path does — a free correctness bonus, not a separate deliverable.
- `_ENSURE_RUNTIME_DEFAULT_CONFIG` carries the `:1420` frontend keys by default, so `frontend_probe` auto-binds in production; a repo with no :1420 frontend overrides the key off and every non-serving legacy re-probe classifies `dead` (byte-identical to a bare DEAD route). Keep this default-off discipline.

---

### Phase 2: Consumer health cross-check at Step 1d.0 (defense-in-depth)

**Scope:** Harden the sole consumer — `/lazy-batch` Step 1d.0 — so it does not dispatch an `mcp-test` subagent on a `state: READY` verdict that carries a non-200 `health_code` (or `mcp_tools_present: false`). Add an explicit `state == READY AND health_code == 200` precondition before dispatch; on a miss, the orchestrator owns the cold-compile boot FIRST (the recovery path it already documents at 17:36:15Z in the SPEC's timeline) before any subagent dispatch.

This is the SPEC's Recommended Fix item 2 and Theory 3 (Confirmed amplifier). It is prose-only (a SKILL.md routing clause) — there is no executable consumer to test in this repo; it documents the orchestrator's routing contract.

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md` Step 1d.0 (the `state: READY` bullet at `:611` and the surrounding routing block `:609-619`) gains an explicit `health_code == 200` (and `mcp_tools_present: true`) precondition on the "proceed to dispatch" decision: a `state: READY` paired with a non-200 `health_code` is treated as NOT-ready and routes to the orchestrator-owned boot/recovery path before any `mcp-test` dispatch — never a dispatch against a runtime the verdict itself reports as non-serving.
- [ ] The clause names this as defense-in-depth atop the Phase 1 producer fix (the producer should never emit `READY` + non-200 after Phase 1; this guard catches a future producer regression and the residual `mcp_tools_present: false` case the block already mentions at `:615`).
- [ ] The routing change introduces NO new `blocker_kind` and NO new state — a `READY` + non-200 miss reuses the existing orchestrator-owned `--ensure-runtime` boot path (or surfaces the existing `mcp-runtime-unready` BLOCKED.md if recovery exhausts), exactly as the `DEAD`/`BLOCKED` bullets already do.
- [ ] Re-run `python ~/.claude/scripts/project-skills.py` and `python ~/.claude/scripts/lint-skills.py` so the projected copy of `lazy-batch/SKILL.md` is regenerated and the edit passes the skill lint (no broken injections / embedded-pattern regressions).

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/lint-skills.py` (full: `--check-projected --check-capabilities`) passes against the edited `lazy-batch/SKILL.md`, and the projected `skills-projected/_default/lazy-batch/SKILL.md` regenerates cleanly with the new precondition present — confirmable by grepping the projected output for the `health_code == 200` precondition clause.

**MCP Integration Test Assertions:** N/A — Step 1d.0 is orchestrator routing prose, not runtime-observable app behavior. Its correctness is a documentation/lint property, not an MCP assertion.

**Prerequisites:**
- Phase 1: the producer is honest first, so the cross-check is belt-and-suspenders rather than papering over an optimistic producer. (Phase 2 is independently authorable but is sequenced second so its prose can state "the producer never emits this after Phase 1.")

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — Step 1d.0 routing clause (`:609-619`).
- (regenerated, not hand-edited) `skills-projected/_default/lazy-batch/SKILL.md` via `project-skills.py`.

**Testing Strategy:** This is prose; verification is the skill lint + the projection regen. `lint-skills.py --check-projected --check-capabilities` is the gate (no broken `!cat` injections, no embedded-pattern regressions, projected copy matches). Manually confirm the precondition reads coherently against the existing `state: DEAD`/`HIJACKED`/`BLOCKED` bullets and does not contradict the "route from the FULL probe JSON" completeness rule already in the block.

**Integration Notes for Next Phase:** Terminal phase. After both phases land, the SPEC's three Confirmed theories are all addressed: Theory 1 (root cause) by Phase 1, Theory 3 (consumer amplifier) by Phase 2, and Theory 2 (the unbound-marker trigger) is left intact by design — the Open-Question fixes (threading `--session-id` at `--run-start`; binding `read_lock`/`kernel_start_time_fn`) are DEFERRED per the SPEC because the producer fix makes the verdict honest regardless of whether legacy mode is reached. If a future cycle wants to additionally remove the trigger, that is a separate bug/feature against the run-start wiring (cross-referenced in the SPEC's Open Questions), not a reopening of this one.

---

## Cross-feature Integration Notes

No hard `**Depends on:**` deps (the SPEC carries a `**Related:**` block of sibling bugs/features, not machine-parseable hard deps). The related items are read-only context:
- `ensure-runtime-recovery-starves-cold-compile` (Fixed, archived) — fixed the **M4** two-port discriminator; this bug is the false-READY sibling in the **legacy** path that fix never touched. Phase 1 deliberately REUSES that fix's `_classify_compile_state` / `_route_non_serving` / patient-wait machinery rather than duplicating it.
- `long-build-and-runtime-ownership` — owns the LD3 verdict contract + orchestrator-owned cold-compile takeover that Phase 2's consumer cross-check routes into on a miss.
- `single-slot-marker-ownership-race-disarms-owning-run` — the born-owner-bound vs. bind-on-first-ALLOW marker mechanics that decide whether `live_session_id` is set at Step 1d.0 (the legacy-mode trigger this bug leaves intact by design).
