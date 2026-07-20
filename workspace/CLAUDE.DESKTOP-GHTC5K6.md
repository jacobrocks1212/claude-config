# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code under this
workspace root on **DESKTOP-GHTC5K6** (the personal workstation, user `Jacob`). It is projected
to `~/source/repos/CLAUDE.md` on THIS machine only, via the `Machine = 'DESKTOP-GHTC5K6'` entry
in `claude-config/manifest.psd1`; the machine-agnostic `workspace/CLAUDE.md` serves the work
laptop.

## Machine Overview

- **OS:** Windows 10 Enterprise (10.0.19045) — NOT Windows 11 (that's the work laptop).
- **User:** `Jacob` (home `C:\Users\Jacob`). The work laptop's user is `JacobMadsen` — any doc
  or script hard-coding `C:\Users\JacobMadsen\...` refers to the OTHER box.
- **WSL2:** Ubuntu at `/home/jacob` — the phone-steerable harness side (Tailscale). WSL audio
  falls back to `headless` mode; the native Windows environment exists so AlgoBooth MCP audio
  tools exercise a real WASAPI device.
- **Shell:** Git Bash is the default; use `$null` (PowerShell) or `NUL` (cmd) instead of
  `/dev/null`. Absolute Windows paths with backslashes in PowerShell, forward slashes in bash.

## Repo Map (this box)

| Repo | Windows (native) | WSL2 (`/home/jacob`) | Notes |
|------|------------------|----------------------|-------|
| claude-config | `C:\Users\Jacob\source\repos\claude-config` | `~/repos/claude-config` | Canonical Claude Code config + the autonomous-pipeline harness. The Windows checkout is the symlink target for `~/.claude/*` on this box. |
| AlgoBooth | `C:\Users\Jacob\repos\AlgoBooth` | `~/repos/AlgoBooth` | Tauri/Strudel DJ app. The native path is **deliberately outside** `~/source/repos` — real-WASAPI audio (`cpal`) + MSVC builds need a native path, never `\\wsl$\...`. Tooling that globs `~/source/repos/*` will MISS it. Setup runbook: `C:\Users\Jacob\algobooth-windows-native-setup.md`. |

`~/source/repos` on this box contains ONLY `claude-config/` (+ this projected `CLAUDE.md`). No
work (Cognito Forms) repos exist here — Cognito work happens on the work laptop; don't look for
`Cognito Forms/`, `Overwatch/`, or their worktrees on this machine.

## Git Identity (verified on this box)

Single personal profile — `~/.gitconfig` sets `user.name = jacobrocks1212`,
`user.email = 66210812+jacobrocks1212@users.noreply.github.com`; credentials via the GitHub CLI
helper (`gh auth git-credential`). There are **no work `includeIf` directives** on this box
(unlike the work laptop) — do not apply the work-laptop git-identity/`gh`-account guidance here.
Remotes: `github.com/jacobrocks1212/{AlgoBooth,claude-config}`.

## Claude Config (`claude-config/`)

Same projection system as everywhere: all Claude Code configuration is authored in
`C:\Users\Jacob\source\repos\claude-config` and projected to its live locations via symlinks.
Editing through a symlink writes through to the repo, so `git status` in `claude-config/` shows
every config change on this machine in one place.

| Scope | Live location (symlink) | Repo source |
|-------|------------------------|-------------|
| User | `~/.claude/{skills,hooks,scripts,templates,CLAUDE.md,settings.json,...}` | `claude-config/user/` |
| Personal | `~/.claude-personal/CLAUDE.md` | `claude-config/personal/` |
| Workspace | `~/source/repos/CLAUDE.md` (this file) | `claude-config/workspace/CLAUDE.DESKTOP-GHTC5K6.md` |
| Repos | `<repo>/.claude/{skill-config,skills,...}` and select root files | `claude-config/repos/<name>/` |

- **Source of truth:** `claude-config/manifest.psd1` defines every symlink mapping;
  `setup.ps1` / `setup.py` create/verify/repair them (`.\setup.ps1 check` /
  `python3 setup.py check` / `repair` / `bootstrap`). Entries may carry an optional
  `Machine = '<hostname>'` key — this file's entry is keyed to `DESKTOP-GHTC5K6`.
- **AlgoBooth's `.claude/` symlinks** resolve from `claude-config/repos/algobooth/` with NO
  manifest `Repos` entry (deliberate — the manifest is shared with the work laptop, where the
  repo doesn't exist; see the comment block in `manifest.psd1`). The live repo here already
  carries its symlinks; on a fresh checkout use
  `python3 setup.py bootstrap --target Repos --repos-root <root>`.
- **Editing config:** the Edit tool refuses to write through a symlink — edit the real target
  inside `claude-config/` (e.g. `claude-config/repos/<name>/...`), not the symlinked path.
- See `claude-config/CLAUDE.md` for the full layout, skills system, components, and hooks.

### Scheduled Autonomous Runs (nightly lazy)

Opted-in repos (claude-config, AlgoBooth) drain their lazy queues **nightly** via platform
scheduled triggers — one `nightly-lazy-<repo>` trigger per repo, each firing a fresh cloud
session that invokes the batch orchestrator with a bounded budget (`/lazy-batch-cloud 10 --park`;
`/lazy-batch 10 --park` in claude-config). Collisions with live interactive runs are refused by
run-marker arbitration (exit 3, zero side effects — never delete a marker to "fix" this).
Canonical docs: `claude-config/docs/features/scheduled-autonomous-runs/`.

### Concurrent-writer coordination (this shared worktree is multi-writer-safe)

This claude-config worktree has **robust multi-writer coordination** from the shipped
`concurrent-worktree-agent-coordination` feature: the FIFO per-item file-lock
(`user/scripts/lazy_coord.py` `acquire_item_lock`/`release_item_lock`; PowerShell plane
`concurrent-lock.ps1`; one documented grammar in
`user/skills/_components/concurrent-lock-contract.md`) **+ git-safety + conflict-routing**
(`lazy_core.py`) serialize *genuine* write contention and halt only on a **true SEMANTIC
conflict**. Multiple sanctioned writers (a `/lazy-batch-parallel` lane, a background
`/harden-harness` dispatch, a second interactive/scheduled session) legitimately commit to this
same branch at once.

- **The orchestrator must NOT pre-serialize or delay a dispatch on the MERE POSSIBILITY of write
  contention** — e.g. do not hold a background `/harden-harness` or other concurrent worker until
  an in-flight cycle's boundary "just in case." Dispatch concurrently and trust the coordination
  layer; an unexpected incoming commit / moved HEAD is **EXPECTED, not a defect**. This is the
  local restatement of the user-global `<orchestration>` "Concurrent-writer awareness" block and
  `/lazy-batch` **HARD CONSTRAINT 11** ("no monsters-in-the-closet serialization",
  `user/skills/lazy-batch/SKILL.md`) — see those for the full policy; this note does not duplicate it.
- **The ONE real caveat that DOES need care — the single-slot cycle-active marker**
  (`~/.claude/state/lazy-cycle-active.json`): a concurrently-dispatched background worker must
  **NOT open a competing `--cycle-begin` bracket** while an in-flight cycle holds it — that
  clobbers the running cycle's `--cycle-end` accounting. Dispatch the concurrent worker via the
  **registered emit-dispatch path WITHOUT a competing bracket** instead.

## Navigation Pattern

When asked to work on a specific project, `cd` into that repo first and check: (1) root
`CLAUDE.md` / `CLAUDE.local.md`, (2) `.claude/` for project settings. Remember AlgoBooth lives
at `C:\Users\Jacob\repos\AlgoBooth`, NOT under `~/source/repos`.
