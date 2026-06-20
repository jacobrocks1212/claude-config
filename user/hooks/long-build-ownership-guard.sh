#!/bin/bash
# long-build-ownership-guard.sh — PreToolUse(Bash) hook
# (long-build-and-runtime-ownership, Phase 3 / WU-1; M5 Prevent / LD4).
#
# THE M5-PREVENT REQUEST-TIME GUARD. A long build (`tauri build`,
# `cargo build --release`, `npm run build`) backgrounded from inside a dispatched
# cycle subagent DIES when that subagent's turn ends — its process tree is torn
# down with the turn, leaving no artifact and no error. This guard redirects
# exactly those long-build signatures to ORCHESTRATOR ownership so the build runs
# under controller supervision and survives a subagent tear by construction. It
# is the long-build analog of the existing lazy-cycle-containment deny-set, and a
# sibling of block-noncanonical-blocker-write.sh in the fail-OPEN guard family.
#
# RULE: deny a Bash command whose FIRST real token (after an optional run of
# leading `NAME=value` env assignments) is an EXACT long-build binary invocation:
#   * `tauri build`
#   * `cargo build --release`
#   * `npm run build`
# On match → DENY with a corrective reason naming the orchestrator-takeover
# signature LONG-BUILD-OWNERSHIP-TAKEOVER, so the orchestrator can deterministically
# recognize the redirect and re-launch the build itself (Bash run_in_background
# from the main session). The matcher is anchored to exact long-build binary
# invocations to keep the false-positive rate near zero — it NEVER redirects
# `ls` / `cat` / `npm run lint` / `cargo check --release` (the fast pre-build
# check the long-build rule recommends) / `npm run build:docs` / a `tauri build`
# substring buried inside another command.
#
# NOTE on "fail-open block": SPEC §M5 prose says the guard "fail-open blocks
# (exit 2)". In Claude Code a PreToolUse blocks via the JSON
# `permissionDecision: deny` — a non-zero exit is a HARD error, not a soft block.
# So the BLOCK is expressed as a `deny` JSON whose reason names the takeover
# signature; that IS the "fail-open block" in this hook framework, matching every
# sibling guard.
#
# FAIL-OPEN: any parse/match error (malformed JSON, missing python, unexpected
# payload shape) ALLOWS the command — a broken hook must never block legitimate
# work. The contract is fail-OPEN-via-empty-output (exit 0, no decision = allow).
# A best-effort breadcrumb is written to the state dir on an internal error,
# mirroring the sibling guards.
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

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin and emits an allow/deny hookSpecificOutput block (or nothing for a
# fast allow). It NEVER exits non-zero on an internal error.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON
# piped into this hook. With `-c`, the hook's real stdin (the payload) flows
# straight through to python's sys.stdin.
read -r -d '' _LBO_PY <<'PYEOF'
import datetime
import json
import os
import re
import sys

# The orchestrator-takeover signature the deny reason MUST name (SSOT; part 5
# consumes the same literal to deterministically recognize the redirect).
TAKEOVER_SIGNATURE = "LONG-BUILD-OWNERSHIP-TAKEOVER"

# Breadcrumb base dir (best-effort diagnostic only; un-keyed base / override).
STATE_DIR = os.environ.get("LAZY_STATE_DIR") or os.path.join(
    os.path.expanduser("~"), ".claude", "state"
)

# Anchored matcher: an optional run of leading `NAME=value` env assignments
# (prefix tolerance), then EXACTLY one of the long-build binary invocations.
# Anchored at ^ so a long-build token buried inside another command (e.g.
# `echo tauri build`) does NOT match. `npm run build` is matched as a whole
# token followed by end-of-string or whitespace, so `npm run build:docs` and
# `npm run build-foo` do NOT match. `cargo build` REQUIRES `--release` (a plain
# `cargo build` debug build is fast and not redirected; `cargo check --release`
# is a different binary verb and never matches).
_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
_LONG_BUILD_RE = re.compile(
    r"^\s*" + _ENV_PREFIX + r"(?:"
    r"tauri\s+build(?:\s|$)"
    r"|cargo\s+build\s+--release(?:\s|$)"
    r"|npm\s+run\s+build(?:\s|$)"
    r")"
)


def _breadcrumb(err):
    """Write a fail-open breadcrumb; never raise."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(
            os.path.join(STATE_DIR, "hook-error.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(
                {
                    "hook": "long-build-ownership-guard",
                    "error": str(err),
                    "at": datetime.datetime.now(tz=datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
                fh,
            )
    except Exception:
        pass


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
    if payload.get("tool_name", "") != "Bash":
        _allow()
    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        _allow()
    if _LONG_BUILD_RE.match(command):
        _deny(
            "LONG BUILD REDIRECTED TO ORCHESTRATOR "
            f"[{TAKEOVER_SIGNATURE}]: a long build "
            "(`tauri build` / `cargo build --release` / `npm run build`) "
            "backgrounded from inside a cycle subagent DIES when the subagent's "
            "turn ends — its process tree is torn down with the turn, leaving no "
            "artifact and no error. This build is ORCHESTRATOR-OWNED: the main "
            "(non-subagent) session must re-launch it via `Bash run_in_background: "
            "true` and drive it through harness task-tracking so it survives "
            "subagent turn boundaries. Run `cargo check --release` first to surface "
            "compile errors fast before committing to the long build."
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
# variable is populated. Run python with the captured body via -c so the hook's
# real stdin (the PreToolUse payload) reaches python untouched.
"$PYTHON" -c "$_LBO_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
