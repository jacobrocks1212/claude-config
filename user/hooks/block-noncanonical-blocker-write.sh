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
# shared-hook-lib (Phase 3): python resolution, the scripts-dir derivation, and
# the no-python breadcrumb are provided by the SOURCED hook-prelude.sh
# (HOOK_PYTHON / HOOK_SCRIPTS_DIR / HOOK_NAME); the allow/deny emitters, the
# countable hook-events append, and the fail-open breadcrumb are provided by
# hook_lib (imported from HOOK_SCRIPTS_DIR by the inline body below). The
# per-hook inline copies of all four are GONE — they live once in hook_lib now.

# Source the shared hook prelude, fail-open-guarded (shared-hook-lib SPEC D2).
# A missing/broken prelude ALLOWS (exit 0), never wedges. Derive this hook's own
# directory here ONLY to locate the prelude; the prelude then provides
# HOOK_PYTHON (python3→python resolution; total absence ⇒ pure-bash breadcrumb
# + exit 0 — guard-fail-open-leaves-no-trace §1) and HOOK_SCRIPTS_DIR (the
# sibling user/scripts/ dir, the hook_lib import seed). Builtins only for the
# bootstrap ($0 may carry Windows backslashes; `dirname` is not guaranteed on a
# non-login git-bash PATH).
SELF="${0//\\//}"
case "$SELF" in
  */*) _HOOK_DIR="$(cd "${SELF%/*}" && pwd)" ;;
  *)   _HOOK_DIR="$(pwd)" ;;
esac
. "$_HOOK_DIR/hook-prelude.sh" 2>/dev/null || exit 0

# shared-hook-lib (SPEC D2): if hook_lib is unavailable in the scripts dir, leave
# a prelude-side trace (hook_emit_error_event — the shared pure-bash breadcrumb)
# and fail OPEN. Restores the "trace even when the shared module is unavailable"
# property the pre-migration inline lazy_core fallback carried; the inline body's
# `except ImportError: sys.exit(0)` is the silent last-resort for a
# present-but-unimportable hook_lib.
if [ ! -f "$HOOK_SCRIPTS_DIR/hook_lib.py" ]; then
  hook_emit_error_event "$HOOK_NAME" "" "hook_lib.py not found in scripts dir"
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
read -r -d '' _BNB_PY <<'PYEOF'
import json
import os
import re
import sys

# shared-hook-lib (SPEC D2): seed sys.path from HOOK_SCRIPTS_DIR (threaded via
# env) and import hook_lib for the allow/deny emitters, the countable
# hook-events append, and the fail-open breadcrumb. A missing/failed import must
# ALLOW, never wedge — the ONLY retained inline fallback is this minimal
# `except ImportError: sys.exit(0)`. The prelude already left a no-python trace;
# a hook_lib-import failure with python present leaves the prelude's source-side
# guard intact and simply allows.
try:
    _sd = os.environ.get("HOOK_SCRIPTS_DIR")
    if _sd and _sd not in sys.path:
        sys.path.insert(0, _sd)
    import hook_lib
except ImportError:
    sys.exit(0)

_HOOK = "block-noncanonical-blocker-write"


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
        hook_lib.allow()
    tool_input = payload.get("tool_input") or {}
    # Both Write and Edit carry the target as `file_path`.
    file_path = tool_input.get("file_path") or ""
    if not isinstance(file_path, str) or not file_path:
        hook_lib.allow()
    # Match against the BASENAME only (a path's final component). Normalize
    # backslashes first so a Windows path resolves correctly.
    norm_path = file_path.replace("\\", "/")
    basename = os.path.basename(norm_path)
    if _is_noncanonical_blocker(basename) and _is_in_sentinel_scope(norm_path):
        # incident-auto-capture D2: countable deny event (fail-open, additive).
        hook_lib.append_hook_event(
            "deny", _HOOK, "noncanonical-blocker", basename,
            repo_root=payload.get("cwd") or "",
        )
        hook_lib.deny(
            f"MIS-NAMED BLOCKER WRITE DENIED: '{basename}' is blocker-shaped but "
            "non-canonical. The lazy/bug state machines only see the EXACT "
            "filename 'BLOCKED.md' as a blocker — a mis-named blocker is invisible "
            "and silently loops the pipeline. Write the canonical 'BLOCKED.md' "
            "(in the item's docs/features/<slug>/ or docs/bugs/<slug>/ directory) "
            "instead."
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
# variable is populated. Run python with the captured body via -c so the hook's
# real stdin (the PreToolUse payload) reaches python untouched. HOOK_SCRIPTS_DIR
# is threaded via env so the inline body can import hook_lib.
HOOK_SCRIPTS_DIR="$HOOK_SCRIPTS_DIR" "$HOOK_PYTHON" -c "$_BNB_PY"

# Always exit 0 from the shell side: a non-zero PreToolUse exit is a hard
# blocking error in Claude Code; deny is expressed in JSON, never an exit code.
exit 0
