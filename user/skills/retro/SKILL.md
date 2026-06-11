---
name: retro
description: Retrospective analysis of completed work — identifies issues, incorrect assumptions, and workflow improvements. After writing the retro plan, dispatches a Sonnet spec-body-fixer (Step 6b.5) to propagate Minor doc-drift divergences (resolved-research checklists, stale counts, deferred-API surface entries, stale Status) into SPEC.md inline and annotates the plan's Minor rows with the fix commit — Significant rows untouched. RETRO_DONE.md (Step 6c) only fires when the Significant table is empty.
argument-hint: [feature-name | SPEC path | PHASES path] [--auto]
plan-mode: never
---

# Retro

Reviews completed work (specified by user, or inferred from conversation history) and produces a structured retrospective. Identifies issues encountered, incorrect assumptions, inefficient implementation order, missed parallelism, and proposes concrete workflow improvements. The improvement plan is written to a file for execution via `/execute-plan`.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. The deliverable is a written plan file, not a plan-mode interaction.

### `--auto` / `--batch` Flag

If `$ARGUMENTS` contains `--auto` OR `--batch`, this is an autonomous invocation (typically from `/lazy` or `/lazy-batch`). The two flags are aliases — they trigger identical behavior. Strip whichever is present from arguments before processing.

- **Skip ALL clarifying questions** (Step 5) — use your best judgment for improvement priorities
- **Skip AskUserQuestion in Step 1** — infer scope from arguments or conversation context; if truly ambiguous in `--batch` mode (no recoverable signal), halt with NEEDS_INPUT.md (see below). `--auto` mode (legacy) falls back to PushNotification + STOP.
- **Runtime evidence path:** when runtime evidence is needed but unavailable, do NOT use AskUserQuestion. In `--batch`/`--auto` mode, proceed with code-level analysis only and add a top-level note in the retro plan: "Runtime evidence unavailable in this session — alignment assessed at the code level. Re-run interactively with runtime data for higher confidence."
- Focus on systematic issues and defects; skip subjective/preference questions
- **MANDATORY spec divergence reporting:** The plan file output MUST include a top-level `## Spec Divergences` section (before defects/improvements) that classifies all divergences found by Subagent B:

```markdown
## Spec Divergences

**Overall alignment:** {percentage}%

### Significant (require corrective implementation)
| Spec Requirement | What Was Built | Gap |
|-----------------|----------------|-----|
| ... | ... | ... |

### Minor (document only)
| Item | Nature of Divergence |
|------|---------------------|
| ... | ... |
```

If the "Significant" table has any rows, the retro MUST flag this clearly in its final output message: `"SIGNIFICANT SPEC DIVERGENCES FOUND — corrective phases needed before feature completion."` This signal is consumed by `/lazy` to trigger `/add-phase`.

**Minor row propagation (Step 6b.5):** Minor divergences are NOT deferred to `/execute-plan`. After the plan file is written (Step 6b), Step 6b.5 dispatches a Sonnet spec-body-fixer subagent that propagates each Minor row into SPEC.md inline (e.g. "Needs Research" checklist → "Resolved by Research" with answers from RESEARCH_SUMMARY.md; stale counts bumped; deferred APIs removed from surface tables; stale Status flipped when phases are Complete). The plan file's Minor rows are then patched to record the fix commit per row (or the skip reason). This closes the 25%-of-features SPEC-drift gap the audit walk surfaced.

### Halt protocol — `NEEDS_INPUT.md` (under `--batch` only)

**Post-research positioning:** `/retro --batch` runs at the very end of the per-feature pipeline (Step 9 in the state machine) — long after research has landed. This skill is therefore eligible to write `NEEDS_INPUT.md` per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`. Real ambiguity at retro time (e.g., which of two architectural fixes to encode as a corrective phase) is a genuine design choice the halting rule permits.

The two halt cases for `/retro --batch` are: (a) unresolvable scope at Step 1 (no PHASES.md / SPEC.md / feature name in arguments or context), and (b) a Significant divergence whose corrective phase shape genuinely could go multiple ways. Both must follow the rich-body convention so the orchestrator can re-print the tradeoffs to chat before calling `AskUserQuestion`.

In `--batch` mode, if Step 1 cannot resolve the work scope (no path/feature in arguments, no usable signal in conversation context), write `{cwd}/NEEDS_INPUT.md` per `~/.claude/skills/_components/sentinel-frontmatter.md` using the rich-body skeleton below:

```markdown
---
kind: needs-input
feature_id: <best-guess from arguments, or "unknown">
written_by: retro
decisions:
  - "Cannot determine retro scope — no PHASES.md / SPEC.md / feature name supplied"
date: <today>
next_skill: retro
---

# /retro --batch — Needs Input

## Decision Context

### 1. Cannot determine retro scope — no PHASES.md / SPEC.md / feature name supplied

**Problem:** `/retro --batch` requires an explicit scope but received none.
Recent conversation context did not surface a unique candidate. Picking
arbitrarily would risk reviewing the wrong feature.

**Options:**
- **Re-run with explicit scope** — pass `<feature-name | SPEC path | PHASES path>` to `/retro` and try again. Safest; preserves audit trail.
- **Skip retro for this cycle** — proceed past Step 9 and mark complete; loses the workflow-improvement signal but unblocks the queue.

