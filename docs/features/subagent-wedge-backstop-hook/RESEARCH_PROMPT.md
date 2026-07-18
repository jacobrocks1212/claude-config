# Research: A `SubagentStop` backstop hook that catches a genuinely-wedged autonomous sub-agent and forces it to commit/complete (or declare BLOCKED) before it stops

## Research Question

I am building a mechanical safety net for an autonomous, multi-agent software-development
pipeline built on Claude Code. When a dispatched sub-agent (or a dispatched sub-orchestrator)
**wedges** — its own tool calls start erroring, or it otherwise gives up — it stops/returns with
work left incomplete: uncommitted changes in the git working tree and/or unchecked work-unit
checkboxes in an active implementation plan. Because the agent is wedged, it cannot self-enforce
any prose "before you stop, finish your work" contract — a broken agent cannot follow
instructions. The pipeline is then stranded until a human notices.

The proposed fix is a `SubagentStop` **lifecycle hook** that fires at a sub-agent's genuine
termination, detects the "stopping with pending work" condition mechanically, and **blocks the
stop exactly once** — injecting an actionable instruction to commit + complete the plan (or write
a `BLOCKED.md` obstacle sentinel), then allowing the agent to stop on its second attempt.

**Main question:** What are the best-practice design patterns, failure modes, and prior art for a
lifecycle-termination "backstop" hook that intercepts a wedged/terminating autonomous agent and
forces a completion-or-honest-halt discipline — and specifically, what pitfalls arise around
(a) distinguishing a genuine wedge from legitimate completion, (b) preventing an infinite
block→continue→block loop, (c) fail-open safety so the guard can never itself deadlock the system,
and (d) garbage-collecting per-agent guard state?

## Context

- **System:** an autonomous "lazy" pipeline that walks a feature/bug from spec → phases → plan →
  implement → validate → mark-complete. A stateful Python driver owns all state transitions; thin
  LLM skills wrap it; shell **hooks** (registered in Claude Code `settings.json`) enforce
  invariants at tool-call boundaries and lifecycle events. Hooks are the *mechanical* enforcement
  layer; skill prose is the *cooperative* layer.
- **The specific surface:** Claude Code exposes a `SubagentStop` hook that fires when a dispatched
  sub-agent's agentic loop terminates. Its documented input fields are `session_id`,
  `transcript_path`, `cwd`, `agent_id`, `agent_type`, `permission_mode`. It supports blocking the
  stop via exit code 2 (with a stderr `reason`) or a JSON `{"decision":"block","reason":…}`; on a
  block the sub-agent continues working and the `reason`/`additionalContext` is injected into its
  conversation. `SubagentStop` fires at EVERY nesting level, and each sub-agent has a unique,
  stable `agent_id`.
