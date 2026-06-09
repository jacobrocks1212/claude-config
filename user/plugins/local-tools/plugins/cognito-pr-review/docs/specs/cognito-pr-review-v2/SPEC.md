# Cognito PR Review Plugin v2 — Feature Specification

> Rework the cognito-pr-review plugin from a rule-scanning system into a critical-first, investigation-driven review system that mirrors Jacob's manual review process, with first-class re-review support and iterative calibration.

**Status:** Final
**Priority:** P1
**Last updated:** 2026-05-06
**Depends on:** Existing cognito-pr-review plugin v2.4.0, Azure DevOps REST API access

---

## Executive Summary

The current cognito-pr-review plugin (v2.4.0) runs 6 specialist agents in parallel, each scanning for YAML rule violations, then synthesizes findings via a Haiku aggregator. After ~30 reviews, the core feedback is: it catches small inconsistencies well but produces significant noise and fails to deeply investigate the changes that actually matter.

v2 fundamentally restructures the review pipeline from "scan everything for rule violations" to "understand the PR → identify what's critical → investigate critical areas deeply → sweep the rest lightly." The new pipeline introduces a **Hierarchical Planner** (Journey Agent elevated to orchestrator role, producing persistent PR lifecycle documentation and validating triage before dispatching work), a **Triage Agent** (criticality classification combining semantic + deterministic signals), **Investigation Agents** (deep-dive with full codebase exploration, Solver-Verifier grounding, and specialist escalation), a **Sweep Agent** (rule-based review with escalation rights), and an upgraded **Sonnet Synthesizer** (weight-based ranking + narrative review).

A **per-rule + category-multiplier weight system** uses Exponential Moving Average (EMA) calibration against actual human review feedback. Re-reviews are first-class: auto-detected, iteration-aware, comment-resolution-tracking, with finding lifespan tracking across iterations.

---

## Pipeline Architecture

### v1 (Current)
```
Prep Script → [6 Specialist Agents (parallel)] → Haiku Synthesizer → Review File
```

