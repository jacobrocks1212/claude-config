---
description: Draft a TDD fix plan for a manually-reported bug using parallel Sonnet subagents
argument-hint: [bug description] [optional path/to/PHASES.md]
name: fix
---

# Fix

Draft a detailed fix plan (in plan mode) for a bug or issue discovered during manual testing — typically (but not always) after `/implement-phase`. The plan uses systematic debugging, TDD, and parallel Sonnet subagents, with all hard requirements encoded as explicit non-skippable steps in the plan itself.

This skill may be invoked standalone (no associated PHASES.md). Handle both cases.

---

## Step 1: Understand the Feedback

### 1a. Parse the Report

- Read `$ARGUMENTS` and any bug description the user provided in the conversation
- Identify: observed behavior, expected behavior, reproduction steps, affected area
- If ANY of these are unclear or missing, use **AskUserQuestion** to clarify before proceeding
- Do NOT guess at intent — a misunderstood bug produces a wrong fix

### 1b. Restate the Problem

Before investigating, restate the bug in your own words (one short paragraph) and confirm alignment if there's meaningful ambiguity. Skip confirmation only if the report is unambiguous.

---

## Step 2: Investigate Root Cause (Systematic Debugging)

Apply the **`systematic-debugging`** skill's methodology. Do NOT jump to fixes.

- Read the relevant code paths end-to-end — do not speculate about files you haven't read
- Form hypotheses, then verify each against the code / logs / tests
- Identify the **root cause**, not just the symptom
- Distinguish root cause from contributing factors
- If the root cause cannot be determined from code alone, **AskUserQuestion** for logs, repro steps, or screenshots

Produce a short "Root Cause" summary before drafting the plan.

### 2c. Categorize the Failure Mode

Classify **why** the original implementation produced this bug. Pick the best-fit category (or add a new one if none fit):

- **requirements-change** — Not really a bug; requirements shifted after implementation. No process failure.
- **inadequate-test-coverage** — Code was correct-looking but a missing/weak test let the bug through.
- **inadequate-research** — SPEC.md / PHASES.md / prior code was not read carefully enough; assumptions were wrong.
- **incorrect-spec** — SPEC.md itself was wrong or ambiguous; implementation matched spec but spec didn't match reality.
- **integration-gap** — Each piece worked in isolation; the bug lives at the seam between components/phases.
- **environment-platform** — Worked in dev/test but failed due to OS, timing, concurrency, or platform-specific behavior (e.g. Windows paths, async races).
- **regression** — A prior change silently broke working behavior; no test caught it.
- **ui-ux-polish** — Functionally correct but violates UX/interaction expectations.
- **tooling-config** — Build, lint, type-check, or dependency config caused or masked the issue.
- **other** — Explain briefly.

Record the chosen category (and a one-sentence justification) — it drives Step 6 and the persistent log (Step 6c).

---

## Step 3: Load Phase Context (If Applicable)

### 3a. Resolve PHASES.md (optional)

- If `$ARGUMENTS` references a PHASES.md path, use it
- Else if the current/recent session context clearly ties to a PHASES.md file, use that
- Else if the bug is standalone with no PHASES.md context, **skip this step entirely** and note "No PHASES.md — standalone fix"
- If ambiguous, use **AskUserQuestion**

### 3b. Read PHASES.md and SPEC.md (if resolved)

- Read PHASES.md in full, including prior phase Implementation Notes
- Read sibling SPEC.md — the correctness source of truth
- Identify which phase(s) introduced the buggy behavior — the fix's Implementation Notes will be appended there

---

## Step 4: Enter Plan Mode

If not already in plan mode, enter it now.

---

## Step 5: Draft the Fix Plan (TDD)

TDD enforcement is injected automatically via `subagent-launch.md` — every subagent inherits the TDD protocol.

### 5a. Partition Work

- Identify files that must change to fix the root cause
- Identify the regression test file(s) that will pin the bug
- If the fix naturally splits across independent files, partition into **work units** and **batches** — no two subagents in the same batch may touch the same file
- For a small single-file fix, a single work unit in a single batch is fine

### 5b. Write the Plan

The plan MUST contain all of the following sections as explicit, non-skippable steps. Use imperative language.

