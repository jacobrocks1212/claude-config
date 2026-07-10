#!/usr/bin/env python3
"""
test_hooks.py — Failing pipe-tests for Phase 2 hook mechanics.

Tests lazy-dispatch-guard.sh, lazy-route-inject.sh, and lazy_guard.py —
none of which exist yet (RED state).  Every test is expected to fail for
a specific reason: missing files, missing behaviour, or correct denials.

Contract under test (to be implemented by the next agent):
  - user/scripts/lazy_guard.py
  - user/hooks/lazy-dispatch-guard.sh
  - user/hooks/lazy-route-inject.sh

Run with:  python user/scripts/test_hooks.py
Exit 0 only when ALL tests pass.  Legitimate exception: test_pipe_tests_wsl
may print SKIP and still count as passing when WSL is unavailable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT   = _SCRIPTS_DIR.parent.parent          # claude-config root
_HOOKS_DIR   = _REPO_ROOT / "user" / "hooks"
_GUARD_SH    = _HOOKS_DIR / "lazy-dispatch-guard.sh"
_INJECT_SH   = _HOOKS_DIR / "lazy-route-inject.sh"
_GUARD_PY    = _SCRIPTS_DIR / "lazy_guard.py"

# ---------------------------------------------------------------------------
# Bash resolver — finds a POSIX-capable bash.exe on Windows (Git Bash),
# or the system bash on any other platform.  Never returns System32\bash.exe
# (the WSL launcher) because that cannot execute Windows-path scripts.
# ---------------------------------------------------------------------------

def _find_bash() -> str:
    """Return the absolute path to a usable bash executable.

    On Windows (os.name == "nt"):
      Probes in order:
        1. %ProgramFiles%\\Git\\usr\\bin\\bash.exe  (Git Bash canonical location)
        2. %ProgramFiles%\\Git\\bin\\bash.exe
        3. %ProgramFiles(x86)%\\Git\\usr\\bin\\bash.exe  (32-bit Git install)
        4. %ProgramFiles(x86)%\\Git\\bin\\bash.exe
        5. Derive from shutil.which("git"):
             git.exe lives at <git-root>\\cmd\\git.exe or <git-root>\\bin\\git.exe;
             bash.exe is at <git-root>\\usr\\bin\\bash.exe.
      Any path that contains "System32" (case-insensitive) is skipped — that is
      the WSL launcher and cannot execute Windows-path scripts.

    Elsewhere:
      Returns shutil.which("bash").

    Raises RuntimeError if no usable bash is found, naming every path probed.
    """
    if os.name != "nt":
        bash = shutil.which("bash")
        if bash:
            return bash
        raise RuntimeError("bash not found on PATH")

    probed: list[str] = []

    def _try(path: str) -> str | None:
        """Return *path* if it exists and is not the WSL System32 launcher."""
        probed.append(path)
        if "system32" in path.lower():
            return None  # explicitly skip WSL launcher
        if os.path.isfile(path):
            return path
        return None

    # 1-4: Fixed candidate locations under %ProgramFiles% and %ProgramFiles(x86)%
    for pf_var in ("ProgramFiles", "ProgramFiles(x86)"):
        pf = os.environ.get(pf_var, "")
        if not pf:
            continue
        for rel in (r"Git\usr\bin\bash.exe", r"Git\bin\bash.exe"):
            result = _try(os.path.join(pf, rel))
            if result:
                return result

    # 5: Derive from git on PATH
    git_exe = shutil.which("git")
    if git_exe:
        # git.exe is typically at <git-root>\cmd\git.exe or <git-root>\bin\git.exe
        git_path = os.path.realpath(git_exe)
        git_parent = os.path.dirname(git_path)   # e.g. <git-root>\cmd
        git_root   = os.path.dirname(git_parent)  # e.g. <git-root>
        candidate  = os.path.join(git_root, "usr", "bin", "bash.exe")
        result = _try(candidate)
        if result:
            return result

    raise RuntimeError(
        "No usable bash found on Windows. Probed:\n"
        + "\n".join(f"  {p}" for p in probed)
        + "\nInstall Git for Windows (https://git-scm.com/download/win) "
        "and ensure it is on PATH."
    )


# Resolve once at module load so every subprocess invocation shares the same path.
_BASH_EXE = _find_bash()

# Ensure lazy_core is importable.
sys.path.insert(0, str(_SCRIPTS_DIR))

import os as _os_env  # alias used by _set_state_dir / _clear_state_dir helpers

# Attempt to import lazy_core (should already be extracted — Phase 1 complete).
_IMPORT_ERROR: Exception | None = None
lazy_core = None
try:
    import lazy_core  # type: ignore[import]
except ImportError as exc:
    _IMPORT_ERROR = exc

# ---------------------------------------------------------------------------
# State-dir helpers (mirror the pattern from test_lazy_core.py)
# ---------------------------------------------------------------------------

def _set_state_dir(path: Path) -> None:
    """Point the lazy_core state-dir override at *path* for this process."""
    _os_env.environ["LAZY_STATE_DIR"] = str(path)


def _clear_state_dir() -> None:
    """Remove the state-dir override."""
    _os_env.environ.pop("LAZY_STATE_DIR", None)


# ---------------------------------------------------------------------------
# Test infrastructure — same _run_test / _guard / _FAILURES / _PASSES pattern
# as test_lazy_core.py so both files behave identically.
# ---------------------------------------------------------------------------

_FAILURES: list[str] = []
_PASSES:   list[str] = []
_SKIPPED:  list[str] = []


class _ModuleMissing(Exception):
    """Raised when lazy_core is not importable."""


class _TestSkip(unittest.SkipTest):
    """Raised to signal a legitimate SKIP (not a failure).

    Subclasses unittest.SkipTest so BOTH runners agree: the in-file runner
    catches _TestSkip explicitly, and a pytest collection of this module
    treats the raise as a skip (pytest honors unittest.SkipTest) instead of
    an error — keeping the two invocation forms' verdicts consistent."""


def _guard() -> None:
    """Raise _ModuleMissing when lazy_core hasn't been extracted yet."""
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"lazy_core not importable: {_IMPORT_ERROR}")


def _run_test(name: str, fn) -> None:
    """Run a single test, recording PASS / SKIP / FAIL."""
    try:
        fn()
        _PASSES.append(name)
        print(f"  PASS  {name}")
    except _TestSkip as exc:
        _SKIPPED.append(name)
        print(f"  SKIP  {name}: {exc}")
    except _ModuleMissing as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except AssertionError as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _e1_preToolUse_json(
    prompt: str,
    tool_use_id: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
) -> str:
    """Return a JSON string matching the E1 PreToolUse hook-input shape captured
    in RUNTIME_SPIKE.md.  This is the ground-truth fixture shape.

    Fields present in the spike capture:
      session_id, transcript_path, cwd, permission_mode, hook_event_name,
      tool_name ("Agent"), tool_input.{description, prompt, subagent_type},
      tool_use_id

    ``cwd`` (multi-repo-concurrent-runs Phase 2): override the tool-call cwd so a
    test can fire the hook "from" a specific repo. Default preserves the original
    spike-captured value so every pre-Phase-2 test is byte-identical.
    """
    if tool_use_id is None:
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
    if session_id is None:
        session_id = str(uuid.uuid4())
    if cwd is None:
        cwd = "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike-turn-routing"
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {
            "description": "Test dispatch",
            "prompt": prompt,
            "subagent_type": "general-purpose",
        },
        "tool_use_id": tool_use_id,
    }
    return json.dumps(payload)


def _userPromptSubmit_json(
    prompt: str = "what is the current step?",
    session_id: str | None = None,
    cwd: str | None = None,
) -> str:
    """Return a JSON string matching the E1/E3 UserPromptSubmit hook-input shape.

    ``cwd`` (multi-repo-concurrent-runs Phase 2): override the event cwd; default
    preserves the original spike-captured value (pre-Phase-2 tests unchanged).
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    if cwd is None:
        cwd = "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike-turn-routing"
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }
    return json.dumps(payload)


def _run_bash(script: Path, stdin_text: str, env: dict) -> subprocess.CompletedProcess:
    """Pipe *stdin_text* into ``bash <script>`` and return the result.

    Uses _BASH_EXE (resolved at module load) instead of a bare "bash" literal
    so that on Windows we get Git Bash rather than System32\bash.exe (the WSL
    launcher, which cannot execute Windows-path scripts).
    """
    return subprocess.run(
        [_BASH_EXE, str(script)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_guard_py(stdin_text: str, env: dict) -> subprocess.CompletedProcess:
    """Pipe *stdin_text* into ``python lazy_guard.py`` and return the result."""
    return subprocess.run(
        [sys.executable, str(_GUARD_PY)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )


def _base_env(state_dir: Path) -> dict:
    """Return a subprocess env with LAZY_STATE_DIR pointed at *state_dir*."""
    env = dict(os.environ)
    env["LAZY_STATE_DIR"] = str(state_dir)
    return env


def _write_marker_in_dir(
    state_dir: Path,
    repo_root: str | None = None,
    session_id: str | None = None,
) -> None:
    """Write a fresh (non-stale) run marker into *state_dir* via lazy_core.

    Phase 9: pass ``session_id`` to write a BOUND marker.  Tests that fire the
    guard or inject hook multiple times with a single owning session must bind
    the marker up front and pass the SAME session_id in the hook-input JSON —
    otherwise the guard's bind-on-first-allow (WU-9.2) would bind the marker to
    the first random session and treat later calls as non-owner (fast-path
    allow), or the inject hook (WU-9.1) would silently no-op on an unbound
    marker.  Default None preserves the bind-pending marker for tests that
    specifically exercise the unbound path.
    """
    _set_state_dir(state_dir)
    try:
        lazy_core.write_run_marker(
            pipeline="feature",
            cloud=False,
            repo_root=repo_root or str(state_dir / "fixture-repo"),
            max_cycles=10,
            now=time.time(),
            session_id=session_id,
        )
    finally:
        _clear_state_dir()


def _build_fixture_repo(parent: Path) -> Path:
    """Build the minimal fixture repo used by test_subprocess_emit_prompt in
    test_lazy_core.py.  Returns the fixture-repo path.

    The structure mirrors _build_fixture("mid-implementation") from lazy-state.py
    so that --repeat-count --probe --emit-prompt returns a non-null cycle_prompt.
    """
    fixture_repo = parent / "fixture-repo"
    features = fixture_repo / "docs" / "features"
    features.mkdir(parents=True, exist_ok=True)
    (features / "queue.json").write_text(
        json.dumps({"queue": [
            {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
        ]}),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-c"
    fdir.mkdir(exist_ok=True)
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (fdir / "PHASES.md").write_text(
        "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n",
        encoding="utf-8",
    )
    plans = fdir / "plans"
    plans.mkdir(exist_ok=True)
    (plans / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
    return fixture_repo


# ---------------------------------------------------------------------------
# Test 1 — guard files exist
# ---------------------------------------------------------------------------

def test_guard_files_exist():
    """All three hook/guard files must exist on disk.

    RED reason: none of lazy_guard.py, lazy-dispatch-guard.sh, or
    lazy-route-inject.sh have been created yet.
    """
    missing = []
    if not _GUARD_PY.exists():
        missing.append(str(_GUARD_PY))
    if not _GUARD_SH.exists():
        missing.append(str(_GUARD_SH))
    if not _INJECT_SH.exists():
        missing.append(str(_INJECT_SH))
    assert not missing, (
        f"Required files missing (Phase 2 not yet implemented): {missing}"
    )


# ---------------------------------------------------------------------------
# Test 2 — bash guard fast path when no marker
# ---------------------------------------------------------------------------

def test_guard_fast_path_no_marker():
    """With an empty state dir (no marker), the bash wrapper must exit 0 with
    no stdout output.

    RED reason: lazy-dispatch-guard.sh does not exist.
    """
    assert _GUARD_SH.exists(), (
        f"lazy-dispatch-guard.sh missing — Phase 2 not yet implemented: {_GUARD_SH}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        stdin_text = _e1_preToolUse_json("say hello and stop")
        result = _run_bash(_GUARD_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"guard bash fast-path must exit 0 (no marker); "
            f"got exit {result.returncode}; stderr: {result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"guard bash fast-path must produce no stdout (no marker); "
            f"got: {result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# Test 3 — guard denies unregistered prompt
# ---------------------------------------------------------------------------

def test_guard_denies_unregistered_prompt():
    """With a marker present but the prompt NOT in the registry, the guard CLI
    must output deny JSON containing the three corrective substrings:
      're-run the Step 1a probe', '--emit-prompt', '--emit-dispatch hardening'.

    RED reason: lazy_guard.py does not exist.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write a marker so the guard is not in fast-path mode.
        _write_marker_in_dir(state_dir)

        # Prompt is NOT registered — guard must deny.
        unregistered_prompt = "This prompt was never emitted by the script."
        stdin_text = _e1_preToolUse_json(unregistered_prompt)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard CLI must always exit 0 (deny is expressed in JSON, not exit code); "
            f"got exit {result.returncode}; stderr: {result.stderr!r}"
        )

        output = result.stdout.strip()
        assert output != "", (
            "guard must produce deny JSON on stdout when prompt is unregistered; "
            "got empty output"
        )

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard stdout must be valid JSON; got: {output!r}; parse error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        decision = hso.get("permissionDecision")
        assert decision == "deny", (
            f"permissionDecision must be 'deny'; got {decision!r}"
        )

        reason = hso.get("permissionDecisionReason", "")
        for needle in ("re-run the Step 1a probe", "--emit-prompt", "--emit-dispatch hardening"):
            assert needle in reason, (
                f"permissionDecisionReason must contain {needle!r}; "
                f"full reason: {reason!r}"
            )


# ---------------------------------------------------------------------------
# Test 4 — guard allows registered prompt and consumes nonce
# ---------------------------------------------------------------------------

def test_guard_allows_registered_prompt_and_consumes():
    """After register_emission, the guard must allow and consume the nonce.
    The registry entry must have consumed_by == tool_use_id after the call.

    RED reason: lazy_guard.py does not exist / consume_nonce does not record
    consumer.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write marker.
        _write_marker_in_dir(state_dir)

        # Register the prompt.
        the_prompt = "Run the next cycle step exactly as specified."
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(the_prompt, cls="cycle", item_id="feat-c")
        finally:
            _clear_state_dir()

        nonce = entry["nonce"]

        # Pipe into guard — should allow.
        stdin_text = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard CLI must exit 0; got {result.returncode}; stderr: {result.stderr!r}"
        )

        output = result.stdout.strip()
        assert output != "", "guard must produce allow JSON for a registered prompt"

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard stdout must be valid JSON; got: {output!r}; error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        decision = hso.get("permissionDecision")
        assert decision == "allow", (
            f"permissionDecision must be 'allow' for a registered prompt; "
            f"got {decision!r}"
        )

        reason = hso.get("permissionDecisionReason", "")
        assert nonce in reason, (
            f"allow reason must contain the nonce {nonce!r}; got {reason!r}"
        )

        # The registry entry must now be consumed AND record consumed_by.
        _set_state_dir(state_dir)
        try:
            looked_up = lazy_core.lookup_emission(the_prompt)
        finally:
            _clear_state_dir()

        assert looked_up is None, (
            "lookup_emission must return None after the nonce is consumed"
        )

        # Verify consumed_by field directly in the registry JSON.
        registry_path = state_dir / "lazy-prompt-registry.json"
        assert registry_path.exists(), "registry file must exist after guard ran"
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        entries = registry_data.get("entries", [])
        matching = [e for e in entries if e.get("nonce") == nonce]
        assert len(matching) == 1, f"expected 1 entry with nonce {nonce!r}"
        assert matching[0].get("consumed") is True, "entry must be marked consumed"
        # consumed_by is a Phase 2 extension — test its presence explicitly.
        assert matching[0].get("consumed_by") == tool_use_id, (
            f"entry consumed_by must equal tool_use_id {tool_use_id!r}; "
            f"got {matching[0].get('consumed_by')!r}"
        )


# ---------------------------------------------------------------------------
# Test 5 — idempotent re-fire: same tool_use_id allows; different id denies
# ---------------------------------------------------------------------------

def test_guard_idempotent_refire_same_tool_use_id():
    """E4 spike: the PreToolUse hook fires twice for the same denied dispatch
    (same tool_use_id).  The guard must:
      - ALLOW a second call with the SAME tool_use_id (idempotent re-fire).
      - DENY a call with a DIFFERENT tool_use_id (consumed by someone else).

    RED reason: lazy_guard.py does not exist / idempotent re-fire logic not
    yet implemented.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Phase 9: bind the marker to one owning session and pass that session_id
        # on every guard call, so the bind-on-first-allow (WU-9.2) doesn't turn
        # later calls into non-owner fast-path allows.
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        the_prompt = "Execute the planned implementation step."
        tool_use_id_a = "toolu_" + uuid.uuid4().hex[:24]

        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()

        # First call — allow and consume (establishes consumed_by = tool_use_id_a).
        stdin_a = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_a, session_id=owner_session)
        result_first = _run_guard_py(stdin_a, env)
        first_payload = json.loads(result_first.stdout.strip())
        assert first_payload["hookSpecificOutput"]["permissionDecision"] == "allow", (
            f"first call must allow; got {first_payload['hookSpecificOutput'].get('permissionDecision')!r}"
        )

        # Second call with THE SAME tool_use_id — must still allow (idempotent).
        result_same = _run_guard_py(stdin_a, env)
        assert result_same.returncode == 0, (
            f"re-fire with same tool_use_id must exit 0; stderr: {result_same.stderr!r}"
        )
        same_output = result_same.stdout.strip()
        assert same_output != "", "re-fire with same tool_use_id must produce output"
        same_payload = json.loads(same_output)
        same_decision = same_payload["hookSpecificOutput"]["permissionDecision"]
        assert same_decision == "allow", (
            f"re-fire with same tool_use_id must be ALLOW (idempotent); "
            f"got {same_decision!r}"
        )

        # Third call with a DIFFERENT tool_use_id (same owning session) — must deny.
        tool_use_id_b = "toolu_" + uuid.uuid4().hex[:24]
        stdin_b = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_b, session_id=owner_session)
        result_diff = _run_guard_py(stdin_b, env)
        assert result_diff.returncode == 0
        diff_output = result_diff.stdout.strip()
        assert diff_output != "", (
            "guard must produce deny JSON for different tool_use_id consuming a spent nonce"
        )
        diff_payload = json.loads(diff_output)
        diff_decision = diff_payload["hookSpecificOutput"]["permissionDecision"]
        assert diff_decision == "deny", (
            f"different tool_use_id after nonce consumed must be DENY; "
            f"got {diff_decision!r}"
        )


# ---------------------------------------------------------------------------
# Test 6 — CRLF prompt matches LF registration
# ---------------------------------------------------------------------------

def test_guard_crlf_prompt_matches():
    """A prompt registered with LF line endings must be allowed when the
    PreToolUse JSON carries the same prompt with CRLF endings.

    RED reason: lazy_guard.py does not exist / normalization not yet wired.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        _write_marker_in_dir(state_dir)

        # Register with LF endings.
        lf_prompt = "First line.\nSecond line.\nThird line."
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(lf_prompt, cls="cycle")
        finally:
            _clear_state_dir()

        # Pipe a PreToolUse whose prompt uses CRLF endings.
        crlf_prompt = "First line.\r\nSecond line.\r\nThird line."
        stdin_text = _e1_preToolUse_json(crlf_prompt)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0
        output = result.stdout.strip()
        assert output != "", (
            "guard must produce allow JSON when CRLF prompt matches LF registration"
        )
        payload = json.loads(output)
        decision = payload["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow", (
            f"CRLF prompt must match LF registration (normalization must be applied); "
            f"got permissionDecision={decision!r}"
        )


# ---------------------------------------------------------------------------
# Test 7 — hardening depth cap
# ---------------------------------------------------------------------------

def test_guard_hardening_depth_cap():
    """A registry entry with class='hardening' that is consumed by another
    tool_use_id must produce a deny reason containing 'halt' and
    'PushNotification', and must NOT contain '--emit-dispatch hardening'
    (no recursion at depth 1).

    RED reason: lazy_guard.py does not exist / depth guard not yet implemented.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Phase 9: bind to one owning session so both guard calls are owner calls.
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        hardening_prompt = "You are the harden-harness subagent.  Analyze and fix."
        tool_use_id_original = "toolu_" + uuid.uuid4().hex[:24]
        tool_use_id_other    = "toolu_" + uuid.uuid4().hex[:24]

        # Register as class 'hardening'.
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(
                hardening_prompt, cls="hardening", item_id=None
            )
        finally:
            _clear_state_dir()

        # First call — consume by tool_use_id_original (allow, establishes consumer).
        stdin_orig = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_original, session_id=owner_session)
        result_first = _run_guard_py(stdin_orig, env)
        first_payload = json.loads(result_first.stdout.strip())
        assert first_payload["hookSpecificOutput"]["permissionDecision"] == "allow", (
            "First hardening dispatch must be allowed"
        )

        # Now a DIFFERENT tool_use_id tries to dispatch the same (now-consumed)
        # hardening entry — this is depth-1 deny of a hardening-class entry.
        stdin_other = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_other, session_id=owner_session)
        result_depth = _run_guard_py(stdin_other, env)
        assert result_depth.returncode == 0

        depth_output = result_depth.stdout.strip()
        assert depth_output != "", (
            "guard must produce deny JSON for hardening depth-cap case"
        )
        depth_payload = json.loads(depth_output)
        hso = depth_payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"hardening depth-cap must deny; got {hso.get('permissionDecision')!r}"
        )

        reason = hso.get("permissionDecisionReason", "")
        assert "halt" in reason, (
            f"hardening depth-cap deny reason must contain 'halt'; got: {reason!r}"
        )
        assert "PushNotification" in reason, (
            f"hardening depth-cap deny reason must contain 'PushNotification'; "
            f"got: {reason!r}"
        )
        assert "--emit-dispatch hardening" not in reason, (
            f"hardening depth-cap deny reason must NOT contain '--emit-dispatch hardening' "
            f"(no recursion); got: {reason!r}"
        )


# ---------------------------------------------------------------------------
# Test 8 — fail-open on corrupt registry
# ---------------------------------------------------------------------------

