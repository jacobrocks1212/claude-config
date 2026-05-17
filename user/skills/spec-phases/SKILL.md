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

## Task Tracking (MANDATORY — DO NOT SKIP)

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

!`cat .claude/skill-config/touchpoint-audit-gate.md 2>/dev/null || cat ~/.claude/skills/_components/touchpoint-audit-gate.md`

### Step 3: Propose Phase Structure

Present proposed phases to user with `AskUserQuestion`:

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

### Phase 1: {Title}

**Scope:** {Clear description of what's built}

**Deliverables:**
- [ ] {Concrete code output 1}
- [ ] {Concrete code output 2}
- [ ] Tests: {What tests verify this phase}

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
