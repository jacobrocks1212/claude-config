---
description: "Learn new review rules from a PR's senior reviewer feedback"
argument-hint: "<PR_ID or path to comments file>"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "AskUserQuestion", "Agent"]
---

# Learn from PR

Extract new review rules from a completed PR by analyzing senior reviewer feedback.

**Input:** "$ARGUMENTS"

**Plugin root:** `~/.claude/plugins/local-tools/plugins/cognito-pr-review`

## Rules Storage

Rules are stored as YAML files in `{plugin_root}/knowledge/rules/`:

| File | Category | Target Agent |
|------|----------|--------------|
| csharp-architecture.yaml | C# backend patterns | cognito-architecture |
| api-design.yaml | HTTP/REST API patterns | cognito-api-design |
| frontend-vue.yaml | Vue/TypeScript patterns | cognito-frontend |
| performance.yaml | Performance optimization | cognito-architecture |
| testing.yaml | Test patterns | cognito-test-coverage |
| code-consistency.yaml | General consistency | cognito-consistency-checker |
| security.yaml | Security patterns | cognito-architecture |
| template-binding.yaml | build.js/ExoWeb bindings | cognito-frontend |

Rules are embedded into agent prompts by `/cognito-pr-review:rebuild-agents`.

## Workflow

### 1. Load PR Comments

If `$ARGUMENTS` is a PR number, run the export script:
```powershell
cd "C:\Users\JacobMadsen\source\repos\Cognito Forms"
.\get-pr-comments.ps1 $ARGUMENTS
```

If `$ARGUMENTS` is a file path, read it directly.

Comments are in `.claude.local/slop/pr-comments/`.

### 2. Read and Filter Comments

Extract comments from senior reviewers. Skip:
- Vote-only comments ("voted 10", "voted -5")
- Policy update comments
- System/TFS comments
- Already-resolved discussions
- Design discussion threads with no clear generalizable pattern

### 2.5. Compare Findings vs. Actual Comments (EMA Calibration)

Before extracting new rules, compare the plugin's review findings against the actual reviewer comments to calibrate rule weights.

**Prerequisites:** This step requires that a plugin review artifact exists at `.claude.local/reviews/PR-{PR_ID}.md`. If no review artifact exists for this PR, skip to step 3.

#### 2.5.1 Load Review Artifact

Read the plugin's review artifact from `.claude.local/reviews/PR-{PR_ID}.md`. Parse the review to extract all findings with their:
- File path and line number
- Rule ID (for sweep/rule-based findings)
- Finding title (for investigation findings)
- Severity

#### 2.5.2 Hybrid Matching

For each plugin finding, apply hybrid matching against the GitHub reviewer comments:

**Step 1 — Proximity filter:** Find comments on the same file, within ~20 lines of the finding's line number. If no proximity match exists, the finding has no matching comment.

**Step 2 — Haiku semantic judge:** For each proximity-matched pair (finding + comment), spawn a Haiku agent to evaluate semantic equivalence:

```
Agent:
  model: haiku
  prompt: |
    Compare these two items and determine if they refer to the same issue:
    
    Plugin finding:
    - File: {file}:{line}
    - Title: {title}
    - Description: {description or hypothesis}
    
    Reviewer comment:
    - File: {comment_file}:{comment_line}
    - Text: {comment_text}
    
    Do they refer to the same underlying issue? Reply with JSON:
    { "match": true/false, "confidence": 0.0-1.0, "reasoning": "..." }
```

Consider it a match if `match: true` AND `confidence >= 0.7`.

#### 2.5.3 Classify Findings

Based on matching results, classify each plugin finding:

- **True Positive (TP):** Plugin finding has a semantically matched human comment → `signal = 1.0`
- **False Positive (FP):** Plugin finding has no matching human comment → `signal = 0.0`
- **False Negative (FN):** Human comment has no matching plugin finding → candidate for new rule (feed into step 3)

#### 2.5.4 Update Weights via EMA

For each TP or FP finding that has a `rule_id` (sweep findings):

1. Load `{plugin_root}/knowledge/weights.yaml`
2. Find the rule entry under `rule_weights`
3. Apply EMA update:
   ```
   new_weight = α × signal + (1 - α) × old_weight
   ```
   Where:
   - `α` = `ema_alpha` from weights.yaml (default 0.25)
   - `signal` = 1.0 for TP, 0.0 for FP
   - `old_weight` = current weight for the rule
4. Increment `data_points` by 1
5. Write the updated weights.yaml

Investigation findings (no rule_id) are not weight-calibrated — they don't have associated rules.

#### 2.5.5 Update Calibration Metadata

After updating weights:
1. Set `last_calibrated` to today's date (YYYY-MM-DD format)
2. Append the PR ID to `calibration_prs` list (if not already present)

#### 2.5.6 Print Calibration Summary

```
## Calibration Results for PR #{PR_ID}

- **True Positives:** {count} (findings matched by reviewer comments)
- **False Positives:** {count} (findings with no matching comment)
- **False Negatives:** {count} (reviewer comments with no matching finding)
- **Rules updated:** {count}
- **Weight changes:**
  - {rule_id}: {old_weight} → {new_weight} ({TP|FP})
  - ...
```

### 3. Analyze Each Comment

**Note:** False Negative comments identified in step 2.5 (reviewer comments with no matching plugin finding) are high-priority candidates for new rules. Prioritize analyzing these when proposing new rules.

For each substantive comment:

1. **Identify the pattern**: What specific issue is being flagged?
2. **Generalize**: Can this become a reusable rule? Skip one-off observations.
3. **Check for duplicates**: Read existing YAML rules in `{plugin_root}/knowledge/rules/` to avoid duplicates
4. **Determine category**: Which YAML file does this belong in? (see table above)

### 4. Propose New Rules via AskUserQuestion

Present ALL proposed rules in a single AskUserQuestion with multiSelect, showing:
- Source comment (quote only — no attribution)
- Generalized rule description
- Category (which YAML file)
- Proposed YAML snippet

Options per rule:
- Add rule
- Skip this rule

### 5. YAML Rule Format

Each rule follows this structure:
```yaml
- id: kebab-case-unique-id
  severity: critical | important | minor
  description: >
    Clear description of what to check for and why.
  trigger_patterns:        # Optional - patterns that suggest this rule applies
    - "pattern1"
    - "pattern2"
  anti_pattern: |          # Optional - code example to avoid
    // Bad code example
  correct_pattern: |       # Optional - preferred approach
    // Good code example
```

### 6. Update Rules Files

For each approved rule:
1. Read the appropriate YAML file from `{plugin_root}/knowledge/rules/`
2. Append the new rule under the `rules:` list
3. Maintain consistent indentation (2 spaces)

### 7. Suggest Agent Rebuild

After adding new rules:
```
New rules added! Run /cognito-pr-review:rebuild-agents to update agent prompts.
```

## Notes

- Rules are YAML, not markdown
- Each category has its own file — see the table above for category→agent mapping
- Use AskUserQuestion for approval workflow
- `/cognito-pr-review:rebuild-agents` reads the YAML files and embeds rules into agent markdown prompts
- Never record a `source:` field in rules — rules are anonymous patterns, not attributed to individuals
- After calibration, rules that were consistently FP will have lower weights, naturally reducing noise in future reviews
- FN patterns are presented alongside new rule proposals for user review
