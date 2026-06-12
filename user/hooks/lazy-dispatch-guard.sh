#!/bin/bash
# lazy-dispatch-guard.sh — PreToolUse guard hook for lazy orchestrator runs.
#
# Fast path: if the run marker is absent, exit 0 silently without starting
# Python — one `test -f` per PreToolUse event, zero overhead for interactive
# sessions.
#
# Slow path: pipe stdin to lazy_guard.py which performs the full registry
# lookup and emits allow/deny hookSpecificOutput JSON.
#
# Python resolution: `python3` preferred (WSL / Linux), falling back to
# `python` (Windows git-bash where python3 may not be on PATH).
# Script path: resolved relative to this file's own directory so the hook
# works both from the repo checkout (user/hooks/) and via symlinks from
# ~/.claude/hooks/ that point into the same layout.
#
# State dir: LAZY_STATE_DIR env var overrides ~/.claude/state/ for hermetic
# pipe-tests (the same override used by test_lazy_core.py and test_hooks.py).

# Resolve the state dir (mirrors lazy_core.claude_state_dir() logic).
STATE_DIR="${LAZY_STATE_DIR:-$HOME/.claude/state}"

# Fast path: no marker → exit 0 silently (interactive session).
if [ ! -f "$STATE_DIR/lazy-run-marker.json" ]; then
  exit 0
fi

# Resolve python interpreter: prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all — fail open (exit 0, no output).
  exit 0
fi

# Resolve the guard script path relative to this hook's own directory.
# Builtins only (${0%/*}, cd, pwd) — `dirname` is a coreutils binary that is
# NOT guaranteed on PATH when git-bash runs non-login (observed: hook env
# without /usr/bin → "dirname: command not found" → mangled script path).
# $0 may carry Windows backslashes (invoked as `bash C:\...\hook.sh`);
# normalize to forward slashes before splitting (builtin string ops only).
SELF="${0//\\//}"
case "$SELF" in
  */*) SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   SCRIPT_DIR="$(pwd)" ;;
esac
GUARD_PY="$SCRIPT_DIR/../scripts/lazy_guard.py"

# Fail open when the guard script is missing — a missing script must never
# block a run.  This guards against partial checkouts, broken symlinks, or a
# claude-config repo update that has not yet been pulled on this machine.
[ -f "$GUARD_PY" ] || exit 0

# Pipe stdin through the guard CLI.  We do NOT propagate Python's exit code:
# PreToolUse exit 2 is a blocking error in Claude Code (the entire tool call
# is treated as a hard failure), so the guard MUST fail open.  The Python
# contract is that deny is expressed in JSON output, not a non-zero exit code;
# any Python crash is therefore a fail-open event — the dispatch is allowed and
# the breakage is announced via the hook-error.json breadcrumb on the next
# inject turn.  Unconditional exit 0 enforces this contract from the shell side.
"$PYTHON" "$GUARD_PY"
exit 0
