#!/bin/bash
# subagent-wedge-backstop.sh — SubagentStop wedge-backstop hook
# (subagent-wedge-backstop-hook feature; split from turn-routing-enforcement
# decision #14, operator-authorized 2026-07-17).
#
# WHAT IT DOES: mechanically catches a GENUINELY-WEDGED dispatched subagent —
# one that tries to stop/return with pending plan work still incomplete
# (uncommitted changes and/or unchecked plan-WU checkboxes) — and BLOCKS its
# premature stop AT MOST ONCE, forcing it to commit + complete (or write
# BLOCKED.md) instead of returning dead and stranding the pipeline. It is the
# mechanical complement to the SENDER-side turn-end-gate.md prose, which a
# wedged/erroring agent cannot self-enforce.
#
# PLATFORM CONFIRMATION (claude-code-guide, 2026-07-17):
#   - SubagentStop fires ONLY at a subagent's genuine agentic-loop termination,
#     NOT at the mid-turn yields that produce false-`completed` notifications.
#   - Blocking is exit code 2 with a stderr `reason` (or {"decision":"block"}).
#     So — unlike the PreToolUse guards in this dir, where a non-zero exit is a
#     hard error and deny is JSON — this hook BLOCKS via exit 2 and the bash
#     side PROPAGATES python's exit code.
#   - The loop-guard keys on the DOCUMENTED, stable per-subagent `agent_id`
#     field. `stop_hook_active` is UNDOCUMENTED for SubagentStop (absent from
#     its input schema) and is NEVER consulted here.
#   - SubagentStop fires at EVERY nesting level; each subagent has a unique
#     agent_id, so per-agent_id breadcrumbing is well-defined.
#
# FAIL-OPEN (load-bearing): any error / missing field / unresolvable repo /
# breadcrumb I/O failure / no python ⇒ exit 0 (allow the stop). A backstop hook
# that could itself wedge the pipeline is worse than the wedge it prevents. Bias
# to false-negative (let it stop) over false-positive (force-spin a done agent).
#
# The loop-guard breadcrumb lives OUTSIDE any repo — <claude-state>/subagent-
# stops/<agent_id>.json (LAZY_STATE_DIR override in hermetic tests) — so it never
# dirties the very tree the predicate inspects.

WEDGE_BASE_DIR="${LAZY_STATE_DIR:-$HOME/.claude/state}"

