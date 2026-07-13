#!/bin/bash
# block-terminal-kill.sh — PreToolUse(Bash|PowerShell) hook.
#
# Block commands that could kill terminal processes during the mobile/remote
# workflow. Terminals run 24/7 — accidental termination requires physical laptop
# access. Rewritten on the stdin-JSON interface (legacy-tool-input-env-hooks-dead):
# the old body read $TOOL_INPUT_command, an env var the hook interface never
# populates, so every payload passed clean (dead code since May 2026).
#
# The PreToolUse payload arrives as stdin JSON ({tool_name, tool_input:{command},
# cwd, ...}); this hook reads tool_input.command TOOL-NAME-AGNOSTICALLY (a kill
# command is a kill command whatever tool emits it — so a Stop-Process fired via
# the PowerShell tool denies exactly like one fired via Bash).
#
# CONTRACT (per user/hooks/CLAUDE.md):
#   * Deny is JSON permissionDecision, NEVER `exit 2` (a PreToolUse non-zero exit
#     is a hard blocking error; the old body used exit 2).
#   * FAIL-OPEN: any parse/match error (malformed JSON, missing python, unexpected
#     payload shape) ALLOWS the tool call (exit 0, no decision).
#   * Python resolution: python3 preferred (WSL/Linux), falling back to python
#     (Windows git-bash where python3 may not be on PATH).

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  # No python at all → fail open (exit 0, no output).
  exit 0
fi

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin and emits a deny hookSpecificOutput block (or nothing for a fast
# allow). It NEVER exits non-zero on an internal error.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON piped
# into this hook. With `-c`, the hook's real stdin (the payload) flows straight
# through to python's sys.stdin.
read -r -d '' _BTK_PY <<'PYEOF'
import json
import re
import sys

# operator-observed false-positive (powershell-tool-bypasses-bash-matched-guards
# item 5): the original `\b(kill|exit|...)\b` word-boundary matches fire on
# INNOCENT text that merely CONTAINS the word — an awk script body
# (`awk '{exit}'`) or a pytest `-k` expression (`-k "test and kill"`) — because
# `\b` only asserts a word/non-word boundary, not "this token invokes a
# command". Tightened to SEGMENT-START anchoring (mirrors
# build-queue-enforce.sh / long-build-ownership-guard.sh's _CMD_START): a
# session-terminating token denies only when it BEGINS a command segment
# (string start, or immediately after a shell separator, with optional leading
# env-assignment(s)) — never when it appears as an embedded/quoted argument
# token. `{` counts as a separator ONLY when followed by whitespace (bash's
# `{ cmd; }` grouping requires a blank after the reserved word) — this is
# exactly what keeps `{exit}` (no space; an awk/PowerShell script-block
# literal) from matching, since real shell grouping never glues `{` directly
# onto the next token.
_ENV_PREFIX = (
    r"(?:"
    r"[A-Za-z_][A-Za-z0-9_]*=\S+\s+"
    r"|\$env:[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:'[^']*'|\"[^\"]*\"|\S+)\s*;\s*"
    r")*"
)
_CMD_START = r"(?:^|[\n;&|(]|\{(?=\s))\s*" + _ENV_PREFIX

# PowerShell backtick line-continuation: the next physical line is part of the
# SAME logical command — collapsed to a space before matching so a continued
# invocation is not accidentally split into two segments by _CMD_START's `\n`.
_PS_LINE_CONTINUATION_RE = re.compile(r"`\r?\n")

_TASKKILL_RE = re.compile(_CMD_START + r"(?:taskkill|Stop-Process)\b", re.IGNORECASE)
_KILL_RE = re.compile(_CMD_START + r"kill\b", re.IGNORECASE)
_KILL_PORT_RE = re.compile(r"kill-port", re.IGNORECASE)
_TERMINATE_RE = re.compile(
    _CMD_START + r"(?:exit|logout|Stop-Computer|Restart-Computer|shutdown)\b",
    re.IGNORECASE,
)
_WT_EXE_RE = re.compile(_CMD_START + r"wt\.exe\b", re.IGNORECASE)


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
    command = _PS_LINE_CONTINUATION_RE.sub(" ", command)

    # (1) Process termination — but allow `npx kill-port` for /mcp-test.
    if _TASKKILL_RE.search(command):
        _deny(
            "BLOCKED: process termination (taskkill/Stop-Process) is not allowed "
            "during the mobile/remote workflow — terminating a terminal requires "
            "physical laptop access. Use `npx kill-port <port>` for port cleanup."
        )
    if _KILL_RE.search(command) and not _KILL_PORT_RE.search(command):
        _deny(
            "BLOCKED: `kill` is not allowed during the mobile/remote workflow. "
            "Use `npx kill-port <port>` for port cleanup."
        )

    # (2) Session/system termination.
    if _TERMINATE_RE.search(command):
        _deny(
            "BLOCKED: session/system termination (exit/logout/shutdown) is not "
            "allowed during the mobile/remote workflow — it would drop a terminal "
            "that requires physical laptop access to restart."
        )

    # (3) Windows Terminal management.
    if _WT_EXE_RE.search(command):
        _deny(
            "BLOCKED: Windows Terminal management (wt.exe) is not allowed during "
            "the mobile/remote workflow."
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
# variable is populated. Run python with the captured body via -c so the hook's
# real stdin (the PreToolUse payload) reaches python untouched.
"$PYTHON" -c "$_BTK_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
