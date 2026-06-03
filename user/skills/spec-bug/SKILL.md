---
name: spec-bug
description: Investigate a complex bug or issue — gather evidence, verify symptoms, produce an investigation spec, then optionally transition to /fix
argument-hint: [bug description, area of concern, or work-item id]
---

# Spec Bug

Structured investigation workflow for bugs and issues that turn out more complex than expected. Gathers all available evidence via parallel subagents, confirms symptoms interactively with the user, and produces an investigation SPEC.md as the source of truth. Optionally transitions into `/fix` for implementation planning.

**When to use:**
- A bug or issue is more complex than initially expected
- You want to document what's known before attempting a fix
- You need to separate verified symptoms from theories
- Before starting work on a tricky issue (proactive investigation)

**User's description:**
$ARGUMENTS

---

## Step 1: Context Gathering (Parallel Subagents)

Launch parallel research subagents to collect all available evidence. Each subagent returns structured findings. Adapt the subagent set based on what's available — skip subagents whose data sources don't exist.

If the user's description is (or references) a work-item id, the work-item context subagent (F, below) fetches that item and its related items first, so the rest of the investigation is grounded in what was actually reported.

### Subagent A: Conversation & Session History

**Prompt:** Search for evidence of the issue in recent conversation and session history.

1. Check the current conversation for: error messages, failed commands, unexpected behavior, theories discussed, files mentioned
2. Search `~/.claude-personal/projects/` for recent `.jsonl` session files mentioning relevant keywords
3. Extract: what was attempted, what failed, what was observed, any theories or hypotheses already explored

Report format: chronological list of relevant findings with source attribution.

### Subagent B: Work Log & Recent Activity

**Prompt:** Check the interview-prep-plugin work log and recent git activity for context.

1. Call `interview_work_log_append` — no, read the work log: check `~/.interview-prep/work-log.jsonl` for recent entries related to this project
2. Run `git log --oneline -20` and `git diff --stat HEAD~5` to understand recent changes
3. Run `git diff` (unstaged) and `git diff --cached` (staged) to see current uncommitted work
4. Identify: what was recently changed, what skills were used, what files were modified

Report format: timeline of recent work with file lists and commit messages.

### Subagent C: Related Documentation

**Prompt:** Search for existing documentation related to this issue.

1. Read project `CLAUDE.md` for architecture context and known gotchas
2. Search `docs/bugs/` for related bug docs (open and archived)
3. Search `docs/features/` for feature specs that touch the affected area
4. Check subdirectory `CLAUDE.md` files near the affected code

Report format: list of related documents with relevance summary for each.

!`cat .claude/skill-config/spec-bug-runtime-evidence.md 2>/dev/null || cat ~/.claude/skills/_components/spec-bug-runtime-evidence.md`

### Subagent E: Source Code Analysis

**Prompt:** Read the source code in the affected area to understand the current implementation.

1. Based on the bug description, identify the likely affected files and code paths
2. Read the relevant source files end-to-end
3. Identify: control flow, state management, error handling, edge cases
4. Note any code that looks suspicious, fragile, or inconsistent with surrounding patterns

Report format: annotated code path summary with flagged areas of concern.

!`cat .claude/skill-config/spec-bug-work-item-context.md 2>/dev/null || cat ~/.claude/skills/_components/spec-bug-work-item-context.md`

---

## Step 2: Synthesize Findings

After all subagents return, synthesize their findings into three categories:

### 2a. Evidence Inventory

| Source | Key Finding | Confidence |
|--------|------------|------------|
| conversation | ... | high/medium/low |
| git log | ... | ... |
| session logs | ... | ... |
| source code | ... | ... |
| docs | ... | ... |

### 2b. Preliminary Theories

Based on the evidence, form 1-3 hypotheses about root cause. For each:
- **Theory:** one-sentence description
- **Supporting evidence:** what points to this theory
- **Contradicting evidence:** what argues against it
- **Verification method:** how to confirm or rule out

### 2c. Open Questions

List anything that can't be determined from the evidence alone — these become AskUserQuestion items in Step 3.

---

## Step 3: Verify Symptoms with User

Use **AskUserQuestion** to confirm the user's actual experience. This is critical — don't assume. Each confirmed answer becomes a **verified symptom** in the spec.

Ask about:
- **Observed behavior:** "When you [action], what exactly happens? Is it [description from evidence]?"
- **Expected behavior:** "What should happen instead?"
- **Reproduction:** "Is this consistent or intermittent? Any specific conditions?"
- **Scope:** "Does this affect [related area] too, or just [primary area]?"
- **Timeline:** "When did this start? After a specific change?"

