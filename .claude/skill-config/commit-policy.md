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
- **`LAZY_QUEUE.md` regen (mobile-queue-control)** — before each per-cycle commit, the orchestrator
  runs `python user/scripts/lazy-queue-doc.py --repo-root <repo>` so the regenerated root-level
  `LAZY_QUEUE.md` (the GitHub-mobile-readable queue status doc) is staged by the existing `git add -A`
  and rides the cycle's commit on `main`. The generator is a PURE read over on-disk lazy state — it
  embeds no wall-clock, so an unchanged-state regen is byte-identical and adds nothing to the commit
  (no spurious diff). It is orchestrator-invoked only — NEVER called from the `lazy-state.py` /
  `bug-state.py` compute path (preserves "pure read, never writes during a probe").
