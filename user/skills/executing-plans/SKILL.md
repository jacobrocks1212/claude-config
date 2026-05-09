---
name: executing-plans
description: Use when you have a written implementation plan to execute in a separate session with review checkpoints
---

> **Note:** This is the legacy planning pipeline. For new work, prefer: `/spec` → `/spec-phases` → `/implement-phase`

# Executing Plans

## Overview

Load plan, review critically, execute tasks in batches, report for review between batches.

**Core principle:** Batch execution with checkpoints for architect review.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## The Process

### Step 1: Load and Review Plan
1. Read plan file
2. Review critically - identify any questions or concerns about the plan
3. If concerns: Raise them with your human partner before starting
4. If no concerns: proceed to Step 1.5

### Step 1.5: Load Task Tools and Initialize Tracking (MANDATORY FIRST ACTION)

**STOP. Before executing ANY part of the plan, you MUST load task tools and create tasks.**

1. Call `ToolSearch({ query: "select:TaskCreate,TaskUpdate,TaskGet,TaskList" })` NOW
2. Verify all four tools are available in your tool list
3. If the plan contains a "Task Tracking" or "Initialize Task Tracking" section, follow it to create tasks for every work unit
4. If the plan does NOT have an explicit task tracking section, create one task per work unit/batch yourself using the plan's work unit definitions
5. **Do NOT proceed to Step 1.6 or Step 2 until all tasks are created and you can verify them with TaskList**

### Step 1.6: Honor the Plan's Execution Model (MANDATORY IF PRESENT)

If the plan contains an **EXECUTION MODEL** section or mandatory rules about delegating to Sonnet subagents:
- **You are the orchestrator** — your job is to compose `Agent` tool calls and dispatch Sonnet subagents, NOT to write source/test code yourself
- **HARD RULE: You MUST NOT call `Edit` or `Write` on any source or test file.** If you are about to edit a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP. Compose an `Agent({ model: "sonnet", prompt: "..." })` call instead and dispatch it
- Each step labeled "Launch Subagents" means composing `Agent` tool calls with full self-contained context (subagents have zero prior context)
- Review each subagent's output per the plan's review protocol before proceeding
- This overrides the default "execute directly" behavior in Step 2
- **Self-check:** Before every code-modifying action, ask: "Am I about to call Edit/Write on a source file?" If yes, compose an Agent call instead

If the plan does NOT specify an execution model, execute tasks directly in Step 2 as usual.

### Step 2: Execute Batch
**Follow the plan's batch structure.** If the plan doesn't define batches, default to first 3 tasks.

For each task:
1. Mark as in_progress
2. Follow each step exactly (plan has bite-sized steps). **If the plan requires subagent delegation (Step 1.5), compose Agent tool calls — do not edit source/test files yourself.**
3. Run verifications as specified
4. Mark as completed

### Step 3: Report
When batch complete:
- Show what was implemented
- Show verification output
- Say: "Ready for feedback."

### Step 4: Continue
Based on feedback:
- Apply changes if needed
- Execute next batch
- Repeat until complete

### Step 5: Complete Development

After all tasks complete and verified:
- Run the full test suite to confirm nothing is broken
- Present a summary of changes and any remaining concerns
- Ask the user how they'd like to proceed (merge, more testing, etc.)

## When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker mid-batch (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember
- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Between batches: just report and wait
- Stop when blocked, don't guess
