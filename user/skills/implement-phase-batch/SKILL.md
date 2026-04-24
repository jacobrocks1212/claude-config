---
description: Plan and implement ALL phases across 1+ PHASES.md files using parallel Sonnet subagents, committing after each phase
argument-hint: <path/to/PHASES1.md> [path/to/PHASES2.md] [...]
name: implement-phase-batch
---

# Implement Phase Batch

Plan (once) and then continuously implement all phases from one or more PHASES.md files using TDD and parallel Sonnet subagents until all phases are complete or a blocking issue forces early exit.

**Flow:** Load context → enter plan mode → draft ONE self-contained plan covering all phases → user approves → exit plan mode → execute the plan autonomously.

**Critical: the plan must be fully self-contained.** The plan may be executed after the context window is cleared. Every execution instruction, loop control, blocking-issue protocol, and completion step MUST be baked into the generated plan itself — not left in this skill file. After approval, the plan is the sole source of truth.

**Key differences from `/implement-phase`:**
- Takes 1+ PHASES.md paths (not just one); covers ALL phases across all of them in a single plan
- Plan mode entered exactly once (at the start); after user approval, execution is fully autonomous
- Commits and pushes after each completed phase (docs updated + QGs green)
- Cross-feature parallelism: phases from different features run concurrently when dependencies are satisfied and no file conflicts exist
- Early exit on blocking issues with a clear status report

All other constraints from `/implement-phase` carry over: TDD, Sonnet subagents, mandatory review, mandatory PHASES.md updates, mandatory QG pass, mandatory integration verification, mandatory CLAUDE.md review.

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

## Step 2: Enter Plan Mode

If not already in plan mode, enter it now.

---

## Step 3: Draft the Comprehensive Plan

Write a single, **fully self-contained** plan covering ALL phases across ALL input features. **The plan must include every instruction needed for autonomous execution** — including the execution loop, phase-selection logic, blocking-issue protocol, and completion steps. After the user approves this plan, it will be executed verbatim, potentially after a context-window clear. Nothing outside the plan can be relied upon.

The plan MUST contain all of the following sections.

### Plan Structure

The plan must follow this structure exactly:

---

```
# Implementation Plan — [feature1] [+ feature2] [+ ...]

**PHASES.md files:**
- [path1] ([feature1], N phases)
[- [path2] ([feature2], M phases)]

**SPEC.md files:**
- [path1]
[- [path2]]

**Total phases:** X [across Y features]

---

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. All subagent edits happen in the current worktree — NEVER create worktrees for subagents
2. Every subagent follows TDD — failing test BEFORE implementation code
3. PHASES.md is updated AFTER EACH batch completes (not deferred)
4. Every subagent's output is reviewed for correctness and spec alignment before continuing
5. Mistakes are fixed immediately before launching the next batch
6. After all batches in a phase finish, integration verification confirms all changes work together
7. Relevant CLAUDE.md files are created/updated after each phase if changes warrant it
8. Each completed phase is committed and pushed before the next phase begins
9. Cross-feature phases may run in parallel when dependencies are satisfied and no file conflicts exist
10. This plan is self-contained — follow it exactly as written without relying on external context

---

## Execution Schedule

| Step | Feature(s) | Phase(s) | Title(s) | Blocked by | Parallel? |
|------|-----------|----------|----------|------------|-----------|
| 1    | foundation | P1 | Scaffold | — | Solo |
| 2    | foundation P2 + auth-bootstrap P1 | Models + Keyring | foundation P1 | Yes |
| ...  | ... | ... | ... | ... | ... |

---

## Per-Phase Plans

[For each phase in execution order:]

### Phase: [feature] P[N] — [title]

**Goal:** [one sentence]
**Entry criteria:** [what must be complete — reference specific features+phases]
**SPEC.md references:** [which sections of the feature's SPEC.md this phase implements]

**Work Units:**

[For each work unit:]
- **Scope:** Which deliverables it covers (copy the checkbox items from PHASES.md)
- **Files to create/modify:** Exact paths
- **Test files:** Exact paths
- **TDD sequence:** What tests to write, what they assert, what implementation satisfies them
- **Spec requirements:** Quote or reference the specific SPEC.md sections
- **Batch:** Which parallel batch within this phase (1, 2, etc.)

**Batch Overview:**

| Batch | Work Units | Parallel? | File Conflicts? |
|-------|-----------|-----------|-----------------|
| 1     | A, B      | Yes       | None            |
| 2     | C         | Solo      | N/A             |

[Repeat for each phase]

---

## Execution Protocol

This protocol governs the autonomous execution of every phase. Follow it exactly.

### Phase Selection Loop

Repeat until all phases in the Execution Schedule are complete or a blocking issue triggers early exit:

1. **Select ready phase(s):** Identify phase(s) whose entry criteria are satisfied (prerequisite phases complete — all deliverables checked off in their PHASES.md). If multiple phases from different features are ready and marked parallel-eligible in the schedule, execute them concurrently. If no phases are ready, jump to Blocking Issue Protocol.
2. **Announce:** Print "⏳ Implementing [feature] Phase N: [title]"
3. **Review prior context:** Re-read all previously completed phases' Implementation Notes in this feature's PHASES.md. These contain imports, patterns, gotchas, and actual file paths that may differ from the original plan. They take priority over the plan where they diverge.
4. **Execute all batches** per the Per-Batch Steps below.
5. **Run Post-Phase Steps** below.
6. **Report:** Print "✅ [feature] Phase N: [title] — committed as [hash]"
7. **Loop:** Re-evaluate which phases are now ready (completing one phase may unblock others). Return to step 1.

### Initialize Task Tracking (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/task-tracking.md`

