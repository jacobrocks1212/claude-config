# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace Overview

This is a workspace root containing ~30 independent git repositories, not a single project. Each repo has its own build system, language, and conventions. Many repos already have their own `CLAUDE.md` or `CLAUDE.local.md` — always check the target repo first.

A `scripts/` directory at the workspace root contains consolidated PowerShell diagnostic utilities (moved from individual repo roots).

Projects use `.claude/skill-config/` for project-specific quality gates and skill catalogs that are injected into user-level orchestration skills at runtime.

## Key Repositories

### Work (Cognito Forms)
- **Cognito Forms/** — Main product. Multi-tenant form builder. .NET Framework 4.7.2 backend + Vue 2.7/TypeScript/Nx frontend. Has extensive `CLAUDE.local.md` with build commands, architecture, and workflow skills. This is the most complex repo in the workspace.
- **Cognito Forms.wiki/** — Azure DevOps wiki content.
- **cognito-docs/** — Documentation sync repo.
- **Overwatch/** — Internal Cognito admin/monitoring tool (.NET).
- **mcp/** — Microsoft MCP servers (C# .NET).
- **model.js/** — Cognito reactive entity/type/property framework (remote `cognitoforms/model.js`). Treated as a **work** repo: path-matched to the work `includeIf`, commits as `jacob@cognitoforms.com`.

### Personal Projects
- **maestro/** — Tauri desktop app for orchestrating parallel Claude Code sessions in isolated git worktrees.
- **algobooth/** — Tauri desktop app for DJ workflow with Strudel live coding.
- **work-dashboard/** — Tauri desktop app for Azure DevOps task integration.
- **zen-mcp-server/** — MCP server project.
- **interview-prep-plugin/** — Claude Code plugin for passive SWE interview prep.
- **scene-remixer/** — Node.js project.
- **housing-locator/** — Node.js project.
- **semantic-docs/** — Semantic document processing pipeline with Gemini support.

### Tauri Apps Pattern
Three repos use **Tauri 2.0** (Rust backend + web frontend): `algobooth`, `maestro`, `work-dashboard`. When working in these, the `tauri-patterns` skill applies. Rust source lives in `src-tauri/`.

## Platform Notes

This is a **Windows 11** development machine. Key constraints:
- Use `$null` (PowerShell) or `NUL` (cmd) instead of `/dev/null`
- Use absolute Windows paths with backslashes in PowerShell, forward slashes in bash
- PowerShell is available via the PowerShell tool for Windows-native operations
- Git Bash is the default shell — Unix syntax works for most commands

## Git Identity

Two GitHub profiles are in use. The global `.gitconfig` defaults to the **personal** identity:

| Profile | Email | GitHub Account | Used For |
|---------|-------|----------------|----------|
| Personal (default) | jacobmadsen12321@gmail.com | jacobrocks1212 | All repos unless overridden |
| Work | jacob@cognitoforms.com | jacob-cognitoforms | Cognito Forms repos via `includeIf` |

Work repos are configured via `~/.gitconfig-cognitoforms` + `includeIf` directives in `~/.gitconfig`. When creating a new Cognito Forms-related repo, add an `includeIf` entry to `~/.gitconfig`.

### Credential helper mechanism

Both accounts live on the same host (`github.com`), so account selection is by **repo path**, not host. Resolution per context:

Both contexts use **Git Credential Manager (GCM)** with an explicitly *pinned* account, so git credentials are fully deterministic and never depend on gh's (mutable, global) active account:

- **Personal repos (default)** — global `~/.gitconfig` pins `username = jacobrocks1212`.
- **Work repos** — `~/.gitconfig-cognitoforms` (loaded via `includeIf` *after* the global block, so it wins for matched paths) overrides to `username = jacob-cognitoforms`.

  ```ini
  # global ~/.gitconfig — default/personal
  [credential "https://github.com"]
      helper =                       # reset the inherited helper chain
      helper = manager
      username = jacobrocks1212

  # ~/.gitconfig-cognitoforms — work override (includeIf-matched paths only)
  [credential "https://github.com"]
      helper =
      helper = manager
      username = jacob-cognitoforms
  ```

  GCM (the same helper Visual Studio uses) looks up the stored credential for the pinned username in Windows Credential Manager and returns it silently — no account picker. GCM holds **both** accounts' tokens, keyed by username.

**Guarantee:** in a personal repo, both the commit identity (`jacobmadsen12321@gmail.com`) *and* the push credential (`jacobrocks1212`) are personal regardless of what gh's active account happens to be. A push from a personal repo can never authenticate as the work account.

**Seeding / re-auth:** if GCM ever prompts or a push 401s (stored token rotated/expired), reseed the affected account from a repo of that type — or just let the GCM browser flow re-auth, which stores a fresh token:

```bash
# work (run from a work repo)
printf "protocol=https\nhost=github.com\nusername=jacob-cognitoforms\npassword=%s\n\n" \
  "$(gh auth token --user jacob-cognitoforms)" | git credential approve
# personal (run from a personal repo)
printf "protocol=https\nhost=github.com\nusername=jacobrocks1212\npassword=%s\n\n" \
  "$(gh auth token --user jacobrocks1212)" | git credential approve
```

**Why this design (history):** the previous helper was a bash script (`~/.git-credential-cognitoforms.sh`) that ran `gh auth switch` to flip the active account, fetch the credential, then switch back. That caused two failures: (1) Visual Studio couldn't run a `!bash …/.sh` helper on Windows, so it fell back to GCM's two-account picker and prompted every time; (2) the constant active-account flipping (plus personal repos depending on gh's active account) meant Claude Code's `gh` commands and personal pushes could run as the **wrong** account → **403s** / wrong attribution. The script is now orphaned and can be deleted.

**Remaining sharp edge — bare `gh` CLI commands:** path-based pinning governs **git credentials only**. Bare `gh` commands (`gh pr create`, `gh api`, the GitHub MCP fallback) still use gh's single global **active account**. So `git commit`/`git push` are always correct per repo, but a `gh` command run in the "wrong" repo type acts as whatever account is currently active. For deliberate cross-account CLI work, pass `gh … --user <account>` rather than relying on the active account.

## Claude Code Aliases

Two bash aliases in `~/.bashrc` select the appropriate config profile:

| Alias | Config dir | Use for |
|-------|-----------|---------|
| `claude-work` | `~/.claude` (default) | Cognito Forms and other work repos |
| `claude-personal` | `~/.claude-personal` | Personal projects |

### Skill File Relationship

Skills and components are **hardlinked** between `~/.claude/skills/` and `~/.claude-personal/skills/`. Editing a file in either location modifies both — there is no need to apply changes to both directories separately. When updating skills or components, edit once in either location and verify the other reflects the change.

## Claude Config (`claude-config/`)

All Claude Code configuration is authored in the **`claude-config/`** repo and projected to its live locations via symlinks. The files you edit at `~/.claude/`, `~/.claude-personal/`, this workspace `CLAUDE.md`, and per-repo `.claude/` directories are symlinks pointing back into `claude-config/`. Editing through a symlink writes through to the repo, so `git status` in `claude-config/` shows every config change across the machine in one place.

| Scope | Live location (symlink) | Repo source |
|-------|------------------------|-------------|
| User | `~/.claude/{skills,hooks,scripts,templates,CLAUDE.md,settings.json,...}` | `claude-config/user/` |
| Personal | `~/.claude-personal/CLAUDE.md` | `claude-config/personal/` |
| Workspace | `~/source/repos/CLAUDE.md` (this file) | `claude-config/workspace/CLAUDE.md` |
| Repos | `<repo>/.claude/{skill-config,skills,...}` and select root files | `claude-config/repos/<name>/` |

- **Source of truth:** `claude-config/manifest.psd1` defines every symlink mapping; `claude-config/setup.ps1` creates/verifies/repairs them (`.\setup.ps1 check` / `repair` / `bootstrap`).
- **Editing config:** the Edit tool refuses to write through a symlink — edit the real target inside `claude-config/` (e.g. `claude-config/repos/<name>/...`), not the symlinked path.
- **Consequence for per-repo skills:** skill and `.claude/` config files are not tracked by the host repo's git — they live in `claude-config`. `git status` in the host repo will never show them; commit those changes in `claude-config` instead.
- **Adding a repo:** create `claude-config/repos/<name>/.claude/`, add an entry under `Repos` in `manifest.psd1`, then run `.\setup.ps1 bootstrap -Target Repos`.
- See `claude-config/CLAUDE.md` for the full layout, skills system, components, and hooks.

## Work Repo Git Workflow

In work repos (`git config user.email == jacob@cognitoforms.com`):

- **Commits:** allowed locally (Claude can checkpoint freely)
- **Push:** blocked by a PreToolUse hook on the `Bash` tool
- **Squash-push:** Jacob explicitly invokes `/push "commit message"` which squashes all branch commits into one clean commit and pushes with a bypass token

The hook lives at `~/.claude/hooks/block-work-repo-git-push.sh`. Personal repos are unaffected.

## Navigation Pattern

When asked to work on a specific project, `cd` into that repo directory first and check for:
1. `CLAUDE.md` or `CLAUDE.local.md` at the repo root
2. `.claude/` directory for project-specific settings
3. Subdirectory-level `CLAUDE.local.md` files (Cognito Forms has these throughout)