**Recommendation:** Re-run with explicit scope — the workflow-improvement signal is the reason retro exists.
```

For Significant divergence ambiguity (after Subagent B's report), follow the same rich-body shape with one H3 per decision and a `**Recommendation:**` line on each.

**Echo the entire `## Decision Context` section to chat output** before returning (per Producer responsibilities in `sentinel-frontmatter.md`).

STOP without dispatching subagents.

---

## Step 0: Task Tracking (MANDATORY — DO NOT SKIP)

Load task tools and create tasks for compaction recovery:

```
ToolSearch: "select:TaskCreate,TaskUpdate,TaskGet,TaskList"
```

Create tasks immediately:
1. `TaskCreate({ subject: "Identify work scope", description: "Resolve PHASES.md, SPEC.md, git log, and other source documents" })`
2. `TaskCreate({ subject: "Gather evidence via subagents", description: "Launch parallel subagents A-F for implementation notes, spec diff, commit history, quality gaps, runtime evidence, session history" })`
3. `TaskCreate({ subject: "Synthesize findings", description: "Aggregate subagent results into structured retrospective" })`
4. `TaskCreate({ subject: "Propose improvements", description: "Defects to fix, skill changes, CLAUDE.md updates, process changes" })`
5. `TaskCreate({ subject: "Write improvement plan file", description: "Convert proposals into executable plan file" })`

Update each task to `in_progress` when starting it, `completed` when done. After context compaction, call `TaskList` first to find your current position.

---

## Step 1: Identify the Work Scope

Determine what completed work to review:

1. **Explicit argument:** If `$ARGUMENTS` specifies a feature name, SPEC path, or PHASES path, use that
2. **Conversation context:** If no argument, infer from the current conversation history (recent commits, files modified, active feature)
3. **Ambiguous:** in interactive mode use **AskUserQuestion** — "Which completed work should I review? (feature name, SPEC.md path, or PHASES.md path)". Under `--auto`/`--batch`: halt per the NEEDS_INPUT.md protocol above.

### Resolve Source Documents

Once the scope is identified, locate and read:
- **PHASES.md** — primary source of implementation history (phases, batches, implementation notes)
- **SPEC.md** — original requirements and design decisions
- **Git log** — commits associated with the work (use commit messages + diff stats)
- **CLAUDE.md files** — any updates made during implementation
- **Chat history** (when applicable) — search `~/.claude-personal/projects/` for `.jsonl` session files containing the feature name. Extract: compaction count, user interventions, review verdicts, session count. This reveals context loss patterns and orchestrator drift.
- **Runtime evidence** (when applicable) — if the feature produces observable runtime output (session logs, API responses, files), locate and read it. If session logs exist in `logs/session-*/`, read them. If the app must be running to produce evidence and it's not available, flag: "Cannot verify spec alignment without runtime data — recommend running the app."

Default scope: all phases marked complete in the PHASES.md, unless user specifies a subset.

### Assess Data Sufficiency

Before launching subagents, determine if you have enough information to assess spec alignment:

| Evidence Type | Where to Find | Required? |
|---------------|---------------|-----------|
| Implementation notes | PHASES.md | Always |
| Spec requirements | SPEC.md | Always |
| Commit history | `git log` | Always |
| Runtime evidence | Test output, API responses, app logs | If spec defines observable behavior |
| Chat history | `~/.claude-personal/projects/` | If implementation used `/implement-phase-batch` or had compactions |

If runtime evidence is needed but unavailable, **interactive mode** uses **AskUserQuestion**: "This retro requires runtime evidence to validate spec alignment. Should I (a) start the dev app and test, (b) proceed with code-level analysis only, or (c) use existing session logs at [path]?"

Under `--auto`/`--batch`: proceed with code-level analysis only and note "Runtime evidence unavailable in this session" at the top of the retro plan.

---

## Step 3: Gather Evidence (Subagent Strategy)

Launch parallel research subagents to collect evidence across multiple dimensions. Each subagent reports findings in structured format.

### Subagent A: Implementation Notes Analyzer

**Prompt:** Read the PHASES.md implementation notes for all completed phases. Extract:
- Problems encountered (bugs, blockers, rework)
- Deviations from the original plan
- Scope changes (additions, removals, deferrals)
- Integration issues between phases/batches

### Subagent B: Spec vs Reality Diff

**Prompt:** Compare SPEC.md requirements against what was actually built (by reading the PHASES.md deliverables and checking key source files). Identify:
- Spec items that were descoped or simplified
- Implementation that exceeded spec (scope creep)
- Assumptions in the spec that proved wrong
- Requirements that were ambiguous and caused rework

### Subagent C: Commit History Analyzer

**Prompt:** Analyze the git log for commits related to this feature. Look for:
- Fix-up commits that indicate rework (e.g., "fix: ...", commits amending earlier work)
- Multiple commits touching the same file (churn indicator)
- Large time gaps suggesting blockers
- Commits that could have been parallelized but were serial

### Subagent D: Quality & Testing Gaps

**Prompt:** Review test files and quality gate results. Identify:
- Tests that had to be rewritten (brittle test design)
- Quality gate failures that blocked progress
- Missing test coverage discovered late
- Tests that test implementation rather than behavior

