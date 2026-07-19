# Bug: Orchestrator misroutes on grandchild (sub-sub-agent) task-notifications

**Status:** Concluded
**Severity:** P1 (destroys productive cycles mid-work; wastes forward-cycle budget)
**Pipeline:** feature (observed in `/lazy-batch`; applies to the whole coupled trio)
**Origin:** harden-harness Round 98 (2026-07-18), live `/lazy-batch` run on feature
`concurrent-worktree-agent-coordination`. Operator-directed inline harden.

## Verified symptom

During a live `/lazy-batch` run, the orchestrator dispatched a single cycle subagent (`/spec`,
agentId `a67b27d4…`) in the background and awaited its completion. Before that cycle returned, two
`<task-notification>` events arrived at the orchestrator session, each `status: completed` with a
BLOCKED result:

- "Ground concurrency-plane systems" (task-id `af1772d5…`)
- "Ground provisional and conflict precedents" (task-id `a9c766b9…`)

Neither task-id was an agent the orchestrator had dispatched — both were **read-only Explore
fan-outs the cycle subagent (`a67b27d4…`) had itself dispatched** (grandchildren of the
orchestrator). Both reported the same total tool-execution wedge (see "Secondary finding" below).

The orchestrator misread these grandchild BLOCKED notifications as evidence that its OWN cycle was
stuck/deadlocked and `TaskStop`-killed the direct cycle subagent. The kill notification then
revealed the cycle had actually been productive: *"Both agents returned precise anchors. All five
deps are Complete + receipted. I have full grounding … let me draft the baseline SPEC.md."* The
orchestrator repeated the mistake on the re-dispatched cycle (killed a second productive spec agent
mid-draft) before the pattern was understood. Net: two productive forward cycles destroyed, ~2
cycles of budget wasted, zero progress.

## Root cause

**Class: ambiguous-prose / missing-contract (orchestrator SKILL prose).** The `/lazy-batch`
orchestrator prose (and its coupled twins `/lazy-bug-batch`, `/lazy-batch-cloud`) never told the
orchestrator that:

1. The `Agent` cycle dispatch is asynchronous — the result arrives as a `<task-notification>` the
   orchestrator is re-invoked on, not as a synchronous return of the `Agent` tool call. (The §1d
   prose says "IMMEDIATELY after the Agent returns", implying a synchronous return.)
2. A cycle subagent's own sub-subagents (the sanctioned workstation sub-subagent model:
   `/execute-plan` test/impl agents, read-only Explore fan-outs, `/retro` research agents)
   **bubble their `<task-notification>` up to the top orchestrator session**, not only to the cycle
   subagent that dispatched them.
3. Therefore the orchestrator can receive notifications for agents it never dispatched, and must
   distinguish its DIRECT cycle child from grandchildren before acting.

With no contract for (1)–(3), the orchestrator applied its only available heuristic — "a BLOCKED
notification means my work failed" — to a grandchild's notification, and intervened. The fix
site is the orchestrator prose; there is no script surface to change (task-notifications are
delivered into the orchestrator's context by the harness — the state scripts never see them), so
prose + judgment is the only available lever. The fix biases the judgment toward the SAFE default
(do not intervene) and gives a positive match test (task-id == the dispatched agentId).

### Platform-behavior confirmation (claude-code-guide, 2026-07-18)

All three mechanics are **UNDOCUMENTED** in the Claude Code CLI docs (confirmed via
`claude-code-guide`): grandchild-notification bubbling, the task-id↔agentId correlation, and the
"No tools needed for summary" error. Per the harden-harness platform-behavior rule, the fix does
**not depend** on the undocumented correlation as load-bearing logic — it uses the task-id match
as a positive "this is my cycle" signal, with a WAIT (do-nothing) default on any non-matching or
ambiguous notification. The default is the safe direction: the incident was caused by
OVER-reacting, so biasing to non-intervention cannot reproduce it. Empirically this session
corroborated the correlation (the direct child's notification task-id equalled the dispatched
`agentId`; grandchildren carried task-ids never dispatched) — used as a signal, not a guarantee.

## Secondary finding — the tool wedge (PINNED as platform transient; not claude-config-fixable)

The two grandchildren wedged with the literal error **"No tools needed for summary"** returned
before EVERY tool call (Bash / Read / Grep / Glob / ToolSearch), 9+ consecutive, touching nothing.

- **Not a claude-config surface.** `grep -r "No tools needed"` across the entire claude-config repo
  (hooks, scripts, skills, MCP registrations) → **no match**. The message is produced by the Claude
  Code platform/runtime, not by any repo hook/skill/MCP.
- **No per-tool hook could produce it.** It fires uniformly for Read/Glob/Grep/ToolSearch with the
  same "for summary" wording — a `PreToolUse` hook is per-tool and cannot emit that uniformly. It
  reads as the platform gating tool use while an agent is in a summary/finalization state.
- **claude-code-guide:** the exact string is UNDOCUMENTED; interpretations are all platform-level
  (transient tool-gating / budget-saturation / bug), recoverable by re-dispatch into a fresh
  subagent (which both wedged agents independently recommended).

**Disposition: PIN, do not fabricate a fix.** This is a platform/runtime condition outside
claude-config's control. The durable claude-config response is the standing rule below, not a code
change.

## Fix scope (shipped this round)

1. **BUG 1 — orchestrator await/notification contract (mechanical, mirrored ×3).** New `§1d-await`
   subsection after the Dispatch block in `lazy-batch`, `lazy-bug-batch`, and `lazy-batch-cloud`
   SKILL.md: act only on the DIRECT child's notification (task-id == dispatched agentId, positive
   signal, WAIT-default otherwise); grandchild notifications bubble up and are the cycle subagent's
   to handle — never `--cycle-end`/route/`TaskStop` on them; never kill the cycle on a grandchild
   BLOCKED/failure.

2. **BUG 2 — sub-sub-agent tool-wedge standing rule (mechanical, mirrored ×3 + auto-invoke pointer).**
   A wedge is a species of observed friction (§1d.1 Trigger 5) handled POST-HOC only, with a
   transient carve-out: a single wedge whose siblings/re-dispatch succeed, or one attributable to a
   platform/API blip (incl. the undocumented `No tools needed for summary`), is TRANSIENT → do not
   harden. A REPRODUCIBLE or ≥2×-recurring, non-platform-attributable wedge IS harden-worthy.

## Why no mechanical (script/hook) enforcement

Task-notifications are delivered by the harness directly into the orchestrator's LLM context; no
state script, hook, or registry ever observes them. There is no seam at which a script could
mechanically block a spurious `TaskStop` or discriminate direct-child vs grandchild. The correct
and only lever is orchestrator prose + judgment, hardened toward the safe default. This is recorded
so a future round does not re-investigate looking for a script fix that cannot exist.
