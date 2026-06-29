---
description: Generate a lane-based implementation plan for ALL phases across 1+ PHASES.md files — Cognito Forms variant (backend/frontend lanes, tiered gates, typegen seam)
argument-hint: <path/to/PHASES1.md> [path/to/PHASES2.md] [...]
name: write-plan-cognito
plan-mode: never
---

# Write Plan (Cognito Forms)

Repo-scoped variant of `/write-plan` tuned for this repo's cost profile: slow backend builds, generated server types committed to source, no MCP surface. Plan (once), then a separate session continuously implements all phases from one or more PHASES.md files until complete or blocked.

**Key differences from the generic `/write-plan`:**

- **Lane partitioning, not per-deliverable work units.** A phase's work is split into at most a few coarse lanes (default: one backend lane + one frontend lane), each executed by a single Sonnet agent. This minimizes build/test cycles — the dominant cost in this repo.
- **TDD is inline in the lane briefing** — one agent writes failing tests, captures RED output, implements, captures GREEN output. No separate test-agent/impl-agent pipeline.
- **Tiered quality gates:** Tier 1 (incremental project build via `/msbuild -Project` + `--no-build` filtered tests via `/mstest`/`/nxtest`) in-loop; the authoritative Tier 2 full-solution `/msbuild` runs **once per plan-part** (plus on escalation triggers) — never per batch. Every build/test routes through the queue skills (`/msbuild` `/mstest` `/nxbuild` `/nxtest`) — never raw `dotnet`/`npx nx`.
- **Typegen seam is orchestrator-owned:** when a phase changes server-side types, the orchestrator runs an incremental `Cognito.Services` build (`/msbuild -Project`) + `generate-server-types.ps1 -UpdateInPlace` between the backend and frontend lanes. No full solution build is needed for type regeneration.
- **No MCP integration test step** — this repo has no testable MCP surface.
- **No auto-commits or pushes** — repo policy (`.claude/skill-config/commit-policy.md`) is that all git operations are manual.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode` under any circumstances. Do NOT present the plan for interactive approval. The deliverable of this skill is a written PLAN.md file, not a plan-mode interaction.

**Flow:** Load context → partition into lanes and parts → draft ONE self-contained plan per part → write plan file(s) → report path(s).

**Critical: each plan part must be fully self-contained.** It may be executed after the context window is cleared. Every execution instruction, loop control, blocking-issue protocol, and completion step MUST be baked into the generated plan itself. Execution-time components are referenced by file path (not inlined) — the executing session reads them from disk on demand.

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation. Strip `--batch` before resolving PHASES.md paths.

- **Skip the Step 1a `AskUserQuestion`** — refuse cleanly with an error if no paths are supplied.
- For genuine ambiguity during drafting (a phase's deliverables admit two materially different lane decompositions), write `NEEDS_INPUT.md` and halt rather than picking arbitrarily. Operational/mechanical choices (file paths, naming, part cutoffs, seam classification) MUST be auto-accepted; only genuine design forks halt.

### Halt protocol — `NEEDS_INPUT.md`

Compute `{feature-dir}/NEEDS_INPUT.md` (parent of the first PHASES.md in `$ARGUMENTS`). Write per `~/.claude/skills/_components/sentinel-frontmatter.md` using the rich-body convention — one `## Decision Context` subsection per decision with `**Problem:**` / `**Options:**` / `**Recommendation:**`.

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

Echo the entire `## Decision Context` section to chat before returning. STOP without writing the plan file (or set `status: Draft` on any unavoidable partial plan files and list them under `partial_artifacts:`).

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
3. Note the feature name (directory name)

Also read:
- Root `AGENTS.md` and the nearest `AGENTS.md`/`CLAUDE.local.md` for each area the phases will touch (e.g. `Cognito.Web.Client/CLAUDE.local.md` for frontend work) — these inform lane briefings and file-path reality

### 1b.1. Load Upstream Plan References

For each input PHASES.md, read the sibling SPEC.md's `**Depends on:**` block to find prior plans the new plan should reference.

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Procedure:

1. Parse the SPEC's `**Depends on:**` block. Filter to `kind == hard`.
2. For each hard dep, resolve the upstream directory and apply the completion check.
3. For each completed hard upstream: glob `<upstream-dir>/plans/*.md` and read selectively — only plans whose title touches a domain this plan's lanes will modify (contracts, paths, schemas, types). Record the absolute paths of plans you read for the generated plan's `## References` section.
4. If the block is missing, malformed, or all hard deps are incomplete, skip this step. Do NOT abort.

