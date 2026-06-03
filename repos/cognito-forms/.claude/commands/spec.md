---
description: Brainstorm, research, and draft a feature spec in C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/
allowed-tools: Read, Glob, Grep, Write, Edit, Bash, AskUserQuestion, Agent, WebSearch
---

# Feature Spec Workflow — Cognito Forms

You are helping the user create a new feature specification for Cognito Forms. This is a **3-phase** interactive workflow. Follow each phase strictly — do not skip ahead.

**User's feature description:**
$ARGUMENTS

---

## Phase 0: Project Context Discovery

Before starting, understand the existing architecture:

1. Read `.claude/KNOWLEDGE_INDEX.md` to understand where knowledge is stored and what exists.
2. Read relevant skills in `.claude/skills/` that relate to the feature domain (e.g., `cognito-payments/`, `cognito-forms/`, `cognito-auth/`).
3. Check `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/` for related specs that might conflict or overlap.
4. Identify which layers are affected: `Cognito.Core`, `Cognito`, `Cognito.Services`, `Cognito.Web.Client`.
5. Note any work items or PRs that relate to this feature.

### Gathering ADO & Slack Context (Optional but Recommended)

When the user requests it or the feature touches existing systems, **launch background agents** to gather organizational context:

**Slack Search (via MCP)**
- Search for discussions about the feature area, prior decisions, and constraints
- Look for architectural decisions, rejected approaches, and performance concerns
- Check channels like `#forms-engineering`, `#frontend`, `#po-sync`, `#midnight`
- Search for any related work item numbers mentioned in discussions

**Azure DevOps Search**
- Find the primary work item(s) and read full descriptions and acceptance criteria
- Look for related/linked work items that provide additional context
- Check for prior art: closed work items that attempted similar work
- Note any constraints or decisions documented in work item comments

**How to search:**
```
Agent tool with run_in_background=true:
- Slack: Use mcp__slack__conversations_search_messages for keyword searches
- ADO: Use the Azure DevOps MCP tools (project ID: 54d9f307-1306-430c-b206-1a55b294a94b)
```

**What to capture:**
- Explicit architectural decisions (e.g., "we intentionally avoided X for Y reason")
- Performance constraints or requirements
- Prior attempts and why they succeeded/failed
- Stakeholder concerns or requirements not captured in work items
- Related work items that should be referenced in the spec

---

## Phase 1: Brainstorm the Baseline Spec

**Goal:** Nail down the core feature concept, scope, and key design decisions through interactive dialogue.

1. Synthesize your understanding of the feature request and related context.
2. Use `AskUserQuestion` to iteratively refine the spec. Ask about:
   - **Scope boundaries** — What's in v1 vs future? What's explicitly out of scope?
   - **User experience** — How does the user interact with this? Key workflows?
   - **Layer impacts** — Which Cognito layers are affected (Core, Business, Services, Web.Client)?
   - **Technical constraints** — Database migrations? API changes? Expression engine? ExoWeb/model.js integration?
   - **Design decisions** — Where there are multiple valid approaches, present options with tradeoffs.
   - **Edge cases** — What happens in unusual scenarios?
   - **Testing strategy** — Which test projects need coverage (Unit, Integration, MSTest patterns)?
3. **Iteratively update the SPEC file** as decisions are locked in. Don't wait until the end — write to `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/{feature-slug}/SPEC.md` after each brainstorming round with confirmed decisions. Mark undecided items as "TBD" or "Open Question".
4. Continue brainstorming rounds until the user signals they're satisfied with the baseline.
5. Summarize the agreed-upon baseline spec clearly before moving to Phase 2.

**Rules for brainstorming:**
- Ask 2-4 focused questions per round (not more).
- Present concrete options where possible — don't ask open-ended "what do you think?" questions.
- Reference existing Cognito patterns (services, controllers, Vue components, model.js).
- Flag any conflicts with current architecture early (e.g., StorageContext patterns, service inheritance).
- **For UI proposals:** Use `AskUserQuestion` with `markdown` previews to show ASCII wireframe mockups.
- **Before drafting research prompt:** Ask if user wants ADO/Slack context gathered. If yes, launch background agents and incorporate findings into the spec before Phase 2.

---

## Phase 2: Gemini Deep Research Prompt

**Goal:** Draft a comprehensive research prompt for Gemini Deep Research to validate ideas, explore prior art, and surface pitfalls.

1. Create the feature directory: `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/{feature-slug}/`
2. Write the research prompt to `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/{feature-slug}/RESEARCH_PROMPT.md`.

**Research prompt structure:**
- **Research Question** — Clear, specific main question
- **Context: Cognito Forms** — Relevant project context:
  - Stack: ASP.NET MVC, C# 9+, Vue 2.7, TypeScript, model.js/ExoWeb
  - Architecture: 4-layer (Core → Business → Services → Web.Client)
  - Existing patterns and conventions
- **Baseline Spec Summary** — Condensed version of Phase 1 decisions
- **Research Areas** — Specific things to investigate:
  - Prior art in similar SaaS form builders (Typeform, JotForm, Formstack, Google Forms)
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
2. Copy it to `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/{feature-slug}/RESEARCH.md`.
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
6. Write the final `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/{feature-slug}/SPEC.md` with this structure:

```markdown
# {Feature Name} — Feature Specification

> One-line summary

**Status:** Draft
**Priority:** {P0-P3}
**Last updated:** {today's date}
**Work Item:** {ADO link or "TBD"}
**Depends on:** {other features or "None"}

---

## Executive Summary
{2-3 paragraphs describing the feature, its value, and high-level approach}

## User Experience
{Detailed UX description with workflows}

## Technical Design

### Layer Changes

#### Cognito.Core (Domain)
{Models, interfaces, domain logic}

#### Cognito (Business)
{Service implementations, business rules}

#### Cognito.Services (API)
{Controllers, endpoints, DTOs}

#### Cognito.Web.Client (Frontend)
{Vue components, model.js integration, ExoWeb rules}

### Database Changes
{Migrations, schema changes}

### API Changes
{New/modified endpoints, contracts}

## Implementation Phases
{Phased breakdown with clear deliverables per phase}

## Testing Strategy
{Unit tests, integration tests, E2E considerations}

## Open Questions
{Anything still unresolved}

## Research References
{Link to RESEARCH.md and key findings that shaped decisions}
```

7. Update `.claude/KNOWLEDGE_INDEX.md` with a reference to the new feature spec.
8. Confirm with the user that the spec is complete.

---

## Notes

- The feature slug should be kebab-case, derived from the feature name (e.g., `conditional-payments`).
- If the user says "skip research" or similar, skip Phase 2 and go directly to finalizing the spec in Phase 3 (without research integration).
- If the user provides a research file path at any point, treat it as the Phase 2→3 transition.
- Always check `C:/Users/JacobMadsen/source/repos/cog-docs/docs/features/` for related specs that might conflict or overlap.
- Reference relevant skills from `.claude/skills/` when discussing technical approaches.
