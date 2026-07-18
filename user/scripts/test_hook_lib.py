#!/usr/bin/env python3
"""Unit suite for hook_lib.py (shared-hook-lib feature, Phase 2).

hook_lib.py is the imported python substrate the python-bearing hooks migrate
onto in Phase 3: allow()/deny() emitters, append_hook_event(...) (lazily
delegating to lazy_core), breadcrumb(), and the ENV_PREFIX / CMD_START anchor
constants.

Run directly: ``python user/scripts/test_hook_lib.py`` (exit 0 iff all pass).
Also pytest-collectable (plain ``test_*`` functions asserting).

Key contract asserted here (D4, import-light): a fresh ``import hook_lib`` must
NOT pull ``lazy_core`` — the import is stdlib-only at module top; ``lazy_core``
is imported lazily INSIDE ``append_hook_event``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_HOOK_LIB = _SCRIPTS_DIR / "hook_lib.py"

sys.path.insert(0, str(_SCRIPTS_DIR))

_IMPORT_ERROR: Exception | None = None
hook_lib = None
try:
    import hook_lib  # type: ignore[import]
except Exception as exc:  # noqa: BLE001 — surfaced as a failing test, not a crash
    _IMPORT_ERROR = exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_snippet(snippet: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a python snippet in a FRESH subprocess with _SCRIPTS_DIR on sys.path.

    Used to exercise allow()/deny() (which sys.exit) and the import-light guard
    the way the hooks themselves invoke the interpreter (python -c)."""
    full = (
        "import sys\n"
        f"sys.path.insert(0, {str(_SCRIPTS_DIR)!r})\n"
        + snippet
    )
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", full],
        capture_output=True, text=True, env=run_env,
    )


def _read_events(state_dir: Path) -> list[dict]:
    p = state_dir / "hook-events.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# (d) — module constants present
# ---------------------------------------------------------------------------

def test_env_prefix_and_cmd_start_constants_present():
    """ENV_PREFIX / CMD_START are module-level string constants (the single
    source for the anchor pair the Phase-3 hooks collapse onto)."""
    assert isinstance(hook_lib.ENV_PREFIX, str) and hook_lib.ENV_PREFIX, hook_lib.ENV_PREFIX
    assert isinstance(hook_lib.CMD_START, str) and hook_lib.CMD_START, hook_lib.CMD_START
    # CMD_START is the segment-start boundary built on top of ENV_PREFIX.
    assert hook_lib.ENV_PREFIX in hook_lib.CMD_START, (
        "CMD_START must be composed on top of ENV_PREFIX"
    )
    # Sanity: the anchors compile and match a real bash env-prefixed segment.
    import re
    assert re.search(hook_lib.CMD_START + r"cargo", "FOO=bar cargo build")
    # PATH_PREFIX helper: a path-qualified binary token still anchors.
    assert isinstance(hook_lib.PATH_PREFIX, str) and hook_lib.PATH_PREFIX, hook_lib.PATH_PREFIX
    assert re.search(
        hook_lib.CMD_START + hook_lib.PATH_PREFIX + r"cargo\s+build",
        "/abs/path/cargo build --release",
    )


# ---------------------------------------------------------------------------
# (a) — allow() / deny(reason) emit the exact JSON shape the hooks produce
# ---------------------------------------------------------------------------

def test_allow_emits_nothing_and_exits_zero():
    r = _run_snippet("import hook_lib; hook_lib.allow()")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", f"allow() must emit nothing; got {r.stdout!r}"


def test_deny_emits_exact_permission_decision_shape_and_exits_zero():
    r = _run_snippet("import hook_lib; hook_lib.deny('blocked because X')")
    assert r.returncode == 0, r.stderr
    expected = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "blocked because X",
        }
    }
    # Parsed-shape equality AND byte-shape (dict insertion order preserved by
    # json.dumps) so Phase-3 migrations produce byte-identical deny output.
    assert json.loads(r.stdout) == expected, r.stdout
    assert r.stdout.strip() == json.dumps(expected), (
        f"deny() byte-shape drift: {r.stdout!r}"
    )


# ---------------------------------------------------------------------------
# (b) — append_hook_event writes the JSONL entry / returns False (never raises)
# ---------------------------------------------------------------------------

