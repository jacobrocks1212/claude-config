---
description: Generate an implementation plan across 1+ PHASES.md files (all unchecked phases by default; optionally target specific phases) — optimized for mobile/async workflow (reference-based components)
argument-hint: <path/to/PHASES1.md> [path/to/PHASES2.md] [...] [--phase <id> ...]
name: write-plan
plan-mode: never
# adhoc-derive-multi-commit-budget-from-dispatch-sites: this skill may emit a
# multi-part plan series (one commit per part). Read by
# lazy_core.skill_declares_multi_commit to derive the unexpected-commits budget.
commit-cadence: multi
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

**A phase selector is IGNORED under `--batch`.** The optional `--phase <id>` / bare `phase <id>` selector (Step 1a) is an interactive-operator convenience only. When `--batch` is present, discard any selector token and keep today's behavior exactly — full PHASES.md read (Step 1b) and plan every unchecked phase (Step 1c). The autonomous path always plans the whole queue.

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

### 1a. Resolve PHASES.md Paths (+ optional phase selector)

- **Parse the optional phase selector first, then strip it.** `$ARGUMENTS` may carry a repeatable phase selector — a canonical flag `--phase <id>` and/or a bare trailing `phase <id>` token (the form an operator types, e.g. `… PHASES.md phase 9`). Ids are phase tokens (`3`, `3.5`, `12`, …). Collect every selected id into a `TARGET_PHASES` set, then **remove the selector tokens** (`--phase`, `phase`, and their id arguments) from `$ARGUMENTS` so they are not mistaken for `.md` paths. If `--batch` is present, discard the selector entirely (see Batch Mode) — `TARGET_PHASES` is empty on the batch path.
- `$ARGUMENTS` must contain 1+ `.md` paths (after selector stripping). If none are provided, use **AskUserQuestion** to ask for them.
- For each PHASES.md, confirm the file exists. If not, report and exclude it.

### 1b. Read Everything

**Phase-targeted read (when `TARGET_PHASES` is non-empty and NOT `--batch`).** The operator scoped the plan to specific phase id(s), so slice instead of reading the whole file. For **each** PHASES.md, run the deterministic scoped reader (the canonical command + flags live in `~/.claude/skills/_components/source-reread.md` lines 9-18 — do not reinvent it):

```bash
python ~/.claude/scripts/phases-slice.py <path/to/PHASES.md> --phase <id> [--phase <id> ...] --notes all
```

Pass one `--phase <id>` per targeted id; `--notes all` appends the sibling `IMPLEMENTATION_NOTES.md` sections. This prints the phase index plus the full slice of each targeted phase (and the notes), which is the working context for those phases. If the script is unavailable (exit 1 on a machine without it), fall back to `grep -n '^#\{2,3\} Phase' <PHASES.md>` to locate the targeted phase heading(s), then a bounded offset/limit `Read` of only those phase sections. Then continue with steps 2-3 below (SPEC.md, feature name, CLAUDE.md) as normal.

**Full read (default — no phase selector).** For **each** PHASES.md:
1. Read the PHASES.md file **in full** — including all previously completed phases. For Implementation Notes, apply the sibling-then-embedded read order: check for a sibling `IMPLEMENTATION_NOTES.md` first; fall back to embedded notes in PHASES.md. See `~/.claude/skills/_components/implementation-notes-read-order.md`.
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

Scan all loaded PHASES.md files. **When `TARGET_PHASES` is non-empty (interactive phase-targeted invocation), restrict the scan to the targeted phase id(s) only** — plan those phases and skip all others, even if other phases have unchecked deliverables. When `TARGET_PHASES` is empty (default / `--batch`), scan every phase as usual. For each phase in scope with unchecked deliverables (`- [ ]`):
1. Record its feature, phase number, title, entry criteria, and files it will create/modify
2. Parse entry criteria for cross-feature dependencies (e.g. "Foundation Phase 1 complete")
3. Parse entry criteria for intra-feature dependencies (e.g. "Phase 2 complete")

