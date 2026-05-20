# claude-config

Canonical source for all Claude Code configuration. Files live here; symlinks at their expected locations (`~/.claude/`, `~/.claude-personal/`, per-repo `.claude/`) point back. Edits anywhere write through symlinks — `git status` in this repo shows changes immediately.

## Directory Layout

```
claude-config/
├── manifest.psd1          # Defines ALL symlink mappings (source of truth)
├── setup.ps1              # Creates/verifies/repairs symlinks
├── user/                  # → ~/.claude/
│   ├── CLAUDE.md          # User-level constitution (persona, coding style, platform rules)
│   ├── settings.json      # Model, permissions, hooks, status line config
│   ├── keybindings.json   # Keyboard shortcuts
│   ├── skills/            # 60+ user-level skills
│   │   └── _components/   # Shared building blocks injected into skills
│   ├── hooks/             # PreToolUse/PostToolUse shell hooks
│   ├── scripts/           # Python/PowerShell utilities
│   └── templates/         # Boilerplate generators
├── personal/              # → ~/.claude-personal/
│   └── CLAUDE.md          # Desktop app constitution
├── workspace/             # → ~/source/repos/CLAUDE.md
│   └── CLAUDE.md          # Cross-repo workspace documentation
├── repos/                 # → per-repo .claude/ directories
│   ├── algobooth/         # .claude/ contents for algobooth
│   ├── cognito-forms/     # .claude/ contents for Cognito Forms (most complex)
│   ├── strudel/           # .claude/ contents for strudel
│   └── ...                # 14 more repos
└── archived/              # Deprecated skills (audit trail)
```

## Symlink System

### How It Works

1. **Authoring:** All config is written in this repo
2. **Symlinks:** `setup.ps1` creates directory/file symlinks from live locations to this repo
3. **Write-through:** Editing `~/.claude/skills/lazy/SKILL.md` writes to `claude-config/user/skills/lazy/SKILL.md`
4. **Git tracking:** `git status` in this repo shows all changes across all linked locations

### Manifest (`manifest.psd1`)

Defines four symlink scopes:

| Scope | Live Location | Repo Location |
|-------|--------------|---------------|
| `User` | `~/.claude/{skills,hooks,scripts,templates,CLAUDE.md,settings.json,...}` | `user/` |
| `Personal` | `~/.claude-personal/CLAUDE.md` | `personal/` |
| `Workspace` | `~/source/repos/CLAUDE.md` | `workspace/` |
| `Repos` | `<repo>/.claude/{skill-config,skills,settings,...}` | `repos/<name>/.claude/` |

Per-repo entries support: `RootFiles` (at repo root), `DotClaudeFiles` (individual files in `.claude/`), `DotClaudeDirs` (directories in `.claude/`), and `Alias` (share config with another repo).

### Setup Commands

```powershell
.\setup.ps1 bootstrap               # First time — moves live files in, creates symlinks
.\setup.ps1 check                    # Verify all symlinks intact
.\setup.ps1 repair                   # Fix broken symlinks
.\setup.ps1 bootstrap -Target Repos  # Scope to repos only
```

### Adding a New Repo

1. Create `repos/<name>/.claude/` with desired files
2. Add entry to `manifest.psd1` under `Repos`
3. Run `.\setup.ps1 bootstrap -Target Repos`

## Skills System

### Skill Structure

Each skill lives at `user/skills/<name>/SKILL.md` with YAML frontmatter:

```yaml
---
name: skill-name
description: One-line purpose
argument-hint: <what to pass>
plan-mode: never | required | flag
model: opus | sonnet | haiku    # optional override
allowed-tools: [...]            # optional tool restrictions
---
```

### Component Injection

Skills share logic via `_components/`. The injection syntax:

```
!`cat ~/.claude/skills/_components/<name>.md`
```

At runtime, Claude Code expands this inline. The `project-skills.py` script pre-expands all injections for validation.

**Key components:**
- `task-tracking.md` — TaskCreate/TaskUpdate for compaction recovery
- `plan-file-output.md` — Writes plan files to `plans/` subdirs
- `quality-gates.md` — Project-specific build/test gates
- `subagent-launch.md` / `subagent-review.md` — Orchestrator+subagent execution model
- `tdd-protocol.md` / `tdd-test-agent.md` / `implementation-agent.md` — TDD pipeline
- `work-log.md` — Interview prep work logging

### Per-Repo Skill Config

