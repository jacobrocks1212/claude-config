---
description: "Cognito Forms PR review with team-specific patterns"
argument-hint: "[PR_ID] [aspects: all|csharp|frontend|api|consistency|testing] [sequential]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Agent"]
---

# Cognito Forms PR Review

Run a PR review using Cognito-specific patterns derived from senior reviewer feedback.

**Arguments:** "$ARGUMENTS"

## Architecture Overview

This command uses a hierarchical planner pipeline: deterministic prep → planning → triage → parallel investigation/sweep/reuse-candidacy → deterministic post-processing → synthesis.

```
┌──────────────────────────────────────────────────────────────────┐
│  Step 1: Enhanced Prep Script (deterministic TypeScript)          │
│  - Everything from v1 + PR timeline + iteration diffs            │
│  - Thread status tracking, re-review detection                   │
│  - Context distillation for large files                          │
│  - Manifest v2 with structural context                           │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 2: Journey/Planner Agent (Opus)                            │
│  - Produces persistent PR-{id}-journey.md                        │
│  - Contains: overview, objectives, file map, review guide        │
│  - Re-review: appends new iteration section                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 3: Triage Agent (Opus)                                     │
│  - Classifies files: critical / important / skim                 │
│  - Re-review: tier boost for changed + unresolved files          │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 4: Planner Validates Triage                                │
│  - Cross-checks against prep data                                │
│  - Overrides misclassifications with rationale                   │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 5: Investigation + Sweep (parallel)          ┐             │
│  - 1 Investigation Agent per critical group (Opus) │ concurrent  │
│  - 1 Sweep Agent for important+skim files (Sonnet) │             │
│  Step 5b: Reuse-Candidacy Stage (parallel)         │             │
│  - 1 Reuse Agent per cluster (Opus)                ┘             │
│    (cognito-consistency-checker, ≤6 clusters)                    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 6: Planner Evaluates Sweep Escalations                     │
│  - Evaluates sweep escalation candidates                         │
│  - Optionally spawns ad-hoc investigation agents                 │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 7: Aggregate Findings JSON                                 │
│  - Combine investigation + sweep into unified input              │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 8: Deterministic Post-Processing (TypeScript)              │
│  - scripts/post-process.ts                                       │
│  - EMA weights, dedup, rank, filter, lifespan                    │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 9: Synthesizer Agent (Sonnet)                              │
│  - agents/synthesizer-v2.md                                      │
│  - Narrative review from processed findings + journey            │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Steps 10-12: Write Review + Finalize + Report                   │
│  - Write to .claude.local/reviews/                               │
│  - Finalize journey file                                         │
│  - Print completion output                                       │
└──────────────────────────────────────────────────────────────────┘
```

## Argument Parsing

**Determine mode from arguments:**
- If `$ARGUMENTS` contains a numeric PR ID → PR Mode
- If `$ARGUMENTS` is empty, "local", or contains only aspect keywords → Local Mode

**Parse all arguments:**
- **PR_ID**: First numeric token (e.g., `17890`)
- **aspects**: `all`, `csharp`, `frontend`, `api`, `consistency`, `testing` — defaults to `all`
- **sequential**: If present, run investigation agents sequentially instead of in parallel
- **--local**: Force local mode
- **--base <branch>**: Target branch for local diff (default: `main`)
- **--include-untracked**: Include untracked files in local review

## Review Workflow

### Step 1: Run Enhanced Prep Script

**PR Mode** — Run the TypeScript prep script to gather PR data via GitHub API:

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts {pr_id}
```

**Local Mode** — Run the prep script with `--local` to review uncommitted changes:

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts --local --base main --include-untracked
```

The script produces a cache with: manifest v2, pr-timeline.json, pr-context.json, diffs, downloaded files, structural-context/ for large files.

**Cache paths:**
- PR Mode: `.claude/pr-cache/{pr_id}/`
- Local Mode: `.claude/pr-cache/local/` (always overwritten)

**Cache check (PR Mode only):** The script automatically checks if cache is current (same iteration and commit). Use `--force` to rebuild cache.

**If the script fails**, stop and report the error. Common issues:
- PR Mode: Not logged in (`gh auth login`), PR doesn't exist, network error
- Local Mode: Not in a git repository, base branch doesn't exist

**IMPORTANT:** Wait for the script to complete before proceeding.

### Step 1.5: Enable Cache Boundary Enforcement

Create marker file to enable the PreToolUse hook that blocks reads outside the cache:

**PR Mode:**
```bash
echo '{"cacheDir": ".claude/pr-cache/{pr_id}", "prId": {pr_id}}' > .claude/pr-cache/pr-review-active.json
```

