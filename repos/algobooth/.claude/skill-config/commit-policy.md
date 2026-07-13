**Project policy: use the standard commit-and-push pattern.**

AlgoBooth has no project-specific commit conventions beyond the generic default — this file
is an explicit *adoption* of `~/.claude/skills/_components/commit-and-push.md`, not a fork.
Read that component and follow it verbatim:

1. `git status` — skip if clean.
2. Stage specific files (never `git add .`).
3. Conventional-commit message, no AI attribution, HEREDOC form matching the caller's
   context (phase batch / post-phase / spec decomposition — see the component for the exact
   message shapes).
4. AlgoBooth is a **personal** repo (`git config user.email` != `jacob@cognitoforms.com`) —
   push to `origin main` is allowed (no work-repo push block applies here).
5. On push failure: `git pull --rebase origin main`, retry once; a rebase conflict is a
   blocking issue.

This file exists so every skill that reads `.claude/skill-config/commit-policy.md` (the
read-then-fallback convention) succeeds on the first Read instead of falling back after a
failed lookup — see `docs/features/skill-config-schema-and-reference-lint/SPEC.md` D4 (the
377-failed-Read quick win). No behavior changes: the content is the same policy the fallback
component already specified.
