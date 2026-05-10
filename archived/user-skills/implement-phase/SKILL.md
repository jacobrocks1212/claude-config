---
description: Draft a TDD implementation plan for a PHASES.md phase using parallel Sonnet subagents
argument-hint: <path/to/PHASES.md> [phase number]
name: implement-phase
plan-mode: required
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

## Step 2: Dirty Tree Check (MANDATORY — BEFORE PLAN MODE)

!`cat .claude/skill-config/dirty-tree-check.md 2>/dev/null || cat ~/.claude/skills/_components/dirty-tree-check.md`

---

## Step 3: Plan Mode Gate (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/plan-mode-gate.md`

---

## Step 4: Analyze and Partition

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

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

---

## Step 5: Draft the Plan

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

## EXECUTION MODEL — READ THIS FIRST

This plan uses an **orchestrator + Sonnet subagent** architecture:

| Role | What it does | Allowed tools |
|------|-------------|---------------|
| **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch subagents, review output, run quality gates, update tracking docs | `Agent`, `Read`, `Bash` (gates only), `TaskCreate`/`TaskUpdate` |
| **Sonnet subagent** | Write ALL source and test code | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob` |

**HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, `work-log.jsonl`.

**Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained context — subagent has zero prior context>" })`

Every "Launch Subagents" step below MUST be executed by composing Agent calls using this pattern.

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. **ALL implementation and test-writing work MUST be delegated to Sonnet subagents via the Agent tool** — the orchestrating session MUST NOT call `Edit` or `Write` on source or test files. The ONLY exception: trivial PASS-WITH-FIXES items (a few lines). If you are composing an `Edit` or `Write` call targeting a source/test file, STOP — compose an `Agent` tool call instead.
2. All subagent edits happen in the current worktree — NEVER create worktrees for subagents
3. Every TDD work unit goes through the test-first pipeline — dedicated test agent writes failing tests, dedicated implementation agent makes them pass
4. PHASES.md is updated AFTER EACH batch completes (not deferred)
5. Every subagent's output is reviewed for correctness, spec alignment, and TDD discipline before continuing
6. Mistakes are fixed immediately before launching the next batch
7. After all agents finish, integration verification confirms all changes work together
8. Relevant CLAUDE.md files are updated if changes warrant it
```

#### Work Unit Definitions

For each work unit, document:
- **Scope:** Which deliverables it covers (copy the checkbox items from PHASES.md)
- **TDD:** yes/no (yes if deliverable has testable behavior; no for config, docs, scaffolding without logic)
- **Files to create/modify:** Exact paths (implementation files)
- **Test files:** Exact paths (TDD work units only)
- **Test expectations:** What tests to write and what they assert (TDD work units only)
- **Implementation goal:** What the implementation must achieve to satisfy tests and spec
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

#### Step 0: Task Initialization (PREREQUISITE GATE)

This MUST be the first executable step in the plan — before any batch. Label it "Step 0" so it is unambiguously first:

```
## Step 0: Initialize Task Tracking (MANDATORY PREREQUISITE — EXECUTE BEFORE ANYTHING ELSE)

**This is the first thing you do when executing this plan. Do NOT skip ahead to Batch 1.**

!`cat ~/.claude/skills/_components/task-tracking.md`
```

#### Per-Batch Execution Steps

For each batch, the plan must include these steps verbatim:

```
## Batch N

### Step N.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/source-reread.md`

### Step N.1: Launch Subagents (COMPOSE Agent TOOL CALLS — ZERO INLINE IMPLEMENTATION)

**PRE-FLIGHT CHECK:** You are about to dispatch work to Sonnet subagents. Confirm: (1) you will use the `Agent` tool with `model: "sonnet"` for ALL code changes in this step, (2) you will NOT call `Edit` or `Write` on any source or test file. If either is false, re-read the EXECUTION MODEL section above before proceeding.

!`cat ~/.claude/skills/_components/subagent-launch.md`

**POST-DISPATCH GATE:** After all subagents in this step complete, verify you composed `Agent` tool calls and did NOT edit source/test files directly. If you violated this constraint, revert your inline edits and re-dispatch via Agent before proceeding to the review step.

### Step N.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step N.3 until the review protocol below is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

!`cat ~/.claude/skills/_components/subagent-review.md`

### Step N.3: Update PHASES.md (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/phases-update.md`

### Step N.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/quality-gates.md`

### Step N.4.5: MCP Integration Test (BLOCKING — execute Applicability Rule)

!`cat ~/.claude/skills/_components/mcp/mcp-integration-test.md`

### Step N.5: Proceed to Next Batch

**Checklist before proceeding (all must be true):**
- [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
- [ ] PHASES.md updated with completed deliverables and implementation notes
- [ ] All quality gates pass
- [ ] Step N.4.5 MCP integration test executed, OR explicitly skipped with documented reason (check PHASES.md for `MCP Integration Test Assertions` block — if present, test is MANDATORY)

If any item is unchecked, go back and complete it. Do NOT launch the next batch.
```

#### Propagation Awareness Note

When drafting work units, identify any that introduce import indirection (wrappers, proxies, facades) or add fields to widely-constructed structs/interfaces. For these work units, the plan MUST include:
- A "propagation step" ensuring all consumers are migrated in the same batch
- A vitest/jest alias addition if the new module wraps a mocked dependency
- A note in the QG step to run the full suite (not just the affected language)

This prevents delayed blast-zone failures — where a correct wrapper works in isolation but breaks 50+ tests that mock the underlying module.

#### Integration Verification Step

```
!`cat .claude/skill-config/integration-verification.md 2>/dev/null || cat ~/.claude/skills/_components/integration-verification.md`
```

#### CLAUDE.md Update Step

```
!`cat ~/.claude/skills/_components/claude-md-review.md`
```

#### Work Log Step

```
## Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`
```

---

## Step 6: Present Plan for Approval

Present the completed plan and wait for user approval before exiting plan mode.
