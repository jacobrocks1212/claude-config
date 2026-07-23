---
kind: fixed
feature_id: archive-fixed-blanket-stages-docs-bugs-tree
date: 2026-07-23
provenance: backfilled-unverified
---

# Fixed

`lazy_core.gates.archive_fixed` step 7 now stages and commits only the paths the
archive operation owns (moved source dir, `_archive/` destination, `queue.json`,
repointed `*.md` refs) via an explicit `-- <pathspec>` partial commit, instead of a
blanket `git add -A -- docs/bugs` + bare `git commit`. A concurrent session's
untracked or already-staged file elsewhere under `docs/bugs/` is no longer absorbed.

**Fix commit:** f353684a

**Evidence:** new regression test
`test_archive_fixed_does_not_capture_concurrent_docs_bugs_files` (test_pseudo.py)
proves both an untracked AND a pre-staged concurrent file survive un-captured;
14/14 archive_fixed tests pass; full `test_lazy_core` suite 1354 passed (1 unrelated
Windows subprocess-spawn flake); `test_hooks.py` 295/295; `bug-state.py --fsck` clean.
