# Execution Contract — single-source autonomous-execution policy

This component is the **one canonical home** for the execution policy that every generated plan
used to duplicate verbatim and that `/write-plan` used to re-emit into each plan body. A generated
plan carries a one-line pointer to this file; `/execute-plan` reads this file as its operating
contract. Edit the policy HERE — never re-inline it into a plan.

> **How this file is consumed**
> - **Generated plans** carry a single pointer line: *"Execution policy: follow `~/.claude/skills/_components/execution-contract.md` (read it before executing any batch)."* They do NOT inline the sections below.
> - **`/execute-plan`** reads this file (or `!cat`-includes it) as the authoritative execution policy, then layers its executor-specific logic (plan-status protocol, ground-truth verification gate, compaction recovery, PHASES.md slice reading) on top.
> - This file is `!cat`-includable and round-trips through `project-skills.py`.

---

## EXECUTION MODEL — READ THIS FIRST

This contract uses an **orchestrator + Sonnet subagent** architecture:

| Role | What it does | Allowed tools |
|------|-------------|---------------|
| **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch subagents, review output, run quality gates, update tracking docs | `Agent`, `Read`, `Bash` (gates only), `TaskCreate`/`TaskUpdate` |
| **Sonnet subagent** | Write ALL source and test code | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob` |

**HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, the plan file's frontmatter status field, and task tracking.

**Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained context — subagent has zero prior context>" })`

## COMPONENT LOADING PROTOCOL

This contract and the plan it governs reference reusable component files by path instead of inlining their content. **Before executing each step**, `Read` the component files listed for that step from disk. Do NOT proceed from memory of their contents — always load fresh. After context compaction, re-read the plan file first, then this contract, then load components for your current step.

## Component Reference Card

| Step | Component | Path |
|------|-----------|------|
| Step 0 | Task Tracking | `~/.claude/skills/_components/task-tracking.md` |
| Step B.0 | Source Re-read | `~/.claude/skills/_components/source-reread.md` |
| Step B.1 | TDD Protocol | `~/.claude/skills/_components/tdd-protocol.md` |
| Step B.1 | Subagent Launch | `~/.claude/skills/_components/subagent-launch.md` |
| Step B.1 | Test Agent Briefing | `~/.claude/skills/_components/tdd-test-agent.md` |
| Step B.1 | Impl Agent Briefing | `~/.claude/skills/_components/implementation-agent.md` |
| Step B.2 | Subagent Review | `~/.claude/skills/_components/subagent-review.md` |
| Step B.2 | Mount-Site Verification | `~/.claude/skills/_components/mount-site-verification.md` |
| Step B.3 | PHASES.md Update | `~/.claude/skills/_components/phases-update.md` |
| Step B.4 | Quality Gates | `~/.claude/skills/_components/quality-gates.md` |
| Step B.4.5 | MCP Integration Test | `~/.claude/skills/_components/mcp/mcp-integration-test.md` |
| Step B.5 | Commit Policy | `.claude/skill-config/commit-policy.md` (fallback: `~/.claude/skills/_components/commit-and-push.md`) |
| Post-phase | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
| Post-phase | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |

> A plan MAY override or extend rows of this card in its own `## Component Reference Card` when its repo uses non-default paths (e.g. harness-config plans whose gates are Python/projection rather than `/msbuild`/`/mstest`). Where a plan is silent, this card governs.

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. **ALL implementation and test-writing work MUST be delegated to Sonnet subagents via the Agent tool** — the orchestrating session MUST NOT call `Edit` or `Write` on source or test files. The ONLY exception: trivial PASS-WITH-FIXES items (a few lines).
2. All subagent edits happen in the current worktree — NEVER create worktrees for subagents.
3. Every TDD work unit goes through the test-first pipeline — dedicated test agent writes failing tests, dedicated implementation agent makes them pass.
4. PHASES.md is updated AFTER EACH batch completes (not deferred).
5. Every subagent's output is reviewed for correctness, spec alignment, and TDD discipline before continuing.
6. Mistakes are fixed immediately before launching the next batch.
7. After all batches in a phase finish, integration verification confirms all changes work together.
8. Relevant CLAUDE.md files are created/updated after each phase if changes warrant it.
9. Each completed phase is committed (and pushed where policy allows) before the next phase begins.
10. Cross-feature phases may run in parallel when dependencies are satisfied and no file conflicts exist.
11. The plan is self-contained — follow it exactly as written without relying on external context.
12. **Before each step, `Read` the component files listed for that step from disk** — do NOT rely on memory.

---

## Execution Protocol

