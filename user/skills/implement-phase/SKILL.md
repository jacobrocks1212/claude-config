---
description: Draft a TDD implementation plan for a PHASES.md phase using parallel Sonnet subagents (reference-based components)
argument-hint: <path/to/PHASES.md> [phase number]
name: implement-phase
plan-mode: never
---

# Implement Phase

Draft a detailed implementation plan for a single phase from a PHASES.md file. The plan is written to a file for execution via `/execute-plan` in a separate session. The plan uses TDD and parallel Sonnet subagents, with all hard requirements encoded as explicit non-skippable steps in the plan itself.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. The deliverable is a written plan file, not a plan-mode interaction.

Execution-time components (review protocol, launch protocol, quality gates, etc.) are referenced by file path in the generated plan instead of inlined. The executing session reads them on demand from disk, reducing plan size and improving post-compaction recovery.

---

## Step 0: Task Tracking (MANDATORY — DO NOT SKIP)

Load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Load context", description: "Resolve PHASES.md, read SPEC.md, determine target phase, read CLAUDE.md" })`
2. `TaskCreate({ subject: "Dirty tree check", description: "Verify clean working tree before planning" })`
3. `TaskCreate({ subject: "Analyze and partition", description: "Analyze phase, partition into TDD work units, structure batches" })`
4. `TaskCreate({ subject: "Draft implementation plan", description: "Write full plan with execution model, work units, QG steps" })`
5. `TaskCreate({ subject: "Write plan file", description: "Write plan to feature plans/ directory" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

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

## Step 3: Analyze and Partition

### 4a. Analyze the Phase

**First, review all previously completed phases** — especially their **Implementation Notes** sections. These contain:
- Integration notes for subsequent phases (imports, patterns established, gotchas)
- Pitfalls and guidance (wrong assumptions, workarounds applied)
- Actual files modified (may differ from original plan)

Use this context to inform the plan. If a prior phase's integration notes say "Phase 2 imports X from Y", the plan must reflect that. If a pitfall says "serde not added yet — use feature gate in Phase 4", the plan must account for it.

Then, for each deliverable in the target phase:
- Identify the files that will be created or modified
- Identify the test files needed
- Determine dependencies between deliverables

### 4b. Partition into Subagent Work Units

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

---

## Step 5: Draft the Plan

Write the plan. The plan MUST contain all of the following sections as explicit, non-skippable steps. Use imperative language ("Do X", not "Consider X").

**v2 RULE:** Execution-time components are NOT inlined in the plan. Each step lists the component file paths the executor must `Read` from disk before proceeding. Only the unique per-plan content (execution model, work units, batch structure) is written inline.

### Plan Structure

The plan must follow this exact structure. Everything below is plan template content — write it into the plan.

---

**Plan header (write this verbatim, filling in the bracketed values):**

> # Phase N: [Title] — Implementation Plan (v2)
>
> **PHASES.md:** [path]
> **SPEC.md:** [path]
> **Goal:** [one sentence]
> **Plan version:** v2 (reference-based — components loaded from disk per step)

**Execution model section (write this verbatim):**

> ## EXECUTION MODEL — READ THIS FIRST
>
> This plan uses an **orchestrator + Sonnet subagent** architecture:
>
> | Role | What it does | Allowed tools |
> |------|-------------|---------------|
> | **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch subagents, review output, run quality gates, update tracking docs | `Agent`, `Read`, `Bash` (gates only), `TaskCreate`/`TaskUpdate` |
> | **Sonnet subagent** | Write ALL source and test code | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob` |
>
> **HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, `work-log.jsonl`.
>
> **Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained context — subagent has zero prior context>" })`

**Component loading protocol (write this verbatim):**

> ## COMPONENT LOADING PROTOCOL
>
> This plan references reusable component files by path instead of inlining their content. **Before executing each step**, `Read` the component files listed for that step from disk. Do NOT proceed from memory of their contents — always load fresh. After context compaction, re-read this plan file first, then load components for your current step.

**Component reference card (write this verbatim):**

