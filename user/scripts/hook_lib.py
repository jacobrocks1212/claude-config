"""hook_lib.py — shared python substrate for the python-bearing hooks in
``user/hooks/`` (shared-hook-lib feature, Phase 2).

IMPORTED (never executed) by the hooks' inline Python bodies, with ``sys.path``
seeded from the threaded scripts dir (``HOOK_SCRIPTS_DIR`` — the bash prelude's
derivation) exactly as the five ``_append_hook_event`` copies already do for
``lazy_core``. Provides the scaffolding those copies duplicate today, collapsed
to one home:

  - ``allow()`` / ``deny(reason)``      the allow/deny PreToolUse JSON emitters
  - ``append_hook_event(...)``          the countable hook-events.jsonl appender
                                        (LAZILY delegates to
                                        ``lazy_core.append_hook_event`` when
                                        importable; inline base-dir fallback
                                        otherwise — the current per-hook fallback
                                        branch, once)
  - ``breadcrumb(hook, err)``           the fail-open hook-error.json writer,
                                        chaining into ``append_hook_event``
  - ``ENV_PREFIX`` / ``CMD_START``      the shared command-segment anchor
                                        regexes (single source for the pair that
                                        is triplicated across the enforcement
                                        hooks today)

IMPORT-LIGHT (SPEC D4) — HARD: only stdlib is imported at module top; the
``lazy_core`` import is deferred INSIDE ``append_hook_event``. Importing this
module must NOT pull ``lazy_core`` (it imports all of ``lazy_core`` per
invocation, ~95 ms warm) and must NOT read stdin (stdin carries the PreToolUse
payload for the ``-c`` body). ``test_hook_lib.py`` asserts the import-light
guard.

Every function here is best-effort / FAIL-OPEN — the house constitution's
sacred invariant: a breadcrumb/append failure can NEVER change a hook's
deny/allow output, and no error path raises.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time

# --- Shared command-segment anchor regexes ---------------------------------
# The single source for the ``_ENV_PREFIX`` / ``_CMD_START`` pair currently
# hand-copied into lazy-cycle-containment.sh / long-build-ownership-guard.sh /
# build-queue-enforce.sh. Kept byte-identical to those copies so the Phase-3
# migration is a pure de-duplication (no matcher-semantics change).
#
# PowerShell-syntax regex audit (powershell-tool-bypasses-bash-matched-guards):
# env-assignment prefixes differ between shells (`NAME=value` in bash vs
# `$env:NAME='value';` in PowerShell) — ENV_PREFIX recognizes both forms.
ENV_PREFIX = (
    r"(?:"
    r"[A-Za-z_][A-Za-z0-9_]*=\S+\s+"
    r"|\$env:[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:'[^']*'|\"[^\"]*\"|\S+)\s*;\s*"
    r")*"
)
# A command-start boundary: string start, or a shell separator, then optional
# whitespace and optional env-assignment prefix.
CMD_START = r"(?:^|[\n;&|({])\s*" + ENV_PREFIX

# An optional path prefix so a path-qualified binary token
# (`/abs/path/cargo build --release`) still matches — the idiom
# long-build-ownership-guard.sh / build-queue-enforce.sh use for their
# `_FILTERED_SCRIPT_DIRECT_RE` / `_PATH_PREFIX` (a run of non-separator chars
# ending in a path separator, optionally preceded by a `./`/`.\` relative
# marker). Kept byte-identical to those copies so the Phase-3 collapse is a
# pure de-duplication.
PATH_PREFIX = r"(?:\.?[\\/])?(?:[^\s;&|]*[\\/])?"

_SIGNATURE_HEAD_CHARS = 200
_DETAIL_HEAD_CHARS = 500


def _base_state_dir() -> str:
    """Best-effort base state dir for the inline fallbacks: the LAZY_STATE_DIR
    override when set (hermetic tests / hook pipe-tests), else ~/.claude/state.

    This is the UN-KEYED base dir — the keyed per-repo attribution lives inside
    ``lazy_core.append_hook_event`` and is only reached on the delegation path.
    Matches the residency of the per-hook ``_breadcrumb`` writers today."""
    override = os.environ.get("LAZY_STATE_DIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "state")


def allow() -> None:
    """Fast allow: emit nothing (a PreToolUse hook with no decision = allow)."""
    sys.exit(0)


def deny(reason: str) -> None:
    """Emit the deny hookSpecificOutput JSON and exit 0.

    Deny is expressed in JSON, NEVER via a non-zero exit — a PreToolUse
    non-zero exit is a HARD harness error, not a soft block."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def append_hook_event(
    kind: str,
    hook: str,
    signature: str,
    detail: str,
    repo_root: str | None = None,
) -> bool:
    """Append one countable ``hook-events.jsonl`` event (incident-auto-capture
    D2). Best-effort / FAIL-OPEN — never raises, returns False on any write
    failure, never changes the caller's deny/allow output.

    Prefers the shared ``lazy_core.append_hook_event`` (keyed state dir when the
    repo is resolvable; exact LAZY_STATE_DIR dir under the override). Falls back
    to an inline base-dir append ONLY when ``lazy_core`` is unavailable — the
    collapsed once-home of the per-hook inline fallback branch.

    The signature is deliberately a pass-through of ``lazy_core.append_hook_event``
    (kind, hook, signature, detail, repo_root) so the delegation adds no
    translation layer."""
    try:
        lazy_core = None
        try:
            # Lazy (import-light D4): only reached at a real event site, never
            # at module import. hook_lib sits beside lazy_core in the scripts
            # dir, so ensure that dir is importable before delegating.
            _here = os.path.dirname(os.path.abspath(__file__))
            if _here not in sys.path:
                sys.path.insert(0, _here)
            import lazy_core as _lc  # noqa: PLC0415 — deliberate lazy import
            lazy_core = _lc
        except Exception:  # noqa: BLE001 — any import failure ⇒ inline fallback
            lazy_core = None

        if lazy_core is not None:
            # Bind the active repo so the keyed state dir attributes the event
            # (a no-op under the LAZY_STATE_DIR override). Best-effort.
            resolved_root = repo_root or ""
            if repo_root:
                try:
                    lazy_core.set_active_repo_root(repo_root or None)
                    resolved_root = str(lazy_core.active_repo_root() or "")
                except Exception:  # noqa: BLE001
                    resolved_root = repo_root or ""
            return bool(lazy_core.append_hook_event(
                kind, hook, signature, detail, repo_root=resolved_root,
            ))

        # Inline fallback: lazy_core unavailable → base-dir append.
        base = _base_state_dir()
        os.makedirs(base, exist_ok=True)
        entry = {
            "ts": time.time(),
            "kind": kind,
            "hook": hook,
            "repo_root": repo_root or "",
            "signature": (signature or "")[:_SIGNATURE_HEAD_CHARS],
            "detail": (detail or "")[:_DETAIL_HEAD_CHARS],
        }
        with open(
            os.path.join(base, "hook-events.jsonl"), "a", encoding="utf-8"
        ) as fh:
            fh.write(json.dumps(entry) + "\n")
        return True
    except Exception:  # noqa: BLE001
        # Fail-open: an events write must never propagate.
        return False


def breadcrumb(hook: str, err: object) -> None:
    """Write a fail-open ``hook-error.json`` breadcrumb (the at-a-glance "is a
    hook broken" file, overwritten each time) and chain into an
    ``append_hook_event("error", ...)`` line (the countable history). Never
    raises — mirrors the per-hook ``_breadcrumb`` byte-shape."""
    try:
        base = _base_state_dir()
        os.makedirs(base, exist_ok=True)
        with open(
            os.path.join(base, "hook-error.json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(
                {
                    "hook": hook,
                    "error": str(err),
                    "at": datetime.datetime.now(tz=datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                },
                fh,
            )
    except Exception:  # noqa: BLE001
        pass
    # The breadcrumb stays byte-identical; the countable history is the additive
    # hook-events line beside it (fail-open, never raises).
    append_hook_event("error", hook, "", str(err))