Limit to 2-4 focused questions per round. Continue rounds until symptoms are clear.

Mark each confirmed item as `VERIFIED` in the spec. Mark unconfirmed items as `REPORTED` or `SUSPECTED`.

---

## Step 4: Determine Placement

Infer whether this belongs in `docs/features/` or `docs/bugs/` based on context:

**Signals for `docs/bugs/`:**
- A previously working behavior is now broken
- The issue is a regression
- There's no associated feature spec
- The user describes it as a bug, error, or broken behavior

**Signals for `docs/features/`:**
- The issue is within an in-progress feature (has an existing SPEC.md or PHASES.md)
- The "bug" is really a missing or incomplete implementation
- The user is investigating behavior for a planned feature

**If ambiguous**, use **AskUserQuestion:**
> "This issue touches [area]. Should I file this as a bug investigation (`docs/bugs/`) or as part of a feature spec (`docs/features/[group]/`)?"

### Directory creation

- **Bug:** `docs/bugs/{bug-dir}/SPEC.md` — name `{bug-dir}` per the repo's `docs/bugs/CLAUDE.md` naming convention (e.g. `<WI_ID>-<slug>` where bugs map to work items, or a descriptive `<slug>` otherwise). Read that file first; do not assume a fixed format.
- **Feature:** `docs/features/{group}/{feature-slug}/SPEC.md` — use existing feature directory if one exists, or create new

For bugs, also create the standard bug doc header fields alongside the investigation spec format.

---

## Step 5: Write the Investigation SPEC

Write the SPEC.md with this structure:

```markdown
# {Title} — Investigation Spec

> One-line summary of the issue.

**Status:** Investigating
**Severity:** {P0 | P1 | P2 | Low}
**Discovered:** {today's date}
**Placement:** {docs/bugs or docs/features path}
**Related:** {links to related specs, bugs, or phases}

---

## Verified Symptoms

<!-- Each symptom confirmed directly with the user via AskUserQuestion -->

1. **[VERIFIED]** {symptom description} — {how confirmed}
2. **[VERIFIED]** {symptom description} — {how confirmed}
3. **[REPORTED]** {unconfirmed symptom} — {source}

## Reproduction Steps

1. {step}
2. {step}
3. {observed result}

**Expected:** {what should happen}
**Actual:** {what does happen}
**Consistency:** {always | intermittent | conditions}

## Evidence Collected

### Source Code
{Annotated code path findings from Subagent E}

### Runtime Evidence
{Session log findings, error events, anomalies from Subagent D}

### Git History
{Recent changes, relevant commits from Subagent B}

### Related Documentation
{Existing specs, bug docs, CLAUDE.md entries from Subagent C}

## Theories

### Theory 1: {name}
- **Hypothesis:** {description}
- **Supporting evidence:** {list}
- **Contradicting evidence:** {list}
- **Status:** Unverified | Likely | Confirmed | Ruled Out

### Theory 2: {name}
...

## Proven Findings

<!-- Move theories here as they are confirmed or ruled out -->

{findings confirmed through investigation}

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| ... | ... | ... |

## Open Questions

- {question that needs further investigation}
```

If the spec becomes large (>200 lines), split supplementary evidence into a sibling `EVIDENCE.md` file and reference it from the main SPEC.

---

## Step 6: Transition to /fix

After writing the spec, present a summary to the user:

> **Investigation spec created at `{path}`.**
>
> **Verified symptoms:** {count}
> **Theories:** {count} ({confirmed count} confirmed)
> **Severity:** {severity}
>
> Ready to create a fix plan?

Use **AskUserQuestion:**
- **"Create fix plan now"** — Invoke the `fix` skill, passing the SPEC path and a synthesized bug description derived from the verified symptoms and strongest theory
- **"Not yet"** — Stop here. The spec is the deliverable.
- **"Need more investigation"** — Return to Step 3 for additional symptom verification or Step 1 to gather more evidence

When transitioning to `/fix`, pass the investigation spec path so `/fix` can read verified symptoms and proven findings instead of re-investigating from scratch.

---

## Step 7: Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`

**Extra fields for spec-bug:**

| Field | Value |
|-------|-------|
| `verified_symptoms` | Count of VERIFIED symptoms |
| `theories` | Count of theories formed |
| `theories_confirmed` | Count of theories confirmed |
| `placement` | `docs/bugs` or `docs/features/{group}` |
| `transitioned_to_fix` | boolean — whether the user proceeded to /fix |