---

#### Header

```
# Fix: [Short Bug Title] — Implementation Plan

**Bug report:** [one-line summary of user's feedback]
**Root cause:** [one or two sentences]
**PHASES.md:** [path, or "N/A — standalone fix"]
**SPEC.md:** [path, or "N/A"]
**Goal:** [one sentence — the observable behavior after the fix]

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. All subagent edits happen in the current worktree — NEVER create worktrees for subagents
2. Every subagent follows TDD — write a failing regression test that pins the bug BEFORE the fix
3. The regression test must fail for the documented root cause, not for an unrelated reason
4. PHASES.md (if applicable) is updated AFTER EACH subagent completes (not deferred)
5. Every subagent's output is reviewed for correctness and root-cause alignment before continuing
6. Mistakes are fixed immediately before launching the next batch
7. After all agents finish, integration verification confirms the bug is gone and nothing else broke
8. Relevant CLAUDE.md files are updated if the fix establishes a new rule or gotcha
```

#### Work Unit Definitions

For each work unit, document:
- **Scope:** What part of the fix it covers
- **Files to create/modify:** Exact paths
- **Test files:** Exact paths for the regression test
- **TDD sequence:** The failing regression test (what it asserts, why it fails today), then the implementation that makes it pass
- **Root-cause link:** How this work unit addresses the root cause from Step 2
- **Batch:** Which parallel batch

Include a batch overview table if there are multiple units:

```
## Batch Overview

| Batch | Work Units | Parallel? | File Conflicts? |
|-------|-----------|-----------|-----------------|
| 1     | A         | Solo      | N/A             |
```

#### Task Initialization

```
## Initialize Task Tracking

!`cat ~/.claude/skills/_components/task-tracking.md`
```

#### Per-Batch Execution Steps

For each batch, include verbatim:

```
## Batch N

### Step N.1: Launch Subagents

!`cat ~/.claude/skills/_components/subagent-launch.md`

### Step N.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step N.3 until the review protocol below is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

!`cat ~/.claude/skills/_components/subagent-review.md`

### Step N.3: Update PHASES.md (MANDATORY IF APPLICABLE — DO NOT SKIP)

!`cat ~/.claude/skills/_components/phases-update.md`

### Step N.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/quality-gates.md`

### Step N.5: Proceed to Next Batch