!`cat .claude/skill-config/retro-runtime-evidence.md 2>/dev/null || cat ~/.claude/skills/_components/retro-runtime-evidence.md`

### Subagent F: Session History Analyzer (when chat history available)

**Only launch if** implementation used `/implement-phase-batch` or arguments mention compactions/context loss.

**Prompt:** Search the Claude Code session history for this feature. The session history lives at:

```
~/.claude-personal/projects/{project-dir}/
├── {session-id}.jsonl              # Main conversation log
├── {session-id}/
│   ├── subagents/
│   │   ├── agent-{id}.jsonl        # Subagent conversation log
│   │   └── agent-{id}.meta.json    # {"agentType": "...", "description": "..."}
│   └── tool-results/               # Large tool outputs
```

**How to search:**
1. Identify the project directory by matching the cwd-encoded path (e.g., `C--Users-JacobMadsen-source-repos-algobooth`)
2. List session files by modification time (newest first) — recent sessions are most relevant
3. Search main `.jsonl` files for the feature name/keywords to identify relevant sessions
4. For relevant sessions, also search `{session-id}/subagents/agent-*.jsonl` — subagent history contains the actual implementation work and is where most issues surface
5. Read `.meta.json` files to understand what each subagent was doing (the `description` field summarizes the work unit)

Extract from matched sessions:
- Total session count and compaction count
- Pattern of user interventions (did user have to redirect the orchestrator?)
- Review verdicts (PASS/NEEDS-REWORK counts)
- Whether the orchestrator lost track of the plan after compaction
- Evidence of "drift" — where the orchestrator proceeded on stale/incomplete information
- Subagent failures or retries visible in agent logs

### Subagent G: Skill Compliance Verifier (ALWAYS launch)

**Pre-flight (orchestrator does this BEFORE launching Subagent G):**

1. Determine which skills were invoked during this feature's lifecycle. Check:
   - PHASES.md implementation notes for skill references (`/spec`, `/spec-phases`, `/implement-phase`, `/execute-plan`, `/write-plan`, `/mcp-test`, `/fix`, `/retro`, `/add-phase`)
   - Git log commit messages for skill references
   - Plan files in `{spec_path}/plans/` — each plan's header names the generating skill
2. Read every identified skill's SKILL.md **in full** — these are the source of truth for what each skill's mandatory requirements are:
   - `~/.claude/skills/{name}/SKILL.md` for user-level skills
   - `.claude/skills/{name}/SKILL.md` for repo-scoped skills (e.g., `/mcp-test`)
3. Pass the full text of each relevant skill's SKILL.md to Subagent G in its prompt so it can verify compliance against the actual requirements, not a stale summary

**Prompt:** Verify that all skills invoked during this feature's implementation followed their mandatory requirements. The full text of each skill is provided below for reference — use these as the authoritative checklist. Check each of the following:

**1. PHASES.md Implementation Notes:**
- For each completed phase, verify an `## Implementation Notes` block exists with:
  - Date
  - Work completed summary
  - Files modified
  - Integration notes for subsequent phases
  - Pitfalls/guidance
- Report: which phases have complete notes vs. which are missing/incomplete

**2. Quality gates passed:**
- Check git log for evidence of QG runs (commit messages mentioning "qg", "quality gate", or presence of QG-related files)
- Check PHASES.md implementation notes for QG pass/fail mentions
- Report: evidence of QG compliance per phase

**3. Task tracking was used:**
- Search session history (if available) for `TaskCreate`/`TaskUpdate` tool calls
- If session history unavailable, check PHASES.md notes for task-related references
- Report: evidence of task tracking usage

**4. TDD discipline:**
- For each phase that produced source code, verify corresponding test files exist
- Check if tests were created BEFORE or alongside implementation (look at commit order)
- Report: test file coverage per phase, any phases with implementation but no tests

**5. Subagent review was performed:**
- Check PHASES.md implementation notes for review verdicts (PASS/PASS-WITH-FIXES/NEEDS-REWORK)
- If session history available, search for review report patterns
- Report: review evidence per batch

**Output format:**

```markdown
## Skill Compliance Report

| Requirement | Status | Evidence | Gap |
|-------------|--------|----------|-----|
| Implementation Notes | ✓/✗ | {N}/{total} phases complete | {missing phases} |
| Quality gates | ✓/✗ | {evidence} | {gaps} |
| Task tracking | ✓/✗ | {evidence} | {gaps} |
| TDD discipline | ✓/✗ | {test coverage} | {untested phases} |
| Subagent review | ✓/✗ | {verdicts found} | {unreviewed batches} |

**Overall compliance:** {percentage}%
**Critical gaps:** {list any that indicate systematic non-compliance}
```

---

## Step 4: Synthesize Findings

Aggregate subagent results into a structured retrospective. Organize by category:

### 4a. Issues Encountered

| Category | Description | Impact | Root Cause |
|----------|-------------|--------|------------|
| ... | ... | ... | ... |

Impact levels: `blocked` (stopped progress), `rework` (required redo), `friction` (slowed down), `minor` (annoying but no delay)

### 4b. Incorrect Assumptions

List assumptions made during spec/planning that proved wrong during implementation. For each:
- What was assumed
- What reality was
- How it was discovered
- What could have caught it earlier

