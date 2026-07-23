---
kind: adhoc-brief
bug_id: adhoc-lazy-core-broad-git-staging-guard
enqueued_by: lazy-adhoc
date: 2026-07-23
---

# Ad-hoc bug: Guard broad git-staging in shared-checkout lazy_core commit sites

A regression guard preventing reintroduction of the broad git-add-dash-A-dir plus bare pathspec-less git-commit pattern in lazy_core write-paths that commit in the shared claude-config checkout, which absorbs a concurrent session untracked or staged files into an unrelated commit. Two instances hit this class and were both fixed by converting to explicit-pathspec partial commits: ledgers.commit_flush_artifacts (end-of-run-flush-commit-absorbs-concurrent-writer-staged-files) and gates.archive_fixed step 7 (archive-fixed-blanket-stages-docs-bugs-tree). Add a mechanical check (doc-drift-lint or a test over lazy_core) that flags any new commit site pairing a broad directory-wide git add with a bare pathspec-less commit in a shared-checkout writer, so the third occurrence is caught structurally rather than by another live incident. Class boundary: only lazy_core write-paths that git-commit in the shared claude-config checkout; explicitly out of scope are single-item-scoped adds like the archive step-3 add of the bug own dir.