This protocol governs the autonomous execution of every phase. Follow it exactly.

### Phase Selection Loop

Repeat until all phases in the Execution Schedule are complete or a blocking issue triggers early exit:

1. **Select ready phase(s):** Identify phase(s) whose entry criteria are satisfied (prerequisite phases complete — all deliverables checked off in their PHASES.md). If multiple phases from different features are ready and marked parallel-eligible in the schedule, execute them concurrently. If no phases are ready, jump to Blocking Issue Protocol.
2. **Announce:** Print "Implementing [feature] Phase N: [title]".
3. **Review prior context:** Re-read all previously completed phases' Implementation Notes. Apply the sibling-then-embedded read order: check `IMPLEMENTATION_NOTES.md` (sibling to PHASES.md) first; fall back to embedded notes in PHASES.md for in-flight features predating the D3 writer flip. These contain imports, patterns, gotchas, and actual file paths that may differ from the original plan. They take priority over the plan where they diverge.
4. **Execute all batches** per the Per-Batch Steps below.
5. **Run Post-Phase Steps** below.
6. **Report:** Print "[feature] Phase N: [title] — committed as [hash]".
7. **Loop:** Re-evaluate which phases are now ready (completing one phase may unblock others). Return to step 1.

### Step 0: Initialize Task Tracking (MANDATORY PREREQUISITE — EXECUTE BEFORE ANYTHING ELSE)

**This is the first thing you do when executing a plan. Do NOT skip ahead to any phase or batch.**

Read `~/.claude/skills/_components/task-tracking.md` and follow its instructions exactly.
It defines: task tool loading via ToolSearch, task creation for all work units, and the update protocol for tracking progress through test and implementation phases.

### Per-Batch Steps

For each batch within a phase:

#### Step B.0: Re-read Source Documents (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/source-reread.md` and follow its instructions.
Re-read from disk: PHASES.md (current phase + prior Implementation Notes), SPEC.md (relevant sections), and the plan file itself. Do NOT rely on cached/remembered content.

#### Step B.1: Launch Subagents (COMPOSE Agent TOOL CALLS — ZERO INLINE IMPLEMENTATION)

**PRE-FLIGHT CHECK:** You are about to dispatch work to Sonnet subagents. Confirm: (1) you will use the `Agent` tool with `model: "sonnet"` for ALL code changes in this step, (2) you will NOT call `Edit` or `Write` on any source or test file. If either is false, re-read the EXECUTION MODEL section above.

Read ALL of these before proceeding:
1. `~/.claude/skills/_components/tdd-protocol.md` — TDD decision gate: determines which WUs get test-first pipeline vs. direct implementation.
2. `~/.claude/skills/_components/subagent-launch.md` — Launch orchestration: Phase A (test agents), Phase B (impl agents), failed agent recovery protocol.
3. `~/.claude/skills/_components/tdd-test-agent.md` — Test agent prompt template: include this briefing verbatim in every test agent's prompt.
4. `~/.claude/skills/_components/implementation-agent.md` — Impl agent prompt template: include this briefing verbatim in every impl agent's prompt.

Note: `subagent-launch.md` references the other components above via internal directives — since you've already read them, ignore those directives in the file.

**POST-DISPATCH GATE:** After all subagents complete, verify you composed `Agent` tool calls and did NOT edit source/test files directly. If you violated this, revert inline edits and re-dispatch via Agent.

#### Step B.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step B.3 until the review protocol is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

Read `~/.claude/skills/_components/subagent-review.md` and follow its complete protocol.
Also read `~/.claude/skills/_components/mount-site-verification.md` (referenced within subagent-review for new-file checks).
Protocol covers: batch scope measurement, review execution (inline or via subagent), propagation check, mount-site verification, and verdict handling (PASS / PASS-WITH-FIXES / NEEDS-REWORK).

#### Step B.3: Update PHASES.md (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/phases-update.md` and follow its instructions.
Check off completed deliverables, add Implementation Notes block with date, work completed, integration notes, pitfalls, and files modified.

#### Step B.4: Run Quality Gates (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/quality-gates.md` and follow its instructions.
Run project quality gates. If the batch introduced import indirection, field additions, alias changes, or re-exports — run the FULL suite. 100% pass required before proceeding.

> See **Per-WU verification gate** below for how a plan may declare a tighter per-work-unit gate that this step must honor.

#### Step B.4.5: MCP Integration Test (BLOCKING — if applicable)

Read `~/.claude/skills/_components/mcp/mcp-integration-test.md` to determine applicability.
If the phase's PHASES.md has an `MCP Integration Test Assertions` block OR the phase produces runtime-observable changes, this is MANDATORY. Otherwise skip with a note.

