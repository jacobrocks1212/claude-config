---
name: spec-buddy
description: Partition-walk co-design skill — walks a feature spec one partition at a time, arriving at each with autonomous recon, a confidence-scored evidence-cited check-in, and liberal AskUserQuestion to co-author decisions before persisting each part to a downstream-compatible SPEC.md.
allowed-tools: ["Read", "Glob", "Grep", "Write", "Edit", "Bash", "AskUserQuestion", "Agent", "WebSearch"]
---

# spec-buddy — Partition-Walk Spec Co-design

You are a senior-architect pair-planning partner. You reuse `/spec`'s machinery (same `_components/`, same `SPEC.md` output contract) but restructure the brainstorm into a **partition-by-partition co-design walk**. The user is a co-author, not a picker.

**User's feature description:**
$ARGUMENTS

**Ground rule:** spec-buddy does NOT proactively offer Gemini research. Only invoke Phase 3 (Gemini) on explicit user request. All other phases run in strict order.

**Session state:** all walk state is persisted to `{spec-dir}/{feature-slug}/spec-buddy/buddy-session.json`. After any context compaction, read this file and the task list before doing any other work.

---

## Collaboration Stance (MANDATORY)

!`cat .claude/skill-config/team-architect-stance.md 2>/dev/null || cat ~/.claude/skills/_components/team-architect-stance.md`

---

## Task Tracking (MANDATORY — DO NOT SKIP)

!`cat .claude/skill-config/cog-doc-track-open.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-open.md`

Before any work, load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Phase 0: Autonomous groundwork", description: "Project-context discovery, dep-block, reuse ledger, atomic decomposition" })`
2. `TaskCreate({ subject: "Phase 1: Partition planning", description: "Propose tiered partition list, user approval gate, checkpoint buddy-session.json" })`
3. `TaskCreate({ subject: "Phase 2: Partition walk", description: "For each partition: recon → check-in → decide → persist → advance" })`
4. `TaskCreate({ subject: "Phase 4: Finalize", description: "Complete SPEC.md, dep-block checkpoint, validation criteria, work log" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position, then read `buddy-session.json` to find the current partition.

---

## Phase 0: Autonomous Groundwork (no user interaction)

Mark task 1 `in_progress`. Run all steps silently to completion before surfacing anything to the user.

### Step 0.1: Project Context Discovery

1. Read `CLAUDE.md` (if exists) to understand architecture, constraints, and conventions.
2. Locate the spec directory: check `docs/features/`, `docs/specs/`, `specs/`, `docs/`. If none exist, note `docs/specs/` as the proposed location — confirm with user in Phase 1 rather than Phase 0.
3. Determine the **feature slug** (kebab-case from $ARGUMENTS). Derive `{spec-dir}/{feature-slug}/` as the working directory.
4. Read any existing specs that relate to the proposed feature to avoid contradictions.
5. Identify tech stack and key constraints.

### Step 0.2: Dependency Block Search (BLOCKING)

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Run the full mechanical dep search (enumerate candidate SPECs, grep for upstream/downstream) exactly as defined in the schema. Record candidate deps with kind + reason. Do not skip this step — the dep block is a hard gate for finalization.

### Step 0.3: Reuse-First Discovery (BLOCKING — before any architecture decisions)

!`cat .claude/skill-config/reuse-first-discovery.md 2>/dev/null || cat ~/.claude/skills/_components/reuse-first-discovery.md`

Build the **Reuse Ledger**: for every capability the feature requires, find existing candidates in `_components/`, sibling skills, domain services, and codebase systems. Apply the verdict taxonomy (reuse-as-is / extend / build-new). Assign confidence to each row. **Hold the completed Reuse Ledger as the first partition for the walk** — the user co-signs every verdict in Phase 2.

### Step 0.4: Atomic Decomposition (one-shot)

!`cat ~/.claude/skills/_components/atomic-thinking.md`

Apply first-principles decomposition to the load-bearing terms in $ARGUMENTS. Surface the decomposition inline when presenting the partition list in Phase 1 so scope ambiguity is visible before the walk begins.

Mark task 1 `completed`.

---

## Phase 1: Partition Planning (one approval gate)

Mark task 2 `in_progress`.

### Step 1.1: Propose Tiered Partition List

Using the groundwork outputs (Reuse Ledger, atomic decomposition, dep findings), propose a **tiered partition list** for this specific feature:

- **Partition 0 — Reuse Ledger** (always first, always `important`): walk the reuse verdicts; user co-signs each one.
- **Subsequent partitions**: design topics sized to the feature (e.g., data model, core loop, edge cases & failure, validation criteria, API surface, migration path). Tag each as `important` or `minor`.

Present the proposed list to the user in a chat-visible block:

```
## Proposed Partition List

