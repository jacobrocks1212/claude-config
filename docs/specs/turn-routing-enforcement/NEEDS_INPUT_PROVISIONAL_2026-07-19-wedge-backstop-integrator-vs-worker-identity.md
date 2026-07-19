---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
class: product
divergence: structural
next_skill: harden-harness
decisions:
  - "wedge-backstop-integrator-vs-worker-identity: how should subagent-wedge-backstop.sh exempt a cycle's NESTED WU workers (great-grandchildren) from the wedge block while still blocking a genuinely-wedged execute-plan INTEGRATOR? The now-cycle-scoped predicate (Rounds 99+107) cannot tell WHICH agent under the shared cycle marker is stopping; every discrimination option is structural, coverage-reducing, or hinges on an UNCONFIRMED SubagentStop lineage field (claude-code-guide dispatch prohibited to the marked-run harden agent). Recommended: Option A (self-managed integrator-agent_id breadcrumb). (harden Round 108, 2026-07-19)"
date: 2026-07-19
---

## Decision Context

An **observed-friction** dispatch (item in flight `hydra-overlay`, AlgoBooth) surfaced a THIRD
false-fire facet of the `subagent-wedge-backstop.sh` `SubagentStop` predicate. During the
`hydra-overlay` phase-8.5 `execute-plan` cycle the hook BLOCKED **3 correctly-scoped, non-committing
WU sub-subagents** (great-grandchildren the cycle integrator dispatched via the workstation
sub-subagent split). Root cause is CONCLUDED and reproduced —
`docs/bugs/subagent-wedge-backstop-blocks-nested-wu-workers/SPEC.md`.

This is a DISTINCT axis from the two prior facets, both already FIXED:
- Round 99 (`adhoc-subagent-wedge-hook-overfires-globs-all-plans`) scoped the **plan-WU** half to
  the active cycle's plan.
- Round 107 (`subagent-wedge-backstop-dirty-tree-predicate-repo-wide`) scoped the **git-dirty** half
  to the cycle's own item dir.

Those closed the **path/plan** scoping axis. Round 107's own log entry flagged "a future third
un-scoped input added to this predicate is an unambiguous trigger." The un-scoped dimension here is
not a path — it is **agent identity**. The cycle marker is a *cycle-level* object: the integrator AND
every nested WU worker it dispatches stop under the *same* marker, naming the *same* non-terminal
plan with the *same* unchecked WUs. `plan_pending` is UNAVOIDABLY true for any worker that stops
mid-cycle (the integrator ticks WUs only after all workers return), and the integrator's genuine
wedge state and a worker's normal mid-flight stop are **byte-identical on disk**. Discrimination
therefore requires agent lineage, which the harness does not have at `SubagentStop`.

