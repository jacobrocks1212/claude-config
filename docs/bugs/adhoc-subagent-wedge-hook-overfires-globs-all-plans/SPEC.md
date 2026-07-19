---
kind: bug-investigation
bug_id: adhoc-subagent-wedge-hook-overfires-globs-all-plans
severity: P2
discovered: 2026-07-18
status: Fixed
written_by: harden-harness
---

# SubagentStop wedge-backstop over-fires: counts unchecked WUs in stray plans

**Status:** Fixed

**Fix:** `subagent-wedge-backstop.sh::_active_plan_unchecked` now scopes the
plan-WU signal to ONLY the active cycle's plan (via the cycle marker's
`sub_skill == execute-plan` + `sub_skill_args`); a non-execute-plan cycle
resolves no plan and never trips. Two regression tests added. Shipped
out-of-pipeline via harden Round 99, commit `bd0948bc` (gated: `test_hooks`
268/268). Receipt provenance: backfilled-unverified (hook fix, no MCP surface).

**Related:** feature `subagent-wedge-backstop-hook` (origin); `user/hooks/CLAUDE.md`;
`docs/specs/turn-routing-enforcement/` (hardening stage, Round 99); origin — observed live
during the `concurrent-worktree-agent-coordination` `/lazy-batch` run, 2026-07-18 (a `/spec`
cycle with a pre-existing `plans/realign-2026-07-18.md` on disk). Supersedes the
`ADHOC_BRIEF.md` stub in this dir.

## Symptom (verified)

On a `/spec`, research, or realign cycle (a cycle that owns NO `/execute-plan` plan), the
`subagent-wedge-backstop.sh` SubagentStop hook BLOCKS the cycle subagent's stop (exit 2,
"commit your work and complete the plan"), forcing the subagent to argue past a spurious
stop-block. The block is bounded to once per `agent_id` by the loop-guard breadcrumb, but
it is pipeline-wide friction on every clean cycle in a multi-plan repo.

## Reproduction Steps

1. In a repo carrying ≥1 non-terminal plan the current cycle is NOT executing (a
   `plans/realign-<date>.md`, a prior part's plan) with an unchecked `- [ ] WU-…` row.
2. Run a `/spec` cycle (or any non-`execute-plan` cycle) under a live run marker; the tree
   is dirty (a `/spec` cycle writes SPEC.md by nature).
3. At SubagentStop, the hook globs `docs/{features,bugs}/*/plans/*.md`, finds the stray
   non-terminal plan, counts its unchecked WU > 0 (`plan_pending`), and — combined with the
   dirty tree — the predicate is TRUE → BLOCK.

## Root cause (proven) — hook-defect

`subagent-wedge-backstop.sh`'s `_active_plan_unchecked` predicate helper resolves "the
active plan" by globbing **every** `docs/{features,bugs}/*/plans/*.md` in the repo and
counting unchecked WU checkboxes in any non-terminal (not Complete/Superseded/Draft) plan.
The SubagentStop hook input carries no plan identity, so the helper over-broadens to ALL
plans on disk — including plans the just-stopped cycle is not executing. A `/spec` /
research / realign cycle owns no `/execute-plan` plan at all, yet a stray `plans/*.md` makes
`active` non-empty, and the git-dirty half of the predicate then trips the block.

The correct plan identity IS available on disk: the cycle-subagent marker
(`lazy-cycle-active.json`, written by `--cycle-begin` immediately before every Agent dispatch
and cleared only later by `--cycle-end`, so present at SubagentStop) carries `sub_skill` and
`sub_skill_args` — for an `execute-plan` cycle, `sub_skill_args`'s leading token is the plan
path (the same field `lazy_core._execute_plan_commit_budget` already reads).

## Fix scope

Scope the predicate's plan-WU signal to ONLY the plan the ACTIVE cycle is executing:

- Read the cycle marker (`lazy_core.read_cycle_marker`). When `sub_skill == "execute-plan"`
  and `sub_skill_args` names a plan, count unchecked WUs in THAT plan only (status not
  Complete/Superseded/Draft), resolving the plan path relative to `repo_root`.
- When the active cycle is NOT `execute-plan` (`/spec`, research, realign, `/plan-*`), or the
  cycle marker is absent/unreadable, the plan-WU signal contributes nothing (empty list) →
  the caller's `if not active: _allow()` biases to false-negative, per the operator steer. A
  stray `plans/*.md` the current cycle is not executing can never trip the hook.

The wedge backstop's genuine purpose is preserved: during an `execute-plan` cycle the cycle
marker names exactly that plan, so a real execute-plan wedge (dirty tree OR unchecked WUs in
its own plan) still BLOCKS once. Fail-open on every error path is retained.

Regression tests: (1) a non-`execute-plan` cycle marker + a stray non-terminal plan + dirty
tree → ALLOW (red on the glob-all predicate, green on the scoped predicate); (2) an
`execute-plan` cycle marker naming a plan with an unchecked WU + a CLEAN tree → BLOCK
(proving the scoped plan-WU signal still catches a genuine wedge). Existing block-path tests
are updated to write the cycle marker naming the plan (they implicitly relied on glob-all).