**Checklist before proceeding (all must be true):**
- [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
- [ ] Regression test passes
- [ ] PHASES.md updated (if applicable)
- [ ] All quality gates pass

If any item is unchecked, go back and complete it. Do NOT launch the next batch.
```

#### Integration Verification Step

```
## Integration Verification (MANDATORY — DO NOT SKIP)

### Verify the Bug is Actually Fixed
- Re-run the regression test(s) — must pass
- Walk through the user's original reproduction steps mentally (or via tests) — confirm the symptom is gone
- Confirm no symptom-only patches: the fix must address the root cause from Step 2

### Verify Nothing Else Broke
- Read all modified files across subagents
- Verify imports resolve, no duplicate code, no conflicting exports
- Run broader quality gates relevant to the touched areas

### Fix Integration Issues
- If issues found: fix them and update PHASES.md (if applicable) with notes about what was fixed
```

#### CLAUDE.md Update Step

```
## Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

Review whether any CLAUDE.md files need updates as a result of this fix:
- A new critical rule / gotcha revealed by the root cause
- A new architectural constraint discovered
- A correction to outdated guidance that contributed to the bug

Rules:
- Keep lean and effective — only stable, structural information
- Do NOT add volatile info (test counts, line numbers, version strings)
- If no updates needed, explicitly state "No CLAUDE.md updates required" and move on
```

---

## Step 6: Prevent Recurrence — Update Upstream Skills (MANDATORY IF APPLICABLE)

Based on the failure category from Step 2c, identify which **existing skills** (if any) could be strengthened so this class of bug never reaches `/fix` again. This is NOT about the bug fix itself — it's about improving the process that let the bug through.

### 6a. Map Category → Candidate Skills

!`cat .claude/skill-config/skill-catalog.md 2>/dev/null || echo "No project-specific skill catalog configured. Use the available skills list from the system prompt to identify relevant skills for the failure category."`

Only propose updates where a concrete, durable rule can be added. Do **not** add volatile info or speculative guidance. If no skill genuinely benefits, explicitly state "No skill updates warranted" and skip Step 6b.

### 6b. Include Skill-Update Work Units in the Plan

For each skill that should be updated, add a dedicated **post-fix work unit** to the plan (runs AFTER the integration verification step, in its own batch):

- **Scope:** Update skill `<name>` to prevent category `<category>` recurrence
- **File to modify:** Exact path to the skill file (typically `~/.claude/skills/<name>/SKILL.md` or `~/.claude/commands/<name>.md`)
- **Rule to add:** The exact rule/guidance to append, phrased imperatively, grounded in the root cause from Step 2
- **Subagent:** Launch a Sonnet subagent to perform the edit. Prompt must include: the bug summary, root cause, category, the skill file path, and the precise rule text. Instructions: read the full skill first, insert the rule in the most appropriate section (do not append blindly), keep the skill lean, preserve existing structure.
- **Verification:** After the subagent completes, read the skill and confirm the rule is present, well-placed, and doesn't duplicate existing content.

Skill-update work units are independent of the bug-fix batches and MUST NOT block the bug fix itself. They run after Integration Verification but before final CLAUDE.md review.

Add this block verbatim to the plan when skill updates are warranted:

```
## Prevent Recurrence — Skill Updates (MANDATORY IF APPLICABLE — DO NOT SKIP)

**Failure category:** [from Step 2c]
**Justification:** [one sentence]

### Skills to update
| Skill | Path | Rule to add |
|-------|------|-------------|
| ...   | ...  | ...         |

### Step: Launch Skill-Update Subagents
Launch Sonnet subagent(s) in parallel (no worktree) — one per skill file. Each subagent:
1. Reads the full skill file
2. Inserts the new rule in the most appropriate section (not blindly appended)
3. Keeps the skill lean — no volatile info, no duplication
4. Returns a diff summary

### Step: Verify Skill Updates
For each updated skill: read the file, confirm the rule is present, well-placed, and coherent. Fix any issues immediately.
```

If no updates are warranted, include a one-line note in the plan: `**Prevent Recurrence:** No skill updates warranted — <reason>.`

### 6c. Append to Persistent Fix Log (MANDATORY — DO NOT SKIP)

Append one JSON record per fix to the user-level log so categories can be tracked over time:

**Log file:** `~/.claude/fix-log.jsonl` (one JSON object per line, UTF-8)

Append the entry as the FINAL step of the plan — after Integration Verification, after Skill Updates, after CLAUDE.md review — so it records the final state. Include this block verbatim in the plan:

```
## Append to Fix Log (MANDATORY — DO NOT SKIP)

Append a single JSON line to `~/.claude/fix-log.jsonl` with this schema:

{
  "timestamp": "<ISO-8601 UTC>",
  "project": "<repo name or cwd basename>",
  "branch": "<current git branch, or null>",
  "commit": "<HEAD short sha, or null>",
  "title": "<short bug title>",
  "bug_summary": "<one-line user report>",
  "root_cause": "<one or two sentences>",
  "category": "<one of: requirements-change | inadequate-test-coverage | inadequate-research | incorrect-spec | integration-gap | environment-platform | regression | ui-ux-polish | tooling-config | other>",
  "category_justification": "<one sentence>",
  "phases_md": "<path or null>",
  "phase_number": "<N or null>",
  "files_modified": ["path1", "path2"],
  "regression_tests": ["path/to/test"],
  "skills_updated": [
    { "skill": "<name>", "path": "<path>", "rule_added": "<summary>" }
  ],
  "skills_update_note": "<reason if none updated, else null>"
}

Use the Bash tool to append (create the file if missing). Do NOT rewrite existing lines. Example:

```
mkdir -p ~/.claude && printf '%s\n' '<single-line JSON>' >> ~/.claude/fix-log.jsonl
```

Verify the append succeeded by reading the last line of the file.
```

This log is the authoritative record for tracking failure-mode trends across projects over time. Do not store this data in project-local files.

---

## Step 7: Present Plan for Approval

Present the completed plan and wait for user approval before exiting plan mode.
