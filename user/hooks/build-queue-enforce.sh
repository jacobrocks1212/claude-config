#!/bin/bash
# build-queue-enforce.sh — PreToolUse(Bash) hook
#
# COGNITO FORMS BUILD-QUEUE SERIALIZER GATE. A machine-global FIFO build queue
# (build-queue.ps1) serializes the four expensive Cognito builds so only one runs
# at a time across worktrees. The four skills /msbuild, /mstest, /nxbuild, /nxtest
# route through that wrapper. This hook makes the queue un-bypassable: it DENIES
# raw heavy-build Bash invocations in Cognito Forms worktrees and redirects the
# agent to the correct skill.
#
# SCOPE GATE: fires only in Cognito Forms worktrees (remote matches
# cognitoforms/cognito). All other repos are fail-open. Remote is resolved via
# `git -C <cwd> config --get remote.origin.url`; any subprocess failure → allow.
# This deliberately differs from block-work-repo-git-push.sh (which gates on
# user.email) — Overwatch and mcp/ share the same work email but have DIFFERENT
# remotes and MUST NOT be gated.
#
# DENY SURFACE (conservative): the command's first real token (after optional
# leading NAME=value env assignments) is one of:
#   * dotnet build
#   * dotnet test
#   * nx / npx nx with a build / test / run-many target
#   * a *-filtered.ps1 script invocation (build-filtered.ps1, test-filtered.ps1,
#     client-build-filtered.ps1, client-test-filtered.ps1)
#
# NEVER denied: dotnet restore, dotnet --version, dotnet ef, nx lint/typecheck/
# format, msbuild, dotnet msbuild, npm, pnpm, the build-queue.ps1 wrapper itself
# (the sanctioned path), or any command prefixed BUILD_QUEUE_BYPASS=1.
#
# BYPASS TOKEN (L6): any command with BUILD_QUEUE_BYPASS=1 as a leading env
# assignment is allowed through immediately (before deny-matching).
#
# KNOWN BLIND SPOT (shared with sibling hooks): a command that `cd`s into a
# different repository before running a build is NOT detected — the hook sees the
# original cwd from the payload and cannot parse cd-chain redirects. This is a
# deliberate non-goal; avoid `cd <other-repo> && dotnet build` patterns.
#
# FAIL-OPEN: any parse/match/subprocess error (malformed JSON, missing python,
# unexpected payload, git failure) ALLOWS the command — a broken hook must never
# block legitimate work. Deny is expressed via JSON permissionDecision: deny;
# a non-zero PreToolUse exit is a HARD error and is never used here.
#
# Python resolution: python3 preferred, falling back to python (Windows git-bash).

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  exit 0
fi

read -r -d '' _BQE_PY <<'PYEOF'
import datetime
import json
import os
import re
import subprocess
import sys

STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)

_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"

# Match the bypass token as a leading env assignment.
_BYPASS_RE = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*BUILD_QUEUE_BYPASS=1(?:\s|$)")

# Match the sanctioned wrapper — allow before any deny-check.
# Matches the wrapper script name anywhere in the command (it may appear inside
# a quoted path as an argument to powershell.exe -File "...path.../build-queue.ps1").
_WRAPPER_RE = re.compile(r"build-queue\.ps1", re.IGNORECASE)

# Deny patterns (anchored; env-prefix tolerant).
_DOTNET_BUILD_RE = re.compile(
    r"^\s*" + _ENV_PREFIX + r"dotnet\s+build(?:\s|$)"
)
_DOTNET_TEST_RE = re.compile(
    r"^\s*" + _ENV_PREFIX + r"dotnet\s+test(?:\s|$)"
)
# nx / npx nx with build, test, or run-many target.
# Matches: nx build X, nx test X, nx run-many --target=build/test,
#          npx nx build X, npx nx test X, npx nx run-many --target=build/test
_NX_BUILD_TEST_RE = re.compile(
    r"^\s*" + _ENV_PREFIX +
    r"(?:npx\s+)?nx\s+"
    r"(?:"
    r"(?:run-many\b.*?--target[= ]\s*(?:build|test)\b)"
    r"|(?:(?:build|test|run-many)\b)"
    r")",
    re.DOTALL,
)
# A *-filtered.ps1 script invoked directly or via powershell.exe.
_FILTERED_SCRIPT_RE = re.compile(
    r"(?:build-filtered|test-filtered|client-build-filtered|client-test-filtered)\.ps1(?:\s|$|\")",
    re.IGNORECASE,
)

# Allow-list for dotnet sub-commands that must NOT be denied even though they
# start with "dotnet build" or "dotnet test" (e.g. dotnet msbuild is separate).
_DOTNET_ALLOW_RE = re.compile(
    r"^\s*" + _ENV_PREFIX + r"dotnet\s+(?:restore|--version|-v|ef|msbuild)\b"
)

# Allow-list for nx targets that are safe (lint, typecheck, format).
_NX_ALLOW_RE = re.compile(
    r"^\s*" + _ENV_PREFIX + r"(?:npx\s+)?nx\s+(?:lint|typecheck|format)\b"
)