### Per-Batch Steps

For each batch within a phase:

#### Step B.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/source-reread.md`

#### Step B.1: Launch Subagents

!`cat ~/.claude/skills/_components/subagent-launch.md`

#### Step B.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step B.3 until the review protocol below is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

!`cat ~/.claude/skills/_components/subagent-review.md`

#### Step B.3: Update PHASES.md (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/phases-update.md`

#### Step B.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/quality-gates.md`

#### Step B.5: Commit and Push Batch (use "Phase batch" message format)

!`cat .claude/skill-config/commit-policy.md 2>/dev/null || cat ~/.claude/skills/_components/commit-and-push.md`

#### Step B.6: Proceed to Next Batch

**Checklist before proceeding (all must be true):**
- [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
- [ ] PHASES.md updated with completed deliverables and implementation notes
- [ ] All quality gates pass
- [ ] Step B.5 completed (commit per project policy, or skip if policy says so)

If any item is unchecked, go back and complete it. Do NOT launch the next batch.

### Post-Phase Steps (after all batches in a phase)

#### Integration Verification (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/integration-verification.md`

#### Create/Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/claude-md-review.md`

#### Commit and Push Post-Phase Changes (use "Post-phase" message format)

!`cat .claude/skill-config/commit-policy.md 2>/dev/null || cat ~/.claude/skills/_components/commit-and-push.md`

---

## Blocking Issue Protocol

If a blocking issue is encountered at any point during execution:

1. **Stop all in-progress work.** Do not launch new subagents.
2. **Commit and push any completed phases** that haven't been committed yet.
3. **Print a blocking-issue report:**

   ## ⛔ Implementation Batch — Blocked

   **Completed phases:** [list with commit hashes]
   **Blocked phase:** [feature] Phase N: [title]
   **Reason:** [specific description]
   **Recovery suggestion:** [what the user should do]

   **Remaining phases (not attempted):**
   - [list]

4. **Do not attempt to work around the blocker.** The user provides a resolution and triggers autonomous implementation after.

Blocking issues include:
- Circular dependency in the phase graph
- A subagent failure that can't be fixed after 2 retry attempts
- A quality-gate failure that can't be fixed after 2 retry attempts
- A git push conflict that can't be resolved by rebase
- A phase whose entry criteria reference a feature/phase not in the input set
- Any error that would require architectural decisions beyond the scope of the specs

---

## Completion

When all phases in the Execution Schedule are complete:

1. **Run the full quality-gate suite one final time** across the entire codebase.
2. **Print a completion report:**

   ## ✅ Implementation Batch — Complete

   **Features implemented:** [list]
   **Total phases completed:** N
   **Total commits:** M
   **Final quality-gate status:** all green

   **Commit log:**
   | Commit | Feature | Phase | Title |
   |--------|---------|-------|-------|
   | abc1234 | foundation | P1 | Scaffold |
   | def5678 | auth-bootstrap | P1 | Keyring Wrapper |
   | ... | ... | ... | ... |

   **Implementation Notes summary:**
   [key cross-feature integration notes and pitfalls, collapsed into a brief reference for the next wave]
```

---

## Step 4: Present Plan for Approval

Present the completed plan and wait for user approval before exiting plan mode. This is the **only** approval gate.

**Remind the user:** "This plan is self-contained. After approval, I will execute it autonomously — committing after each phase, looping until all phases are complete or a blocking issue halts progress. No further approval will be requested."