def test_guard_fail_open_corrupt_registry():
    """When the registry file is corrupt (garbage bytes), the guard must:
      - exit 0 (fail-open — do not deny)
      - produce no deny output on stdout
      - write a hook-error.json breadcrumb in the state dir

    RED reason: lazy_guard.py does not exist / HOOK_ERROR breadcrumb not yet
    implemented.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write a marker so the guard is not in fast-path mode.
        _write_marker_in_dir(state_dir)

        # Corrupt the registry.
        registry_path = state_dir / "lazy-prompt-registry.json"
        registry_path.write_bytes(b"\xff\xfe CORRUPT \x00 NOT JSON")

        stdin_text = _e1_preToolUse_json("some dispatch prompt")
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0 on corrupt registry (fail-open); "
            f"got exit {result.returncode}; stderr: {result.stderr!r}"
        )

        # stdout must NOT contain a deny permissionDecision.
        stdout = result.stdout.strip()
        if stdout:
            try:
                payload = json.loads(stdout)
                hso = payload.get("hookSpecificOutput", {})
                decision = hso.get("permissionDecision")
                assert decision != "deny", (
                    f"guard must NOT deny on corrupt registry (fail-open); "
                    f"stdout: {stdout!r}"
                )
            except json.JSONDecodeError:
                # Non-JSON stdout is also acceptable for fail-open path.
                pass

        # A hook-error.json breadcrumb must be written.
        hook_error_path = state_dir / "hook-error.json"
        assert hook_error_path.exists(), (
            "guard must write hook-error.json breadcrumb in state dir on internal error"
        )
        try:
            breadcrumb = json.loads(hook_error_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AssertionError(
                f"hook-error.json must be valid JSON; error: {exc}"
            ) from exc

        assert breadcrumb.get("hook") == "lazy-dispatch-guard", (
            f"breadcrumb 'hook' must be 'lazy-dispatch-guard'; got {breadcrumb!r}"
        )
        assert "error" in breadcrumb, (
            f"breadcrumb must have an 'error' field; got keys: {list(breadcrumb)}"
        )
        assert "at" in breadcrumb, (
            f"breadcrumb must have an 'at' field; got keys: {list(breadcrumb)}"
        )


# ---------------------------------------------------------------------------
# Test 9 — inject fast path when no marker
# ---------------------------------------------------------------------------

def test_inject_fast_path_no_marker():
    """With no marker in the state dir, the inject bash hook must exit 0 with
    no stdout output.

    RED reason: lazy-route-inject.sh does not exist.
    """
    assert _INJECT_SH.exists(), (
        f"lazy-route-inject.sh missing — Phase 2 not yet implemented: {_INJECT_SH}"
    )

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        stdin_text = _userPromptSubmit_json()
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject fast-path must exit 0 (no marker); "
            f"got exit {result.returncode}; stderr: {result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"inject fast-path must produce no stdout (no marker); "
            f"got: {result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# Test 10 — inject emits LAZY-ROUTE banner with probe evidence
# ---------------------------------------------------------------------------

def test_inject_emits_lazy_route_banner():
    """With a marker pointing at a real fixture repo, the inject hook must
    produce stdout JSON whose hookSpecificOutput.additionalContext:
      - starts with 'LAZY-ROUTE (hook-injected'
      - contains probe-JSON evidence (e.g. 'current_step' or 'cycle_header'
        or a sub_skill field from the probe output JSON)

    RED reason: lazy-route-inject.sh does not exist.
    """
    _guard()
    assert _INJECT_SH.exists(), (
        f"lazy-route-inject.sh missing — Phase 2 not yet implemented: {_INJECT_SH}"
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()

        # Build a fixture repo so the probe has a real queue to read.
        fixture_repo = _build_fixture_repo(td_path)
        env = _base_env(state_dir)

        # Phase 9: the marker must be BOUND to the hook-input session for inject
        # to emit a banner (inject is a silent no-op on an UNBOUND marker — WU-9.1).
        owner_session = str(uuid.uuid4())
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
                session_id=owner_session,
            )
        finally:
            _clear_state_dir()

        stdin_text = _userPromptSubmit_json(session_id=owner_session)
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject hook must exit 0; got {result.returncode}; stderr: {result.stderr!r}"
        )

        output = result.stdout.strip()
        assert output != "", (
            "inject hook must produce output when marker is present and repo is valid"
        )

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"inject hook stdout must be valid JSON; got: {output[:300]!r}; error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        ctx = hso.get("additionalContext", "")

        assert ctx.startswith("LAZY-ROUTE (hook-injected"), (
            f"additionalContext must start with 'LAZY-ROUTE (hook-injected'; "
            f"got: {ctx[:120]!r}"
        )

        # Probe evidence: at least one of these keys appears in the injected context
        # because the probe JSON is embedded in the additionalContext string.
        probe_evidence_keys = ("current_step", "cycle_header", "sub_skill", "cycle_prompt")
        assert any(key in ctx for key in probe_evidence_keys), (
            f"additionalContext must contain probe-JSON evidence "
            f"(one of {probe_evidence_keys}); got: {ctx[:300]!r}"
        )


# ---------------------------------------------------------------------------
# Test 11 — inject surfaces HOOK_ERROR breadcrumb
# ---------------------------------------------------------------------------

def test_inject_surfaces_hook_error_breadcrumb():
    """When a hook-error.json breadcrumb already exists in the state dir AND
    a marker is present, the inject hook must include 'HOOK_ERROR' in the
    injected additionalContext (self-announcing guard breakage).

    RED reason: lazy-route-inject.sh does not exist / HOOK_ERROR surfacing not
    yet implemented.
    """
    _guard()
    assert _INJECT_SH.exists(), (
        f"lazy-route-inject.sh missing — Phase 2 not yet implemented: {_INJECT_SH}"
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()

        # Build fixture repo for the marker.
        fixture_repo = _build_fixture_repo(td_path)
        env = _base_env(state_dir)

        # Phase 9: bind the marker to the hook-input session (inject is a silent
        # no-op on an UNBOUND marker — WU-9.1 — so the breadcrumb surfacing only
        # happens on the bound-owner path).
        owner_session = str(uuid.uuid4())
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
                session_id=owner_session,
            )
        finally:
            _clear_state_dir()

        # Pre-place a hook-error.json breadcrumb.
        breadcrumb = {
            "hook": "lazy-dispatch-guard",
            "error": "simulated error for test",
            "at": "2026-06-11T00:00:00Z",
        }
        (state_dir / "hook-error.json").write_text(
            json.dumps(breadcrumb), encoding="utf-8"
        )

        stdin_text = _userPromptSubmit_json(session_id=owner_session)
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject hook must exit 0 even when breadcrumb is present; "
            f"stderr: {result.stderr!r}"
        )

        output = result.stdout.strip()
        assert output != "", "inject hook must produce output when marker and breadcrumb present"

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"inject hook stdout must be valid JSON; got: {output[:300]!r}; error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        ctx = hso.get("additionalContext", "")

        assert "HOOK_ERROR" in ctx, (
            f"additionalContext must contain 'HOOK_ERROR' when breadcrumb is present; "
            f"got: {ctx[:300]!r}"
        )


# ---------------------------------------------------------------------------
# Test 12 — WSL pipe-test (platform-conditional)
# ---------------------------------------------------------------------------

def test_pipe_tests_wsl():
    """Re-run tests 2 and 3 inside WSL if wsl is available.

    If wsl is unavailable (not on PATH or wsl bash python3 not found), print a
    SKIP line.  This test must never FAIL due to WSL absence — only due to
    actual behaviour regressions when WSL is present.

    RED reason: WSL environment may lack the hooks or lazy_guard.py;
    SKIP reason: WSL unavailable on this machine.
    """
    # Check if wsl is on PATH. On a non-Windows host the binary does not exist
    # at all, which raises before the returncode check — that is the same
    # "WSL absent" condition and must SKIP, not FAIL (this test's contract).
    try:
        wsl_check = subprocess.run(
            ["wsl", "bash", "-c", "echo OK"],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, OSError):
        raise _TestSkip("wsl not available on this machine (no wsl binary)")
    if wsl_check.returncode != 0 or "OK" not in wsl_check.stdout:
        raise _TestSkip("wsl not available or not functional on this machine")

    # Check if python3 is available inside WSL.
    py3_check = subprocess.run(
        ["wsl", "bash", "-c", "command -v python3"],
        capture_output=True, text=True, timeout=15,
    )
    if py3_check.returncode != 0 or not py3_check.stdout.strip():
        raise _TestSkip("python3 not available inside WSL")

    # Translate the hook paths to WSL-compatible paths.
    def _wslpath(win_path: str) -> str:
        # wslpath requires forward-slash form on its command line (the WSL
        # shell strips backslashes from the argument when the host passes the
        # raw Windows path with backslashes).  Convert before invoking.
        forward_slash_path = win_path.replace("\\", "/")
        r = subprocess.run(
            ["wsl", "wslpath", "-u", forward_slash_path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            raise AssertionError(
                f"wslpath failed for {win_path!r} (converted: {forward_slash_path!r}): "
                f"{r.stderr.strip()!r}"
            )
        return r.stdout.strip()

    guard_sh_wsl   = _wslpath(str(_GUARD_SH))
    guard_py_wsl   = _wslpath(str(_GUARD_PY))

    # -- WSL test 2 equivalent: fast-path no-marker --

    with tempfile.TemporaryDirectory() as td:
        state_dir_win = Path(td) / "state"
        state_dir_win.mkdir()
        state_dir_wsl = _wslpath(str(state_dir_win))

        stdin_text = _e1_preToolUse_json("say hello and stop")

        result_fast = subprocess.run(
            ["wsl", "bash", "-c",
             f"echo '{stdin_text}' | LAZY_STATE_DIR={state_dir_wsl} bash {guard_sh_wsl}"],
            capture_output=True, text=True, timeout=30,
        )
        assert result_fast.returncode == 0, (
            f"WSL guard fast-path must exit 0; got {result_fast.returncode}; "
            f"stderr: {result_fast.stderr!r}"
        )
        assert result_fast.stdout.strip() == "", (
            f"WSL guard fast-path must produce no stdout; got: {result_fast.stdout!r}"
        )

    # -- WSL test 3 equivalent: deny unregistered prompt --

    # We need a marker in a temp state dir that WSL can also see.
    with tempfile.TemporaryDirectory() as td:
        state_dir_win = Path(td) / "state"
        state_dir_win.mkdir()
        state_dir_wsl = _wslpath(str(state_dir_win))

        # Write marker via lazy_core (Python in this process, Windows paths).
        _guard()
        _write_marker_in_dir(state_dir_win)

        stdin_text = _e1_preToolUse_json("Unregistered prompt for WSL test")

        result_deny = subprocess.run(
            ["wsl", "bash", "-c",
             f"echo '{stdin_text}' | "
             f"LAZY_STATE_DIR={state_dir_wsl} python3 {guard_py_wsl}"],
            capture_output=True, text=True, timeout=30,
        )
        assert result_deny.returncode == 0, (
            f"WSL guard CLI must exit 0; got {result_deny.returncode}; "
            f"stderr: {result_deny.stderr!r}"
        )
        wsl_output = result_deny.stdout.strip()
        assert wsl_output != "", (
            "WSL guard must produce deny JSON for unregistered prompt"
        )
        try:
            wsl_payload = json.loads(wsl_output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"WSL guard stdout must be valid JSON; got: {wsl_output!r}; error: {exc}"
            ) from exc

        wsl_decision = wsl_payload["hookSpecificOutput"]["permissionDecision"]
        assert wsl_decision == "deny", (
            f"WSL guard must deny unregistered prompt; got {wsl_decision!r}"
        )
        wsl_reason = wsl_payload["hookSpecificOutput"].get("permissionDecisionReason", "")
        assert "re-run the Step 1a probe" in wsl_reason, (
            f"WSL deny reason must contain 're-run the Step 1a probe'; "
            f"got: {wsl_reason!r}"
        )


# ---------------------------------------------------------------------------
# Helper: SessionStart JSON fixture
# ---------------------------------------------------------------------------

def _sessionStart_json(
    source: str = "compact",
    session_id: str | None = None,
) -> str:
    """Return a JSON string matching the SessionStart hook-input shape."""
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike-turn-routing",
        "hook_event_name": "SessionStart",
        "source": source,
    }
    return json.dumps(payload)


def _preToolUse_no_prompt_json(
    tool_use_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Return a PreToolUse JSON where tool_input has NO 'prompt' key at all."""
    if tool_use_id is None:
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike-turn-routing",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "ls",
        },
        "tool_use_id": tool_use_id,
    }
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Test 13 — _find_entry_by_sha prefers matching consumer then newest entry
# ---------------------------------------------------------------------------

def test_find_entry_by_sha_same_prompt_two_consumers():
    """Item 1 regression: same prompt registered twice, consumed by A then B.
    Re-firing as B must be ALLOW (idempotent re-fire for B's own nonce).

    Before the fix, _find_entry_by_sha returned the OLDEST matching entry
    (index 0, consumed by A), so B's re-fire was mistakenly seen as
    'consumed-by-other' and DENIED.  After the fix, it prefers the entry
    with consumed_by == B's tool_use_id.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Phase 9: one owning session for all three guard calls (A consume,
        # B consume, B re-fire) so the bind-on-first-allow doesn't reclassify
        # later calls as non-owner fast-path allows.
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        the_prompt = "Run next cycle step — shared prompt text for two registrations."
        tool_use_id_a = "toolu_" + uuid.uuid4().hex[:24]
        tool_use_id_b = "toolu_" + uuid.uuid4().hex[:24]

        # Register first emission and consume it as A.
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()
        stdin_a = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_a, session_id=owner_session)
        r1 = _run_guard_py(stdin_a, env)
        p1 = json.loads(r1.stdout.strip())
        assert p1["hookSpecificOutput"]["permissionDecision"] == "allow", (
            f"first registration (consumed by A) must allow; got {p1}"
        )

        # Register second emission and consume it as B.
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()
        stdin_b = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_b, session_id=owner_session)
        r2 = _run_guard_py(stdin_b, env)
        p2 = json.loads(r2.stdout.strip())
        assert p2["hookSpecificOutput"]["permissionDecision"] == "allow", (
            f"second registration (consumed by B) must allow; got {p2}"
        )

        # Re-fire as B — must ALLOW (idempotent re-fire: B owns its nonce).
        r3 = _run_guard_py(stdin_b, env)
        output3 = r3.stdout.strip()
        assert output3 != "", "re-fire as B must produce output"
        p3 = json.loads(output3)
        decision3 = p3["hookSpecificOutput"]["permissionDecision"]
        assert decision3 == "allow", (
            f"re-fire as B must be ALLOW (idempotent — B owns its nonce); "
            f"got {decision3!r}.  This is the _find_entry_by_sha regression: "
            f"the guard must prefer the entry consumed_by==B, not the oldest entry."
        )


# ---------------------------------------------------------------------------
# Test 14 — inject stamps session_id when marker is unbound
# ---------------------------------------------------------------------------

def test_inject_unbound_marker_silent_and_unchanged():
    """Phase 9 WU-9.1 (REVISED from test_inject_stamps_session_id_when_unbound):
    when the run marker has session_id=None (bind-pending), the inject hook must
    be a SILENT NO-OP — exit 0, no stdout, AND the marker file must remain
    BYTE-IDENTICAL (still unbound, no stamp).  Binding moved to the guard's
    ALLOW path (WU-9.2); inject NEVER binds.

    Previously (Phase 2) this test asserted inject STAMPED the marker with the
    hook-input session_id (bind-on-first-hook-firing) — that is exactly the race
    Phase 9 WU-9.1 removed.
    """
    _guard()
    assert _INJECT_SH.exists(), f"lazy-route-inject.sh missing: {_INJECT_SH}"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        fixture_repo = _build_fixture_repo(td_path)
        env = _base_env(state_dir)

        # Write marker with session_id=None (bind-pending).
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
                session_id=None,  # deliberately unbound
            )
        finally:
            _clear_state_dir()

        # Capture the marker bytes BEFORE the inject hook fires.
        marker_path = state_dir / "lazy-run-marker.json"
        marker_bytes_before = marker_path.read_bytes()
        marker_before = json.loads(marker_bytes_before)
        assert marker_before.get("session_id") is None, (
            f"marker must start with session_id=None; got {marker_before.get('session_id')!r}"
        )

        # No registry should exist yet (the probe would create one if it ran).
        registry_path = state_dir / "lazy-prompt-registry.json"
        assert not registry_path.exists(), "pre-condition: no registry before inject"

        # Run the inject hook with a specific session_id.
        the_session_id = str(uuid.uuid4())
        stdin_text = _userPromptSubmit_json(session_id=the_session_id)
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject hook must exit 0; stderr: {result.stderr!r}"
        )
        # No banner / no output — silent no-op on an unbound marker.
        assert result.stdout.strip() == "", (
            f"inject on an UNBOUND marker must produce NO output (silent no-op); "
            f"got: {result.stdout!r}"
        )

        # The marker file must be BYTE-IDENTICAL — no stamp, no mutation.
        marker_bytes_after = marker_path.read_bytes()
        assert marker_bytes_after == marker_bytes_before, (
            "Phase 9 WU-9.1: inject must NOT mutate an unbound marker "
            "(no bind-on-first-hook-firing); the marker file must be byte-identical"
        )

        # And NO registry was created — the probe must never have run.
        assert not registry_path.exists(), (
            "Phase 9 WU-9.1: inject on an unbound marker must NOT run the probe "
            "or register any emission (no registry file should appear)"
        )


# ---------------------------------------------------------------------------
# Test 15 — guard: marker bound to different session_id → silent allow (stale)
# ---------------------------------------------------------------------------

def test_guard_different_session_id_silent_allow():
    """Item 2 (REVISED for Phase 8 WU-8.1): when the marker is bound to a
    different session_id, the guard must treat the marker as stale (path B) and
    silently allow (exit 0, no output) — as if no marker were present — BUT must
    LEAVE THE MARKER ON DISK (non-destructive path B).  A concurrent non-owner
    session's guard firing must never disarm the owning session's live run.

    Previously this test asserted the guard DELETED the stale marker; that
    delete-on-read-B behavior is exactly what Phase 8 WU-8.1 removed.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write marker bound to session A.
        session_a = str(uuid.uuid4())
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(state_dir / "fixture-repo"),
                max_cycles=10,
                now=time.time(),
                session_id=session_a,
            )
        finally:
            _clear_state_dir()

        # Register a prompt (so there's something to deny if the guard fires).
        the_prompt = "Execute the step from the run marker session A."
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()

        # Guard fires for a DIFFERENT session_id — marker is treated as stale.
        session_b = str(uuid.uuid4())
        stdin_text = _e1_preToolUse_json(the_prompt, session_id=session_b)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0 when marker is stale (different session); "
            f"stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output == "", (
            f"guard must produce no output when marker is stale (different session); "
            f"got: {output!r}"
        )

        # Phase 8 WU-8.1: the marker file must SURVIVE — a non-owner guard firing
        # must NOT disarm the owner's live run (non-destructive path B).
        marker_path = state_dir / "lazy-run-marker.json"
        assert marker_path.exists(), (
            "Phase 8 WU-8.1: guard must LEAVE the marker on disk on a non-owner "
            "session mismatch (non-destructive path B) — the owning session's "
            "live run must stay armed"
        )
        # And the owning session must still read it.
        _set_state_dir(state_dir)
        try:
            owner_marker = lazy_core.read_run_marker(session_id=session_a)
        finally:
            _clear_state_dir()
        assert owner_marker is not None and owner_marker.get("session_id") == session_a, (
            "owner session must still read the marker after a non-owner guard firing"
        )


# ---------------------------------------------------------------------------
# Test 16 — guard slow path via bash: marker present, registered prompt → allow
# ---------------------------------------------------------------------------

def test_guard_bash_slow_path_allows_registered_prompt():
    """Item 5(a): the bash guard slow path (marker present, registered prompt)
    invoked THROUGH bash lazy-dispatch-guard.sh must produce allow JSON.

    This path had zero coverage previously and previously broke (the bash
    wrapper was untested end-to-end with a registered prompt).
    """
    _guard()
    assert _GUARD_SH.exists(), f"lazy-dispatch-guard.sh missing: {_GUARD_SH}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        _write_marker_in_dir(state_dir)

        the_prompt = "Execute this registered dispatch prompt via bash guard."
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()

        stdin_text = _e1_preToolUse_json(the_prompt)
        result = _run_bash(_GUARD_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"bash guard slow-path must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", (
            "bash guard slow-path must produce allow JSON for a registered prompt"
        )
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"bash guard output must be valid JSON; got {output[:200]!r}; error: {exc}"
            ) from exc
        decision = payload["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow", (
            f"bash guard slow-path must allow a registered prompt; got {decision!r}"
        )


# ---------------------------------------------------------------------------
# Test 17 — inject with SessionStart + source==compact includes re-entry text
# ---------------------------------------------------------------------------

def test_inject_sessionstart_compact_includes_reentry_protocol():
    """Item 5(b): inject with SessionStart + source='compact' must include the
    post-compaction re-entry protocol marker text and the cycle counters in
    additionalContext.
    """
    _guard()
    assert _INJECT_SH.exists(), f"lazy-route-inject.sh missing: {_INJECT_SH}"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        fixture_repo = _build_fixture_repo(td_path)
        env = _base_env(state_dir)

        # Phase 9: bind the marker to the SessionStart session so inject emits
        # (silent no-op on an UNBOUND marker — WU-9.1).
        the_session_id = str(uuid.uuid4())
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
                session_id=the_session_id,
            )
        finally:
            _clear_state_dir()

        # Build a SessionStart with source=compact.
        stdin_text = _sessionStart_json(source="compact", session_id=the_session_id)
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject hook must exit 0 for SessionStart/compact; stderr: {result.stderr!r}"
        )

        output = result.stdout.strip()
        assert output != "", "inject hook must produce output for SessionStart/compact"

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"inject output must be valid JSON; got {output[:200]!r}; error: {exc}"
            ) from exc

        ctx = payload["hookSpecificOutput"].get("additionalContext", "")

        # Must contain post-compaction re-entry protocol marker text.
        assert "POST-COMPACTION RE-ENTRY" in ctx, (
            f"additionalContext must contain 'POST-COMPACTION RE-ENTRY' for "
            f"SessionStart/compact; got: {ctx[:300]!r}"
        )

        # Must contain cycle counters (forward_cycles and meta_cycles appear in the text).
        assert "forward_cycles=" in ctx, (
            f"additionalContext must contain 'forward_cycles=' for SessionStart/compact; "
            f"got: {ctx[:300]!r}"
        )
        assert "meta_cycles=" in ctx, (
            f"additionalContext must contain 'meta_cycles=' for SessionStart/compact; "
            f"got: {ctx[:300]!r}"
        )


# ---------------------------------------------------------------------------
# Test 18 — stale marker (>24h) → both hooks silent exit 0, marker deleted
# ---------------------------------------------------------------------------

def test_stale_marker_both_hooks_silent_and_deleted():
    """Item 5(c): when the marker's started_at is >24h ago, both the guard and
    inject hooks must exit 0 silently (no output), and the marker file must be
    deleted (stale-marker cleanup path A).
    """
    _guard()
    assert _GUARD_SH.exists(), f"lazy-dispatch-guard.sh missing: {_GUARD_SH}"
    assert _INJECT_SH.exists(), f"lazy-route-inject.sh missing: {_INJECT_SH}"

    stale_seconds = 25 * 3600  # 25 hours ago — definitely stale

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write a marker with a started_at 25 hours in the past.
        stale_now = time.time() - stale_seconds
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(state_dir / "fixture-repo"),
                max_cycles=10,
                now=stale_now,
            )
        finally:
            _clear_state_dir()

        marker_path = state_dir / "lazy-run-marker.json"
        assert marker_path.exists(), "marker must exist before test"

        # --- Guard hook ---
        stdin_g = _e1_preToolUse_json("some dispatch prompt")
        result_g = _run_bash(_GUARD_SH, stdin_g, env)
        assert result_g.returncode == 0, (
            f"guard must exit 0 for stale marker; stderr: {result_g.stderr!r}"
        )
        assert result_g.stdout.strip() == "", (
            f"guard must produce no output for stale marker; got: {result_g.stdout!r}"
        )
        # Marker must be deleted after the guard fired on a stale marker.
        assert not marker_path.exists(), (
            "guard must delete the stale marker (age staleness path A)"
        )

    # Re-create a fresh stale marker for the inject hook test (separate state dir).
    with tempfile.TemporaryDirectory() as td2:
        td2_path = Path(td2)
        state_dir2 = td2_path / "state"
        state_dir2.mkdir()
        env2 = _base_env(state_dir2)

        stale_now2 = time.time() - stale_seconds
        _set_state_dir(state_dir2)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(state_dir2 / "fixture-repo"),
                max_cycles=10,
                now=stale_now2,
            )
        finally:
            _clear_state_dir()

        marker_path2 = state_dir2 / "lazy-run-marker.json"
        assert marker_path2.exists(), "marker must exist before inject test"

        # --- Inject hook ---
        stdin_i = _userPromptSubmit_json()
        result_i = _run_bash(_INJECT_SH, stdin_i, env2)
        assert result_i.returncode == 0, (
            f"inject must exit 0 for stale marker; stderr: {result_i.stderr!r}"
        )
        assert result_i.stdout.strip() == "", (
            f"inject must produce no output for stale marker; got: {result_i.stdout!r}"
        )
        # Marker must be deleted after the inject fired on a stale marker.
        assert not marker_path2.exists(), (
            "inject must delete the stale marker (age staleness path A)"
        )


# ---------------------------------------------------------------------------
# Test 19 — guard: no "prompt" key in tool_input → silent allow (exit 0)
# ---------------------------------------------------------------------------

def test_guard_no_prompt_key_silent_allow():
    """Item 6: when tool_input has NO 'prompt' key at all, the guard must
    exit 0 and produce no output (silent allow).  This is NOT the same as
    an empty or unregistered prompt — a missing key means there is nothing
    to validate.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write a marker so we are NOT in the fast-path (marker-absent) branch.
        _write_marker_in_dir(state_dir)

        # Use a PreToolUse JSON with no "prompt" key in tool_input.
        stdin_text = _preToolUse_no_prompt_json()
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0 when tool_input has no 'prompt' key; "
            f"stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output == "", (
            f"guard must produce NO output when tool_input has no 'prompt' key; "
            f"got: {output!r}"
        )


# ---------------------------------------------------------------------------
# Test 20 — hardening depth cap: stale unconsumed hardening entry → cap deny
# ---------------------------------------------------------------------------

def test_guard_hardening_depth_cap_stale_unconsumed():
    """Item 7: a hardening-class entry that is stale/TTL-expired but NOT yet
    consumed must still trigger the hardening depth-cap deny (halt +
    PushNotification, no --emit-dispatch hardening) when a new dispatch attempt
    arrives for the same prompt.

    Before the fix, only consumed-by-other hardening entries triggered the cap;
    stale/expired unconsumed hardening entries fell through to the standard
    corrective deny (which contains '--emit-dispatch hardening', causing the
    exact recursion the cap is supposed to prevent).
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        _write_marker_in_dir(state_dir)

        hardening_prompt = "You are the harden-harness subagent (stale unconsumed test)."

        # Register the hardening entry with an emitted_at far in the past so
        # it fails the TTL gate in lookup_emission (stale = expired).
        stale_emitted_at = time.time() - (2 * 3600)  # 2 hours ago > 30min TTL
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(
                hardening_prompt, cls="hardening", item_id=None, now=stale_emitted_at
            )
        finally:
            _clear_state_dir()

        # A fresh dispatch attempt with a new tool_use_id — the entry is stale
        # (not consumed, but expired).  Must trigger hardening cap deny, NOT
        # the standard corrective recipe that contains '--emit-dispatch hardening'.
        new_tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(hardening_prompt, tool_use_id=new_tool_use_id)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", "guard must produce deny JSON for stale unconsumed hardening entry"

        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard output must be valid JSON; got {output[:200]!r}; error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"stale unconsumed hardening entry must deny; got {hso.get('permissionDecision')!r}"
        )
        reason = hso.get("permissionDecisionReason", "")
        assert "halt" in reason, (
            f"hardening depth-cap deny must contain 'halt'; got: {reason!r}"
        )
        assert "PushNotification" in reason, (
            f"hardening depth-cap deny must contain 'PushNotification'; got: {reason!r}"
        )
        assert "--emit-dispatch hardening" not in reason, (
            f"hardening depth-cap deny must NOT contain '--emit-dispatch hardening'; "
            f"got: {reason!r}"
        )


# ---------------------------------------------------------------------------
# Phase 4 — hardening depth-cap integration test against a REAL emitted entry
# ---------------------------------------------------------------------------
#
# RED STATE: 'hardening' is not yet in lazy_core.DISPATCH_CLASSES (Phase 3 only),
# so the --emit-dispatch hardening CLI invocation will fail (ValueError or
# argparse exit 2), causing the subprocess to exit non-zero → the fixture-setup
# assertion fires before any guard logic is reached.
#
# Resolve the scripts dir path for the subprocess invocation.
_LAZY_STATE_SCRIPT = _SCRIPTS_DIR / "lazy-state.py"

# Resolve the real dispatch-hardening.md template dir to read @requires keys
# dynamically — mirrors the pattern in test_lazy_core.py's matrix tests.
_HARDENING_TEMPLATE_DIR = _SCRIPTS_DIR.parent / "skills" / "_components" / "lazy-batch-prompts"
if not _HARDENING_TEMPLATE_DIR.exists():
    _HARDENING_TEMPLATE_DIR = _SCRIPTS_DIR.parent.parent / "skills" / "_components" / "lazy-batch-prompts"


def _read_hardening_requires_keys_hooks() -> list[str] | None:
    """Return the @requires keys declared in dispatch-hardening.md, or None."""
    tpl_path = _HARDENING_TEMPLATE_DIR / "dispatch-hardening.md"
    if not tpl_path.exists():
        return None
    text = tpl_path.read_text(encoding="utf-8")
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    import re as _re
    m = _re.match(r"^<!-- @requires ([a-z0-9_,]+) -->", first_line)
    if not m:
        return None
    return [k.strip() for k in m.group(1).split(",") if k.strip()]


