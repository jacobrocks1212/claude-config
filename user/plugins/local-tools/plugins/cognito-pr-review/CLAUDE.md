# Cognito PR Review Plugin

## Plugin Overview

Claude Code plugin for reviewing Cognito Forms PRs using a hierarchical investigation-driven pipeline. The plugin lives at `~/.claude/plugins/local-tools/plugins/cognito-pr-review/` and operates on the Cognito Forms repo at `C:\Users\JacobMadsen\source\repos\Cognito Forms`.

## Target Repository

- **GitHub:** `cognitoforms/cognito` (origin)
- **Work Items:** Azure DevOps project "Cognito Forms" (ID: 54d9f307-1306-430c-b206-1a55b294a94b)
- PRs and PR comments come from GitHub; work items remain in ADO

## Key Commands

| Command | Purpose |
|---------|---------|
| `/cognito-pr-review:review-pr [PR#]` | Full v2 review pipeline |
| `/cognito-pr-review:review-pr-buddy [PR#]` | Interactive senior-architect pair-review (walks the PR chunk-by-chunk over the same pipeline) |
| `/cognito-pr-review:learn-from-pr PR#` | Extract rules + EMA calibration |
| `/cognito-pr-review:calibrate` | Bulk weight calibration |
| `/cognito-pr-review:weights` | View/adjust rule weights |
| `/cognito-pr-review:rebuild-agents` | Re-embed rules into agent prompts |

## Architecture

The v2 pipeline replaces the v1 parallel-specialist model with a hierarchical approach:

```
prep-pr.ts (GitHub API) → journey-planner (Opus) → triage (Opus)
  → investigation (Opus, per critical group) + sweep (Sonnet, rules)
    + reuse-candidacy (Opus, per net-new cluster)
    + intra-file consistency (Opus, per modified cluster)   [all parallel]
  → post-process.ts (deterministic) → synthesizer-v2 (Sonnet)
```

The **reuse-candidacy stage** (`review-pr.md` Step 5b) runs in parallel with investigation+sweep: it clusters net-new/substantive files (seeded from `manifest.baselines[]`) and fans out one `cognito-consistency-checker` (Opus) per cluster. Each agent reads the shared reuse-discovery protocol (`~/.claude/skills/_components/reuse-discovery-protocol.md`), inherits investigation's access model (local-codebase-on-`main` + tree-sitter, NOT sweep's cache-only), and emits `{cacheDir}/agent-output/reuse-{cluster}.json` with a verdict (`reuse`/`extend`/`refactor`/`wrap`/`acceptable-new`). post-process routes reuse findings through the investigation lane (fixed weight 1.0) and maps **verdict→severity** — `refactor`/`reuse` → important, `extend`/`wrap` → nit, `acceptable-new` → dropped. **This verdict→severity boundary is a tunable** for future `/cognito-pr-review:learn-from-pr` calibration. The cache-only `sweep` agent can only FLAG reuse heuristics and ESCALATE (its 4 `reuse-*` rules in `code-consistency.yaml`); it never asserts a local-codebase fact.

The **intra-file consistency stage** (also `review-pr.md` Step 5b, a second clustering pass concurrent with the reuse pass) is the *intra-file* complement to the cross-file reuse stage. Where reuse compares each changed file against *other* similar files (`manifest.baselines[]`, which excludes the file itself), this stage asks whether new code should have reused code already in **that same file**, and whether it is **consistent with the file's surrounding conventions**. It clusters all substantively-modified substantive files (all tiers; excludes test/config/generated; no baseline required) and fans out one `cognito-intra-file-consistency` (Opus) per cluster. Each agent reads BOTH the shared reuse-discovery protocol and `~/.claude/skills/_components/pr-review-reuse-agent-scaffold.md`, uses the host file's own `main` version as the implicit baseline, and emits `{cacheDir}/agent-output/intrafile-{cluster}.json` with `source:"intrafile"`. post-process routes these through the same investigation lane (fixed weight 1.0) and maps **verdict→severity** — intra-file duplication (`refactor`/`reuse`) → important, surrounding-code `inconsistent` → nit, `consistent`/`acceptable`/`acceptable-new` → dropped (with negative-search trail). synthesizer renders them under a distinct `## Intra-File Consistency` section. Sweep's 2 `intrafile-*` rules FLAG+ESCALATE in-file heuristics to this stage. The duplication-vs-consistency severity boundary is a `learn-from-pr` tunable, same as the reuse boundary.

**`review-pr-buddy`** (`commands/review-pr-buddy.md`) is an interactive front-end over the SAME pipeline: Phase 0 delegates entirely to `review-pr.md` (the single source of pipeline truth — steps are not duplicated); Phase 1 walks the journey's Manual Review Guide chunk-by-chunk, capturing per-finding verdicts to `{cacheDir}/buddy-session.json` (compaction-safe); Phase 2 emits a human-curated `PR-{id}.md` in synthesizer-v2 format. `review-pr.md` remains the main pipeline orchestration; `review-pr-buddy.md` is the buddy orchestration.

