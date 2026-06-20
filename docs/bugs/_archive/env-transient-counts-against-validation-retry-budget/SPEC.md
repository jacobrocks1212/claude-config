# Self-inflicted environment transients (stale named-pipe / runtime not ready) are counted against the feature's validation-retry budget — Investigation Spec

> During a `/lazy-batch` run on AlgoBooth, an orchestrator-caused environment transient — a stale Windows named-pipe handle / zombie node process left behind by a `dev:restart` — prevented the dev sidecar from booting. Because the runtime never came up, every MCP assertion went pending and the failure surfaced as a *validation BLOCKED at retry 5*, inflating the feature's validation-escalation count even though no code was wrong. The validation-retry accounting does not distinguish a self-inflicted environment transient from a genuine code failure.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-06-19
**Fixed:** 2026-06-20
**Fix commit:** 1fc0b3e
**Placement:** docs/bugs/env-transient-counts-against-validation-retry-budget
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` Step 1d.0 (`--ensure-runtime` readiness gate) + `validation_escalation` retry accounting (`lazy_core.py`); `repos/algobooth/.claude/skills/mcp-test/SKILL.md` Step 2/Step 5 (orchestrated runtime-up path); `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` `mcp-test-runtime` variants

<!-- Status lifecycle: Investigating → Concluded (root cause proven; ready for /plan-bug). -->

---

## Verified Symptoms
1. **[OBSERVED in logs]** An orchestrator-caused infra transient was charged to the validation-retry budget as a BLOCKED at retry 5 — session `5d4b6c93` @ `2026-06-17T12:52:40Z`: "7/15 — ENVIRONMENT failure, not code: sidecar never booted ('Failed to create pipe server: Access is denied, os error 5')… This BLOCKED (retry 5) is a transient infra failure I caused — my `dev:restart` left a stale Windows named-pipe handle."
2. **[OBSERVED in logs]** A surviving zombie node process held the named pipe across kill attempts — session `5d4b6c93` @ `2026-06-17T12:58:52`: "One node process (8680) survived both `dev:kill`s… A zombie sidecar holding the named pipe would explain the recurring 'Access denied.'".

## Reproduction Steps
1. A `/lazy-batch` workstation run reaches a Step-9 `/mcp-test` cycle for a feature (`sub_skill == "mcp-test"`).
2. The orchestrator's Step 1d.0 runs `lazy-state.py --ensure-runtime`. A prior `dev:restart` left a **zombie node process holding the Windows named pipe**; the freshly-restarted sidecar cannot bind it (`Failed to create pipe server: Access is denied, os error 5`).
3. The HTTP server boots independently of the sidecar pipe, so `GET /health` still returns **200**. `--ensure-runtime` returns `status: ready|booted` with `health_code: 200` and (optionally) `mcp_tools_present: true` — **it never probes `get_sidecar_status` / `is_connected`**, so the pipe-dead state is invisible to the gate. The orchestrator dispatches the mcp-test cycle against a runtime that is HTTP-healthy but MCP-functionally dead.
4. The cycle runs the `mcp-test-runtime` **runtime-up** prompt variant. Its sidecar readiness check (or the engine's Gate-1 pre-flight) finds the sidecar unreachable → every assertion goes pending / the engine emits a non-passing classification.
5. In the runtime-up variant there is **no `NEEDS_RUNTIME` escape hatch** (that exists only in the `no-runtime` variant), so the cycle's only enumerated non-pass terminal is `BLOCKED.md` with `blocker_kind: mcp-validation`, carrying the running `retry_count` (here 5).

**Expected:** A self-inflicted env transient (sidecar pipe held / runtime not MCP-ready) is caught BEFORE dispatch (or surfaced as a runtime-readiness condition mid-cycle) and is NOT charged to the feature's `mcp-validation` retry/escalation budget — the orchestrator re-boots cleanly (killing the zombie) and re-dispatches.
**Actual:** The transient passes the HTTP-only readiness gate, the cycle mislabels it as an `mcp-validation` BLOCKED at retry 5, and `validation_escalation` counts it toward the 2+-failure escalation even though no code was wrong.
**Consistency:** Conditional — reproduces when a `dev:restart` orphans a node process that holds the `:3333` sidecar named pipe (Windows-specific handle-lifetime quirk; recurs across kill attempts until the zombie is reaped).

## Evidence Collected

### Source Code
- **`lazy_core.ensure_runtime` (`user/scripts/lazy_core.py:5643-5740`)** — the orchestrator-side readiness gate. Its readiness assertion is exactly two checks: HTTP `/health == 200` (`health_code`) and an OPTIONAL `_mcp_tool_in_payload` (`mcp_tools_present`, skipped when `mcp_tool_name == ""`, which is the default in `_ENSURE_RUNTIME_DEFAULT_CONFIG:5587`). There is **NO `get_sidecar_status` / `is_connected` probe**. A zombie-held pipe leaves `/health` at 200 while the sidecar is dead → the gate returns `ready`/`booted` and the orchestrator dispatches anyway. This is the discriminator gap.
- **`validation_escalation` (`user/scripts/lazy_core.py:322-354`)** — counts a BLOCKED toward escalation iff `blocker_kind == "mcp-validation"` AND `retry_count >= 2`. The predicate is correct; the defect is that an env-transient is REACHING it wearing the `mcp-validation` label. Note the harness ALREADY has a distinct, escalation-immune `blocker_kind: mcp-runtime-unready` (used at lazy-batch Step 1d.0 when `--ensure-runtime` itself fails — `lazy-batch/SKILL.md:581`); the env-transient simply never routes through it because the HTTP gate passes.
- **`mcp-test-runtime` prompt variants (`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md:257-288`)** — the **runtime-up** variant (line 264) tells the cycle to "start at the Step 4 readiness check (session-events / **sidecar** / smoke test)", so the cycle IS expected to verify the sidecar. But the `NEEDS_RUNTIME` escape (line 286) lives ONLY in the **no-runtime** variant (gated by a plan-declared `**MCP runtime:** not-required`). The runtime-up cycle that finds the sidecar dead has no runtime-readiness terminal — its only enumerated non-pass sentinel is the `mcp-validation` `BLOCKED.md` (lines 230, 246-255).
- **`mcp-test/SKILL.md`** — Step 2 orchestrated path (line 156-163): "If the runtime appears dead mid-cycle, do NOT try to boot it yourself — surface `NEEDS_RUNTIME`." This instruction exists, but it is not reflected as a writable terminal in the runtime-up *prompt variant*, and "appears dead" is HTTP-framed — a HTTP-healthy-but-pipe-dead runtime does not obviously "appear dead" to the cycle, which instead runs the engine and gets a pending/failed verdict it routes to BLOCKED.

### Runtime Evidence (session logs)
- session `5d4b6c93` @ `2026-06-17T12:52:40Z` — "7/15 — ENVIRONMENT failure, not code: sidecar never booted ('Failed to create pipe server: Access is denied, os error 5')… This BLOCKED (retry 5) is a transient infra failure I caused — my `dev:restart` left a stale Windows named-pipe handle." (The cycle itself diagnosed the transient correctly AFTER it had already been charged as retry 5.)
- session `5d4b6c93` @ `2026-06-17T12:58:52` — "One node process (8680) survived both `dev:kill`s… A zombie sidecar holding the named pipe would explain the recurring 'Access denied.'" (`dev:kill` did not reliably reap the pipe-holding node process — the transient is self-perpetuating until the zombie is force-killed.)

### Git History
- No code regression introduced this — the gap is a missing readiness dimension, present since `ensure_runtime` was introduced (unified-pipeline-orchestrator Phase 5, F7 `docs/specs/lazy-validation-readiness/SPEC.md`). Recent commits in this repo are unrelated bug fixes (windows-portability, mark-complete roadmap-strike).

### Related Documentation
- `user/scripts/CLAUDE.md` → "mcp-test model-tier routing" + the `--ensure-runtime` CLI doc — describes the readiness dance (probe /health → stale-binary → dev:restart → curl-until-200 → assert MCP tool present); the sidecar-pipe dimension is absent from that contract, matching the code gap.
- `lazy-batch/SKILL.md:581` — the existing `mcp-runtime-unready` route (the correct, escalation-immune classification the env-transient should land in).

## Theories

### Theory 1: HTTP-only orchestrator readiness gate lets a pipe-dead runtime through (PRIMARY)
- **Hypothesis:** `ensure_runtime` asserts only `/health == 200` (+ optional tool-listing), never the sidecar pipe connection, so a zombie-held named pipe passes the gate and the orchestrator dispatches the mcp-test cycle against an MCP-functionally-dead runtime.
- **Supporting evidence:** `ensure_runtime` body (`:5721-5739`) has no `get_sidecar_status` call; default config has empty `mcp_tool_name` (tool check vacuously true); session log shows `/health`-passing while "sidecar never booted".
- **Contradicting evidence:** None. The standalone mcp-test path DOES check `is_connected: true` (`mcp-test/SKILL.md:186`), confirming the pipe check is the recognized readiness signal — it is simply absent from the orchestrated gate.
- **Status:** Confirmed.

### Theory 2: The runtime-up cycle has no runtime-readiness terminal, so a mid-cycle sidecar-dead state is mislabeled `mcp-validation` (PRIMARY, compounding)
- **Hypothesis:** Even when the cycle's own sidecar check catches the dead pipe, the runtime-up prompt variant gives it no `NEEDS_RUNTIME` / `mcp-runtime-unready` terminal — only `mcp-validation` `BLOCKED.md` — so the env-transient is charged to the validation-retry budget.
- **Supporting evidence:** `NEEDS_RUNTIME` exists only in the `no-runtime` variant (`cycle-base-prompt.md:286`); the runtime-up variant's enumerated non-pass terminals are all `mcp-validation`-flavored (`:230, :246-255`). The session log's BLOCKED carried `retry_count: 5` with `blocker_kind: mcp-validation`.
- **Contradicting evidence:** `mcp-test/SKILL.md:162` says to surface `NEEDS_RUNTIME` if the runtime "appears dead mid-cycle" — but this is not wired into the runtime-up dispatch prompt as a writable terminal, and the HTTP-healthy framing obscures the pipe-dead case.
- **Status:** Confirmed.

### Theory 3: `dev:restart` / `dev:kill` does not reliably reap the pipe-holding node process (CONTRIBUTING)
- **Hypothesis:** The Windows named-pipe handle survives `dev:kill` because a zombie node process (pid 8680) keeps it open, so successive `dev:restart`s keep hitting "Access is denied" — the transient is self-perpetuating until the zombie is force-killed.
- **Supporting evidence:** session `5d4b6c93` @ `12:58:52` — node 8680 survived both `dev:kill`s.
- **Contradicting evidence:** This is the AlgoBooth-side `dev:kill` script's robustness, not the harness accounting per se — but it is WHY the transient recurred enough to reach retry 5 rather than self-clearing on the next boot.
- **Status:** Confirmed as a contributing factor (out of scope for the accounting fix; in scope as a reliability hardening if `dev:kill` lives in a harness-owned repo — see Affected Area).

## Proven Findings

The root cause is a **two-part discriminator gap**: an orchestrator-caused environment transient (a zombie node process holding the `:3333` sidecar named pipe after a `dev:restart`) is invisible to the harness's runtime-readiness checks AND has no escalation-immune terminal once it surfaces mid-cycle, so it is charged to the feature's `mcp-validation` retry/escalation budget.

1. **The orchestrator-side gate is HTTP-only.** `lazy_core.ensure_runtime` (`:5643`) asserts `/health == 200` and (optionally) a tool name in the health payload — it never asserts the sidecar pipe is connected (`get_sidecar_status.is_connected == true`). Because the HTTP server boots independently of the sidecar pipe, a zombie-held pipe passes the gate. The orchestrator dispatches the mcp-test cycle against a runtime that is HTTP-healthy but MCP-functionally dead.
2. **The runtime-up cycle has no runtime-readiness terminal.** The `mcp-test-runtime` runtime-up prompt variant (`cycle-base-prompt.md:257-268`) routes every non-pass outcome to an `mcp-validation`-flavored `BLOCKED.md`; the `NEEDS_RUNTIME` escape exists only in the `no-runtime` variant (`:286`). So even when the cycle's own sidecar check catches the dead pipe, it has nowhere to put the failure except the validation-retry budget.
3. **`validation_escalation` is correct; the LABEL is wrong.** The predicate (`:322`) rightly escalates `blocker_kind: mcp-validation` at `retry_count >= 2`. The harness already owns a distinct escalation-immune class, `mcp-runtime-unready` (`lazy-batch/SKILL.md:581`). The fix is to route env-transients into a runtime-readiness class (caught upstream by an enriched `ensure_runtime`, or surfaced mid-cycle via a runtime-up `NEEDS_RUNTIME`/`mcp-runtime-unready` terminal) — NOT to weaken the escalation predicate.

### Fix scope (for `/plan-bug`)
- **A — Enrich the orchestrator readiness gate (PRIMARY).** Add a sidecar-pipe readiness assertion to `lazy_core.ensure_runtime` (`get_sidecar_status` → `is_connected: true`, parameterized in `_ENSURE_RUNTIME_DEFAULT_CONFIG` like the other AlgoBooth specifics, repo-agnostic default = check skipped). When the pipe is not connected despite `/health == 200`, force a `dev:restart` (the stale-pipe case) and, if it stays disconnected, return a `mcp_tools_present: false`-equivalent so Step 1d.0 writes `blocker_kind: mcp-runtime-unready` (escalation-immune) instead of dispatching. Keep `--test` hermetic via the existing injected-probe pattern.
- **B — Give the runtime-up cycle a runtime-readiness terminal (PRIMARY).** In the `mcp-test-runtime` runtime-up variant (`cycle-base-prompt.md:257-268`), add the `NEEDS_RUNTIME` (or `mcp-runtime-unready` BLOCKED) escape for the "sidecar/pipe dead mid-cycle" case, so a cycle that detects the dead pipe does NOT write an `mcp-validation` BLOCKED. Mirror the wording into `mcp-test/SKILL.md` Step 2/Step 5 (the orchestrated runtime-up path) so the standalone and orchestrated paths agree. COUPLED with `/lazy-batch-cloud`? No — cloud never runs mcp-test (`mcp-test-runtime` sections are `modes=workstation`), so this is workstation-only; verify no cloud divergence is needed.
- **C — (Contributing, optional) Harden `dev:kill` zombie reaping.** If `npm run dev:kill` lives in a harness-owned repo, make it reap the pipe-holding node process (e.g. find-and-kill the process holding `\\.\pipe\...:3333`) so the transient self-clears. NOTE: `dev:kill`/`dev:restart` are AlgoBooth (`package.json`) scripts, NOT in this `claude-config` repo — this leg is likely an AlgoBooth spin-off, not a claude-config change. `/plan-bug` should scope A+B here and spin off C to AlgoBooth if the reaping fix is wanted.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Orchestrator readiness gate | `user/scripts/lazy_core.py` (`ensure_runtime` :5643-5740, `_ENSURE_RUNTIME_DEFAULT_CONFIG` :5587) | PRIMARY — add sidecar-pipe (`is_connected`) readiness dimension; route a pipe-dead-but-HTTP-healthy runtime to `mcp-runtime-unready`, not a dispatch. |
| mcp-test cycle prompt (runtime-up variant) | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (`mcp-test-runtime` :257-288, `skill-mcp-test-common` :206-255) | PRIMARY — add a `NEEDS_RUNTIME`/`mcp-runtime-unready` terminal for a mid-cycle sidecar-dead state so it is NOT charged to `mcp-validation` retries. Re-run `project-skills.py` after editing. |
| mcp-test SKILL (orchestrated path) | `repos/algobooth/.claude/skills/mcp-test/SKILL.md` (Step 2 :146-201, Step 5 :289-297) | SECONDARY — mirror the runtime-readiness-vs-validation distinction so standalone and orchestrated agree. |
| Step 1d.0 readiness prose | `user/skills/lazy-batch/SKILL.md` (:540-587) | SECONDARY — document the sidecar-pipe dimension of `--ensure-runtime` and its `mcp-runtime-unready` routing. |
| Escalation accounting | `user/scripts/lazy_core.py` (`validation_escalation` :322-354) | NO CHANGE — the predicate is correct; the fix prevents env-transients from reaching it with the `mcp-validation` label. |
| `dev:kill` / `dev:restart` zombie reaping | AlgoBooth `package.json` scripts (NOT in this repo) | CONTRIBUTING / likely AlgoBooth spin-off — reap the pipe-holding node process so the transient self-clears. |
| State-machine smoke tests | `user/scripts/lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py` | Gate — any `ensure_runtime` change must keep all three green (hermetic injected-probe fixtures + a new pipe-disconnected fixture). |

## Open Questions

- Should the sidecar-pipe readiness check be a HARD gate (always assert `is_connected` when a sidecar is configured) or a soft signal (warn + dispatch)? Recommendation: HARD when an mcp-test cycle is about to run (the only time MCP-functional readiness is load-bearing), parameterized so non-AlgoBooth repos opt in via config — resolve in `/plan-bug`.
- Is `dev:kill` zombie-reaping (leg C) wanted as an AlgoBooth spin-off, or is the upstream A+B gate sufficient (catch + re-boot until clean, accepting one extra boot cycle)? Defer to `/plan-bug` / operator; A+B alone fixes the accounting defect without it.
