### Dispatched-Agent Liveness — a `completed` notification is not proof of completion (MANDATORY)

The RECEIVER-side counterpart to `turn-end-gate.md`. That gate governs the SENDER (never end
your turn while your own work is in flight); this contract governs the party that DISPATCHED a
long-running orchestrator (e.g. a backgrounded `/execute-plan`) and now watches it via
`<task-notification>`s. Read it before acting on ANY `completed` notification from a dispatched
agent whose work is not independently confirmed done.

#### Why a `completed` notification is only ADVISORY

The `<task-notification>` fires "each time this agent stops with **no live background children**
of its own." That condition is NOT the same as "terminally done":

- The mandated sub-subagent dispatch pattern is FOREGROUND / synchronous — `lazy-cycle-containment.sh`
  DENIES background sub-subagent dispatch (it would deadlock on a child→parent message that can
  never arrive). So a well-behaved fan-out orchestrator has **no *background* children, ever.**
- Consequently, at EVERY inter-dispatch pause where the orchestrator ends its turn to await its
  FOREGROUND children (an impl/test sub-subagent, a batch review gate, the next batch), the
  "no live background children" condition holds and a `status=completed` notification fires —
  even though the orchestrator is merely PAUSED and the harness will re-invoke it the moment a
  child returns (resume-on-child-completion works; the parent is not wedged).
- A backgrounded gate+commit job that has ended the turn is the same shape: `completed` can fire
  in the gap between "gates launched" and "commit landed".

So `completed` from a dispatched orchestrator means "its turn ended with no background children"
— which is true at every pause of a correctly-behaving run. Treating it as terminal completion
is the misread that invites a dual-writer collision against a live single-writer lineage.

#### The AUTHORITATIVE completion signal (consult this, not the notification)

An orchestrator is done only when its own on-disk terminal state says so:

- **`/execute-plan`:** its run marker `~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json`
  is present iff the run is IN FLIGHT, and is removed only at genuine completion / on a
  `BLOCKED.md` / `NEEDS_INPUT.md` halt (Step 1d / Step 4). Marker present ⇒ NOT done. Combine
  with the plan frontmatter: `status: Complete` on the plan file ⇒ done; `Ready`/`In-progress` ⇒
  not done. (`git status` / a fresh commit are corroborating, never sufficient — a live agent's
  tree is legitimately dirty mid-run.)
- **A lazy cycle / other skill dispatch you awaited FOREGROUND:** you receive its final report as
  the `Agent` tool call's own result — that result, not a notification, is the completion signal.
  You never need to interpret a notification for an agent you dispatched and are awaiting in-turn.

#### Decision procedure on a `completed` notification against a live orchestrator

1. **Check the authoritative signal first.** Run-marker absent AND plan `status: Complete`
   (or the awaited `Agent` result already consumed) → genuinely done; proceed normally.
2. **Marker present (or plan not `Complete`) → the orchestrator is PAUSED, not done.**
   - Do **NOT** `TaskStop` it. Do **NOT** `Edit`/`Write` any file its lineage owns
     (source/test files the impl/test sub-subagents are writing) — that is a dual-writer
     collision, the exact failure the one-writer discipline forbids.
   - Do **NOT** inspect-then-act on its uncommitted partial tree as if abandoned. A dirty tree
     under a live marker is work in progress, not residue.
   - `TaskList` to confirm the lineage is live (the orchestrator and/or its descendant impl/test
     agents still running). If any descendant is live → simply WAIT; the harness will re-invoke
     the orchestrator when its child returns. Silence between notifications is normal.

#### Genuine-wedge recovery (only after confirming the lineage is DEAD)

A genuine wedge is: run marker present + plan not `Complete` + **no live descendants**
(`TaskList` shows the orchestrator and all its sub-subagents finished/errored) + the orchestrator
does not resume after a bounded wait. Distinguish it from a pause by the absence of ANY live
descendant — never by the `completed` notification alone.

- **Prefer resume over teardown.** `SendMessage` the orchestrator to continue from its last
  durable checkpoint (its `TaskList` position + the plan/PHASES ledger) before any `TaskStop`.
- **Take over only as the SOLE writer.** Only after `TaskList` confirms NO descendant is still
  writing the target files may you `TaskStop` and take over — otherwise you re-create the
  dual-writer hazard you were avoiding. On takeover, remove the stale run marker as part of
  re-establishing single ownership.
- **Marker-teardown authority is not decided here.** The mechanical
  liveness/ownership/`--force-run-end` question is HARD-PARKED as
  `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #12 — do not improvise a
  competing mechanism; recover by hand per the above until that lands.
