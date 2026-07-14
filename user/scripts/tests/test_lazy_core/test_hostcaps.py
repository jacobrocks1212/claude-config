#!/usr/bin/env python3
"""
test_hostcaps.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_hostcaps.py
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



from _util import _ModuleMissing, _load_state_script  # noqa: E402




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





# ---------------------------------------------------------------------------
# host-capability-declaration-for-gated-features
#   WU-1 (Phase 1): _HOST_CAPABILITY_REGISTRY + parse_requires_host +
#                   unknown_capability_ids
#   WU-2 (Phase 2): probe_binary_capability / probe_env_capability
#   WU-3 (Phase 3): host_present_capabilities resolver + per-run cache
# ---------------------------------------------------------------------------

def test_host_capability_registry_keys_shape_valid():
    """Every _HOST_CAPABILITY_REGISTRY key matches ^[a-z0-9][a-z0-9-]*$ and the
    seed v1 vocabulary is present."""
    _guard()
    reg = lazy_core._HOST_CAPABILITY_REGISTRY
    assert isinstance(reg, dict) and reg, "registry must be a non-empty dict"
    shape = re.compile(r"^[a-z0-9][a-z0-9-]*$")
    for key in reg:
        assert shape.match(key), f"registry id {key!r} is not shape-valid"
    for seed in ("real-audio-device", "zimtohrli-toolchain", "gpu"):
        assert seed in reg, f"seed capability {seed!r} missing from registry"




def test_host_capability_midi_controller_registered_and_env_probed():
    """midi-controller is a registered host capability probed via the
    ALGOBOOTH_REAL_MIDI_DEVICE env var (Round 40). The audio-axis device re-open
    ($ALGOBOOTH_REAL_AUDIO_DEVICE) cannot express a MIDI-hardware-only deferral,
    so a host with real audio but no motorized fader looped on the device re-open;
    this capability lets such a feature defer cleanly via requires_host."""
    _guard()
    # Registered in the closed vocabulary + shape-valid.
    assert "midi-controller" in lazy_core._HOST_CAPABILITY_REGISTRY
    assert lazy_core._HOST_CAPABILITY_ID_RE.match("midi-controller")
    # Bound to an env probe on ALGOBOOTH_REAL_MIDI_DEVICE (mirrors real-audio-device).
    cfg = lazy_core._HOST_CAPABILITY_PROBE_CONFIG.get("midi-controller")
    assert cfg == {"kind": "env", "var": "ALGOBOOTH_REAL_MIDI_DEVICE"}
    # Present iff the bound probe returns truthy (injected, hermetic).
    present = lazy_core.host_present_capabilities(
        probes={"midi-controller": (lambda: True)}, cache=False
    )
    assert "midi-controller" in present
    absent = lazy_core.host_present_capabilities(
        probes={"midi-controller": (lambda: False)}, cache=False
    )
    assert "midi-controller" not in absent
    # A feature declaring `requires_host: midi-controller` parses cleanly and is
    # NOT an unknown-capability typo (fail-fast must accept it).
    spec = "---\nrequires_host: midi-controller\n---\n# x\n"
    assert lazy_core.parse_requires_host(spec, None) == {"midi-controller"}
    assert lazy_core.unknown_capability_ids({"midi-controller"}) == set()




def test_host_capability_link_peer_and_non_windows_registered_and_probed():
    """link-multi-peer + non-windows-host are registered host capabilities
    (device-vs-host mis-classification, Round 41, 2026-06-29).

    d5-ableton-link's multi-peer scenarios (peerCount:0, need a 2nd LAN peer) and
    non-windows-audio-hardening's cfg(unix) code (need a Linux/macOS host) were
    being mis-routed to DEFERRED_REQUIRES_DEVICE, which re-opens and loops on a
    real-audio-device host. They are HOST-capability gaps, not device gaps. This
    pins: (a) both ids are in the closed registry; (b) parse_requires_host accepts
    them (no unknown-capability fail-fast); (c) the non-windows-host platform probe
    resolves present on a non-Windows system_fn and absent on a Windows one (the OS
    is deterministically detectable); (d) link-multi-peer resolves absent — it has
    NO probe config (a solo host can't self-detect a 2nd peer) so it binds the
    constant-False placeholder (fail-safe absent until a peer probe is configured).
    """
    _guard()
    # (a) Both registered in the closed vocabulary + shape-valid.
    assert "link-multi-peer" in lazy_core._HOST_CAPABILITY_REGISTRY
    assert "non-windows-host" in lazy_core._HOST_CAPABILITY_REGISTRY
    assert lazy_core._HOST_CAPABILITY_ID_RE.match("link-multi-peer")
    assert lazy_core._HOST_CAPABILITY_ID_RE.match("non-windows-host")

    # (b) parse_requires_host accepts both; neither is an unknown-capability typo.
    spec = "---\nrequires_host: [link-multi-peer, non-windows-host]\n---\n# x\n"
    assert lazy_core.parse_requires_host(spec, None) == {
        "link-multi-peer",
        "non-windows-host",
    }
    assert lazy_core.unknown_capability_ids(
        {"link-multi-peer", "non-windows-host"}
    ) == set()

    # (c) The non-windows-host probe is a real platform probe: present on a
    # non-Windows OS, absent on Windows (inject system_fn — hermetic).
    cfg = lazy_core._HOST_CAPABILITY_PROBE_CONFIG.get("non-windows-host")
    assert cfg == {"kind": "platform", "predicate": "non-windows"}
    assert lazy_core.probe_platform_capability(
        "non-windows", system_fn=lambda: "Linux"
    ) is True
    assert lazy_core.probe_platform_capability(
        "non-windows", system_fn=lambda: "Darwin"
    ) is True
    assert lazy_core.probe_platform_capability(
        "non-windows", system_fn=lambda: "Windows"
    ) is False

    # (d) link-multi-peer has NO probe config → constant-False placeholder bound by
    # _default_host_probes → never present until a peer probe is configured.
    assert "link-multi-peer" not in lazy_core._HOST_CAPABILITY_PROBE_CONFIG
    default_probes = lazy_core._default_host_probes()
    assert default_probes["link-multi-peer"]() is False
    # And the non-windows-host default probe reflects the REAL host OS (Windows here
    # → absent; non-Windows CI → present) — assert it tracks platform.system().
    expected_non_windows = platform.system().strip().lower() != "windows"
    assert default_probes["non-windows-host"]() is expected_non_windows




def test_parse_requires_host_from_spec_frontmatter_only():
    """A list value in the SPEC frontmatter parses to the capability set."""
    _guard()
    spec = (
        "---\n"
        "title: x\n"
        "requires_host: [zimtohrli-toolchain, gpu]\n"
        "---\n"
        "# Heading\n"
    )
    assert lazy_core.parse_requires_host(spec, None) == {
        "zimtohrli-toolchain",
        "gpu",
    }




def test_parse_requires_host_from_queue_entry_only():
    """A queue entry list value parses; spec has no field."""
    _guard()
    spec = "# No frontmatter here\n"
    entry = {"feature_id": "x", "requires_host": ["real-audio-device"]}
    assert lazy_core.parse_requires_host(spec, entry) == {"real-audio-device"}




def test_parse_requires_host_union_of_both_sources():
    """SPEC + queue entry union into one set."""
    _guard()
    spec = "---\nrequires_host: [gpu]\n---\n"
    entry = {"requires_host": ["zimtohrli-toolchain"]}
    assert lazy_core.parse_requires_host(spec, entry) == {
        "gpu",
        "zimtohrli-toolchain",
    }




def test_parse_requires_host_absent_is_empty_set():
    """No requires_host anywhere ⇒ empty set (ungated baseline-regression lock)."""
    _guard()
    spec = "---\ntitle: x\n---\n# Body\n"
    assert lazy_core.parse_requires_host(spec, None) == set()
    assert lazy_core.parse_requires_host(spec, {"feature_id": "x"}) == set()
    assert lazy_core.parse_requires_host("", None) == set()




def test_parse_requires_host_comma_and_space_string_tolerant():
    """A comma/space-separated string value parses to the same set as a list."""
    _guard()
    spec_comma = "---\nrequires_host: gpu, zimtohrli-toolchain\n---\n"
    spec_space = "---\nrequires_host: gpu zimtohrli-toolchain\n---\n"
    expected = {"gpu", "zimtohrli-toolchain"}
    assert lazy_core.parse_requires_host(spec_comma, None) == expected
    assert lazy_core.parse_requires_host(spec_space, None) == expected
    # queue entry string form too
    assert lazy_core.parse_requires_host(
        "", {"requires_host": "gpu, zimtohrli-toolchain"}
    ) == expected




def test_parse_requires_host_rejects_malformed_id():
    """A malformed id (uppercase / leading dash) is dropped — the parse never
    emits a shape-invalid id (the chosen tolerant-drop contract)."""
    _guard()
    spec = "---\nrequires_host: [GPU, -bad, real-audio-device]\n---\n"
    result = lazy_core.parse_requires_host(spec, None)
    assert result == {"real-audio-device"}, (
        f"malformed ids must be dropped, got {result!r}"
    )




def test_unknown_capability_ids_returns_typo():
    """unknown_capability_ids returns ids not in the registry; registered ⇒ empty."""
    _guard()
    assert lazy_core.unknown_capability_ids({"typo-cap"}) == {"typo-cap"}
    assert lazy_core.unknown_capability_ids({"gpu"}) == set()
    assert lazy_core.unknown_capability_ids(
        {"gpu", "typo-cap"}
    ) == {"typo-cap"}
    assert lazy_core.unknown_capability_ids(set()) == set()




# --- WU-3: host_present_capabilities resolver + per-run cache ---------------

def test_host_present_capabilities_injected_probes():
    """Resolver returns exactly the True-valued ids from an injected probe map."""
    _guard()
    probes = {
        "gpu": lambda: True,
        "zimtohrli-toolchain": lambda: False,
        "real-audio-device": lambda: True,
    }
    with tempfile.TemporaryDirectory() as td:
        os.environ["LAZY_STATE_DIR"] = td
        try:
            present = lazy_core.host_present_capabilities(probes=probes, cache=False)
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)
    assert present == {"gpu", "real-audio-device"}




def test_host_present_capabilities_no_marker_probes_fresh():
    """No run marker ⇒ probes fresh every call (no cache)."""
    _guard()
    counter = {"n": 0}

    def gpu_probe():
        counter["n"] += 1
        return True

    probes = {"gpu": gpu_probe}
    with tempfile.TemporaryDirectory() as td:
        os.environ["LAZY_STATE_DIR"] = td
        try:
            lazy_core.host_present_capabilities(probes=probes, cache=True)
            lazy_core.host_present_capabilities(probes=probes, cache=True)
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)
    assert counter["n"] == 2, "no marker ⇒ no cache ⇒ probe each call"




def test_host_present_capabilities_default_bindings_present():
    """Default (probes=None) binds the production registry — every registry id
    has a callable bound (no KeyError / missing binding)."""
    _guard()
    # Inject a fully-stubbed map mirroring the registry keys to confirm the
    # resolver iterates the registry, not a hard-coded id list.
    stub = {k: (lambda: False) for k in lazy_core._HOST_CAPABILITY_REGISTRY}
    with tempfile.TemporaryDirectory() as td:
        os.environ["LAZY_STATE_DIR"] = td
        try:
            present = lazy_core.host_present_capabilities(probes=stub, cache=False)
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)
    assert present == set(), "all-false stub ⇒ empty present set"




# --- Phases 4 + 5: blocker formatter + DEFERRED_REQUIRES_HOST.md writer ------

def test_format_unknown_host_capability_blocker_names_typo_and_registry():
    """The Phase-4 blocker body names BOTH the offending typo id AND the sorted
    registry ids (so the operator can fix the typo or register a probe)."""
    _guard()
    body = lazy_core.format_unknown_host_capability_blocker(
        "feat-x", {"typo-cap"}
    )
    assert "typo-cap" in body, "body must name the offending unregistered id"
    for reg_id in lazy_core._HOST_CAPABILITY_REGISTRY:
        assert reg_id in body, f"body must name registry id {reg_id!r}"
    # It is human-readable: keeps the Details + Recovery sections.
    assert "## Details" in body
    assert "## Recovery Suggestion" in body




def test_utc_now_iso_format_z_suffix():
    """utc_now_iso returns an ISO-8601 UTC timestamp with a trailing Z; the
    injected epoch is deterministic."""
    _guard()
    # 2021-01-01T00:00:00Z is epoch 1609459200.
    assert lazy_core.utc_now_iso(1609459200) == "2021-01-01T00:00:00Z"
    live = lazy_core.utc_now_iso()
    assert live.endswith("Z") and "T" in live




def test_p7_sanctioned_stop_terminal_constant_exists():
    """lazy_core must expose a SANCTIONED_STOP_TERMINAL set/frozenset containing
    the canonical stop reasons so both state scripts can import it.

    RED until SANCTIONED_STOP_TERMINAL is defined in lazy_core.py.
    """
    _guard()
    assert hasattr(lazy_core, "SANCTIONED_STOP_TERMINAL"), (
        "lazy_core must export SANCTIONED_STOP_TERMINAL"
    )
    sst = lazy_core.SANCTIONED_STOP_TERMINAL
    assert isinstance(sst, (set, frozenset)), (
        f"SANCTIONED_STOP_TERMINAL must be a set/frozenset; got {type(sst)!r}"
    )
    # Check all sanctioned reasons are present (incl. the host-capability-axis
    # terminal added by host-capability-declaration-for-gated-features Phase 6).
    required = {
        "all-features-complete",
        "all-bugs-fixed",
        "max-cycles",
        "cloud-queue-exhausted",
        "device-queue-exhausted",
        "host-capability-saturated",
        "queue-missing",
        "blocked-halt-for-manual",
        "needs-research",
        "queue-blocked-on-research",
    }
    missing = required - sst
    assert not missing, (
        f"SANCTIONED_STOP_TERMINAL missing expected reasons: {missing}"
    )




def test_pin_bug_severity_creates_new_entry():
    """bug-queue-aging-backpressure D2-A: bug-state.py --pin creates a queue
    entry (appended) for a not-yet-queued on-disk bug, stamping
    pinned_at/pinned_until/pin_reason and nulling severity."""
    _guard()
    import datetime
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bug_dir = root / "docs" / "bugs" / "my-bug"
        bug_dir.mkdir(parents=True)
        (bug_dir / "SPEC.md").write_text(
            "# My Bug\n\n**Status:** Concluded\n**Severity:** P2\n"
            "**Discovered:** 2026-06-22\n", encoding="utf-8",
        )
        result = bs.pin_bug_severity(
            root, "my-bug", until="2026-08-01", reason="host-capability: windows",
            today=datetime.date(2026, 7, 13),
        )
        assert result["status"] == "pinned"
        assert result["pinned_at"] == "2026-07-13"
        queue = json.loads((root / "docs" / "bugs" / "queue.json").read_text())
        entry = queue["queue"][0]
        assert entry["id"] == "my-bug"
        assert entry["severity"] is None
        assert entry["pinned_until"] == "2026-08-01"
        assert entry["pin_reason"] == "host-capability: windows"


_TESTS = [
    ("test_host_capability_registry_keys_shape_valid", test_host_capability_registry_keys_shape_valid),
    ("test_host_capability_midi_controller_registered_and_env_probed", test_host_capability_midi_controller_registered_and_env_probed),
    ("test_host_capability_link_peer_and_non_windows_registered_and_probed", test_host_capability_link_peer_and_non_windows_registered_and_probed),
    ("test_parse_requires_host_from_spec_frontmatter_only", test_parse_requires_host_from_spec_frontmatter_only),
    ("test_parse_requires_host_from_queue_entry_only", test_parse_requires_host_from_queue_entry_only),
    ("test_parse_requires_host_union_of_both_sources", test_parse_requires_host_union_of_both_sources),
    ("test_parse_requires_host_absent_is_empty_set", test_parse_requires_host_absent_is_empty_set),
    ("test_parse_requires_host_comma_and_space_string_tolerant", test_parse_requires_host_comma_and_space_string_tolerant),
    ("test_parse_requires_host_rejects_malformed_id", test_parse_requires_host_rejects_malformed_id),
    ("test_unknown_capability_ids_returns_typo", test_unknown_capability_ids_returns_typo),
    ("test_host_present_capabilities_injected_probes", test_host_present_capabilities_injected_probes),
    ("test_host_present_capabilities_no_marker_probes_fresh", test_host_present_capabilities_no_marker_probes_fresh),
    ("test_host_present_capabilities_default_bindings_present", test_host_present_capabilities_default_bindings_present),
    ("test_format_unknown_host_capability_blocker_names_typo_and_registry", test_format_unknown_host_capability_blocker_names_typo_and_registry),
    ("test_utc_now_iso_format_z_suffix", test_utc_now_iso_format_z_suffix),
    ("test_p7_sanctioned_stop_terminal_constant_exists", test_p7_sanctioned_stop_terminal_constant_exists),
    ("test_pin_bug_severity_creates_new_entry", test_pin_bug_severity_creates_new_entry),
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
