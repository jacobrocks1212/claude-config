#!/usr/bin/env python3
"""
test_runtimeplane.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_runtimeplane.py
Exit 0 on pass, non-zero on any failure. No third-party dependencies.
"""

from __future__ import annotations

import ast
import difflib
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# This file lives 2 directories deeper than the original flat
# test_lazy_core.py (user/scripts/tests/test_lazy_core/ vs. user/scripts/),
# so parents[2] is the scripts dir where lazy_core/ actually lives:
# parents[0]=test_lazy_core/, parents[1]=tests/, parents[2]=user/scripts.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))



from _util import _ModuleMissing, _M4_CONFIG, _M4_CONFIG_BOOT, _M4_CONFIG_FRONTEND, _M4_KEYS, _SESSION, _build_no_plans_verification_only_repo, _collect_orphaned_test_names, _load_lazy_state_module, _load_state_script, _make_git_repo_with_origin, _make_git_tree, _owned_lock, _t  # noqa: E402




# ---------------------------------------------------------------------------
# Attempt the import — RED today, GREEN after extraction.
# ---------------------------------------------------------------------------

_IMPORT_ERROR: Exception | None = None


lazy_core = None



try:
    import lazy_core  # type: ignore[import]
except ImportError as exc:
    _IMPORT_ERROR = exc




# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_FAILURES: list[str] = []


_PASSES: list[str] = []




def _guard() -> None:
    """Raise _ModuleMissing if lazy_core hasn't been extracted yet.

    Call at the top of every test function so that, while in RED state, each
    test cleanly fails with a consistent reason rather than an AttributeError
    on the None module.
    """
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"lazy_core not importable: {_IMPORT_ERROR}")




def _run_test(name: str, fn) -> None:
    """Run a single test, recording PASS or FAIL."""
    try:
        fn()
        _PASSES.append(name)
        print(f"  PASS  {name}")
    except _ModuleMissing as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except AssertionError as exc:
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        _FAILURES.append(name)
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")





def test_bug_state_algobooth_baseline_wellformed():
    """user/scripts/tests/baselines/bug-state-algobooth.json parses as JSON and
    contains the core structural keys expected for a bug-state AlgoBooth snapshot.

    This is a drift-tolerant structural contract — exact values are NOT asserted
    because the AlgoBooth tree evolves.  The baseline file now exists and this test
    is a steady-state structural contract.
    """
    # No _guard() — does not require lazy_core to be importable.
    baseline_path = (
        _SCRIPTS_DIR / "tests" / "baselines" / "bug-state-algobooth.json"
    )
    # The baseline file exists; FileNotFoundError here would indicate it was accidentally deleted.
    raw = baseline_path.read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"bug-state-algobooth.json is not valid JSON: {exc}"
        ) from exc

    assert isinstance(data, dict), (
        f"bug-state-algobooth.json must be a JSON object (dict), got {type(data).__name__}"
    )

    required_keys = {
        "feature_id",
        "current_step",
        "sub_skill",
        "terminal_reason",
        "diagnostics",
        "operator_deferred",
    }
    missing = required_keys - set(data.keys())
    assert not missing, (
        f"bug-state-algobooth.json is missing required keys: {sorted(missing)}"
    )




def test_lazy_state_no_plans_real_impl_row_still_write_plan():
    """Guard the inverse: NO plans/ dir but a genuine implementation row still
    unchecked (verification_only False) must STILL route to write-plan — the fix
    must not blanket-bypass features with real pending implementation work."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_no_plans_verification_only_repo(Path(td))
        # Re-open a real (non-verification) implementation row.
        fdir = Path(td) / "docs" / "features" / "feat-noplan"
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n- [x] Impl one\n\n"
            "### Phase 2\n- [ ] Impl two still open\n\n"
            "### Runtime Verification\n- [ ] MCP test only\n",
            encoding="utf-8",
        )
        state = ls.compute_state(root, False)
    assert state["sub_skill"] == "write-plan", state




# --- WU-2: probe primitives -------------------------------------------------

class _FakeCompleted:
    """Minimal subprocess.CompletedProcess stand-in for hermetic probe tests."""

    def __init__(self, returncode):
        self.returncode = returncode




def test_probe_binary_capability_exit_zero_true():
    """Injected run returning exit 0 ⇒ True."""
    _guard()
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _FakeCompleted(0)

    assert lazy_core.probe_binary_capability(["tool", "--version"], run=run) is True
    assert calls, "the injected run must have been invoked (active invocation)"




def test_probe_binary_capability_exit_nonzero_false():
    """Injected run returning exit 1 ⇒ False."""
    _guard()
    assert (
        lazy_core.probe_binary_capability(
            ["tool", "--version"], run=lambda *a, **k: _FakeCompleted(1)
        )
        is False
    )




def test_probe_binary_capability_windowsapps_alias_false():
    """The \\WindowsApps zero-byte App-Execution-Alias false-positive guard:
    an injected run simulating the alias (non-zero exit / would-hang surrogate)
    ⇒ False. Asserts the active-invocation contract, NOT a which()/exists()
    presence check."""
    _guard()

    def alias_run(argv, **kwargs):
        # The alias stub resolves on PATH but exits non-zero on invocation
        # (the GUI Store prompt path is surrogated as a timeout/non-zero exit).
        return _FakeCompleted(9009)  # cmd.exe "not recognized" style code

    assert lazy_core.probe_binary_capability(["python3", "--version"], run=alias_run) is False




def test_probe_binary_capability_run_error_false():
    """An injected run that raises (timeout / OSError) ⇒ False, never propagates."""
    _guard()

    def boom(argv, **kwargs):
        raise OSError("would hang")

    assert lazy_core.probe_binary_capability(["x"], run=boom) is False




def test_probe_env_capability_set_unset_falsy():
    """Env probe: set truthy ⇒ True; unset ⇒ False; falsy value ⇒ False."""
    _guard()
    assert lazy_core.probe_env_capability("CAP", environ={"CAP": "1"}) is True
    assert lazy_core.probe_env_capability("CAP", environ={}) is False
    for falsy in ("0", "", "false", "no", "off"):
        assert (
            lazy_core.probe_env_capability("CAP", environ={"CAP": falsy}) is False
        ), f"falsy value {falsy!r} must read as absent"




# ===========================================================================
# unified-pipeline-orchestrator Phase 5 — first three subcommands
# ===========================================================================
#
# WU-1: ensure_runtime() — structured runtime status with INJECTED probe / now
#       / restart / stale_check (no real network, deterministic).
# WU-2: gate_coverage() — symlink-resolving Gate-1 verdict.
# WU-3: apply_pseudo __mark_complete__ enhancement — ROADMAP strike + resolved
#       spec_dir queue trim (the -followups regression).
# ---------------------------------------------------------------------------


# ---- WU-1: ensure_runtime ----

_ENSURE_RUNTIME_CONFIG = {
    "health_url": "http://localhost:3333/health",
    "restart_command": "npm run dev:restart",
    "mcp_tool_name": "render_chart",
    "native_globs": ["src-tauri", "crates"],
}




def test_ensure_runtime_symbol_present():
    _guard()
    assert hasattr(lazy_core, "ensure_runtime"), (
        "lazy_core.ensure_runtime is missing"
    )




def test_ensure_runtime_down_returns_booted():
    """Runtime down (probe returns non-200 first, 200 after restart) → status
    'booted'; mcp_tools_present reflects the post-boot payload."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"probe": 0, "restart": 0}

        def probe():
            calls["probe"] += 1
            if calls["probe"] == 1:
                return (0, None)  # down on first probe
            return (200, {"tools": ["render_chart"]})

        def restart():
            calls["restart"] += 1
            return True

        def stale_check():
            raise AssertionError("stale_check must not run when runtime is down")

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_ENSURE_RUNTIME_CONFIG,
            probe=probe,
            restart=restart,
            stale_check=stale_check,
        )
        assert result["status"] == "booted", result
        assert result["mcp_tools_present"] is True, result
        assert calls["restart"] == 1, result




def test_ensure_runtime_up_and_current_returns_ready():
    """Runtime up (200) + not stale → status 'ready'; no restart called."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0}

        def probe():
            return (200, {"tools": ["render_chart", "list_charts"]})

        def restart():
            calls["restart"] += 1
            return True

        def stale_check():
            return False  # current

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_ENSURE_RUNTIME_CONFIG,
            probe=probe,
            restart=restart,
            stale_check=stale_check,
        )
        assert result["status"] == "ready", result
        assert result["mcp_tools_present"] is True, result
        assert calls["restart"] == 0, "must NOT restart a current, live runtime"




def test_ensure_runtime_up_but_stale_returns_stale_rebuilt():
    """Runtime up (200) but stale binary → restart → status 'stale-rebuilt'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0, "probe": 0}

        def probe():
            calls["probe"] += 1
            return (200, {"tools": ["render_chart"]})

        def restart():
            calls["restart"] += 1
            return True

        def stale_check():
            return True  # stale → force rebuild

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_ENSURE_RUNTIME_CONFIG,
            probe=probe,
            restart=restart,
            stale_check=stale_check,
        )
        assert result["status"] == "stale-rebuilt", result
        assert result["mcp_tools_present"] is True, result
        assert calls["restart"] == 1, "stale runtime must trigger exactly one restart"




def test_ensure_runtime_mcp_tool_absent_sets_false():
    """When the configured MCP tool is NOT in the post-boot payload,
    mcp_tools_present must be False (the assertion is meaningful)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:

        def probe():
            return (200, {"tools": ["some_other_tool"]})

        def stale_check():
            return False

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_ENSURE_RUNTIME_CONFIG,
            probe=probe,
            restart=lambda: True,
            stale_check=stale_check,
        )
        assert result["status"] == "ready", result
        assert result["mcp_tools_present"] is False, (
            "configured MCP tool absent from payload but mcp_tools_present True"
        )




# ---------------------------------------------------------------------------
# ensure-runtime-legacy-mode-optimistic-ready-verdict (Phase 1, WU-2) — the
# legacy branch must derive its verdict from the post-restart() re-probe code
# instead of hard-setting status='booted'. A still-dead runtime (re-probe still
# non-200, frontend down) must NEVER return state: READY with a non-200
# health_code — the honest invariant the M4 path already guarantees.
# ---------------------------------------------------------------------------

# A legacy-mode config with NO :1420 frontend key (claude-config / any non-:1420
# repo) — the frontend signal binds `lambda: False`, so a non-serving re-probe
# classifies `dead` (byte-identical to a bare DEAD route, the repo-agnostic path).
_LEGACY_NO_FRONTEND_CONFIG = {
    "health_url": "http://localhost:3333/health",
    "restart_command": "npm run dev:restart",
    "mcp_tool_name": "",  # vacuous default — the SPEC Open Question 3 surface
    "native_globs": ["src-tauri", "crates"],
    "lock_filename": ".runtime.lock.json",
    "port": 3333,
    "frontend_health_url": "",  # no :1420 → frontend_probe binds lambda: False
}




def test_ensure_runtime_legacy_down_still_non200_is_not_ready():
    """Legacy mode (live_session_id=None, no lock), runtime down, re-probe STILL
    non-200 with the frontend down → the verdict is a DEAD-class non-READY state,
    health_code is the honest non-200, and restart() was attempted (bounded). This
    is the SPEC's verified symptom: the pre-fix code returns state: READY,
    health_code: 0 here — the optimistic verdict this fix kills.

    RED before WU-1: today's legacy down-arm hard-sets status='booted'
    (_LEGACY_STATUS_TO_STATE['booted'] == 'READY') so result['state'] == 'READY'
    with health_code == 0 — exactly the lie this asserts against.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0, "sleep": 0}

        def probe():
            return (0, None)  # down on EVERY probe (first + post-restart re-probe)

        def restart():
            calls["restart"] += 1
            return True

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_LEGACY_NO_FRONTEND_CONFIG,
            probe=probe,
            restart=restart,
            stale_check=lambda: False,
            live_session_id=None,  # LEGACY mode — no identity
            sleep=lambda s: calls.__setitem__("sleep", calls["sleep"] + 1),
        )
        # The honest invariant: never READY with a non-200 health_code.
        assert result["state"] != "READY", result
        assert result["state"] in {"DEAD", "BLOCKED"}, result
        assert result["health_code"] != 200, result
        assert not (result["state"] == "READY" and result["health_code"] != 200), result
        # restart() was attempted to try to recover the down runtime (bounded).
        assert calls["restart"] >= 1, f"a down runtime must attempt restart: {calls}"
        # mcp_tools_present must NOT be vacuously True for a non-serving runtime
        # when no tool name is configured (SPEC Open Question 3, resolved in-cycle).
        assert result["mcp_tools_present"] is False, (
            "non-serving legacy runtime with empty tool name must NOT claim "
            f"mcp_tools_present True: {result}"
        )




def test_ensure_runtime_m4_vs_legacy_never_ready_when_non200():
    """M4-vs-legacy parity: for the SAME down-then-still-down probe sequence,
    NEITHER the M4 path (lock + live_session_id) NOR the legacy path (no identity)
    ever returns state: READY with health_code != 200. The honest invariant holds
    regardless of mode — the whole point of the producer fix.
    """
    _guard()

    def _down_probe():
        return (0, None)  # down on every probe

    # (a) M4 path — owned lock + live_session_id, runtime genuinely dead.
    with tempfile.TemporaryDirectory() as td_m4:
        lock = _owned_lock(start_time=111.0)
        m4 = lazy_core.ensure_runtime(
            Path(td_m4),
            config=_M4_CONFIG,
            probe=_down_probe,
            restart=lambda: True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead
        )

    # (b) Legacy path — no identity, same down-then-still-down sequence.
    with tempfile.TemporaryDirectory() as td_legacy:
        legacy = lazy_core.ensure_runtime(
            Path(td_legacy),
            config=_LEGACY_NO_FRONTEND_CONFIG,
            probe=_down_probe,
            restart=lambda: True,
            stale_check=lambda: False,
            live_session_id=None,
            sleep=lambda s: None,
        )

    for label, verdict in (("M4", m4), ("legacy", legacy)):
        assert not (
            verdict["state"] == "READY" and verdict["health_code"] != 200
        ), f"{label} path returned READY with non-200 health_code: {verdict}"
        assert verdict["state"] != "READY", f"{label}: {verdict}"




def test_ensure_runtime_m4_ready_when_owned_current_healthy():
    """Owned (verify→True via matching kernel start_time + session) + not stale +
    probe 200 → state READY, ownership_verified True, health_code 200; the verdict
    is a SUPERSET of the legacy dict (health_code + mcp_tools_present retained)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a READY runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # matches recorded
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result
        assert result["health_code"] == 200, result
        assert result["mcp_tools_present"] is True, result
        assert result["terminal_blocker"] is None, result
        # Backward-compat: legacy fields retained (Phase-5 incremental migration).
        assert "health_code" in result and "mcp_tools_present" in result, result




def test_ensure_runtime_m4_stale_when_owned_but_stale():
    """Owned + stale_check True routes into the STALE recovery branch (restart is
    invoked, distinguishing it from a no-recovery READY). A healthy re-probe then
    resolves it to READY. (WU-2 asserts the bound/backoff/lock-rewrite specifics.)"""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=222.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: True,  # STALE → recovery
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 222.0,
            sleep=lambda s: None,
        )
        # STALE routed through recovery (restart fired) — NOT a bare READY.
        assert calls["restart"] >= 1, "STALE must route into the recovery branch"
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result




def test_ensure_runtime_m4_hijacked_when_unowned_but_health_answers():
    """Lock present but verify→False (divergent kernel start_time → a foreign
    port-holder) while /health answers 200 → state HIJACKED, ownership_verified
    False. No restart in WU-1's classification."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=333.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a HIJACKED runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            # Divergent start_time → verify_runtime_ownership returns False, but
            # the PID is live (start_time is not None) and /health answers.
            kernel_start_time_fn=lambda pid, **kw: 999.0,
        )
        assert result["state"] == "HIJACKED", result
        assert result["ownership_verified"] is False, result




def test_ensure_runtime_m4_dead_when_pid_missing_routes_to_recovery():
    """Recorded PID is gone (kernel_start_time → None) → classified DEAD (missing
    PID), so it enters the recovery branch (restart fired — NOT a HIJACKED no-kill
    halt). With recovery never restoring health it exhausts to BLOCKED with
    ownership_verified False (the Identity decision: DEAD, not HIJACKED)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=444.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (0, None),  # nothing answering, never recovers
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: None,  # PID dead → DEAD
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        # DEAD routed into recovery (a HIJACKED would NEVER restart).
        assert calls["restart"] >= 1, "DEAD (missing PID) must enter recovery"
        assert result["state"] == "BLOCKED", result
        assert result["ownership_verified"] is False, result




def test_ensure_runtime_m4_dead_when_owned_pid_alive_but_health_refused_routes_to_recovery():
    """Owned + live PID but /health refused → classified DEAD (endpoint not
    serving), enters recovery. ownership_verified stays True (the failure is
    health, not identity); exhausted recovery → BLOCKED."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=555.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (0, None),  # /health refused, never recovers
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 555.0,  # owned + alive
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        assert calls["restart"] >= 1, "DEAD (health refused) must enter recovery"
        assert result["state"] == "BLOCKED", result
        # ownership was verifiable; the failure is health, not identity.
        assert result["ownership_verified"] is True, result




def test_ensure_runtime_m4_no_lock_plus_health_answers_is_hijacked():
    """No `.runtime.lock.json` recorded but /health answers 200 serving a FOREIGN
    tool surface → an unverified foreign port-holder → HIJACKED (health=200 is NOT
    proof of ownership, LD1).

    NOTE (Gap-2, harness-mcp-observation-gap-disposition-and-hijacked-runtime):
    the payload here serves a DIFFERENT app's tool (`some_other_app_tool`), NOT
    `_M4_CONFIG`'s asserted `render_chart`. A no-lock runtime serving OUR OWN tools
    is now the soft owned-unverified-serving READY case (the post-mcp-test lock
    divergence — covered by
    `test_ensure_runtime_lock_none_serving_our_tools_is_soft_ready`); only a
    GENUINELY foreign tool surface stays HIJACKED. This fixture was updated from
    `render_chart` to a foreign tool so it still exercises the LD3 foreign-holder
    fail-safe it is named for, rather than the now-soft-READY post-mcp-test case.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["some_other_app_tool"]}),  # FOREIGN
            restart=lambda: True,
            stale_check=lambda: False,
            read_lock=lambda: None,  # no recorded ownership
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 1.0,
        )
        assert result["state"] == "HIJACKED", result
        assert result["ownership_verified"] is False, result




def test_ensure_runtime_m4_no_lock_plus_down_routes_to_recovery():
    """No lock + nothing answering → classified DEAD (nothing to verify, nothing
    serving), enters recovery (restart fired — NOT a HIJACKED halt). Exhausted →
    BLOCKED, ownership_verified False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0}
        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (0, None),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: None,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: None,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        assert calls["restart"] >= 1, "no-lock + down must enter recovery (DEAD)"
        assert result["state"] == "BLOCKED", result
        assert result["ownership_verified"] is False, result




def test_ensure_runtime_m4_legacy_callers_get_superset_dict():
    """A legacy caller passing ONLY probe/restart/stale_check (no Identity
    callables) still gets a verdict dict carrying health_code + mcp_tools_present
    (the part-5 migration is incremental — the superset never drops old fields)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True,
            stale_check=lambda: False,
        )
        # No lock on disk + no injected read_lock → no recorded ownership; a 200
        # with no proof of ownership is HIJACKED, but the legacy fields resolve.
        assert "health_code" in result, result
        assert "mcp_tools_present" in result, result
        assert result["health_code"] == 200, result
        assert result["state"] in {"READY", "STALE", "HIJACKED", "DEAD", "BLOCKED"}, result




# ---------------------------------------------------------------------------
# long-build-and-runtime-ownership Phase 2 — WU-2: bounded recovery (≤5 backoff)
# + HIJACKED / BLOCKED fail-safe. Every external interaction (probe/restart/
# stale_check/kernel_start_time/sleep/write_lock/recover_identity) is injected,
# so the ≤5-attempt bound, the backoff schedule, and the never-SIGKILL invariant
# are asserted WITHOUT a real runtime, network, clock, or process kill.
# ---------------------------------------------------------------------------


def test_ensure_runtime_m4_stale_recovers_to_ready():
    """STALE (owned + stale) → restart() once → re-probe 200 → lock rewritten →
    state READY. restart called exactly once; write_lock invoked on recovery."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=222.0)
        calls = {"restart": 0, "write_lock": 0, "sleep": []}

        def restart():
            calls["restart"] += 1
            return True

        def write_lock(**kw):
            calls["write_lock"] += 1

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=restart,
            stale_check=lambda: True,  # STALE
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 222.0,
            sleep=lambda s: calls["sleep"].append(s),
            write_lock=write_lock,
            recover_identity=lambda: {"pid": 5000, "start_time": 222.0},
        )
        assert result["state"] == "READY", result
        assert calls["restart"] == 1, calls
        assert calls["write_lock"] == 1, "lock must be rewritten on recovery"
        assert result["ownership_verified"] is True, result




