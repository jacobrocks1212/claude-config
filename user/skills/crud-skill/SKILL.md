---
name: crud-skill
description: Create or update a skill (and its components), with automatic decomposition
argument-hint: <skill-name> [description of changes]
plan-mode: flag
---

# CRUD Skill

Create, read, update, or delete Claude Code skills and their shared components. Handles both user-level skills (`~/.claude/skills/`) and repo-scoped skills (`.claude/skills/` in a project).

---

## Step 1: Parse the Request

- Extract the skill name from `$ARGUMENTS`
- Extract any description of what the user wants (creation intent, update request, etc.)
- If `$ARGUMENTS` is empty, use **AskUserQuestion**: "Which skill do you want to create or update?"

---

## Step 1.5: Plan Mode Gate (MANDATORY — DO NOT SKIP)

!`cat ~/.claude/skills/_components/plan-mode-gate.md`

---

## Step 2: Determine Scope

### 2a. User-level vs Repo-scoped

- If the user explicitly says "project skill", "repo skill", or "local skill" → repo-scoped (`.claude/skills/<name>/SKILL.md` in the current project)
- If the user explicitly says "user skill", "global skill", or "user-level" → user-level (`~/.claude/skills/<name>/SKILL.md`)
- If the skill already exists at one scope → use that scope
- If ambiguous, use **AskUserQuestion**: "Should this be a user-level skill (available everywhere) or a repo-scoped skill (only in this project)?"

### 2b. Resolve the Skill Path

- **User-level:** `~/.claude/skills/<name>/SKILL.md` (symlinked to `claude-config/user/skills/`)
- **Repo-scoped:** `.claude/skills/<name>/SKILL.md` (may be symlinked to `claude-config/repos/<repo>/.claude/skills/`)
- File operations work identically through symlinks — no special handling needed

---

## Step 3: Determine Operation

### If skill EXISTS at the resolved path → UPDATE

1. Read the existing SKILL.md in full
2. Read any component files it injects via `!`cat`` references
3. Understand the user's requested change
4. Proceed to Step 4 (Update)

### If skill DOES NOT exist → FUZZY MATCH before creating

The user may have slightly misnamed an existing skill (e.g., "mcp-tester" when they mean "mcp-test", "implement-phases" vs "implement-phase"). Before assuming a new skill is needed:

1. Glob for all SKILL.md files across both scopes:
   - `~/.claude/skills/*/SKILL.md`
   - `~/.claude-personal/skills/*/SKILL.md`
   - `.claude/skills/*/SKILL.md` (current project)
2. Extract skill names from directory names and compare against the requested name. Look for:
   - **Prefix/suffix matches** — requested name starts with or ends with an existing name (or vice versa)
   - **Substring matches** — one contains the other
   - **Plural/singular variants** — trailing "s", "er", "ing" differences
   - **Hyphen-segment overlap** — shared hyphen-delimited segments (e.g., "mcp-test" shares segments with "mcp-tester")
3. Also check the `$ARGUMENTS` description text — it may clarify intent (e.g., "update that skill" implies an existing skill)
4. If close matches are found, use **AskUserQuestion** presenting the matches: "Did you mean one of these existing skills, or do you want to create a new one?"
   - List each close match with its `description:` from frontmatter
   - Include a "Create new skill" option
5. If the user selects an existing skill → resolve its path and proceed to Step 4 (Update)
6. If no close matches, or user explicitly wants a new skill → proceed to Step 5 (Create):
   - If the description is too vague to write a useful skill, use **AskUserQuestion** to clarify:
     - What problem does this skill solve?
     - When should it be invoked? (trigger conditions)
     - What are the key steps or rules?
     - Any model or tool requirements?

---

## Step 4: Update an Existing Skill

### 4a. Assess the Change

Read the full skill and its injected components. Classify the change:

- **Skill-only:** The change affects only this skill's unique logic → edit the SKILL.md directly
- **Component-only:** The change affects shared behavior used by multiple skills → edit the component file(s)
- **Both:** The change spans unique and shared logic → edit both, ensuring consistency
- **Decomposition opportunity:** The update adds logic that overlaps with other skills → propose extracting a new component (see Step 6)

### 4b. Apply the Change

- Edit the SKILL.md and/or component files
- Preserve existing frontmatter (`name:`, `description:`, `argument-hint:`, `model:`, `allowed-tools:`)
- Preserve `!`cat`` injection points — do not inline component content
- If modifying a component, verify the change doesn't break OTHER skills that inject it by reading those skills' headers to understand their usage context

### 4c. Verify

- Read the updated file(s) back
- Confirm the change matches the user's intent
- If a component was modified, list all skills that inject it so the user is aware of the blast radius

---

## Step 5: Create a New Skill

### 5a. Draft the Skill

Write the SKILL.md with:

**Frontmatter (required):**
```yaml
---
name: <skill-name>
description: <one-line description — this appears in the skill list>
argument-hint: <usage hint> (if the skill takes arguments)
model: <model> (only if a specific model is required, e.g., haiku for lightweight tasks, opus for complex reasoning)
allowed-tools: <tool list> (only if the skill needs restricted tool access)
plan-mode: required | flag (optional — "required" always enters plan mode; "flag" enters only when --plan is in $ARGUMENTS)
---
```

**Body:**
- Clear H1 title
- Brief overview paragraph (when to use, what it does)
- Step-by-step instructions using imperative language
- Inject existing components where applicable (see Step 6)

**Component injection syntax:**

