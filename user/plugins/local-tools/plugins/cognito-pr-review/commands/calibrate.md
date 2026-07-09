---
description: "One-time bulk calibration of rule weights against historical PR reviews"
argument-hint: "[--dry-run] [--pr PR_ID]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Agent"]
---

# Calibrate Rule Weights

One-time bulk calibration that analyzes historical PR reviews against actual human feedback to establish baseline EMA weights.

**Arguments:** "$ARGUMENTS"

**Plugin root:** `~/.claude/plugins/local-tools/plugins/cognito-pr-review`

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Enumerate Review Artifacts                             │
│  - Scan cog-docs/docs/{bugs,features}/*/PR-*.md for reviews     │
│  - Extract PR IDs from filenames                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Pull GitHub PR Comments (per PR)                       │
│  - Run get-pr-comments.ps1 for each PR ID                       │
│  - Filter to substantive reviewer comments                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Parse Plugin Review Artifacts                          │
│  - Extract findings: file, line, rule ID, severity, text        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Hybrid Matching (per PR)                               │
│  - Proximity filter: same file + line within ~20 lines          │
│  - Haiku semantic judge: match / partial / no_match             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: Classify Findings                                      │
│  - TP: plugin found it AND human confirmed it                   │
│  - FP: plugin found it, no human confirmation                   │
│  - FN: human commented, plugin missed it                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: Apply EMA Updates via disposition-calibration.ts       │
│  - Serialize TP/FP per PR → calibration-session.json            │
│  - Shell the helper (single EMA implementation)                 │
│  - Skipped if --dry-run                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 7: Write Calibration Report                               │
│  - Per-rule TP/FP/FN table, per-category aggregates             │
│  - False negative patterns for new rule candidates              │
└─────────────────────────────────────────────────────────────────┘
```

## Argument Parsing

Before starting, parse `$ARGUMENTS`:

- If `--dry-run` is present → `DRY_RUN=true` (report only, do not write weights.yaml)
- If `--pr {PR_ID}` is present → `SINGLE_PR={PR_ID}` (calibrate one PR only)
- Otherwise → calibrate all available review artifacts

## Workflow

### Step 1: Enumerate Review Artifacts

Scan the cog-docs item dirs for historical plugin review artifacts (one `PR-{id}.md` per item dir):

```bash
ls "C:\Users\JacobMadsen\source\repos\cog-docs\docs\bugs\*\PR-*.md" "C:\Users\JacobMadsen\source\repos\cog-docs\docs\features\*\PR-*.md"
```

Extract PR IDs from filenames (pattern: `PR-{id}.md`; skip `PR-{id}-journey.md`).

If `--pr PR_ID` was specified, restrict to that single PR ID. Verify it has a corresponding review artifact; abort with a clear error if not.

Report: "Found {N} review artifact(s) to calibrate against: PR-{id1}, PR-{id2}, ..."

### Step 2: For Each PR, Pull GitHub PR Comments

For each PR ID in the list, run the export script:

```powershell
cd "C:\Users\JacobMadsen\source\repos\Cognito Forms"
.\get-pr-comments.ps1 {PR_ID}
```

Comments land in `.claude.local/slop/pr-comments/` (relative to the Cognito Forms repo root). The filename pattern is typically `pr-{id}-comments.json` or similar — check what the script produces and read accordingly.

Filter to substantive reviewer comments. Skip:
- Vote-only comments ("voted 10", "voted -5", "approved", etc.)
- Policy update comments
- System/GitHub auto-generated comments
- Already-resolved discussions with no clear feedback
- Bot or automated-pipeline comments

For each surviving comment, capture:
- Thread ID / comment ID
- File path (if inline comment)
- Line number (if inline comment)
- Comment text

### Step 3: Parse Plugin Review Artifact

Read each `PR-{id}.md` review file and extract all findings. For each finding, record:

- **file**: file path referenced (e.g., `Cognito/Services/PersonService.cs`)
- **line**: line number referenced (if present; otherwise `null`)
- **rule_id**: rule ID string if the finding cites a rule (e.g., `no-storagecontext-query`); otherwise `null`
- **severity**: `critical` / `important` / `minor` / `nit`
- **text**: the finding description (first sentence or summary line)

If a finding spans a range of lines, use the start line.

### Step 4: Hybrid Matching (per PR)

For each (plugin finding, human comment) pair within the same PR:

#### Step 4a — Proximity Filter

A pair passes the proximity filter if BOTH conditions are true:
1. The comment references the same file path as the finding (normalized: strip leading `/`, match case-insensitively)
2. The line numbers are within 20 lines of each other (or either is `null`, in which case proximity cannot be confirmed — skip the pair)

Pairs that don't pass the proximity filter are not sent to the semantic judge (saves tokens).

#### Step 4b — Semantic Judge

For each proximity-matched pair, spawn a Haiku sub-agent to evaluate semantic equivalence:

```
Agent({
  model: "claude-haiku-...",   # use the available Haiku model
  prompt: |
    You are comparing two code review comments about the same file and nearby lines.
    Determine whether they refer to the same issue.

    Plugin finding (automated review):
    File: {file}
    Line: {line}
    Severity: {severity}
    Text: {finding_text}

    Human reviewer comment:
    File: {file}
    Line: {comment_line}
    Text: {comment_text}

    Reply with ONLY one of these words:
    - match      (they clearly refer to the same issue)
    - partial    (they are related but not identical — same area, overlapping concern)
    - no_match   (they refer to different issues)
})
```

Collect the judge verdict for each pair. A finding is considered "confirmed" if any of its proximity-matched pairs returns `match` or `partial`.

### Step 5: Classify Findings

For each plugin finding across all calibrated PRs:

- **True Positive (TP):** Plugin raised a finding AND at least one human comment semantically matched it (`match` or `partial` from Haiku judge)
- **False Positive (FP):** Plugin raised a finding but NO human comment matched it (either no proximity candidates, or all judged `no_match`)
- **False Negative (FN):** A human comment exists with NO corresponding plugin finding that matched it

Track FN patterns: for each unmatched human comment, record the file, comment text, and a short description of the issue type. These are candidates for new rules.

Group all TP/FP/FN results by rule ID (for rule-based findings) and by category (for aggregate reporting).

### Step 6: Apply EMA Updates via the Calibration Helper

**Do NOT hand-compute EMA math here.** `scripts/disposition-calibration.ts` is the single calibration implementation — this step serializes the Step 5 classifications and shells the helper, once per PR (the helper performs per-PR aggregation internally: one bounded EMA step per (lane|rule) per run).

For each calibrated PR:

1. **Locate the PR's cache dir** (`<cogDocsItemDir>/.pr-review/pr-cache/{id}/`). The helper joins dispositions against `{cacheDir}/processed-findings.json`; if the cache or that file no longer exists (old review, cache cleaned), **skip this PR's weight update** and note it in the report — classifications without the findings join cannot be calibrated.

2. **Serialize the PR's TP/FP classifications** into `{cacheDir}/calibration-session.json` (same session shape `buddy-session.json` uses):
   - TP finding → disposition with its original kept severity (signal 1)
   - FP finding → disposition with `"severity": "dismiss"` (signal 0)
   - `finding_ref`: `<basename>:<line>` (line-less: `<basename>#<slug>`)

3. **Shell the helper:**
   ```bash
   npx tsx {plugin_root}/scripts/disposition-calibration.ts \
     --session {cacheDir}/calibration-session.json \
     --findings {cacheDir}/processed-findings.json \
     --weights ~/.claude/state/cognito-pr-review/weights.yaml
   ```
   The helper owns the EMA math (per-PR aggregation, floor/ceiling clamp, α annealing — constants in `scripts/weight-constants.ts`), updates `rule_weights` and `source_weights`, and does the comment-preserving surgical write. The `--weights` target is the mutable state file (seeded from `knowledge/weights.yaml` on first use; the knowledge copy is shipped defaults and is never written).

4. **Collect the helper's printed deltas** for the report.

After all PRs, update the state file's top-level metadata:
- `calibration_prs`: append the PR IDs processed in this run (deduplicate against any already listed)
- `last_bulk_calibration`: today's date

**If `--dry-run`:** Do NOT invoke the helper and do NOT write anything. Report the Step 5 classifications (per-rule TP/FP counts and derived signals) only — computed new weights are not simulated, since the EMA math lives solely in the helper.

### Step 7: Write Calibration Report

Write the report to:
```
~/.claude/plugins/local-tools/plugins/cognito-pr-review/docs/specs/cognito-pr-review-v2/calibration-report.md
```

Create parent directories if they don't exist.

Report format:

```markdown
# Calibration Report

**Date:** {ISO date}
**Mode:** {Full bulk / Single PR (PR-{id}) / Dry run}
**PRs analyzed:** {count}
**Total plugin findings analyzed:** {count}
**Total human comments analyzed:** {count}

## Per-Rule Results

| Rule ID | TP | FP | FN | Old Weight | New Weight | Data Points |
|---------|----|----|-----|------------|------------|-------------|
| {rule}  | {n}| {n}| {n} | {0.0000}   | {0.0000}   | {n}         |

(Sorted by |new_weight − old_weight| descending — biggest movers first)

## Per-Category Aggregates

| Category | Total TP | Total FP | TP Rate | Suggested Multiplier |
|----------|----------|----------|---------|---------------------|
| {cat}    | {n}      | {n}      | {pct}%  | {multiplier}        |

Suggested multiplier = TP Rate / 0.80  (i.e., 1.0 = meets the 80% TP target)

## False Negative Patterns

Human reviewer comments that the plugin missed — candidates for new rules:

{For each unmatched human comment, one bullet:}
- **PR #{id} | {file}:{line}** — "{comment_text}" *(possible rule: {inferred category})*

## Rules With No Data

Rules present in weights.yaml but not encountered in any calibrated PR:
- {rule_id}: no findings in calibrated PRs — weight unchanged

## Dry Run Notice (if applicable)

This was a dry run. No changes were written to weights.yaml.
Computed weight changes are shown in the Per-Rule Results table above.
```

### Step 8: Report Summary to Stdout

After writing the report, print a concise summary:

```
Calibration complete.

PRs analyzed:          {N}
Plugin findings:       {total}
Human comments:        {total}

Weight changes:
  Increased (TP-heavy): {list of rule IDs with new_weight > old_weight}
  Decreased (FP-heavy): {list of rule IDs with new_weight < old_weight}
  Unchanged:            {count} rules

False negative patterns: {count} unmatched human comments
  → Review these in the calibration report as candidates for new rules

Report written to: ~/.claude/plugins/local-tools/plugins/cognito-pr-review/docs/specs/cognito-pr-review-v2/calibration-report.md
```

If `--dry-run`:
```
Dry run complete — no weights updated.
```

## Notes

- **ALL weight calibration** routes through the shared helper `scripts/disposition-calibration.ts` — the single EMA implementation (this command's Step 6, `learn-from-pr` §2.5.4/§2.5.7, and the buddy session close all shell it). Never duplicate the EMA logic in prose. The legacy bulk script `calibrate-weights.ts` is archived (`archived/`) — do not resurrect it; it destroyed YAML comments and used hardcoded paths.

- This command is designed for **one-time bulk calibration** after initial plugin deployment, or after accumulating a batch of reviewed PRs.
- For **ongoing incremental calibration**, use `/cognito-pr-review:learn-from-pr` after each reviewed PR. That command updates weights for a single PR immediately after human review.
- The Haiku semantic judge is essential — proximity filtering alone would produce too many false matches in large files with many comments on nearby lines.
- Rules without a `rule_id` in the plugin finding cannot be individually calibrated; the helper routes them through `source_weights` for their lane instead. Unmatched human comments contribute to FN counts only.
- Weights state file (calibration target): `~/.claude/state/cognito-pr-review/weights.yaml` — seeded from `{plugin_root}/knowledge/weights.yaml` (shipped defaults, never written)
- Review artifacts path: `cog-docs/docs/{bugs,features}/*/PR-*.md` (under `C:\Users\JacobMadsen\source\repos\cog-docs`)
- PR comments path: `.claude.local/slop/pr-comments/` (relative to `C:\Users\JacobMadsen\source\repos\Cognito Forms`)
- `get-pr-comments.ps1` lives at the Cognito Forms repo root; always `cd` into the repo before running it