### v2 (Proposed)
```
┌──────────────────────────────────────────────────────────────────┐
│  Phase 1: Enhanced Prep Script (deterministic)                   │
│  - Everything from v1 (ADO API, files, diffs, manifest)          │
│  - NEW: PR timeline/lifecycle metadata                           │
│  - NEW: ADO iteration diffs (what changed between iterations)    │
│  - NEW: PR thread status tracking (active/resolved/won't fix)    │
│  - NEW: ADO status history (votes, status changes, approvals)    │
│  - NEW: Detect existing journey file → flag as re-review         │
│  - NEW: Context distillation for large files (Haiku sub-agent)   │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Phase 2: Hierarchical Planner / Journey Agent (Opus)            │
│  - Reads all prep context + previous journey file (if re-review) │
│  - Produces persistent PR-{id}-journey.md                        │
│  - Contains: PR overview, objective mapping, manual review guide │
│  - On re-review: appends new iteration section, tracks lifecycle │
│  - PLANNER ROLE: Validates triage output before dispatching      │
│    investigation. Acts as orchestrator, not just document writer. │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Phase 3: Triage Agent (Opus)                                    │
│  - Reads journey file + prep context                             │
│  - Classifies each file/change-group as critical/important/skim  │
│  - Signals: PR objective alignment × code complexity/blast radius│
│  - On re-review: prioritizes changed areas + unresolved comments │
│  - Outputs triage manifest (JSON)                                │
│  ↕ VALIDATION: Planner cross-checks triage against prep metrics  │
│    before proceeding. Overrides obvious misclassifications.       │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Phase 4: Investigation + Sweep (parallel)                       │
│                                                                  │
│  Investigation Agents (1 per critical area, Opus):               │
│  - Deep-dive critical changes with Solver-Verifier grounding     │
│  - Full codebase access (aware: local = main, not PR branch)     │
│  - Consider alternatives, explore patterns, validate approach    │
│  - Can escalate to specialist sub-agents (security, perf, etc.)  │
│                                                                  │
│  Sweep Agent (1 agent, Sonnet):                                  │
│  - Runs full rule set against non-critical files                 │
│  - Higher confidence thresholds for skim tier (noise reduction)  │
│  - ESCALATION RIGHTS: Can promote findings to investigation tier │
│  ↕ Planner evaluates escalations, spawns ad-hoc investigators   │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Phase 5: Synthesizer (Sonnet)                                   │
│  - Deterministic pre-processing: EMA weight application, dedup   │
│  - LLM synthesis: narrative review, prioritized findings         │
│  - Reads journey file for PR context in narrative                │
│  - Finding lifespan annotations for re-reviews                   │
│  - Outputs final review markdown                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Enhanced Prep Script

### Existing Capabilities (Preserved)
- Fetch PR metadata via ADO REST API
- Server-side diff with `diffCommonCommit=true`
- File content download via Items API
- Manifest generation with aspects, baselines
- PR context fetch (description, comments, work items)
- Local mode via `git diff`

### New Capabilities

#### 1.1 PR Timeline Metadata
Fetch and structure the chronological lifecycle of the PR:
- Creation date, all iteration timestamps
- Vote history (who voted when, what value)
- Status transitions (Active → Waiting for Author → Active → Approved)
- Comment thread timeline (when threads were created, resolved, re-activated)

**Data source:** ADO REST API — `GET /pullrequests/{id}/threads`, `GET /pullrequests/{id}/iterations`, `GET /pullrequests/{id}/statuses`

**Output:** New `pr-timeline.json` in cache directory.

#### 1.2 Iteration Diffs
When re-reviewing, compute what changed between the current and previous iteration:
- Files added/removed/modified since last reviewed iteration
- Per-file diff-of-diffs (what specifically changed in each file between iterations)

**Data source:** ADO REST API — `GET /pullrequests/{id}/iterations/{iterationId}/changes`

**Output:** New `iteration-diff.json` in cache directory (only present on re-reviews).

#### 1.3 Thread Status Tracking
For each PR comment thread, track:
- Thread status: active, resolved, won't-fix, closed
- Whether the thread was created by the current user (reviewer) vs. author vs. others
- Thread context: which file/line, what iteration

**Output:** Enhanced `pr-context.json` with structured thread data.

#### 1.4 Re-Review Detection
Check for existing journey file at `.claude.local/reviews/PR-{id}-journey.md`:
- If found → set `manifest.isReReview = true`
- Record `manifest.previousIterationId` from journey file metadata
- Include path to previous journey file in manifest

#### 1.5 Context Distillation for Large Files
For files exceeding 2000 lines, generate structural context:

**For known large files** with existing skills:
- `build.js` → invoke `/build-js` skill index to get function/section map
- `FormsService.cs` → invoke `/forms-service` skill index to get method map
- Output: `structural-context/{filename}.md` in cache directory

**For other large files:**
- Spawn a Haiku context distiller sub-agent that reads the full file + diff
- Distiller extracts: modified functions/methods, their immediate callers and callees, class-level state variables, and surrounding structural context
- Output: `structural-context/{filename}.md` — a condensed, structurally coherent payload for the investigation or sweep agent
- This ensures the expensive Opus investigator receives only high-signal context from massive files

### Manifest v2 Schema Additions
```json
{
  "version": 2,
  "isReReview": false,
  "previousIterationId": null,
  "journeyFile": null,
  "timelineFile": "pr-timeline.json",
  "iterationDiffFile": null,
  "structuralContextFiles": [],
  "aspects": [],
  "files": [],
  "weights": "weights.yaml"
}
```

---

## Phase 2: Hierarchical Planner / Journey Agent

### Dual Role

The Journey Agent serves two functions:

1. **Document Producer:** Creates and maintains the persistent journey file for human consumption
2. **Hierarchical Planner:** Orchestrates the review pipeline by validating triage output and managing the investigation/sweep dispatch. This prevents cascading triage failures — if the triage agent misclassifies a critical architectural change as "skim," the planner catches the inconsistency before investigation agents are spawned.

### Journey Document

**Path:** `.claude.local/reviews/PR-{id}-journey.md`

```markdown
# PR #{id} — {title}

## Overview
{2-3 paragraph summary: what this PR does, why, and how}

## Objectives
{Extracted from WI + PR description, mapped to specific file changes}
- Objective 1: {description} → {files}
- Objective 2: {description} → {files}

## File Change Map
{Logical grouping of all changed files by purpose}

