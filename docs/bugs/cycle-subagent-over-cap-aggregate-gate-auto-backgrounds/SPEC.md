# Bug: cycle subagent auto-backgrounds an over-10min-cap aggregate gate and pauses at its turn boundary

**Status:** Concluded
**Reported via:** `/harden-harness` observed-friction dispatch (2026-07-16, item in flight `d8-signal-flow-viz`, AlgoBooth `/lazy-batch`, blocking=false)
**Root-cause class:** `missing-contract`
**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); `user/skills/_components/turn-end-gate.md` (Round 39 — the canonical turn-end gate this round completes); hardening-log Round 39/44.

## Symptom (verified)

On BOTH consecutive `/execute-plan` cycles of the `d8-signal-flow-viz` run (plan part-4 AND
part-5), the cycle subagent (integrator) ran the AGGREGATE gate `npm run qg -- ts`, which
EXCEEDS the Bash tool's ~10-minute cap. The harness auto-backgrounds an over-cap command; the
integrator then ended its turn WAITING on that backgrounded gate, and the backgrounded
build/test process tree was torn down at the subagent turn boundary — the exact failure the
turn-end contract warns about ("your background processes DIE when your turn ends"). Result:
every `/execute-plan` cycle paused mid-cycle and required the orchestrator to `SendMessage`-resume
it with an explicit "run gates synchronously in the foreground, component-wise" instruction.

The integrator on part-5 discovered the working recovery itself: `npm run qg -- ts` is an
aggregate of 4 sub-components (`vue-tsc`, `eslint`, `vitest`, `vite build`), each individually
UNDER the ~10-min cap — so running them individually in the foreground avoids the auto-background
entirely and drives each to a real pass/fail within the turn.

**Cost:** one orchestrator resume round-trip per `/execute-plan` cycle (2 observed this run).
Non-blocking: the resume-recovery works, so the run continues on current behavior; the fix removes
the per-cycle resume round-trip for future cycles.

## Root cause

**`missing-contract`.** The turn-end contract on every relevant surface is REACTIVE only. The
lazy cycle prompt's turn-end section
(`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`, `@section turn-end`
workstation + cloud, item 1) and the canonical shared component
(`user/skills/_components/turn-end-gate.md`, bullet "Backgrounded shell job → block on it:
re-run it foreground, or poll its output in a bounded foreground loop") both say: *if a long
gate was auto-backgrounded, block on it (re-run it foreground).* That remediation is
STRUCTURALLY INSUFFICIENT for the over-cap-AGGREGATE case: re-running the same aggregate in the
foreground simply re-hits the ~10-min cap and re-backgrounds. There is NO contract prescribing
the PREVENTIVE move — when a required gate command would exceed the ~10-min cap, do NOT reach for
the aggregate at all; run its individual under-cap sub-components synchronously in the foreground
(and never background a long gate from inside a dispatched cycle subagent, whose process tree is
torn down when its turn ends).

The gap is specifically the DECOMPOSITION contract for over-cap aggregate gates. The AlgoBooth
`/execute-plan` cycle prompt does not tell the subagent to substitute `npm run qg -- ts`'s 4
under-cap components for the over-cap aggregate, so the subagent reaches for the aggregate, hits
the cap, auto-backgrounds, and pauses — every cycle.

The pattern is repo-agnostic (over-cap aggregate gate → run components foreground, never
background from a dispatched agent); only the concrete command decomposition
(`npm run qg -- ts` → `vue-tsc` + `eslint` + `vitest` + `vite build`) is AlgoBooth-specific.

## Fix scope

Three tightly-scoped prose edits (no Python; no gate weakened):

1. **`user/skills/_components/turn-end-gate.md`** (canonical SSOT, propagates to `/execute-plan`,
   `/gate-battery`, `execution-contract.md`, `subagent-launch.md`, `subagent-review.md`): extend
   the "Backgrounded shell job" remediation bullet with the PREVENTIVE over-cap-aggregate rule —
   when the aggregate command itself exceeds the ~10-min cap, run its individual under-cap
   sub-components in the foreground instead of reaching for the aggregate (never background a long
   gate from inside a dispatched agent).

2. **`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`** `@section turn-end`
   (workstation + cloud), item 1: restate the same preventive decomposition rule in the cycle
   contract the subagent reads at turn end.

3. **`repos/algobooth/.claude/skill-config/cycle-prompt-addenda.md`**: add an
   `execute-plan`-scoped section carrying the concrete AlgoBooth decomposition
   (`npm run qg -- ts` → `vue-tsc` + `eslint` + `vitest` + `vite build`, each under the cap; run
   foreground, never the aggregate, never backgrounded from the cycle subagent).

`cycle-base-prompt.md` and the addenda are on the auto-refresh boundary, so the fix takes effect
on the next emitted cycle prompt. This does NOT weaken any gate (all 4 sub-components still run;
the fix only changes HOW they are invoked to keep each under the cap and in the foreground).