def _breadcrumb(err):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(
            os.path.join(STATE_DIR, "hook-error.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(
                {
                    "hook": "build-queue-enforce",
                    "error": str(err),
                    "at": datetime.datetime.now(tz=datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
                fh,
            )
    except Exception:
        pass


def _allow():
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


def _is_cognito_worktree(cwd):
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            return False
        url = result.stdout.strip().lower()
        return "cognitoforms/cognito" in url
    except Exception:
        return False


def _redirect_reason(op, command):
    if op == "dotnet-build":
        return (
            "BUILD QUEUE ENFORCED — use `/msbuild` instead of `dotnet build` directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/msbuild` routes through the queue "
            "automatically.\n"
            "  Correct: /msbuild\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 dotnet build ..."
        )
    if op == "dotnet-test":
        # Try to extract a --filter value for the redirect hint.
        m = re.search(r"--filter\s+['\"]?([^'\"]+)['\"]?", command)
        filter_hint = f' -Filter "{m.group(1)}"' if m else ""
        return (
            f"BUILD QUEUE ENFORCED — use `/mstest{filter_hint}` instead of `dotnet test` directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/mstest` routes through the queue "
            "automatically.\n"
            f"  Correct: /mstest{filter_hint}\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 dotnet test ..."
        )
    if op == "nx-build":
        return (
            "BUILD QUEUE ENFORCED — use `/nxbuild` instead of running nx build directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/nxbuild` routes through the queue "
            "automatically.\n"
            "  Correct: /nxbuild\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 npx nx build ..."
        )
    if op == "nx-test":
        return (
            "BUILD QUEUE ENFORCED — use `/nxtest` instead of running nx test directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. `/nxtest` routes through the queue "
            "automatically.\n"
            "  Correct: /nxtest\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 npx nx test ..."
        )
    if op == "filtered-build":
        return (
            "BUILD QUEUE ENFORCED — use `/msbuild` or `/nxbuild` instead of invoking "
            "*-filtered.ps1 directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. The skills route through the queue "
            "automatically.\n"
            "  Correct: /msbuild (backend) or /nxbuild (frontend)\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ..."
        )
    if op == "filtered-test":
        return (
            "BUILD QUEUE ENFORCED — use `/mstest` or `/nxtest` instead of invoking "
            "*-filtered.ps1 directly.\n"
            "The build queue serializes the 4 expensive Cognito builds across worktrees "
            "so they do not thrash the machine. The skills route through the queue "
            "automatically.\n"
            "  Correct: /mstest (backend) or /nxtest (frontend)\n"
            "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ..."
        )
    return (
        "BUILD QUEUE ENFORCED — use the appropriate skill (/msbuild, /mstest, /nxbuild, /nxtest) "
        "instead of running the build command directly.\n"
        "  Emergency one-off: BUILD_QUEUE_BYPASS=1 ..."
    )


def _classify_filtered_script(command):
    """Return 'filtered-build' or 'filtered-test' based on the matched script name."""
    lower = command.lower()
    if "test-filtered" in lower or "client-test-filtered" in lower:
        return "filtered-test"
    return "filtered-build"


def _classify_nx(command):
    """Return 'nx-build' or 'nx-test' based on target in the matched nx command."""
    lower = command.lower()
    # run-many with explicit --target
    m = re.search(r"--target[= ]\s*(build|test)", lower)
    if m:
        return "nx-build" if m.group(1) == "build" else "nx-test"
    # direct nx build/test
    if re.search(r"(?:npx\s+)?nx\s+test\b", lower):
        return "nx-test"
    return "nx-build"


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)
    if payload.get("tool_name", "") != "Bash":
        _allow()
    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        _allow()

    # L6 bypass token — allow immediately.
    if _BYPASS_RE.match(command):
        _allow()

    # Scope gate — only Cognito Forms worktrees.
    cwd = payload.get("cwd") or os.getcwd()
    if not _is_cognito_worktree(cwd):
        _allow()

    # Allow the sanctioned wrapper before the filtered-script closure.
    if _WRAPPER_RE.search(command):
        _allow()

    # Allow-list: safe dotnet sub-commands.
    if _DOTNET_ALLOW_RE.match(command):
        _allow()

    # Allow-list: safe nx targets.
    if _NX_ALLOW_RE.match(command):
        _allow()

    # Deny surface.
    if _DOTNET_BUILD_RE.match(command):
        _deny(_redirect_reason("dotnet-build", command))

    if _DOTNET_TEST_RE.match(command):
        _deny(_redirect_reason("dotnet-test", command))

    if _NX_BUILD_TEST_RE.match(command):
        _deny(_redirect_reason(_classify_nx(command), command))

    if _FILTERED_SCRIPT_RE.search(command):
        _deny(_redirect_reason(_classify_filtered_script(command), command))

    _allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

"$PYTHON" -c "$_BQE_PY"
exit 0
