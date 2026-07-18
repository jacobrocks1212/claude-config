# SubagentStop Wedge-Backstop Hook — Feature Specification

> A `SubagentStop` hook that mechanically catches a GENUINELY-WEDGED dispatched subagent — one
> that tries to stop/return with pending plan work still incomplete — and blocks its premature
> stop once, forcing it to commit + complete (or write `BLOCKED.md`) instead of returning dead
> and stranding the pipeline. The mechanical complement to the SENDER-side `turn-end-gate.md`
> prose (which a wedged/erroring agent cannot self-enforce).

**Status:** Ready
**Priority:** P1
**Last updated:** 2026-07-17

**Depends on:** (none)
<!-- Composes with the already-shipped receiver contract (dispatched-agent-liveness.md, the
FALSE-COMPLETION half, harden Round 81, commit 4197e5d8) and the sender contract
(turn-end-gate.md). Both are complete, so there is no blocking upstream. Decision #12
(descendant-liveness/ownership marker-teardown authority) is a SEPARATE parked NEEDS_INPUT and is
NOT a hard dependency of this hook — this hook reads liveness/ownership state, it does not
mutate marker teardown. -->

## Origin

Split out from `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` **decision #14** (harden
Round 81, 2026-07-17), operator-authorized 2026-07-17 conditioned on a `claude-code-guide`
confirmation of the mechanism (obtained — see "Platform confirmation" below). Decision #14 was
hard-parked as `divergence: structural` because it introduces a new subagent-lifecycle
enforcement authority AND its first-draft design leaned on the undocumented `stop_hook_active`.
The operator has now authorized the authority, and the loop-guard is redesigned to depend on a
DOCUMENTED field (`agent_id`) instead — removing the undocumented-dependency blocker.

### The gap this closes

The **genuine-wedge** variant of the "agent stopped waiting on a test/build" class: a dispatched
subagent (or dispatched orchestrator) whose work is left incomplete — uncommitted changes and/or
unchecked plan work — and that returns/stops dead, leaving the pipeline stranded until a human
notices and does a manual `TaskStop` + inline recovery. Observed live this session: three
consecutive sub-subagents of a part-10 `/execute-plan` cycle wedged (every tool call erroring),
leaving work uncommitted. The SENDER-side `turn-end-gate.md` prose cannot help — a wedged/erroring
agent cannot self-enforce prose. Only a hook that fires at the agent's genuine stop can catch it.

The **FALSE-COMPLETION** half (a live orchestrator's `completed` notification misread by the main
session as terminal) was already fixed mechanically in Round 81 via the receiver contract
`dispatched-agent-liveness.md`; THIS feature is the remaining genuine-wedge mechanical backstop.

## Platform confirmation (claude-code-guide, 2026-07-17)

Confirmed against current Claude Code docs before authoring (per the harden-harness Step-2
platform-confirmation rule):

- **Firing scope:** `SubagentStop` fires ONLY at a subagent's genuine agentic-loop termination,
  NOT at the mid-turn yields that produce the false-`completed` `<task-notification>`s. A
  correctly-fanning-out orchestrator's yields do not trip the hook. (The notification surface and
  the hook surface are distinct, with different firing rules.)
- **Blocking mechanism:** documented + supported — exit code 2 (stderr `reason`) or
  `{"decision":"block","reason":…}` blocks the stop and the subagent continues working;
  `additionalContext` is injected into the conversation.
- **Loop-guard:** `stop_hook_active` is **undocumented for `SubagentStop`** (it appears only in
  `Stop` guidance and is NOT in the `SubagentStop` input schema) — do NOT depend on it. The
  hook input DOES include a documented, stable per-subagent identifier **`agent_id`**, which is
  the sanctioned breadcrumb key.
- **Hook input fields:** `session_id`, `transcript_path`, `cwd`, `agent_id`, `agent_type`,
  `permission_mode`.
- **Nested subagents:** `SubagentStop` fires at EVERY level (not just leaves); each subagent gets
  its own unique `agent_id`, so per-`agent_id` breadcrumbing is well-defined and a mid-tier
  subagent never shares a breadcrumb with its children.

## Design (the authorized option)

A new hook `user/hooks/subagent-wedge-backstop.sh`, matcher `*`, registered in `user/settings.json`
under a `SubagentStop` key.

### Predicate (block only a genuine wedge)

Block the stop only when ALL hold (fail-OPEN on any error or missing field — never wedge the
pipeline):

1. **A run marker is present** for the repo resolved from the hook input `cwd` (an active
   pipeline run owns this subagent's lineage).
2. **The active plan's status is not `Complete`** (there is genuinely unfinished plan work).
3. **Pending work exists:** the git working tree is dirty OR the active plan has unchecked work-unit
   checkboxes.

When the predicate is false — no marker, plan Complete, clean tree with all WUs checked — ALLOW the
stop (exit 0). This is the "legitimately done / not a pipeline subagent" path.

### Loop-guard (block at most once per subagent)

Keyed on the documented `agent_id`:

- On entry, check a breadcrumb file (absolute path OUTSIDE any repo — the claude state dir, e.g.
  `<claude-state>/subagent-stops/<agent_id>.json`). If it exists, the agent was already blocked
  once — ALLOW the stop (do not loop).
- On the first block, WRITE the breadcrumb, then block (exit 2 + actionable reason).
- This guarantees at most one block per subagent: a genuinely-stuck agent (children keep erroring)
  stops on the second attempt rather than entering an infinite block→continue→block loop. No
  dependency on the undocumented `stop_hook_active`.

### Block reason (actionable)

The `reason` tells the agent exactly what to do: *"You are stopping with pending plan work and the
completion protocol has not run. Commit your work and complete the plan (or write BLOCKED.md with
the obstacle), then stop."*

### Fail-open (load-bearing)

Any error — unreadable input JSON, missing `agent_id`, unresolvable repo, breadcrumb I/O failure —
MUST exit 0 (allow the stop). A backstop hook that can itself wedge the pipeline is worse than the
wedge it prevents. Bias to false-negative (let it stop) over false-positive (force-spin a done
agent), per the operator steer.

### Breadcrumb lifecycle

Write on first block; garbage-collect on genuine completion (a `SessionEnd` cleanup path and/or a
staleness sweep) so the `subagent-stops/` dir does not accumulate. GC failure is non-fatal.

## Scope / non-goals

- **claude-config only** (a harness hook + tests). Never touches a target repo's source.
- **Not a gate-weakening** — it ADDS enforcement, removes no gate (so it is outside Prohibition #2).
- **Does not mutate the run marker or registry** — it READS liveness/ownership state only. The
  marker-teardown authority (decision #12) is separate and NOT re-opened here.
- **Does not replace** the receiver contract (`dispatched-agent-liveness.md`) or the sender
  contract (`turn-end-gate.md`) — it is the third, mechanical leg for the wedge the prose cannot
  self-enforce.

## Testability

Fully unit-testable in `test_hooks.py` with synthetic hook-input JSON + a temp repo/marker/plan
fixture (no live subagent needed): predicate-true→block-once, second-attempt→allow (breadcrumb),
fail-open on malformed input / missing `agent_id`, clean-tree-or-Complete-plan→allow,
no-marker→allow, nested distinct-`agent_id`→independent breadcrumbs.