Build a directed acyclic graph of all pending phases. The execution order respects this graph — a phase only becomes "ready" when all its entry criteria are satisfied.

### 1c.5. Do NOT author the live MCP-validation gate as a blocking plan work unit (HARD)

The pipeline has a **dedicated runtime-validation step** — `/lazy-batch` Step 9 (`/mcp-test`), which boots the Tauri runtime, runs the MCP scenarios, and writes the `VALIDATED.md` sentinel that gates feature completion. That step OWNS live runtime validation. The plan you author here is consumed by `/execute-plan`, which performs **implementation** and flips the plan-part frontmatter `status:` to `Complete` when its work units are done.

Therefore, when building the WU list:

- **Do NOT emit a terminal plan WU of the form "re-run `/mcp-test` and earn `VALIDATED.md`" (or "run the runtime validation", "live-validate on device", etc.).** Such a WU can only be closed by the Step 9 runtime pass, NOT by `/execute-plan` — so `/execute-plan` correctly leaves the plan `status: In-progress`, and `lazy-state.py` then routes straight back to `/execute-plan` on the same plan, **looping**. The dedicated Step 9 already does this work; duplicating it as a plan WU is the cause of the loop, not a safeguard.
- **Runtime-observable verification still belongs in PHASES.md** — author it as a **non-blocking runtime-verification row** carrying the canonical `<!-- verification-only -->` marker (an HTML comment; SSOT `lazy_core:_VERIFICATION_ONLY_MARKER`), e.g. `- [ ] <!-- verification-only --> API returns expected response after action`, under a recognized `**Runtime Verification**` / `**MCP Integration Test Assertions:**` subsection. **The per-row marker is mandatory — the subsection header alone is the DEPRECATED `_VERIFICATION_SECTION_RE` shim (it merely warns; do not rely on it).** `lazy-state.py`'s `remaining_unchecked_are_verification_only()` recognizes marked rows and routes a phase whose ONLY remaining unchecked rows are verification rows forward to the retro→MCP gate (Step 8→9) instead of looping on `write-plan`/`execute-plan`; the completion gate also auto-ticks a marked row when its verification actually ran. These rows are ticked by the Step 9 `/mcp-test` pass, not by `/execute-plan`.

  > **PLACEMENT RULE (enforced by state-script heuristic):** Runtime-verification / MCP-assertion `- [ ]` checkboxes MUST live under the `## Runtime Verification` section (or the `**Runtime Verification**` / `**MCP Integration Test Assertions:**` bold-marker subsection). They MUST **never** appear under a phase's `### Deliverables` list. A verification checkbox mistakenly placed under `### Deliverables` is classified as an outstanding implementation item, causing spurious write-plan/execute-plan churn. See `~/.claude/skills/_components/phases-runtime-verification.md` for the full placement rule and rationale.
  >
  > **GATE-OWNED ROW BAN (same component, sibling rule):** pipeline-owned actions — SPEC.md/PHASES.md top-level `**Status:**` flips, COMPLETED.md/FIXED.md receipt writes, ROADMAP completion marks, archive moves — are NEVER authored as `- [ ]` rows anywhere (not even under Runtime Verification); they are `__mark_complete__`/`__mark_fixed__`-gate-owned and a checkbox for them loops the state machine. **When consuming an existing PHASES.md into the plan, SKIP/flag any such gate-owned row you encounter rather than planning a work unit for it** — it is not work `/execute-plan` can close (a gate-owned row that survived authoring is a PHASES quality issue; surface it in the final report, do not emit a WU). See `~/.claude/skills/_components/phases-runtime-verification.md`.
