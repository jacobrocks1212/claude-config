# claude-config

Canonical source for all Claude Code configuration. Files live here; symlinks at their expected locations (`~/.claude/`, `~/.claude-personal/`, per-repo `.claude/`) point back. Edits anywhere write through symlinks — `git status` in this repo shows changes immediately.

## Mission

This repo is the **harness for Jacob's autonomous agentic development system**. The end goal: the most **efficient, effective, and best-practice-aligned software builder** we can construct from Claude Code primitives (skills, components, state scripts, hooks, sentinels).

Every change to this repo should be evaluated against that goal:

- **Efficient** — minimize wasted tokens, redone work, and orchestrator boilerplate. Deterministic script-owned state (`lazy-state.py` / `bug-state.py`) over LLM-inferred state; script-emitted prompts over hand-composed ones; gates that refuse early over reviews that catch late.
- **Effective** — features and fixes ship with real, certified evidence (gated receipts, MCP validation, runtime-spike artifacts), not narrative claims. Integrity gates are load-bearing: a bypass found in a retro is a defect in the harness, not an acceptable workaround.
- **Best-practice-aligned** — TDD, spec-first development, distributed verification, honest BLOCKED/NEEDS_INPUT halts, and audit-grade provenance on every completion. When the harness and best practice conflict, fix the harness.

