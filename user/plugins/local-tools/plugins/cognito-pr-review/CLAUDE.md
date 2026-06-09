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
| `/cognito-pr-review:learn-from-pr PR#` | Extract rules + EMA calibration |
| `/cognito-pr-review:calibrate` | Bulk weight calibration |
| `/cognito-pr-review:weights` | View/adjust rule weights |
| `/cognito-pr-review:rebuild-agents` | Re-embed rules into agent prompts |

## Architecture

The v2 pipeline replaces the v1 parallel-specialist model with a hierarchical approach:

```
prep-pr.ts (GitHub API) → journey-planner (Opus) → triage (Opus)
  → investigation (Opus, per critical group) + sweep (Sonnet, rules)
    + reuse-candidacy (Opus, per net-new cluster)        [all three parallel]
  → post-process.ts (deterministic) → synthesizer-v2 (Sonnet)
```

The **reuse-candidacy stage** (`review-pr.md` Step 5b) runs in parallel with investigation+sweep: it clusters net-new/substantive files (seeded from `manifest.baselines[]`) and fans out one `cognito-consistency-checker` (Opus) per cluster. Each agent reads the shared reuse-discovery protocol (`~/.claude/skills/_components/reuse-discovery-protocol.md`), inherits investigation's access model (local-codebase-on-`main` + tree-sitter, NOT sweep's cache-only), and emits `{cacheDir}/agent-output/reuse-{cluster}.json` with a verdict (`reuse`/`extend`/`refactor`/`wrap`/`acceptable-new`). post-process routes reuse findings through the investigation lane (fixed weight 1.0) and maps **verdict→severity** — `refactor`/`reuse` → important, `extend`/`wrap` → nit, `acceptable-new` → dropped. **This verdict→severity boundary is a tunable** for future `/cognito-pr-review:learn-from-pr` calibration. The cache-only `sweep` agent can only FLAG reuse heuristics and ESCALATE (its 4 `reuse-*` rules in `code-consistency.yaml`); it never asserts a local-codebase fact.

### Scripts (deterministic TypeScript, no LLM)
- `scripts/prep-pr.ts` — Gathers PR data from GitHub API, populates `.claude/pr-cache/{id}/`
- `scripts/post-process.ts` — EMA weights, dedup, rank, filter, lifespan annotations
- `scripts/aggregate-findings.ts` — Combines agent outputs into unified format

### Agents (LLM-based)
- `agents/journey-planner.md` — Opus; produces journey file + validates triage
- `agents/triage.md` — Opus; classifies files into critical/important/skim
- `agents/investigation.md` — Opus; deep-dive with Solver-Verifier protocol
- `agents/sweep.md` — Sonnet; embedded YAML rules, weight-aware thresholds (incl. `reuse-*` flag+escalate rules)
- `agents/cognito-consistency-checker.md` — Opus; per-cluster reuse-candidacy agent (grown from the orphaned checker); reads the shared reuse-discovery protocol; investigation-level access
- `agents/synthesizer-v2.md` — Sonnet; narrative review synthesis (incl. "Reuse & Duplication" section)

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
- Agent output JSON schema must match what `post-process.ts` expects

### When editing rules (*.yaml)
- Each rule needs: `id`, `severity`, `description`; optional: `trigger_patterns`, `anti_pattern`, `correct_pattern`
- Rule IDs must match entries in `knowledge/weights.yaml`
- After adding/modifying rules, run `/cognito-pr-review:rebuild-agents` to update sweep.md
- Never add `source:` fields — rules are anonymous

### When editing commands (*.md)
- YAML frontmatter: `description`, `argument-hint`, `allowed-tools`
- `review-pr.md` is the main orchestration — 12-step pipeline
- `learn-from-pr.md` uses hybrid matching (proximity + Haiku semantic judge) for calibration

## Cache & Artifacts

- PR cache: `.claude/pr-cache/{id}/` (relative to Cognito Forms repo)
- Review artifacts: `.claude.local/reviews/PR-{id}.md` and `PR-{id}-journey.md`
- PR comments export: `.claude.local/slop/pr-comments/`

## External Dependencies

- `get-pr-comments.ps1` at Cognito Forms repo root — exports GitHub PR comments for calibration
- Tree-Sitter MCP server at `~/.claude/mcp-servers/tree-sitter/` — optional structural queries for investigation agents

## Specs & Phases

- `docs/specs/cognito-pr-review-v2/SPEC.md` — Feature specification
- `docs/specs/cognito-pr-review-v2/PHASES.md` — Implementation phases (10 phases, 1-9 complete)
