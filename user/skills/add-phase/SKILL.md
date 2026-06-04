---
name: add-phase
description: Add a new phase to an existing PHASES.md, checking Implementation Notes and marking superseded phases
argument-hint: <path/to/PHASES.md> [phase description]
---

# Add Phase

Add a new phase to an existing PHASES.md file. Reads all prior phases — including their Implementation Notes — to ensure the new phase is well-informed and consistent. Marks superseded phases if the new phase replaces or obsoletes prior work.

---

## Batch Mode (`--batch` flag)

If `$ARGUMENTS` contains `--batch`, this is an autonomous invocation (typically from `/lazy-batch` Step 4.6 acting on a `/realign-spec` recommendation).

- Strip `--batch` from `$ARGUMENTS` before processing.
- Steps 1–5 (resolve inputs, read context, analyze, draft, mark superseded) run unchanged.
- **Step 6 (Present for Approval) is skipped.** The orchestrator passes the desired phase title and scope in the description argument; `--batch` mode trusts the orchestrator's framing and proceeds to Step 7.
- **Halt protocol — `NEEDS_INPUT.md`:** if Step 1b cannot resolve the phase description (no description supplied AND no usable context AND the supplied description is genuinely ambiguous about scope), do NOT invent a phase. Instead write `{phases-md-dir}/NEEDS_INPUT.md` per `~/.claude/skills/_components/sentinel-frontmatter.md`:

  ```markdown
  ---
  kind: needs-input
  feature_id: {feature-slug derived from phases-md-dir}
  written_by: add-phase
  decisions:
    - "Phase scope ambiguous — orchestrator did not provide enough context"
  date: {today}
  next_skill: add-phase
  ---

  # /add-phase --batch — Needs Input

  Phase description missing or ambiguous; refusing to invent a phase.
  Re-run `/add-phase` interactively with explicit title + scope.
  ```

  STOP without writing PHASES.md.

- Step 7 (Write Changes) runs unchanged. The change is committed by the caller per the orchestrator's commit policy.

---

## Step 1: Resolve Inputs

### 1a. PHASES.md Path

- If `$ARGUMENTS` contains a `.md` path, use it.
- Otherwise, check session history for a recently-referenced PHASES.md.
- If still unresolved, use **AskUserQuestion**: "Which PHASES.md should I add a phase to?"

### 1b. Phase Description

- If `$ARGUMENTS` contains a description (beyond the path), use it.
- Otherwise, check session history for context about what the user wants to add.
- If still unresolved, use **AskUserQuestion**: "What should this new phase accomplish? Describe the scope and goal."

---

## Step 2: Read Full Context

1. **Read the PHASES.md in full** — every phase, including all Implementation Notes blocks. Do not skim or summarize.
2. **Read the sibling SPEC.md** (same directory) — source of truth for feature requirements.
3. **Read project CLAUDE.md** (if it exists at the project root) — for conventions and patterns.

---

## Step 3: Analyze Existing Phases

### 3a. Extract State

For each existing phase, record:
- Phase number, title, scope
- Status: all deliverables checked (`[x]`) = complete, any unchecked (`[ ]`) = incomplete
- Implementation Notes (if present): completed date, integration notes, pitfalls, files modified
- Prerequisites and dependencies

### 3b. Mine Implementation Notes

Implementation Notes contain ground truth about what was _actually_ built (vs. what was planned). Before drafting the new phase:

- Identify **patterns established** — imports, APIs, conventions the new phase should follow
- Identify **pitfalls documented** — things to avoid or work around
- Identify **actual file paths** — may differ from original plan; use real paths
- Identify **integration seams** — where the new phase connects to completed work

### 3c. Check for Supersession

Compare the new phase's scope against existing phases:

- **Fully superseded:** The new phase completely replaces an existing phase's purpose (e.g., "rewrite X" supersedes "implement X"). Mark as superseded.
- **Partially superseded:** The new phase replaces some deliverables of an existing phase. Mark specific deliverables as superseded, not the whole phase.
- **Not superseded:** The new phase adds net-new functionality alongside existing phases. No marking needed.

---

## Step 3.5: Runtime Assumption Validation (where appropriate — BEFORE DRAFTING THE PHASE)

A new phase often rests on assumptions about how the *running* system behaves — the actual shape of data crossing a boundary, whether an existing code path fires, the live output of a separate process, the rendered result of an audio/effect path. These are NOT provable from source: reading the types or the function body can mislead (a value's runtime shape, a stale build, a module-singleton split, timing). Where the new phase rests on a load-bearing **runtime-coupled** assumption, validate it against the running system BEFORE drafting the phase — or make the validation an explicit early deliverable of the phase itself. Do not draft (and then implement) a phase against a code-read assumption the runtime might contradict. This is especially important for `/add-phase`, which frequently appends *corrective* phases that exist precisely because a prior assumption proved wrong — confirm the new assumption is real before building on it.

!`cat .claude/skill-config/phases-runtime-validation.md 2>/dev/null || cat ~/.claude/skills/_components/phases-runtime-validation.md`

---

## Step 4: Draft the New Phase

Determine the next phase number (highest existing + 1, or fill a gap if prior phases were superseded and removed).

Write the phase using the established PHASES.md format:

```markdown
### Phase N: {Title}

**Scope:** {Clear description of what's built — informed by Implementation Notes from prior phases}

**Deliverables:**
- [ ] {Concrete output 1}
- [ ] {Concrete output 2}
- [ ] Tests: {What tests verify this phase}

**Prerequisites:**
- {Phase X}: {Specific dependency — reference actual outputs from Implementation Notes, not planned outputs}

**Files likely modified:**
- `path/to/file` — {what changes} (use actual paths from Implementation Notes where applicable)

**Testing Strategy:**
{How this phase is verified in isolation}

**Integration Notes for Next Phase:**
- {What a subsequent phase would need to know}

**Context from prior phases:**
- {Key patterns, pitfalls, or integration details extracted from Implementation Notes that inform this phase's implementation}
```

---

## Step 5: Mark Superseded Phases

If any phases are superseded (identified in Step 3c):

### Fully Superseded

Add a supersession notice at the top of the phase and strike through all deliverables:

```markdown
### Phase M: {Original Title}

> **⚠️ SUPERSEDED by Phase N: {New Title}** — This phase's scope has been replaced. Do not implement.

**Deliverables:**
- [~] ~~{Original deliverable 1}~~ — superseded
- [~] ~~{Original deliverable 2}~~ — superseded
```

### Partially Superseded

Mark only the specific deliverables that are replaced:

```markdown
- [~] ~~{Superseded deliverable}~~ — superseded by Phase N
- [ ] {Still-valid deliverable}
```

### Already-Completed Phases

Never mark a completed phase (all `[x]`) as superseded. If the new phase _replaces_ completed work (a rewrite), note this in the new phase's scope instead:

```
**Scope:** Rewrite the implementation from Phase M. Phase M's approach of {X} is replaced with {Y} because {reason}.
```

---

## Step 6: Present for Approval

**Under `--batch`:** SKIP this step entirely. The orchestrator's description argument is treated as approval. Proceed to Step 7.

**Interactive mode:** show the user:
1. The drafted new phase
2. Any supersession markings (with before/after)
3. Key context extracted from Implementation Notes that shaped the draft

Use **AskUserQuestion**: "Here's the new phase and any supersession changes. Approve, or adjust?"

---

## Step 7: Write Changes

After approval:
1. Append the new phase to PHASES.md (before any trailing notes/appendix sections)
2. Apply supersession markings to affected phases
3. Read back the modified file to verify formatting is correct

## Step 8: Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`