### 4c. Implementation Order Analysis

- Were phases in the right order?
- Which phases/batches could have been parallelized?
- Did any phase depend on information only available from a later phase?
- Were there unnecessary serial bottlenecks?

### 4d. Tooling & Workflow Gaps

- What manual work could have been automated?
- Where did existing skills/tools fall short?
- What context was lost between sessions that slowed progress?
- Were subagent prompts effective or did they need rework?

### 4e. Classify: Implementation Defect vs Systematic Issue

For **every** finding from 4a–4d and 4i, classify it into exactly one bucket:

| Bucket | Definition | Example | Action |
|--------|-----------|---------|--------|
| **Implementation defect** | A bug, omission, or incomplete item from *this* implementation that should be fixed in code | "traceparent field added but constructors not updated" | Add to **Defects to Fix** list (Step 6) — these are code changes, not process changes |
| **Systematic issue** | A process, tooling, or knowledge gap that is likely to recur across *future* work | "No quality gate catches missing struct field propagation" | Propose skill/CLAUDE.md/tool improvement (Step 6) |

**Key distinction:** If the finding describes something that was simply missed or done wrong in this specific implementation, it's a defect — fix it in code. Only escalate to systematic improvements when the root cause is a recurring gap in process, tooling, or documentation. A one-off mistake is not a systematic issue.

**Propagation rule — shared-source phantoms (MANDATORY):** When a systematic finding traces back to a **RESEARCH template, a shared research artifact, or any reused source** (not a mistake local to this feature), a local fix is insufficient. The retro plan MUST include a **propagation edit to that shared source** as a separate work unit — so sibling features that inherited the same artifact cannot inherit the same phantom. Concretely: the `Arc<dyn Trait>` "use a `Guard` for zero-copy reads" NO-OP appeared in both `d7-wavetable-generation` and `d8-tempo-sync` because `d7`'s retro fixed it locally without updating the RESEARCH content; `d8` re-inherited it on the next cycle. Identify the upstream source (RESEARCH_SUMMARY.md, a shared component, a template) and schedule its correction as a plan work unit in Step 6b — do not leave it for the affected sibling's own retro to re-discover.

### 4f. What Went Well

- Patterns that worked efficiently
- Correct early decisions that saved time later
- Effective use of parallelism or decomposition

### 4g. Spec Alignment Assessment (when Subagent E ran)

Produce a summary alignment table from Subagent E's findings:

| Domain | Spec Coverage | Runtime Verified | Confidence | Gap |
|--------|--------------|-----------------|------------|-----|
| ... | ... | ... | ... | ... |

Overall alignment score: weighted average of confidence across all spec requirements.

If alignment < 80%, this is a **critical finding** — the implementation is incomplete despite phases being marked done. Propose corrective phases in Step 6.

### 4h. Context Loss Assessment (when Subagent F ran)

Summarize how context compaction affected the implementation:
- Compactions per phase (did later phases suffer more drift?)
- User intervention frequency (did the user have to manually correct the orchestrator?)
- Plan adherence (did the orchestrator follow its own plan, or improvise post-compaction?)
- Recommendation: was the plan too large? Should it have been split? Was the SessionStart compact hook in place?

### 4i. Skill Compliance Assessment (from Subagent G)

Incorporate Subagent G's compliance report. For any requirement below 100%:
- Classify as implementation defect (one-off miss) or systematic issue (skill enforcement too weak)
- If Implementation Notes are incomplete: flag as **high** — downstream phases and retros depend on them
- If QG evidence is missing: flag as **medium** — may indicate skipped gates
- If TDD evidence is weak: assess whether the feature's nature warranted TDD (pure config/scaffolding may not)

Overall compliance < 80% is a **systematic issue** — propose skill enforcement improvements in Step 6.

---

## Step 5: Clarify Expectations

**If `--auto` flag was set:** Skip this step entirely. Prioritize all findings by impact (blocked > rework > friction > minor). Propose changes to skills, CLAUDE.md, and tools as appropriate based on findings.

**Otherwise:** Use **AskUserQuestion** to align on what improvements to propose:

> Based on my analysis, I found [N] issues across [categories]. The highest-impact improvements I could propose are:
>
> 1. [Brief description of top improvement]
> 2. [Brief description of second improvement]
> 3. [Brief description of third improvement]
>
> Should I focus on all of these, or prioritize specific areas? Also: should I propose changes to skills, CLAUDE.md rules, new tools, or all of the above?

---

## Step 6: Propose Improvements

Based on the findings and user direction, propose concrete changes. Each proposal must be actionable:

### Defects to Fix

List all findings classified as **implementation defects** in Step 4e. These are code-level fixes, not process improvements:

| Defect | Files Affected | Severity | Suggested Fix |
|--------|---------------|----------|---------------|
| ... | ... | ... | ... |

If the retro was run on completed work that is still in-progress or pre-merge, these should be fixed before merging. If already merged, propose them as follow-up work items.

**Do NOT convert implementation defects into CLAUDE.md rules or skill changes.** A missed constructor update is a bug to fix, not a documentation gap to fill.

### Skill Changes (create / update / remove)

