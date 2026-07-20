# A Dispatched Orchestrator's `completed` Task-Notification Is Misread as Terminal While Its Lineage Is Live — Investigation Spec

> A background-dispatched orchestrator subagent (e.g. `/execute-plan`) that fans out FOREGROUND
> sub-subagents (impl/test agents, per the mandated synchronous-dispatch pattern) ends its turn
> at every inter-dispatch pause to await those foreground children. At each such pause the
> harness fires a `<task-notification>` with `status=completed` — because the contract fires
> "each time this agent stops with **no live background children** of its own", and FOREGROUND
> children are not *background* children. The receiving session (the main/dispatcher session)
> has **no contract** telling it that `completed` here means "paused awaiting foreground
> children", not "terminally done". It read the notification as terminal completion, inspected
> the orchestrator's uncommitted partial work, and nearly `TaskStop`'d the orchestrator + took
> over its files — which would have created a **dual-writer collision** against the still-live
> impl sub-subagents on `src-tauri/src/hydra/mod.rs`. Only a coincidental `TaskStop` failure
> (target already superseded) prevented the interference.

**Status:** Fixed
**Severity:** P1 (integrity/single-writer — the misread invites the main session to `TaskStop` a
live single-writer lineage and dual-write its owned files, the exact catastrophic failure the
one-writer discipline exists to prevent. No on-disk corruption occurred this time only by
coincidence.)
**Discovered:** 2026-07-17
**Fixed:** 2026-07-18
**Fix commit:** 6c2e9700
**Placement:** docs/bugs/dispatched-orchestrator-completed-notification-misread-as-terminal
**Related:**
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` — this investigation is the
  Step-2.5 audit-trail artifact for the corresponding hardening round.
- `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Rounds 39 & 45 — the SENDER-side
  fixes of the same broad "agent stopped waiting on a test/build" class (`turn-end-gate.md`).
  This bug is the complementary RECEIVER-side half never covered by those rounds.
