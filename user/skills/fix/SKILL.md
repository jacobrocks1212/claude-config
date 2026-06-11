---
description: Draft a TDD fix plan for a manually-reported bug using parallel Sonnet subagents
argument-hint: [bug description] [optional path/to/PHASES.md]
name: fix
plan-mode: never
---

# Fix

Draft a detailed TDD fix plan for a bug or issue discovered during manual testing — typically (but not always) after `/implement-phase`. The plan is written to a file for execution via `/execute-plan` in a separate session. The plan uses systematic debugging, TDD, and parallel Sonnet subagents, with all hard requirements encoded as explicit non-skippable steps in the plan itself.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. The deliverable is a written plan file, not a plan-mode interaction.

This skill may be invoked standalone (no associated PHASES.md). Handle both cases.

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation (typically from `/lazy-batch`). Strip `--batch` from `$ARGUMENTS` before processing.

- **Skip Step 1's clarifying `AskUserQuestion`.** If the bug report is so ambiguous that systematic debugging cannot identify a single hypothesis, halt with `NEEDS_INPUT.md` (see below) rather than guessing.
- **Skip Step 2's `AskUserQuestion` for logs/repro steps.** Proceed with code-level analysis only; add a top-level note in the fix plan: "Runtime evidence unavailable in this session — fix proposed at the code level. Re-run interactively with runtime data for higher confidence."

**Post-research positioning:** `/fix --batch` operates on already-implemented work where research, spec, and phases are all on disk. This skill is therefore eligible to write `NEEDS_INPUT.md` per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`. A genuinely ambiguous root cause that admits multiple defensible fixes (different blast radii, different invariants) is a real design choice the halting rule permits.

### Halt protocol — `NEEDS_INPUT.md`

When at least one decision is genuinely ambiguous (multiple defensible fixes, or unresolvable bug scope), write `{feature-dir}/NEEDS_INPUT.md` (or `{cwd}/NEEDS_INPUT.md` when standalone — no PHASES.md context) per `~/.claude/skills/_components/sentinel-frontmatter.md`. The body MUST use the **rich-body convention** — `## Decision Context` H2 with one H3 per `decisions[i]`, each carrying `**Problem:**` / `**Options:**` / `**Recommendation:**`. **Echo the entire section to chat output** before returning. STOP without writing the fix plan.

---

## Step 0: Task Tracking (MANDATORY — DO NOT SKIP)

Load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Understand the feedback", description: "Parse bug report, restate problem, resolve PHASES.md context" })`
2. `TaskCreate({ subject: "Systematic debugging", description: "Investigate root cause via subagents" })`
3. `TaskCreate({ subject: "Draft fix plan", description: "Generate TDD fix plan with work units and batches" })`
4. `TaskCreate({ subject: "Write plan file", description: "Write plan to feature/bug plans/ directory" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

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

Record the chosen category (and a one-sentence justification) — it drives the skill-suggestion step (Step 6a).

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

## Step 4: Draft the Fix Plan (TDD)

TDD enforcement is injected automatically via `subagent-launch.md` — every subagent inherits the TDD protocol.

### 5a. Partition Work

- Identify files that must change to fix the root cause
- Identify the regression test file(s) that will pin the bug
- Apply the partitioning protocol to divide work across subagents:

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

For a small single-file fix with a single concern, a single work unit in a single batch is the natural result of this protocol.

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

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

## EXECUTION MODEL — READ THIS FIRST

This plan uses an **orchestrator + Sonnet subagent** architecture:

| Role | What it does | Allowed tools |
|------|-------------|---------------|
| **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch subagents, review output, run quality gates, update tracking docs | `Agent`, `Read`, `Bash` (gates only), `TaskCreate`/`TaskUpdate` |
| **Sonnet subagent** | Write ALL source and test code | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob` |

**HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`.

**Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained context — subagent has zero prior context>" })`

