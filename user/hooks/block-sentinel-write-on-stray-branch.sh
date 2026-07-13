#!/bin/bash
# block-sentinel-write-on-stray-branch.sh — PreToolUse(Write/Edit) hook
# (cycle-subagent-fabricates-policy-or-stray-branch, Phase 3).
#
# DEFENSE-IN-DEPTH WRITE-TIME LAYER for symptom 2 (a cycle subagent fabricates a
# stray branch, then writes a pipeline sentinel onto it where the state scripts —
# which only read the run's work branch — can never see it, silently looping the
# pipeline). The prose ban in cycle-base-prompt.md (Phase 1) is the first layer;
# this hook is the mechanical write-time complement, exactly the two-layer pattern
# block-noncanonical-blocker-write.sh (write-time) + lazy_core.detect_noncanonical
# _blocker (read-time) already establish for the mis-named-blocker class. Keep BOTH.
#
# RULE: deny a Write/Edit whose resolved target BASENAME is a pipeline sentinel
# (NEEDS_INPUT.md / BLOCKED.md / FIXED.md / COMPLETED.md / VALIDATED.md — the
# canonical receipt/halt set) WHILE the current branch differs from the run
# marker's work_branch. The deny NAMES the work branch and instructs the agent to
# switch back and write the sentinel there (a deny without the corrective branch
# just loops the retry — corrective-name discipline, like the noncanonical hook).
#
# FAIL-OPEN on EVERY error path: no python / no marker / --marker-work-branch
# exit 1 (no known work branch to enforce against) / non-sentinel target / git
# failure / malformed payload → ALLOW (emit nothing, exit 0). A PreToolUse
# non-zero exit is a hard blocking error in Claude Code, so the contract is
# fail-OPEN-via-empty-output (exit 0, no decision = allow); the deny is JSON only.
#
# Python resolution: python3 preferred (WSL / Linux), falling back to python
# (Windows git-bash where python3 may not be on PATH).

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all → fail open (exit 0, no output). guard-fail-open-leaves-no-trace:
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
  printf '{"hook":"block-sentinel-write-on-stray-branch","error":"no python interpreter on PATH","at":"%s"}' \
    "$_HOOK_NOPY_TS" > "$_HOOK_NOPY_BASE/hook-error.json" 2>/dev/null || true
  printf '{"ts":%s,"kind":"error","hook":"block-sentinel-write-on-stray-branch","repo_root":"","signature":"","detail":"no python interpreter on PATH"}\n' \
    "$_HOOK_NOPY_TS" >> "$_HOOK_NOPY_BASE/hook-events.jsonl" 2>/dev/null || true
  exit 0
fi