# Resolve the scripts dir relative to this hook so the embedded Python can import
# lazy_core (builtins only — dirname is not guaranteed on PATH for git-bash).
# $0 may carry Windows backslashes; normalize to forward slashes first.
SELF="${0//\\//}"
case "$SELF" in
  */*) WEDGE_SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   WEDGE_SCRIPT_DIR="$(pwd)" ;;
esac
WEDGE_SCRIPTS_DIR="$WEDGE_SCRIPT_DIR/../scripts"

# Resolve python: prefer python3 (WSL/Linux), fall back to python (Windows
# git-bash). No python at all → fail open (exit 0) + a breadcrumb, so a dead
# guard plane is never silent (guard-fail-open-leaves-no-trace). Pure bash here
# (date/mkdir/printf; every write `2>/dev/null || true`).
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  _HOOK_NOPY_TS="$(date +%s 2>/dev/null || echo 0)"
  mkdir -p "$WEDGE_BASE_DIR" 2>/dev/null
  printf '{"hook":"subagent-wedge-backstop","error":"no python interpreter on PATH","at":"%s"}' \
    "$_HOOK_NOPY_TS" > "$WEDGE_BASE_DIR/hook-error.json" 2>/dev/null || true
  printf '{"ts":%s,"kind":"error","hook":"subagent-wedge-backstop","repo_root":"","signature":"","detail":"no python interpreter on PATH"}\n' \
    "$_HOOK_NOPY_TS" >> "$WEDGE_BASE_DIR/hook-events.jsonl" 2>/dev/null || true
  exit 0
fi

# The Python body is passed via `-c` (NOT a heredoc): a heredoc would bind the
# python process's stdin to the script body, swallowing the SubagentStop JSON
# piped into this hook. With `-c`, the hook's real stdin (the payload) flows
# straight through to python's sys.stdin. The body is deliberately COMPACT so it
# never approaches the platform `-c` argument-length limit.
read -r -d '' _WEDGE_PY <<'PYEOF'
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_HOOK = "subagent-wedge-backstop"
_STALE_SECONDS = 24 * 3600
_STOPS_SUBDIR = "subagent-stops"
_BASE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)
_REASON = (
    "You are stopping with pending plan work and the completion protocol has "
    "not run. Commit your work and complete the plan (or write BLOCKED.md with "
    "the obstacle), then stop."
)


def _import_lc():
    try:
        sd = os.environ.get("WEDGE_SCRIPTS_DIR")
        if sd and sd not in sys.path:
            sys.path.insert(0, sd)
        import lazy_core
        return lazy_core
    except Exception:
        return None


def _append_event(kind, signature, detail, repo_root=""):
    """Best-effort countable hook-events.jsonl append; FAIL-OPEN, never raises."""
    try:
        lc = _import_lc()
        if lc is not None:
            try:
                lc.set_active_repo_root(repo_root or None)
                rr = str(lc.active_repo_root() or "")
            except Exception:
                rr = repo_root or ""
            try:
                lc.append_hook_event(kind, _HOOK, signature, detail, repo_root=rr)
                return
            except Exception:
                pass
        os.makedirs(_BASE_DIR, exist_ok=True)
        entry = {
            "ts": time.time(), "kind": kind, "hook": _HOOK,
            "repo_root": repo_root or "", "signature": (signature or "")[:200],
            "detail": (detail or "")[:500],
        }
        with open(os.path.join(_BASE_DIR, "hook-events.jsonl"), "a",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _breadcrumb(err):
    """Write a fail-open breadcrumb (+ a countable error event); never raise."""
    try:
        os.makedirs(_BASE_DIR, exist_ok=True)
        with open(os.path.join(_BASE_DIR, "hook-error.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"hook": _HOOK, "error": str(err),
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh)
    except Exception:
        pass
    _append_event("error", "", str(err))


def _allow():
    """Allow the stop: emit nothing, exit 0."""
    sys.exit(0)


def _block(repo_root=""):
    """Block the stop ONCE: stderr reason + exit 2 (the documented mechanism)."""
    _append_event("block", "subagent-wedge", _REASON, repo_root)
    sys.stderr.write(_REASON + "\n")
    sys.exit(2)


def _safe_name(agent_id):
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(agent_id))


def _stops_dir(lc, cwd):
    base = _BASE_DIR
    if lc is not None:
        try:
            lc.set_active_repo_root(cwd or None)
            base = str(lc.claude_state_dir(create=True))
        except Exception:
            base = _BASE_DIR
    return os.path.join(base, _STOPS_SUBDIR)


def _sweep_stale(stops_dir, now):
    """Entry staleness sweep — GC breadcrumbs older than the threshold. Non-fatal."""
    try:
        names = os.listdir(stops_dir)
    except Exception:
        return
    for name in names:
        if not name.endswith(".json"):
            continue
        p = os.path.join(stops_dir, name)
        try:
            with open(p, encoding="utf-8") as fh:
                written = json.load(fh).get("written_at")
            if not isinstance(written, (int, float)):
                written = os.path.getmtime(p)
        except Exception:
            try:
                written = os.path.getmtime(p)
            except Exception:
                continue
        if now - written > _STALE_SECONDS:
            try:
                os.remove(p)
            except Exception:
                pass


def _gc_by_session(stops_dir, session_id):
    """SessionEnd GC — remove breadcrumbs recorded under this session. Non-fatal."""
    try:
        names = os.listdir(stops_dir)
    except Exception:
        return
    for name in names:
        if not name.endswith(".json"):
            continue
        p = os.path.join(stops_dir, name)
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("session_id") == session_id:
                os.remove(p)
        except Exception:
            pass


def _active_plan_unchecked(lc, repo_root):
    """Return the per-plan unchecked-WU counts for every ACTIVE (non-terminal)
    plan under the repo. A Complete/Superseded/Draft plan is not active pending
    work and is excluded (so a non-empty result ⇒ predicate condition 2 holds:
    an active plan whose status != Complete)."""
    counts = []
    for sub in ("features", "bugs"):
        pat = os.path.join(repo_root, "docs", sub, "*", "plans", "*.md")
        for path in glob.glob(pat):
            try:
                status = lc._plan_status(Path(path))
            except Exception:
                status = "Ready"
            if status in ("Complete", "Superseded", "Draft"):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    unchecked, _checked = lc._plan_wu_checkbox_counts(fh.read())
            except Exception:
                unchecked = 0
            counts.append(unchecked)
    return counts


def _git_dirty(repo_root):
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "status", "--porcelain"],
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            return False
        return bool(out.stdout.strip())
    except Exception:
        return False


def _write_breadcrumb(stops_dir, agent_id, session_id, now):
    """Persist the loop-guard breadcrumb (atomic). Returns True on success; a
    write failure returns False so the caller ALLOWS rather than blocking without
    a persisted guard (which would loop block->continue->block forever)."""
    try:
        os.makedirs(stops_dir, exist_ok=True)
        p = os.path.join(stops_dir, _safe_name(agent_id) + ".json")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"agent_id": agent_id, "session_id": session_id,
                       "written_at": now}, fh)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def main():
    now = time.time()
    payload = json.loads(sys.stdin.read())  # JSONDecodeError → outer fail-open
    agent_id = payload.get("agent_id")
    session_id = payload.get("session_id")
    cwd = payload.get("cwd") or ""

    lc = _import_lc()
    stops_dir = _stops_dir(lc, cwd)

    # Staleness sweep on entry (non-fatal) — keeps subagent-stops/ from growing.
    _sweep_stale(stops_dir, now)

    # SessionEnd / agent_id-less branch: GC this session's breadcrumbs, allow.
    if not agent_id:
        if session_id:
            _gc_by_session(stops_dir, session_id)
        _allow()

    # Loop-guard: this agent was already blocked once → allow (block at most once).
    if os.path.exists(os.path.join(stops_dir, _safe_name(agent_id) + ".json")):
        _allow()

    # Predicate condition 1: a run marker is present for the repo.
    if lc is None:
        _allow()
    try:
        lc.set_active_repo_root(cwd or None)
        marker = lc.read_run_marker()
    except Exception:
        _allow()
    if not isinstance(marker, dict):
        _allow()

    repo_root = marker.get("repo_root") or cwd
    if not repo_root:
        _allow()

    # Conditions 2 & 3: an active (non-Complete) plan AND pending work
    # (git dirty OR unchecked plan WUs). No active plan resolves ⇒ fail-open
    # allow (bias to false-negative, per the operator steer).
    active = _active_plan_unchecked(lc, repo_root)
    if not active:
        _allow()
    plan_pending = any(u > 0 for u in active)
    if not (_git_dirty(repo_root) or plan_pending):
        _allow()

    # Predicate TRUE → block ONCE. Write the breadcrumb BEFORE blocking; a write
    # failure ⇒ allow (never block without a persisted loop-guard).
    if not _write_breadcrumb(stops_dir, agent_id, session_id, now):
        _allow()
    _block(repo_root)


try:
    main()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 — fail-OPEN on ANY error.
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

# Run python with the captured body via -c so the hook's real stdin (the
# SubagentStop payload) reaches python untouched. PROPAGATE python's exit code:
# exit 2 blocks the stop, exit 0 allows it (fail-open). `read -d ''` returns
# non-zero at EOF even on success — expected; the variable is populated.
WEDGE_SCRIPTS_DIR="$WEDGE_SCRIPTS_DIR" "$PYTHON" -c "$_WEDGE_PY"
exit $?