**Why this is a hard-park, not a park-provisional-implement.** The `/harden-harness` default is to
implement the recommended option provisionally. It does NOT apply here because every viable option
lands in a hard-park carve-out (structural divergence, coverage-semantics change, or an unconfirmed
platform dependency). Specifically, the recommended precise fixes are `structural` (new state + a new
hook seam), and the only one-line non-structural option is coverage-reducing. Per the skill's Step-2
platform-confirmation rule (origin: Round 81's `SubagentStop`/`stop_hook_active` incident), no
load-bearing discrimination logic may be shipped on an unconfirmed `SubagentStop` lineage field — and
the marked-run harden agent is prohibited from dispatching `claude-code-guide` to confirm one. So the
round ships the investigation + this park, and implements nothing.

The friction is **non-blocking**: the block is bounded to once per `agent_id` (loop-guard intact), so
each worker proceeds on its second stop. There is no pipeline-stranding urgency forcing a hasty
mechanism — which is itself an argument for operator sign-off over a rushed provisional ship.

### Established facts the decision rests on

- **Only `agent_id` is documented + stable on `SubagentStop`, and it carries NO lineage.**
  `agent_id` is unique per subagent at every nesting level but has no parent/depth information
  (feature `subagent-wedge-backstop-hook/RESEARCH_SUMMARY.md`; `subagent-wedge-backstop.sh` header).
  `session_id`/`cwd` are shared across the session. `stop_hook_active` is undocumented for
  `SubagentStop` and unused.
- **`agent_id` is hook-input-only** — it does not propagate to a subagent's own subprocess env
  (`user/scripts/lazy_core/markers.py`, CYCLE_REFUSED_OPS comment ~L2388–2394), so a subagent cannot
  self-record its own id.
- **`execute-plan` declares `subagent-model: true`** (`user/skills/execute-plan/SKILL.md:6`), so its
  cycle marker carries `subagent_model: True` and the dispatch guard's workstation sub-subagent
  exemption is armed; each allowed worker dispatch writes a `worker_subdispatch: true` deny-ledger
  event (`dispatch.append_worker_subdispatch_event`) recording the worker's *dispatch* `tool_use_id`
  (no documented correlation to the stopping `agent_id`).
- **The pitfall was pre-identified** in the feature's `RESEARCH_SUMMARY.md` Q2 ("a child that
  intentionally leaves the tree dirty for a parent to integrate must not be force-spun"), but the
  baseline mitigation ("confirm the predicate does not fire for a subagent whose lineage has no
  active plan") FAILS: a nested execute-plan WU worker's lineage DOES have an active plan.

## Decision 1 — Mechanism to exempt nested WU workers from the wedge block

**`divergence: structural`** (most severe across the options).

### Option A — Self-managed integrator-`agent_id` breadcrumb  ★ RECOMMENDED

A PreToolUse hook (extend the existing `lazy-cycle-containment.sh`, which already runs in the
PreToolUse pipeline and receives `agent_id`) records the **FIRST** `agent_id` observed under each
cycle-marker generation as the **integrator**, keyed by the marker nonce, into a sibling breadcrumb
(e.g. `<claude-state>/cycle-integrator/<nonce>.json`). The wedge-backstop then BLOCKS only when the
stopping `agent_id == recorded integrator agent_id`; a nested WU worker's `agent_id` never matches →
always allowed.

- **Load-bearing assumption:** the integrator's first tool-use fires before any worker's first
  tool-use. This is structurally guaranteed — the integrator must act (read the plan, etc.) before it
  can dispatch a worker, and session tool calls are serial (the SAME assumption the consumed-fence at
  `dispatch.py:2268` already relies on: "session tool calls are serial").
- **Non-platform-dependent:** uses only the documented `agent_id`; NO `SubagentStop` lineage field.
- **Preserves integrator-wedge coverage precisely** while exempting workers.
- **Cost / risk (why operator-owned):** new persistent breadcrumb + a new recording seam in a
  delicate, heavily-invarianted containment hook + a cross-hook predicate change; a wrong ordering
  edge case would either re-introduce a false-fire or (worse) let a wedged integrator escape.
  `structural`.

**Recommendation:** Option A. It is the only option that both preserves the hook's primary purpose
(catching a wedged execute-plan integrator) AND avoids the unconfirmed-platform dependency, at the
cost of a bounded, well-understood structural addition. Recommend green-lighting A for a follow-on
implementation round (mechanical once the mechanism is blessed).

### Option B — Platform lineage field on `SubagentStop`

If the platform exposes a `parent_agent_id` / depth / `parent_tool_use_id` on `SubagentStop`, block
only the top-level integrator directly. **Blocked on confirmation:** requires a `claude-code-guide`
dispatch (prohibited to the marked-run harden agent); may not exist at all. Cannot ship on
assumption (Round-81 rule). Cheapest IF the field exists — worth the operator confirming before
committing to Option A's machinery.

### Option C — Broad `subagent_model` exemption

One line: allow the stop whenever `marker.subagent_model == True`. Non-dependent, ships immediately,
no new state. **But** the wedge-backstop then NEVER blocks an `execute-plan` integrator wedge — its
PRIMARY target — leaning entirely on the completion gate (`verify_ledger`) and
`detect_cycle_bracket_friction` for that coverage. Coverage-reducing; guts the hook's main value.
Acceptable only if the operator judges those other backstops sufficient and prefers to retire the
SubagentStop-level net for execute-plan.

**Recommendation across options:** confirm B (does a lineage field exist?) → if yes, implement B; if
no, implement A. Reserve C as the fallback only if the operator wants zero new machinery and accepts
the coverage loss.

## Requested operator action

1. Confirm (or delegate confirming) whether `SubagentStop` exposes any parent/depth lineage field
   (Option B viability).
2. Pick the mechanism (A / B / C) for a follow-on implementation round.
3. Until resolved, the wedge-backstop keeps its current behavior — the false-fire is non-blocking
   (bounded to once per `agent_id`), so no interim degradation is shipped.

## Resolution

*Recorded on 2026-07-19. Provisionally auto-accepted on recommendation (harden Round 109,
operator-authorized self-resolve-then-provisional-accept flow). Ratify or redirect via the
provisional-ratification affordance before completion.*

resolved_by: auto-provisional
decision_commit: 5312b9dba365251cd42a9a5328dd3eef1bfeb733

**Platform blocker cleared by self-consultation.** Per the Round-109 protocol change
(`docs/bugs/harden-hard-parks-on-unconfirmed-platform-assumptions/`), the marked-run harden
agent CONSULTED `claude-code-guide` itself (2026-07-19) to resolve the platform assumption that
blocked Round 108. The guide **independently confirmed**: the `SubagentStop` hook input exposes the
documented, stable `agent_id` and `agent_type`, `session_id` is shared across the session, but there
is **NO lineage field** — `parent_agent_id` / `parent_tool_use_id` / nesting `depth` are undocumented
and absent from the schema (source: code.claude.com/docs/en/agent-sdk/hooks.md). This eliminates
**Option B** (no platform lineage field exists to block only the top-level integrator) and confirms
**Option A** is non-platform-dependent (it uses only the documented `agent_id` plus the serial-tool-call
ordering the guard's consumed-fence already relies on).

**Operator authorization.** The operator explicitly authorized both this protocol change and the
provisional acceptance of Option A, which overrides the standing `structural`-divergence hard-park
carve-out for this instance (the platform blocker is resolved and Option B is eliminated, so only the
recommended Option A remains viable). Recorded here for operator ratification.

### 1. Decision 1 — Mechanism to exempt nested WU workers from the wedge block

**Choice:** Option A — Self-managed integrator-`agent_id` breadcrumb.
**Notes:** Provisionally accepted (operator-authorized) — divergence graded `structural` (producer);
platform blocker cleared via claude-code-guide self-consultation (Option B eliminated). Implemented in
commit `5312b9db`: `lazy-cycle-containment.sh` records the FIRST `agent_id` under each cycle nonce as
the integrator (`<state>/cycle-integrator/<nonce>.json`); `subagent-wedge-backstop.sh` blocks ONLY the
recorded integrator and exempts nested WU workers. Pending operator ratification via the
provisional-ratification affordance.
