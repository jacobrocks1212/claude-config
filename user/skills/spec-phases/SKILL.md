---
name: spec-phases
description: Break a spec into logical implementation phases with detailed integration notes. Use after /spec creates a feature spec.
argument-hint: <spec-path>
---

# Spec Phase Decomposition

## Overview

Analyzes a feature spec and decomposes it into well-bounded implementation phases. Each phase is self-contained, testable in isolation, and includes integration notes for subsequent phases.

**Announce at start:** "I'm using the /spec-phases skill to decompose this spec into implementation phases."

## Arguments

- `spec-path` (required): Path to spec file (e.g., `docs/features/my-feature/SPEC.md`)
- `--batch` (optional): autonomous mode. Skip the Step 3 user picker; act on red-flag detection by writing NEEDS_INPUT.md.

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation (typically from `/lazy-batch` via `/plan-feature`).

- Strip `--batch` from `$ARGUMENTS` before resolving the spec path.
- **Skip the Step 3 `AskUserQuestion` picker.** The user is not present; the picker would block forever.
- Still run the Step 3 red-flag detection logic at the bottom of this file (circular dependencies, unclear scope, integration explosion, testing impossible). If ANY red flag triggers, **halt** with NEEDS_INPUT.md (see below) — do NOT proceed to Step 4 with phases the human would have wanted to adjust.
- The Step 6 subagent review gate still runs — review is read-only structured analysis, no human prompts.

**Post-research positioning:** `/spec-phases --batch` runs *after* Phase 3 of `/spec` has finalized SPEC.md, so by definition `RESEARCH.md`/`RESEARCH_SUMMARY.md` are already on disk. This skill is therefore eligible to write `NEEDS_INPUT.md` per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`. Red-flag detection is genuine design judgment — the kind of decision the halting rule permits.

### Halt protocol — `NEEDS_INPUT.md`

When red-flag detection triggers under `--batch`:

1. Compute `{spec-dir}/NEEDS_INPUT.md` (sibling of the SPEC.md passed as `$ARGUMENTS`).
2. Write the sentinel per `~/.claude/skills/_components/sentinel-frontmatter.md`. The body MUST use the **rich-body convention** (`## Decision Context` H2 with one H3 per `decisions[i]`, each carrying `**Problem:**` / `**Options:**` / `**Recommendation:**`) defined in that component. The orchestrator re-prints this body verbatim before calling `AskUserQuestion`.

   Skeleton (see the component for the full template):

   ```markdown
   ---
   kind: needs-input
   feature_id: {feature-slug derived from spec-dir}
   written_by: spec-phases
   decisions:
     - <one-line description of red flag 1>
     - <one-line description of red flag 2>
   date: {today}
   next_skill: spec-phases
   ---

   # /spec-phases --batch — Needs Input

   ## Decision Context

   ### 1. <red-flag title — must equal decisions[0] verbatim>

   **Problem:** <Which phase boundary is at risk and why. Cite the SPEC section
   and the affected phases.>

   **Options:**
   - **<resolution A>** — <description with tradeoffs.>
   - **<resolution B>** — <description with tradeoffs.>

   **Recommendation:** <option> — <one-sentence justification.>

   ### 2. <next title matching decisions[1]>
   ...
   ```

3. **Echo the entire `## Decision Context` section to chat output** before returning (per Producer responsibilities in `sentinel-frontmatter.md`).
4. STOP. Do NOT write PHASES.md. Do NOT invoke the Step 5 subagent.

## Task Tracking (MANDATORY — DO NOT SKIP)

!`cat .claude/skill-config/cog-doc-track-open.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-open.md`

Load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Read context", description: "Read spec, architecture docs, related code" })`
2. `TaskCreate({ subject: "Analyze phase boundaries", description: "Identify natural boundaries, dependency chains, testability" })`
3. `TaskCreate({ subject: "Draft PHASES.md", description: "Write phase decomposition with deliverables, prerequisites, testing strategy" })`
4. `TaskCreate({ subject: "Review and refine", description: "Cross-check against spec, validate phase ordering, red-flag detection" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

## Workflow

### Step 1: Read Context

1. Read the spec file completely
2. Identify related files:
   - Architecture docs (`ARCHITECTURE.md`, `docs/architecture/`)
   - Existing related code
   - Any referenced dependencies

**DSP / audio / quality features — Baseline Health (REQUIRED before Step 2):**
If the spec is audio, DSP, or quality-related (reverb, EQ, gain, mix, pipeline routing, quality gates), run the relevant baseline before authoring any phases and record results in a `## Baseline Health` block in `RESEARCH_SUMMARY.md`:
- `npm run qg:golden` — perceptual quality (Zimtohrli distance per contract)
- `npm run qg:realtime` — real-time factor / xrun rate
- `npm run qg:multichannel` — multichannel isolation / crosstalk