### Scripts (deterministic TypeScript, no LLM)
- `scripts/prep-pr.ts` — Gathers PR data from GitHub API; resolves/creates the cog-docs item dir and populates `<cogDocsItemDir>/.pr-review/pr-cache/{id}/` (hard-fails if no cog-docs repo)
- `scripts/post-process.ts` — EMA weights, dedup, rank, filter, lifespan annotations
- `scripts/aggregate-findings.ts` — Combines agent outputs into unified format

### Agents (LLM-based)
- `agents/journey-planner.md` — Opus; produces journey file + validates triage
- `agents/triage.md` — Opus; classifies files into critical/important/skim
- `agents/investigation.md` — Opus; deep-dive with Solver-Verifier protocol
- `agents/sweep.md` — Sonnet; embedded YAML rules, weight-aware thresholds (incl. `reuse-*` and `intrafile-*` flag+escalate rules)
- `agents/cognito-consistency-checker.md` — Opus; per-cluster reuse-candidacy agent (grown from the orphaned checker); reads the shared reuse-discovery protocol + agent scaffold; investigation-level access
- `agents/cognito-intra-file-consistency.md` — Opus; per-cluster intra-file duplication + surrounding-code consistency agent; reads the same protocol + scaffold; investigation-level access; emits `source:"intrafile"`
- `agents/synthesizer-v2.md` — Sonnet; narrative review synthesis (incl. "Reuse & Duplication" + "Intra-File Consistency" sections)

### Knowledge
- `knowledge/rules/*.yaml` — 95 rules across 8 categories
- `knowledge/weights.yaml` — Per-rule EMA weights + category multipliers

## Editing Guidelines

### When editing scripts (*.ts)
- Scripts run via `npx tsx` — no local TypeScript compilation step
- `prep-pr.ts` uses GitHub REST API; auth via `gh auth token` or `GITHUB_TOKEN`
- Output interfaces (`Manifest`, `ManifestFile`, `TimelineData`) are consumed by all downstream agents — changes here ripple through the entire pipeline
- Local mode (`--local`) uses only git commands, no remote API

### When editing agents (*.md)
- YAML frontmatter specifies model, color, and allowed-tools
- `sweep.md` has embedded rules between `RULES_START`/`RULES_END` markers — use `/cognito-pr-review:rebuild-agents` to re-embed after rule changes
- `investigation.md` has unrestricted read access (cache + local codebase); `sweep.md` has cache-only access
- The reuse-class agents (`cognito-consistency-checker.md`, `cognito-intra-file-consistency.md`) share `~/.claude/skills/_components/pr-review-reuse-agent-scaffold.md` (access model + tree-sitter guidance + output schema + verdict/severity reminders) — `Read` at runtime, one source of truth, do not fork. They differ only by the documented per-agent overrides (output prefix, baseline source, extra verdicts)
- Agent output JSON schema must match what `post-process.ts` expects

### When editing rules (*.yaml)
- Each rule needs: `id`, `severity`, `description`; optional: `trigger_patterns`, `anti_pattern`, `correct_pattern`
- Rule IDs must match entries in `knowledge/weights.yaml`
- After adding/modifying rules, run `/cognito-pr-review:rebuild-agents` to update sweep.md
- Never add `source:` fields — rules are anonymous

### When editing commands (*.md)
- YAML frontmatter: `description`, `argument-hint`, `allowed-tools`
- `review-pr.md` is the main orchestration — 12-step pipeline
- `review-pr-buddy.md` delegates Phase 0 to `review-pr.md`; do NOT copy or duplicate its step bodies
- `learn-from-pr.md` uses hybrid matching (proximity + Haiku semantic judge) for calibration

## Cache & Artifacts

cog-docs is the sole output destination (PR mode). All artifacts land under the resolved cog-docs item dir `<cogDocsItemDir>` (= `<cog-docs>/docs/{bugs,features}/<id>-<slug>/`, created with a minimal SPEC.md if it doesn't exist):

- PR cache (gitignored): `<cogDocsItemDir>/.pr-review/pr-cache/{id}/`
- Review artifacts (committable): `<cogDocsItemDir>/PR-{id}.md`, `PR-{id}-journey.md`, `REVIEWED.md`
- Transient lock (work repo, the only file outside cog-docs): `.claude/pr-cache/pr-review-active.json`
- PR comments export (input, unchanged): `.claude.local/slop/pr-comments/`
- Local mode (no work item) still uses `.claude/pr-cache/local/` + `.claude.local/reviews/`

## External Dependencies

- `get-pr-comments.ps1` at Cognito Forms repo root — exports GitHub PR comments for calibration
- Tree-Sitter MCP server at `~/.claude/mcp-servers/tree-sitter/` — optional structural queries for investigation agents

## Specs & Phases

- `docs/specs/cognito-pr-review-v2/SPEC.md` — Feature specification
- `docs/specs/cognito-pr-review-v2/PHASES.md` — Implementation phases (10 phases, 1-9 complete)
