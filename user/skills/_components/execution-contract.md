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

**HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, `CLAUDE.local.md`, the plan file's frontmatter status field, and task tracking.

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
13. **No turn ends on in-flight work.** A backgrounded gate/build/commit job, an un-consumed inner-agent dispatch, or a bare queue enqueue is NOT an outcome — drive it to a terminal result first (see the Turn-end gate under "Parallelism & background builds").

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

The harness runs `Agent` dispatches concurrently **only when they appear in a single assistant message**. Successive single-agent dispatches across separate turns are serial (the 15–20-min-gap failure mode). This is the only real-parallelism path; the rules below exploit it without unbounded fan-out.

#### Same-message file-disjoint batching (MANDATORY)

- **When a batch's work units are provably file-disjoint, dispatch them as multiple `Agent` blocks in ONE assistant message** — not one per turn. "Provably disjoint" means the plan's batch table marks the work units parallel AND no two of them list any shared file in their `Files to create/modify`. The existing file-overlap rule (work units in the same batch must not share files) already guarantees disjoint-WU safety; you do not add a new check — you act on the disjointness the plan already encoded.
- **Seam classification gates what is disjoint.** A plan may mark a batch `Sequenced` (e.g. backend → typegen → frontend) precisely because its lanes are *not* independent; never collapse a Sequenced batch into one message. Only `Parallel`-classified / file-disjoint batches are dispatched together.
- **If the plan's batch table does not assert disjointness, do not infer it** — dispatch sequentially. Disjointness is a plan-author claim you exploit, not one you manufacture at execution time.

#### Background builds (MANDATORY)

- **Long / Tier-2 / typegen builds run `run_in_background: true`** from the orchestrator session; while the build runs, dispatch the next independent agent (or the next disjoint batch) rather than blocking the turn on the build. Follow the build to its authoritative result afterward (for the queue skills: `powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-await.ps1" -Seq <N>` — it blocks until the `RESULT=` banner and exits with the build's own exit code; its exit `124` means the run is still going, NEVER success. `seq` is printed in the `build-queue: enqueued as seq=N` line. Do NOT hand-read `results/<seq>.json` — the await helper is the sanctioned reader).
- **The long-build signature set (settles OQ4 against the queue skills `/msbuild` `/nxbuild` `/mstest` `/nxtest`):**
  - **Background these (Tier-2 / typegen / long):** full-solution `/msbuild` (no `-Project` — this is also the authoritative server-typegen trigger), `/msbuild -Test`, the typegen step's `Cognito.Services` build, `/nxbuild -All`, and any Nx library build that fans out through the model.js → vuemodel → element-ui dependency chain. These are exactly the builds the `/msbuild` and `/nxbuild` skills themselves flag with "if the build is expected to exceed 10 minutes, run with `run_in_background: true`."
  - **Do NOT background these (fast, in-loop):** single-project `/msbuild -Project "<csproj>"`, targeted `/nxbuild -Project "<one project>"`, and `--no-build` filtered tests (`/mstest -Filter …`, `/nxtest … -NoCoverage`). They return in seconds-to-a-minute; backgrounding them just adds polling overhead.
- **Builds remain a serial spine through the queue.** Backgrounding does not parallelize builds against each other — the build-queue still serializes them machine-wide. What overlaps is *agent think/edit/test-author time* with the build's wall-clock. The aim is **~1.5–2× wall-clock per phase, not unbounded fan-out** — do not dispatch more concurrent agents than the disjoint-file set supports.

#### Constraint guard (MANDATORY)

A backgrounded build's output must **never** be consumed by a dependent agent before that build completes. This is enforced by the **disjoint-file + seam-classification rules already in force** — not by new queue machinery: an agent dispatched alongside a backgrounded build must be file-disjoint from (and seam-independent of) whatever that build verifies. If the next unit of work depends on the build's output (e.g. a frontend lane consuming freshly regenerated types), it is Sequenced by definition — block on the build's `exit_code` and review its output before dispatching that dependent agent.

- Cross-feature phases may run in parallel only when dependencies are satisfied and no file conflicts exist (MANDATORY RULE 10).
- Within a phase, batches are sequential; work units within a batch run in parallel (same-message) only when the plan's batch table marks them file-disjoint per the rules above.

#### Turn-end gate (MANDATORY — RULE 13's policy home; binds you AND every agent you dispatch)

Backgrounding buys wall-clock overlap WITHIN your turn — it never licenses ending the turn with the job (or an inner agent) still in flight. The canonical statement:

!`cat ~/.claude/skills/_components/turn-end-gate.md`

### Per-WU verification gate

The per-WU ground-truth gate (`subagent-review.md` Step 1.5) historically re-ran the **full test suite** for every work unit — a 0/16 defect-catch rate across the mined corpus, pure cost. The default is now **cheap**; the full-suite re-run is **conditional**.

#### Default per WU — cheap integrity checks + the assertion-vs-intent read (MANDATORY)

For each work unit, the per-WU verification is:

1. **Cheap integrity checks** — `git status --short`, `wc -l <file>` for every file the subagent listed, and `grep -n '<symbol>' <file>` for every new symbol. Re-run from the orchestrator's shell and diff against the subagent's `GROUND-TRUTH OUTPUT` block. These are seconds-cheap and catch a falsified file/LOC/symbol report.
2. **Dirty-tree assertion against the WU's declared files (MANDATORY, independent of the subagent's report)** — self-report-vs-fresh-run parity (item 1) only proves the two readings agree with each other; it is blind to a tree silently reverted (e.g. an un-popped `git stash`) BEFORE either reading was taken, since both readings then agree on the same wrong (clean) ground truth. Close that gap: for every file on this WU's plan-declared `Files to create/modify:` list (or the subagent's prose `Files created\modified:` line), confirm it shows as a change in the fresh `git status --short`, or is present in the WU's own commit (`git show --stat HEAD -- <file>`). A declared file that is clean in both is an automatic fail — regardless of self-report agreement. Full mechanics + the exact failure mode this closes: `~/.claude/skills/_components/subagent-review.md` Step 1.5 item 2.
3. **The assertion-vs-intent read** — read each test's assertion against the behavior its name/description claims (a green `..._ReturnsTrue` test that actually asserts `False`/`Unknown` is defective). **This stays MANDATORY** — it is the *only* mechanism that caught the single real defect in the corpus, and ground-truth diffing cannot catch it (the test genuinely passes). Never drop it to make the gate cheaper.