def test_ensure_runtime_m4_dead_recovers_within_five():
    """DEAD (owned PID alive but /health refused) recovers: probe stays down for
    the first 2 restarts then answers 200 on the 3rd → state READY, restart ≤5."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=555.0)
        calls = {"restart": 0, "probe": 0}

        def probe():
            # Initial probe + one re-probe per restart. Answer 200 only after the
            # 3rd restart (probe call index 4 = initial(1) + 3 re-probes).
            calls["probe"] += 1
            return (200, {"tools": ["render_chart"]}) if calls["restart"] >= 3 else (0, None)

        def restart():
            calls["restart"] += 1
            return True

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=probe,
            restart=restart,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 555.0,
            sleep=lambda s: None,
            write_lock=lambda **kw: None,
            recover_identity=lambda: {"pid": 5001, "start_time": 555.0},
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        assert result["state"] == "READY", result
        assert calls["restart"] == 3, calls
        assert calls["restart"] <= 5, "recovery must be bounded at 5 attempts"




def test_ensure_runtime_m4_dead_exhausts_to_blocked():
    """DEAD where restart never restores health → restart invoked EXACTLY 5 times
    (bounded), exponential backoff applied via the injected sleep (no real
    sleeps), then state BLOCKED + terminal_blocker set."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=666.0)
        calls = {"restart": 0, "sleep": []}

        def restart():
            calls["restart"] += 1
            return True

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (0, None),  # never recovers
            restart=restart,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 666.0,
            sleep=lambda s: calls["sleep"].append(s),
            write_lock=lambda **kw: (_ for _ in ()).throw(
                AssertionError("lock must NOT be rewritten on a failed recovery")
            ),
            recover_identity=lambda: {"pid": 5002, "start_time": 666.0},
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 5, f"recovery must cap at 5: {calls}"
        assert result["terminal_blocker"], "BLOCKED must carry a terminal_blocker"
        # Exponential backoff: each delay strictly larger than the previous, and
        # at least one sleep occurred between retries (no busy loop).
        assert len(calls["sleep"]) >= 4, calls
        assert calls["sleep"] == sorted(calls["sleep"]), (
            f"backoff must be non-decreasing (exponential): {calls['sleep']}"
        )
        assert calls["sleep"][-1] > calls["sleep"][0], (
            f"backoff must grow: {calls['sleep']}"
        )




def test_ensure_runtime_m4_hijacked_sets_blocker_never_restarts_never_kills():
    """HIJACKED (foreign port-holder: recorded PID dead but /health answers, OR a
    live divergent owner) → terminal_blocker set, and restart()/kill() are NEVER
    invoked (the never-SIGKILL-an-unowned-process safety invariant, LD3)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Foreign owner: divergent live start_time (999 != recorded 333) while
        # /health answers — a live foreign port-holder.
        lock = _owned_lock(start_time=333.0)
        calls = {"restart": 0, "kill": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 999.0,  # foreign, divergent
            sleep=lambda s: None,
            write_lock=lambda **kw: None,
            kill=lambda pid: calls.__setitem__("kill", calls["kill"] + 1),
        )
        assert result["state"] == "HIJACKED", result
        assert result["terminal_blocker"], "HIJACKED must carry a terminal_blocker"
        assert calls["restart"] == 0, "HIJACKED must NEVER restart"
        assert calls["kill"] == 0, "HIJACKED must NEVER kill the foreign process"




def test_ensure_runtime_m4_ready_does_no_recovery():
    """A clean READY (owned + current + healthy) performs NO restart and NO sleep
    — the bounded-recovery loop is reachable only from STALE/DEAD."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0, "sleep": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: calls.__setitem__("sleep", calls["sleep"] + 1),
            write_lock=lambda **kw: None,
        )
        assert result["state"] == "READY", result
        assert calls["restart"] == 0, result
        assert calls["sleep"] == 0, result
        assert result["terminal_blocker"] is None, result




# ---------------------------------------------------------------------------
# ensure-runtime-false-hijacked-on-owned-serving-runtime (Phase P1) — the SOFT
# owned-unverified READY classifier. When ownership cannot be VERIFIED (the lock's
# controller_session_id diverges from the threaded live_session_id) BUT the live
# PID is the SAME process this run booted (kernel start_time == recorded lock
# start_time) AND the runtime is provably serving THIS app's MCP tools (/health
# 200 + mcp_tools_present), the verdict is a non-terminal READY (`ownership_verified:
# false`, proceed) instead of terminal HIJACKED. A genuine-foreign case (divergent
# live start_time, or a dead PID) stays the strict never-SIGKILL HIJACKED/DEAD
# fail-safe (LD3/LD4). The guard is 200-gated, MCP-gated, and runs AFTER stale_check
# so a genuinely stale binary is not masked.
# ---------------------------------------------------------------------------

# A lock whose controller_session_id differs from the threaded live_session_id —
# the SESSION component of verify_runtime_ownership diverges. The PID/start_time
# match (or not) is controlled per-test via the injected kernel_start_time_fn.
_SESSION_OTHER = "session-other-xyz"




def _session_divergent_lock(start_time=111.0, pid=4321):
    """A lock recorded by a DIFFERENT controller session than the live one — so
    verify_runtime_ownership fails on the session component. Used to isolate the
    'session diverges, process may or may not match' soft-READY case."""
    lock = _owned_lock(start_time=start_time, pid=pid)
    lock["controller_session_id"] = _SESSION_OTHER
    return lock




def test_ensure_runtime_owned_unverified_serving_is_soft_ready():
    """Session diverges (controller_session_id != live_session_id) but the live PID
    is the SAME serving process (kernel start_time == recorded start_time), /health
    200 + MCP tools present, not stale → SOFT owned-unverified READY: state READY,
    ownership_verified False, terminal_blocker None, mcp_tools_present True. This is
    the cured false-positive (pre-fix this fixture returns HIJACKED)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _session_divergent_lock(start_time=111.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a soft-READY runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,  # != lock's _SESSION_OTHER → verify False
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # MATCHES recorded
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is False, result
        assert result["terminal_blocker"] is None, result
        assert result["mcp_tools_present"] is True, result




def test_ensure_runtime_foreign_live_pid_stays_hijacked():
    """Same session divergence, but the live PID is a DIFFERENT process (kernel
    start_time != recorded → PID reuse / genuine foreign port-holder). Stays
    terminal HIJACKED with the _hijacked_blocker text — never SIGKILL (LD3).
    GREEN both before and after the fix (regression guard)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _session_divergent_lock(start_time=111.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a HIJACKED runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 999.0,  # DIVERGENT → foreign
        )
        assert result["state"] == "HIJACKED", result
        assert result["ownership_verified"] is False, result
        assert result["terminal_blocker"] == lazy_core._hijacked_blocker(lock), result




def test_ensure_runtime_dead_pid_stays_dead():
    """Session divergence + a dead PID (kernel start_time → None) routes to DEAD
    recovery (unchanged) — not the soft-READY shortcut, not HIJACKED. With recovery
    never restoring health it exhausts to BLOCKED (the DEAD path is intact).
    GREEN both before and after the fix."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _session_divergent_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (0, None),  # nothing answering, never recovers
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: None,  # PID dead → DEAD
            sleep=lambda s: None,
            write_lock=lambda **kw: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        # DEAD entered recovery (restart fired — NOT a HIJACKED no-kill halt, NOT
        # a soft-READY); exhausts to BLOCKED since health never returns.
        assert calls["restart"] >= 1, "a dead PID must enter the recovery branch"
        assert result["state"] == "BLOCKED", result
        assert result["ownership_verified"] is False, result




def test_ensure_runtime_owned_unverified_non_200_not_soft_ready():
    """Session-only-divergent + matching PID but probe is NON-200 (503) → the
    soft-READY does NOT fire (it is 200-gated). Routes through the non-serving
    recovery path, never a spurious READY. GREEN both before and after the fix —
    proves the guard is health-gated."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _session_divergent_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (503, {"tools": ["render_chart"]}),  # NOT serving
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # matching PID
            sleep=lambda s: None,
            write_lock=lambda **kw: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        # A non-200 probe with a matching live PID is DEAD (live owned PID, health
        # refused) → recovery, not a soft-READY shortcut.
        assert result["state"] != "READY", result




def test_ensure_runtime_owned_unverified_no_mcp_tools_not_soft_ready():
    """Session-only-divergent + matching PID + 200 but the payload is MISSING the
    asserted MCP tool (mcp_tools_present False) → NOT soft READY. A serving-but-not-
    our-MCP process is not provably ours, so it falls through to the existing
    terminal HIJACKED (the guard requires mcp_tools_present)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _session_divergent_lock(start_time=111.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,  # asserts mcp_tool_name "render_chart"
            probe=lambda: (200, {"tools": ["some_other_tool"]}),  # tool absent
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a HIJACKED runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # matching PID
        )
        assert result["state"] == "HIJACKED", result
        assert result["mcp_tools_present"] is False, result




def test_ensure_runtime_owned_unverified_stale_not_masked():
    """Session-only-divergent + matching PID + 200 + MCP present but stale_check
    True → the soft-READY must NOT mask a stale binary. The stale path runs first,
    so the verdict is NOT a bare soft-READY shortcut (it routes through STALE/
    rebuild). (Open Question 'Boot-stamp interaction'.)"""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _session_divergent_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: True,  # STALE — must NOT be masked by soft-READY
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # matching PID
            sleep=lambda s: None,
            write_lock=lambda **kw: None,
            frontend_probe=lambda: False,  # Vite down → genuine rebuild, not compiling
        )
        # The stale rebuild ran (restart fired) — the soft-READY shortcut did NOT
        # short-circuit a genuinely stale binary into a bare READY.
        assert calls["restart"] >= 1, "a stale binary must route through rebuild"




# ---- Gap 2: soft owned-unverified-serving READY on the lock-is-None branch ---
# (harness-mcp-observation-gap-disposition-and-hijacked-runtime, Phase 2)
# After an /mcp-test cycle the cycle's own dev:restart/engine boot overwrites or
# invalidates .runtime.lock.json, so read_lock() returns None on the next
# --ensure-runtime probe. With code == 200 the M4 classifier's lock-is-None branch
# returned terminal HIJACKED unconditionally — forcing the orchestrator to
# dev:kill + cold-reboot its OWN serving dev runtime every cycle. The fix extends
# the existing soft owned-unverified-serving recognition (which previously fired
# only on the lock-present session-divergent path) to the lock-is-None branch:
# when health is 200 AND _mcp_tools_present_honest confirms the runtime is serving
# THIS app's MCP tools, re-adopt ownership (rewrite the lock) and return a soft
# READY (ownership_verified False). A genuinely foreign tool surface still fails
# _mcp_tools_present_honest and stays terminal HIJACKED (LD3 fail-safe preserved).


def test_ensure_runtime_lock_none_serving_our_tools_is_soft_ready():
    """lock is None (post-mcp-test divergence) + code 200 + payload serving THIS
    app's MCP tool (_mcp_tools_present_honest True) → SOFT owned-unverified READY:
    state READY, ownership_verified False, no HIJACKED terminal_blocker, AND the
    lock is re-adopted (write_lock invoked). RED before WU-5: the lock-is-None +
    200 branch returns terminal HIJACKED unconditionally."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"write_lock": 0}

        def write_lock(**kw):
            calls["write_lock"] += 1

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,  # asserts mcp_tool_name "render_chart"
            probe=lambda: (200, {"tools": ["render_chart"]}),  # OUR tool present
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a soft-READY runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: None,  # post-mcp-test lock divergence / absence
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            write_lock=write_lock,
            recover_identity=lambda: {
                "pid": 5000, "start_time": 111.0, "artifact_hash": "deadbeef",
                "controller_session_id": _SESSION,
            },
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is False, result
        assert result["terminal_blocker"] is None, result
        assert result["mcp_tools_present"] is True, result
        assert calls["write_lock"] >= 1, (
            "the serving-our-tools runtime must be re-adopted (write_lock called)"
        )




def test_ensure_runtime_lock_none_foreign_surface_stays_hijacked():
    """REGRESSION GUARD (LD3 fail-safe): lock is None + code 200 but the payload
    serves a DIFFERENT app's tool surface (_mcp_tools_present_honest False) → stays
    terminal HIJACKED (ownership_verified False, non-None terminal_blocker), AND
    write_lock is NOT called (never re-adopt a foreign process). GREEN both before
    and after the fix."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"write_lock": 0}

        def write_lock(**kw):
            calls["write_lock"] += 1

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,  # asserts mcp_tool_name "render_chart"
            probe=lambda: (200, {"tools": ["some_other_app_tool"]}),  # foreign
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a HIJACKED runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: None,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            write_lock=write_lock,
            recover_identity=lambda: {"pid": 5000, "start_time": 111.0},
        )
        assert result["state"] == "HIJACKED", result
        assert result["ownership_verified"] is False, result
        assert result["terminal_blocker"] is not None, result
        assert result["mcp_tools_present"] is False, result
        assert calls["write_lock"] == 0, (
            "a foreign tool surface must NEVER be re-adopted (LD3 fail-safe)"
        )




def test_ensure_runtime_lock_none_non200_stays_dead():
    """lock is None + code != 200 (nothing serving) → DEAD (recovery), unchanged.
    The soft-READY is 200-gated, so a non-200 never re-adopts. GREEN both before
    and after the fix."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0, "write_lock": 0}
        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,
            probe=lambda: (0, None),  # nothing answering
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: None,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: None,
            sleep=lambda s: None,
            write_lock=lambda **kw: calls.__setitem__("write_lock", calls["write_lock"] + 1),
            recover_identity=lambda: None,
            frontend_probe=lambda: False,  # Vite down → genuinely dead (not compiling)
        )
        # No lock + nothing serving classifies DEAD → recovery (restart fired),
        # exhausts to BLOCKED since health never returns. NOT a soft-READY.
        assert calls["restart"] >= 1, "no-lock + down must enter recovery (DEAD)"
        assert result["state"] == "BLOCKED", result
        assert result["ownership_verified"] is False, result




# ---------------------------------------------------------------------------
# env-transient-counts-against-validation-retry-budget Phase 1 (Leg A) — the
# sidecar-pipe (`is_connected`) readiness dimension. A runtime that is
# HTTP-healthy (/health 200) but MCP-functionally dead (a zombie node process
# holding the :3333 sidecar named pipe → get_sidecar_status.is_connected: false)
# must NOT return a bare READY — it routes into recovery (a dev:restart that
# reaps the stale pipe) and, on persistent disconnect, to BLOCKED. The dimension
# is config-gated (`assert_sidecar_connected`, default off → repo-agnostic) and
# injected (`sidecar_check`, default treated-as-connected) so --test is hermetic.
# ---------------------------------------------------------------------------

_M4_CONFIG_SIDECAR = {**_M4_CONFIG, "assert_sidecar_connected": True}




def test_ensure_runtime_sidecar_disconnected_despite_health_200_routes_to_recovery():
    """Owned + current + /health 200 but sidecar pipe DEAD (sidecar_check → False)
    with assert_sidecar_connected on → NOT a bare READY: recovery is entered
    (restart attempted to reap the stale pipe). On persistent disconnect (restart
    never reconnects the pipe) the terminal verdict is BLOCKED with a non-null
    terminal_blocker (routable to mcp-runtime-unready)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_SIDECAR,
            probe=lambda: (200, {"tools": ["render_chart"]}),  # HTTP-healthy
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # owned + current
            sleep=lambda s: None,
            sidecar_check=lambda: False,  # pipe dead despite HTTP 200
        )
        # NOT a bare READY on the disconnected pass — recovery was entered.
        assert result["state"] != "READY", result
        assert calls["restart"] >= 1, "a dead sidecar pipe must enter recovery"
        # Persistent disconnect → BLOCKED with a terminal_blocker.
        assert result["state"] == "BLOCKED", result
        assert result["terminal_blocker"], "BLOCKED must carry a terminal_blocker"




def test_ensure_runtime_sidecar_check_default_off_preserves_ready():
    """Same owned+current+200 runtime but NO assert_sidecar_connected in config
    (default) and NO injected sidecar_check → the verdict is EXACTLY READY (the
    existing test_ensure_runtime_m4_ready_when_owned_current_healthy behavior is
    preserved byte-for-byte). Regression guard for the default-off path."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG,  # NO assert_sidecar_connected → check skipped
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a default-off READY runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            # NO sidecar_check injected.
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result
        assert result["health_code"] == 200, result
        assert result["terminal_blocker"] is None, result




def test_ensure_runtime_legacy_config_without_sidecar_key_does_not_crash():
    """A config dict WITHOUT assert_sidecar_connected (a legacy override) must not
    raise KeyError and treats the sidecar as connected (the assertion is skipped)
    — an owned+current+200 runtime is READY."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        legacy_cfg = {  # no assert_sidecar_connected / sidecar_status_url keys
            "health_url": "http://localhost:3333/health",
            "restart_command": "npm run dev:restart",
            "mcp_tool_name": "render_chart",
            "native_globs": ["src-tauri", "crates"],
            "lock_filename": ".runtime.lock.json",
            "port": 3333,
        }

        result = lazy_core.ensure_runtime(
            Path(td),
            config=legacy_cfg,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
        )
        assert result["state"] == "READY", result
        assert result["terminal_blocker"] is None, result




def test_ensure_runtime_sidecar_connected_yields_ready():
    """Owned+current+200 with assert_sidecar_connected on and sidecar_check → True
    (a connected pipe) → state READY. A connected sidecar is the happy path; the
    assertion does not perturb a genuinely-ready runtime."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_SIDECAR,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sidecar_check=lambda: True,  # connected sidecar → happy path
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result
        assert calls["restart"] == 0, "a connected sidecar needs no recovery"
        assert result["terminal_blocker"] is None, result




def test_ensure_runtime_sidecar_default_probe_reads_is_connected():
    """_default_sidecar_probe returns is_connected from the get_sidecar_status
    payload (True only when the field is literally True; False on any error or a
    missing/False field) — mirroring _default_runtime_probe's never-raises shape."""
    _guard()
    # The default probe is best-effort over urllib; assert its payload-parsing
    # contract directly with an injected fetch so no network is touched.
    assert lazy_core._sidecar_is_connected({"is_connected": True}) is True
    assert lazy_core._sidecar_is_connected({"is_connected": False}) is False
    assert lazy_core._sidecar_is_connected({}) is False
    assert lazy_core._sidecar_is_connected(None) is False
    assert lazy_core._sidecar_is_connected({"is_connected": "true"}) is False




# ---------------------------------------------------------------------------
# ensure-runtime-recovery-starves-cold-compile Phase 1 — the two-port (Vite
# :1420 + backend :3333) compiling-vs-dead discriminator. A cold `tauri dev`
# brings Vite up on :1420 within seconds while :3333 /health refuses until the
# Rust compile finishes — so (:3333 down, :1420 up) means "compiling, be
# patient", NOT "dead". WU-1 adds the config keys, the default frontend probe,
# and the pure classifier. WU-2 threads the injected frontend_probe through
# ensure_runtime (default-bound when the config carries the frontend keys, else
# lambda: False so a non-:1420 repo is byte-identical to today).
# ---------------------------------------------------------------------------


