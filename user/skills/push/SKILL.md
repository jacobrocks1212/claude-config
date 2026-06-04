---
name: push
description: Push work branch to remote (explicit approval only); pass --squash to squash commits first
argument-hint: "[--squash] [commit message]"
---

<command-name>push</command-name>

# Push Skill

Push the work branch to remote. By default, commits are pushed as-is. Pass `--squash` to squash all branch commits into a single clean commit first. Only for work repos where autonomous push is blocked by hook.

## Instructions

You MUST follow these steps exactly:

### 1. Parse arguments

- If `--squash` is present in the args → **squash mode**. Strip `--squash` from the args.
- Any remaining args are the commit message (e.g., `/push --squash "feat: add payment flow"`).
- If `--squash` is absent → **plain push mode**. Skip steps 4–6 (squash steps) entirely.

### 2. Verify work repo

```bash
git config user.email
```

If the email is NOT `jacob@cognitoforms.com`, this skill is unnecessary — just push normally and stop.

### 3. Determine base branch

Default base branch is `main`. Check what exists:

```bash
git branch -r | grep -E 'origin/(main|master)' | head -1
```

Use `main` if it exists, otherwise `master`.

### 4. Show summary for confirmation (squash mode only)

Display the following to the user before proceeding:

- **Branch:** current branch name
- **Base:** the base branch
- **Commits to squash:** count of commits since base (`git rev-list --count <base>..HEAD`)
- **Commit log:** `git log --oneline <base>..HEAD`
- **Diff stats:** `git diff --stat <base>..HEAD`

### 5. Compose commit message (squash mode only)

- If the user provided a message as args (e.g., `/push --squash "feat: add payment flow"`), use that message exactly.
- If no message was provided, compose a conventional-commit message from the commit log. Keep it concise (1-2 lines).

### 6. Squash commits (squash mode only)

```bash
git reset --soft $(git merge-base HEAD <base>)
```

Then create the single squashed commit:

```bash
git commit -m "<message>"
```

Do NOT add Co-Authored-By attribution — this is Jacob's work repo.

### 7. Handle uncommitted changes (plain push mode only)

If there are uncommitted changes, stage and commit them before pushing:

- If the user provided a message as args, use that message exactly.
- Otherwise, compose a concise conventional-commit message from the diff.
- Do NOT add Co-Authored-By attribution — this is Jacob's work repo.

If the working tree is clean, proceed directly to push.

### 8. Push with bypass token

```bash
CLAUDE_PUSH_APPROVED=1 git push -u origin HEAD
```

The `CLAUDE_PUSH_APPROVED=1` prefix bypasses the PreToolUse hook that blocks `git push` in work repos.

### 9. Confirm

Show the user:
- The pushed branch name
- The commit hash(es) and message(s) pushed
- Remote URL

## Important

- This skill is NEVER auto-invoked. Only runs when Jacob explicitly types `/push`.
- Squashing ONLY happens when `--squash` is explicitly passed — never squash by default.
- In squash mode, if there are uncommitted changes, stage and include them in the squash.
- If the branch has no commits beyond base, just push the current state (no squash needed).
- If push fails, show the error and suggest `git pull --rebase origin <base>` then retry.