def test_guard_depth_cap_real_hardening_entry():
    """Phase 4 integration test: register a REAL emitted hardening prompt via
    the actual --emit-dispatch hardening CLI subprocess (with a marker present),
    then:
      (a) Pipe a PreToolUse JSON with the exact prompt → ALLOW (depth-0
          dispatch works; nonce is unconsumed at this point).
      (b) Pipe the same prompt with a DIFFERENT tool_use_id (simulating a
          second dispatch attempt after the nonce was consumed by (a)) →
          DENY with a reason that contains 'halt' and 'PushNotification' and
          does NOT contain '--emit-dispatch hardening' (depth-cap on a real
          hardening entry, not a synthetic one).

    This test is the Phase 4 analog of test_guard_hardening_depth_cap (Phase 2)
    and test_guard_hardening_depth_cap_stale_unconsumed (Phase 2 review fix),
    but uses a REAL script-emitted hardening registry entry rather than a
    synthetically registered one.

    RED reasons:
      - 'hardening' not in DISPATCH_CLASSES → lazy-state.py --emit-dispatch
        hardening exits non-zero → fixture-setup assertion fires.
      - dispatch-hardening.md template missing → exit 1 → same path.
      - Guard py missing → AssertionError on _GUARD_PY.exists() check.
    """
    _guard()
    assert _GUARD_PY.exists(), (
        f"lazy_guard.py missing — Phase 2 not yet implemented: {_GUARD_PY}"
    )

    # Read @requires keys for hardening template so we can build the context
    # flags.  If the template doesn't exist we let the subprocess failure below
    # produce the actual RED reason (missing template → exit 1).
    requires_keys = _read_hardening_requires_keys_hooks()
    context_flags: list[str] = []
    if requires_keys:
        for k in requires_keys:
            context_flags += ["--context", f"{k}=test-{k}"]
        if "item_id" not in requires_keys:
            context_flags += ["--context", "item_id=feat-hardening-test"]
    else:
        # Template absent: use generic context flags; the subprocess will fail
        # with a meaningful error about the missing template or class, which is
        # the correct RED failure reason.
        context_flags = [
            "--context", "denied_prompt_summary=test-dps",
            "--context", "denial_reason=test-dr",
            "--context", "probe_json=test-pj",
            "--context", "registry_state=test-rs",
            "--context", "trigger_kind=test-tk",
            "--context", "item_id=feat-hardening-test",
            "--context", "cwd=/tmp/test",
        ]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Write a marker so --emit-dispatch hardening registers in the registry.
        # Phase 9: bind it so both guard calls below are owner calls (the second
        # call's different tool_use_id must reach the depth-cap DENY, not a
        # non-owner fast-path allow from a bind-on-first-allow side effect).
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        # --- Emit a REAL hardening dispatch prompt via the actual CLI. ---
        cmd = [
            sys.executable, str(_LAZY_STATE_SCRIPT),
            "--emit-dispatch", "hardening",
        ] + context_flags

        emit_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        # Argparse exit 2 = flag not recognized → 'hardening' not in DISPATCH_CLASSES.
        assert emit_result.returncode != 2, (
            "--emit-dispatch hardening: flag not recognized or class unknown "
            f"(argparse exit 2 — 'hardening' not yet in DISPATCH_CLASSES).\n"
            f"stderr: {emit_result.stderr[:400]!r}"
        )
        assert emit_result.returncode == 0, (
            f"lazy-state.py --emit-dispatch hardening failed with exit "
            f"{emit_result.returncode}; "
            f"stderr: {emit_result.stderr[:400]!r}; "
            f"stdout: {emit_result.stdout[:400]!r}"
        )

        try:
            emit_out = json.loads(emit_result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"--emit-dispatch hardening stdout must be valid JSON; "
                f"got: {emit_result.stdout[:400]!r}; error: {exc}"
            ) from exc

        hardening_prompt = emit_out.get("dispatch_prompt")
        assert hardening_prompt, (
            f"--emit-dispatch hardening must emit a non-null dispatch_prompt; "
            f"got: {emit_out!r}"
        )
        assert emit_out.get("dispatch_class") == "hardening", (
            f"dispatch_class must be 'hardening'; got {emit_out.get('dispatch_class')!r}"
        )

        # Verify the registry entry exists (sanity check before guard tests).
        registry_path = state_dir / "lazy-prompt-registry.json"
        assert registry_path.exists(), (
            "Registry file must exist after --emit-dispatch hardening with marker"
        )
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        entries = registry_data.get("entries", [])
        hardening_entries = [e for e in entries if e.get("class") == "hardening"]
        assert len(hardening_entries) >= 1, (
            f"Registry must contain at least one entry with class='hardening'; "
            f"found entries: {[(e.get('class'), e.get('prompt_sha256', '')[:8]) for e in entries]}"
        )

        # --- (a) Depth-0: pipe the real hardening prompt → ALLOW. ---
        tool_use_id_original = "toolu_" + uuid.uuid4().hex[:24]
        stdin_allow = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_original, session_id=owner_session)
        result_allow = _run_guard_py(stdin_allow, env)

        assert result_allow.returncode == 0, (
            f"guard must exit 0 for depth-0 hardening dispatch; "
            f"stderr: {result_allow.stderr!r}"
        )
        allow_output = result_allow.stdout.strip()
        assert allow_output != "", (
            "guard must produce allow JSON for depth-0 hardening dispatch "
            "(unconsumed real registry entry)"
        )
        try:
            allow_payload = json.loads(allow_output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard output must be valid JSON; got: {allow_output[:200]!r}; "
                f"error: {exc}"
            ) from exc

        allow_decision = allow_payload["hookSpecificOutput"]["permissionDecision"]
        assert allow_decision == "allow", (
            f"depth-0 hardening dispatch must be ALLOWED; got {allow_decision!r}.\n"
            f"Full payload: {allow_payload}"
        )

        # --- (b) Depth-1: same prompt, different tool_use_id → depth-cap DENY. ---
        # The nonce was consumed by (a); a different tool_use_id now tries the
        # same hardening prompt — this is the depth-1 deny case on a REAL entry.
        tool_use_id_other = "toolu_" + uuid.uuid4().hex[:24]
        stdin_deny = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_other, session_id=owner_session)
        result_deny = _run_guard_py(stdin_deny, env)

        assert result_deny.returncode == 0, (
            f"guard must exit 0 for depth-1 hardening deny; "
            f"stderr: {result_deny.stderr!r}"
        )
        deny_output = result_deny.stdout.strip()
        assert deny_output != "", (
            "guard must produce deny JSON for depth-1 hardening dispatch "
            "(real consumed registry entry, different tool_use_id)"
        )
        try:
            deny_payload = json.loads(deny_output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard output must be valid JSON; got: {deny_output[:200]!r}; "
                f"error: {exc}"
            ) from exc

        hso = deny_payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"depth-1 hardening dispatch must be DENIED; "
            f"got {hso.get('permissionDecision')!r}.\nFull payload: {deny_payload}"
        )

        reason = hso.get("permissionDecisionReason", "")

        # Reason must contain 'halt' (halt instruction per SPEC depth-cap rule).
        assert "halt" in reason, (
            f"depth-1 hardening depth-cap deny reason must contain 'halt'; "
            f"got: {reason!r}"
        )
        # Reason must contain 'PushNotification' (operator notification required).
        assert "PushNotification" in reason, (
            f"depth-1 hardening depth-cap deny reason must contain "
            f"'PushNotification'; got: {reason!r}"
        )
        # Reason must NOT contain '--emit-dispatch hardening' — no recursion.
        assert "--emit-dispatch hardening" not in reason, (
            f"depth-1 hardening depth-cap deny reason must NOT contain "
            f"'--emit-dispatch hardening' (no recursion at depth 1); "
            f"got: {reason!r}"
        )


# ---------------------------------------------------------------------------
# Phase 7 — guard deny-ledger write through the real bash hook path
# ---------------------------------------------------------------------------

def test_guard_bash_deny_writes_deny_ledger():
    """Phase 7 WU-7.1: a deny through the REAL bash lazy-dispatch-guard.sh hook
    path (marked run + unregistered prompt) produces the deny JSON on stdout AND
    creates the deny-ledger file in the scoped state dir.

    Mirrors test_guard_bash_slow_path_allows_registered_prompt's structure, but
    for the deny path and asserting the ledger side-effect.
    """
    _guard()
    assert _GUARD_SH.exists(), f"lazy-dispatch-guard.sh missing: {_GUARD_SH}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Marked run, but the prompt is NEVER registered → the guard must deny.
        # stale-marker-arms-validate-deny-on-unrelated-dispatches D2 (2026-06-19):
        # the ledger append for a GENERIC default-deny now requires a BOUND
        # marker (an UNBOUND/pre-bind deny is no-debt by design — WU-3). Bind the
        # marker to an owner session and dispatch AS the owner so this remains a
        # genuine validate-deny that DOES accrue debt (the test's original intent).
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        the_prompt = "HAND-COMPOSED unregistered dispatch through bash guard."
        stdin_text = _e1_preToolUse_json(
            the_prompt, tool_use_id="toolu_deny7", session_id=owner_session
        )
        result = _run_bash(_GUARD_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"bash guard deny-path must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", "bash guard must produce deny JSON for unregistered prompt"
        payload = json.loads(output)
        decision = payload["hookSpecificOutput"]["permissionDecision"]
        assert decision == "deny", f"bash guard must deny; got {decision!r}"

        # The deny-ledger file must now exist in the SCOPED state dir with one
        # unacked entry for this tool_use_id.
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        assert ledger_path.exists(), (
            "the bash guard deny path must create lazy-deny-ledger.jsonl in the "
            "scoped state dir"
        )
        lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        assert len(lines) == 1, f"exactly one ledger entry expected, got {len(lines)}"
        entry = json.loads(lines[0])
        assert entry["tool_use_id"] == "toolu_deny7", entry
        assert entry["acked"] is False, entry
        assert len(entry["denied_sha12"]) == 12, entry


# ---------------------------------------------------------------------------
# Phase 8 — inject is non-destructive against a marker bound to another session
# ---------------------------------------------------------------------------

def test_inject_non_owner_session_leaves_marker_intact():
    """Phase 8 WU-8.1: the REAL bash lazy-route-inject.sh, fired with a hook-input
    session_id DIFFERENT from the marker's bound session_id, must:
      - exit 0,
      - inject nothing (no LAZY-ROUTE banner / empty stdout),
      - AND leave the marker file on disk (non-destructive path B).

    This is the concurrent-session safety guarantee at the hook level: an
    interactive session firing the inject hook during a live marked run must not
    disarm the owning run.
    """
    _guard()
    assert _INJECT_SH.exists(), f"lazy-route-inject.sh missing: {_INJECT_SH}"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        fixture_repo = _build_fixture_repo(td_path)
        env = _base_env(state_dir)

        owner_session = str(uuid.uuid4())
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
                session_id=owner_session,  # bound to the OWNER
            )
        finally:
            _clear_state_dir()

        marker_path = state_dir / "lazy-run-marker.json"
        assert marker_path.exists(), "pre-condition: marker must exist"

        # Fire the inject hook from a DIFFERENT (non-owner) session.
        other_session = str(uuid.uuid4())
        stdin_text = _userPromptSubmit_json(session_id=other_session)
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject must exit 0 for a non-owner session; stderr: {result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"inject must produce NO banner for a non-owner session; "
            f"got: {result.stdout!r}"
        )
        # The marker must SURVIVE (Phase 8 non-destructive path B).
        assert marker_path.exists(), (
            "Phase 8 WU-8.1: a non-owner inject firing must LEAVE the marker on "
            "disk so the owning run stays armed"
        )
        # And the owner still reads it.
        _set_state_dir(state_dir)
        try:
            owner_marker = lazy_core.read_run_marker(session_id=owner_session)
        finally:
            _clear_state_dir()
        assert owner_marker is not None and owner_marker.get("session_id") == owner_session, (
            "owner session must still read the marker after a non-owner inject firing"
        )


# ---------------------------------------------------------------------------
# F1b (lazy-pipeline-ergonomics Phase 1) — pure-suffix auto-readmit via the real
# bash lazy-dispatch-guard.sh hook path (the Phase 1 MVB).
# ---------------------------------------------------------------------------

def test_guard_bash_pure_suffix_auto_readmits():
    """Phase 1 MVB through the REAL bash hook: a dispatch whose prompt = a
    registered cycle prompt + a trailing ORCHESTRATOR NOTE suffix is ALLOWED via
    auto-readmit (nonce consumed, `auto_readmit: true` ledger event), while the
    same prompt with a word changed mid-body is DENIED with the F1a corrective
    reason naming `--context` and `--emit-dispatch`."""
    _guard()
    assert _GUARD_SH.exists(), f"lazy-dispatch-guard.sh missing: {_GUARD_SH}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Bind the marker to one owning session and pass it on every call so the
        # guard's bind-on-allow doesn't reclassify the call as a non-owner.
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        base = "Run the next cycle step exactly as specified by the probe."
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(base, cls="cycle", item_id="feat-c")
        finally:
            _clear_state_dir()
        nonce = entry["nonce"]

        # --- pure-suffix superset → auto-readmit (allow) ---
        suffixed = base + "\n\nORCHESTRATOR NOTE: keep going, do not stop."
        stdin_allow = _e1_preToolUse_json(
            suffixed, tool_use_id="toolu_suffix", session_id=owner_session,
        )
        r_allow = _run_bash(_GUARD_SH, stdin_allow, env)
        assert r_allow.returncode == 0, (
            f"bash guard must exit 0; stderr: {r_allow.stderr!r}"
        )
        out_allow = r_allow.stdout.strip()
        assert out_allow != "", "auto-readmit must produce allow JSON via the bash hook"
        p_allow = json.loads(out_allow)
        assert p_allow["hookSpecificOutput"]["permissionDecision"] == "allow", (
            f"a pure-suffix cycle prompt must auto-readmit (allow) through the bash "
            f"hook; got {p_allow['hookSpecificOutput'].get('permissionDecision')!r}"
        )

        # The nonce must be consumed and an auto_readmit event written.
        _set_state_dir(state_dir)
        try:
            assert lazy_core.lookup_emission(base) is None, (
                "auto-readmit must consume the matched nonce"
            )
        finally:
            _clear_state_dir()
        registry = json.loads(
            (state_dir / "lazy-prompt-registry.json").read_text(encoding="utf-8")
        )
        match = [e for e in registry["entries"] if e.get("nonce") == nonce]
        assert match and match[0].get("consumed") is True, "entry must be consumed"

        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        assert ledger_path.exists(), "auto-readmit must write an auditable ledger event"
        events = [json.loads(ln) for ln in
                  ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        auto = [e for e in events if e.get("auto_readmit") is True]
        assert len(auto) == 1, f"exactly one auto_readmit event expected; got {events!r}"
        assert auto[0].get("tool_use_id") == "toolu_suffix", auto[0]

        # --- in-body edit → DENY with the F1a corrective reason ---
        edited = base.replace("exactly", "approximately")
        stdin_deny = _e1_preToolUse_json(
            edited, tool_use_id="toolu_edit", session_id=owner_session,
        )
        r_deny = _run_bash(_GUARD_SH, stdin_deny, env)
        assert r_deny.returncode == 0, r_deny.stderr
        p_deny = json.loads(r_deny.stdout.strip())
        assert p_deny["hookSpecificOutput"]["permissionDecision"] == "deny", (
            "an in-body edit must still DENY (not a pure suffix)"
        )
        reason = p_deny["hookSpecificOutput"]["permissionDecisionReason"]
        for needle in ("--context KEY=VALUE", "--emit-dispatch <class>", "verbatim"):
            assert needle in reason, (
                f"F1a deny reason must contain {needle!r}; got {reason!r}"
            )


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 2 (lazy-validation-readiness) — F2b + F2c guard integration tests
# ---------------------------------------------------------------------------

def test_f2b_emdash_slip_allows_via_guard():
    """F2b end-to-end (lazy-validation-readiness Phase 2): an em-dash typo on a
    freshly-registered prompt must ALLOW through the guard (sha matches after leg-5
    folding).  Confirms F2b is wired end-to-end from normalize → prompt_sha256 →
    lookup_emission → guard ALLOW.

    RED: normalize_prompt_for_hash lacks leg 5 — em-dash sha != hyphen sha → deny.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        # Register the HYPHEN form (the script-emitted baseline).
        hyphen_prompt = "Run the next step - implementation phase as specified."
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(hyphen_prompt, cls="cycle", item_id="feat-f2b")
        finally:
            _clear_state_dir()

        # Dispatch the EM-DASH form (the orchestrator's transcription slip).
        em_prompt = "Run the next step — implementation phase as specified."  # U+2014
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(em_prompt, tool_use_id=tool_use_id,
                                         session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", (
            "guard must produce JSON for an em-dash slip on a registered prompt"
        )
        payload = json.loads(output)
        decision = payload["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow", (
            f"em-dash slip on a registered prompt must ALLOW via F2b hash-folding; "
            f"got {decision!r}.  F2b leg 5 is not yet wired into normalize_prompt_for_hash."
        )


def test_f2c_near_copy_slip_deny_no_ledger_append():
    """F2c (lazy-validation-readiness Phase 2): a near-copy of a registered prompt
    that F2b does NOT fold (one word changed) → deny via the transcription-slip path,
    which must NOT append to the deny-ledger (no hardening debt for a slip).

    The deny reason must NOT contain '--emit-dispatch hardening'.

    RED: find_transcription_slip_entry / _deny_no_ledger do not exist yet —
    the deny falls through to _deny_and_ledger, writing a ledger entry.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        # Register the verbatim prompt.  Must be long enough (>= ~267 chars) so that
        # changing one word ('criteria' → 'CRITERIA', 8 chars) keeps difflib ratio
        # >= 0.97 (the F2c slip threshold).  ratio = (n-8)/n; need n >= 267.
        original_prompt = (
            "Run the next dispatch cycle step exactly as specified in the feature "
            "implementation plan. Execute all planned tasks in order, verify each "
            "deliverable against the acceptance criteria, record the observed "
            "behavior in your response output section, and note any deviations "
            "from the expected outcome in your analysis."
        )
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(original_prompt, cls="cycle", item_id="feat-slip")
        finally:
            _clear_state_dir()

        # Count ledger lines before the guard call.
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        lines_before = (
            len([l for l in ledger_path.read_text(encoding="utf-8").splitlines()
                 if l.strip()])
            if ledger_path.exists() else 0
        )

        # Dispatch a near-copy: 'criteria' → 'CRITERIA' — high similarity ratio
        # but NOT a hash-fold match (F2b folds dashes/quotes/NBSP, not case changes).
        # F2c slip-check should catch it and route to the cheap no-ledger deny.
        near_copy = (
            "Run the next dispatch cycle step exactly as specified in the feature "
            "implementation plan. Execute all planned tasks in order, verify each "
            "deliverable against the acceptance CRITERIA, record the observed "
            "behavior in your response output section, and note any deviations "
            "from the expected outcome in your analysis."
        )
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(near_copy, tool_use_id=tool_use_id,
                                          session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output != "", "guard must produce deny JSON for a near-copy slip"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"near-copy slip must be denied (F2c: cheap deny, no ledger); "
            f"got {hso.get('permissionDecision')!r}"
        )
        # The reason must NOT contain '--emit-dispatch hardening' — this is a cheap slip deny.
        reason = hso.get("permissionDecisionReason", "")
        assert "--emit-dispatch hardening" not in reason, (
            f"F2c transcription-slip deny reason must NOT contain '--emit-dispatch hardening'; "
            f"got: {reason!r}"
        )
        # The deny-ledger must NOT be appended (no debt for a transcription slip).
        lines_after = (
            len([l for l in ledger_path.read_text(encoding="utf-8").splitlines()
                 if l.strip()])
            if ledger_path.exists() else 0
        )
        assert lines_after == lines_before, (
            f"F2c transcription-slip deny must NOT append to the deny-ledger "
            f"(before={lines_before}, after={lines_after}); a slip is NOT hardening debt"
        )


def test_f2c_genuinely_unregistered_deny_appends_ledger():
    """F2c (lazy-validation-readiness Phase 2): a genuinely unregistered / totally
    different prompt (no close match in the registry) must use the FULL corrective
    deny path — deny-ledger IS appended (+1 line) and the reason contains the
    hardening recipe (debt is preserved for real gaps).

    RED: find_transcription_slip_entry / _deny_no_ledger do not exist yet — but
    once F2c lands the ledger-append behavior for the GENUINE no-match case must
    remain exactly as before.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        # Register a prompt (so the registry is non-empty, but we'll send a different one).
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(
                "Run the next dispatch cycle step as specified.",
                cls="cycle", item_id="feat-genuine",
            )
        finally:
            _clear_state_dir()

        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        lines_before = (
            len([l for l in ledger_path.read_text(encoding="utf-8").splitlines()
                 if l.strip()])
            if ledger_path.exists() else 0
        )

        # A totally different / hand-composed prompt — no close registered match.
        genuinely_different = (
            "This is a completely hand-composed prompt about a different topic entirely "
            "and has nothing whatsoever to do with any registered emission in the system."
        )
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(genuinely_different, tool_use_id=tool_use_id,
                                          session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output != "", "guard must produce deny JSON for genuinely unregistered prompt"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"genuinely unregistered prompt must be denied; "
            f"got {hso.get('permissionDecision')!r}"
        )
        # Reason MUST contain '--emit-dispatch hardening' (the corrective recipe is preserved).
        reason = hso.get("permissionDecisionReason", "")
        assert "--emit-dispatch hardening" in reason, (
            f"genuine no-match deny reason must contain '--emit-dispatch hardening' "
            f"(debt is preserved for real gaps); got: {reason!r}"
        )
        # Ledger MUST be appended (+1 entry — debt for a genuine gap).
        lines_after = (
            len([l for l in ledger_path.read_text(encoding="utf-8").splitlines()
                 if l.strip()])
            if ledger_path.exists() else 0
        )
        assert lines_after == lines_before + 1, (
            f"genuine no-match deny MUST append to the deny-ledger "
            f"(before={lines_before}, after={lines_after}); "
            f"real harness gaps still create hardening debt"
        )


# ---------------------------------------------------------------------------
# Phase 3 (lazy-validation-readiness) — F2a dispatch-by-reference guard tests
# ---------------------------------------------------------------------------

def test_f2a_guard_ref_fresh_allows_with_updated_input():
    """F2a (guard): a '@@lazy-ref nonce=<hex>' prompt for a FRESH registered entry
    returns an ALLOW JSON with hookSpecificOutput.updatedInput.prompt == the
    registered raw prompt bytes; other tool_input fields (model, subagent_type,
    description) are preserved; nonce is consumed afterward; a
    dispatch_by_reference audit event is written to the ledger.

    RED until _allow_with_updated_input and the reference branch are implemented.
    """
    _guard()

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)

        # Register a real prompt via lazy_core.
        raw_prompt = (
            "Execute Phase 2 of the lazy-validation-readiness plan exactly as "
            "specified in the PHASES.md — F2a dispatch-by-reference implementation."
        )
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(raw_prompt, cls="cycle", item_id="feat-f2a")
        finally:
            _clear_state_dir()

        nonce = entry["nonce"]
        ref_token = f"@@lazy-ref nonce={nonce}"

        # Build the PreToolUse hook-input with extra tool_input fields to verify
        # they survive the updatedInput passthrough.
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        hook_input = {
            "session_id": owner_session,
            "transcript_path": f"C:\\test\\{owner_session}.jsonl",
            "cwd": "C:\\test",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {
                "description": "lazy-batch f2a test dispatch",
                "prompt": ref_token,
                "subagent_type": "general-purpose",
                "model": "claude-opus-4-5",
            },
            "tool_use_id": tool_use_id,
        }
        stdin_text = json.dumps(hook_input)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output, "guard must produce JSON for a fresh by-reference dispatch"
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard output must be valid JSON; got {output!r}; parse error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "allow", (
            f"by-reference fresh nonce must be ALLOWED; "
            f"got {hso.get('permissionDecision')!r}; "
            f"full output: {output!r}"
        )

        # The allow must carry updatedInput.
        updated = hso.get("updatedInput")
        assert updated is not None, (
            f"by-reference allow must carry hookSpecificOutput.updatedInput; "
            f"full output: {output!r}"
        )
        assert updated.get("prompt") == raw_prompt, (
            f"updatedInput.prompt must equal the registered raw prompt; "
            f"got {updated.get('prompt')!r}, expected {raw_prompt!r}"
        )
        # Verify other tool_input fields are preserved in updatedInput.
        assert updated.get("model") == "claude-opus-4-5", (
            f"updatedInput must preserve the 'model' field; got {updated!r}"
        )
        assert updated.get("subagent_type") == "general-purpose", (
            f"updatedInput must preserve 'subagent_type'; got {updated!r}"
        )
        assert updated.get("description") == "lazy-batch f2a test dispatch", (
            f"updatedInput must preserve 'description'; got {updated!r}"
        )

        # Nonce must be consumed.
        _set_state_dir(state_dir)
        try:
            registry_data = lazy_core._load_registry()  # type: ignore[attr-defined]
        finally:
            _clear_state_dir()
        entries = registry_data.get("entries", [])
        matched = [e for e in entries if e.get("nonce") == nonce]
        assert matched, f"Registry must still have the nonce entry; entries: {entries!r}"
        assert matched[0].get("consumed") is True, (
            f"Nonce must be consumed after a by-reference allow; "
            f"entry: {matched[0]!r}"
        )

        # Audit event must be written to deny-ledger.
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        assert ledger_path.exists(), (
            "By-reference dispatch must write an audit event to lazy-deny-ledger.jsonl"
        )
        lines = [
            ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        ref_events = [json.loads(ln) for ln in lines
                      if json.loads(ln).get("dispatch_by_reference")]
        assert ref_events, (
            "At least one 'dispatch_by_reference: true' event must be in the ledger"
        )
        evt = ref_events[-1]
        assert evt.get("acked") is True, (
            "dispatch_by_reference audit events must be pre-acked (no debt)"
        )


def test_f2a_guard_ref_consumed_nonce_denies():
    """F2a (guard): a reference to a CONSUMED nonce must result in a DENY
    (fall-through corrective path), never a spurious allow.

    RED until the reference branch is implemented.
    """
    _guard()

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)

        raw_prompt = "Execute the consumed-nonce deny test step."
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(raw_prompt, cls="cycle")
            nonce = entry["nonce"]
            # Consume the nonce before the guard call.
            lazy_core.consume_nonce(nonce, consumer="toolu_prior")
        finally:
            _clear_state_dir()

        ref_token = f"@@lazy-ref nonce={nonce}"
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(ref_token, tool_use_id=tool_use_id,
                                          session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output, "guard must produce JSON for a consumed-nonce reference"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"Reference to a consumed nonce must be DENIED; "
            f"got {hso.get('permissionDecision')!r}"
        )


def test_f2a_guard_ref_nonexistent_nonce_denies():
    """F2a (guard): a reference to a NONEXISTENT nonce must result in a DENY
    (never allows).

    RED until the reference branch is implemented.
    """
    _guard()

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)

        bogus_nonce = "cafebabe" * 4
        ref_token = f"@@lazy-ref nonce={bogus_nonce}"
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(ref_token, tool_use_id=tool_use_id,
                                          session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output, "guard must produce JSON for a nonexistent-nonce reference"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"Reference to a nonexistent nonce must be DENIED; "
            f"got {hso.get('permissionDecision')!r}"
        )


def test_f2a_guard_ref_stale_nonce_denies():
    """F2a (guard): a reference to a STALE nonce (emitted before run-start) must
    result in a DENY — the run-start gate applies to by-reference too.

    RED until the reference branch is implemented.
    """
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Register the prompt at old_time BEFORE writing the marker.
        old_time = _time.time() - 7200
        raw_prompt = "Execute the stale-nonce deny test step."
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(raw_prompt, cls="cycle", now=old_time)
            nonce = entry["nonce"]
        finally:
            _clear_state_dir()

        # Write the marker with a recent time (started_at > emitted_at).
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        ref_token = f"@@lazy-ref nonce={nonce}"
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(ref_token, tool_use_id=tool_use_id,
                                          session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output, "guard must produce JSON for a stale-nonce reference"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"Reference to a stale nonce must be DENIED; "
            f"got {hso.get('permissionDecision')!r}"
        )


def test_dc_guard_bare_ref_no_marker_denies_not_allows():
    """D-C (2026-06-16): a bare '@@lazy-ref nonce=<hex>' token dispatched while NO
    live run marker is present must DENY, NOT silently allow the literal token
    through to the subagent. Previously the marker-absent fast-path returned None
    (silent allow), so a subagent received the bare token and improvised an
    off-task run (this is the exact mechanism the D-B marker clobber triggered).
    The deny reason names the unresolved-by-reference defect and prescribes the
    verbatim dispatch_prompt."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)
        # NO run marker written → marker-absent path.
        bogus_nonce = "deadbeef" * 4
        ref_token = f"@@lazy-ref nonce={bogus_nonce}"
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(ref_token, tool_use_id=tool_use_id)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output, "guard must DENY (emit JSON) for a bare ref token with no marker"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", (
            f"bare @@lazy-ref with no live marker must be DENIED, not silently "
            f"allowed; got {hso.get('permissionDecision')!r}; output: {output!r}"
        )
        reason = hso.get("permissionDecisionReason", "").lower()
        assert "by-reference" in reason and "verbatim" in reason, (
            f"deny reason must name the unresolved-by-reference defect and "
            f"prescribe the verbatim prompt; got {reason!r}"
        )


