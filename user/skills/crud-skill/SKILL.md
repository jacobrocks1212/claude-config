---
name: crud-skill
description: Create or update a skill (and its components), with automatic decomposition
argument-hint: <skill-name> [description of changes]
---

# CRUD Skill

Create, read, update, or delete Claude Code skills and their shared components. Handles both user-level skills (`~/.claude/skills/`) and repo-scoped skills (`.claude/skills/` in a project).

---

## Step 1: Parse the Request

- Extract the skill name from `$ARGUMENTS`
- Extract any description of what the user wants (creation intent, update request, etc.)
- If `$ARGUMENTS` is empty, use **AskUserQuestion**: "Which skill do you want to create or update?"

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

### If skill DOES NOT exist → CREATE

1. Understand the user's intent for the new skill
2. If the description is too vague to write a useful skill, use **AskUserQuestion** to clarify:
   - What problem does this skill solve?
   - When should it be invoked? (trigger conditions)
   - What are the key steps or rules?
   - Any model or tool requirements?
3. Proceed to Step 5 (Create)

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
---
```

**Body:**
- Clear H1 title
- Brief overview paragraph (when to use, what it does)
- Step-by-step instructions using imperative language
- Inject existing components via `!`cat`` where applicable (see Step 6)

### 5b. Check for Component Reuse

Scan the existing shared components to see if any apply:

| Component | Use when the skill... |
|---|---|
| `subagent-launch.md` | dispatches parallel Sonnet subagents |
| `subagent-review.md` | needs batch review after subagent work |
| `tdd-protocol.md` | requires TDD (failing test → red → implement → green) |
| `quality-gates.md` | runs project-specific build/test/lint gates |
| `phases-update.md` | updates a PHASES.md file |
| `integration-verification.md` | verifies cross-agent integration + spec alignment |
| `claude-md-review.md` | reviews/updates CLAUDE.md files |
| `source-reread.md` | re-reads source documents before each batch |
| `task-tracking.md` | tracks work units via TaskCreate/TaskUpdate |
| `commit-and-push.md` | commits and pushes with conventional-commit messages (project-configurable) |

If the new skill uses any of these patterns, inject via `!`cat ~/.claude/skills/_components/<component>.md`` instead of writing the logic inline.

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
2. If approved:
   - Write `~/.claude/skills/_components/<component-name>.md`
   - Replace the inline block in the skill with `!`cat ~/.claude/skills/_components/<component-name>.md``
   - Update any other skills that have the same inline block

---

## Step 7: Final Verification

After creating or updating:

1. Read the final SKILL.md back — confirm it's well-formed
2. Verify all `!`cat`` paths resolve to existing files
3. Verify frontmatter has `name:` field
4. If repo-scoped, verify the file is appropriately git-excluded or git-ignored (check `.git/info/exclude` and `.gitignore`)
5. Report what was created/updated to the user
6. If user-level, note that skills are tracked in `claude-config`:
   - User-level skills resolve through symlinks to `~/source/repos/claude-config/user/skills/`
   - Repo-scoped skills may resolve through symlinks to `~/source/repos/claude-config/repos/<name>/.claude/skills/`
   - After create/update, suggest: "This change is tracked in claude-config — commit when ready."