**Local Mode:**
```bash
echo '{"cacheDir": ".claude/pr-cache/local", "prId": 0, "local": true}' > .claude/pr-cache/pr-review-active.json
```

**IMPORTANT:** The marker file MUST be in the project directory (`.claude/pr-cache/`), NOT in `~/.claude/`. Writing to `~/.claude/` triggers Claude Code's "modify settings" permission prompt.

### Step 1.6: Resolve cog-docs Destination (PR Mode only)

Read `{cacheDir}/pr-context.json` and check `cogDocsItemDir`. This field controls where Step 10/11 land the review artifacts.

**If non-null:** nothing to do — proceed to Step 2.

**If null**, the prep script's deterministic resolution (materialized.json, `<wi_id>-*` dir scan, WIP.md branch match) found nothing. Attempt to resolve it yourself:

1. Locate the cog-docs root: `$COG_DOCS_ROOT` if set, else the sibling `../cog-docs` of the current repo. If neither exists, skip this step (artifacts fall back to `.claude.local/reviews/`).
2. List the item directories: `docs/features/*/` and `docs/bugs/*/`.
3. Match against the PR using, in order of strength:
   - A directory whose `<id>-` prefix matches a work item id you know for this PR (from the invocation, conversation context, or `workItems` in pr-context.json).
   - A directory whose name is a clear semantic match for the PR title or source branch slug (e.g. PR "Classify target action viability" / branch `p/is-target-action-filtering` → `docs/features/target-action-viability/`). Require an obvious single match — do not guess between plausible candidates.
4. **If exactly one confident match:** update `{cacheDir}/pr-context.json`, setting `cogDocsItemDir` to the matched directory's absolute path (edit the JSON in place; preserve all other fields). State which directory was chosen and why. Steps 10/11 then use it automatically.
5. **If no confident match (or ambiguous):** leave it null and note that artifacts will land in `.claude.local/reviews/`.

### Step 2: Launch Journey/Planner Agent

Read the manifest to understand PR context, then launch the journey/planner agent:

```
Agent:
  subagent_type: cognito-pr-review:journey-planner (or use the agent prompt file)
  prompt: |
    You are the Journey/Planner agent for PR #{pr_id}: {title}
    
    Cache directory: {cacheDir}
    Manifest: {cacheDir}/manifest.json
    PR context: {cacheDir}/pr-context.json
    PR timeline: {cacheDir}/pr-timeline.json
    {If re-review: Previous journey file: .claude.local/reviews/PR-{pr_id}-journey.md}
    {If re-review: Iteration diff: {cacheDir}/iteration-diff.json}
    
    TASK: Create (or update on re-review) the journey file at .claude.local/reviews/PR-{pr_id}-journey.md
    Read all prep context from the cache directory.
    Produce the journey file with: Overview, Objectives, File Change Map, Manual Review Guide, PR Lifecycle.
```

Read the agent's output and confirm journey file was created/updated.

### Step 3: Launch Triage Agent

```
Agent:
  subagent_type: cognito-pr-review:triage (or use agent prompt)
  prompt: |
    You are the Triage Agent for PR #{pr_id}: {title}
    
    Cache directory: {cacheDir}
    Journey file: .claude.local/reviews/PR-{pr_id}-journey.md
    Manifest: {cacheDir}/manifest.json
    {If re-review: Iteration diff: {cacheDir}/iteration-diff.json}
    {If re-review: PR context with thread statuses: {cacheDir}/pr-context.json}
    
    TASK: Classify all files into critical/important/skim tiers.
    Output triage JSON with critical, important, skim arrays.
    Each entry: { group, files, rationale, investigationFocus, reReviewNote }
```

Capture the triage JSON output.

### Step 4: Planner Validates Triage

Re-invoke the journey-planner agent to cross-check the triage:

```
Agent (journey-planner):
  prompt: |
    PLANNER VALIDATION MODE
    
    Triage JSON to validate:
    {triage JSON from step 3}
    
    Cache directory: {cacheDir}
    Journey file: .claude.local/reviews/PR-{pr_id}-journey.md
    
    Cross-check the triage against prep data:
    - Files touching core services classified as skim? → Override to important/critical
    - Files central to PR objectives classified below important? → Override
    - Re-review files that changed since last iteration classified as skim? → Override to at least important
    
    Return the validated/amended triage JSON with any overrides logged.
```

Use the validated triage for subsequent steps.

### Step 5: Dispatch Investigation + Sweep in Parallel

