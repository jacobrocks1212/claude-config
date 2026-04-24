---
description: Stage, commit, and push changes with a clean commit message (no AI attribution)
argument-hint: [optional commit message]
model: haiku
name: commit
---

# Commit - Clean Git Workflow

Stage all changes, create a commit with a professional commit message, and push to remote. The commit history will have no indication of AI involvement.

## Process

### 1. Check Git Status

Run `git status` to see what's changed.

If no changes exist, inform the user and stop:
> "No changes to commit."

### 2. Review Changes

Run `git diff --stat` to understand what changed.

Analyze:
- Which files were modified/added/deleted
- The nature of the changes (feature, fix, refactor, test, docs, chore)

### 3. Stage Changes

```powershell
git add -A
```

### 4. Generate Commit Message

If `$ARGUMENTS` provided, use it as the commit message.

Otherwise, generate a commit message following conventional commits format:

**Format:** `type(scope): description`

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `refactor` - Code restructuring without behavior change
- `test` - Adding or updating tests
- `docs` - Documentation only
- `chore` - Build, config, dependencies
- `style` - Formatting, whitespace (no logic change)
- `perf` - Performance improvement

**Rules:**
- Use imperative mood ("add" not "added", "fix" not "fixed")
- Keep first line under 72 characters
- Be specific but concise
- Reference the actual change, not the process

**Good examples:**
- `feat(auth): add password reset flow`
- `fix(api): handle null response from payment gateway`
- `refactor(utils): extract date formatting to shared helper`
- `test(checkout): add edge cases for empty cart`

**Bad examples (never use):**
- ❌ `Update code` (too vague)
- ❌ `Fix bug` (what bug?)
- ❌ `Changes` (meaningless)
- ❌ Any mention of AI, Claude, automation, or agents

### 5. Create Commit

```powershell
git commit -m "[generated message]"
```

**CRITICAL:**
- Do NOT add any footer about Claude, AI, or automation
- Do NOT add Co-Authored-By headers
- Do NOT use --signoff or similar flags
- The commit should look like any human-written commit

### 6. Push to Remote

```powershell
git push
```

If push fails due to upstream changes:
```powershell
git pull --rebase
git push
```

If push fails for other reasons (no upstream, auth), inform the user with the specific error.

### 7. Confirm Success

Output:
```
Committed and pushed: [commit hash short]
  [commit message]
  [N files changed, X insertions, Y deletions]
```

## Examples

**User provides message:**
```
/commit fix login redirect loop
```
→ Commits with message: `fix: login redirect loop`

**Auto-generated from changes:**
If the diff shows new test files for authentication:
→ Commits with message: `test(auth): add unit tests for login validation`

## Important

This command is designed for the autonomous vibe-coding workflow. Commits should be:
- **Professional** - Indistinguishable from manual commits
- **Descriptive** - Future readers understand what changed
- **Clean** - No AI attribution, no automation markers
- **Atomic** - One logical change per commit when possible