def test_dc_guard_non_ref_no_marker_still_allows():
    """D-C regression guard: the D-C deny is SCOPED to bare ref tokens only — a
    normal (non-ref) prompt with no marker still gets the fast-path silent allow
    (exit 0, no deny). The bare-ref deny must not broaden into a general
    marker-absent deny."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)
        # A normal dispatch prompt, NOT a ref token, with no marker present.
        stdin_text = _e1_preToolUse_json("Implement Phase 3 of the plan verbatim.")
        result = _run_guard_py(stdin_text, env)
        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        # Marker-absent non-ref path is a silent allow → either no output, or an
        # explicit allow. Never a deny.
        if output:
            payload = json.loads(output)
            decision = payload.get("hookSpecificOutput", {}).get("permissionDecision")
            assert decision != "deny", (
                f"non-ref prompt with no marker must NOT be denied; got {decision!r}"
            )


def test_f2a_guard_ref_hardening_class_allows_and_acks():
    """F2a (guard): a by-reference dispatch of a HARDENING-class fresh nonce must
    ALLOW + consume + write updatedInput + ack the oldest hardening debt.

    The depth-1 cap still applies to the NORMAL path; a by-reference of a fresh
    hardening nonce is a legitimate first dispatch (safe path — carries no
    hand-composed body).

    RED until the reference branch is implemented.
    """
    _guard()

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)

        hardening_prompt = (
            "Harden the harness: diagnose the validate-deny gap and implement "
            "the mechanical fix. trigger_kind=validate-deny item_id=feat-f2a."
        )
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(hardening_prompt, cls="hardening",
                                                  item_id="feat-f2a")
            nonce = entry["nonce"]
            # Write one deny-ledger entry so there is debt to ack.
            lazy_core.append_deny_ledger_entry(
                tool_use_id="toolu_prior_deny",
                denied_sha12="aabbcc001122",
                reason_head="test prior deny",
                prompt_head="some prior prompt",
            )
            debt_before = lazy_core.pending_hardening()
        finally:
            _clear_state_dir()

        assert debt_before == 1, f"Expected 1 unit of hardening debt before dispatch; got {debt_before}"

        ref_token = f"@@lazy-ref nonce={nonce}"
        tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
        stdin_text = _e1_preToolUse_json(ref_token, tool_use_id=tool_use_id,
                                          session_id=owner_session)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, f"guard must exit 0; stderr: {result.stderr!r}"
        output = result.stdout.strip()
        assert output, "guard must produce JSON for a hardening by-reference dispatch"
        payload = json.loads(output)
        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "allow", (
            f"By-reference hardening fresh nonce must be ALLOWED; "
            f"got {hso.get('permissionDecision')!r}"
        )
        assert hso.get("updatedInput", {}).get("prompt") == hardening_prompt, (
            "updatedInput.prompt must be the registered hardening prompt"
        )

        # Hardening debt must be acked.
        _set_state_dir(state_dir)
        try:
            debt_after = lazy_core.pending_hardening()
        finally:
            _clear_state_dir()
        assert debt_after == 0, (
            f"Hardening debt must be acked after by-reference hardening allow; "
            f"got pending={debt_after}"
        )


def test_f2a_guard_ref_malformed_falls_through_to_normal_deny():
    """F2a (guard): a malformed '@@lazy-ref' token (no nonce, bad chars, etc.)
    must NOT crash — it must fall through to the normal deny path (treated as an
    unregistered prompt).

    Variants tested: bare '@@lazy-ref', '@@lazy-ref nonce=', invalid hex chars.

    RED until the reference branch is implemented (should be safe — fail-open).
    """
    _guard()

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)

        malformed_tokens = [
            "@@lazy-ref",                          # no nonce at all
            "@@lazy-ref nonce=",                   # empty nonce value
            "@@lazy-ref nonce=GGGG",               # invalid hex chars
            "@@lazy-ref nonce=abc xyz",            # extra whitespace / trailing word
        ]

        for token in malformed_tokens:
            tool_use_id = "toolu_" + uuid.uuid4().hex[:24]
            stdin_text = _e1_preToolUse_json(token, tool_use_id=tool_use_id,
                                              session_id=owner_session)
            result = _run_guard_py(stdin_text, env)

            assert result.returncode == 0, (
                f"guard must exit 0 for malformed ref {token!r}; "
                f"stderr: {result.stderr!r}"
            )
            output = result.stdout.strip()
            # Must produce SOME output (a deny JSON) — must not crash/be silent.
            assert output, (
                f"guard must produce deny JSON for malformed ref {token!r}; "
                f"got empty output"
            )
            try:
                payload = json.loads(output)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"guard output must be valid JSON for malformed ref {token!r}; "
                    f"got {output!r}; error: {exc}"
                ) from exc
            # Must be a deny (normal path — not registered).
            hso = payload.get("hookSpecificOutput", {})
            assert hso.get("permissionDecision") == "deny", (
                f"Malformed ref {token!r} must fall through to deny; "
                f"got {hso.get('permissionDecision')!r}"
            )


# ---------------------------------------------------------------------------
# Phase 7 (lazy-validation-readiness) — meta dispatch-by-reference via --emit-dispatch
# ---------------------------------------------------------------------------
# Deliverable 3: --emit-dispatch registers a meta prompt and exposes the nonce
# as dispatch_prompt_ref.  The guard's existing @@lazy-ref path (Phase 3) must
# resolve it via updatedInput.  This test proves the full round-trip without
# touching lazy_guard.py — it reuses the existing guard code path that Phase 3
# already certified.
# ---------------------------------------------------------------------------

def test_p7_meta_dispatch_by_reference_via_guard():
    """A META-class entry (e.g. 'apply-resolution') registered via the same
    path --emit-dispatch uses (register_emission) can be dispatched by reference
    via '@@lazy-ref nonce=<hex>' and the guard resolves it to the registered
    prompt bytes via updatedInput.

    Proves:
      - The guard's existing @@lazy-ref resolution works for any registered class
        (not only 'cycle' — meta classes registered by --emit-dispatch are also
         resolvable by reference).
      - permissionDecision == 'allow'
      - hookSpecificOutput.updatedInput.prompt == the registered raw prompt text
      - nonce is consumed after the allow

    RED until the guard's Phase 3 reference path is proven to resolve meta-class
    entries; a green run here confirms no lazy_guard.py change is needed.
    """
    _guard()

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)

        # Register a META-class prompt directly via lazy_core (same path
        # --emit-dispatch uses via register_emission_if_marked → register_emission).
        meta_prompt = (
            "Apply the resolution documented in BLOCKED.md for feature feat-meta:\n"
            "1. Add the missing Rust wiring to context.rs\n"
            "2. Run `npm run qg` to confirm green\n"
            "3. Commit the changes and mark the phase complete"
        )
        _set_state_dir(state_dir)
        try:
            entry = lazy_core.register_emission(
                meta_prompt, cls="apply-resolution", item_id="feat-meta"
            )
        finally:
            _clear_state_dir()

        nonce = entry["nonce"]
        ref_token = f"@@lazy-ref nonce={nonce}"

        # Build the guard hook-input with the meta dispatch reference token.
        tool_use_id = "toolu_meta_" + uuid.uuid4().hex[:20]
        hook_input = {
            "session_id": owner_session,
            "transcript_path": f"C:\\test\\{owner_session}.jsonl",
            "cwd": "C:\\test",
            "permission_mode": "default",
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_input": {
                "description": "meta dispatch: apply-resolution for feat-meta",
                "prompt": ref_token,
                "subagent_type": "general-purpose",
                "model": "claude-opus-4-5",
            },
            "tool_use_id": tool_use_id,
        }
        stdin_text = json.dumps(hook_input)
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0 for meta @@lazy-ref dispatch; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output, "guard must produce JSON for a meta by-reference dispatch"
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"guard output must be valid JSON for meta ref; got {output!r}; error: {exc}"
            ) from exc

        hso = payload.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "allow", (
            f"meta by-reference dispatch must be ALLOWED; "
            f"got {hso.get('permissionDecision')!r}; full output: {output!r}"
        )

        # The allow must carry updatedInput with the resolved meta prompt.
        updated = hso.get("updatedInput")
        assert updated is not None, (
            f"meta by-reference allow must carry hookSpecificOutput.updatedInput; "
            f"got: {hso!r}"
        )
        assert updated.get("prompt") == meta_prompt, (
            f"updatedInput.prompt must equal the registered meta prompt bytes; "
            f"got {updated.get('prompt')!r}"
        )

        # The nonce must be consumed (single-use).
        _set_state_dir(state_dir)
        try:
            resolved_after = lazy_core.resolve_emission_by_nonce(nonce)
        finally:
            _clear_state_dir()
        assert resolved_after is None, (
            f"nonce must be consumed after meta dispatch-by-reference allow; "
            f"got {resolved_after!r}"
        )


# ===========================================================================
# Phase 4 (lazy-cycle-containment C2) — PreToolUse containment hook tests.
#
# Drives user/hooks/lazy-cycle-containment.sh with crafted PreToolUse JSON
# payloads + a tmp LAZY_STATE_DIR.  The hook's contract:
#   - fast-path ALLOW (exit 0, no stdout) when the cycle marker is ABSENT
#   - while the marker is present, DENY (permissionDecision: deny + corrective
#     reason) loop-formation / lifecycle / recursive-dispatch / 2nd-feature
#     commit / over-ceiling commit; ALLOW the narrow ops + same-feature commit
#   - fail-OPEN (ALLOW + breadcrumb) on malformed input
#
# The 2nd-feature commit tripwire shells `git diff --cached --name-only`; for
# hermetic tests the hook honors a LAZY_CYCLE_STAGED_PATHS env override
# (newline-separated staged paths) so no temp git repo is required.
# ===========================================================================

_CONTAINMENT_SH = _HOOKS_DIR / "lazy-cycle-containment.sh"

# A synthetic subagent identifier — its mere PRESENCE in a PreToolUse payload
# marks the call as coming from within a dispatched subagent (D4 trip).
_SUBAGENT_AGENT_ID = "agent_" + uuid.uuid4().hex[:16]


def _bash_preToolUse_json(
    command: str,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Return a PreToolUse JSON payload for a Bash tool call.

    agent_id: when provided, marks the payload as a SUBAGENT call (the field
    Claude Code injects only when the hook fires from within a subagent —
    confirmed against the installed version's hook-input schema). Absent ⇒
    main-thread orchestrator call.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return json.dumps(payload)


def _agent_preToolUse_json(
    session_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    """Return a PreToolUse JSON payload for an Agent tool call.

    agent_id: when provided, marks the payload as a SUBAGENT call (recursive
    dispatch from within an already-dispatched cycle subagent). Absent ⇒ the
    main-thread orchestrator's own legitimate Agent dispatch.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {
            "description": "recursive dispatch",
            "prompt": "do a thing",
            "subagent_type": "general-purpose",
        },
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return json.dumps(payload)


def _write_cycle_marker_in_dir(
    state_dir: Path,
    feature_id: str = "feat-A",
    commit_tally: int = 0,
) -> None:
    """Write a cycle-subagent marker into *state_dir* via lazy_core, optionally
    overriding commit_tally (lazy_core always writes 0; tests that exercise the
    ceiling patch the value on disk after writing)."""
    _set_state_dir(state_dir)
    try:
        lazy_core.write_cycle_marker(feature_id, "deadbeef", now=time.time())
    finally:
        _clear_state_dir()
    if commit_tally != 0:
        marker_path = state_dir / "lazy-cycle-active.json"
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        data["commit_tally"] = commit_tally
        marker_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _run_containment(
    stdin_text: str, state_dir: Path, staged_paths: list[str] | None = None
) -> subprocess.CompletedProcess:
    """Run the containment hook with stdin_text + a tmp state dir.  When
    staged_paths is provided, set LAZY_CYCLE_STAGED_PATHS so the 2nd-feature
    tripwire reads the fixture instead of real `git diff --cached`."""
    env = _base_env(state_dir)
    if staged_paths is not None:
        env["LAZY_CYCLE_STAGED_PATHS"] = "\n".join(staged_paths)
    return _run_bash(_CONTAINMENT_SH, stdin_text, env)


def _containment_decision(result: subprocess.CompletedProcess) -> str | None:
    """Extract permissionDecision from the hook's stdout, or None if no JSON /
    empty stdout (fast-path allow)."""
    out = result.stdout.strip()
    if not out:
        return None
    payload = json.loads(out)
    return payload.get("hookSpecificOutput", {}).get("permissionDecision")


def test_containment_hook_file_exists():
    """The containment hook script must exist on disk."""
    assert _CONTAINMENT_SH.exists(), (
        f"lazy-cycle-containment.sh missing — Phase 4 not implemented: {_CONTAINMENT_SH}"
    )


def test_containment_fast_path_no_marker_allows():
    """Marker ABSENT + any Bash payload → fast-path ALLOW (exit 0, no deny)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(
            _bash_preToolUse_json("python3 lazy-state.py --probe"), state_dir
        )
        assert result.returncode == 0, (
            f"fast-path must exit 0; got {result.returncode}; stderr: {result.stderr!r}"
        )
        assert _containment_decision(result) != "deny", (
            f"fast-path (no marker) must NOT deny; stdout: {result.stdout!r}"
        )


def test_containment_denies_next_route_probe():
    """Subagent (agent_id) + marker + `lazy-state.py --probe` → deny + corrective
    reason.  (D4: the routing deny now keys on agent_id; a live cycle subagent
    carries both the marker and agent_id, so this exercises that real path.)"""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        result = _run_containment(
            _bash_preToolUse_json(
                "python3 ~/.claude/scripts/lazy-state.py --probe",
                agent_id=_SUBAGENT_AGENT_ID,
            ),
            state_dir,
        )
        assert result.returncode == 0
        assert _containment_decision(result) == "deny", (
            f"--probe under marker must deny; stdout: {result.stdout!r}"
        )
        payload = json.loads(result.stdout.strip())
        reason = payload["hookSpecificOutput"].get("permissionDecisionReason", "")
        assert "orchestrator" in reason.lower() or "stop" in reason.lower(), (
            f"deny reason must be corrective; got {reason!r}"
        )


def test_containment_denies_loop_formation_flags():
    """Each loop-formation flag from a subagent (agent_id) under the marker →
    deny.  (D4: routing deny keys on agent_id.)"""
    _guard()
    flags = [
        "--emit-prompt", "--repeat-count", "--repeat-count-peek",
        "--run-start", "--run-end", "--apply-pseudo",
        "--enqueue-adhoc", "--emit-dispatch",
    ]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        for flag in flags:
            result = _run_containment(
                _bash_preToolUse_json(
                    f"python3 lazy-state.py {flag}", agent_id=_SUBAGENT_AGENT_ID
                ),
                state_dir,
            )
            assert _containment_decision(result) == "deny", (
                f"loop-formation flag {flag!r} under marker must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_denies_lifecycle_commands():
    """Runtime-lifecycle commands from a subagent (agent_id) under the marker →
    deny.  (D4: lifecycle deny keys on agent_id.)"""
    _guard()
    cmds = [
        "npm run dev:kill", "npm run dev:restart",
        "dev:kill", "dev:restart",
        "kill-port 3333", "kill-port 1420",
    ]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        for cmd in cmds:
            result = _run_containment(
                _bash_preToolUse_json(cmd, agent_id=_SUBAGENT_AGENT_ID), state_dir
            )
            assert _containment_decision(result) == "deny", (
                f"lifecycle command {cmd!r} under marker must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_allows_narrow_ops():
    """Allow-listed ops (--neutralize-sentinel, --verify-ledger) → ALLOW."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        for cmd in (
            "python3 lazy-state.py --neutralize-sentinel docs/features/x/BLOCKED.md",
            "python3 lazy-state.py --verify-ledger docs/features/x/SPEC.md",
        ):
            result = _run_containment(_bash_preToolUse_json(cmd), state_dir)
            assert _containment_decision(result) != "deny", (
                f"allow-listed op {cmd!r} must NOT deny; stdout: {result.stdout!r}"
            )


def test_containment_allows_unrelated_bash():
    """An unrelated Bash command under the marker (the subagent's real work,
    e.g. running tests) → ALLOW."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        result = _run_containment(
            _bash_preToolUse_json("python3 -m pytest user/scripts/test_hooks.py"),
            state_dir,
        )
        assert _containment_decision(result) != "deny", (
            f"unrelated Bash under marker must NOT deny; stdout: {result.stdout!r}"
        )


def test_containment_allows_recursive_agent_dispatch():
    """A recursive Agent tool call from a subagent (agent_id) while the marker is
    present → ALLOW.  (2026-07-09: the harness allows nested dispatch; the blanket
    recursion deny broke mandated read-only Explore fan-outs — see
    docs/bugs/adhoc-containment-denies-mandated-explore-fanout. Regression guard:
    re-introducing the deny fails this test.)"""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        result = _run_containment(
            _agent_preToolUse_json(agent_id=_SUBAGENT_AGENT_ID), state_dir
        )
        assert _containment_decision(result) != "deny", (
            f"subagent Agent dispatch must NOT deny (removed 2026-07-09); "
            f"stdout: {result.stdout!r}"
        )


def test_containment_denies_second_feature_commit():
    """A `git commit` staging a DIFFERENT feature dir than the marker's
    feature_id → deny (staged-path fixture)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir, feature_id="feat-A")
        result = _run_containment(
            _bash_preToolUse_json("git commit -m 'work'"),
            state_dir,
            staged_paths=["docs/features/feat-B/SPEC.md"],
        )
        assert _containment_decision(result) == "deny", (
            f"2nd-feature commit must deny; stdout: {result.stdout!r}"
        )


def test_containment_allows_same_feature_commit():
    """A `git commit` staging only the marker's own feature dir → ALLOW."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir, feature_id="feat-A")
        result = _run_containment(
            _bash_preToolUse_json("git commit -m 'work'"),
            state_dir,
            staged_paths=["docs/features/feat-A/SPEC.md",
                          "docs/features/feat-A/PHASES.md"],
        )
        assert _containment_decision(result) != "deny", (
            f"same-feature commit must NOT deny; stdout: {result.stdout!r}"
        )


def test_containment_allows_carve_out_commit():
    """A `git commit` staging only carve-out shared roots (queue.json,
    ROADMAP.md, repo-root CLAUDE.md) → ALLOW even though they are not under the
    feature dir."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir, feature_id="feat-A")
        result = _run_containment(
            _bash_preToolUse_json("git commit -m 'roadmap'"),
            state_dir,
            staged_paths=["docs/features/queue.json",
                          "docs/features/ROADMAP.md",
                          "CLAUDE.md"],
        )
        assert _containment_decision(result) != "deny", (
            f"carve-out commit must NOT deny; stdout: {result.stdout!r}"
        )


def test_containment_increments_commit_tally_on_allow():
    """An ALLOWED same-feature `git commit` increments commit_tally in the
    marker (read-modify-write)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir, feature_id="feat-A")
        marker_path = state_dir / "lazy-cycle-active.json"
        before = json.loads(marker_path.read_text(encoding="utf-8"))["commit_tally"]
        _run_containment(
            _bash_preToolUse_json("git commit -m 'work'"),
            state_dir,
            staged_paths=["docs/features/feat-A/SPEC.md"],
        )
        after = json.loads(marker_path.read_text(encoding="utf-8"))["commit_tally"]
        assert after == before + 1, (
            f"commit_tally must increment on allowed commit; {before} → {after}"
        )


def test_containment_commit_count_backstop_denies():
    """A `git commit` when commit_tally is already at the ceiling (25) → deny."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir, feature_id="feat-A", commit_tally=25)
        result = _run_containment(
            _bash_preToolUse_json("git commit -m 'too many'"),
            state_dir,
            staged_paths=["docs/features/feat-A/SPEC.md"],
        )
        assert _containment_decision(result) == "deny", (
            f"commit at/over ceiling must deny; stdout: {result.stdout!r}"
        )


def test_containment_fail_open_on_malformed_json():
    """Malformed PreToolUse JSON with the marker present → ALLOW (fail-OPEN) +
    a breadcrumb; never a wedge."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        result = _run_containment("{ this is not valid json", state_dir)
        assert result.returncode == 0, (
            f"fail-open must exit 0; got {result.returncode}; stderr: {result.stderr!r}"
        )
        assert _containment_decision(result) != "deny", (
            f"malformed input must NOT deny (fail-open); stdout: {result.stdout!r}"
        )
        breadcrumb = state_dir / "hook-error.json"
        assert breadcrumb.exists(), (
            "fail-open must write a hook-error.json breadcrumb"
        )


# ===========================================================================
# hardening-blind-to-process-friction Phase 1 (D4) — agent_id-targeted
# containment.  The recursion/lifecycle/routing deny logic no longer depends on
# the orchestrator arming a cycle marker; it trips whenever the PreToolUse
# payload carries `agent_id` (the field Claude Code injects ONLY when the hook
# fires from within a subagent — confirmed against the installed version's
# hook-input schema: `agent_id?: "Subagent identifier. Present only when the
# hook fires from within a subagent ... Absent for the main thread"`).
#
#   - agent_id PRESENT  (subagent) → deny /lazy-batch invocation, /lazy* Skill
#     calls, lazy-state/bug-state routing+lifecycle flags, dev:kill/restart
#     — REGARDLESS of whether a cycle marker is present (arming-free).
#     Recursive Agent/Task dispatch is NO LONGER denied (removed 2026-07-09 —
#     harness-legal nested dispatch, needed for mandated Explore fan-outs; see
#     docs/bugs/adhoc-containment-denies-mandated-explore-fanout).
#   - agent_id ABSENT   (main-thread orchestrator) → allow all of the above; the
#     orchestrator is never self-denied.
#
# The marker-gated 2nd-feature tripwire + commit-ceiling backstop are retained
# unchanged (they read feature_id/commit_tally from the marker).
# ===========================================================================


def test_containment_agentid_present_allows_recursive_agent_no_marker():
    """SUBAGENT-shaped payload (agent_id present) + recursive Agent call, with
    NO cycle marker → ALLOW (recursion deny removed 2026-07-09 — nested dispatch
    is harness-legal and needed for mandated Explore fan-outs)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(
            _agent_preToolUse_json(agent_id=_SUBAGENT_AGENT_ID), state_dir
        )
        assert result.returncode == 0, (
            f"hook must exit 0; got {result.returncode}; stderr: {result.stderr!r}"
        )
        assert _containment_decision(result) != "deny", (
            f"subagent Agent dispatch (agent_id present, no marker) must NOT deny; "
            f"stdout: {result.stdout!r}"
        )