Every "Launch Subagents" step below MUST be executed by composing Agent calls using this pattern.

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. **ALL implementation and test-writing work MUST be delegated to Sonnet subagents via the Agent tool** — the orchestrating session MUST NOT call `Edit` or `Write` on source or test files. The ONLY exception: trivial PASS-WITH-FIXES items (a few lines). If you are composing an `Edit` or `Write` call targeting a source/test file, STOP — compose an `Agent` tool call instead.
2. All subagent edits happen in the current worktree — NEVER create worktrees for subagents
3. Every TDD work unit goes through the test-first pipeline — dedicated test agent writes failing tests, dedicated implementation agent makes them pass
4. The regression test must fail for the documented root cause, not for an unrelated reason
5. PHASES.md (if applicable) is updated AFTER EACH batch completes (not deferred)
6. Every subagent's output is reviewed for correctness and root-cause alignment before continuing
7. Mistakes are fixed immediately before launching the next batch
8. After all agents finish, integration verification confirms the bug is gone and nothing else broke
9. Relevant CLAUDE.md files are updated if the fix establishes a new rule or gotcha
```

#### Work Unit Definitions

For each work unit, document:
- **Scope:** What part of the fix it covers
- **TDD:** yes/no (yes for any work unit with testable behavior or a reproducible root cause)
- **Files to create/modify:** Exact paths (implementation files)
- **Test files:** Exact paths for the regression test (TDD work units only)
- **Test expectations:** What the regression test asserts and why it fails today (TDD work units only)
- **Implementation goal:** What the fix must achieve to make tests pass and resolve the root cause
- **Root-cause link:** How this work unit addresses the root cause from Step 2
- **Batch:** Which parallel batch

Include a batch overview table if there are multiple units:

```
## Batch Overview

| Batch | Work Units | Parallel? | File Conflicts? |
|-------|-----------|-----------|-----------------|
| 1     | A         | Solo      | N/A             |
```

#### Step 0: Task Initialization (PREREQUISITE GATE)

This MUST be the first executable step in the plan — before any batch. Label it "Step 0" so it is unambiguously first:

```
## Step 0: Initialize Task Tracking (MANDATORY PREREQUISITE — EXECUTE BEFORE ANYTHING ELSE)

**This is the first thing you do when executing this plan. Do NOT skip ahead to Batch 1.**

!`cat ~/.claude/skills/_components/task-tracking.md`
```

#### Per-Batch Execution Steps

For each batch, include verbatim:

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

### Step N.3: Update PHASES.md (MANDATORY IF APPLICABLE — DO NOT SKIP)

!`cat ~/.claude/skills/_components/phases-update.md`

### Step N.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/quality-gates.md`

### Step N.4.5: MCP Integration Test (BLOCKING — execute Applicability Rule if fix touches runtime behavior)

!`cat ~/.claude/skills/_components/mcp/mcp-integration-test.md`

### Step N.5: Proceed to Next Batch

**Checklist before proceeding (all must be true):**
- [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
- [ ] Regression test passes
- [ ] PHASES.md updated (if applicable)
- [ ] All quality gates pass
- [ ] Step N.4.5 MCP integration test executed, OR explicitly skipped with documented reason

If any item is unchecked, go back and complete it. Do NOT launch the next batch.
```

#### Integration Verification Step

```
## Integration Verification (MANDATORY — DO NOT SKIP)

!`cat .claude/skill-config/integration-verification.md 2>/dev/null || cat ~/.claude/skills/_components/integration-verification.md`
```

#### CLAUDE.md Update Step

```
## Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/claude-md-review.md`
```

---

## Step 7: Write Plan File

!`cat ~/.claude/skills/_components/plan-file-output.md`

**Frontmatter for `/fix`:**
- `kind: fix-plan`
- `feature_id:` — parent feature directory name (or bug-directory slug for standalone fixes targeting `docs/bugs/<slug>/plans/`)
- `status: Ready`
- `phases:` — phase number(s) the fix attributes to, if applicable. Omit (`[]`) for standalone fixes with no PHASES.md context.