### 1c. Build the Cross-Feature Phase Queue

Scan all loaded PHASES.md files. For each phase with unchecked deliverables (`- [ ]`):
1. Record its feature, phase number, title, entry criteria, and files it will create/modify
2. Parse entry criteria for cross-feature and intra-feature dependencies

Build a directed acyclic graph of all pending phases. Execution order respects this graph.

---

## Step 2: Dirty Tree Check (MANDATORY — BEFORE DRAFTING)

1. Run `git status --porcelain`.
2. Empty output → clean; proceed.
3. Non-empty → announce "Dirty tree detected — committing existing changes before planning", run `git diff --stat` to understand scope, then `git add -A` and commit with message `chore: checkpoint uncommitted changes before phased implementation`. Do NOT push (work repo — the hook blocks it). Do NOT run a quality-gate baseline — a full build here is wasted; the part-end Tier 2 gate is the authority.

---

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

---

## Step 2.5: Partition into Lanes and Parts (MANDATORY — BEFORE DRAFTING)

### Lane partitioning (replaces per-deliverable work units)

A **lane** is a coarse, cohesive slice of one phase executed by a single Sonnet agent that owns both tests and implementation for its scope. Default decomposition per phase:

- **Backend lane:** ALL C# changes for the phase — model, service, controller, and their MSTest tests.
- **Frontend lane:** ALL Vue/TS changes for the phase — components, composables, stores, and their Jest tests.
- A phase that is backend-only or frontend-only gets a single lane. Never invent an empty lane.

**Soft cap — split rule:** if a lane would exceed **~4 deliverables or ~8 files**, split it into sequential sub-lanes along the cleanest internal boundary (e.g. domain model + service vs. controller + endpoints). Sub-lanes of the same side run sequentially (they may share files); they never run in parallel with each other.

**File-overlap rule:** lanes dispatched in the same batch must not share files. Backend and frontend lanes never share files by construction — EXCEPT generated server types, which neither lane touches (orchestrator-owned, see seam below).

**Anti-patterns:**
- Splitting a phase into per-deliverable micro-units — that is exactly the overhead this variant removes
- Splitting a lane "for safety" when it is under the soft cap
- Letting a lane own `Cognito.Web.Client/libs/types/server-types/**` — generated types are never agent-edited

### Seam classification (per phase)

Classify each phase **at plan time**:

- **Sequenced** — the phase's backend deliverables touch any generated-contract source: classes with `[ExportToTypeScript]`, anything under `Cognito.Core/Model/` or `Cognito.Core/DataTransfer/`, or other types the frontend consumes via `libs/types/server-types/`. Execution order: backend lane → orchestrator typegen step → frontend lane.
- **Parallel** — no generated-contract impact. Backend and frontend lanes dispatch concurrently in one message.

When unsure, classify Sequenced — a wrong Parallel costs rework; a wrong Sequenced costs only wall-clock.

### Part partitioning (replaces the 8-WU cap)

