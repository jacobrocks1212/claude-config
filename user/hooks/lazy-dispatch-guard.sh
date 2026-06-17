#!/bin/bash
# lazy-dispatch-guard.sh — PreToolUse guard hook for lazy orchestrator runs.
#
# Fast path: if no run marker is present FOR THE CURRENT REPO, exit 0 silently
# without running the full guard — interactive sessions (and sessions in a repo
# with no live run) pay only the cost of one read-only marker-presence query.
#
# multi-repo-concurrent-runs (Phase 2): the marker is now per-repo. The state
# dir is keyed by repo (~/.claude/state/<repo-key>/) when LAZY_STATE_DIR is
# unset, so a raw `test -f "$STATE_DIR/lazy-run-marker.json"` against the BASE
# dir would always miss. Instead this hook asks the state script
# (`lazy-state.py --marker-present --repo-root <cwd>`) whether a live marker is
# present for the tool-call's repo. Python owns ALL repo-key derivation — bash
# NEVER re-derives it. A marker for a DIFFERENT repo resolves to a different
# subdir → absent → fast-path allow.
#
# Slow path: pipe the captured stdin to lazy_guard.py which performs the full
# registry lookup and emits allow/deny hookSpecificOutput JSON.
#
# Python resolution: `python3` preferred (WSL / Linux), falling back to
# `python` (Windows git-bash where python3 may not be on PATH).
# Script path: resolved relative to this file's own directory so the hook
# works both from the repo checkout (user/hooks/) and via symlinks from
# ~/.claude/hooks/ that point into the same layout.
#
# State dir: LAZY_STATE_DIR env var overrides ~/.claude/state/ for hermetic
# pipe-tests (the same override used by test_lazy_core.py and test_hooks.py).
# It is passed through to the --marker-present query unchanged so the query
# resolves the exact same dir the writer used.
#
# Fail-OPEN: if the marker query cannot run (no python, missing script, error),
# fall through to the full guard — a broken query must never silently disable
# enforcement (here "fail open" means "do not skip the guard"), and the guard
# itself fails open on its own internal errors.

# Capture stdin ONCE — it is a single stream and is consumed both by the
# marker-presence query (to read the tool-call cwd) and by lazy_guard.py.
PAYLOAD="$(cat)"

# Resolve python interpreter: prefer python3, fall back to python.
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all — fail open (exit 0, no output).
  exit 0
fi

# Resolve the scripts dir relative to this hook's own directory.
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
STATE_PY="$SCRIPT_DIR/../scripts/lazy-state.py"

# Extract the tool-call's cwd from the payload (the repo whose marker we must
# consult). Builtin-only JSON parse is fragile, so use python on the captured
# payload. On ANY failure CWD stays empty → the marker query is skipped → we
# fall through to the full guard (fail-OPEN: never skip enforcement on a parse
# error).
CWD="$(printf '%s' "$PAYLOAD" | "$PYTHON" -c \
  'import sys,json
try:
    print((json.load(sys.stdin) or {}).get("cwd","") or "")
except Exception:
    pass' 2>/dev/null)"

# Marker-presence gate: only consult it when we have BOTH a cwd and the state
# script. lazy-state.py --marker-present exits 1 (absent — different repo / no
# run) → fast-path allow; exits 0 (present for this repo) → run the full guard.
# Any other condition (script missing, crash, non-0/1 exit) → fall through to
# the guard (fail-OPEN).
if [ -n "$CWD" ] && [ -f "$STATE_PY" ]; then
  LAZY_STATE_DIR="${LAZY_STATE_DIR}" "$PYTHON" "$STATE_PY" \
    --marker-present --repo-root "$CWD" >/dev/null 2>&1
  MARKER_RC=$?
  if [ "$MARKER_RC" -eq 1 ]; then
    # No live marker for this repo → nothing to guard → fast-path allow.
    exit 0
  fi
  # MARKER_RC == 0 (present) → run the guard.
  # MARKER_RC anything else (query error) → fail open: run the guard anyway.
fi

# Fail open when the guard script is missing — a missing script must never
# block a run.  This guards against partial checkouts, broken symlinks, or a
# claude-config repo update that has not yet been pulled on this machine.
[ -f "$GUARD_PY" ] || exit 0

# Pipe the captured stdin through the guard CLI.  We do NOT propagate Python's
# exit code: PreToolUse exit 2 is a blocking error in Claude Code (the entire
# tool call is treated as a hard failure), so the guard MUST fail open.  The
# Python contract is that deny is expressed in JSON output, not a non-zero exit
# code; any Python crash is therefore a fail-open event — the dispatch is
# allowed and the breakage is announced via the hook-error.json breadcrumb on
# the next inject turn.  Unconditional exit 0 enforces this contract from the
# shell side.
printf '%s' "$PAYLOAD" | "$PYTHON" "$GUARD_PY"
exit 0
