---
description: Draft a TDD implementation plan for a PHASES.md phase using parallel Sonnet subagents
argument-hint: <path/to/PHASES.md> [phase number]
name: implement-phase
---

# Implement Phase

Draft a detailed implementation plan (in plan mode) for a single phase from a PHASES.md file. The plan uses TDD and parallel Sonnet subagents, with all hard requirements encoded as explicit non-skippable steps in the plan itself.

---

## Step 1: Load Context

### 1a. Resolve PHASES.md Path

- If `$ARGUMENTS` contains a `.md` path, use it as the PHASES.md file
- If `$ARGUMENTS` contains only a number, infer PHASES.md from previous conversation context
- If no path can be determined, use **AskUserQuestion** to ask for it

### 1b. Read PHASES.md and SPEC.md

- Read the PHASES.md file **in full** — including all previously completed phases and their Implementation Notes
- Read the SPEC.md in the same directory (sibling file) — this is the source of truth for correctness
- If SPEC.md doesn't exist, **AskUserQuestion** to confirm proceeding without a spec

### 1c. Determine Target Phase

- If `$ARGUMENTS` contains a phase number or title, use it
- Otherwise, scan PHASES.md for the first phase with unchecked deliverables (`- [ ]`)
- If all phases are complete, inform the user and stop
- Announce: **"Implementing Phase N: [title]"**

### 1d. Check Prerequisites

- Read the phase's **Prerequisites** section
- Verify prerequisite phases are complete (all deliverables checked in PHASES.md)
- If prerequisites are incomplete, **AskUserQuestion**: "Phase N depends on [X] which isn't complete. Proceed anyway?"

---

## Step 2: Enter Plan Mode

If not already in plan mode, enter it now.

---

## Step 3: Analyze and Partition

### 3a. Analyze the Phase

**First, review all previously completed phases** — especially their **Implementation Notes** sections. These contain:
- Integration notes for subsequent phases (imports, patterns established, gotchas)
- Pitfalls and guidance (wrong assumptions, workarounds applied)
- Actual files modified (may differ from original plan)

Use this context to inform the plan. If a prior phase's integration notes say "Phase 2 imports X from Y", the plan must reflect that. If a pitfall says "serde not added yet — use feature gate in Phase 4", the plan must account for it.

Then, for each deliverable in the target phase:
- Identify the files that will be created or modified
- Identify the test files needed
- Determine dependencies between deliverables

### 3b. Partition into Subagent Work Units

**Critical constraint: No two subagents in the same batch may modify the same file.**

Partition deliverables into **work units** — groups of deliverables assignable to a single Sonnet subagent. Then group work units into **batches** where all units in a batch can run in parallel (no file overlap). Batch 1 runs first, Batch 2 after Batch 1 completes, etc.

---

## Step 4: Draft the Plan

Write the plan in plan mode. The plan MUST contain all of the following sections as explicit, non-skippable steps. Use imperative language ("Do X", not "Consider X").

### Plan Structure

The plan must follow this structure exactly:

---

#### Header

```
# Phase N: [Title] — Implementation Plan

**PHASES.md:** [path]
**SPEC.md:** [path]
**Goal:** [one sentence]

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. All subagent edits happen in the current worktree — NEVER create worktrees for subagents
2. Every subagent follows TDD — failing test BEFORE implementation code
3. PHASES.md is updated AFTER EACH subagent completes (not deferred)
4. Every subagent's output is reviewed for correctness and spec alignment before continuing
5. Mistakes are fixed immediately before launching the next batch
6. After all agents finish, integration verification confirms all changes work together
7. Relevant CLAUDE.md files are updated if changes warrant it
```

#### Work Unit Definitions

For each work unit, document:
- **Scope:** Which deliverables it covers (copy the checkbox items from PHASES.md)
- **Files to create/modify:** Exact paths
- **Test files:** Exact paths
- **TDD sequence:** What tests to write, what they assert, what implementation satisfies them
- **Spec requirements:** Quote or reference the specific SPEC.md sections this unit must satisfy
- **Batch:** Which parallel batch (1, 2, etc.)

Include a summary table:

```
## Batch Overview

| Batch | Work Units | Parallel? | File Conflicts? |
|-------|-----------|-----------|-----------------|
| 1     | A, B      | Yes       | None            |
| 2     | C         | Solo      | N/A             |
```

#### Task Initialization

```
## Initialize Task Tracking

!`cat ~/.claude/skills/_components/task-tracking.md`
```

#### Per-Batch Execution Steps

For each batch, the plan must include these steps verbatim:

```
## Batch N

### Step N.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/source-reread.md`

### Step N.1: Launch Subagents

!`cat ~/.claude/skills/_components/subagent-launch.md`

### Step N.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step N.3 until the review protocol below is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

!`cat ~/.claude/skills/_components/subagent-review.md`

### Step N.3: Update PHASES.md (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/phases-update.md`

### Step N.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/quality-gates.md`

### Step N.5: Proceed to Next Batch

**Checklist before proceeding (all must be true):**
- [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
- [ ] PHASES.md updated with completed deliverables and implementation notes
- [ ] All quality gates pass

If any item is unchecked, go back and complete it. Do NOT launch the next batch.
```

#### Integration Verification Step

```
## Integration Verification (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/integration-verification.md`
```

#### CLAUDE.md Update Step

```
## Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/claude-md-review.md`
```

---

## Step 5: Present Plan for Approval

Present the completed plan and wait for user approval before exiting plan mode.