def test_classify_compile_state_truth_table():
    """_classify_compile_state(backend_code, frontend_up) maps the two-port
    observation to serving|compiling|dead:
      - backend 200 ⇒ serving (regardless of the frontend signal),
      - backend != 200 AND frontend up ⇒ compiling (Vite up, backend not yet
        serving — be patient, do NOT kill),
      - backend != 200 AND frontend down ⇒ dead."""
    _guard()
    assert lazy_core._classify_compile_state(200, False) == "serving"
    assert lazy_core._classify_compile_state(200, True) == "serving"
    assert lazy_core._classify_compile_state(0, True) == "compiling"
    assert lazy_core._classify_compile_state(0, False) == "dead"
    # Any non-200 backend code with Vite up is compiling (e.g. a 503 while the
    # backend is still booting behind a proxy).
    assert lazy_core._classify_compile_state(503, True) == "compiling"
    assert lazy_core._classify_compile_state(503, False) == "dead"




def test_default_frontend_probe_returns_false_on_connection_error():
    """_default_frontend_probe is best-effort (stdlib urllib) and NEVER raises —
    an unreachable URL returns False (mirrors _default_sidecar_probe)."""
    _guard()
    # Port 1 is reserved/unreachable → connection error → False, no exception.
    assert lazy_core._default_frontend_probe("http://localhost:1") is False




def test_ensure_runtime_default_config_carries_frontend_keys():
    """The default config carries the :1420 Vite-up signal keys with the
    documented defaults (frontend_health_url + frontend_port)."""
    _guard()
    assert (
        lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG["frontend_health_url"]
        == "http://localhost:1420"
    )
    assert lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG["frontend_port"] == 1420




def test_ensure_runtime_threads_injected_frontend_probe_to_m4():
    """When a frontend_probe is injected, ensure_runtime threads it through to the
    M4 path: the injected probe is observed being CALLED, without perturbing the
    existing READY verdict for a :3333-serving runtime."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"frontend": 0}

        def frontend_probe():
            calls["frontend"] += 1
            return True

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_FRONTEND,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a serving runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            frontend_probe=frontend_probe,
        )
        # The serving verdict is unchanged for the :3333-200 fixture.
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result
        # The injected frontend_probe was threaded into the M4 path (the classifier
        # is consulted at the recovery entry points; for a serving runtime it may
        # short-circuit, but the seam must be wired — Phase 2 consumes it on the
        # compiling branch). At minimum the call does not crash and the verdict is
        # well-formed; observable wiring is asserted on the compiling path (P2).
        assert _M4_KEYS.issubset(result.keys()), result




def test_ensure_runtime_legacy_config_without_frontend_keys_does_not_crash():
    """A config WITHOUT the frontend keys (a legacy override / non-:1420 repo) must
    not raise and behaves byte-identically to today — an owned+current+200 runtime
    is READY (the discriminator degrades to the :3333-only path, frontend → False)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        legacy_cfg = {  # no frontend_health_url / frontend_port keys
            "health_url": "http://localhost:3333/health",
            "restart_command": "npm run dev:restart",
            "mcp_tool_name": "render_chart",
            "native_globs": ["src-tauri", "crates"],
            "lock_filename": ".runtime.lock.json",
            "port": 3333,
        }

        result = lazy_core.ensure_runtime(
            Path(td),
            config=legacy_cfg,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            # NO frontend_probe injected → default binds to lambda: False.
        )
        assert result["state"] == "READY", result
        assert result["terminal_blocker"] is None, result




def test_ensure_runtime_frontend_probe_default_binds_when_config_carries_keys():
    """With the frontend config keys present and NO injected frontend_probe, the
    default binds to the real _default_frontend_probe (a callable bound from the
    config's frontend_health_url) — mirroring the sidecar_check default-binding
    shape. We assert it does not crash and the verdict is well-formed; the bound
    probe is best-effort over urllib (no network reached in this READY fixture)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_FRONTEND,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a serving runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            # NO frontend_probe → default-binds to the real probe via the config.
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result




def test_classify_compile_state_boot_alive_extended_truth_table():
    """_classify_compile_state gains a back-compat `boot_alive` parameter:
      - backend 200 ⇒ serving regardless of frontend OR boot_alive,
      - non-200 + frontend up ⇒ compiling regardless of boot_alive (prior branch),
      - non-200 + frontend down + boot_alive ⇒ compiling (the NEW pre-Vite branch:
        both ports down but the boot process is alive → patient-wait, not dead),
      - non-200 + frontend down + NOT boot_alive ⇒ dead (UNCHANGED)."""
    _guard()
    # The NEW branch: both ports down + live boot ⇒ patient-wait.
    assert lazy_core._classify_compile_state(0, False, True) == "compiling"
    # Both ports down + dead boot ⇒ dead (UNCHANGED).
    assert lazy_core._classify_compile_state(0, False, False) == "dead"
    # Prior branches are independent of boot_alive.
    assert lazy_core._classify_compile_state(200, False, True) == "serving"
    assert lazy_core._classify_compile_state(200, True, True) == "serving"
    assert lazy_core._classify_compile_state(200, False, False) == "serving"
    assert lazy_core._classify_compile_state(0, True, True) == "compiling"
    assert lazy_core._classify_compile_state(0, True, False) == "compiling"
    assert lazy_core._classify_compile_state(503, True, False) == "compiling"




def test_classify_compile_state_boot_alive_back_compat_default():
    """The `boot_alive` parameter DEFAULTS to False, so every existing positional
    caller is byte-identical to the prior three-branch truth table — both-ports-
    down with no boot_alive arg is still `dead`."""
    _guard()
    # No boot_alive arg → byte-identical to the prior fix's truth table.
    assert lazy_core._classify_compile_state(200, False) == "serving"
    assert lazy_core._classify_compile_state(200, True) == "serving"
    assert lazy_core._classify_compile_state(0, True) == "compiling"
    assert lazy_core._classify_compile_state(0, False) == "dead"
    assert lazy_core._classify_compile_state(503, True) == "compiling"
    assert lazy_core._classify_compile_state(503, False) == "dead"




def test_ensure_runtime_threads_injected_boot_alive_to_m4():
    """When a boot_alive callable is injected, ensure_runtime threads it through to
    the M4 path without crashing and without perturbing the READY verdict for a
    :3333-serving runtime (mirrors the frontend_probe threading test)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"boot": 0}

        def boot_alive():
            calls["boot"] += 1
            return True

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT run for a serving runtime")
            ),
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            boot_alive=boot_alive,
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is True, result
        assert _M4_KEYS.issubset(result.keys()), result




def test_ensure_runtime_legacy_config_without_boot_key_does_not_crash():
    """A config WITHOUT the boot-liveness key (a legacy override) must not raise and
    behaves byte-identically to today — an owned+current+200 runtime is READY (the
    discriminator degrades to the no-boot-signal path, boot_alive → False)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        legacy_cfg = {  # no boot_liveness key
            "health_url": "http://localhost:3333/health",
            "restart_command": "npm run dev:restart",
            "mcp_tool_name": "render_chart",
            "native_globs": ["src-tauri", "crates"],
            "lock_filename": ".runtime.lock.json",
            "port": 3333,
        }

        result = lazy_core.ensure_runtime(
            Path(td),
            config=legacy_cfg,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            # NO boot_alive injected → default binds to lambda: False.
        )
        assert result["state"] == "READY", result
        assert result["terminal_blocker"] is None, result




def test_ensure_runtime_boot_alive_default_off_when_config_lacks_key():
    """With NO boot-liveness config key and NO injected boot_alive, a both-ports-
    down runtime classifies `dead` ⇒ byte-identical to today's recovery path (the
    boot-liveness branch is inert unless the signal is configured)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        cfg_no_boot = {**_M4_CONFIG_FRONTEND}  # frontend on, boot signal absent
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=cfg_no_boot,
            probe=lambda: (0, None),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite down
            # NO boot_alive → default binds lambda: False → genuinely dead.
        )
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 5, f"default-off must run today's recovery: {calls}"




# ---------------------------------------------------------------------------
# ensure-runtime-starves-pre-vite-sidecar-build Phase 2 — route the pre-Vite
# live-boot window off the crash-recovery loop (both routers). A both-ports-down
# runtime with a LIVE boot process (boot_alive True) is patiently WAITED on via
# _await_compile_serving (never kill-restarted) on BOTH the legacy and M4 paths;
# the bounded ≤5×backoff loop is reserved strictly for a genuinely dead runtime
# (both ports down AND boot NOT alive). All probes injected → hermetic.
# ---------------------------------------------------------------------------


def test_ensure_runtime_legacy_pre_vite_live_boot_patiently_waits_never_restarts():
    """THE regression test for the SPEC's exact failure. Legacy path (no Identity
    callables → ownership_verified False), both ports DOWN + boot_alive=True (the
    pre-Vite BeforeDevCommand/sidecar:build window): _route_legacy_non_serving
    patient-waits, restart() is NEVER called (call-count == 0), and reaches READY
    once :3333 answers 200 within the cold-compile ceiling. Before this fix the
    boot was kill-restarted 5× into a false BLOCKED."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0, "probe": 0}

        def probe():
            # First probe (DOWN) → restart() (legacy first-attempt boot) → re-probe
            # (still DOWN) → _route_legacy_non_serving. Then the patient-wait re-
            # probes; answer 200 only after a few cold-boot polls.
            calls["probe"] += 1
            return (200, {}) if calls["probe"] >= 5 else (0, None)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=probe,
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite NOT yet up (pre-Vite window)
            boot_alive=lambda: True,       # boot process IS alive → patient-wait
            # NO live_session_id / read_lock → LEGACY mode (the SPEC's failing path).
        )
        assert result["state"] == "READY", result
        assert result["ownership_verified"] is False, result
        # The legacy first-attempt restart() fires ONCE in ensure_runtime's
        # down→boot→re-probe arm; the PATIENT WAIT itself must add ZERO restarts.
        # The starvation bug was the ≤5×backoff loop; here recovery must not run.
        assert calls["restart"] <= 1, (
            f"the pre-Vite live boot must be waited, not kill-restarted: {calls}"
        )




def test_ensure_runtime_legacy_pre_vite_boot_dies_falls_through_to_recovery():
    """Legacy path, both ports down + a live boot that CROSSES to dead mid-wait
    (boot_alive goes False while ports stay down) → the patient wait abandons and
    falls through to the bounded _recover_runtime crash loop (restart fired, capped
    at 5, exhausts to BLOCKED)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0, "boot": 0}

        def boot_alive():
            # Alive on the first classification (→ compiling/patient-wait), then
            # DOWN (→ dead) so the wait falls through to recovery.
            calls["boot"] += 1
            return calls["boot"] <= 1

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=lambda: (0, None),  # backend never serves
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite stays down
            boot_alive=boot_alive,
        )
        assert result["state"] == "BLOCKED", result
        # First-attempt boot restart (≤1) + the bounded recovery loop after the
        # went-dead fall-through → restart fired more than the patient-wait's zero.
        assert calls["restart"] >= 1, (
            f"a live-boot→dead transition must fall through to recovery: {calls}"
        )
        assert calls["restart"] <= 6, "recovery must stay bounded (≤1 boot + ≤5 loop)"




def test_ensure_runtime_legacy_pre_vite_boot_never_serves_blocks_distinct_text():
    """Legacy path, both ports down + live boot that NEVER serves within the
    ceiling → BLOCKED with the DISTINCT cold-compile-timeout text, and the patient
    wait NEVER kill-restarts (only the legacy first-attempt boot, ≤1)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=lambda: (0, None),  # backend never serves
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            sleep=lambda s: None,
            frontend_probe=lambda: False,
            boot_alive=lambda: True,  # boot STAYS alive → compiling the whole time
        )
        assert result["state"] == "BLOCKED", result
        assert result["terminal_blocker"] == lazy_core._cold_compile_timeout_blocker(), (
            result["terminal_blocker"]
        )
        # The patient wait must add zero restarts (≤ the single legacy boot attempt).
        assert calls["restart"] <= 1, (
            f"the pre-Vite patient wait must not kill-restart: {calls}"
        )




def test_ensure_runtime_m4_pre_vite_live_boot_patiently_waits_never_restarts():
    """M4 mirror: owned runtime, both ports down + boot_alive=True → the M4
    _route_non_serving patient-waits via _await_compile_serving, restart() == 0,
    reaches READY once :3333 answers 200."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0, "probe": 0}

        def probe():
            calls["probe"] += 1
            return (200, {"tools": ["render_chart"]}) if calls["probe"] >= 4 else (0, None)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=probe,
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # owned + alive
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite NOT up (pre-Vite)
            boot_alive=lambda: True,       # boot alive → patient-wait
        )
        assert result["state"] == "READY", result
        assert calls["restart"] == 0, (
            f"an M4 pre-Vite live boot must NEVER be kill-restarted: {calls}"
        )
        assert result["ownership_verified"] is True, result




def test_ensure_runtime_m4_genuine_dead_no_boot_unchanged_recovery():
    """M4, both ports down + boot_alive=False (genuine dead — not a fresh cold
    boot) → UNCHANGED bounded _recover_runtime (restart fired, capped at 5,
    GENERIC _blocked_blocker). The genuine-crash path is preserved."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=lambda: (0, None),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite down
            boot_alive=lambda: False,      # boot NOT alive → genuinely dead
        )
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 5, f"genuine dead must run bounded recovery: {calls}"
        assert result["terminal_blocker"] == lazy_core._blocked_blocker(5), (
            "genuine dead must carry the GENERIC blocker, not cold-compile text"
        )




# ---------------------------------------------------------------------------
# ensure-runtime-starves-pre-vite-sidecar-build Phase 3 (CLI-seam WIRING — the
# harden(script) production-binding fix). The prior Phase-2 tests above all
# INJECT `boot_alive`; these two exercise the PRODUCTION binding that was the
# dead seam: with `boot_liveness` enabled (the base default) and NO injected
# `boot_alive`, `ensure_runtime` must derive the signal from the liveness of the
# `restart()`-spawned `Popen` handle (`.poll()` None ⇒ alive). Driven through the
# REAL default `restart` closure by swapping `lazy_core.runtimeplane.subprocess`/`lazy_core.runtimeplane.time`
# for fakes — the only way to reach the closure-shared boot-handle holder, which is
# private to `ensure_runtime` (no injection seam, by design).
# ---------------------------------------------------------------------------


class _FakeBootPopen:
    """Stand-in for the `dev:restart` boot `Popen` handle. `.poll()` returns None
    while ``_exit_code`` is None (boot still running ⇒ the pre-Vite window), or the
    exit code once set (boot exited ⇒ crossed to dead)."""

    def __init__(self, exit_code=None):
        self._exit_code = exit_code
        self.pid = 4321

    def poll(self):
        return self._exit_code




class _FakeSubprocess:
    """Module stand-in for `lazy_core.runtimeplane.subprocess` — `Popen(...)` returns the given
    fake handle and records the spawn; carries the DEVNULL sentinel the default
    `restart` references."""

    DEVNULL = -3

    def __init__(self, handle):
        self._handle = handle
        self.spawns = 0

    def Popen(self, *a, **kw):  # noqa: N802 — mirrors subprocess.Popen
        self.spawns += 1
        return self._handle




class _FakeTime:
    """Module stand-in for `lazy_core.runtimeplane.time` — `sleep` is a no-op so the default
    `restart`'s ~7.5-min poll loop and the patient wait run instantly; `time()` is
    a real monotonic-ish counter in case anything reads it."""

    def __init__(self):
        self._t = 0.0

    def sleep(self, _s):
        self._t += 1.0

    def time(self):
        return self._t




def test_ensure_runtime_production_boot_alive_live_handle_patient_waits():
    """PRODUCTION binding, live handle: `boot_liveness` on (base default) + NO
    injected `boot_alive`/`restart` → the real default `restart` spawns a boot
    process whose `.poll()` stays None (still booting). With both ports down the
    derived `boot_alive` reports ALIVE, so the runtime classifies `compiling` and is
    PATIENTLY WAITED on (the default restart's own poll loop is the only spawn — the
    patient wait NEVER re-spawns). The wait then ends READY once :3333 answers 200.

    This is the seam the fix wired: before, the production `boot_alive` was a hard
    `lambda: False`, so this both-ports-down cold boot was misclassified `dead`."""
    _guard()
    live = _FakeBootPopen(exit_code=None)  # boot stays alive (poll → None)
    fake_sub = _FakeSubprocess(live)
    fake_time = _FakeTime()
    probe_calls = {"n": 0}

    def probe():
        # Non-200 until the patient wait has polled a few times, then serve — so the
        # default restart's internal loop never succeeds (handle stays the signal),
        # and the patient wait resolves READY once the cold compile "finishes".
        probe_calls["n"] += 1
        return (200, {"tools": ["render_chart"]}) if probe_calls["n"] >= 95 else (0, None)

    _real_sub, _real_time = lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time
    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time
    try:
        with tempfile.TemporaryDirectory() as td:
            result = lazy_core.ensure_runtime(
                Path(td),
                config=_M4_CONFIG_BOOT,           # boot_liveness: True
                probe=probe,                       # only the BACKEND probe is injected
                stale_check=lambda: False,
                sleep=lambda s: None,              # patient-wait sleep (hermetic)
                frontend_probe=lambda: False,      # Vite stays down (pre-Vite window)
                # NO restart, NO boot_alive → BOTH production defaults bind. This is
                # the exact production-call shape (lazy-state.py passes neither).
            )
    finally:
        lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = _real_sub, _real_time

    assert result["state"] == "READY", result
    # Exactly ONE boot spawn (the default restart) — the patient wait added none.
    assert fake_sub.spawns == 1, (
        f"a live-boot pre-Vite window must spawn once (restart) and then patient-wait "
        f"with NO re-spawn: {fake_sub.spawns}"
    )




def test_ensure_runtime_production_boot_alive_dead_handle_recovers():
    """PRODUCTION binding, EXITED handle that never serves: `boot_liveness` on + NO
    injected `boot_alive`/`restart`, the spawned boot's `Popen.poll()` returns an
    exit code, and the backend never reaches 200.

    UPDATED for ensure-runtime-recovery-starves-cold-compile-round-2: the
    Round-32 expectation (an exited handle ⇒ GENERIC ≤5×-recovery BLOCKED) was
    PREMISED ON the now-removed wrapper-handle-only signal. With the time-window
    grace, the harness's OWN first `restart()` writes a fresh boot stamp, so the
    runtime is correctly seen as a cold boot in progress (`compiling`) and is
    PATIENTLY WAITED on — never 5× kill-restarted. A backend that never serves
    within the cold-compile budget ends BLOCKED with the COLD-COMPILE-timeout text
    (still `blocker_kind: mcp-runtime-unready` downstream) and exactly ONE spawn.
    Fail-safe is preserved: it still reaches BLOCKED, never a forever wait."""
    _guard()
    dead = _FakeBootPopen(exit_code=1)  # wrapper exited (poll → 1) — Windows reality
    fake_sub = _FakeSubprocess(dead)
    fake_time = _FakeTime()

    _real_sub, _real_time = lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time
    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time
    try:
        with tempfile.TemporaryDirectory() as td:
            result = lazy_core.ensure_runtime(
                Path(td),
                config=_M4_CONFIG_BOOT,           # boot_liveness: True
                probe=lambda: (0, None),           # backend never serves
                stale_check=lambda: False,
                sleep=lambda s: None,
                frontend_probe=lambda: False,      # Vite down (pre-Vite window)
                # NO restart, NO boot_alive → production defaults bind. The exited
                # handle + fresh boot stamp ⇒ the grace reports the cold boot in
                # progress (the Windows wrapper-exits-early case).
            )
    finally:
        lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = _real_sub, _real_time

    assert result["state"] == "BLOCKED", result
    # Patient-wait timeout (cold-compile text), NOT the 5×-crash-recovery generic —
    # AND exactly ONE spawn (the starvation is gone).
    assert result["terminal_blocker"] == lazy_core._cold_compile_timeout_blocker(), (
        "an exited handle with a fresh boot stamp must patient-wait then time out "
        f"with the COLD-COMPILE blocker, not the generic recovery text: {result['terminal_blocker']}"
    )
    assert fake_sub.spawns == 1, (
        f"the never-serving cold boot must spawn ONCE then patient-wait — no 5× "
        f"kill-restart: spawns={fake_sub.spawns}"
    )




# ---------------------------------------------------------------------------
# ensure-runtime-recovery-starves-cold-compile-round-2 — the Windows-wrapper-
# exits-early refix (production re-fix of a9ab567). The Round-32 fix derived
# `boot_alive` SOLELY from the `restart()`-spawned `Popen.poll()`, but on Windows
# `npm run dev:restart` spawns a SHORT-LIVED npm/cmd shell-chain wrapper that
# EXITS within seconds (`.poll()` returns an exit code) long before the ~3.5-min
# cold `tauri dev`/`cargo build` child finishes — so a genuinely-compiling cold
# boot was misclassified `dead` and the bounded `_recover_runtime` loop kill-
# restarted it up to 5× in ~60s → false BLOCKED. The Round-32 "live handle" test
# only proved the case where `.poll()` STAYS None — it NEVER exercised the
# wrapper-exits-early production reality (the false-green).
#
# These tests reproduce that production reality: an EXITED `Popen` handle
# (`.poll()` returns a code) PLUS the persistent boot-spawn TIME-WINDOW grace.
# A green test here means production works: the exited-wrapper cold boot now
# classifies `compiling` (via the grace), the recovery loop HANDS OFF to the
# patient wait after its FIRST restart (exactly ONE spawn — no 5× kill-restart),
# and a genuinely-stale stamp (grace aged out) still reaches BLOCKED (fail-safe).
# ---------------------------------------------------------------------------


def test_boot_spawn_stamp_roundtrip_and_grace_window():
    """write/read_boot_stamp roundtrip + boot_recently_spawned time-window grace:
    a fresh stamp is within grace; a stamp older than the grace ceiling is not; a
    missing stamp is never within grace (fail-safe toward NOT-booting)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        # Missing stamp ⇒ never within grace.
        assert lazy_core.boot_recently_spawned(repo, now=1000.0) is False
        # Fresh stamp (spawned at t=1000) ⇒ within grace at t=1000 + small delta.
        lazy_core.write_boot_stamp(repo, spawn_ts=1000.0)
        assert lazy_core.read_boot_stamp(repo) == 1000.0
        assert lazy_core.boot_recently_spawned(repo, now=1000.0) is True
        assert lazy_core.boot_recently_spawned(
            repo, now=1000.0 + lazy_core._BOOT_SPAWN_GRACE_SECONDS - 1
        ) is True
        # Aged-out stamp ⇒ NOT within grace (fail-safe: a stuck/dead host ages out
        # of the patient-wait grace and reaches bounded recovery → BLOCKED).
        assert lazy_core.boot_recently_spawned(
            repo, now=1000.0 + lazy_core._BOOT_SPAWN_GRACE_SECONDS + 1
        ) is False




