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
├── setup.ps1              # Creates/verifies/repairs symlinks (Windows/PowerShell)
├── setup.py               # Cross-platform port of setup.ps1 (stdlib Python; same manifest)
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

### Nested CLAUDE.md docs

Directory-level `CLAUDE.md` files capture what you can't infer from filenames — coupled-pair sync
rules, fail-OPEN hooks, state-machine contracts, gotchas. Read the one nearest your edit:

- `user/skills/CLAUDE.md` · `user/skills/_components/CLAUDE.md` — frontmatter, injection, coupled pairs, projection workflow
- `user/scripts/CLAUDE.md` — the lazy/bug state machine + contributor conventions (atomic writes, diagnostics, parity audit, shell dialect)
- `user/hooks/CLAUDE.md` — fail-OPEN, per-repo keying, deny signatures, unwired hooks
- `repos/CLAUDE.md` — per-repo `.claude/` anatomy + onboarding
- `docs/features/CLAUDE.md` · `docs/specs/CLAUDE.md` · `docs/bugs/CLAUDE.md` — pipeline lifecycle & file contracts
- `user/templates/CLAUDE.md` · `archived/CLAUDE.md` — boilerplate & deprecation trail

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

Cross-platform (Linux/macOS/cloud containers, and Windows with python3 — `cross-platform-setup`):
`setup.py` is a stdlib-only Python port of `setup.ps1` reading the SAME `manifest.psd1`
(no second manifest; a minimal tolerant psd1 parser that dies loudly on unknown constructs).
`setup.ps1` is kept as-is (retirement is a separate operator decision after Windows soak).

