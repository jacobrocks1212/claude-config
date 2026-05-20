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

### Step 1b: Brainstorm Architecture & Scope

**Atomic Decomposition Gate (one-shot — run once, before iterative brainstorming begins):**

Before locking in any design decisions, apply first-principles decomposition to the load-bearing terms in the user's feature request and your synthesized understanding from Step 1a. Run this *once* at the start of Step 1b — do NOT repeat per brainstorming round. Surface the decomposition to the user as part of your synthesis so any ambiguity in goals like "simple", "scalable", "robust", "fast", "secure", or domain-specific jargon is resolved before scope and architecture get committed to writing.

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
**Depends on:** {other features or "None"}

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

8. **Cross-Boundary Validation (before marking Final):**
   Before finalizing any spec that references runtime data access, surface counts, or cross-boundary propagation:
   - **Formulas referencing runtime data** (e.g., "total = sum(lineItems.price)"): Verify the data is accessible at the proposed instrumentation point — read the source code or dispatch a subagent to confirm the variables are in scope
   - **Surface counts** (e.g., "~50 API endpoints"): Run a subagent to grep/count the actual surfaces in the codebase; report the real number
   - **Cross-boundary propagation** (e.g., "auth token flows through middleware"): Verify the boundary contract supports it — check the protocol schema, third-party docs, or IPC layer
   - Mark any unverified quantities with `(estimated — verify during Phase N)` in the spec; never commit to a specific number without evidence

9. Confirm with the user that the spec is complete.

---

## Step 4: Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`

---

## Notes

- The feature slug should be kebab-case, derived from the feature name (e.g., `user-notifications`).
- If the user says "skip research" or similar, skip Phase 2 and go directly to finalizing the spec in Phase 3 (without research integration).
- If the user provides a research file path at any point, treat it as the Phase 2→3 transition.
- Always check for related specs that might conflict or overlap.