def test_append_hook_event_writes_jsonl_line_and_returns_true():
    # Snapshot/restore lazy_core's module-level active-repo binding: passing a
    # repo_root exercises the set_active_repo_root branch, which would otherwise
    # leak into other tests sharing this process (a global mutation).
    import lazy_core  # noqa: PLC0415 — test-only, after the import-light guard
    _prior_root = lazy_core.active_repo_root()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        os.environ["LAZY_STATE_DIR"] = str(state_dir)
        try:
            ok = hook_lib.append_hook_event(
                "deny", "test-hook", "sig-token", "a detail", repo_root=str(state_dir)
            )
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)
            lazy_core.set_active_repo_root(_prior_root)
        assert ok is True, "a successful append must return True"
        events = _read_events(state_dir)
        assert len(events) == 1, events
        e = events[0]
        assert e["kind"] == "deny" and e["hook"] == "test-hook", e
        assert e["signature"] == "sig-token" and e["detail"] == "a detail", e
        assert isinstance(e["ts"], (int, float)) and not isinstance(e["ts"], bool), e


def test_append_hook_event_returns_false_on_write_error_never_raises():
    # Point LAZY_STATE_DIR at a regular FILE so both the lazy_core delegation
    # and the inline fallback fail to open <dir>/hook-events.jsonl.
    with tempfile.TemporaryDirectory() as td:
        blocker = Path(td) / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        os.environ["LAZY_STATE_DIR"] = str(blocker)
        try:
            result = hook_lib.append_hook_event("error", "test-hook", "", "boom")
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)
        assert result is False, "a write error must return False (fail-open), not raise"


# ---------------------------------------------------------------------------
# (c) — breadcrumb() writes hook-error.json and chains an error event
# ---------------------------------------------------------------------------

def test_breadcrumb_writes_hook_error_json_and_chains_event():
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        os.environ["LAZY_STATE_DIR"] = str(state_dir)
        try:
            hook_lib.breadcrumb("test-hook", "kaboom")
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)
        crumb_path = state_dir / "hook-error.json"
        assert crumb_path.exists(), "breadcrumb must write hook-error.json"
        crumb = json.loads(crumb_path.read_text(encoding="utf-8"))
        assert crumb["hook"] == "test-hook", crumb
        assert crumb["error"] == "kaboom", crumb
        assert "at" in crumb, crumb
        # ...and it chains into an append_hook_event("error", ...) line.
        events = _read_events(state_dir)
        assert len(events) == 1 and events[0]["kind"] == "error", events
        assert events[0]["hook"] == "test-hook", events


# ---------------------------------------------------------------------------
# (e) — import-light guard (D4): import hook_lib must NOT pull lazy_core
# ---------------------------------------------------------------------------

def test_import_hook_lib_does_not_import_lazy_core():
    r = _run_snippet(
        "import hook_lib\n"
        "assert 'lazy_core' not in sys.modules, "
        "'importing hook_lib must not pull lazy_core (import-light, D4)'\n"
        "print('IMPORT_LIGHT_OK')\n"
    )
    assert r.returncode == 0, f"import-light guard failed: {r.stderr}"
    assert "IMPORT_LIGHT_OK" in r.stdout, r.stdout


# ---------------------------------------------------------------------------
# Standalone runner (mirrors test_hooks.py's simple harness)
# ---------------------------------------------------------------------------

_TESTS = [
    ("test_env_prefix_and_cmd_start_constants_present",
     test_env_prefix_and_cmd_start_constants_present),
    ("test_allow_emits_nothing_and_exits_zero",
     test_allow_emits_nothing_and_exits_zero),
    ("test_deny_emits_exact_permission_decision_shape_and_exits_zero",
     test_deny_emits_exact_permission_decision_shape_and_exits_zero),
    ("test_append_hook_event_writes_jsonl_line_and_returns_true",
     test_append_hook_event_writes_jsonl_line_and_returns_true),
    ("test_append_hook_event_returns_false_on_write_error_never_raises",
     test_append_hook_event_returns_false_on_write_error_never_raises),
    ("test_breadcrumb_writes_hook_error_json_and_chains_event",
     test_breadcrumb_writes_hook_error_json_and_chains_event),
    ("test_import_hook_lib_does_not_import_lazy_core",
     test_import_hook_lib_does_not_import_lazy_core),
]


def main() -> int:
    print("=" * 60)
    print("test_hook_lib.py — shared-hook-lib Phase 2 unit suite")
    print("=" * 60)
    if _IMPORT_ERROR is not None:
        print(f"\nREQUIRED MODULE MISSING: hook_lib not importable: {_IMPORT_ERROR}\n")
        return 1
    passed, failed = 0, 0
    for name, fn in _TESTS:
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name} -> {type(exc).__name__}: {exc}")
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(_TESTS)} passed, {failed} failed")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