Skills are organized using a decomposition system (see `/crud-skill` for the full spec):
- **Skills** live at `~/.claude/skills/<name>/SKILL.md` (user-level) or `.claude/skills/<name>/SKILL.md` (repo-scoped)
- **Shared components** live at `~/.claude/skills/_components/<name>.md` — injected into skills via the `!` + backtick-quoted `cat` directive (see any SKILL.md with a component injection for the exact syntax)
- A single component edit propagates to ALL skills that inject it — always check the blast radius

**Comprehension requirement (MANDATORY):** Before proposing any change to a skill or component, you MUST:
1. **Read the target skill/component in full** — not just the section you want to change
2. **Understand its purpose** — what class of work does it orchestrate? What are its invariants?
3. **Check for existing coverage** — does the skill already address this concern (perhaps differently than you'd propose)?
4. **Assess fit** — would your proposed change distort the skill's primary purpose or add orthogonal concerns?

If a proposed change doesn't fit the target skill's purpose, either find a more appropriate skill, propose it as a CLAUDE.md rule instead, or drop it (if it's an implementation defect, not a systematic issue).

**Generalization rule (MANDATORY):** Every proposed skill or CLAUDE.md change must target a **class of problem**, not a specific instance. Before proposing any change, apply this test:

| Question | If NO → | If YES → |
|----------|---------|----------|
| Would this rule prevent at least 3 different specific mistakes? | Drop it — over-fitted to one incident | Proceed |
| Could a reader understand this rule without knowing what retro produced it? | Rewrite to remove incident-specific language | Proceed |
| Does this rule duplicate logic the target skill/CLAUDE.md already handles? | Drop it — the existing rule wasn't followed, not missing | Proceed |
| Is this rule so broad it would trigger false positives in normal work? | Narrow the scope or add a qualifying condition | Proceed |

Anti-pattern examples:
- BAD: "Always check constructors when adding a field to a struct" → only prevents one specific mistake
- GOOD: "After modifying a type's public surface, verify all construction sites compile" → class-level, catches additions, removals, renames, type changes
- BAD: "Run clippy after changing Rust code" → already covered by quality gates
- GOOD: "Quality gates must include cross-crate type propagation checks" → identifies a gap in existing process

For each proposed change, identify the correct target:
- **Component change:** If the improvement affects shared behavior (e.g., subagent briefing, quality gates, MCP testing) → edit the component file. List all skills that inject it.
- **Skill change:** If the improvement affects only one skill's unique logic → edit the SKILL.md
- **New component:** If the improvement adds reusable logic (>10 lines, used by 2+ skills) → create a new component, inject it into relevant skills
- **New skill:** Only if a new workflow is needed — not for extending existing ones

For each proposed change:
- **Target:** component name or skill name
- **File:** exact path
- **Action:** create | update | remove
- **Blast radius:** which skills are affected (list them)
- **Rationale:** what problem it solves
- **Draft:** key rules or steps

**Coupling rule:** `/implement-phase` and `/implement-phase-batch` should almost always be updated together — they share the same execution model and components. If proposing a change to one, apply it to both unless there's a specific reason not to. Same for `/spec-phases` and `/spec-phases-batch`.

### CLAUDE.md Updates

For each proposed CLAUDE.md change:
- **File:** path (be specific — project root CLAUDE.md vs subdirectory CLAUDE.md vs user-level CLAUDE.md)
- **Section:** new or existing
- **Content:** the rule, gotcha, or documentation to add
- **Rationale:** what it prevents

**Durability rule:** Every CLAUDE.md update must be **durable and non-transient**. Before proposing any update, verify:
- No references to specific phases, batches, or implementation steps (e.g., "Phase 4", "Batch 2")
- No references to specific features or tasks by name unless the knowledge is permanently relevant to the codebase
- No references to what was "just added" or "recently changed" — these rot immediately
- The content would still be useful to a reader 6 months from now with no context about this retro
- The knowledge captures a **general pattern or invariant**, not a one-time incident

If a finding fails this test, it's either an implementation defect (put it in "Defects to Fix") or not worth documenting.

**Targeting rule:** Place gotchas and rules in the CLAUDE.md closest to the code they affect:
- Project-wide patterns → project root `CLAUDE.md`
- Language/framework-specific → subdirectory `CLAUDE.md` (e.g., `src/composables/CLAUDE.md` for Vue composables)
- Cross-project workflow rules → user-level `~/.claude/CLAUDE.md`
- Never duplicate the same rule in multiple CLAUDE.md files — pick the narrowest scope that covers all affected code

### New Tools / Components

For each proposed tool:
- **Type:** script | component | MCP tool | ESLint rule | etc.
- **Purpose:** what it automates
- **Trigger:** when it would be used

### Process Changes

For changes that aren't captured in files:
- **Current:** how it works now
- **Proposed:** how it should work
- **Rationale:** why the change improves outcomes

---

## Step 6b: Write Improvement Plan File

Convert all proposed improvements from Step 6 into a self-contained execution plan. The plan should include:
- All defect fixes as work units (with file paths and suggested changes)
- All skill/component changes as work units
- All CLAUDE.md updates as work units
- All new tool/component creation as work units

**Retro-specific plan content:**
- Skill/component file edits (`.md` in `~/.claude/skills/` or `~/.claude/skills/_components/`) may be done directly by the orchestrator — these are documentation, not source code
- Rust/TypeScript source changes (e.g., new MCP tools, ESLint rules) MUST go to subagents
- When editing a component, include blast radius check: `grep -r "component-name.md" ~/.claude/skills/ --include="*.md" -l`
- Include `python ~/.claude/scripts/project-skills.py` verification step after all skill/component changes
- If the retro proposed PHASES.md additions (corrective phases), include those as work units
- If `~/.claude/skills/` and `~/.claude-personal/skills/` are symlinked (same files), no mirroring needed. If separate, copy changed files to both directories.

**Frontmatter for retro plans (override defaults from plan-file-output.md):**

When writing the retro plan file, the YAML frontmatter MUST use:
- `kind: retro-plan` (NOT `implementation-plan`)
- `feature_id:` — the feature directory name being retrospected
- `status: Ready` (or `Draft` if `--batch` halted mid-generation)
- `created:` — today's date
- `phases:` — list every PHASES.md phase covered by this retro. For a first-ever retro on a feature, this is typically every phase that has landed (e.g. `[1, 2, 3, 4, 5]`, or just `["all"]` if the feature uses non-numeric phase IDs). For a follow-up retro (retro-2, retro-3), list only the phases that have landed since the previous retro.

The retro plan file is colocated with the feature's other plans (`<feature-dir>/plans/retro-N-<slug>.md`) so the state script's `find_retro_plans()` discovers it the same way as implementation plans.

!`cat ~/.claude/skills/_components/plan-file-output.md`

---

## Step 6b.5: Spec-Body Fixer (Minor divergences only — propagate inline)

**Rationale.** The walk pattern repeatedly observed: `/retro` writes a `## Spec Divergences > Minor` table into the retro plan file, then the plan is archived without `/execute-plan` ever running its Minor rows — the SPEC body never catches up. Examples: research resolved every item under a "Needs Research" checklist but the checklist still shows `- [ ]` unchecked; SPEC advertises a deprecated API in its surface table that research deferred; SPEC `Status: Draft` despite every PHASES.md phase Complete. These are mechanical doc-drift fixes — not design decisions — so the fixer dispatches a dedicated Sonnet subagent to apply them inline and patches the plan file's Minor rows to mark them resolved. **Significant rows are untouched** — those continue to flow through `/add-phase` / follow-up retro as designed.

### When to run

Run iff Step 6b just wrote a retro plan whose `## Spec Divergences > Minor` table has **at least one** data row. Skip when the Minor table is empty (no rows = nothing to propagate) or absent (no `## Spec Divergences` section at all = retro was a clean pass).

### When to skip the dispatch entirely

- Runtime evidence was unavailable AND the Minor table was synthesized from code-level analysis only (the Step 4 top-level note `"Runtime evidence unavailable in this session"` is present). The fixer would be guessing about Minor row evidence; skip and leave the rows un-resolved for a later interactive retro to verify.
- The orchestrator caller (`/lazy-batch`, `/lazy-batch-cloud`) is already inside Step 1c.5 pseudo-skill handling — irrelevant since `/retro --batch` is always dispatched as a real-skill cycle, never as a pseudo-skill, so this case cannot arise in practice. Documented for completeness.

### Algorithm

1. **Parse the Minor table from the just-written plan file.** Read `{spec_path}/plans/retro-N-<slug>.md` and locate the `## Spec Divergences > ### Minor` table. Extract each data row as `{idx, item, nature_of_divergence}`. If parsing fails (table malformed, missing header), skip Step 6b.5 entirely and note the parse failure in the chat output — do NOT improvise.

2. **Compose the spec-body-fixer prompt.** ONE Sonnet subagent for ALL Minor rows (Q1 of the design — single commit, easier to audit, no SPEC.md race). The subagent receives the full table content + `{spec_path}/SPEC.md` + `{spec_path}/RESEARCH_SUMMARY.md` (or `RESEARCH.md` if summary absent).

3. **Dispatch.**

   ```
   Agent({
     description: "retro spec-body-fixer for {feature_id} ({N} minor rows)",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <the prompt below>
   })
   ```

   **Subagent prompt:**

   ```
   You are the /retro spec-body-fixer subagent. Your sole job is to propagate
   the Minor doc-drift divergences from the retro plan into the SPEC.md body
   inline — turning each "Needs Research" checklist whose answers exist in
   RESEARCH_SUMMARY.md into a "Resolved by Research" block with the answers
   inlined; bumping stale counts; removing deferred APIs from surface tables;
   flipping stale Status fields when all phases are Complete; and so on.

   Feature: {feature_id}
   Working directory: {cwd}

   Inputs you MUST read first:
     - {spec_path}/SPEC.md
     - {spec_path}/RESEARCH_SUMMARY.md (or RESEARCH.md if summary absent)
     - {spec_path}/PHASES.md (for Status / phase-completion cross-checks only)
     - The Minor divergences table below (verbatim from this round's retro plan)

   HARD SCOPE — non-negotiable:
     - You MAY Edit ONLY {spec_path}/SPEC.md. No other file.
     - You MUST NOT touch source code, tests, PHASES.md, plan files, sentinels,
       or any file outside {spec_path}/SPEC.md.
     - You MUST NOT call Skill, MUST NOT dispatch further subagents, MUST NOT
       call AskUserQuestion. Halt with a one-line summary if you encounter a
       row that requires judgment (see "Row-skipping" below).
     - You MUST commit exactly once at the end with all SPEC.md edits in a
       single commit (per the project's commit policy at
       .claude/skill-config/commit-policy.md if present, else the standard
       pattern).

   Row-by-row algorithm:
     For each Minor row in the table:
       a. Identify the target SPEC.md section / line referenced by the row's
          "Item" column.
       b. Apply the correction described in "Nature of Divergence":
          - "Needs Research checklist with N unchecked items" → rewrite the
            section heading from "Needs Research" to "Resolved by Research"
            (keep the original heading level), replace each `- [ ]` with
            `- [x]`, and append the one-line answer from RESEARCH_SUMMARY.md
            to each item (format: `- [x] <original question> — <answer from
            research>`).
          - "Stale count (e.g., 19 vs actual 49)" → update the number in
            place; leave surrounding prose intact.
          - "Deferred API still advertised in surface table" → delete the row
            from the surface table; if the row had narrative prose elsewhere
            that referenced it, leave the prose alone (out of scope).
          - "Status: Draft despite phases Complete" → flip the `Status:` line
            to `Complete`; bump `Last updated:` to today's date if present.
          - "Duplicate deliverable in single phase (both [ ] and [x])" → this
            is a PHASES.md issue, NOT a SPEC.md issue. SKIP this row and
            report it in your row-skipping list — out of fixer scope.
          - Any other Minor row whose fix is genuinely mechanical and
            unambiguous → apply.
       c. If the target text is NOT findable (the SPEC section was already
          fixed, was renamed since the retro snapshot, or the row's
          description is ambiguous about WHICH line to edit), SKIP the row.
          Do NOT improvise.

     After all rows are processed:
       1. Run a final read of SPEC.md to confirm the edits applied cleanly
          (no syntax breakage in markdown tables, no orphaned bullets).
       2. Commit with message:
          docs({feature_id}): retro round N — propagate minor spec divergences inline
          The commit should contain ONLY {spec_path}/SPEC.md.
       3. Return a one-paragraph summary (≤ 8 lines) covering:
          - N total Minor rows attempted.
          - List of row indices applied (e.g. "applied: 1, 2, 4").
          - List of row indices skipped + one-line reason per skip (e.g.
            "skipped: 3 — target text not found, may already be fixed").
          - The commit sha.
          - Any failures (commit refused, dirty tree, etc.).

   Minor divergences table (verbatim from this round's retro plan):

   ---
   {paste the Minor table content here, including the header row}
   ---

   Begin.
   ```

4. **Patch the plan file's Minor rows.** After the subagent returns, re-read the plan file and update the `## Spec Divergences > ### Minor` table:
   - For each applied row (per the subagent's report), append a final column note (or trailing parenthetical inside the row's last cell): `(resolved inline by Step 6b.5 — commit <sha>)`.
   - For each skipped row, append: `(skipped by Step 6b.5 — <reason>)`.
   - Do NOT delete rows; mark them. The audit trail is the value here — the next reader sees both the original drift and how it was resolved.
   - Re-write the plan file with the modified table. This is a SECOND commit on the plan file. Commit message: `docs({feature_id}): retro round N — mark minor divergences resolved inline`.

5. **Chat-output note.** Print a one-line confirmation: `🔧 Step 6b.5: spec-body-fixer applied {N_applied}/{N_total} minor rows (commit {sha}); skipped {N_skipped} — see plan file for details.`

### `--auto` / `--batch` mode

Step 6b.5 runs in `--auto` and `--batch` modes identically to interactive. The fixer's row-skipping discipline (skip when the target text isn't findable) is the mechanical-vs-judgment guardrail — it never invents an edit, so it cannot "decide on the user's behalf" the way the deferred-to-`/execute-plan` flow did silently. If the fixer skips most rows for genuine ambiguity, that's a signal the Minor table was over-classified and a follow-up retro / interactive review is warranted; the plan file's annotated rows make this visible.

### Interactive mode

In interactive mode (no `--auto`/`--batch`), Step 6b.5 still runs. The user can review the fixer's commit before Step 6c writes RETRO_DONE.md (one commit window between the two steps), and revert the SPEC.md commit if dissatisfied — the plan file's Minor rows record what was attempted, which preserves the audit trail even if the SPEC edit is reverted.

---

## Step 6c: Write `RETRO_DONE.md` sentinel (when no significant divergences)

**HARD REQUIREMENT — applies in ALL modes (interactive, `--auto`, `--batch`).** If the **Significant** divergence table written in Step 6b's plan has NO data rows — i.e. this retro round's conclusion is "ready for the next step, no corrective work needed" — the skill MUST write a terminal `RETRO_DONE.md` sentinel before returning. Without it, the next `/lazy` / `/lazy-batch` cycle re-enters Step 9 retro and runs again on the same evidence, because `lazy-state.py`'s `find_retro_plans()` may still see this round's plan (or an earlier round's plan) as `status: Ready` and re-dispatch retro.

The retro skill is the natural emitter of this sentinel because it owns the "no significant divergences" decision (via Subagent B's classification) and has the round-count / plan-list context from Step 6b's frontmatter computation. The orchestrator (`/lazy-batch` / `/lazy-batch-cloud`) only sees a dispatch summary, not the divergence classification — so it cannot reliably emit the sentinel.

### When to write

Write `RETRO_DONE.md` **iff** the following holds:

1. Step 6b just wrote a retro plan whose `## Spec Divergences` → `### Significant` table has **zero** data rows (separator rows and the header row don't count).

**No MCP precondition.** Under the current state-machine ordering, `/retro` runs at **Step 8** — BEFORE `/mcp-test` (Step 9). The entry gate is simply "all PHASES.md phases Complete AND no open BLOCKED/NEEDS_INPUT"; neither `VALIDATED.md` nor `DEFERRED_NON_CLOUD.md` are required to exist when retro runs. The earlier rule that gated `RETRO_DONE.md` on one of those sentinels existing was a holdover from the old MCP-before-retro order; it has been removed.

Skip this step (do NOT write the sentinel) iff the retro identified at least one Significant divergence. In that case, the corrective work still needs to ship under a `/add-phase` or follow-on retro plan; `RETRO_DONE.md` is written by a later retro round that verifies the fix and finds no remaining divergences.

### Algorithm

1. **Enumerate retro plans** in `{spec_path}/plans/` matching `retro-*.md` (including the one just written in Step 6b):
   - `rounds` = total count of retro plans on disk (one-indexed — the round just written is the current round number).
   - `retro_plans` = list of basenames (just `retro-N-slug.md`, not absolute paths), sorted by leading `retro-N-` number.

2. **Determine `mcp_validation_status`:**
   - If `{spec_path}/VALIDATED.md` exists → `complete`
   - Else if `{spec_path}/DEFERRED_NON_CLOUD.md` exists → `deferred-to-workstation`
   - Else → `pending` (the normal case under the current ordering — MCP test runs AFTER retro at Step 9, so neither VALIDATED.md nor DEFERRED_NON_CLOUD.md is on disk yet when retro concludes). The downstream state machine reads `mcp_validation_status` only for human-facing audit; it does not gate any state-machine transitions on this field.

2b. **Compute `phase_count_at_retro`:** count the `### Phase` section headings in `{spec_path}/PHASES.md` (e.g. `grep -c '^### Phase' PHASES.md`; if the feature has no PHASES.md, omit the field). This is the retro staleness anchor — if corrective `/add-phase` rounds later grow PHASES.md past this count, `lazy-state.py` routes another retro round and `__mark_complete__` refuses completion until it runs, so a retro never silently stands for phases it never saw.

3. **Write `{spec_path}/RETRO_DONE.md`** per `~/.claude/skills/_components/sentinel-frontmatter.md`:

   ```yaml
   ---
   kind: retro-done
   feature_id: <feature_id resolved in Step 1>
   date: <today YYYY-MM-DD>
   rounds: <N>
   retro_plans: [<retro-1-...md>, <retro-2-...md>, ...]
   mcp_validation_status: complete   # or deferred-to-workstation
   phase_count_at_retro: <count of "### Phase" sections in PHASES.md right now>
   ---

   # Retro Done

   Round <N> of `/retro` concluded with no significant spec divergences —
   the feature is ready to advance past Step 8 (retro). This sentinel
   terminates the retro phase so subsequent `/lazy` and `/lazy-batch`
   cycles skip Step 8 and route to Step 9 (MCP test) — workstation runs
   the test, cloud writes DEFERRED_NON_CLOUD.md.

   ## Round summary

   | Round | Plan | Outcome |
   |-------|------|---------|
   | 1 | retro-1-...md | <one-line> |
   | ... | ... | ... |
   | N | <plan just written> | no significant divergences |
   ```

4. **Commit the sentinel alongside the retro plan from Step 6b** — single logical action, single commit. Commit message convention: `chore({feature_id}): retro round {N} done — no significant divergences`. Follow the project's `.claude/skill-config/commit-policy.md` if present.

### `--auto` / `--batch` mode

This step is REQUIRED in `--auto` and `--batch` mode (autonomous invocations from `/lazy`, `/lazy-batch`, `/lazy-batch-cloud`). Without the sentinel, the autonomous orchestrator will loop on Step 8 — the failure mode this requirement exists to prevent. The `--auto` / `--batch` paths MUST NOT skip Step 6c on the grounds of "the human will write it manually" — the entire point of autonomous mode is that no human is in the loop.

In interactive mode, this step is also required for the same downstream-state-machine reason. The skill should not branch behavior on flag.

### What if a future retro round detects regressions?

If a later session re-runs `/retro` on the same feature and finds new Significant divergences (e.g. a subsequent change introduced spec drift), the operator should delete `RETRO_DONE.md` before re-running retro, OR the retro skill will refuse to overwrite (treating the existing sentinel as a "this round closed cleanly" attestation that must be explicitly revoked). The cleanest invariant: `RETRO_DONE.md` is written by retro and deleted only by `/lazy`'s `__mark_complete__` step (per the sentinel lifecycle table in `sentinel-frontmatter.md`).

---

## Step 7: Close Documentation Tracking (MANDATORY — DO NOT SKIP)

!`cat .claude/skill-config/cog-doc-track-close.md 2>/dev/null || cat ~/.claude/skills/_components/cog-doc-track-close.md`
