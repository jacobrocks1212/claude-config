---
description: "Cognito Forms PR review with team-specific patterns"
argument-hint: "[PR_ID] [aspects: all|csharp|frontend|api|consistency|testing] [sequential]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Agent"]
---

# Cognito Forms PR Review

Run a PR review using Cognito-specific patterns derived from senior reviewer feedback.

**Arguments:** "$ARGUMENTS"

## Architecture Overview

This command uses a size-routed hierarchical pipeline: deterministic prep → size router (small PRs take a downshifted, spot-check-shaped path that KEEPS sentinels + calibration) → planning → self-checked triage → parallel investigation/sweep/reuse-candidacy/intra-file-consistency (all agents self-write their outputs) → deterministic post-processing → synthesis.

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
│  Step 1.7: Size Router (deterministic)                           │
│  - manifest.substantive_count ≤ 5 → Downshifted Path (D1–D5):    │
│    inline review + ≤1 investigation + inline synthesis; KEEPS    │
│    REVIEWED.md + pending-calibration; resumes at Step 10         │
│  - otherwise → full pipeline below (--full / --spot override)    │
└──────────────────────────────────────────────────────────────────┘
                              ↓ (full pipeline)
┌──────────────────────────────────────────────────────────────────┐
│  Step 2: Journey/Planner Agent (Opus)                            │
│  - Produces persistent PR-{id}-journey.md                        │
│  - Compact form for small / ≤2-thread PRs                        │
│  - Re-review: appends new iteration section                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 3: Triage Agent (Opus) — with mandatory self-check         │
│  - Classifies files: critical / important / skim                 │
│  - Self-checks planner Rules 1–3; logs overrides                 │
│  - Re-review: emits reReviewScope (changed ∪ unresolved)         │
│  (Step 4 planner re-invoke removed — folded into Step 3)         │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 5: Investigation + Sweep (parallel)          ┐             │
│  - 1 Investigation Agent per critical group (Opus) │ concurrent  │
│  - 1 Sweep Agent for important+skim files (Sonnet) │             │
│  Step 5b: Reuse-Candidacy Stage (parallel)         │             │
│  - 1 Reuse Agent per cluster (Opus)                │             │
│    (≤6 clusters; ONE cluster if ≤4 substantive)    │             │
│  Step 5b: Intra-File Consistency Stage (parallel)  │             │
│  - 1 Intra-File Agent per cluster (Opus)           ┘             │
│    (≤6 clusters; ONE cluster if ≤4 substantive)                  │
│  All agents self-write {cacheDir}/agent-output/*.json            │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│  Step 6: Orchestrator Evaluates Sweep Escalations (inline)       │
│  - Judges escalation candidates itself — no planner dispatch     │
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
│  - scripts/post-process.ts (stdout → processed-findings.json)    │
│  - EMA weights, dedup, rank, filter, lifespan; --summary counts  │
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
│  - Write to <cogDocsItemDir>/ (cog-docs item dir)               │
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
- **--full**: Force the full pipeline regardless of PR size (overrides Step 1.7 routing)
- **--spot**: Force the downshifted path regardless of PR size (overrides Step 1.7 routing)
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

**Cache paths** (read the exact `cacheDir` from the manifest the script prints):
- PR Mode: `<cogDocsItemDir>/.pr-review/pr-cache/{pr_id}/` — under the resolved (or newly created) cog-docs item dir
- Local Mode: `.claude/pr-cache/local/` (always overwritten)

**Cache check (PR Mode only):** The script automatically checks if cache is current (same iteration and commit). Use `--force` to rebuild cache.

**If the script fails**, stop and report the error. Common issues:
- PR Mode: Not logged in (`gh auth login`), PR doesn't exist, network error
- Local Mode: Not in a git repository, base branch doesn't exist

**IMPORTANT:** Wait for the script to complete before proceeding.

### Step 1.5: Enable Cache Boundary Enforcement

Create the marker file that activates the `pr-review-cache-guard` PreToolUse hook (a read-warning guard). The hook only checks the marker's **presence** and already whitelists reads under `/cog-docs/` (where the cache now lives), so the marker stays a small transient lock in the work repo. `{cacheDir}` is the path printed in the Step 1 manifest — in PR mode that is `<cogDocsItemDir>/.pr-review/pr-cache/{pr_id}`.

**PR Mode:**
```bash
mkdir -p .claude/pr-cache
echo '{"cacheDir": "{cacheDir}", "prId": {pr_id}}' > .claude/pr-cache/pr-review-active.json
```

**Local Mode:**
```bash
mkdir -p .claude/pr-cache
echo '{"cacheDir": ".claude/pr-cache/local", "prId": 0, "local": true}' > .claude/pr-cache/pr-review-active.json
```

**IMPORTANT:** The marker file MUST be in the project directory (`.claude/pr-cache/`), NOT in `~/.claude/`. Writing to `~/.claude/` triggers Claude Code's "modify settings" permission prompt. This marker is the *only* plugin file written outside cog-docs — it is a transient process-lock (removed in Step 12.5), created independent of the resolved destination. All durable artifacts live in cog-docs.

### Step 1.6: Confirm cog-docs Destination (PR Mode only)

The prep script (Step 1) **guarantees** `cogDocsItemDir` is set. It resolves the cog-docs item dir for the PR's work item (materialized.json → `<id>-*` dir scan → WIP.md branch match), and if none matches it **creates** `docs/bugs/<id>-<slug>/` with a minimal SPEC.md (carrying a `**Branch:**` line so the branch-doc SessionStart hook resolves it later). If no cog-docs repo is present at all, prep hard-fails — there is **no** `.claude.local/reviews/` fallback.

Read `{cacheDir}/pr-context.json` and confirm `cogDocsItemDir` is present (it always will be in PR mode). All artifacts — cache, review, and journey — live under it. State which directory was chosen, and whether it was newly created (the prep log prints `Created cog-docs item dir: ...` when it creates one).

### Step 1.7: Size-Aware Route (deterministic, silent)

Read `substantive_count` from `{cacheDir}/manifest.json` — the prep script's count of files that are not pure test files, config files, or generated types (`SMALL_MAX = 5`). Route:

- `--full` in arguments → **full pipeline**, regardless of size.
- `--spot` in arguments → **downshifted path**, regardless of size.
- Otherwise: `substantive_count <= 5` → **downshifted path**; else → **full pipeline**.

**Announce the route up front, never prompt** — e.g. "3 substantive files → downshifted review (spot-check shape; sentinels + calibration kept)" or "7 substantive files → full pipeline". On re-reviews also announce the iteration scope (see Step 3).

**Downshifted route:** remove the Step 1.5 marker now (`rm -f .claude/pr-cache/pr-review-active.json`) — this path has no cache-only agent, and the inline review + optional investigation agent need normal codebase read access (the same rationale `spot-check.md` documents for skipping the marker). Then follow the **Downshifted Path (D1–D5)** below and resume at Step 10. Steps 2–9, 11, and 12.5 are skipped.

**Full route:** continue with Step 2. If the manifest predates `substantive_count` (older cache), re-run prep with `--force`; if that is not possible, take the full pipeline.

### Downshifted Path (D1–D5)

A review-pr-native spot-check shape: prep + inline review + at most one investigation agent + inline synthesis — but unlike `/spot-check` (which stays untouched and standalone), this path **keeps the learning loop**: REVIEWED.md (Step 12.6), the pending-calibration marker (Step 12.7), and a minimal `processed-findings.json` so buddy mode and `/learn-from-pr` operate uniformly on both routes.

**D1 — Scope.** The whole PR: all manifest files (there are ≤5 substantive ones). No journey, triage, sweep, reuse, or intra-file agents run on this path.

**D2 — Inline review.** Read the cached diffs (and cached files for surrounding context) and review directly with senior-Cognito-reviewer judgment: correctness, DI/storage/async pattern issues, and test gaps on changed behavior — the same inline-first discipline as `commands/spot-check.md` Step 3.

**D3 — Conditional escalation (≤1 investigation agent).** If a change cannot be confidently resolved inline — a subtle correctness risk, a non-obvious blast radius, or a pattern needing codebase verification — dispatch **exactly one** investigation agent scoped to that area (spot-check's Step-4 rule). Include in its prompt: `Write your output to: {cacheDir}/agent-output/investigation-downshift.json` (the agent self-writes; its reply is a one-line confirmation + counts). Most small PRs warrant none.

**D4 — Inline synthesis.** Compose the review yourself in the synthesizer-v2 format (same section and omission rules `spot-check.md` Step 5 documents), with two deviations: (a) add a `**Route:** downshifted ({N} substantive files)` line in the header block for auditability; (b) this IS the authoritative review — Step 10 writes it to `PR-{pr_id}.md`, not to a `-spot-` stamped file.

**D5 — Minimal processed-findings.json.** Write `{cacheDir}/processed-findings.json` in the standard schema:

```json
{
  "processed_findings": [
    {
      "file": "path/from/manifest.cs",
      "line": 42,
      "severity": "blocking | important | nit",
      "title": "...",
      "hypothesis": "...",
      "evidence": { "snippet": "...", "reference": "..." },
      "suggestion": "...",
      "confidence": "CONFIRMED | UNVERIFIED",
      "source": "investigation",
      "group": "downshift-inline",
      "effective_weight": 0.7
    }
  ],
  "dropped_count": 0,
  "dedup_count": 0,
  "lifespan_annotations": 0
}
```

- Findings from the D3 agent (if dispatched): copy from `agent-output/investigation-downshift.json`, keeping its `group`.
- Your own inline findings: `group: "downshift-inline"`.
- All downshifted findings carry `source: "investigation"` and `effective_weight: 0.7` — the `investigation` source key is deliberate (locked decision: disposition calibration and post-process treat downshifted findings identically to investigation findings; do NOT invent a new source key).
- Zero findings → `"processed_findings": []` (still write the file).

After writing the file, run the Step 8.5 sidecar emitter: `npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/emit-chunk-index.ts --cache-dir {cacheDir}` — with no journey on this route it emits a single synthetic whole-PR chunk, so buddy-mode consumption stays uniform across both routes. On failure: WARN and continue.

**Then resume at Step 10** (write review) → Step 12 (report — include the route) → Step 12.6 (REVIEWED.md) → Step 12.7 (pending-calibration.json) → Step 13. Skip Step 12.5 — the marker was already removed at Step 1.7.

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
    {If re-review: Previous journey file: <cogDocsItemDir>/PR-{pr_id}-journey.md}
    {If re-review: Iteration diff: {cacheDir}/iteration-diff.json}
    
    TASK: Create (or update on re-review) the journey file at <cogDocsItemDir>/PR-{pr_id}-journey.md
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
    Journey file: <cogDocsItemDir>/PR-{pr_id}-journey.md
    Manifest: {cacheDir}/manifest.json
    {If re-review: Iteration diff: {cacheDir}/iteration-diff.json}
    {If re-review: PR context with thread statuses: {cacheDir}/pr-context.json}
    
    TASK: Classify all files into critical/important/skim tiers.
    Run your Mandatory Self-Check Pass (Rules 1–3) and log overrides.
    Output triage JSON with critical, important, skim arrays plus
    overrides[] and selfCheckCompleted: true.
    Each tier entry: { group, files, rationale, investigationFocus, reReviewNote }
    {If re-review: Also emit reReviewScope (files / carriedForward).}
```

Capture the triage JSON output. The agent self-checks the former planner-validation rules (Rules 1–3) before emitting — verify the JSON carries `selfCheckCompleted: true` and an `overrides` array (empty is fine). If either is missing, re-invoke triage once with a reminder; do not proceed on an unchecked draft.

**Inline coverage check (former planner Rule 4):** count files per tier in the triage JSON. If the majority are `skim` but the PR description indicates significant behavioral or architectural change, do not auto-override — record a triage confidence warning and surface it in the Step 12 report.

**Re-review scoping:** on re-reviews the triage JSON carries `reReviewScope` — `files` (changed since last iteration ∪ unresolved threads) and `carriedForward` (unchanged and resolved). Steps 5 and 5b dispatch agents ONLY over `reReviewScope.files`; carried-forward files keep their prior findings via the `--previous-review` lifespan machinery (Steps 7–8). Announce the scope: "iteration {n} — re-reviewing {k} changed files (iteration diff); {m} unchanged files carried forward."

### Step 4: (Removed — folded into Step 3)

The separate planner-validation re-invoke is gone: triage self-checks Rules 1–3 itself (see its `overrides` log), and the Rule-4 coverage count is the orchestrator-inline check in Step 3. Use the triage JSON from Step 3 directly for all subsequent steps. (The step number is retained so existing cross-references — e.g. buddy's "Steps 1–8" delegation — stay stable.)

### Step 5: Dispatch Investigation + Sweep in Parallel

**Aspect filtering:** If the user specified aspects (e.g., `csharp`, `frontend`), filter which files go through the pipeline. Triage still classifies all files, but investigation/sweep agents only receive files matching the requested aspects.

**Re-review scoping:** on re-reviews, dispatch investigation agents only for critical groups containing at least one `reReviewScope.files` member (scope each agent's file list to the in-scope files), and give the sweep agent only in-scope important/skim files. Carried-forward files are not re-dispatched.

**For each critical group** from the triage JSON, launch an investigation agent (compute the group slug — the group name lowercased with spaces replaced by hyphens, e.g. "Core Service Changes" → "core-service-changes" — when building the prompt):

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

    ## Output
    Write your output to: {cacheDir}/agent-output/investigation-{group-slug}.json
```

**Launch sweep agent** on all important + skim files.

First compute the **applicable rule shards** from the manifest's file types among the sweep tier assignment (important + skim files) — the applicability mapping lives in `agents/sweep.md`'s shard manifest table:

- Any `.cs` file → `csharp-architecture.md`, `api-design.md`
- Any `.vue`/`.ts`/`.tsx` file → `frontend-vue.md`, `template-binding.md`
- Any `.cs`/`.vue`/`.ts`/`.tsx` file → `performance.md`
- Any test file (either stack) → `testing.md`
- Always → `code-consistency.md`, `security.md`

List each applicable shard once (both-stack categories load once). The shards were copied into `{cacheDir}/rules/` by the prep script.

```
Agent:
  subagent_type: cognito-pr-review:sweep (or use agent prompt)
  prompt: |
    Review non-critical files for PR #{pr_id}: {title}
    
    Cache directory: {cacheDir}
    
    Triage tier assignments:
    Important: {list of important files with groups}
    Skim: {list of skim files with groups}
    
    Applicable rule shards (read ONLY these; weights from {cacheDir}/weights-snapshot.json):
    {list of applicable {cacheDir}/rules/<category>.md paths}
    
    Apply weight-aware thresholds:
    - Important tier: effective_weight >= 0.5
    - Skim tier: effective_weight >= 0.7

    ## Output
    Write your output to: {cacheDir}/agent-output/sweep.json
```

All investigation agents + sweep agent launch in parallel (or sequentially if `sequential` arg was provided).

**Each agent writes its own output file** (the same self-write contract the reuse/intrafile agents carry) and replies with a one-line confirmation + counts. Do NOT transcribe agent output into files yourself — after each agent completes, just confirm its file exists:
- Investigation agents: `{cacheDir}/agent-output/investigation-{group-slug}.json`
- Sweep agent: `{cacheDir}/agent-output/sweep.json`

If an agent's output file is missing after it completes, re-request that agent once; do not reconstruct its output from the transcript.

### Step 5b: Reuse-Candidacy Stage (parallel with Step 5)

This stage runs **concurrently with Step 5** — it does NOT add serial latency. Launch the reuse agents at the same time as the investigation and sweep agents above (or sequentially after them if `sequential` arg was provided).

**Cluster the files:**

From `manifest.baselines[]` (populated by the prep script), select net-new or substantially-modified substantive files: services, types, components, helpers. Exclude pure test files, config files, and generated types (the manifest's per-file `substantive` flag encodes this same exclusion list). On re-reviews, restrict eligibility to `reReviewScope.files`. Group them into at most 6 clusters by domain area or shared concern (e.g., "Workflow Services", "Frontend Components", "API Types"). Each cluster should contain 1–6 files. **Single-cluster floor:** if 4 or fewer substantive files are eligible for this pass, form exactly ONE cluster — cluster agents handle 1–6 files, and a tiny PR must not fan out multiple agents per stage.

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

**Intra-file consistency pass — also part of Step 5b, concurrent with the reuse pass above:**

**prep (`prep-pr.ts`) is NOT modified** for this pass — eligibility is derived entirely from manifest file status and path heuristics. The agent reads the `main` version of each file directly via its local-codebase access; the host file's `main` version is the implicit baseline.

**Cluster the files for intra-file analysis:**

Select all substantively-modified substantive files from the manifest: services, types, components, helpers — any triage tier. Exclude pure test files, config files, and generated types (the manifest's per-file `substantive` flag encodes this same exclusion list). Unlike the reuse pass, `manifest.baselines[]` is NOT required; any modified substantive file is eligible. On re-reviews, restrict eligibility to `reReviewScope.files`. Group them into at most 6 clusters by domain area or shared concern (1–6 files each). **Single-cluster floor:** if 4 or fewer substantive files are eligible for this pass, form exactly ONE cluster — same floor as the reuse pass.

If no substantive modified files are present, skip this pass.

**For each cluster**, launch one intra-file consistency agent:

```
Agent (for each cluster — up to 6):
  subagent_type: cognito-pr-review:cognito-intra-file-consistency
  prompt: |
    ## Your Assignment
    Cluster: {cluster name}
    Files in cluster: {list of file paths for this cluster's files}

    ## PR Context
    {Condensed from journey file overview + objectives}

    ## Cache
    Cache directory: {cacheDir}
    Manifest: {cacheDir}/manifest.json

    ## Task
    Perform intra-file consistency analysis on each file in this cluster.
    Compare the PR diff for each file against the current `main` version of that file.
    Identify inconsistencies in naming, style, error handling, patterns, or structure
    introduced by the PR changes that are inconsistent with the rest of the file.
    Write your output to: {cacheDir}/agent-output/intrafile-{cluster-slug}.json

    ## Access Model
    You have investigation-level access: you may read ANY file in the local
    codebase on `main` and use tree-sitter MCP tools (get_file_structure,
    find_symbol_usages, get_callers, get_callees, get_dependencies).
    You do NOT have sweep's cache-only restriction.
```

**After each intra-file agent completes**, confirm it wrote its output file:
- Intra-file agents: `{cacheDir}/agent-output/intrafile-{cluster-slug}.json`

The cluster slug is the cluster name lowercased with spaces replaced by hyphens — the same convention as the reuse pass. Step 7's aggregate script already discovers `intrafile-*.json` files from `{cacheDir}/agent-output/`, and Step 8's post-process routes their findings through the investigation lane with verdict→severity mapping (`refactor`/`reuse` → `important`, `inconsistent` → `nit`, `consistent`/`acceptable-new` → dropped).

### Step 6: Evaluate Sweep Escalations (orchestrator-inline)

If the sweep output contains escalations, judge each one yourself — no agent dispatch for the judgment:

- **Worthy of investigation-depth review** (a credible blocking / security / data-integrity concern that cannot be settled from the evidence already in hand) → spawn an ad-hoc investigation agent for it, with the same self-write contract: `Write your output to: {cacheDir}/agent-output/investigation-escalation-{slug}.json`.
- **Otherwise** → the finding already sits in sweep's output and flows through aggregation as-is; no action needed.

Be conservative — escalations rarely warrant a dedicated agent. If sweep returned no escalations, skip this step.

### Step 7: Aggregate Findings JSON

Run the aggregation script to combine all agent outputs into the unified CombinedFindings format expected by post-process.ts:

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/aggregate-findings.ts --cache-dir {cacheDir} --manifest {cacheDir}/manifest.json [--previous-review <cogDocsItemDir>/PR-{pr_id}.md]
```

The `--previous-review` flag is only included for re-reviews.

The script reads all `investigation-*.json` and `sweep.json` from `{cacheDir}/agent-output/`, validates their structure, and writes `{cacheDir}/combined-findings.json`.

### Step 8: Run Deterministic Post-Processing

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/post-process.ts --input {cacheDir}/combined-findings.json --manifest {cacheDir}/manifest.json --summary [--previous-review <cogDocsItemDir>/PR-{pr_id}.md] > {cacheDir}/processed-findings.json
```

The `--previous-review` flag is only included for re-reviews.

Stdout is shell-redirected straight to `{cacheDir}/processed-findings.json` — do NOT capture the findings JSON into your context or Write the file yourself. `--summary` prints the one line you need on stderr:

```
[post-process] summary: total=N blocking=B important=I nit=X dropped=D deduped=E lifespan=L scope_filtered=N lane_zeroed=[...]
```

Use those counts for the Step 12 report; open `processed-findings.json` only with targeted reads if a specific finding must be inspected. If `scope_filtered` is non-zero or `lane_zeroed` is non-empty, surface that in the Step 12 report — scope-filtered findings were dropped for pointing outside the PR's file set (path-normalization mismatches land here), and a zeroed lane means an entire finding source was filtered out.

### Step 8.5: Emit Chunk Index + Phase-0 Envelope (deterministic)

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/emit-chunk-index.ts --cache-dir {cacheDir}
```

Deterministically derives the buddy-mode lazy-loading sidecars from artifacts already on disk: `{cacheDir}/chunk-index.json` (journey `### Step N` chunks joined to processed findings), `{cacheDir}/findings-by-chunk/chunk-{k}.json` shards (every processed finding in exactly one shard; findings matching no chunk land in a trailing catch-all chunk), and `{cacheDir}/phase0-result.json` (the Phase-0 result envelope: pr_id, cacheDir, cogDocsItemDir, journey path, chunk count, per-source finding counts, chunk index path). The journey is discovered via `manifest.journeyFile`. Purely additive — the autonomous pipeline does not consume these files; `review-pr-buddy.md` loads chunks lazily from them. On failure: WARN and continue (non-buddy reviews are unaffected; a buddy Phase-0 delegate treats a Step 8.5 failure as a Phase-0 failure).

### Step 9: Launch Synthesizer Agent

```
Agent:
  subagent_type: cognito-pr-review:synthesizer-v2 (or use agents/synthesizer-v2.md)
  model: sonnet
  prompt: |
    Synthesize the final review for PR #{pr_id}: {title}
    
    Read these files:
    - Processed findings: {cacheDir}/processed-findings.json
    - Journey file: <cogDocsItemDir>/PR-{pr_id}-journey.md
    - Triage classification: {triage JSON from Step 3, inline or file path}
    
    PR metadata:
    - Author: {author}
    - Branch: {source} → {target}
    - Date: {current date}
    - Review type: {Initial | Re-review (iteration {n})}
    
    Produce the final review markdown following your output format template.
```

### Step 10: Write Review

Read `{cacheDir}/pr-context.json` for the `cogDocsItemDir` field (always set in PR mode — see Step 1.6).

**PR Mode:**
Write both the review artifact and the journey file under the cog-docs item directory:
- `<cogDocsItemDir>/PR-{pr_id}.md` — the synthesized review
- `<cogDocsItemDir>/PR-{pr_id}-journey.md` — the persistent journey file (already created in Step 2 under this directory)

```bash
mkdir -p "<cogDocsItemDir>"
# Write PR-{pr_id}.md to <cogDocsItemDir>; the journey file is already there from Step 2.
```

**Local Mode:** Local mode has no work item, so it is not routed to cog-docs. Write to `.claude.local/reviews/LOCAL-{branch}-{timestamp}.md`.

```bash
mkdir -p ".claude.local/reviews"
# Write review content
```

### Step 11: Finalize Journey File

The journey file was already created in Step 2. No additional action needed.

### Step 12: Print Completion Output

Report to user:
- Route taken — `downshifted (N substantive files)` or `full pipeline` — and, on re-reviews, the iteration scope announcement
- Cache directory path
- Review artifact path
- Journey file path (full pipeline only)
- Summary stats (findings count by severity, dropped, deduped — from the Step 8 `--summary` stderr line; on the downshifted path, from your inline synthesis)
- Any triage confidence warning from the Step 3 inline coverage check

### Step 12.5: Cleanup Cache Boundary Marker

Remove the marker file to restore normal Read behavior:

```bash
rm -f .claude/pr-cache/pr-review-active.json
```

### Step 12.6: Emit REVIEWED.md Sentinel (PR Mode)

Read `{cacheDir}/pr-context.json` for the `cogDocsItemDir` field (always set in PR mode — see Step 1.6).

Write `<cogDocsItemDir>/REVIEWED.md` with YAML frontmatter carrying the PR identity, today's date, the **reviewed head SHA** (`reviewed_sha`), and the finding counts reported in Step 12 (total count plus per-tier counts — critical, important, minor — as produced by the synthesizer). Follow the frontmatter with a one-line human-readable body.

`reviewed_sha` is the head commit that was actually reviewed — the `pr.sourceCommit` field in the prep manifest (`{cacheDir}/manifest.json`, written by `prep-pr.ts`). Persisting it lets the NEXT re-review anchor its incremental diff on the real commit that was last reviewed, instead of using a journey review-round number as an index into the commit array (RC-2a). On a re-review this is what `detectReReview` reads back as the previous-review anchor.

Template (substitute live values; use ISO date `YYYY-MM-DD` for `date`, and the manifest `pr.sourceCommit` for `reviewed_sha`):

```bash
cat > "<cogDocsItemDir>/REVIEWED.md" << 'EOF'
---
kind: reviewed
pr: {pr_id}
date: "{YYYY-MM-DD}"
reviewed_sha: "{manifest.pr.sourceCommit}"
findings_total: {total_findings_count}
critical: {critical_count}
important: {important_count}
minor: {minor_count}
---
# Reviewed
EOF
```

This makes `derive_stage` report stage `reviewed` for the cog-docs item (it detects `REVIEWED.md` presence).

**Local Mode:** no work item, so no `REVIEWED.md` — skip this step entirely.

**On write failure:** WARN the user (e.g. "Warning: could not write REVIEWED.md to <path> — <reason>") and continue. Never block or fail the review on this write; the review artifact from Step 10 is the primary deliverable.

**No ADO board write:** this step is a purely local stage signal. The ADO poller PAT is read-only; do not attempt any ADO board or work-item update here.

### Step 12.7: Write pending-calibration Marker (PR Mode)

Write `{cacheDir}/pending-calibration.json` so that a subsequent `/learn-from-pr` run can locate this completed review, consume the marker, and perform post-review calibration.

Template (substitute live values; use ISO date `YYYY-MM-DD` for `date`):

```bash
cat > "{cacheDir}/pending-calibration.json" << 'EOF'
{
  "pr": {pr_id},
  "cache_dir": "{cacheDir}",
  "date": "{YYYY-MM-DD}"
}
EOF
```

**Buddy-safe by construction:** `review-pr-buddy.md` delegates only Steps 1–8 of this file (its Phase 0) and then runs its own Phase 2 completion, which includes its own REVIEWED.md write and inline recalibration. Buddy execution therefore never reaches Step 12 in this file and this marker is never written on the buddy path. That asymmetry is intentional: buddy recalibrates inline at Phase 2; non-buddy defers recalibration via this marker for `/learn-from-pr` to consume later.

**PR Mode only:** no work item in Local Mode, so skip this step entirely — same as Step 12.6.

**On write failure:** WARN the user (e.g. "Warning: could not write pending-calibration.json to <path> — <reason>") and continue. Never block or fail the review on this marker write.

### Step 13: Cache Cleanup (Background)

Optionally clean up old caches (>7 days) — the PR cache now lives under the cog-docs item dir (gitignored), plus local-mode caches in the work repo:

```bash
find "<cogDocsItemDir>/.pr-review/pr-cache" -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \; 2>/dev/null
find .claude/pr-cache -maxdepth 1 -type d -mtime +7 -exec rm -rf {} \; 2>/dev/null
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
- Manifest v2 with structural context for large files, per-file `substantive` flags, and `substantive_count` (the Step 1.7 router input)
- Uses GitHub REST API for all data — no dependency on local git branch state
- Resolves/creates the cog-docs item dir and writes the cache to `<cogDocsItemDir>/.pr-review/pr-cache/{pr-number}/` (hard-fails if no cog-docs repo)

**journey-planner** (Opus):
- Creates persistent journey file at `<cogDocsItemDir>/PR-{id}-journey.md`
- Contains: overview, objectives, file change map, manual review guide, PR lifecycle
- Compact journey form when `substantive_count <= 5` or the PR has ≤2 behavioral threads
- Re-review: appends new iteration section to existing journey

**triage** (Opus):
- Classifies files into critical / important / skim tiers
- Mandatory self-check pass (former planner-validation Rules 1–3) with an `overrides` log
- Groups related files for investigation assignments
- Re-review: tier boost for changed + unresolved files; emits `reReviewScope`

**investigation** (Opus):
- Deep-dive critical areas with Solver-Verifier protocol
- One agent per critical group from triage
- Reads cached diffs + structural context for large files
- Self-writes `{cacheDir}/agent-output/investigation-{group-slug}.json`

**sweep** (Sonnet):
- Rule-based review of important + skim files
- Weight-aware thresholds (important >= 0.5, skim >= 0.7)
- Escalation pathway for findings that warrant deeper investigation
- Self-writes `{cacheDir}/agent-output/sweep.json`

**cognito-consistency-checker** (Opus) — reuse-candidacy stage:
- One agent per cluster of net-new / substantially-modified substantive files (≤6 clusters)
- Applies R1–R4 reuse-discovery protocol: extract capabilities, baseline-first check, capability-level discovery, duplicate-logic detection
- Inherits investigation access model: reads local codebase on `main` + tree-sitter MCP tools; NOT cache-only
- Writes `{cacheDir}/agent-output/reuse-{cluster-slug}.json`; aggregate-findings.ts picks up `reuse-*.json` automatically

**post-process.ts** (deterministic TypeScript):
- EMA weight application, deduplication, ranking, filtering
- Lifespan annotation for re-review tracking
- Deterministic — no LLM involved
- Stdout (the processed-findings JSON) is shell-redirected to `processed-findings.json`; `--summary` emits a one-line stderr count summary for the orchestrator

**emit-chunk-index.ts** (deterministic TypeScript): derives chunk-index.json + findings-by-chunk/ shards + phase0-result.json for buddy-mode lazy loading (Step 8.5; journey-less single-chunk fallback on the downshifted route).

**synthesizer-v2** (Sonnet):
- Narrative review synthesis from processed findings + journey
- Produces final review markdown

## Forward Compatibility Note

Investigation agent tool list is defined in the agent prompt (agents/investigation.md), not hardcoded here. Phase 9 Tree-Sitter tools can be added to the agent prompt without changing this orchestration command.

## Notes

- No more 6 parallel specialist agents — replaced by journey → triage → investigation+sweep → post-process → synthesize
- Size-aware routing: ≤5 substantive files auto-downshift to the spot-check shape while KEEPING sentinels + calibration (`--full`/`--spot` override); `/spot-check` remains the standalone, no-sentinel command
- Synthesizer is Sonnet (not Haiku)
- Post-processing is deterministic TypeScript (not LLM); its stdout is shell-redirected, never transited through orchestrator context
- Investigation/sweep/reuse/intrafile agents all self-write their `agent-output/*.json`
- Journey file is a persistent artifact for human consumption (compact form for small PRs)
- Triage self-check (the former planner-validation rules) prevents cascading misclassification without a third Opus dispatch
- Re-reviews scope fan-out to `reReviewScope.files` (iteration diff ∪ unresolved threads); carried-forward findings ride the lifespan machinery
- Escalation pathway from sweep to investigation (orchestrator-judged inline)
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
