---
description: Brainstorm, research, and draft a feature spec
allowed-tools: Read, Glob, Grep, Write, Edit, Bash, AskUserQuestion, Agent, WebSearch
name: spec
---

# Feature Spec Workflow

You are helping the user create a new feature specification. This is a **3-phase** interactive workflow. Follow each phase strictly — do not skip ahead.

**User's feature description:**
$ARGUMENTS

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

1. Synthesize your understanding of the feature request and related context.
2. Use `AskUserQuestion` to iteratively refine the spec. Ask about:
   - **Scope boundaries** — What's in v1 vs future? What's explicitly out of scope?
   - **User experience** — How does the user interact with this? Key workflows?
   - **Technical constraints** — Platform differences? Performance concerns? Integration with existing systems?
   - **Design decisions** — Where there are multiple valid approaches, present options with tradeoffs.
   - **Edge cases** — What happens in unusual scenarios?
3. **Iteratively update the SPEC file** as decisions are locked in. Don't wait until the end — write to `{spec-dir}/{feature-slug}/SPEC.md` after each brainstorming round with confirmed decisions. Mark undecided items as "TBD" or "Open Question".
4. Continue brainstorming rounds until the user signals they're satisfied with the baseline.
5. Summarize the agreed-upon baseline spec clearly before moving to Phase 2.

**Rules for brainstorming:**
- Ask 2-4 focused questions per round (not more).
- Present concrete options where possible — don't ask open-ended "what do you think?" questions.
- Reference existing project patterns and conventions.
- Flag any conflicts with current architecture early.
- **For UI proposals:** Use `AskUserQuestion` with `markdown` previews to show ASCII wireframe mockups where helpful.

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
3. Write a research summary analyzing:
   - Key findings relevant to our baseline spec
   - Ideas we should adopt from prior art
   - Pitfalls or concerns we need to address
   - Any baseline spec decisions that should be revisited based on research
4. Present the summary to the user, then use `AskUserQuestion` to refine:
   - **Spec adjustments** — What changes based on research?
   - **Prioritization** — What's v1 vs later phases?
   - **Technical approach** — Has research clarified the right technical direction?
   - **Open questions** — Anything still unresolved?
5. Continue refining until the user is satisfied.
6. Write the final `{spec-dir}/{feature-slug}/SPEC.md` with this structure:

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

## Open Questions
{Anything still unresolved}

## Research References
{Link to RESEARCH.md and key findings that shaped decisions}
```

7. Confirm with the user that the spec is complete.

---

## Notes

- The feature slug should be kebab-case, derived from the feature name (e.g., `user-notifications`).
- If the user says "skip research" or similar, skip Phase 2 and go directly to finalizing the spec in Phase 3 (without research integration).
- If the user provides a research file path at any point, treat it as the Phase 2→3 transition.
- Always check for related specs that might conflict or overlap.