Record actual numbers (e.g. `Zimtohrli: 0.158–0.259, target 0.010`). Never plan remediation against a quality state that hasn't been measured. (`analysis-informed-dsp-updates` and `audio-quality-analysis` both expanded 2–3× because Phase 1 targeted a baseline nobody had measured.)

### Step 1.5: Read Upstream PHASES.md (per hard dep)

The spec carries a `**Depends on:**` block. Use it to load phase-level decisions from upstream features so the new phase plan integrates against what was actually built, not what the upstream's SPEC originally claimed.

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Procedure:

1. Parse the SPEC's `**Depends on:**` block. Filter to `kind == hard`.
2. For each hard dep, resolve the upstream directory using the resolution protocol.
3. Apply the completion check. For each upstream where the check passes, read:
   - `<upstream-dir>/PHASES.md` in full, paying particular attention to Implementation Notes blocks — they document what actually shipped vs. what was originally planned.
   - Skip non-Complete upstreams; there's nothing settled to integrate against.
4. From each upstream PHASES.md, extract any decisions, contracts, file paths, or invariants that the current spec's phases will need to consume. Hold these in working memory for Step 2 (phase boundary analysis) and Step 5 (PHASES.md drafting).
5. If a hard dep's upstream is Complete but has no PHASES.md (older feature, never decomposed), note this — surface it as a quality issue in the final PHASES.md's `## Cross-feature Integration Notes` section.

If the block is missing, malformed, or all deps are soft/composes/incomplete, skip this step with a one-line note. Do NOT abort.

### Step 2: Analyze Phase Boundaries

Consider these factors when identifying phase boundaries:

**Component Dependencies:**
- What can be built in isolation?
- What requires prior work to exist?
- Are there interfaces that need to be defined early?

**Testing Isolation:**
- Can this phase be verified without subsequent work?
- What mocks/stubs are needed for isolation testing?

**Integration Complexity:**
- Where are the "seams" between components?
- What gotchas might trip up later phases?

**Risk Areas:**
- Which phases have highest uncertainty?
- What should be prototyped early?

**HARD RULE — Phase 1 must cross the boundary (applies to any pipeline feature):**
If the feature crosses any boundary in the taxonomy in `phases-testing-strategy.md` (process: sidecar ↔ Rust; serialization: capnp/N-API; IPC: Tauri commands; thread: audio-callback handoff), **Phase 1 MUST include a minimal full-stack integration test** — one real input driven through the real production path → one far-side observable asserted. Do NOT defer this to a terminal phase. `d7-macros-scenes` absorbed 10 corrective fixes in Phase 4 because no prior phase drove the full `pattern → sidecar → IPC → engine → output` path; that failure mode is prevented only if Phase 1 closes the loop.

**Verification is distributed per-phase — NOT terminal-only:**
Do NOT design a plan where all MCP/runtime verification is collected into a single trailing "MCP Test Phase N+1". Each phase must carry its own verifiable slice. A dedicated terminal-only MCP phase is a red flag for poor verification distribution; restructure the phase boundaries instead. (`d7-multi-timbral`, `hard-state-reload`, `vst3-au-wrapper-export` all show the corrective-tail pattern that results from terminal-only MCP phases.)

**Sentinel triage at authoring time (REQUIRED for any phase with MCP assertions):**
When authoring a phase's MCP test assertions, classify each assertion NOW — at authoring time, not at completion:
- `permanently-non-observable` — the behavior is structurally inaccessible via MCP (e.g., raw PCM callback timing)
- `device-deferred` — requires hardware not present in the cloud session (MIDI, audio interface)
- `cloud-deferred` — technically observable but the cloud environment lacks the prerequisite (build artifact, specific hardware config)

Record the classification and the sentinel it maps to (`SKIP_MCP_TEST.md`, `DEFERRED_NON_CLOUD.md`, etc.) inline in the phase, not retroactively. `learn-system-v2` Phase 6 was reopened because a single `SKIP_MCP_TEST.md` bundled testable and untestable items that hadn't been classified when the phase was authored.

