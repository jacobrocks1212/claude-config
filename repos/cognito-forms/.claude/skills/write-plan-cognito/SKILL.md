---
description: Generate a lane-based implementation plan across 1+ PHASES.md files (all unchecked phases by default; optionally target specific phases) — Cognito Forms variant (backend/frontend lanes, tiered gates, typegen seam)
argument-hint: <path/to/PHASES1.md> [path/to/PHASES2.md] [...] [--phase <id> ...]
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

**Critical: each plan part must be self-contained via its pointer block.** It may be executed after the context window is cleared. Self-contained does NOT mean the execution policy is inlined — it means the plan carries (a) a pointer block naming the two on-disk contracts (generic + Cognito-lane) the executor must `Read`, and (b) ALL per-plan content (touchpoint audit, schedule, lanes, batch structure, plan-specific notes). The lane policy is **single-sourced** in `.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` — never re-emit it into a plan (that was the ~16KB/plan dual-sourcing defect this v2 removed).

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation. Strip `--batch` before resolving PHASES.md paths.

**A phase selector is IGNORED under `--batch`.** The optional `--phase <id>` / bare `phase <id>` selector (Step 1a) is an interactive-operator convenience only. When `--batch` is present, discard any selector token and keep today's behavior exactly — full PHASES.md read (Step 1b) and plan every unchecked phase (Step 1c / Step 2). The autonomous path always plans the whole queue.

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

### 1a. Resolve PHASES.md Paths (+ optional phase selector)

- **Parse the optional phase selector first, then strip it.** `$ARGUMENTS` may carry a repeatable phase selector — a canonical flag `--phase <id>` and/or a bare trailing `phase <id>` token (the form an operator types, e.g. `… PHASES.md phase 9`). Ids are phase tokens (`3`, `3.5`, `12`, …). Collect every selected id into a `TARGET_PHASES` set, then **remove the selector tokens** (`--phase`, `phase`, and their id arguments) from `$ARGUMENTS` so they are not mistaken for `.md` paths. If `--batch` is present, discard the selector entirely (see Batch Mode) — `TARGET_PHASES` is empty on the batch path.
- `$ARGUMENTS` must contain 1+ `.md` paths (after selector stripping). If none are provided, use **AskUserQuestion** to ask for them.
- For each PHASES.md, confirm the file exists. If not, report and exclude it.

### 1b. Read Everything

**Phase-targeted read (when `TARGET_PHASES` is non-empty and NOT `--batch`).** The operator scoped the plan to specific phase id(s), so slice instead of reading the whole file. For **each** PHASES.md, run the deterministic scoped reader (canonical command + flags in `~/.claude/skills/_components/source-reread.md` lines 9-18 — do not reinvent it):

```bash
python ~/.claude/scripts/phases-slice.py <path/to/PHASES.md> --phase <id> [--phase <id> ...] --notes all
```

Pass one `--phase <id>` per targeted id; `--notes all` appends the sibling `IMPLEMENTATION_NOTES.md` sections. This prints the phase index plus the full slice (and notes) of each targeted phase — the working context for those phases. If the script is unavailable (exit 1), fall back to `grep -n '^#\{2,3\} Phase' <PHASES.md>` + a bounded offset/limit `Read` of only the targeted phase section(s). Then continue with steps 2-3 below (SPEC.md, feature name) as normal.

**Full read (default — no phase selector).** For **each** PHASES.md:
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

Scan all loaded PHASES.md files. **When `TARGET_PHASES` is non-empty (interactive phase-targeted invocation), restrict the scan to the targeted phase id(s) only** — plan those phases and skip all others, even if other phases have unchecked deliverables. When `TARGET_PHASES` is empty (default / `--batch`), scan every phase as usual. For each phase in scope with unchecked deliverables (`- [ ]`):
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

### Bug-fix reachability check (SEAM A — extends the touchpoint audit; planning-time HALT)

