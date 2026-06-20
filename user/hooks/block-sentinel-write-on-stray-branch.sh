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
  # No python at all → fail open (exit 0, no output).
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
import json
import os
import subprocess
import sys

# Canonical pipeline sentinel basenames (receipt + halt set). A Write/Edit whose
# target basename is in this set is the only thing this hook can gate.
_SENTINELS = {
    "NEEDS_INPUT.md", "BLOCKED.md", "FIXED.md", "COMPLETED.md", "VALIDATED.md",
}


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
except Exception:  # noqa: BLE001 — fail-OPEN on ANY error.
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
