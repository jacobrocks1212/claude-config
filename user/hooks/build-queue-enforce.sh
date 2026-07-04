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
# DENY SURFACE: a heavy build appears ANYWHERE in the command (not only at the
# start), so a build chained behind a leading command — `cd "..." && dotnet
# build ...`, a pipeline, a `;`-chain — is still caught. The denied forms are:
#   * dotnet build
#   * dotnet test
#   * nx / npx nx with a build / test / run-many target
#   * a *-filtered.ps1 script invocation (build-filtered.ps1, test-filtered.ps1,
#     client-build-filtered.ps1, client-test-filtered.ps1)
#
# NEVER denied: dotnet restore, dotnet --version, dotnet ef, nx lint/typecheck/
# format, msbuild, dotnet msbuild, npm, pnpm, the build-queue.ps1 wrapper itself
# (the sanctioned path — allowed even though it carries a *-filtered.ps1 -Exec
# arg), or any command prefixed BUILD_QUEUE_BYPASS=1.
#
# ALLOW-LIST PRECEDENCE (unanchored): because deny is unanchored, a leading safe
# token can no longer short-circuit the whole command — `dotnet restore && dotnet
# build` MUST still deny (a real build is present). So the safe dotnet/nx variants
# are SUPPRESSED per-occurrence (blanked out of a scratch copy of the command)
# before the unanchored heavy-build scan; if any real heavy build survives the
# suppression, the command is denied.
#
# BYPASS TOKEN (L6): any command with BUILD_QUEUE_BYPASS=1 as a leading env
# assignment is allowed through immediately (before deny-matching).
#
# CLOSED BLIND SPOT: a `cd <dir> && dotnet build` no longer bypasses the deny
# matcher (the build verb is detected wherever it sits in the command). The
# Cognito-worktree SCOPE gate still keys on the payload cwd, so a build that
# `cd`s OUT of a Cognito worktree into a non-Cognito repo is still governed by
# the cwd at dispatch time (fail-open outside Cognito worktrees).
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