These three together are the default gate. **Do NOT re-run the test suite by default.**

#### Conditional full-suite re-run — only on integrity mismatch

Re-run the test suite for a work unit **only when a cheap integrity check disagrees** with the subagent's report — a `wc -l`/`grep -n`/`git status` mismatch, a missing `GROUND-TRUTH OUTPUT` block, a WU-declared file that fails the item 2 dirty-tree assertion, or an "already complete" claim contradicted by `git log`. A clean integrity check + a clean dirty-tree assertion + a clean assertion-vs-intent read is sufficient to tick the WU checkbox. (The per-batch Quality Gates step — Step B.4 — still runs the project's gate at batch granularity, and the full suite still runs whenever a batch trips a propagation trigger; this section governs the *per-WU* granularity only.)

### Propagation Awareness Note

When drafting work units, identify any that introduce import indirection (wrappers, proxies, facades) or add fields to widely-constructed structs/interfaces. For these work units, the plan MUST include:
- A "propagation step" ensuring all consumers are migrated in the same batch.
- A vitest/jest alias addition if the new module wraps a mocked dependency.
- A note in the QG step to run the full suite (not just the affected language).

### Post-Phase Steps (after all batches in a phase)

#### Integration Verification (MANDATORY — DO NOT SKIP)

Read `~/.claude/skills/_components/integration-verification.md` and follow its complete protocol.
Covers: cross-agent integration, spec alignment, and full-stack coverage for user-facing APIs.

#### Update CLAUDE.md Files (rare — only durable structural knowledge)

Read `~/.claude/skills/_components/claude-md-review.md` and follow its instructions.
Most phases warrant no update; write one only when durable structural knowledge changed and it passes the component's bar.

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
