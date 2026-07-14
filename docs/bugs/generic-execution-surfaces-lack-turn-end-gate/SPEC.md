# Generic execution surfaces lack a turn-end gate — orchestrating agents end their turn "awaiting" backgrounded verification / inner agents — Investigation Spec

> An orchestrating/execution subagent (running `/execute-plan` OUTSIDE the lazy state machine)
> ends its turn while work it owns is still in flight — a backgrounded gate+commit job, or a
> dispatched inner agent whose report has not returned — with a final message of the form
> "awaiting its completion" / "the watcher will re-invoke me". The claimed re-invocation never
> fires (inside a dispatched agent, ending the turn ends the agent), so the run stalls until a
> human manually resumes it. The failure class is already named and fixed for the Cognito
> build-queue surfaces (`subagent-backgrounds-verification-ends-turn-before-green`) and for
> lazy-dispatched cycles (cycle-base-prompt R13 TURN-END CONTRACT + SYNCHRONOUS AWAIT), but the
> GENERIC shared execution contract carries no such gate.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-13
**Placement:** docs/bugs/generic-execution-surfaces-lack-turn-end-gate
**Related:** `docs/bugs/_archive/subagent-backgrounds-verification-ends-turn-before-green/` (the
build-queue instance of the class), `docs/specs/turn-routing-enforcement/` (hardening stage),
`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` R13 (the lazy-cycle instance)

---

## Verified Symptoms

1. **[VERIFIED — 4 recurrences in one orchestrated run, 2026-07-13]** During orchestrated
   multi-phase execution of `lazy-core-package-decomposition` (manual orchestrator dispatching
   one `/execute-plan` subagent per plan part — outside the lazy state machine), execution
   subagents ended their turn while owned work remained in flight:
   - Phase-1 executor: final message "Waiting for the WU-1 agent to finish its report." (1×)
   - Phase-2 executor: "The gate+commit job is running in the background; I'll be notified when
     it completes" (1×); "WU-2 agent resumed to complete its verification... Awaiting its
     completion." (1×); "WU-3 agent resumed... The ground-truth marker watcher remains armed on
     its transcript and will re-invoke me when the report lands." (1×)
2. **[VERIFIED]** The claimed watcher/notification re-invocation did NOT fire in any of the 4
   cases; each stall required a manual `SendMessage` resume from the main orchestrator.
3. **[VERIFIED]** Two distinct in-flight shapes: (a) a backgrounded Bash gate+commit job; (b) a
   dispatched/resumed inner `Agent` whose final report was never consumed.

## Reproduction Steps

1. Dispatch an `/execute-plan` execution subagent for a plan part (plain `Agent` dispatch — no
   lazy run marker, so no cycle-base-prompt R13 TURN-END CONTRACT is injected).
2. Have it either (a) launch its batch gate+commit chain `run_in_background: true`, or
   (b) dispatch an inner WU agent and treat "dispatched / resumed / watcher armed" as a
   stopping point.
3. The subagent ends its turn on the in-flight state, satisfied it "will be notified".

