---
description: Plan and implement ALL phases across 1+ PHASES.md files using parallel Sonnet subagents, committing after each phase (reference-based components)
argument-hint: <path/to/PHASES1.md> [path/to/PHASES2.md] [...]
name: implement-phase-batch
plan-mode: never
---

# Implement Phase Batch

Draft a single self-contained plan covering all phases from one or more PHASES.md files. The plan is written to a file for execution via `/execute-plan` in a separate session. Uses TDD and parallel Sonnet subagents.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. The deliverable is a written plan file, not a plan-mode interaction.

**Flow:** Load context -> draft ONE self-contained plan covering all phases -> write plan to file -> report path to user.

**Critical: the plan must be fully self-contained.** The plan may be executed after the context window is cleared. Every execution instruction, loop control, blocking-issue protocol, and completion step MUST be baked into the generated plan itself — not left in this skill file. After the plan is written, it is the sole source of truth.

Execution-time components (review protocol, launch protocol, quality gates, etc.) are referenced by file path in the generated plan instead of inlined. The executing session reads them on demand from disk, reducing plan size and improving post-compaction recovery.

**Key differences from `/implement-phase`:**
- Takes 1+ PHASES.md paths (not just one); covers ALL phases across all of them in a single plan
- Plan is written to a file (not presented in plan mode) for execution in a separate session
- Commits and pushes after each completed phase (docs updated + QGs green)
- Cross-feature parallelism: phases from different features run concurrently when dependencies are satisfied and no file conflicts exist
- Early exit on blocking issues with a clear status report

All other constraints from `/implement-phase` carry over: TDD, Sonnet subagents, mandatory review, mandatory PHASES.md updates, mandatory QG pass, mandatory integration verification, mandatory CLAUDE.md review.

---

## Step 0: Task Tracking (MANDATORY — DO NOT SKIP)