The harness **self-improves**: retros (`/lazy-batch-retro`), investigations (`/investigate`), and the routing/hardening stage feed observed friction back into this repo as contract changes. Friction observed in a run is a bug report against this repo.

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
- `adhoc-enqueue.md` — Shared `/lazy*` ad-hoc enqueue protocol (`--adhoc`): prepends an item to `queue.json` via `lazy-state.py --enqueue-adhoc`, seeds `ADHOC_BRIEF.md`, adds a ROADMAP row. Injected into all four `/lazy*` skills. **Type-aware (`unified-pipeline-orchestrator` Phase 3):** `--type {feature|bug}` (default `feature` — byte-identical when omitted) selects the destination pipeline; `--type bug` routes into `docs/bugs/queue.json` via the existing `bug-state.py` enqueue + seeds `docs/bugs/<slug>/`, for harden-harness spin-offs and other defect items.
- `mcp-coverage-audit.md` — Gates `__mark_complete__` (feature pipeline) and `__mark_fixed__` (bug pipeline) across the `/lazy*` family: **Gate 1** in `/lazy` + `/lazy-cloud` + `/lazy-bug`, Step 1c.5 in `/lazy-batch` + `/lazy-batch-cloud` + `/lazy-bug-batch`. Reads SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface; greps `mcp-tests/*.md` for each decision's id + keywords (consumers pass `{feature_id}` or `{bug_id}`); uncovered decisions write `NEEDS_INPUT.md` (test-or-exempt choice) instead of flipping SPEC to Complete. Docs-only — runs identically in cloud and workstation.
- `audit-table-validator.md` — Post-generation validator for any audit artifact that writes per-feature decision tables. Non-destructive — appends `⚠ NOT-FOUND-IN-SPEC` (SPEC keyword search miss) and `⚠ CROSS-FEATURE-DUP(<other-feature-id>)` (literal duplicate row text across artifacts) markers in place + a `## Audit-Table Validator Report` summary. Injected into `/lazy-batch-retro` Step 6c; future ad-hoc audit-ledger generators inject it the same way.
- `tdd-protocol.md` / `tdd-test-agent.md` / `implementation-agent.md` — TDD pipeline
- `work-log.md` — Interview prep work logging (cognito-forms skills only)

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
| `/lazy` ↔ `/lazy-cloud` | `user/skills/lazy/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` | Both are thin LLM wrappers around `user/scripts/lazy-state.py`; the state machine itself is the script. The skills' only intended divergence is whether they pass `--cloud` to the script. Any change to wrapper prose (status bookends, special-action handling, dispatch glue, the shared Step 0.3 ad-hoc enqueue) MUST be mirrored. Any state-machine change goes into `lazy-state.py`, not the wrapper prose. When editing either, diff the other immediately afterward and confirm the diff matches what was intended. |
| `/lazy-batch` ↔ `/lazy-batch-cloud` | `user/skills/lazy-batch/SKILL.md` ↔ `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Both are autonomous orchestrators looping on `lazy-state.py`. Their only intended divergences (state script `--cloud` flag, `cloud-queue-exhausted` normal vs. defensive, `__write_deferred_non_cloud__` pseudo-skill, cycle subagent prompt's cloud-limitations block, `NEEDS_RESEARCH.md written_by` field, Step 0.45 ad-hoc enqueue's immediate cloud push) are tabulated in `/lazy-batch-cloud`'s "Differences from /lazy-batch" block. The Step 0.45 ad-hoc enqueue itself (shared component `adhoc-enqueue.md`) is mirrored. Any change to orchestration shape (cycle loop, hard constraints, terminal handling, max-cycles semantics) MUST be mirrored. |

When adding to a coupled pair, also update each file's State Machine Summary / orchestration shape at the bottom so the dispatch table reflects the new state.

## Scripts

| Script | Purpose |
|--------|---------|
| `project-skills.py` | Expands `!cat` component refs → `~/.claude/skills-projected/` |
| `lint-skills.py` | Validates skills: broken injections, embedded patterns, capabilities |
| `validate-plan.py` | Validates PHASES.md plan structure |
| `gemini-research.py` | Google Gemini deep research tool |
| `toolify-miner.py` | Offline session-log toolification miner (stdlib-only, **READ-ONLY over logs**): parses `~/.claude/projects/**/*.jsonl` (+ `subagents/agent-*.jsonl`), normalizes orchestrator tool-call sequences into argument-shape signatures, ranks by `occurrences × est_tokens_per_occurrence`, and applies the deterministic-only bar (above-bar iff deterministic AND repeated AND token-heavy). Emits markdown + JSON; never mutates logs. The miner *proposes* — promotion is deliberate (see `docs/features/unified-pipeline-orchestrator/toolify-bar.md`) |
| `analyze_har.py` | HTTP Archive file analysis |
| `pipeline_visualizer/` | Local web control-plane for the lazy feature/bug pipelines: `python -m pipeline_visualizer --repo-root <repo>` serves a graph/queues/fleet dashboard (`/api/state`, `/api/queue`) by shelling `lazy-state.py`/`bug-state.py` (stdlib-only renderer, never re-infers state) |
| `fix-line-endings.ps1` | CRLF/LF normalization script (NOT wired as a hook in `user/settings.json` — see Hooks table note) |
| `run-eslint.ps1` | Auto-lint TypeScript/Vue on save (PostToolUse hook) |

### Lint Commands

```bash
python ~/.claude/scripts/lint-skills.py                           # Basic: broken/embedded patterns
python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities  # Full: cross-repo check
python ~/.claude/scripts/project-skills.py                        # Expand all skills → projected/
```

### Research resume in claude-config

claude-config has no `docs/gemini-sprint/` staging by design (negligible research volume). Research resume in this repo is a **direct `RESEARCH.md` drop** into the canonical feature or bug dir (`docs/features/<slug>/RESEARCH.md` or `docs/bugs/<slug>/RESEARCH.md`), picked up by `lazy-state.py` Step 5 → `/spec` Phase 3 naturally. For future high-research-volume cases, see `user/skills/ingest-research/SKILL.md` line ~65 — parameterize the staging path via `.claude/skill-config/gemini-sprint.md`.

## Hooks

Hooks run before/after tool calls. Defined in `settings.json`, scripts in `user/hooks/`.

| Hook | Trigger | Purpose |
|------|---------|---------|
| `block-work-repo-git-push.sh` | PreToolUse (Bash) | Blocks `git push` in work repos |
| `block-terminal-kill.sh` | PreToolUse (Bash) | Blocks process/terminal termination (mobile workflow) |
| `block-work-repo-git-writes.sh` | PreToolUse (Bash) | Blocks destructive git in work repos |
| `pr-review-cache-guard.sh` | PreToolUse (Bash) | PR review caching guard |
| `lazy-cycle-containment.sh` | PreToolUse (Bash, Agent, Skill) | While the lazy cycle-subagent marker is present (scoped to the current repo), denies in-flight the routing/lifecycle/recursive-dispatch/2nd-feature-commit ops a runaway needs (fail-OPEN); also denies a subagent invoking any `/lazy*` skill via the Skill tool (defense-in-depth, agent_id-targeted, arming-free) |
| `block-noncanonical-blocker-write.sh` | PreToolUse (Write, Edit) | Denies writing a mis-named blocker sentinel — a target basename matching `BLOCKED*` + `.md` (case-insensitive) that is NOT exactly `BLOCKED.md` and does NOT contain `_RESOLVED_`. Such a stray is invisible to the `lazy-state.py`/`bug-state.py` Step-3 check and silently loops the pipeline. The deny message names canonical `BLOCKED.md`. Fail-OPEN. Write-time complement to the read-time `lazy_core.detect_noncanonical_blocker` backstop |
| `long-build-ownership-guard.sh` | PreToolUse (Bash) | **Request-time, NOT marker-armed** (distinct from the marker-armed `lazy-cycle-containment.sh`). Denies a Bash command whose first real token (after an optional `NAME=value` env-assignment prefix) is an EXACT long-build invocation — `tauri build`, `cargo build --release`, or `npm run build` — redirecting it to **orchestrator ownership** via the `LONG-BUILD-OWNERSHIP-TAKEOVER` deny signature, so the build runs in the main session (`run_in_background`) and survives a subagent turn boundary instead of being torn down with it (`long-build-and-runtime-ownership` M5 Prevent / LD4). Tightly scoped (never `ls`/`cat`/`npm run lint`/`cargo check --release`/`npm run build:docs`/a buried `tauri build` substring). Fail-OPEN — any internal error allows + writes a `hook-error.json` breadcrumb. The deny is the JSON `permissionDecision: deny` (a PreToolUse non-zero exit is a hard error, so the "fail-open block" is a deny, not `exit 2`). Pairs with the `run_transient_build` Transient Build contract in `lazy_core` (the orchestrator's takeover path) |
| `fix-line-endings.ps1` | **NOT registered** (script exists; `user/settings.json` `PostToolUse` is `[]`) | CRLF/LF normalization. **Deliberately left unwired** (`windows-portability-in-probe-glue-and-field-validators`): the script normalizes *to* CRLF (`-replace "\`n", "\`r\`n"`, i.e. it ADDS `\r`), which is exactly what a `\n`-only downstream validator (AlgoBooth `check-docs-consistency.ts`, Symptom B primary) then trips on. A naive global PostToolUse registration would INCREASE `\r`-bearing writes reaching that validator, not reduce them. The real `\r`-tolerance fix is AlgoBooth-side (`.trim()` each frontmatter value before field-type checks — see the bug's PHASES Phase 3 follow-up). Do NOT blind-wire this hook. |
| `run-eslint.ps1` | **NOT registered** (script exists; `user/settings.json` `PostToolUse` is `[]`) | Auto-lints TypeScript/Vue on save. Per-repo formatting is wired in repo-scoped settings instead (e.g. Cognito Forms registers `format-frontend.ps1` in `repos/cognito-forms/.claude/settings.json`), not at the user level. |

> **Per-repo hook scoping (`multi-repo-concurrent-runs`).** The three lazy enforcement hooks —
> `lazy-dispatch-guard.sh`, `lazy-route-inject.sh`, and `lazy-cycle-containment.sh` — no longer
> key off the *mere existence* of a global run marker. They scope by the **current repo** by
> calling `lazy-state.py --marker-present --repo-root <cwd>` (read-only; exit 0 present / 1
> absent), which resolves the per-repo keyed state dir `~/.claude/state/<repo_key>/`. A live run
> in repo A no longer arms the guard/inject/containment in a session for repo B, and a stale
> marker in one repo cannot block unrelated work in another. Fail-OPEN preserved: a query error
> falls back to prior behavior. See `user/scripts/CLAUDE.md` → "Per-repo keyed state dir".

## What's NOT Tracked

- Secrets: `*.env`, `.credentials.json`, `settings.local.json` contents
- Ephemeral state: `cache/`, `sessions/`, `pr-cache/`, `telemetry/`
- Projected output: `skills-projected/` (generated by `project-skills.py`)
- Backups: `*.bak`