# ---------------------------------------------------------------------------
# stale-runtime-health-200-false-blocked — _default_stale_check (the F7
# stale_binary.native_source_newer_than wiring) + the production ensure_runtime
# binding. `stale_check` is on the production-binding guard's ALLOWED-injection
# list (_PRODUCTION_BINDING_ALLOWED_KWARGS), so these `test_ensure_runtime_
# production_*`-named tests are free to either derive OR inject it; the two
# integration tests below deliberately DERIVE (no `stale_check=` kwarg) to
# actually exercise the new default binding, matching the unit tests' direct
# `_default_stale_check` coverage.
# ---------------------------------------------------------------------------

def test_default_stale_check_native_commit_after_boot_stamp_is_stale():
    """Boot stamp recorded BEFORE a native-source commit → stale (True)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        lazy_core.write_boot_stamp(repo_root, spawn_ts=_t.time() - 3600)
        (repo_root / "src-tauri").mkdir()
        (repo_root / "src-tauri" / "main.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)

        result = lazy_core._default_stale_check(
            repo_root, dict(lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG)
        )
        assert result is True, "boot BEFORE a native commit must report stale"




def test_default_stale_check_native_commit_before_boot_stamp_is_fresh():
    """Boot stamp recorded AFTER the native-source commit → not stale (False)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        (repo_root / "src-tauri").mkdir()
        (repo_root / "src-tauri" / "main.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)
        lazy_core.write_boot_stamp(repo_root, spawn_ts=_t.time() + 3600)

        result = lazy_core._default_stale_check(
            repo_root, dict(lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG)
        )
        assert result is False, "boot AFTER the native commit must report fresh"




def test_default_stale_check_no_boot_stamp_falls_back_to_lock_start_time():
    """No `.runtime.boot.json` (e.g. a runtime that booted before this fix, or a
    legacy/foreign lock) → falls back to `.runtime.lock.json`'s recorded kernel
    `start_time` (D1's documented fallback signal), not straight to False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        cfg = dict(lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG)
        # No write_boot_stamp call — the boot-stamp file is genuinely absent.
        lazy_core.runtimeplane.write_runtime_lock(
            repo_root, config=cfg, pid=123, start_time=_t.time() - 3600,
            port=cfg["port"], artifact_hash=None, controller_session_id="s1",
        )
        (repo_root / "crates").mkdir()
        (repo_root / "crates" / "lib.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)

        result = lazy_core._default_stale_check(repo_root, cfg)
        assert result is True, (
            "no boot stamp + a lock start_time BEFORE the native commit must "
            "still report stale via the lock fallback"
        )




def test_default_stale_check_no_signal_at_all_returns_false():
    """Neither a boot stamp NOR a runtime lock exists → fail-safe False (D2) —
    never a spurious STALE with nothing to compare against."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        (repo_root / "src-tauri").mkdir()
        (repo_root / "src-tauri" / "main.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)

        result = lazy_core._default_stale_check(
            repo_root, dict(lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG)
        )
        assert result is False, "no boot signal at all must fail safe to False"




def test_default_stale_check_respects_configured_native_globs():
    """A repo config's `native_globs` override is honored — a commit outside the
    configured globs is invisible, mirroring stale_binary.py's own glob contract."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        lazy_core.write_boot_stamp(repo_root, spawn_ts=_t.time() - 3600)
        (repo_root / "src-tauri").mkdir()
        (repo_root / "src-tauri" / "main.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)

        cfg = dict(lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG)
        cfg["native_globs"] = ["custom-native-only"]
        result = lazy_core._default_stale_check(repo_root, cfg)
        assert result is False, (
            "a custom native_globs list must scope the freshness check — the "
            "src-tauri commit is outside it and must be invisible"
        )




def test_default_stale_check_bogus_repo_root_never_raises():
    """A non-git repo_root (or any predicate-level error) must fail safe to
    False, never raise — the binding's own fail-safe contract."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        non_repo = Path(td) / "not-a-repo"
        non_repo.mkdir()
        result = lazy_core._default_stale_check(
            non_repo, dict(lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG)
        )
        assert result is False




def test_ensure_runtime_derived_stale_check_routes_to_stale_rebuild():
    """PRODUCTION binding, legacy mode (no Identity injected — no `live_session_id`
    / `read_lock` / `kernel_start_time_fn`): `stale_check` is DERIVED (no kwarg
    passed) from a REAL boot stamp + a REAL git repo with a native-source commit
    landing AFTER boot. The previously-orphaned F7 predicate must now route the
    runtime through the existing STALE→rebuild branch (`restart()` fires) instead
    of the pre-fix `lambda: False` default that made STALE unreachable.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        lazy_core.write_boot_stamp(repo_root, spawn_ts=_t.time() - 3600)
        (repo_root / "src-tauri").mkdir()
        (repo_root / "src-tauri" / "main.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)

        calls = {"restart": 0}
        result = lazy_core.ensure_runtime(
            repo_root,
            probe=lambda: (200, {"tools": []}),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            # NO stale_check= kwarg — the production default must DERIVE it from
            # the real boot stamp + real git repo above.
        )
        assert calls["restart"] >= 1, (
            "a derived-stale runtime must route through restart() — the STALE "
            "verdict must be REACHABLE in production, not defaulted to False"
        )
        # Legacy mode's verdict superset reports the terminal "stale-rebuilt"
        # status as state STALE (_LEGACY_STATUS_TO_STATE maps "stale-rebuilt"
        # -> "STALE", distinct from the M4 path's fully-resolved READY after
        # recovery) — restart() having fired + a healthy 200 re-probe together
        # PROVE the previously-unreachable STALE verdict is now reachable and
        # drove a rebuild, which is what this test exists to demonstrate.
        assert result["state"] == "STALE", result
        assert result["health_code"] == 200, result




def test_ensure_runtime_derived_stale_check_fresh_boot_no_restart():
    """PRODUCTION binding, legacy mode: boot stamp AFTER the native commit derives
    NOT stale — `restart()` must never fire on the staleness path (the runtime is
    demonstrably current; health=200 alone is sufficient)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        (repo_root / "src-tauri").mkdir()
        (repo_root / "src-tauri" / "main.rs").write_text("// native\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "native change"], check=True, capture_output=True)
        lazy_core.write_boot_stamp(repo_root, spawn_ts=_t.time() + 3600)

        result = lazy_core.ensure_runtime(
            repo_root,
            probe=lambda: (200, {"tools": []}),
            restart=lambda: (_ for _ in ()).throw(
                AssertionError("restart must NOT fire for a fresh (derived) runtime")
            ),
            # NO stale_check= kwarg — must derive NOT-stale and skip restart.
        )
        assert result["state"] == "READY", result




def test_ensure_runtime_production_wrapper_exits_early_patient_waits_one_spawn():
    """THE production-reproducing test (ensure-runtime-recovery-starves-cold-compile
    -round-2). PRODUCTION binding, EXITED wrapper handle (`.poll()` → exit code, the
    Windows npm/cmd wrapper that returns immediately) + both ports down. The
    Round-32 fix would have classified this `dead` and kill-restarted 5× → false
    BLOCKED in ~60s. With the time-window grace + the `_recover_runtime` handoff:
    the first restart writes a fresh boot stamp, the derived `boot_alive` reports
    ALIVE via the grace (despite the exited handle), the runtime classifies
    `compiling`, the recovery loop HANDS OFF to the patient wait — exactly ONE
    spawn, NO 5× kill-restart — and ends READY once :3333 finally answers 200.

    A GREEN assertion here means the production cold boot is no longer starved."""
    _guard()
    exited = _FakeBootPopen(exit_code=0)  # wrapper EXITED immediately (Windows)
    fake_sub = _FakeSubprocess(exited)
    fake_time = _FakeTime()
    probe_calls = {"n": 0}

    def probe():
        # Both ports down through the bounded-recovery entry + the first restart,
        # then serve once the cold compile "finishes" deep in the patient wait.
        probe_calls["n"] += 1
        return (200, {"tools": ["render_chart"]}) if probe_calls["n"] >= 50 else (0, None)

    _real_sub, _real_time = lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time
    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time
    try:
        with tempfile.TemporaryDirectory() as td:
            result = lazy_core.ensure_runtime(
                Path(td),
                config=_M4_CONFIG_BOOT,           # boot_liveness: True
                probe=probe,                       # only the BACKEND probe injected
                stale_check=lambda: False,
                sleep=lambda s: None,              # patient-wait sleep (hermetic)
                frontend_probe=lambda: False,      # Vite stays down (pre-Vite window)
                # NO restart, NO boot_alive → production defaults bind. The EXITED
                # handle is the exact Windows wrapper-exits-early condition the
                # Round-32 test never exercised.
            )
    finally:
        lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = _real_sub, _real_time

    assert result["state"] == "READY", result
    # THE starvation guard: exactly ONE spawn. The Round-32 bug would re-`restart()`
    # (kill-dev.js murders the compile) up to 5×; the handoff to patient-wait must
    # leave the spawn count at 1.
    assert fake_sub.spawns == 1, (
        f"wrapper-exits-early cold boot must spawn ONCE then patient-wait — the "
        f"5×-kill-restart starvation must be gone: spawns={fake_sub.spawns}"
    )




def test_ensure_runtime_m4_wrapper_exits_early_patient_waits_one_spawn():
    """M4-mode (PRODUCTION shape — the run-marker `--ensure-runtime` call threads a
    real `live_session_id` + lock, so identity is engaged) reproduction of the
    Windows wrapper-exits-early cold boot. Owned + non-serving + both ports down +
    the spawned boot's `Popen.poll()` returns an exit code (wrapper exited). Without
    the round-2 fix the M4 `_recover_runtime` would kill-restart 5×; with the
    time-window grace + handoff the first restart writes a fresh stamp, the runtime
    classifies `compiling`, hands off to the patient wait — ONE spawn — and ends
    READY once :3333 serves. Covers the M4 seam (the legacy-mode reproduction above
    exercises the no-marker path); both production entry shapes are now covered."""
    _guard()
    exited = _FakeBootPopen(exit_code=0)  # wrapper exited immediately (Windows)
    fake_sub = _FakeSubprocess(exited)
    fake_time = _FakeTime()
    probe_calls = {"n": 0}

    def probe():
        probe_calls["n"] += 1
        return (200, {"tools": ["render_chart"]}) if probe_calls["n"] >= 50 else (0, None)

    _real_sub, _real_time = lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time
    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time
    try:
        with tempfile.TemporaryDirectory() as td:
            lock = _owned_lock(start_time=111.0)
            result = lazy_core.ensure_runtime(
                Path(td),
                config=_M4_CONFIG_BOOT,           # boot_liveness: True
                probe=probe,
                stale_check=lambda: False,
                read_lock=lambda: lock,
                live_session_id=_SESSION,          # IDENTITY engaged → M4 path
                kernel_start_time_fn=lambda pid, **kw: 111.0,  # ownership verified
                sleep=lambda s: None,
                frontend_probe=lambda: False,      # Vite down (pre-Vite window)
                # NO restart, NO boot_alive → production defaults bind (the exited
                # handle + fresh stamp is the wrapper-exits-early case).
            )
    finally:
        lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = _real_sub, _real_time

    assert result["state"] == "READY", result
    assert fake_sub.spawns == 1, (
        f"M4 wrapper-exits-early cold boot must spawn ONCE then patient-wait — no 5× "
        f"kill-restart starvation: spawns={fake_sub.spawns}"
    )




def test_ensure_runtime_no_boot_ever_spawned_still_blocks_generic():
    """FAIL-SAFE: a genuinely dead host where NO boot is ever spawned — every
    `restart()` FAILS to launch (the injected restart returns False without writing
    a boot stamp), so `boot_recently_spawned` reports False every cycle and the
    derived `boot_alive` reports NOT-booting. With both ports down the runtime stays
    classified `dead`, exhausts the bounded ≤5× crash recovery (each backoff a real
    restart ATTEMPT), and ends BLOCKED with the GENERIC recovery-exhausted text — it
    is NEVER patient-waited forever. This proves the time-window grace cannot mask a
    host where no compile was ever put in flight (the spawn-failure fail-safe)."""
    _guard()
    restart_calls = {"n": 0}

    def failing_restart():
        # A restart that never launches a boot: no stamp written, so the grace
        # stays stale and the host stays `dead` → bounded recovery → generic BLOCKED.
        restart_calls["n"] += 1
        return False

    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_BOOT,
            probe=lambda: (0, None),               # backend never serves
            restart=failing_restart,               # boot is NEVER spawned (no stamp)
            stale_check=lambda: False,
            sleep=lambda s: None,
            frontend_probe=lambda: False,
            # NO boot_alive injected → the production grace-based default binds;
            # with no stamp ever written it reports NOT-booting every cycle.
        )

    assert result["state"] == "BLOCKED", result
    assert result["terminal_blocker"] == lazy_core._blocked_blocker(
        lazy_core._RUNTIME_RECOVERY_MAX_ATTEMPTS
    ), (
        "a host where no boot was ever spawned (no stamp, stale grace) must reach "
        f"the GENERIC bounded-recovery blocker, never a forever wait: {result['terminal_blocker']}"
    )
    # Restart was attempted a BOUNDED number of times (the M4 staleness/health
    # entry restart + the ≤5× recovery loop) — never an unbounded loop. The exact
    # count is an implementation detail; the contract is "bounded, then BLOCKED".
    assert restart_calls["n"] <= lazy_core._RUNTIME_RECOVERY_MAX_ATTEMPTS + 1, (
        f"a never-spawning host must exhaust a BOUNDED recovery, never loop forever: "
        f"{restart_calls['n']}"
    )
    assert restart_calls["n"] >= lazy_core._RUNTIME_RECOVERY_MAX_ATTEMPTS, (
        f"a never-spawning dead host must use the full bounded recovery budget "
        f"(no premature give-up): {restart_calls['n']}"
    )




class _WindowsSpawnSemanticsSubprocess:
    """Module stand-in for `lazy_core.runtimeplane.subprocess` that emulates Windows
    `CreateProcess` resolution (ensure-runtime-cold-boot-starvation-round-3).

    The two prior fixes' tests used `_FakeSubprocess`, whose `.Popen(*a, **kw)`
    ALWAYS succeeds regardless of how it is called — so they NEVER exercised the
    real production defect: on Windows `npm` is `npm.cmd`, which `CreateProcess`
    will NOT resolve from a bare-token argv list (no shell, no PATHEXT lookup), so
    the platform-blind `subprocess.Popen(shlex.split("npm run dev:restart"))`
    raised `FileNotFoundError` and the production `restart()` returned False BEFORE
    spawning anything. This fake reproduces exactly that asymmetry:

      - called with a LIST argv and NOT `shell=True`  → raise `FileNotFoundError`
        (the [WinError 2] the bare-token `npm` spawn hit in production);
      - called with `shell=True` and a STRING command → succeed (the shell resolves
        `npm.cmd` exactly as an interactive `npm run dev:restart` does).

    A test using this fake FAILS against the old platform-blind spawn (restart()
    returns False ⇒ no stamp ⇒ never `compiling` ⇒ generic BLOCKED) and PASSES only
    with the Windows-shell spawn fix — closing the false-green gap that let two
    unit-green fixes ship a live-BLOCKED runtime."""

    DEVNULL = -3

    def __init__(self, handle):
        self._handle = handle
        self.spawns = 0
        self.shell_spawns = 0

    def Popen(self, cmd, *a, **kw):  # noqa: N802 — mirrors subprocess.Popen
        if kw.get("shell") and isinstance(cmd, str):
            # Shell resolution path: `npm.cmd` resolves, boot launches.
            self.spawns += 1
            self.shell_spawns += 1
            return self._handle
        # Bare-token argv with no shell: Windows cannot find `npm` (= `npm.cmd`).
        raise FileNotFoundError(2, "The system cannot find the file specified")




def test_ensure_runtime_production_restart_spawns_via_shell_on_windows_cold_boot():
    """ROUND-3 REGRESSION (ensure-runtime-cold-boot-starvation-round-3): the LIVE-
    confirmed root cause the two prior unit-green fixes never reached. The
    production `restart()` closure spawned `npm run dev:restart` with a bare-token
    argv and `shell=False`, which on Windows raises `FileNotFoundError` (`npm` =
    `npm.cmd`, unresolvable without a shell) — so restart() returned False BEFORE
    spawning the boot, BEFORE stashing `_boot_handle`, and BEFORE `write_boot_stamp`.
    The entire boot-liveness / time-window-grace / patient-wait machinery (rounds 32
    + 2) was therefore DEAD on Windows: no boot ⇒ no stamp ⇒ `boot_alive()` always
    False ⇒ a cold boot was misclassified `dead` and "kill-restarted" 5× → false
    BLOCKED.

    This test exercises the REAL production `restart()` closure (NO injected
    `restart`) against a subprocess fake that reproduces Windows `CreateProcess`
    semantics (raise for a no-shell bare-token argv; succeed only for a `shell=True`
    string). With the fix, the cold boot spawns ONCE via the shell, writes a fresh
    stamp, classifies `compiling`, patient-waits, and ends READY. Against the OLD
    platform-blind spawn this FAILS (BLOCKED, zero successful spawns) — the assertion
    the two prior false-green tests could not make because their fake always spawned.
    """
    _guard()
    if os.name != "nt":
        import pytest as _pytest
        _pytest.skip(
            "spawn-binding under test is the Windows (os.name == 'nt') shell "
            "branch of the production restart(); on posix the production "
            "closure legitimately uses the no-shell argv form the "
            "_WindowsSpawnSemanticsSubprocess double rejects by design"
        )
    live = _FakeBootPopen(exit_code=None)  # boot stays alive once it launches
    fake_sub = _WindowsSpawnSemanticsSubprocess(live)
    fake_time = _FakeTime()
    probe_calls = {"n": 0}

    def probe():
        # Both ports down until the patient wait has polled a while, then serve.
        probe_calls["n"] += 1
        return (200, {"tools": ["render_chart"]}) if probe_calls["n"] >= 50 else (0, None)

    _real_sub, _real_time = lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time
    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time
    try:
        with tempfile.TemporaryDirectory() as td:
            result = lazy_core.ensure_runtime(
                Path(td),
                config=_M4_CONFIG_BOOT,           # boot_liveness: True
                probe=probe,                       # only the BACKEND probe injected
                stale_check=lambda: False,
                read_lock=lambda: _owned_lock(start_time=111.0),
                live_session_id=_SESSION,          # IDENTITY engaged → M4 path
                kernel_start_time_fn=lambda pid, **kw: 111.0,
                sleep=lambda s: None,
                frontend_probe=lambda: False,      # Vite down (pre-Vite window)
                # NO restart, NO boot_alive → the REAL production restart() closure
                # binds and must spawn `npm run dev:restart` through the shell on nt.
            )
    finally:
        lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = _real_sub, _real_time

    assert result["state"] == "READY", (
        "the production restart() must launch the cold boot via the shell so the "
        f"boot-liveness/patient-wait machinery engages — got {result}"
    )
    # The boot was spawned through the shell at least once (the fix path).
    assert fake_sub.shell_spawns >= 1, (
        "the Windows production restart() must spawn via shell=True so npm.cmd "
        f"resolves: shell_spawns={fake_sub.shell_spawns}"
    )
    # And it patient-waited rather than 5×-kill-restarting: ONE spawn total.
    assert fake_sub.spawns == 1, (
        "a successfully-launched cold boot must spawn ONCE then patient-wait, not "
        f"re-spawn through the recovery loop: spawns={fake_sub.spawns}"
    )




# ---------------------------------------------------------------------------
# ensure-runtime-recovery-starves-cold-compile Phase 2 — patient compiling-aware
# wait. A runtime classified `compiling` (Vite :1420 up, backend :3333 not yet
# serving) is WAITED on (owned, cold-compile-sized, NEVER kill-restarted) and
# ends on "actually serving" (:3333 200 + sidecar when asserted). The bounded
# ≤5×backoff crash-recovery loop is reserved strictly for a genuinely `dead`
# runtime. All probes injected → hermetic (no real runtime/network/clock).
# ---------------------------------------------------------------------------


def test_cold_compile_timeout_blocker_distinct_from_blocked_blocker():
    """_cold_compile_timeout_blocker() returns a non-empty string DISTINGUISHABLE
    from the generic recovery-exhausted _blocked_blocker (Open Question 5: distinct
    verdict text, same blocker_kind downstream)."""
    _guard()
    cold = lazy_core._cold_compile_timeout_blocker()
    generic = lazy_core._blocked_blocker(5)
    assert isinstance(cold, str) and cold.strip(), cold
    assert cold != generic, "cold-compile timeout text must differ from generic"
    # It should read as a cold-compile / still-compiling timeout, not a crash.
    assert "compil" in cold.lower(), cold




def test_ensure_runtime_m4_compiling_patiently_waits_never_restarts_then_ready():
    """compiling (:3333 down, :1420 up): the runtime is patiently WAITED on —
    restart() is NEVER called — and reaches READY once :3333 answers 200 within
    the patience ceiling. This is the starvation root cause structurally gone."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0, "probe": 0}

        def probe():
            # Initial probe (M4 Health) + the patient-wait re-probes. Answer 200
            # only on the 4th probe call (simulating a cold compile finishing).
            calls["probe"] += 1
            return (200, {"tools": ["render_chart"]}) if calls["probe"] >= 4 else (0, None)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_FRONTEND,
            probe=probe,
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,  # owned + alive
            sleep=lambda s: None,
            frontend_probe=lambda: True,  # Vite up → compiling, not dead
        )
        assert result["state"] == "READY", result
        assert calls["restart"] == 0, (
            f"a compiling runtime must NEVER be kill-restarted: {calls}"
        )
        assert result["ownership_verified"] is True, result




def test_ensure_runtime_m4_compiling_crosses_to_dead_falls_through_to_recovery():
    """compiling that crosses to dead mid-wait (Vite :1420 goes DOWN) → the patient
    wait abandons and falls through to the bounded _recover_runtime crash path
    (restart IS called, capped at 5)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0, "frontend": 0}

        def frontend_probe():
            # Vite up on the first observation (→ compiling), then DOWN (→ dead).
            calls["frontend"] += 1
            return calls["frontend"] <= 1

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_FRONTEND,
            probe=lambda: (0, None),  # backend never serves
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=frontend_probe,
        )
        # Crossed to dead → bounded recovery ran (restart fired), then exhausted.
        assert calls["restart"] >= 1, (
            f"a compiling→dead transition must fall through to recovery: {calls}"
        )
        assert calls["restart"] <= 5, "recovery must stay bounded at 5"
        assert result["state"] == "BLOCKED", result




