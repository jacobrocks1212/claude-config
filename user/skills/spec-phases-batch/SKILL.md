---
description: Decompose 1+ feature specs into PHASES.md files using parallel Sonnet subagents, with holistic cross-feature review
argument-hint: <path/to/SPEC1.md> [path/to/SPEC2.md] [...]
name: spec-phases-batch
plan-mode: never
---

# Spec Phases Batch

Decompose one or more feature specs into TDD-able implementation phases via parallel Sonnet subagents, with a holistic cross-feature review pass at the end. Produces a `PHASES.md` sibling file for each input spec. The plan is written to a file for execution via `/execute-plan` in a separate session.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. The deliverable is a written plan file, not a plan-mode interaction.

**Flow:** Load context → draft ONE self-contained plan covering all specs → write plan to file → report path to user.

**Critical: the plan must be fully self-contained.** The plan may be executed after the context window is cleared. Every execution instruction, subagent prompt template, review protocol, and completion step MUST be baked into the generated plan itself. After the plan is written, it is the sole source of truth.

All phase-decomposition constraints from `/spec-phases` carry over: phase size guidelines, red-flag detection, PHASES.md format, cross-linking back to spec, integration notes for subsequent phases.

---

## Step 1: Load All Context

### 1a. Resolve SPEC.md Paths

- `$ARGUMENTS` must contain 1+ `.md` paths to SPEC.md files. If none are provided, use **AskUserQuestion** to ask for them.
- For each path, confirm the file exists. If not, report and exclude it.
- Note the feature name for each (directory name, e.g. `foundation`, `auth-bootstrap`).

### 1b. Read Everything

For **each** SPEC.md:
1. Read the SPEC.md file **in full**
2. Check for an existing sibling PHASES.md — if it already exists, note it (may be updating rather than creating)
3. Note any wave/phased-spec constraints mentioned in the spec's frontmatter or body

Also read:
- `CLAUDE.md` (project root) — for quality gates, critical rules, directory layout
- `docs/features/architecture/SPEC.md` — skim Locked Decisions and Tech Stack for cross-cutting context

### 1c. Identify Cross-Feature Constraints