```bash
python3 setup.py check                     # Verify symlinks; exit 0 iff none broken
python3 setup.py bootstrap --target User   # Materialize ~/.claude/* links (cloud self-hosting)
python3 setup.py repair                    # Fix broken symlinks (real files -> .bak)
python3 setup.py bootstrap --target Repos --repos-root ~/source/repos
                                           # Repos scope against a host-local checkout root;
                                           # repos absent on disk are skipped, never broken
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
- `phases-runtime-validation.md` — The `/spec-phases` Step 2.7 capability-audit injected BEFORE drafting phases. Generic version under `_components/`; per-repo override at `repos/<name>/.claude/skill-config/`. Carries two planning-time audits: (1) the **SPEC-example capability audit** (negative-evidence grep over every API surface / construct the SPEC's code examples consume — an explicitly-rejected capability is a planning-time halt); and (2) the **MCP tool-existence audit** (`mcp-tooling-not-predetermined-at-planning`) — enumerates the MCP tools the SPEC's validation will call, greps the per-repo `mcp-tool-catalog.md` registry sources, and AUTO-AUTHORS a "build MCP tool X" deliverable up front on a miss (catalog absent → no-op). Moves MCP tool-surface determination to the FRONT of the pipeline so a missing tool lands before `/mcp-test` instead of forcing a late corrective add-phase / `adhoc-mcp-*` spin-off. The repo-specific registry paths live in `repos/<name>/.claude/skill-config/mcp-tool-catalog.md` (AlgoBooth: `scripts/mcp-test/tool-methods.ts` + the Rust `inventory::submit!` sites).
- `mcp-coverage-audit.md` — Gates `__mark_complete__` (feature pipeline) and `__mark_fixed__` (bug pipeline) across the `/lazy*` family: **Gate 1** in `/lazy` + `/lazy-cloud` + `/lazy-bug`, Step 1c.5 in `/lazy-batch` + `/lazy-batch-cloud` + `/lazy-bug-batch`. Reads SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface; greps `mcp-tests/*.md` for each decision's id + keywords (consumers pass `{feature_id}` or `{bug_id}`); uncovered decisions write `NEEDS_INPUT.md` (test-or-exempt choice) instead of flipping SPEC to Complete. Docs-only — runs identically in cloud and workstation. **Completion-time half of the MCP-tooling two-seam contract (`mcp-tooling-not-predetermined-at-planning`):** a required-MCP-tooling Locked Decision captured at `/spec` is enumerated here with no algorithm change (ordinary `## Locked Decisions` row), so the gate asserts the tool's scenario coverage — defense-in-depth with the planning-time `phases-runtime-validation.md` audit above.
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
| `/lazy` ↔ `/lazy-bug` | `user/skills/lazy/SKILL.md` ↔ `user/skills/lazy-bug/SKILL.md` | Bug-axis derivation (`inherit-by-reference`): `/lazy-bug` wraps `bug-state.py` with the same dispatch shape (`--bug-id`, `FIXED.md`/`__mark_fixed__` instead of `COMPLETED.md`/`__mark_complete__`); shared mechanics + tabulated divergences are audited per-heading by `lazy_parity_audit.py` against `user/scripts/lazy-parity-manifest.json`. Run the parity audit after editing either half. |
| `/lazy-batch` ↔ `/lazy-bug-batch` | `user/skills/lazy-batch/SKILL.md` ↔ `user/skills/lazy-bug-batch/SKILL.md` | Bug-axis derivation of the autonomous orchestrator (no Gemini-research/staged-ingest steps — operator-confirmed divergences tabulated in the parity manifest). Same audit rule: `lazy_parity_audit.py --repo-root .` must stay exit 0. |
| `/lazy-status` ↔ `/lazy-bug-status` | `user/skills/lazy-status/SKILL.md` ↔ `user/skills/lazy-bug-status/SKILL.md` | Bug-axis derivation of the read-only dashboard; parity-audited like the other bug-axis pairs. |

The **canonical machine-readable registry of these pairs is `user/scripts/lazy-parity-manifest.json`** (consumed by `lazy_parity_audit.py`); this table must list the same pairs — `doc-drift-lint.py` cross-checks it.

When adding to a coupled pair, also update each file's State Machine Summary / orchestration shape at the bottom so the dispatch table reflects the new state.

## Scripts

| Script | Purpose |
|--------|---------|
| `project-skills.py` | Expands `!cat` component refs → `~/.claude/skills-projected/` |
| `lint-skills.py` | Validates skills: broken injections, embedded patterns, capabilities |
| `doc-drift-lint.py` | **Doc-drift linter** (doc-drift-linter): pure-read stdlib cross-check of this repo's structured doc claims against reality — root `CLAUDE.md` Hooks table ↔ `user/settings.json` registrations (incl. asserting the NOT-registered rows stay unregistered), root + `user/scripts/CLAUDE.md` script tables ↔ `user/scripts/` on disk (doc→disk), Coupled Skill Pairs table ↔ `user/scripts/lazy-parity-manifest.json`, and `manifest.psd1` Repos entries ↔ `repos/<name>/` dirs. Deliberate divergences carry the `doc-drift:deliberate-divergence` marker in place (HTML comment on the md row; `#` comment in the psd1). `--repo-root`; exit 0 clean / 1 drift / 2 malformed. Prose claims out of scope. Tests: `test_doc_drift_lint.py` (incl. a self-check that THIS repo is clean) |
| `validate-plan.py` | Validates PHASES.md plan structure |
| `gemini-research.py` | Google Gemini deep research tool |
| `toolify-miner.py` | Offline session-log toolification miner (stdlib-only, **READ-ONLY over logs**): parses `~/.claude/projects/**/*.jsonl` (+ `subagents/agent-*.jsonl`), normalizes orchestrator tool-call sequences into argument-shape signatures, ranks by `occurrences × est_tokens_per_occurrence`, and applies the deterministic-only bar (above-bar iff deterministic AND repeated AND token-heavy). Emits markdown + JSON; never mutates logs. The miner *proposes* — promotion is deliberate (see `docs/features/unified-pipeline-orchestrator/toolify-bar.md`). Each candidate carries a stable `candidate_id` (`sha256(signature)[:12]`) — the promotion ledger's key |
| `toolify-promote.py` | **Toolify materializer + promotion ledger** (toolify-auto-promotion): the write-side sibling of the READ-ONLY miner. `--promote <candidate_id> --id <slug> --name "<title>"` re-verifies above-bar, dedups against the central git-tracked ledger (`docs/features/unified-pipeline-orchestrator/toolify-ledger.json`; `promoted` = hard refusal, `declined` re-promotes only with `--force --reason`), then shells `lazy-state.py --enqueue-adhoc --tier 2 --stub --at tail` (single queue author) and writes a stub SPEC carrying the canonical Step-4.5 stub markers — the item halts at the interactive `/spec` baseline-lock (auto-draft ≠ approval; naming stays human). `--decline --reason` / `--status` (NEW / promoted / declined / receipt-derived `shipped`) / report-only `--acceptance-report` (sample sizes named; the bar's constants stay human-edited). `/lazy-batch-retro` Step 6d resurfaces NEW candidates report-only. Tests: `test_toolify_promote.py` |
| `skill-usage-miner.py` | Offline **skill-usage miner + dead-weight audit** (stdlib-only, **READ-ONLY over logs AND both skills trees**): sibling of `toolify-miner.py` (reuses its `_iter_log_files` corpus walk), joins the SKILL.md inventory (user-level + repo-scoped, keyed by dir name) against two separately-counted detectors (assistant `Skill` tool_use incl. subagent transcripts; the `<command-name>` slash marker) and emits a ranked usage report: age-gated never-invoked list with ready-to-review archival proposal blocks (`git mv` + `archived/CLAUDE.md` row — **proposes, never executes**), hygiene sweep of non-skill artifacts, annotate-only toolify-candidate cross-links to `toolify-bar.md`, unknown invocations, and standing caveats (component-injection / auto-invoke / cloud usage is invisible — zero = investigate, never proof of deadness). `--since` / `--markdown` / `--json` / `--out`; on-demand only. Tests: `test_skill_usage_miner.py` |
| `analyze_har.py` | HTTP Archive file analysis |
| `pipeline_visualizer/` | Local web control-plane for the lazy feature/bug pipelines: `python -m pipeline_visualizer --repo-root <repo>` serves a graph/queues/fleet dashboard (`/api/state`, `/api/queue`) by shelling `lazy-state.py`/`bug-state.py` (stdlib-only renderer, never re-infers state). **`--fleet` mode (cross-repo-fleet-view):** one instance serves a cross-repo landing page at `/` — one *shallow* row per lazy-enabled repo (discovery: `~/source/repos/*/docs/{features,bugs}/queue.json` ∪ `~/.claude/lazy-repos.json` pins/excludes ∪ live run-marker `repo_root`s; row = queue depths + halt-sentinel presence + graded run badge `run-active` / `run-silent` ≥2h / `stale-marker` ≥24h / `idle`) + a cross-repo "Needs attention" triage strip; drill-in nests the full per-repo views under `/repo/<slug>/…`. The fleet layer (`pipeline_visualizer/fleet.py`) is a PURE READ: raw marker reads only (never `read_run_marker` — it is delete-on-read), never deletes a marker, adds no POST route, and spawns zero state-script subprocesses on the fleet poll (`/api/fleet`, own ~5s `TtlCache`) |
| `lazy-queue-doc.py` | Pure-read **GitHub-mobile queue-status doc** generator (mobile-queue-control): `python user/scripts/lazy-queue-doc.py --repo-root <repo>` renders a per-repo root-level `LAZY_QUEUE.md` (Features/Bugs tables with SPEC.md links, inline drill-in summary, "Needs attention" triage, run-active/idle header) over `pipeline_visualizer.probe.probe_state`. Byte-stable (no embedded wall-clock); orchestrator-invoked at the per-cycle commit so the doc rides the commit on `main`. Never mutates `queue.json`, never on the state-script compute path. `--stdout` / `--link-mode {relative,absolute}`. Tests: `test_lazy_queue_doc.py` |
| `incident-scan.py` | **Deterministic incident collector → bug stubs** (incident-auto-capture): `python3 user/scripts/incident-scan.py --repo-root <repo> [--dry-run]` — stdlib, READ-ONLY over the keyed state dir (deny ledger + the D2 append-only `hook-events.jsonl` + legacy `hook-error.json`). Clusters recurring denies/friction/hook errors by `(repo, signal_class, signature)`, applies per-signal recurrence bars (top-of-script config; acked denies count), dedups against every open + archived `docs/bugs/**/INCIDENT.md` `incident_key` (post-archive recurrence → NEW stub carrying `recurrence_of:`; archive never mutated), and enqueues ≤2 stubs/scan via the sanctioned `--enqueue-adhoc --type bug` path + an `INCIDENT.md` evidence capsule. Runs once per `/lazy-batch(-cloud)` run at the end-of-run flush (before `--run-end`) + on-demand via `/incident-scan`; `/spec-bug` owns root cause. Tests: `test_incident_scan.py` |
| `fix-line-endings.ps1` | CRLF/LF normalization script (NOT wired as a hook in `user/settings.json` — see Hooks table note) |
| `run-eslint.ps1` | Auto-lint TypeScript/Vue on save (PostToolUse hook) |
| `build-queue.ps1` | **Machine-global FIFO build serializer for Cognito Forms.** Heavy Cognito builds route through this wrapper via the four skills (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`), so only ONE build runs at a time across all worktrees (state under `~/.claude/state/build-queue/`). `-Op <op> -Exec <filtered-script> [pass-through args]`; runs the filtered script in a detached PowerShell (survives a Bash-tool timeout). Prints an **authoritative one-line outcome banner** as its LAST stdout line (`build-queue: seq=<N> op=<op> RESULT=<PASS|FAIL|NO-TESTS-MATCHED> [tests=<T> failed=<F>] (result_fidelity=...) [-> next-action]`, composed by `Format-BuildQueueBanner` in `build-queue-hygiene.ps1`) — the skills tell agents to trust that line and NOT `cat`/`grep` the runner or `results/<seq>.json` to disambiguate `exit_code=0`. Raw `dotnet build`/`dotnet test`/`nx build|test|run-many`/direct `*-filtered.ps1` in a Cognito worktree are hook-denied (see `build-queue-enforce.sh`, which denies only when a build token *begins a command segment* — a reference-only mention like `cat …/build-filtered.ps1` is allowed); `BUILD_QUEUE_BYPASS=1 <cmd>` is the deliberate one-off override. |
| `build-queue-status.ps1` | Read-only status view for the build queue (active build, ordered waiters, live machine load). Surfaced by the `/build-queue-status` skill (`repos/cognito-forms/.claude/skills/`). Also surfaces each build's `hygiene` outcome (`vbcscompiler_recycled`, `recycle_skipped_reason`, `quarantined_artifacts`, `result_fidelity` — incl. `no-tests-matched` for a zero-match test filter (`test-filtered.ps1` exit 5), distinct from a real all-pass — plus test-op `counts` (`passed`/`failed`/`total`), recorded on `results/<seq>.json` by `build-queue-runner.ps1`); a recycle skipped under concurrency renders neutrally (`recycled=False (skipped: concurrent-build-active)`), not as an error. Two writers touch `results/<seq>.json` (runner + wrapper release); the wrapper **read-merge-writes** it (refreshing only `exit_code`/`ended_at`) so the runner's `hygiene`/`counts` survive. |