def test_ensure_runtime_m4_compiling_never_serves_blocks_with_distinct_text():
    """compiling that never serves within the ceiling → BLOCKED whose
    terminal_blocker is the DISTINCT _cold_compile_timeout_blocker text (NOT the
    generic _blocked_blocker), and restart() is STILL never called during the
    compiling wait."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_FRONTEND,
            probe=lambda: (0, None),  # backend never serves
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=lambda: True,  # Vite STAYS up → compiling the whole time
        )
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 0, (
            f"restart must NEVER fire during a compiling wait: {calls}"
        )
        assert result["terminal_blocker"] == lazy_core._cold_compile_timeout_blocker(), (
            result["terminal_blocker"]
        )




def test_ensure_runtime_m4_compiling_waits_for_sidecar_too():
    """compiling that reaches :3333 200 but with a DEAD sidecar pipe (config asserts
    it) does NOT return READY on the 200 alone — the patient wait composes the
    sidecar assertion (a serving-but-pipe-dead runtime is not READY)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        cfg = {**_M4_CONFIG_FRONTEND, "assert_sidecar_connected": True}
        calls = {"probe": 0, "restart": 0}

        def probe():
            calls["probe"] += 1
            # backend answers 200 from the 2nd probe on
            return (200, {"tools": ["render_chart"]}) if calls["probe"] >= 2 else (0, None)

        result = lazy_core.ensure_runtime(
            Path(td),
            config=cfg,
            probe=probe,
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=lambda: True,  # Vite up → compiling
            sidecar_check=lambda: False,  # pipe stays dead → never READY
        )
        # A 200 with a dead pipe never satisfies the patient wait → BLOCKED, and
        # the patient wait never kill-restarts (sidecar reconnection is awaited).
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 0, (
            f"the compiling+sidecar wait must not restart: {calls}"
        )




def test_ensure_runtime_m4_genuine_dead_unchanged_bounded_recovery():
    """genuine dead (both ports down: :3333 refused AND :1420 down) → UNCHANGED
    bounded _recover_runtime (restart fired, capped at 5, exhausts to BLOCKED with
    the GENERIC _blocked_blocker — NOT the cold-compile text). The preserved
    crash-recovery path."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=_M4_CONFIG_FRONTEND,
            probe=lambda: (0, None),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite ALSO down → genuinely dead
        )
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 5, f"genuine dead must run bounded recovery: {calls}"
        assert result["terminal_blocker"] == lazy_core._blocked_blocker(5), (
            "genuine dead must carry the GENERIC blocker, not cold-compile text"
        )




def test_ensure_runtime_m4_default_off_byte_identical_dead_recovery():
    """default-off / repo-agnostic (a non-:1420 repo overrides the frontend signal
    OFF via an empty frontend_health_url) → frontend_probe default-binds to
    `lambda: False`, so every non-serving runtime classifies `dead` ⇒ byte-identical
    to today's DEAD→recovery path (bounded recovery, generic _blocked_blocker). The
    discriminator is inert when the frontend signal is absent — no injected
    frontend_probe needed, exercising the real config-driven default binding."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        lock = _owned_lock(start_time=111.0)
        # A repo with NO :1420 frontend overrides the key off (the base default
        # carries :1420 — the AlgoBooth-flavored harness default — so a non-:1420
        # repo opts out exactly the way the sidecar key opts in/out).
        cfg_no_frontend = {**_M4_CONFIG, "frontend_health_url": ""}
        calls = {"restart": 0}

        result = lazy_core.ensure_runtime(
            Path(td),
            config=cfg_no_frontend,  # frontend off → frontend_probe binds lambda: False
            probe=lambda: (0, None),
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: lock,
            live_session_id=_SESSION,
            kernel_start_time_fn=lambda pid, **kw: 111.0,
            sleep=lambda s: None,
            # NO injected frontend_probe → exercises the config-driven default bind.
        )
        assert result["state"] == "BLOCKED", result
        assert calls["restart"] == 5, f"default-off must run today's recovery: {calls}"
        assert result["terminal_blocker"] == lazy_core._blocked_blocker(5), result




def test_ensure_runtime_handler_no_marker_falls_back_to_legacy_superset():
    """No live run marker → live_session_id None → ensure_runtime runs the legacy
    boot/ready flow but STILL returns the verdict superset (state + the retained
    legacy fields), so the CLI never emits a key-missing dict."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # live_session_id None + no Identity callables → legacy mode.
        result = lazy_core.ensure_runtime(
            Path(td), config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True, stale_check=lambda: False,
        )
        assert _M4_KEYS.issubset(result.keys()), result
        assert result["state"] in lazy_core._RUNTIME_STATES, result
        assert result["health_code"] == 200, result
        assert "status" in result, "legacy status field must be retained"




# ---------------------------------------------------------------------------
# adhoc-ensure-runtime-test-injects-signal-under-test — production-binding
# test-discipline guard (Phases 1 + 2).
# ---------------------------------------------------------------------------
#
# A `test_ensure_runtime_production_*` test must reach the OS signal under test
# by swapping `lazy_core.runtimeplane.subprocess` / `lazy_core.runtimeplane.time` and letting the DEFAULT
# `restart` / `boot_alive` closures DERIVE the signal — it must NOT inject the
# derivation itself as a keyword (`boot_alive=` / `restart=`), and a spawn-binding
# production test must drive a FAITHFUL subprocess double with real Windows
# spawn-resolution semantics (`_WindowsSpawnSemanticsSubprocess`), not an
# always-succeeds `_FakeSubprocess` that hides the `CreateProcess` defect.
#
# These two guards mirror the `_collect_orphaned_test_names` /
# `test_no_orphaned_test_functions` / `test_dead_coverage_guard_detects_orphan_by_name`
# trio: a pure AST collector + a positive self-checking meta-test (GREEN on the
# live suite) + a negative-fixture test (proves the guard catches a synthetic
# violator AND does not flag an allow-listed sibling).

# The signal-under-test derivations that a production-binding test must NEVER
# inject as keywords (the default closures must derive them from the swapped
# `lazy_core.runtimeplane.subprocess`/`lazy_core.runtimeplane.time`).
_PRODUCTION_BINDING_SIGNAL_KWARGS = frozenset({"boot_alive", "restart"})



# Legitimate external-collaborator injections — NEVER flagged. These are real
# seams `ensure_runtime` exposes for hermetic testing that do NOT short-circuit
# the signal under test.
_PRODUCTION_BINDING_ALLOWED_KWARGS = frozenset({
    "probe", "stale_check", "sidecar_check", "frontend_probe", "read_lock",
    "live_session_id", "kernel_start_time_fn", "sleep", "write_lock",
    "recover_identity", "config",
})



# The always-succeeds subprocess double (succeeds for any argv → hides the real
# Windows `CreateProcess` resolution defect) vs the faithful double that raises
# for a bare-token no-shell argv and succeeds only for the `shell=True` string.
_ALWAYS_SUCCEEDS_SPAWN_DOUBLE = "_FakeSubprocess"


_FAITHFUL_SPAWN_DOUBLE = "_WindowsSpawnSemanticsSubprocess"




def _iter_production_binding_test_defs(module_source: str):
    """Yield ``(node, name)`` for every top-level
    ``def test_ensure_runtime_production_*`` function in ``module_source``.

    AST (``ast.parse``) over regex so docstring/comment occurrences of the names
    are ignored — same rationale as ``_collect_orphaned_test_names``. Pure: takes
    source text, performs no I/O, so the negative fixtures can feed synthetic
    source.
    """
    tree = ast.parse(module_source)
    for node in tree.body:  # top-level only — production tests are module-level
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_ensure_runtime_production_"):
                yield node, node.name




def _call_is_ensure_runtime(call: "ast.Call") -> bool:
    """True iff ``call`` invokes ``ensure_runtime(...)`` or
    ``lazy_core.ensure_runtime(...)`` (the production entry point)."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id == "ensure_runtime"
    if isinstance(func, ast.Attribute):
        return func.attr == "ensure_runtime"
    return False




def _collect_production_binding_smells(module_source: str) -> list:
    """Phase 1 — pure AST collector: enumerate every
    ``def test_ensure_runtime_production_*`` and flag the SIGNAL-INJECTION smell —
    an ``ensure_runtime(...)`` call inside the function body carrying a
    ``boot_alive=`` or ``restart=`` keyword (the derivations the production code
    must DERIVE, not be handed).

    Returns a sorted, stable list of ``(test_name, injected_kwarg)`` tuples — one
    per offending injection. The legitimate external-collaborator kwargs
    (``_PRODUCTION_BINDING_ALLOWED_KWARGS``) are NEVER flagged; only the two
    signal derivations are smells. AST over regex (ignores docstring/comment
    occurrences), matching the ``_collect_orphaned_test_names`` rationale. Pure
    (``module_source`` parameter, no I/O) so the negative fixture can feed
    synthetic source.
    """
    smells: list = []
    for node, name in _iter_production_binding_test_defs(module_source):
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call) or not _call_is_ensure_runtime(sub):
                continue
            for kw in sub.keywords:
                # kw.arg is None for **kwargs unpacking — never a named signal.
                if kw.arg in _PRODUCTION_BINDING_SIGNAL_KWARGS:
                    smells.append((name, kw.arg))
    return sorted(set(smells))