From each input spec's `**Depends on:**` block (the source of truth for cross-feature coupling) and the specs themselves, identify:
1. **Cross-feature dependencies** — which features depend on which (e.g. auth-bootstrap depends on foundation at implementation time)
2. **Phased specs** — features that implement across multiple waves (auth-bootstrap, orchestration, tui). These specs' PHASES.md files must be scoped to the appropriate wave(s), with later-wave phases noted as placeholders.
3. **Shared-file ownership** — features that touch the same files (e.g. `src/cli/main.py` owned by orchestration; auth-bootstrap registers subcommands into it). Phase decomposition must assign clear ownership.
4. **Entry-criteria alignment** — Phase N of feature A might depend on Phase M of feature B completing first. These cross-references must be explicit in the PHASES.md files.
5. **Dependency-chain depth and speculation flagging** — Compute the longest dependency chain across the input specs (derived from the specs' `**Depends on:**` blocks). Specs deep in the chain (2+ hops from a root spec) produce **speculative** phase breakdowns because their implementation details will be informed by actual implementation decisions in earlier specs. Example: if the batch includes A → B → C → D, then C's and D's phase breakdowns are speculative — they will likely change once A and B are actually implemented and their Implementation Notes reveal real interfaces, gotchas, and file structures.

   **Flag these specs explicitly:**
   - In the plan's Decomposition Schedule, mark them with a `Speculative` column
   - In the subagent prompt for each speculative spec, instruct the subagent to add a **Speculation Notice** banner at the top of the PHASES.md
   - The banner must name the specific upstream dependencies whose implementation will inform this breakdown and state that the phases are likely to change after those dependencies are implemented

   **Still produce the PHASES.md** — speculative breakdowns are valuable as a planning scaffold even if they change. But they must be honest about their confidence level.

6. **Cross-feature contract verification (HARD REQUIREMENT):** When a phase in input spec A plans against an API, IPC command, capnp field, or symbol that belongs to a sibling feature B, you MUST verify that B has **actually shipped** that contract — not merely specced it. Grep the repo for the real symbol before including it in the plan:
   - If the grep resolves: proceed, cite the file:line in the PHASES.md cross-feature integration notes.
   - If the grep returns zero hits: the API does not exist yet. The phase must be marked **Speculative / Blocked on B** and must NOT be planned as if the API is available. Raise this as a cross-feature dependency gap in the plan and surface it to the orchestrating agent.
   - "B's SPEC.md describes this API" is NOT sufficient — specs are plans, not deliverables. Only a live symbol in the tree confirms B shipped it.

   `d8-track-pattern-interaction` built an entire integration phase against `d8-effect-chains`'s `chainParam` IPC before it existed. A single grep would have caught it.

---

### 1d. Collect Candidate Touchpoints Across All Input Specs (REQUIRED before the audit gate below)

Before the touchpoint audit fires, enumerate the **existing source files** that the proposed phase decompositions across **all input specs** will modify. For each spec in the batch, pull from:
- The SPEC's "Technical Design" / "Files likely modified" sections
- Shared-file ownership entries you just identified in Step 1c (these are high-signal — multiple features touching the same file is a bloat risk amplifier)
- Any files you read while assessing cross-feature constraints that the plans will touch

Merge into one deduplicated list of repo-root-relative paths. Hold it in working memory — the gate consumes it.

The audit subject is the **source files the planned implementations will modify**, NOT the parent plan markdown or the per-spec PHASES.md documents. Skipping the audit because "this is documentation work" is incorrect — the documentation schedules source modifications, which is exactly what the audit checks.

---

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

---

## Step 2: Draft the Comprehensive Plan

Write a single, **fully self-contained** plan covering the phase decomposition of ALL input specs. The plan must include every instruction needed for autonomous execution — including subagent prompts, review protocol, cross-feature holistic review, and commit steps.

The plan MUST contain all of the following sections.

### Plan Structure

The plan must follow this structure exactly:

---

```
# Spec Phases Decomposition Plan — [feature1] [+ feature2] [+ ...]

**SPEC.md files:**
- [path1] ([feature1])
[- [path2] ([feature2])]

**Architecture SPEC.md:** [path]

**Total specs to decompose:** N
**Phased-spec constraints:** [list any specs that must be scoped to specific waves per their `**Depends on:**` blocks]

---

## MANDATORY RULES — DO NOT SKIP ANY STEP

1. Each spec gets its own Sonnet subagent for phase decomposition — subagents run in parallel when no cross-feature file conflicts exist
2. Every subagent's output (PHASES.md) is reviewed by the orchestrating agent for quality and spec fidelity
3. After all individual PHASES.md files are written, a holistic cross-feature review identifies and fixes dependency conflicts, shared-file ownership issues, and entry-criteria misalignment
4. PHASES.md files are written as sibling files to the SPEC.md (same directory)
5. Phased specs (features spanning multiple waves) produce a PHASES.md scoped to the appropriate wave(s), with later-wave phases as documented placeholders
6. All results are committed and pushed as a single commit after the holistic review passes
7. This plan is self-contained — follow it exactly as written without relying on external context

---

## Decomposition Schedule

| # | Feature | SPEC.md Path | PHASES.md Path (output) | Phased-spec? | Wave scope | Parallel? | Speculative? |
|---|---------|-------------|------------------------|--------------|------------|-----------|--------------|
| 1 | [name]  | [path]      | [path]                 | No / Yes (W1/W2/...) | [wave] | Yes/Solo | No — root of chain |
| 2 | [name]  | [path]      | [path]                 | ...          | ...        | ...       | Yes — depends on [feature] implementation (2 hops) |
| ... | ...  | ...         | ...                    | ...          | ...        | ...       | ... |

**Speculation notice:** Specs marked "Speculative" in the table above are 2+ dependency hops from a root spec in the batch. Their phase breakdowns are produced as planning scaffolds but are likely to change once upstream dependencies are actually implemented and their Implementation Notes reveal real interfaces, file structures, and gotchas. Each speculative PHASES.md includes a banner documenting this.

---

## Per-Spec Subagent Prompts

[For each spec, write the FULL subagent prompt that will be sent to a Sonnet subagent. The prompt must be self-contained — the subagent has no conversation context.]

### Subagent: [feature] PHASES.md

**Prompt to send to subagent:**

[The prompt must include:]
- The full SPEC.md content (quoted or summarized — enough for the subagent to decompose without reading additional files)
- Relevant cross-feature dependency context (dependency graph, phased-spec constraints) derived from the specs' `**Depends on:**` blocks in Step 1c
- Cross-feature dependency constraints (which other features' phases this feature's phases depend on, and vice versa)
- The exact PHASES.md output format (copied from the /spec-phases skill format):

  ```markdown
  # Implementation Phases — {Feature Name}

  > Phases for [`SPEC.md`](./SPEC.md)

  ### Phase N: {Title}

  **Scope:** {Clear description of what's built}

  **Deliverables:**
  - [ ] {Concrete code output 1}
  - [ ] {Concrete code output 2}
  - [ ] Tests: {What tests verify this phase}

  !`cat .claude/skill-config/phases-runtime-verification.md 2>/dev/null || cat ~/.claude/skills/_components/phases-runtime-verification.md`

  **Prerequisites:** None (first phase) OR {specific prior phase work, including cross-feature}

  **Files likely modified:**
  - `path/to/file` — {what changes}

  **Testing Strategy:**
  {How this phase is verified in isolation}

  **Integration Notes for Next Phase:**
  - {Gotcha or pattern established that the next phase needs to know}
  - {Decision made here that affects subsequent work}
  ```

- Phase size guidelines:
  - **Too Small:** Less than 1 hour of implementation, no distinct testing story, could combine with adjacent phase
  - **Too Large:** Spans multiple major components, testing requires >3 mock boundaries, too many "and then..." statements
  - **Just Right:** Single component or clear subsystem, testable with 1-2 mock boundaries, clear deliverable ("X can now do Y")
- Red flags to surface (don't silently resolve — document in the PHASES.md):
  - Circular dependencies between phases
  - Unclear spec scope that prevents bounding a phase
  - Integration explosion (every phase touches every file)
  - Testing impossible without full system
- For phased specs: explicit instruction to scope phases to the specified wave(s) and add "Future Phases (not yet decomposed)" placeholders for later waves
- **For speculative specs (marked in Decomposition Schedule):** instruct the subagent to prepend a Speculation Notice banner immediately after the PHASES.md title. The banner format:

  ```markdown
  > **⚠️ Speculation Notice:** This phase breakdown is speculative. It depends on implementation
  > decisions in [upstream feature 1] and [upstream feature 2] that have not been made yet.
  > Phase boundaries, file paths, prerequisite details, and integration notes are best-effort
  > estimates based on the current SPEC.md and will likely change once upstream Implementation
  > Notes are available. Re-run `/spec-phases` (or `/spec-phases-batch`) after upstream features
  > are implemented to produce a grounded breakdown.
  >
  > **Dependency chain:** [root feature] → [mid feature] → **[this feature]** (N hops from root)
  ```

  Additionally, each individual phase within a speculative PHASES.md must note in its **Prerequisites** section which specific upstream phases it depends on and that those phases' actual Implementation Notes don't exist yet.
- The exact output file path where the subagent must write the PHASES.md
- Instruction to read the SPEC.md from disk (provide the path) rather than relying on the prompt summary, for full fidelity

[Repeat for each spec]

---

## Execution Protocol

### Step E.0: Initialize Task Tracking (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/task-tracking.md`

### Step E.1: Launch Subagents

!`cat ~/.claude/skills/_components/subagent-launch.md`

### Step E.2: Review Batch Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed to Step E.3 until the review protocol below is fully executed and produces a structured review report with a verdict. Reading a few files and saying "looks correct" is NOT a review.

!`cat ~/.claude/skills/_components/subagent-review.md`

### Step E.3: Holistic Cross-Feature Review (MANDATORY — DO NOT SKIP)

After ALL individual PHASES.md files are written and individually reviewed, perform a cross-feature review:

**Dependency Alignment:**
- For each cross-feature dependency identified in Step 1c, verify the PHASES.md files reference each other correctly
- Example: if auth-bootstrap Phase 1 says "Entry criteria: Foundation Phase 1 complete", verify that foundation Phase 1 exists and its deliverables are sufficient for auth-bootstrap to proceed
- Fix any misaligned cross-references

**Shared-File Ownership:**
- Scan all PHASES.md files for overlapping file paths (two features' phases modifying the same file)
- Resolve ownership: one feature owns the file; the other contributes via a well-defined interface
- Example: if both foundation and auth-bootstrap create `main.py health`, assign ownership to one and have the other contribute a helper function
- Update the PHASES.md files to reflect resolved ownership

**Phase Ordering Consistency:**
- Verify the cross-feature phase ordering is implementable — no feature's Phase N requires another feature's Phase M that hasn't been scheduled yet in the cross-feature ordering from Step 1c
- If ordering issues found, adjust phase boundaries or add explicit "blocked by" notes

**Entry-Criteria Completeness:**
- Every phase with cross-feature dependencies must have explicit entry criteria naming the specific feature + phase number it depends on
- Vague references like "foundation must exist" are insufficient — must be "Foundation Phase 2 (Pydantic Models) complete"

**Speculation Verification:**
- For every PHASES.md marked speculative in the Decomposition Schedule, verify the Speculation Notice banner is present and names the correct upstream dependencies
- Verify each speculative phase's Prerequisites section acknowledges that upstream Implementation Notes don't exist yet
- If a spec was marked speculative but actually has no deep dependencies (false positive from chain analysis), remove the banner

Fix all issues found. Document fixes in a brief "Cross-Feature Review Notes" comment at the bottom of each affected PHASES.md.

### Step E.4: Commit and Push (MANDATORY — DO NOT SKIP, use "Spec decomposition" message format)

!`cat .claude/skill-config/commit-policy.md 2>/dev/null || cat ~/.claude/skills/_components/commit-and-push.md`

---

## Completion

Print a completion report:

   ## ✅ Spec Phases Decomposition — Complete

   **Specs decomposed:** [list]

   **Results:**
   | Feature | PHASES.md | Total Phases | Wave Scope | Key Dependencies |
   |---------|-----------|-------------|------------|-----------------|
   | [name]  | [path]    | N           | W1         | None            |
   | [name]  | [path]    | M (W1 scope) + K placeholders | W1/W2/W4/W5 | foundation P1 |

   **Cross-feature issues resolved:**
   - [list any ownership conflicts, dependency misalignments, or ordering fixes applied]

   **Speculative breakdowns (will need re-phasing after upstream implementation):**
   - [list any PHASES.md files flagged speculative, with their dependency chains]
   - If none: "No speculative breakdowns — all specs are root-level or 1 hop from root"

   **Next step:** `/implement-phase-batch [paths to PHASES.md files]`

---

## Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`
```

---

## Step 4: Write Plan File

!`cat ~/.claude/skills/_components/plan-file-output.md`
