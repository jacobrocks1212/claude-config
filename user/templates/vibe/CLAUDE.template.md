# {PROJECT_NAME}

## Quick Reference

| Item | Value |
|------|-------|
| **Stack** | {TECH_STACK} |
| **Tests** | {TEST_FRAMEWORK} |
| **Status** | Phase 1 - Foundation |

## TDD + Review Workflow (MANDATORY)

**Every feature or fix MUST follow this sequence:**

```
RED → GREEN → REVIEW → REFACTOR
```

### Required Skills (INVOKE THESE)

| When | Skill to Invoke |
|------|-----------------|
| Before writing ANY code | `test-driven-development` |
| Before code review | `code-review-excellence` |
| Multiple independent tasks | `dispatching-parallel-agents` |

### The Workflow

1. **Invoke `test-driven-development` skill** - Read it before writing any code
2. **Write a failing test first** - Test the expected behavior before any implementation
3. **Run the test** - Verify it fails for the right reason (RED)
4. **Implement the minimum code** - Just enough to make the test pass
5. **Run tests again** - Verify the test now passes (GREEN)
6. **Invoke `code-review-excellence` skill** - Read it before reviewing
7. **Code Review** - Spawn `/code-review` agent for unbiased review
8. **Address findings:**
   - **Critical/Significant** → Use brainstorming skill to confirm approach with user
   - **Minor** → Auto-fix without asking
9. **Refactor if needed** - Clean up while tests stay green

```
❌ NEVER write implementation code without a failing test first
❌ NEVER skip invoking the TDD skill before starting
❌ NEVER skip the code review step after tests pass
❌ NEVER auto-fix significant issues without user confirmation
✅ ALWAYS invoke `test-driven-development` skill first
✅ ALWAYS start with: "Let me write a test for this behavior..."
✅ ALWAYS invoke `code-review-excellence` before reviewing
✅ ALWAYS ask about significant changes via brainstorming
```

### Parallel Execution

When working on 3+ independent tasks (different files, no shared state):
1. Invoke `dispatching-parallel-agents` skill
2. Spawn multiple subagents in a SINGLE Task tool call
3. Each subagent follows the full TDD workflow independently
4. Review all changes together after completion

### Code Review Integration

After tests pass:

1. **Invoke `code-review-excellence` skill** to load review guidance
2. **Read and follow** `.claude/commands/code-review.md`

> **Note:** Subagents cannot directly invoke /slash-commands. They must read the command markdown file and follow its instructions.

3. **Handle the review results:**
- **Critical issues:** Block and fix immediately
- **Significant issues:** Ask user with brainstorming skill pattern (one question at a time)
- **Minor issues:** Fix automatically, no confirmation needed
- **Nitpicks:** Note but don't fix unless user requests

## Specs (Read These First)

Before making any changes, read the relevant spec:

- **@specs/PRD.md** - User stories, acceptance criteria, requirements
- **@specs/TECH_SPEC.md** - Architecture, schemas, API contracts
- **@specs/current_plan.md** - Active task queue, session log

## Quality Gates

**All must pass before any PR or "done" declaration:**

```bash
{TYPECHECK_COMMAND}     # No type errors
{LINT_COMMAND}          # No lint errors
{TEST_COMMAND}          # All tests pass
{BUILD_COMMAND}         # Build succeeds
```

## Commands

| Command | Purpose |
|---------|---------|
| `/vibe-work` | **Main command** - Autonomously implement next task via subagent |
| `/vibe-work all` | Complete all remaining tasks in current phase |
| `/vibe-spec` | Generate specs from natural language description |
| `/vibe-research` | Synthesize Gemini research document into specs |
| `/code-review` | Spawn review agent for unbiased code review |
| `/commit` | Stage, commit (clean message), and push to remote |

## Autonomous Workflow

Start the orchestrator, then let subagents do the work:

```
1. /vibe-work        → Spawns subagent for next task
2. Subagent does:    → Write test → Implement → Verify → Review → Commit → Push
3. Orchestrator:     → Receives summary, ready for next task
4. Repeat or:        → /vibe-work all (complete entire phase)
```

This preserves orchestrator tokens - all heavy work happens in subagents.

### Subagent Command Usage

**Important:** Subagents cannot directly invoke `/slash-commands`. When a subagent needs to follow a command:

1. **Read the command file:** `.claude/commands/<command-name>.md`
2. **Follow its instructions** exactly as documented

Example: For code review, subagent reads `.claude/commands/code-review.md` and follows its process.

## Conventions

<!-- Project-specific conventions that override or extend global CLAUDE.md -->

### Code Style
- Follow {TECH_STACK} standard conventions
- See global CLAUDE.md for language-specific rules

### Commit Messages
- Format: `type: description`
- Types: feat, fix, refactor, test, docs, chore

### Testing
- TDD: Write failing test first, then implement
- AAA pattern: Arrange, Act, Assert
- Test behavior, not implementation

## File Structure

```
{PROJECT_NAME}/
├── specs/                 # Specifications (PRD, TECH_SPEC, plan)
├── src/                   # Source code
│   ├── [organize by feature or layer]
│   └── ...
├── tests/                 # Test files
├── CLAUDE.md              # This file
└── .claude/
    └── settings.json      # Project hooks
```

## Session Start Checklist

1. Read `specs/current_plan.md` for context
2. Check git status for uncommitted work
3. Review recent commits if resuming someone else's work
4. Run quality gates to verify environment

---

**Need to update specs?** Run `/vibe-spec` with a description of changes.
