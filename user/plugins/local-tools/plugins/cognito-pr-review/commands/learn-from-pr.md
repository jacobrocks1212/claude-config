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

| File | Category | Live Consumer(s) |
|------|----------|------------------|
| csharp-architecture.yaml | C# backend patterns | sweep |
| api-design.yaml | HTTP/REST API patterns | sweep |
| frontend-vue.yaml | Vue/TypeScript patterns | sweep |
| performance.yaml | Performance optimization | sweep |
| testing.yaml | Test patterns | sweep |
| code-consistency.yaml | General consistency | cognito-consistency-checker, cognito-intra-file-consistency, sweep |
| security.yaml | Security patterns | sweep |
| template-binding.yaml | build.js/ExoWeb bindings | sweep |

Rules are embedded into agent prompts by `/cognito-pr-review:rebuild-agents` (categories map 1:1 to the rule files — no intermediate agent-mapping layer).

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

**Prerequisites:** This step requires that a plugin review artifact exists at `<cog-docs>/docs/{bugs,features}/*/PR-{PR_ID}.md` (locate it by globbing the cog-docs item dirs for `PR-{PR_ID}.md`). If no review artifact exists for this PR, skip to step 3.

#### 2.5.1 Load Review Artifact

Read the plugin's review artifact (the `PR-{PR_ID}.md` found under the matching cog-docs item dir). Parse the review to extract all findings with their:
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

#### 2.5.4 Update Weights via the Calibration Helper

**Do NOT hand-compute EMA math here.** `scripts/disposition-calibration.ts` is the single calibration implementation — all weight updates route through it.

1. **Serialize the TP/FP classifications** into a session-shaped file at `{cacheDir}/calibration-session.json` (same schema the helper accepts from `buddy-session.json`):
   ```json
   {
     "pr_id": {PR_ID},
     "cache_dir": "{cacheDir}",
     "chunks": [
       {
         "index": 0,
         "dispositions": [
           { "finding_ref": "<basename>:<line>", "source": "<finding source>", "severity": "<original severity>" },
           { "finding_ref": "<basename>:<line>", "source": "<finding source>", "severity": "dismiss" }
         ]
       }
     ]
   }
   ```
   - **TP** finding → a disposition carrying its original kept severity (signal 1)
   - **FP** finding → a disposition with `"severity": "dismiss"` (signal 0)
   - `finding_ref` uses the standard convention: `<basename>:<line>` (line-less findings: `<basename>#<slug>`)
2. **Shell the helper:**
   ```bash
   npx tsx {plugin_root}/scripts/disposition-calibration.ts \
     --session {cacheDir}/calibration-session.json \
     --findings {cacheDir}/processed-findings.json \
     --weights ~/.claude/state/cognito-pr-review/weights.yaml
   ```
   The helper owns the EMA math (per-PR aggregation, floor/ceiling clamping, α annealing — constants in `scripts/weight-constants.ts`), updates `rule_weights` (sweep findings) and `source_weights` (non-sweep findings), and performs the comment-preserving surgical YAML write.
3. **Surface the printed delta summary** to the user.

The `--weights` target is the mutable state file `~/.claude/state/cognito-pr-review/weights.yaml` (seeded from the plugin's `knowledge/weights.yaml` on first use; the knowledge copy is shipped defaults and is never calibrated in place).

#### 2.5.5 Update Calibration Metadata

After the helper runs, in the state file (`~/.claude/state/cognito-pr-review/weights.yaml`):
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

#### 2.5.7 Buddy-Disposition Signal Source

The §2.5.2/§2.5.4 path above (Haiku semantic judge → GitHub-comment matching) is the **non-buddy** calibration signal. It remains intact and runs unconditionally when a review artifact exists. The buddy-disposition path described here is **additive and asymmetric**: per SPEC R2, buddy recalibrates inline at session close while non-buddy defers to this learn-from-pr step.

**If a persisted `buddy-session.json` exists in the PR's cache dir**, invoke the shared helper to calibrate from its dispositions:

```bash
npx tsx {plugin_root}/scripts/disposition-calibration.ts \
  --session {cacheDir}/buddy-session.json \
  --findings {cacheDir}/processed-findings.json \
  --weights ~/.claude/state/cognito-pr-review/weights.yaml
```

Surface the printed delta summary to the user.

**Gate the helper on the session file:** only invoke the disposition helper when `{cacheDir}/buddy-session.json` exists — non-buddy caches have none (their disposition signal is the human PR comments, calibrated via §2.5.1–2.5.6 above). If the helper is invoked without a session file anyway, it exits cleanly with a "nothing to calibrate" diagnostic rather than an ENOENT error.

**Consume + clear the `pending-calibration` marker:** if `{cacheDir}/pending-calibration.json` exists (written by `review-pr.md` Step 12.7 on non-buddy completion), read it to recover the cache dir and PR ID, then run the **§2.5.1–2.5.6 comment-matching calibration** for that PR — the marker payload (cache dir + PR ID) is exactly what §2.5 needs, and the semantics are *calibrate after human feedback*: the marker defers calibration until reviewer comments exist to match against. Do NOT point the marker at the disposition helper — a non-buddy cache has no `buddy-session.json` to feed it. After the §2.5 pass completes, delete the marker (`rm -f {cacheDir}/pending-calibration.json`) so it is consumed exactly once.

The helper (`scripts/disposition-calibration.ts`) is the **single calibration implementation** — reused by the buddy path (dispositions), the §2.5.4 comment-matching path (synthetic `calibration-session.json`), and `/cognito-pr-review:calibrate`. Do not re-implement the EMA math anywhere; all weight updates route through that helper.

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
