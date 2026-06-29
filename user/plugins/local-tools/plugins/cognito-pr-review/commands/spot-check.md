---
description: "Fast, lightweight spot-check review of a small or narrowly-scoped PR — inline-first, ≤1 investigation agent, standalone (no ADO/calibration/sentinels)."
argument-hint: "[PR_ID | local] [scope: last-commit|since-review|<sha>..<sha>|<glob>|<free-text>]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Agent"]
---

# Cognito Forms Spot-Check Review

A deliberately lightweight sibling of `/cognito-pr-review:review-pr`. It reuses the
deterministic prep step (so PR data, diffs, timeline, and the cog-docs item dir resolve
exactly as in the full pipeline), then replaces the multi-agent fan-out with an
**inline-first review**: you read the (optionally scoped) diff and review it directly with
senior-Cognito-reviewer judgment, escalating to **at most one** `investigation` agent only
when a change is genuinely risky. It still produces a committable review artifact in the
same format as a full review — it just casts a narrower net.

Use it for the common case: a small PR (<5 files) that almost always comes back clean, or a
narrow slice of a larger PR (the latest commit, the author's latest attempt at your
feedback, a commit range, specific files, or a natural-language description).

**Arguments:** "$ARGUMENTS"

## Architecture Overview

```
spot-check [PR|local] [scope]
   │
   ├─ Step 1  prep-pr.ts            (REUSED as-is: cache, diffs, timeline, cog-docs item dir)
   │
   ├─ Step 2  Resolve scope         (inline: token/free-text → target file+hunk set)
   │
   ├─ Step 3  Inline review         (read scoped cached diffs; senior-reviewer judgment;
   │                                 NO sweep / triage / journey / reuse / intra-file agents)
   │
   ├─ Step 4  Conditional escalate  (dispatch ONE investigation agent ONLY for a risky change)
   │
   ├─ Step 5  Inline synthesis      (write the artifact in synthesizer-v2 FORMAT; no synth agent)
   │
   └─ Step 6  Write + report        (PR-{id}-spot-{datetime}.md; print summary)
```

Contrast with `review-pr.md`: spot-check keeps **Step 1 (prep)** and a **conditional**
version of investigation, and drops the journey/triage/planner-validate steps, the sweep
+ reuse + intra-file passes, the aggregate/post-process steps, the synthesizer-v2 *agent*
(its format is reused inline), and the stage-sentinel + calibration-marker steps.

## Standalone Guarantees (Non-Goals)

This command is intentionally self-contained. It NEVER does any of the following:

- **No Azure DevOps interaction** — it never invokes the ADO MCP server or the `az` CLI at
  any point. (`prep-pr.ts` only parses `AB#NNNNN` from the PR title/branch as plain strings;
  that is preserved, and no board read/write occurs.)
- **No calibration loop** — it does not read or write `weights.yaml`, does not write
  `pending-calibration.json`, and does not run any disposition-calibration step.
- **No stage sentinels** — it does not write `REVIEWED.md`, so it never flips a PR's derived
  stage to `reviewed`.
- **No journey file, triage, sweep, reuse-candidacy, or intra-file passes.**
- **No hard size guard** — it warns about nothing and never refuses; you choose the scope.

## Argument Parsing

Determine mode and scope from `$ARGUMENTS`:

- **PR mode:** the first numeric token is the PR ID (e.g. `17890`).
- **Local mode:** no numeric PR ID, or the `local` keyword — reviews uncommitted changes via
  `prep-pr.ts --local`. Supports `--base <branch>` (default `main`) and `--include-untracked`,
  identical to `review-pr`.
- **scope:** zero or more scope tokens and/or a free-text phrase (see Step 2). Tokens and
  free-text may combine — e.g. `17890 last-commit "the retry logic"`. Default scope = the
  whole PR/local diff.

### Step 1: Run Prep (reused)

Run prep **exactly as `commands/review-pr.md` Step 1 does** — that command is the source of
truth for the invocation; do not duplicate its body here.