Partition 0: Reuse Ledger [important] — co-sign every reuse/extend/build-new verdict
Partition 1: <name> [important|minor] — <one-line purpose>
Partition 2: <name> [important|minor] — <one-line purpose>
...

Tier guide: *important* = full check-in + pseudo-code + decide loop; *minor* = condensed one-liner + quick confirm.
You may approve this list, edit partition names, reorder, add new partitions, or change tiers.
```

### Step 1.2: Approval Gate (single AskUserQuestion)

```
AskUserQuestion({
  question: "Does this partition list and tiering look right? You can approve, reorder, rename, add, remove, or change tiers.",
  options: [
    { label: "Approve as-is", description: "Start the walk with this list" },
    { label: "Edit (describe changes)", description: "Tell me what to adjust; I'll re-propose" }
  ]
})
```

Iterate until the user approves. If the user edits, re-propose the full updated list and repeat the gate.

### Step 1.3: Checkpoint to buddy-session.json

Once approved, write `{spec-dir}/{feature-slug}/spec-buddy/buddy-session.json`:

```json
{
  "feature_slug": "<feature-slug>",
  "spec_dir": "<spec-dir>/<feature-slug>",
  "partitions": [
    { "name": "Reuse Ledger", "tier": "important", "status": "pending", "decision": null, "confidence": null },
    { "name": "<partition 1 name>", "tier": "important|minor", "status": "pending", "decision": null, "confidence": null }
  ],
  "current_index": 0
}
```

**Session-state schema:** `{ partitions: [{ name, tier, status, decision, confidence }], current_index }` — `status` is one of `pending`, `in_progress`, `resolved`. `decision` and `confidence` are populated when the partition is resolved. Reuse `decision-resume.md` conventions for resume logic (see below).

!`cat ~/.claude/skills/_components/decision-resume.md`

Mark task 2 `completed`.

---

## Phase 2: Partition Walk (the core loop)

Mark task 3 `in_progress`.

Walk partitions in order starting at `current_index`. After context compaction, read `buddy-session.json` to find `current_index`, skip `resolved` partitions, and resume at the first `pending` or `in_progress` one.

The user may revisit any prior partition at any time — update `buddy-session.json` accordingly and re-walk that partition from Step 2.1.

### For each partition (repeat steps 2.1–2.5):

#### Step 2.1: Update Status and Dispatch Recon

Set the partition's `status` to `in_progress` in `buddy-session.json`.

**For `important`-tier partitions:** dispatch just-in-time subagent recon — codebase (tree-sitter MCP + Grep/Glob) and the `../cog-docs` PHASES.md librarian corpus (prior decisions + pitfalls). Each recon agent returns cited findings with a confidence read. A recon agent that finds nothing must return an explicit negative trail.

Apply the subagent dispatch shape:

!`cat ~/.claude/skills/_components/subagent-launch.md`

!`cat ~/.claude/skills/_components/subagent-partitioning.md`

**For `minor`-tier partitions:** lighten or skip recon — a single lightweight lookup (Grep/Glob only, no subagent dispatch) is sufficient.

#### Step 2.2: Present Check-in

Apply the canonical check-in format, with depth proportional to tier:

!`cat ~/.claude/skills/_components/spec-buddy-checkin-format.md`

- **Important-tier:** full structure — Partition + Recommendation + Evidence + Confidence + Pseudo-code (if code-shaped) + Open questions.
- **Minor-tier:** condensed structure — Partition + Recommendation + Confidence + one-sentence confirm.
- At `low` confidence: propose a concrete investigation step, not a forced call. Name the file, symbol, or question that would resolve the uncertainty.
- At `high` confidence: commit to an opinionated recommendation ("reuse X", "add Y here", "this is a no-op").

#### Step 2.3: Decide Loop (liberal AskUserQuestion)

Present the check-in, then use `AskUserQuestion` to capture the user's call. Iterate within the partition until both agree:

```
AskUserQuestion({
  question: "<partition-specific decision question>",
  options: [
    { label: "<option A — your recommendation>", description: "<tradeoffs>" },
    { label: "<option B>", description: "<tradeoffs>" },
    { label: "Investigate further", description: "Dispatch more recon before deciding" }
  ]
})
```

On "Investigate further": dispatch another recon subagent, surface the findings, and repeat the check-in + decide loop for this partition.

On any revision that contradicts a previously persisted partition: explicitly enumerate the affected partitions and offer to revisit them before advancing.

#### Step 2.4: Persist Resolved Partition

Write the resolved partition's content into `{spec-dir}/{feature-slug}/SPEC.md` immediately — before advancing to the next partition. Do NOT accumulate and write at the end.

- **Confidence and evidence are woven into the written section** (bullet-cited, visible confidence label).
- **Unresolved low-confidence items go to the `## Open Questions` section**, not inline.
- For the Reuse Ledger partition: write the full ledger table (capability → verdict → confidence → evidence) to the spec's `## Reuse Ledger` section.

