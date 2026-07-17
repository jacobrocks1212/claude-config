#!/bin/bash
# block-work-repo-git-push.sh — PreToolUse(Bash|PowerShell) hook.
#
# Block `git push` in work repos unless explicitly approved via the /push skill.
# Local `git commit` (checkpoints) is fine. Rewritten on the stdin-JSON interface
# (legacy-tool-input-env-hooks-dead): the old body read $TOOL_INPUT_command, an
# env var the hook interface never populates, so every push passed clean (dead
# code since May 2026).
#
# The PreToolUse payload arrives as stdin JSON ({tool_name, tool_input:{command},
# cwd, ...}); this hook reads tool_input.command TOOL-NAME-AGNOSTICALLY (a work-
# repo push denies whatever tool emits it). The work-repo signal is the repo's
# `git config user.email` read from the payload cwd.
#
# CONTRACT (per user/hooks/CLAUDE.md):
#   * Deny is JSON permissionDecision, NEVER `exit 2`.
#   * FAIL-OPEN: any parse/match error ALLOWS the tool call (exit 0, no decision).
#   * Bypass: CLAUDE_PUSH_APPROVED=1 present anywhere in the command (set by
#     the /push skill; survives a `cd <repo> &&` prefix).
#   * Python resolution: python3 preferred, falling back to python.

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all → fail open (exit 0, no output).
  exit 0
fi

# Inline Python body passed via `-c` (NOT a heredoc — a heredoc binds python's
# stdin and swallows the payload). See block-terminal-kill.sh for the rationale.
read -r -d '' _BWP_PY <<'PYEOF'
import json
import re
import subprocess
import sys

# PowerShell-syntax regex audit (powershell-tool-bypasses-bash-matched-guards):
# the bypass token was recognized only in bash env-assignment form
# (`CLAUDE_PUSH_APPROVED=1`). PowerShell's equivalent is `$env:NAME=value` —
# recognized here as an additional alternative so /push can compose the bypass
# either way.
#
# The token is matched ANYWHERE in the command (search, not a leading match):
# a compound command such as `cd <repo> && CLAUDE_PUSH_APPROVED=1 git push`
# pushes the assignment off the front, so anchoring at `^` denied a legitimately
# bypassed push. `\b` before the bash form still requires it to appear as a
# distinct token (whitespace/`&&`/`;`/start boundary), not glued to other text.
_BYPASS_RE = re.compile(
    r"(?:\bCLAUDE_PUSH_APPROVED=1\b"
    r"|\$env:CLAUDE_PUSH_APPROVED\s*=\s*(?:'1'|\"1\"|1))"
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


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)  # JSONDecodeError → caught below → fail-open
    command = (payload.get("tool_input") or {}).get("command") or ""

    # Only care about git push commands.
    if not re.search(r"\bgit\s+push\b", command, re.IGNORECASE):
        _allow()

    # Allow if the bypass token appears anywhere in the command (set by /push).
    if _BYPASS_RE.search(command):
        _allow()

    # Resolve the work-repo signal from the payload cwd (a git config read from
    # the wrong dir would misclassify — thread cwd into the subprocess).
    cwd = payload.get("cwd") or None
    try:
        proc = subprocess.run(
            ["git", "config", "user.email"],
            cwd=cwd, capture_output=True, text=True,
        )
        email = (proc.stdout or "").strip()
    except Exception:
        _allow()  # git unavailable / cwd gone → fail open

    if email == "jacob@cognitoforms.com":
        _deny(
            "BLOCKED: git push is not allowed in work repos (detected work email: "
            f"{email}). Use /push to push branch commits when ready "
            "(/push --squash \"msg\" to squash first), or ask Jacob to push manually."
        )

    _allow()


try:
    main()
except SystemExit:
    raise
except Exception:  # noqa: BLE001 — fail-OPEN on ANY error.
    sys.exit(0)
PYEOF

# `read -d ''` returns non-zero at EOF even on success — expected; var populated.
"$PYTHON" -c "$_BWP_PY"

# Always exit 0 from the shell side: deny is JSON, never an exit code.
exit 0