#### Step B.5: Commit Batch

Read the commit policy: first try `.claude/skill-config/commit-policy.md` in the project root. If it doesn't exist, read `~/.claude/skills/_components/commit-and-push.md` instead. Follow whichever policy applies.

#### Step B.6: Proceed to Next Batch

**Checklist before proceeding (all must be true):**
- [ ] Review report produced with PASS/PASS-WITH-FIXES/NEEDS-REWORK verdict
- [ ] PHASES.md updated with completed deliverables and implementation notes
- [ ] All quality gates pass
- [ ] Step B.5 completed (commit per project policy, or skip if policy says so)

If any item is unchecked, go back and complete it. Do NOT launch the next batch.

### Parallelism & background builds

> **Anticipated home for the D4 parallelism / background-build rules (added in a later phase of plan-skills-redesign).** Until those rules land, the baseline parallelism policy is:
>
> - Cross-feature phases may run in parallel only when dependencies are satisfied and no file conflicts exist (MANDATORY RULE 10).
> - Within a phase, batches are sequential; work units within a batch run in parallel only when the plan's batch table marks them file-disjoint.
> - Background-build and long-gate orchestration guidance will be specified here.

### Per-WU verification gate

> **Anticipated home for the D5 per-work-unit gate rules (added in a later phase of plan-skills-redesign).** Until those rules land, the baseline is the per-batch Quality Gates step (Step B.4) plus the per-WU plan checkbox discipline in the Completion section. The per-WU gate granularity — exactly which gate must pass before a single WU's checkbox may be ticked — will be specified here.

### Propagation Awareness Note

When drafting work units, identify any that introduce import indirection (wrappers, proxies, facades) or add fields to widely-constructed structs/interfaces. For these work units, the plan MUST include:
- A "propagation step" ensuring all consumers are migrated in the same batch.
- A vitest/jest alias addition if the new module wraps a mocked dependency.
- A note in the QG step to run the full suite (not just the affected language).

### Post-Phase Steps (after all batches in a phase)

#### Integration Verification (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/integration-verification.md` and follow its complete protocol.
Covers: cross-agent integration, spec alignment, and full-stack coverage for user-facing APIs.

#### Update CLAUDE.md Files (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/claude-md-review.md` and follow its instructions.
Review whether project root or subdirectory CLAUDE.md files need updates based on this phase's changes.

#### Commit and Push Post-Phase Changes

Read the commit policy: first try `.claude/skill-config/commit-policy.md` in the project root. If it doesn't exist, read `~/.claude/skills/_components/commit-and-push.md` instead. Follow whichever policy applies.

---

## Blocking Issue Protocol

If a blocking issue is encountered at any point during execution:

1. **Stop all in-progress work.** Do not launch new subagents.
2. **Commit and push any completed phases** that haven't been committed yet.
3. **Print a blocking-issue report:**

   ## Implementation Batch — Blocked

   **Completed phases:** [list with commit hashes]
   **Blocked phase:** [feature] Phase N: [title]
   **Reason:** [specific description]
   **Recovery suggestion:** [what the user should do]

   **Remaining phases (not attempted):**
   - [list]

4. **Do not attempt to work around the blocker.** The user provides a resolution and triggers autonomous implementation after.

Blocking issues include:
- Circular dependency in the phase graph.
- A subagent failure that can't be fixed after 2 retry attempts.
- A quality-gate failure that can't be fixed after 2 retry attempts.
- A git push conflict that can't be resolved by rebase.
- A phase whose entry criteria reference a feature/phase not in the input set.
- Any error that would require architectural decisions beyond the scope of the specs.

---

## Completion

When all phases in the Execution Schedule are complete:

1. **Run the full quality-gate suite one final time** across the entire codebase.
2. **Print a completion report:**

   ## Implementation Batch — Complete

   **Features implemented:** [list]
   **Total phases completed:** N
   **Total commits:** M
   **Final quality-gate status:** all green

   **Commit log:**
   | Commit | Feature | Phase | Title |
   |--------|---------|-------|-------|
   | abc1234 | foundation | P1 | Scaffold |
   | def5678 | auth-bootstrap | P1 | Keyring Wrapper |

   **Implementation Notes summary:**
   [key cross-feature integration notes and pitfalls, collapsed into a brief reference for the next wave]

---

## Work Log

Record execution in the work log when the run produces meaningful engineering output (per the project's work-logging policy). Skip for trivial edits, config tweaks, or exploratory runs that produce no artifacts.