**Expected:** the agent drives every in-flight item to a terminal result (job exit read; inner
agent's returned report consumed) before ending its turn, or explicitly reports verification
INCOMPLETE.
**Actual:** the turn ends "awaiting"; nothing re-invokes a finished agent; the run stalls.
**Consistency:** 4/4 within one run whenever verification was backgrounded or an inner agent was
awaited asynchronously.

## Root-Cause Trace (SEAM A — serving path, `traced`)

```
surface: orchestrated run stalls; execution subagent's final message is "awaiting X"
  → subagent backgrounds its gate battery / dispatches-then-awaits an inner agent
  → subagent ends its turn believing a completion callback / watcher / SendMessage
       will re-invoke it — structurally false inside a dispatched agent (ending the
       turn ends the agent; only a top-level session gets background re-invocation)
  → the GENERIC contracts it operates under carry NO turn-end gate:
       user/skills/_components/execution-contract.md            ← FIX SITE 1
         ("Background builds" §, line ~167, even instructs "poll the build's result
          afterward ... read results/<seq>.json and check exit_code" — the stale
          hand-read idiom the build-queue skills themselves prohibit; and nowhere
          states the turn may not end on a pending job)
       user/skills/_components/subagent-launch.md ~:33          ← FIX SITE 2
         (same "waits on the build's exit_code" idiom; no await/turn-end language)
       user/skills/execute-plan/SKILL.md Step 4 item 3          ← FIX SITE 3
         (has "Do NOT end your turn while the gate+commit job is still backgrounded"
          — completion-seam only; silent on inner-agent dispatches and per-batch jobs)
  → contrast: the covered surfaces all carry the gate —
       cycle-base-prompt.md R13 (+ SYNCHRONOUS AWAIT, workstation-dispatch §)   [lazy cycles]
       implementation-agent.md:36,52 / tdd-test-agent.md:28                    [worker agents]
       msbuild:40 / mstest:43 / nxbuild:42 / nxtest:43 SKILL.md §4             [Cognito queue skills]
       tauri-build:48 / cargo-release:44 SKILL.md                              [AlgoBooth queue skills]
       write-plan-cognito/lane-agent-briefing.md:28,89                         [Cognito lanes]
  = a generic /execute-plan orchestrator has no contract forbidding a turn-end on
    in-flight work; the observed stalls satisfy every contract it was given
```

**Cause label: `traced`.** All three fix sites lie on the serving path (they ARE the operating
contract the stalling agents executed under). Runtime evidence: the 4 observed stalls + the
manual SendMessage resumes (run transcript, 2026-07-13).

## Root-cause class (hardening taxonomy)

**missing-contract.** The class fix (`subagent-backgrounds-verification-ends-turn-before-green`,
2026-07-09) landed the turn-end gate on the Cognito/build-queue consumer surfaces and the worker
briefings, and `cycle-subagent-leaves-work-uncommitted-or-unticked` landed R13 for lazy cycles —
but the shared GENERIC contract (`execution-contract.md` / `subagent-launch.md` /
`subagent-review.md` / `/execute-plan` outside the completion seam) was never retrofitted. A
legitimately-covered scenario (queue builds, lazy cycles) coexists with an uncovered near
neighbor (generic backgrounded gate batteries; inner-agent dispatch-await), and the harness was
not designed for the latter yet.

## Proven Findings

- **PROVEN:** No generic-contract text forbids ending a turn on a backgrounded job or an
  un-consumed inner-agent dispatch; the observed stalls violated no contract they were given.
- **PROVEN:** The "I'll be notified" belief is structurally false inside a dispatched agent —
  4/4 claimed re-invocations never fired; each needed a manual resume.
- **FOUND (adjacent, same seam):** `execution-contract.md` "Background builds" and
  `subagent-launch.md:33` still instruct hand-reading `results/<seq>.json` / "the build's
  `exit_code`" — contradicting the queue skills' own contract ("do not hand-read
  `results/<seq>.json`; await via `build-queue-await.ps1`; exit 124 ≠ success"). Stale
  pre-`build-queue-await.ps1` prose; fixed in the same pass.
- **RULED OUT:** hook/script defect — no guard misfired; this is prose-contract absence.
- **AUDITED CLEAN (Gap-2 sweep, 2026-07-13):** all four Cognito build skills, both AlgoBooth
  queue skills, both worker briefings, and the Cognito lane contract carry the §4 turn-end gate
  + the exit-124-not-success echo; the lane contract's Step L.3 even treats a lane reporting a
  bare `enqueued as seq=N` as a trust-break trigger forcing a conditional re-run.

## Affected Area / Fix Scope

| Component | File | Fix role |
|-----------|------|----------|
| Canonical statement | `user/skills/_components/turn-end-gate.md` (NEW) | ONE generic, role-neutral turn-end gate: in-flight work (backgrounded job / un-consumed inner agent / bare enqueue) is not an outcome; dispatch-and-await; poll-or-foreground to terminal; honest INCOMPLETE fallback |
| Generic execution policy | `user/skills/_components/execution-contract.md` | Inject the component as a MANDATORY subsection of "Parallelism & background builds"; add MANDATORY RULE 13; replace the stale `results/<seq>.json` hand-read poll instruction with `build-queue-await.ps1` (exit 124 ≠ success) |
| Launch mechanics | `user/skills/_components/subagent-launch.md` | Same stale-idiom fix; add a compact turn-end pointer to the component |
| Executor | `user/skills/execute-plan/SKILL.md` Step 4 item 3 | Generalize the completion-seam sentence to inner-agent dispatches + name the component |
| Review protocol | `user/skills/_components/subagent-review.md` | One-line reinforcement: "wait for ALL subagents" means dispatch-and-await per the component |

Deliberately out of scope: a mechanical backstop (a hook denying turn-end with a live owned job)
— the same "Enforcement vs. instruction" open question the archived class bug left to prose +
the await primitive; the covered surfaces have held with prose since 2026-07-09. Lazy-cycle and
Cognito surfaces are already covered — no edits owed there (no coupled-pair mirror: none of the
touched files is in `lazy-parity-manifest.json`).