**Collect candidate touchpoints (REQUIRED before the audit gate below):**

Before the touchpoint audit fires, enumerate the **existing source files** the proposed phases will modify. Pull from:
- The SPEC's "Technical Design" / "Files likely modified" sections, if present
- Each candidate phase boundary you just synthesized — for each, list the files you'd expect that phase to edit
- Any files you read or grepped during boundary analysis that the plan will touch

Hold this list in working memory (or jot it in your reasoning) — the gate below consumes it. The audit is about the source files the PLAN will modify, NOT about the PHASES.md document you're about to write. Skipping the audit because "this is documentation work" is incorrect; PHASES.md is the planning artifact, but the audit subject is the source files PHASES.md schedules for modification.

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

### Step 2.7: Runtime Assumption Validation (where appropriate — BEFORE DRAFTING PHASES)

Some phase plans rest on assumptions about how the *running* system behaves — the actual shape of data crossing a boundary, whether an existing code path fires, the live output of a separate process, the rendered result of an audio/effect path. These are NOT provable from source: reading the types or the function body can mislead (a value's runtime shape, a stale build, a module-singleton split, timing). Where the plan rests on a load-bearing **runtime-coupled** assumption, validate it against the running system BEFORE committing the phases — or schedule an explicit early validation spike. Do not plan (and then implement) against a code-read assumption the runtime might contradict.

!`cat .claude/skill-config/phases-runtime-validation.md 2>/dev/null || cat ~/.claude/skills/_components/phases-runtime-validation.md`

### Step 3: Propose Phase Structure

**Under `--batch`:** skip the picker below. Run the red-flag detection block at the end of this file. If clean, proceed to Step 4. If any red flag triggers, halt with NEEDS_INPUT.md per the Batch Mode section above.

**Interactive mode:** present proposed phases to user with `AskUserQuestion`:

```
Proposed phase breakdown for {spec name}:

Phase 1: {title}
- Scope: {what's built}
- Risk: {low/medium/high} - {why}
- Can be verified independently: {yes/no}

Phase 2: {title}
- Scope: {what's built}
- Depends on: Phase 1 ({specific dependency})
- Risk: {low/medium/high}

...

Questions:
1. {any ambiguities}
2. {clarifications needed}

Adjust boundaries or proceed?
```

Wait for user approval before writing.

### Step 4: Initialize Task Tracking (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/task-tracking.md`

### Step 5: Launch Subagent to Write Phases File

Create a **separate** `PHASES.md` file in the **same directory** as the spec file. Do NOT add phases inline to the spec.

- Spec: `docs/features/my-feature/SPEC.md`
- Phases: `docs/features/my-feature/PHASES.md`

The phases file links back to the spec for context.

#### Subagent Dispatch

!`cat ~/.claude/skills/_components/subagent-launch.md`

Launch a Sonnet subagent with:
- The full SPEC.md content
- The approved phase structure from Step 3
- The PHASES.md output format below
- Instruction to write the file at the resolved path

**PHASES.md Output Format:**

```markdown
# Implementation Phases — {Feature Name}

> Phases for [`SPEC.md`](./SPEC.md)

## Cross-feature Integration Notes

Phase-level dependencies on completed upstream features, extracted from each upstream's PHASES.md during /spec-phases Step 1.5. Phase plans below MUST honor these; deviations require /realign-spec before implementation.

- **<upstream-feature-id> (kind=hard, Complete):** <one or two lines: the upstream phase(s) this feature consumes, the actual API/contract/path/invariant locked in by the upstream's PHASES.md, and which downstream phase(s) below depend on it>
- ...

(Omit this section entirely if there are no hard deps on Complete upstreams. If a hard upstream is Complete but lacks PHASES.md, list it here with `(no PHASES.md — verify against SPEC.md and Implementation Notes)` and surface as a quality issue.)

### Phase 1: {Title}

**Scope:** {Clear description of what's built}

**Deliverables:**
- [ ] {Concrete code output 1}
- [ ] {Concrete code output 2}
- [ ] Tests: {What tests verify this phase}

**Minimum Verifiable Behavior:** {The smallest runtime-observable proof that this phase's slice is wired — expressed as a runnable command, MCP assertion, or observable UI state. If the behavior does not exist yet, replace with a `- [ ]` Runtime Verification checklist row. This is NOT optional; "unit tests pass" is not a valid entry here.}

!`cat .claude/skill-config/phases-runtime-verification.md 2>/dev/null || cat ~/.claude/skills/_components/phases-runtime-verification.md`

**Prerequisites:** None (first phase) OR {specific prior phase work}

**Files likely modified:**
- `path/to/file.ts` - {what changes}

**Testing Strategy:**
{How this phase is verified in isolation}

**Integration Notes for Next Phase:**
- {Gotcha or pattern established that Phase 2 needs to know}
- {Decision made here that affects subsequent work}
- {Interface or behavior to build upon}

---

### Phase 2: {Title}

**Scope:** {Clear description}

**Deliverables:**
- [ ] {Concrete code output 1}

**Minimum Verifiable Behavior:** {The smallest runtime-observable proof that this phase's slice is wired. Same rule as Phase 1 — runnable command, MCP assertion, or `- [ ]` row if the behavior doesn't yet exist. "Unit tests pass" is not valid.}

**Runtime Verification** *(checked by integration test or manual testing):*
- [ ] {Observable runtime behavior if applicable — omit section if none}

**Prerequisites:**
- Phase 1: {Specific dependency - what must exist}

**Files likely modified:**
- `path/to/file.ts` - {what changes}

**Testing Strategy:**
{How this phase is verified}

**Integration Notes for Next Phase:**
- {Notes for Phase 3}

---
```

!`cat .claude/skill-config/phases-testing-strategy.md 2>/dev/null || cat ~/.claude/skills/_components/phases-testing-strategy.md`

**Review Guardrails (per phase):** the drafting subagent must front-load the review pitfalls most likely to recur on each phase's files, so implementation gets them right the first time instead of fielding them in review. Apply the protocol below when present and include its output per phase. This is a no-op outside repos that configure a guardrail source:

!`cat .claude/skill-config/phases-review-guardrails.md 2>/dev/null || cat ~/.claude/skills/_components/phases-review-guardrails.md`

### Step 6: Review Subagent Output (MANDATORY GATE — DO NOT SKIP OR SHORTCUT)

**This is a blocking gate.** You CANNOT proceed until the review protocol below is fully executed and produces a structured review report with a verdict.

!`cat ~/.claude/skills/_components/subagent-review.md`

### Step 7: Cross-link and Update Spec

1. If the spec previously had an inline `## Implementation Phases` section, **replace** it with a link:
   ```markdown
   ## Implementation Phases

   See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.
   ```
2. Add any new "Open Questions" discovered during analysis to the spec
3. Update "Decisions Log" in the spec with phase boundary rationale

### Step 8: Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`

## Phase Size Guidelines

**Too Small:**
- Less than 1 hour of implementation time
- No distinct testing story
- Could be combined with adjacent phase

**Too Large:**
- Spans multiple major components
- Testing requires >3 mock boundaries
- Too many "and then..." statements

**Just Right:**
- Single component or clear subsystem
- Testable with 1-2 mock boundaries
- Clear deliverable ("X can now do Y")

## Red Flags - Ask User

1. **Circular dependencies** - Phase 2 needs Phase 3 which needs Phase 2
2. **Unclear scope** - Spec is vague, phases can't be bounded
3. **Integration explosion** - Every phase touches every file
4. **Testing impossible** - Can't test without full system
5. **Platform/variant expansion without a gate phase** - If the plan includes per-platform, per-variant, or per-target phases (e.g. macOS / Windows / Linux export formats, multiple WebView targets, multiple plugin formats), these are NOT authored until a prototype "gate phase" closes with an explicit go decision confirming the approach is sound. `clap-target-export` authored four detailed per-platform WebView phases then superseded all four — roughly half the plan was write-off churn. Author only the gate phase; defer expansion phases until the gate closes.

!`cat .claude/skill-config/phases-example-output.md 2>/dev/null || cat ~/.claude/skills/_components/phases-example-output.md`

## When to Use This Skill

Use `/spec-phases` after:
- `/spec` creates a new feature spec
- You're revisiting a spec that needs implementation planning
- An existing spec has only a rough "Implementation" section

Do NOT use if:
- Spec doesn't exist yet (use `/spec` first)
- Already well-defined phases exist
- Feature is small enough for single implementation