**PR Mode:**

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts {pr_id}
```

**Local Mode:**

```bash
npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts --local [--base <branch>] [--include-untracked]
```

The script populates the cache (manifest, per-file diffs, `pr-timeline.json`,
`pr-context.json`) and resolves/creates the cog-docs item dir. From its output, read:

- **`cacheDir`** — from the **manifest JSON the script prints to stdout**. In PR mode the cache
  lives at `<cogDocsItemDir>/.pr-review/pr-cache/{pr_id}/`; in local mode at
  `.claude/pr-cache/local/`.
- **`cogDocsItemDir`** — from the `Cog-docs item dir: <path>` line the script prints to
  **stderr**.

**If the script fails**, stop and report the error (PR mode: not logged in, PR doesn't exist,
network error; local mode: not a git repo, base branch missing).

**Explicitly SKIP the cache-boundary marker** (`review-pr.md` Step 1.5 / the
`.claude/pr-cache/pr-review-active.json` lock). It is unnecessary here: the inline review and
the optional `investigation` agent both need normal codebase read access, and there is no
cache-only `sweep` agent in this pipeline whose reads need to be fenced to the cache. Do not
create that marker.

### Step 2: Resolve Scope (inline)

Start from the manifest's full file list and narrow to the target set per the scope grammar:

| Token | Meaning | How to resolve |
|-------|---------|----------------|
| *(none — default)* | The whole PR / local diff. | All manifest files. |
| `last-commit` / `latest` | Only the files/hunks in the most recent commit. | PR: `gh api repos/cognitoforms/cognito/pulls/{id}/commits` (last entry) or `gh pr diff`; local: `git show` / `git diff HEAD~1`. |
| `since-review` | Changes since your most recent review on this PR — the author's latest attempt to address your feedback. | Read `pr-timeline.json` from the cache, find the reviewer's most recent review timestamp, and select commits/files pushed after it. |
| `<sha>..<sha>` | A commit range. | The diff for that range. |
| `<path>` / glob (e.g. `*.cs`, `Cognito.Core/**`) | Restrict to matching files. | Filter the manifest by path. |

Any remaining argument text is **free-text scope** — a natural-language description ("just the
validation changes", "the new queue message class"). Interpret it against the manifest + diffs,
select the relevant files/hunks, and **state which files you chose**.

**`since-review` fallback:** if no prior review by the reviewer is found in `pr-timeline.json`
(ambiguous), fall back to `last-commit` scope and **state the fallback in the artifact header**.

Record a human-readable **resolved-scope** string (e.g. "latest commit (3 files)",
"since reviewer's review on 2026-06-20", "files under `Cognito.Core/**`") for the artifact
header and the completion summary.

### Step 3: Inline Review

Read the scoped cached diffs and review them directly with senior-Cognito-reviewer judgment:
correctness, obvious DI / storage / async pattern issues, and test gaps on changed behavior.
Apply focused judgment rather than the 95-rule sweep — the goal is "investigate the changes
that matter," not "cast a wide net." Do **not** dispatch sweep / triage / journey / reuse /
intra-file agents. Most small PRs produce no findings here.

### Step 4: Conditional Escalation (≤ 1 investigation agent)

If you encounter a change you cannot confidently resolve inline — a subtle correctness risk,
a non-obvious blast radius, or a pattern that needs codebase verification — dispatch
**exactly one** `investigation` agent scoped to that area:

```
Agent:
  subagent_type: cognito-pr-review:investigation
  prompt: |
    ## Your Assignment
    Investigation Focus: {the specific risk you could not resolve inline}

    ## Files to Review
    {relevant cached file paths + diffs}

    Cache directory: {cacheDir}
```

Fold the agent's evidence-based findings into synthesis. **Dispatch at most one** investigation
agent for the entire run — if a clean small PR warrants none, dispatch nothing (the common case).

### Step 5: Inline Synthesis (synthesizer-v2 format)

Compose the review yourself, following the `agents/synthesizer-v2.md` **output format** — do NOT
dispatch the synthesizer agent. Produce the sections below, in order, applying synthesizer-v2's
omission rules. Add a short header line near the top marking this a **spot-check** and stating
the **reviewed scope** (from Step 2).

```markdown
# Cognito PR Review — PR #{id}: {title}
<!-- local mode: "# Cognito PR Review — local: {branch}" -->

> **Spot-check review** — reviewed scope: {resolved-scope string from Step 2}

**Author:** {author}
**Branch:** {source} → {target}
**Date:** {date}
**Review type:** {Initial | Re-review (iteration {n})}

---

## Summary
{2-3 paragraph narrative: what the change does, overall assessment, key concerns if any.}

## Requirements Coverage
| # | Objective | Status | Evidence |
|---|-----------|--------|----------|
| 1 | {objective} | Covered / Partial / Gap | {files reviewed; whether findings block it; test presence} |

## Critical Findings
{Inline + investigation findings. Each gets its own subsection. Omit the whole section if none.}

### {Finding title}
**File:** {path}:{line}
**Severity:** {blocking | important | nit}
**Evidence:** {specific code snippet / reference}
**Suggestion:** {specific, grounded recommendation}

## Strengths
- {what's well-done — every PR has something positive}
```

Section rules (from synthesizer-v2):

- **Never omit** `## Summary`, `## Requirements Coverage`, or `## Strengths`.
- Omit `## Critical Findings` if there are no findings.
- **Always omit** `## Rule-Based Findings` (spot-check runs no sweep), `## Reuse & Duplication`
  (not run), and `## Intra-File Consistency` (not run).
- Include `## Re-Review Status` **only** when the scope implies a re-review (e.g. `since-review`),
  with comments resolved / unresolved threads / new changes since last review.
- Severity tiers: `blocking` / `important` / `nit`.

### Step 6: Write + Report

Write the artifact with a date-**and-time** stamp so repeat spot-checks never clobber each other
or the authoritative full-review `PR-{id}.md`:

```bash
STAMP=$(date +%Y-%m-%d-%H%M)
```

- **PR mode:** `<cogDocsItemDir>/PR-{id}-spot-{YYYY-MM-DD-HHMM}.md`
- **Local mode:** `.claude.local/reviews/LOCAL-{branch}-spot-{YYYY-MM-DD-HHMM}.md`
  (create `.claude.local/reviews/` if it does not exist).

Then print a chat completion summary:

- artifact path
- the resolved scope that was reviewed
- file count reviewed and finding count (by severity)
- whether an `investigation` agent was escalated (and on what)

Do **not** write `REVIEWED.md` or `pending-calibration.json`; do **not** run calibration or
touch `weights.yaml`. The review artifact is the only durable output.

## Examples

```
/cognito-pr-review:spot-check 17890                          # whole small PR, fresh-eyes spot check
/cognito-pr-review:spot-check 17890 since-review             # only the author's latest attempt at my feedback
/cognito-pr-review:spot-check 17890 last-commit              # only the most recent commit
/cognito-pr-review:spot-check 17890 "the validation changes" # natural-language slice of a larger PR
/cognito-pr-review:spot-check 17890 Cognito.Core/**          # only files under Cognito.Core
/cognito-pr-review:spot-check                                # local uncommitted changes
/cognito-pr-review:spot-check local last-commit              # local, just the last commit
```