**Aspect filtering:** If the user specified aspects (e.g., `csharp`, `frontend`), filter which files go through the pipeline. Triage still classifies all files, but investigation/sweep agents only receive files matching the requested aspects.

**For each critical group** from validated triage, launch an investigation agent:

```
Agent (for each critical group):
  Read agents/investigation.md for the prompt template
  subagent_type: cognito-pr-review:investigation (or use agent prompt)
  prompt: |
    ## Your Assignment
    Group: {group.group}
    Investigation Focus: {group.investigationFocus}
    
    ## PR Context
    {Condensed from journey file overview + objectives}
    
    ## Files to Review
    {List of cached file paths + diffs for this group's files}
    {For large files: structural-context/{filename}.md path}
    
    Cache directory: {cacheDir}
```

**Launch sweep agent** on all important + skim files:

```
Agent:
  subagent_type: cognito-pr-review:sweep (or use agent prompt)
  prompt: |
    Review non-critical files for PR #{pr_id}: {title}
    
    Cache directory: {cacheDir}
    
    Triage tier assignments:
    Important: {list of important files with groups}
    Skim: {list of skim files with groups}
    
    Apply weight-aware thresholds:
    - Important tier: effective_weight >= 0.5
    - Skim tier: effective_weight >= 0.7
```

All investigation agents + sweep agent launch in parallel (or sequentially if `sequential` arg was provided).

**After each agent completes**, write its raw JSON output to `{cacheDir}/agent-output/`:
- Investigation agents: `{cacheDir}/agent-output/investigation-{group-slug}.json` (the agent already emits a `"group"` field in its JSON)
- Sweep agent: `{cacheDir}/agent-output/sweep.json`

Create the `agent-output/` directory if it doesn't exist. The group slug should be the group name lowercased with spaces replaced by hyphens (e.g., "Core Service Changes" → "core-service-changes").

### Step 5b: Reuse-Candidacy Stage (parallel with Step 5)

This stage runs **concurrently with Step 5** — it does NOT add serial latency. Launch the reuse agents at the same time as the investigation and sweep agents above (or sequentially after them if `sequential` arg was provided).

**Cluster the files:**

From `manifest.baselines[]` (populated by the prep script), select net-new or substantially-modified substantive files: services, types, components, helpers. Exclude pure test files, config files, and generated types. Group them into at most 6 clusters by domain area or shared concern (e.g., "Workflow Services", "Frontend Components", "API Types"). Each cluster should contain 1–6 files.

If `manifest.baselines[]` is empty or the manifest has no substantive net-new files, skip this step.

**For each cluster**, launch one reuse agent using `agents/cognito-consistency-checker.md`:

```
Agent (for each cluster — up to 6):
  Read agents/cognito-consistency-checker.md for the prompt template
  subagent_type: cognito-pr-review:cognito-consistency-checker
  prompt: |
    ## Your Assignment
    Cluster: {cluster name}
    Files in cluster: {list of cached file paths for this cluster's files}

    ## PR Context
    {Condensed from journey file overview + objectives}

    ## Cache
    Cache directory: {cacheDir}
    Manifest (with baselines[]): {cacheDir}/manifest.json

    ## Task
    Apply your full reuse-candidacy workflow (R1–R4, Steps 1–6) to this cluster.
    Write your output to: {cacheDir}/agent-output/reuse-{cluster-slug}.json

    ## Access Model
    You have investigation-level access: you may read ANY file in the local
    codebase on `main` and use tree-sitter MCP tools (get_file_structure,
    find_symbol_usages, get_callers, get_callees, get_dependencies).
    You do NOT have sweep's cache-only restriction.
```

**After each reuse agent completes**, confirm it wrote its output file:
- Reuse agents: `{cacheDir}/agent-output/reuse-{cluster-slug}.json`

The cluster slug is the cluster name lowercased with spaces replaced by hyphens (e.g., "Workflow Services" → "workflow-services") — the same convention as investigation group slugs. Step 7's aggregate script already picks up `reuse-*.json` files from `{cacheDir}/agent-output/`, and Step 8's post-process routes their findings through the investigation lane with verdict→severity mapping (`refactor`/`reuse` → `important`, `extend`/`wrap` → `nit`, `acceptable-new` → dropped).

### Step 6: Planner Evaluates Sweep Escalations

If the sweep agent returned any escalations:

```
Agent (journey-planner):
  prompt: |
    ESCALATION EVALUATION MODE
    
    Sweep escalations:
    {escalations JSON}
    
    For each escalation, decide:
    - Is this worthy of a dedicated investigation agent?
    - Or can it be included as-is in the findings?
    
    If spawning ad-hoc investigators, specify the group and focus.
```

