# Bug: cycle subagent stalls on wedged sub-sub-agent instead of falling back to inline

**Status:** Fixed
**Fixed:** 2026-07-18
**Fix commit:** 15fe485a
**Reported:** 2026-07-18
**Pipeline:** claude-config harness (lazy-batch cycle-dispatch contract)
**Origin:** harden-harness round (observed-friction), item in flight `concurrent-worktree-agent-coordination`

## Symptom (verified, observed live 2026-07-18)

During a `concurrent-worktree-agent-coordination` `/lazy-batch` run, a **plan-feature cycle
subagent** (`a911…`) dispatched three verification sub-sub-agents (spec-phases capability / reuse
audits). Every one of those depth-2 (grandchild) dispatches hit the Claude Code internal error
`No tools needed for summary` — every grandchild tool call errored before executing. The cycle
subagent then announced *"I'll wait for the two remaining audit agents"* and **TERMINATED without
drafting PHASES.md**, leaving the feature stuck at Step 6 (plan-feature) with `step_repeat_count`
climbing toward the oscillation tripwire.

**Contrast (the tell):** the `/spec`, `/realign-spec`, and Phase-2 cycles in the SAME run ALSO had
all their grandchildren wedge on the identical error — but each fell back to its OWN inline
`Read`/`Grep`/`Glob` and completed successfully. Only the plan-feature cycle stalled. The gap is
therefore not the platform wedge itself (present run-wide) — it is the ABSENCE of a resilience
directive telling a cycle subagent what to do when a dispatched grandchild returns a total wedge.

## Root cause

**Class: `missing-contract`** — the cycle-dispatch template
`user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` `@section workstation-dispatch`
(the sub-sub-agent dispatch policy auto-refreshed into every emitted workstation cycle prompt)
authorizes `Agent`-tool fan-out and carries a `SYNCHRONOUS AWAIT` guardrail — but that guardrail
only covers the **child→parent SendMessage deadlock** case ("never wait on a message FROM a
child"). It has **no contract for the case where an AWAITED dispatch RETURNS a total
tool-execution wedge** (every tool call erroring before execution, e.g. `No tools needed for
summary`). With no explicit directive, the cycle subagent treated "grandchildren didn't produce
usable output" as "keep waiting," rather than mapping it to "the fan-out failed — do this work
INLINE myself (depth-1 tools work fine)."

**Platform behavior (cited, NOT depended upon):** the depth-2 nested-dispatch wedge, grandchild
bubbling, and the `No tools needed for summary` string were confirmed **UNDOCUMENTED** via
`claude-code-guide` in harden Round 98 (`ca7f2c8b`) and pinned there as a platform-runtime
transient (grep finds it nowhere in claude-config; it fires uniformly before every tool type). The
fix here does NOT try to fix the platform bug and does NOT depend on the undocumented behavior — it
makes the cycle subagent RESILIENT to it (fall back to inline), which is the recommended posture
for an undocumented platform dependency.

## Why Round 98 did not already close this

Round 98 (`ca7f2c8b`, `grandchild-notification-misroute`) fixed the **ORCHESTRATOR** side: don't
misroute / `TaskStop` a productive cycle over a grandchild's bubbled notification, plus a
harden-auto-invoke wedge-classification rule (when a wedge is harden-worthy vs transient). It never
touched the **cycle subagent's own** dispatch contract. This bug is the distinct, uncovered seam:
the parent-of-the-wedged-grandchildren stalling. The two fixes compose into the complete
"depth-2 wedge resilience" contract — orchestrator (R98) + cycle subagent (this round).

## Fix scope

Add a **wedge-resilience directive** to `cycle-base-prompt.md` `@section workstation-dispatch`
(`modes=workstation`, `pipelines=feature,bug`, `skills=all` — one edit covers both pipelines;
cloud already mandates inline via `@section cloud-override`, so it is resilient by construction).
The directive: if a dispatched sub-sub-agent returns a **total tool-execution wedge**, do NOT wait
for it and do NOT re-dispatch it (it will wedge identically) — fall back to performing that work
INLINE with the cycle subagent's own `Read`/`Grep`/`Glob`/`Bash` (which execute fine at depth-1).
Applies to the skills that define a Sonnet fan-out and would otherwise strand on it
(`plan-feature`, `spec-phases(-batch)`, `write-plan`, `execute-plan` test/impl split, Explore
audits). Composes with the concurrent-worktree feature's Requirement 7 (trust the coordination
layer — resilience, not defensive serialization).

This is a shared-component prose edit, not a SKILL.md change, so no `/lazy-batch` ↔ `/lazy-bug-batch`
coupled-pair SKILL mirror is owed (the emitter reads this one template for both pipelines). No
sentinel schema touched.

## Verification

The fix is a prose contract; verification is the full gate battery (lint-skills projected +
capabilities, test_lazy_core, lazy-state/bug-state --test, test_hooks) staying green, plus the
`emit_cycle_prompt` residue/token check accepting the added prose (no unbound `{token}`).
