---
name: push
description: Squash-push work branch to remote (explicit approval only)
---

<command-name>push</command-name>

# Push Skill

Squash all branch commits into a single clean commit and push to remote. Only for work repos where autonomous push is blocked by hook.

## Instructions

You MUST follow these steps exactly:

### 1. Verify work repo

```bash
git config user.email
```

If the email is NOT `jacob@cognitoforms.com`, this skill is unnecessary — just push normally and stop.

### 2. Determine base branch

Default base branch is `main`. Check what exists:

```bash
git branch -r | grep -E 'origin/(main|master)' | head -1
```

Use `main` if it exists, otherwise `master`.

### 3. Show summary for confirmation

Display the following to the user before proceeding:

- **Branch:** current branch name
- **Base:** the base branch
- **Commits to squash:** count of commits since base (`git rev-list --count <base>..HEAD`)
- **Commit log:** `git log --oneline <base>..HEAD`
- **Diff stats:** `git diff --stat <base>..HEAD`

### 4. Compose commit message

- If the user provided a message as args (e.g., `/push "feat: add payment flow"`), use that message exactly.
- If no message was provided, compose a conventional-commit message from the commit log. Keep it concise (1-2 lines).

### 5. Squash commits

```bash
git reset --soft $(git merge-base HEAD <base>)
```

Then create the single squashed commit:

```bash
git commit -m "<message>"
```

Do NOT add Co-Authored-By attribution — this is Jacob's work repo.

### 6. Push with bypass token

```bash
CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD
```

The `CLAUDE_PUSH_APPROVED=1` prefix bypasses the PreToolUse hook that blocks `git push` in work repos.

### 7. Confirm

Show the user:
- The pushed branch name
- The single commit hash and message
- Remote URL

## Important

- This skill is NEVER auto-invoked. Only runs when Jacob explicitly types `/push`.
- If there are uncommitted changes, stage and include them in the squash.
- If the branch has no commits beyond base, just push the current state (no squash needed).
- If push fails, show the error and suggest `git pull --rebase origin <base>` then retry.
