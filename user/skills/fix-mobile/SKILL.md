---
description: Draft a TDD fix plan for a manually-reported bug using parallel Sonnet subagents (mobile workflow — writes plan to file)
argument-hint: [bug description] [optional path/to/PHASES.md]
name: fix-mobile
plan-mode: never
---

# Fix (Mobile)

Draft a detailed fix plan for a bug or issue discovered during manual testing — typically (but not always) after `/implement-phase`. The plan uses systematic debugging, TDD, and parallel Sonnet subagents, with all hard requirements encoded as explicit non-skippable steps in the plan itself.

**Mobile variant:** Identical to `/fix` except the plan is written to a file (colocated with the feature's PHASES.md, or in `docs/plans/` for standalone fixes) instead of entering plan mode. This enables remote mobile workflow where plans are generated and then executed in separate sessions.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode` under any circumstances. Do NOT present the plan for interactive approval. The deliverable of this skill is a written PLAN.md file, not a plan-mode interaction. If you feel the urge to enter plan mode, re-read this paragraph.

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

Record the chosen category (and a one-sentence justification) — it drives Step 5 and the persistent log (Step 5c).

---

## Step 3: Load Phase Context (If Applicable)

### 3a. Resolve PHASES.md (optional)

- If `$ARGUMENTS` references a PHASES.md path, use it
- Else if the current/recent session context clearly ties to a PHASES.md file, use that
- Else if the bug is standalone with no PHASES.md context, **skip this step entirely** and note "No PHASES.md — standalone fix"
- If ambiguous, use **AskUserQuestion**

### 3b. Read PHASES.md and SPEC.md (if resolved)

- Read PHASES.md in full. For Implementation Notes, apply the sibling-then-embedded read order: check for a sibling `IMPLEMENTATION_NOTES.md` first; fall back to embedded notes in PHASES.md. See `~/.claude/skills/_components/implementation-notes-read-order.md`.
- Read sibling SPEC.md — the correctness source of truth
- Identify which phase(s) introduced the buggy behavior — the fix's Implementation Notes will be appended there

---

## Step 4: Draft the Fix Plan (TDD)

TDD enforcement is injected automatically via `subagent-launch.md` — every subagent inherits the TDD protocol.

### 4a. Partition Work

- Identify files that must change to fix the root cause
- Identify the regression test file(s) that will pin the bug
- Apply the partitioning protocol to divide work across subagents:

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

For a small single-file fix with a single concern, a single work unit in a single batch is the natural result of this protocol.

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

### 4b. Write the Plan

The plan MUST contain all of the following sections as explicit, non-skippable steps. Use imperative language.

---

#### Header

```
# Fix: [Short Bug Title] — Implementation Plan

**Bug report:** [one-line summary of user's feedback]
**Root cause:** [one or two sentences]
**Failure mode:** [category from Step 2c] — [one-sentence justification]
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

#### Component Reference Card

```
## Component Reference Card

| Step | Component | Path |
|------|-----------|------|
| Step 0 | Task Tracking | `~/.claude/skills/_components/task-tracking.md` |
| Step N.0 | Source Re-read | `~/.claude/skills/_components/source-reread.md` |
| Step N.1 | TDD Protocol | `~/.claude/skills/_components/tdd-protocol.md` |
| Step N.1 | Subagent Launch | `~/.claude/skills/_components/subagent-launch.md` |
| Step N.1 | Test Agent Briefing | `~/.claude/skills/_components/tdd-test-agent.md` |
| Step N.1 | Impl Agent Briefing | `~/.claude/skills/_components/implementation-agent.md` |
| Step N.2 | Subagent Review | `~/.claude/skills/_components/subagent-review.md` |
| Step N.2 | Mount-Site Verification | `~/.claude/skills/_components/mount-site-verification.md` |
| Step N.3 | PHASES.md Update | `~/.claude/skills/_components/phases-update.md` |
| Step N.4 | Quality Gates | `~/.claude/skills/_components/quality-gates.md` |
| Step N.4.5 | MCP Integration Test | `~/.claude/skills/_components/mcp/mcp-integration-test.md` |
| Step N.5 | Commit Policy | `.claude/skill-config/commit-policy.md` (fallback: `~/.claude/skills/_components/commit-and-push.md`) |
| Post-fix | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
| Post-fix | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |
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

Read `~/.claude/skills/_components/task-tracking.md` and follow its instructions exactly.
```

#### Per-Batch Execution Steps

For each batch, include verbatim:

```
## Batch N

### Step N.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/source-reread.md` and follow its instructions.

### Step N.1: Launch Subagents (COMPOSE Agent TOOL CALLS — ZERO INLINE IMPLEMENTATION)

**PRE-FLIGHT CHECK:** You are about to dispatch work to Sonnet subagents. Confirm: (1) you will use the `Agent` tool with `model: "sonnet"` for ALL code changes in this step, (2) you will NOT call `Edit` or `Write` on any source or test file. If either is false, re-read the EXECUTION MODEL section above before proceeding.

Read ALL of these before proceeding:
1. `~/.claude/skills/_components/tdd-protocol.md`
2. `~/.claude/skills/_components/subagent-launch.md`
3. `~/.claude/skills/_components/tdd-test-agent.md`
4. `~/.claude/skills/_components/implementation-agent.md`

**POST-DISPATCH GATE:** After all subagents in this step complete, verify you composed `Agent` tool calls and did NOT edit source/test files directly. If you violated this constraint, revert your inline edits and re-dispatch via Agent before proceeding to the review step.

### Step N.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step N.3 until the review protocol below is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

Read `~/.claude/skills/_components/subagent-review.md` and follow its complete protocol.
Also read `~/.claude/skills/_components/mount-site-verification.md`.

### Step N.3: Update PHASES.md (MANDATORY IF APPLICABLE — DO NOT SKIP)

Read `~/.claude/skills/_components/phases-update.md` and follow its instructions.

### Step N.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/quality-gates.md` and follow its instructions.

### Step N.4.5: MCP Integration Test (BLOCKING — execute Applicability Rule if fix touches runtime behavior)

Read `~/.claude/skills/_components/mcp/mcp-integration-test.md` to determine applicability.

### Step N.5: Commit Batch

Read the commit policy: first try `.claude/skill-config/commit-policy.md` in the project root. If it doesn't exist, read `~/.claude/skills/_components/commit-and-push.md` instead.

### Step N.6: Proceed to Next Batch

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

Read `~/.claude/skills/_components/integration-verification.md` and follow its complete protocol.
```

#### CLAUDE.md Update Step

```
## Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/claude-md-review.md` and follow its instructions.
```

#### Commit and Push

```
## Commit and Push

Read the commit policy: first try `.claude/skill-config/commit-policy.md` in the project root. If it doesn't exist, read `~/.claude/skills/_components/commit-and-push.md` instead.
```

---

## Step 5: Write Plan to File (MANDATORY)

!`cat ~/.claude/skills/_components/plan-file-output.md`

**Frontmatter for `/fix-mobile`:**
- `kind: fix-plan`
- `feature_id:` — parent feature directory name (or bug-directory slug for standalone fixes)
- `status: Ready`
- `phases:` — phase number(s) the fix attributes to, if applicable. Omit (`[]`) for standalone fixes.
