# CLAUDE.md — repos/

Each subdirectory is the `.claude/` payload for one repo under `~/source/repos/<name>/`.
`setup.ps1` symlinks `repos/<name>/.claude/` into the live repo per `manifest.psd1`, so edits
here write through to that repo's `.claude/`.

> **Edit the real file here, not the symlink.** The Edit tool refuses to write through a symlink.
> To change a repo's config, edit `claude-config/repos/<name>/.claude/...` directly — never the
> symlinked `<repo>/.claude/...` path.

## Anatomy of a repo's .claude/

A repo declares only what it needs:

| Path | Purpose |
|------|---------|
| `skill-config/` | Per-repo skill customization (see below) |
| `skills/` | Repo-scoped skills, available only in this repo (e.g. `lazy-cloud`, `csharp-cognito`) |
| `settings.json` | Repo-scoped hooks / permissions (e.g. cognito-forms registers `format-frontend.ps1`) |
| `settings.local.json` | Uncommitted local overrides |
| `commands/`, `knowledge/` | Optional repo extras |
| `CLAUDE.md` | Repo constitution (at repo root via `RootFiles`, or inside `.claude/`) |

## skill-config/ files

These tune shared skills per repo. The generic component under `user/skills/_components/` is the
fallback; a same-named file here wins (see `_components/CLAUDE.md`).

| File | Role | Typical |
|------|------|---------|
| `capabilities.txt` | Declares namespaced component sets (e.g. `mcp`) | common |
| `quality-gates.md` | Repo build/test commands | common |
| `commit-policy.md` | Commit format + push rules | common |
| `skill-catalog.md` | Lists repo-scoped skills | common |
| `mcp-tool-catalog.md`, `phases-runtime-validation.md`, … | Repo-specific audit/validation overrides | bespoke |

AlgoBooth is the most fully-configured repo (~18 skill-config files) and the reference for a
maximal setup; `finances` / `housing-locator` are minimal.

## Adding a repo

1. Create `repos/<name>/.claude/` with the files the repo needs (start minimal —
   `capabilities.txt`, `quality-gates.md`).
2. Add an entry under `Repos` in `manifest.psd1` (`RootFiles` / `DotClaudeFiles` /
   `DotClaudeDirs` / `Alias`).
3. `.\setup.ps1 bootstrap -Target Repos`.

## Coupled with user-level skills

`repos/algobooth/.claude/skills/lazy-cloud` and `lazy-batch-cloud` are the cloud halves of
coupled pairs whose other half lives in `user/skills/`. Mirror changes across both — see
`user/skills/CLAUDE.md`.
