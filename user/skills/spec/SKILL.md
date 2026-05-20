---
description: Brainstorm, research, and draft a feature spec
allowed-tools: ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "AskUserQuestion", "Agent", "WebSearch"]
name: spec
---

# Feature Spec Workflow

You are helping the user create a new feature specification. This is a **3-phase** interactive workflow. Follow each phase strictly — do not skip ahead.

**User's feature description:**
$ARGUMENTS

---

## Task Tracking (MANDATORY — DO NOT SKIP)

Before any work, load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Phase 0: Project context discovery", description: "Read CLAUDE.md, find spec directory, read related specs" })`
2. `TaskCreate({ subject: "Phase 1: Brainstorm baseline spec", description: "Interactive brainstorming, iterative spec drafting" })`
3. `TaskCreate({ subject: "Phase 2: Research prompt", description: "Draft and save Gemini deep research prompt" })`
4. `TaskCreate({ subject: "Phase 3: Finalize spec", description: "Integrate research, finalize SPEC.md, cross-boundary validation" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

---

## Phase 0: Project Context Discovery

Before starting, understand the project:

1. Read `CLAUDE.md` (if exists) to understand current architecture and constraints.
2. Find where specs/docs live:
   - Check for `docs/features/`, `docs/specs/`, `specs/`, or `docs/` directories
   - If none exist, propose creating `docs/specs/` and confirm with user
3. Read any existing specs that relate to the proposed feature — avoid contradictions.
4. Identify the tech stack and key constraints from the codebase.

---

## Phase 1: Brainstorm the Baseline Spec

**Goal:** Nail down the core feature concept, scope, and key design decisions through interactive dialogue.

### Step 1a: Understand Before Architecting

Before asking about architecture, technology, or infrastructure, ensure you understand what's actually being built and why. The depth of this step depends on the feature:

- **Automating existing workflows:** Ask the user (or end user, if the developer is a proxy) to describe the current process step by step. Understand where time is lost and what requires human judgment vs. what's mechanical. If the developer is building for someone else, ask for the end user's own description — summaries often miss the real pain points.
- **New capabilities (no existing workflow):** Clarify the desired outcome and key interactions. What does success look like from the user's perspective?
- **Technical/infrastructure features:** Clarify the constraints and integration points. Workflow interviews don't apply here.

Do NOT make architecture or technology decisions until the problem space is understood.

### Step 1b: Resolve Dependencies and Dependees (BLOCKING — before architecture brainstorm)

Before brainstorming architecture, perform an **explicit mechanical search** across all existing specs to identify (a) upstream features this one depends on, and (b) existing downstream features that depend on this one (relevant when this is a re-spec or expansion of a stub). The dependency block is a **hard checkpoint** — Phase 3 will refuse to finalize SPEC.md without it.

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Do NOT skip the mechanical search and rely on intuition or Phase 0 context alone — that's exactly how dep blocks drift into "(none)" when there are real deps. Run every step below.

#### 1b.1. Enumerate the candidate set (mechanical)

1. **List all existing SPEC.md files.** Use the spec directory resolved in Phase 0:
   ```bash
   # Algobooth-style layout
   ls {spec-dir}/*/SPEC.md 2>/dev/null
   # Generic fallback
   find {spec-dir} -name SPEC.md -not -path "*/{this-feature-slug}/*"
   ```
   Skip the feature being authored (if a directory already exists for it).

2. **Read queue/ROADMAP if present.** If `docs/features/queue.json` exists, read it to map feature-id → directory and tier. If `docs/features/ROADMAP.md` exists, read it to learn which features are Complete vs. pending — `hard` deps on Complete upstreams will trigger reality-check via `/realign-spec` in `/lazy` Step 4.6.

3. **Read any project-level dependency catalog** if it exists (e.g., `docs/features/dependency-audit.md`, `docs/features/PARTITIONING.md`). These pre-classify coupling between features and are gold for candidate selection.

#### 1b.2. Search for upstream dependencies (what THIS feature consumes)

For each candidate SPEC found in 1b.1, identify whether the new feature depends on it. Use both keyword search and section reading:

1. **Extract load-bearing terms** from the user's feature request and Phase 0 synthesis: API names, data types, subsystem names, capability terms. List them.

2. **Grep across all candidate SPECs** for those terms:
   ```bash
   # For each load-bearing term:
   grep -l -i "<term>" {spec-dir}/*/SPEC.md
   ```
   Record matches.

3. **Grep across candidate SPECs for things they EXPOSE** that this feature might consume. Common exposure patterns:
   ```bash
   grep -l -E "^## (Public API|Exposes|Surface|Exports|Provides|IPC|MCP Tools)" {spec-dir}/*/SPEC.md
   grep -l -E "(provides|exposes|exports|publishes|emits|owns)" {spec-dir}/*/SPEC.md
   ```

4. **For each matching SPEC**, open it and read the Executive Summary, Technical Design, and any "Public API"/"Exposes" sections. For each, decide:
   - Does the new feature's design require something this upstream provides? If yes → candidate dep.
   - Classify kind:
     - **hard** — new feature's design hinges on the upstream's concrete contract (API shape, schema, IPC channel). Phase planning will need to read this upstream's PHASES.md.
     - **soft** — new feature needs the upstream to exist but not its impl specifics.
     - **composes** — new feature builds atop the upstream as a peer/extension.
   - Capture a one-sentence reason (used for the dep block's reason field).

#### 1b.3. Search for downstream dependees (what depends on THIS feature)

If this is a re-spec, stub expansion, or expansion of an existing concept, downstream features may already declare a dep on this feature. Surface them so the user knows what will need updating if this SPEC changes contract shape.

1. **Determine the feature-id** for this feature (kebab-case of the name).

2. **Grep all existing SPECs' Depends-on blocks** for this id:
   ```bash
   # Find SPECs that reference this feature-id in their dep block:
   grep -l -E "^- {feature-id} — (hard|soft|composes)" {spec-dir}/*/SPEC.md
   ```
   Also try common variants of the feature-id if the new name might already be referenced under a different slug.

3. **Grep advanced-feature catalogs and research summaries** for the feature-id or its keywords:
   ```bash
   grep -l -i -E "<feature-id>|<load-bearing-terms>" docs/features/*RESEARCH*.md docs/features/*AUDIT*.md docs/features/*PARTITIONING*.md 2>/dev/null
   ```

4. For each downstream dependee found, record: `feature-id`, the kind they declared, and the file path. These are not added to the new SPEC's Depends-on block — they're recorded as a side note for the user.

#### 1b.4. Present findings in chat (BEFORE AskUserQuestion)

Surface a single chat-visible block before any picker. The picker UI truncates option descriptions, so the user must see the full evidence inline. Use this structure:

```
## Dependency Search Results

### Upstream candidates (would go into this feature's Depends on: block)

| Feature-id | Kind | Reason | Evidence (file:section) | Confirm? |
|------------|------|--------|--------------------------|----------|
| <id> | hard | <one sentence> | <path>:<section heading> | recommend yes |
| <id> | soft | <one sentence> | <path>:<section heading> | recommend yes/no |
...

(If zero candidates after the search, write: "No upstream dependencies found. Dep block will be `**Depends on:** (none)`.")

### Existing downstream dependees (other SPECs already depending on this feature-id)

| Downstream feature-id | Kind they declared | File |
|-----------------------|--------------------|------|
| <id> | hard | <path>/SPEC.md |
...

(If zero, write: "No existing dependees — this is a leaf or greenfield feature.")

**Implication if contract shifts during this /spec:** the dependees listed above will need to be reality-checked by `/realign-spec` (which `/lazy` runs automatically). No action needed now — just noting it.
```

#### 1b.5. Confirm via AskUserQuestion (only if non-obvious)

If the upstream candidate set has any rows the user might want to add/remove/reclassify, use `AskUserQuestion` to confirm:
- One question per ambiguous candidate, with options like "Keep as hard", "Reclassify as soft", "Drop — not a real dep".
- If every candidate is unambiguous (clear hard deps with strong evidence), skip the picker and proceed.

Do NOT ask about dependees — they're informational, not authored here.

#### 1b.6. Record the dep block immediately

Write the confirmed dep block into the in-progress SPEC.md draft using the schema's Form A or Form B verbatim. Treat it as a first-class section, not a TBD placeholder. It will iterate alongside the rest of the spec during brainstorming, but the *shape* must be correct from this point forward.

If you find yourself wanting to defer this ("we'll figure out deps later"), STOP. Deferral is how the look-back mechanism breaks. Lock in the best-evidence block now; revise as brainstorming surfaces new dependencies.

### Step 1c: Brainstorm Architecture & Scope

**Atomic Decomposition Gate (one-shot — run once, before iterative brainstorming begins):**

Before locking in any design decisions, apply first-principles decomposition to the load-bearing terms in the user's feature request and your synthesized understanding from Step 1a. Run this *once* at the start of Step 1c — do NOT repeat per brainstorming round. Surface the decomposition to the user as part of your synthesis so any ambiguity in goals like "simple", "scalable", "robust", "fast", "secure", or domain-specific jargon is resolved before scope and architecture get committed to writing.

!`cat ~/.claude/skills/_components/atomic-thinking.md`

After the decomposition, proceed with iterative brainstorming below.

1. Synthesize your understanding of the feature request and related context.
2. Use `AskUserQuestion` to iteratively refine the spec. **Ask about the problem and desired outcomes before infrastructure details:**
   - **Desired outcomes** — What should the experience look like?
   - **Scope boundaries** — What's in v1 vs future? What's explicitly out of scope?
   - **Technical constraints** — Platform differences? Performance concerns? Integration with existing systems?
   - **Design decisions** — Where there are multiple valid approaches, present options with tradeoffs.
   - **Infrastructure details** — Runtime, repo structure, package manager, etc.
   - **Edge cases** — What happens in unusual scenarios?
3. **Iteratively update the SPEC file** as decisions are locked in. Don't wait until the end — write to `{spec-dir}/{feature-slug}/SPEC.md` after each brainstorming round with confirmed decisions. Mark undecided items as "TBD" or "Open Question".
4. Continue brainstorming rounds until the user signals they're satisfied with the baseline.
5. Summarize the agreed-upon baseline spec clearly before moving to Phase 2.

**Rules for brainstorming:**
- Ask 2-4 focused questions per round (not more).
- Present concrete options where possible — don't ask open-ended "what do you think?" questions.
- **Surface full option context in chat BEFORE calling `AskUserQuestion`.** The picker UI truncates option descriptions (~80 chars on mobile), so the user cannot make an informed decision from labels alone. For every multi-option question you are about to ask, first write a chat-visible block containing: (a) the question and why it matters now, (b) each option as a bullet with a 1-2 sentence description, explicit pros, explicit cons, and any relevant project/research context, (c) which option you'd recommend and why (or "no strong preference — depends on X"). Only after that block goes out, call `AskUserQuestion` with the same options as concise picker labels. The picker is for capturing the choice, not for explaining it.
- Reference existing project patterns and conventions.
- Flag any conflicts with current architecture early.
- **For UI proposals:** Use `AskUserQuestion` with `markdown` previews to show ASCII wireframe mockups where helpful.
- **Late requirement impact check:** When a new requirement or decision contradicts or significantly changes a previously written spec section, explicitly enumerate which existing sections are affected before rewriting. State: "This changes sections: [list]. Updating all affected sections now." This prevents partial updates where some sections reflect a stale architecture.

---

## Phase 2: Gemini Deep Research Prompt

**Goal:** Draft a comprehensive research prompt for Gemini Deep Research to validate ideas, explore prior art, and surface pitfalls.

1. Create the feature directory: `{spec-dir}/{feature-slug}/`
2. Write the research prompt to `{spec-dir}/{feature-slug}/RESEARCH_PROMPT.md`.

**Research prompt structure:**
- **Research Question** — Clear, specific main question
- **Context** — Relevant project context (tech stack, current architecture, what exists today)
- **Baseline Spec Summary** — Condensed version of Phase 1 decisions
- **Research Areas** — Specific things to investigate:
  - Prior art in similar products
  - UI/UX patterns for the specific interaction model
  - Technical approaches and tradeoffs
  - Potential pitfalls, accessibility concerns, performance implications
  - Industry standards or conventions users would expect
- **Specific Questions** — 5-10 targeted questions that would benefit from deep research
- **Output Format Request** — Ask for structured findings with sections, examples, and actionable recommendations

3. Tell the user: "Research prompt saved. Run deep research, then give me the file path to the results."
4. **STOP and wait for the user to return with the research file path.**

---

## Phase 3: Integrate Research & Finalize Spec

**Goal:** Incorporate research findings and finalize the complete feature specification.

1. Read the research results file the user provides.
2. Copy it to `{spec-dir}/{feature-slug}/RESEARCH.md`.
3. Write a research summary to `{spec-dir}/{feature-slug}/RESEARCH_SUMMARY.md` (MANDATORY — this file gates downstream workflow) analyzing:
   - Key findings relevant to our baseline spec
   - Ideas we should adopt from prior art
   - Pitfalls or concerns we need to address
   - Any baseline spec decisions that should be revisited based on research
4. **Surface the full decision landscape in chat BEFORE any `AskUserQuestion` call.** After research, the user typically faces several interlocking decisions, and the picker UI truncates option descriptions — so the user cannot answer informed from picker labels alone. Write a chat-visible "Open Decisions" block first, structured as:

   ```
   ## Open Decisions (post-research)

   The research surfaced N decisions that need to be locked in before finalizing the SPEC. Full context for each below — picker questions follow.

   ### Decision 1: {short name}
   **Question:** {what we're deciding}
   **Why it matters now:** {what downstream choices depend on this}
   **Research signal:** {1-2 sentence summary of what RESEARCH.md says about this}

   - **Option A — {label}:** {1-2 sentence description}
     - Pros: {bulleted or comma-separated}
     - Cons: {bulleted or comma-separated}
     - Fit with our stack/constraints: {note}
   - **Option B — {label}:** ...
   - **Option C — {label}:** ...

   **My recommendation:** {Option X, because Y} — or — "no strong preference, depends on {Z}"

   ### Decision 2: ...
   ```

   Cover at minimum: spec adjustments based on research, v1-vs-later prioritization, technical approach clarifications, and any remaining open questions. Use the actual research findings — don't restate generic categories.

5. **Then** use `AskUserQuestion` to capture the choices. Each picker question should match one decision from the chat block above, with concise labels (the full tradeoff context already lives in chat). Ask 2-4 questions per round.
6. Continue refining until the user is satisfied. On each new round of decisions, repeat the "surface context in chat first, then ask" pattern.
7. Write the final `{spec-dir}/{feature-slug}/SPEC.md` with this structure:

```markdown
# {Feature Name} — Feature Specification

> One-line summary

**Status:** Draft
**Priority:** {P0-P3}
**Last updated:** {today's date}

**Depends on:**

- {feature-id} — {hard|soft|composes} — {one-sentence reason}
- {feature-id} — {hard|soft|composes} — {one-sentence reason}

(or, if there are no deps, replace the bulleted block with exactly: `**Depends on:** (none)`)

---

## Executive Summary
{2-3 paragraphs describing the feature, its value, and high-level approach}

## User Experience
{Detailed UX description with workflows}

## Technical Design
{Architecture, data model, component changes}

## Implementation Phases
{Phased breakdown with clear deliverables per phase}

## Validation Criteria

For each major observable behavior defined in this spec, define how to verify it works end-to-end:

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| {e.g., "data persisted after save"} | {e.g., "submit the form"} | {e.g., "record exists in database"} | {e.g., "database query, API response"} |

These criteria are used during `/implement-phase-batch` to validate spec alignment. Each row becomes a test assertion.

## Open Questions
{Anything still unresolved}

## Research References
{Link to RESEARCH.md and key findings that shaped decisions}
```

!`cat .claude/skill-config/spec-testing-guidance.md 2>/dev/null || cat ~/.claude/skills/_components/spec-testing-guidance.md`

8. **Depends-on Finalization Checkpoint (BLOCKING — before marking Final):**

   Re-verify the `**Depends on:**` block against the final SPEC content. Things change during Phase 3 — research often introduces a new upstream, descopes one, or shifts a `soft` dep to `hard`.

   Apply the schema rules from `~/.claude/skills/_components/dep-block-schema.md` (you read this in Phase 1b). Confirm:

   - The block exists exactly once and is positioned after the frontmatter and before the first design heading.
   - Every line uses ` — ` (space, em-dash U+2014, space) as the separator. Hyphen-minus is invalid.
   - Every `<feature-id>` resolves to a real feature directory using the resolution protocol.
   - Every `<kind>` is one of `hard`, `soft`, `composes`.
   - If no deps, the block reads exactly `**Depends on:** (none)`.

   If any check fails, fix the block before writing the final SPEC.md. Do NOT write the SPEC.md with a malformed or missing dep block — downstream skills (`/spec-phases`, `/write-plan`, `/lazy` Step 4.6, `/realign-spec`) depend on this being parseable, and project-side doc-lint will reject the commit.

9. **Cross-Boundary Validation (before marking Final):**
   Before finalizing any spec that references runtime data access, surface counts, or cross-boundary propagation:
   - **Formulas referencing runtime data** (e.g., "total = sum(lineItems.price)"): Verify the data is accessible at the proposed instrumentation point — read the source code or dispatch a subagent to confirm the variables are in scope
   - **Surface counts** (e.g., "~50 API endpoints"): Run a subagent to grep/count the actual surfaces in the codebase; report the real number
   - **Cross-boundary propagation** (e.g., "auth token flows through middleware"): Verify the boundary contract supports it — check the protocol schema, third-party docs, or IPC layer
   - Mark any unverified quantities with `(estimated — verify during Phase N)` in the spec; never commit to a specific number without evidence

10. Confirm with the user that the spec is complete.

---

## Step 4: Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`

---

## Notes

- The feature slug should be kebab-case, derived from the feature name (e.g., `user-notifications`).
- If the user says "skip research" or similar, skip Phase 2 and go directly to finalizing the spec in Phase 3 (without research integration).
- If the user provides a research file path at any point, treat it as the Phase 2→3 transition.
- Always check for related specs that might conflict or overlap.
