#!/bin/bash
# SessionStart hook (Claude Code on the web) — materialize the ~/.claude/*
# symlinks from this repo at container startup.
#
# WHY THIS EXISTS
#   A fresh cloud container clones this repo but ~/.claude has NO symlinks yet,
#   so ~/.claude/settings.json does not exist. Claude Code loads hook
#   registrations from settings at session start, so the lazy pipeline's
#   PreToolUse hooks (lazy-dispatch-guard.sh / lazy-route-inject.sh /
#   lazy-cycle-containment.sh) never load — and the by-reference cycle dispatch
#   (@@lazy-ref nonce=... resolved to the real prompt via the guard's
#   updatedInput) silently breaks: dispatched subagents receive a bare, unusable
#   token and improvise, mutating the repo off-contract. lazy-state.py itself is
#   also missing (~/.claude/scripts is unlinked), so /lazy* is DOA.
#
#   Running the documented cloud self-hosting path — `setup.py bootstrap
#   --target User` — at session start closes the gap. The container caches the
#   resulting filesystem state after the hook completes, so every subsequent
#   session starts with settings.json present and the hooks registered.
#
# SCOPE
#   Cloud-only (guarded on CLAUDE_CODE_REMOTE). Workstations run setup.ps1 /
#   setup.py manually and may keep a real ~/.claude/skills with other content,
#   so this hook never touches them.
#
# CONTRACT
#   Idempotent, non-interactive, synchronous (the symlinks must exist before the
#   agent loop / settings load), and exit 0 on every path so a setup failure can
#   never wedge session startup.
set -uo pipefail

# Only run in the Claude Code on the web remote environment.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

# Repo root: prefer the harness-provided var, else derive from this script's path
# (.claude/hooks/session-start.sh -> repo root is two dirs up).
REPO="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$REPO" ]; then
  REPO="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)" || exit 0
fi
cd "$REPO" 2>/dev/null || exit 0

# Materialize the User-scope symlinks (hooks, scripts, templates, settings.json,
# CLAUDE.md, ...). Idempotent — a no-op when already linked.
python3 setup.py bootstrap --target User >/dev/null 2>&1 || true

# bootstrap deliberately will NOT clobber a real ~/.claude/skills directory (it
# warns + skips), but _components + the lazy skills must resolve through
# ~/.claude/skills. Move a real dir aside ONCE, then symlink to the repo.
if [ ! -L "$HOME/.claude/skills" ]; then
  if [ -d "$HOME/.claude/skills" ] && [ ! -e "$HOME/.claude/skills.env-bak" ]; then
    mv "$HOME/.claude/skills" "$HOME/.claude/skills.env-bak" 2>/dev/null || true
  fi
  ln -sfn "$REPO/user/skills" "$HOME/.claude/skills" 2>/dev/null || true
fi

exit 0