If planner approves ad-hoc investigators, spawn them and collect their output.

If no escalations, skip this step.

### Step 7: Aggregate Findings JSON

Run the aggregation script to combine all agent outputs into the unified CombinedFindings format expected by post-process.ts:

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/aggregate-findings.ts --cache-dir {cacheDir} --manifest {cacheDir}/manifest.json [--previous-review .claude.local/reviews/PR-{pr_id}.md]
```

The `--previous-review` flag is only included for re-reviews.

The script reads all `investigation-*.json` and `sweep.json` from `{cacheDir}/agent-output/`, validates their structure, and writes `{cacheDir}/combined-findings.json`.

### Step 8: Run Deterministic Post-Processing

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/post-process.ts --input {cacheDir}/combined-findings.json --manifest {cacheDir}/manifest.json [--previous-review .claude.local/reviews/PR-{pr_id}.md]
```

The `--previous-review` flag is only included for re-reviews.

Capture stdout (processed findings JSON). Write to `{cacheDir}/processed-findings.json`.

### Step 9: Launch Synthesizer Agent

```
Agent:
  subagent_type: cognito-pr-review:synthesizer-v2 (or use agents/synthesizer-v2.md)
  model: sonnet
  prompt: |
    Synthesize the final review for PR #{pr_id}: {title}
    
    Read these files:
    - Processed findings: {cacheDir}/processed-findings.json
    - Journey file: .claude.local/reviews/PR-{pr_id}-journey.md
    - Triage classification: {validated triage JSON inline or file path}
    
    PR metadata:
    - Author: {author}
    - Branch: {source} → {target}
    - Date: {current date}
    - Review type: {Initial | Re-review (iteration {n})}
    
    Produce the final review markdown following your output format template.
```

### Step 10: Write Review

Read `{cacheDir}/pr-context.json` and check the `cogDocsItemDir` field.

**PR Mode — cogDocsItemDir is set (non-null):**
Write both the review artifact and the journey file under the cog-docs item directory:
- `<cogDocsItemDir>/PR-{pr_id}.md` — the synthesized review
- `<cogDocsItemDir>/PR-{pr_id}-journey.md` — the persistent journey file

```bash
mkdir -p "<cogDocsItemDir>"
# Write PR-{pr_id}.md and PR-{pr_id}-journey.md to <cogDocsItemDir>
```

**PR Mode — cogDocsItemDir is null/absent:**
Fall back to the default location (unchanged behavior):
- `.claude.local/reviews/PR-{pr_id}.md`
- `.claude.local/reviews/PR-{pr_id}-journey.md`

```bash
mkdir -p ".claude.local/reviews"
# Write review content to .claude.local/reviews/PR-{pr_id}.md
```

**Local Mode (unchanged):** Write to `.claude.local/reviews/LOCAL-{branch}-{timestamp}.md`

```bash
mkdir -p ".claude.local/reviews"
# Write review content
```

### Step 11: Finalize Journey File

The journey file was already created in Step 2. No additional action needed unless planner has updates.

### Step 12: Print Completion Output

Report to user:
- Cache directory path
- Review artifact path
- Journey file path
- Summary stats (findings count by tier, dropped, deduped)

### Step 12.5: Cleanup Cache Boundary Marker

Remove the marker file to restore normal Read behavior:

```bash
rm -f .claude/pr-cache/pr-review-active.json
```

### Step 12.6: Emit REVIEWED.md Sentinel (cog-docs only)

Read `{cacheDir}/pr-context.json` and check the `cogDocsItemDir` field (the same field used in Step 10).

**IF `cogDocsItemDir` is non-null:**

Write `<cogDocsItemDir>/REVIEWED.md` with YAML frontmatter carrying the PR identity, today's date, and the finding counts reported in Step 12 (total count plus per-tier counts — critical, important, minor — as produced by the synthesizer). Follow the frontmatter with a one-line human-readable body.

Template (substitute live values; use ISO date `YYYY-MM-DD` for `date`):

```bash
cat > "<cogDocsItemDir>/REVIEWED.md" << 'EOF'
---
kind: reviewed
pr: {pr_id}
date: "{YYYY-MM-DD}"
findings_total: {total_findings_count}
critical: {critical_count}
important: {important_count}
minor: {minor_count}
---
# Reviewed
EOF
```

This makes `derive_stage` report stage `reviewed` for the cog-docs item (it detects `REVIEWED.md` presence).

**IF `cogDocsItemDir` is null/absent:** no-op — do nothing. No `REVIEWED.md` is written; the review still landed in `.claude.local/reviews/` per Step 10's fallback. This step is entirely skipped.

