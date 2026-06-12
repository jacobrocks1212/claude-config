#!/bin/bash
# lazy-route-inject.sh — UserPromptSubmit / SessionStart / PostCompact inject hook.
#
# Fast path: if the run marker is absent, exit 0 silently without starting
# Python — one test -f per event, zero overhead for interactive sessions.
#
# Slow path: pipe stdin to lazy_inject.py which runs the full probe form and
# emits a hookSpecificOutput JSON block with additionalContext containing the
# LAZY-ROUTE banner, probe evidence, nonce, and (for post-compact events) the
# re-entry protocol and marker counters.
#
# Python resolution: python3 preferred (WSL / Linux), falling back to python
# (Windows git-bash where python3 may not be on PATH).

# Resolve the state dir (mirrors lazy_core.claude_state_dir() logic).
STATE_DIR="${LAZY_STATE_DIR:-$HOME/.claude/state}"

# Fast path: no marker -> exit 0 silently (interactive session).
if [ ! -f "$STATE_DIR/lazy-run-marker.json" ]; then
  exit 0
fi

# Resolve python interpreter: prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all -- fail open (exit 0, no output).
  exit 0
fi

# Resolve the inject script path relative to this hook's own directory.
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
INJECT_PY="$SCRIPT_DIR/../scripts/lazy_inject.py"

# Fail open when the inject script is missing — a missing script must never
# prevent the hook from exiting cleanly.  Same rationale as the guard hook:
# partial checkout or unresolved symlink must not brick a session.
[ -f "$INJECT_PY" ] || exit 0

# Pipe stdin through the inject CLI.  We do NOT propagate Python's exit code:
# a non-zero exit from UserPromptSubmit / SessionStart hooks causes Claude Code
# to surface a blocking error to the user; the inject hook MUST fail open.
# The Python contract is that any internal error writes a hook-error.json
# breadcrumb and exits 0; unconditional exit 0 enforces this from the shell side.
"$PYTHON" "$INJECT_PY"
exit 0
