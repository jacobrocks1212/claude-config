### claude-config Commit Policy

- **Conventional Commits** — `type(scope): subject`. Types: `feat`, `fix`, `refactor`, `docs`,
  `test`, `chore`. Scope is the feature/skill/script area (e.g. `lazy-pipeline-visualizer`,
  `lazy-state`, `skills`).
- **No AI attribution.** Do NOT append `Co-Authored-By: Claude` or any "Generated with" footer.
  This matches the repo's existing commit history and the `/commit` skill convention.
- **Commit cadence** — commit after each completed plan part / phase (the lazy pipeline expects a
  clean tree between cycles). Keep commits scoped to one logical change.
- **Push** — allowed. claude-config is a personal config repo, not a work repo (the
  `block-work-repo-git-push` hook does not apply here). Push when a feature or coherent batch is
  complete.
- **Symlink awareness** — edits to `user/**`, `repos/**`, `personal/**`, `workspace/**` write
  through to live `~/.claude/` locations; `git status` in this repo reflects them directly.