- **Net rule:** a plan WU must be something `/execute-plan` can actually DO and CLOSE in-session (write code, write tests, run quality gates, commit). Anything that can only be closed by booting the live runtime is a Step-9 responsibility — keep it OUT of the plan's WU list, and let the PHASES.md runtime-verification subsection carry the deferred verification intent.
- **Spike WUs state their evidence requirement.** When a WU is a runtime spike ("instrument and confirm X at the live boundary"), the WU text MUST state the runtime artifact that closes it — the MCP tool call to make, the log line to grep, or the test that drives the REAL component (actual ring/transport, not a mock) — and MUST state that a static code trace does NOT satisfy it. An evidence-less spike WU invites the d8 WU-9.0 failure: a "runtime spike" closed on a static trace that concluded "no broken seam" and was wrong twice.
- **Cite `INVESTIGATION.md` instead of re-deriving it.** When the feature/bug dir carries a current `INVESTIGATION.md` (the `/investigate` cycle's evidence artifact; freshness anchored on `investigated_commit`), the plan cites its `## Repro Recipe` and `## Recommended Fix Scope`, and SKIPS any spike WU that would merely duplicate an already-**confirmed** Hypothesis-Ledger row — cite the row (artifact + its evidence) instead of re-proving it. Plan no work against a `refuted` row. A stale artifact is cited only as `(stale — re-verify)` and a re-verification row replaces blind trust.

---

## Step 2: Dirty Tree Check (MANDATORY — BEFORE DRAFTING PLAN)

!`cat .claude/skill-config/dirty-tree-check.md 2>/dev/null || cat ~/.claude/skills/_components/dirty-tree-check.md`

---

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

---

## Step 2.5: Partition the Plan by Work-Unit Cap (MANDATORY — BEFORE DRAFTING)

**Hard cap:** a single generated plan file may contain at most **8 work units**. If the queue analysis from Step 1c would produce more than 8 WUs across all input PHASES.md, this skill MUST partition the output into N sequential plan files, each ≤ 8 WUs.

**Soft target (Phase 9 — cost-aware partitioning): ~3–4 WUs per part.** Beyond the 8-WU hard cap, AIM for **3–4 work units per part** so a large phase splits into several *fresh-context* parts. This is a token-cost lever, not a correctness rule: a workstation `/execute-plan` cycle runs **inline in one Opus context** (a dispatched subagent cannot recursively fan out), so its cost is dominated by monotonic context accumulation — every file read, gate output, and edit for the whole part stays in one context. The orchestrator dispatches **one fresh subagent per plan part**, so finer parts = the context reset that nested subagents would otherwise give. A part at the 8-WU cap (d7-multi-timbral: one part hit 399k tok / 106 min in a single inline context) is the cost shape to avoid. The soft target yields to the rules below — never split a phase mid-WU to hit it, and never fragment so finely you bloat cycle count past the savings.

**Minimize N for SMALL phases; split LARGE phases toward the soft target.** Two forces, applied together: (a) pack multiple *small* phases into one part whenever it's legal — a part covering two or three small phases (`phases: [3, 4]`) is normal output; (b) when a single phase (or a legal pack) exceeds the ~3–4 WU soft target, prefer splitting it into multiple parts (still ≤ 8 WUs each, still no phase split mid-WU) so each `/execute-plan` cycle starts lean. One-phase-per-part is correct when that phase is large; multi-phase-per-part is correct when the phases are small. Over-fragmentation (N parts each with 1 WU when packing was legal) is still a contract violation — `/lazy-batch{,-cloud}` budgets one cycle per `/execute-plan` dispatch.

**Partition INTENTIONALLY by complexity (Phase 9).** When partitioning, GROUP mechanical WUs together into mechanical parts and complex WUs into complex parts — **do NOT interleave**. Grouping lets an entire mechanical part dispatch on the cheaper model (Sonnet) without touching the complex work. Tag each emitted part with a `complexity:` frontmatter field (see below). Grouping by complexity is subordinate to the contract rules: parts still cover every phase in execution order, and a phase is never split mid-WU. When a phase's own WUs are a mix of mechanical and complex AND the dependency edges allow it, you MAY split that phase's mechanical WUs into a mechanical part and its complex WUs into a complex part (both tagged `phases: [<that phase>]`) — provided no WU in the later part is depended on by a WU in the earlier part. When complexity grouping would violate execution order or a dependency edge, keep the WUs together and tag the part `complex` (the safe tier).

**Mechanical clusters are a SPLIT SIGNAL — do not absorb them into adjacent complex parts.** The most common missed-Sonnet opportunity is a phase that has a genuine complex core (new DSP, IPC wiring, architecture) PLUS a tail of mechanical WUs (registry/enum encoding, `index.d.ts` regeneration, intellisense completions, Reference-panel prose, tutorial-step authoring, sentinel/doc updates, golden-hash registration, HOT_PATH_FILES rows). When you see this shape, actively ask: can the mechanical tail be carved into a separate `complexity: mechanical` part? Apply the split unless it would:
- violate execution order (a complex WU depends on the mechanical one or vice versa), OR
- push any part over the 8-WU hard cap.

If neither constraint applies, the split is REQUIRED — absorbing a mechanical tail into the complex part simply because they belong to the same phase wastes Opus cycles on work Sonnet handles equally well. The most common mechanical clusters to watch for: any WU whose primary deliverable is adding a variant to an existing enum or registry (`ParamId`, `ModulationSource`, a feature-flag enum), regenerating a type-declaration file, writing intellisense-completion entries, authoring Reference-panel content or tutorial steps, or updating INVARIANTS §10.1 rows and HOT_PATH_FILES registrations with no logic changes.

### Per-part `complexity` tag (Phase 9 — mechanical-vs-complex test)

Every emitted part carries `complexity: mechanical | complex` in its frontmatter (default **`complex`** — the safe tier). The tag drives the `/execute-plan` cycle's dispatch model: `mechanical → sonnet`, `complex → opus`. This is the ONLY place implementation quality could regress, so the boundary is NOT guessed — apply this test:

Tag a part `mechanical` **only when ALL of its WUs** are genuinely mechanical:
- boilerplate / scaffolding,
- test-fixture authoring,
- codegen,
- pure documentation edits,
- mechanical refactors with snapshot/golden coverage,
- registry/enum variant additions (adding a new `ParamId` variant, extending a discriminated union with a new encoding), where the value/wire format is already fully specified by an upstream contract,
- regenerating type-declaration files (`index.d.ts`, napi bindings) from existing definitions,
- intellisense-completion entries filtered to an already-defined eligible set,
- Reference-panel prose or tutorial-step authoring where the API being documented already exists,
- INVARIANTS §10.1 row additions and HOT_PATH_FILES registrations for a module whose hot-path classification is unambiguous (pure float math, no `RefCell`/`Drop`/alloc),

**AND none of its WUs involve**:
- a novel design decision,
- an algorithm or DSP,
- cross-boundary wiring (IPC, service↔store, Rust↔TS, a new production seam).

If **any** WU in the part fails the test — or you are uncertain — tag the part `complex`. A single complex WU contaminates the whole part; never average. `complex` is always safe (it dispatches on Opus, the full-capability tier); `mechanical` is the deliberate, documented downgrade. When you tag a part `mechanical`, note in its WU prose why every WU qualifies, so the `lazy-batch-retro` audit can confirm the boundary was applied (not assumed).

**`complex` is NOT the safe default for tagging — it is the safe fallback for genuinely ambiguous cases.** Every part whose WUs are all mechanical MUST be tagged `mechanical`; tagging it `complex` to "play it safe" wastes Opus budget and defeats the cost-tiering mechanism. Apply the mechanical-vs-complex test above conscientiously for every part, not just the ones that feel obviously mechanical. The default `complex` applies only when the test leaves genuine uncertainty; it is not a license to skip the test.

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

**Execution-policy pointer (write this verbatim — do NOT inline the policy):**

The execution policy (EXECUTION MODEL, COMPONENT LOADING PROTOCOL, Component Reference Card, MANDATORY RULES, Execution Protocol with the Phase-Selection Loop and per-batch Steps B.0–B.6, Blocking Issue Protocol, and Completion) is **single-sourced** in `~/.claude/skills/_components/execution-contract.md`. Do NOT re-emit those sections into the plan. Write only this pointer block:

> ## Execution Policy — single-sourced
>
> This plan's autonomous-execution policy lives in **`~/.claude/skills/_components/execution-contract.md`**. The executing session MUST `Read` that file before executing any batch and follow it as the operating contract — it defines the EXECUTION MODEL (orchestrator + Sonnet subagent roles), the COMPONENT LOADING PROTOCOL, the Component Reference Card, the MANDATORY RULES, the full Execution Protocol (Phase-Selection Loop + per-batch Steps B.0–B.6 + Post-Phase Steps), the Blocking Issue Protocol, and the Completion report.
>
> Where this plan's repo uses non-default gates or component paths (e.g. a harness-config repo whose gates are Python/projection rather than `/msbuild`/`/mstest`), this plan's own per-phase steps and any local `## Component Reference Card` override the contract's defaults for those rows. Everything the contract specifies that this plan does not override still applies.

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

(The MANDATORY RULES, COMPONENT LOADING PROTOCOL, and Component Reference Card are part of the single-sourced `execution-contract.md` pointed to above — do NOT re-emit them into the plan.)

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

**PER-WU PROGRESS CHECKBOX (HARD — ISSUE 6, d8-effect-chains run 2026-06-14).** Every work unit in every generated plan part MUST have exactly one parseable progress checkbox of the form:

```
- [ ] WU-N — <short title>
```

where `N` is the work-unit number (stable within the part) and `<short title>` matches the WU's heading. Place these together in a `## Work Units` checklist near the top of the part body (a single flat list), in addition to the detailed per-WU documentation above. Rationale: `/execute-plan` resumes from the **first unchecked `- [ ] WU-N`** after a `BLOCKED.md`/`NEEDS_INPUT.md` halt or a compaction, and the verify-ledger / resume-granularity logic counts WU progress from these rows. A part whose ONLY checkboxes are MCP-reachability rows and generic Step-B review boxes (no `- [ ] WU-N`) leaves resume + `deliverables_done` BLIND to per-WU progress — exactly the d8-effect-chains part-1 defect a recovery had to patch by hand. These `- [ ] WU-N` rows are plan-body progress markers; they are NOT PHASES.md deliverable rows and NOT the gate-owned/runtime rows banned in Step 1c.5 (`/execute-plan` ticks them as it lands each WU). Do NOT omit them even for a single-WU part.

> **SOURCE OF TRUTH (2026-06-15 — d8-effect-chains review).** When `--verify-ledger --plan <plan_part>` runs, the plan part's `- [ ] WU-N` checkboxes are the **machine source of truth** for that part's deliverable completion (`deliverables_done`). PHASES.md per-deliverable checkboxes are **human-readable documentation**, no longer the gate. Reason: the plan part is the unit of execution and its WUs never span parts or phases, so reading them eliminates two false-fail classes the old PHASES-phase-level read suffered — (a) cross-part (a phase's deliverable row belonging to a *different* plan part of the same phase) and (b) cross-phase attribution (a deliverable filed under Phase N but built in a corrective Phase N+1). A legacy pre-ISSUE-6 plan with no `- [ ] WU-N` rows falls back to the old PHASES-phase-level read (verify-ledger reports `deliverables_source: "phases-fallback …"`). **Because these rows are now the gate, they MUST be present and accurate** — this is precisely why they are a HARD requirement, not best-effort. (A verification-only `- [ ] WU-N` placed under a `**Runtime Verification**` / `## MCP Integration Test` subsection stays exempt at the WU level too — ticked by the Step-9 `/mcp-test` gate, not `/execute-plan`.)

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

**Execution Protocol / Blocking Issue Protocol / Completion — do NOT inline; these are single-sourced.**

The Execution Protocol (Phase-Selection Loop, Step 0 task tracking, per-batch Steps B.0–B.6, Propagation Awareness Note, Post-Phase Steps), the Blocking Issue Protocol, and the Completion report all live in `~/.claude/skills/_components/execution-contract.md`. The pointer block already written above (under "Execution Policy — single-sourced") directs the executor to read them there. Do NOT re-emit any of these sections into the plan.

What you DO still write into each plan, per phase, is the phase-specific control content that the contract cannot know in advance:
- The **Execution Schedule** table (above).
- Each **Phase** block (Goal / Entry criteria / SPEC.md references) and its **work units** and **batch overview table**.
- The flat `## Work Units` checklist of `- [ ] WU-N` progress checkboxes (above).
- Any **plan-specific deviations** from the contract's defaults (non-default gates, repo-specific component paths, an explicit per-phase execution note) — written as a short "Plan-specific execution notes" paragraph that the contract's override clause defers to.

---

## Step 3.4: MCP Scenario Surface Lint (F8 — if this cycle authored or modified an mcp-tests scenario)

If this write-plan cycle authored or modified **any** MCP test scenario under a feature's
`mcp-tests/` or `docs/testing/mcp-tests/` directory, run the surface-existence lint
BEFORE writing plan files to disk:

```bash
python ~/.claude/scripts/surface_resolver.py --lint \
    --repo-root <repo-root> \
    <path/to/scenario.md> [...]
```

The script is at `~/.claude/scripts/surface_resolver.py` (symlinked from the
`claude-config` repo's `user/scripts/surface_resolver.py`).

**If the lint exits non-zero:** fix every flagged tool BEFORE the plan lands.
Each `ERROR: <file>:<line> asserts unregistered MCP tool '<name>'` line means the
asserted tool does not exist in `src-tauri/src/ipc/mcp/registrations/` (nor in
`GOLDEN_TOOL_NAMES`).  Resolution options:

1. **Tool does not exist yet** — add a PHASES.md deliverable to implement it, or
   remove the assertion from the scenario until the tool is registered.
2. **Tool exists under a different name** — correct the scenario's tool name.
3. **Tool is a non-MCP pseudo-step** (e.g., a test-harness sleep directive) — pass
   `--allow <name>` to suppress it (built-in allowlist already covers `sleep`).

**Rationale (F8 / lazy-validation-readiness):** write-plan/execute-plan authoring
scenarios asserting `evaluate_code` (d8-session-format) and missing diagnostic tools
(polyphonic) caused BLOCKED discoveries at Step-9 mcp-test — ~3 full cycles later.
This lint catches the gap at authoring time with a single cheap check.

> Skip this step if the cycle did NOT author or modify any `mcp-tests/` scenario.

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
- `complexity: mechanical | complex` — the per-part cost tier from Step 2.5's mechanical-vs-complex test (Phase 9). Default `complex` (Opus). Emit `mechanical` ONLY when every WU in the part passed the test above. This field is REQUIRED on every part — write `complexity: complex` explicitly even for complex parts so the tier is auditable and never inferred from absence.
- `phases:` — YAML list of every PHASES.md phase number this plan implements. **Multi-element lists are normal and expected** when Step 2.5 packed multiple phases into one part — e.g. `phases: [1, 2]`, `phases: [3, 4]`, `phases: [5, 6, 7]`. A singleton `phases: [N]` is correct ONLY when that one phase saturates the 8-WU cap on its own (or it's the last part and no other phase remained to pack). For a multi-feature plan, list every phase across every feature this part covers. For partitioned multi-part output (Step 2.5), each part's `phases:` lists every phase assigned to that part — not just the lowest.

### Step 4.5: Structural Gate (MANDATORY — BEFORE reporting done)

!`cat .claude/skill-config/plan-structural-gate.md 2>/dev/null || cat ~/.claude/skills/_components/plan-structural-gate.md`

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