def test_containment_agentid_absent_allows_main_thread_agent_no_marker():
    """MAIN-THREAD payload (agent_id absent) + Agent call, NO marker → allow.
    The orchestrator's own legitimate cycle dispatch must never be self-denied
    (the Proven-Finding-#3 defect)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(_agent_preToolUse_json(), state_dir)
        assert result.returncode == 0
        assert _containment_decision(result) != "deny", (
            f"main-thread Agent dispatch (agent_id absent) must NOT deny; "
            f"stdout: {result.stdout!r}"
        )


def test_containment_agentid_present_allows_recursive_agent_with_marker():
    """SUBAGENT payload + Agent call WITH a marker present → ALLOW (recursion
    deny removed 2026-07-09; the marker-gated tripwires are Bash-only and do not
    consult Agent calls)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _write_cycle_marker_in_dir(state_dir)
        result = _run_containment(
            _agent_preToolUse_json(agent_id=_SUBAGENT_AGENT_ID), state_dir
        )
        assert _containment_decision(result) != "deny", (
            f"subagent Agent dispatch (agent_id present, marker present) must NOT "
            f"deny; stdout: {result.stdout!r}"
        )


def test_containment_agentid_present_denies_lazy_batch_invocation():
    """SUBAGENT payload invoking /lazy-batch in a Bash command, NO marker →
    deny (recursive batch is the literal runaway path)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for cmd in ("claude -p '/lazy-batch 25'", "/lazy-batch 10"):
            result = _run_containment(
                _bash_preToolUse_json(cmd, agent_id=_SUBAGENT_AGENT_ID), state_dir
            )
            assert _containment_decision(result) == "deny", (
                f"subagent /lazy-batch invocation {cmd!r} must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_agentid_present_allows_lazy_batch_path_reference():
    """SUBAGENT payload whose Bash command merely REFERENCES a lazy-batch* skill
    file path (cat/grep/ls/git add) must ALLOW — the false-positive that recurred
    8x in claude-config (docs/bugs/adhoc-incident-hook-deny-4b767b). RED against
    the current unanchored _LAZY_BATCH_RE (benign `cat` denies today)."""
    _guard()
    benign = (
        "cat user/skills/lazy-batch/SKILL.md",
        "cat ~/.claude/skills/lazy-batch/SKILL.md",
        "grep -rn foo repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
        "ls user/skills/lazy-bug-batch/",
        "git add user/skills/lazy-batch/SKILL.md",
    )
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for cmd in benign:
            result = _run_containment(
                _bash_preToolUse_json(cmd, agent_id=_SUBAGENT_AGENT_ID), state_dir
            )
            assert _containment_decision(result) != "deny", (
                f"subagent benign lazy-batch path reference {cmd!r} must NOT deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_agentid_present_denies_lazy_batch_invocation_extra_forms():
    """SUBAGENT payload actually INVOKING a nested batch orchestrator (chained,
    bug-batch, or a headless `claude -p` spawn) must still DENY — the anchored
    pair must preserve every real-runaway form."""
    _guard()
    runaway = (
        "cd foo && /lazy-batch",
        "/lazy-bug-batch 10",
        "claude --dangerously-skip-permissions -p '/lazy-bug-batch 10'",
    )
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for cmd in runaway:
            result = _run_containment(
                _bash_preToolUse_json(cmd, agent_id=_SUBAGENT_AGENT_ID), state_dir
            )
            assert _containment_decision(result) == "deny", (
                f"subagent nested batch invocation {cmd!r} must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_agentid_absent_allows_lazy_batch_invocation():
    """MAIN-THREAD payload (agent_id absent) invoking /lazy-batch → allow (the
    orchestrator may invoke the batch)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(
            _bash_preToolUse_json("claude -p '/lazy-batch 25'"), state_dir
        )
        assert _containment_decision(result) != "deny", (
            f"main-thread /lazy-batch invocation must NOT deny; "
            f"stdout: {result.stdout!r}"
        )


def test_containment_agentid_present_denies_routing_flags_no_marker():
    """SUBAGENT payload + each loop-formation routing flag, NO marker → deny."""
    _guard()
    flags = [
        "--probe", "--emit-prompt", "--repeat-count", "--run-start",
        "--run-end", "--apply-pseudo", "--enqueue-adhoc", "--emit-dispatch",
    ]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for flag in flags:
            result = _run_containment(
                _bash_preToolUse_json(
                    f"python3 lazy-state.py {flag}", agent_id=_SUBAGENT_AGENT_ID
                ),
                state_dir,
            )
            assert _containment_decision(result) == "deny", (
                f"subagent routing flag {flag!r} (no marker) must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_agentid_absent_allows_routing_flags_no_marker():
    """MAIN-THREAD payload + routing flags, NO marker → allow (the orchestrator
    runs these between cycles)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for flag in ("--run-end", "--emit-prompt", "--probe"):
            result = _run_containment(
                _bash_preToolUse_json(f"python3 lazy-state.py {flag}"), state_dir
            )
            assert _containment_decision(result) != "deny", (
                f"main-thread routing flag {flag!r} must NOT deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_agentid_present_denies_lifecycle_no_marker():
    """SUBAGENT payload + dev:kill / dev:restart, NO marker → deny."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for cmd in ("npm run dev:kill", "npm run dev:restart"):
            result = _run_containment(
                _bash_preToolUse_json(cmd, agent_id=_SUBAGENT_AGENT_ID), state_dir
            )
            assert _containment_decision(result) == "deny", (
                f"subagent lifecycle {cmd!r} (no marker) must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_agentid_absent_allows_lifecycle_no_marker():
    """MAIN-THREAD payload + dev:kill, NO marker → allow (the orchestrator owns
    the dev runtime)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(
            _bash_preToolUse_json("npm run dev:kill"), state_dir
        )
        assert _containment_decision(result) != "deny", (
            f"main-thread dev:kill must NOT deny; stdout: {result.stdout!r}"
        )


def test_containment_agentid_present_allows_unrelated_bash():
    """SUBAGENT payload + the subagent's REAL work (running tests) → allow.  The
    agent_id trip denies only recursion/lifecycle/routing, not ordinary work."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(
            _bash_preToolUse_json(
                "python3 -m pytest user/scripts/test_hooks.py",
                agent_id=_SUBAGENT_AGENT_ID,
            ),
            state_dir,
        )
        assert _containment_decision(result) != "deny", (
            f"subagent's real work (pytest) must NOT deny; stdout: {result.stdout!r}"
        )


def test_containment_agentid_present_allows_narrow_ops():
    """SUBAGENT payload + allow-listed state-script ops (--neutralize-sentinel,
    --verify-ledger) → allow even though agent_id is present."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for cmd in (
            "python3 lazy-state.py --neutralize-sentinel docs/features/x/BLOCKED.md",
            "python3 lazy-state.py --verify-ledger docs/features/x/SPEC.md",
        ):
            result = _run_containment(
                _bash_preToolUse_json(cmd, agent_id=_SUBAGENT_AGENT_ID), state_dir
            )
            assert _containment_decision(result) != "deny", (
                f"subagent allow-listed op {cmd!r} must NOT deny; "
                f"stdout: {result.stdout!r}"
            )


# ---------------------------------------------------------------------------
# cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE, C2 side) —
# --cycle-end / --cycle-begin added to LOOP_FORMATION_FLAGS so the arming-free
# agent_id subagent trip denies a subagent's marker-mutation Bash call (belt-and-
# suspenders with the C3 refuse_cycle_marker_mutation_if_subagent guard). The
# main-thread orchestrator (agent_id ABSENT) is never self-denied — its own
# bracket (--cycle-begin before dispatch, --cycle-end after) must always pass.
# ---------------------------------------------------------------------------

def test_containment_agentid_present_denies_cycle_bracket_no_marker():
    """SUBAGENT payload (agent_id) + lazy-state.py --cycle-end / --cycle-begin,
    NO marker → deny (the agent_id trip is arming-free)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for flag in ("--cycle-end", "--cycle-begin"):
            result = _run_containment(
                _bash_preToolUse_json(
                    f"python3 lazy-state.py {flag}", agent_id=_SUBAGENT_AGENT_ID
                ),
                state_dir,
            )
            assert _containment_decision(result) == "deny", (
                f"subagent {flag!r} (no marker) must deny; stdout: {result.stdout!r}"
            )


def test_containment_agentid_present_denies_cycle_bracket_bug_state():
    """SUBAGENT payload + bug-state.py --cycle-end / --cycle-begin → deny (the
    state-script regex matches bug-state.py too)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for flag in ("--cycle-end", "--cycle-begin"):
            result = _run_containment(
                _bash_preToolUse_json(
                    f"python3 bug-state.py {flag}", agent_id=_SUBAGENT_AGENT_ID
                ),
                state_dir,
            )
            assert _containment_decision(result) == "deny", (
                f"subagent bug-state {flag!r} must deny; stdout: {result.stdout!r}"
            )


def test_containment_agentid_absent_allows_cycle_bracket():
    """MAIN-THREAD payload (agent_id absent) + --cycle-end / --cycle-begin →
    allow (the orchestrator owns the bracket; it must never be self-denied)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for flag in ("--cycle-end", "--cycle-begin"):
            result = _run_containment(
                _bash_preToolUse_json(f"python3 lazy-state.py {flag}"), state_dir
            )
            assert _containment_decision(result) != "deny", (
                f"main-thread {flag!r} must NOT deny; stdout: {result.stdout!r}"
            )


# ---------------------------------------------------------------------------
# cycle-subagent-runs-orchestrator-work Phase 3 — Skill-tool intercept.
#
# A subagent invoking a /lazy* skill via the Skill tool must be denied.
# The Skill PreToolUse payload: {"tool_name":"Skill","tool_input":{"skill":"<name>"}}.
# The containment hook must intercept the Skill tool when agent_id is present
# and the skill name matches the lazy family regex.
# ---------------------------------------------------------------------------


def _skill_preToolUse_json(
    skill_name: str,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """Return a PreToolUse JSON payload for a Skill tool call.

    agent_id: when provided, marks the payload as a SUBAGENT call (D4 trip).
    skill_name: the skill name, e.g. 'lazy-batch' or 'commit'.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Skill",
        "tool_input": {"skill": skill_name},
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    return json.dumps(payload)


def test_containment_skill_subagent_denies_lazy_family():
    """SUBAGENT (agent_id present) + Skill tool + lazy family skill → deny.

    cycle-subagent-runs-orchestrator-work Phase 3 (defense-in-depth): the
    Skill-tool path for /lazy* must be closed for subagents. Each member of the
    lazy family must be denied individually.
    """
    lazy_family = [
        "lazy", "lazy-bug", "lazy-batch", "lazy-bug-batch",
        "lazy-cloud", "lazy-batch-cloud",
    ]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for skill_name in lazy_family:
            result = _run_containment(
                _skill_preToolUse_json(skill_name, agent_id=_SUBAGENT_AGENT_ID),
                state_dir,
            )
            assert _containment_decision(result) == "deny", (
                f"subagent Skill({skill_name!r}) must deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_skill_subagent_allows_non_lazy_skill():
    """SUBAGENT (agent_id) + Skill tool + non-lazy skill → allow.

    Non-lazy skills (e.g. 'commit', 'spec') must never be denied by the
    lazy-family denylist.
    """
    non_lazy_skills = ["commit", "spec", "fix", "explain", "code-review"]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for skill_name in non_lazy_skills:
            result = _run_containment(
                _skill_preToolUse_json(skill_name, agent_id=_SUBAGENT_AGENT_ID),
                state_dir,
            )
            assert _containment_decision(result) != "deny", (
                f"subagent Skill({skill_name!r}) must NOT deny (non-lazy); "
                f"stdout: {result.stdout!r}"
            )


def test_containment_skill_main_thread_allows_lazy_family():
    """MAIN-THREAD (no agent_id) + Skill tool + lazy family skill → allow.

    The main-thread orchestrator must never be self-denied when it invokes a
    /lazy* skill via the Skill tool.
    """
    lazy_family = ["lazy", "lazy-batch", "lazy-bug-batch", "lazy-batch-cloud"]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for skill_name in lazy_family:
            result = _run_containment(
                _skill_preToolUse_json(skill_name, agent_id=None),
                state_dir,
            )
            assert _containment_decision(result) != "deny", (
                f"main-thread Skill({skill_name!r}) must NOT deny; "
                f"stdout: {result.stdout!r}"
            )


def test_containment_skill_fail_open_missing_skill_field():
    """SUBAGENT (agent_id) + Skill tool + missing 'skill' field in tool_input →
    allow (fail-OPEN on unrecognized payload shape).

    An unrecognized Skill payload must never wedge the pipeline.
    """
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        # Craft a Skill payload with an empty tool_input (no 'skill' key).
        payload = {
            "session_id": str(uuid.uuid4()),
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {},   # missing 'skill' field
            "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
            "agent_id": _SUBAGENT_AGENT_ID,
        }
        result = _run_containment(json.dumps(payload), state_dir)
        assert _containment_decision(result) != "deny", (
            f"Skill payload with no 'skill' field must fail-OPEN (allow); "
            f"stdout: {result.stdout!r}"
        )


def test_containment_skill_fail_open_null_skill_field():
    """SUBAGENT (agent_id) + Skill tool + null 'skill' field → allow (fail-OPEN).

    A null or empty skill name must not deny (fail-OPEN on malformed input).
    """
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for null_val in [None, "", 123]:
            payload = {
                "session_id": str(uuid.uuid4()),
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {"skill": null_val},
                "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
                "agent_id": _SUBAGENT_AGENT_ID,
            }
            result = _run_containment(json.dumps(payload), state_dir)
            assert _containment_decision(result) != "deny", (
                f"Skill payload with skill={null_val!r} must fail-OPEN; "
                f"stdout: {result.stdout!r}"
            )


# ---------------------------------------------------------------------------
# multi-repo-concurrent-runs (Phase 2 / WU-2.4) — two-repo isolation harness.
#
# These tests do NOT pin LAZY_STATE_DIR (that override bypasses per-repo keying
# and returns one exact dir). Instead they pin HOME/USERPROFILE at a temp dir so
# the PRODUCTION keyed resolution applies (~/.claude/state/<repo-key>/), create a
# live run marker for repo-key A only, and fire the hook with the tool-call cwd
# in repo B (→ no-op) vs repo A (→ enforce, unchanged). Python owns ALL repo-key
# derivation via lazy-state.py --marker-present; bash never re-derives it.
# ---------------------------------------------------------------------------

def _keyed_env_no_state_override(home: Path) -> dict:
    """Subprocess env with HOME/USERPROFILE pinned at *home* and LAZY_STATE_DIR
    REMOVED, so claude_state_dir() resolves the production keyed subdir."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env.pop("LAZY_STATE_DIR", None)
    return env


def _init_git_repo(path: Path) -> Path:
    """Create *path* as a real git repo so active_repo_root() (cwd git-toplevel)
    and repo_key() resolve it consistently. Returns the realpath'd repo root."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"],
                   capture_output=True, text=True)
    return Path(os.path.realpath(str(path)))


def _write_keyed_marker(home: Path, repo_root: Path, session_id: str | None = None):
    """Write a live run marker into the PRODUCTION keyed subdir for *repo_root*
    under the temp *home* (HOME pinned, LAZY_STATE_DIR cleared)."""
    prior = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE", "LAZY_STATE_DIR")}
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ.pop("LAZY_STATE_DIR", None)
    lazy_core._legacy_state_migrated = False
    lazy_core.set_active_repo_root(str(repo_root))
    try:
        lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root=str(repo_root),
            max_cycles=10, now=time.time(), session_id=session_id,
        )
    finally:
        lazy_core.set_active_repo_root(None)
        lazy_core._legacy_state_migrated = False
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_guard_two_repo_isolation_crossrepo_noop_samerepo_enforces():
    """multi-repo-concurrent-runs (Phase 2): a live marker for repo A must NOT
    arm the dispatch guard in repo B (cross-repo no-op), while it still denies an
    unregistered dispatch in repo A (no same-repo regression)."""
    _guard()
    assert _GUARD_SH.exists(), f"guard hook missing: {_GUARD_SH}"
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        home.mkdir()
        repo_a = _init_git_repo(Path(td) / "repoA")
        repo_b = _init_git_repo(Path(td) / "repoB")
        env = _keyed_env_no_state_override(home)

        # Live marker for repo A ONLY (production keyed subdir).
        _write_keyed_marker(home, repo_a)

        unregistered = "This dispatch prompt was never emitted by the script."

        # --- Cross-repo: fired with cwd in repo B → fast-path allow (no-op). ---
        stdin_b = _e1_preToolUse_json(unregistered, cwd=str(repo_b))
        res_b = subprocess.run(
            [_BASH_EXE, str(_GUARD_SH)], input=stdin_b,
            capture_output=True, text=True, env=env, cwd=str(repo_b),
        )
        assert res_b.returncode == 0, (
            f"cross-repo guard must exit 0; stderr: {res_b.stderr!r}"
        )
        assert res_b.stdout.strip() == "", (
            f"cross-repo guard (marker for A, fired in B) must be a no-op "
            f"(empty stdout); got: {res_b.stdout!r}"
        )

        # --- Same-repo: fired with cwd in repo A → deny unregistered dispatch. ---
        stdin_a = _e1_preToolUse_json(unregistered, cwd=str(repo_a))
        res_a = subprocess.run(
            [_BASH_EXE, str(_GUARD_SH)], input=stdin_a,
            capture_output=True, text=True, env=env, cwd=str(repo_a),
        )
        assert res_a.returncode == 0, (
            f"same-repo guard must exit 0 (deny is in JSON); stderr: {res_a.stderr!r}"
        )
        out_a = res_a.stdout.strip()
        assert out_a != "", (
            "same-repo guard (marker for A, fired in A) must reach the guard and "
            "emit deny JSON for an unregistered prompt; got empty stdout"
        )
        payload = json.loads(out_a)
        decision = payload.get("hookSpecificOutput", {}).get("permissionDecision")
        assert decision == "deny", (
            f"same-repo unregistered dispatch must be denied; got {decision!r}"
        )


def test_inject_two_repo_isolation_crossrepo_noop_samerepo_injects():
    """multi-repo-concurrent-runs (Phase 2): a live marker for repo A must NOT
    inject the LAZY-ROUTE banner in repo B (cross-repo no-op), while it still
    injects in repo A (no same-repo regression)."""
    _guard()
    assert _INJECT_SH.exists(), f"inject hook missing: {_INJECT_SH}"
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        home.mkdir()
        # Repo A is a real git repo AND carries the fixture feature queue so the
        # inject probe has a queue to read.
        repo_a = _init_git_repo(Path(td) / "repoA")
        # Build the feature queue directly under repo A so the inject probe's
        # repo (the marker's repo_root) has a real queue to read.
        features = repo_a / "docs" / "features"
        features.mkdir(parents=True, exist_ok=True)
        (features / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
            ]}), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        fdir = features / "feat-c"
        fdir.mkdir(exist_ok=True)
        (fdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n",
            encoding="utf-8")
        plans = fdir / "plans"
        plans.mkdir(exist_ok=True)
        (plans / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")

        repo_b = _init_git_repo(Path(td) / "repoB")
        env = _keyed_env_no_state_override(home)

        # Marker BOUND to the owning session (inject is a no-op on an unbound
        # marker), repo_root = repo A.
        owner = str(uuid.uuid4())
        _write_keyed_marker(home, repo_a, session_id=owner)

        # --- Cross-repo: cwd in repo B → no inject (empty stdout). ---
        stdin_b = _userPromptSubmit_json(session_id=owner, cwd=str(repo_b))
        res_b = subprocess.run(
            [_BASH_EXE, str(_INJECT_SH)], input=stdin_b,
            capture_output=True, text=True, env=env, cwd=str(repo_b),
        )
        assert res_b.returncode == 0, (
            f"cross-repo inject must exit 0; stderr: {res_b.stderr!r}"
        )
        assert res_b.stdout.strip() == "", (
            f"cross-repo inject (marker for A, fired in B) must be a no-op "
            f"(empty stdout); got: {res_b.stdout!r}"
        )

        # --- Same-repo: cwd in repo A → inject the LAZY-ROUTE banner. ---
        stdin_a = _userPromptSubmit_json(session_id=owner, cwd=str(repo_a))
        res_a = subprocess.run(
            [_BASH_EXE, str(_INJECT_SH)], input=stdin_a,
            capture_output=True, text=True, env=env, cwd=str(repo_a),
        )
        assert res_a.returncode == 0, (
            f"same-repo inject must exit 0; stderr: {res_a.stderr!r}"
        )
        out_a = res_a.stdout.strip()
        assert out_a != "", (
            "same-repo inject (marker for A, fired in A) must emit the banner; "
            f"got empty stdout; stderr: {res_a.stderr!r}"
        )
        ctx = json.loads(out_a).get("hookSpecificOutput", {}).get("additionalContext", "")
        assert ctx.startswith("LAZY-ROUTE (hook-injected"), (
            f"same-repo inject must emit the LAZY-ROUTE banner; got: {ctx[:120]!r}"
        )


# ---------------------------------------------------------------------------
# stale-marker-arms-validate-deny-on-unrelated-dispatches Phase 1 (D1) —
# over-fire regression: the dispatch-guard GATE must be session-scoped, so a
# same-repo NON-OWNING-session dispatch fast-path-allows at the gate (never
# reaching the guard, never accruing hardening debt), while the OWNING session's
# dispatch still runs the guard exactly as the pre-fix baseline.
# ---------------------------------------------------------------------------

def test_marker_present_non_owner_session_reports_absent():
    """D1 gate contract (the load-bearing WU-1 assertion): with a marker BOUND to
    session_A, `lazy-state.py --marker-present --repo-root <repo> --session-id B`
    must report ABSENT (exit 1) for a NON-owner session B, while reporting PRESENT
    (exit 0) for the OWNER session_A.

    This is the exact gate the hook consults.  Pre-WU-1 the hook passed NO
    --session-id, so the gate was session-blind (exit 0 for every session — the
    over-fire root cause).  This unit pins that the handler honors the owner
    scoping; the end-to-end hook fixtures below pin that the HOOK now passes it.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        owner_session = str(uuid.uuid4())
        non_owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)
        env = _base_env(state_dir)
        repo_root = str(state_dir / "fixture-repo")
        state_py = str(_SCRIPTS_DIR / "lazy-state.py")

        def _present(session_id: str) -> int:
            return subprocess.run(
                [sys.executable, state_py, "--marker-present",
                 "--repo-root", repo_root, "--session-id", session_id],
                env=env, capture_output=True, text=True,
            ).returncode

        assert _present(owner_session) == 0, (
            "the OWNER session must see the marker as PRESENT (exit 0)"
        )
        assert _present(non_owner_session) == 1, (
            "a NON-owner session must see the marker as ABSENT (exit 1) — "
            "owning-session scoping at the gate"
        )


def test_guard_hook_wires_session_id_into_marker_present():
    """D1 WU-1 source lock: lazy-dispatch-guard.sh must extract the hook-input
    session_id and pass it as `--session-id "$SID"` into its
    `--marker-present --repo-root` gate query (only when non-empty — fail-OPEN).

    This is the falsifiable WU-1 contract.  For a BOUND marker the guard's own
    session-aware read already self-allows a non-owner, so there is no
    deny/ledger observable that distinguishes the session-blind gate from the
    scoped gate end-to-end — the gate scoping is a defense-in-depth + "two reads
    must AGREE" (D1) change whose seam is the hook wiring itself.  This test pins
    that wiring so a future edit cannot silently revert to the session-blind gate.
    """
    text = _GUARD_SH.read_text(encoding="utf-8")
    # The session_id must be extracted from the payload.
    assert "session_id" in text, (
        "lazy-dispatch-guard.sh must extract session_id from the hook payload"
    )
    # The gate query must carry --session-id alongside the existing --repo-root.
    assert "--session-id" in text, (
        "lazy-dispatch-guard.sh must pass --session-id into the "
        "--marker-present gate query (D1 owner-scoping)"
    )
    # The existing per-repo keying must be preserved (passed ALONGSIDE, never
    # replaced) — the SPEC's explicit non-regression for multi-repo keying.
    assert "--repo-root" in text, (
        "lazy-dispatch-guard.sh must STILL pass --repo-root (per-repo keying "
        "preserved — --session-id is added alongside, not in place of it)"
    )


def test_guard_bash_non_owner_session_gate_does_not_invoke_guard():
    """D1 over-fire lock (end-to-end): with a marker BOUND to session_A AND a
    deliberately CORRUPT prompt registry, a same-repo unregistered dispatch
    carrying a DIFFERENT session_B must, through the REAL bash
    lazy-dispatch-guard.sh hook:
      - exit 0,
      - produce EMPTY stdout (gate fast-path-allow), AND
      - leave NO hook-error.json breadcrumb (the guard NEVER RAN — a corrupt
        registry would force the guard to write the breadcrumb if it had been
        invoked).

    The breadcrumb absence is the falsifiable discriminator: pre-WU-1 the
    session-blind gate runs the guard for the non-owner, the guard hits the
    corrupt registry and writes hook-error.json (fail-open) → this FAILS.
    After WU-1 (the hook passes --session-id "$SID") the gate reports absent for
    session_B → fast-path allow → the guard is never invoked → no breadcrumb.

    (For a BOUND marker the guard's own session-aware read would self-allow the
    non-owner anyway; this fixture proves the GATE scoped it — the guard process
    is never even reached — which is the D1 "two reads must AGREE" invariant and
    the only place the unbound-marker pre-bind window (Phase 2) is left as the
    sole residual same-repo deny surface.)
    """
    _guard()
    assert _GUARD_SH.exists(), f"lazy-dispatch-guard.sh missing: {_GUARD_SH}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Marker BOUND to the OWNER session_A.
        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        # Corrupt the registry so that IF the guard runs it MUST write a
        # hook-error.json breadcrumb (the proven fail-open side effect).
        (state_dir / "lazy-prompt-registry.json").write_bytes(
            b"\xff\xfe CORRUPT \x00 NOT JSON"
        )

        # A DIFFERENT (non-owner) session fires an unregistered dispatch.
        non_owner_session = str(uuid.uuid4())
        assert non_owner_session != owner_session
        unregistered = "Hand-composed unrelated spec dispatch from a NON-owner session."
        stdin_text = _e1_preToolUse_json(
            unregistered, tool_use_id="toolu_nonowner", session_id=non_owner_session
        )
        result = _run_bash(_GUARD_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"non-owner gate fast-path must exit 0; "
            f"got {result.returncode}; stderr: {result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"non-owner dispatch must fast-path-allow at the GATE (empty stdout — "
            f"the guard never ran); got: {result.stdout!r}"
        )

        # The over-fire regression lock: the guard was NEVER invoked, so the
        # corrupt registry produced NO breadcrumb (and NO ledger row).
        breadcrumb = state_dir / "hook-error.json"
        assert not breadcrumb.exists(), (
            "the GATE must fast-path-allow a non-owner BEFORE invoking the guard "
            "— a hook-error.json breadcrumb proves the guard ran against the "
            "corrupt registry, i.e. the gate over-fired (session-blind)"
        )
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        rows = []
        if ledger_path.exists():
            rows = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()]
        assert rows == [], (
            f"a non-owning-session dispatch must NOT accrue hardening debt "
            f"(no lazy-deny-ledger.jsonl row); got {len(rows)} row(s): {rows!r}"
        )


def test_guard_bash_owner_session_gate_still_denies_and_ledgers():
    """D1 baseline-preservation contrast: with the SAME marker bound to
    session_A, an unregistered-prompt dispatch carrying session_A (the OWNER)
    must, through the REAL bash hook, still reach the guard and DENY + ledger
    exactly as the pre-fix baseline.  This pins that WU-1 scoped the gate to the
    owner WITHOUT disabling enforcement for the owning run.
    """
    _guard()
    assert _GUARD_SH.exists(), f"lazy-dispatch-guard.sh missing: {_GUARD_SH}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        unregistered = "Hand-composed unregistered dispatch from the OWNING session."
        stdin_text = _e1_preToolUse_json(
            unregistered, tool_use_id="toolu_owner", session_id=owner_session
        )
        result = _run_bash(_GUARD_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"owner gate must exit 0 (deny is in JSON); stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", (
            "owner-session unregistered dispatch must reach the guard and emit "
            "deny JSON; got empty stdout (gate must NOT fast-path-allow the owner)"
        )
        payload = json.loads(output)
        decision = payload.get("hookSpecificOutput", {}).get("permissionDecision")
        assert decision == "deny", (
            f"owner-session unregistered dispatch must be denied; got {decision!r}"
        )

        # The owner's deny DOES accrue debt (baseline behavior preserved).
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        assert ledger_path.exists(), (
            "the owner deny path must create lazy-deny-ledger.jsonl"
        )
        rows = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()]
        assert len(rows) == 1, f"expected exactly one owner ledger row; got {len(rows)}"
        entry = json.loads(rows[0])
        assert entry["tool_use_id"] == "toolu_owner", entry
        assert entry["acked"] is False, entry


# ---------------------------------------------------------------------------
# stale-marker-arms-validate-deny-on-unrelated-dispatches Phase 2 (D2) —
# pre-bind no-debt deny: when the live marker is UNBOUND (session_id: None),
# the gate cannot owner-scope (Phase 1's path B needs BOTH non-None), so the
# guard still runs and an unregistered prompt is denied.  That pre-bind deny
# must carry NO hardening debt (route through _deny_no_ledger).  A deny under a
# BOUND marker (a genuine validate-deny) still ledgers and accrues debt.
# ---------------------------------------------------------------------------

def test_guard_unbound_marker_deny_writes_no_ledger_no_debt():
    """D2 WU-3 lock: with an UNBOUND marker (session_id: None) and an
    unregistered prompt, the guard returns deny JSON but appends NO
    lazy-deny-ledger.jsonl row and pending_hardening() stays 0.

    Pre-WU-3 this FAILS: the generic default-deny under an unbound marker
    _deny_and_ledger's (writes a row, pending_hardening()==1).  After WU-3 the
    unbound-marker default-deny routes through _deny_no_ledger (no row, no debt).
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # UNBOUND marker (bind-pending — session_id deliberately None).
        _write_marker_in_dir(state_dir, session_id=None)

        unregistered = "Unregistered dispatch under an UNBOUND (pre-bind) marker."
        stdin_text = _e1_preToolUse_json(
            unregistered, tool_use_id="toolu_unbound", session_id=str(uuid.uuid4())
        )
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", "guard must STILL produce deny JSON (verdict preserved)"
        payload = json.loads(output)
        decision = payload.get("hookSpecificOutput", {}).get("permissionDecision")
        assert decision == "deny", (
            f"an unbound-marker unregistered dispatch is still DENIED (only the "
            f"ledger append is suppressed); got {decision!r}"
        )

        # The no-debt lock: NO ledger row, pending_hardening() == 0.
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        rows = []
        if ledger_path.exists():
            rows = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()]
        assert rows == [], (
            f"a PRE-BIND (unbound-marker) deny must write NO ledger row "
            f"(no hardening debt); got {len(rows)} row(s): {rows!r}"
        )

        _set_state_dir(state_dir)
        try:
            debt = lazy_core.pending_hardening()
        finally:
            _clear_state_dir()
        assert debt == 0, (
            f"pending_hardening() must stay 0 for a pre-bind unbound-marker deny; "
            f"got {debt}"
        )


def test_guard_bound_marker_deny_still_ledgers_and_accrues_debt():
    """D2 WU-3 contrast lock: with a BOUND marker (owner session) and an
    unregistered prompt dispatched BY THE OWNER, the guard denies AND ledgers —
    pending_hardening() rises to 1.  This is a genuine validate-deny / harness
    gap and MUST still accrue debt (the no-debt routing is scoped to the unbound
    window ONLY; it must not erode the genuine debt path).
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        owner_session = str(uuid.uuid4())
        _write_marker_in_dir(state_dir, session_id=owner_session)

        unregistered = "Unregistered dispatch under a BOUND marker (owner session)."
        stdin_text = _e1_preToolUse_json(
            unregistered, tool_use_id="toolu_bounddeny", session_id=owner_session
        )
        result = _run_guard_py(stdin_text, env)

        assert result.returncode == 0, (
            f"guard must exit 0; stderr: {result.stderr!r}"
        )
        output = result.stdout.strip()
        assert output != "", "guard must produce deny JSON"
        payload = json.loads(output)
        decision = payload.get("hookSpecificOutput", {}).get("permissionDecision")
        assert decision == "deny", f"bound-marker unregistered dispatch must deny; got {decision!r}"

        # The debt-preservation lock: exactly one ledger row, pending_hardening()==1.
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        assert ledger_path.exists(), (
            "a BOUND-marker validate-deny MUST create lazy-deny-ledger.jsonl"
        )
        rows = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()]
        assert len(rows) == 1, f"expected exactly one bound-marker ledger row; got {len(rows)}"
        entry = json.loads(rows[0])
        assert entry["tool_use_id"] == "toolu_bounddeny", entry
        assert entry["acked"] is False, entry

        _set_state_dir(state_dir)
        try:
            debt = lazy_core.pending_hardening()
        finally:
            _clear_state_dir()
        assert debt == 1, (
            f"pending_hardening() must be 1 for a genuine bound-marker validate-deny; "
            f"got {debt}"
        )