def _names_used_in(node: "ast.AST") -> set:
    """The set of bare ``ast.Name`` ids referenced anywhere under ``node`` —
    used to detect which subprocess double class a production test constructs and
    whether it asserts on ``shell_spawns``."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}




def _assigns_lazy_core_subprocess_double(node: "ast.AST"):
    """If the function body assigns ``lazy_core.runtimeplane.subprocess`` (directly, or as part
    of a tuple ``lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time``),
    return the set of ``ast.Name`` ids used anywhere in the function (the double's
    class name appears among them where it is constructed). Returns None when the
    function never swaps ``lazy_core.runtimeplane.subprocess`` (not a spawn/subprocess-binding
    test at all).
    """
    def _is_lazy_core_chain(value: "ast.AST") -> bool:
        # Accept BOTH the legacy `lazy_core.subprocess` form (value is the bare
        # Name) and the post-decomposition `lazy_core.<submodule>.subprocess`
        # form (value is Attribute(<submodule>) over Name(lazy_core), for ANY
        # submodule — Phase-4 WU-4 moved the patch sites to `runtimeplane`;
        # Phase-4 WU-4 re-pointed them to `runtimeplane` with the plane) —
        # the collector must recognize the chain shape or the enforcer
        # meta-tests go silently vacuous.
        if isinstance(value, ast.Name) and value.id == "lazy_core":
            return True
        return (isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "lazy_core")

    swaps_subprocess = False
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Assign):
            continue
        for target in sub.targets:
            # Direct: lazy_core.runtimeplane.subprocess = ...   AND tuple: (lazy_core.runtimeplane.subprocess, ...) = ...
            elts = target.elts if isinstance(target, ast.Tuple) else [target]
            for elt in elts:
                if (isinstance(elt, ast.Attribute) and elt.attr == "subprocess"
                        and _is_lazy_core_chain(elt.value)):
                    swaps_subprocess = True
    if not swaps_subprocess:
        return None
    return _names_used_in(node)




def _collect_spawn_double_smells(module_source: str) -> list:
    """Phase 2 — extend the production-binding guard: flag a SPAWN-BINDING
    production test that drives an always-succeeds ``_FakeSubprocess`` instead of
    the faithful ``_WindowsSpawnSemanticsSubprocess``.

    Shares the AST walk with Phase 1 (``_iter_production_binding_test_defs``).
    A test is flagged iff ALL of:
      (a) it swaps ``lazy_core.runtimeplane.subprocess`` with a double (subprocess-binding);
      (b) it does NOT inject ``restart=`` (an injected restart bypasses the real
          spawn closure, so spawn-resolution semantics are moot — and that case is
          already the Phase-1 signal-injection smell);
      (c) it is SPAWN-BINDING — a conservative name/marker discriminator
          (⚖ scope-class, resolved at planning): the test name contains
          ``spawn`` OR its body asserts on ``shell_spawns``. This keeps a
          liveness/timing production test that legitimately uses
          ``_FakeSubprocess`` for the ``.poll()`` sub-case (e.g.
          ``test_ensure_runtime_production_boot_alive_live_handle_patient_waits``)
          OUT of scope — it neither names ``spawn`` nor asserts ``shell_spawns``;
      (d) it constructs ``_FakeSubprocess`` (always-succeeds) and NOT the faithful
          ``_WindowsSpawnSemanticsSubprocess``.

    Returns a sorted, stable list of offending ``test_name`` strings. Pure
    (no I/O) so the negative fixture can feed synthetic source.
    """
    smells: list = []
    for node, name in _iter_production_binding_test_defs(module_source):
        names_used = _assigns_lazy_core_subprocess_double(node)
        if names_used is None:
            continue  # (a) not a subprocess-binding test
        # (b) an injected restart= bypasses the spawn closure entirely.
        injects_restart = any(
            isinstance(sub, ast.Call) and _call_is_ensure_runtime(sub)
            and any(kw.arg == "restart" for kw in sub.keywords)
            for sub in ast.walk(node)
        )
        if injects_restart:
            continue
        # (c) spawn-binding discriminator. A SPAWN-RESOLUTION test is one whose
        # body asserts on `shell_spawns` — the attribute ONLY the faithful
        # `_WindowsSpawnSemanticsSubprocess` exposes to prove the `shell=True`
        # resolution path was taken. We deliberately do NOT key on a `*_spawn_*`
        # name substring: the live suite's
        # `test_ensure_runtime_production_wrapper_exits_early_patient_waits_one_spawn`
        # is a liveness/timing test (it asserts the patient-wait did not RE-spawn
        # via the shared `.spawns` COUNT, not spawn RESOLUTION) and legitimately
        # uses `_FakeSubprocess`; a name-substring marker would false-positive it.
        # The `shell_spawns` assertion is the tight, conservative signal that the
        # test is genuinely exercising Windows `CreateProcess` resolution.
        # (⚖ scope-class — see policy note below.)
        spawn_binding = ("shell_spawns" in names_used) or any(
            isinstance(sub, ast.Attribute) and sub.attr == "shell_spawns"
            for sub in ast.walk(node)
        )
        if not spawn_binding:
            continue  # liveness/timing test legitimately using _FakeSubprocess
        # (d) faithful double allowed; always-succeeds double is the smell.
        if _FAITHFUL_SPAWN_DOUBLE in names_used:
            continue
        if _ALWAYS_SUCCEEDS_SPAWN_DOUBLE in names_used:
            smells.append(name)
    return sorted(set(smells))


def test_ensure_runtime_production_tests_derive_not_inject_signal():
    """Phase 1 positive self-checking meta-test + WU-2 split generalization:
    every sibling test_*.py's ``test_ensure_runtime_production_*`` tests all
    reach the OS signal through the default closures (swapping
    ``lazy_core.runtimeplane.subprocess``/``time``) and inject NEITHER
    ``boot_alive=`` NOR ``restart=``, so the collector reports ``[]`` across
    the whole split package.

    GREEN today. It FAILS — naming the offending file + test + injected kwarg
    — if a future ``test_ensure_runtime_production_*`` injects the signal
    under test. Self-checking: this function reads every sibling module
    source (not just its own file), since the production tests it guards may
    live in a different split file than this meta-test.
    """
    _guard()
    all_smells: list = []
    for sibling in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        module_source = sibling.read_text(encoding="utf-8")
        for name, kwarg in _collect_production_binding_smells(module_source):
            all_smells.append((sibling.name, name, kwarg))
    assert all_smells == [], (
        "production-binding guard: the following test_ensure_runtime_production_* "
        "test(s) INJECT the signal under test as an ensure_runtime keyword instead "
        "of deriving it through the default closure — fix by swapping "
        f"lazy_core.runtimeplane.subprocess/time and passing neither boot_alive= nor restart=: {all_smells}"
    )




def test_production_binding_guard_detects_signal_injection():
    """Phase 1 negative fixture — feed synthetic module source containing a
    ``test_ensure_runtime_production_injects`` that calls
    ``lazy_core.ensure_runtime(..., boot_alive=lambda: True)`` and assert the
    collector reports it BY NAME with the injected kwarg (proving non-vacuity).

    A sibling ``test_ensure_runtime_production_clean`` passing only allow-listed
    kwargs (``probe=``/``stale_check=``) must NOT be reported (allow-list /
    would-it-fail proof against a tautological collector).
    """
    _guard()
    synthetic_source = (
        "def test_ensure_runtime_production_injects():\n"
        "    lazy_core.ensure_runtime(Path(td), boot_alive=lambda: True)\n"
        "\n"
        "def test_ensure_runtime_production_clean():\n"
        "    lazy_core.ensure_runtime(Path(td), probe=p, stale_check=sc)\n"
    )
    smells = _collect_production_binding_smells(synthetic_source)
    assert smells == [("test_ensure_runtime_production_injects", "boot_alive")], (
        "the guard must report the synthetic signal-injecting production test by "
        f"name with the injected kwarg, and NOT flag the allow-listed sibling; got {smells}"
    )


def test_spawn_binding_production_tests_use_faithful_double():
    """Phase 2 positive self-checking meta-test + WU-2 split generalization:
    every sibling test_*.py's spawn-binding production test
    (``test_ensure_runtime_production_restart_spawns_via_shell_on_windows_cold_boot``)
    already drives the faithful ``_WindowsSpawnSemanticsSubprocess``, so the
    spawn-double collector reports ``[]`` across the whole split package.

    GREEN today. It FAILS — naming the offending file + test — if a future
    spawn-binding production test reverts to an always-succeeds
    ``_FakeSubprocess``.
    """
    _guard()
    all_smells: list = []
    for sibling in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        module_source = sibling.read_text(encoding="utf-8")
        for name in _collect_spawn_double_smells(module_source):
            all_smells.append((sibling.name, name))
    assert all_smells == [], (
        "production-binding guard: the following spawn-binding "
        "test_ensure_runtime_production_* test(s) drive an always-succeeds "
        "_FakeSubprocess (which hides the Windows CreateProcess resolution defect) "
        "instead of the faithful _WindowsSpawnSemanticsSubprocess — switch to the "
        f"faithful double: {all_smells}"
    )




def test_spawn_double_guard_detects_always_succeeds_double():
    """Phase 2 negative fixture — three synthetic production tests:

    1. a SPAWN-BINDING test using the always-succeeds ``_FakeSubprocess`` and
       asserting on ``shell_spawns`` → MUST be reported (non-vacuity);
    2. a sibling spawn test using the faithful
       ``_WindowsSpawnSemanticsSubprocess`` → MUST NOT be reported (faithful-double
       allow);
    3. a sibling LIVENESS/TIMING test (no ``spawn`` in name, no ``shell_spawns``
       assertion) that legitimately uses ``_FakeSubprocess`` for the ``.poll()``
       sub-case → MUST NOT be reported (the false-positive guard pinning
       ``test_ensure_runtime_production_boot_alive_live_handle_patient_waits``).
    """
    _guard()
    synthetic_source = (
        "def test_ensure_runtime_production_spawn_bad():\n"
        "    fake_sub = _FakeSubprocess(handle)\n"
        "    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time\n"
        "    lazy_core.ensure_runtime(Path(td), probe=probe)\n"
        "    assert fake_sub.shell_spawns >= 1\n"
        "\n"
        "def test_ensure_runtime_production_spawn_good():\n"
        "    fake_sub = _WindowsSpawnSemanticsSubprocess(handle)\n"
        "    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time\n"
        "    lazy_core.ensure_runtime(Path(td), probe=probe)\n"
        "    assert fake_sub.shell_spawns >= 1\n"
        "\n"
        "def test_ensure_runtime_production_liveness_ok():\n"
        "    fake_sub = _FakeSubprocess(handle)\n"
        "    lazy_core.runtimeplane.subprocess, lazy_core.runtimeplane.time = fake_sub, fake_time\n"
        "    lazy_core.ensure_runtime(Path(td), probe=probe)\n"
        "    assert result['state'] == 'READY'\n"
    )
    smells = _collect_spawn_double_smells(synthetic_source)
    assert smells == ["test_ensure_runtime_production_spawn_bad"], (
        "the guard must report ONLY the spawn-binding always-succeeds-double test; "
        "the faithful-double spawn test and the liveness/timing test that "
        f"legitimately uses _FakeSubprocess must NOT be flagged; got {smells}"
    )




def test_load_bug_queue_for_merged_breadcrumb_on_load_failure():
    """WU-3 (RED against the bare-except): when the bug-side loader raises,
    _load_bug_queue_for_merged emits a _diag breadcrumb AND still returns [].

    Forces the failure by monkeypatching importlib.util.module_from_spec (which the
    function calls to materialize bug-state.py) to return a fake module whose
    load_bug_queue raises. Pre-fix the bare-except swallows the error silently (no
    breadcrumb) — RED. Post-fix a _DIAGNOSTICS entry naming the failure appears.
    """
    _guard()
    import importlib.util as _ilu
    ls = _load_lazy_state_module()

    class _FakeMod:
        @staticmethod
        def load_bug_queue(repo_root):
            raise RuntimeError("forced bug-side load failure")

    real_module_from_spec = _ilu.module_from_spec

    def _fake_module_from_spec(spec):
        # Only intercept the bug-state load (the function names it
        # "_bug_state_for_merged"); pass everything else through untouched.
        if getattr(spec, "name", "") == "_bug_state_for_merged":
            return _FakeMod()
        return real_module_from_spec(spec)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # The function only reaches the load (and thus the failure) when
        # bug-state.py exists — it does, as a sibling of lazy-state.py.
        lazy_core.clear_diagnostics()
        _ilu.module_from_spec = _fake_module_from_spec
        try:
            result = ls._load_bug_queue_for_merged(root)
        finally:
            _ilu.module_from_spec = real_module_from_spec

        assert result == [], (
            f"a bug-side load failure must still fail-open to [], got {result!r}"
        )
        breadcrumbs = [d for d in lazy_core._DIAGNOSTICS
                       if "merged-view bug-side load" in d
                       or "bug-side load failed" in d]
        assert breadcrumbs, (
            "a forced bug-side load failure must emit a _diag breadcrumb naming the "
            f"failure; _DIAGNOSTICS={lazy_core._DIAGNOSTICS!r}"
        )




# ===========================================================================
# Phase 1 (long-build-and-runtime-ownership) — detached-spawn primitive +
# verifiable on-disk runtime-ownership sentinel.
#
# All four WUs add NEW top-level functions to lazy_core.py, all hermetic via
# injected `spawn`/`platform`/`replace`/`kernel_start_time_fn` callables — no
# real cross-platform host needed for the unit layer.
#   WU-1: spawn_detached         (cross-platform detached spawn + breakaway fallback)
#   WU-2: kernel_start_time      (temporal-identity extraction, both OS branches)
#   WU-3: write/read_runtime_lock + new _ENSURE_RUNTIME_DEFAULT_CONFIG keys
#   WU-4: verify_runtime_ownership
# ===========================================================================

# Windows creationflags constants (LD6 / SPEC M2).
_DETACHED_PROCESS = 0x00000008


_CREATE_NEW_PROCESS_GROUP = 0x00000200


_CREATE_BREAKAWAY_FROM_JOB = 0x01000000




def test_runtime_ownership_symbols_present():
    """Phase 1 public symbols exist on lazy_core."""
    _guard()
    expected = [
        "spawn_detached",
        "kernel_start_time",
        "write_runtime_lock",
        "read_runtime_lock",
        "verify_runtime_ownership",
    ]
    missing = [sym for sym in expected if not hasattr(lazy_core, sym)]
    assert not missing, f"missing symbols: {missing}"




# --- WU-1: spawn_detached -------------------------------------------------

class _FakeProc:
    """Stand-in for subprocess.Popen — records nothing, just carries a pid."""

    def __init__(self, pid: int = 4321):
        self.pid = pid




def test_spawn_detached_windows_carries_breakaway_flags():
    """Windows branch: first spawn call carries
    DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB."""
    _guard()
    calls = []

    def fake_spawn(cmd, **kwargs):
        calls.append(kwargs)
        return _FakeProc(pid=111)

    result = lazy_core.spawn_detached(
        ["x"], cwd="/tmp", spawn=fake_spawn, platform="win32",
        kernel_start_time_fn=lambda pid, **k: 9.0,
    )
    assert len(calls) == 1, f"expected one spawn call, got {len(calls)}"
    flags = calls[0].get("creationflags")
    expected = (_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
                | _CREATE_BREAKAWAY_FROM_JOB)
    assert flags == expected, f"expected breakaway flags {expected:#x}, got {flags!r}"
    assert result["pid"] == 111
    assert result["start_time"] == 9.0




def test_spawn_detached_windows_breakaway_denied_falls_back():
    """Windows branch: an OSError on the breakaway attempt (ERROR_ACCESS_DENIED)
    triggers a SECOND spawn WITHOUT CREATE_BREAKAWAY_FROM_JOB, and the function
    returns {pid, start_time} from the successful fallback."""
    _guard()
    calls = []

    def fake_spawn(cmd, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise OSError("ERROR_ACCESS_DENIED")
        return _FakeProc(pid=222)

    result = lazy_core.spawn_detached(
        ["x"], cwd="/tmp", spawn=fake_spawn, platform="win32",
        kernel_start_time_fn=lambda pid, **k: 5.5,
    )
    assert len(calls) == 2, f"expected breakaway then fallback (2 calls), got {len(calls)}"
    # First call HAD breakaway; second (fallback) must NOT.
    assert calls[0]["creationflags"] & _CREATE_BREAKAWAY_FROM_JOB
    assert not (calls[1]["creationflags"] & _CREATE_BREAKAWAY_FROM_JOB), \
        "fallback spawn must drop CREATE_BREAKAWAY_FROM_JOB"
    assert calls[1]["creationflags"] == (_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP)
    assert result["pid"] == 222
    assert result["start_time"] == 5.5




def test_spawn_detached_posix_sets_new_session():
    """POSIX branch: start_new_session=True is passed to spawn."""
    _guard()
    calls = []

    def fake_spawn(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return _FakeProc(pid=333)

    result = lazy_core.spawn_detached(
        ["mybin", "--flag"], cwd="/tmp", spawn=fake_spawn, platform="linux",
        which=lambda name: None,  # no systemd-run available
        kernel_start_time_fn=lambda pid, **k: 1.0,
    )
    assert len(calls) == 1
    _cmd, kwargs = calls[0]
    assert kwargs.get("start_new_session") is True, \
        "POSIX spawn must set start_new_session=True"
    assert result["pid"] == 333
    assert "creationflags" not in kwargs, "POSIX must not pass Windows creationflags"




def test_spawn_detached_posix_wraps_systemd_run_when_available():
    """POSIX branch: when systemd-run is on PATH, the command is wrapped in
    `systemd-run --user --scope --quiet --same-dir`."""
    _guard()
    captured = {}

    def fake_spawn(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc(pid=444)

    lazy_core.spawn_detached(
        ["mybin"], cwd="/tmp", spawn=fake_spawn, platform="linux",
        which=lambda name: "/usr/bin/systemd-run" if name == "systemd-run" else None,
        kernel_start_time_fn=lambda pid, **k: 1.0,
    )
    cmd = captured["cmd"]
    assert cmd[:5] == ["systemd-run", "--user", "--scope", "--quiet", "--same-dir"], \
        f"expected systemd-run wrapper prefix, got {cmd[:5]!r}"
    assert "mybin" in cmd, "the original binary must survive the wrap"




def test_spawn_detached_posix_setsid_fallback_when_no_systemd():
    """POSIX branch: when systemd-run is unavailable but setsid is, the command
    is wrapped with setsid + a nohup keep-alive fallback path."""
    _guard()
    captured = {}

    def fake_spawn(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc(pid=555)

    lazy_core.spawn_detached(
        ["mybin"], cwd="/tmp", spawn=fake_spawn, platform="linux",
        which=lambda name: "/usr/bin/setsid" if name == "setsid" else None,
        kernel_start_time_fn=lambda pid, **k: 1.0,
    )
    cmd = captured["cmd"]
    assert cmd[0] == "setsid", f"expected setsid fallback wrapper, got {cmd[0]!r}"
    assert "mybin" in cmd




def test_spawn_detached_never_sets_pdeathsig():
    """PR_SET_PDEATHSIG must NEVER be set (it would kill the child with the
    parent — the opposite of the requirement). No spawn kwarg references it,
    and the source must not invoke it."""
    _guard()
    captured = {}

    def fake_spawn(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return _FakeProc(pid=666)

    lazy_core.spawn_detached(
        ["mybin"], cwd="/tmp", spawn=fake_spawn, platform="linux",
        which=lambda name: None,
        kernel_start_time_fn=lambda pid, **k: 1.0,
    )
    for k in captured["kwargs"]:
        assert "pdeathsig" not in k.lower(), f"PR_SET_PDEATHSIG leaked via kwarg {k}"
    # The source must not INVOKE pdeathsig (a documentation mention in a comment
    # / docstring is fine). Strip comments+docstrings via AST and assert the
    # executable code never references prctl/PR_SET_PDEATHSIG/set_pdeathsig.
    src = inspect.getsource(lazy_core.spawn_detached)
    tree = ast.parse(src)
    code_names = {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    banned = {"PR_SET_PDEATHSIG", "prctl", "set_pdeathsig", "pdeathsig"}
    leaked = {b for b in banned if b in code_names}
    assert not leaked, f"spawn_detached must not invoke pdeathsig — found {leaked}"




def test_spawn_detached_returns_none_start_time_when_no_fn():
    """start_time is None when no kernel_start_time_fn is injected (WU-2 fills
    it in production; WU-1 is independently testable with the stub omitted)."""
    _guard()

    def fake_spawn(cmd, **kwargs):
        return _FakeProc(pid=777)

    result = lazy_core.spawn_detached(
        ["x"], cwd="/tmp", spawn=fake_spawn, platform="linux",
        which=lambda name: None,
    )
    assert result["pid"] == 777
    assert result["start_time"] is None




# --- WU-2: kernel_start_time ----------------------------------------------

def test_kernel_start_time_posix_parses_proc_stat():
    """POSIX: field 22 of /proc/[pid]/stat (clock ticks since boot) converts to
    a Unix epoch float via boot_time + ticks / clk_tck."""
    _guard()
    # Synthetic /proc/[pid]/stat: 52 fields. Field 22 (1-indexed) = starttime.
    # comm "(my proc)" contains spaces+parens to exercise the field-22 logic.
    fields = ["1", "(my proc)", "S"] + [str(i) for i in range(4, 53)]
    # Set field 22 (index 21) to a known tick value.
    fields[21] = "1000"
    stat_line = " ".join(fields)
    result = lazy_core.kernel_start_time(
        1, platform="linux",
        read_stat=lambda pid: stat_line,
        boot_time=2000.0,
        clk_tck=100,
    )
    # 2000.0 + 1000/100 = 2010.0
    assert result == 2010.0, f"expected 2010.0, got {result!r}"




def test_kernel_start_time_windows_converts_filetime():
    """Windows: a FILETIME (100ns intervals since 1601-01-01) converts to a
    Unix epoch float."""
    _guard()
    # FILETIME for 1970-01-01 00:00:00 UTC is 116444736000000000 (100ns units).
    # Add 10 seconds = 10 * 10_000_000 = 100_000_000 units → epoch 10.0.
    filetime = 116444736000000000 + 100_000_000
    result = lazy_core.kernel_start_time(
        1, platform="win32",
        get_process_times=lambda pid: filetime,
    )
    assert abs(result - 10.0) < 1e-6, f"expected ~10.0, got {result!r}"




def test_kernel_start_time_error_returns_none():
    """Best-effort: any error (unreadable /proc, raising stub) → None, never
    raises."""
    _guard()

    def boom(pid):
        raise OSError("no such pid")

    assert lazy_core.kernel_start_time(1, platform="linux", read_stat=boom) is None
    assert lazy_core.kernel_start_time(1, platform="win32", get_process_times=boom) is None
    # Malformed stat line (too few fields) → None.
    assert lazy_core.kernel_start_time(
        1, platform="linux", read_stat=lambda pid: "1 (x) S", boot_time=0.0, clk_tck=100,
    ) is None




# --- WU-3: write/read_runtime_lock + config keys --------------------------

def test_runtime_lock_round_trip_all_five_fields():
    """write → read returns all five LD1 fields equal."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        lazy_core.runtimeplane.write_runtime_lock(
            repo, pid=123, start_time=456.5, port=3333,
            artifact_hash="deadbeef", controller_session_id="sess-uuid",
        )
        lock = lazy_core.read_runtime_lock(repo)
        assert lock is not None
        assert lock["pid"] == 123
        assert lock["start_time"] == 456.5
        assert lock["port"] == 3333
        assert lock["artifact_hash"] == "deadbeef"
        assert lock["controller_session_id"] == "sess-uuid"




def test_runtime_lock_written_at_repo_root_with_config_filename():
    """The lock file lives at repo root under the _ENSURE_RUNTIME_DEFAULT_CONFIG
    lock_filename (NOT a hard-coded literal in the flow)."""
    _guard()
    cfg = lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG
    assert "lock_filename" in cfg, "config must carry lock_filename"
    assert "port" in cfg, "config must carry port"
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        lazy_core.runtimeplane.write_runtime_lock(
            repo, pid=1, start_time=1.0, port=cfg["port"],
            artifact_hash="h", controller_session_id="s",
        )
        assert (repo / cfg["lock_filename"]).exists(), \
            "lock must be written at repo root under cfg['lock_filename']"




def test_runtime_lock_atomic_write_no_partial_on_failure():
    """The write uses a temp file + os.replace (no partial production file when
    the replace fails mid-write)."""
    _guard()
    src = inspect.getsource(lazy_core.runtimeplane.write_runtime_lock)
    # Atomicity via the shared _atomic_write helper (temp + os.replace) OR a
    # direct os.replace — assert one of those is present, not a naive open(w).
    assert ("_atomic_write" in src) or ("os.replace" in src), \
        "write_runtime_lock must use an atomic temp-file + os.replace pattern"