| Group | Files | Purpose | Review Priority |
|-------|-------|---------|-----------------|
| Core Implementation | service.cs, model.cs | Main feature logic | Critical |
| API Surface | controller.cs | Endpoint changes | Important |
| Generated Types | *.ts | Auto-generated from server | Skim |
| Tests | *Tests.cs | Validation of core changes | After core |

## Manual Review Guide
{Ordered list of file groups to review, core changes first, tests last}

### Step 1: {Group Name}
- **Files:** {list}
- **What to look for:** {specific guidance}
- **Key questions:** {what the reviewer should be asking}

### Step 2: ...

## PR Lifecycle
{Chronological record, accumulated across re-reviews, unlimited}

### Iteration 1 (2026-05-01)
- Initial submission
- {summary of initial changes}

### Iteration 2 (2026-05-04) — Re-review
- **Changes since last review:** {summary}
- **Comments addressed:** {list of resolved threads}
- **Comments still open:** {list of unresolved threads}
- **New changes:** {anything added that wasn't in previous feedback}
- **Finding lifespan:** {findings raised N times across iterations}
```

### Planner Validation Logic

After the Triage Agent produces its classification, the Planner:

1. Cross-checks triage output against prep script data:
   - Files touching core services/shared utilities classified as skim? → Override to important/critical
   - Files central to the PR's stated objectives (from journey) classified below important? → Override
   - Re-review: files that changed since last iteration still classified as skim? → Override to at least important
2. If overrides are needed, the Planner amends the triage manifest with rationale
3. Only after validation does the Planner dispatch investigation + sweep agents

### Planner Orchestration Responsibilities

The review-pr command acts as the outer orchestrator, but the Planner agent is the *intelligent* orchestrator:
- Dispatches investigation agents with tailored prompts per critical group
- Monitors sweep agent escalation requests
- Spawns ad-hoc investigation agents for escalated findings
- Passes all collected findings to the deterministic post-processor → synthesizer

### Re-Review Behavior
When `manifest.isReReview` is true:
1. Read the existing journey file
2. Read `iteration-diff.json` to understand what changed
3. Read PR thread statuses to track comment resolution
4. Append a new iteration section to the lifecycle
5. Update the file change map with current state
6. Update finding lifespan counts (how many iterations each finding has persisted)
7. Regenerate the manual review guide, prioritizing:
   - Changed files since last review
   - Files with unresolved review comments
   - Then unchanged critical files
   - Then everything else

### Agent Configuration
- **Model:** Opus
- **Input:** manifest.json, pr-context.json, pr-timeline.json, all diffs, previous journey file (if re-review), iteration-diff.json (if re-review), triage output (for validation)
- **Output:** Journey markdown file + validated triage manifest
- **Allowed tools:** Read, Write (for journey file), Agent (for dispatching investigators)

---

## Phase 3: Triage Agent

### Purpose
Classify each file or change-group into criticality tiers that determine the depth of review. Output is validated by the Planner before investigation proceeds.

### Criticality Classification

**Tier 1 — Critical:** Changes central to the PR's stated objective AND touching code with high complexity or blast radius. These get Investigation Agents.

**Tier 2 — Important:** Changes supporting the PR's objective or touching moderately important code. These get the Sweep Agent with standard confidence thresholds.

**Tier 3 — Skim:** Supporting changes like type regeneration, trivial test updates, formatting, or changes with minimal blast radius. These get the Sweep Agent with elevated confidence thresholds.

### Triage Signals

The agent combines two signal dimensions:

**PR Objective Alignment** (from journey file):
- How directly does this file/change relate to the PR's stated goals?
- Is this implementing the feature, or is it a cascading change?

**Code Complexity / Blast Radius:**
- Is this a core service, shared utility, or high-fan-out code?
- How many other files depend on this code?
- Is this a new pattern being introduced, or following existing patterns?

**Re-Review Priority Boost:**
- Files that changed since the last review get a tier boost
- Files with unresolved review comments get a tier boost
- Net effect: a previously-skim file that changed becomes at least important

### Triage Output
```json
{
  "critical": [
    {
      "group": "Entry Index Service Changes",
      "files": ["EntryIndexService.cs", "CompositeEntryIndex.cs"],
      "rationale": "Core indexing logic changes implementing the PR's main objective. EntryIndexService is a high-fan-out service.",
      "investigationFocus": "Verify index rebuild logic handles edge cases. Check if EntrySummaryFormat lifecycle is correct.",
      "reReviewNote": "Lines 2140-2180 changed since last review to address comment about error handling."
    }
  ],
  "important": [...],
  "skim": [...]
}
```

### Agent Configuration
- **Model:** Opus
- **Input:** Journey file, manifest.json, all diffs (for a holistic view), pr-context.json
- **Output:** Triage JSON (subject to Planner validation)
- **Allowed tools:** Read (cache files + journey file)

---

## Phase 4: Investigation + Sweep

### Investigation Agents

**Purpose:** Deep-dive critical change areas. Unlike v1 specialist agents that scan for rule violations, investigation agents *think* about the changes — considering the approach, alternatives, edge cases, and correctness.

**Investigation Agent Prompt Pattern:**
```
You are reviewing a critical area of PR #{id}: {title}

## Your Assignment
{group name}: {investigationFocus from triage}

## PR Context
{Condensed from journey file: what the PR does, its objectives}

## Files to Review (from PR cache)
{List of cached file paths + diffs for this group}
{If large file: include structural-context/{filename}.md}

## Your Task
1. Read the diffs and full files for your assigned group
2. Understand what the changes are doing and WHY
3. Think about the approach:
   - Is this the right way to solve this problem?
   - Are there edge cases that aren't handled?
   - Would an alternative approach be better? If so, why?
4. If you need to validate an assumption or explore an alternative,
   you may read files from the codebase. NOTE: The local codebase is
   on the 'main' branch, NOT the PR branch. Use it for:
   - Finding existing patterns to compare against
   - Checking how similar problems are solved elsewhere
   - Validating that referenced APIs/methods exist and work as expected
   - Understanding the broader context of the code being changed
   DO NOT use local files as the "current state" of PR files — use
   the cached versions for that.
5. Return findings as structured JSON

## Solver-Verifier Protocol
For EVERY finding you intend to report:
1. GENERATE your hypothesis (the issue you think exists)
2. VERIFY it against evidence:
   - Read the actual code (cached PR files or codebase) that proves your point
   - If suggesting an alternative, confirm the alternative is viable by
     checking that the APIs/patterns you're suggesting actually exist in
     this codebase
   - If claiming a bug, trace the execution path through the code
3. Only include the finding if verification succeeds
4. Include your evidence in the finding output

Do NOT report findings based on general best practices alone.
Every finding must cite specific code evidence from this PR or codebase.

## Specialist Escalation
If you identify a concern that requires domain expertise beyond your
assignment (e.g., a security issue in an architecture review, a
performance concern in a business logic review), flag it as an
escalation candidate with the specialist domain needed. The Planner
may spawn a specialist sub-agent to investigate further.

## What makes a good finding
- Correctness issues (bugs, missing edge cases, stale state)
- Better alternatives backed by codebase evidence
- Missed interactions with other parts of the system
- Architectural concerns with the approach

## What to AVOID
- Style nits (naming, formatting)
- Rule-based pattern matching (the sweep agent handles that)
- Findings without evidence or specific suggestions
- Hallucinated APIs or patterns that don't exist in this codebase
```

**Key Behaviors:**
- Can read ANY file in the repo via the Read tool (for codebase exploration)
- Must use cached files for the PR's actual content
- Must verify every finding via the Solver-Verifier protocol before reporting
- Can flag findings for specialist escalation (security, performance, etc.)
- Returns structured findings with evidence, not just observations

**Agent Configuration:**
- **Model:** Opus
- **Allowed tools:** Read (unrestricted), Grep, Glob (for codebase exploration)
- **Parallelism:** All investigation agents launch in parallel
- **No token cap:** Trust the agent to be appropriately thorough

### Sweep Agent

**Purpose:** Run the existing rule set against non-critical files to maintain the small-bug-catching value of v1, but with noise reduction via elevated confidence thresholds.

**Sweep Agent Behavior:**
- Reviews all important + skim tier files
- Applies the full YAML rule set (all categories)
- Uses the weight system to determine effective confidence thresholds:
  - Important tier: standard thresholds (same as v1)
  - Skim tier: thresholds elevated by +10% (e.g., architecture goes from 80% → 90%)
- Returns findings in the same JSON format as v1 specialist agents

**Escalation Rights:**
The sweep agent can flag findings as escalation candidates when it detects high-severity issues in non-critical files (e.g., a security vulnerability in a skim-tier file). Escalation candidates are sent to the Planner, which evaluates them and optionally spawns an ad-hoc investigation agent for the escalated file. This catches triage misclassifications without requiring the sweep agent to do deep investigation.

**Agent Configuration:**
- **Model:** Sonnet
- **Input:** Manifest, diffs, full files for important/skim tier, all YAML rules, weight configuration, structural context for large files
- **Allowed tools:** Read (cache only — cache boundary enforced)
- **Parallelism:** Runs in parallel with investigation agents

---

## Phase 5: Synthesizer

### Deterministic Pre-Processing

Before the LLM synthesizer runs, a deterministic step (TypeScript post-processing script) handles:

1. **EMA Weight Application:** Load `weights.yaml`, compute effective weight for each finding:
   ```
   effective_weight = rule_weight × category_multiplier
   ```
   Findings below a minimum effective weight threshold (e.g., 0.3) are dropped.

2. **Deduplication:** Same file:line from multiple sources → keep highest-weighted finding.

3. **Ranking:** Sort findings by:
   - Tier (critical > important > skim)
   - Severity within tier (blocking > important > nit)
   - Effective weight within severity

4. **Out-of-Scope Filtering:** Drop findings for files not in the manifest.

5. **Finding Lifespan Annotation (re-reviews):** For each finding, check if a semantically equivalent finding was raised in previous iterations. Annotate with iteration count (e.g., "raised in 2 of 3 iterations").

### LLM Synthesis (Sonnet)

The upgraded synthesizer receives:
- Pre-processed, ranked findings from all agents
- Journey file for PR context
- Triage classification for framing

**Synthesizer responsibilities:**
- Write a narrative summary that contextualizes findings within the PR's objectives
- Group related findings (e.g., "the approach to X has three related concerns...")
- Distinguish between investigation findings (deep, evidence-based) and sweep findings (rule-based)
- On re-reviews: highlight what's new vs. carried forward, note resolved comments, include finding lifespan
- Produce the final review markdown

### Output Format

```markdown
# Cognito PR Review — PR #{id}: {title}

**Author:** {author}
**Branch:** {source} → {target}
**Date:** {date}
**Review type:** {Initial | Re-review (iteration {n})}

---

## Summary
{2-3 paragraph narrative: what the PR does, overall assessment, key concerns}

## Critical Findings
{Investigation agent findings — deep, evidence-based, verified}

### {Finding title}
**File:** {path}:{line}
**Severity:** {blocking|important}
**Evidence:** {what the investigation agent found in the codebase}
**Suggestion:** {specific, grounded recommendation}
{If re-review: **Lifespan:** Raised in {n} of {m} iterations}

## Rule-Based Findings
{Sweep agent findings — pattern-matching}

### Important
- {finding} [{file}:{line}] (weight: {effective_weight})

### Minor
- {finding} [{file}:{line}] (weight: {effective_weight})

## Re-Review Status (if applicable)
- **Comments resolved:** {count} of {total}
- **Unresolved threads:** {list with context}
- **New changes since last review:** {summary}
- **Persistent findings:** {findings raised across multiple iterations}

## Strengths
- {what's well-done}
```

---

## Weight System

### Structure

**File:** `{plugin_root}/knowledge/weights.yaml`

```yaml
version: 1
last_calibrated: "2026-05-06"
calibration_prs: [17766, 17821, 17837, ...]
ema_alpha: 0.25

category_multipliers:
  architecture: 1.0
  frontend: 1.0
  api_design: 1.0
  consistency: 0.8
  testing: 0.9
  security: 1.2
  performance: 0.9
  template_binding: 0.7

rule_weights:
  prefer-abstract-over-lambda:
    weight: 0.85
    data_points: 12
  no-default-di-parameters:
    weight: 0.95
    data_points: 8
  storage-context-query-deprecated:
    weight: 1.0
    data_points: 5
  # ... all ~100 rules
```

### Effective Weight Calculation
```
effective_weight = rule_weight × category_multiplier
```

### Threshold Application
- Investigation findings: no weight filtering (they're already high-value by design)
- Sweep findings (important tier): surface if `effective_weight >= 0.5`
- Sweep findings (skim tier): surface if `effective_weight >= 0.7`

### EMA Weight Update Formula
```
new_weight = α × signal + (1 - α) × old_weight
```
Where:
- `α` = 0.25 (configurable in weights.yaml as `ema_alpha`)
- `signal` = 1.0 for true positive, 0.0 for false positive
- Converges to useful values in ~10-15 data points
- Heavily weights recent feedback, naturally adapts when team standards shift

### Weight Decay (Future Consideration)
Rules that consistently fire without producing human action could have their weights automatically decayed. Not in v2 scope but the EMA system naturally trends weights toward 0 for rules that are consistently false positives.

---

## Calibration System

### One-Time Bulk Calibration

**Goal:** Analyze all ~30 historical reviews to establish baseline weights.

**Process:**
1. For each reviewed PR (from `.claude.local/reviews/PR-*.md`):
   a. Pull actual ADO comments left by Jacob via `get-pr-comments.ps1`
   b. Parse the plugin's review artifact to extract all findings
   c. Match findings to comments using **hybrid matching:**
      - **Step 1 — Proximity filter:** Match by file + line proximity (same file, within ~20 lines)
      - **Step 2 — Semantic judge:** For proximity-matched pairs, use a Haiku LLM judge to evaluate whether the plugin finding and human comment refer to the same issue
   d. Classify each plugin finding as:
      - **True Positive:** Plugin found it AND Jacob left a semantically matched comment
      - **False Positive:** Plugin found it but no corresponding human comment (noise)
      - **False Negative:** Jacob commented but plugin did NOT find a matching issue (gap)
2. Aggregate across all PRs:
   - Per-rule false positive rate → lower weight via EMA
   - Per-rule true positive rate → higher weight via EMA
   - Per-category aggregated rates → category multipliers
3. Identify false-negative patterns → candidates for new rules or investigation prompts
4. Write initial `weights.yaml`

**Output:** `weights.yaml` + `calibration-report.md` documenting the analysis.

### Ongoing Calibration (Enhanced Learn-from-PR)

The existing `/cognito-pr-review:learn-from-pr` command is enhanced to:

1. **Compare findings vs. actual comments:**
   - Pull ADO comments for the PR
   - Load the plugin's review artifact
   - Use hybrid matching (proximity + Haiku judge) to compute TP/FP/FN
   - Update `weights.yaml` via EMA:
     ```
     new_weight = α × signal + (1 - α) × old_weight
     ```
   - Increment `data_points` counter for each affected rule

2. **Extract new rules** (existing behavior, improved):
   - Analyze false negatives for generalizable patterns
   - Propose new rules via AskUserQuestion (same as today)
   - New rules start with a default weight of 0.7 (cautious)

3. **NO names recorded:**
   - Rules never include a `source` field
   - Comments are analyzed for patterns, not attributed to individuals

---

## Re-Review System

### Detection
Automatic. The enhanced prep script checks for an existing journey file at `.claude.local/reviews/PR-{id}-journey.md`. If found:
- `manifest.isReReview = true`
- `manifest.previousIterationId` extracted from journey file metadata
- Iteration diff computed between previous and current iteration

### Finding Lifespan Tracking
Each finding in the review artifact includes a unique fingerprint (rule ID + file + approximate line range). Across re-reviews, the system tracks how many iterations each finding has persisted. This is surfaced in the synthesized review:
- "Raised in 1 of 1 iterations" — new finding
- "Raised in 3 of 3 iterations" — persistent finding, may indicate a contested issue

The system tracks but does not suppress persistent findings. The lifespan annotation gives the human reviewer context to decide whether to escalate, accept, or dismiss.

### Re-Review Pipeline Behavior

**Planner / Journey Agent:**
- Reads existing journey file
- Appends new iteration section with: what changed, why (inferred from commit messages + PR comments), which threads were resolved
- Updates the file change map and review guide to reflect current state
- Updates finding lifespan counts
- Prioritizes: changed files → unresolved comment files → unchanged critical → rest

**Triage Agent:**
- Reads updated journey file (with iteration history)
- Applies tier boost to files that changed since last review
- Applies tier boost to files with unresolved review comments
- Still performs full triage (doesn't skip unchanged files)

**Investigation Agents:**
- Full re-review of all critical areas, but investigation focus is shaped by re-review context
- For previously-reviewed critical areas that haven't changed: lighter investigation, focused on "was previous feedback addressed?"
- For newly-critical areas or changed critical areas: full investigation depth

**Sweep Agent:**
- Full sweep of all important/skim files (same as initial review)
- No special re-review logic needed — the weight system handles noise

**Synthesizer:**
- Highlights what's new vs. carried forward from previous review
- Notes resolved vs. unresolved comment threads
- Includes finding lifespan annotations
- Frames the review in the context of the PR's evolution

---

## Name Scrubbing

### Scope
1. Remove all `source` fields from all YAML rule files (~100 rules across 8 files)
2. Remove any inline name references in agent prompt files
3. Update `learn-from-pr` to never record names or source fields
4. Update `rebuild-agents` to not propagate source fields into agent prompts

### Implementation
- One-time script to strip `source:` lines from all YAML files
- One-time manual review of agent .md files to remove name references
- Update learn-from-pr.md to exclude source field from rule template
- Update rebuild-agents.md to skip source field when embedding rules

---

## Large File Strategy

### Problem
Files like `build.js` (22K+ lines) and `FormsService.cs` (9.6K+ lines) are too large for agents to read in full. The current diff-only approach provides insufficient surrounding context for meaningful review.

### Solution: Skill-Based Context + Haiku Context Distillation

**For known large files** with existing skills:
- `build.js` → invoke `/build-js` skill index to get function/section map
- `FormsService.cs` → invoke `/forms-service` skill index to get method map
- Output: `structural-context/{filename}.md` in cache directory

**For other large files (>2000 lines):**
- Spawn a Haiku context distiller sub-agent during the prep phase
- The distiller reads the full file + diff and extracts:
  - Modified functions/methods with their complete bodies
  - Immediate callers and callees of modified functions
  - Class-level state variables and constants referenced by modified code
  - Surrounding structural context (class hierarchy, interface implementations)
- Output: `structural-context/{filename}.md` — a condensed, structurally coherent payload
- This ensures the expensive Opus investigator receives only high-signal context without reading 20K+ lines

**Agent Instructions:** When reviewing a large file, read the structural context first to understand the file's organization and the specific relevant code, then review the diff with that context in mind.

---

## Tree-Sitter MCP Server (Deferred)

### Purpose
Provide investigation agents with graph-native codebase queries instead of raw file reads. This enables symbol lookups, call graph traversal, impact analysis, and dependency mapping.

### Rationale
Research demonstrates that AST-backed agents achieve higher answer quality while consuming 10x fewer tokens compared to text-based file exploration. For a 500K-line monorepo, structural indexing is the long-term answer to efficient codebase exploration.

### Scope
In-scope for v2 but deferred to the end of the implementation phases. The investigation agents will initially use raw Read/Grep/Glob tools (which already work well in Claude Code). Tree-Sitter MCP is an optimization layer that improves efficiency without changing the pipeline architecture.

### Planned Capabilities
- `find_symbol_usages(symbol)` — find all references to a symbol
- `get_callers(function)` — find all callers of a function
- `get_callees(function)` — find all functions called by a function
- `get_file_structure(path)` — get class/method/function outline
- `get_dependencies(file)` — get imports/references to other files

---

## Commands

### Modified: `/cognito-pr-review:review-pr`
Updated orchestration to use the hierarchical planner pipeline. Arguments unchanged.

### Modified: `/cognito-pr-review:learn-from-pr`
Enhanced with calibration comparison (TP/FP/FN via hybrid matching), EMA weight updates, no source field recording.

### Modified: `/cognito-pr-review:rebuild-agents`
Updated to handle new agent types (planner/journey, triage, investigation template, sweep) and skip source fields.

### New: `/cognito-pr-review:calibrate`
One-time bulk calibration command. Pulls ADO comments for all historical PRs, uses hybrid matching against plugin findings, generates initial `weights.yaml` via EMA.

### New: `/cognito-pr-review:weights`
View and manually adjust the weight system. Shows current weights with calibration stats (data points, last signal).

---

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown with concrete deliverables, file paths, testing strategies, and integration notes.

---

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Journey file created on initial review | Run review-pr on a new PR | `PR-{id}-journey.md` exists with overview, objectives, file map, review guide | `.claude.local/reviews/` |
| Planner validates triage output | Any review | Planner logs show triage cross-check; overrides logged if any | Agent output |
| Re-review auto-detected | Run review-pr on previously-reviewed PR | Journey file updated with new iteration section, manifest.isReReview = true | Journey file, manifest.json |
| Triage classifies files into tiers | Any review | Triage JSON output has critical/important/skim groups with rationale | Agent output |
| Investigation agents explore codebase | Critical area identified | Agent reads files outside PR cache to validate alternatives | Agent tool call log |
| Investigation agents use Solver-Verifier | Any investigation | Findings include explicit evidence citations from code reads | Finding JSON output |
| Sweep agent escalates finding | Security/critical pattern in skim-tier file | Planner receives escalation, optionally spawns ad-hoc investigator | Planner log |
| Sweep agent applies elevated thresholds for skim | Skim-tier borderline finding | Finding suppressed that would have surfaced in v1 | Synthesized review |
| EMA weights converge | After 10-15 learn-from-PR runs | Weights stabilize to reflect actual review patterns | weights.yaml |
| Calibration produces weights | Run calibrate command | `weights.yaml` with per-rule weights, data_points, category multipliers | Plugin knowledge dir |
| Hybrid matching works | Run learn-from-pr | Haiku judge correctly matches semantically equivalent findings + comments | Calibration output |
| Names removed from rules | After name scrub | No personal names in any YAML file or agent prompt | Grep across plugin dir |
| Large file gets context distillation | PR includes build.js changes | `structural-context/build.js.md` in cache with extracted functions | Cache directory |
| Finding lifespan tracked | Re-review of a PR with prior findings | Findings annotated with iteration count | Review artifact |

---

## Resolved Design Decisions

1. **Token budget:** No cap on investigation agent codebase reads. Trust the agent to be appropriately thorough.
2. **Journey file size:** Unlimited, no compression. PRs rarely exceed 3-4 iterations in practice.
3. **Investigation agent count:** No cap. Cost scales with PR complexity.
4. **Planner model:** Hierarchical planner (research-informed). Journey Agent elevated to orchestrator role that validates triage before dispatching.
5. **Investigation agent style:** Generalist per critical area with specialist escalation capability (hybrid approach).
6. **Weight algorithm:** EMA with α = 0.25, converges in ~10-15 data points.
7. **Calibration matching:** Hybrid — file:line proximity filter + Haiku semantic judge.
8. **Finding persistence:** Track lifespan across re-review iterations but do not auto-suppress. Annotate only.
9. **Sweep escalation:** Sweep agent can promote findings; Planner evaluates and optionally spawns ad-hoc investigators.
10. **Anti-sycophancy:** Solver-Verifier protocol baked into investigation agent prompts.
11. **Large file strategy:** Skill-based context for known files + Haiku context distillation for unknown large files.
12. **Tree-Sitter MCP:** In scope but deferred to end of implementation.
13. **Shadow deployment:** Not needed for single-user tool. Just switch to v2.
14. **Weight decay:** Manual only in v2. EMA naturally trends noisy rules toward 0.
15. **Name scrubbing:** Remove source field entirely from all rules. No attribution going forward.

---

## Research References

See [RESEARCH.md](./RESEARCH.md) for the full Gemini Deep Research report.

Key findings that shaped v2 decisions:
- **Hierarchical Planner pattern** (CodeRabbit, OpenHands) — prevents cascading triage failures [ref 2, 6, 7]
- **Solver-Verifier protocol** — LLMs are measurably better at verifying than generating; self-verification reduces hallucination [ref 37]
- **EMA over simple running average** — converges faster, adapts to shifting standards [ref 11, 12]
- **Context distillation** — Haiku distiller for large files saves significant Opus token budget [ref 6]
- **Hybrid calibration matching** — proximity filter + LLM-as-judge for semantic equivalence [ref 27, 28]
- **Specialist outperforms generalist** for complex reasoning, informing the escalation mechanism [ref 7, 15]
- **Anti-sycophancy prompts** — CONSENSAGENT demonstrates that demanding evidentiary proof reduces false consensus [ref 5]
- **Tree-Sitter MCP** — 10x token reduction for structural codebase queries [ref 8]
- **Debugging Decay Index** — informs finding lifespan tracking to prevent feedback rot [ref 33]