For a **bug fix**, the touchpoint audit above verifies each planned fix site *exists* — that is
**not enough**. Add a reachability column to the Step C audit table: for the planned fix site,
show it lies **on the symptom's traced serving path** from the SPEC's root-cause trace
(`~/.claude/skills/_components/root-cause-trace-gate.md`), not merely that it exists. The fix site
must be a node the symptom's surface actually *reads* on its serving path (`file:line` from the
trace).

| Planned fix site | Exists? | On traced serving path? | Evidence (trace hop `file:line`) |
|------------------|---------|-------------------------|----------------------------------|
| `...` | yes | **yes / NO** | `...` |

A fix site that **exists but is not on the traced serving path is a planning-time HALT** — it is
the 57585 failure (a fix that edits a value the symptom never reads). Interactive: surface it and
refuse to draft the plan. `--batch`: write `NEEDS_INPUT.md` per the halt protocol above. If the
SPEC carries no serving-path trace at all, that too is a halt — `/spec-bug`/`/plan-bug`'s
root-cause trace gate should have produced it before planning.

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
- **Parallel** — no generated-contract impact. Backend and frontend lanes dispatch concurrently **in one assistant message** (the harness's only real-parallelism path; see the executor contract's **Parallelism & background builds** section). For the executor to exploit this, a `Parallel` batch must be machine-evidently file-disjoint — see the batch-structure rule in Step 3.
- **Single-lane (no seam)** — the phase has exactly one lane (backend-only or frontend-only), so there is no backend→frontend handoff: the L.2 typegen seam NEVER runs mid-phase and no second lane exists to dispatch — even when a backend-only phase touches generated-contract sources (any resulting `server-types/**` diff is produced and reconciled at the part-end Tier 2 full `/msbuild`, which regenerates types). Classify every one-lane phase this way — do not force it into `Sequenced` (misleads the executor into looking for a seam step / a phantom frontend lane) or `Parallel` (implies a second concurrent lane). Its batches are `Solo` by construction. *(Back-compat: v3 plans written before this value express one-lane phases as `Sequenced` plus a plan-specific note that the seam is not run — executors treat that identically; no contract-version bump.)*

When unsure **between Parallel and Sequenced** (two-lane phases), classify Sequenced — a wrong Parallel costs rework; a wrong Sequenced costs only wall-clock.

**Make disjointness machine-evident (so the D4 executor can same-message-batch).** The generated executor reads the contract's same-message file-disjoint batching rule: it dispatches a batch's lanes in ONE message ONLY when the plan proves they are file-disjoint. So every `Parallel`-seam batch you author MUST make that proof checkable without re-deriving it: each lane in the batch lists its exact `Files to create/modify`, and no two same-batch lanes share a file. Backend and frontend lanes are disjoint by construction (the file-overlap rule), and neither owns `Cognito.Web.Client/libs/types/server-types/**` (orchestrator-owned) — so a `Parallel` BE+FE batch is provably disjoint as long as both lanes' file lists are present and non-overlapping. Do not change lane semantics for this — just ensure the file lists are explicit enough that the executor's disjointness check passes. `Sequenced` batches stay one-lane-per-batch (the typegen seam separates them), so no same-message claim applies.

### Part partitioning (replaces the 8-WU cap)

