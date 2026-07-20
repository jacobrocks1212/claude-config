#!/bin/bash
# lazy-route-inject.sh — UserPromptSubmit / SessionStart / PostCompact inject hook.
#
# Fast path: if no run marker is present FOR THE CURRENT REPO, exit 0 silently
# without running the full inject probe — interactive sessions (and sessions in
# a repo with no live run) pay only the cost of one read-only marker-presence
# query.
#
# multi-repo-concurrent-runs (Phase 2): the marker is now per-repo. The state
# dir is keyed by repo (~/.claude/state/<repo-key>/) when LAZY_STATE_DIR is
# unset, so a raw `test -f "$STATE_DIR/lazy-run-marker.json"` against the BASE
# dir would always miss. Instead this hook asks the state script
# (`lazy-state.py --marker-present --repo-root <cwd>`) whether a live marker is
# present for the event's repo. Python owns ALL repo-key derivation — bash
# NEVER re-derives it. A marker for a DIFFERENT repo → different subdir →
# absent → no inject.
#
# Slow path: pipe the captured stdin to lazy_inject.py which runs the full probe
# form and emits a hookSpecificOutput JSON block with additionalContext
# containing the LAZY-ROUTE banner, probe evidence, nonce, and (for post-compact
# events) the re-entry protocol and marker counters.
#
# Python resolution + scripts-dir derivation are provided by the shared
# hook-prelude.sh (sourced below): HOOK_PYTHON (python3 preferred, then python)
# and HOOK_SCRIPTS_DIR (resolved relative to this file's own directory).
#
# State dir: LAZY_STATE_DIR env var overrides ~/.claude/state/ for hermetic
# pipe-tests; it is passed through to the --marker-present query unchanged.
#
# Fail-OPEN: if the marker query cannot run (no python, missing script, error),
# fall through to the full inject — a broken query must never silently disable
# injection (here "fail open" means "do not skip the inject"), and the inject
# helper fails open on its own internal errors.

# Capture stdin ONCE — it is a single stream consumed both by the marker-
# presence query (to read the event cwd) and by lazy_inject.py.
PAYLOAD="$(cat)"

# Source the shared hook prelude, fail-open-guarded (shared-hook-lib, SPEC D2).
# A missing/broken prelude ALLOWS (exit 0), never wedges. We derive this hook's
# own directory here ONLY to locate the prelude; the prelude then provides
# HOOK_PYTHON (python3→python resolution; total absence ⇒ pure-bash breadcrumb
# + exit 0 — guard-fail-open-leaves-no-trace §1) and HOOK_SCRIPTS_DIR (the
# sibling user/scripts/ dir). Builtins only for the bootstrap ($0 may carry
# Windows backslashes; `dirname` is not guaranteed on a non-login git-bash PATH).
SELF="${0//\\//}"
case "$SELF" in
  */*) _HOOK_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   _HOOK_DIR="$(pwd)" ;;
esac
. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0
INJECT_PY="$HOOK_SCRIPTS_DIR/lazy_inject.py"
STATE_PY="$HOOK_SCRIPTS_DIR/lazy-state.py"

# Extract the event's cwd from the payload (the repo whose marker we consult).
# On ANY failure CWD stays empty → the marker query is skipped → we fall
# through to the full inject (fail-OPEN: never skip injection on a parse error).
CWD="$(printf '%s' "$PAYLOAD" | "$HOOK_PYTHON" -c \
  'import sys,json
try:
    print((json.load(sys.stdin) or {}).get("cwd","") or "")
except Exception:
    pass' 2>/dev/null)"

# Marker-presence gate: only consult it when we have BOTH a cwd and the state
# script. lazy-state.py --marker-present exits 1 (absent — different repo / no
# run) → fast-path no-inject; exits 0 (present for this repo) → run the full
# inject. Any other condition (script missing, crash, non-0/1 exit) → fall
# through to the inject (fail-OPEN).
if [ -n "$CWD" ] && [ -f "$STATE_PY" ]; then
  LAZY_STATE_DIR="${LAZY_STATE_DIR}" "$HOOK_PYTHON" "$STATE_PY" \
    --marker-present --repo-root "$CWD" >/dev/null 2>&1
  MARKER_RC=$?
  if [ "$MARKER_RC" -eq 1 ]; then
    # No live marker for this repo → no banner to inject → exit silently.
    exit 0
  fi
  # MARKER_RC == 0 (present) → run the inject.
  # MARKER_RC anything else (query error) → fail open: run the inject anyway.
fi

# Fail open when the inject script is missing — a missing script must never
# prevent the hook from exiting cleanly.  Same rationale as the guard hook:
# partial checkout or unresolved symlink must not brick a session.
[ -f "$INJECT_PY" ] || exit 0

# Pipe the captured stdin through the inject CLI.  We do NOT propagate Python's
# exit code: a non-zero exit from UserPromptSubmit / SessionStart hooks causes
# Claude Code to surface a blocking error to the user; the inject hook MUST fail
# open.  The Python contract is that any internal error writes a hook-error.json
# breadcrumb and exits 0; unconditional exit 0 enforces this from the shell side.
printf '%s' "$PAYLOAD" | "$HOOK_PYTHON" "$INJECT_PY"
exit 0