Each build now auto-reaps leftover build descendants (Job Object), recycles VBCSCompiler **only when this build is the sole known-active queue seq (occupancy-gated via `Get-BuildQueueOccupancy`, so a build finishing in one worktree cannot force-kill a concurrent worktree's live compiler — `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build`)**, and quarantines 0-byte/truncated-PE DLLs **per project** (recursively across `<root>/**/bin` + `<root>/**/obj` for every project subdir, not just the worktree root — closes the silent-false-green where a poisoned per-project DLL survived a worktree-root-only sweep) between runs — `build-queue-status.ps1` surfaces the per-build `hygiene` outcome (`vbcscompiler_recycled`, `recycle_skipped_reason`, `quarantined_artifacts`, `result_fidelity`, and — for build ops — `build_fidelity` in the domain `log-failure-override | no-output | verified`, where `no-output` flags an exit-0 build that produced no compiled output (the false-green this defect fixed) and forces `RESULT=FAIL`). The provisional `active.lock` is written atomically and the stale-lock reclaim advances only on a *confirmed-dead* pid (an unreadable `'unknown'` read no longer counts), so a transient partial read can't admit a second concurrent build.

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
| `block-work-repo-git-writes.sh` | **NOT registered** (script exists in `user/hooks/`; never wired in tracked `user/settings.json`) | Blocks destructive git in work repos. Overlaps `block-work-repo-git-push.sh` (which IS registered); kept as the legacy standalone variant |
| `pr-review-cache-guard.sh` | PreToolUse (Read) | PR review caching guard |
| `load-branch-docs-context.sh` | SessionStart (startup, resume, clear, compact) | Loads branch-scoped docs context at session start/resume/clear/compact |
| `lazy-cycle-containment.sh` | PreToolUse (Bash, Agent, Skill) | While the lazy cycle-subagent marker is present (scoped to the current repo), denies in-flight the routing/lifecycle/recursive-dispatch/2nd-feature-commit ops a runaway needs (fail-OPEN); also denies a subagent invoking any `/lazy*` skill via the Skill tool (defense-in-depth, agent_id-targeted, arming-free) |
| `block-noncanonical-blocker-write.sh` | PreToolUse (Write, Edit) | Denies writing a mis-named blocker sentinel — a target basename matching `BLOCKED*` + `.md` (case-insensitive) that is NOT exactly `BLOCKED.md` and does NOT contain `_RESOLVED_`. Such a stray is invisible to the `lazy-state.py`/`bug-state.py` Step-3 check and silently loops the pipeline. The deny message names canonical `BLOCKED.md`. Fail-OPEN. Write-time complement to the read-time `lazy_core.detect_noncanonical_blocker` backstop |
| `block-sentinel-write-on-stray-branch.sh` | PreToolUse (Write, Edit) | Denies writing a pipeline sentinel (`NEEDS_INPUT.md` / `BLOCKED.md` / `FIXED.md` / `COMPLETED.md` / `VALIDATED.md`) while `git rev-parse --abbrev-ref HEAD` for the tool-call `cwd` differs from the run marker's `work_branch` (queried via `lazy-state.py --marker-work-branch --repo-root <cwd>` — Python owns branch identity; bash never re-derives it). A sentinel written on a stray branch is invisible to the state scripts (which only read the run's work branch) and silently loops the pipeline. The deny NAMES both the stray branch and the corrective work branch (switch back + write there; never create a branch mid-cycle). Fail-OPEN on every error path (no python / no marker / `--marker-work-branch` exit 1 / non-sentinel target / git failure / malformed payload → allow). Write-time mechanical complement to the Phase-1 prose ban in `cycle-base-prompt.md` (`cycle-subagent-fabricates-policy-or-stray-branch`) — the same two-layer pattern as the noncanonical-blocker hook + `lazy_core.detect_noncanonical_blocker` |
| `long-build-ownership-guard.sh` | PreToolUse (Bash) | **Request-time, NOT marker-armed** (distinct from the marker-armed `lazy-cycle-containment.sh`). Denies a Bash command whose first real token (after an optional `NAME=value` env-assignment prefix) is an EXACT long-build invocation — `tauri build`, `cargo build --release`, or `npm run build` — redirecting it to **orchestrator ownership** via the `LONG-BUILD-OWNERSHIP-TAKEOVER` deny signature, so the build runs in the main session (`run_in_background`) and survives a subagent turn boundary instead of being torn down with it (`long-build-and-runtime-ownership` M5 Prevent / LD4). Tightly scoped (never `ls`/`cat`/`npm run lint`/`cargo check --release`/`npm run build:docs`/a buried `tauri build` substring). Fail-OPEN — any internal error allows + writes a `hook-error.json` breadcrumb. The deny is the JSON `permissionDecision: deny` (a PreToolUse non-zero exit is a hard error, so the "fail-open block" is a deny, not `exit 2`). Pairs with the `run_transient_build` Transient Build contract in `lazy_core` (the orchestrator's takeover path) |
| `build-queue-enforce.sh` | PreToolUse (Bash) | **Cognito build-queue enforcement (5th in the Bash chain).** Denies a raw heavy-build invocation in a Cognito worktree — `dotnet build`/`dotnet test`, `nx`/`npx nx` with a `build`/`test`/`run-many` target, or a direct `*-filtered.ps1` call — and redirects to the matching skill (`/msbuild`, `/mstest`, `/nxbuild`, `/nxtest`), which routes through `build-queue.ps1`. Scoped by **git remote** matching `cognitoforms/cognito` (NOT work email — so Overwatch/`mcp/` are never gated). Allowed: `dotnet restore`/`--version`/`ef`, `nx lint`/`typecheck`/`format`, `msbuild`/`npm`/`pnpm`, the `build-queue.ps1` wrapper itself, and anything prefixed `BUILD_QUEUE_BYPASS=1` (the override). Fail-OPEN (deny-via-JSON, never a non-zero exit); shares the sibling hooks' accepted `cd`-into-another-repo blind spot. |
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
>
> **Same-pipeline concurrent-walker refusal (`concurrent-same-branch-walkers-no-arbitration`).**
> Within a single repo, `refuse_run_start_clobber` (shared `lazy_core` helper, both pipelines) now
> refuses a second `--run-start` even for the **same pipeline** when the existing marker is live +
> age-fresh AND no `lazy-run-checkpoint.json` is waiting (a genuinely-concurrent second `/lazy-batch`
> walker on the same branch) — checkpoint-discriminated so a sanctioned checkpoint-resume (which always
> carries that file) still overwrites. The checkpoint is read non-destructively (existence only).
> Closes the residual same-repo/same-branch/same-pipeline gap left open by `multi-repo-concurrent-runs`.
>
> **Single-slot marker ownership — born owner-bound + owner detect/re-arm
> (`single-slot-marker-ownership-race-disarms-owning-run`).** The run marker's owner is a single mutable
> `session_id` slot. Previously the marker was written bind-pending (`session_id: None`) at `--run-start`
> and bound later by the first orchestrator guard ALLOW — leaving a window in which a WRONG (non-owner)
> session could stamp the slot first, after which the TRUE owner's own dispatches read `None` (staleness
> path B) and silently fast-path-allowed for the rest of the run (the guard disarmed mid-run, no signal).
> Now both `--run-start` handlers thread `session_id=args.session_id` so the marker is **born owner-bound**
> — a foreign session can never be the first writer (Repro A + the checkpoint-resume Repro B both closed at
> the source; legacy `--run-start` without `--session-id` still falls back to the unchanged
> `_bind_marker_on_allow` anchor). As a backstop for the legacy/un-threaded paths, the owner gets a
> NON-DESTRUCTIVE detect (`lazy_core.marker_owner_status` → `absent` / `owned-by-me` / `foreign-stamped`,
> distinguishing "no run" from "wrong-stamped run" without deleting a live foreign-stamped marker) and a
> re-arm (`reassert_marker_owner` + the orchestrator-only `--reassert-owner` CLI action, cycle-guarded
> exit 3) to re-claim its own run's guard. Coupled pair on both state scripts (the marker is shared;
> parity-guarded). See `docs/bugs/single-slot-marker-ownership-race-disarms-owning-run`.

## What's NOT Tracked

- Secrets: `*.env`, `.credentials.json`, `settings.local.json` contents
- Ephemeral state: `cache/`, `sessions/`, `pr-cache/`, `telemetry/`
- Projected output: `skills-projected/` (generated by `project-skills.py`)
- Backups: `*.bak`