def test_guard_unbound_marker_hardening_cap_still_ledgers():
    """D2 WU-3 scope guard: the no-debt routing applies ONLY to the GENERIC
    default-deny.  A depth-1 hardening-cap deny under an UNBOUND marker MUST keep
    its existing ledger semantics (the depth-1 cap is a sacred invariant and is
    NOT broadened into no-debt).

    Setup: register a hardening-class entry, consume it as consumer A (allow),
    then re-dispatch the same (now-consumed) hardening entry as consumer B under
    the UNBOUND marker — this hits the hardening-cap deny path, which must still
    _deny_and_ledger.
    """
    _guard()
    assert _GUARD_PY.exists(), f"lazy_guard.py missing: {_GUARD_PY}"

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)

        # Unbound marker (session_id None) — the no-debt window for the GENERIC
        # path, but NOT for the hardening cap.
        _write_marker_in_dir(state_dir, session_id=None)

        hardening_prompt = "You are the harden-harness subagent. Diagnose and fix."
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(hardening_prompt, cls="hardening", item_id=None)
        finally:
            _clear_state_dir()

        # Consumer A consumes (allow). On allow the marker binds to A's session —
        # so to keep the SECOND call on the unbound-marker path for the GENERIC
        # branch we would need it unbound; but the hardening-cap branch fires
        # regardless of bind state. To exercise the cap under an unbound marker we
        # must prevent the bind: dispatch A with NO session_id (None), so
        # _bind_marker_on_allow is a silent no-op (it skips when session is None).
        stdin_a = _e1_preToolUse_json(hardening_prompt, tool_use_id="toolu_hc_a")
        # _e1 default-generates a session_id; override to empty so the marker stays
        # unbound after the allow.
        payload_a = json.loads(stdin_a)
        payload_a["session_id"] = None
        r_a = _run_guard_py(json.dumps(payload_a), env)
        pa = json.loads(r_a.stdout.strip())
        assert pa["hookSpecificOutput"]["permissionDecision"] == "allow", (
            "first hardening dispatch must allow"
        )

        # Confirm the marker is STILL unbound (the allow did not bind it).
        _set_state_dir(state_dir)
        try:
            m = lazy_core.read_run_marker()
        finally:
            _clear_state_dir()
        assert m is not None and m.get("session_id") is None, (
            "marker must remain unbound for this scope test"
        )

        # Consumer B re-dispatches the consumed hardening entry → depth-1 cap deny.
        stdin_b = _e1_preToolUse_json(hardening_prompt, tool_use_id="toolu_hc_b")
        payload_b = json.loads(stdin_b)
        payload_b["session_id"] = None
        r_b = _run_guard_py(json.dumps(payload_b), env)
        pb = json.loads(r_b.stdout.strip())
        hso = pb["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny", "hardening cap must deny consumer B"
        assert "halt" in hso.get("permissionDecisionReason", ""), (
            "the deny must be the hardening-cap reason, not the generic default deny"
        )

        # The hardening-cap deny MUST still ledger (NOT routed to no-debt).
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        rows = []
        if ledger_path.exists():
            rows = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()]
        assert len(rows) == 1, (
            f"the hardening-cap deny under an unbound marker MUST still write a "
            f"ledger row (depth-1 cap is NOT broadened into no-debt); "
            f"got {len(rows)} row(s)"
        )


# ===========================================================================
# long-build-and-runtime-ownership Phase 3 (WU-1) — long-build-ownership-guard.sh
#
# A NET-NEW fail-OPEN PreToolUse(Bash) guard (M5 Prevent / LD4) that redirects
# subagent-owned long builds to orchestrator ownership.  On a match it emits a
# `deny` JSON whose reason names the orchestrator-takeover signature (the
# "fail-open block" in this hook framework — a non-zero exit is a hard error, so
# the block is a permissionDecision: deny, NOT exit 2).  Matcher is anchored to
# EXACT long-build binary invocations (env-assignment prefix tolerated) and must
# NOT redirect ls/cat/lint/cargo-check.  ANY internal error → exit 0 allow +
# breadcrumb (mirrors the sibling guards).
#
# These tests pipe synthetic PreToolUse JSON on stdin and assert the emitted
# deny/allow, reusing the containment test harness (_bash_preToolUse_json /
# _run_bash / _base_env).  The guard takeover-signature string is asserted via
# the SSOT constant so the test and the hook never drift.
# ===========================================================================

_LONGBUILD_GUARD_SH = _HOOKS_DIR / "long-build-ownership-guard.sh"

# The orchestrator-takeover signature the deny reason MUST name (SSOT; part 5
# consumes the same literal).  The guard's deny reason is required to carry this
# exact token so the orchestrator can recognize the redirect deterministically.
_LONGBUILD_TAKEOVER_SIGNATURE = "LONG-BUILD-OWNERSHIP-TAKEOVER"


def _run_longbuild_guard(
    stdin_text: str, state_dir: Path
) -> subprocess.CompletedProcess:
    """Pipe *stdin_text* into the long-build-ownership guard hook."""
    return _run_bash(_LONGBUILD_GUARD_SH, stdin_text, _base_env(state_dir))


# ---------------------------------------------------------------------------
# cycle-subagent-fabricates-policy-or-stray-branch — Phase 3
#   block-sentinel-write-on-stray-branch.sh (WU-4) + settings registration (WU-5)
#
# The hook denies a pipeline-sentinel Write/Edit while HEAD != the run marker's
# work_branch; fail-OPEN on every error path; the deny names the work branch.
# ---------------------------------------------------------------------------

_STRAYBRANCH_HOOK_SH = _HOOKS_DIR / "block-sentinel-write-on-stray-branch.sh"


def _git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=str(cwd),
        capture_output=True, text=True,
    )


def _init_repo_on_branch(parent: Path, branch: str) -> Path:
    """Create a temp git repo with one commit, checked out on *branch*."""
    repo = parent / "repo"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@t.t"], repo)
    _git(["config", "user.name", "t"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "f.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "init"], repo)
    # Rename the initial branch to a known base, then optionally branch off.
    _git(["branch", "-M", "main"], repo)
    if branch != "main":
        _git(["checkout", "-q", "-b", branch], repo)
    return repo


def _write_marker_with_branch(state_dir: Path, repo_root: str, work_branch: str) -> None:
    """Write a run marker into *state_dir* then force its work_branch on disk."""
    _set_state_dir(state_dir)
    try:
        lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root=repo_root,
            max_cycles=10, now=time.time(),
        )
    finally:
        _clear_state_dir()
    marker_path = state_dir / "lazy-run-marker.json"
    data = json.loads(marker_path.read_text(encoding="utf-8"))
    data["work_branch"] = work_branch
    marker_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _straybranch_payload(file_path: str, cwd: str, tool: str = "Write") -> str:
    """PreToolUse JSON for a Write/Edit targeting file_path, fired from cwd."""
    sid = str(uuid.uuid4())
    return json.dumps({
        "session_id": sid,
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": file_path},
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
    })


def test_straybranch_hook_file_exists():
    """The net-new hook must exist on disk (WU-4)."""
    assert _STRAYBRANCH_HOOK_SH.exists(), (
        f"block-sentinel-write-on-stray-branch.sh missing — Phase 3 WU-4 not "
        f"implemented: {_STRAYBRANCH_HOOK_SH}"
    )


def test_straybranch_denies_sentinel_on_stray_branch():
    """Sentinel write + live marker(work_branch=main) + HEAD=audit/foo → deny,
    reason names the work branch 'main' + a corrective switch-back."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "audit/foo")
        _write_marker_with_branch(state_dir, str(repo), "main")
        payload = _straybranch_payload(str(repo / "NEEDS_INPUT.md"), str(repo))
        result = _run_bash(_STRAYBRANCH_HOOK_SH, payload, _base_env(state_dir))
        assert result.returncode == 0, (
            f"hook must exit 0 (deny is JSON); got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert _containment_decision(result) == "deny", (
            f"a sentinel write on a stray branch must deny; stdout={result.stdout!r}"
        )
        reason = json.loads(result.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert "main" in reason, f"deny reason must name the work branch; got {reason!r}"
        assert "audit/foo" in reason, f"deny reason should name the stray branch; got {reason!r}"


def test_straybranch_allows_sentinel_on_work_branch():
    """Sentinel write while HEAD == work_branch (main) → allow (emit nothing)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "main")
        _write_marker_with_branch(state_dir, str(repo), "main")
        payload = _straybranch_payload(str(repo / "FIXED.md"), str(repo))
        result = _run_bash(_STRAYBRANCH_HOOK_SH, payload, _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"a sentinel write ON the work branch must allow; stdout={result.stdout!r}"
        )


def test_straybranch_fail_open_no_marker():
    """No marker (exit-1 --marker-work-branch) → allow even on a stray branch
    (fail-OPEN: no known work branch to enforce against)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()  # exists but empty → no marker
        repo = _init_repo_on_branch(td, "audit/foo")
        payload = _straybranch_payload(str(repo / "BLOCKED.md"), str(repo))
        result = _run_bash(_STRAYBRANCH_HOOK_SH, payload, _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"no marker must fail-OPEN (allow); stdout={result.stdout!r}"
        )


def test_straybranch_allows_non_sentinel_target():
    """A non-sentinel target (SPEC.md / foo.py) on a stray branch → allow."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "audit/foo")
        _write_marker_with_branch(state_dir, str(repo), "main")
        for target in ("SPEC.md", "foo.py"):
            payload = _straybranch_payload(str(repo / target), str(repo))
            result = _run_bash(_STRAYBRANCH_HOOK_SH, payload, _base_env(state_dir))
            assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
            assert _containment_decision(result) != "deny", (
                f"non-sentinel target {target!r} must allow; stdout={result.stdout!r}"
            )


def test_straybranch_fail_open_malformed_json():
    """Malformed payload → fail-OPEN allow (exit 0, no deny)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_bash(
            _STRAYBRANCH_HOOK_SH, "{ not valid json", _base_env(state_dir)
        )
        assert result.returncode == 0, (
            f"malformed payload must fail-open (exit 0); got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert _containment_decision(result) != "deny", (
            f"malformed payload must NOT deny (fail-open); stdout={result.stdout!r}"
        )


def test_straybranch_non_write_tool_allows():
    """A non-Write/Edit tool (Bash) targeting a sentinel name → allow."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "audit/foo")
        _write_marker_with_branch(state_dir, str(repo), "main")
        payload = json.loads(_straybranch_payload(str(repo / "FIXED.md"), str(repo)))
        payload["tool_name"] = "Bash"
        payload["tool_input"] = {"command": "echo FIXED.md"}
        result = _run_bash(_STRAYBRANCH_HOOK_SH, json.dumps(payload), _base_env(state_dir))
        assert _containment_decision(result) != "deny", (
            f"non-Write/Edit tool must allow; stdout={result.stdout!r}"
        )


def test_straybranch_registered_in_settings():
    """Mount-site verification (WU-5): the hook must be REGISTERED as a command in
    user/settings.json's PreToolUse `matcher: Write|Edit` array — a hook on disk
    but unregistered is dead code."""
    settings_path = _REPO_ROOT / "user" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    pretooluse = settings.get("hooks", {}).get("PreToolUse", [])
    we_blocks = [b for b in pretooluse if b.get("matcher") == "Write|Edit"]
    assert we_blocks, "no PreToolUse matcher:Write|Edit block found in settings.json"
    commands = [
        h.get("command", "")
        for block in we_blocks
        for h in block.get("hooks", [])
    ]
    assert any("block-sentinel-write-on-stray-branch.sh" in c for c in commands), (
        f"block-sentinel-write-on-stray-branch.sh not registered in the "
        f"PreToolUse matcher:Write|Edit array; registered commands: {commands!r}"
    )


def test_longbuild_guard_file_exists():
    """The net-new guard hook must exist on disk (WU-1)."""
    assert _LONGBUILD_GUARD_SH.exists(), (
        f"long-build-ownership-guard.sh missing — Phase 3 WU-1 not implemented: "
        f"{_LONGBUILD_GUARD_SH}"
    )


def test_longbuild_guard_denies_tauri_build():
    """`tauri build` → deny + the takeover-signature in the reason."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json("tauri build"), state_dir
        )
        assert result.returncode == 0, (
            f"guard must exit 0 (deny is JSON, not exit code); "
            f"got {result.returncode}; stderr: {result.stderr!r}"
        )
        assert _containment_decision(result) == "deny", (
            f"`tauri build` must deny; stdout: {result.stdout!r}"
        )
        reason = json.loads(result.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert _LONGBUILD_TAKEOVER_SIGNATURE in reason, (
            f"deny reason must name the takeover signature "
            f"{_LONGBUILD_TAKEOVER_SIGNATURE!r}; got {reason!r}"
        )


def test_longbuild_guard_denies_cargo_build_release():
    """`cargo build --release` → deny."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json("cargo build --release"), state_dir
        )
        assert _containment_decision(result) == "deny", (
            f"`cargo build --release` must deny; stdout: {result.stdout!r}"
        )


def test_longbuild_guard_denies_npm_run_build():
    """`npm run build` → deny."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json("npm run build"), state_dir
        )
        assert _containment_decision(result) == "deny", (
            f"`npm run build` must deny; stdout: {result.stdout!r}"
        )


def test_longbuild_guard_env_prefix_tolerance():
    """A leading env assignment (`ENV=1 tauri build`) → still deny (the matcher
    tolerates the env-assignment prefix before the long-build binary)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json("FOO=bar BAZ=1 tauri build"), state_dir
        )
        assert _containment_decision(result) == "deny", (
            f"env-prefixed `tauri build` must deny (prefix tolerance); "
            f"stdout: {result.stdout!r}"
        )


def test_longbuild_guard_allows_false_positive_scope():
    """False-positive scope guard: short/unrelated commands must ALLOW (no deny).
    `cargo check --release` is explicitly allowed — it is the FAST pre-build
    check the long-build rule recommends, NOT a long build."""
    allow_cmds = [
        "ls -la",
        "cat foo.txt",
        "npm run lint",
        "cargo check --release",
        "npm run build:docs",   # not the exact `npm run build` token
        "echo tauri build",     # a substring inside another command, not the head
    ]
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        for cmd in allow_cmds:
            result = _run_longbuild_guard(
                _bash_preToolUse_json(cmd), state_dir
            )
            assert result.returncode == 0, (
                f"{cmd!r} must exit 0; stderr: {result.stderr!r}"
            )
            assert _containment_decision(result) != "deny", (
                f"{cmd!r} must NOT deny (false-positive scope guard); "
                f"stdout: {result.stdout!r}"
            )


def test_longbuild_guard_fail_open_on_malformed_json():
    """A malformed payload (bad JSON on stdin) → fail-open allow (exit 0, no
    deny), mirroring the sibling guards."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_bash(
            _LONGBUILD_GUARD_SH, "{ this is not valid json", _base_env(state_dir)
        )
        assert result.returncode == 0, (
            f"malformed payload must fail-open (exit 0); "
            f"got {result.returncode}; stderr: {result.stderr!r}"
        )
        assert _containment_decision(result) != "deny", (
            f"malformed payload must NOT deny (fail-open); stdout: {result.stdout!r}"
        )


def test_longbuild_guard_non_bash_tool_allows():
    """A non-Bash tool call (e.g. Read) → allow (the guard scopes to Bash)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        payload = json.loads(_bash_preToolUse_json("tauri build"))
        payload["tool_name"] = "Read"
        payload["tool_input"] = {"file_path": "tauri build"}
        result = _run_bash(
            _LONGBUILD_GUARD_SH, json.dumps(payload), _base_env(state_dir)
        )
        assert _containment_decision(result) != "deny", (
            f"non-Bash tool must NOT deny; stdout: {result.stdout!r}"
        )


def test_longbuild_guard_registered_in_settings():
    """Mount-site verification (d8 mount-site failure class): the net-new guard
    must be REGISTERED as a command in user/settings.json's PreToolUse
    `matcher: Bash` array — a hook on disk but unregistered is dead code."""
    settings_path = _REPO_ROOT / "user" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    pretooluse = settings.get("hooks", {}).get("PreToolUse", [])
    bash_blocks = [b for b in pretooluse if b.get("matcher") == "Bash"]
    assert bash_blocks, "no PreToolUse matcher:Bash block found in settings.json"
    commands = [
        h.get("command", "")
        for block in bash_blocks
        for h in block.get("hooks", [])
    ]
    assert any("long-build-ownership-guard.sh" in c for c in commands), (
        f"long-build-ownership-guard.sh not registered in the PreToolUse "
        f"matcher:Bash array; registered commands: {commands!r}"
    )


# ===========================================================================
# build-queue-enforce-cd-prefix-bypass — build-queue-enforce.sh unanchored deny
#
# The deny matchers were anchored to the START of the command, so a heavy build
# chained behind a leading command (`cd "..." && dotnet build ...`) bypassed the
# gate entirely. These tests pin the unanchored behavior: a real heavy build
# anywhere in the command DENIES (cd-prefix, pipeline, compound), while the
# sanctioned build-queue.ps1 wrapper, safe dotnet sub-commands, bare restore,
# and the BUILD_QUEUE_BYPASS=1 escape hatch stay ALLOWED.
#
# The scope gate (_is_cognito_worktree) shells out to `git config --get
# remote.origin.url`, so these tests build a throwaway git repo with a
# cognitoforms/cognito remote and fire the hook with cwd pointed at it.
# ===========================================================================

_BQE_HOOK_SH = _HOOKS_DIR / "build-queue-enforce.sh"


def _init_cognito_worktree(parent: Path) -> Path:
    """Create a temp git repo whose origin remote matches cognitoforms/cognito,
    so build-queue-enforce.sh's scope gate treats it as a Cognito worktree."""
    repo = parent / "cognito-worktree"
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@t.t"], repo)
    _git(["config", "user.name", "t"], repo)
    _git(["remote", "add", "origin", "https://github.com/cognitoforms/cognito.git"], repo)
    return repo


def _bqe_payload(command: str, cwd: str) -> str:
    """PreToolUse Bash JSON for build-queue-enforce.sh, fired from *cwd*."""
    return json.dumps({
        "session_id": str(uuid.uuid4()),
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "toolu_" + uuid.uuid4().hex[:24],
    })


def test_bqe_denies_cd_prefixed_dotnet_build():
    """`cd "<cognito-worktree>" && dotnet build ...` → deny (cd-prefix bypass closed)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = (f'cd "{repo}" && dotnet build "./Cognito.Core/Cognito.Core.csproj" '
               f'-c Debug -v minimal --nologo')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, (
            f"hook must exit 0 (deny is JSON); got {result.returncode}; stderr={result.stderr!r}"
        )
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed dotnet build must deny; stdout={result.stdout!r}"
        )


def test_bqe_denies_cd_prefixed_dotnet_test():
    """`cd "..." && dotnet test ... --filter ...` → deny."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = (f'cd "{repo}" && dotnet test ./Cognito.UnitTests/Cognito.UnitTests.csproj '
               f'--filter "ClassName~Foo"')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed dotnet test must deny; stdout={result.stdout!r}"
        )


def test_bqe_denies_dotnet_build_in_pipeline():
    """`dotnet build ... 2>&1 | tail -20` → deny (pipeline form)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = f'cd "{repo}" && dotnet build "./Cognito.Core/Cognito.Core.csproj" 2>&1 | tail -20'
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"piped dotnet build must deny; stdout={result.stdout!r}"
        )


def test_bqe_denies_restore_then_build_compound():
    """`dotnet restore && dotnet build` → deny (a real build is present even
    though a safe sub-command leads)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "dotnet restore && dotnet build ./Cognito.sln -c Debug"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"compound restore && build must deny (build present); stdout={result.stdout!r}"
        )


