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
  # No python at all — fail open (exit 0, no output). guard-fail-open-leaves-no-trace:
  # this is the severest failure class (the ENTIRE python-bearing guard plane is
  # dead) and precisely the one no python-side appender can record, so the
  # breadcrumb is written here in pure bash (no python required). Best-effort —
  # every write is `2>/dev/null || true` so a breadcrumb failure never turns into
  # a deny or a non-zero exit. Kept as an identical copied block across every
  # python-bearing hook (interim per docs/bugs/guard-fail-open-leaves-no-trace D4
  # — the natural long-term home is a shared hook-prelude, not yet built; keep
  # the copies in lockstep).
  _HOOK_NOPY_BASE="${LAZY_STATE_DIR:-$HOME/.claude/state}"
  _HOOK_NOPY_TS="$(date +%s 2>/dev/null || echo 0)"
  mkdir -p "$_HOOK_NOPY_BASE" 2>/dev/null
  printf '{"hook":"lazy-dispatch-guard","error":"no python interpreter on PATH","at":"%s"}' \
    "$_HOOK_NOPY_TS" > "$_HOOK_NOPY_BASE/hook-error.json" 2>/dev/null || true
  printf '{"ts":%s,"kind":"error","hook":"lazy-dispatch-guard","repo_root":"","signature":"","detail":"no python interpreter on PATH"}\n' \
    "$_HOOK_NOPY_TS" >> "$_HOOK_NOPY_BASE/hook-events.jsonl" 2>/dev/null || true
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

# Extract the tool-call's cwd AND the caller's session_id from the payload in a
# SINGLE python invocation (the cwd is the repo whose marker we consult; the
# session_id owner-scopes the marker-presence gate — stale-marker-arms-validate-
# deny-on-unrelated-dispatches D1). Builtin-only JSON parse is fragile, so use
# python on the captured payload. The parse prints two newline-separated lines
# (cwd, then session_id); the builtin `read` (NO coreutils binary — `sed`/`head`
# are not guaranteed on PATH in a non-login git-bash, same hazard as `dirname`
# noted above) splits them. On ANY failure both stay empty → the marker query
# degrades (CWD empty → skipped → fall through to the guard; SID empty → the
# gate is queried WITHOUT --session-id, i.e. today's session-blind behavior) —
# fail-OPEN: a parse miss never silently disables enforcement.
PARSED="$(printf '%s' "$PAYLOAD" | "$PYTHON" -c \
  'import sys,json
try:
    d = json.load(sys.stdin) or {}
    print(d.get("cwd","") or "")
    print(d.get("session_id","") or "")
except Exception:
    pass' 2>/dev/null)"
# Builtin-only split of the two-line PARSED block into CWD (line 1) and SID
# (line 2). `read -r` consumes the first line; the remainder (the session_id,
# possibly empty) is assigned to SID via a parameter expansion that strips the
# leading "<cwd>\n" prefix.
IFS= read -r CWD <<EOF
$PARSED
EOF
SID="${PARSED#*$'\n'}"
# If PARSED had no newline (parse failure / single line), the expansion above
# leaves SID == PARSED == CWD; normalize that to empty so we never pass the cwd
# as a session id.
[ "$SID" = "$PARSED" ] && SID=""
# Strip any trailing newline(s) from SID (the python print adds one).
SID="${SID%$'\n'}"
# CRLF hardening (Windows git-bash): the python text-mode stdout that produced
# $PARSED can carry a trailing carriage return on each line, which `read -r` /
# the parameter expansions preserve. A stray \r on the repo-root mangles the
# repo key (a DIFFERENT keyed subdir → marker "absent" → spurious fast-path
# allow) and on the session-id breaks the owner match. Strip ALL carriage
# returns from both before they reach the gate query (builtin // expansion —
# no coreutils binary).
CWD="${CWD//$'\r'/}"
SID="${SID//$'\r'/}"

# Marker-presence gate: only consult it when we have BOTH a cwd and the state
# script. lazy-state.py --marker-present exits 1 (absent — different repo / no
# run / a marker bound to a DIFFERENT session when --session-id is supplied) →
# fast-path allow; exits 0 (present for this repo+session) → run the full guard.
# Any other condition (script missing, crash, non-0/1 exit) → fall through to
# the guard (fail-OPEN).
#
# D1: pass --session-id "$SID" ONLY when non-empty, so the gate treats the
# marker as present for its bound OWNER session only — a non-owner same-repo
# dispatch fast-path-allows at the gate (the gate read then AGREES with the
# guard's own session-aware read_run_marker). An empty SID omits the flag and
# degrades to the session-blind gate (fail-OPEN).
if [ -n "$CWD" ] && [ -f "$STATE_PY" ]; then
  if [ -n "$SID" ]; then
    LAZY_STATE_DIR="${LAZY_STATE_DIR}" "$PYTHON" "$STATE_PY" \
      --marker-present --repo-root "$CWD" --session-id "$SID" >/dev/null 2>&1
  else
    LAZY_STATE_DIR="${LAZY_STATE_DIR}" "$PYTHON" "$STATE_PY" \
      --marker-present --repo-root "$CWD" >/dev/null 2>&1
  fi
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
