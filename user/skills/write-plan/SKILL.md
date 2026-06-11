---
description: Generate an implementation plan for ALL phases across 1+ PHASES.md files — optimized for mobile/async workflow (reference-based components)
argument-hint: <path/to/PHASES1.md> [path/to/PHASES2.md] [...]
name: write-plan
plan-mode: never
---

# Write Plan

Plan (once) and then continuously implement all phases from one or more PHASES.md files using TDD and parallel Sonnet subagents until all phases are complete or a blocking issue forces early exit.

**Mobile variant:** Identical to `/implement-phase-batch` except the plan is written to a file (colocated with the feature's PHASES.md) instead of entering plan mode. This enables remote mobile workflow where plans are generated and then executed in separate sessions.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode` under any circumstances. Do NOT present the plan for interactive approval. The deliverable of this skill is a written PLAN.md file, not a plan-mode interaction. If you feel the urge to enter plan mode, re-read this paragraph.

**Flow:** Load context -> draft ONE self-contained plan covering all phases -> write plan to file -> report path to user.

**Critical: the plan must be fully self-contained.** The plan may be executed after the context window is cleared. Every execution instruction, loop control, blocking-issue protocol, and completion step MUST be baked into the generated plan itself — not left in this skill file. After the plan is written, it is the sole source of truth.

Execution-time components (review protocol, launch protocol, quality gates, etc.) are referenced by file path in the generated plan instead of inlined. The executing session reads them on demand from disk, reducing plan size and improving post-compaction recovery.

**Key differences from `/implement-phase`:**
- Takes 1+ PHASES.md paths (not just one); covers ALL phases across all of them in a single plan
- Commits and pushes after each completed phase (docs updated + QGs green)
- Cross-feature parallelism: phases from different features run concurrently when dependencies are satisfied and no file conflicts exist
- Early exit on blocking issues with a clear status report

All other constraints from `/implement-phase` carry over: TDD, Sonnet subagents, mandatory review, mandatory PHASES.md updates, mandatory QG pass, mandatory integration verification, mandatory CLAUDE.md review.

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation (typically from `/lazy-batch` via `/plan-feature`). Strip `--batch` from `$ARGUMENTS` before resolving PHASES.md paths.

- **Skip the Step 1a `AskUserQuestion`** that prompts for PHASES.md paths — refuse cleanly with an error if no paths are supplied, since guessing the wrong feature would explode work.
- For genuine ambiguity during plan drafting (e.g., a phase's deliverables admit two materially different decompositions — partition along feature boundaries vs. across them), write `NEEDS_INPUT.md` and halt rather than picking arbitrarily.

**Post-research positioning:** `/write-plan --batch` runs *after* `/spec-phases` has succeeded, which only happens after `/spec` Phase 3 finalized SPEC.md — research is on disk by definition. This skill is therefore eligible to write `NEEDS_INPUT.md` per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`. Operational/mechanical choices (file paths, naming, partition cutoffs) MUST be auto-accepted; only genuine design forks halt.

### Halt protocol — `NEEDS_INPUT.md`

Compute `{feature-dir}/NEEDS_INPUT.md` (parent of the first PHASES.md passed as `$ARGUMENTS`). Write per `~/.claude/skills/_components/sentinel-frontmatter.md` using the **rich-body convention** — one H3 `## Decision Context` subsection per decision, each carrying `**Problem:**` / `**Options:**` / `**Recommendation:**`. The orchestrator re-prints this body to chat before calling `AskUserQuestion`.

```yaml
---
kind: needs-input
feature_id: <feature-dir name>
written_by: write-plan
decisions:
  - <one-line decision title>
date: <today>
next_skill: write-plan
partial_artifacts: [<paths to any half-finished plan files>, ...]
---
```

**Echo the entire `## Decision Context` section to chat output** before returning. STOP without writing the plan file (or, if a partial plan file is unavoidable, list it under `partial_artifacts:` so the human can discard it).

Plan-file frontmatter under a halt: set `status: Draft` (not `Ready`) on any partial plan files so downstream consumers don't pick them up. The standard path uses `status: Ready` — see Step 4 below.

---

## Step 1: Load All Context

!`cat .claude/skill-config/cog-doc-track-open.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-open.md`

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

### 1b.1. Load Upstream Plan References (per hard dep on Complete upstream)

For each input PHASES.md, read the sibling SPEC.md's `**Depends on:**` block to find prior plans that the new plan should reference.

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Procedure:

1. Parse the SPEC's `**Depends on:**` block. Filter to `kind == hard`.
2. For each hard dep, resolve the upstream directory and apply the completion check.
3. For each completed hard upstream:
   - Glob `<upstream-dir>/plans/*.md`. Skip `retro-*.md` unless the filename suggests it captured an architectural fix this plan must inherit.
   - Read selectively — only plans whose title or first heading touches a domain that this plan's work units will modify (contracts, paths, schemas, mount points). Do NOT read every plan in every upstream; that explodes context.
   - Record the absolute paths of plans you read; they go into the generated plan's `## References` section so the executing session can re-load them after compaction.
4. If a hard upstream is Complete but has no `plans/` directory (older feature), note it; record only its PHASES.md path in References.

If the block is missing, malformed, or all hard deps are incomplete, skip this step. Do NOT abort.

### 1c. Build the Cross-Feature Phase Queue

Scan all loaded PHASES.md files. For each phase with unchecked deliverables (`- [ ]`):
1. Record its feature, phase number, title, entry criteria, and files it will create/modify
2. Parse entry criteria for cross-feature dependencies (e.g. "Foundation Phase 1 complete")
3. Parse entry criteria for intra-feature dependencies (e.g. "Phase 2 complete")

Build a directed acyclic graph of all pending phases. The execution order respects this graph — a phase only becomes "ready" when all its entry criteria are satisfied.

### 1c.5. Do NOT author the live MCP-validation gate as a blocking plan work unit (HARD)

The pipeline has a **dedicated runtime-validation step** — `/lazy-batch` Step 9 (`/mcp-test`), which boots the Tauri runtime, runs the MCP scenarios, and writes the `VALIDATED.md` sentinel that gates feature completion. That step OWNS live runtime validation. The plan you author here is consumed by `/execute-plan`, which performs **implementation** and flips the plan-part frontmatter `status:` to `Complete` when its work units are done.

Therefore, when building the WU list:

- **Do NOT emit a terminal plan WU of the form "re-run `/mcp-test` and earn `VALIDATED.md`" (or "run the runtime validation", "live-validate on device", etc.).** Such a WU can only be closed by the Step 9 runtime pass, NOT by `/execute-plan` — so `/execute-plan` correctly leaves the plan `status: In-progress`, and `lazy-state.py` then routes straight back to `/execute-plan` on the same plan, **looping**. The dedicated Step 9 already does this work; duplicating it as a plan WU is the cause of the loop, not a safeguard.
- **Runtime-observable verification still belongs in PHASES.md** — author it as a **non-blocking runtime-verification row** under a recognized `**Runtime Verification**` / `**MCP Integration Test Assertions:**` subsection (the bold-marker or `### Runtime Verification` heading formats both work). `lazy-state.py`'s `remaining_unchecked_are_verification_only()` recognizes these rows and routes a phase whose ONLY remaining unchecked rows are verification rows forward to the retro→MCP gate (Step 8→9) instead of looping on `write-plan`/`execute-plan`. These rows are ticked by the Step 9 `/mcp-test` pass, not by `/execute-plan`.

  > **PLACEMENT RULE (enforced by state-script heuristic):** Runtime-verification / MCP-assertion `- [ ]` checkboxes MUST live under the `## Runtime Verification` section (or the `**Runtime Verification**` / `**MCP Integration Test Assertions:**` bold-marker subsection). They MUST **never** appear under a phase's `### Deliverables` list. A verification checkbox mistakenly placed under `### Deliverables` is classified as an outstanding implementation item, causing spurious write-plan/execute-plan churn. See `~/.claude/skills/_components/phases-runtime-verification.md` for the full placement rule and rationale.
  >
  > **GATE-OWNED ROW BAN (same component, sibling rule):** pipeline-owned actions — SPEC.md/PHASES.md top-level `**Status:**` flips, COMPLETED.md/FIXED.md receipt writes, ROADMAP completion marks, archive moves — are NEVER authored as `- [ ]` rows anywhere (not even under Runtime Verification); they are `__mark_complete__`/`__mark_fixed__`-gate-owned and a checkbox for them loops the state machine. **When consuming an existing PHASES.md into the plan, SKIP/flag any such gate-owned row you encounter rather than planning a work unit for it** — it is not work `/execute-plan` can close (a gate-owned row that survived authoring is a PHASES quality issue; surface it in the final report, do not emit a WU). See `~/.claude/skills/_components/phases-runtime-verification.md`.
- **Net rule:** a plan WU must be something `/execute-plan` can actually DO and CLOSE in-session (write code, write tests, run quality gates, commit). Anything that can only be closed by booting the live runtime is a Step-9 responsibility — keep it OUT of the plan's WU list, and let the PHASES.md runtime-verification subsection carry the deferred verification intent.

---

## Step 2: Dirty Tree Check (MANDATORY — BEFORE DRAFTING PLAN)

!`cat .claude/skill-config/dirty-tree-check.md 2>/dev/null || cat ~/.claude/skills/_components/dirty-tree-check.md`

---

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

---

## Step 2.5: Partition the Plan by Work-Unit Cap (MANDATORY — BEFORE DRAFTING)

**Hard cap:** a single generated plan file may contain at most **8 work units**. If the queue analysis from Step 1c would produce more than 8 WUs across all input PHASES.md, this skill MUST partition the output into N sequential plan files, each ≤ 8 WUs.

**Minimize N. Pack multiple phases into one part whenever it's legal.** A part covering two or three phases is the EXPECTED shape when individual phases are small (≤ 4 WUs each) — `phases: [3, 4]` is normal output, not an exception. One-phase-per-part is correct ONLY when that one phase already saturates the cap (or near-saturates: ≥ 5 WUs with no legal neighbor to pack). Producing N parts equal to the phase count when packing was legal is a contract violation — `/lazy-batch{,-cloud}` budgets one Opus cycle per `/execute-plan` dispatch, so over-fragmentation directly burns the cycle budget (8 fragmented parts where 4 packed parts would have fit is a 4-cycle waste).

### Partitioning rules (apply in priority order)

1. **Phases are atomic; parts are NOT.** A phase's WUs all go in the same plan file — never split a phase across two parts. But a single part SHOULD pack multiple consecutive phases together as long as the total stays ≤ 8 WUs and the dependency edges (rule 2) allow it. The unit of partitioning is the PART, not the phase.
2. **Respect cross-feature dependency edges.** A plan's WUs MUST NOT reference an upstream phase that is scheduled in a later plan. If feature B's phase P3 depends on feature A's phase P2, both must land in the same plan or A's P2 must land in an earlier plan than B's P3.
3. **First-fit pack to minimize N, then balance.** Walk the cross-feature phase queue in execution order. Accumulate phases into the current part as long as `current_wus + next_phase_wus ≤ 8` AND rule 2 still holds. When the next phase would overflow the cap (or break a dep edge), close the current part and start a new one with that phase. After this first pass, if any adjacent parts can be balanced (e.g. one part is (8) and the next is (1) — but rebalancing would still respect rule 1 and rule 2), do so. Prefer (7, 6, 7, 6) over (8, 8, 8, 2) when both are legal; prefer either over (3, 3, 3, 3, 3, 3, 3, 3) when packing was available.
4. **Single-phase WU overflow is a red flag, not a split point.** If a single phase has more than 8 WUs on its own, do NOT split that phase — that's a /spec-phases quality issue. Surface it explicitly in the final report:
   > **Red flag:** phase `<feature> P<N>` has <K> work units (> 8 cap). This indicates the phase is too large; re-run `/spec-phases` to decompose it before writing a plan. Generating a single oversized plan anyway as best-effort.
   Then generate one plan for that phase containing all its WUs, exceeding the cap. Other phases still partition normally.

### Worked example (one part per phase is WRONG when packing was legal)

Queue: 8 phases, WUs `[4, 3, 3, 3, 3, 4, 3, 3]` (total 26), no cross-feature deps.

| Wrong (8 parts — one phase each) | Right (4 parts — packed) |
|----------------------------------|--------------------------|
| part-1: P1 (4)                   | part-1: P1 + P2 (4 + 3 = 7) |
| part-2: P2 (3)                   | part-2: P3 + P4 (3 + 3 = 6) |
| part-3: P3 (3)                   | part-3: P5 + P6 (3 + 4 = 7) |
| part-4: P4 (3)                   | part-4: P7 + P8 (3 + 3 = 6) |
| part-5: P5 (3)                   |                          |
| part-6: P6 (4)                   |                          |
| part-7: P7 (3)                   |                          |
| part-8: P8 (3)                   |                          |

The 8-part output is a contract violation even though each part respects the cap. The right output is 4 parts with `phases: [1, 2]`, `phases: [3, 4]`, `phases: [5, 6]`, `phases: [7, 8]`. Anti-pattern to avoid: reading rule 1 as "phases are the units of partitioning" — they aren't, PARTS are. Anti-pattern to avoid: reading the `phases: [N]` frontmatter as a singleton invariant — it's a LIST and multi-element values are normal.

### Output file naming

- **N == 1 (single plan, ≤ 8 WUs):** keep the existing convention — `all-phases-<slug>.md` or `phase-<N>-<slug>.md`.
- **N > 1 (partitioned):** append `-part-K` to the existing slug — `all-phases-<slug>-part-1.md`, `all-phases-<slug>-part-2.md`, etc. (or `phase-<N>-<slug>-part-1.md` for single-phase plans).

### Plan-series preamble

Every part file MUST start (after the existing "Mobile plan" preamble) with a `Plan series` block that lists every sibling part. This anchors recovery if the executing session resumes after compaction without the full directory listing.

> **Plan series:** part K of N. Sibling parts:
> - part 1: `<absolute path to part-1>`
> - part 2: `<absolute path to part-2>` (this file)
> - part 3: `<absolute path to part-3>`
>
> Execute parts strictly in order. Each part is self-contained — do NOT cross-reference siblings during execution.

Each part is otherwise **fully self-contained** per the existing /write-plan contract (execution model, mandatory rules, component reference card, blocking-issue protocol, completion section). Generate each part with the full template; do not abbreviate later parts.

---

## Step 3: Draft the Comprehensive Plan

Write a **fully self-contained** plan for each partition determined in Step 2.5 covering the work units assigned to that partition. **Each plan part must include every instruction needed for autonomous execution** — including the execution loop, phase-selection logic, blocking-issue protocol, and completion steps. When the executing session reads any single plan file, it will execute it verbatim, potentially in a fresh context window. Nothing outside the plan can be relied upon, including sibling parts.

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
> **HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.ts`, `.js`, `.cs`, `.vue`, `.py`, `.rs`, `.tsx`, `.jsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`.
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

**References section (write this, listing each upstream artifact you read in Step 1b.1):**

> ## References — Upstream Artifacts
>
> Upstream plans and PHASES.md files this plan was authored against. The executing session SHOULD `Read` these before starting any work unit whose Implementation goal references the corresponding upstream contract. Listed in dependency order.
>
> | Upstream feature | Kind | Path | Why this plan references it |
> |------------------|------|------|------------------------------|
> | <upstream-id-1> | hard | <abs-path-to-upstream-PHASES.md> | <one-line: what contract/decision this plan inherits> |
> | <upstream-id-1> | hard | <abs-path-to-upstream-plan.md> | <one-line: what implementation pattern this plan inherits> |
> | <upstream-id-2> | hard | <abs-path> | <one-line> |
>
> (If no hard deps on Complete upstreams, write `(none — this plan has no completed hard upstream dependencies)`.)

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

**Anchor discipline (MANDATORY — every dependency that names an existing symbol or file):**
Every phrase in a work unit's Implementation goal or Scope that uses "uses", "extends", "delegates to", "calls existing", "refactors", or "integrates with" an existing file/type/function MUST carry a `[VERIFY: <grep-or-path>]` annotation immediately after the cited name. The annotation is the exact shell command (or absolute path) that proves the symbol/file exists in the tree **today**. Examples:
- `delegates to PatternStore.setPattern() [VERIFY: grep -r "fn setPattern" src/stores/]`
- `extends SampleSource enum [VERIFY: grep -r "enum SampleSource" src-tauri/src/]`
- `uses TrackCommandQueue [VERIFY: grep -rn "TrackCommandQueue" src-tauri/src/]`

If a dependency cannot be verified (zero-hit grep), it is NOT an "existing" dependency — convert it to an explicit "must be BUILT in this plan" deliverable instead. Phantom citations (`SampleSource::TrackLoop`, `TrackCommandQueue`, `Arc<Pattern>` per-channel fields, `chainParam` IPC — all zero-result greps in their respective plans) are the primary cause of plan rot; do not perpetuate them.

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

## Step 3.5: Anchor-Existence Check (MANDATORY — BEFORE WRITING PLAN FILES)

Before writing any plan file to disk, verify every `[VERIFY: …]` annotation you authored in Step 3:

1. **Run each grep** (or confirm each path exists). A `[VERIFY: …]` that returns zero hits is a **phantom anchor** — it blocks finalization.
2. For each phantom anchor, either:
   - **Correct the anchor** (find the real symbol name and re-verify), or
   - **Convert the dependency** to an explicit "must be BUILT in this plan" deliverable (remove the `[VERIFY: …]`, add the file/type to the work unit's Files-to-create list, and mark TDD: yes).
3. A plan with unresolved phantom anchors MUST NOT be written with `status: Ready`. If you cannot resolve an anchor and cannot scope the build into this plan, write `NEEDS_INPUT.md` per the halt protocol above and stop.

**Mechanical backstop:** where the repo provides a `qg:plan-anchors` gate (e.g. AlgoBooth), it enforces this check automatically at QG time — but the manual `[VERIFY: …]` discipline above is required regardless, because not every repo has the gate and the gate runs at execution time, not at authoring time.

---

## Step 4: Write Plan Files to Disk (MANDATORY)

!`cat ~/.claude/skills/_components/plan-file-output.md`

**Frontmatter for `/write-plan`:**
- `kind: implementation-plan`
- `feature_id:` — parent feature directory name
- `status: Ready` (or `Draft` if `--batch` halted on `NEEDS_INPUT.md`)
- `phases:` — YAML list of every PHASES.md phase number this plan implements. **Multi-element lists are normal and expected** when Step 2.5 packed multiple phases into one part — e.g. `phases: [1, 2]`, `phases: [3, 4]`, `phases: [5, 6, 7]`. A singleton `phases: [N]` is correct ONLY when that one phase saturates the 8-WU cap on its own (or it's the last part and no other phase remained to pack). For a multi-feature plan, list every phase across every feature this part covers. For partitioned multi-part output (Step 2.5), each part's `phases:` lists every phase assigned to that part — not just the lowest.

### Multi-part Output Reporting

If Step 2.5 produced **multiple parts**, the standard plan-file-output protocol still applies for path resolution and writing — but the final report changes:

1. Write every part file to its resolved path (use the `-part-K` suffix from Step 2.5's naming rule).
2. Insert the `Plan series` preamble (from Step 2.5) into each part immediately after the "Mobile plan" preamble.
3. Report the full set, not just the first part. Print:
   ```
   Plan written in N parts:
     part 1: <absolute-path-1>  (<wu-count-1> work units)
     part 2: <absolute-path-2>  (<wu-count-2> work units)
     ...
   Total work units: <sum>
   Execute parts strictly in order:
   ```

4. Then output **one fenced code block per part** so each is individually copyable on mobile:

   ~~~
   ```
   /execute-plan <absolute-path-1>
   ```
   ~~~

   ~~~
   ```
   /execute-plan <absolute-path-2>
   ```
   ~~~

5. If any phase exceeded the 8-WU cap on its own (Step 2.5 red flag), print the red-flag block above the code blocks so the user sees it before kicking off execution.

If Step 2.5 produced a **single part** (N == 1), follow the standard plan-file-output protocol exactly as written — single path, single copyable command, no series preamble needed.
