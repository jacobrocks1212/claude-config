#!/bin/bash
# block-noncanonical-blocker-write.sh — PreToolUse(Write/Edit) hook
# (noncanonical-blocker-filename-invisible-to-state-machine, Phase 4).
#
# DEFENSE-IN-DEPTH WRITE-TIME LAYER. The read-time detector
# (lazy_core.detect_noncanonical_blocker, wired into lazy-state.py /
# bug-state.py Step 3) is the load-bearing backstop; this hook stops the stray
# from ever reaching disk so the loop risk never materializes in the first
# place. The two layers are complementary — keep BOTH.
#
# RULE: deny a Write/Edit whose resolved target BASENAME is blocker-shaped but
# NON-canonical:
#   * basename matches BLOCKED* (case-insensitive) AND ends in .md (case-insens.)
#   * AND is NOT exactly the canonical "BLOCKED.md"
#   * AND does NOT contain the literal substring "_RESOLVED_" (a neutralized
#     blocker, e.g. BLOCKED_RESOLVED_2026-06-09.md, is legitimate)
# On match → DENY with a message instructing the agent to write the canonical
# "BLOCKED.md" name instead (a deny WITHOUT the corrective name just loops the
# agent's retry).
#
# This match rule is identical in spirit to the Phase-1 lazy_core helper.
#
# FAIL-OPEN: any parse/match error (malformed JSON, missing python, unexpected
# payload shape) ALLOWS the write — a broken hook must never block legitimate
# work. A PreToolUse non-zero exit is a hard blocking error in Claude Code, so
# the contract is fail-OPEN-via-empty-output (exit 0, no decision = allow).
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
  printf '{"hook":"block-noncanonical-blocker-write","error":"no python interpreter on PATH","at":"%s"}' \
    "$_HOOK_NOPY_TS" > "$_HOOK_NOPY_BASE/hook-error.json" 2>/dev/null || true
  printf '{"ts":%s,"kind":"error","hook":"block-noncanonical-blocker-write","repo_root":"","signature":"","detail":"no python interpreter on PATH"}\n' \
    "$_HOOK_NOPY_TS" >> "$_HOOK_NOPY_BASE/hook-events.jsonl" 2>/dev/null || true
  exit 0
fi

# incident-auto-capture Phase 1 (D2): resolve the scripts dir relative to this
# hook so the inline Python can import lazy_core for the keyed hook-events
# append (best-effort — the appender falls back to the base dir when the import
# is unavailable). Builtins only; $0 may carry Windows backslashes.
SELF="${0//\\//}"
case "$SELF" in
  */*) BNB_SCRIPT_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   BNB_SCRIPT_DIR="$(pwd)" ;;
esac
BNB_SCRIPTS_DIR="$BNB_SCRIPT_DIR/../scripts"

# All deny/allow logic lives in this inline Python. It reads the PreToolUse JSON
# from stdin and emits an allow/deny hookSpecificOutput block (or nothing for a
# fast allow). It NEVER exits non-zero on an internal error.
#
# The Python body is passed via `-c` (NOT a heredoc): a heredoc would BIND the
# python process's stdin to the script body, swallowing the PreToolUse JSON
# piped into this hook. With `-c`, the hook's real stdin (the payload) flows
# straight through to python's sys.stdin.
read -r -d '' _BNB_PY <<'PYEOF'
import datetime
import json
import os
import re
import sys

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


def _append_hook_event(kind, signature, detail, cwd=""):
    """incident-auto-capture Phase 1 (D2): append one countable hook-event line
    (hook-events.jsonl). Best-effort / FAIL-OPEN — never raises, never changes
    the deny/allow output. Prefers the shared lazy_core appender (keyed state
    dir when the repo is resolvable; exact LAZY_STATE_DIR dir in tests); falls
    back to an inline append at the base dir when lazy_core is unavailable."""
    try:
        try:
            _sd = os.environ.get("BNB_SCRIPTS_DIR")
            if _sd and _sd not in sys.path:
                sys.path.insert(0, _sd)
            import lazy_core
            try:
                lazy_core.set_active_repo_root(cwd or None)
                repo_root = str(lazy_core.active_repo_root() or "")
            except Exception:
                repo_root = cwd or ""
            lazy_core.append_hook_event(
                kind, "block-noncanonical-blocker-write", signature, detail,
                repo_root=repo_root,
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
            "hook": "block-noncanonical-blocker-write",
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
                    "hook": "block-noncanonical-blocker-write",
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


def _is_noncanonical_blocker(basename):
    """Mirror of lazy_core.detect_noncanonical_blocker's per-name match rule."""
    return (
        basename.upper().startswith("BLOCKED")
        and basename.lower().endswith(".md")
        and basename != "BLOCKED.md"
        and "_RESOLVED_" not in basename
    )


# adhoc-blocker-write-hook-overbroad-scope: pipeline sentinels live ONLY under
# docs/features/<slug>/ and docs/bugs/<slug>/ (incl. docs/bugs/_archive/<slug>/,
# a harmless over-match) — this hook previously matched a BLOCKED*-shaped
# basename ANYWHERE in the tree with no directory scoping, denying legitimate
# writes with no connection to the pipeline (observed: the skill component
# user/skills/_components/blocked-resolution.md). Matched against the full
# (backslash-normalized) file_path, not just the basename.
_SENTINEL_SCOPE_RE = re.compile(r"(?:^|/)docs/(?:features|bugs)/")


def _is_in_sentinel_scope(norm_path):
    return bool(_SENTINEL_SCOPE_RE.search(norm_path))


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
    # Match against the BASENAME only (a path's final component). Normalize
    # backslashes first so a Windows path resolves correctly.
    norm_path = file_path.replace("\\", "/")
    basename = os.path.basename(norm_path)
    if _is_noncanonical_blocker(basename) and _is_in_sentinel_scope(norm_path):
        # incident-auto-capture D2: countable deny event (fail-open, additive).
        _append_hook_event(
            "deny", "noncanonical-blocker", basename,
            payload.get("cwd") or "",
        )
        _deny(
            f"MIS-NAMED BLOCKER WRITE DENIED: '{basename}' is blocker-shaped but "
            "non-canonical. The lazy/bug state machines only see the EXACT "
            "filename 'BLOCKED.md' as a blocker — a mis-named blocker is invisible "
            "and silently loops the pipeline. Write the canonical 'BLOCKED.md' "
            "(in the item's docs/features/<slug>/ or docs/bugs/<slug>/ directory) "
            "instead."
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
# real stdin (the PreToolUse payload) reaches python untouched. BNB_SCRIPTS_DIR
# is threaded via env (D2) so the inline appender can import lazy_core.
BNB_SCRIPTS_DIR="$BNB_SCRIPTS_DIR" "$PYTHON" -c "$_BNB_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
