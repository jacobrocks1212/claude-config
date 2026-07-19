---
kind: bug-investigation
bug_id: subagent-wedge-backstop-dirty-tree-predicate-repo-wide
severity: P2
discovered: 2026-07-19
status: Fixed
written_by: harden-harness
---

# SubagentStop wedge-backstop dirty-tree predicate is repo-wide — false-fires on concurrent-writer / foreign-lane residue

**Status:** Fixed
**Fixed:** 2026-07-19
**Fix commit:** 24d48e43
**Root-cause class:** hook-defect

**Fix scope (concluded):** scope the wedge-backstop's git-dirty half to the STOPPING
agent's own work — a dirty path under `docs/` that is NOT under the active cycle's own
pipeline-item dir is another writer's bookkeeping residue, never the stopping agent's
incomplete work. Non-`docs/` (source) dirt and the cycle's own item dir still count.
Preserve the fail-OPEN posture and the block-at-most-once loop-guard.

**Related:** sibling defect `docs/bugs/_archive/adhoc-subagent-wedge-hook-overfires-globs-all-plans`
(fixed the plan-WU-glob half of the SAME predicate; this is the git-dirty half); feature
`subagent-wedge-backstop-hook` (origin); `user/hooks/CLAUDE.md`;
`docs/specs/turn-routing-enforcement/` (hardening stage, Round 107). Origin — observed live
during a `/lazy-batch` run in the now-normal concurrent-writer regime (multiple agents committing
to the shared claude-config worktree).

## Symptom (verified)

`subagent-wedge-backstop.sh` BLOCKED a dispatched grandchild subagent's stop (exit 2) even
though the grandchild's own 3 changed files were already correctly committed and landed. The
block fired purely on the DIRTY-TREE half of the wedge predicate, because a FOREIGN uncommitted
file — a concurrent lane's residue (e.g. `docs/provenance-index.json` or a
`docs/features/<other-slug>/IMPLEMENTED.md` left by a concurrent mark-complete/mark-fixed
cycle) — made `git status --porcelain` report the whole tree dirty. The whole-tree dirty read
attributed another writer's uncommitted bookkeeping to the stopping agent as if it were the
agent's own incomplete work.

It blocks AT MOST ONCE (the `agent_id`-keyed loop-guard breadcrumb is intact), so it did NOT
strand this cycle — the grandchild's second stop allowed. Latent / non-blocking, but a
reproducible logic gap that recurs on every concurrent run.

## Reproduction Steps

1. A `/lazy-batch` run dispatches an execute-plan cycle; the cycle marker
   (`lazy-cycle-active.json`) names an active, non-terminal plan whose WU checkboxes are all
   checked (`plan_pending` false).
2. A concurrent lane / cycle (sanctioned concurrent writer) leaves an uncommitted pipeline
   artifact in the shared worktree — e.g. `docs/provenance-index.json` or
   `docs/features/<other-slug>/IMPLEMENTED.md`.
3. The execute-plan cycle's grandchild subagent finishes and commits its OWN work, then stops.
4. `subagent-wedge-backstop.sh` runs its predicate: marker present + active non-terminal plan +
   `_git_dirty(repo_root)` reads the WHOLE tree → sees the foreign residue → returns True →
   BLOCKS the stop.

## Root cause (proven — hook-defect)

`user/hooks/subagent-wedge-backstop.sh`, embedded-python `_git_dirty(repo_root)`:

```python
def _git_dirty(repo_root):
    out = subprocess.run(["git", "-C", repo_root, "status", "--porcelain"], ...)
    ...
    return bool(out.stdout.strip())
```

This is a WHOLE-TREE dirty read with no attribution. The wedge predicate is:

```python
if not (_git_dirty(repo_root) or plan_pending):
    _allow()
```

Under the sanctioned concurrent-writer regime (user/CLAUDE.md `<orchestration>` —
"other agents may be working this same worktree/branch concurrently — an unexpected commit /
moved HEAD is expected, not a defect"), ANY foreign uncommitted file trips `_git_dirty`, so the
git-dirty half of the predicate cannot distinguish the stopping agent's own incomplete work
from a concurrent lane's uncommitted bookkeeping. This is the DIRECT ANALOG of the sibling
`adhoc-subagent-wedge-hook-overfires-globs-all-plans` defect (which fixed the plan-WU half by
scoping it to the active cycle's OWN plan via the cycle marker) — the git-dirty half was left
repo-wide.

## Fix scope (concluded)

Replace `_git_dirty(repo_root)` with `_own_work_dirty(repo_root, own_item_dir)`:

- Derive the active cycle's own pipeline-item dir (`docs/features/<slug>` or
  `docs/bugs/<slug>`) from the resolved plan path already in hand (`sub_skill_args`).
- A dirty porcelain entry is FOREIGN (concurrent-lane residue, ignored) iff it lives under
  `docs/` but NOT under the active cycle's own item dir — this is a purely STRUCTURAL rule
  (the pipeline's shared bookkeeping tree `docs/` is a concurrent-writer battleground; a
  stopping agent's own pending work there is confined to its own item directory), with NO
  incident-literal filename denylist. It captures the named residue exactly: a foreign
  `docs/features/<other>/IMPLEMENTED.md` and the shared `docs/provenance-index.json` are both
  under `docs/` and outside the own item dir.
- Every non-`docs/` path (source files the agent edited) and the cycle's own item dir still
  count as OWN pending work, so genuine own-source wedge detection is PRESERVED.
- Fail-OPEN posture and block-at-most-once loop-guard unchanged.

Regression tests added in `test_hooks.py` (`test_wedge_*`): foreign-residue-only → allow;
own-source dirt → block; own-item-dir dirt → block (non-vacuity — proves the scoping did not
neuter own-work detection).
