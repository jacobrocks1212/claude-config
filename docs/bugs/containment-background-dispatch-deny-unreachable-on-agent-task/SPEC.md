# Cycle-subagent background Agent/Task deny is dead code — `lazy-cycle-containment.sh` not registered on `Agent|Task`

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-19
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage — this SPEC is the Step-2.5
record for hardening Round 117); Round 17 (2026-07-09 prose fix — the synchronous-await guardrail
in `cycle-base-prompt.md`); Round 28 (2026-07-12 — the mechanical `background-dispatch` deny this
SPEC makes reachable); `docs/bugs/byref-updatedinput-unapplied-on-background-agent-dispatch/` (the
same `run_in_background: true` Agent-dispatch problematic class); `docs/bugs/adhoc-containment-denies-mandated-explore-fanout/`
(the 2026-07-09 decision to ALLOW foreground recursive Agent/Task dispatch).

## Trigger

Harness-hardening dispatch (`trigger_kind: observed-friction`, operator-confirmed RECURRING across
runs) during a live `/lazy-batch` run with `orchestrator-tool-search` in flight. A **planning-fan-out
cycle subagent** (`plan-feature` attempt `a1e131482`; the class also spans `spec-phases`,
`spec-phases-batch`, `write-plan`) dispatched its Explore / Sonnet fan-out with
`run_in_background: true`, then **ended its turn awaiting the children's results via a child→parent
message channel that does not exist**. A dispatched child can only reach `main`/top by name — never
its spawning parent subagent — so the awaited message never arrives and the parent returns
**RESULTLESS mid-cycle** ("still awaiting the other three Explore agents before I finalize"),
producing no PHASES.md/plan and re-returning the same Step-6 tuple (`repeat_count` climbs). It ALSO
defeats orchestrator `SendMessage`-resume ("No transcript found for agent ID"), so recovery costs a
full cold re-dispatch.

Prior corroborating (benign) evidence: a single `subagent-wedge-backstop` timing note on an
`execute-plan` test-agent await — the same await-a-child-message class, one occurrence, not a
separate bug.

## Reconstructed route (divergence point)

The deadlock is SPECIFICALLY **async background sub-subagent dispatch + await-message** from inside
a cycle subagent. This exact failure was already addressed by **two** prior harden rounds:

1. **Round 17 (prose)** added a SYNCHRONOUS-AWAIT guardrail to the WORKSTATION DISPATCH policy in
   `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (dispatch-and-await the Agent
   result; never wait on a message FROM a child; collapse to inline on wedge).
2. **Round 28 (mechanical, commit `a43808e`)** added a **`background-dispatch` deny branch** to
   `user/hooks/lazy-cycle-containment.sh` (lines 812–824): when `is_subagent`
   (`agent_id` present) AND `tool_name in ("Agent","Task")` AND `run_in_background` is truthy →
   `_deny(BACKGROUND_CORRECTIVE, "background-dispatch")`. Foreground dispatch and main-thread
   background dispatch stay allowed.

The friction RECURS despite BOTH. The prose (1) is advisory and was measurably not preventing it.
The mechanical deny (2) **is dead code**: `lazy-cycle-containment.sh` is registered in
`user/settings.json` ONLY under the PreToolUse matchers `Bash|PowerShell` and `Skill` — **NOT
`Agent|Task`**. A PreToolUse hook only runs for its registered tool matchers, so when a cycle
subagent dispatches an `Agent`/`Task` tool call, `lazy-cycle-containment.sh` **is never invoked at
all** — the background-dispatch deny branch can never execute in production. Only
`lazy-dispatch-guard.sh` is registered on `Agent|Task`, and it validates prompt REGISTRATION, not
the `run_in_background` flag (it ALLOWS sub-subagent fan-outs per the 2026-07-09 decision), so the
backgrounded dispatch slips straight through to the deadlock.

**Why the Round-28 regression tests passed anyway:** `test_hooks.py`'s
`test_containment_denies_background_subagent_dispatch` (+ siblings) invoke the containment SHELL
SCRIPT DIRECTLY with a synthetic `Agent` PreToolUse payload, so the Python deny branch executes and
the assertion passes. Nothing in the suite asserted the hook is WIRED to receive `Agent`/`Task`
tool calls via `settings.json` — the classic "green tests over unreachable production code" gap.

## Root cause

`hook-defect` — a **registration gap**. The Round-28 mechanical `background-dispatch` deny lives in
a hook that is not registered for the `Agent`/`Task` tool family, making the deny structurally
unreachable. The design decision (deny background sub-subagent dispatch; allow foreground) was
already made, shipped, corrective-message-authored, and tested at the Python level in Round 28 —
only the `settings.json` matcher registration was missing.

Confirmed evidence:
- `user/settings.json` PreToolUse blocks: `lazy-cycle-containment.sh` under `Bash|PowerShell` and
  `Skill`; `Agent|Task` carries ONLY `lazy-dispatch-guard.sh`.
- `user/hooks/lazy-cycle-containment.sh:819-824` — the `is_subagent and tool_name in ("Agent","Task")`
  background-dispatch deny branch (reachable only if the hook receives Agent/Task calls).
- `lazy-dispatch-guard.sh` proves the `Agent|Task` matcher routes tool calls to a PreToolUse hook —
  so no platform uncertainty: registering the containment hook there makes the deny reachable.

## Fix scope (mechanical)

1. **`user/settings.json`** — add `lazy-cycle-containment.sh` to the `Agent|Task` PreToolUse block
   (alongside `lazy-dispatch-guard.sh`), so the already-written `background-dispatch` deny branch
   fires in production. For a foreground Agent/Task dispatch the hook allows (Explore-fan-out
   allowance preserved); main-thread background dispatch is allowed (agent_id absent); only a
   `run_in_background: true` dispatch from a cycle subagent is denied with the
   `BACKGROUND_CORRECTIVE` redirecting to synchronous dispatch-and-await.
2. **Root `CLAUDE.md` Hooks table** — update the `lazy-cycle-containment.sh` trigger cell to
   `PreToolUse (Bash, PowerShell, Skill, Agent, Task)` (doc-drift-lint compares the trigger cell's
   matcher set against `settings.json`; the two must stay in lockstep).
3. **`user/hooks/lazy-cycle-containment.sh` header comment** — note the Agent|Task registration so
   the background-dispatch trip is documented as live, not dead.
4. **`user/scripts/test_hooks.py`** — add a registration meta-test asserting
   `lazy-cycle-containment.sh` is registered under a PreToolUse matcher covering BOTH `Agent` and
   `Task`, so the dead-code gap can never recur silently (the "make the misbehavior
   self-announcing" durable half — the Round-28 branch tests only proved Python behavior, never
   wiring).
5. **`user/hooks/CLAUDE.md`** — note the new Agent|Task registration for the containment hook.

## Reproduction steps

1. Under a live run with the cycle marker present, a dispatched cycle subagent issues an `Agent`
   tool call with `run_in_background: true`.
2. Before fix: `lazy-cycle-containment.sh` is not invoked (not registered on `Agent|Task`); the
   dispatch proceeds; the parent awaits a child→parent message that never arrives → resultless
   mid-cycle return.
3. After fix: the hook fires, matches the background-dispatch predicate, and denies with the
   corrective — the parent must re-dispatch synchronously (foreground) and await the Agent result
   directly. No deadlock.

## Verification

- `test_hooks.py` new registration meta-test RED before the settings.json edit, GREEN after.
- Existing `test_containment_denies_background_subagent_dispatch` / `_allows_foreground_subagent_dispatch`
  / `_allows_main_thread_background_dispatch` remain GREEN (behavior unchanged; now reachable).
- Full gate battery green (see hardening Round 117).
- `doc-drift-lint.py` clean (CLAUDE.md hooks row ↔ settings.json in lockstep).