Place a line like the one in Step 1.5 above (the `plan-mode-gate.md` injection). The format is: `!` followed by a backtick-quoted `cat` command targeting `~/.claude/skills/_components/{name}.md` (or `~/.claude/skills/_components/{namespace}/{name}.md` for namespaced components). The line must contain nothing else — just the injection directive.

**Capability namespaces:** Components under `_components/{namespace}/` are only expanded for repos whose `skill-config/capabilities.txt` lists that namespace. Core components (directly in `_components/`) are always expanded. Repos without `capabilities.txt` get all components (permissive default — opt-in filtering).

**WARNING:** The runtime skill loader expands ALL lines matching the injection pattern regardless of markdown context (including inside code blocks and inline code spans). Never include the full literal pattern as an example in a skill file — always reference an existing live injection (like Step 1.5) instead. The lint script (`python ~/.claude/scripts/lint-skills.py`) catches these embedded patterns — Step 7 runs it before projection.

### 5b. Check for Component Reuse

Scan the existing shared components to see if any apply:

| Component | Use when the skill... |
|---|---|
| `subagent-partitioning.md` | partitions deliverables into work units and batches (sizing rules, file-overlap handling, anti-patterns) |
| `subagent-launch.md` | dispatches parallel Sonnet subagents (test-first pipeline for TDD work units) |
| `subagent-review.md` | needs batch review after subagent work (includes TDD discipline check) |
| `tdd-protocol.md` | needs to decide whether a work unit requires TDD (decision gate) |
| `tdd-test-agent.md` | needs a test-writing agent briefing (write failing tests only, no impl) |
| `implementation-agent.md` | needs an implementation agent briefing (make failing tests green, no test changes) |
| `quality-gates.md` | runs project-specific build/test/lint gates |
| `phases-update.md` | updates a PHASES.md file |
| `integration-verification.md` | verifies cross-agent integration + spec alignment |
| `claude-md-review.md` | reviews/updates CLAUDE.md files |
| `source-reread.md` | re-reads source documents before each batch |
| `task-tracking.md` | tracks work units via TaskCreate/TaskUpdate (test + impl phases separately) |
| `commit-and-push.md` | commits and pushes with conventional-commit messages (project-configurable) |
| `plan-mode-gate.md` | enforces plan mode entry — use with `plan-mode: required` or `plan-mode: flag` in frontmatter |

**Namespaced components** (only included for repos that declare the capability):

| Namespace | Component | Use when the skill... |
|---|---|---|
| `mcp/` | `mcp-integration-test.md` | validates runtime behavior via MCP HTTP tools and session log analysis |

If the new skill uses any of these patterns, inject using the syntax shown in Step 5a instead of writing the logic inline.

### 5c. Present to User

Show the drafted skill and ask for approval before writing. Highlight:
- Trigger conditions (when will this skill activate?)
- Components injected (if any)
- Scope (user-level or repo-scoped)

---

## Step 6: Component Decomposition

Evaluate whether the skill (new or updated) should be decomposed into components.

### When to Propose Decomposition

- The skill contains a protocol block (>10 lines) that is **already duplicated** in another skill → extract to `_components/`
- The skill contains a protocol block that is **likely to be reused** by future orchestration skills → propose extraction
- The skill's update adds logic that **already exists** in a component → inject the component instead

### When NOT to Decompose

- The logic is unique to this one skill and unlikely to be shared
- The block is small (<10 lines) — inline is clearer
- The logic requires skill-specific context that can't be generalized

### How to Decompose

1. Propose the component to the user: name, content summary, which skills would inject it
2. **Decide placement** — core vs namespaced:
   - If the component is universally applicable → `~/.claude/skills/_components/<component-name>.md`
   - If the component only applies to repos with a specific capability (e.g., MCP, Tauri) → `~/.claude/skills/_components/<namespace>/<component-name>.md`
   - Namespaced components are automatically skipped for repos that don't declare the namespace in `skill-config/capabilities.txt`
3. If approved:
   - Write the component file at the appropriate path
   - Replace the inline block in the skill using the injection syntax from Step 5a
   - Update any other skills that have the same inline block

---

## Step 7: Final Verification

After creating or updating:

1. Read the final SKILL.md back — confirm it's well-formed
2. Verify all injection directive paths resolve to existing files
3. Verify frontmatter has `name:` field
4. If repo-scoped, verify the file is appropriately git-excluded or git-ignored (check `.git/info/exclude` and `.gitignore`)
5. Run lint: `python ~/.claude/scripts/lint-skills.py` — must exit 0. Catches broken injections (missing component files) and embedded patterns the runtime would try to expand (e.g. injection syntax used in documentation text). If it fails, fix the flagged lines before proceeding.
6. Run projection: `python ~/.claude/scripts/project-skills.py` — confirm the skill appears in `skills-projected/_default/` with all injections expanded and no errors in the summary output. Check that repos show correct `skipped` counts for namespaced components.
7. Run capability lint: `python ~/.claude/scripts/lint-skills.py --check-projected --check-capabilities` — verifies no cross-repo pollution. Flags repos missing `capabilities.txt` (warning) and namespaced components that leaked into repos that don't declare them (error). Must have 0 errors.
8. Report what was created/updated to the user
9. If user-level, note that skills are tracked in `claude-config`:
   - User-level skills resolve through symlinks to `~/source/repos/claude-config/user/skills/`
   - Repo-scoped skills may resolve through symlinks to `~/source/repos/claude-config/repos/<name>/.claude/skills/`
   - After create/update, suggest: "This change is tracked in claude-config — commit when ready."