- `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #12 (HARD-PARKED, harden Round
  60) — the mechanical liveness/ownership marker-teardown authority. A mechanical guard denying
  the main session's `TaskStop` is subsumed by that already-parked structural fork; this fix
  therefore stays in the prose-contract lane and does not re-open it.
- `user/skills/_components/turn-end-gate.md` — the SENDER contract this fix pairs with.
- `user/hooks/lazy-cycle-containment.sh` (BACKGROUND_CORRECTIVE) — the mandate that sub-subagents
  be dispatched FOREGROUND, which is exactly why the orchestrator has no *background* children at
  its inter-dispatch pauses.

## Reconstructed route (harden-harness Step 1)

- **Trigger kind:** manual (`/harden-harness <description>`) — operator-directed, observed live.
- **Item in flight:** `/execute-plan` for AlgoBooth hydra-overlay Phase 9.5, dispatched
  subagent `a794d046b1a72540d` (attributionAgent `general-purpose`), backgrounded and monitored
  by the main session via task-notifications.
- **Divergence point:** not a dispatch misroute. The orchestrator dispatched its two Batch-1
  impl sub-subagents (`ab06a7856a317a6c6` WU-1, `a53234f114e95e648` WU-2) FOREGROUND and in
  parallel, and was correctly re-invoked per-child-completion by the harness. Its transcript
  tail (task output `a794d046b1a72540d.output`) shows the legitimate inter-dispatch pauses:
  - `03:02:44` end_turn — "Both Batch 1 implementation agents are running in parallel. Awaiting
    their completion before the batch review gate."
  - `03:05:31` end_turn — "WU-1 impl complete ... Awaiting WU-2 impl agent."
  At each of these turn-ends the orchestrator had ZERO *background* children (its children were
  foreground), so the harness fired `status=completed`. The MAIN session read that `completed`
  as terminal, inspected the uncommitted partial tree, and moved to `TaskStop` + take over the
  files — against the live WU-2 impl agent. The `TaskStop` coincidentally failed (target
  superseded); no dual-write landed.

## Root cause (harden-harness Step 2)

**Class: `missing-contract`** (the complementary half of Round 39's `missing-contract`).

The `<task-notification>` is behaving exactly per its literal contract — it fires when the
subagent's turn ends with **no live background children**. The defect is that this condition is
NOT equivalent to "terminally done":

1. The mandated sub-subagent dispatch pattern is FOREGROUND/synchronous
   (`lazy-cycle-containment.sh` BACKGROUND_CORRECTIVE denies background sub-subagent dispatch,
   which would deadlock on a child→parent message that can never arrive). So a well-behaved
   orchestrator NEVER has *background* children.
2. Therefore, at every inter-dispatch pause where the orchestrator ends its turn to await its
   FOREGROUND children (and is correctly re-invoked per-completion by the harness), the
   "no live background children" condition is satisfied and `completed` fires.
3. There is **no receiver-side contract** anywhere in the harness telling a dispatcher/main
   session how to interpret a `completed` notification from an in-flight orchestrator. Rounds 39
   & 45 hardened only the SENDER (don't end your turn awaiting work); the RECEIVER interpretation
   was never written. So the main session had nothing to distinguish "paused awaiting foreground
   children" (do not interfere) from "terminally done" (safe to inspect/act).

The authoritative "is this orchestrator actually done" signal already exists on disk and was
never consulted: the `/execute-plan` **run marker**
(`~/.claude/state/execute-plan/<md5(repo_root)[:12]>.json`) is present iff the run is in-flight
and is removed only at genuine completion / BLOCKED / NEEDS_INPUT halt (execute-plan Step 1d /
Step 4). Combined with the plan frontmatter `status: Complete`, it is the ground truth a
`completed` notification is not.

## Reconciliation of the contract-wording contradiction

The notification is **not firing wrong**. "Fires each time this agent stops with no live
background children of its own" is literally true at a foreground-await pause. The word
`completed` overstates a condition that is really "turn ended, no *background* children" — which
is ALSO true at every inter-dispatch pause of a correctly-behaving fan-out orchestrator. The bug
is the RECEIVER treating an advisory turn-boundary signal as an authoritative completion signal.

## Fix scope (harden-harness Step 3 — mechanical, prose contract)

Author the RECEIVER-side counterpart to `turn-end-gate.md`:

1. **NEW** `user/skills/_components/dispatched-agent-liveness.md` — the interpretation contract:
   the reconciliation above; the rule that a `completed` notification from a dispatched
   orchestrator is ADVISORY, and the orchestrator's own on-disk terminal state (execute-plan run
   marker absent + plan `status: Complete`) is AUTHORITATIVE; a decision procedure for a
   `completed`-against-a-live-marker (check marker + plan status → if live, do NOT interfere:
   no `TaskStop`, no `Edit`/`Write` on the lineage's owned files — dual-writer risk; check
   `TaskList` for live descendants; monitor for resume); and the genuine-wedge recovery path
   (confirm no live descendants, prefer `SendMessage`-resume, take over only as sole writer;
   marker-teardown authority is decision #12, not re-opened here).
2. **Wire it in** at the realistic skill-running receivers, mirroring how `turn-end-gate.md` was
   wired in Round 39: a "Dispatcher's note" in `execute-plan/SKILL.md` Step 1d (run-marker
   section), and a "Receiver counterpart" cross-reference in `turn-end-gate.md` that also
   clarifies legitimate parallel-foreground fan-out (turn ends, harness re-invokes per child)
   is NOT a turn-end-gate violation.

**Deliberately OUT of scope (boundary drawn tight):**
- A mechanical PreToolUse guard denying the main session's `TaskStop`/`Edit` while a run marker
  is live. It is subsumed by the already-HARD-PARKED decision #12 (session-liveness/ownership
  teardown authority — a structural, gate-touching authority fork the operator owns). Adding a
  competing liveness-keyed guard here would pre-empt that decision and carries real
  false-positive risk (blocking legitimate operator recovery). The raw non-skill-running
  interactive main session is therefore the acknowledged residual reach gap, to be closed (if at
  all) when decision #12 lands.
- **The GENUINE-WEDGE mechanical backstop (operator-steered `SubagentStop` hook).** After the
  false-completion (receiver) fix above landed, the operator steered evaluation of a
  `SubagentStop` hook as the lead mechanical candidate for the DISTINCT genuine-wedge variant (a
  dispatched orchestrator whose turn truly ends with pending work uncommitted, nothing
  re-invoking it). Evaluation outcome: firing semantics are FAVORABLE (the hook fires only at a
  subagent's genuine loop-end, not at foreground-child yields) and `/execute-plan`'s existing
  run-marker lifecycle supplies the paused-with-live-children opt-out for free — but the
  loop-guard field `stop_hook_active` is genuinely UNDOCUMENTED and the block is a new
  subagent-lifecycle enforcement authority, making it a `divergence: structural` fork.
  HARD-PARKED (nothing implemented) as `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md`
  decision #14, with a concrete recommendation-first design for operator ratification.
- Any new sentinel/heartbeat field on the run marker: unnecessary. The marker's mere presence is
  already the "paused-not-done" signal, and `TaskList` already enumerates live descendants;
  resume-on-child-completion already works (the harness re-invokes the parent per completion).