- **A known constraint:** the `stop_hook_active` loop-guard flag that exists for the top-level
  `Stop` hook is **undocumented / absent** for `SubagentStop`, so the design must NOT depend on
  it. The chosen loop-guard is a per-`agent_id` breadcrumb file written outside any repo (in the
  tool's state dir): present ⇒ already blocked once ⇒ allow the stop.
- **Design philosophy (load-bearing):** the hook is strictly **fail-open** — any error
  (unreadable input JSON, missing `agent_id`, unresolvable repo, breadcrumb I/O failure) must
  allow the stop. A backstop that can itself wedge the pipeline is worse than the wedge it
  prevents. The system explicitly biases to **false-negative** (occasionally let a wedged agent
  stop) over **false-positive** (force-spin an agent that was legitimately done).
- **Scope:** the hook is a harness component only — it reads liveness/plan/git state, it never
  mutates run-ownership markers and never touches a target repo's source.

## Baseline Spec Summary (the design to pressure-test)

A new hook `subagent-wedge-backstop.sh`, matcher `*`, under a `SubagentStop` key.

**Predicate — block only a genuine wedge** (block iff ALL hold; fail-open on any error):
1. A pipeline run marker is present for the repo resolved from the hook input `cwd`.
2. The active plan's status is not `Complete` (genuinely unfinished work).
3. Pending work exists: the git working tree is dirty OR the active plan has unchecked
   work-unit checkboxes.

When the predicate is false (no marker / plan Complete / clean tree with all boxes checked) →
ALLOW the stop. That is the "legitimately done, or not a pipeline sub-agent" path.

**Loop-guard — block at most once per sub-agent**, keyed on `agent_id`: on entry, if a breadcrumb
file `<state-dir>/subagent-stops/<agent_id>.json` exists, ALLOW (already blocked once); on the
first block, WRITE the breadcrumb then block (exit 2 + actionable reason). This bounds a
genuinely-stuck agent (whose children keep erroring) to stopping on the second attempt rather than
looping forever.

**Block reason (actionable):** tells the agent to commit its work and complete the plan, or write
`BLOCKED.md` with the obstacle, then stop.

**Breadcrumb lifecycle:** write on first block; garbage-collect on genuine completion (a session-end
cleanup path and/or a staleness sweep) so `subagent-stops/` does not accumulate. GC failure is
non-fatal.

## Research Areas

1. **Prior art — forcing completion/honest-halt at agent termination.** How do other autonomous
   agent frameworks (LangGraph, AutoGPT/AutoGen-style loops, CrewAI, OpenAI Assistants/Swarm,
   Devin-class autonomous coders, CI "you must not leave the tree dirty" gates) detect and handle
   a sub-agent that terminates with incomplete/uncommitted work? What termination-interception or
   "definition of done" enforcement patterns exist, and which map onto a single-shot blocking
   lifecycle hook?
2. **Wedge-vs-done classification.** What signals reliably distinguish a *genuinely wedged* agent
   from one that *legitimately finished*? Is "dirty git tree OR unchecked plan checkboxes" a sound
   proxy, and what are its false-positive/false-negative modes (e.g. an agent that intentionally
   leaves the tree dirty for a parent to integrate; a plan whose checkboxes lag the real work; a
   sub-agent doing read-only exploration that never commits)? What additional cheap signals
   (transcript tail, tool-error density, elapsed-since-last-successful-tool) improve the
   classification without over-engineering?
3. **Loop-guard correctness with a filesystem breadcrumb.** What are the failure modes of a
   per-`agent_id` breadcrumb loop-guard (races between concurrent sibling sub-agents, breadcrumb
   written but block-injection lost, a re-used or non-unique id, breadcrumb dir unwritable)? Is
   "block at most once" the right bound, or is a small bounded retry count (e.g. block up to N
   times with backoff) meaningfully better for recovering a transiently-wedged agent? Best
   practices for atomic breadcrumb writes and for keying on an externally-supplied id.
4. **Fail-open guard-hook design.** Established patterns and pitfalls for security/enforcement
   hooks that must *never* themselves become the outage — timeouts, defensive parsing, the
   "allow on any error" discipline, and how to keep fail-open from silently disabling the guard
   permanently (observability of a guard that is failing open every time). How do mature systems
   surface "this backstop keeps erroring" without making the error path blocking?
5. **State/breadcrumb garbage collection.** Patterns for GC of per-entity ephemeral guard state
   keyed by a short-lived id: session-end hooks vs. staleness sweeps vs. TTL-on-read vs.
   write-time capping. Trade-offs for a directory that could otherwise accumulate one small file
   per sub-agent across long autonomous runs.
6. **Injected-instruction efficacy.** When a hook blocks a termination and injects a corrective
   instruction into the agent's conversation, what makes that instruction most likely to actually
   change behavior (specificity, naming the exact next action, giving an explicit escape hatch
   like "or declare BLOCKED")? Prior art on "reason" / `additionalContext` message design for
   agent self-correction, and the risk that a wedged agent ignores the instruction entirely
   (making the single-block bound the real safety property, not the instruction).

## Specific Questions

1. Across autonomous-agent and CI ecosystems, what is the closest prior art to a
   "block termination until work is committed or an honest BLOCKED is declared" gate, and what
   design lessons (especially failure modes) transfer to a `SubagentStop` hook?
2. Is "git tree dirty OR unchecked plan checkboxes" a defensible wedge predicate? What concrete
   false-positive scenarios should the predicate explicitly exclude, and are there low-cost extra
   signals worth ANDing in?
3. Given `stop_hook_active` is unavailable for `SubagentStop`, is a single per-`agent_id`
   breadcrumb the best loop-guard, or is a bounded-retry-count breadcrumb (block up to N with
   backoff) materially better at recovering transient wedges without risking an infinite loop?
4. What are the known races/pitfalls when many sibling sub-agents terminate near-simultaneously
   and each consults/writes its own breadcrumb — and how should breadcrumb writes be made
   race-safe and idempotent?
5. For a strictly fail-open guard, how do mature systems retain *observability* that the guard is
   silently failing open (so a permanently-broken backstop is noticed) without ever making the
   error path block?
6. What breadcrumb-GC strategy best fits short-lived `agent_id`-keyed files across long
   autonomous runs — session-end cleanup, a staleness/TTL sweep, write-time capping, or a
   combination — and what are the trade-offs?
7. What phrasing/structure of the injected block `reason` maximizes the chance a *recoverable*
   (not fully-wedged) agent actually commits + completes rather than immediately re-stopping — and
   what does prior art say about the ceiling on instruction efficacy for an already-erroring agent?
8. Are there second-order risks of adding termination-blocking to an autonomous pipeline (e.g.
   masking an upstream bug that should surface as a hard failure, delaying a legitimate abort,
   interacting badly with nested-subagent termination ordering) that argue for extra guardrails?

## Output Format Request

Return structured findings with these sections:

1. **Executive summary** — the 3–5 most important recommendations for this hook's design.
2. **Prior art** — a short catalog of comparable termination/completion-enforcement mechanisms
   (framework or CI), each with a one-line "what transfers here."
3. **Predicate design** — a concrete recommendation on the wedge predicate, an explicit list of
   false-positive scenarios to exclude, and any extra signals worth ANDing in (with cost/benefit).
4. **Loop-guard** — a recommendation between single-block vs. bounded-retry, the race/atomicity
   pitfalls, and safe breadcrumb-write guidance.
5. **Fail-open + observability** — how to keep the guard fail-open while remaining able to detect a
   permanently-failing backstop.
6. **Breadcrumb GC** — a recommended strategy with trade-offs.
7. **Injected-reason design** — concrete guidance (and an example reason string) plus the honest
   ceiling on its efficacy.
8. **Risks & guardrails** — second-order risks of termination-blocking and how to mitigate them.
9. **Actionable recommendations** — a prioritized punch-list mapped back to the baseline spec
   (confirm / revise / add), calling out anything the baseline got wrong.

Prefer concrete, implementation-level guidance over generalities. Where you cite a pattern from a
specific framework, name it and note the mechanism. Flag any recommendation that would change a
user-visible behavior of the pipeline (vs. an internal implementation detail).