Repos can customize skill behavior via `.claude/skill-config/`:

| File | Purpose |
|------|---------|
| `capabilities.txt` | Declares which namespaced components apply (e.g., `mcp`) |
| `quality-gates.md` | Repo-specific build/test commands |
| `commit-policy.md` | Commit message format, push rules |
| `skill-catalog.md` | Lists repo-scoped skills |

The `project-skills.py` script auto-discovers repos with `skill-config/` and produces per-repo projections.

### Repo-Scoped Skills

Some skills live in `repos/<name>/.claude/skills/` instead of `user/skills/`. These are only available when working in that repo. Examples:
- `repos/algobooth/.claude/skills/mcp-test/` — AlgoBooth-specific MCP testing
- `repos/algobooth/.claude/skills/lazy-cloud/` — cloud-environment variant of `/lazy`
- `repos/cognito-forms/.claude/skills/csharp-cognito/` — Cognito Forms C# patterns

### Coupled Skill Pairs

Some skills are **paired** — they share a state machine and must stay in sync. Editing one without the other silently breaks the pair's invariants.

| Pair | Files | Coupling rule |
|------|-------|---------------|
| `/lazy` ↔ `/lazy-cloud` | `user/skills/lazy/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` | Both are thin LLM wrappers around `user/scripts/lazy-state.py`; the state machine itself is the script. The skills' only intended divergence is whether they pass `--cloud` to the script. Any change to wrapper prose (status bookends, special-action handling, dispatch glue) MUST be mirrored. Any state-machine change goes into `lazy-state.py`, not the wrapper prose. When editing either, diff the other immediately afterward and confirm the diff matches what was intended. |
| `/lazy-batch` ↔ `/lazy-batch-cloud` | `user/skills/lazy-batch/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Both are autonomous orchestrators looping on `lazy-state.py`. Their only intended divergences (state script `--cloud` flag, `cloud-queue-exhausted` normal vs. defensive, `__write_deferred_non_cloud__` pseudo-skill, cycle subagent prompt's cloud-limitations block, `NEEDS_RESEARCH.md written_by` field) are tabulated in `/lazy-batch-cloud`'s "Differences from /lazy-batch" block. Any change to orchestration shape (cycle loop, hard constraints, terminal handling, max-cycles semantics) MUST be mirrored. |

When adding to a coupled pair, also update each file's State Machine Summary / orchestration shape at the bottom so the dispatch table reflects the new state.

## Scripts

| Script | Purpose |
|--------|---------|
| `project-skills.py` | Expands `!cat` component refs → `~/.claude/skills-projected/` |
| `lint-skills.py` | Validates skills: broken injections, embedded patterns, capabilities |
| `validate-plan.py` | Validates PHASES.md plan structure |
| `gemini-research.py` | Google Gemini deep research tool |
| `analyze_har.py` | HTTP Archive file analysis |
| `fix-line-endings.ps1` | CRLF/LF normalization (PostToolUse hook) |
| `run-eslint.ps1` | Auto-lint TypeScript/Vue on save (PostToolUse hook) |

### Lint Commands

```bash
python ~/.claude/scripts/lint-skills.py                           # Basic: broken/embedded patterns
python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities  # Full: cross-repo check
python ~/.claude/scripts/project-skills.py                        # Expand all skills → projected/
```

## Hooks

Hooks run before/after tool calls. Defined in `settings.json`, scripts in `user/hooks/`.

| Hook | Trigger | Purpose |
|------|---------|---------|
| `block-work-repo-git-push.sh` | PreToolUse (Bash) | Blocks `git push` in work repos |
| `block-terminal-kill.sh` | PreToolUse (Bash) | Blocks process/terminal termination (mobile workflow) |
| `block-work-repo-git-writes.sh` | PreToolUse (Bash) | Blocks destructive git in work repos |
| `pr-review-cache-guard.sh` | PreToolUse (Bash) | PR review caching guard |
| `fix-line-endings.ps1` | PostToolUse (Edit/Write) | Normalizes line endings |
| `run-eslint.ps1` | PostToolUse (Edit/Write) | Auto-lints Cognito Forms TS/Vue |

## What's NOT Tracked

- Secrets: `*.env`, `.credentials.json`, `settings.local.json` contents
- Ephemeral state: `cache/`, `sessions/`, `pr-cache/`, `telemetry/`
- Projected output: `skills-projected/` (generated by `project-skills.py`)
- Backups: `*.bak`