**On write failure:** WARN the user (e.g. "Warning: could not write REVIEWED.md to <path> — <reason>") and continue. Never block or fail the review on this write; the review artifact from Step 10 is the primary deliverable.

**No ADO board write:** this step is a purely local stage signal. The ADO poller PAT is read-only; do not attempt any ADO board or work-item update here.

### Step 13: Cache Cleanup (Background)

Optionally clean up old caches (>7 days):

```bash
find .claude/pr-cache -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \;
```

## Usage Examples

**Review a specific PR by ID:**
```
/cognito-pr-review:review-pr 17890
```

**Review local uncommitted changes:**
```
/cognito-pr-review:review-pr
```

**Review local changes, C# only:**
```
/cognito-pr-review:review-pr csharp
```

**Review local changes, frontend only:**
```
/cognito-pr-review:review-pr frontend
```

**Review a PR sequentially:**
```
/cognito-pr-review:review-pr 17890 sequential
```

## Component Descriptions

**prep-pr.ts** (deterministic TypeScript):
- Fetches PR data, timeline, iteration diffs, thread statuses, structural context
- Manifest v2 with structural context for large files
- Uses GitHub REST API for all data — no dependency on local git branch state
- Writes cache to `.claude/pr-cache/{pr-number}/`

**journey-planner** (Opus):
- Creates persistent journey file at `.claude.local/reviews/PR-{id}-journey.md`
- Contains: overview, objectives, file change map, manual review guide, PR lifecycle
- Validates triage classifications as hierarchical planner
- Evaluates sweep escalations for ad-hoc investigation dispatch
- Re-review: appends new iteration section to existing journey

**triage** (Opus):
- Classifies files into critical / important / skim tiers
- Groups related files for investigation assignments
- Re-review: tier boost for changed + unresolved files

**investigation** (Opus):
- Deep-dive critical areas with Solver-Verifier protocol
- One agent per critical group from triage
- Reads cached diffs + structural context for large files

**sweep** (Sonnet):
- Rule-based review of important + skim files
- Weight-aware thresholds (important >= 0.5, skim >= 0.7)
- Escalation pathway for findings that warrant deeper investigation

**cognito-consistency-checker** (Opus) — reuse-candidacy stage:
- One agent per cluster of net-new / substantially-modified substantive files (≤6 clusters)
- Applies R1–R4 reuse-discovery protocol: extract capabilities, baseline-first check, capability-level discovery, duplicate-logic detection
- Inherits investigation access model: reads local codebase on `main` + tree-sitter MCP tools; NOT cache-only
- Writes `{cacheDir}/agent-output/reuse-{cluster-slug}.json`; aggregate-findings.ts picks up `reuse-*.json` automatically

**post-process.ts** (deterministic TypeScript):
- EMA weight application, deduplication, ranking, filtering
- Lifespan annotation for re-review tracking
- Deterministic — no LLM involved

**synthesizer-v2** (Sonnet):
- Narrative review synthesis from processed findings + journey
- Produces final review markdown

## Forward Compatibility Note

Investigation agent tool list is defined in the agent prompt (agents/investigation.md), not hardcoded here. Phase 9 Tree-Sitter tools can be added to the agent prompt without changing this orchestration command.

## Notes

- No more 6 parallel specialist agents — replaced by journey → triage → investigation+sweep → post-process → synthesize
- Synthesizer is Sonnet (not Haiku)
- Post-processing is deterministic TypeScript (not LLM)
- Journey file is a persistent artifact for human consumption
- Triage validation prevents cascading misclassification
- Escalation pathway from sweep to investigation
- Prep script is deterministic TypeScript (not LLM) — ensures correct file counts
- Uses GitHub REST API for all data — no dependency on local git branch state
- Cache is reused if iteration and commit unchanged

## Local Mode

Local mode allows reviewing uncommitted/unpushed changes before creating a PR.

**How it works:**
- Uses `git diff` to detect changed files (staged, unstaged, and optionally untracked)
- Compares working tree against a base branch (default: `main`)
- Reads file content directly from filesystem
- Generates diffs locally without requiring GitHub API access

**Invocation:**
- No PR ID → automatic local mode
- Explicit `local` keyword → local mode
- Numeric PR ID → PR mode (existing behavior)

**Options in prep-pr.ts:**
- `--base <branch>`: Target branch to diff against (default: `main`)
- `--include-untracked`: Include untracked files in review

**Cache location:** `.claude/pr-cache/local/` (always overwritten — no iteration tracking)
