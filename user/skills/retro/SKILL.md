---
name: retro
description: Retrospective analysis of completed work — identifies issues, incorrect assumptions, and workflow improvements
argument-hint: [feature-name | SPEC path | PHASES path] [--auto]
plan-mode: never
---

# Retro

Reviews completed work (specified by user, or inferred from conversation history) and produces a structured retrospective. Identifies issues encountered, incorrect assumptions, inefficient implementation order, missed parallelism, and proposes concrete workflow improvements. The improvement plan is written to a file for execution via `/execute-plan`.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. The deliverable is a written plan file, not a plan-mode interaction.

### `--auto` Flag

If `$ARGUMENTS` contains `--auto`, this is an autonomous invocation (typically from `/lazy`):
- Strip `--auto` from arguments before processing
- **Skip ALL clarifying questions** (Step 5) — use your best judgment for improvement priorities
- **Skip AskUserQuestion in Step 2** — infer scope from arguments or conversation context; if truly ambiguous, STOP with PushNotification
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
3. **Ambiguous:** Use **AskUserQuestion** — "Which completed work should I review? (feature name, SPEC.md path, or PHASES.md path)"

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

If runtime evidence is needed but unavailable, use **AskUserQuestion**: "This retro requires runtime evidence to validate spec alignment. Should I (a) start the dev app and test, (b) proceed with code-level analysis only, or (c) use existing session logs at [path]?"

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

For **every** finding from 4a–4d, classify it into exactly one bucket:

| Bucket | Definition | Example | Action |
|--------|-----------|---------|--------|
| **Implementation defect** | A bug, omission, or incomplete item from *this* implementation that should be fixed in code | "traceparent field added but constructors not updated" | Add to **Defects to Fix** list (Step 6) — these are code changes, not process changes |
| **Systematic issue** | A process, tooling, or knowledge gap that is likely to recur across *future* work | "No quality gate catches missing struct field propagation" | Propose skill/CLAUDE.md/tool improvement (Step 6) |

**Key distinction:** If the finding describes something that was simply missed or done wrong in this specific implementation, it's a defect — fix it in code. Only escalate to systematic improvements when the root cause is a recurring gap in process, tooling, or documentation. A one-off mistake is not a systematic issue.

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

!`cat ~/.claude/skills/_components/plan-file-output.md`

---

## Step 7: Work Log

!`cat ~/.claude/skills/_components/work-log.md`

**Extra fields for retro:**

| Field | Value |
|-------|-------|
| `retro_scope` | Feature/work reviewed |
| `issues_found` | Count of issues identified |
| `improvements_proposed` | Count of concrete improvements proposed |
| `categories` | Array of issue categories found (e.g. `["incorrect-assumptions", "serial-bottleneck", "tooling-gap"]`) |
