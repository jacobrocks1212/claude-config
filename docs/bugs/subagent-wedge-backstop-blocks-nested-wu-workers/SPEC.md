---
kind: bug-investigation
bug_id: subagent-wedge-backstop-blocks-nested-wu-workers
severity: P2
discovered: 2026-07-19
status: Concluded
written_by: harden-harness
---

# SubagentStop wedge-backstop false-fires on nested execute-plan WU workers — the predicate is cycle-scoped but not AGENT-scoped

**Status:** Concluded (root cause proven; **fix is OPERATOR-PARKED** — see
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md`, decision
`wedge-backstop-integrator-vs-worker-identity`). No fix has shipped. This spec is the durable
investigation record cited by hardening Round 108.

**Root-cause class:** hook-defect (predicate-scope gap on a NEW axis) + missing-contract (no
harness mechanism distinguishes the cycle integrator from its nested WU workers at
`SubagentStop`).

**Related:**
- Sibling facets of the SAME predicate, both FIXED: `adhoc-subagent-wedge-hook-overfires-globs-all-plans`
  (Round 99 — plan-WU half scoped to the active cycle's plan) and
  `subagent-wedge-backstop-dirty-tree-predicate-repo-wide` (Round 107 — git-dirty half scoped to
  the cycle's own item dir). Those two closed the **path/plan** scoping axis. This defect is a
  DISTINCT axis — **agent identity** — which neither addressed. Round 107's log entry explicitly
  flagged "a future third un-scoped input added to this predicate is an unambiguous trigger."
- Feature `subagent-wedge-backstop-hook` (origin); the pitfall was pre-identified in its
  `RESEARCH_SUMMARY.md` Q2 ("a child that intentionally leaves the tree dirty for a parent to
  integrate must not be force-spun") but the baseline's "confirm the predicate does not fire for a
  subagent whose lineage has no active plan" mitigation FAILS here: a nested execute-plan WU
  worker's lineage DOES have an active plan (it shares the integrator's cycle marker).

## Symptom (verified)

During the `hydra-overlay` phase-8.5 `execute-plan` cycle, `subagent-wedge-backstop.sh`
(`SubagentStop`) BLOCKED (exit 2, "commit your work and complete the plan…") **3 correctly-scoped,
non-committing WU sub-subagents** (great-grandchildren). Those workers were behaving exactly to
contract: they do their work unit and do NOT commit / do NOT tick the plan checkbox (the
execute-plan integrator commits and ticks after integrating). Reported by the cycle subagent.

The block is bounded to once per `agent_id` by the loop-guard breadcrumb, so each worker proceeded
on its second stop — **latent / non-blocking**, same severity profile as the two sibling facets. But
it reproduces on every `execute-plan` cycle that uses the workstation sub-subagent split, and each
worker must argue past a spurious force-spin.

## Reproduction

1. Under a live run marker, the orchestrator dispatches an `execute-plan` cycle. `execute-plan`
   declares `subagent-model: true` (`user/skills/execute-plan/SKILL.md:6`), so its cycle marker
   carries `subagent_model: True` and the dispatch guard's workstation sub-subagent exemption is
   armed.
2. The cycle **integrator** (grandchild) dispatches WU workers (great-grandchildren) via the Agent
   tool. Each allowed worker dispatch writes a `worker_subdispatch: true` deny-ledger event
   (`dispatch.append_worker_subdispatch_event`).
3. A WU worker finishes its unit and STOPS. `SubagentStop` fires (it fires at EVERY nesting level).
   At that instant the active cycle marker still names the non-terminal plan and the plan's WU
   checkboxes are still unchecked (the integrator has not ticked them yet), so
   `_active_plan_unchecked` returns `[unchecked>0]` → `plan_pending = True`. (If the worker also left
   uncommitted source, `_own_work_dirty` is `True` too; but `plan_pending` alone suffices — the
   predicate is `_own_work_dirty(...) OR plan_pending`.)
4. Predicate TRUE → BLOCK the worker's stop. The worker is NOT the integrator and legitimately owns
   no commit/completion duty → false-fire.

## Root cause (proven) — hook-defect + missing-contract

Rounds 99 and 107 scoped BOTH predicate inputs (plan-WU count, git-dirty) to the active cycle via
the cycle marker. But the cycle marker is a **cycle-level** object: the integrator AND every nested
WU worker it dispatches stop under the *same* marker, with the *same* non-terminal plan and *same*
unchecked WUs. So the now-correctly-cycle-scoped predicate still cannot tell **which agent** is
stopping. `plan_pending` is UNAVOIDABLY true for any worker that stops mid-cycle (the integrator
ticks only after all workers return), and there is no worker-specific on-disk tell — the integrator's
genuine-wedge state and a worker's normal mid-flight stop are byte-identical on disk.

Distinguishing them requires **agent identity / lineage**, which the harness does not have at
`SubagentStop`:

- The only documented, stable `SubagentStop` field is `agent_id` — unique per subagent at every
  nesting level, but **carrying no parent/depth/lineage** (feature `RESEARCH_SUMMARY.md`;
  `subagent-wedge-backstop.sh` header). `session_id` is shared across the whole session; `cwd` is
  shared. `stop_hook_active` is undocumented for `SubagentStop` and unused.
- `agent_id` is **hook-input-only** — it does not propagate to a subagent's own subprocess env
  (`markers.py` §CYCLE_REFUSED_OPS comment, lines ~2388–2394), so a subagent cannot self-record its
  own id.
- The `worker_subdispatch` deny-ledger events record the worker's *dispatch* `tool_use_id`, which
  has no documented correlation to the stopping `agent_id`.

Whether the platform exposes ANY lineage field on `SubagentStop` (a `parent_agent_id` / depth /
`parent_tool_use_id`) is **not documented in-repo** and confirming it requires dispatching the
`claude-code-guide` agent — which the harness-hardening agent is **prohibited from doing during a
marked run**. Per the skill's Step-2 platform-confirmation rule (whose ORIGIN is Round 81's
`SubagentStop`/`stop_hook_active` incident), load-bearing discrimination logic must NOT be shipped
on an unconfirmed platform field.

## Fix scope (operator-parked — design fork)

Every viable option to exempt nested WU workers while preserving integrator-wedge coverage falls
into a `/harden-harness` **hard-park carve-out** (structural divergence, coverage-semantics change,
or an unconfirmed-platform dependency), so nothing was implemented this round. The options are
enumerated with a recommendation in
`docs/specs/turn-routing-enforcement/NEEDS_INPUT.md`
(decision `wedge-backstop-integrator-vs-worker-identity`):

- **Option A (recommended): self-managed integrator-`agent_id` breadcrumb.** A PreToolUse hook
  (extend `lazy-cycle-containment.sh`, which already receives `agent_id`) records the FIRST
  `agent_id` seen under each cycle-marker generation as the integrator (keyed by the marker nonce);
  the wedge-backstop blocks ONLY when `stopping agent_id == recorded integrator agent_id`.
  Non-platform-dependent (documented `agent_id` + the serial-tool-call ordering the consumed-fence
  already relies on). Structural: new persistent breadcrumb + new PreToolUse recording seam +
  cross-hook predicate change.
- **Option B: platform lineage field** — block only the top-level integrator via a
  `parent_*`/depth field IF one exists. REQUIRES `claude-code-guide` confirmation; cannot ship on
  assumption (Round-81 rule).
- **Option C: broad `subagent_model` exemption** — allow the stop whenever
  `marker.subagent_model == True`. One line, non-dependent, ships now, but the wedge-backstop then
  never blocks an `execute-plan` integrator wedge (its PRIMARY target), leaning on the completion
  gate + `detect_cycle_bracket_friction` for that coverage. Coverage-reducing.

The `divergence` grade is `structural` (Option A adds state + a hook seam; Option C forks the
hook's coverage contract; Option B is platform-unconfirmed) → operator-owned park.
