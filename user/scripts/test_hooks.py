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


class _TestSkip(Exception):
    """Raised to signal a legitimate SKIP (not a failure)."""


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
) -> str:
    """Return a JSON string matching the E1 PreToolUse hook-input shape captured
    in RUNTIME_SPIKE.md.  This is the ground-truth fixture shape.

    Fields present in the spike capture:
      session_id, transcript_path, cwd, permission_mode, hook_event_name,
      tool_name ("Agent"), tool_input.{description, prompt, subagent_type},
      tool_use_id
    """
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
) -> str:
    """Return a JSON string matching the E1/E3 UserPromptSubmit hook-input shape."""
    if session_id is None:
        session_id = str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "transcript_path": f"C:\\\\Users\\\\Jacob\\\\.claude\\\\projects\\\\test\\\\{session_id}.jsonl",
        "cwd": "C:\\\\Users\\\\Jacob\\\\AppData\\\\Local\\\\Temp\\\\spike-turn-routing",
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


def _write_marker_in_dir(state_dir: Path, repo_root: str | None = None) -> None:
    """Write a fresh (non-stale) run marker into *state_dir* via lazy_core."""
    _set_state_dir(state_dir)
    try:
        lazy_core.write_run_marker(
            pipeline="feature",
            cloud=False,
            repo_root=repo_root or str(state_dir / "fixture-repo"),
            max_cycles=10,
            now=time.time(),
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

        _write_marker_in_dir(state_dir)

        the_prompt = "Execute the planned implementation step."
        tool_use_id_a = "toolu_" + uuid.uuid4().hex[:24]

        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()

        # First call — allow and consume (establishes consumed_by = tool_use_id_a).
        stdin_a = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_a)
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

        # Third call with a DIFFERENT tool_use_id — must deny.
        tool_use_id_b = "toolu_" + uuid.uuid4().hex[:24]
        stdin_b = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_b)
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

        _write_marker_in_dir(state_dir)

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
        stdin_orig = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_original)
        result_first = _run_guard_py(stdin_orig, env)
        first_payload = json.loads(result_first.stdout.strip())
        assert first_payload["hookSpecificOutput"]["permissionDecision"] == "allow", (
            "First hardening dispatch must be allowed"
        )

        # Now a DIFFERENT tool_use_id tries to dispatch the same (now-consumed)
        # hardening entry — this is depth-1 deny of a hardening-class entry.
        stdin_other = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_other)
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

        # Write marker pointing at the fixture repo.
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
            )
        finally:
            _clear_state_dir()

        stdin_text = _userPromptSubmit_json()
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

        # Write marker.
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
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

        stdin_text = _userPromptSubmit_json()
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
    # Check if wsl is on PATH.
    wsl_check = subprocess.run(
        ["wsl", "bash", "-c", "echo OK"],
        capture_output=True, text=True, timeout=15,
    )
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

        _write_marker_in_dir(state_dir)

        the_prompt = "Run next cycle step — shared prompt text for two registrations."
        tool_use_id_a = "toolu_" + uuid.uuid4().hex[:24]
        tool_use_id_b = "toolu_" + uuid.uuid4().hex[:24]

        # Register first emission and consume it as A.
        _set_state_dir(state_dir)
        try:
            lazy_core.register_emission(the_prompt, cls="cycle")
        finally:
            _clear_state_dir()
        stdin_a = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_a)
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
        stdin_b = _e1_preToolUse_json(the_prompt, tool_use_id=tool_use_id_b)
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

def test_inject_stamps_session_id_when_unbound():
    """Item 2: when the run marker has session_id=None, the inject hook must
    stamp it with the hook-input's session_id (bind-on-first-hook-firing).
    Verified by reading the marker FILE after the inject hook runs.
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

        # Verify the marker starts unbound.
        marker_path = state_dir / "lazy-run-marker.json"
        marker_before = json.loads(marker_path.read_text(encoding="utf-8"))
        assert marker_before.get("session_id") is None, (
            f"marker must start with session_id=None; got {marker_before.get('session_id')!r}"
        )

        # Run the inject hook with a specific session_id.
        the_session_id = str(uuid.uuid4())
        stdin_text = _userPromptSubmit_json(session_id=the_session_id)
        result = _run_bash(_INJECT_SH, stdin_text, env)

        assert result.returncode == 0, (
            f"inject hook must exit 0; stderr: {result.stderr!r}"
        )

        # Read the marker file and verify session_id was stamped.
        marker_after = json.loads(marker_path.read_text(encoding="utf-8"))
        assert marker_after.get("session_id") == the_session_id, (
            f"inject hook must stamp marker with session_id {the_session_id!r}; "
            f"got {marker_after.get('session_id')!r}"
        )


# ---------------------------------------------------------------------------
# Test 15 — guard: marker bound to different session_id → silent allow (stale)
# ---------------------------------------------------------------------------

def test_guard_different_session_id_silent_allow():
    """Item 2: when the marker is bound to a different session_id, the guard
    must treat the marker as stale (path B), delete it, and silently allow
    (exit 0, no output) — as if no marker were present.
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

        # The marker file must have been deleted (stale cleanup).
        marker_path = state_dir / "lazy-run-marker.json"
        assert not marker_path.exists(), (
            "guard must delete the stale marker (different session_id path B cleanup)"
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

        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=time.time(),
            )
        finally:
            _clear_state_dir()

        # Build a SessionStart with source=compact.
        the_session_id = str(uuid.uuid4())
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
        _write_marker_in_dir(state_dir)

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
        stdin_allow = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_original)
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
        stdin_deny = _e1_preToolUse_json(hardening_prompt, tool_use_id=tool_use_id_other)
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
# Test registry
# ---------------------------------------------------------------------------

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
    ("test_inject_stamps_session_id_when_unbound",
     test_inject_stamps_session_id_when_unbound),
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
