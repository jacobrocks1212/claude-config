# Cycle-containment hook allows background sub-subagent dispatch → cycle deadlock — Investigation Spec

> While a lazy cycle-subagent marker is active, `lazy-cycle-containment.sh` allows a cycle
> subagent to dispatch a sub-subagent with `run_in_background: true`. The parent then blocks
> awaiting a child→parent `SendMessage` that can never arrive (backgrounded children reach only
> the main thread), deadlocking the cycle. Observed twice in one `/lazy-bug-batch` run.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-12
**Fixed:** 2026-07-12 (commit `a43808ee`, landed same-evening in-run; receipt: `FIXED.md`)
**Placement:** docs/bugs/cycle-containment-allows-background-subagent-dispatch-deadlock
**Related:** `user/hooks/lazy-cycle-containment.sh` (the enforcement point); `docs/bugs/adhoc-containment-denies-mandated-explore-fanout` (the 2026-07-09 decision that recursive *synchronous* dispatch stays allowed — this fix must not regress it); the cycle-subagent synchronous-await execution contract (currently prose-only in the cycle dispatch model).

---

## Verified Symptom

During a live `/lazy-bug-batch` run (2026-07-11), cycle subagents dispatched on opus spawned
sub-subagents with `run_in_background: true`, then blocked awaiting a child→parent `SendMessage`
that can never be delivered — backgrounded children can only reach the **main** thread, not their
dispatching parent subagent. The cycle deadlocked. Detected twice (cycles 6 and 7 of that run)
via an output-file mtime freeze; each recurrence cost a `TaskStop` + re-dispatch.

The synchronous-await contract (a cycle subagent dispatches sub-agents **synchronously** and
awaits their return) exists only as prose in the cycle-subagent execution model. Nothing
mechanically prevents a background dispatch, so the deadlock is reachable on every cycle.

## Root Cause

**Class: hook-defect.** `lazy-cycle-containment.sh` is the marker-armed / `agent_id`-targeted
PreToolUse containment point for cycle subagents, but its `main()` routes every non-Bash,
non-Skill tool call — including `Agent`/`Task` — straight to `_allow()` (the
`if tool_name != "Bash": _allow()` fall-through). Recursive *synchronous* Agent/Task dispatch is
deliberately allowed (2026-07-09, to preserve mandated read-only Explore fan-outs), but the hook
draws no distinction between a synchronous dispatch (safe) and a **background** dispatch (the
deadlock trigger). The `run_in_background: true` flag on an `Agent`/`Task` tool call from within a
cycle subagent (`agent_id` present) is never inspected.

## Fix Scope

Mechanical hook fix, surgically scoped so the 2026-07-09 synchronous-dispatch allowance is
preserved:

- In `lazy-cycle-containment.sh`'s inline Python `main()`, BEFORE the `if tool_name != "Bash"`
  fall-through, add: when `is_subagent` (agent_id present) AND `tool_name in ("Agent", "Task")`
  AND the `tool_input` carries a truthy `run_in_background` flag → `_deny(...)` with a corrective
  message directing synchronous/foreground dispatch (stable signature `background-dispatch`).
- Foreground (`run_in_background` absent/falsy) Agent/Task dispatch continues to ALLOW
  (regression-guarded — the Explore fan-out path is unaffected).
- Main-thread (`agent_id` absent) background dispatch continues to ALLOW (the main thread can
  receive child messages; the deadlock is subagent-parent-specific).
- Add `test_hooks.py` pipe-tests: subagent background Agent → deny; subagent foreground Agent →
  allow; main-thread background Agent → allow.

Mechanically promotes the prose-only synchronous-await contract to a hook-enforced write-side
guard, making the deadlock unreachable from a contained cycle subagent.