def test_bqe_allows_bare_restore():
    """`dotnet restore` alone (no build) → allow."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        result = _run_bash(
            _BQE_HOOK_SH, _bqe_payload("dotnet restore ./Cognito.sln", str(repo)),
            _base_env(state_dir),
        )
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"bare dotnet restore must allow; stdout={result.stdout!r}"
        )


def test_bqe_allows_build_queue_wrapper_with_filtered_exec():
    """The sanctioned wrapper carrying a *-filtered.ps1 -Exec arg → allow (a
    naive unanchored *-filtered.ps1 deny would wrongly block the one sanctioned
    path)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = (f'REPO_ROOT="{repo}" && powershell.exe -ExecutionPolicy Bypass -File '
               f'"$HOME/.claude/scripts/build-queue.ps1" -Op mstest '
               f'-Exec "$REPO_ROOT/.claude/scripts/test-filtered.ps1" -Filter "ClassName~Foo"')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"build-queue.ps1 wrapper (even carrying a -Exec filtered script) must "
            f"allow; stdout={result.stdout!r}"
        )


def test_bqe_allows_bypass_token_with_cd_prefixed_build():
    """`BUILD_QUEUE_BYPASS=1 dotnet build ...` → allow (escape hatch)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("BUILD_QUEUE_BYPASS=1 dotnet build ./Cognito.sln", str(repo)),
            _base_env(state_dir),
        )
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"BUILD_QUEUE_BYPASS=1 must allow even a real build; stdout={result.stdout!r}"
        )


def test_bqe_allows_bypass_leading_build_segment_after_cd():
    """`cd "..." && BUILD_QUEUE_BYPASS=1 dotnet build ...` → allow. The bypass
    token is recognized per segment (matching the deny surface's segment
    awareness), so a token leading the build's own segment behind a cd prefix
    works — the asymmetry where deny was unanchored but bypass was
    leading-anchored is closed."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = f'cd "{repo}" && BUILD_QUEUE_BYPASS=1 dotnet build ./Cognito.sln -c Debug'
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"cd-prefixed BUILD_QUEUE_BYPASS=1 build must allow; stdout={result.stdout!r}"
        )


def test_bqe_allows_env_prefixed_bypass_after_cd():
    """`cd "..." && NAME=val BUILD_QUEUE_BYPASS=1 dotnet build ...` → allow
    (other leading env assignments before the token, per-segment form)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = (f'cd "{repo}" && MSBUILDDEBUGPATH=/tmp BUILD_QUEUE_BYPASS=1 '
               f'dotnet build ./Cognito.sln')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) != "deny", (
            f"env-prefixed bypass in a cd-prefixed segment must allow; stdout={result.stdout!r}"
        )


def test_bqe_allows_env_prefixed_bypass_leading():
    """`NAME=val BUILD_QUEUE_BYPASS=1 dotnet build ...` → allow (unchanged
    leading form with other env assignments before the token)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "MSBUILDDEBUGPATH=/tmp BUILD_QUEUE_BYPASS=1 dotnet build ./Cognito.sln"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) != "deny", (
            f"leading env-prefixed bypass must allow (unchanged); stdout={result.stdout!r}"
        )


def test_bqe_denies_bypass_in_other_segment():
    """`cd "..." && BUILD_QUEUE_BYPASS=1 echo prep && dotnet build ...` → deny.
    The bypass suppresses ONLY the segment it leads — a real un-bypassed build
    in another segment must still deny (segment-aware bypass detection must
    not re-open the enforcement escape the cd-prefix-bypass fix closed)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = (f'cd "{repo}" && BUILD_QUEUE_BYPASS=1 echo prep && '
               f'dotnet build ./Cognito.sln')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"un-bypassed build in a different segment must deny; stdout={result.stdout!r}"
        )


def test_bqe_denies_bypass_token_as_argument():
    """`echo BUILD_QUEUE_BYPASS=1 && dotnet build ...` → deny. The token as a
    mid-segment ARGUMENT (not a leading env assignment of the build segment)
    must not bypass."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "echo BUILD_QUEUE_BYPASS=1 && dotnet build ./Cognito.sln"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"bypass token as an argument must not bypass; stdout={result.stdout!r}"
        )


def test_bqe_denies_cd_prefixed_filtered_script():
    """A raw `cd "..." && powershell ... build-filtered.ps1` → deny (filtered
    script invoked directly, not through the wrapper)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = (f'cd "{repo}" && powershell.exe -ExecutionPolicy Bypass -File '
               f'"$HOME/.claude/scripts/build-filtered.ps1"')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"raw filtered-script invocation must deny; stdout={result.stdout!r}"
        )


def test_bqe_denies_cd_prefixed_nx_build():
    """`cd "..." && npx nx build cognito-spa` → deny."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = f'cd "{repo}" && npx nx build cognito-spa'
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed nx build must deny; stdout={result.stdout!r}"
        )


def test_bqe_allows_outside_cognito_worktree():
    """A cd-prefixed dotnet build fired from a NON-Cognito repo → allow (scope
    gate intact: fail-open outside Cognito worktrees)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "main")  # no cognitoforms/cognito remote
        cmd = f'cd "{repo}" && dotnet build ./Foo.sln -c Debug'
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"non-Cognito worktree must allow (scope gate); stdout={result.stdout!r}"
        )


def test_bqe_fail_open_malformed_json():
    """Malformed payload → fail-open allow (exit 0, no deny)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_bash(_BQE_HOOK_SH, "{ not valid json", _base_env(state_dir))
        assert result.returncode == 0, (
            f"malformed payload must fail-open (exit 0); got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert _containment_decision(result) != "deny", (
            f"malformed payload must NOT deny (fail-open); stdout={result.stdout!r}"
        )


def test_longbuild_guard_denies_cd_prefixed_cargo_build_release():
    """`cd "..." && cargo build --release` → deny (cd-prefix bypass closed for
    the long-build set too)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json('cd "/some/app" && cargo build --release'), state_dir
        )
        assert result.returncode == 0, f"guard must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed cargo build --release must deny; stdout={result.stdout!r}"
        )


def test_longbuild_guard_denies_cd_prefixed_tauri_build():
    """`cd "..." && tauri build` → deny."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json('cd "/some/app" && tauri build'), state_dir
        )
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed tauri build must deny; stdout={result.stdout!r}"
        )


def test_longbuild_guard_denies_cd_prefixed_npm_run_build():
    """`cd "..." && npm run build` → deny."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json('cd "/some/app" && npm run build'), state_dir
        )
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed npm run build must deny; stdout={result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# build-queue-recycle-kills-concurrent-worktree-build (test-agent addendum) —
# build-queue-enforce.sh's deny regexes are UNANCHORED, so a READ-ONLY command
# that merely REFERENCES a build token (grep/cat/find over a *-filtered.ps1
# path, or a build-log/results-json path) is wrongly DENIED. The fix (a later
# impl agent) anchors the deny to command-segment-start / the
# `powershell -File <...>-filtered.ps1` arg case. These tests pin the
# CORRECT behavior; the three *-filtered.ps1-as-read-argument ALLOW cases are
# the genuine RED regression (currently wrongly denied).
# ---------------------------------------------------------------------------


def test_bqe_allows_cat_results_json():
    """`cat "$HOME/.claude/state/build-queue/results/614.json"` → allow (a
    read of a build-queue results file is not a build invocation)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = 'cat "$HOME/.claude/state/build-queue/results/614.json"'
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"reading a build-queue results json must allow; stdout={result.stdout!r}"
        )


def test_bqe_allows_grep_filtered_script():
    """`grep -n "stale|exit 4" test-filtered.ps1` → allow (grepping a
    *-filtered.ps1 script's contents is a read, not a build invocation).
    Currently RED: the unanchored deny regex wrongly denies this."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = 'grep -n "stale|exit 4" test-filtered.ps1'
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"grep over test-filtered.ps1 must allow (read-only reference); "
            f"stdout={result.stdout!r}"
        )


def test_bqe_allows_tail_build_log():
    """`tail logs/500.build.err.log` → allow (tailing a build log is a read,
    not a build invocation)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "tail logs/500.build.err.log"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"tailing a build log must allow; stdout={result.stdout!r}"
        )


def test_bqe_allows_find_filtered_script():
    """`find . -name build-filtered.ps1` → allow (locating the file by name
    is a read-only filesystem query, not a build invocation). Currently RED."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "find . -name build-filtered.ps1"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"find over build-filtered.ps1 must allow (read-only reference); "
            f"stdout={result.stdout!r}"
        )


def test_bqe_allows_cat_filtered_script_piped_head():
    """`cat build-filtered.ps1 | head -100` → allow (reading the script's
    source, not executing it). Currently RED."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "cat build-filtered.ps1 | head -100"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"cat | head over build-filtered.ps1 must allow (read-only reference); "
            f"stdout={result.stdout!r}"
        )


def test_bqe_allows_git_diff_settings():
    """`git diff user/settings.json` → allow (an ordinary git diff, no build
    token at all)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "git diff user/settings.json"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"git diff must allow; stdout={result.stdout!r}"
        )


def test_bqe_denies_bare_dotnet_build():
    """`dotnet build ./Cognito.sln -c Debug` (bare, no cd prefix) → deny."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "dotnet build ./Cognito.sln -c Debug"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) == "deny", (
            f"bare dotnet build must deny; stdout={result.stdout!r}"
        )


def test_bqe_denies_powershell_file_filtered_script():
    """A bare `powershell.exe -File <...>-filtered.ps1` invocation NOT routed
    through build-queue.ps1 → deny (the filtered script is being EXECUTED,
    not merely referenced)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = ('powershell.exe -ExecutionPolicy Bypass -File '
               '"$HOME/.claude/scripts/test-filtered.ps1" -Filter "ClassName~Foo"')
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) == "deny", (
            f"bare powershell -File invocation of a filtered script must deny; "
            f"stdout={result.stdout!r}"
        )


def test_bqe_denies_direct_filtered_script_dot_slash():
    """`./build-filtered.ps1` (direct segment-leading invocation) → deny."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        cmd = "./build-filtered.ps1"
        result = _run_bash(_BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir))
        assert result.returncode == 0, f"hook must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) == "deny", (
            f"direct ./build-filtered.ps1 invocation must deny; stdout={result.stdout!r}"
        )


def test_longbuild_guard_allows_cat_referencing_cargo_build():
    """A read-verb ARG referencing `cargo build --release` (not the command
    head) → allow. Expected already-green: the long-build guard is already
    anchored to command-segment-start."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json('grep -n "cargo build --release" build-notes.md'),
            state_dir,
        )
        assert result.returncode == 0, f"guard must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"grep referencing 'cargo build --release' as an arg must allow; "
            f"stdout={result.stdout!r}"
        )


def test_longbuild_guard_allows_grep_referencing_tauri_build():
    """`grep -rn "tauri build" docs/` → allow. Expected already-green."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json('grep -rn "tauri build" docs/'), state_dir
        )
        assert result.returncode == 0, f"guard must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"grep referencing 'tauri build' as an arg must allow; stdout={result.stdout!r}"
        )


def test_longbuild_guard_allows_find_referencing_npm_run_build():
    """`find . -name "npm run build.log"` → allow. Expected already-green."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json('find . -name "npm run build.log"'), state_dir
        )
        assert result.returncode == 0, f"guard must exit 0; stderr={result.stderr!r}"
        assert _containment_decision(result) != "deny", (
            f"find referencing 'npm run build.log' as an arg must allow; "
            f"stdout={result.stdout!r}"
        )


# ===========================================================================
# incident-auto-capture Phase 1 (D2) — hook-events.jsonl appender wiring.
#
# Every hook-level DENY (and every existing fail-open ERROR breadcrumb site)
# additionally appends one {ts, kind, hook, repo_root, signature, detail} line
# to hook-events.jsonl in the state dir, making recurrence countable for
# incident-scan.py.  THE SACRED INVARIANT: the append is fail-open — the
# deny/allow JSON output, exit code, and hook-error.json behavior are
# BYTE-UNCHANGED whether the append succeeds or fails.  These tests pin both
# halves: event-appended-on-deny/error, and unwritable-events-path changes
# nothing.
# ===========================================================================

_NONCANON_HOOK_SH = _HOOKS_DIR / "block-noncanonical-blocker-write.sh"


def _read_hook_events(state_dir: Path) -> list[dict]:
    """Parse hook-events.jsonl from *state_dir* (empty list when absent)."""
    p = state_dir / "hook-events.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def test_events_longbuild_deny_appends_event():
    """Long-build deny → one kind:deny event (hook + takeover signature)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_longbuild_guard(
            _bash_preToolUse_json("tauri build"), state_dir
        )
        assert _containment_decision(result) == "deny", result.stdout
        events = _read_hook_events(state_dir)
        assert len(events) == 1, (
            f"exactly one hook-event line expected on a deny; got {events!r}"
        )
        e = events[0]
        assert e["kind"] == "deny", e
        assert e["hook"] == "long-build-ownership-guard", e
        assert e["signature"] == _LONGBUILD_TAKEOVER_SIGNATURE, e
        assert isinstance(e.get("ts"), (int, float)), e
        assert "repo_root" in e and "detail" in e, e


def test_events_longbuild_deny_byte_identical_and_fail_open_unwritable():
    """The deny JSON is byte-identical whether the events append succeeds or
    fails (hook-events.jsonl squatting as a DIRECTORY), and the failed append
    is swallowed (exit 0, no event, no crash)."""
    with tempfile.TemporaryDirectory() as td:
        ok_dir = Path(td) / "ok"
        ok_dir.mkdir()
        r_ok = _run_longbuild_guard(_bash_preToolUse_json("npm run build"), ok_dir)
        assert _containment_decision(r_ok) == "deny", r_ok.stdout
        assert len(_read_hook_events(ok_dir)) == 1

        bad_dir = Path(td) / "bad"
        bad_dir.mkdir()
        (bad_dir / "hook-events.jsonl").mkdir()  # unwritable events path
        r_bad = _run_longbuild_guard(_bash_preToolUse_json("npm run build"), bad_dir)
        assert r_bad.returncode == 0, (
            f"append failure must be swallowed (exit 0); stderr={r_bad.stderr!r}"
        )
        assert r_bad.stdout == r_ok.stdout, (
            "deny output must be BYTE-IDENTICAL whether the events append "
            f"succeeds or fails; ok={r_ok.stdout!r} bad={r_bad.stdout!r}"
        )
        assert (bad_dir / "hook-events.jsonl").is_dir(), "squatting dir must survive"


def test_events_longbuild_error_appends_error_event():
    """Malformed payload → fail-open allow + hook-error.json breadcrumb
    (unchanged) + one kind:error event beside it."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_bash(
            _LONGBUILD_GUARD_SH, "{ not json", _base_env(state_dir)
        )
        assert result.returncode == 0
        assert _containment_decision(result) != "deny"
        assert (state_dir / "hook-error.json").exists(), (
            "the existing breadcrumb write must be preserved byte-identically"
        )
        events = _read_hook_events(state_dir)
        assert len(events) == 1, events
        assert events[0]["kind"] == "error", events
        assert events[0]["hook"] == "long-build-ownership-guard", events


def test_events_noncanonical_deny_appends_event():
    """Mis-named blocker Write deny → one kind:deny event
    (signature: noncanonical-blocker; detail carries the basename)."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        payload = _straybranch_payload(
            "C:/repo/docs/bugs/x/BLOCKED_NOTES.md", "C:/repo"
        )
        result = _run_bash(_NONCANON_HOOK_SH, payload, _base_env(state_dir))
        assert _containment_decision(result) == "deny", result.stdout
        events = _read_hook_events(state_dir)
        assert len(events) == 1, events
        e = events[0]
        assert e["kind"] == "deny", e
        assert e["hook"] == "block-noncanonical-blocker-write", e
        assert e["signature"] == "noncanonical-blocker", e
        assert "BLOCKED_NOTES.md" in e["detail"], e


def test_events_noncanonical_allow_appends_nothing():
    """An allowed write (canonical BLOCKED.md) appends NO event — the appender
    fires only at deny/error sites."""
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        payload = _straybranch_payload("C:/repo/docs/bugs/x/BLOCKED.md", "C:/repo")
        result = _run_bash(_NONCANON_HOOK_SH, payload, _base_env(state_dir))
        assert _containment_decision(result) != "deny", result.stdout
        assert _read_hook_events(state_dir) == [], (
            "no event may be appended on an allow"
        )


def test_events_straybranch_deny_appends_event():
    """Stray-branch sentinel deny → one kind:deny event
    (signature: stray-branch-sentinel)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "audit/foo")
        _write_marker_with_branch(state_dir, str(repo), "main")
        payload = _straybranch_payload(str(repo / "NEEDS_INPUT.md"), str(repo))
        result = _run_bash(_STRAYBRANCH_HOOK_SH, payload, _base_env(state_dir))
        assert _containment_decision(result) == "deny", result.stdout
        events = _read_hook_events(state_dir)
        assert len(events) == 1, events
        e = events[0]
        assert e["kind"] == "deny", e
        assert e["hook"] == "block-sentinel-write-on-stray-branch", e
        assert e["signature"] == "stray-branch-sentinel", e
        assert "NEEDS_INPUT.md" in e["detail"], e


def test_events_containment_deny_appends_event():
    """Containment /lazy* Skill deny (agent_id trip) → one kind:deny event
    (signature: skill-lazy-family). (Re-pointed 2026-07-09 from the removed
    recursive-agent-dispatch deny to the retained Skill-tool deny.)"""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        result = _run_containment(
            _skill_preToolUse_json("lazy-batch", agent_id=_SUBAGENT_AGENT_ID),
            state_dir,
        )
        assert _containment_decision(result) == "deny", result.stdout
        events = _read_hook_events(state_dir)
        assert len(events) == 1, events
        e = events[0]
        assert e["kind"] == "deny", e
        assert e["hook"] == "lazy-cycle-containment", e
        assert e["signature"] == "skill-lazy-family", e


def test_events_bqe_deny_appends_event():
    """Build-queue-enforce deny → one kind:deny event (signature = the
    classified op, e.g. dotnet-build)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("dotnet build ./Cognito.sln", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(result) == "deny", result.stdout
        events = _read_hook_events(state_dir)
        assert len(events) == 1, events
        e = events[0]
        assert e["kind"] == "deny", e
        assert e["hook"] == "build-queue-enforce", e
        assert e["signature"] == "dotnet-build", e


def test_events_guard_breadcrumb_appends_error_event():
    """lazy_guard.py internal error (corrupt registry) → breadcrumb unchanged
    + one kind:error event (hook: lazy-dispatch-guard). Guard DENIES stay
    events-free (they already ledger — SPEC D2 implementation note)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)
        _write_marker_in_dir(state_dir)
        (state_dir / "lazy-prompt-registry.json").write_bytes(
            b"\xff\xfe CORRUPT \x00 NOT JSON"
        )
        result = _run_guard_py(_e1_preToolUse_json("some dispatch prompt"), env)
        assert result.returncode == 0
        assert (state_dir / "hook-error.json").exists()
        events = _read_hook_events(state_dir)
        assert len(events) == 1, events
        assert events[0]["kind"] == "error", events
        assert events[0]["hook"] == "lazy-dispatch-guard", events


def test_events_guard_deny_appends_no_event():
    """A guard DENY appends to the deny LEDGER only — no hook-events line
    (double-count guard; SPEC D2 implementation note)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = _base_env(state_dir)
        _write_marker_in_dir(state_dir)
        result = _run_guard_py(
            _e1_preToolUse_json("an unregistered hand-composed prompt"), env
        )
        payload = json.loads(result.stdout.strip())
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert _read_hook_events(state_dir) == [], (
            "guard denies must NOT append hook-events (already deny-ledgered)"
        )


# ===========================================================================
# build-queue-generalization — Phase 3 (enforcement generalization) + the D5
# arbitration seam. Locked 2026-07-09: D4-B (manifest presence primary gate +
# Cognito remote-match legacy fallback for a missing/unreadable manifest),
# D5-A (transient builds route THROUGH the queue — the ownership guard's deny
# gains an additive routing hint in manifested repos, signature unchanged),
# D7-A (workstation-only; BQE_PLATFORM_OVERRIDE=inert|armed is the test seam).
# ===========================================================================

_BQ_OPS_MANIFEST_RELPATH = Path(".claude") / "skill-config" / "build-queue-ops.json"


def _init_manifested_repo(parent: Path, ops: dict, name: str = "manifested-repo") -> Path:
    """Create a temp git repo (NO cognito remote) carrying a build-queue ops
    manifest with the given ops mapping."""
    repo = parent / name
    repo.mkdir()
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "t@t.t"], repo)
    _git(["config", "user.name", "t"], repo)
    manifest_path = repo / _BQ_OPS_MANIFEST_RELPATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"version": 1, "ops": ops}, indent=2) + "\n", encoding="utf-8"
    )
    return repo


_ALGOBOOTH_STYLE_OPS = {
    "tauri-build": {
        "exec": "scripts/tauri-build-filtered.ps1",
        "kind": "build",
        "hygiene": "rust-tauri",
        "skill": "/tauri-build",
        "deny": ["tauri build", "cargo build --release"],
    },
}


def test_bqe_manifest_denies_registered_op():
    """A manifested (non-Cognito) repo denies its registered raw op; the deny
    reason names the op's skill + the manifest path."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, _ALGOBOOTH_STYLE_OPS)
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("tauri build --verbose", str(repo)),
            _base_env(state_dir),
        )
        assert result.returncode == 0, (
            f"hook must exit 0 (deny is JSON); stderr={result.stderr!r}"
        )
        assert _containment_decision(result) == "deny", (
            f"manifested raw op must deny; stdout={result.stdout!r}"
        )
        reason = json.loads(result.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert "/tauri-build" in reason, (
            f"deny reason must name the op's skill; got {reason!r}"
        )
        assert "build-queue-ops.json" in reason, (
            f"deny reason must name the manifest; got {reason!r}"
        )


def test_bqe_manifest_denies_cd_prefixed_op():
    """`cd "..." && cargo build --release` in a manifested repo → deny (the
    manifest patterns ride the same _CMD_START segment anchor)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, _ALGOBOOTH_STYLE_OPS)
        cmd = f'cd "{repo}" && cargo build --release'
        result = _run_bash(
            _BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir)
        )
        assert _containment_decision(result) == "deny", (
            f"cd-prefixed manifested op must deny; stdout={result.stdout!r}"
        )


