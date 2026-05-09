## Commit and Push (project-configurable)

1. Run `git status` — if no uncommitted changes, skip this step entirely.
2. Stage modified files (`git add <file1> <file2> ...` — specific files, never `git add .`)
3. Commit with a conventional-commit message (no AI attribution). Use a HEREDOC.
   Use the message format appropriate to the caller's context:
   - **Phase batch:** `feat(<feature>): Phase N batch B — <description>`
   - **Post-phase:** `chore(<feature>): Phase N — integration fixes and docs`
   - **Spec decomposition:** `spec(phases): decompose <features> into implementation phases`
4. Check if this is a work repo: `git config user.email`
   - If `jacob@cognitoforms.com`: **stop here** — do NOT push. Commit locally only. Push is blocked by hook; Jacob will use `/push` when ready.
   - Otherwise: push to `origin main`
5. If push fails: `git pull --rebase origin main` and retry once. If rebase conflicts → blocking issue.