> ## Component Reference Card
>
> | Step | Component | Path |
> |------|-----------|------|
> | Step 0 | Task Tracking | `~/.claude/skills/_components/task-tracking.md` |
> | Step B.0 | Source Re-read | `~/.claude/skills/_components/source-reread.md` |
> | Step B.1 | TDD Protocol | `~/.claude/skills/_components/tdd-protocol.md` |
> | Step B.1 | Subagent Launch | `~/.claude/skills/_components/subagent-launch.md` |
> | Step B.1 | Test Agent Briefing | `~/.claude/skills/_components/tdd-test-agent.md` |
> | Step B.1 | Impl Agent Briefing | `~/.claude/skills/_components/implementation-agent.md` |
> | Step B.2 | Subagent Review | `~/.claude/skills/_components/subagent-review.md` |
> | Step B.2 | Mount-Site Verification | `~/.claude/skills/_components/mount-site-verification.md` |
> | Step B.3 | PHASES.md Update | `~/.claude/skills/_components/phases-update.md` |
> | Step B.4 | Quality Gates | `~/.claude/skills/_components/quality-gates.md` |
> | Step B.4.5 | MCP Integration Test | `~/.claude/skills/_components/mcp/mcp-integration-test.md` |
> | Post-batch | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
> | Post-batch | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |
> | Final | Work Log | `~/.claude/skills/_components/work-log.md` |

**Mandatory rules section (write this verbatim):**

> ## MANDATORY RULES — DO NOT SKIP ANY STEP
>
> 1. **ALL implementation and test-writing work MUST be delegated to Sonnet subagents via the Agent tool** — the orchestrating session MUST NOT call `Edit` or `Write` on source or test files. The ONLY exception: trivial PASS-WITH-FIXES items (a few lines).
> 2. All subagent edits happen in the current worktree — NEVER create worktrees for subagents
> 3. Every TDD work unit goes through the test-first pipeline — dedicated test agent writes failing tests, dedicated implementation agent makes them pass
> 4. PHASES.md is updated AFTER EACH batch completes (not deferred)
> 5. Every subagent's output is reviewed for correctness, spec alignment, and TDD discipline before continuing
> 6. Mistakes are fixed immediately before launching the next batch
> 7. After all agents finish, integration verification confirms all changes work together
> 8. Relevant CLAUDE.md files are updated if changes warrant it
> 9. **Before each step, `Read` the component files listed for that step from disk** — do NOT rely on memory

---

**Work Unit Definitions — for each work unit, document:**

- **Scope:** Which deliverables it covers (copy the checkbox items from PHASES.md)
- **TDD:** yes/no (yes if deliverable has testable behavior; no for config, docs, scaffolding without logic)
- **Files to create/modify:** Exact paths (implementation files)
- **Test files:** Exact paths (TDD work units only)
- **Test expectations:** What tests to write and what they assert (TDD work units only)
- **Implementation goal:** What the implementation must achieve to satisfy tests and spec
- **Spec requirements:** Quote or reference the specific SPEC.md sections this unit must satisfy
- **Batch:** Which parallel batch (1, 2, etc.)

**Include a Batch Overview table:**

> | Batch | Work Units | Parallel? | File Conflicts? |
> |-------|-----------|-----------|-----------------|
> | 1     | A, B      | Yes       | None            |
> | 2     | C         | Solo      | N/A             |

---

**Step 0 — write this into the plan:**

> ## Step 0: Initialize Task Tracking (MANDATORY PREREQUISITE — EXECUTE BEFORE ANYTHING ELSE)
>
> **This is the first thing you do when executing this plan. Do NOT skip ahead to Batch 1.**
>
> Read `~/.claude/skills/_components/task-tracking.md` and follow its instructions exactly.
> It defines: task tool loading via ToolSearch, task creation for all work units, and the update protocol for tracking progress through test and implementation phases.

---

**Per-Batch Execution Steps — for each batch, write these steps into the plan:**

