# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workspace Overview

This is a workspace root containing independent git repositories, not a single project. Each repo has its own build system, language, and conventions — always check the target repo's `CLAUDE.md` / `CLAUDE.local.md` first.

A `scripts/` directory at the workspace root contains consolidated PowerShell diagnostic utilities. Projects use `.claude/skill-config/` for project-specific quality gates and skill catalogs injected into user-level orchestration skills at runtime.

## Machines

This file is shared config (symlinked from `claude-config/workspace/CLAUDE.md`) and serves **two
Windows machines**. Check `whoami`/`hostname` when a path matters — the user differs per box:

| Machine | User | OS | Repos present | claude-config path |
|---------|------|----|--------------|--------------------|
| Work laptop | `JacobMadsen` | Windows 11 | Cognito Forms (+ -B/-C/-D worktrees), Overwatch, model.js, wiki/docs repos, claude-config | `C:\Users\JacobMadsen\source\repos\claude-config` |
| `DESKTOP-GHTC5K6` (personal workstation) | `Jacob` | Windows 10 Enterprise | claude-config, AlgoBooth (native + WSL twin) | `C:\Users\Jacob\source\repos\claude-config` |

**`DESKTOP-GHTC5K6` repo map** (see the setup runbook `C:\Users\Jacob\algobooth-windows-native-setup.md`):

| Repo | Windows (native) | WSL2 (`/home/jacob`) | Notes |
|------|------------------|----------------------|-------|
| AlgoBooth | `C:\Users\Jacob\repos\AlgoBooth` | `~/repos/AlgoBooth` | Native path is **deliberately outside** `~/source/repos` — real-WASAPI audio (`cpal`) + MSVC builds need a native path, never `\\wsl$\...`. Tooling that globs `~/source/repos/*` will miss it. |
| claude-config | `C:\Users\Jacob\source\repos\claude-config` | `~/repos/claude-config` | Windows checkout is the symlink target for `~/.claude/*` on this box. |

The WSL side is the phone-steerable harness (Tailscale); WSL audio falls back to `headless` mode —
the native Windows environment exists so MCP audio tools exercise a real device.

## Key Repositories