- **Hard cap: 3 phases per plan part** (a phase with split sub-lanes counts as one phase). Walk the phase queue in execution order, first-fit packing phases into parts while respecting cross-feature dependency edges (a part's phases must not depend on phases scheduled in a later part).
- Phases are atomic — never split one phase across parts.
- **N == 1:** name the plan `all-phases-<slug>.md` (or `phase-<N>-<slug>.md` for a single phase).
- **N > 1:** append `-part-K` to the slug, and start every part (after the "Mobile plan" preamble) with a `Plan series` block listing every sibling part's absolute path and the rule "Execute parts strictly in order. Each part is self-contained — do NOT cross-reference siblings during execution."

---

## Step 3: Draft the Plan

Write a **fully self-contained** plan for each part. Everything below is plan template content — write it into the plan, filling bracketed values.

---

**Plan header:**

> # Implementation Plan — [feature(s)] (Cognito Forms, lane-based)
>
> **PHASES.md files:** [paths, with feature names and phase counts]
> **SPEC.md files:** [paths]
> **Total phases in this part:** X
> **Plan version:** cognito-lanes-v1 (reference-based — components loaded from disk per step)

**Execution-policy pointer (write this verbatim — single-source the generic policy):**

The generic autonomous-execution policy (COMPONENT LOADING PROTOCOL, the generic MANDATORY RULES, the generic Phase-Selection Loop, Blocking Issue Protocol, and Completion report) is **single-sourced** in `~/.claude/skills/_components/execution-contract.md`. Emit this pointer block, then emit ONLY the Cognito lane-specific overrides below it — do NOT re-emit the generic sections the contract already carries:

> ## Execution Policy — single-sourced + Cognito lane overrides
>
> This plan's baseline autonomous-execution policy lives in **`~/.claude/skills/_components/execution-contract.md`**. The executing session MUST `Read` it before executing any batch and follow it as the operating contract. The Cognito-lane sections written below this pointer (lane-based EXECUTION MODEL, the lane Component Reference Card, the lane MANDATORY RULES, the lane Execution Protocol with the typegen seam and tiered queue-routed gates, and the no-auto-commit repo policy) **override the contract's generic defaults** wherever they differ — they are not duplication, they are the Cognito-lane specialization. Where neither this plan nor the repo's `.claude/skill-config/` overrides a contract rule, the contract governs.

**Lane EXECUTION MODEL (Cognito override — write verbatim):**

> ## EXECUTION MODEL — READ THIS FIRST (Cognito lane override)
>
> This plan uses an **orchestrator + Sonnet lane-agent** architecture:
>
> | Role | What it does | Allowed tools |
> |------|-------------|---------------|
> | **Orchestrator (you)** | Read plan, compose Agent prompts, dispatch lane agents, run the typegen seam step, review output, run quality gates, update tracking docs | `Agent`, `Read`, `Bash` (gates/typegen only), `Skill` (build/test gates — `/msbuild` `/mstest` `/nxbuild` `/nxtest`), `TaskCreate`/`TaskUpdate` |
> | **Sonnet lane agent** | Write ALL source and test code for ONE lane — tests first (RED), then implementation (GREEN) | `Edit`, `Write`, `Read`, `Bash`, `Grep`, `Glob`, `Skill` (for `/msbuild`, `/mstest`, `/nxtest` — the only sanctioned build/test path) |
>
> **HARD CONSTRAINT:** You MUST NOT call `Edit` or `Write` on source or test files. If you are about to modify a `.cs`, `.ts`, `.vue`, `.js`, `.tsx`, or test file — STOP and compose an `Agent` tool call instead. The ONLY files you may modify directly: `PHASES.md`, `CLAUDE.md`, the plan file's frontmatter, `work-log.jsonl`. The ONLY source-adjacent artifact you regenerate directly is `Cognito.Web.Client/libs/types/server-types/**` — via the typegen script, never by hand.
>
> **Dispatch pattern:** `Agent({ description: "...", model: "sonnet", prompt: "<FULL self-contained context — lane definition + lane-agent briefing — the agent has zero prior context>" })`
>
> **Dispatch-census note (overrides generic executor expectations):** This plan uses inline-TDD lane agents. ONE lane agent serves as BOTH the test agent and the implementation agent for its lane — its briefing mandates failing-tests-first with pasted RED and GREEN output. For any dispatch census, count each lane agent as one test-agent AND one impl-agent. A batch with ≥ 1 lane-agent dispatch satisfies the per-batch dispatch contract; do NOT dispatch separate test/impl agents.

(The COMPONENT LOADING PROTOCOL is part of the single-sourced `execution-contract.md` pointed to above — do NOT re-emit it. The Cognito Component Reference Card below OVERRIDES the contract's default card, because this lane uses lane-specific steps L.0–L.7, repo-relative components, and queue-routed gates.)

**Lane Component Reference Card (Cognito override — write verbatim):**

> ## Component Reference Card (Cognito lane override)
>
> | Step | Component | Path |
> |------|-----------|------|
> | Step 0 | Task Tracking | `~/.claude/skills/_components/task-tracking.md` |
> | Step L.0 | Source Re-read | `~/.claude/skills/_components/source-reread.md` |
> | Step L.1 | Lane Agent Briefing | `.claude/skills/write-plan-cognito/lane-agent-briefing.md` (repo-relative) |
> | Step L.3 | Lane Review | `~/.claude/skills/_components/subagent-review.md` |
> | Step L.3 | Mount-Site Verification | `~/.claude/skills/_components/mount-site-verification.md` |
> | Step L.4 | PHASES.md Update | `~/.claude/skills/_components/phases-update.md` |
> | Step L.5 / Part-end | Quality Gates (tiered) | `.claude/skill-config/quality-gates.md` (repo-relative) |
> | Step L.6 | Commit Policy | `.claude/skill-config/commit-policy.md` (repo-relative — this repo: no auto-commits) |
> | Part-end | Integration Verification | `~/.claude/skills/_components/integration-verification.md` |
> | Part-end | CLAUDE.md Review | `~/.claude/skills/_components/claude-md-review.md` |
> | Final | Work Log | `~/.claude/skills/_components/work-log.md` |

**References section (write this, listing each upstream artifact read in Step 1b.1):**

> ## References — Upstream Artifacts
>
> | Upstream feature | Kind | Path | Why this plan references it |
> |------------------|------|------|------------------------------|
> | ... | hard | ... | ... |
>
> (If none: `(none — this plan has no completed hard upstream dependencies)`.)

**Lane MANDATORY RULES (Cognito override — write verbatim; these replace the contract's generic rules for this lane plan):**

> ## MANDATORY RULES — DO NOT SKIP ANY STEP (Cognito lane override)
>
> 1. ALL source and test code is written by Sonnet lane agents via the `Agent` tool. The orchestrator never edits source/test files. The ONLY exception: trivial PASS-WITH-FIXES items (a few lines).
> 2. All lane-agent edits happen in the current worktree — NEVER create worktrees for agents.
> 3. Every lane with testable behavior follows inline TDD — the lane agent writes failing tests first and pastes RED then GREEN ground-truth output.
> 4. Lane agents use Tier 1 verification commands only, routed through the queue skills: `/msbuild -Project "<csproj>"` for an incremental project build and `/mstest -Filter "ClassName~…"` / `/nxtest -Project … -Pattern … -NoCoverage` for filtered tests. Never raw `dotnet`/`npx nx`. Nobody runs a full-solution `/msbuild` (no `-Project`) except the orchestrator at part-end Tier 2 (or on an escalation trigger).
> 5. Sequenced phases: the frontend lane is NOT dispatched until the typegen seam step completes and the server-types diff is reviewed.
> 6. Every lane's output is reviewed (ground-truth re-run included) before PHASES.md is updated or the next batch launches.
> 7. PHASES.md is updated after EACH batch completes (not deferred).
> 8. NO git commits or pushes at any point — repo policy. All git operations are manual (see commit-policy component).
> 9. The part-end Tier 2 gate (full-solution `/msbuild` (no `-Project`) + filtered `/mstest`/`/nxtest` for all touched areas) is MANDATORY and 100%-pass before this plan part is reported complete.
> 10. This plan is self-contained — follow it exactly without relying on external context.
> 11. Before each step, `Read` the component files listed for that step from disk.

**Execution Schedule (fill in from the phase queue):**

> ## Execution Schedule
>
> | Step | Feature | Phase | Title | Seam | Lanes | Blocked by |
> |------|---------|-------|-------|------|-------|------------|
> | 1 | [feature] | P[N] | [title] | Parallel \| Sequenced | BE, FE | — |
> | ... | | | | | | |

**Per-Phase Plans — for each phase in execution order:**

> ### Phase: [feature] P[N] — [title]
>
> **Goal:** [one sentence]
> **Entry criteria:** [prerequisite phases]
> **SPEC.md references:** [sections]
> **Seam classification:** [Parallel | Sequenced] — [one-line justification: which deliverables do/don't touch generated contracts]
>
> #### Work Units (Lanes)
>
> For each lane: **Lane ID** (e.g. P2-BE), **Side** (backend/frontend), **Scope** (the PHASES.md checkbox items it covers, copied verbatim), **TDD** (yes/no), **Files to create/modify** (exact paths), **Test files** (exact paths), **Test expectations** (what tests assert), **Implementation goal**, **Spec requirements** (quoted/referenced), **Tier 1 verification commands** (the exact queue-routed skill commands for this lane — `/mstest -Filter "ClassName~…"` for backend tests, `/nxtest -Project … -Pattern … -NoCoverage` for frontend tests, `/msbuild -Project "…"` for an incremental build; never raw `dotnet`/`npx nx`), **Batch** (1, 2, ...).
>
> #### Batch structure
>
> | Batch | Lanes | Parallel? | Notes |
> |-------|-------|-----------|-------|
> | 1 | P[N]-BE [+ P[N]-FE if Parallel seam] | [Yes/Solo] | |
> | [seam] | — typegen seam step — | — | Sequenced phases only |
> | 2 | P[N]-FE | Solo | Sequenced phases only |

**Lane Execution Protocol (Cognito override — write this entire section into the plan; the lane steps L.0–L.7, typegen seam, and tiered gates replace the contract's generic per-batch steps):**

> ## Execution Protocol (Cognito lane override)
>
> ### Phase Selection Loop
>
> Repeat until all phases in the Execution Schedule are complete or a blocking issue triggers early exit:
>
> 1. **Select ready phase(s):** entry criteria satisfied (prerequisite phases' deliverables all checked off). Phases from different features may run concurrently when the schedule allows and no lanes conflict on files.
> 2. **Announce:** "Implementing [feature] Phase N: [title]"
> 3. **Review prior context:** re-read previously completed phases' Implementation Notes in PHASES.md — they take priority over this plan where they diverge.
> 4. **Execute all batches** per the Per-Batch Steps below.
> 5. **Report:** "[feature] Phase N: [title] — complete (uncommitted, per repo policy)"
> 6. **Loop.**
>
> ### Step 0: Initialize Task Tracking (MANDATORY — BEFORE ANYTHING ELSE)
>
> Read `~/.claude/skills/_components/task-tracking.md` and follow it. Create one task per lane (not per deliverable).
>
> ### Per-Batch Steps
>
> #### Step L.0: Re-read Source Documents (MANDATORY)
>
> Read `~/.claude/skills/_components/source-reread.md` and follow it. Re-read from disk: PHASES.md (current phase + prior Implementation Notes), SPEC.md (relevant sections), and this plan file.
>
> #### Step L.1: Dispatch Lane Agent(s)
>
> **PRE-FLIGHT:** confirm you will use `Agent` with `model: "sonnet"` for ALL code changes and will NOT edit source/test files yourself.
>
> Read `.claude/skills/write-plan-cognito/lane-agent-briefing.md`. For each lane in this batch, compose an Agent prompt containing: (1) the lane definition from this plan (scope, files, test expectations, implementation goal, spec requirements, Tier 1 commands), (2) the relevant SPEC.md excerpts, (3) prior Implementation Notes that affect this lane, (4) the lane-agent briefing verbatim.
>
> Parallel-seam phases: dispatch the backend and frontend lane agents in a SINGLE message. Sequenced phases: dispatch only the backend lane now.
>
> **Failed-agent recovery:** if a lane agent fails or returns garbage, re-dispatch once with the failure context appended. Two failures on the same lane = blocking issue.
>
> #### Step L.2: Typegen Seam (Sequenced phases only — between backend and frontend lanes)
>
> After the backend lane passes review (Step L.3 runs for the backend lane FIRST in sequenced phases):
>
> 1. Incremental build of the Services chain (NOT the full solution), queue-serialized + filtered:
>    `/msbuild -Project "Cognito.Services/Cognito.Services.csproj"`
> 2. Regenerate types in place:
>    `powershell.exe -Command "cd 'C:\Users\JacobMadsen\source\repos\Cognito Forms\Cognito.Web.Client\libs\types\typegen'; ./generate-server-types.ps1 -UpdateInPlace"`
> 3. Review the diff: `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` then `git diff -- "Cognito.Web.Client/libs/types/server-types/"`. Confirm the type changes match the backend lane's contract changes — nothing missing, nothing unexpected. Unexpected diffs = treat as a backend-lane review finding (NEEDS-REWORK the backend lane).
> 4. Dispatch the frontend lane (return to Step L.1) — its briefing must note that regenerated types are already on disk.
>
> If a Sequenced phase's backend lane turns out to produce NO server-types diff, note that in PHASES.md and continue — the classification was conservative, no harm done.
>
> #### Step L.3: Review Lane Output (MANDATORY BLOCKING GATE)
>
> Read `~/.claude/skills/_components/subagent-review.md` and follow its complete protocol (including the Ground-Truth Verification Gate), plus `~/.claude/skills/_components/mount-site-verification.md` for new files.
>
> **Cognito gate-cost rules for the ground-truth re-run:** re-run the EQUIVALENT queue-routed test command the lane used — `/mstest -Filter "ClassName~<same filter>"` for backend, or `/nxtest -Project <same project> -Pattern <same pattern> -NoCoverage` for frontend. The falsified-report check compares PASS/FAIL outcome, not byte-identical output, so the equivalent skill command is sufficient. `/mstest` is already `--no-build` and filtered, so it is cheap. NEVER trigger a build (no full-solution `/msbuild`, no `/msbuild -Project`) as part of ground-truth verification. For inline-TDD lanes, the TDD-discipline checks read the lane agent's OWN pasted RED output as the red-state evidence — verify the failures were for the right reason (behavioral, not compile/setup errors) and that the GREEN run passes the same filter.
>
> #### Step L.4: Update PHASES.md (MANDATORY)
>
> Read `~/.claude/skills/_components/phases-update.md` and follow it. Check off completed deliverables; add Implementation Notes (date, work completed, integration notes, pitfalls, files modified).
>
> #### Step L.5: Quality Gates (Tier 1 — already satisfied; verify, don't re-run)
>
> Read `.claude/skill-config/quality-gates.md`. In-loop (Tier 1), the lane agent's verified ground-truth output IS the gate — do not run additional builds or test passes beyond the Step L.3 re-run. **Escalation check:** if this batch changed server-side types consumed by the frontend beyond what the typegen seam handled, added a field to a widely-constructed entity, or renamed/re-exported a module — run the Tier 2 gate NOW (see Part Completion) before proceeding.
>
> #### Step L.6: Commit Step
>
> Read `.claude/skill-config/commit-policy.md`. **This repo: no auto-commits, no pushes — this step is a no-op.** Proceed.
>
> #### Step L.7: Proceed to Next Batch
>
> Checklist (all must be true): review report with verdict produced; ground-truth verified; PHASES.md updated; escalation check done. If any item is unchecked, go back.
>
> ### Part Completion (after ALL phases in this plan part)
>
> 1. **Tier 2 authoritative gate (MANDATORY, 100% pass):**
>    - C# changes: `/msbuild` (full-solution, no `-Project` — also regenerates server types authoritatively) → `/mstest` filtered to ALL test classes touched by this part (never unfiltered).
>    - Frontend changes: `/nxbuild` (touched projects) → `/nxtest` (touched projects).
>    - Mixed: C# pair then frontend pair.
>    - After the full build, check `git status --short -- "Cognito.Web.Client/libs/types/server-types/"` — any NEW diff means the typegen seam missed something; reconcile before proceeding.
>    - Failures: dispatch Sonnet fix agents, re-run the failing gate. Two failed fix attempts = blocking issue.
> 2. **Integration verification:** read `~/.claude/skills/_components/integration-verification.md` and follow it (cross-lane integration, spec alignment, full-stack coverage for user-facing changes).
> 3. **CLAUDE.md review:** read `~/.claude/skills/_components/claude-md-review.md` and follow it.
> 4. Leave everything uncommitted — the developer commits manually (repo policy).

**Blocking Issue Protocol — write this into the plan:**

> ## Blocking Issue Protocol
>
> If a blocking issue is encountered:
>
> 1. **Stop all in-progress work.** Do not dispatch new agents.
> 2. Do NOT commit anything (repo policy) — leave the working tree as-is and describe its state precisely in the report.
> 3. **Print a blocking-issue report:** completed phases, blocked phase + reason, exact working-tree state (`git status --short` output), recovery suggestion, remaining phases not attempted.
> 4. **Do not work around the blocker.**
>
> Blocking issues include: circular phase dependencies; a lane agent failing twice; a Tier 2 failure unfixable in two attempts; a typegen run that fails or produces irreconcilable diffs; entry criteria referencing a feature/phase not in the input set; anything requiring architectural decisions beyond the specs.

**Completion section — write this into the plan:**

> ## Completion
>
> When all phases in this part are complete and the Part Completion steps have passed:
>
> Print a completion report: features/phases implemented, lane dispatch census (lane agents dispatched, batches executed), Tier 2 gate result, files modified (grouped by lane), Implementation Notes summary, and the reminder that the working tree is intentionally uncommitted for manual review (`git status --short` snapshot).

**Work Log — write this into the plan:**

> ## Append to Work Log (MANDATORY)
>
> Read `~/.claude/skills/_components/work-log.md` and follow it. Call work_log_append with skill, project (`cognito-forms`), title, summary, files_modified, and technical_context.

---

## Step 4: Write Plan Files to Disk (MANDATORY)

!`cat ~/.claude/skills/_components/plan-file-output.md`

**Frontmatter for this skill:**
- `kind: implementation-plan`
- `feature_id:` — parent feature directory name
- `status: Ready` (or `Draft` if `--batch` halted on `NEEDS_INPUT.md`)
- `phases:` — YAML list of every PHASES.md phase number this part implements (multi-element lists are normal when a part packs multiple phases)

### Multi-part Output Reporting

If Step 2.5 produced multiple parts: write every part file (with `-part-K` suffix and the `Plan series` preamble), then report the full set — one line per part with its lane count — followed by **one fenced code block per part** containing `/execute-plan <absolute-path>` so each is individually copyable. Execute parts strictly in order.

If a single part: follow the standard plan-file-output protocol exactly — single path, single copyable command.