def test_runtime_lock_read_missing_returns_none():
    """Missing lock file → None, never raises."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        assert lazy_core.read_runtime_lock(Path(td)) is None




def test_runtime_lock_read_corrupt_returns_none():
    """Corrupt JSON → None, never raises."""
    _guard()
    cfg = lazy_core._ENSURE_RUNTIME_DEFAULT_CONFIG
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        (repo / cfg["lock_filename"]).write_text("{not json", encoding="utf-8")
        assert lazy_core.read_runtime_lock(repo) is None




# --- WU-4: verify_runtime_ownership ---------------------------------------

def _lock_fixture():
    return {
        "controller_session_id": "live-sess",
        "pid": 999,
        "start_time": 123.0,
        "port": 3333,
        "artifact_hash": "h",
    }




def test_verify_ownership_match_returns_true():
    """Recorded start_time == kernel start_time AND session matches → True."""
    _guard()
    ok = lazy_core.verify_runtime_ownership(
        _lock_fixture(), live_session_id="live-sess",
        kernel_start_time_fn=lambda pid, **k: 123.0,
    )
    assert ok is True




def test_verify_ownership_divergent_start_time_false():
    """PID reused by a foreign process: kernel start_time diverges → False."""
    _guard()
    ok = lazy_core.verify_runtime_ownership(
        _lock_fixture(), live_session_id="live-sess",
        kernel_start_time_fn=lambda pid, **k: 999.0,
    )
    assert ok is False




def test_verify_ownership_foreign_controller_false():
    """controller_session_id != live session → False (a crashed prior
    controller's runtime)."""
    _guard()
    ok = lazy_core.verify_runtime_ownership(
        _lock_fixture(), live_session_id="other-sess",
        kernel_start_time_fn=lambda pid, **k: 123.0,
    )
    assert ok is False




def test_verify_ownership_missing_pid_false():
    """Process dead: kernel_start_time_fn returns None → False."""
    _guard()
    ok = lazy_core.verify_runtime_ownership(
        _lock_fixture(), live_session_id="live-sess",
        kernel_start_time_fn=lambda pid, **k: None,
    )
    assert ok is False




# --- Integration: the four-function round-trip (Post-Phase seam) ----------

def test_runtime_ownership_round_trip_compose():
    """spawn_detached → write_runtime_lock → read_runtime_lock →
    verify_runtime_ownership composes end-to-end with injected callables (the
    seam Phase 2's reworked ensure_runtime builds on)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)

        def fake_spawn(cmd, **kwargs):
            return _FakeProc(pid=2024)

        spawned = lazy_core.spawn_detached(
            ["runtime"], cwd=str(repo), spawn=fake_spawn, platform="linux",
            which=lambda name: None,
            kernel_start_time_fn=lambda pid, **k: 77.0,
        )
        lazy_core.runtimeplane.write_runtime_lock(
            repo, pid=spawned["pid"], start_time=spawned["start_time"],
            port=3333, artifact_hash="abc", controller_session_id="S1",
        )
        lock = lazy_core.read_runtime_lock(repo)
        assert lock["pid"] == 2024 and lock["start_time"] == 77.0
        assert lazy_core.verify_runtime_ownership(
            lock, live_session_id="S1",
            kernel_start_time_fn=lambda pid, **k: 77.0,
        ) is True
        # A divergent live session breaks ownership.
        assert lazy_core.verify_runtime_ownership(
            lock, live_session_id="S2",
            kernel_start_time_fn=lambda pid, **k: 77.0,
        ) is False




# ===========================================================================
# Phase 3 (long-build-and-runtime-ownership) WU-2 — run_transient_build:
# the M3.2 Transient Build contract over the single spawn_detached primitive.
#
# LD5: one cross-platform spawn primitive, TWO supervisory contracts. The
# Persistent Service contract (Phase 2's ensure_runtime) leaves the process
# detached and behind for re-attach in later cycles. The Transient Build
# contract — run_transient_build — spawns detached ONLY to survive subagent
# reaping, but synchronously AWAITS the build's conclusion (capturing stdout for
# telemetry), then returns. It does NOT write `.runtime.lock.json` and does NOT
# abandon the process for a future cycle. Atomic Artifact Promotion is composed
# AROUND it in Phase 4 — kept OUT of run_transient_build itself.
#
# All hermetic via injected `spawn`/`wait` callables — no real build process.
# ===========================================================================


def test_run_transient_build_symbol_present():
    """run_transient_build is a public symbol on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "run_transient_build"), (
        "lazy_core.run_transient_build missing — Phase 3 WU-2 not implemented"
    )




def test_run_transient_build_spawns_through_detached_path():
    """The build is spawned via spawn_detached (the injected `spawn` records the
    detached creationflags / start_new_session) — survives a subagent tear by
    construction, NOT a bare subprocess.run."""
    _guard()
    spawn_calls = []

    def fake_spawn(cmd, **kwargs):
        spawn_calls.append(kwargs)
        return _FakeProc(pid=7777)

    lazy_core.run_transient_build(
        ["cargo", "build", "--release"], cwd="/tmp",
        spawn=fake_spawn, wait=lambda proc: (0, "ok"),
        platform="linux", which=lambda name: None,
    )
    assert len(spawn_calls) == 1, (
        f"expected exactly one detached spawn, got {len(spawn_calls)}"
    )
    # POSIX detached signature: start_new_session=True, no Windows creationflags.
    assert spawn_calls[0].get("start_new_session") is True, (
        "the build must be spawned through the DETACHED path (spawn_detached) — "
        f"start_new_session not set; kwargs: {spawn_calls[0]!r}"
    )




def test_run_transient_build_windows_detached_flags():
    """On Windows the build is spawned with the DETACHED_PROCESS breakaway flags
    (proof it routes through spawn_detached, not a plain Popen)."""
    _guard()
    spawn_calls = []

    def fake_spawn(cmd, **kwargs):
        spawn_calls.append(kwargs)
        return _FakeProc(pid=8888)

    lazy_core.run_transient_build(
        ["tauri", "build"], cwd="C:\\repo",
        spawn=fake_spawn, wait=lambda proc: (0, ""),
        platform="win32",
    )
    flags = spawn_calls[0].get("creationflags")
    expected = (_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
                | _CREATE_BREAKAWAY_FROM_JOB)
    assert flags == expected, (
        f"Windows transient build must carry detached breakaway flags "
        f"{expected:#x}; got {flags!r}"
    )




def test_run_transient_build_awaits_and_returns_exit_code_and_stdout():
    """The contract synchronously AWAITS conclusion (injected `wait` returns an
    exit code + stdout) and returns {exit_code, stdout, ...} — NOT abandoned."""
    _guard()

    def fake_wait(proc):
        return (0, "Compiling… Finished release [optimized] target(s)")

    result = lazy_core.run_transient_build(
        ["cargo", "build", "--release"], cwd="/tmp",
        spawn=lambda cmd, **k: _FakeProc(pid=9001),
        wait=fake_wait, platform="linux", which=lambda name: None,
    )
    assert result["exit_code"] == 0, f"expected exit_code 0; got {result!r}"
    assert "Finished release" in result["stdout"], (
        f"stdout must be captured for telemetry; got {result!r}"
    )




def test_run_transient_build_propagates_nonzero_exit():
    """A failing build's non-zero exit code is propagated (the orchestrator
    needs it to skip Atomic Artifact Promotion in Phase 4)."""
    _guard()
    result = lazy_core.run_transient_build(
        ["npm", "run", "build"], cwd="/tmp",
        spawn=lambda cmd, **k: _FakeProc(pid=9002),
        wait=lambda proc: (101, "error[E0277]: the trait bound is not satisfied"),
        platform="linux", which=lambda name: None,
    )
    assert result["exit_code"] == 101, f"non-zero exit must propagate; got {result!r}"




def test_run_transient_build_does_not_write_runtime_lock():
    """LD5 two-contracts distinction: the Transient Build contract does NOT write
    `.runtime.lock.json` and does NOT register a persistent process for a future
    cycle. Assert no lock file appears at the repo root after the build."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        lock_path = repo / ".runtime.lock.json"
        assert not lock_path.exists(), "precondition: no lock before the build"

        lazy_core.run_transient_build(
            ["cargo", "build", "--release"], cwd=str(repo),
            spawn=lambda cmd, **k: _FakeProc(pid=9003),
            wait=lambda proc: (0, "done"),
            platform="linux", which=lambda name: None,
        )
        assert not lock_path.exists(), (
            "run_transient_build must NOT write .runtime.lock.json (that is the "
            "Persistent Service contract's job — LD5 two-contracts distinction)"
        )




def test_run_transient_build_does_not_call_lock_writer(monkeypatch=None):
    """Defense-in-depth: even with an injected spy, write_runtime_lock is NEVER
    invoked by run_transient_build (the persistent path is structurally absent)."""
    _guard()
    called = {"n": 0}
    original = lazy_core.runtimeplane.write_runtime_lock

    def spy(*args, **kwargs):
        called["n"] += 1
        return original(*args, **kwargs)

    lazy_core.runtimeplane.write_runtime_lock = spy
    try:
        lazy_core.run_transient_build(
            ["tauri", "build"], cwd="/tmp",
            spawn=lambda cmd, **k: _FakeProc(pid=9004),
            wait=lambda proc: (0, ""),
            platform="linux", which=lambda name: None,
        )
    finally:
        lazy_core.runtimeplane.write_runtime_lock = original
    assert called["n"] == 0, (
        "run_transient_build must never call write_runtime_lock — the lock writer "
        "belongs to the Persistent Service contract only"
    )




# ===========================================================================
# Phase 4 (long-build-and-runtime-ownership) WU-1 — promote_artifact_atomically:
# Atomic Artifact Promotion (SPEC M5 Detect; LD4 detect-half).
#
# Composed AROUND run_transient_build (NOT inside it): the build writes into a
# staging dir, and the artifact is `os.replace()`d into the final path ONLY on
# `exit_code == 0` (atomic NTFS MoveFileEx / POSIX rename). A non-zero exit (a
# torn / failed build) leaves the production artifact UNTOUCHED — no partial
# promotion. Injectable `replace` keeps `--test` hermetic and lets the atomicity
# ordering be asserted (the single mutation is os.replace, not copy-then-delete).
# ===========================================================================


def test_promote_artifact_atomically_symbol_present():
    """promote_artifact_atomically is a public symbol on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "promote_artifact_atomically"), (
        "lazy_core.promote_artifact_atomically missing — Phase 4 WU-1 not implemented"
    )




def test_promote_artifact_atomically_exit0_promotes_via_replace():
    """exit_code == 0: the injected `replace` is called staging→final exactly
    once → {promoted: True}; the call is os.replace (atomic rename), the single
    mutation (NOT a copy-then-delete)."""
    _guard()
    replace_calls = []

    def fake_replace(src, dst):
        replace_calls.append((str(src), str(dst)))

    result = lazy_core.promote_artifact_atomically(
        "/repo/target/release_staging", "/repo/target/release",
        exit_code=0, replace=fake_replace,
    )
    assert result["promoted"] is True, f"exit 0 must promote; got {result!r}"
    assert len(replace_calls) == 1, (
        f"promotion must be a SINGLE atomic os.replace, not copy-then-delete; "
        f"got {len(replace_calls)} replace calls"
    )
    src, dst = replace_calls[0]
    assert src.endswith("release_staging") and dst.endswith("release"), (
        f"replace must move staging→final; got {replace_calls[0]!r}"
    )




def test_promote_artifact_atomically_nonzero_exit_leaves_production_untouched():
    """exit_code != 0 (torn/failed build): `replace` is NEVER called and the
    final artifact is untouched → {promoted: False, reason: ...}. This is the
    load-bearing no-partial-promotion guarantee — it MUST fail if promotion ran
    unconditionally."""
    _guard()
    replace_calls = []

    def fake_replace(src, dst):
        replace_calls.append((str(src), str(dst)))

    result = lazy_core.promote_artifact_atomically(
        "/repo/target/release_staging", "/repo/target/release",
        exit_code=101, replace=fake_replace,
    )
    assert result["promoted"] is False, (
        f"a non-zero exit must NOT promote; got {result!r}"
    )
    assert "reason" in result and result["reason"], (
        f"a non-promotion must carry a reason; got {result!r}"
    )
    assert len(replace_calls) == 0, (
        "replace must NEVER be called on a non-zero exit (no partial promotion); "
        f"got {replace_calls!r}"
    )




def test_promote_artifact_atomically_real_tempdir_exit0_moves_artifact():
    """Real temp-dir variant (default real os.replace): on exit 0 the staging
    artifact ends up at final_dir and no partial file remains at staging."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        staging = root / "release_staging"
        final = root / "release"
        staging.write_text("ARTIFACT-BYTES", encoding="utf-8")
        assert not final.exists(), "precondition: no final artifact yet"

        result = lazy_core.promote_artifact_atomically(
            str(staging), str(final), exit_code=0,
        )
        assert result["promoted"] is True, f"expected promotion; got {result!r}"
        assert final.exists(), "final artifact must exist after promotion"
        assert final.read_text(encoding="utf-8") == "ARTIFACT-BYTES", (
            "promoted artifact must carry the staging bytes"
        )
        assert not staging.exists(), (
            "staging must be gone after an atomic rename (no partial left behind)"
        )




def test_promote_artifact_atomically_real_tempdir_nonzero_leaves_final():
    """Real temp-dir variant: on a non-zero exit the existing final artifact is
    byte-for-byte untouched and the staging partial is NOT promoted."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        staging = root / "release_staging"
        final = root / "release"
        staging.write_text("PARTIAL-TORN", encoding="utf-8")
        final.write_text("GOOD-PRODUCTION", encoding="utf-8")

        result = lazy_core.promote_artifact_atomically(
            str(staging), str(final), exit_code=1,
        )
        assert result["promoted"] is False, f"expected no promotion; got {result!r}"
        assert final.read_text(encoding="utf-8") == "GOOD-PRODUCTION", (
            "the production artifact must be untouched on a torn build"
        )




# ===========================================================================
# Phase 4 (long-build-and-runtime-ownership) WU-2 — reconcile_cycle_begin_git_
# consistency: the --cycle-begin git-consistency reconciliation (SPEC M5 Detect).
#
# A pre-boot `.git/index.lock` (creation/mtime OLDER than the orchestrator /
# run-marker boot stamp) ⇒ a previous op was torn ⇒ remove the stale lock and
# `git clean -fdx` the staging dir, neutralizing the uncommitted delta before the
# next cycle. Best-effort + fail-open: a fresh/own lock is PRESERVED (never
# clobber a live git op); no lock / non-git tree → no-op, never raises.
#
# It COMPOSES with — does NOT duplicate — the existing --cycle-end friction
# detector: a torn-build delta neutralized here must not subsequently false-trip
# detect_cycle_bracket_friction's unexpected-commits / cycle-bracket-break.
# ===========================================================================


def test_reconcile_cycle_begin_symbol_present():
    """reconcile_cycle_begin_git_consistency is a public symbol on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "reconcile_cycle_begin_git_consistency"), (
        "lazy_core.reconcile_cycle_begin_git_consistency missing — "
        "Phase 4 WU-2 not implemented"
    )




def test_reconcile_stale_lock_removed_and_staging_cleaned():
    """Stale pre-boot index.lock (mtime < boot stamp) → removed + staging dir
    git-cleaned; reconciliation recorded."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = _make_git_tree(Path(td))
        lock = repo / ".git" / "index.lock"
        lock.write_text("", encoding="utf-8")
        # Make the lock OLD relative to a boot stamp far in the future.
        old = 1_000.0
        os.utime(lock, (old, old))
        boot_stamp = 2_000_000_000.0  # well after the lock mtime

        # An uncommitted staging delta that the git clean should remove.
        staging = repo / "target" / "release_staging"
        staging.mkdir(parents=True)
        (staging / "torn.bin").write_text("partial", encoding="utf-8")

        result = lazy_core.reconcile_cycle_begin_git_consistency(
            repo, boot_stamp=boot_stamp, staging_dir=str(staging),
        )
        assert result["reconciled"] is True, f"expected reconciliation; got {result!r}"
        assert result["removed_lock"] is True, f"stale lock must be removed; got {result!r}"
        assert not lock.exists(), "the stale index.lock must be gone on disk"
        assert result.get("staging_cleaned") is True, (
            f"staging dir must be git-cleaned; got {result!r}"
        )
        assert not (staging / "torn.bin").exists(), (
            "git clean -fdx must remove the uncommitted staging partial"
        )




def test_reconcile_fresh_lock_preserved():
    """Fresh/own lock (mtime >= boot stamp) → PRESERVED (never clobber a live
    git op). MUST fail if the reconciliation removed a live lock."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = _make_git_tree(Path(td))
        lock = repo / ".git" / "index.lock"
        lock.write_text("", encoding="utf-8")
        # Lock newer than the boot stamp → a live in-flight git op.
        fresh = 2_000_000_500.0
        os.utime(lock, (fresh, fresh))
        boot_stamp = 2_000_000_000.0  # before the lock mtime

        result = lazy_core.reconcile_cycle_begin_git_consistency(
            repo, boot_stamp=boot_stamp,
        )
        assert result["removed_lock"] is False, (
            f"a fresh/own lock must NOT be removed; got {result!r}"
        )
        assert lock.exists(), "the fresh index.lock must survive (live git op)"




def test_reconcile_no_lock_is_noop():
    """No index.lock present → no-op, never raises, reconciled False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = _make_git_tree(Path(td))
        result = lazy_core.reconcile_cycle_begin_git_consistency(
            repo, boot_stamp=2_000_000_000.0,
        )
        assert result["reconciled"] is False, f"no lock → no-op; got {result!r}"
        assert result["removed_lock"] is False