# Resolve the scripts dir relative to this hook's own directory so the inline
# python body can locate lazy-state.py. Builtins only (${0%/*}, cd, pwd) —
# `dirname` is a coreutils binary NOT guaranteed on PATH in a non-login git-bash.
# $0 may carry Windows backslashes; normalize to forward slashes before splitting.
SELF="${0//\\//}"
case "$SELF" in
  */*) SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   SCRIPT_DIR="$(pwd)" ;;
esac
STATE_PY="$SCRIPT_DIR/../scripts/lazy-state.py"

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin, resolves the marker's work_branch (via lazy-state.py
# --marker-work-branch, querying the tool-call cwd's repo) and the current HEAD,
# and denies on a mismatch for a sentinel target. It NEVER exits non-zero on an
# internal error.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON piped
# into this hook. With `-c`, the hook's real stdin (the payload) flows straight
# through to python's sys.stdin. The resolved STATE_PY path is threaded via the
# environment (not argv) so the payload remains python's sole stdin.
read -r -d '' _BSW_PY <<'PYEOF'
import datetime
import json
import os
import subprocess
import sys

# Canonical pipeline sentinel basenames (receipt + halt set). A Write/Edit whose
# target basename is in this set is the only thing this hook can gate.
_SENTINELS = {
    "NEEDS_INPUT.md", "BLOCKED.md", "FIXED.md", "COMPLETED.md", "VALIDATED.md",
}

# guard-fail-open-leaves-no-trace (c): this hook previously had NO error-path
# observability at all (its catch-all was a bare `sys.exit(0)`) — a broken hook
# was indistinguishable from a quiet one. STATE_DIR + _breadcrumb below mirror
# the sibling guards (long-build-ownership-guard.sh / build-queue-enforce.sh)
# that already had this.
STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)


def _allow():
    """Fast allow: emit nothing (PreToolUse with no decision = allow)."""
    sys.exit(0)


def _deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _pick_python():
    """Mirror the bash python3→python resolution for the marker subquery."""
    from shutil import which
    if which("python3"):
        return "python3"
    if which("python"):
        return "python"
    return None


def _append_hook_event(kind, signature, detail, cwd=""):
    """incident-auto-capture Phase 1 (D2): append one countable hook-event line
    (hook-events.jsonl). Best-effort / FAIL-OPEN — never raises, never changes
    the deny/allow output. Prefers the shared lazy_core appender (keyed state
    dir when the repo is resolvable; exact LAZY_STATE_DIR dir in tests); falls
    back to an inline append at the base dir when lazy_core is unavailable.
    The scripts dir is derived from the threaded _BSW_STATE_PY path."""
    try:
        try:
            state_py = os.environ.get("_BSW_STATE_PY", "")
            _sd = os.path.dirname(state_py) if state_py else ""
            if _sd and _sd not in sys.path:
                sys.path.insert(0, _sd)
            import lazy_core
            try:
                lazy_core.set_active_repo_root(cwd or None)
                repo_root = str(lazy_core.active_repo_root() or "")
            except Exception:
                repo_root = cwd or ""
            lazy_core.append_hook_event(
                kind, "block-sentinel-write-on-stray-branch", signature,
                detail, repo_root=repo_root,
            )
            return
        except ImportError:
            pass
        import time as _time
        base = os.environ.get("LAZY_STATE_DIR") or os.path.join(
            os.path.expanduser("~"), ".claude", "state"
        )
        os.makedirs(base, exist_ok=True)
        entry = {
            "ts": _time.time(), "kind": kind,
            "hook": "block-sentinel-write-on-stray-branch",
            "repo_root": cwd or "", "signature": (signature or "")[:200],
            "detail": (detail or "")[:500],
        }
        with open(
            os.path.join(base, "hook-events.jsonl"), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _breadcrumb(err, cwd=""):
    """Write a fail-open breadcrumb; never raise. guard-fail-open-leaves-no-trace
    (c): every python-bearing hook's catch-all must leave a diagnosable trace."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(
            os.path.join(STATE_DIR, "hook-error.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(
                {
                    "hook": "block-sentinel-write-on-stray-branch",
                    "error": str(err),
                    "at": datetime.datetime.now(tz=datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
                fh,
            )
    except Exception:
        pass
    # D2: the breadcrumb stays byte-identical; the countable history is the
    # additive hook-events line beside it (fail-open, never raises).
    _append_hook_event("error", "", str(err), cwd)


def _marker_work_branch(state_py, cwd):
    """Return the run marker's work_branch via lazy-state.py, or None.

    None on ANY non-clean path (script missing, query exit != 0, empty output,
    subprocess error) — the caller fails OPEN on None (no known work branch to
    enforce against).
    """
    if not state_py or not os.path.isfile(state_py) or not cwd:
        return None
    py = _pick_python()
    if not py:
        return None
    try:
        r = subprocess.run(
            [py, state_py, "--marker-work-branch", "--repo-root", cwd],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    branch = (r.stdout or "").strip()
    return branch or None


def _current_head(cwd):
    """Return `git -C <cwd> rev-parse --abbrev-ref HEAD`, or None on any error."""
    if not cwd:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    head = (r.stdout or "").strip()
    return head or None


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)  # JSONDecodeError → caught below → fail-open
    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        _allow()
    tool_input = payload.get("tool_input") or {}
    # Both Write and Edit carry the target as `file_path`.
    file_path = tool_input.get("file_path") or ""
    if not isinstance(file_path, str) or not file_path:
        _allow()
    # Match against the BASENAME only. Normalize backslashes first (Windows path).
    basename = os.path.basename(file_path.replace("\\", "/"))
    if basename not in _SENTINELS:
        _allow()  # non-sentinel target → nothing to gate

    # The tool-call cwd is the repo whose run marker + git HEAD we consult.
    cwd = payload.get("cwd") or ""
    if isinstance(cwd, str):
        cwd = cwd.replace("\\", "/").rstrip("\r").strip()
    else:
        cwd = ""

    state_py = os.environ.get("_BSW_STATE_PY", "")

    work_branch = _marker_work_branch(state_py, cwd)
    if not work_branch:
        _allow()  # no live marker / no known work branch → fail-OPEN (nothing to enforce)

    head = _current_head(cwd)
    if not head:
        _allow()  # cannot resolve HEAD → fail-OPEN

    if head != work_branch:
        # incident-auto-capture D2: countable deny event (fail-open, additive).
        _append_hook_event(
            "deny", "stray-branch-sentinel",
            f"{basename} on {head} (work branch {work_branch})", cwd,
        )
        _deny(
            f"STRAY-BRANCH SENTINEL WRITE DENIED: you are on branch '{head}', but "
            f"this run's work branch is '{work_branch}'. A pipeline sentinel "
            f"('{basename}') written on '{head}' is INVISIBLE to the state "
            "scripts (which only read the run's work branch) and silently loops "
            f"the pipeline. Switch back to '{work_branch}' "
            f"(git checkout {work_branch}) and write '{basename}' there. NEVER "
            "create a branch mid-cycle."
        )
    _allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 — fail-OPEN on ANY error.
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — that is expected; the
# variable is populated. Thread the resolved STATE_PY via env (NOT argv) so the
# hook's real stdin (the PreToolUse payload) reaches python untouched, and run
# the captured body via -c.
_BSW_STATE_PY="$STATE_PY" "$PYTHON" -c "$_BSW_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