# incident-auto-capture Phase 1 (D2): resolve the scripts dir relative to this
# hook so the inline Python can import lazy_core for the keyed hook-events
# append (best-effort — the appender falls back to the base dir when the import
# is unavailable). Builtins only; $0 may carry Windows backslashes.
SELF="${0//\\//}"
case "$SELF" in
  */*) BQE_SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   BQE_SCRIPT_DIR="$(pwd)" ;;
esac
BQE_SCRIPTS_DIR="$BQE_SCRIPT_DIR/../scripts"

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

# Match the bypass token as a leading env assignment.
_BYPASS_RE = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*BUILD_QUEUE_BYPASS=1(?:\s|$)")

# Match the sanctioned wrapper — allow before any deny-check.
# Matches the wrapper script name anywhere in the command (it may appear inside
# a quoted path as an argument to powershell.exe -File "...path.../build-queue.ps1").
_WRAPPER_RE = re.compile(r"build-queue\.ps1", re.IGNORECASE)

# Safe dotnet/nx variants that must NEVER count as a heavy build even though
# they share the "dotnet"/"nx" prefix. These occurrences are blanked out of a
# scratch copy of the command BEFORE the unanchored heavy-build scan, so a
# leading `dotnet restore` no longer masks a trailing `dotnet build`.
_DOTNET_SAFE_RE = re.compile(
    r"dotnet\s+(?:restore|--version|-v|ef|msbuild)\b", re.IGNORECASE
)
_NX_SAFE_RE = re.compile(
    r"(?:npx\s+)?nx\s+(?:lint|typecheck|format)\b", re.IGNORECASE
)

# Command-position anchor (mirrors long-build-ownership-guard.sh): a heavy
# build must be the INVOKED command — either the start of the string, or
# immediately after a shell separator (`&&`, `||`, `|`, `;`, `(`, `{`,
# newline), with optional leading `NAME=value` env assignments. This lets a
# build chained behind a leading command still deny (`cd "..." && dotnet
# build ...`) while a read verb referencing a build token as an ARGUMENT
# (`grep ... test-filtered.ps1`, `cat build-filtered.ps1 | head`) does not
# begin a command segment and so does not match.
_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX

# Deny patterns. Run against the SUPPRESSED command (safe variants blanked out).
_DOTNET_BUILD_RE = re.compile(_CMD_START + r"dotnet\s+build(?:\s|$)", re.IGNORECASE)
_DOTNET_TEST_RE = re.compile(_CMD_START + r"dotnet\s+test(?:\s|$)", re.IGNORECASE)
# nx / npx nx with build, test, or run-many target.
# Matches: nx build X, nx test X, nx run-many --target=build/test,
#          npx nx build X, npx nx test X, npx nx run-many --target=build/test
_NX_BUILD_TEST_RE = re.compile(
    _CMD_START + r"(?:npx\s+)?nx\s+"
    r"(?:"
    r"(?:run-many\b.*?--target[= ]\s*(?:build|test)\b)"
    r"|(?:(?:build|test|run-many)\b)"
    r")",
    re.IGNORECASE | re.DOTALL,
)
# A *-filtered.ps1 script invoked directly (segment-leading, optionally with a
# path prefix so `./x`, `.\x`, and an absolute path still deny) — this does
# NOT match a bare `cat build-filtered.ps1` / `grep x test-filtered.ps1` /
# `find . -name build-filtered.ps1` because the script name there follows a
# read verb, not a command separator.
_FILTERED_SCRIPT_DIRECT_RE = re.compile(
    _CMD_START
    + r"(?:\.?[\\/])?(?:[^\s;&|]*[\\/])?"
    r"(?:build-filtered|test-filtered|client-build-filtered|client-test-filtered)\.ps1"
    r"(?:\s|$|\")",
    re.IGNORECASE,
)
# ...or invoked via `powershell(.exe)?`/`pwsh` with a `-File <path>` argument
# naming one of the four filtered scripts.
_FILTERED_SCRIPT_POWERSHELL_RE = re.compile(
    r"(?:powershell(?:\.exe)?|pwsh)\b[^\n;&|]*-File\s+\S*"
    r"(?:build-filtered|test-filtered|client-build-filtered|client-test-filtered)\.ps1",
    re.IGNORECASE,
)


def _suppress_safe(command):
    """Return a scratch copy of *command* with the safe dotnet/nx variant
    occurrences blanked out, so the unanchored heavy-build scan does not trip on
    them and a leading safe token cannot mask a trailing real build."""
    suppressed = _DOTNET_SAFE_RE.sub(" ", command)
    suppressed = _NX_SAFE_RE.sub(" ", suppressed)
    return suppressed


# incident-auto-capture Phase 1 (D2): the tool-call cwd, captured in main() so
# the event appender can attribute the event to the active repo. Best-effort.
_EVT_CWD = ""


def _append_hook_event(kind, signature, detail):
    """incident-auto-capture Phase 1 (D2): append one countable hook-event line
    (hook-events.jsonl). Best-effort / FAIL-OPEN — never raises, never changes
    the deny/allow output. Prefers the shared lazy_core appender (keyed state
    dir when the repo is resolvable; exact LAZY_STATE_DIR dir in tests); falls
    back to an inline append at the base dir when lazy_core is unavailable."""
    try:
        try:
            _sd = os.environ.get("BQE_SCRIPTS_DIR")
            if _sd and _sd not in sys.path:
                sys.path.insert(0, _sd)
            import lazy_core
            try:
                lazy_core.set_active_repo_root(_EVT_CWD or None)
                repo_root = str(lazy_core.active_repo_root() or "")
            except Exception:
                repo_root = _EVT_CWD or ""
            lazy_core.append_hook_event(
                kind, "build-queue-enforce", signature, detail,
                repo_root=repo_root,
            )
            return
        except ImportError:
            pass
        import time as _time
        os.makedirs(STATE_DIR, exist_ok=True)
        entry = {
            "ts": _time.time(), "kind": kind,
            "hook": "build-queue-enforce",
            "repo_root": _EVT_CWD or "", "signature": (signature or "")[:200],
            "detail": (detail or "")[:500],
        }
        with open(
            os.path.join(STATE_DIR, "hook-events.jsonl"), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


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
    # D2: the breadcrumb stays byte-identical; the countable history is the
    # additive hook-events line beside it (fail-open, never raises).
    _append_hook_event("error", "", str(err))


def _allow():
    sys.exit(0)


def _deny(reason, signature="build-queue-enforced"):
    # incident-auto-capture D2: countable deny event (fail-open, additive) —
    # each deny site passes its classified op as the signature.
    _append_hook_event("deny", signature, reason)
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
    global _EVT_CWD
    raw = sys.stdin.read()
    payload = json.loads(raw)
    # D2: capture the tool-call cwd for hook-event repo attribution.
    _EVT_CWD = payload.get("cwd") or ""
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

    # Allow the sanctioned wrapper before the deny surface — it carries a
    # *-filtered.ps1 path as its -Exec arg, which would otherwise trip the
    # filtered-script deny.
    if _WRAPPER_RE.search(command):
        _allow()

    # Suppress the safe dotnet/nx variants per-occurrence, then scan the scratch
    # copy for any surviving heavy build (unanchored). A leading `dotnet restore`
    # no longer masks a trailing `dotnet build`.
    scan = _suppress_safe(command)

    # Deny surface.
    if _DOTNET_BUILD_RE.search(scan):
        _deny(_redirect_reason("dotnet-build", command), "dotnet-build")

    if _DOTNET_TEST_RE.search(scan):
        _deny(_redirect_reason("dotnet-test", command), "dotnet-test")

    if _NX_BUILD_TEST_RE.search(scan):
        _nx_op = _classify_nx(command)
        _deny(_redirect_reason(_nx_op, command), _nx_op)

    if _FILTERED_SCRIPT_DIRECT_RE.search(scan) or _FILTERED_SCRIPT_POWERSHELL_RE.search(scan):
        _f_op = _classify_filtered_script(command)
        _deny(_redirect_reason(_f_op, command), _f_op)

    _allow()


try:
    main()
except SystemExit:
    raise
except Exception as exc:
    _breadcrumb(exc)
    sys.exit(0)
PYEOF

# BQE_SCRIPTS_DIR is threaded via env (D2) so the inline appender can import
# lazy_core for the keyed hook-events append.
BQE_SCRIPTS_DIR="$BQE_SCRIPTS_DIR" "$PYTHON" -c "$_BQE_PY"
exit 0
