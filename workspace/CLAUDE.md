# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace Overview

This is a workspace root containing ~30 independent git repositories, not a single project. Each repo has its own build system, language, and conventions. Many repos already have their own `CLAUDE.md` or `CLAUDE.local.md` — always check the target repo first.

A `scripts/` directory at the workspace root contains consolidated PowerShell diagnostic utilities (moved from individual repo roots).

Projects use `.claude/skill-config/` for project-specific quality gates and skill catalogs that are injected into user-level orchestration skills at runtime.

## Key Repositories

### Work (Cognito Forms)
- **Cognito Forms/** — Main product. Multi-tenant form builder. .NET Framework 4.7.2 backend + Vue 2.7/TypeScript/Nx frontend. Has extensive `CLAUDE.local.md` with build commands, architecture, and workflow skills. This is the most complex repo in the workspace.
- **Cognito Forms-side-repo/** — Mirror of Cognito Forms for parallel worktree experiments.
- **Cognito Forms.wiki/** — Azure DevOps wiki content.
- **cognito-docs/** — Documentation sync repo.
- **Overwatch/** — Internal Cognito admin/monitoring tool (.NET).
- **mcp/** — Microsoft MCP servers (C# .NET).

### Personal Projects
- **maestro/** — Tauri desktop app for orchestrating parallel Claude Code sessions in isolated git worktrees.
- **algobooth/** — Tauri desktop app for DJ workflow with Strudel live coding.
- **work-dashboard/** — Tauri desktop app for Azure DevOps task integration.
- **zen-mcp-server/** — MCP server project.
- **interview-prep-plugin/** — Claude Code plugin for passive SWE interview prep.
- **model.js/** — Standalone fork/version of the Cognito reactive entity/type/property framework.
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

## Claude Code Aliases

Two bash aliases in `~/.bashrc` select the appropriate config profile:

| Alias | Config dir | Use for |
|-------|-----------|---------|
| `claude-work` | `~/.claude` (default) | Cognito Forms and other work repos |
| `claude-personal` | `~/.claude-personal` | Personal projects |

### Skill File Relationship

Skills and components are **hardlinked** between `~/.claude/skills/` and `~/.claude-personal/skills/`. Editing a file in either location modifies both — there is no need to apply changes to both directories separately. When updating skills or components, edit once in either location and verify the other reflects the change.

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