def test_reconcile_non_git_tree_is_noop_fail_open():
    """Non-git tree → no-op, never raises (fail-open; the --cycle-begin write
    must always proceed)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "not-a-repo"
        plain.mkdir()
        # Must not raise.
        result = lazy_core.reconcile_cycle_begin_git_consistency(
            plain, boot_stamp=2_000_000_000.0,
        )
        assert isinstance(result, dict), f"must return a dict; got {result!r}"
        assert result["reconciled"] is False, f"non-git → no-op; got {result!r}"


# ---------------------------------------------------------------------------
# git_safe_push (net-new — RED until lazy_core/runtimeplane.py implements it).
#
# SPEC Requirement 2 (Git safety): "fetch + fast-forward before every push;
# bounded push-retry on a non-ff rejection (never --force)". Validation row 2:
# "Fetch+ff+retry succeeds; no --force; bounded attempts."
#
# Hermetic via an injected `run(*args)` (the _git(repo_root, *args) shape,
# called with the git args only — mirrors probe_binary_capability's injected
# `run` above) and an injected `sleep` recorder so retries never really sleep.
# ---------------------------------------------------------------------------

class _FakeGitCompleted:
    """subprocess.CompletedProcess stand-in carrying stdout/stderr — the
    module-level _FakeCompleted above (used by the probe_binary_capability
    fixtures) only carries .returncode, so git_safe_push's non-ff-rejection
    detection (which inspects stderr) needs this local twin with the same
    minimal-stand-in style."""

    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


_NON_FF_REJECTION_STDERR = (
    "To github.com/example/repo.git\n"
    " ! [rejected]        main -> main (non-fast-forward)\n"
    "error: failed to push some refs to 'github.com/example/repo.git'\n"
)


def _make_git_safe_push_fake(push_results):
    """Build a fake run(*args) for git_safe_push tests.

    push_results: list of _FakeGitCompleted returned on successive PUSH
    invocations (in call order); once exhausted the LAST entry repeats (so a
    single-element list models "every push attempt is rejected"). Every
    non-push invocation (fetch / merge / rebase fast-forward) unconditionally
    succeeds (returncode 0) — these fixtures model the retry trigger solely
    via the push outcome, per the SPEC's non-ff-rejection contract.

    Returns (run, calls): `calls` records every composed argv tuple, in
    order, for both the never-force scan and the fetch-before-retry ordering
    assertion.
    """
    calls = []
    state = {"push_n": 0}

    def run(*args):
        calls.append(args)
        if "push" in args:
            idx = min(state["push_n"], len(push_results) - 1)
            state["push_n"] += 1
            return push_results[idx]
        return _FakeGitCompleted(0, "", "")

    return run, calls


def test_git_safe_push_retry_then_succeed():
    """(a) Retry-then-succeed: a non-fast-forward REJECTION on the FIRST push
    attempt followed by SUCCESS on the second → status 'pushed', retried == 1.
    Also asserts the fetch+ff demonstrably ran again BEFORE the retried push
    (a git call carrying 'fetch' appears strictly between the two push
    calls' argv)."""
    _guard()
    run, calls = _make_git_safe_push_fake([
        _FakeGitCompleted(1, "", _NON_FF_REJECTION_STDERR),
        _FakeGitCompleted(0, "", ""),
    ])
    sleeps = []

    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.git_safe_push(
            Path(td), branch="main", remote="origin",
            run=run, sleep=lambda s: sleeps.append(s), max_retries=3,
        )

    assert result["status"] == "pushed", result
    assert result["retried"] == 1, result

    push_indices = [i for i, c in enumerate(calls) if "push" in c]
    assert len(push_indices) == 2, f"expected exactly 2 push attempts: {calls}"
    between = calls[push_indices[0] + 1: push_indices[1]]
    assert any("fetch" in c for c in between), (
        f"no re-fetch between the rejected push and the retried push: {calls}"
    )


def test_git_safe_push_never_composes_force():
    """(b) Never force: across EVERY attempt composed by git_safe_push —
    including the retried push, so the retry path's argv is inspected too —
    no argv may contain --force, -f, or --force-with-lease."""
    _guard()
    run, calls = _make_git_safe_push_fake([
        _FakeGitCompleted(1, "", _NON_FF_REJECTION_STDERR),
        _FakeGitCompleted(0, "", ""),
    ])

    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.git_safe_push(
            Path(td), branch="main", remote="origin",
            run=run, sleep=lambda s: None, max_retries=3,
        )

    assert result["status"] == "pushed", result
    assert result["retried"] >= 1, "fixture must exercise the retry path"

    forbidden = {"--force", "-f", "--force-with-lease"}
    for argv in calls:
        hit = forbidden.intersection(argv)
        assert not hit, f"forbidden force flag {hit} composed in argv {argv!r}"


def test_git_safe_push_bounded_retry_returns_structured_conflict():
    """(c) Bounded retry / structured conflict: a non-ff rejection on EVERY
    push attempt must bound the retries at max_retries (never loop forever)
    and return a structured conflict result — never raise, never hang."""
    _guard()
    max_retries = 2
    # Single-entry list ⇒ _make_git_safe_push_fake repeats the rejection on
    # every push call — "every push attempt is rejected".
    run, calls = _make_git_safe_push_fake([
        _FakeGitCompleted(1, "", _NON_FF_REJECTION_STDERR),
    ])

    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.git_safe_push(
            Path(td), branch="main", remote="origin",
            run=run, sleep=lambda s: None, max_retries=max_retries,
        )

    push_indices = [i for i, c in enumerate(calls) if "push" in c]
    assert len(push_indices) <= max_retries, (
        f"push attempted {len(push_indices)} times, bound is {max_retries}: {calls}"
    )
    assert result["status"] == "conflict", result
    assert result["retried"] == max_retries, result


_TESTS = [
    ("test_bug_state_algobooth_baseline_wellformed", test_bug_state_algobooth_baseline_wellformed),
    ("test_lazy_state_no_plans_real_impl_row_still_write_plan", test_lazy_state_no_plans_real_impl_row_still_write_plan),
    ("test_probe_binary_capability_exit_zero_true", test_probe_binary_capability_exit_zero_true),
    ("test_probe_binary_capability_exit_nonzero_false", test_probe_binary_capability_exit_nonzero_false),
    ("test_probe_binary_capability_windowsapps_alias_false", test_probe_binary_capability_windowsapps_alias_false),
    ("test_probe_binary_capability_run_error_false", test_probe_binary_capability_run_error_false),
    ("test_probe_env_capability_set_unset_falsy", test_probe_env_capability_set_unset_falsy),
    ("test_ensure_runtime_symbol_present", test_ensure_runtime_symbol_present),
    ("test_ensure_runtime_down_returns_booted", test_ensure_runtime_down_returns_booted),
    ("test_ensure_runtime_up_and_current_returns_ready", test_ensure_runtime_up_and_current_returns_ready),
    ("test_ensure_runtime_up_but_stale_returns_stale_rebuilt", test_ensure_runtime_up_but_stale_returns_stale_rebuilt),
    ("test_ensure_runtime_mcp_tool_absent_sets_false", test_ensure_runtime_mcp_tool_absent_sets_false),
    ("test_ensure_runtime_legacy_down_still_non200_is_not_ready", test_ensure_runtime_legacy_down_still_non200_is_not_ready),
    ("test_ensure_runtime_m4_vs_legacy_never_ready_when_non200", test_ensure_runtime_m4_vs_legacy_never_ready_when_non200),
    ("test_ensure_runtime_m4_ready_when_owned_current_healthy", test_ensure_runtime_m4_ready_when_owned_current_healthy),
    ("test_ensure_runtime_m4_stale_when_owned_but_stale", test_ensure_runtime_m4_stale_when_owned_but_stale),
    ("test_ensure_runtime_m4_hijacked_when_unowned_but_health_answers", test_ensure_runtime_m4_hijacked_when_unowned_but_health_answers),
    ("test_ensure_runtime_m4_dead_when_pid_missing_routes_to_recovery", test_ensure_runtime_m4_dead_when_pid_missing_routes_to_recovery),
    ("test_ensure_runtime_m4_dead_when_owned_pid_alive_but_health_refused_routes_to_recovery", test_ensure_runtime_m4_dead_when_owned_pid_alive_but_health_refused_routes_to_recovery),
    ("test_ensure_runtime_m4_no_lock_plus_health_answers_is_hijacked", test_ensure_runtime_m4_no_lock_plus_health_answers_is_hijacked),
    ("test_ensure_runtime_m4_no_lock_plus_down_routes_to_recovery", test_ensure_runtime_m4_no_lock_plus_down_routes_to_recovery),
    ("test_ensure_runtime_m4_legacy_callers_get_superset_dict", test_ensure_runtime_m4_legacy_callers_get_superset_dict),
    ("test_ensure_runtime_m4_stale_recovers_to_ready", test_ensure_runtime_m4_stale_recovers_to_ready),
    ("test_ensure_runtime_m4_dead_recovers_within_five", test_ensure_runtime_m4_dead_recovers_within_five),
    ("test_ensure_runtime_m4_dead_exhausts_to_blocked", test_ensure_runtime_m4_dead_exhausts_to_blocked),
    ("test_ensure_runtime_m4_hijacked_sets_blocker_never_restarts_never_kills", test_ensure_runtime_m4_hijacked_sets_blocker_never_restarts_never_kills),
    ("test_ensure_runtime_m4_ready_does_no_recovery", test_ensure_runtime_m4_ready_does_no_recovery),
    ("test_ensure_runtime_owned_unverified_serving_is_soft_ready", test_ensure_runtime_owned_unverified_serving_is_soft_ready),
    ("test_ensure_runtime_foreign_live_pid_stays_hijacked", test_ensure_runtime_foreign_live_pid_stays_hijacked),
    ("test_ensure_runtime_dead_pid_stays_dead", test_ensure_runtime_dead_pid_stays_dead),
    ("test_ensure_runtime_owned_unverified_non_200_not_soft_ready", test_ensure_runtime_owned_unverified_non_200_not_soft_ready),
    ("test_ensure_runtime_owned_unverified_no_mcp_tools_not_soft_ready", test_ensure_runtime_owned_unverified_no_mcp_tools_not_soft_ready),
    ("test_ensure_runtime_owned_unverified_stale_not_masked", test_ensure_runtime_owned_unverified_stale_not_masked),
    ("test_ensure_runtime_lock_none_serving_our_tools_is_soft_ready", test_ensure_runtime_lock_none_serving_our_tools_is_soft_ready),
    ("test_ensure_runtime_lock_none_foreign_surface_stays_hijacked", test_ensure_runtime_lock_none_foreign_surface_stays_hijacked),
    ("test_ensure_runtime_lock_none_non200_stays_dead", test_ensure_runtime_lock_none_non200_stays_dead),
    ("test_ensure_runtime_sidecar_disconnected_despite_health_200_routes_to_recovery", test_ensure_runtime_sidecar_disconnected_despite_health_200_routes_to_recovery),
    ("test_ensure_runtime_sidecar_check_default_off_preserves_ready", test_ensure_runtime_sidecar_check_default_off_preserves_ready),
    ("test_ensure_runtime_legacy_config_without_sidecar_key_does_not_crash", test_ensure_runtime_legacy_config_without_sidecar_key_does_not_crash),
    ("test_ensure_runtime_sidecar_connected_yields_ready", test_ensure_runtime_sidecar_connected_yields_ready),
    ("test_ensure_runtime_sidecar_default_probe_reads_is_connected", test_ensure_runtime_sidecar_default_probe_reads_is_connected),
    ("test_classify_compile_state_truth_table", test_classify_compile_state_truth_table),
    ("test_default_frontend_probe_returns_false_on_connection_error", test_default_frontend_probe_returns_false_on_connection_error),
    ("test_ensure_runtime_default_config_carries_frontend_keys", test_ensure_runtime_default_config_carries_frontend_keys),
    ("test_ensure_runtime_threads_injected_frontend_probe_to_m4", test_ensure_runtime_threads_injected_frontend_probe_to_m4),
    ("test_ensure_runtime_legacy_config_without_frontend_keys_does_not_crash", test_ensure_runtime_legacy_config_without_frontend_keys_does_not_crash),
    ("test_ensure_runtime_frontend_probe_default_binds_when_config_carries_keys", test_ensure_runtime_frontend_probe_default_binds_when_config_carries_keys),
    ("test_classify_compile_state_boot_alive_extended_truth_table", test_classify_compile_state_boot_alive_extended_truth_table),
    ("test_classify_compile_state_boot_alive_back_compat_default", test_classify_compile_state_boot_alive_back_compat_default),
    ("test_ensure_runtime_threads_injected_boot_alive_to_m4", test_ensure_runtime_threads_injected_boot_alive_to_m4),
    ("test_ensure_runtime_legacy_config_without_boot_key_does_not_crash", test_ensure_runtime_legacy_config_without_boot_key_does_not_crash),
    ("test_ensure_runtime_boot_alive_default_off_when_config_lacks_key", test_ensure_runtime_boot_alive_default_off_when_config_lacks_key),
    ("test_ensure_runtime_legacy_pre_vite_live_boot_patiently_waits_never_restarts", test_ensure_runtime_legacy_pre_vite_live_boot_patiently_waits_never_restarts),
    ("test_ensure_runtime_legacy_pre_vite_boot_dies_falls_through_to_recovery", test_ensure_runtime_legacy_pre_vite_boot_dies_falls_through_to_recovery),
    ("test_ensure_runtime_legacy_pre_vite_boot_never_serves_blocks_distinct_text", test_ensure_runtime_legacy_pre_vite_boot_never_serves_blocks_distinct_text),
    ("test_ensure_runtime_m4_pre_vite_live_boot_patiently_waits_never_restarts", test_ensure_runtime_m4_pre_vite_live_boot_patiently_waits_never_restarts),
    ("test_ensure_runtime_m4_genuine_dead_no_boot_unchanged_recovery", test_ensure_runtime_m4_genuine_dead_no_boot_unchanged_recovery),
    ("test_ensure_runtime_production_boot_alive_live_handle_patient_waits", test_ensure_runtime_production_boot_alive_live_handle_patient_waits),
    ("test_ensure_runtime_production_boot_alive_dead_handle_recovers", test_ensure_runtime_production_boot_alive_dead_handle_recovers),
    ("test_boot_spawn_stamp_roundtrip_and_grace_window", test_boot_spawn_stamp_roundtrip_and_grace_window),
    ("test_default_stale_check_native_commit_after_boot_stamp_is_stale", test_default_stale_check_native_commit_after_boot_stamp_is_stale),
    ("test_default_stale_check_native_commit_before_boot_stamp_is_fresh", test_default_stale_check_native_commit_before_boot_stamp_is_fresh),
    ("test_default_stale_check_no_boot_stamp_falls_back_to_lock_start_time", test_default_stale_check_no_boot_stamp_falls_back_to_lock_start_time),
    ("test_default_stale_check_no_signal_at_all_returns_false", test_default_stale_check_no_signal_at_all_returns_false),
    ("test_default_stale_check_respects_configured_native_globs", test_default_stale_check_respects_configured_native_globs),
    ("test_default_stale_check_bogus_repo_root_never_raises", test_default_stale_check_bogus_repo_root_never_raises),
    ("test_ensure_runtime_derived_stale_check_routes_to_stale_rebuild", test_ensure_runtime_derived_stale_check_routes_to_stale_rebuild),
    ("test_ensure_runtime_derived_stale_check_fresh_boot_no_restart", test_ensure_runtime_derived_stale_check_fresh_boot_no_restart),
    ("test_ensure_runtime_production_wrapper_exits_early_patient_waits_one_spawn", test_ensure_runtime_production_wrapper_exits_early_patient_waits_one_spawn),
    ("test_ensure_runtime_m4_wrapper_exits_early_patient_waits_one_spawn", test_ensure_runtime_m4_wrapper_exits_early_patient_waits_one_spawn),
    ("test_ensure_runtime_no_boot_ever_spawned_still_blocks_generic", test_ensure_runtime_no_boot_ever_spawned_still_blocks_generic),
    ("test_ensure_runtime_production_restart_spawns_via_shell_on_windows_cold_boot", test_ensure_runtime_production_restart_spawns_via_shell_on_windows_cold_boot),
    ("test_cold_compile_timeout_blocker_distinct_from_blocked_blocker", test_cold_compile_timeout_blocker_distinct_from_blocked_blocker),
    ("test_ensure_runtime_m4_compiling_patiently_waits_never_restarts_then_ready", test_ensure_runtime_m4_compiling_patiently_waits_never_restarts_then_ready),
    ("test_ensure_runtime_m4_compiling_crosses_to_dead_falls_through_to_recovery", test_ensure_runtime_m4_compiling_crosses_to_dead_falls_through_to_recovery),
    ("test_ensure_runtime_m4_compiling_never_serves_blocks_with_distinct_text", test_ensure_runtime_m4_compiling_never_serves_blocks_with_distinct_text),
    ("test_ensure_runtime_m4_compiling_waits_for_sidecar_too", test_ensure_runtime_m4_compiling_waits_for_sidecar_too),
    ("test_ensure_runtime_m4_genuine_dead_unchanged_bounded_recovery", test_ensure_runtime_m4_genuine_dead_unchanged_bounded_recovery),
    ("test_ensure_runtime_m4_default_off_byte_identical_dead_recovery", test_ensure_runtime_m4_default_off_byte_identical_dead_recovery),
    ("test_ensure_runtime_handler_no_marker_falls_back_to_legacy_superset", test_ensure_runtime_handler_no_marker_falls_back_to_legacy_superset),
    ("test_ensure_runtime_production_tests_derive_not_inject_signal", test_ensure_runtime_production_tests_derive_not_inject_signal),
    ("test_production_binding_guard_detects_signal_injection", test_production_binding_guard_detects_signal_injection),
    ("test_spawn_binding_production_tests_use_faithful_double", test_spawn_binding_production_tests_use_faithful_double),
    ("test_spawn_double_guard_detects_always_succeeds_double", test_spawn_double_guard_detects_always_succeeds_double),
    ("test_load_bug_queue_for_merged_breadcrumb_on_load_failure", test_load_bug_queue_for_merged_breadcrumb_on_load_failure),
    ("test_runtime_ownership_symbols_present", test_runtime_ownership_symbols_present),
    ("test_spawn_detached_windows_carries_breakaway_flags", test_spawn_detached_windows_carries_breakaway_flags),
    ("test_spawn_detached_windows_breakaway_denied_falls_back", test_spawn_detached_windows_breakaway_denied_falls_back),
    ("test_spawn_detached_posix_sets_new_session", test_spawn_detached_posix_sets_new_session),
    ("test_spawn_detached_posix_wraps_systemd_run_when_available", test_spawn_detached_posix_wraps_systemd_run_when_available),
    ("test_spawn_detached_posix_setsid_fallback_when_no_systemd", test_spawn_detached_posix_setsid_fallback_when_no_systemd),
    ("test_spawn_detached_never_sets_pdeathsig", test_spawn_detached_never_sets_pdeathsig),
    ("test_spawn_detached_returns_none_start_time_when_no_fn", test_spawn_detached_returns_none_start_time_when_no_fn),
    ("test_kernel_start_time_posix_parses_proc_stat", test_kernel_start_time_posix_parses_proc_stat),
    ("test_kernel_start_time_windows_converts_filetime", test_kernel_start_time_windows_converts_filetime),
    ("test_kernel_start_time_error_returns_none", test_kernel_start_time_error_returns_none),
    ("test_runtime_lock_round_trip_all_five_fields", test_runtime_lock_round_trip_all_five_fields),
    ("test_runtime_lock_written_at_repo_root_with_config_filename", test_runtime_lock_written_at_repo_root_with_config_filename),
    ("test_runtime_lock_atomic_write_no_partial_on_failure", test_runtime_lock_atomic_write_no_partial_on_failure),
    ("test_runtime_lock_read_missing_returns_none", test_runtime_lock_read_missing_returns_none),
    ("test_runtime_lock_read_corrupt_returns_none", test_runtime_lock_read_corrupt_returns_none),
    ("test_verify_ownership_match_returns_true", test_verify_ownership_match_returns_true),
    ("test_verify_ownership_divergent_start_time_false", test_verify_ownership_divergent_start_time_false),
    ("test_verify_ownership_foreign_controller_false", test_verify_ownership_foreign_controller_false),
    ("test_verify_ownership_missing_pid_false", test_verify_ownership_missing_pid_false),
    ("test_runtime_ownership_round_trip_compose", test_runtime_ownership_round_trip_compose),
    ("test_run_transient_build_symbol_present", test_run_transient_build_symbol_present),
    ("test_run_transient_build_spawns_through_detached_path", test_run_transient_build_spawns_through_detached_path),
    ("test_run_transient_build_windows_detached_flags", test_run_transient_build_windows_detached_flags),
    ("test_run_transient_build_awaits_and_returns_exit_code_and_stdout", test_run_transient_build_awaits_and_returns_exit_code_and_stdout),
    ("test_run_transient_build_propagates_nonzero_exit", test_run_transient_build_propagates_nonzero_exit),
    ("test_run_transient_build_does_not_write_runtime_lock", test_run_transient_build_does_not_write_runtime_lock),
    ("test_promote_artifact_atomically_symbol_present", test_promote_artifact_atomically_symbol_present),
    ("test_promote_artifact_atomically_exit0_promotes_via_replace", test_promote_artifact_atomically_exit0_promotes_via_replace),
    ("test_promote_artifact_atomically_nonzero_exit_leaves_production_untouched", test_promote_artifact_atomically_nonzero_exit_leaves_production_untouched),
    ("test_promote_artifact_atomically_real_tempdir_exit0_moves_artifact", test_promote_artifact_atomically_real_tempdir_exit0_moves_artifact),
    ("test_promote_artifact_atomically_real_tempdir_nonzero_leaves_final", test_promote_artifact_atomically_real_tempdir_nonzero_leaves_final),
    ("test_reconcile_cycle_begin_symbol_present", test_reconcile_cycle_begin_symbol_present),
    ("test_reconcile_stale_lock_removed_and_staging_cleaned", test_reconcile_stale_lock_removed_and_staging_cleaned),
    ("test_reconcile_fresh_lock_preserved", test_reconcile_fresh_lock_preserved),
    ("test_reconcile_no_lock_is_noop", test_reconcile_no_lock_is_noop),
    ("test_reconcile_non_git_tree_is_noop_fail_open", test_reconcile_non_git_tree_is_noop_fail_open),
    ("test_git_safe_push_retry_then_succeed", test_git_safe_push_retry_then_succeed),
    ("test_git_safe_push_never_composes_force", test_git_safe_push_never_composes_force),
    ("test_git_safe_push_bounded_retry_returns_structured_conflict", test_git_safe_push_bounded_retry_returns_structured_conflict),
]





def main() -> int:
    print("=" * 60)
    print("test_lazy_core.py — characterization tests")
    print("=" * 60)

    if _IMPORT_ERROR is not None:
        print(f"\nREQUIRED MODULE MISSING: {_IMPORT_ERROR}")
        print("This is the expected RED state — lazy_core has not been extracted yet.\n")

    print()
    for name, fn in _TESTS:
        _run_test(name, fn)

    total = len(_TESTS)
    passed = len(_PASSES)
    failed = len(_FAILURES)

    print()
    print("=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        print()
        if _IMPORT_ERROR is not None:
            print("FIX: extract lazy_core.py from lazy-state.py and re-run.")
        return 1
    print("\nAll tests passed.")
    return 0



if __name__ == "__main__":
    sys.exit(main())