- **Hard cap: 3 phases per plan part** (a phase with split sub-lanes counts as one phase). Walk the phase queue in execution order, first-fit packing phases into parts while respecting cross-feature dependency edges (a part's phases must not depend on phases scheduled in a later part).
- Phases are atomic — never split one phase across parts.
- **N == 1:** name the plan `all-phases-<slug>.md` (or `phase-<N>-<slug>.md` for a single phase).
- **N > 1:** append `-part-K` to the slug, and start every part (after the "Mobile plan" preamble) with a `Plan series` block listing every sibling part's absolute path and the rule "Execute parts strictly in order. Each part is self-contained — do NOT cross-reference siblings during execution."

---

## Step 3: Draft the Plan

Write a **pointer-based** plan for each part (self-contained via its pointer block + per-plan content — see the "Critical" note at the top of this skill). Everything below is plan template content — write it into the plan, filling bracketed values.

**SPEC-excerpt discipline (v3):** you read the full SPEC.md at Step 1b — the executor never does (a measured ~14–38KB read per session it doesn't need). Each phase's `#### SPEC excerpts` block must therefore be **sufficient on its own**: quote verbatim every Locked Decision row, requirement, and acceptance criterion the phase's lanes implement, each tagged with its SPEC section/LD id so escalation reads are targeted. Excerpting too little forces the executor into a full-SPEC escalation read (and each escalation is recorded against the plan); excerpting whole sections wholesale just moves the bloat — quote the rows the lanes act on, not their surrounding narrative.

**Planner-side contract consultation (scoped — never the full file):** the executor Reads both execution contracts at run time; the planner does NOT need them to draft a plan — this SKILL.md carries the lane semantics required for partitioning and the templates below. Consult `execution-contract-cognito-lanes.md` ONLY when drafting a `## Plan-specific execution notes` row that cites or deltas a specific contract behavior (e.g. the L.2 typegen seam, Part Completion): list its headings first (`grep -n "^#" .claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md`), then range-`Read` just the section(s) the note touches (~1–3KB) — never the whole ~18KB contract (a measured planner-context sink with no accuracy payoff over the scoped read). A plan whose notes section is `(none — the two contracts govern unmodified)` warrants zero contract reads.

---

**Plan header:**

> # Implementation Plan — [feature(s)] (Cognito Forms, lane-based)
>
> **PHASES.md files:** [paths, with feature names and phase counts]
> **SPEC.md files:** [paths]
> **Total phases in this part:** X
> **Plan version:** cognito-lanes-v3 (pointer-based — execution policy lives on disk; SPEC content rides as scoped excerpts)

**Execution-policy pointer (write this verbatim — the ONLY policy content in the plan):**

The execution policy is **single-sourced in two on-disk contracts** — the generic
`~/.claude/skills/_components/execution-contract.md` and the Cognito lane specialization
`.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md` (repo-relative). Do NOT
re-emit ANY policy section into the plan — no EXECUTION MODEL, no Component Reference Card, no
MANDATORY RULES, no Execution Protocol / L.0–L.7 steps, no Blocking Issue Protocol, no Completion
or Work Log sections. Write only this pointer block:

> ## Execution Policy — single-sourced (pointer only)
>
> This plan carries NO inlined execution policy. The executing session MUST, before executing any batch:
>
> 1. `Read` **`~/.claude/skills/_components/execution-contract.md`** — the generic autonomous-execution contract.
> 2. `Read` **`.claude/skills/write-plan-cognito/execution-contract-cognito-lanes.md`** (repo-relative from the worktree root; contract version: cognito-lanes-v3) — the Cognito lane specialization. It defines the lane EXECUTION MODEL, the lane Component Reference Card, the lane MANDATORY RULES, the lane Execution Protocol (Steps L.0–L.7 + typegen seam + tiered queue-routed gates + Part Completion), the Blocking Issue Protocol, the Completion report, and the Work Log step.
>
> **Precedence (most-specific wins):** this plan's "Plan-specific execution notes" → the lane contract → the generic contract. After any context compaction, re-read this plan first, then both contracts, before resuming.

**References section (write this, listing each upstream artifact read in Step 1b.1):**

> ## References — Upstream Artifacts
>
> | Upstream feature | Kind | Path | Why this plan references it |
> |------------------|------|------|------------------------------|
> | ... | hard | ... | ... |
>
> (If none: `(none — this plan has no completed hard upstream dependencies)`.)

**Execution Schedule (fill in from the phase queue):**

> ## Execution Schedule
>
> | Step | Feature | Phase | Title | Seam | Lanes | Blocked by |
> |------|---------|-------|-------|------|-------|------------|
> | 1 | [feature] | P[N] | [title] | Parallel \| Sequenced \| Single-lane | BE, FE | — |
> | ... | | | | | | |

**Per-Phase Plans — for each phase in execution order:**

> ### Phase: [feature] P[N] — [title]
>
> **Goal:** [one sentence]
> **Entry criteria:** [prerequisite phases]
> **Seam classification:** [Parallel | Sequenced | Single-lane (no seam)] — [one-line justification: which deliverables do/don't touch generated contracts; for Single-lane, name the one lane and note the part-end Tier 2 build reconciles any `server-types/**` diff]
>
> #### SPEC excerpts (authoritative for this phase — executor does NOT read SPEC.md)
>
> > **[SPEC section heading / LD id]** (SPEC.md § [section])
> > [verbatim quote of the requirement / Locked Decision row / acceptance criterion]
>
> > ... (one blockquote per requirement this phase's lanes implement)
>
> **Escalation rule:** these excerpts are the working SPEC content for this phase. Read the on-disk SPEC.md ONLY if an excerpt is ambiguous, contradicts observed code, or a lane needs context the excerpt doesn't carry — then read just the named section, and record the escalation + reason in the phase's Implementation Notes (it means the planner under-excerpted).
>
> #### Work Units (Lanes)
>
> For each lane: **Lane ID** (e.g. P2-BE), **Side** (backend/frontend), **Scope** (the PHASES.md checkbox items it covers, copied verbatim), **TDD** (yes/no), **Files to create/modify** (exact paths), **Test files** (exact paths), **Test expectations** (what tests assert), **Implementation goal**, **Spec requirements** (quoted/referenced), **Tier 1 verification commands** (the exact queue-routed skill commands for this lane — `/mstest -Filter "ClassName~…"` for backend tests, `/nxtest -Project … -Pattern … -NoCoverage` for frontend tests, `/msbuild -Project "…"` for an incremental build; never raw `dotnet`/`npx nx`), **Batch** (1, 2, ...).
>
> #### Batch structure
>
> The `Parallel?` column is the executor's same-message-dispatch signal: `Yes` means the executor SHOULD emit this batch's lane agents as multiple `Agent` blocks in ONE message (it is provably file-disjoint); `Solo` means one lane. The `Files (disjoint?)` column makes the disjointness machine-checkable — list each same-batch lane's file set and assert non-overlap, so the executor's file-disjoint check passes without re-deriving it.
>
> | Batch | Lanes | Parallel? | Files (disjoint?) | Notes |
> |-------|-------|-----------|-------------------|-------|
> | 1 | P[N]-BE [+ P[N]-FE if Parallel seam] | [Yes if Parallel seam / Solo] | BE: [files]; FE: [files] — no shared file | |
> | [seam] | — typegen seam step — | — | — | Sequenced phases only |
> | 2 | P[N]-FE | Solo | FE: [files] | Sequenced phases only |
>
> (Single-lane (no seam) phases: exactly one `Solo` batch — no seam row, no batch 2.)

**Plan-specific execution notes (write this section — per-plan deltas ONLY):**

This is the ONLY place plan-level policy deviations live. Everything generic stays in the two
contracts. Write a `## Plan-specific execution notes` section containing ONLY the items below
that actually apply (omit rows that don't — an empty section is written as `(none — the two
contracts govern unmodified)`):

> ## Plan-specific execution notes
>
> - **Typegen seam:** [e.g. "N/A this part — no generated-contract changes; if the part-end full `/msbuild` produces any `server-types/**` diff, treat it as a finding and reconcile before completing." OR "Phase N is Sequenced — run the L.2 typegen seam between its BE and FE lanes."]
> - **Single-writer files:** [any file shared by sequential sub-lanes, with the dispatch-order rule — e.g. "`CoreService.cs` is single-writer across P6-BE-A then P6-BE-B; B dispatches only after A passes review and re-reads the file from disk."]
> - **Tier 2 gate commands (exact):** [the exact part-end `/msbuild` → `/mstest -Filter "..."` / `/nxbuild -Project ...` → `/nxtest -Project ... -Pattern ... -NoCoverage` invocations for the areas this part touches]
> - **Additional blocking triggers:** [phase-specific blocking issues beyond the lane contract's generic list]
> - **Component overrides:** [only if this plan overrides a Component Reference Card row — otherwise omit]

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