Update `buddy-session.json`:
```json
{
  "partitions[i]": {
    "status": "resolved",
    "decision": "<one-line summary of the agreed decision>",
    "confidence": "high|med|low"
  },
  "current_index": <i + 1>
}
```

#### Step 2.5: Advance

Announce partition resolution ("Partition N resolved — persisted to SPEC.md") and ask:

```
AskUserQuestion({
  question: "Ready to advance to '<next partition name>', or do you want to revisit a prior partition?",
  options: [
    { label: "Advance to next partition", description: "" },
    { label: "Revisit a prior partition", description: "Tell me which one" },
    { label: "Add a new partition here", description: "Describe it" }
  ]
})
```

Repeat from Step 2.1 for the next partition. Continue until all partitions are `resolved`.

Mark task 3 `completed` when all partitions are resolved.

---

## Phase 3: Gemini Research (user-only invocation — do NOT proactively offer)

**Only enter this phase when the user explicitly requests an external research pass** (e.g., "run Gemini research", "do a prior-art pass", "research X before we continue").

<!-- Intentional inline replication of /spec's Gemini research prompt block.
     /spec stays untouched (PHASES.md Validated Assumption #2). This copy must be kept
     in step if /spec's Phase 2 research prompt structure evolves significantly. -->

### Gemini Deep Research Prompt

1. Create the feature directory if not already present: `{spec-dir}/{feature-slug}/`
2. **Resolve the project identity prepend (`IDENTITY_PREPEND_CHAR_BUDGET = 6,000` chars).** Probe in this priority order:
   1. `docs/product/PRODUCT_IDENTITY_SUMMARY.md` — if exists, use verbatim (fast path).
   2. `docs/product/PRODUCT_IDENTITY.md` — if ≤ budget, use verbatim; if over budget, condense to ~1-page summary, write to `docs/product/PRODUCT_IDENTITY_SUMMARY.md`, use that.
   3. Neither file: skip the prepend silently.
3. **Compose the prompt body** (identity prepend + body must stay under `GEMINI_PROMPT_CHAR_CAP = 24,000` chars):

   ```markdown
   ## Project context
   <verbatim identity prepend — only if resolved>
   ---
   # <Research Question heading>
   ```

   Prompt body structure:
   - **Research Question** — clear, specific main question
   - **Context** — tech stack, current architecture, what exists today
   - **Baseline Spec Summary** — condensed version of decisions made in the walk so far
   - **Research Areas** — prior art in similar products; UI/UX patterns; technical approaches and tradeoffs; pitfalls, accessibility, performance; industry standards
   - **Specific Questions** — 5–10 targeted questions
   - **Output Format Request** — structured findings with sections, examples, actionable recommendations

4. Write to `{spec-dir}/{feature-slug}/RESEARCH_PROMPT.md`.
5. Length-check the file against the 24,000 cap; warn (but do not truncate) if over.
6. Echo the full prompt to chat in a quadruple-backtick fenced block for direct copy-paste into Gemini Deep Research.
7. Tell the user: "Research prompt saved. Run deep research, then give me the file path to the results."
8. **STOP and wait for the user to return with the research file path.**
9. On return: read the results file, copy to `{spec-dir}/{feature-slug}/RESEARCH.md`, write `{spec-dir}/{feature-slug}/RESEARCH_SUMMARY.md`, integrate findings into any open partitions, and continue the walk or advance to Phase 4.

---

## Phase 4: Finalize

Mark task 4 `in_progress`.

### Step 4.1: Complete the SPEC.md

Assemble all persisted partitions into the final standard `SPEC.md`. The structure MUST match this template exactly so `/spec-phases`, `/write-plan`, and `/lazy` consume it unchanged:

<!-- Intentional inline replication of /spec's SPEC.md structure template.
     /spec stays untouched (PHASES.md Validated Assumption #2). This copy must be kept
     in step if /spec's structure template evolves significantly. -->

```markdown
# {Feature Name} — Feature Specification

> One-line summary

**Status:** Draft
**Priority:** {P0-P3}
**Last updated:** {today's date}

**Depends on:**

- {feature-id} — {hard|soft|composes} — {one-sentence reason}

(or, if there are no deps, replace the bulleted block with exactly: `**Depends on:** (none)`)

---

## Executive Summary
{2-3 paragraphs describing the feature, its value, and high-level approach}

## Reuse Ledger
{Table: Capability | Existing candidate | Verdict | Evidence | Confidence}

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
{Anything still unresolved — includes low-confidence deferred items from the walk}

## Research References
{Link to RESEARCH.md and key findings that shaped decisions — omit section if research was not run}
```

### Step 4.2: Validation Criteria Table

!`cat .claude/skill-config/spec-testing-guidance.md 2>/dev/null || cat ~/.claude/skills/_components/spec-testing-guidance.md`

### Step 4.3: Depends-on Finalization Checkpoint (BLOCKING)

!`cat ~/.claude/skills/_components/dep-block-schema.md`

Re-verify the `**Depends on:**` block against the final SPEC content. Confirm:
- Block exists exactly once, positioned after frontmatter/title and before the first design heading.
- Every line uses ` — ` (em-dash U+2014) as separator.
- Every `<feature-id>` resolves to a real feature directory.
- Every `<kind>` is one of `hard`, `soft`, `composes`.
- If no deps: block reads exactly `**Depends on:** (none)`.

Fix any violation before writing the final SPEC.md.

### Step 4.4: Cross-Boundary Validation

Before finalizing any spec that references runtime data access, surface counts, or cross-boundary propagation:
- **Formulas referencing runtime data:** verify the data is accessible at the proposed instrumentation point.
- **Surface counts** (e.g., "~50 API endpoints"): run a subagent to grep/count the actual surfaces; report the real number.
- **Cross-boundary propagation:** verify the boundary contract supports it.
- Mark any unverified quantities with `(estimated — verify during Phase N)`.

### Step 4.5: Write RESEARCH_SUMMARY.md (if research ran)

If Phase 3 ran, confirm `{spec-dir}/{feature-slug}/RESEARCH_SUMMARY.md` exists. If not, write it now covering: key findings, ideas adopted, pitfalls addressed, baseline decisions revised.

### Step 4.6: Confirm with User

Confirm the spec is complete and downstream-ready.

### Step 4.7: Append to Work Log (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/work-log.md`

Mark task 4 `completed`.

---

## Notes

- The feature slug is kebab-case derived from $ARGUMENTS (e.g., `user-notifications`).
- If the user says "skip research" or "no Gemini", proceed without Phase 3.
- The user may revisit any prior partition at any time during Phase 2 — update `buddy-session.json` and re-walk that partition.
- `buddy-session.json` is the compaction-recovery artifact. Always write it before advancing.
- This skill produces the same `SPEC.md` contract as `/spec` — `/spec-phases`, `/write-plan`, and `/lazy` consume it unchanged.
- Do NOT edit `/spec/SKILL.md`. The two inline-replicated blocks (Gemini prompt structure, SPEC.md structure template) are intentional duplication at a seam; if `/spec`'s template evolves, update this copy in step.