> ## Batch N
>
> ### Step N.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/source-reread.md` and follow its instructions.
> Re-read from disk: PHASES.md (current phase + prior Implementation Notes), SPEC.md (relevant sections), and the plan file itself. Do NOT rely on cached/remembered content.
>
> ### Step N.1: Launch Subagents (COMPOSE Agent TOOL CALLS — ZERO INLINE IMPLEMENTATION)
>
> **PRE-FLIGHT CHECK:** You are about to dispatch work to Sonnet subagents. Confirm: (1) you will use the `Agent` tool with `model: "sonnet"` for ALL code changes in this step, (2) you will NOT call `Edit` or `Write` on any source or test file. If either is false, re-read the EXECUTION MODEL section above.
>
> Read ALL of these before proceeding:
> 1. `~/.claude/skills/_components/tdd-protocol.md` — TDD decision gate: determines which WUs get test-first pipeline vs. direct implementation
> 2. `~/.claude/skills/_components/subagent-launch.md` — Launch orchestration: Phase A (test agents), Phase B (impl agents), failed agent recovery protocol
> 3. `~/.claude/skills/_components/tdd-test-agent.md` — Test agent prompt template: include this briefing verbatim in every test agent's prompt
> 4. `~/.claude/skills/_components/implementation-agent.md` — Impl agent prompt template: include this briefing verbatim in every impl agent's prompt
>
> Note: `subagent-launch.md` references the other components above via internal directives — since you've already read them, ignore those directives in the file.
>
> **POST-DISPATCH GATE:** After all subagents complete, verify you composed `Agent` tool calls and did NOT edit source/test files directly. If you violated this, revert inline edits and re-dispatch via Agent.
>
> ### Step N.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)
>
> **This is a blocking gate.** You CANNOT proceed to Step N.3 until the review protocol is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.
>
> Read `~/.claude/skills/_components/subagent-review.md` and follow its complete protocol.
> Also read `~/.claude/skills/_components/mount-site-verification.md` (referenced within subagent-review for new-file checks).
> Protocol covers: batch scope measurement, review execution (inline or via subagent), propagation check, mount-site verification, and verdict handling (PASS / PASS-WITH-FIXES / NEEDS-REWORK).
>
> ### Step N.3: Update PHASES.md (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/phases-update.md` and follow its instructions.
> Check off completed deliverables, add Implementation Notes block with date, work completed, integration notes, pitfalls, and files modified.
>
> ### Step N.4: Run Quality Gates (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/quality-gates.md` and follow its instructions.
> Run project quality gates. If batch introduced import indirection, field additions, alias changes, or re-exports — run the FULL suite. 100% pass required before proceeding.
>
> ### Step N.4.5: MCP Integration Test (BLOCKING — if applicable)
>
> Read `~/.claude/skills/_components/mcp/mcp-integration-test.md` to determine applicability.
> If the phase's PHASES.md has an `MCP Integration Test Assertions` block OR the phase produces runtime-observable changes, this is MANDATORY. Otherwise skip with a note.
>
> ### Step N.5: Proceed to Next Batch
>
> **Checklist before proceeding (all must be true):**
> - [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
> - [ ] PHASES.md updated with completed deliverables and implementation notes
> - [ ] All quality gates pass
>
> If any item is unchecked, go back and complete it. Do NOT launch the next batch.

---

**Propagation Awareness Note — write this into the plan:**

When drafting work units, identify any that introduce import indirection (wrappers, proxies, facades) or add fields to widely-constructed structs/interfaces. For these work units, the plan MUST include:
- A "propagation step" ensuring all consumers are migrated in the same batch
- A vitest/jest alias addition if the new module wraps a mocked dependency
- A note in the QG step to run the full suite (not just the affected language)

---

**Integration Verification Step — write this into the plan:**

> ## Integration Verification (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/integration-verification.md` and follow its complete protocol.
> Covers: cross-agent integration (imports resolve, no duplicates, no conflicts), spec alignment (re-read SPEC.md, verify correctness), and full-stack coverage for user-facing APIs.

**CLAUDE.md Update Step — write this into the plan:**

> ## Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/claude-md-review.md` and follow its instructions.
> Review whether project root or subdirectory CLAUDE.md files need updates based on this phase's changes.

**Work Log Step — write this into the plan:**

> ## Append to Work Log (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/work-log.md` and follow its instructions.
> Call interview_work_log_append MCP tool with skill, project, title, summary, files_modified, and technical_context.

---

## Step 6: Write Plan File

!`cat ~/.claude/skills/_components/plan-file-output.md`
