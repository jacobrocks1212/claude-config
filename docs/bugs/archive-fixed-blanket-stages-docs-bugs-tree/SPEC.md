# archive_fixed blanket-stages the entire docs/bugs tree — Bug Specification

**Status:** Concluded

**Severity:** P1 (concurrency-integrity — captures a foreign session's files into an archive commit)

**Discovered:** 2026-07-23

**Related:** `docs/specs/turn-routing-enforcement/` (hardening stage); prior-art fix
`end-of-run-flush-commit-absorbs-concurrent-writer-staged-files` (live commit `115a991a`),
embodied in `lazy_core/ledgers.py` `commit_flush_artifacts`.

## Verified Symptom

`lazy_core.gates.archive_fixed` step 7 (invoked via `bug-state.py --archive-fixed`, the
orchestrator's archive-on-fix path) stages and commits the entire `docs/bugs` subtree:

```python
to_stage = ["docs/bugs"] + result["repointed"]
add_proc = _git(repo_root, "add", "-A", "--", *to_stage)
...
commit_proc = _git(repo_root, "commit", "-m", f"fix({bug_id}): ...")   # bare, no pathspec
```

`git add -A -- docs/bugs` stages every untracked/modified file anywhere under `docs/bugs/`,
and the subsequent bare `git commit -m` (no pathspec) commits the whole index. Under the
shared-worktree concurrency that is normal in this workspace (multiple lazy/interactive
sessions share the claude-config checkout and its index), this sweeps a DIFFERENT session's
in-progress files into the archive commit.

**Observed impact (this session):** an unrelated bug's untracked
`docs/bugs/build-filtered-targets-nonexistent-cognito-sln/SPEC.md`, owned by a concurrent
session, was captured into an `--archive-fixed` commit. It was caught and evicted via a local
history rewrite before push, so nothing contaminated shipped — but the tool defect remains and
recurs under concurrent runs.

## Root Cause

**script-defect.** The archive commit was written to be maximally forgiving of partial state
(resume after a failed move, unstaged sentinel deletions) by staging the whole `docs/bugs`
tree and committing everything. That breadth is unsafe under a shared index: the operation
stages files it does not own. This is the exact class the sibling end-of-run flush already
fixed (`commit_flush_artifacts` in `ledgers.py`) — stage explicit owned pathspecs, then commit
with a trailing `-- <pathspec>` so a foreign file a concurrent writer already STAGED is left in
the index, never absorbed. `archive_fixed` never received that treatment.

## Fix Scope

Stage and commit ONLY the paths this archive operation owns:

- the moved bug's **source dir** (`spec_path`) — its staged rename-deletion, passed only as a
  **commit pathspec** (a `git add` of a vanished source path is fatal: `pathspec did not match`);
- the **`_archive/` destination** (`result["archived_to"]`);
- **`docs/bugs/queue.json`** when present (step 6's trim — an owned write that currently rides
  in only via the blanket `docs/bugs`);
- everything already in **`result["repointed"]`** (step 5's repointed `*.md` references).

Mechanics (empirically verified against git):
- `git add -- <dest> <queue-if-exists> <repointed>` (plain, not `-A`; the source deletion is
  already staged by the step-4 `git mv`).
- Scope the noop check: `git diff --cached --quiet -- <owned pathspecs incl source>` so a
  concurrent staged file no longer defeats the "nothing owned to commit" resume noop.
- `git commit -m <msg> -- <owned pathspecs incl source>` — a partial commit; a foreign file a
  concurrent writer already staged is left in the index, and untracked foreign files stay
  untracked. `queue.json` guarded by `.exists()` (a never-tracked pathspec aborts the whole
  commit even when siblings match).

The happy path stays byte-equivalent (clean tree, same commit message, evidence header,
repoint, queue trim). New unit coverage proves a concurrent file elsewhere under `docs/bugs/`
— both untracked AND pre-staged — is NOT captured by the archive commit.
