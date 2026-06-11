# Cognito PR Review Plugin v2.5

Custom PR review plugin for Cognito Forms that uses a hierarchical investigation-driven pipeline: deterministic prep → planning → triage → parallel investigation/sweep/reuse-candidacy → deterministic post-processing → synthesis.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Step 1: Enhanced Prep Script (deterministic TypeScript)          │
│  - Fetch PR data via GitHub REST API (or git diff for local)     │
│  - PR timeline, iteration diffs, thread status tracking          │
│  - Context distillation for large files                          │
│  - Manifest v2 with structural context                           │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 2: Journey/Planner Agent (Opus)                            │
│  - Produces persistent PR-{id}-journey.md                        │
│  - Overview, objectives, file map, manual review guide           │
│  - Re-review: appends new iteration, tracks lifecycle            │
│  - Validates triage as hierarchical planner                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 3: Triage Agent (Opus)                                     │
│  - Classifies files: critical / important / skim                 │
│  - Re-review: tier boost for changed + unresolved files          │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 4: Investigation + Sweep + Reuse-Candidacy (parallel)      │
│  - 1 Investigation Agent per critical group (Opus)               │
│    Solver-Verifier protocol, full codebase access                │
│  - 1 Sweep Agent for important+skim files (Sonnet)               │
│    95 YAML rules, weight-aware thresholds, escalation rights     │
│  - Reuse-Candidacy Stage (Opus) — runs concurrently              │
│    Clusters net-new files; 1 cognito-consistency-checker per     │
│    cluster; emits reuse findings with verdict (reuse / extend /  │
│    refactor / wrap / acceptable-new); surfaces in               │
│    "Reuse & Duplication" section of the final review             │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 5: Deterministic Post-Processing (TypeScript)              │
│  - EMA weight application, dedup, rank, filter, lifespan         │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 6: Synthesizer Agent (Sonnet)                              │
│  - Narrative review from processed findings + journey            │
└──────────────────────────────────────────────────────────────────┘
```

## Usage

### Review a Specific PR

```
/cognito-pr-review:review-pr 42
```

Reviews the PR using GitHub API. No local git operations needed.

### Review Local Changes (Before Creating PR)

```
/cognito-pr-review:review-pr                   # All local uncommitted changes
/cognito-pr-review:review-pr csharp            # C# changes only
/cognito-pr-review:review-pr frontend          # Frontend changes only
```

### Specific Aspects

```
/cognito-pr-review:review-pr 42 csharp         # C# architecture only
/cognito-pr-review:review-pr 42 frontend       # Vue/TypeScript only
/cognito-pr-review:review-pr 42 api            # API controllers only
/cognito-pr-review:review-pr 42 consistency    # Pattern consistency
/cognito-pr-review:review-pr 42 testing        # Test quality and coverage
/cognito-pr-review:review-pr 42 sequential     # Run agents one at a time
```

### Buddy Review (Interactive Pair-Review)

```
/cognito-pr-review:review-pr-buddy 42          # Interactive walk-through of PR 42
/cognito-pr-review:review-pr-buddy             # Buddy review of local uncommitted changes
/cognito-pr-review:review-pr-buddy 42 csharp   # C# aspects only
/cognito-pr-review:review-pr-buddy 42 sequential  # Pipeline agents run one at a time
```

An interactive senior-architect pair-review. Arguments mirror `review-pr` (`[PR_ID | local] [aspects] [sequential]`).

**Phase 0 — Non-interactive prep:** Delegates to the full `review-pr` pipeline (prep → journey → triage → reuse-candidacy + investigation + sweep → aggregate → post-process). Produces the journey file and `processed-findings.json` (including reuse findings) without any interaction.

**Phase 1 — Interactive walk:** Steps through every chunk in the journey's Manual Review Guide. For each chunk: explains what changed (senior-architect framing), surfaces pre-computed findings grouped by source (investigation / sweep / reuse), poses Socratic key-questions, then captures your verdict on each finding via a keep / dismiss / will-comment / add-own picker. Progress is checkpointed to `{cacheDir}/buddy-session.json` after every chunk — compaction-safe resume on restart.

**Phase 2 — Curated synthesis:** Writes the final `PR-{id}.md` in synthesizer-v2 format containing only kept findings and your own observations. The autonomous synthesizer agent is not invoked — the interactive session is the synthesis.

### Learn from PRs / Calibrate

```
/cognito-pr-review:learn-from-pr 42            # Extract rules from reviewer feedback + EMA calibration
/cognito-pr-review:calibrate                   # Bulk calibrate weights against historical reviews
/cognito-pr-review:calibrate --dry-run         # Preview weight changes without writing
/cognito-pr-review:weights                     # View current rule weights
/cognito-pr-review:rebuild-agents              # Re-embed rules into agent prompts
```

## Agents

### v2 Pipeline Agents

| Agent | Role | Model |
|-------|------|-------|
| journey-planner | PR lifecycle document + hierarchical planner | Opus |
| triage | File classification (critical/important/skim) | Opus |
| investigation | Deep-dive critical areas with Solver-Verifier | Opus |
| sweep | Rule-based review with weight-aware thresholds | Sonnet |
| synthesizer-v2 | Narrative review synthesis | Sonnet |

### Legacy Agents (v1 reference)

| Agent | Focus | Model |
|-------|-------|-------|
| cognito-architecture | C# patterns, DI, StorageContext, async | Opus |
| cognito-frontend | Vue 2.7, TypeScript, dialogs | Opus |
| cognito-api-design | Controllers, HTTP methods, types | Opus |
| cognito-consistency-checker | Pattern consistency | Opus |
| cognito-test-coverage | Test quality, coverage gaps, entity IDs | Opus |
| cognito-behavior | Behavior correctness verification | Opus |
| review-synthesizer | v1 aggregation and deduplication | Haiku |

## Rules

95 rules organized as YAML in `knowledge/rules/`:

| File | Category |
|------|----------|
| csharp-architecture.yaml | C# patterns, DI, StorageContext |
| api-design.yaml | HTTP methods, controllers, idempotency |
| frontend-vue.yaml | Vue 2.7, TypeScript, dialogs |
| performance.yaml | Memory, lazy evaluation, HttpClient |
| security.yaml | Sanitization, input validation |
| testing.yaml | Test patterns, assertions |
| code-consistency.yaml | Naming, event handlers, comments |
| template-binding.yaml | build.js patterns |

### Weight System

Per-rule EMA weights calibrated against human reviewer feedback:
- `knowledge/weights.yaml` stores rule weights + category multipliers
- Calibration via `/cognito-pr-review:learn-from-pr` (per-PR) or `/cognito-pr-review:calibrate` (bulk)
- Sweep agent applies weight-aware thresholds: important tier >= 0.5, skim tier >= 0.7

## File Structure

```
~/.claude/plugins/local-tools/plugins/cognito-pr-review/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── journey-planner.md          # v2: PR lifecycle + planner
│   ├── triage.md                   # v2: file classification
│   ├── investigation.md            # v2: deep-dive critical areas
│   ├── sweep.md                    # v2: rule-based review (95 rules embedded)
│   ├── synthesizer-v2.md           # v2: narrative synthesis
│   ├── cognito-architecture.md     # v1 legacy
│   ├── cognito-api-design.md       # v1 legacy
│   ├── cognito-frontend.md         # v1 legacy
│   ├── cognito-consistency-checker.md  # v1 legacy
│   ├── cognito-test-coverage.md    # v1 legacy
│   ├── cognito-behavior.md         # v1 legacy
│   └── review-synthesizer.md       # v1 legacy
├── commands/
│   ├── review-pr.md                # Main review orchestration (v2 pipeline)
│   ├── review-pr-buddy.md          # Interactive pair-review (buddy mode)
│   ├── learn-from-pr.md            # Extract rules + EMA calibration
│   ├── calibrate.md                # Bulk weight calibration
│   ├── weights.md                  # View/adjust weights
│   └── rebuild-agents.md           # Re-embed rules into agent prompts
├── knowledge/
│   ├── weights.yaml                # EMA rule weights + category multipliers
│   ├── code-review-rules.md        # Legacy reference
│   └── rules/
│       ├── csharp-architecture.yaml
│       ├── api-design.yaml
│       ├── frontend-vue.yaml
│       ├── performance.yaml
│       ├── security.yaml
│       ├── testing.yaml
│       ├── code-consistency.yaml
│       └── template-binding.yaml
├── scripts/
│   ├── prep-pr.ts                  # Deterministic PR data gathering (GitHub API)
│   ├── post-process.ts             # Deterministic findings processing
│   ├── aggregate-findings.ts       # Combine agent outputs
│   ├── tsconfig.json
│   └── package.json
├── docs/
│   └── specs/
│       └── cognito-pr-review-v2/
│           ├── SPEC.md
│           ├── PHASES.md
│           ├── RESEARCH.md
│           └── RESEARCH_PROMPT.md
└── README.md
```

## Prep Script

The `prep-pr.ts` script gathers PR data and populates a local cache:

**PR Mode:**
```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts <pr_number> [--force] [--cache-root <path>]
```

**Local Mode:**
```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts --local [--base <branch>] [--include-untracked]
```

Options:
- `--force`: Force rebuild even if cache is current (PR mode only)
- `--cache-root`: Directory for .claude/pr-cache (default: current dir)
- `--local`: Enable local mode (review uncommitted changes)
- `--base <branch>`: Target branch to diff against (default: main)
- `--include-untracked`: Include untracked files in review
- `--context <lines>`: Number of context lines in diffs (default: 3)

## Cache Structure

cog-docs is the sole output destination in PR mode. The cache (gitignored via `.pr-review/`) and the human-facing review/journey both live under the resolved cog-docs item dir — `<cog-docs>/docs/{bugs,features}/<id>-<slug>/`, created with a minimal SPEC.md if absent. If no cog-docs repo is present, prep hard-fails.

PR Mode cache: `<cogDocsItemDir>/.pr-review/pr-cache/{pr_number}/`
Local Mode cache: `.claude/pr-cache/local/`

```
<cogDocsItemDir>/.pr-review/pr-cache/{id}/
├── manifest.json               # PR metadata + file listing (v2 schema)
├── pr-context.json             # PR description, comments, thread statuses
├── pr-timeline.json            # Iterations, reviews, statuses, votes
├── iteration-diff.json         # (re-reviews only) Changes between iterations
├── files/{path}                # Downloaded file contents
├── diffs/{path}.diff           # Per-file unified diffs
├── structural-context/         # Large file distillations
├── agent-output/               # Raw agent findings JSON
│   ├── investigation-{group}.json
│   └── sweep.json
├── combined-findings.json      # Aggregated findings
└── processed-findings.json     # Post-processed, ranked findings
```

## Review Artifacts

PR mode (committable, alongside the cache's `.pr-review/` sibling):

```
<cogDocsItemDir>/                # <cog-docs>/docs/{bugs,features}/<id>-<slug>/
├── SPEC.md                     # Minimal stub if auto-created
├── PR-{id}-journey.md          # Persistent journey file (lifecycle tracking)
├── PR-{id}.md                  # Final review markdown
└── REVIEWED.md                 # Stage sentinel (derive_stage → reviewed)
```

Local mode (no work item) falls back to `.claude.local/reviews/`.

## Requirements

- GitHub CLI (`gh`) installed and authenticated (`gh auth login`)
- Node.js 18+ (for native fetch)
- tsx installed globally or via npx
- Azure CLI (`az login`) only needed for ADO work item integration

## Target Repository

- GitHub: `cognitoforms/cognito`
- Work items: Azure DevOps (Cognito Forms project)

## Author

Jacob Madsen