def test_bqe_manifest_allows_bypassed_segment():
    """Segment-aware BUILD_QUEUE_BYPASS=1 works on the manifest path too."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, _ALGOBOOTH_STYLE_OPS)
        cmd = f'cd "{repo}" && BUILD_QUEUE_BYPASS=1 tauri build'
        result = _run_bash(
            _BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir)
        )
        assert _containment_decision(result) != "deny", (
            f"bypassed segment must allow on the manifest path; "
            f"stdout={result.stdout!r}"
        )


def test_bqe_manifest_allows_reference_only():
    """A read verb referencing a manifested op token as an ARGUMENT does not
    begin a command segment → allow (invoke-vs-reference discrimination)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, _ALGOBOOTH_STYLE_OPS)
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload('grep -rn "tauri build" docs/ | head -5', str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(result) != "deny", (
            f"reference-only mention must allow; stdout={result.stdout!r}"
        )


def test_bqe_manifest_allows_wrapper_invocation():
    """The sanctioned build-queue.ps1 wrapper is exempt on the manifest path
    (the D5 no-ping-pong seam: the takeover re-launch carries the wrapper)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, _ALGOBOOTH_STYLE_OPS)
        cmd = (
            'powershell.exe -File "$HOME/.claude/scripts/build-queue.ps1" '
            '-Op tauri-build'
        )
        result = _run_bash(
            _BQE_HOOK_SH, _bqe_payload(cmd, str(repo)), _base_env(state_dir)
        )
        assert _containment_decision(result) != "deny", (
            f"wrapper invocation must stay exempt; stdout={result.stdout!r}"
        )


def test_bqe_manifest_ps1_deny_pattern():
    """A `*.ps1` manifest deny entry reuses the filtered-script shapes: the
    direct segment-leading invocation AND the powershell -File form deny; a
    `cat` reference does not."""
    ops = {
        "mybuild": {
            "exec": "scripts/my-build-filtered.ps1",
            "kind": "build",
            "hygiene": "none",
            "skill": "/mybuild",
            "deny": ["my-build-filtered.ps1"],
        },
    }
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, ops)
        direct = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("./scripts/my-build-filtered.ps1 -Fast", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(direct) == "deny", (
            f"direct ps1 invocation must deny; stdout={direct.stdout!r}"
        )
        psfile = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload(
                "powershell.exe -File scripts/my-build-filtered.ps1", str(repo)
            ),
            _base_env(state_dir),
        )
        assert _containment_decision(psfile) == "deny", (
            f"powershell -File ps1 invocation must deny; stdout={psfile.stdout!r}"
        )
        ref = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("cat scripts/my-build-filtered.ps1 | head", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(ref) != "deny", (
            f"ps1 read reference must allow; stdout={ref.stdout!r}"
        )


def test_bqe_no_manifest_non_cognito_allows_long_build():
    """No manifest + no Cognito remote → the hook is a no-op even for a raw
    long build (the ownership guard owns that command, not this hook)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "main")  # plain repo, no remote
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("tauri build", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(result) != "deny", (
            f"unmanifested non-Cognito repo must allow; stdout={result.stdout!r}"
        )


def test_bqe_cognito_broken_manifest_legacy_fallback():
    """D4: Cognito remote + UNPARSEABLE manifest → the legacy hard-coded deny
    set still fires (enforcement can never be silently disarmed)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        broken = repo / _BQ_OPS_MANIFEST_RELPATH
        broken.parent.mkdir(parents=True)
        broken.write_text("{ this is not json", encoding="utf-8")
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("dotnet build ./Cognito.sln -c Debug", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(result) == "deny", (
            f"broken manifest in a Cognito worktree must fall back to the "
            f"legacy deny set; stdout={result.stdout!r}"
        )
        reason = json.loads(result.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert "/msbuild" in reason, (
            f"legacy fallback deny must carry the legacy redirect; got {reason!r}"
        )


def test_bqe_cognito_valid_manifest_is_primary():
    """D4: a VALID manifest in a Cognito-remote repo is the primary deny
    source — its registered op denies with the manifest message; a legacy
    token the manifest does NOT register is allowed (manifest wins)."""
    ops = {
        "msbuild": {
            "exec": ".claude/scripts/build-filtered.ps1",
            "kind": "build",
            "hygiene": "dotnet",
            "skill": "/msbuild",
            "deny": ["dotnet build"],
        },
    }
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        manifest_path = repo / _BQ_OPS_MANIFEST_RELPATH
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(
            json.dumps({"version": 1, "ops": ops}) + "\n", encoding="utf-8"
        )
        denied = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("dotnet build ./Cognito.sln", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(denied) == "deny", (
            f"manifested op must deny; stdout={denied.stdout!r}"
        )
        reason = json.loads(denied.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert "build-queue-ops.json" in reason, (
            f"a valid manifest must be the deny source (manifest message), "
            f"not the legacy set; got {reason!r}"
        )
        unregistered = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("npx nx build client", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(unregistered) != "deny", (
            f"an op the valid manifest does not register must allow "
            f"(manifest is primary, legacy set not additive); "
            f"stdout={unregistered.stdout!r}"
        )


def test_bqe_platform_override_inert_allows():
    """D7: BQE_PLATFORM_OVERRIDE=inert simulates an off-workstation host —
    even a legacy Cognito deny is silently allowed."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_cognito_worktree(td)
        env = _base_env(state_dir)
        env["BQE_PLATFORM_OVERRIDE"] = "inert"
        result = _run_bash(
            _BQE_HOOK_SH,
            _bqe_payload("dotnet build ./Cognito.sln", str(repo)),
            env,
        )
        assert _containment_decision(result) != "deny", (
            f"an inert (off-workstation) host must allow everything; "
            f"stdout={result.stdout!r}"
        )


def test_longbuild_guard_manifest_routing_hint():
    """D5: in a manifested repo, the takeover deny ADDITIONALLY names the op +
    the queue-wrapper routing; the signature is still present."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_manifested_repo(td, _ALGOBOOTH_STYLE_OPS)
        result = _run_bash(
            _LONGBUILD_GUARD_SH,
            _bqe_payload("tauri build", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(result) == "deny", (
            f"long build must still deny; stdout={result.stdout!r}"
        )
        reason = json.loads(result.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert _LONGBUILD_TAKEOVER_SIGNATURE in reason, (
            f"takeover signature must survive the routing hint; got {reason!r}"
        )
        assert "tauri-build" in reason and "-Op tauri-build" in reason, (
            f"routing hint must name the manifested op + wrapper invocation; "
            f"got {reason!r}"
        )


def test_longbuild_guard_no_manifest_message_unchanged():
    """D5: without a manifest the takeover deny message is byte-identical to
    the legacy form — no routing hint, signature present."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        state_dir = td / "state"
        state_dir.mkdir()
        repo = _init_repo_on_branch(td, "main")
        result = _run_bash(
            _LONGBUILD_GUARD_SH,
            _bqe_payload("tauri build", str(repo)),
            _base_env(state_dir),
        )
        assert _containment_decision(result) == "deny"
        reason = json.loads(result.stdout.strip())["hookSpecificOutput"][
            "permissionDecisionReason"
        ]
        assert _LONGBUILD_TAKEOVER_SIGNATURE in reason
        assert "QUEUE ROUTING" not in reason and "build-queue-ops.json" not in reason, (
            f"no-manifest repo must get the legacy message with no routing "
            f"hint; got {reason!r}"
        )


def test_bq_hook_order_guard_before_enforce():
    """D5 ordering invariant: long-build-ownership-guard.sh is registered
    BEFORE build-queue-enforce.sh in the PreToolUse matcher:Bash chain, so a
    subagent's raw long build surfaces the takeover signature first."""
    settings_path = _REPO_ROOT / "user" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    pretooluse = settings.get("hooks", {}).get("PreToolUse", [])
    commands = [
        h.get("command", "")
        for block in pretooluse
        if block.get("matcher") == "Bash"
        for h in block.get("hooks", [])
    ]
    guard_idx = next(
        (i for i, c in enumerate(commands) if "long-build-ownership-guard.sh" in c),
        None,
    )
    enforce_idx = next(
        (i for i, c in enumerate(commands) if "build-queue-enforce.sh" in c),
        None,
    )
    assert guard_idx is not None and enforce_idx is not None, (
        f"both hooks must be registered in matcher:Bash; got {commands!r}"
    )
    assert guard_idx < enforce_idx, (
        f"long-build-ownership-guard.sh (idx {guard_idx}) must precede "
        f"build-queue-enforce.sh (idx {enforce_idx}) — D5 ordering invariant"
    )


_TESTS = [
    ("test_guard_files_exist",                    test_guard_files_exist),
    ("test_guard_fast_path_no_marker",            test_guard_fast_path_no_marker),
    ("test_guard_denies_unregistered_prompt",     test_guard_denies_unregistered_prompt),
    ("test_guard_allows_registered_prompt_and_consumes",
     test_guard_allows_registered_prompt_and_consumes),
    ("test_guard_idempotent_refire_same_tool_use_id",
     test_guard_idempotent_refire_same_tool_use_id),
    ("test_guard_crlf_prompt_matches",            test_guard_crlf_prompt_matches),
    ("test_guard_hardening_depth_cap",            test_guard_hardening_depth_cap),
    ("test_guard_fail_open_corrupt_registry",     test_guard_fail_open_corrupt_registry),
    ("test_inject_fast_path_no_marker",           test_inject_fast_path_no_marker),
    ("test_inject_emits_lazy_route_banner",       test_inject_emits_lazy_route_banner),
    ("test_inject_surfaces_hook_error_breadcrumb",
     test_inject_surfaces_hook_error_breadcrumb),
    ("test_pipe_tests_wsl",                       test_pipe_tests_wsl),
    # Phase 2 review items — new tests
    ("test_find_entry_by_sha_same_prompt_two_consumers",
     test_find_entry_by_sha_same_prompt_two_consumers),
    ("test_inject_unbound_marker_silent_and_unchanged",
     test_inject_unbound_marker_silent_and_unchanged),
    ("test_guard_different_session_id_silent_allow",
     test_guard_different_session_id_silent_allow),
    ("test_guard_bash_slow_path_allows_registered_prompt",
     test_guard_bash_slow_path_allows_registered_prompt),
    ("test_inject_sessionstart_compact_includes_reentry_protocol",
     test_inject_sessionstart_compact_includes_reentry_protocol),
    ("test_stale_marker_both_hooks_silent_and_deleted",
     test_stale_marker_both_hooks_silent_and_deleted),
    ("test_guard_no_prompt_key_silent_allow",
     test_guard_no_prompt_key_silent_allow),
    ("test_guard_hardening_depth_cap_stale_unconsumed",
     test_guard_hardening_depth_cap_stale_unconsumed),
    # Phase 4 — hardening depth-cap integration test (real emitted entry)
    ("test_guard_depth_cap_real_hardening_entry",
     test_guard_depth_cap_real_hardening_entry),
    # Phase 7 — deny-ledger write through the real bash hook path
    ("test_guard_bash_deny_writes_deny_ledger",
     test_guard_bash_deny_writes_deny_ledger),
    # Phase 8 — inject non-destructive against a marker bound to another session
    ("test_inject_non_owner_session_leaves_marker_intact",
     test_inject_non_owner_session_leaves_marker_intact),
    # F1b (lazy-pipeline-ergonomics Phase 1) — pure-suffix auto-readmit via bash
    ("test_guard_bash_pure_suffix_auto_readmits",
     test_guard_bash_pure_suffix_auto_readmits),
    # Phase 2 (lazy-validation-readiness) — F2b end-to-end + F2c transcription-slip deny
    ("test_f2b_emdash_slip_allows_via_guard", test_f2b_emdash_slip_allows_via_guard),
    ("test_f2c_near_copy_slip_deny_no_ledger_append",
     test_f2c_near_copy_slip_deny_no_ledger_append),
    ("test_f2c_genuinely_unregistered_deny_appends_ledger",
     test_f2c_genuinely_unregistered_deny_appends_ledger),
    # Phase 3 (lazy-validation-readiness) — F2a dispatch-by-reference guard tests
    ("test_f2a_guard_ref_fresh_allows_with_updated_input",
     test_f2a_guard_ref_fresh_allows_with_updated_input),
    ("test_f2a_guard_ref_consumed_nonce_denies",
     test_f2a_guard_ref_consumed_nonce_denies),
    ("test_f2a_guard_ref_nonexistent_nonce_denies",
     test_f2a_guard_ref_nonexistent_nonce_denies),
    ("test_f2a_guard_ref_stale_nonce_denies",
     test_f2a_guard_ref_stale_nonce_denies),
    ("test_f2a_guard_ref_hardening_class_allows_and_acks",
     test_f2a_guard_ref_hardening_class_allows_and_acks),
    ("test_f2a_guard_ref_malformed_falls_through_to_normal_deny",
     test_f2a_guard_ref_malformed_falls_through_to_normal_deny),
    # Phase 7 (lazy-validation-readiness) — meta dispatch-by-reference via --emit-dispatch
    ("test_p7_meta_dispatch_by_reference_via_guard",
     test_p7_meta_dispatch_by_reference_via_guard),
    # Phase 4 (lazy-cycle-containment C2) — PreToolUse containment hook
    ("test_containment_hook_file_exists",         test_containment_hook_file_exists),
    ("test_containment_fast_path_no_marker_allows",
     test_containment_fast_path_no_marker_allows),
    ("test_containment_denies_next_route_probe",
     test_containment_denies_next_route_probe),
    ("test_containment_denies_loop_formation_flags",
     test_containment_denies_loop_formation_flags),
    ("test_containment_denies_lifecycle_commands",
     test_containment_denies_lifecycle_commands),
    ("test_containment_allows_narrow_ops",        test_containment_allows_narrow_ops),
    ("test_containment_allows_unrelated_bash",    test_containment_allows_unrelated_bash),
    ("test_containment_allows_recursive_agent_dispatch",
     test_containment_allows_recursive_agent_dispatch),
    ("test_containment_denies_second_feature_commit",
     test_containment_denies_second_feature_commit),
    ("test_containment_allows_same_feature_commit",
     test_containment_allows_same_feature_commit),
    ("test_containment_allows_carve_out_commit",
     test_containment_allows_carve_out_commit),
    ("test_containment_increments_commit_tally_on_allow",
     test_containment_increments_commit_tally_on_allow),
    ("test_containment_commit_count_backstop_denies",
     test_containment_commit_count_backstop_denies),
    ("test_containment_fail_open_on_malformed_json",
     test_containment_fail_open_on_malformed_json),
    # hardening-blind-to-process-friction Phase 1 (D4) — agent_id-targeted trip
    ("test_containment_agentid_present_allows_recursive_agent_no_marker",
     test_containment_agentid_present_allows_recursive_agent_no_marker),
    ("test_containment_agentid_absent_allows_main_thread_agent_no_marker",
     test_containment_agentid_absent_allows_main_thread_agent_no_marker),
    ("test_containment_agentid_present_allows_recursive_agent_with_marker",
     test_containment_agentid_present_allows_recursive_agent_with_marker),
    ("test_containment_agentid_present_denies_lazy_batch_invocation",
     test_containment_agentid_present_denies_lazy_batch_invocation),
    ("test_containment_agentid_present_allows_lazy_batch_path_reference",
     test_containment_agentid_present_allows_lazy_batch_path_reference),
    ("test_containment_agentid_present_denies_lazy_batch_invocation_extra_forms",
     test_containment_agentid_present_denies_lazy_batch_invocation_extra_forms),
    ("test_containment_agentid_absent_allows_lazy_batch_invocation",
     test_containment_agentid_absent_allows_lazy_batch_invocation),
    ("test_containment_agentid_present_denies_routing_flags_no_marker",
     test_containment_agentid_present_denies_routing_flags_no_marker),
    ("test_containment_agentid_absent_allows_routing_flags_no_marker",
     test_containment_agentid_absent_allows_routing_flags_no_marker),
    ("test_containment_agentid_present_denies_lifecycle_no_marker",
     test_containment_agentid_present_denies_lifecycle_no_marker),
    ("test_containment_agentid_absent_allows_lifecycle_no_marker",
     test_containment_agentid_absent_allows_lifecycle_no_marker),
    ("test_containment_agentid_present_allows_unrelated_bash",
     test_containment_agentid_present_allows_unrelated_bash),
    ("test_containment_agentid_present_allows_narrow_ops",
     test_containment_agentid_present_allows_narrow_ops),
    # cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE, C2 side) —
    # --cycle-end/--cycle-begin in LOOP_FORMATION_FLAGS
    ("test_containment_agentid_present_denies_cycle_bracket_no_marker",
     test_containment_agentid_present_denies_cycle_bracket_no_marker),
    ("test_containment_agentid_present_denies_cycle_bracket_bug_state",
     test_containment_agentid_present_denies_cycle_bracket_bug_state),
    ("test_containment_agentid_absent_allows_cycle_bracket",
     test_containment_agentid_absent_allows_cycle_bracket),
    # cycle-subagent-runs-orchestrator-work Phase 3 — Skill-tool intercept
    ("test_containment_skill_subagent_denies_lazy_family",
     test_containment_skill_subagent_denies_lazy_family),
    ("test_containment_skill_subagent_allows_non_lazy_skill",
     test_containment_skill_subagent_allows_non_lazy_skill),
    ("test_containment_skill_main_thread_allows_lazy_family",
     test_containment_skill_main_thread_allows_lazy_family),
    ("test_containment_skill_fail_open_missing_skill_field",
     test_containment_skill_fail_open_missing_skill_field),
    ("test_containment_skill_fail_open_null_skill_field",
     test_containment_skill_fail_open_null_skill_field),
    # multi-repo-concurrent-runs (Phase 2 / WU-2.4) — two-repo isolation harness
    ("test_guard_two_repo_isolation_crossrepo_noop_samerepo_enforces",
     test_guard_two_repo_isolation_crossrepo_noop_samerepo_enforces),
    ("test_inject_two_repo_isolation_crossrepo_noop_samerepo_injects",
     test_inject_two_repo_isolation_crossrepo_noop_samerepo_injects),
    # stale-marker-arms-validate-deny-on-unrelated-dispatches Phase 1 (D1) —
    # over-fire regression: session-scoped gate (handler honors owner scoping;
    # the hook now passes --session-id so a non-owner fast-path-allows at the
    # gate WITHOUT invoking the guard; owner still denies + ledgers).
    ("test_marker_present_non_owner_session_reports_absent",
     test_marker_present_non_owner_session_reports_absent),
    ("test_guard_hook_wires_session_id_into_marker_present",
     test_guard_hook_wires_session_id_into_marker_present),
    ("test_guard_bash_non_owner_session_gate_does_not_invoke_guard",
     test_guard_bash_non_owner_session_gate_does_not_invoke_guard),
    ("test_guard_bash_owner_session_gate_still_denies_and_ledgers",
     test_guard_bash_owner_session_gate_still_denies_and_ledgers),
    # stale-marker-arms-validate-deny-on-unrelated-dispatches Phase 2 (D2) —
    # pre-bind no-debt deny: unbound marker → no ledger/no debt; bound marker →
    # still ledgers + accrues debt; hardening cap stays ledgered (scope guard).
    ("test_guard_unbound_marker_deny_writes_no_ledger_no_debt",
     test_guard_unbound_marker_deny_writes_no_ledger_no_debt),
    ("test_guard_bound_marker_deny_still_ledgers_and_accrues_debt",
     test_guard_bound_marker_deny_still_ledgers_and_accrues_debt),
    ("test_guard_unbound_marker_hardening_cap_still_ledgers",
     test_guard_unbound_marker_hardening_cap_still_ledgers),
    # long-build-and-runtime-ownership Phase 3 (WU-1) — long-build-ownership
    # guard: deny exact long-build signatures (env-prefix tolerant) with the
    # takeover signature; allow short/lint/check; fail-open on malformed; non-Bash
    # allow; registered in settings.json (mount-site).
    ("test_longbuild_guard_file_exists", test_longbuild_guard_file_exists),
    ("test_longbuild_guard_denies_tauri_build",
     test_longbuild_guard_denies_tauri_build),
    ("test_longbuild_guard_denies_cargo_build_release",
     test_longbuild_guard_denies_cargo_build_release),
    ("test_longbuild_guard_denies_npm_run_build",
     test_longbuild_guard_denies_npm_run_build),
    ("test_longbuild_guard_env_prefix_tolerance",
     test_longbuild_guard_env_prefix_tolerance),
    ("test_longbuild_guard_allows_false_positive_scope",
     test_longbuild_guard_allows_false_positive_scope),
    ("test_longbuild_guard_fail_open_on_malformed_json",
     test_longbuild_guard_fail_open_on_malformed_json),
    ("test_longbuild_guard_non_bash_tool_allows",
     test_longbuild_guard_non_bash_tool_allows),
    ("test_longbuild_guard_registered_in_settings",
     test_longbuild_guard_registered_in_settings),
    # cycle-subagent-fabricates-policy-or-stray-branch Phase 3 (WU-4 + WU-5) —
    # block-sentinel-write-on-stray-branch.sh: deny a sentinel write on a stray
    # branch (deny names the work branch); allow on the work branch / no marker /
    # non-sentinel / non-Write tool / malformed payload (fail-OPEN); registered.
    ("test_straybranch_hook_file_exists", test_straybranch_hook_file_exists),
    ("test_straybranch_denies_sentinel_on_stray_branch",
     test_straybranch_denies_sentinel_on_stray_branch),
    ("test_straybranch_allows_sentinel_on_work_branch",
     test_straybranch_allows_sentinel_on_work_branch),
    ("test_straybranch_fail_open_no_marker",
     test_straybranch_fail_open_no_marker),
    ("test_straybranch_allows_non_sentinel_target",
     test_straybranch_allows_non_sentinel_target),
    ("test_straybranch_fail_open_malformed_json",
     test_straybranch_fail_open_malformed_json),
    ("test_straybranch_non_write_tool_allows",
     test_straybranch_non_write_tool_allows),
    ("test_straybranch_registered_in_settings",
     test_straybranch_registered_in_settings),
    # build-queue-enforce-cd-prefix-bypass — unanchored deny in
    # build-queue-enforce.sh: a heavy build anywhere in the command denies
    # (cd-prefix / pipeline / compound), while the wrapper, safe sub-commands,
    # bare restore, BUILD_QUEUE_BYPASS=1, and non-Cognito worktrees stay allowed.
    ("test_bqe_denies_cd_prefixed_dotnet_build",
     test_bqe_denies_cd_prefixed_dotnet_build),
    ("test_bqe_denies_cd_prefixed_dotnet_test",
     test_bqe_denies_cd_prefixed_dotnet_test),
    ("test_bqe_denies_dotnet_build_in_pipeline",
     test_bqe_denies_dotnet_build_in_pipeline),
    ("test_bqe_denies_restore_then_build_compound",
     test_bqe_denies_restore_then_build_compound),
    ("test_bqe_allows_bare_restore", test_bqe_allows_bare_restore),
    ("test_bqe_allows_build_queue_wrapper_with_filtered_exec",
     test_bqe_allows_build_queue_wrapper_with_filtered_exec),
    ("test_bqe_allows_bypass_token_with_cd_prefixed_build",
     test_bqe_allows_bypass_token_with_cd_prefixed_build),
    ("test_bqe_denies_cd_prefixed_filtered_script",
     test_bqe_denies_cd_prefixed_filtered_script),
    ("test_bqe_denies_cd_prefixed_nx_build",
     test_bqe_denies_cd_prefixed_nx_build),
    ("test_bqe_allows_outside_cognito_worktree",
     test_bqe_allows_outside_cognito_worktree),
    ("test_bqe_fail_open_malformed_json", test_bqe_fail_open_malformed_json),
    # build-queue-recycle-kills-concurrent-worktree-build (test-agent addendum)
    # — build-queue-enforce.sh's UNANCHORED deny regexes wrongly deny a
    # read-only command that merely REFERENCES a build token. The
    # *-filtered.ps1-as-read-argument ALLOW cases (grep/find/cat|head) are
    # the genuine RED regression; the rest are guard/regression coverage.
    ("test_bqe_allows_cat_results_json", test_bqe_allows_cat_results_json),
    ("test_bqe_allows_grep_filtered_script", test_bqe_allows_grep_filtered_script),
    ("test_bqe_allows_tail_build_log", test_bqe_allows_tail_build_log),
    ("test_bqe_allows_find_filtered_script", test_bqe_allows_find_filtered_script),
    ("test_bqe_allows_cat_filtered_script_piped_head",
     test_bqe_allows_cat_filtered_script_piped_head),
    ("test_bqe_allows_git_diff_settings", test_bqe_allows_git_diff_settings),
    ("test_bqe_denies_bare_dotnet_build", test_bqe_denies_bare_dotnet_build),
    ("test_bqe_denies_powershell_file_filtered_script",
     test_bqe_denies_powershell_file_filtered_script),
    ("test_bqe_denies_direct_filtered_script_dot_slash",
     test_bqe_denies_direct_filtered_script_dot_slash),
    # build-queue-enforce-cd-prefix-bypass — same cd-prefix fix in
    # long-build-ownership-guard.sh for its long-build set.
    ("test_longbuild_guard_denies_cd_prefixed_cargo_build_release",
     test_longbuild_guard_denies_cd_prefixed_cargo_build_release),
    ("test_longbuild_guard_denies_cd_prefixed_tauri_build",
     test_longbuild_guard_denies_cd_prefixed_tauri_build),
    ("test_longbuild_guard_denies_cd_prefixed_npm_run_build",
     test_longbuild_guard_denies_cd_prefixed_npm_run_build),
    # build-queue-recycle-kills-concurrent-worktree-build (test-agent addendum)
    # — regression pins: the long-build guard already discriminates a
    # read-verb arg reference from a command-head invocation.
    ("test_longbuild_guard_allows_cat_referencing_cargo_build",
     test_longbuild_guard_allows_cat_referencing_cargo_build),
    ("test_longbuild_guard_allows_grep_referencing_tauri_build",
     test_longbuild_guard_allows_grep_referencing_tauri_build),
    ("test_longbuild_guard_allows_find_referencing_npm_run_build",
     test_longbuild_guard_allows_find_referencing_npm_run_build),
    # incident-auto-capture Phase 1 (D2) — hook-events.jsonl appender: every
    # hook-level deny/error site appends one countable event line; the append
    # is fail-open (deny/allow output byte-unchanged either way); guard denies
    # stay events-free (already deny-ledgered).
    ("test_events_longbuild_deny_appends_event",
     test_events_longbuild_deny_appends_event),
    ("test_events_longbuild_deny_byte_identical_and_fail_open_unwritable",
     test_events_longbuild_deny_byte_identical_and_fail_open_unwritable),
    ("test_events_longbuild_error_appends_error_event",
     test_events_longbuild_error_appends_error_event),
    ("test_events_noncanonical_deny_appends_event",
     test_events_noncanonical_deny_appends_event),
    ("test_events_noncanonical_allow_appends_nothing",
     test_events_noncanonical_allow_appends_nothing),
    ("test_events_straybranch_deny_appends_event",
     test_events_straybranch_deny_appends_event),
    ("test_events_containment_deny_appends_event",
     test_events_containment_deny_appends_event),
    ("test_events_bqe_deny_appends_event",
     test_events_bqe_deny_appends_event),
    ("test_events_guard_breadcrumb_appends_error_event",
     test_events_guard_breadcrumb_appends_error_event),
    ("test_events_guard_deny_appends_no_event",
     test_events_guard_deny_appends_no_event),
    # build-queue-generalization Phase 3 + D5 seam — manifest-driven deny set
    # (locked D4-B), guard routing hint (locked D5-A), platform gate (locked
    # D7-A), hook-order invariant.
    ("test_bqe_manifest_denies_registered_op",
     test_bqe_manifest_denies_registered_op),
    ("test_bqe_manifest_denies_cd_prefixed_op",
     test_bqe_manifest_denies_cd_prefixed_op),
    ("test_bqe_manifest_allows_bypassed_segment",
     test_bqe_manifest_allows_bypassed_segment),
    ("test_bqe_manifest_allows_reference_only",
     test_bqe_manifest_allows_reference_only),
    ("test_bqe_manifest_allows_wrapper_invocation",
     test_bqe_manifest_allows_wrapper_invocation),
    ("test_bqe_manifest_ps1_deny_pattern",
     test_bqe_manifest_ps1_deny_pattern),
    ("test_bqe_no_manifest_non_cognito_allows_long_build",
     test_bqe_no_manifest_non_cognito_allows_long_build),
    ("test_bqe_cognito_broken_manifest_legacy_fallback",
     test_bqe_cognito_broken_manifest_legacy_fallback),
    ("test_bqe_cognito_valid_manifest_is_primary",
     test_bqe_cognito_valid_manifest_is_primary),
    ("test_bqe_platform_override_inert_allows",
     test_bqe_platform_override_inert_allows),
    ("test_longbuild_guard_manifest_routing_hint",
     test_longbuild_guard_manifest_routing_hint),
    ("test_longbuild_guard_no_manifest_message_unchanged",
     test_longbuild_guard_no_manifest_message_unchanged),
    ("test_bq_hook_order_guard_before_enforce",
     test_bq_hook_order_guard_before_enforce),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("test_hooks.py — Phase 2 hook pipe-tests")
    print("=" * 60)

    if _IMPORT_ERROR is not None:
        print(f"\nREQUIRED MODULE MISSING: {_IMPORT_ERROR}")
        print("lazy_core must be importable (Phase 1 complete) to run these tests.\n")

    print()
    for name, fn in _TESTS:
        _run_test(name, fn)

    total   = len(_TESTS)
    passed  = len(_PASSES)
    skipped = len(_SKIPPED)
    failed  = len(_FAILURES)

    print()
    print("=" * 60)
    print(f"Results: {passed}/{total} passed, {skipped} skipped, {failed} failed")
    if _SKIPPED:
        print("\nSkipped tests (legitimate):")
        for s in _SKIPPED:
            print(f"  - {s}")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        print()
        return 1
    print("\nAll tests passed (or legitimately skipped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
