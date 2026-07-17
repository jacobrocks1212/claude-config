### claude-config Commit Policy

- **Conventional Commits** — `type(scope): subject`. Types: `feat`, `fix`, `refactor`, `docs`,
  `test`, `chore`. Scope is the feature/skill/script area (e.g. `lazy-pipeline-visualizer`,
  `lazy-state`, `skills`).
- **No AI attribution.** Do NOT append `Co-Authored-By: Claude` or any "Generated with" footer.
  This matches the repo's existing commit history and the `/commit` skill convention.
- **Commit cadence** — commit after each completed plan part / phase (the lazy pipeline expects a
  clean tree between cycles). Keep commits scoped to one logical change.
- **Push — ALWAYS keep the remote in sync (HARD REQUIREMENT).** claude-config is a personal config
  repo, not a work repo (the `block-work-repo-git-push` hook does not apply here), so its
  `origin/main` MUST NOT lag local `main`: **`git push` after every commit** (or immediately after a
  coherent batch of commits in the same turn). Never leave a claude-config commit unpushed. This is
  the OPPOSITE of the work-repo policy (AlgoBooth / cognito), where push is operator-gated via
  `/push` — here, if you commit, you push. Any skill/component prose that says "commits stay local"
  or "the operator owns pushes" for claude-config is superseded by this rule.
- **Symlink awareness** — edits to `user/**`, `repos/**`, `personal/**`, `workspace/**` write
  through to live `~/.claude/` locations; `git status` in this repo reflects them directly.
- **`LAZY_QUEUE.md` regen (mobile-queue-control)** — before each per-cycle commit, the orchestrator
  runs `python user/scripts/lazy-queue-doc.py --repo-root <repo>` so the regenerated root-level
  `LAZY_QUEUE.md` (the GitHub-mobile-readable queue status doc) is staged by the existing `git add -A`
  and rides the cycle's commit on `main`. The generator is a PURE read over on-disk lazy state — it
  embeds no wall-clock, so an unchanged-state regen is byte-identical and adds nothing to the commit
  (no spurious diff). It is orchestrator-invoked only — NEVER called from the `lazy-state.py` /
  `bug-state.py` compute path (preserves "pure read, never writes during a probe").
