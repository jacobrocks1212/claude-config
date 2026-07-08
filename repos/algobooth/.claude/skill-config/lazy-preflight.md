# Lazy-family environment preflight (config pointer)

The canonical Step 0 environment preflight for the `/lazy*` skill family lives at
`~/.claude/skills/_components/lazy-preflight.md`. All six entry points (`/lazy-batch`,
`/lazy-bug-batch`, `/lazy-batch-cloud`, `/lazy`, `/lazy-bug`, `/lazy-cloud`) read and run it as
their first action — before the start banner and before any remote sync — so a missing
symlink / `python3` / node aborts the run with a recipe at **zero cycles consumed**.

## Baked node path (so per-call `export PATH` boilerplate disappears)
- **Windows Git-Bash:** `/c/nvm4w/nodejs` (contains `node.exe`)
- **WSL:** nvm node under `~/.nvm/versions/node/<ver>/bin`, restored via `BASH_ENV` →
  `<claude-config>/user/scripts/claude-bash-env.sh`.

The preflight prepends the Windows home automatically when `node` is not already on PATH.
