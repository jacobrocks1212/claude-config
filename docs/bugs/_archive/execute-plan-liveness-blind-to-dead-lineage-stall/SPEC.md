# Bug: execute-plan-liveness discriminator is blind to a dead-lineage stall (mis-verdicts a wedged cycle as `paused`, stalling the orchestrator forever)

**Status:** Fixed
**Fixed:** 2026-07-20
**Fix commit:** 6d46f295
**Reported:** 2026-07-20
**Pipeline:** claude-config harness (lazy-batch/lazy-bug-batch orchestrator — Gap-2 pause-vs-terminal discriminator)
**Origin:** harden-harness round (observed-friction), item in flight `inspector-track-dashboard` (part-2)
**Root-cause class:** script-defect (primary) + ambiguous-prose (secondary — the genuine-wedge fallback was prose-only, never verdict-routed)

## Symptom (verified — LIVE INCIDENT 2026-07-20, `inspector-track-dashboard` part-2)

The Step 1e.4a pause-vs-terminal discriminator (`lazy-state.py --execute-plan-liveness`, i.e.
`lazy_core.execute_plan_liveness`) classified a stalled/wedged `/execute-plan` cycle as
`verdict: paused` and the orchestrator suppressed recovery **indefinitely**, so the run stalled
until the operator manually intervened.

Sequence:

1. The `/execute-plan` cycle child backgrounded a WU-7 test sub-subagent that WEDGED and died
   ("No tools needed for summary" — a depth-2 total tool-execution failure; recurred a 2nd time
   on the WU-5 grandchild).
2. The child's turn ended and it fired its completion notification (which, per the harness,
   fires only when it has NO live background children — `dispatched-agent-liveness.md` L11), so it
   returned control to the orchestrator with a dirty tree and a still-present execute-plan marker.
3. The execute-plan marker was ~3.6h old (mtime unchanged — the marker is written ONCE at
   `/execute-plan` Step 1d and never refreshed), plan `status: In-progress`.
4. `--execute-plan-liveness` returned `{marker_present: true, plan_status: In-progress,
   verdict: paused}`, so the orchestrator emitted `⚠ execute-plan cycle paused … recovery
   suppressed, awaiting harness re-invocation` and ended its turn to await a re-invocation.
5. The lineage was DEAD — no re-invocation ever came. The run stalled until the operator
   intervened.

## Root cause (Concluded)

`lazy_core.execute_plan_liveness` (`user/scripts/lazy_core/markers.py:100`) returns `paused`
whenever the execute-plan marker is present AND the plan is not `Complete`, with **no liveness or
marker-staleness dimension**. A live backgrounded pause and a dead-lineage wedge are therefore
**indistinguishable** to the discriminator — both present a marker + a non-Complete plan. The
function's own docstring RESERVED a `"wedge-candidate"` verdict for exactly this escalation but
never returned it ("the pure function CANNOT observe live descendants, so it never returns that
value in v1").

The genuine-wedge fallback IS documented — `lazy-batch/SKILL.md` Step 1e.4a L1016 and
`dispatched-agent-liveness.md` §60–65: "marker persists with NO live descendant after a bounded
wait ⇒ genuine wedge, recovery IS appropriate." But it was **prose-only and never verdict-routed**:
the discriminator never emits a wedge signal, so the orchestrator's `paused` branch silently
suppresses recovery and waits forever. The originating SPEC (`_archive/adhoc-orchestrator-redundant-
recovery-on-background-suite-reinvoke/SPEC.md` L138) explicitly anticipated this exact risk ("if
re-invocation is UNreliable … a genuine resultless stall") but the v1 fix punted it to prose.

### Why marker-mtime (not a wall-clock-since-activity) is the tractable pure-function signal

The execute-plan marker JSON (`{"plan":…,"repo_root":…}`) carries NO timestamp; the marker file is
written once at Step 1d and never refreshed, so its **file mtime = when the `/execute-plan` part
began**. The truly-decisive live-vs-dead signal is a `TaskList` descendant-liveness probe, which is
an ORCHESTRATOR capability the pure Python function cannot perform. The pure function CAN observe
marker-file mtime (a filesystem stat) — a bounded **staleness candidate** signal.

## Fix scope

1. **`lazy_core.execute_plan_liveness`** — add a marker-mtime staleness dimension. When the marker
   is present + plan not `Complete` + marker mtime age exceeds a generous, env-overridable bound
   (`_EXECUTE_PLAN_MARKER_WEDGE_SECONDS`, default 1800s, override `LAZY_EXECUTE_PLAN_MARKER_WEDGE_SECS`),
   return `verdict: "wedge-candidate"` (a candidate — the orchestrator confirms live-vs-dead). Below
   the bound → `paused` (unchanged). Additive + fail-safe: any error computing the age falls back to
   the existing `paused` behavior, so all prior semantics/tests are preserved.
2. **`lazy-batch/SKILL.md` Step 1e.4a** (+ coupled `lazy-bug-batch` overlay, regenerated) — route
   `verdict == "wedge-candidate"` to the genuine-wedge fallback (the `TaskList` lineage-alive probe
   per `dispatched-agent-liveness.md` §60–65): if the lineage is DEAD → route recovery; if somehow
   still live → WAIT (fall through to Step 1a). `wedge-candidate` does **NOT** auto-tear-down the
   marker (that mechanical liveness/teardown authority is HARD-PARKED as turn-routing-enforcement
   decision #12 — not reinvented here). This makes a false-positive (a legit >bound run) SAFE: it
   only triggers a liveness probe that correctly finds the live lineage and waits.
3. **Regression test** — a stale-marker fixture (`os.utime` back-dating the marker) asserting
   `verdict == "wedge-candidate"`; the existing fresh-marker tests keep asserting `paused`.

## Non-goals

- Reinventing the HARD-PARKED (decision #12) mechanical marker-teardown / `--force-run-end`
  authority — `wedge-candidate` escalates to the existing prose fallback, it does not tear down.
- A `TaskList` probe inside the pure function (an orchestrator-only capability).

Fix shipped OUT-OF-PIPELINE via a `harden(...)` commit (see the round in
`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`).
