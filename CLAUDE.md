# claude-config

Canonical source for all authored Claude Code configuration. Files live here; symlinks at their expected locations (`~/.claude/`, `~/.claude-personal/`, per-repo `.claude/`) point back. Edits anywhere write through symlinks — `git status` in this repo shows changes immediately.

## Structure

- `user/` — User-level config symlinked from `~/.claude/` (skills, hooks, scripts, templates, settings)
- `personal/` — Desktop app config symlinked from `~/.claude-personal/`
- `workspace/` — Workspace root config symlinked from `~/source/repos/`
- `repos/` — Per-repo `.claude/` config (17 repos, each with its authored content)

## Setup

```powershell
# First time — moves live files into repo, creates symlinks
.\setup.ps1 bootstrap

# Verify all symlinks are intact
.\setup.ps1 check

# Fix broken symlinks (after clone or file moves)
.\setup.ps1 repair
```

Use `-Target User|Personal|Workspace|Repos` to scope operations.

## Manifest

`manifest.psd1` defines every symlink mapping. To track a new repo, add an entry and run `.\setup.ps1 bootstrap -Target Repos`.

## What's NOT tracked

Secrets (`*.env`, `.credentials.json`), ephemeral Claude Code state (`cache/`, `sessions/`, `pr-cache/`, `telemetry/`, etc.), and files already committed to their source repos.
