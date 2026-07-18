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
# shared-hook-lib (Phase 3): python resolution, the scripts-dir derivation, and
# the no-python breadcrumb are provided by the SOURCED hook-prelude.sh
# (HOOK_PYTHON / HOOK_SCRIPTS_DIR); the allow/deny emitters, the countable
# hook-events append, and the fail-open breadcrumb are provided by hook_lib
# (imported from HOOK_SCRIPTS_DIR by the inline body). The marker-work-branch
# subquery (lazy-state.py) is unchanged — Python owns branch identity.

# Source the shared hook prelude, fail-open-guarded (shared-hook-lib SPEC D2).
# A missing/broken prelude ALLOWS (exit 0), never wedges. Derive this hook's own
# directory here ONLY to locate the prelude; the prelude then provides
# HOOK_PYTHON (python3→python resolution; total absence ⇒ pure-bash breadcrumb
# + exit 0 — guard-fail-open-leaves-no-trace §1) and HOOK_SCRIPTS_DIR (the
# sibling user/scripts/ dir). Builtins only ($0 may carry Windows backslashes;
# `dirname` is not guaranteed on a non-login git-bash PATH).
SELF="${0//\\//}"
case "$SELF" in
  */*) _HOOK_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   _HOOK_DIR="$(pwd)" ;;
esac
. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0
STATE_PY="$HOOK_SCRIPTS_DIR/lazy-state.py"

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin, resolves the marker's work_branch (via lazy-state.py
# --marker-work-branch, querying the tool-call cwd's repo) and the current HEAD,
# and denies on a mismatch for a sentinel target. It NEVER exits non-zero on an
# internal error.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON piped
# into this hook. With `-c`, the hook's real stdin (the payload) flows straight
# through to python's sys.stdin. The resolved STATE_PY path and HOOK_SCRIPTS_DIR
# are threaded via the environment (not argv) so the payload remains python's
# sole stdin.
read -r -d '' _BSW_PY <<'PYEOF'
import json
import os
import subprocess
import sys

# shared-hook-lib (SPEC D2): seed sys.path from HOOK_SCRIPTS_DIR (threaded via
# env) and import hook_lib for the allow/deny emitters, the countable
# hook-events append, and the fail-open breadcrumb. A missing/failed import must
# ALLOW, never wedge — the ONLY retained inline fallback is this minimal
# `except ImportError: sys.exit(0)`.
try:
    _sd = os.environ.get("HOOK_SCRIPTS_DIR")
    if _sd and _sd not in sys.path:
        sys.path.insert(0, _sd)
    import hook_lib
except ImportError:
    sys.exit(0)

_HOOK = "block-sentinel-write-on-stray-branch"

# Canonical pipeline sentinel basenames (receipt + halt set). A Write/Edit whose
# target basename is in this set is the only thing this hook can gate.
_SENTINELS = {
    "NEEDS_INPUT.md", "BLOCKED.md", "FIXED.md", "COMPLETED.md", "VALIDATED.md",
}


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
        hook_lib.allow()
    tool_input = payload.get("tool_input") or {}
    # Both Write and Edit carry the target as `file_path`.
    file_path = tool_input.get("file_path") or ""
    if not isinstance(file_path, str) or not file_path:
        hook_lib.allow()
    # Match against the BASENAME only. Normalize backslashes first (Windows path).
    basename = os.path.basename(file_path.replace("\\", "/"))
    if basename not in _SENTINELS:
        hook_lib.allow()  # non-sentinel target → nothing to gate

    # The tool-call cwd is the repo whose run marker + git HEAD we consult.
    cwd = payload.get("cwd") or ""
    if isinstance(cwd, str):
        cwd = cwd.replace("\\", "/").rstrip("\r").strip()
    else:
        cwd = ""

    state_py = os.environ.get("_BSW_STATE_PY", "")

    work_branch = _marker_work_branch(state_py, cwd)
    if not work_branch:
        hook_lib.allow()  # no live marker / no known work branch → fail-OPEN

    head = _current_head(cwd)
    if not head:
        hook_lib.allow()  # cannot resolve HEAD → fail-OPEN

    if head != work_branch:
        # incident-auto-capture D2: countable deny event (fail-open, additive).
        hook_lib.append_hook_event(
            "deny", _HOOK, "stray-branch-sentinel",
            f"{basename} on {head} (work branch {work_branch})",
            repo_root=cwd,
        )
        hook_lib.deny(
            f"STRAY-BRANCH SENTINEL WRITE DENIED: you are on branch '{head}', but "
            f"this run's work branch is '{work_branch}'. A pipeline sentinel "
            f"('{basename}') written on '{head}' is INVISIBLE to the state "
            "scripts (which only read the run's work branch) and silently loops "
            f"the pipeline. Switch back to '{work_branch}' "
            f"(git checkout {work_branch}) and write '{basename}' there. NEVER "
            "create a branch mid-cycle."
        )
    hook_lib.allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:  # noqa: BLE001 — fail-OPEN on ANY error.
    hook_lib.breadcrumb(_HOOK, exc)
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — that is expected; the
# variable is populated. Thread the resolved STATE_PY + HOOK_SCRIPTS_DIR via env
# (NOT argv) so the hook's real stdin (the PreToolUse payload) reaches python
# untouched, and run the captured body via -c.
_BSW_STATE_PY="$STATE_PY" HOOK_SCRIPTS_DIR="$HOOK_SCRIPTS_DIR" "$HOOK_PYTHON" -c "$_BSW_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
