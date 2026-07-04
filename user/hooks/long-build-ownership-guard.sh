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
# RULE: deny a Bash command that contains an EXACT long-build binary invocation
# ANYWHERE in it (not only at the start), so a build chained behind a leading
# command — `cd "..." && cargo build --release`, a pipeline, a `;`-chain — is
# still caught:
#   * `tauri build`
#   * `cargo build --release`
#   * `npm run build`
# On match → DENY with a corrective reason naming the orchestrator-takeover
# signature LONG-BUILD-OWNERSHIP-TAKEOVER, so the orchestrator can deterministically
# recognize the redirect and re-launch the build itself (Bash run_in_background
# from the main session). The matcher is scoped to exact long-build binary
# invocations to keep the false-positive rate near zero — it NEVER redirects
# `ls` / `cat` / `npm run lint` / `cargo check --release` (the fast pre-build
# check the long-build rule recommends) / `npm run build:docs`. It is preceded by
# a word boundary so a long-build token glued onto a longer word does not match,
# but it WILL match a real invocation that follows a `cd ... &&`.
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

# incident-auto-capture Phase 1 (D2): resolve the scripts dir relative to this
# hook so the inline Python can import lazy_core for the keyed hook-events
# append (best-effort — the appender falls back to the base dir when the import
# is unavailable). Builtins only; $0 may carry Windows backslashes.
SELF="${0//\\//}"
case "$SELF" in
  */*) LBO_SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   LBO_SCRIPT_DIR="$(pwd)" ;;
esac
LBO_SCRIPTS_DIR="$LBO_SCRIPT_DIR/../scripts"

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

# Command-position matcher: a long-build invocation that sits at a COMMAND
# position — the start of the string (after optional leading `NAME=value` env
# assignments) OR immediately after a shell command separator (`&&`, `||`, `|`,
# `;`, `(`, `{`, newline, with optional surrounding env assignments). This catches
# a build chained behind a leading command (`cd "..." && cargo build --release`,
# pipelines, `;`-chains) while still NOT matching a long-build token buried inside
# an argument string (e.g. `echo tauri build` — `build` there follows `echo`, not
# a command separator). `npm run build` is matched as a whole token followed by
# end-of-string or whitespace, so `npm run build:docs` / `npm run build-foo` do
# NOT match. `cargo build` REQUIRES `--release` (a plain `cargo build` debug build
# is fast and not redirected; `cargo check --release` is a different verb).
_ENV_PREFIX = r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
# A command-start boundary: string start, or a shell separator, then optional
# whitespace and optional env-assignment prefix.
_CMD_START = r"(?:^|[\n;&|({])\s*" + _ENV_PREFIX
_LONG_BUILD_RE = re.compile(
    _CMD_START + r"(?:"
    r"tauri\s+build(?:\s|$)"
    r"|cargo\s+build\s+--release(?:\s|$)"
    r"|npm\s+run\s+build(?:\s|$)"
    r")"
)


def _append_hook_event(kind, signature, detail, cwd=""):
    """incident-auto-capture Phase 1 (D2): append one countable hook-event line
    (hook-events.jsonl). Best-effort / FAIL-OPEN — never raises, never changes
    the deny/allow output. Prefers the shared lazy_core appender (keyed state
    dir when the repo is resolvable; exact LAZY_STATE_DIR dir in tests); falls
    back to an inline append at the base dir when lazy_core is unavailable."""
    try:
        try:
            _sd = os.environ.get("LBO_SCRIPTS_DIR")
            if _sd and _sd not in sys.path:
                sys.path.insert(0, _sd)
            import lazy_core
            try:
                lazy_core.set_active_repo_root(cwd or None)
                repo_root = str(lazy_core.active_repo_root() or "")
            except Exception:
                repo_root = cwd or ""
            lazy_core.append_hook_event(
                kind, "long-build-ownership-guard", signature, detail,
                repo_root=repo_root,
            )
            return
        except ImportError:
            pass
        import time as _time
        os.makedirs(STATE_DIR, exist_ok=True)
        entry = {
            "ts": _time.time(), "kind": kind,
            "hook": "long-build-ownership-guard",
            "repo_root": cwd or "", "signature": (signature or "")[:200],
            "detail": (detail or "")[:500],
        }
        with open(
            os.path.join(STATE_DIR, "hook-events.jsonl"), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:
        pass


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
    # D2: the breadcrumb stays byte-identical; the countable history is the
    # additive hook-events line beside it (fail-open, never raises).
    _append_hook_event("error", "", str(err))


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
    if _LONG_BUILD_RE.search(command):
        # incident-auto-capture D2: countable deny event (fail-open, additive).
        _append_hook_event(
            "deny", TAKEOVER_SIGNATURE, command, payload.get("cwd") or ""
        )
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
# real stdin (the PreToolUse payload) reaches python untouched. LBO_SCRIPTS_DIR
# is threaded via env (D2) so the inline appender can import lazy_core.
LBO_SCRIPTS_DIR="$LBO_SCRIPTS_DIR" "$PYTHON" -c "$_LBO_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