### Work (Cognito Forms — work laptop only)
- **Cognito Forms/** (+ **-B/-C/-D** worktrees) — Main product. Multi-tenant form builder. .NET Framework 4.7.2 backend + Vue 2.7/TypeScript/Nx frontend. Extensive `CLAUDE.local.md` with build commands, architecture, and workflow skills. The most complex repo in the workspace.
- **Cognito Forms.wiki/** — Azure DevOps wiki content.
- **cognito-docs/**, **cog-docs/** — Documentation sync / feature-docs repos.
- **Overwatch/** — Internal Cognito admin/monitoring tool (.NET).
- **model.js/** — Cognito reactive entity/type/property framework (remote `cognitoforms/model.js`). Treated as a **work** repo: path-matched to the work `includeIf`, commits as `jacob@cognitoforms.com`.

### Personal
- **claude-config/** — Canonical Claude Code configuration + the autonomous-pipeline harness (see below). Present on **both** machines.
- **AlgoBooth** (Tauri/Strudel DJ app) — live native checkout on `DESKTOP-GHTC5K6` at `C:\Users\Jacob\repos\AlgoBooth` (+ a WSL twin at `~/repos/AlgoBooth`; see the Machines table). NOT checked out on the work laptop — there, AlgoBooth work happens via cloud sessions and the nightly scheduled triggers only. (An older note here claimed AlgoBooth was cloud-only everywhere — stale since the 2026-06 native-Windows setup.)
- Other former personal repos (maestro, work-dashboard, scene-remixer, housing-locator, semantic-docs, zen-mcp-server) are no longer checked out locally; the work-logging plugin lives in `claude-config/user/plugins/local-tools/plugins/work-logging-plugin`.

## Platform Notes

Both machines are **Windows** development boxes (Windows 11 on the work laptop, Windows 10
Enterprise on `DESKTOP-GHTC5K6`):
- Use `$null` (PowerShell) or `NUL` (cmd) instead of `/dev/null`
- Absolute Windows paths with backslashes in PowerShell, forward slashes in bash
- Git Bash is the default shell — Unix syntax works for most commands

## Git Identity

Two GitHub profiles; the global `.gitconfig` defaults to **personal**:

| Profile | Email | GitHub Account | Used For |
|---------|-------|----------------|----------|
| Personal (default) | jacobmadsen12321@gmail.com | jacobrocks1212 | All repos unless overridden |
| Work | jacob@cognitoforms.com | jacob-cognitoforms | Cognito Forms repos via `includeIf` |

Work repos are configured via `~/.gitconfig-cognitoforms` + `includeIf` directives in `~/.gitconfig`; when creating a new Cognito-related repo, add an `includeIf` entry. Git **credentials** are deterministic per repo path: both scopes pin a GCM `username`, so a push from a personal repo can never authenticate as the work account. Full mechanism, seeding/re-auth recipes, and design history: `claude-config/docs/git-identity.md`.

**Remaining sharp edge — bare `gh` CLI commands:** path-based pinning governs **git credentials only**. Bare `gh` commands (`gh pr create`, `gh api`) use gh's single global **active account**, so a `gh` command run in the "wrong" repo type acts as whatever account is active. For deliberate cross-account CLI work, pass `gh … --user <account>`.

## Claude Code Profiles

Two bash aliases in `~/.bashrc` select the config profile:

| Alias | Config dir | Use for |
|-------|-----------|---------|
| `claude-work` | `~/.claude` (default) | Cognito Forms and other work repos |
| `claude-personal` | `~/.claude-personal` | Personal projects |

**Skills are one shared tree:** both `~/.claude/skills` and `~/.claude-personal/skills` are directory **symlinks** to `claude-config/user/skills` — a single source; one edit serves both profiles. (Historical docs said "hardlinked" — that is obsolete.)

## Claude Config (`claude-config/`)

All Claude Code configuration is authored in the **`claude-config/`** repo and projected to its live locations via symlinks. Editing through a symlink writes through to the repo, so `git status` in `claude-config/` shows every config change across the machine in one place.

| Scope | Live location (symlink) | Repo source |
|-------|------------------------|-------------|
| User | `~/.claude/{skills,hooks,scripts,templates,CLAUDE.md,settings.json,...}` | `claude-config/user/` |
| Personal | `~/.claude-personal/CLAUDE.md` | `claude-config/personal/` |
| Workspace | `~/source/repos/CLAUDE.md` (this file) | `claude-config/workspace/CLAUDE.md` |
| Repos | `<repo>/.claude/{skill-config,skills,...}` and select root files | `claude-config/repos/<name>/` |

- **Source of truth:** `claude-config/manifest.psd1` defines every symlink mapping; `claude-config/setup.ps1` creates/verifies/repairs them (`.\setup.ps1 check` / `repair` / `bootstrap`).
- **Editing config:** the Edit tool refuses to write through a symlink — edit the real target inside `claude-config/` (e.g. `claude-config/repos/<name>/...`), not the symlinked path.
- **Consequence for per-repo skills:** skill and `.claude/` config files are not tracked by the host repo's git — commit those changes in `claude-config` instead.
- **Adding a repo:** create `claude-config/repos/<name>/.claude/`, add an entry under `Repos` in `manifest.psd1`, then run `.\setup.ps1 bootstrap -Target Repos`.
- See `claude-config/CLAUDE.md` for the full layout, skills system, components, and hooks.

### Scheduled Autonomous Runs (nightly lazy)

Opted-in repos (claude-config, AlgoBooth) drain their lazy queues **nightly** via platform scheduled triggers — one `nightly-lazy-<repo>` trigger per repo, each firing a fresh cloud session that invokes the batch orchestrator with a bounded budget (`/lazy-batch-cloud 10 --park`; `/lazy-batch 10 --park` in claude-config). Collisions with live interactive runs are refused by run-marker arbitration (exit 3, zero side effects — never delete a marker to "fix" this); halts are parked and flushed at run end; MCP validation + receipt-gated completion still require a morning workstation `/lazy-batch` flush. Canonical docs (trigger template, recipes, failure/recovery playbook): `claude-config/docs/features/scheduled-autonomous-runs/`.

## Work Repo Git Workflow

In work repos (`git config user.email == jacob@cognitoforms.com`):

- **Commits:** allowed locally (Claude can checkpoint freely)
- **Push:** blocked by a PreToolUse hook (`~/.claude/hooks/block-work-repo-git-push.sh`); Jacob explicitly invokes `/push`, which pushes branch commits as-is with a bypass token (`/push --squash "msg"` to squash first). Personal repos are unaffected.

## Navigation Pattern

When asked to work on a specific project, `cd` into that repo first and check: (1) root `CLAUDE.md`/`CLAUDE.local.md`, (2) `.claude/` for project settings, (3) subdirectory `CLAUDE.local.md` files (Cognito Forms has these throughout).