Load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Load all context", description: "Resolve PHASES.md paths, read SPEC.md, read CLAUDE.md, check partitioning" })`
2. `TaskCreate({ subject: "Dirty tree check", description: "Verify clean working tree before planning" })`
3. `TaskCreate({ subject: "Draft comprehensive plan", description: "Write full plan covering all phases with execution model, work units, batches" })`
4. `TaskCreate({ subject: "Write plan file", description: "Write plan to feature plans/ directory" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

---

## Step 1: Load All Context

### 1a. Resolve PHASES.md Paths

- `$ARGUMENTS` must contain 1+ `.md` paths. If none are provided, use **AskUserQuestion** to ask for them.
- For each PHASES.md, confirm the file exists. If not, report and exclude it.

### 1b. Read Everything

For **each** PHASES.md:
1. Read the PHASES.md file **in full** — including all previously completed phases and their Implementation Notes
2. Read the sibling SPEC.md in the same directory — source of truth for correctness
3. Note the feature name (directory name, e.g. `foundation`, `auth-bootstrap`)

Also read:
- `CLAUDE.md` (project root) — for quality gates, critical rules, directory layout
- `docs/features/PARTITIONING.md` — for wave plan, dependency graph, phased-spec guidance, cross-feature ordering constraints

### 1c. Build the Cross-Feature Phase Queue

Scan all loaded PHASES.md files. For each phase with unchecked deliverables (`- [ ]`):
1. Record its feature, phase number, title, entry criteria, and files it will create/modify
2. Parse entry criteria for cross-feature dependencies (e.g. "Foundation Phase 1 complete")
3. Parse entry criteria for intra-feature dependencies (e.g. "Phase 2 complete")

Build a directed acyclic graph of all pending phases. The execution order respects this graph — a phase only becomes "ready" when all its entry criteria are satisfied.

---

## Step 2: Dirty Tree Check (MANDATORY — BEFORE DRAFTING PLAN)

!`cat .claude/skill-config/dirty-tree-check.md 2>/dev/null || cat ~/.claude/skills/_components/dirty-tree-check.md`

---

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

---

## Step 3: Draft the Comprehensive Plan

Write a single, **fully self-contained** plan covering ALL phases across ALL input features. **The plan must include every instruction needed for autonomous execution** — including the execution loop, phase-selection logic, blocking-issue protocol, and completion steps. When the executing session reads this plan file, it will execute it verbatim, potentially in a fresh context window. Nothing outside the plan can be relied upon.

**v2 RULE:** Execution-time components are NOT inlined in the plan. Each step lists the component file paths the executor must `Read` from disk before proceeding. Only the unique per-plan content (execution model, work units, batch structure, loop control) is written inline.

The plan MUST contain all of the following sections. Everything below is plan template content — write it into the plan.

### Plan Structure

---

**Plan header (write this, filling in bracketed values):**

> # Implementation Plan — [feature1] [+ feature2] [+ ...]  (v2)
>
> **PHASES.md files:**
> - [path1] ([feature1], N phases)
> [- [path2] ([feature2], M phases)]
>
> **SPEC.md files:**
> - [path1]
> [- [path2]]
>
> **Total phases:** X [across Y features]
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
> | Step B.5 | Commit Policy | `.claude/skill-config/commit-policy.md` (fallback: `~/.claude/skills/_components/commit-and-push.md`) |
> | Post-phase | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
> | Post-phase | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |
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
> 7. After all batches in a phase finish, integration verification confirms all changes work together
> 8. Relevant CLAUDE.md files are created/updated after each phase if changes warrant it
> 9. Each completed phase is committed and pushed before the next phase begins
> 10. Cross-feature phases may run in parallel when dependencies are satisfied and no file conflicts exist
> 11. This plan is self-contained — follow it exactly as written without relying on external context
> 12. **Before each step, `Read` the component files listed for that step from disk** — do NOT rely on memory

---

**Execution Schedule (fill in from the phase queue analysis):**

> ## Execution Schedule
>
> | Step | Feature(s) | Phase(s) | Title(s) | Blocked by | Parallel? |
> |------|-----------|----------|----------|------------|-----------|
> | 1    | foundation | P1 | Scaffold | — | Solo |
> | 2    | foundation P2 + auth-bootstrap P1 | Models + Keyring | foundation P1 | Yes |
> | ...  | ... | ... | ... | ... | ... |

---

**Per-Phase Plans — for each phase in execution order, write:**

> ### Phase: [feature] P[N] — [title]
>
> **Goal:** [one sentence]
> **Entry criteria:** [what must be complete — reference specific features+phases]
> **SPEC.md references:** [which sections of the feature's SPEC.md this phase implements]

Then define work units using the partitioning protocol:

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

For each work unit, document:
- **Scope:** Which deliverables it covers (copy the checkbox items from PHASES.md)
- **TDD:** yes/no (yes if deliverable has testable behavior; no for config, docs, scaffolding without logic)
- **Files to create/modify:** Exact paths (implementation files)
- **Test files:** Exact paths (TDD work units only)
- **Test expectations:** What tests to write and what they assert (TDD work units only)
- **Implementation goal:** What the implementation must achieve to satisfy tests and spec
- **Spec requirements:** Quote or reference the specific SPEC.md sections
- **Batch:** Which parallel batch within this phase (1, 2, etc.)

Include a batch overview table per phase:

> | Batch | Work Units | Parallel? | File Conflicts? |
> |-------|-----------|-----------|-----------------|
> | 1     | A, B      | Yes       | None            |
> | 2     | C         | Solo      | N/A             |

---

**Execution Protocol — write this entire section into the plan:**

> ## Execution Protocol
>
> This protocol governs the autonomous execution of every phase. Follow it exactly.
>
> ### Phase Selection Loop
>
> Repeat until all phases in the Execution Schedule are complete or a blocking issue triggers early exit:
>
> 1. **Select ready phase(s):** Identify phase(s) whose entry criteria are satisfied (prerequisite phases complete — all deliverables checked off in their PHASES.md). If multiple phases from different features are ready and marked parallel-eligible in the schedule, execute them concurrently. If no phases are ready, jump to Blocking Issue Protocol.
> 2. **Announce:** Print "Implementing [feature] Phase N: [title]"
> 3. **Review prior context:** Re-read all previously completed phases' Implementation Notes in this feature's PHASES.md. These contain imports, patterns, gotchas, and actual file paths that may differ from the original plan. They take priority over the plan where they diverge.
> 4. **Execute all batches** per the Per-Batch Steps below.
> 5. **Run Post-Phase Steps** below.
> 6. **Report:** Print "[feature] Phase N: [title] — committed as [hash]"
> 7. **Loop:** Re-evaluate which phases are now ready (completing one phase may unblock others). Return to step 1.
>
> ### Step 0: Initialize Task Tracking (MANDATORY PREREQUISITE — EXECUTE BEFORE ANYTHING ELSE)
>
> **This is the first thing you do when executing this plan. Do NOT skip ahead to any phase or batch.**
>
> Read `~/.claude/skills/_components/task-tracking.md` and follow its instructions exactly.
> It defines: task tool loading via ToolSearch, task creation for all work units, and the update protocol for tracking progress through test and implementation phases.
>
> ### Per-Batch Steps
>
> For each batch within a phase:
>
> #### Step B.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/source-reread.md` and follow its instructions.
> Re-read from disk: PHASES.md (current phase + prior Implementation Notes), SPEC.md (relevant sections), and the plan file itself. Do NOT rely on cached/remembered content.
>
> #### Step B.1: Launch Subagents (COMPOSE Agent TOOL CALLS — ZERO INLINE IMPLEMENTATION)
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
> #### Step B.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)
>
> **This is a blocking gate.** You CANNOT proceed to Step B.3 until the review protocol is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.
>
> Read `~/.claude/skills/_components/subagent-review.md` and follow its complete protocol.
> Also read `~/.claude/skills/_components/mount-site-verification.md` (referenced within subagent-review for new-file checks).
> Protocol covers: batch scope measurement, review execution (inline or via subagent), propagation check, mount-site verification, and verdict handling (PASS / PASS-WITH-FIXES / NEEDS-REWORK).
>
> #### Step B.3: Update PHASES.md (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/phases-update.md` and follow its instructions.
> Check off completed deliverables, add Implementation Notes block with date, work completed, integration notes, pitfalls, and files modified.
>
> #### Step B.4: Run Quality Gates (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/quality-gates.md` and follow its instructions.
> Run project quality gates. If batch introduced import indirection, field additions, alias changes, or re-exports — run the FULL suite. 100% pass required before proceeding.
>
> #### Step B.4.5: MCP Integration Test (BLOCKING — if applicable)
>
> Read `~/.claude/skills/_components/mcp/mcp-integration-test.md` to determine applicability.
> If the phase's PHASES.md has an `MCP Integration Test Assertions` block OR the phase produces runtime-observable changes, this is MANDATORY. Otherwise skip with a note.
>
> #### Step B.5: Commit Batch
>
> Read the commit policy: first try `.claude/skill-config/commit-policy.md` in the project root. If it doesn't exist, read `~/.claude/skills/_components/commit-and-push.md` instead. Follow whichever policy applies.
>
> #### Step B.6: Proceed to Next Batch
>
> **Checklist before proceeding (all must be true):**
> - [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
> - [ ] PHASES.md updated with completed deliverables and implementation notes
> - [ ] All quality gates pass
> - [ ] Step B.5 completed (commit per project policy, or skip if policy says so)
>
> If any item is unchecked, go back and complete it. Do NOT launch the next batch.
>
> ### Propagation Awareness Note
>
> When drafting work units, identify any that introduce import indirection (wrappers, proxies, facades) or add fields to widely-constructed structs/interfaces. For these work units, the plan MUST include:
> - A "propagation step" ensuring all consumers are migrated in the same batch
> - A vitest/jest alias addition if the new module wraps a mocked dependency
> - A note in the QG step to run the full suite (not just the affected language)
>
> ### Post-Phase Steps (after all batches in a phase)
>
> #### Integration Verification (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/integration-verification.md` and follow its complete protocol.
> Covers: cross-agent integration, spec alignment, and full-stack coverage for user-facing APIs.
>
> #### Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/claude-md-review.md` and follow its instructions.
> Review whether project root or subdirectory CLAUDE.md files need updates based on this phase's changes.
>
> #### Commit and Push Post-Phase Changes
>
> Read the commit policy: first try `.claude/skill-config/commit-policy.md` in the project root. If it doesn't exist, read `~/.claude/skills/_components/commit-and-push.md` instead. Follow whichever policy applies.

---

**Blocking Issue Protocol — write this into the plan:**

> ## Blocking Issue Protocol
>
> If a blocking issue is encountered at any point during execution:
>
> 1. **Stop all in-progress work.** Do not launch new subagents.
> 2. **Commit and push any completed phases** that haven't been committed yet.
> 3. **Print a blocking-issue report:**
>
>    ## Implementation Batch — Blocked
>
>    **Completed phases:** [list with commit hashes]
>    **Blocked phase:** [feature] Phase N: [title]
>    **Reason:** [specific description]
>    **Recovery suggestion:** [what the user should do]
>
>    **Remaining phases (not attempted):**
>    - [list]
>
> 4. **Do not attempt to work around the blocker.** The user provides a resolution and triggers autonomous implementation after.
>
> Blocking issues include:
> - Circular dependency in the phase graph
> - A subagent failure that can't be fixed after 2 retry attempts
> - A quality-gate failure that can't be fixed after 2 retry attempts
> - A git push conflict that can't be resolved by rebase
> - A phase whose entry criteria reference a feature/phase not in the input set
> - Any error that would require architectural decisions beyond the scope of the specs

---

**Completion section — write this into the plan:**

> ## Completion
>
> When all phases in the Execution Schedule are complete:
>
> 1. **Run the full quality-gate suite one final time** across the entire codebase.
> 2. **Print a completion report:**
>
>    ## Implementation Batch — Complete
>
>    **Features implemented:** [list]
>    **Total phases completed:** N
>    **Total commits:** M
>    **Final quality-gate status:** all green
>
>    **Commit log:**
>    | Commit | Feature | Phase | Title |
>    |--------|---------|-------|-------|
>    | abc1234 | foundation | P1 | Scaffold |
>    | def5678 | auth-bootstrap | P1 | Keyring Wrapper |
>
>    **Implementation Notes summary:**
>    [key cross-feature integration notes and pitfalls, collapsed into a brief reference for the next wave]

---

**Work Log — write this into the plan:**

> ## Append to Work Log (MANDATORY — DO NOT SKIP)
>
> Read `~/.claude/skills/_components/work-log.md` and follow its instructions.
> Call interview_work_log_append MCP tool with skill, project, title, summary, files_modified, and technical_context.

---

## Step 5: Write Plan File

!`cat ~/.claude/skills/_components/plan-file-output.md`

**Frontmatter for `/implement-phase-batch`:**
- `kind: implementation-plan`
- `feature_id:` — parent feature directory name (or composite if multi-feature; use the first feature's directory name and note the others in the plan body)
- `status: Ready` (or `Draft` if `--batch` halted on `NEEDS_INPUT.md`)
- `phases:` — every phase number this plan covers across all input PHASES.md files.
