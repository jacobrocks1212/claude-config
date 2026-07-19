#!/usr/bin/env python3
"""
test_dispatch.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_dispatch.py
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


from _util import _ModuleMissing, _REAL_TEMPLATE_DIR, _STATE_A, _assert_run_end_refusal_emits, _build_bug_retro_routing_repo, _clear_state_dir, _commit_dummy, _dispatch_requires, _drive_run_end, _f1_guard_module, _f1_hook_input, _load_state_script, _make_git_repo_with_origin, _os_env, _record_consume, _set_state_dir, _write_marker_in  # noqa: E402


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
# Tests: load_context_json — ISSUE 3 robust --context channel (d8-effect-chains)
# ---------------------------------------------------------------------------

def test_load_context_json_valid_long_value():
    """A long failure_summary with commas/colons/parens/newlines round-trips."""
    _guard()
    long_summary = (
        "Execute-plan deviated: part-2 (phases:[5], complexity:mechanical) was "
        "dispatched, but its entry criteria (Part 1 complete) were unmet; the "
        "subagent silently executed part-1 (Phase 6, complex audio/IPC), committed "
        "WU-1/WU-2, then died waiting on a backgrounded build (returned resultless). "
        "Faults: (i) silent part-switch; (ii) complex work under sonnet.\n"
        "Next: route part-1 first, surface BLOCKED on unmet entry criterion."
    ) * 3  # ~1500+ chars
    payload = json.dumps({"failure_summary": long_summary, "item_id": "d8-effect-chains"})
    result = lazy_core.load_context_json(payload)
    assert result["failure_summary"] == long_summary, "long value must round-trip intact"
    assert result["item_id"] == "d8-effect-chains"


def test_load_context_json_rejects_non_object():
    """A JSON array/string top level → ValueError (caught as structured error)."""
    _guard()
    import pytest as _pytest
    with _pytest.raises(ValueError):
        lazy_core.load_context_json('["not", "an", "object"]')
    with _pytest.raises(ValueError):
        lazy_core.load_context_json('"a bare string"')


def test_load_context_json_rejects_malformed():
    """Invalid JSON → ValueError, never a silent empty dict."""
    _guard()
    import pytest as _pytest
    with _pytest.raises(ValueError):
        lazy_core.load_context_json('{not valid json,,,}')


def test_load_context_json_coerces_values_to_str():
    """Non-string values are stringified; None → empty string."""
    _guard()
    result = lazy_core.load_context_json('{"n": 42, "b": true, "empty": null}')
    assert result == {"n": "42", "b": "True", "empty": ""}, (
        f"values must coerce to str (None→''), got {result}"
    )


# Same feature_id + current_step as _STATE_A but a DIFFERENT sub_skill_args.
# The step signature is (feature_id, current_step) ONLY, so this state has the
# SAME step signature as _STATE_A even though the dispatch tuple differs — used
# to prove the step counter ignores sub_skill / sub_skill_args.
_STATE_A_SAME_STEP_DIFF_ARGS = {
    "feature_id": "feat-a",
    "sub_skill": "/write-plan",            # differs from _STATE_A
    "sub_skill_args": "plan-part-9.md",    # differs from _STATE_A
    "current_step": "Step 7a: execute plan",  # SAME current_step as _STATE_A
}


def test_update_repeat_counts_step_counter_ordered_args_advance_resets():
    """ORDERED-ADVANCE EXEMPTION (audio-rate-modulation false-positive fix):
    a probe with the same (feature_id, current_step) but an ADVANCED
    sub_skill_args is genuine ordered forward progress (e.g. a multi-part
    /execute-plan marching plan-part-1 → plan-part-9 while staying on the same
    "Step 7a: execute plan") → step_repeat_count RESETS to 1, it does NOT count
    toward the oscillation tripwire. The dispatch-tuple repeat_count also resets
    to 1 (its full tuple changed).

    This is the inverse of the original Phase-10 args-blind behavior: the step
    counter used to INCREMENT here. The discriminator is whether sub_skill_args
    moved — see test_update_repeat_counts_step_same_args_still_increments for the
    d8 same-target case that MUST still climb.
    RED: the pre-fix args-blind step counter returned 2 here.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Non-git root → repeat_count head path is None==None (increment), so the
        # only thing resetting repeat_count below is the signature change.
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_counts(Path(td), _STATE_A, signature_path=sig_path)
        # Same (feature_id, current_step) but ADVANCED sub_skill_args (and skill).
        r2 = lazy_core.update_repeat_counts(
            Path(td), _STATE_A_SAME_STEP_DIFF_ARGS, signature_path=sig_path
        )
    assert r1["step_repeat_count"] == 1, f"first step count should be 1, got {r1!r}"
    assert r2["step_repeat_count"] == 1, (
        f"step counter must RESET to 1 when sub_skill_args ADVANCED (ordered "
        f"forward progress), even though (feature_id, current_step) is unchanged, "
        f"got {r2!r}"
    )
    assert r2["repeat_count"] == 1, (
        f"dispatch-tuple repeat_count must RESET when sub_skill/args change, got {r2!r}"
    )


def test_update_repeat_counts_step_multipart_progress_does_not_trip():
    """MANDATORY case 1 — multi-part progress does NOT trip the tripwire.

    Simulate a healthy multi-part /execute-plan sequence: consecutive probes with
    the SAME (feature_id, "Step 7a: execute plan") but ADVANCING sub_skill_args
    (plan-part-1 → part-2 → part-3). Each is ordered forward progress, so
    step_repeat_count must stay at 1 every cycle and NEVER reach the >=3 loop
    warning the orchestrator acts on.

    This is the audio-rate-modulation false-positive: before the fix the
    args-blind step counter climbed 1 → 2 → 3 here and force a manual
    inspect-before-dispatch on parts 3/4/5 of a genuine forward sequence.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        # A real git repo so the dispatch-tuple HEAD path is realistic; commits
        # land between parts (each part commits its work) — the step counter must
        # stay flat regardless of commits AND of advancing args.
        repo_root, _origin = _make_git_repo_with_origin(td)
        parts = ["plan-part-1.md", "plan-part-2.md", "plan-part-3.md"]
        step_counts = []
        for i, part in enumerate(parts):
            state = {
                "feature_id": "audio-rate-modulation",
                "sub_skill": "/execute-plan",
                "sub_skill_args": part,
                "current_step": "Step 7a: execute plan",
            }
            r = lazy_core.update_repeat_counts(repo_root, state, signature_path=sig_path)
            step_counts.append(r["step_repeat_count"])
            # Each part commits its work → HEAD advances between cycles.
            _commit_dummy(repo_root, f"part-{i}.txt")
    assert step_counts == [1, 1, 1], (
        f"multi-part ordered progress must keep step_repeat_count at 1 each cycle "
        f"(args advance = forward progress), got {step_counts!r}"
    )
    assert max(step_counts) < 3, (
        f"step_repeat_count must NEVER reach the >=3 tripwire for genuine "
        f"multi-part progress, got {step_counts!r}"
    )


def test_update_repeat_counts_step_same_args_oscillation_still_trips():
    """MANDATORY case 2 — same-target oscillation STILL trips (d8 preserved).

    Simulate the 2026-06-11 d8 failure: consecutive probes with the SAME
    (feature_id, current_step) AND IDENTICAL sub_skill_args, with HEAD advancing
    each cycle (each spurious cycle commits a file, so the dispatch-tuple
    repeat_count keeps resetting to 1 and never catches the loop). The
    HEAD-blind, args-unchanged step_repeat_count must climb 1 → 2 → 3 → 4 and
    reach the >=3 tripwire.

    RED for the ordered-advance fix done wrong: if the exemption mis-fired on
    unchanged args, this would stay at 1.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        repo_root, _origin = _make_git_repo_with_origin(td)
        # SAME args every cycle — the same plan re-emitted (genuine stuck loop).
        state = {
            "feature_id": "d8-stuck",
            "sub_skill": "/write-plan",
            "sub_skill_args": "plan.md",          # UNCHANGED across all repeats
            "current_step": "Step 7a: execute plan",
        }
        step_counts = []
        repeat_counts = []
        for i in range(4):
            r = lazy_core.update_repeat_counts(repo_root, state, signature_path=sig_path)
            step_counts.append(r["step_repeat_count"])
            repeat_counts.append(r["repeat_count"])
            # Each oscillation cycle COMMITS (HEAD advances) — the property that
            # makes the dispatch-tuple counter useless and step_repeat_count vital.
            _commit_dummy(repo_root, f"osc-{i}.txt")
    assert step_counts == [1, 2, 3, 4], (
        f"same-target oscillation (unchanged args, HEAD advancing) must keep "
        f"climbing the step counter, got {step_counts!r}"
    )
    assert max(step_counts) >= 3, (
        f"the >=3 oscillation tripwire MUST still fire for the d8 same-target "
        f"loop, got {step_counts!r}"
    )
    # Confirm the d8 property that motivated step_repeat_count: the dispatch-tuple
    # repeat_count stays low (resets each commit) so it alone would miss the loop.
    assert max(repeat_counts) == 1, (
        f"dispatch-tuple repeat_count must reset to 1 each commit (the d8 blind "
        f"spot step_repeat_count exists to cover), got {repeat_counts!r}"
    )


def test_update_repeat_counts_legacy_file_without_step_keys():
    """A persisted file written by the Phase-9 shape (signature/count/head, NO
    step_signature/step_count) → step_repeat_count starts at 1, and the new keys
    are added on the next write (legacy fallback, mirroring the head migration).

    RED: an impl that KeyErrors or crashes on the missing step keys.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)  # non-git → head None
        sig_path = Path(td) / "sig.json"
        # Hand-write the Phase-9 shape: dispatch tuple matching _STATE_A, NO step keys.
        legacy_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        sig_path.write_text(
            json.dumps({"signature": legacy_sig, "count": 1, "head": None}),
            encoding="utf-8",
        )
        r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
    assert r1["step_repeat_count"] == 1, (
        f"legacy file without step keys → step_count starts at 1, got {r1!r}"
    )
    assert "step_signature" in persisted and "step_count" in persisted, (
        f"the new step keys must be added on the next write, got {persisted!r}"
    )
    assert r2["step_repeat_count"] == 2, (
        f"second identical-step probe increments now that keys exist, got {r2!r}"
    )
    # The Phase-9 dispatch-tuple count keeps incrementing (legacy file had it at 1).
    assert r1["repeat_count"] == 2, (
        f"dispatch repeat_count must still honor the legacy count (1 → 2), got {r1!r}"
    )


def test_update_repeat_count_wrapper_still_returns_int():
    """The backward-compatible wrapper update_repeat_count returns the bare
    dispatch-tuple int (NOT a dict) — existing callers/tests are unbroken.

    Also confirms the wrapper persists the step keys (a subsequent
    update_repeat_counts sees step_count already at 1, so its identical probe
    returns 2) — i.e. the wrapper and the plural share ONE state file.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        sig_path = Path(td) / "sig.json"
        r = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
        assert r == 1, f"wrapper must return a bare int (1), got {r!r}"
        # The wrapper wrote step keys too → a plural probe of the same step → 2.
        r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
    assert isinstance(r, int), f"wrapper must return int, got {type(r).__name__}"
    assert r2["step_repeat_count"] == 2, (
        f"wrapper must persist step keys so the plural sees them, got {r2!r}"
    )


# ---------------------------------------------------------------------------
# Tests: loop-detector-false-positives-probes-and-cross-run-state
# Residual gap A — meta-class consumption must not defeat the F1/F2 debounce.
# Residual gap B — run-lifetime scoping of the persisted streak.
# ---------------------------------------------------------------------------


def _record_meta_consume(state_dir: "Path", cls: str = "hardening") -> None:
    """Register + consume a META-class (non-"cycle") emission — a mid-step
    hardening/recovery/investigation/input-audit dispatch that consumes a
    registry nonce WITHOUT being a forward attempt at the step.

    Used by the Residual-gap-A fixtures to prove such a dispatch no longer
    defeats the F1/F2 double-probe debounce (which now filters the oracle to
    cls="cycle" consumptions only).
    """
    _set_state_dir(state_dir)
    try:
        entry = lazy_core.register_emission("meta dispatch prompt", cls)
        consumed = lazy_core.dispatch.consume_nonce(entry["nonce"])
        assert consumed, "pre-condition: the fresh nonce must consume cleanly"
    finally:
        _clear_state_dir()


def test_gap_a_meta_class_consume_does_not_defeat_step_debounce():
    """Residual gap A: a META-class consume (hardening) landing BETWEEN two
    identical same-step probes must NOT advance step_repeat_count — only a
    CYCLE-class consume proves "a forward dispatch landed between probes".

    RED (pre-fix): consumed_emission_count() counted ANY consumed class, so a
    mid-step hardening dispatch raised the count and the F2 hold's precondition
    (current_consume_count == prior_consume_count) failed, incrementing
    step_repeat_count on the next same-step probe even though no forward
    attempt occurred.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        # A META dispatch (hardening) consumes a nonce between the two probes —
        # NOT a forward attempt at the step.
        _record_meta_consume(state_dir, cls="hardening")
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 1, (
        f"a META-class consume between two identical same-step probes must NOT "
        f"advance step_repeat_count (it is not a forward attempt), got {r2!r}"
    )


def test_gap_a_meta_class_consume_does_not_defeat_dispatch_tuple_debounce():
    """Residual gap A mirror for repeat_count (F1, dispatch-tuple streak): the
    SAME oracle feeds both counters, so a META-class consume between two
    identical probes must not advance repeat_count either."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        _record_meta_consume(state_dir, cls="investigation")
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["repeat_count"] == 1, (
        f"a META-class consume between two identical probes must NOT advance "
        f"repeat_count, got {r2!r}"
    )


def test_gap_a_cycle_class_consume_still_trips_despite_intervening_meta():
    """Negative/regression fixture (d8 design constraint preserved): a genuine
    CYCLE-class dispatch between two identical same-step probes STILL trips the
    oscillation counter, even when a META-class consume ALSO occurred in the
    same window — the oracle counts cycle-class consumptions specifically, it
    does not merely ignore all consumptions."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        # Both a meta dispatch AND a genuine cycle dispatch land between probes.
        _record_meta_consume(state_dir, cls="hardening")
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"a genuine cycle-class dispatch between probes must still trip the "
        f"oscillation counter (1 → 2), regardless of an intervening meta "
        f"consume, got {r2!r}"
    )


def test_f1_repeat_count_head_reset_wins_over_debounce():
    """F1 invariant 3 — HEAD reset overrides the debounce.

    When a NEW HEAD is recorded since the last probe (a commit landed), the
    dispatch-tuple streak resets to 1 regardless of the consume-count oracle
    — a commit is always forward progress and must never be suppressed.

    This verifies the debounce ONLY applies inside the same-head branch.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)
        # Hand-write a prior state that has NO consume_count → prior_consume_count
        # is the sentinel.  Then even if the current probe records a consume count,
        # the oracle says "can't prove re-read" → would normally increment.  But we
        # want to check the HEAD-reset path specifically, so use a real HEAD mismatch.
        # Write a prior state with a fake head so the current (None) differs.
        prior_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        prior_step_sig = [_STATE_A["feature_id"], _STATE_A["current_step"]]
        sig_path.write_text(
            json.dumps({
                "signature": prior_sig, "count": 3, "head": "deadbeef1234",
                "step_signature": prior_step_sig, "step_count": 3,
                "consume_count": 0,
            }),
            encoding="utf-8",
        )
        _set_state_dir(state_dir)
        try:
            # Probe against repo_root which is NOT a git repo → current_head=None.
            # prior_head="deadbeef1234" ≠ None → HEAD reset branch fires.
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1, (
        f"a new HEAD since the last probe must reset repeat_count to 1 regardless "
        f"of the consume-count oracle, got {r1!r}"
    )


# ---------------------------------------------------------------------------
# Tests: format_cycle_header — WU-5 single-probe payload (cycle header)
# ---------------------------------------------------------------------------

def test_format_cycle_header_full():
    """All counters provided, state has feature_id and sub_skill → exact pinned
    string in the SANCTIONED T2 forward shape `### {Step} — {summary} [{fwd}/{max}]`.

    The retired WU-5 format (`### Cycle fwd N/M · meta K · feat · sub_skill`) must
    NOT reappear (docs/bugs/format-cycle-header-emits-retired-cycle-fwd-format):
    Step is derived from sub_skill (`/execute-plan` → `Implement`), summary is the
    feature_id, counter is the forward `[fwd/max]`. meta_cycles is accepted for
    signature back-compat but no longer rendered into the forward header.
    """
    _guard()
    state = {"feature_id": "audio-engine", "sub_skill": "/execute-plan", "other": "ignored"}
    result = lazy_core.format_cycle_header(
        state, forward_cycles=2, max_cycles=8, meta_cycles=3
    )
    expected = "### Implement — audio-engine [2/8]"
    assert result == expected, (
        f"format_cycle_header returned wrong string.\n"
        f"  expected: {expected!r}\n"
        f"  got:      {result!r}"
    )


def test_format_cycle_header_missing_fields():
    """state={} and all counters None → Step falls back to 'Cycle', summary to the
    em-dash sentinel, counters to '?'.

    Placeholder contract: absent sub_skill → Step `Cycle`; missing feature_id →
    summary `—`; fwd counters None → `?`.  Never the retired `· … ·` suffix.
    """
    _guard()
    state = {}
    result = lazy_core.format_cycle_header(
        state, forward_cycles=None, max_cycles=None, meta_cycles=None
    )
    expected = "### Cycle — — [?/?]"
    assert result == expected, (
        f"format_cycle_header returned wrong string for all-None/empty state.\n"
        f"  expected: {expected!r}\n"
        f"  got:      {result!r}"
    )


# Residue regex — the same pattern the emitter's residue guard uses.
_TOKEN_RESIDUE_RE = re.compile(r"\{[a-z_]+\}")


def _emit_state(**overrides):
    """Build a representative compute_state-shaped dict for emit tests.

    Defaults to a feature-pipeline execute-plan cycle; override any key.
    """
    base = {
        "feature_id": "feat-x",
        "feature_name": "Feature X",
        "spec_path": "/nonexistent/spec/dir",
        "current_step": "Step 7a: execute plan",
        "sub_skill": "/execute-plan",
        "sub_skill_args": "plan-part-1.md",
    }
    base.update(overrides)
    return base


def test_emit_cycle_prompt_symbol_present():
    """emit_cycle_prompt must be importable from lazy_core.

    RED: emit_cycle_prompt missing → AttributeError.
    """
    _guard()
    assert hasattr(lazy_core, "emit_cycle_prompt"), "lazy_core.emit_cycle_prompt missing"


def test_emit_cycle_prompt_binding_matrix_real_template():
    """Binding-completeness matrix over the REAL template for the non-variant
    skills × both pipelines × both modes: ok, ZERO token residue, and the
    mode/always anchors present.

    RED: emit_cycle_prompt missing → AttributeError.
    """
    _guard()
    skills = ["/execute-plan", "/retro", "/retro-feature", "/spec"]
    for pipeline in ("feature", "bug"):
        for cloud in (False, True):
            mode = "cloud" if cloud else "workstation"
            for skill in skills:
                state = _emit_state(sub_skill=skill)
                result = lazy_core.emit_cycle_prompt(
                    Path("/nonexistent/repo"), state,
                    pipeline=pipeline, cloud=cloud,
                    template_dir=_REAL_TEMPLATE_DIR,
                )
                ctx = f"pipeline={pipeline} mode={mode} skill={skill}"
                assert result is not None, f"{ctx}: expected a dict, got None"
                assert result.get("ok") is True, f"{ctx}: not ok → {result}"
                prompt = result["prompt"]
                residue = _TOKEN_RESIDUE_RE.findall(prompt)
                assert not residue, f"{ctx}: unbound token residue {residue}"
                # Always-present anchor (retro grader keys on this literal).
                assert "Operating mode: batch" in prompt, f"{ctx}: missing 'Operating mode: batch'"
                # Mode-specific load-bearing dispatch-policy anchor.
                # workstation-recursive-subagent-dispatch (2026-07-09): the
                # workstation INLINE OVERRIDE was lifted — workstation cycle
                # prompts now carry the dispatch-permitted policy marker; cloud
                # keeps the inline override verbatim.
                if cloud:
                    assert "CLOUD OVERRIDE — LOAD-BEARING" in prompt, f"{ctx}: missing cloud override anchor"
                    assert "WORKSTATION DISPATCH — LOAD-BEARING" not in prompt, (
                        f"{ctx}: workstation dispatch policy leaked into a cloud prompt"
                    )
                else:
                    assert "WORKSTATION DISPATCH — LOAD-BEARING" in prompt, f"{ctx}: missing workstation dispatch anchor"
                    assert "INLINE OVERRIDE — LOAD-BEARING" not in prompt, (
                        f"{ctx}: retired inline-override marker leaked into a workstation prompt"
                    )
                assert result["model"] == "opus", f"{ctx}: expected opus model, got {result['model']!r}"


def test_emit_cycle_prompt_mcp_test_variant_anchors_real_template():
    """mcp-test (workstation) over the REAL template: runtime-up variant by
    default (no PHASES.md), no-runtime variant when PHASES declares
    not-required — each with its distinct anchor and zero residue.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # --- runtime-up: no PHASES.md present → default runtime-up ---
        state_up = _emit_state(sub_skill="/mcp-test", spec_path=str(spec_dir))
        res_up = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), state_up,
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
        assert res_up is not None and res_up.get("ok") is True, f"runtime-up: {res_up}"
        assert "RUNTIME IS ALREADY UP" in res_up["prompt"], "runtime-up anchor missing"
        assert "RUNTIME NOT PRE-BOOTED" not in res_up["prompt"], "no-runtime section leaked into runtime-up"
        assert not _TOKEN_RESIDUE_RE.findall(res_up["prompt"]), "runtime-up residue"

        # --- no-runtime: PHASES.md declares not-required + a reason ---
        reason = "the plan touches no MCP-reachable surface at all"
        (spec_dir / "PHASES.md").write_text(
            f"# PHASES\n\n**MCP runtime:** not-required — {reason}\n",
            encoding="utf-8",
        )
        state_nr = _emit_state(sub_skill="/mcp-test", spec_path=str(spec_dir))
        res_nr = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), state_nr,
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
        assert res_nr is not None and res_nr.get("ok") is True, f"no-runtime: {res_nr}"
        assert "RUNTIME NOT PRE-BOOTED" in res_nr["prompt"], "no-runtime anchor missing"
        assert "RUNTIME IS ALREADY UP" not in res_nr["prompt"], "runtime-up section leaked into no-runtime"
        assert reason in res_nr["prompt"], "untestability_reason not bound"
        assert not _TOKEN_RESIDUE_RE.findall(res_nr["prompt"]), "no-runtime residue"


def test_emit_cycle_prompt_bug_tokens_real_template():
    """pipeline=bug binds FIXED.md + __mark_fixed__ (never COMPLETED.md /
    __mark_complete__ in a NO-LOOP emission); feature is the mirror image.

    Scoped to a no-loop emission because loop-block.md legitimately names both
    receipts; the base template's receipt name is exclusively via {receipt_name}.
    """
    _guard()
    state = _emit_state(sub_skill="/execute-plan")
    bug = lazy_core.emit_cycle_prompt(
        Path("/nonexistent/repo"), state,
        pipeline="bug", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
    )
    assert bug is not None and bug.get("ok") is True, f"bug emit: {bug}"
    bp = bug["prompt"]
    assert "FIXED.md" in bp, "bug prompt missing FIXED.md"
    assert "__mark_fixed__" in bp, "bug prompt missing __mark_fixed__"
    assert "COMPLETED.md" not in bp, "bug prompt leaked COMPLETED.md"
    assert "__mark_complete__" not in bp, "bug prompt leaked __mark_complete__"
    assert "bug pipeline" in bp, "bug prompt missing pipeline_phrase 'bug pipeline'"

    feat = lazy_core.emit_cycle_prompt(
        Path("/nonexistent/repo"), state,
        pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
    )
    assert feat is not None and feat.get("ok") is True, f"feature emit: {feat}"
    fp = feat["prompt"]
    assert "COMPLETED.md" in fp, "feature prompt missing COMPLETED.md"
    assert "__mark_complete__" in fp, "feature prompt missing __mark_complete__"
    assert "FIXED.md" not in fp, "feature prompt leaked FIXED.md"
    assert "__mark_fixed__" not in fp, "feature prompt leaked __mark_fixed__"
    assert "feature pipeline" in fp, "feature prompt missing pipeline_phrase 'feature pipeline'"


def test_emit_cycle_prompt_pseudo_and_idle_return_none():
    """Pseudo-skill (__*), falsy sub_skill, and falsy feature_id each → None."""
    _guard()
    repo = Path("/nonexistent/repo")
    # Pseudo-skill.
    assert lazy_core.emit_cycle_prompt(
        repo, _emit_state(sub_skill="__mark_complete__"),
        pipeline="feature", template_dir=_REAL_TEMPLATE_DIR,
    ) is None, "pseudo-skill must return None"
    # Falsy sub_skill (empty / None).
    assert lazy_core.emit_cycle_prompt(
        repo, _emit_state(sub_skill=""),
        pipeline="feature", template_dir=_REAL_TEMPLATE_DIR,
    ) is None, "empty sub_skill must return None"
    assert lazy_core.emit_cycle_prompt(
        repo, _emit_state(sub_skill=None),
        pipeline="feature", template_dir=_REAL_TEMPLATE_DIR,
    ) is None, "None sub_skill must return None"
    # Falsy feature_id (terminal / idle probe).
    assert lazy_core.emit_cycle_prompt(
        repo, _emit_state(feature_id=None),
        pipeline="feature", template_dir=_REAL_TEMPLATE_DIR,
    ) is None, "None feature_id must return None"
    assert lazy_core.emit_cycle_prompt(
        repo, _emit_state(feature_id=""),
        pipeline="feature", template_dir=_REAL_TEMPLATE_DIR,
    ) is None, "empty feature_id must return None"


def test_emit_cycle_prompt_loop_append_and_model_flip():
    """repeat_count>=2 → loop block appended (fence stripped, tokens bound,
    LOOP DETECTED present) + model=='sonnet'. repeat_count 1/None → no block,
    model=='opus'.

    Uses /retro (an opus-base, NOT complexity-pinned skill) so the loop-flip to
    sonnet is exercised. A defaulting-to-complex /execute-plan cycle is now
    complexity-pinned to opus (checkpoint-resume-false-loop-flips-complex-part-to-
    sonnet), so it would NOT flip — that pin is covered by its own tests below.
    """
    _guard()
    repo = Path("/nonexistent/repo")
    state = _emit_state(sub_skill="/retro")

    # repeat_count == 2 → loop appended, sonnet.
    looped = lazy_core.emit_cycle_prompt(
        repo, state, pipeline="feature", cloud=False,
        repeat_count=2, template_dir=_REAL_TEMPLATE_DIR,
    )
    assert looped is not None and looped.get("ok") is True, f"looped: {looped}"
    assert looped["model"] == "sonnet", f"expected sonnet, got {looped['model']!r}"
    assert "LOOP DETECTED" in looped["prompt"], "loop block not appended"
    # Fence lines stripped: no bare ``` triple-backtick fence in the assembled prompt.
    assert "```" not in looped["prompt"], "loop-block code fence not stripped"
    # Tokens bound (item_id appears in the loop block's literal text).
    assert "feat-x" in looped["prompt"], "loop block item_id not bound"
    assert not _TOKEN_RESIDUE_RE.findall(looped["prompt"]), "loop residue"

    # repeat_count == 1 → no block, opus.
    one = lazy_core.emit_cycle_prompt(
        repo, state, pipeline="feature", cloud=False,
        repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
    )
    assert one is not None and one.get("ok") is True
    assert one["model"] == "opus", f"repeat_count=1 expected opus, got {one['model']!r}"
    assert "LOOP DETECTED" not in one["prompt"], "loop block appended at repeat_count=1"

    # repeat_count == None → no block, opus.
    none = lazy_core.emit_cycle_prompt(
        repo, state, pipeline="feature", cloud=False,
        repeat_count=None, template_dir=_REAL_TEMPLATE_DIR,
    )
    assert none is not None and none.get("ok") is True
    assert none["model"] == "opus", f"repeat_count=None expected opus, got {none['model']!r}"
    assert "LOOP DETECTED" not in none["prompt"], "loop block appended at repeat_count=None"


def test_emit_cycle_prompt_mcp_test_cycle_model_haiku():
    """A happy-path mcp-test cycle (no loop) dispatches on haiku — the Informed
    Dispatcher base tier (run the deterministic engine, read the small verdict;
    no MCP API driven by the model, no assertions model-judged). repeat_count 1
    and None both → 'haiku'. Regression for docs/bugs/mcp-test-haiku-tier-unwired
    (the 'haiku happy path' was description-only prose, wired into zero paths).

    Reshaped for docs/bugs/mcp-test-legacy-md-routes-to-haiku: under option-(b)
    conservative escalation a bare empty spec_dir (no scenarios) now correctly
    routes to sonnet (no ready YAML). To keep asserting the genuine haiku happy
    path, the fixture seeds a READY converted-YAML scenario under
    mcp-tests/corpus/live/, so 'all candidates are ready YAML' → haiku holds.
    """
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        live = spec_dir / "mcp-tests" / "corpus" / "live"
        live.mkdir(parents=True)
        (live / "scenario-x.yaml").write_text("name: scenario-x\n", encoding="utf-8")
        for rc in (1, None):
            state = _emit_state(sub_skill="/mcp-test", spec_path=str(spec_dir))
            r = lazy_core.emit_cycle_prompt(
                repo, state, pipeline="feature", cloud=False,
                repeat_count=rc, template_dir=_REAL_TEMPLATE_DIR,
            )
            assert r is not None and r.get("ok") is True, f"rc={rc}: {r}"
            assert r["model"] == "haiku", f"rc={rc}: mcp-test expected haiku, got {r['model']!r}"


def test_emit_cycle_prompt_mcp_test_legacy_md_escalates_sonnet():
    """An mcp-test cycle whose ONLY scenario is an unconverted legacy `.md`
    (no converted corpus/live/*.yaml counterpart) escalates to sonnet at emit
    time — so the .md→v1-YAML conversion lands on a capable tier instead of the
    haiku that BLOCKs. Regression for docs/bugs/mcp-test-legacy-md-routes-to-haiku.
    This MUST fail against the pre-fix hardcoded-haiku emit.
    """
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        legacy = spec_dir / "mcp-tests"
        legacy.mkdir(parents=True)
        # Legacy .md with NO sibling .yaml and NO corpus/live converted YAML.
        (legacy / "scenario-x.md").write_text("# legacy scenario\n", encoding="utf-8")
        state = _emit_state(sub_skill="/mcp-test", spec_path=str(spec_dir))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
        )
        assert r is not None and r.get("ok") is True, f"{r}"
        assert r["model"] == "sonnet", (
            f"legacy-.md mcp-test expected sonnet, got {r['model']!r}"
        )


def test_emit_cycle_prompt_mcp_test_ready_yaml_stays_haiku():
    """An mcp-test cycle whose candidate scenarios are ALL ready converted YAML
    (corpus/live/*.yaml present) stays on the haiku happy path. The explicit
    happy-path sibling of the legacy-.md escalation fixture above
    (docs/bugs/mcp-test-legacy-md-routes-to-haiku)."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        live = spec_dir / "mcp-tests" / "corpus" / "live"
        live.mkdir(parents=True)
        (live / "scenario-x.yaml").write_text("name: scenario-x\n", encoding="utf-8")
        state = _emit_state(sub_skill="/mcp-test", spec_path=str(spec_dir))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
        )
        assert r is not None and r.get("ok") is True, f"{r}"
        assert r["model"] == "haiku", (
            f"ready-YAML mcp-test expected haiku, got {r['model']!r}"
        )


def test_emit_cycle_prompt_mcp_test_loop_cycle_model_sonnet():
    """A looping (repeat_count>=2) mcp-test cycle ESCALATES from the haiku base to
    sonnet — the loop block's unconditional 'sonnet' target composes correctly
    with the cheaper base (a stuck mechanical cycle gets a stronger model)."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        state = _emit_state(sub_skill="/mcp-test", spec_path=str(spec_dir))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=2, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "sonnet", f"looping mcp-test expected sonnet, got {r['model']!r}"
    assert "LOOP DETECTED" in r["prompt"], "loop block not appended for looping mcp-test"


# --- Phase 9: per-part complexity model tiering (lazy-validation-readiness) ---
#
# The /execute-plan cycle's dispatch model is selected from the current plan
# part's `complexity` frontmatter tag:
#   mechanical  → sonnet
#   complex     → opus
#   absent/untagged → opus (back-compat — the safe default tier)
# This composes with the loop-block downgrade (repeat_count >= 2 → sonnet) WITH A
# COMPLEXITY FLOOR (checkpoint-resume-false-loop-flips-complex-part-to-sonnet):
# a looping *mechanical* part still downgrades to sonnet, but a looping *complex*
# (or untagged-default-complex) part is PINNED to opus — a complex part on sonnet
# is HARD-refused by the cycle prompt (model-tier-mismatch), so a loop-flip to
# sonnet only climbs the stall streak toward a halt.

def _write_complexity_plan(plan_dir: Path, name: str, complexity: str | None) -> Path:
    """Write a minimal plan file carrying an optional complexity tag; return path."""
    plan_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", "kind: implementation-plan", "status: Ready", "phases:", "  - 1"]
    if complexity is not None:
        lines.append(f"complexity: {complexity}")
    lines += ["---", "", "# Plan", ""]
    p = plan_dir / name
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_emit_cycle_prompt_mechanical_part_cycle_model_sonnet():
    """A `mechanical`-tagged execute-plan part → cycle_model == 'sonnet' even
    with no loop (repeat_count=1)."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", "mechanical")
        state = _emit_state(sub_skill="/execute-plan", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "sonnet", f"mechanical part expected sonnet, got {r['model']!r}"


def test_emit_cycle_prompt_complex_part_cycle_model_opus():
    """A `complex`-tagged execute-plan part → cycle_model == 'opus'."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", "complex")
        state = _emit_state(sub_skill="/execute-plan", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "opus", f"complex part expected opus, got {r['model']!r}"


def test_emit_cycle_prompt_untagged_part_cycle_model_opus():
    """An untagged execute-plan part → cycle_model == 'opus' (back-compat)."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", None)
        state = _emit_state(sub_skill="/execute-plan", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "opus", f"untagged part expected opus, got {r['model']!r}"


def test_emit_cycle_prompt_complex_part_loop_stays_opus():
    """A looping (repeat_count>=2) `complex` execute-plan part STAYS opus — the
    loop-flip is capped at the declared complexity floor
    (checkpoint-resume-false-loop-flips-complex-part-to-sonnet). A complex part on
    sonnet is HARD-refused by the cycle prompt (model-tier-mismatch), so the flip
    must NOT downgrade it. The loop block is still appended (model-independent).
    This MUST fail against the pre-fix unconditional-sonnet loop-flip."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", "complex")
        state = _emit_state(sub_skill="/execute-plan", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=2, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "opus", f"looping complex part expected opus, got {r['model']!r}"
    assert "LOOP DETECTED" in r["prompt"], "loop block not appended for looping complex part"


def test_emit_cycle_prompt_untagged_part_loop_stays_opus():
    """A looping (repeat_count>=2) UNTAGGED execute-plan part STAYS opus — the
    complexity floor uses plan_complexity's SAFE `complex` default for an untagged
    part, matching the base-tier conservatism (untagged → opus base). Locks the
    conservative boundary against a future 'downgrade untagged on loop' regression
    (checkpoint-resume-false-loop-flips-complex-part-to-sonnet, Out of Scope note)."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", None)
        state = _emit_state(sub_skill="/execute-plan", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=2, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "opus", f"looping untagged part expected opus, got {r['model']!r}"
    assert "LOOP DETECTED" in r["prompt"], "loop block not appended for looping untagged part"


def test_emit_cycle_prompt_mechanical_part_loop_stays_sonnet():
    """A looping (repeat_count>=2) `mechanical` execute-plan part downgrades to
    sonnet exactly as before — the complexity floor only pins NON-mechanical parts,
    so a mechanical part's loop-flip is unaffected."""
    _guard()
    repo = Path("/nonexistent/repo")
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", "mechanical")
        state = _emit_state(sub_skill="/execute-plan", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=2, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "sonnet", f"looping mechanical part expected sonnet, got {r['model']!r}"
    assert "LOOP DETECTED" in r["prompt"], "loop block not appended for looping mechanical part"


def test_emit_cycle_prompt_non_execute_plan_ignores_complexity():
    """Complexity tiering applies ONLY to /execute-plan cycles. A non-execute
    cycle (e.g. /retro) selects opus regardless of any plan file."""
    _guard()
    repo = Path("/nonexistent/repo")
    # sub_skill_args points at a mechanical plan, but the cycle is NOT execute-plan.
    with tempfile.TemporaryDirectory() as td:
        plan = _write_complexity_plan(Path(td), "part-1.md", "mechanical")
        state = _emit_state(sub_skill="/retro", sub_skill_args=str(plan))
        r = lazy_core.emit_cycle_prompt(
            repo, state, pipeline="feature", cloud=False,
            repeat_count=1, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r.get("ok") is True, f"emit: {r}"
    assert r["model"] == "opus", f"non-execute cycle expected opus, got {r['model']!r}"


# --- Synthetic-template parser-behavior unit tests --------------------------

def _write_synth_template(template_dir: Path, sections: str, loop_body: str | None = None):
    """Write a synthetic cycle-base-prompt.md (+ optional loop-block.md) into
    template_dir. `sections` is the post-metadata body (markers + content);
    a metadata header line is prepended so the emitter strips it.
    """
    template_dir.mkdir(parents=True, exist_ok=True)
    header = "# synthetic template\n\nMetadata line that must never be emitted.\n\n"
    (template_dir / "cycle-base-prompt.md").write_text(header + sections, encoding="utf-8")
    if loop_body is not None:
        (template_dir / "loop-block.md").write_text(loop_body, encoding="utf-8")


def test_emit_cycle_prompt_section_selection_synthetic():
    """Selection unit tests: skills csv inclusion, mode exclusion, pipeline
    exclusion — all on a synthetic template.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "tpl"
        body = (
            "<!-- @section a pipelines=feature modes=workstation skills=execute-plan -->\n"
            "SECTION_A for execute-plan workstation feature only.\n"
            "\n"
            "<!-- @section b pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
            "SECTION_B universal.\n"
            "\n"
            "<!-- @section c pipelines=bug modes=workstation skills=all -->\n"
            "SECTION_C bug only.\n"
            "\n"
            "<!-- @section d pipelines=feature modes=cloud skills=all -->\n"
            "SECTION_D feature cloud only.\n"
        )
        _write_synth_template(tdir, body)

        # feature / workstation / execute-plan → A + B, not C (bug) not D (cloud).
        r = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=tdir,
        )
        assert r is not None and r["ok"], r
        p = r["prompt"]
        assert "SECTION_A" in p and "SECTION_B" in p
        assert "SECTION_C" not in p, "bug-only section leaked into feature emission"
        assert "SECTION_D" not in p, "cloud-only section leaked into workstation emission"
        # Metadata header never emitted.
        assert "Metadata line that must never be emitted" not in p
        # Exactly one blank line between the two joined sections.
        assert "SECTION_A for execute-plan workstation feature only.\n\nSECTION_B universal." in p

        # feature / workstation / retro → skills csv excludes A → only B.
        r2 = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), _emit_state(sub_skill="/retro"),
            pipeline="feature", cloud=False, template_dir=tdir,
        )
        assert r2 is not None and r2["ok"], r2
        assert "SECTION_A" not in r2["prompt"], "skills-csv exclusion failed (A should be excluded for retro)"
        assert "SECTION_B" in r2["prompt"]

        # bug / workstation → B + C, not A (skills + pipeline) not D.
        r3 = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), _emit_state(sub_skill="/retro"),
            pipeline="bug", cloud=False, template_dir=tdir,
        )
        assert r3 is not None and r3["ok"], r3
        assert "SECTION_C" in r3["prompt"] and "SECTION_B" in r3["prompt"]
        assert "SECTION_A" not in r3["prompt"]

        # feature / cloud → B + D, not A not C.
        r4 = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), _emit_state(sub_skill="/retro"),
            pipeline="feature", cloud=True, template_dir=tdir,
        )
        assert r4 is not None and r4["ok"], r4
        assert "SECTION_D" in r4["prompt"] and "SECTION_B" in r4["prompt"]
        assert "SECTION_C" not in r4["prompt"]


def test_emit_cycle_prompt_refuses_unknown_token_synthetic():
    """A synthetic section with an unknown {bogus_token} → ok=False naming it."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "tpl"
        body = (
            "<!-- @section a pipelines=feature modes=workstation skills=all -->\n"
            "This section references {bogus_token} which is not bindable.\n"
        )
        _write_synth_template(tdir, body)
        r = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"), _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=tdir,
        )
        assert r is not None, "refusal must be a dict, not None"
        assert r.get("ok") is False, f"expected refusal, got {r}"
        assert "bogus_token" in r.get("refused", ""), f"refusal must name the token: {r}"


def test_emit_cycle_prompt_mcp_variant_routing_synthetic():
    """Variant routing on a synthetic template: PHASES.md with not-required →
    no-runtime section + reason bound; PHASES.md absent → runtime-up section.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "tpl"
        body = (
            "<!-- @section base pipelines=feature modes=workstation skills=mcp-test -->\n"
            "MCP base section.\n"
            "\n"
            "<!-- @section v pipelines=feature modes=workstation skills=mcp-test variant=runtime-up -->\n"
            "VARIANT_RUNTIME_UP body.\n"
            "\n"
            "<!-- @section v pipelines=feature modes=workstation skills=mcp-test variant=no-runtime -->\n"
            "VARIANT_NO_RUNTIME body — reason: {untestability_reason}.\n"
        )
        _write_synth_template(tdir, body)

        # No PHASES.md → runtime-up.
        spec_up = Path(td) / "spec_up"
        spec_up.mkdir()
        r_up = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"),
            _emit_state(sub_skill="/mcp-test", spec_path=str(spec_up)),
            pipeline="feature", cloud=False, template_dir=tdir,
        )
        assert r_up is not None and r_up["ok"], r_up
        assert "VARIANT_RUNTIME_UP" in r_up["prompt"]
        assert "VARIANT_NO_RUNTIME" not in r_up["prompt"]

        # PHASES.md not-required → no-runtime + reason.
        spec_nr = Path(td) / "spec_nr"
        spec_nr.mkdir()
        reason = "no MCP-reachable surface in this plan"
        (spec_nr / "PHASES.md").write_text(
            f"**MCP runtime:** not-required — {reason}\n", encoding="utf-8"
        )
        r_nr = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"),
            _emit_state(sub_skill="/mcp-test", spec_path=str(spec_nr)),
            pipeline="feature", cloud=False, template_dir=tdir,
        )
        assert r_nr is not None and r_nr["ok"], r_nr
        assert "VARIANT_NO_RUNTIME" in r_nr["prompt"]
        assert "VARIANT_RUNTIME_UP" not in r_nr["prompt"]
        assert reason in r_nr["prompt"], "untestability_reason not bound from PHASES line"


def test_emit_cycle_prompt_work_branch_fallback_non_git():
    """A non-git repo_root → {work_branch} falls back to 'the current branch',
    and the emission still succeeds (ok=True, no residue).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        non_git = Path(td) / "not-a-repo"
        non_git.mkdir()
        r = lazy_core.emit_cycle_prompt(
            non_git, _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
        assert r is not None and r["ok"] is True, f"non-git emit: {r}"
        assert "the current branch" in r["prompt"], "work_branch fallback string missing"
        assert not _TOKEN_RESIDUE_RE.findall(r["prompt"]), "non-git residue"


def test_emit_cycle_prompt_sub_skill_args_none_binds_empty():
    """sub_skill_args=None binds to an empty string (no 'None' literal, no residue)."""
    _guard()
    state = _emit_state(sub_skill="/execute-plan", sub_skill_args=None)
    r = lazy_core.emit_cycle_prompt(
        Path("/nonexistent/repo"), state,
        pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
    )
    assert r is not None and r["ok"] is True, f"emit: {r}"
    # The literal "args: None" must not appear (None → "").
    assert "args: None" not in r["prompt"], "sub_skill_args=None leaked a 'None' literal"
    assert not _TOKEN_RESIDUE_RE.findall(r["prompt"]), "residue with None args"


# ---------------------------------------------------------------------------
# Tests: emit_cycle_prompt repo prompt addenda — Phase 10 WU-3
#
# emit_cycle_prompt reads an OPTIONAL <repo_root>/.claude/skill-config/
# cycle-prompt-addenda.md, parsed with the SAME @section grammar + selection
# semantics as the base template. Selected addenda are appended AFTER base
# sections and BEFORE the loop block, token-bound + residue-guarded with the
# same map. Absent file → byte-identical to current behavior. NOTE: the addenda
# path is keyed off repo_root, NOT template_dir.
# ---------------------------------------------------------------------------

def _write_addenda(repo_root: Path, body: str) -> Path:
    """Write <repo_root>/.claude/skill-config/cycle-prompt-addenda.md (creating
    the dir tree). Returns the addenda path."""
    addenda_dir = repo_root / ".claude" / "skill-config"
    addenda_dir.mkdir(parents=True, exist_ok=True)
    path = addenda_dir / "cycle-prompt-addenda.md"
    header = "# repo addenda\n\nMetadata that must never be emitted.\n\n"
    path.write_text(header + body, encoding="utf-8")
    return path


def test_emit_cycle_prompt_addenda_absent_is_byte_identical():
    """A repo_root with NO addenda file → output byte-identical to the emission
    without any addenda dir. Pins the absent-file no-op contract.

    RED: an impl that always tries to read the addenda file and crashes, or that
    changes output shape when the file is absent.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # repo_root WITHOUT a .claude/skill-config/cycle-prompt-addenda.md.
        repo_a = Path(td) / "repo_a"
        repo_a.mkdir()
        state = _emit_state(sub_skill="/execute-plan")
        r_no_file = lazy_core.emit_cycle_prompt(
            repo_a, state, pipeline="feature", cloud=False,
            template_dir=_REAL_TEMPLATE_DIR,
        )
        # A second repo_root, also without the file, but with the .claude tree
        # present-but-empty (proves it's the FILE, not the dir, that gates it).
        repo_b = Path(td) / "repo_b"
        (repo_b / ".claude" / "skill-config").mkdir(parents=True)
        state_b = dict(state)
        state_b["sub_skill"] = "/execute-plan"
        r_empty_dir = lazy_core.emit_cycle_prompt(
            repo_b, state_b, pipeline="feature", cloud=False,
            template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r_no_file is not None and r_no_file["ok"], r_no_file
    assert r_empty_dir is not None and r_empty_dir["ok"], r_empty_dir
    # cwd token binds to repo_root, so normalize it out before comparing prompts.
    norm_a = r_no_file["prompt"].replace(str(repo_a), "<CWD>")
    norm_b = r_empty_dir["prompt"].replace(str(repo_b), "<CWD>")
    assert norm_a == norm_b, (
        "absent addenda file must produce byte-identical output (modulo cwd)"
    )


def test_emit_cycle_prompt_addenda_selected_and_appended_after_base():
    """A matching addenda section is appended AFTER the base sections (and the
    addenda content + a base-section marker both appear, addenda LAST)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_addenda(
            repo,
            "<!-- @section repo-extra pipelines=feature modes=workstation skills=execute-plan -->\n"
            "ADDENDA_BODY for execute-plan workstation feature.\n",
        )
        r = lazy_core.emit_cycle_prompt(
            repo, _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r["ok"], r
    p = r["prompt"]
    assert "ADDENDA_BODY" in p, "selected addenda section was not appended"
    assert "Metadata that must never be emitted" not in p, "addenda metadata header leaked"
    # The addenda body must come AFTER the base template body (the base 'task'
    # section's batch-mode text is near the top). Use a stable base anchor.
    base_anchor_idx = p.find("batch")  # base 'task' section mentions batch mode
    addenda_idx = p.find("ADDENDA_BODY")
    assert base_anchor_idx != -1, "base section anchor not found in prompt"
    assert addenda_idx > base_anchor_idx, "addenda must be appended AFTER base sections"


def test_emit_cycle_prompt_addenda_filtered_by_skill_and_pipeline_and_mode():
    """Addenda sections honor the same skills / pipeline / mode filters as base
    sections: a section scoped to skills=mcp-test is NOT selected on an
    execute-plan cycle; a section scoped to modes=cloud is NOT selected
    workstation; a section scoped to pipelines=bug is NOT selected on feature.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_addenda(
            repo,
            "<!-- @section match pipelines=feature modes=workstation skills=execute-plan -->\n"
            "ADDENDA_MATCH.\n"
            "\n"
            "<!-- @section wrongskill pipelines=feature modes=workstation skills=mcp-test -->\n"
            "ADDENDA_WRONGSKILL.\n"
            "\n"
            "<!-- @section wrongmode pipelines=feature modes=cloud skills=all -->\n"
            "ADDENDA_WRONGMODE.\n"
            "\n"
            "<!-- @section wrongpipe pipelines=bug modes=workstation skills=all -->\n"
            "ADDENDA_WRONGPIPE.\n",
        )
        r = lazy_core.emit_cycle_prompt(
            repo, _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r["ok"], r
    p = r["prompt"]
    assert "ADDENDA_MATCH" in p, "matching addenda section not selected"
    assert "ADDENDA_WRONGSKILL" not in p, "skills filter not applied to addenda"
    assert "ADDENDA_WRONGMODE" not in p, "modes filter not applied to addenda"
    assert "ADDENDA_WRONGPIPE" not in p, "pipelines filter not applied to addenda"


def test_emit_cycle_prompt_addenda_tokens_bound():
    """Tokens inside an addenda section are bound by the SAME binding map."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_addenda(
            repo,
            "<!-- @section tok pipelines=feature modes=workstation skills=execute-plan -->\n"
            "Addenda for {item_id} ({item_label}).\n",
        )
        r = lazy_core.emit_cycle_prompt(
            repo, _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r["ok"], r
    p = r["prompt"]
    assert "Addenda for feat-x (Feature)." in p, f"addenda tokens not bound: {p[-300:]!r}"
    assert not _TOKEN_RESIDUE_RE.findall(p), "residue after addenda binding"


def test_emit_cycle_prompt_addenda_residue_refuses_naming_file():
    """An addenda section with an unbound {bogus_token} → the WHOLE emission
    refuses (ok=False), and the refusal names the addenda file so the operator
    knows where the bad section lives.

    RED: an impl that binds addenda but skips the residue guard, or one whose
    refusal does not identify the addenda source.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_addenda(
            repo,
            "<!-- @section bad pipelines=feature modes=workstation skills=all -->\n"
            "This addenda references {not_a_real_token}.\n",
        )
        r = lazy_core.emit_cycle_prompt(
            repo, _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None, "refusal must be a dict, not None"
    assert r.get("ok") is False, f"expected refusal on addenda residue, got {r}"
    refused = r.get("refused", "")
    assert "not_a_real_token" in refused, f"refusal must name the token: {refused!r}"
    assert "cycle-prompt-addenda.md" in refused, (
        f"refusal must name the addenda file so the bad section is locatable: {refused!r}"
    )


def test_emit_cycle_prompt_addenda_before_loop_block():
    """With repeat_count >= 2, the assembled order is: base sections → addenda →
    loop block. The addenda body must appear AFTER the base body and BEFORE the
    LOOP DETECTED block.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_addenda(
            repo,
            "<!-- @section pre-loop pipelines=feature modes=workstation skills=execute-plan -->\n"
            "ADDENDA_PRELOOP marker.\n",
        )
        r = lazy_core.emit_cycle_prompt(
            repo, _emit_state(sub_skill="/execute-plan"),
            pipeline="feature", cloud=False, repeat_count=2,
            template_dir=_REAL_TEMPLATE_DIR,
        )
    assert r is not None and r["ok"], r
    p = r["prompt"]
    assert "ADDENDA_PRELOOP" in p, "addenda not present with loop block"
    assert "LOOP DETECTED" in p, "loop block not appended at repeat_count=2"
    addenda_idx = p.find("ADDENDA_PRELOOP")
    loop_idx = p.find("LOOP DETECTED")
    base_idx = p.find("batch")
    assert base_idx < addenda_idx < loop_idx, (
        f"order must be base < addenda < loop, got base={base_idx} "
        f"addenda={addenda_idx} loop={loop_idx}"
    )
    # This is a defaulting-to-complex /execute-plan cycle, so the loop-flip is
    # capped at the opus complexity floor (checkpoint-resume-false-loop-flips-
    # complex-part-to-sonnet) — the loop block is still appended, but the model
    # stays opus (the ordering, not the model, is this test's subject).
    assert r["model"] == "opus", (
        f"complexity-pinned execute-plan loop keeps opus (loop block still "
        f"appended), got {r['model']!r}"
    )


# ---------------------------------------------------------------------------
# cycle-prompt-environment-dialect Phase 2 (STATE lane) — `hosts=` selection
# filter. Both selection loops (base template + repo addenda) must exclude a
# `hosts=windows` section when the emitting host is not Windows, and always
# select it (byte-identical to a section with no `hosts=` attribute) when it
# is.
#
# Faking the host CANNOT be done by patching the real `os.name` global: the
# stdlib `pathlib.Path()` factory itself branches on `os.name` at
# CONSTRUCTION time to pick WindowsPath/PosixPath, and emit_cycle_prompt
# calls the bare `Path(...)` factory internally (e.g.
# `_read_mcp_runtime_decision`'s `Path(spec_path) / "PHASES.md"`) on every
# invocation — patching the real os.name to the "wrong" platform makes that
# internal call raise `NotImplementedError: cannot instantiate 'PosixPath'
# on your system` (or vice versa). Instead, `lazy_core.dispatch.os` (the module-level
# name `emit_cycle_prompt`'s `os.name` reads resolve through) is rebound to a
# transparent proxy that overrides ONLY `.name` and forwards every other
# attribute to the REAL os module — pathlib's own `os` reference (a separate
# namespace binding to the same real module) is completely unaffected.
# ---------------------------------------------------------------------------

class _FakeOsName:
    """Transparent proxy for the `os` module overriding only `.name`."""

    def __init__(self, name: str):
        self.name = name

    def __getattr__(self, attr):
        return getattr(os, attr)


def test_emit_cycle_prompt_hosts_windows_selected_on_win32():
    """A `hosts=windows` section IS selected when the emitting host is
    Windows (os.name == 'nt')."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "tpl"
        repo = Path("/nonexistent/repo")
        body = (
            "<!-- @section core pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
            "SECTION_CORE universal.\n"
            "\n"
            "<!-- @section win pipelines=feature,bug modes=workstation skills=all hosts=windows -->\n"
            "SECTION_WINDOWS host-conditional.\n"
        )
        _write_synth_template(tdir, body)
        state = _emit_state(sub_skill="/retro")
        old_os = lazy_core.dispatch.os
        lazy_core.dispatch.os = _FakeOsName("nt")
        try:
            r = lazy_core.emit_cycle_prompt(
                repo, state, pipeline="feature", cloud=False, template_dir=tdir,
            )
        finally:
            lazy_core.dispatch.os = old_os
    assert r is not None and r["ok"], r
    assert "SECTION_WINDOWS" in r["prompt"], (
        "hosts=windows section must be selected when os.name == 'nt'"
    )
    assert "SECTION_CORE" in r["prompt"]


def test_emit_cycle_prompt_hosts_windows_excluded_on_non_windows():
    """A `hosts=windows` section is EXCLUDED when the emitting host is not
    Windows (os.name != 'nt'); the unconditional core section still selects —
    the filter is additive, never over-broad."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "tpl"
        repo = Path("/nonexistent/repo")
        body = (
            "<!-- @section core pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
            "SECTION_CORE universal.\n"
            "\n"
            "<!-- @section win pipelines=feature,bug modes=workstation skills=all hosts=windows -->\n"
            "SECTION_WINDOWS host-conditional.\n"
        )
        _write_synth_template(tdir, body)
        state = _emit_state(sub_skill="/retro")
        old_os = lazy_core.dispatch.os
        lazy_core.dispatch.os = _FakeOsName("posix")
        try:
            r = lazy_core.emit_cycle_prompt(
                repo, state, pipeline="feature", cloud=False, template_dir=tdir,
            )
        finally:
            lazy_core.dispatch.os = old_os
    assert r is not None and r["ok"], r
    assert "SECTION_WINDOWS" not in r["prompt"], (
        "hosts=windows section must be EXCLUDED when os.name != 'nt'"
    )
    assert "SECTION_CORE" in r["prompt"], (
        "a section without hosts= must still select — the filter is additive"
    )


def test_emit_cycle_prompt_hosts_windows_addenda_excluded_on_non_windows():
    """The `hosts=` filter applies identically to the repo-addenda selection
    loop, not just the base-template loop."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _write_addenda(
            repo,
            "<!-- @section addenda-win pipelines=feature modes=workstation "
            "skills=all hosts=windows -->\n"
            "ADDENDA_WINDOWS marker.\n",
        )
        state = _emit_state(sub_skill="/retro")
        old_os = lazy_core.dispatch.os
        lazy_core.dispatch.os = _FakeOsName("posix")
        try:
            r = lazy_core.emit_cycle_prompt(
                repo, state, pipeline="feature", cloud=False,
                template_dir=_REAL_TEMPLATE_DIR,
            )
        finally:
            lazy_core.dispatch.os = old_os
    assert r is not None and r["ok"], r
    assert "ADDENDA_WINDOWS" not in r["prompt"], (
        "an addenda hosts=windows section must be excluded on a non-Windows host"
    )


def test_env_dialect_section_byte_budget():
    """The real template's env-dialect-core / env-dialect-windows sections
    each stay under the D4 2,048-byte budget (parsed via the SAME
    _parse_cycle_template the emitter uses — not a hand-copy of the text)."""
    _guard()
    text = (_REAL_TEMPLATE_DIR / "cycle-base-prompt.md").read_text(encoding="utf-8")
    sections = {
        sec["attrs"]["name"]: sec
        for sec in lazy_core._parse_cycle_template(text)
    }
    for name in ("env-dialect-core", "env-dialect-windows"):
        assert name in sections, f"expected section {name!r} in the real template"
        size = len(sections[name]["content"].encode("utf-8"))
        assert size < 2048, (
            f"{name} is {size} bytes, over the D4 2,048-byte budget"
        )


def test_bug_state_retro_fresh_routes_past_step8():
    """bug-state: RETRO_DONE.md whose phase_count_at_retro EQUALS the current
    phase count → fresh retro; routing falls through Step 8 to the Step 9
    workstation mcp-test dispatch as today."""
    _guard()
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_bug_retro_routing_repo(
            Path(td),
            "kind: retro-done\nbug_id: bug-retro\ndate: 2026-06-01\n"
            "rounds: 1\nphase_count_at_retro: 3\n",
            phase_count=3,
        )
        state = bs.compute_state(root, False)
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]


def test_normalize_widened_equivalence_pairs():
    """Widened normalize_prompt_for_hash: CRLF + trailing-whitespace + NFD all
    hash equal to the clean LF/NFC form; a semantic word change still differs."""
    _guard()
    import unicodedata as _ud
    base = "first line\nsecond café line\nthird"
    # CRLF variant
    crlf = base.replace("\n", "\r\n")
    # trailing-whitespace variant (spaces + tabs at line ends)
    trailing = "first line   \nsecond café line\t\nthird  "
    # NFD variant of the same text (decompose the accented é)
    nfd = _ud.normalize("NFD", base)
    # combined: CRLF + trailing ws + NFD
    combined = _ud.normalize("NFD", trailing.replace("\n", "\r\n"))

    h_base = lazy_core.prompt_sha256(base)
    for label, variant in [("crlf", crlf), ("trailing", trailing),
                           ("nfd", nfd), ("combined", combined)]:
        assert lazy_core.prompt_sha256(variant) == h_base, (
            f"{label} variant must hash equal to the clean form"
        )
    # The NFD variant must NOT be byte-identical pre-normalization (otherwise the
    # test proves nothing) — confirm the inputs genuinely differed.
    assert nfd != base, "NFD input must differ from NFC input pre-normalization"

    # Semantic mutation: an appended word changes the hash.
    mutated = base + " EXTRA"
    assert lazy_core.prompt_sha256(mutated) != h_base, (
        "a real word change must still change the hash (deny still fires)"
    )


def test_f2b_emdash_hashes_equal_to_hyphen():
    """F2b (lazy-validation-readiness Phase 2): normalize_prompt_for_hash / prompt_sha256
    must fold em-dash U+2014 → hyphen-minus '-' so an em-dash transcription slip
    produces the SAME sha256 as the hyphen form.

    Also covers en-dash (U+2013), horizontal bar (U+2015), and figure dash (U+2012).

    RED: normalize_prompt_for_hash has no dash-folding leg yet — the hashes differ.
    """
    _guard()
    # Em-dash → hyphen
    base = "Run the next step - implementation phase."
    em   = "Run the next step — implementation phase."  # em-dash U+2014
    assert lazy_core.prompt_sha256(em) == lazy_core.prompt_sha256(base), (
        f"em-dash variant must hash equal to hyphen form (F2b leg 5)"
    )
    # En-dash U+2013
    en = "Run the next step – implementation phase."
    assert lazy_core.prompt_sha256(en) == lazy_core.prompt_sha256(base), (
        f"en-dash variant must hash equal to hyphen form (F2b leg 5)"
    )
    # Horizontal bar U+2015
    hbar = "Run the next step ― implementation phase."
    assert lazy_core.prompt_sha256(hbar) == lazy_core.prompt_sha256(base), (
        f"horizontal-bar variant must hash equal to hyphen form (F2b leg 5)"
    )
    # Figure dash U+2012
    fdash = "Run the next step ‒ implementation phase."
    assert lazy_core.prompt_sha256(fdash) == lazy_core.prompt_sha256(base), (
        f"figure-dash variant must hash equal to hyphen form (F2b leg 5)"
    )


def test_f2b_curly_quotes_hash_equal_to_straight():
    """F2b: left/right single curly quotes → apostrophe; left/right double curly
    quotes → straight double quote.  A prompt with curly quotes must hash equal to
    the straight-quote form.

    RED: normalize_prompt_for_hash has no curly-quote folding leg yet.
    """
    _guard()
    # Single curly quotes U+2018 (left) and U+2019 (right)
    base_single = "it's a cycle dispatch prompt"
    curly_right = "it’s a cycle dispatch prompt"   # U+2019 RIGHT SINGLE QUOTATION MARK
    curly_left  = "‘it’s a cycle dispatch prompt"  # both curly singles
    base_left   = "'it's a cycle dispatch prompt"
    assert lazy_core.prompt_sha256(curly_right) == lazy_core.prompt_sha256(base_single), (
        f"right-single-curly-quote must hash equal to apostrophe form (F2b leg 5)"
    )
    assert lazy_core.prompt_sha256(curly_left) == lazy_core.prompt_sha256(base_left), (
        f"left-single-curly-quote must hash equal to apostrophe form (F2b leg 5)"
    )
    # Double curly quotes U+201C (left) and U+201D (right)
    base_double  = '"run the cycle step"'
    curly_double = "“run the cycle step”"
    assert lazy_core.prompt_sha256(curly_double) == lazy_core.prompt_sha256(base_double), (
        f"double-curly-quote pair must hash equal to straight-double-quote form (F2b leg 5)"
    )


def test_f2b_nbsp_hashes_equal_to_space():
    """F2b: non-breaking space U+00A0 and narrow NBSP U+202F must fold to regular
    space so a copy that picks up NBSP (common in web/docx copy-paste) still
    hashes equal.

    RED: normalize_prompt_for_hash has no NBSP-folding leg yet.
    """
    _guard()
    base = "Run step 1: implement the feature."
    nbsp      = "Run step 1: implement the feature."  # non-breaking space U+00A0
    narrow_nb = "Run step 1: implement the feature."  # narrow NBSP U+202F
    assert lazy_core.prompt_sha256(nbsp) == lazy_core.prompt_sha256(base), (
        f"NBSP (U+00A0) must fold to space (F2b leg 5); hashes differed"
    )
    assert lazy_core.prompt_sha256(narrow_nb) == lazy_core.prompt_sha256(base), (
        f"narrow NBSP (U+202F) must fold to space (F2b leg 5); hashes differed"
    )


def test_f2b_genuine_word_change_still_differs():
    """F2b guard: the dash/quote/NBSP folding must NOT over-collapse — a genuine
    word change must still produce a different sha256 so the deny fires for real edits.

    RED: if fold is incorrectly broad, this test would fail (hashes equal when they
    should differ).  Currently RED because the other F2b tests are RED; once leg 5
    is added this test must pass WITH them.
    """
    _guard()
    # Baseline requires F2b leg 5 to be present (will fail if not).
    base = "Run the next step - implementation phase."
    em   = "Run the next step — implementation phase."
    assert lazy_core.prompt_sha256(em) == lazy_core.prompt_sha256(base), (
        "pre-condition: F2b must be in place (em-dash == hyphen) before word-change guard"
    )
    # Now mutate a real WORD — the fold must not have collapsed this.
    mutated = "Run the PREVIOUS step - implementation phase."
    assert lazy_core.prompt_sha256(mutated) != lazy_core.prompt_sha256(base), (
        "a genuine word change must still produce a different sha256 (F2b must not over-fold)"
    )


def test_single_slot_dispatch_templates():
    """Every @requires token appears EXACTLY ONCE as a {token} slot in each
    dispatch template body (WU-7.3a transcription-surface reduction)."""
    _guard()
    templates = sorted(_REAL_TEMPLATE_DIR.glob("dispatch-*.md"))
    assert templates, f"no dispatch templates found under {_REAL_TEMPLATE_DIR}"
    for tpl in templates:
        text = tpl.read_text(encoding="utf-8")
        first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
        m = re.match(r"^<!--\s*@requires\s+([a-z0-9_,]+)\s*-->", first_line)
        assert m, f"{tpl.name}: line 1 must declare @requires"
        reqs = [k.strip() for k in m.group(1).split(",") if k.strip()]
        for tok in reqs:
            count = len(re.findall(r"\{" + re.escape(tok) + r"\}", text))
            assert count == 1, (
                f"{tpl.name}: @requires token {tok!r} must appear EXACTLY ONCE "
                f"as a {{{tok}}} slot, found {count}"
            )


def test_emit_dispatch_cycle_header_marker_gated():
    """emit_dispatch_prompt attaches cycle_header ONLY when a marker is present;
    the header matches `### {Step} — {summary} [meta {m}]` (bare meta COUNT, no
    denominator — meta_cycles is uncapped, operator decision 2026-06-14) with the
    class-map step name, item_name summary, and m = meta+1."""
    _guard()
    requires_keys = _read_recovery_requires_keys()
    assert requires_keys is not None, "dispatch-recovery.md missing"
    ctx = {k: f"v-{k}" for k in requires_keys}
    ctx["item_name"] = "My Feature"
    ctx["item_id"] = "feat-z"

    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # --- No marker → no cycle_header key at all (marker-gated). ---
            r_nomarker = lazy_core.emit_dispatch_prompt(
                "recovery", ctx, pipeline="feature",
            )
            assert r_nomarker["ok"], r_nomarker
            assert "cycle_header" not in r_nomarker, (
                "cycle_header must be ABSENT without a marker (baseline-safety)"
            )

            # --- Marker present (meta=3, max=5) → header present, exact format. ---
            import time as _time
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            # Advance the meta counter to 3 via direct marker edit.
            marker = lazy_core.read_run_marker()
            marker["meta_cycles"] = 3
            (Path(td) / "lazy-run-marker.json").write_text(
                json.dumps(marker, indent=2) + "\n", encoding="utf-8"
            )
            r = lazy_core.emit_dispatch_prompt("recovery", ctx, pipeline="feature")
            assert r["ok"], r
            assert "cycle_header" in r, "cycle_header must be present with a marker"
            # Step for 'recovery' is 'Recover'; m = meta(3)+1 = 4; NO cap (uncapped).
            assert r["cycle_header"] == "### Recover — My Feature [meta 4]", (
                f"unexpected cycle_header: {r['cycle_header']!r}"
            )

            # Step-name map covers investigation → 'Investigate'.
            ri = lazy_core.emit_dispatch_prompt(
                "investigation",
                {k: f"v-{k}" for k in _dispatch_requires("investigation")}
                | {"item_name": "Bug Q", "item_id": "bug-q"},
                pipeline="feature",
            )
            assert ri["ok"], ri
            assert ri["cycle_header"].startswith("### Investigate — Bug Q [meta 4]"), ri["cycle_header"]
        finally:
            _clear_state_dir()


def test_record_decision_cli_and_apply_resolution_binds_end_to_end():
    """mechanize-prose-only-orchestrator-contracts (c) / D3-A end-to-end via
    subprocess: `--emit-dispatch apply-resolution` with a sentinel_path and
    NO prior --record-decision refuses (exit 1, dispatch_prompt_refused
    names --record-decision); after `--record-decision --sentinel ...
    --chosen ... --summary ...`, the SAME emit succeeds and the emitted
    dispatch_prompt embeds the chosen option + summary VERBATIM (Validation
    Criteria: 'Answer reaches worker')."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_dir = td_path / "repo"
        (repo_dir / "docs" / "features" / "feat-1").mkdir(parents=True)
        (repo_dir / "docs" / "features" / "queue.json").write_text(json.dumps({
            "queue": [{"id": "feat-1", "name": "Test Feature", "tier": 1}]
        }), encoding="utf-8")
        sentinel = repo_dir / "docs" / "features" / "feat-1" / "NEEDS_INPUT.md"
        sentinel.write_text("# needs input\n", encoding="utf-8")

        state_dir = td_path / "state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        emit_args = [
            "--emit-dispatch", "apply-resolution",
            "--repo-root", str(repo_dir),
            "--context", "item_name=Test Feature",
            "--context", "spec_path=" + str(repo_dir / "docs" / "features" / "feat-1"),
            "--context", "sentinel_path=" + str(sentinel),
            "--context", "resolution_kind=needs-input",
            "--context", "item_id=feat-1",
            "--context", "cwd=" + str(repo_dir),
        ]

        # 1. No recorded decision yet -> refuses naming --record-decision.
        r0 = run(emit_args)
        assert r0.returncode == 1, r0.stdout
        out0 = json.loads(r0.stdout)
        assert out0.get("dispatch_prompt") is None
        assert "--record-decision" in out0.get("dispatch_prompt_refused", ""), out0

        # 2. Record the decision.
        r_rec = run([
            "--record-decision",
            "--sentinel", str(sentinel),
            "--chosen", "Option A — use the recommended default",
            "--summary", "operator picked the recommended default at the prompt",
        ])
        assert r_rec.returncode == 0, r_rec.stdout + r_rec.stderr
        rec_out = json.loads(r_rec.stdout)
        assert rec_out["chosen_path"] == "Option A — use the recommended default"

        # 3. The SAME emit now succeeds, embedding the recorded answer
        # verbatim — the orchestrator never had to type chosen_path/
        # resolution_summary as --context args at all.
        r1 = run(emit_args)
        assert r1.returncode == 0, r1.stdout + r1.stderr
        out1 = json.loads(r1.stdout)
        prompt = out1.get("dispatch_prompt") or ""
        assert "Option A — use the recommended default" in prompt, prompt
        assert "operator picked the recommended default at the prompt" in prompt, prompt


def test_emit_dispatch_always_emits_json_on_error():
    """ISSUE 3: --emit-dispatch NEVER emits non-JSON, even on a bad context payload.

    A --context-file pointing at malformed JSON must yield a STRUCTURED JSON error
    object (dispatch_prompt: null, error_kind present), exit 1 — not a bare
    traceback or empty stdout.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        cf = Path(td) / "bad.json"
        cf.write_text("{not valid json,,,}", encoding="utf-8")
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(Path(td) / "state")
        r = subprocess.run(
            [sys.executable, str(lazy_state), "--emit-dispatch", "recovery",
             "--context-file", str(cf)],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 1, f"malformed context must exit 1, got {r.returncode}"
        data = json.loads(r.stdout)  # MUST be valid JSON
        assert data["dispatch_prompt"] is None
        assert data.get("error_kind") == "ValueError", (
            f"structured error must carry error_kind, got {data}"
        )
        assert "not valid JSON" in data["dispatch_prompt_refused"]


def test_f1a_default_deny_reason_names_customization_path():
    """F1a: the default deny reason ADDS the sanctioned-customization wording
    (`--context KEY=VALUE`, `--emit-dispatch <class>`, "dispatch verbatim",
    "never append") while PRESERVING every preexisting recipe substring that the
    Phase 6/7 byte-match tests assert."""
    _guard()
    lazy_guard = _f1_guard_module()
    reason = lazy_guard._default_deny_reason()

    # Preexisting substrings (byte-matched by test_hooks / WSL leg) MUST survive.
    for needle in (
        "re-run the Step 1a probe",
        "--emit-prompt",
        "--emit-dispatch hardening",
    ):
        assert needle in reason, (
            f"F1a must NOT drop the preexisting recipe substring {needle!r}; "
            f"reason={reason!r}"
        )

    # New F1a wording naming the sanctioned customization path.
    assert "--context KEY=VALUE" in reason, (
        f"F1a deny reason must name `--context KEY=VALUE`; reason={reason!r}"
    )
    assert "--emit-dispatch <class>" in reason, (
        f"F1a deny reason must name `--emit-dispatch <class>`; reason={reason!r}"
    )
    assert "verbatim" in reason, (
        f"F1a deny reason must state the dispatch-verbatim rule; reason={reason!r}"
    )
    # The explicit prohibition against editing the emitted prompt.
    assert "never append" in reason, (
        f"F1a deny reason must say 'never append to or edit the emitted prompt'; "
        f"reason={reason!r}"
    )


def test_f1a_hardening_cap_reason_unchanged():
    """F1a must NOT touch the hardening depth-1 cap reason: it still says halt +
    PushNotification and must NOT recommend `--emit-dispatch hardening`."""
    _guard()
    lazy_guard = _f1_guard_module()
    reason = lazy_guard._hardening_cap_deny_reason()
    assert "halt" in reason, reason
    assert "PushNotification" in reason, reason
    assert "--emit-dispatch hardening" not in reason, (
        "the hardening cap reason must never recommend recursive hardening"
    )


def test_f1b_pure_suffix_cycle_prompt_auto_readmits():
    """F1b: a dispatch whose normalized prompt is a registered cycle prompt PLUS a
    trailing suffix is ALLOWED, the entry's nonce is consumed, and a deny-ledger
    line with `auto_readmit: true` is written (auditable, never silent)."""
    _guard()
    lazy_guard = _f1_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            base = "Run the next cycle step exactly as specified."
            entry = lazy_core.register_emission(base, cls="cycle", item_id="feat-x")
            nonce = entry["nonce"]

            dispatched = base + "\n\nORCHESTRATOR NOTE: keep going, do not stop."
            out = lazy_guard.guard(_f1_hook_input(dispatched, "tu-suffix"))
            assert out is not None, "auto-readmit must produce allow JSON (not None)"
            payload = json.loads(out)
            decision = payload["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", (
                f"a pure-suffix superset of a fresh cycle entry must auto-readmit "
                f"(allow); got {decision!r}; reason="
                f"{payload['hookSpecificOutput'].get('permissionDecisionReason')!r}"
            )

            # The nonce must now be consumed (lookup_emission returns None).
            assert lazy_core.lookup_emission(base) is None, (
                "auto-readmit must consume the matched entry's nonce"
            )
            registry = json.loads(
                (state_dir / "lazy-prompt-registry.json").read_text(encoding="utf-8")
            )
            match = [e for e in registry["entries"] if e.get("nonce") == nonce]
            assert match and match[0].get("consumed") is True, (
                "the auto-readmitted entry must be marked consumed"
            )

            # An auto_readmit ledger event must be present (same JSONL stream).
            ledger = state_dir / "lazy-deny-ledger.jsonl"
            assert ledger.exists(), "auto-readmit must write an auditable ledger event"
            events = [
                json.loads(ln)
                for ln in ledger.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            auto = [e for e in events if e.get("auto_readmit") is True]
            assert len(auto) == 1, (
                f"exactly one auto_readmit event expected; got {len(auto)}: {events!r}"
            )
            assert auto[0].get("tool_use_id") == "tu-suffix", auto[0]
        finally:
            _clear_state_dir()


def test_f1b_in_body_edit_still_denies():
    """F1b exclusion: an in-body edit (a word changed mid-prompt, NOT a pure
    trailing suffix) is NOT a suffix superset → it still DENIES with the default
    corrective reason, and writes a NORMAL (non-auto_readmit) deny ledger line."""
    _guard()
    lazy_guard = _f1_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        # D2 (stale-marker-arms-validate-deny-on-unrelated-dispatches, 2026-06-19):
        # the GENERIC default-deny is no-debt under an UNBOUND marker (WU-3). This
        # in-body-edit deny lands on that generic path, so bind the marker + pass
        # the owner session to keep it a genuine validate-deny that DOES ledger.
        _f1b_owner = "11111111-2222-3333-4444-555555555555"
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(), session_id=_f1b_owner,
            )
            base = "Run the next cycle step exactly as specified now."
            lazy_core.register_emission(base, cls="cycle", item_id="feat-x")

            edited = base.replace("exactly", "approximately")
            out = lazy_guard.guard(_f1_hook_input(edited, "tu-edit", session_id=_f1b_owner))
            assert out is not None
            payload = json.loads(out)
            assert payload["hookSpecificOutput"]["permissionDecision"] == "deny", (
                "an in-body edit is not a pure suffix → it must still DENY"
            )
            reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
            assert "--context KEY=VALUE" in reason and "verbatim" in reason, (
                "the in-body-edit deny must use the F1a corrective reason"
            )
            # The matched entry must NOT have been consumed by the deny.
            assert lazy_core.lookup_emission(base) is not None, (
                "a deny must never consume the registry entry"
            )
            ledger = state_dir / "lazy-deny-ledger.jsonl"
            events = [
                json.loads(ln)
                for ln in ledger.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            assert events and all(not e.get("auto_readmit") for e in events), (
                "an in-body-edit deny must NOT write an auto_readmit event"
            )
        finally:
            _clear_state_dir()


def test_f1b_auto_readmit_error_falls_through_to_deny():
    """F1b fail-open: if the auto-readmit path raises internally (here:
    consume_nonce poisoned), the guard must fall through to the NORMAL deny — never
    a spurious allow."""
    _guard()
    lazy_guard = _f1_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            base = "Run the next cycle step exactly as specified for failopen."
            lazy_core.register_emission(base, cls="cycle")
            dispatched = base + "\n\nORCHESTRATOR NOTE: appended."

            original = lazy_core.dispatch.consume_nonce
            def _boom(*a, **k):
                raise RuntimeError("consume exploded")
            lazy_core.dispatch.consume_nonce = _boom  # type: ignore[assignment]
            try:
                out = lazy_guard.guard(_f1_hook_input(dispatched, "tu-boom"))
            finally:
                lazy_core.dispatch.consume_nonce = original  # type: ignore[assignment]

            assert out is not None
            payload = json.loads(out)
            assert payload["hookSpecificOutput"]["permissionDecision"] == "deny", (
                "an auto-readmit-path error must fall through to deny, never a "
                "spurious allow"
            )
        finally:
            _clear_state_dir()


def test_f1b_register_emission_stores_normalized_prompt_text():
    """F1b registry-text field: register_emission stores the
    normalize_prompt_for_hash-normalized prompt text on each entry (the field the
    auto-readmit prefix match keys on)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # CRLF + trailing whitespace → must be normalized before storage.
            raw = "Line one.  \r\nLine two.\r\n"
            entry = lazy_core.register_emission(raw, cls="cycle")
            expected = lazy_core.normalize_prompt_for_hash(raw)
            assert entry.get("prompt_norm") == expected, (
                f"register_emission must store the normalized prompt text; "
                f"got {entry.get('prompt_norm')!r}, expected {expected!r}"
            )
        finally:
            _clear_state_dir()


# ---------------------------------------------------------------------------
# Test 5: registry register→lookup→consume round-trip
# ---------------------------------------------------------------------------

def test_registry_register_lookup_consume():
    """register_emission → lookup_emission returns the entry with correct
    prompt_sha256; consume_nonce → True; subsequent lookup → None (consumed);
    second consume_nonce → False (already consumed).

    RED state: register_emission / lookup_emission / consume_nonce missing.
    """
    _guard()
    import time as _time
    prompt = "dispatch Feature X via /execute-plan"
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            entry = lazy_core.register_emission(prompt, cls="cycle", now=now)
            assert entry is not None, "register_emission must return the entry dict"
            expected_sha = lazy_core.prompt_sha256(prompt)
            assert entry["prompt_sha256"] == expected_sha, (
                f"prompt_sha256 mismatch: expected {expected_sha!r}, got {entry['prompt_sha256']!r}"
            )
            assert entry["class"] == "cycle", f"class mismatch: {entry}"
            assert entry["consumed"] is False, f"entry must start unconsumed: {entry}"

            # lookup returns the entry
            found = lazy_core.lookup_emission(prompt, now=now)
            assert found is not None, "lookup_emission must return entry after registration"
            assert found["prompt_sha256"] == expected_sha, f"lookup sha mismatch: {found}"

            # consume_nonce: first call True, then lookup returns None
            nonce = entry["nonce"]
            consumed_ok = lazy_core.dispatch.consume_nonce(nonce)
            assert consumed_ok is True, (
                f"consume_nonce must return True on first consumption, got {consumed_ok!r}"
            )
            after_consume = lazy_core.lookup_emission(prompt, now=now)
            assert after_consume is None, (
                "lookup_emission must return None after nonce consumed"
            )

            # second consume → False
            second = lazy_core.dispatch.consume_nonce(nonce)
            assert second is False, (
                f"consume_nonce must return False when already consumed, got {second!r}"
            )
        finally:
            _clear_state_dir()


# ---------------------------------------------------------------------------
# Test 6: registry TTL — stale entry not dispatchable; fresh entry is
# ---------------------------------------------------------------------------

def test_registry_ttl():
    """Entry registered at 'now'; lookup at now+1801 → None (stale, TTL=1800s);
    lookup at now+100 → hit.

    RED state: REGISTRY_ENTRY_TTL_SECONDS / TTL logic not implemented.
    """
    _guard()
    import time as _time
    prompt = "ttl-test dispatch"
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            lazy_core.register_emission(prompt, cls="cycle", now=now)

            # Beyond TTL → None
            stale_result = lazy_core.lookup_emission(prompt, now=now + 1801)
            assert stale_result is None, (
                f"lookup_emission must return None when entry is beyond TTL "
                f"(now+1801 > TTL={lazy_core.REGISTRY_ENTRY_TTL_SECONDS}s), "
                f"got {stale_result!r}"
            )

            # Within TTL → hit
            fresh_result = lazy_core.lookup_emission(prompt, now=now + 100)
            assert fresh_result is not None, (
                "lookup_emission must return entry when within TTL (now+100 < 1800s)"
            )
        finally:
            _clear_state_dir()


# ---------------------------------------------------------------------------
# Test 8: CRLF/LF normalization — same hash across line-ending variants
# ---------------------------------------------------------------------------

def test_crlf_lf_normalization():
    """prompt_sha256('a\\r\\nb') == prompt_sha256('a\\nb') — CRLF is normalized
    to LF before hashing so Windows round-trips cannot defeat the registry match.

    Also: register with CRLF prompt then lookup with LF variant → hit.

    RED state: normalize_prompt_for_hash / CRLF normalization not implemented.
    """
    _guard()
    import time as _time

    # Hash equality
    crlf_hash = lazy_core.prompt_sha256("a\r\nb")
    lf_hash = lazy_core.prompt_sha256("a\nb")
    assert crlf_hash == lf_hash, (
        f"CRLF and LF prompts must produce the same sha256 "
        f"(crlf={crlf_hash!r} vs lf={lf_hash!r})"
    )

    # Also test lone CR → LF
    cr_hash = lazy_core.prompt_sha256("a\rb")
    lf_hash2 = lazy_core.prompt_sha256("a\nb")
    assert cr_hash == lf_hash2, (
        f"lone CR and LF prompts must produce the same sha256 "
        f"(cr={cr_hash!r} vs lf={lf_hash2!r})"
    )

    # Registry cross-variant lookup
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            crlf_prompt = "dispatch with windows line endings\r\nSecond line"
            lf_prompt = "dispatch with windows line endings\nSecond line"
            lazy_core.register_emission(crlf_prompt, cls="cycle", now=now)

            # Lookup with the LF variant must hit
            found = lazy_core.lookup_emission(lf_prompt, now=now)
            assert found is not None, (
                "lookup with LF variant must find the CRLF-registered entry "
                "(normalization makes them the same hash)"
            )
        finally:
            _clear_state_dir()


def test_advance_run_counters_census_regression_does_not_strand():
    """Phase 2 (byref-dispatch-undercounts-forward-cycles): a ONE-TIME downward
    census step (ring-cap eviction of consumed entries) must NOT permanently
    strand advance_run_counters' watermark gate.

    Mechanism of the strand (Contributor B): consumed_emission_count() is a LIVE
    census over the ring-capped registry. When cumulative emissions cross
    _REGISTRY_RING_CAP (64), the oldest CONSUMED entries are evicted, so the live
    consumed-count DROPS below a previously-persisted last_advance_consume_count.
    Pre-clamp, the gate (current_consume <= prior_consume → no-op) then no-ops
    FOREVER for any future consume rise that does not first climb back PAST the
    now-too-high watermark — a permanent freeze.

    Post-clamp: a census that has dropped BELOW the persisted watermark re-arms
    (the stale watermark is treated as invalid), so a subsequent legitimate
    consume rise still advances. The ISSUE-5 bare-re-probe no-op (no consume
    between two probes ⇒ no advance) must stay intact.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=100, now=now,
            )
            state = {"sub_skill": "/execute-plan", "feature_id": "feat-x"}

            # Drive the registry well past the ring cap with CONSUMED entries so the
            # live census plateaus at the cap and then any further consumed-entry
            # eviction drops it. After 80 consumed registrations the registry holds
            # 64 entries, all consumed → census == 64 (the plateau).
            for i in range(80):
                entry = lazy_core.register_emission(
                    f"dispatch prompt {i}", "cycle", now=now + i
                )
                lazy_core.dispatch.consume_nonce(entry["nonce"])
            census_plateau = lazy_core.consumed_emission_count()
            assert census_plateau == lazy_core._REGISTRY_RING_CAP, (
                f"after 80 consumed registrations the census plateaus at the ring "
                f"cap ({lazy_core._REGISTRY_RING_CAP}), got {census_plateau!r}"
            )

            # Advance once — this persists last_advance_consume_count == 64.
            m1 = lazy_core.advance_run_counters(state)
            assert m1 is not None and m1["forward_cycles"] == 1, (
                f"first advance over the plateau must set forward_cycles=1, got {m1!r}"
            )
            assert m1["last_advance_consume_count"] == census_plateau, (
                f"watermark must persist at the plateau census, got "
                f"{m1.get('last_advance_consume_count')!r}"
            )

            # Now force the census DOWN below the persisted watermark by evicting
            # consumed entries: register UNCONSUMED entries past the cap so the
            # oldest (consumed) entries are evicted, dropping the consumed-count.
            for i in range(40):
                lazy_core.register_emission(
                    f"unconsumed filler {i}", "cycle", now=now + 1000 + i
                )
            census_dropped = lazy_core.consumed_emission_count()
            assert census_dropped < m1["last_advance_consume_count"], (
                f"eviction of consumed entries must drop the census BELOW the "
                f"persisted watermark ({m1['last_advance_consume_count']}), got "
                f"{census_dropped!r}"
            )

            # THE STRAND TEST: a fresh legitimate dispatch consume happens. Pre-clamp
            # this consume (which only nudges the census up by ~1, still far below the
            # stranded watermark of 64) would NOT advance — a permanent freeze.
            # Post-clamp the watermark re-arms on the census drop, so this advances.
            entry = lazy_core.register_emission("post-eviction dispatch", "cycle")
            lazy_core.dispatch.consume_nonce(entry["nonce"])
            m2 = lazy_core.advance_run_counters(state)
            assert m2["forward_cycles"] == 2, (
                f"a census drop below the watermark must NOT permanently strand the "
                f"gate — a subsequent legitimate consume must still advance "
                f"forward_cycles (expected 2), got {m2['forward_cycles']!r}. "
                f"This is the permanent-strand bug the Phase-2 clamp fixes."
            )

            # ISSUE-5 inflation invariant intact: a bare re-probe with NO new consume
            # between two probes must NOT advance.
            for _ in range(3):
                mN = lazy_core.advance_run_counters(state)
                assert mN["forward_cycles"] == 2, (
                    f"bare re-probe with no new consume must NOT advance (ISSUE-5 "
                    f"inflation invariant), got {mN['forward_cycles']!r}"
                )
        finally:
            _clear_state_dir()


# ---------------------------------------------------------------------------
# Test 11: subprocess MVB — lazy-state.py --repeat-count --probe --emit-prompt
#          with marker present writes a registry entry with matching sha256
# ---------------------------------------------------------------------------

def test_subprocess_emit_prompt_with_marker_writes_registry():
    """Minimum Verifiable Behavior: a real subprocess invocation of
    lazy-state.py --repeat-count --probe --emit-prompt --repo-root <fixture>
    with LAZY_STATE_DIR set and a marker written writes a registry entry whose
    prompt_sha256 == lazy_core.prompt_sha256(cycle_prompt from the probe stdout),
    and entry class == 'cycle'.

    The SAME invocation WITHOUT a marker writes NO registry file.

    This test crosses the script↔state-dir I/O boundary and is the ground-truth
    literal-hash comparison required by the Phase 1 Testing Strategy.

    RED state: --emit-prompt integration in lazy-state.py not yet wired; the
    symbols used here (write_run_marker, register_emission, prompt_sha256) will
    raise AttributeError immediately after _guard() until Phase 1 lands.
    """
    _guard()
    # Assert early on the key symbols so the failure message names the missing
    # symbol rather than producing an opaque TypeError later.
    assert hasattr(lazy_core, "write_run_marker"), (
        "lazy_core.write_run_marker missing — Phase 1 not yet implemented"
    )
    assert hasattr(lazy_core, "prompt_sha256"), (
        "lazy_core.prompt_sha256 missing — Phase 1 not yet implemented"
    )

    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    # Build the minimal "mid-implementation" fixture (yields sub_skill=execute-plan
    # + non-null cycle_prompt on --emit-prompt).  The fixture structure mirrors
    # _build_fixture("mid-implementation") from lazy-state.py's own smoke harness.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Fixture repo: docs/features/queue.json + feat-c/ with SPEC/RESEARCH/PHASES/plans
        features = td_path / "fixture-repo" / "docs" / "features"
        features.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
            ]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        fdir = features / "feat-c"
        fdir.mkdir()
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
        (fdir / "plans").mkdir()
        (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
        fixture_repo = td_path / "fixture-repo"

        state_dir = td_path / "lazy-state-dir"
        state_dir.mkdir()

        # --- Run WITHOUT a marker: no registry file must be written ---
        env_no_marker = dict(_os_env.environ)
        env_no_marker["LAZY_STATE_DIR"] = str(state_dir)
        result_no_marker = subprocess.run(
            [
                sys.executable, str(lazy_state_script),
                "--repeat-count", "--probe", "--emit-prompt",
                "--repo-root", str(fixture_repo),
            ],
            capture_output=True,
            text=True,
            env=env_no_marker,
        )
        registry_file = state_dir / "lazy-prompt-registry.json"
        assert not registry_file.exists(), (
            "lazy-prompt-registry.json must NOT be written when no marker is present; "
            f"script stdout: {result_no_marker.stdout[:400]!r}"
        )

        # --- Run WITH a marker: registry file must appear with correct sha ---
        import time as _time
        _set_state_dir(state_dir)
        try:
            now = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=now,
            )
        finally:
            _clear_state_dir()

        env_with_marker = dict(_os_env.environ)
        env_with_marker["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [
                sys.executable, str(lazy_state_script),
                "--repeat-count", "--probe", "--emit-prompt",
                "--repo-root", str(fixture_repo),
            ],
            capture_output=True,
            text=True,
            env=env_with_marker,
        )
        assert result.returncode == 0, (
            f"lazy-state.py exited {result.returncode}; "
            f"stderr: {result.stderr[:400]!r}; "
            f"stdout: {result.stdout[:400]!r}"
        )
        try:
            state_json = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"lazy-state.py stdout is not valid JSON: {exc}\n"
                f"stdout: {result.stdout[:400]!r}"
            ) from exc

        cycle_prompt = state_json.get("cycle_prompt")
        assert cycle_prompt is not None and cycle_prompt != "", (
            f"cycle_prompt must be non-null for a DISPATCHABLE state; "
            f"state: sub_skill={state_json.get('sub_skill')!r}, "
            f"terminal_reason={state_json.get('terminal_reason')!r}"
        )

        # Registry must exist and hold exactly one entry matching the cycle_prompt
        assert registry_file.exists(), (
            "lazy-prompt-registry.json must be written when marker is present "
            "and --emit-prompt is passed"
        )
        registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
        entries = registry_data.get("entries", [])
        expected_sha = lazy_core.prompt_sha256(cycle_prompt)
        matching = [e for e in entries if e["prompt_sha256"] == expected_sha]
        assert len(matching) == 1, (
            f"expected exactly 1 registry entry whose prompt_sha256 == "
            f"sha256(cycle_prompt); found {len(matching)} matching entries. "
            f"expected sha={expected_sha!r}; "
            f"entries={[e['prompt_sha256'] for e in entries]!r}"
        )
        assert matching[0]["class"] == "cycle", (
            f"registry entry class must be 'cycle', got {matching[0]['class']!r}"
        )


def test_subprocess_emit_prompt_withholds_when_merged_head_is_p0_bug():
    """dispatch-probe-and-inject-bypass-merged-head (end-to-end): a real
    subprocess `lazy-state.py --repeat-count --probe --emit-prompt` with a
    feature-run marker but a P0 bug at the merged head must WITHHOLD the feature
    route: route_overridden_by == "merged-head-diverged", merged_head names the
    bug, cycle_prompt is null, and NO cycle registry entry is written (the
    orchestrator must re-probe --next-merged and type-dispatch to the bug).

    RED state (pre-fix): the probe emitted the feat-c cycle_prompt and registered
    it, silently skipping the P0 bug — the live 2026-07-17 friction.
    """
    _guard()
    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Feature fixture (feat-c tier 1) — dispatchable on its own.
        features = td_path / "fixture-repo" / "docs" / "features"
        features.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
            ]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        fdir = features / "feat-c"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n",
            encoding="utf-8")
        (fdir / "plans").mkdir()
        (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
        fixture_repo = td_path / "fixture-repo"

        # P0 bug at the merged head (rank 0 outranks feature tier 1).
        bug_dir = fixture_repo / "docs" / "bugs" / "bug-z"
        (bug_dir / "plans").mkdir(parents=True)
        (fixture_repo / "docs" / "bugs" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-z", "name": "Bug Z", "spec_dir": "bug-z", "severity": "P0"}
            ]
        }), encoding="utf-8")
        (bug_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n", encoding="utf-8")
        (bug_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Fix the thing\n- [ ] Tests\n", encoding="utf-8")
        (bug_dir / "plans" / "all-phases-z.md").write_text("# Plan\n", encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"
        state_dir.mkdir()

        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time(),
            )
        finally:
            _clear_state_dir()

        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [sys.executable, str(lazy_state_script),
             "--repeat-count", "--probe", "--emit-prompt",
             "--repo-root", str(fixture_repo)],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, (
            f"lazy-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
        state_json = json.loads(result.stdout)

        assert state_json.get("route_overridden_by") == "merged-head-diverged", (
            f"feature probe must WITHHOLD over a P0-bug merged head; "
            f"route_overridden_by={state_json.get('route_overridden_by')!r}, "
            f"feature_id={state_json.get('feature_id')!r}")
        assert state_json.get("merged_head") == {"item_id": "bug-z", "type": "bug"}, (
            f"merged_head must name the P0 bug; got {state_json.get('merged_head')!r}")
        assert state_json.get("cycle_prompt") is None, (
            "cycle_prompt must be null on a withheld route")
        # No cycle registry entry written (the withheld route registers nothing).
        registry_file = state_dir / "lazy-prompt-registry.json"
        if registry_file.exists():
            entries = json.loads(registry_file.read_text(encoding="utf-8")).get("entries", [])
            assert not [e for e in entries if e.get("class") == "cycle"], (
                "a withheld route must NOT register a cycle emission")


def test_subprocess_emit_prompt_oracle_excludes_nondispatchable_bug_head_no_withhold():
    """merged-head-actionability-oracle Phase 2 (feature-side, real scoped probe):
    a NON-DISPATCHABLE bug at the merged head (a BLOCKED bug — a category the old
    file-predicate never excluded on the feature-side cross-pipeline path) is now
    EXCLUDED by the oracle's REAL cross-pipeline scoped `bug-state.compute_state`,
    so the feature probe does NOT withhold and dispatches the workable feature.
    Pre-oracle this withheld behind the undriveable bug head (the stall class this
    feature ends). Byte-identity for a DISPATCHABLE P0 bug is covered by
    test_subprocess_emit_prompt_withholds_when_merged_head_is_p0_bug (still green)."""
    _guard()
    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        features = td_path / "fixture-repo" / "docs" / "features"
        features.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [{"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        fdir = features / "feat-c"
        (fdir / "plans").mkdir(parents=True)
        (fdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n", encoding="utf-8")
        (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
        fixture_repo = td_path / "fixture-repo"

        # P0 bug at the merged head, but BLOCKED → scoped bug probe is
        # non-dispatchable → the oracle excludes it (no withhold).
        bug_dir = fixture_repo / "docs" / "bugs" / "bug-blk"
        bug_dir.mkdir(parents=True)
        (fixture_repo / "docs" / "bugs" / "queue.json").write_text(json.dumps({
            "queue": [{"id": "bug-blk", "name": "Bug Blocked", "spec_dir": "bug-blk", "severity": "P0"}]
        }), encoding="utf-8")
        (bug_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n", encoding="utf-8")
        (bug_dir / "BLOCKED.md").write_text(
            "---\nphase: External gate\nblocker_kind: external-gate\n---\nAwaiting.\n",
            encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"
        state_dir.mkdir()
        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time())
        finally:
            _clear_state_dir()

        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [sys.executable, str(lazy_state_script),
             "--repeat-count", "--probe", "--emit-prompt", "--repo-root", str(fixture_repo)],
            capture_output=True, text=True, env=env)
        assert result.returncode == 0, (
            f"lazy-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
        state_json = json.loads(result.stdout)
        # NO withhold — the blocked bug is excluded; the feature is dispatched.
        assert state_json.get("route_overridden_by") is None, (
            f"blocked bug head must NOT withhold; got "
            f"route_overridden_by={state_json.get('route_overridden_by')!r}")
        assert state_json.get("feature_id") == "feat-c", state_json.get("feature_id")
        assert state_json.get("cycle_prompt"), "feature cycle_prompt must be emitted"


def test_subprocess_bug_emit_prompt_oracle_excludes_nondispatchable_feature_head_no_withhold():
    """merged-head-actionability-oracle Phase 2 (bug-side coupled mirror, real
    scoped probe): a higher-priority BLOCKED FEATURE at the merged head is EXCLUDED
    by the oracle's real cross-pipeline scoped `lazy-state.compute_state`, so the
    bug probe does NOT withhold and dispatches the workable bug."""
    _guard()
    bug_state_script = _SCRIPTS_DIR / "bug-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = td_path / "fixture-repo"
        # Workable bug (current, P2).
        bugs = fixture_repo / "docs" / "bugs"
        bug_dir = bugs / "bug-w"
        (bug_dir / "plans").mkdir(parents=True)
        (bugs / "queue.json").write_text(json.dumps({
            "queue": [{"id": "bug-w", "name": "Bug W", "spec_dir": "bug-w", "severity": "P2"}]
        }), encoding="utf-8")
        (bug_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n", encoding="utf-8")
        (bug_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Fix\n- [ ] Tests\n", encoding="utf-8")
        (bug_dir / "plans" / "all-phases-w.md").write_text("# Plan\n", encoding="utf-8")

        # Higher-priority BLOCKED feature at the merged head (tier 0).
        features = fixture_repo / "docs" / "features"
        fdir = features / "feat-blk"
        fdir.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [{"id": "feat-blk", "name": "Feature Blocked", "spec_dir": "feat-blk", "tier": 0}]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (fdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (fdir / "BLOCKED.md").write_text(
            "---\nphase: External gate\nblocker_kind: external-gate\n---\nAwaiting.\n",
            encoding="utf-8")

        state_dir = td_path / "bug-state-dir"
        state_dir.mkdir()
        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="bug", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time())
        finally:
            _clear_state_dir()

        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [sys.executable, str(bug_state_script),
             "--repeat-count", "--probe", "--emit-prompt", "--repo-root", str(fixture_repo)],
            capture_output=True, text=True, env=env)
        assert result.returncode == 0, (
            f"bug-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
        state_json = json.loads(result.stdout)
        assert state_json.get("route_overridden_by") is None, (
            f"blocked feature head must NOT withhold on the bug side; got "
            f"route_overridden_by={state_json.get('route_overridden_by')!r}")
        assert state_json.get("feature_id") == "bug-w", state_json.get("feature_id")
        assert state_json.get("cycle_prompt"), "bug cycle_prompt must be emitted"


def test_subprocess_emit_prompt_lane_marker_skips_merged_head_withhold():
    """lazy-batch-parallel-run-harness-gaps gap 1: the SAME divergent-head fixture
    as above, but with a LANE marker (parent_run set), must NOT withhold — the
    merged-head divergence guard is exempt for a coordinator-authorized lane probe
    (claim_shardable owns lane arbitration). route_overridden_by must NOT be
    'merged-head-diverged'; the lane emits its own route normally."""
    _guard()
    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        features = td_path / "fixture-repo" / "docs" / "features"
        features.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
            ]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        fdir = features / "feat-c"
        fdir.mkdir()
        (fdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        (fdir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n",
            encoding="utf-8")
        (fdir / "plans").mkdir()
        (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
        fixture_repo = td_path / "fixture-repo"

        # Same P0 bug at the merged head that WOULD withhold in a serial run.
        bug_dir = fixture_repo / "docs" / "bugs" / "bug-z"
        (bug_dir / "plans").mkdir(parents=True)
        (fixture_repo / "docs" / "bugs" / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "bug-z", "name": "Bug Z", "spec_dir": "bug-z", "severity": "P0"}
            ]
        }), encoding="utf-8")
        (bug_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n", encoding="utf-8")
        (bug_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Fix the thing\n- [ ] Tests\n", encoding="utf-8")
        (bug_dir / "plans" / "all-phases-z.md").write_text("# Plan\n", encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"
        state_dir.mkdir()

        import time as _time
        _set_state_dir(state_dir)
        try:
            # LANE marker: parent_run stamped (the coordinator identity).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time(),
                parent_run={"repo_root": str(fixture_repo),
                            "started_at": "2026-07-18T03:38:27Z"},
            )
        finally:
            _clear_state_dir()

        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [sys.executable, str(lazy_state_script),
             "--repeat-count", "--probe", "--emit-prompt",
             "--repo-root", str(fixture_repo), "--feature-id", "feat-c"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, (
            f"lazy-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
        state_json = json.loads(result.stdout)
        assert state_json.get("route_overridden_by") != "merged-head-diverged", (
            f"a LANE probe (parent_run set) must NOT withhold on merged-head "
            f"divergence; got route_overridden_by="
            f"{state_json.get('route_overridden_by')!r}")


def _gap8_build_divergent_fixture(td_path):
    """Shared fixture for the gap-8 serial-tail lease exemption tests: a
    dispatchable feature `feat-c` (tier 1) with a P0 bug `bug-z` at the merged
    head that WOULD withhold a serial `--feature-id feat-c` probe. Returns the
    fixture repo path."""
    features = td_path / "fixture-repo" / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}
        ]
    }), encoding="utf-8")
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-c"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
    (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (fdir / "PHASES.md").write_text(
        "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n",
        encoding="utf-8")
    (fdir / "plans").mkdir()
    (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
    fixture_repo = td_path / "fixture-repo"
    bug_dir = fixture_repo / "docs" / "bugs" / "bug-z"
    (bug_dir / "plans").mkdir(parents=True)
    (fixture_repo / "docs" / "bugs" / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": "bug-z", "name": "Bug Z", "spec_dir": "bug-z", "severity": "P0"}
        ]
    }), encoding="utf-8")
    (bug_dir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n", encoding="utf-8")
    (bug_dir / "PHASES.md").write_text(
        "# Phases\n\n### Phase 1\n- [ ] Fix the thing\n- [ ] Tests\n", encoding="utf-8")
    (bug_dir / "plans" / "all-phases-z.md").write_text("# Plan\n", encoding="utf-8")
    return fixture_repo


def _gap8_run_emit_probe(lazy_state_script, fixture_repo, state_dir):
    """Run the serial-tail-shape `--emit-prompt --feature-id feat-c` probe (SERIAL
    parent marker, parent_run null) and return the parsed state JSON."""
    env = dict(_os_env.environ)
    env["LAZY_STATE_DIR"] = str(state_dir)
    result = subprocess.run(
        [sys.executable, str(lazy_state_script),
         "--repeat-count", "--probe", "--emit-prompt",
         "--repo-root", str(fixture_repo), "--feature-id", "feat-c"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, (
        f"lazy-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
    return json.loads(result.stdout)


def test_subprocess_emit_prompt_serial_tail_lease_held_skips_merged_head_withhold():
    """lazy-batch-parallel-run-harness-gaps round-2 gap 8: a SERIAL parent-marker
    (parent_run null) tail probe for `feat-c` whose OWN feature_id holds a LIVE
    coordinator lease in leases.json must NOT withhold on merged-head divergence —
    completing the merged, lease-held item is the coordinator's obligation. The
    round-1 lane exemption keys on parent_run (null here), so only the gap-8 own-
    lease exemption clears this. route_overridden_by must NOT be
    'merged-head-diverged'."""
    _guard()
    import lazy_coord  # type: ignore[import]
    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _gap8_build_divergent_fixture(td_path)
        state_dir = td_path / "lazy-state-dir"
        state_dir.mkdir()

        import time as _time
        _set_state_dir(state_dir)
        try:
            # SERIAL parent marker: parent_run null (the main-root tail marker).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time(),
            )
        finally:
            _clear_state_dir()

        # Live lease on the PROBED item, in the state dir's leases.json.
        lazy_coord.acquire_lease(
            state_dir / "leases.json", "feat-c", os.getpid(), "wt-00", 3600,
            now=_time.time(),
        )

        state_json = _gap8_run_emit_probe(lazy_state_script, fixture_repo, state_dir)
        assert state_json.get("route_overridden_by") != "merged-head-diverged", (
            f"a serial-tail probe whose feature_id holds a LIVE lease must NOT "
            f"withhold on merged-head divergence; got route_overridden_by="
            f"{state_json.get('route_overridden_by')!r}")


def test_subprocess_emit_prompt_serial_tail_no_lease_still_withholds():
    """lazy-batch-parallel-run-harness-gaps round-2 gap 8 (negative control /
    lease-gating proof): the SAME divergent fixture + SERIAL marker but with NO
    live lease on `feat-c` must STILL withhold (route_overridden_by ==
    'merged-head-diverged') — proving the exemption is gated on the probed item's
    OWN live lease, not merely on the --feature-id scoping."""
    _guard()
    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _gap8_build_divergent_fixture(td_path)
        state_dir = td_path / "lazy-state-dir"
        state_dir.mkdir()

        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time(),
            )
        finally:
            _clear_state_dir()

        # No lease written → the serial guard must run and withhold.
        state_json = _gap8_run_emit_probe(lazy_state_script, fixture_repo, state_dir)
        assert state_json.get("route_overridden_by") == "merged-head-diverged", (
            f"a serial-tail probe with NO live lease must WITHHOLD over a P0-bug "
            f"merged head; got route_overridden_by="
            f"{state_json.get('route_overridden_by')!r}")
        assert state_json.get("merged_head") == {"item_id": "bug-z", "type": "bug"}, (
            f"merged_head must name the P0 bug; got {state_json.get('merged_head')!r}")


# ---------------------------------------------------------------------------
# Test 13: --repeat-count-peek does NOT advance marker counters
#          + freshness-leg assertion for lookup_emission
# ---------------------------------------------------------------------------

def test_repeat_count_peek_does_not_advance_marker_counters():
    """--repeat-count-peek must NOT advance forward_cycles or meta_cycles in the
    run marker.  Additionally, an entry with emitted_at BEFORE the marker's
    started_at → lookup_emission returns None (freshness gate); a post-start
    entry is returned normally.

    Subprocess part mirrors the fixture pattern from
    test_subprocess_emit_prompt_with_marker_writes_registry.
    """
    _guard()
    import time as _time

    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    # --- Sub-test A: --repeat-count-peek does not advance marker counters ---
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Build the same mid-implementation fixture used in Test 11.
        features = td_path / "fixture-repo" / "docs" / "features"
        features.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-peek", "name": "Feature Peek", "spec_dir": "feat-peek", "tier": 1}
            ]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        fdir = features / "feat-peek"
        fdir.mkdir()
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
        (fdir / "plans").mkdir()
        (fdir / "plans" / "all-phases-peek.md").write_text("# Plan\n", encoding="utf-8")
        fixture_repo = td_path / "fixture-repo"

        state_dir = td_path / "peek-state-dir"
        state_dir.mkdir()

        # Write a marker (forward_cycles=0, meta_cycles=0) via lazy_core
        now = _time.time()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=now,
            )
        finally:
            _clear_state_dir()

        # Invoke the script with --repeat-count-peek (not --repeat-count)
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [
                sys.executable, str(lazy_state_script),
                "--repeat-count-peek", "--probe",
                "--repo-root", str(fixture_repo),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, (
            f"lazy-state.py --repeat-count-peek exited {result.returncode}; "
            f"stderr: {result.stderr[:400]!r}; stdout: {result.stdout[:400]!r}"
        )

        # Re-read the marker and assert counters are UNCHANGED (still 0/0)
        _set_state_dir(state_dir)
        try:
            marker_after = lazy_core.read_run_marker(now=now + 1)
        finally:
            _clear_state_dir()

        assert marker_after is not None, (
            "run marker must still be present after --repeat-count-peek"
        )
        assert marker_after["forward_cycles"] == 0, (
            f"--repeat-count-peek must NOT advance forward_cycles; "
            f"got forward_cycles={marker_after['forward_cycles']!r}"
        )
        assert marker_after["meta_cycles"] == 0, (
            f"--repeat-count-peek must NOT advance meta_cycles; "
            f"got meta_cycles={marker_after['meta_cycles']!r}"
        )

    # --- Sub-test B: freshness-leg — emitted_at before started_at → None ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            base = _time.time()

            # Write a marker with started_at = base + 10 (10 seconds in the future)
            # so that entries registered at `base` predate the run.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, now=base + 10,
            )

            # Register an entry BEFORE the marker's started_at
            prompt = "freshness-leg-test prompt"
            lazy_core.register_emission(prompt, cls="cycle", now=base)

            # lookup at base + 20 (within TTL, but before started_at epoch)
            stale_result = lazy_core.lookup_emission(prompt, now=base + 20)
            assert stale_result is None, (
                "lookup_emission must return None when emitted_at is before "
                f"the marker's started_at (freshness gate); got {stale_result!r}"
            )

            # Register a FRESH entry (after the marker's started_at)
            lazy_core.register_emission(prompt, cls="cycle", now=base + 15)
            fresh_result = lazy_core.lookup_emission(prompt, now=base + 20)
            assert fresh_result is not None, (
                "lookup_emission must return the entry when emitted_at >= "
                f"marker's started_at; got None"
            )
        finally:
            _clear_state_dir()


# ---------------------------------------------------------------------------
# End of Phase 1 test definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: Phase 3 — emit_dispatch_prompt (--emit-dispatch <class>)
# ---------------------------------------------------------------------------
#
# RED STATE for all tests below: lazy_core lacks DISPATCH_CLASSES,
# DISPATCH_MODELS, and emit_dispatch_prompt.  Tests 2 and 3 additionally
# fail because the dispatch-<class>.md template files do not yet exist.
# Tests 8 and 9 fail because lazy-state.py / bug-state.py do not yet
# accept the --emit-dispatch CLI flag (argparse exits 2 — asserted explicitly
# so the failure is meaningful rather than a confusing returncode mismatch).
#
# Isolation discipline: subprocess tests that touch the state dir set
# LAZY_STATE_DIR via the env dict (NOT os.environ directly) so hermetic
# isolation is preserved across all parallel-run scenarios.

# The six Phase 3 dispatch classes, ordered as the spec defines them.
# "hardening" arrives in Phase 4 and MUST NOT appear here.
_EXPECTED_DISPATCH_CLASSES = (
    "apply-resolution",
    "input-audit",
    "investigation",
    "recovery",
    "coherence-recovery",
    "needs-runtime-redispatch",
)


# Model assignment per class — derived from the SOURCE COMPONENTS (not SPEC.md,
# which pins no per-class models).  apply-resolution=opus because
# blocked-resolution.md dispatches its apply subagent as Opus.
_EXPECTED_DISPATCH_MODELS = {
    "apply-resolution": "opus",   # blocked-resolution.md: Opus apply subagent
    "input-audit": "opus",
    "investigation": "opus",
    "recovery": "sonnet",
    "coherence-recovery": "sonnet",
    "needs-runtime-redispatch": "opus",
}


def test_emit_dispatch_symbols_present():
    """DISPATCH_CLASSES, DISPATCH_MODELS, and emit_dispatch_prompt must exist
    on lazy_core.  The six Phase 3 classes must all be present (Phase 4 adds
    'hardening' as the 7th entry — exact-set check updated to subset check so
    the test remains green after Phase 4).  Every class must map to 'opus' or
    'sonnet' per the spec contract.

    RED: all three names missing → AttributeError / AssertionError.

    Phase 4 note: 'hardening' is now a valid 7th class (added by Phase 4 per
    test_hardening_dispatch_class_present).  This test verifies the 6 Phase 3
    classes remain present in order; the Phase 4 test verifies the full 7-tuple.
    """
    _guard()

    # --- Symbol presence ---
    assert hasattr(lazy_core, "DISPATCH_CLASSES"), (
        "lazy_core.DISPATCH_CLASSES missing — Phase 3 not yet implemented"
    )
    assert hasattr(lazy_core, "DISPATCH_MODELS"), (
        "lazy_core.DISPATCH_MODELS missing — Phase 3 not yet implemented"
    )
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing — Phase 3 not yet implemented"
    )

    # --- DISPATCH_CLASSES: all 6 Phase 3 classes must be present as the first 6 ---
    classes = lazy_core.DISPATCH_CLASSES
    # Must be a tuple (ordered, hashable).
    assert isinstance(classes, tuple), (
        f"DISPATCH_CLASSES must be a tuple, got {type(classes).__name__}"
    )
    # All 6 Phase 3 classes must be a subset (Phase 4 may add more entries).
    missing = set(_EXPECTED_DISPATCH_CLASSES) - set(classes)
    assert not missing, (
        f"DISPATCH_CLASSES is missing Phase 3 classes: {sorted(missing)}\n"
        f"  current tuple: {classes}"
    )
    # The first 6 entries must match the Phase 3 classes in order.
    assert classes[:6] == _EXPECTED_DISPATCH_CLASSES, (
        f"DISPATCH_CLASSES first-6 ordering mismatch.\n"
        f"  expected first 6: {_EXPECTED_DISPATCH_CLASSES}\n"
        f"  got first 6:      {classes[:6]}"
    )

    # --- DISPATCH_MODELS maps every Phase 3 class to a valid model ---
    models = lazy_core.DISPATCH_MODELS
    assert isinstance(models, dict), (
        f"DISPATCH_MODELS must be a dict, got {type(models).__name__}"
    )
    for cls in _EXPECTED_DISPATCH_CLASSES:
        assert cls in models, f"DISPATCH_MODELS missing key: {cls!r}"
        model = models[cls]
        assert model in ("opus", "sonnet"), (
            f"DISPATCH_MODELS[{cls!r}] must be 'opus' or 'sonnet', got {model!r}"
        )
        expected_model = _EXPECTED_DISPATCH_MODELS[cls]
        assert model == expected_model, (
            f"DISPATCH_MODELS[{cls!r}] = {model!r}; expected {expected_model!r} "
            f"per the Phase 3 spec contract"
        )


def test_emit_dispatch_real_template_binding_matrix():
    """Binding-completeness matrix over the REAL dispatch templates:
    for each class × pipeline (feature, bug) × cloud (False, True),
    emit_dispatch_prompt must return ok=True with zero {lower_snake} residue,
    model == DISPATCH_MODELS[cls], and prompt length > 200 (real dispatch briefs,
    not stubs).

    The context dict is constructed from the @requires keys declared in the
    template's first line plus 'item_id' and 'cwd' as standard extras.

    RED: DISPATCH_CLASSES / emit_dispatch_prompt missing → AttributeError;
         template files missing → ok=False or FileNotFoundError.
    """
    _guard()
    assert hasattr(lazy_core, "DISPATCH_CLASSES"), (
        "lazy_core.DISPATCH_CLASSES missing"
    )
    assert hasattr(lazy_core, "DISPATCH_MODELS"), (
        "lazy_core.DISPATCH_MODELS missing"
    )
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )

    for cls in lazy_core.DISPATCH_CLASSES:
        tpl_path = _REAL_TEMPLATE_DIR / f"dispatch-{cls}.md"
        # Read @requires keys from line 1 of the template.
        text = tpl_path.read_text(encoding="utf-8")
        first_line = next(
            (ln for ln in text.splitlines() if ln.strip()),
            ""
        )
        m = re.match(r'^<!-- @requires ([a-z0-9_,]+) -->', first_line)
        assert m, (
            f"dispatch-{cls}.md has no valid @requires on line 1; got: {first_line!r}"
        )
        requires_keys = [k.strip() for k in m.group(1).split(",") if k.strip()]

        # Build context: every @requires key → synthetic "test-<key>" value,
        # plus standard extras.
        context = {k: f"test-{k}" for k in requires_keys}
        context["item_id"] = "feat-x"
        context["cwd"] = "/tmp/x"

        for pipeline in ("feature", "bug"):
            for cloud in (False, True):
                mode = "cloud" if cloud else "workstation"
                ctx_label = f"cls={cls} pipeline={pipeline} mode={mode}"

                result = lazy_core.emit_dispatch_prompt(
                    cls, context,
                    pipeline=pipeline,
                    cloud=cloud,
                    template_dir=_REAL_TEMPLATE_DIR,
                )

                assert isinstance(result, dict), (
                    f"{ctx_label}: emit_dispatch_prompt must return a dict, got {result!r}"
                )
                assert result.get("ok") is True, (
                    f"{ctx_label}: expected ok=True; got {result!r}"
                )

                prompt = result["prompt"]
                residue = _TOKEN_RESIDUE_RE.findall(prompt)
                assert not residue, (
                    f"{ctx_label}: unbound token residue {residue} in dispatch prompt"
                )

                expected_model = lazy_core.DISPATCH_MODELS[cls]
                assert result.get("model") == expected_model, (
                    f"{ctx_label}: expected model={expected_model!r}; "
                    f"got {result.get('model')!r}"
                )

                assert len(prompt) > 200, (
                    f"{ctx_label}: dispatch prompt suspiciously short ({len(prompt)} chars); "
                    f"real dispatch briefs must be > 200 chars (not a stub)"
                )


def test_emit_dispatch_refuses_missing_requires():
    """Synthetic template with @requires foo,bar; context missing 'bar'
    → ok=False, refusal message names 'bar'.

    Uses a synthetic template dir so no real template file is needed.

    RED: emit_dispatch_prompt missing → AttributeError.
    """
    _guard()
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )
    # Use any known dispatch class as cls — 'recovery' is representative.
    cls = "recovery"

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "synth-dispatch-tpl"
        tdir.mkdir(parents=True, exist_ok=True)
        # Minimal template: @requires foo,bar; body uses both tokens.
        tpl_text = (
            "<!-- @requires foo,bar -->\n"
            "<!-- @section body pipelines=feature,bug modes=workstation,cloud -->\n"
            "This dispatch requires {foo} and {bar}.\n"
        )
        (tdir / f"dispatch-{cls}.md").write_text(tpl_text, encoding="utf-8")

        # Context provides 'foo' but NOT 'bar'.
        context = {"foo": "foo-value", "item_id": "feat-x"}
        result = lazy_core.emit_dispatch_prompt(
            cls, context,
            pipeline="feature",
            cloud=False,
            template_dir=tdir,
        )

        assert isinstance(result, dict), (
            f"emit_dispatch_prompt must return a dict on @requires failure, got {result!r}"
        )
        assert result.get("ok") is False, (
            f"expected ok=False when @requires key is missing; got {result!r}"
        )
        refused_msg = result.get("refused", "")
        assert "bar" in refused_msg, (
            f"refusal message must name the missing @requires key 'bar'; "
            f"got: {refused_msg!r}"
        )


def test_emit_dispatch_refuses_unbound_residue():
    """Synthetic template with a {not_supplied} token NOT declared in @requires
    → ok=False, refusal message names the token.

    Mirrors test_emit_cycle_prompt_refuses_unknown_token_synthetic.

    RED: emit_dispatch_prompt missing → AttributeError.
    """
    _guard()
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )
    cls = "recovery"

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "synth-dispatch-tpl"
        tdir.mkdir(parents=True, exist_ok=True)
        # @requires declares nothing; body has an unbound token.
        tpl_text = (
            "<!-- @requires item_id -->\n"
            "<!-- @section body pipelines=feature,bug modes=workstation,cloud -->\n"
            "Dispatching recovery for {item_id}.\n"
            "This section references {not_supplied} which is not bindable.\n"
        )
        (tdir / f"dispatch-{cls}.md").write_text(tpl_text, encoding="utf-8")

        context = {"item_id": "feat-x"}
        result = lazy_core.emit_dispatch_prompt(
            cls, context,
            pipeline="feature",
            cloud=False,
            template_dir=tdir,
        )

        assert isinstance(result, dict), (
            f"emit_dispatch_prompt must return a dict on residue failure, got {result!r}"
        )
        assert result.get("ok") is False, (
            f"expected ok=False when unbound residue survives; got {result!r}"
        )
        refused_msg = result.get("refused", "")
        assert "not_supplied" in refused_msg, (
            f"refusal message must name the unbound token 'not_supplied'; "
            f"got: {refused_msg!r}"
        )


def test_emit_dispatch_content_braces_in_value_do_not_refuse():
    """A context VALUE containing a literal {lower_snake} brace (code snippet /
    JSON / curly-brace wire-type in a free-text resolution_summary) must NOT be
    mis-flagged as an unbound token — the emission succeeds and the brace
    survives verbatim in the prompt.

    Regression for docs/bugs/emit-dispatch-residue-guard-flags-content-braces:
    the residue guard previously scanned the FULLY-BOUND prompt, so a literal
    `{trigger_id}` inside the injected value fail-closed a correct dispatch.
    """
    _guard()
    cls = "recovery"
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "synth-dispatch-tpl"
        tdir.mkdir(parents=True, exist_ok=True)
        tpl_text = (
            "<!-- @requires item_id,failure_summary -->\n"
            "<!-- @section body pipelines=feature,bug modes=workstation,cloud -->\n"
            "Recovery for {item_id}. Summary: {failure_summary}\n"
        )
        (tdir / f"dispatch-{cls}.md").write_text(tpl_text, encoding="utf-8")

        # The free-text value legitimately contains literal {lower_snake} braces
        # AND a JSON object — all opaque DATA, none of it a template placeholder.
        brace_value = 'wire-type {trigger_id} in payload {"kind": "route_loop"}'
        context = {"item_id": "feat-x", "failure_summary": brace_value}
        result = lazy_core.emit_dispatch_prompt(
            cls, context, pipeline="feature", cloud=False, template_dir=tdir,
        )

        assert isinstance(result, dict), result
        assert result.get("ok") is True, (
            f"content braces in a context VALUE must not refuse the dispatch; "
            f"got: {result!r}"
        )
        assert brace_value in result["prompt"], (
            "the brace-bearing value must survive verbatim in the emitted prompt"
        )
        # The genuine {item_id} placeholder is still bound (no residual placeholder).
        assert "{item_id}" not in result["prompt"], "template placeholder left unbound"


def test_emit_cycle_prompt_content_braces_in_state_value_do_not_refuse():
    """Near-neighbor: emit_cycle_prompt binds free-text state values (item_name,
    sub_skill_args, …). A literal {lower_snake} brace inside such a value must NOT
    trip the residue guard (same class as the dispatch-site regression).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "tpl"
        body = (
            "<!-- @section a pipelines=feature modes=workstation skills=all -->\n"
            "Working {item_name} at {current_step}.\n"
        )
        _write_synth_template(tdir, body)
        brace_name = "Feature {viz_param} overlay"
        r = lazy_core.emit_cycle_prompt(
            Path("/nonexistent/repo"),
            _emit_state(sub_skill="/execute-plan", feature_name=brace_name),
            pipeline="feature", cloud=False, template_dir=tdir,
        )
        assert r is not None and r.get("ok") is True, (
            f"content braces in a state VALUE must not refuse the cycle prompt; got {r}"
        )
        assert brace_name in r["prompt"], "brace-bearing item_name must survive verbatim"


def test_emit_dispatch_section_filtering():
    """Section filtering on a synthetic dispatch template:
    - A section gated pipelines=bug modes=cloud must appear only for bug+cloud.
    - A section gated pipelines=feature modes=workstation must appear only for
      feature+workstation.

    Mirrors the section-selection logic in test_emit_cycle_prompt_section_selection_synthetic.

    RED: emit_dispatch_prompt missing → AttributeError.
    """
    _guard()
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )
    cls = "recovery"

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td) / "synth-dispatch-tpl"
        tdir.mkdir(parents=True, exist_ok=True)
        # @requires one key; two filtered sections so every combo hits something.
        tpl_text = (
            "<!-- @requires item_id -->\n"
            "<!-- @section always pipelines=feature,bug modes=workstation,cloud -->\n"
            "SECTION_ALWAYS common content for {item_id}.\n"
            "\n"
            "<!-- @section bug_cloud pipelines=bug modes=cloud -->\n"
            "SECTION_BUG_CLOUD — bug + cloud only.\n"
            "\n"
            "<!-- @section feature_ws pipelines=feature modes=workstation -->\n"
            "SECTION_FEATURE_WS — feature + workstation only.\n"
        )
        (tdir / f"dispatch-{cls}.md").write_text(tpl_text, encoding="utf-8")

        context = {"item_id": "feat-x"}

        # feature + workstation → ALWAYS + FEATURE_WS, NOT BUG_CLOUD.
        r_fw = lazy_core.emit_dispatch_prompt(
            cls, context,
            pipeline="feature",
            cloud=False,
            template_dir=tdir,
        )
        assert r_fw is not None and r_fw.get("ok") is True, (
            f"feature/workstation emission failed: {r_fw!r}"
        )
        assert "SECTION_ALWAYS" in r_fw["prompt"]
        assert "SECTION_FEATURE_WS" in r_fw["prompt"]
        assert "SECTION_BUG_CLOUD" not in r_fw["prompt"], (
            "bug+cloud section must NOT appear in feature+workstation emission"
        )

        # bug + cloud → ALWAYS + BUG_CLOUD, NOT FEATURE_WS.
        r_bc = lazy_core.emit_dispatch_prompt(
            cls, context,
            pipeline="bug",
            cloud=True,
            template_dir=tdir,
        )
        assert r_bc is not None and r_bc.get("ok") is True, (
            f"bug/cloud emission failed: {r_bc!r}"
        )
        assert "SECTION_ALWAYS" in r_bc["prompt"]
        assert "SECTION_BUG_CLOUD" in r_bc["prompt"]
        assert "SECTION_FEATURE_WS" not in r_bc["prompt"], (
            "feature+workstation section must NOT appear in bug+cloud emission"
        )


def test_emit_dispatch_unknown_class_raises():
    """emit_dispatch_prompt raises ValueError for unknown classes (e.g. 'nonsense').
    'hardening' was listed here in Phase 3 as a future unknown class; it is now
    a registered Phase 4 class and has been removed from this test's bad-class list
    (covered by test_hardening_dispatch_class_present instead).

    RED: emit_dispatch_prompt missing → AttributeError.
    """
    _guard()
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )
    for bad_cls in ("nonsense",):
        raised = False
        try:
            lazy_core.emit_dispatch_prompt(
                bad_cls, {},
                pipeline="feature",
                cloud=False,
            )
        except ValueError:
            raised = True
        except Exception as exc:
            assert False, (
                f"emit_dispatch_prompt({bad_cls!r}) raised {type(exc).__name__} "
                f"instead of ValueError: {exc}"
            )
        assert raised, (
            f"emit_dispatch_prompt({bad_cls!r}) must raise ValueError for an "
            f"unknown dispatch class; it returned without raising"
        )


def _build_dispatch_registry_fixture(td_path):
    """Build the minimal lazy-state.py fixture repo used by the dispatch CLI tests.

    Returns the fixture_repo Path.  Mirrors the fixture layout from
    test_subprocess_emit_prompt_with_marker_writes_registry.
    """
    features = td_path / "fixture-repo" / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [
            {"id": "feat-x", "name": "Feature X", "spec_dir": "feat-x", "tier": 1}
        ]
    }), encoding="utf-8")
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-x"
    fdir.mkdir()
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
    (fdir / "plans").mkdir()
    (fdir / "plans" / "all-phases-x.md").write_text("# Plan\n", encoding="utf-8")
    return td_path / "fixture-repo"


def _read_recovery_requires_keys():
    """Return the @requires keys declared in dispatch-recovery.md line 1,
    or None if the file doesn't exist (so callers can skip gracefully).
    """
    tpl_path = _REAL_TEMPLATE_DIR / "dispatch-recovery.md"
    if not tpl_path.exists():
        return None
    text = tpl_path.read_text(encoding="utf-8")
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    m = re.match(r'^<!-- @requires ([a-z0-9_,]+) -->', first_line)
    if not m:
        return None
    return [k.strip() for k in m.group(1).split(",") if k.strip()]


def test_emit_dispatch_cli_registry_gating():
    """Subprocess test against the REAL lazy-state.py with --emit-dispatch.

    Three sub-scenarios for the 'recovery' class (model = 'sonnet'):

    (a) NO marker present: --emit-dispatch recovery succeeds (exit 0), stdout
        JSON has non-null dispatch_prompt, dispatch_model == 'sonnet'; the
        registry file is NOT written (peek semantics without a marker).

    (b) Marker present: same invocation writes a registry entry with
        class == 'recovery', item_id == 'feat-x', and prompt_sha256 ==
        lazy_core.prompt_sha256(dispatch_prompt from stdout).

    (c) Refusal: a required @requires context key is dropped → exit 1, stdout
        JSON has dispatch_prompt_refused non-empty, NO new registry entry added.

    RED: --emit-dispatch flag not yet added to lazy-state.py → argparse exits 2
    (unknown flag); the test asserts returncode == 2 when the flag is unknown so
    the failure reason is explicit and meaningful rather than a confusing EOF.
    """
    _guard()
    # Guard on Phase 1 symbols needed by this test.
    assert hasattr(lazy_core, "write_run_marker"), (
        "lazy_core.write_run_marker missing — Phase 1 not yet implemented"
    )
    assert hasattr(lazy_core, "prompt_sha256"), (
        "lazy_core.prompt_sha256 missing — Phase 1 not yet implemented"
    )
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing — Phase 3 not yet implemented"
    )

    # Read the real @requires keys for 'recovery' so the context is exactly right.
    requires_keys = _read_recovery_requires_keys()
    if requires_keys is None:
        # Template not yet written — fail explicitly rather than skip silently.
        assert False, (
            "dispatch-recovery.md does not exist or has no valid @requires on line 1; "
            "Phase 3 template authoring is incomplete"
        )

    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"
    import time as _time

    # Build the context flags: one --context KEY=VALUE per @requires key + item_id.
    context_flags = []
    for k in requires_keys:
        context_flags += ["--context", f"{k}=test-{k}"]
    context_flags += ["--context", "item_id=feat-x"]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _build_dispatch_registry_fixture(td_path)
        state_dir = td_path / "dispatch-state-dir"
        state_dir.mkdir()

        # === Sub-scenario (a): NO marker — output produced, no registry write ===
        env_no_marker = dict(_os_env.environ)
        env_no_marker["LAZY_STATE_DIR"] = str(state_dir)
        cmd = [
            sys.executable, str(lazy_state_script),
            "--emit-dispatch", "recovery",
        ] + context_flags

        result_a = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_no_marker,
        )

        # If the flag is unknown, argparse exits 2 — fail with an explicit reason.
        assert result_a.returncode != 2, (
            "--emit-dispatch flag not recognized by lazy-state.py "
            f"(argparse exit 2).\n"
            f"stderr: {result_a.stderr[:400]!r}"
        )
        assert result_a.returncode == 0, (
            f"lazy-state.py --emit-dispatch recovery (no marker) exited "
            f"{result_a.returncode}; stderr: {result_a.stderr[:400]!r}; "
            f"stdout: {result_a.stdout[:400]!r}"
        )

        try:
            out_a = json.loads(result_a.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout is not valid JSON: {exc}\nstdout: {result_a.stdout[:400]!r}"
            ) from exc

        dispatch_prompt_a = out_a.get("dispatch_prompt")
        assert dispatch_prompt_a is not None, (
            f"dispatch_prompt must be non-null in no-marker run; out={out_a!r}"
        )
        assert out_a.get("dispatch_model") == "sonnet", (
            f"dispatch_model must be 'sonnet' for 'recovery' class; got {out_a.get('dispatch_model')!r}"
        )
        assert out_a.get("dispatch_class") == "recovery", (
            f"dispatch_class must be 'recovery'; got {out_a.get('dispatch_class')!r}"
        )

        registry_file = state_dir / "lazy-prompt-registry.json"
        assert not registry_file.exists(), (
            "Registry file must NOT be written when no marker is present "
            "(peek semantics). --emit-dispatch without a marker is output-only."
        )

        # === Sub-scenario (b): marker present — registry entry written ===
        now = _time.time()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=now,
            )
        finally:
            _clear_state_dir()

        env_with_marker = dict(_os_env.environ)
        env_with_marker["LAZY_STATE_DIR"] = str(state_dir)

        result_b = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_with_marker,
        )
        assert result_b.returncode == 0, (
            f"lazy-state.py --emit-dispatch recovery (with marker) exited "
            f"{result_b.returncode}; stderr: {result_b.stderr[:400]!r}; "
            f"stdout: {result_b.stdout[:400]!r}"
        )

        try:
            out_b = json.loads(result_b.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout is not valid JSON (marker run): {exc}\nstdout: {result_b.stdout[:400]!r}"
            ) from exc

        dispatch_prompt_b = out_b.get("dispatch_prompt")
        assert dispatch_prompt_b is not None, (
            f"dispatch_prompt must be non-null in marker run; out={out_b!r}"
        )

        # Registry must now exist with exactly one matching entry.
        assert registry_file.exists(), (
            "Registry file must be written when a marker is present and "
            "--emit-dispatch succeeds."
        )
        registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
        entries = registry_data.get("entries", [])
        expected_sha = lazy_core.prompt_sha256(dispatch_prompt_b)
        matching = [e for e in entries if e.get("prompt_sha256") == expected_sha]
        assert len(matching) >= 1, (
            f"Expected at least 1 registry entry with prompt_sha256 == "
            f"sha256(dispatch_prompt); found {len(matching)} matching.\n"
            f"expected sha={expected_sha!r}\n"
            f"entries={[e.get('prompt_sha256') for e in entries]!r}"
        )
        assert matching[-1].get("class") == "recovery", (
            f"Registry entry class must be 'recovery'; got {matching[-1].get('class')!r}"
        )
        assert matching[-1].get("item_id") == "feat-x", (
            f"Registry entry item_id must be 'feat-x'; got {matching[-1].get('item_id')!r}"
        )

        # === Sub-scenario (c): refusal — drop one required key → exit 1 ===
        if requires_keys:
            # Build context flags with the FIRST required key dropped.
            context_flags_missing = []
            for k in requires_keys[1:]:  # drop index 0
                context_flags_missing += ["--context", f"{k}=test-{k}"]
            context_flags_missing += ["--context", "item_id=feat-x"]

            cmd_refusal = [
                sys.executable, str(lazy_state_script),
                "--emit-dispatch", "recovery",
            ] + context_flags_missing

            entries_before = len(
                json.loads(registry_file.read_text(encoding="utf-8")).get("entries", [])
            )

            result_c = subprocess.run(
                cmd_refusal,
                capture_output=True,
                text=True,
                env=env_with_marker,
            )
            assert result_c.returncode == 1, (
                f"lazy-state.py --emit-dispatch with a missing @requires key must exit 1; "
                f"got returncode={result_c.returncode}; "
                f"stdout: {result_c.stdout[:400]!r}"
            )

            try:
                out_c = json.loads(result_c.stdout)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"stdout must be JSON even on refusal: {exc}\n"
                    f"stdout: {result_c.stdout[:400]!r}"
                ) from exc

            assert out_c.get("dispatch_prompt") is None, (
                f"dispatch_prompt must be null on refusal; got {out_c.get('dispatch_prompt')!r}"
            )
            refused_msg = out_c.get("dispatch_prompt_refused", "")
            assert refused_msg, (
                f"dispatch_prompt_refused must be non-empty on refusal; got {out_c!r}"
            )

            # No new registry entry must be added on refusal.
            entries_after = len(
                json.loads(registry_file.read_text(encoding="utf-8")).get("entries", [])
            )
            assert entries_after == entries_before, (
                f"Registry must NOT grow on refusal; had {entries_before} entries, "
                f"now have {entries_after}"
            )


def test_emit_dispatch_cli_bug_state_mirror():
    """Coupled-pair mirror of test_emit_dispatch_cli_registry_gating sub-scenario (a):
    bug-state.py --emit-dispatch recovery must also accept the flag and return
    exit 0 with a non-null dispatch_prompt (no marker → peek semantics, no write).

    RED: --emit-dispatch flag not yet added to bug-state.py → argparse exits 2;
    the test asserts returncode == 2 explicitly so the failure is meaningful.
    """
    _guard()
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing — Phase 3 not yet implemented"
    )

    requires_keys = _read_recovery_requires_keys()
    if requires_keys is None:
        assert False, (
            "dispatch-recovery.md does not exist or has no valid @requires on line 1; "
            "Phase 3 template authoring is incomplete"
        )

    bug_state_script = _SCRIPTS_DIR / "bug-state.py"
    context_flags = []
    for k in requires_keys:
        context_flags += ["--context", f"{k}=test-{k}"]
    context_flags += ["--context", "item_id=feat-x"]

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "dispatch-bug-state-dir"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        cmd = [
            sys.executable, str(bug_state_script),
            "--emit-dispatch", "recovery",
        ] + context_flags

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        # Explicit argparse-unknown-flag check (RED reason).
        assert result.returncode != 2, (
            "--emit-dispatch flag not recognized by bug-state.py "
            f"(argparse exit 2 — coupled-pair parity missing).\n"
            f"stderr: {result.stderr[:400]!r}"
        )
        assert result.returncode == 0, (
            f"bug-state.py --emit-dispatch recovery exited {result.returncode}; "
            f"stderr: {result.stderr[:400]!r}; stdout: {result.stdout[:400]!r}"
        )

        try:
            out = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"bug-state.py stdout is not valid JSON: {exc}\n"
                f"stdout: {result.stdout[:400]!r}"
            ) from exc

        assert out.get("dispatch_prompt") is not None, (
            f"bug-state.py --emit-dispatch recovery: dispatch_prompt must be "
            f"non-null (no marker → peek); got {out!r}"
        )
        assert out.get("dispatch_class") == "recovery", (
            f"bug-state.py dispatch_class must be 'recovery'; got {out.get('dispatch_class')!r}"
        )

        # No registry file without a marker.
        registry_file = state_dir / "lazy-prompt-registry.json"
        assert not registry_file.exists(), (
            "bug-state.py must NOT write the registry without a marker "
            "(peek semantics — coupled-pair mirror of lazy-state.py behavior)"
        )


# ---------------------------------------------------------------------------
# End of Phase 3 test definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 4 test definitions — /harden-harness skill + hardening dispatch class
# ---------------------------------------------------------------------------
#
# RED STATE for all tests below: "hardening" is not yet in DISPATCH_CLASSES
# (the tuple has 6 entries, Phase 3 only), DISPATCH_MODELS has no "hardening"
# key, the dispatch-hardening.md template does not exist, and the
# harden-harness SKILL.md file does not exist.
#
# Each test fails for a specific, meaningful reason rather than a confusing
# AttributeError or file-not-found traceback.
#
# Isolation discipline: subprocess tests set LAZY_STATE_DIR via the env dict.
#
# The 8 @requires keys the hardening dispatch template MUST declare (spec
# §"The harness-hardening stage" full contract + PHASES.md Phase 4
# deliverables; `blocking` added by no-mid-run-observed-friction-harden-dispatch
# §1 — the observed-friction block/background policy token, defaulted to
# `n/a (auto-trigger)` by normalize_hardening_dispatch_context for the
# non-observed triggers).  Read dynamically from the real template where
# possible; this tuple is used as the ground-truth set to assert against.
_HARDENING_REQUIRED_KEYS: frozenset[str] = frozenset({
    "denied_prompt_summary",
    "denial_reason",
    "probe_json",
    "registry_state",
    "trigger_kind",
    "item_id",
    "cwd",
    "blocking",
})


# Resolve the harden-harness SKILL.md path relative to the repo root inferred
# from _SCRIPTS_DIR (user/scripts).
_HARDEN_SKILL_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills" / "harden-harness" / "SKILL.md"
)


def test_hardening_dispatch_class_present():
    """Phase 4 contract: 'hardening' is present in DISPATCH_CLASSES as the LAST
    entry; DISPATCH_MODELS['hardening'] == 'opus'; calling
    emit_dispatch_prompt('hardening', ...) does NOT raise ValueError.

    The tuple length grew from 7 (Phase 4) to 9 when harden Round 44 (2026-06-29)
    appended 'corrective-coverage' + 'ingest-research' BEFORE 'hardening', and to
    10 when harden Round 80 (2026-07-17) appended 'spike' BEFORE 'hardening' (so
    the last-entry invariant is preserved). The exact count is asserted to catch
    an accidental class drop; bump it deliberately when adding a class.

    RED reasons:
      - DISPATCH_MODELS['hardening'] absent → KeyError.
      - emit_dispatch_prompt('hardening') raises ValueError → AssertionError.
      - 'hardening' is no longer the last entry → AssertionError.
    """
    _guard()

    assert hasattr(lazy_core, "DISPATCH_CLASSES"), (
        "lazy_core.DISPATCH_CLASSES missing"
    )
    assert hasattr(lazy_core, "DISPATCH_MODELS"), (
        "lazy_core.DISPATCH_MODELS missing"
    )
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )

    classes = lazy_core.DISPATCH_CLASSES

    # Must be a tuple (ordered) and contain exactly 7 entries after Phase 4.
    assert isinstance(classes, tuple), (
        f"DISPATCH_CLASSES must be a tuple, got {type(classes).__name__}"
    )
    assert len(classes) == 10, (
        f"DISPATCH_CLASSES must have 10 entries (7 Phase-4 + Round-44 "
        f"'corrective-coverage' + 'ingest-research' + Round-80 'spike'); "
        f"got {len(classes)}: {classes}"
    )

    # 'hardening' must be present.
    assert "hardening" in classes, (
        f"'hardening' must be in DISPATCH_CLASSES (Phase 4 deliverable); "
        f"current classes: {classes}"
    )

    # 'hardening' must be the last entry (appended after the 6 Phase 3 classes).
    assert classes[-1] == "hardening", (
        f"'hardening' must be the last entry in DISPATCH_CLASSES; "
        f"got last={classes[-1]!r}, full tuple={classes}"
    )

    # All 6 Phase 3 classes must still be present in order.
    phase3_classes = (
        "apply-resolution",
        "input-audit",
        "investigation",
        "recovery",
        "coherence-recovery",
        "needs-runtime-redispatch",
    )
    assert classes[:6] == phase3_classes, (
        f"The first 6 entries of DISPATCH_CLASSES must be the Phase 3 classes "
        f"in order; got {classes[:6]!r}"
    )

    # DISPATCH_MODELS must include 'hardening' mapped to 'opus'.
    models = lazy_core.DISPATCH_MODELS
    assert "hardening" in models, (
        "DISPATCH_MODELS must include 'hardening' (Phase 4 deliverable)"
    )
    assert models["hardening"] == "opus", (
        f"DISPATCH_MODELS['hardening'] must be 'opus' (Opus judgment work — "
        f"root-cause analysis + mechanical fixes); got {models['hardening']!r}"
    )

    # emit_dispatch_prompt('hardening', ...) must NOT raise ValueError now that
    # 'hardening' is a registered class.  It may return ok=False if the template
    # or context is missing — that is acceptable here; we only verify the
    # ValueError for unknown-class no longer fires.
    raised_value_error = False
    try:
        lazy_core.emit_dispatch_prompt(
            "hardening",
            # Supply dummy values for all 8 required keys so binding can proceed
            # if the template exists; if the template is missing, ok=False is
            # returned without ValueError — that is fine for this test.
            {k: f"dummy-{k}" for k in _HARDENING_REQUIRED_KEYS},
            pipeline="feature",
            cloud=False,
            template_dir=_REAL_TEMPLATE_DIR,
        )
    except ValueError:
        raised_value_error = True
    except Exception:
        # Any other exception (e.g. FileNotFoundError if template absent,
        # caught internally and returned as ok=False) is not our concern here —
        # the test only guards against ValueError.
        pass

    assert not raised_value_error, (
        "emit_dispatch_prompt('hardening', ...) must NOT raise ValueError after "
        "Phase 4 adds 'hardening' to DISPATCH_CLASSES; "
        "currently raises ValueError because 'hardening' is not yet registered"
    )


def test_hardening_template_binding():
    """Phase 4 contract: the real dispatch-hardening.md template file exists,
    declares all 8 required @requires keys, binds cleanly for feature and bug
    pipelines, and the emitted prompt satisfies the content contract.

    @requires contract (all 8 must appear in the declared set):
      denied_prompt_summary, denial_reason, probe_json, registry_state,
      trigger_kind, item_id, cwd, blocking

    Prompt content contract:
      - contains '/harden-harness' (the skill invocation instruction)
      - contains the literal commit prefix 'harden(' (log discipline)
      - contains 'never edits the registry' OR 'never edits the registry/marker'
        (prohibition phrase — phrasing variant allowed)
      - contains 'never weakens a gate' (prohibition phrase)
      - does NOT contain 'You do not run `git commit`' (the hardening stage
        DOES commit under full gates — it works on claude-config itself)

    RED reasons:
      - dispatch-hardening.md does not exist → template file missing
        AssertionError (file-existence check fires first).
      - @requires set incomplete → AssertionError naming missing keys.
      - emit ok=False → AssertionError naming the refusal.
      - Prompt content missing required phrase → AssertionError.
    """
    _guard()

    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing"
    )

    tpl_path = _REAL_TEMPLATE_DIR / "dispatch-hardening.md"
    assert tpl_path.exists(), (
        f"dispatch-hardening.md does not exist at {tpl_path}; "
        f"Phase 4 must create this template under "
        f"user/skills/_components/lazy-batch-prompts/"
    )

    # Read the @requires line dynamically (line 1 of the template).
    text = tpl_path.read_text(encoding="utf-8")
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    m = re.match(r"^<!-- @requires ([a-z0-9_,]+) -->$", first_line)
    assert m, (
        f"dispatch-hardening.md first non-empty line must be "
        f"'<!-- @requires key1,key2,... -->' (only [a-z0-9_,] chars); "
        f"got: {first_line!r}"
    )

    declared_keys = frozenset(k.strip() for k in m.group(1).split(",") if k.strip())

    # Assert all 7 required keys are declared.
    missing_from_declared = _HARDENING_REQUIRED_KEYS - declared_keys
    assert not missing_from_declared, (
        f"dispatch-hardening.md @requires must declare all 8 required keys; "
        f"missing from declared set: {sorted(missing_from_declared)}\n"
        f"  declared: {sorted(declared_keys)}\n"
        f"  required: {sorted(_HARDENING_REQUIRED_KEYS)}"
    )

    # Build a context that supplies every declared @requires key with a dummy value.
    context = {k: f"test-{k}" for k in declared_keys}
    context["item_id"] = "feat-hardening-test"
    context["cwd"] = "/tmp/hardening-test"

    for pipeline in ("feature", "bug"):
        for cloud in (False, True):
            mode = "cloud" if cloud else "workstation"
            ctx_label = f"pipeline={pipeline} mode={mode}"

            result = lazy_core.emit_dispatch_prompt(
                "hardening",
                context,
                pipeline=pipeline,
                cloud=cloud,
                template_dir=_REAL_TEMPLATE_DIR,
            )

            assert isinstance(result, dict), (
                f"{ctx_label}: emit_dispatch_prompt must return a dict; "
                f"got {result!r}"
            )
            assert result.get("ok") is True, (
                f"{ctx_label}: expected ok=True; got {result!r}"
            )

            prompt = result["prompt"]

            # Residue check.
            residue = _TOKEN_RESIDUE_RE.findall(prompt)
            assert not residue, (
                f"{ctx_label}: unbound token residue {residue} in hardening prompt"
            )

            # Model must be 'opus'.
            assert result.get("model") == "opus", (
                f"{ctx_label}: hardening dispatch model must be 'opus'; "
                f"got {result.get('model')!r}"
            )

            # Prompt must be substantial (not a stub).
            assert len(prompt) > 400, (
                f"{ctx_label}: hardening dispatch prompt suspiciously short "
                f"({len(prompt)} chars); must be > 400 chars"
            )

            # --- Content contract checks ---

            # Must reference the /harden-harness skill.
            assert "/harden-harness" in prompt, (
                f"{ctx_label}: hardening prompt must contain '/harden-harness' "
                f"(the skill invocation instruction); not found in:\n{prompt[:500]!r}"
            )

            # Must contain the commit prefix 'harden(' (HARDENING.md log discipline).
            assert "harden(" in prompt, (
                f"{ctx_label}: hardening prompt must contain the commit prefix "
                f"'harden(' (per SPEC §The harness-hardening stage, Deliverable 4); "
                f"not found in:\n{prompt[:500]!r}"
            )

            # Must contain the 'never edits the registry' prohibition phrase.
            # Accept either the short form or the 'registry/marker' expanded form.
            assert (
                "never edits the registry" in prompt
                or "never edits the registry/marker" in prompt
            ), (
                f"{ctx_label}: hardening prompt must contain the prohibition phrase "
                f"'never edits the registry' (or 'registry/marker' variant); "
                f"not found in:\n{prompt[:500]!r}"
            )

            # Must contain the 'never weakens a gate' prohibition phrase.
            assert "never weakens a gate" in prompt, (
                f"{ctx_label}: hardening prompt must contain the prohibition phrase "
                f"'never weakens a gate'; not found in:\n{prompt[:500]!r}"
            )

            # Must NOT contain the standard no-commit clause.
            # The hardening stage DOES commit (it works on claude-config under full
            # gates); the standard dispatch template no-commit clause must be absent.
            assert "You do not run `git commit`" not in prompt, (
                f"{ctx_label}: hardening prompt must NOT contain "
                f"'You do not run `git commit`' — the hardening stage commits "
                f"under full gates on claude-config (it is NOT the standard "
                f"no-commit dispatch); found in:\n{prompt[:500]!r}"
            )


def test_spike_dispatch_class_registered():
    """harden Round 80: 'spike' is a registered dispatch class (Opus), inserted
    BEFORE 'hardening' so the last-entry invariant is preserved, and
    emit_dispatch_prompt('spike', ...) does NOT raise the unknown-class ValueError.
    """
    _guard()
    classes = lazy_core.DISPATCH_CLASSES
    assert "spike" in classes, f"'spike' must be in DISPATCH_CLASSES; got {classes}"
    assert classes[-1] == "hardening", (
        f"'hardening' must remain the LAST entry (spike inserted before it); "
        f"got last={classes[-1]!r}"
    )
    assert classes.index("spike") < classes.index("hardening"), (
        "'spike' must precede 'hardening' in DISPATCH_CLASSES"
    )
    assert lazy_core.DISPATCH_MODELS["spike"] == "opus", (
        f"DISPATCH_MODELS['spike'] must be 'opus' (runtime-proof judgment); "
        f"got {lazy_core.DISPATCH_MODELS.get('spike')!r}"
    )
    # Unknown-class ValueError must NOT fire for a registered class.
    raised = False
    try:
        lazy_core.emit_dispatch_prompt(
            "spike", {}, pipeline="feature", cloud=False,
            template_dir=_REAL_TEMPLATE_DIR,
        )
    except ValueError:
        raised = True
    except Exception:
        pass
    assert not raised, "emit_dispatch_prompt('spike', ...) must not raise ValueError"


def test_spike_template_binding():
    """harden Round 80: the real dispatch-spike.md template exists, declares its
    @requires keys, binds cleanly across feature/bug × workstation/cloud, emits an
    Opus prompt with no unbound residue, and carries the load-bearing honesty +
    orchestrator-owned-runtime prose.
    """
    _guard()
    tpl_path = _REAL_TEMPLATE_DIR / "dispatch-spike.md"
    assert tpl_path.exists(), (
        f"dispatch-spike.md must exist at {tpl_path} "
        f"(user/skills/_components/lazy-batch-prompts/)"
    )
    text = tpl_path.read_text(encoding="utf-8")
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    m = re.match(r"^<!-- @requires ([a-z0-9_,]+) -->$", first_line)
    assert m, f"dispatch-spike.md line 1 must be a valid @requires decl; got {first_line!r}"
    declared = frozenset(k.strip() for k in m.group(1).split(",") if k.strip())
    expected = {"item_name", "spec_path", "spike_goal", "next_on_pass", "item_id", "cwd"}
    assert expected <= declared, (
        f"dispatch-spike.md @requires missing {sorted(expected - declared)}; "
        f"declared: {sorted(declared)}"
    )
    context = {k: f"test-{k}" for k in declared}
    for pipeline in ("feature", "bug"):
        for cloud in (False, True):
            ctx_label = f"pipeline={pipeline} cloud={cloud}"
            result = lazy_core.emit_dispatch_prompt(
                "spike", context, pipeline=pipeline, cloud=cloud,
                template_dir=_REAL_TEMPLATE_DIR,
            )
            assert result.get("ok") is True, f"{ctx_label}: expected ok=True; got {result!r}"
            prompt = result["prompt"]
            residue = _TOKEN_RESIDUE_RE.findall(prompt)
            assert not residue, f"{ctx_label}: unbound token residue {residue}"
            assert result.get("model") == "opus", (
                f"{ctx_label}: spike dispatch model must be 'opus'; got {result.get('model')!r}"
            )
            # Honesty invariant prose (all-mode section) — the anti-fabrication rule.
            assert "fabricat" in prompt.lower(), (
                f"{ctx_label}: spike prompt must carry the anti-fabrication honesty rule"
            )
            assert "PENDING" in prompt, (
                f"{ctx_label}: spike prompt must offer the PENDING (no-fabricated-verdict) path"
            )
            # Tooling-existence loop must be described.
            assert "tooling" in prompt.lower(), (
                f"{ctx_label}: spike prompt must describe the tooling-existence check"
            )
    # Workstation-only section: orchestrator-owned runtime must appear for a
    # workstation dispatch (and the cloud dispatch must instead defer).
    ws = lazy_core.emit_dispatch_prompt(
        "spike", context, pipeline="feature", cloud=False,
        template_dir=_REAL_TEMPLATE_DIR,
    )["prompt"]
    assert "ORCHESTRATOR-OWNED" in ws, (
        "workstation spike prompt must state the runtime is ORCHESTRATOR-OWNED"
    )
    cloud = lazy_core.emit_dispatch_prompt(
        "spike", context, pipeline="feature", cloud=True,
        template_dir=_REAL_TEMPLATE_DIR,
    )["prompt"]
    assert "CLOUD RUN" in cloud, "cloud spike prompt must carry the defer-to-workstation note"


def test_hardening_skill_file_contract():
    """Phase 4 contract: user/skills/harden-harness/SKILL.md exists with:
      - YAML frontmatter containing 'name: harden-harness'
      - Body containing all four trigger descriptions (validate-deny/denied,
        no-route, inject, manual)
      - NEEDS_INPUT escalation path
      - Full gate list (lint-skills.py, --check-projected, test_lazy_core.py,
        test_hooks.py, bug-state.py --test)
      - Hardening-log path 'hardening-log'
      - Cadence clause 'unbounded' (per locked decision 4)
      - Prohibition 'never weakens a gate'
      - Depth/recursion cap wording containing 'depth'

    RED reason: user/skills/harden-harness/SKILL.md does not exist →
    file-existence AssertionError fires immediately.
    """
    _guard()  # Ensure lazy_core is importable (not strictly needed here but
               # mirrors harness conventions so the failure is consistent).

    assert _HARDEN_SKILL_PATH.exists(), (
        f"user/skills/harden-harness/SKILL.md does not exist at "
        f"{_HARDEN_SKILL_PATH}; Phase 4 must create this file"
    )

    skill_text = _HARDEN_SKILL_PATH.read_text(encoding="utf-8")

    # --- Frontmatter: name: harden-harness ---
    # YAML frontmatter is delimited by '---' lines.  The 'name: harden-harness'
    # field must appear inside the frontmatter block.
    assert "name: harden-harness" in skill_text, (
        f"SKILL.md frontmatter must contain 'name: harden-harness'; "
        f"not found in first 500 chars: {skill_text[:500]!r}"
    )

    # Convenience: case-insensitive search helper.
    lower = skill_text.lower()

    # --- Trigger descriptions (all four must appear) ---
    # Trigger 1: validate-deny fired (misroute).
    assert any(phrase in lower for phrase in ("validate-deny", "denied")), (
        "SKILL.md must describe trigger 1 (validate-deny / denied dispatch); "
        "neither 'validate-deny' nor 'denied' found"
    )
    # Trigger 2: no-route.
    assert "no-route" in lower, (
        "SKILL.md must describe trigger 2 (no-route); 'no-route' not found"
    )
    # Trigger 3: inject hook error.
    assert "inject" in lower, (
        "SKILL.md must describe trigger 3 (inject hook error); 'inject' not found"
    )
    # Trigger 4: manual invocation.
    assert "manual" in lower, (
        "SKILL.md must describe trigger 4 (manual invocation); 'manual' not found"
    )

    # --- Tiered authority: NEEDS_INPUT escalation ---
    assert "NEEDS_INPUT" in skill_text, (
        "SKILL.md must describe the NEEDS_INPUT escalation path for "
        "contract/policy/design-fork decisions (tiered authority); "
        "'NEEDS_INPUT' not found"
    )

    # --- Full gate list ---
    # Every gate from the SPEC must be named.
    for gate_phrase in (
        "lint-skills.py",
        "--check-projected",
        "test_lazy_core.py",
        "test_hooks.py",
        "bug-state.py --test",
    ):
        assert gate_phrase in skill_text, (
            f"SKILL.md must list the gate {gate_phrase!r} in the full gates "
            f"section (per SPEC §The harness-hardening stage, Act by decision "
            f"class — mechanical autonomous path); not found"
        )

    # --- Hardening-log path ---
    assert "hardening-log" in skill_text, (
        "SKILL.md must reference the hardening-log directory "
        "('docs/specs/turn-routing-enforcement/hardening-log/'); "
        "'hardening-log' not found"
    )

    # --- Cadence clause: unbounded (per locked decision 4) ---
    assert "unbounded" in lower, (
        "SKILL.md must contain the cadence clause 'unbounded' (inline unbounded "
        "per-run dispatch count — locked decision 4); not found"
    )

    # --- Prohibition: never weakens a gate ---
    assert "never weakens a gate" in lower, (
        "SKILL.md must state the prohibition 'never weakens a gate' "
        "(per SPEC §The harness-hardening stage, Prohibitions); not found"
    )

    # --- Recursion / depth cap ---
    assert "depth" in lower, (
        "SKILL.md must describe the recursion/depth cap ('depth' ... '1'); "
        "'depth' not found"
    )


def _read_hardening_requires_keys():
    """Return the @requires keys declared in dispatch-hardening.md line 1,
    or None if the file doesn't exist (so callers can skip gracefully).

    Mirrors _read_recovery_requires_keys() from the Phase 3 test section.
    """
    tpl_path = _REAL_TEMPLATE_DIR / "dispatch-hardening.md"
    if not tpl_path.exists():
        return None
    text = tpl_path.read_text(encoding="utf-8")
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    m = re.match(r"^<!-- @requires ([a-z0-9_,]+) -->", first_line)
    if not m:
        return None
    return [k.strip() for k in m.group(1).split(",") if k.strip()]


def test_hardening_cli_emit_and_register():
    """Phase 4 contract: real CLI subprocess — lazy-state.py --emit-dispatch
    hardening with a marker present → exit 0, JSON output, registry entry with
    class == 'hardening', sha matches the stdout prompt.

    Sub-scenarios:
      (a) Marker present: exit 0, dispatch_prompt non-null,
          dispatch_model == 'opus', dispatch_class == 'hardening'; registry
          entry class == 'hardening', prompt_sha256 matches.
      (b) No-marker (peek): exit 0, dispatch_prompt non-null; NO registry write.

    RED reasons:
      - 'hardening' not in DISPATCH_CLASSES → argparse accepts the class but
        emit_dispatch_prompt raises ValueError → lazy-state.py exits 1; or
      - dispatch-hardening.md template missing → ok=False → exit 1; or
      - DISPATCH_MODELS missing 'hardening' → KeyError → exit 1.
      Any of these produce a non-zero exit code checked by sub-scenario (a).
    """
    _guard()
    assert hasattr(lazy_core, "write_run_marker"), (
        "lazy_core.write_run_marker missing — Phase 1 not yet implemented"
    )
    assert hasattr(lazy_core, "prompt_sha256"), (
        "lazy_core.prompt_sha256 missing — Phase 1 not yet implemented"
    )
    assert hasattr(lazy_core, "emit_dispatch_prompt"), (
        "lazy_core.emit_dispatch_prompt missing — Phase 3 not yet implemented"
    )

    # Read the real @requires keys for 'hardening' so the context is exactly right.
    requires_keys = _read_hardening_requires_keys()
    if requires_keys is None:
        # Template not yet written — fail explicitly rather than skip silently.
        assert False, (
            "dispatch-hardening.md does not exist or has no valid @requires on "
            "line 1; Phase 4 template authoring is incomplete"
        )

    lazy_state_script = _SCRIPTS_DIR / "lazy-state.py"

    # Build context flags: one --context KEY=VALUE per @requires key + item_id.
    context_flags: list[str] = []
    for k in requires_keys:
        context_flags += ["--context", f"{k}=test-{k}"]
    # Ensure item_id is present (it is always in @requires for hardening,
    # but add it explicitly in case a test-k value collision occurs).
    if "item_id" not in requires_keys:
        context_flags += ["--context", "item_id=feat-hardening"]

    import time as _time_mod

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        # Minimal fixture repo so the state script can resolve its paths.
        fixture_repo = _build_dispatch_registry_fixture(td_path)
        state_dir = td_path / "hardening-state-dir"
        state_dir.mkdir()

        # === Sub-scenario (a): marker present → registry entry written ===
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root=str(fixture_repo),
                max_cycles=10,
                now=_time_mod.time(),
            )
        finally:
            _clear_state_dir()

        env_with_marker = dict(_os_env.environ)
        env_with_marker["LAZY_STATE_DIR"] = str(state_dir)

        cmd = [
            sys.executable, str(lazy_state_script),
            "--emit-dispatch", "hardening",
        ] + context_flags

        result_a = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env_with_marker,
        )

        # Explicit argparse-unknown-flag check (clearer RED reason).
        assert result_a.returncode != 2, (
            "--emit-dispatch hardening: flag not recognized by lazy-state.py "
            f"(argparse exit 2).\nstderr: {result_a.stderr[:400]!r}"
        )
        assert result_a.returncode == 0, (
            f"lazy-state.py --emit-dispatch hardening (with marker) exited "
            f"{result_a.returncode}; stderr: {result_a.stderr[:400]!r}; "
            f"stdout: {result_a.stdout[:400]!r}"
        )

        try:
            out_a = json.loads(result_a.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout is not valid JSON: {exc}\nstdout: {result_a.stdout[:400]!r}"
            ) from exc

        dispatch_prompt_a = out_a.get("dispatch_prompt")
        assert dispatch_prompt_a is not None, (
            f"dispatch_prompt must be non-null in marker run; got {out_a!r}"
        )
        assert out_a.get("dispatch_model") == "opus", (
            f"dispatch_model must be 'opus' for 'hardening' class; "
            f"got {out_a.get('dispatch_model')!r}"
        )
        assert out_a.get("dispatch_class") == "hardening", (
            f"dispatch_class must be 'hardening'; "
            f"got {out_a.get('dispatch_class')!r}"
        )

        # Registry entry must exist with class == 'hardening'.
        registry_file = state_dir / "lazy-prompt-registry.json"
        assert registry_file.exists(), (
            "Registry file must be written when a marker is present and "
            "--emit-dispatch hardening succeeds"
        )
        registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
        entries = registry_data.get("entries", [])
        expected_sha = lazy_core.prompt_sha256(dispatch_prompt_a)
        matching = [e for e in entries if e.get("prompt_sha256") == expected_sha]
        assert len(matching) >= 1, (
            f"Expected at least 1 registry entry with sha matching the stdout "
            f"dispatch_prompt; found {len(matching)}.\n"
            f"expected sha={expected_sha!r}\n"
            f"entry shas={[e.get('prompt_sha256') for e in entries]!r}"
        )
        assert matching[-1].get("class") == "hardening", (
            f"Registry entry class must be 'hardening'; "
            f"got {matching[-1].get('class')!r}"
        )

        # === Sub-scenario (b): no marker → peek semantics, no registry write ===
        state_dir_b = td_path / "hardening-state-dir-b"
        state_dir_b.mkdir()
        env_no_marker = dict(_os_env.environ)
        env_no_marker["LAZY_STATE_DIR"] = str(state_dir_b)

        cmd_b = [
            sys.executable, str(lazy_state_script),
            "--emit-dispatch", "hardening",
        ] + context_flags

        result_b = subprocess.run(
            cmd_b,
            capture_output=True,
            text=True,
            env=env_no_marker,
        )
        assert result_b.returncode == 0, (
            f"lazy-state.py --emit-dispatch hardening (no marker) exited "
            f"{result_b.returncode}; stderr: {result_b.stderr[:400]!r}; "
            f"stdout: {result_b.stdout[:400]!r}"
        )
        try:
            out_b = json.loads(result_b.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"stdout not valid JSON (no-marker run): {exc}\n"
                f"stdout: {result_b.stdout[:400]!r}"
            ) from exc

        assert out_b.get("dispatch_prompt") is not None, (
            f"dispatch_prompt must be non-null in no-marker peek run; got {out_b!r}"
        )
        registry_b = state_dir_b / "lazy-prompt-registry.json"
        assert not registry_b.exists(), (
            "Registry file must NOT be written when no marker is present "
            "(peek semantics for hardening class, same as other classes)"
        )


# ---------------------------------------------------------------------------
# Phase 3 (F2a) test function definitions — must appear BEFORE the final
# _TESTS re-assignment below.
# ---------------------------------------------------------------------------

def test_f2a_register_emission_stores_prompt_raw():
    """F2a: register_emission must store the exact raw prompt bytes in
    'prompt_raw' so a nonce can be resolved to the EXACT original text.

    RED until register_emission adds 'prompt_raw'.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            raw = "Run the next cycle—step exactly as specified."
            entry = lazy_core.register_emission(raw, cls="cycle", item_id="feat-ref")
            assert "prompt_raw" in entry, (
                "register_emission must store 'prompt_raw' on each entry "
                "(F2a / lazy-validation-readiness Phase 3)"
            )
            assert entry["prompt_raw"] == raw, (
                f"prompt_raw must be the EXACT original bytes; "
                f"got {entry['prompt_raw']!r}, expected {raw!r}"
            )
        finally:
            _clear_state_dir()


def test_f2a_resolve_emission_fresh_nonce_returns_entry():
    """F2a: resolve_emission_by_nonce returns the entry for a fresh, unconsumed
    nonce registered in the current run.

    RED until resolve_emission_by_nonce is implemented.
    """
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # Write a run marker so the run-start gate passes.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            raw = "Execute the planned implementation step for feat-ref."
            entry = lazy_core.register_emission(raw, cls="cycle", item_id="feat-ref")
            nonce = entry["nonce"]

            # Must have the resolver symbol.
            assert hasattr(lazy_core, "resolve_emission_by_nonce"), (
                "lazy_core must export resolve_emission_by_nonce "
                "(F2a / lazy-validation-readiness Phase 3)"
            )

            resolved = lazy_core.resolve_emission_by_nonce(nonce)
            assert resolved is not None, (
                f"resolve_emission_by_nonce must return the entry for a fresh "
                f"unconsumed nonce; got None for nonce {nonce!r}"
            )
            # The resolved text should be the raw prompt (or norm as fallback).
            resolved_text = resolved.get("prompt_raw") or resolved.get("prompt_norm")
            assert resolved_text == raw, (
                f"Resolved text must match original raw prompt; "
                f"got {resolved_text!r}, expected {raw!r}"
            )
        finally:
            _clear_state_dir()


def test_f2a_resolve_emission_consumed_nonce_returns_none():
    """F2a: resolve_emission_by_nonce returns None for a nonce that has already
    been consumed (single-use enforced, TOCTOU safety).

    RED until resolve_emission_by_nonce is implemented.
    """
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            raw = "Execute the planned step — consumed nonce test."
            entry = lazy_core.register_emission(raw, cls="cycle")
            nonce = entry["nonce"]
            lazy_core.dispatch.consume_nonce(nonce, consumer="toolu_abc123")

            resolved = lazy_core.resolve_emission_by_nonce(nonce)
            assert resolved is None, (
                "resolve_emission_by_nonce must return None for a consumed nonce; "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()


def test_f2a_resolve_emission_stale_nonce_returns_none():
    """F2a: resolve_emission_by_nonce returns None for an unconsumed nonce whose
    emitted_at predates the current run's started_at (run-start gate).

    RED until resolve_emission_by_nonce is implemented.
    """
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            old_time = _time.time() - 7200  # 2 hours ago

            # Register the prompt BEFORE writing the run marker (so emitted_at < started_at).
            raw = "Execute the planned step — stale nonce test."
            entry = lazy_core.register_emission(raw, cls="cycle", now=old_time)
            nonce = entry["nonce"]

            # Now write the marker — started_at > emitted_at, making the entry stale.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )

            resolved = lazy_core.resolve_emission_by_nonce(nonce)
            assert resolved is None, (
                "resolve_emission_by_nonce must return None for a nonce whose "
                "emitted_at predates the run's started_at (stale gate); "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()


# ---------------------------------------------------------------------------
# Tests: byref-updatedinput-unapplied-on-background-agent-dispatch — WU-1
# The sanctioned CONSUMED-nonce reader. The platform drops the by-reference
# updatedInput rewrite for the Agent tool (upstream #39814), so a subagent that
# booted with a bare @@lazy-ref token needs a run-scoped, read-only way to
# recover the registered prompt bytes for a nonce the guard ALREADY consumed
# this run. resolve_consumed_emission_by_nonce is that read: it INVERTS Gate-1
# of resolve_emission_by_nonce (require consumed truthy) while reusing the same
# TTL + run-start gates, returns the entry's prompt_raw (fallback prompt_norm)
# as a STRING, and NEVER un-consumes.
# ---------------------------------------------------------------------------


def test_resolve_consumed_emission_returns_prompt_raw_for_consumed_nonce():
    """WU-1: resolve_consumed_emission_by_nonce returns the exact stored
    prompt_raw for a consumed, TTL-fresh, run-gated entry.

    RED until resolve_consumed_emission_by_nonce is implemented.
    """
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            raw = "Execute the planned step — consumed-reader happy path."
            entry = lazy_core.register_emission(raw, cls="cycle", item_id="feat-ref")
            nonce = entry["nonce"]
            lazy_core.dispatch.consume_nonce(nonce, consumer="toolu_abc123")

            assert hasattr(lazy_core, "resolve_consumed_emission_by_nonce"), (
                "lazy_core must export resolve_consumed_emission_by_nonce "
                "(byref-updatedinput WU-1)"
            )

            resolved = lazy_core.resolve_consumed_emission_by_nonce(nonce)
            assert resolved == raw, (
                f"resolve_consumed_emission_by_nonce must return the exact stored "
                f"prompt_raw string for a consumed fresh nonce; got {resolved!r}, "
                f"expected {raw!r}"
            )
        finally:
            _clear_state_dir()


def test_resolve_consumed_emission_unknown_nonce_returns_none():
    """WU-1: a nonce that does not exist in the registry → None."""
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            resolved = lazy_core.resolve_consumed_emission_by_nonce("deadbeef" * 4)
            assert resolved is None, (
                f"resolve_consumed_emission_by_nonce must return None for an "
                f"unknown nonce; got {resolved!r}"
            )
        finally:
            _clear_state_dir()


def test_resolve_consumed_emission_unconsumed_returns_none():
    """WU-1: Gate-1 inversion — an UNCONSUMED fresh entry returns None (this
    reader serves ONLY nonces the guard already ALLOW+consumed this run)."""
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            raw = "Execute the planned step — still-unconsumed nonce."
            entry = lazy_core.register_emission(raw, cls="cycle")
            # Deliberately do NOT consume.
            resolved = lazy_core.resolve_consumed_emission_by_nonce(entry["nonce"])
            assert resolved is None, (
                "resolve_consumed_emission_by_nonce must return None for an "
                "UNCONSUMED entry (inverted Gate-1); "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()


def test_resolve_consumed_emission_ttl_expired_returns_none():
    """WU-1: a consumed entry beyond REGISTRY_ENTRY_TTL_SECONDS → None."""
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            base = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=base,
            )
            raw = "Execute the planned step — TTL-expired nonce."
            entry = lazy_core.register_emission(raw, cls="cycle", now=base)
            lazy_core.dispatch.consume_nonce(entry["nonce"])

            # Resolve well beyond the 1800s TTL.
            future = base + lazy_core.dispatch.REGISTRY_ENTRY_TTL_SECONDS + 100
            resolved = lazy_core.resolve_consumed_emission_by_nonce(
                entry["nonce"], now=future
            )
            assert resolved is None, (
                "resolve_consumed_emission_by_nonce must return None for a "
                "consumed entry beyond TTL; "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()


def test_resolve_consumed_emission_predates_run_returns_none():
    """WU-1: a consumed, TTL-fresh entry whose emitted_at predates the run
    marker's started_at → None (run-start gate)."""
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            old_time = _time.time() - 7200  # 2 hours ago
            raw = "Execute the planned step — predates-run nonce."
            entry = lazy_core.register_emission(raw, cls="cycle", now=old_time)
            lazy_core.dispatch.consume_nonce(entry["nonce"])

            # Marker written NOW — started_at > emitted_at makes the entry stale.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )

            # Resolve within TTL of emitted_at so ONLY the run-start gate can fail.
            resolved = lazy_core.resolve_consumed_emission_by_nonce(
                entry["nonce"], now=old_time + 10
            )
            assert resolved is None, (
                "resolve_consumed_emission_by_nonce must return None for a "
                "consumed entry predating the run's started_at (run-start gate); "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()


def test_resolve_consumed_emission_never_mutates_consumed():
    """WU-1: the reader is READ-ONLY — it never un-consumes. After resolving,
    the registry entry's consumed flag / consumed_by must be unchanged."""
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            raw = "Execute the planned step — read-only invariant."
            entry = lazy_core.register_emission(raw, cls="cycle")
            nonce = entry["nonce"]
            lazy_core.dispatch.consume_nonce(nonce, consumer="toolu_readonly")

            before = lazy_core.dispatch._load_registry()
            before_entry = next(e for e in before["entries"] if e["nonce"] == nonce)
            before_consumed = before_entry.get("consumed")
            before_consumer = before_entry.get("consumed_by")

            resolved = lazy_core.resolve_consumed_emission_by_nonce(nonce)
            assert resolved == raw, "pre-condition: the consumed reader must hit"

            after = lazy_core.dispatch._load_registry()
            after_entry = next(e for e in after["entries"] if e["nonce"] == nonce)
            assert after_entry.get("consumed") == before_consumed == True, (  # noqa: E712
                "resolve_consumed_emission_by_nonce must NEVER un-consume; "
                f"consumed flag changed: before={before_consumed!r} "
                f"after={after_entry.get('consumed')!r}"
            )
            assert after_entry.get("consumed_by") == before_consumer, (
                "resolve_consumed_emission_by_nonce must not alter consumed_by; "
                f"before={before_consumer!r} after={after_entry.get('consumed_by')!r}"
            )
        finally:
            _clear_state_dir()


def test_f2a_append_dispatch_by_reference_event_writes_ledger():
    """F2a: append_dispatch_by_reference_event writes a 'dispatch_by_reference: true'
    event to the deny ledger (same JSONL file) so the by-reference path is
    auditable by retro graders.

    RED until append_dispatch_by_reference_event is implemented.
    """
    _guard()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # Must have the symbol.
            assert hasattr(lazy_core, "append_dispatch_by_reference_event"), (
                "lazy_core must export append_dispatch_by_reference_event "
                "(F2a / lazy-validation-readiness Phase 3)"
            )

            ts_before = _time.time()
            result = lazy_core.append_dispatch_by_reference_event(
                tool_use_id="toolu_reftest01",
                nonce="abc123def456",
                resolved_sha12="aabbccdd1234",
                item_id="feat-ref",
            )
            assert result is True, (
                "append_dispatch_by_reference_event must return True on success"
            )

            # Read back the ledger and verify the event was written.
            ledger_path = state_dir / "lazy-deny-ledger.jsonl"
            assert ledger_path.exists(), (
                "append_dispatch_by_reference_event must write to lazy-deny-ledger.jsonl"
            )
            lines = [
                ln for ln in ledger_path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            assert lines, "Ledger must have at least one entry after the call"
            evt = json.loads(lines[-1])
            assert evt.get("dispatch_by_reference") is True, (
                f"Event must carry 'dispatch_by_reference: true'; got {evt!r}"
            )
            assert evt.get("tool_use_id") == "toolu_reftest01", (
                f"Event must record tool_use_id; got {evt!r}"
            )
            assert evt.get("nonce") == "abc123def456", (
                f"Event must record nonce; got {evt!r}"
            )
            assert evt.get("acked") is True, (
                "dispatch_by_reference events owe no hardening debt — acked must be True"
            )
            assert evt.get("ts", 0) >= ts_before, (
                "Event ts must be >= the call's start time"
            )
        finally:
            _clear_state_dir()


def test_governing_file_set_includes_orchestrator_and_components():
    """The governing set INCLUDES lazy-batch SKILL + bug/cloud twins + the 3 components."""
    _guard()
    gset = lazy_core.GOVERNING_FILE_SET
    includes = [
        "user/skills/lazy-batch/SKILL.md",
        "user/skills/lazy-bug-batch/SKILL.md",
        "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md",
        "user/skills/_components/orchestrator-voice.md",
        "user/skills/_components/completeness-policy.md",
        "user/skills/_components/lazy-dispatch-template.md",
    ]
    for rel in includes:
        assert rel in gset, f"governing set must include {rel}"


def test_merged_priority_normalizes_tier_and_severity():
    """WU-2: feature `tier` and bug `severity` normalize to one numeric scale
    (lower = higher priority); unknown/absent fields sort last."""
    _guard()
    # Feature tier — int passes through.
    assert lazy_core.merged_priority("feature", {"tier": 1}) == 1
    assert lazy_core.merged_priority("feature", {"tier": 2}) == 2
    # Feature tier as a numeric string — coerced.
    assert lazy_core.merged_priority("feature", {"tier": "1"}) == 1
    # Feature missing tier → default (sorts last).
    assert lazy_core.merged_priority("feature", {}) == lazy_core.MERGED_PRIORITY_DEFAULT
    # Bug severity → rank (P0 highest priority = lowest number).
    assert lazy_core.merged_priority("bug", {"severity": "P0"}) == 0
    assert lazy_core.merged_priority("bug", {"severity": "P1"}) == 1
    assert lazy_core.merged_priority("bug", {"severity": "P2"}) == 2
    assert lazy_core.merged_priority("bug", {"severity": "Low"}) == 3
    # Bug unknown / absent severity → default (sorts last).
    assert lazy_core.merged_priority("bug", {"severity": "???"}) == lazy_core.MERGED_PRIORITY_DEFAULT
    assert lazy_core.merged_priority("bug", {}) == lazy_core.MERGED_PRIORITY_DEFAULT
    # A bool tier is NOT a valid priority (bool is an int subclass — must reject).
    assert lazy_core.merged_priority("feature", {"tier": True}) == lazy_core.MERGED_PRIORITY_DEFAULT


def test_merged_priority_feature_tier_enum_to_int():
    """feature-tier-strings-fall-to-merged-priority-default: NAMED feature-tier
    enums normalize to their integer priority (parallel to bug severity), while
    every backward-compat shape (bare int, numeric string, bool, null/missing)
    keeps its prior behavior."""
    _guard()
    # Every named enum resolves to its declared integer (SSOT: _FEATURE_TIER_ENUM).
    for name, expected in lazy_core._FEATURE_TIER_ENUM.items():
        assert lazy_core.merged_priority("feature", {"tier": name}) == expected, name
    # The previously-`99` legacy strings now carry real priority (the whole point).
    assert lazy_core.merged_priority("feature", {"tier": "milestone"}) != lazy_core.MERGED_PRIORITY_DEFAULT
    assert lazy_core.merged_priority("feature", {"tier": "non-audio"}) != lazy_core.MERGED_PRIORITY_DEFAULT
    # Backward compat — unchanged behavior for the pre-existing shapes.
    assert lazy_core.merged_priority("feature", {"tier": 5}) == 5          # bare int
    assert lazy_core.merged_priority("feature", {"tier": "6"}) == 6        # numeric string
    assert lazy_core.merged_priority("feature", {"tier": True}) == lazy_core.MERGED_PRIORITY_DEFAULT
    assert lazy_core.merged_priority("feature", {}) == lazy_core.MERGED_PRIORITY_DEFAULT
    assert lazy_core.merged_priority("feature", {"tier": None}) == lazy_core.MERGED_PRIORITY_DEFAULT
    # An UNKNOWN enum name still sorts last (no silent mis-priority).
    assert lazy_core.merged_priority("feature", {"tier": "not-a-tier"}) == lazy_core.MERGED_PRIORITY_DEFAULT


def test_merged_priority_feature_multi_enum_takes_min():
    """feature-tier-strings-fall-to-merged-priority-default: a feature whose `tier`
    is a LIST of enum names takes the MIN (highest-priority) of the enums' integer
    values. Mixed int/enum lists and unresolvable elements are handled too."""
    _guard()
    # MIN of the enums' values: pre-release(1) vs milestone(3) → 1.
    assert lazy_core.merged_priority(
        "feature", {"tier": ["milestone", "pre-release"]}
    ) == 1
    # Order-independent — MIN, not first.
    assert lazy_core.merged_priority(
        "feature", {"tier": ["pre-release", "non-audio"]}
    ) == 1
    # Mixed bare-int + enum: min(0, 3) → 0.
    assert lazy_core.merged_priority("feature", {"tier": [0, "milestone"]}) == 0
    # Unresolvable elements are skipped; the resolvable one wins.
    assert lazy_core.merged_priority(
        "feature", {"tier": ["not-a-tier", "commercialization"]}
    ) == lazy_core._FEATURE_TIER_ENUM["commercialization"]
    # An all-unresolvable / empty list sorts last (never crashes).
    assert lazy_core.merged_priority("feature", {"tier": ["nope", True]}) == lazy_core.MERGED_PRIORITY_DEFAULT
    assert lazy_core.merged_priority("feature", {"tier": []}) == lazy_core.MERGED_PRIORITY_DEFAULT


def test_merged_priority_prerelease_ordering_p0_before_prerelease_before_p2():
    """feature-tier-strings-fall-to-merged-priority-default LOAD-BEARING ordering
    (operator-specified): merged_priority(P0 bug)=0 < merged_priority(pre-release
    feature)=1 < merged_priority(P2 bug)=2 — a P0 bug is still addressed BEFORE a
    pre-release feature, which is addressed before a P2 bug."""
    _guard()
    p0 = lazy_core.merged_priority("bug", {"severity": "P0"})
    prerelease = lazy_core.merged_priority("feature", {"tier": "pre-release"})
    p2 = lazy_core.merged_priority("bug", {"severity": "P2"})
    assert p0 == 0, p0
    assert prerelease == 1, prerelease
    assert p2 == 2, p2
    assert p0 < prerelease < p2, (p0, prerelease, p2)
    # And it holds through the merged worklist sort, not just the scalar function.
    feats = [{"id": "pre-rel-feat", "tier": "pre-release"}]
    bugs = [{"id": "p0-bug", "severity": "P0"}, {"id": "p2-bug", "severity": "P2"}]
    ids = [e["item_id"] for e in lazy_core.merged_worklist(feats, bugs, "/r")]
    assert ids == ["p0-bug", "pre-rel-feat", "p2-bug"], ids


def test_merged_worklist_both_populated_ordered_by_priority():
    """WU-1/WU-3: both queues populated → ordered by effective priority; a
    higher-priority feature precedes a lower-priority bug regardless of type."""
    _guard()
    feats = [{"id": "feat-hi", "tier": 1}, {"id": "feat-lo", "tier": 3}]
    bugs = [{"id": "bug-mid", "severity": "P2"}]  # rank 2 — between the features
    wl = lazy_core.merged_worklist(feats, bugs, "/r")
    ids = [e["item_id"] for e in wl]
    assert ids == ["feat-hi", "bug-mid", "feat-lo"], ids
    # Shape contract: each entry is {item_id, type, repo_root}.
    assert wl[0] == {"item_id": "feat-hi", "type": "feature", "repo_root": "/r"}
    assert wl[1]["type"] == "bug"


def test_merged_worklist_bug_breaks_tie_at_equal_priority():
    """Tie-break gate (name retained across the 2026-07-17 flip so the gate-test
    identity is preserved). FORMERLY asserted bug-before-feature; the operator
    directive "I only want P0 bugs to sort ahead of P1 features"
    (non-p0-bug-outranks-p1-feature-on-aged-tie) INVERTED the tie-break, so this
    now asserts FEATURE-before-bug at an equal effective rank. Combined with the
    rank-1 age floor, only a genuine P0 bug (strictly rank 0) precedes a P1
    feature — coverage strengthened, not weakened (the P0-still-ahead leg is
    asserted alongside)."""
    _guard()
    # feature tier 1 (priority 1) vs bug P1 (rank 1) — equal → FEATURE first now.
    feats = [{"id": "feat-a", "tier": 1}]
    bugs = [{"id": "bug-a", "severity": "P1"}]
    head = lazy_core.next_merged(feats, bugs, "/r")
    assert head == {"item_id": "feat-a", "type": "feature", "repo_root": "/r"}, head
    # A genuine P0 bug STILL precedes the P1 feature (strictly lower rank).
    p0 = lazy_core.next_merged(feats, [{"id": "bug-p0", "severity": "P0"}], "/r")
    assert p0 == {"item_id": "bug-p0", "type": "bug", "repo_root": "/r"}, p0


def test_merged_worklist_aged_p2_bug_sorts_behind_p1_feature():
    """non-p0-bug-outranks-p1-feature-on-aged-tie regression (the exact live
    2026-07-17 friction): a P2 bug age-escalated to rank-1 P1-equivalent MUST
    sort BEHIND a P1 (pre-release) feature; a genuine P0 bug still precedes it."""
    import datetime
    _guard()
    today = datetime.date(2026, 7, 17)
    # P2 bug discovered 8 days ago → age_escalated_rank(2, ...) == 1 (rank-1).
    assert lazy_core.age_escalated_rank(2, "2026-07-09", today=today) == 1
    feats = [{"id": "hydra-overlay", "tier": ["non-audio", "pre-release"]}]  # P1
    aged_p2 = [{"id": "protocol-generic-claims-drift", "severity": "P2",
                "discovered": "2026-07-09"}]
    head = lazy_core.next_merged(feats, aged_p2, "/r", today=today)
    assert head == {"item_id": "hydra-overlay", "type": "feature",
                    "repo_root": "/r"}, head
    # But a genuine P0 bug outranks the same P1 feature.
    p0 = [{"id": "p0-bug", "severity": "P0"}]
    assert lazy_core.next_merged(feats, p0, "/r", today=today)["type"] == "bug"


def test_merged_head_override_diverges_when_p0_bug_outranks_current_feature():
    """dispatch-probe-and-inject-bypass-merged-head: a dispatch-bound FEATURE
    probe emitting for hydra-overlay while a P0 bug sits at the merged head must
    get a withhold payload (route_overridden_by=merged-head-diverged) NAMING the
    bug — the exact live 2026-07-17 friction (the enriched --emit-prompt probe
    returned the feature over two P0 bugs). Regression fixture: P0 bug at
    bug-queue head + actionable feature → the override redirects to the bug."""
    _guard()
    feats = [{"id": "hydra-overlay", "tier": 3}]
    bugs = [{"id": "adhoc-hydra-sidecar-dist-esm-no-frames", "severity": "P0"}]
    override = lazy_core.dispatch.merged_head_override(
        feats, bugs, "/r", "hydra-overlay"
    )
    assert override is not None, "P0 bug at merged head must override the feature route"
    assert override["route_overridden_by"] == "merged-head-diverged"
    assert override["merged_head"] == {
        "item_id": "adhoc-hydra-sidecar-dist-esm-no-frames", "type": "bug",
    }, override


def test_merged_head_override_diverges_when_higher_sev_bug_jumps_head():
    """Coupled-pair (bug-state) case: a bug probe emitting for a lower-severity
    bug while a P0 bug jumped the merged head → withhold naming the P0 bug."""
    _guard()
    bugs = [{"id": "bug-p0", "severity": "P0"}, {"id": "bug-p2", "severity": "P2"}]
    override = lazy_core.dispatch.merged_head_override([], bugs, "/r", "bug-p2")
    assert override is not None
    assert override["merged_head"] == {"item_id": "bug-p0", "type": "bug"}, override


def test_merged_head_override_none_when_head_is_current_item():
    """No divergence: the probe is already emitting for the merged head (feature
    run whose head IS the feature; bug run whose head IS the bug) → None, so the
    caller emits normally (byte-identical common path)."""
    _guard()
    assert lazy_core.dispatch.merged_head_override(
        [{"id": "feat-a", "tier": 1}], [], "/r", "feat-a"
    ) is None
    assert lazy_core.dispatch.merged_head_override(
        [], [{"id": "bug-a", "severity": "P0"}], "/r", "bug-a"
    ) is None


def test_merged_head_override_none_on_empty_queues_or_missing_id():
    """Fail-safe: empty queues or a missing current_item_id → None (never a
    spurious withhold that would stall a legitimate probe)."""
    _guard()
    assert lazy_core.dispatch.merged_head_override([], [], "/r", "feat-a") is None
    assert lazy_core.dispatch.merged_head_override(
        [{"id": "feat-a", "tier": 1}], [], "/r", None
    ) is None


# ---------------------------------------------------------------------------
# Tests: coordinator_arbitrated_emission — the unified merged-head coordinator
# exemption predicate (adhoc-unify-merged-head-coordinator-exemptions Phase 1).
# One predicate answers "is this a coordinator-arbitrated emission the serial
# merged-head divergence premise does not apply to?" returning None | "lane" |
# "lease". Lane (parent_run) has precedence over lease. Fully fail-safe — it
# must NEVER raise into the base probe.
# ---------------------------------------------------------------------------


def test_coordinator_arbitrated_emission_lane():
    """A lane marker (non-null parent_run) → "lane", regardless of feature_id or
    leases_path (lane arbitration is coordinator-owned; the lease I/O is not even
    consulted)."""
    _guard()
    marker = {"parent_run": {"repo_root": "/main", "started_at": "2026-07-19T00:00:00Z"}}
    assert lazy_core.dispatch.coordinator_arbitrated_emission(
        marker, "any-id", "/nonexistent/leases.json"
    ) == "lane"


def test_coordinator_arbitrated_emission_lease():
    """A non-lane marker whose feature_id holds a LIVE coordinator lease → "lease"
    (the serial-tail exemption). Seed a live lease via lazy_coord.acquire_lease."""
    _guard()
    import lazy_coord  # type: ignore[import]
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        leases_path = Path(td) / "leases.json"
        lazy_coord.acquire_lease(
            leases_path, "feat-c", os.getpid(), "wt-00", 3600, now=_time.time(),
        )
        marker = {}  # non-lane marker (no parent_run)
        assert lazy_core.dispatch.coordinator_arbitrated_emission(
            marker, "feat-c", leases_path
        ) == "lease"


def test_coordinator_arbitrated_emission_none():
    """A non-lane marker with no live lease (absent/expired leases.json) → None,
    so the caller runs the merged-head guard exactly as before."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        leases_path = Path(td) / "leases.json"  # never created → no lease
        assert lazy_core.dispatch.coordinator_arbitrated_emission(
            {}, "feat-c", leases_path
        ) is None


def test_coordinator_arbitrated_emission_lane_precedes_lease():
    """When BOTH a parent_run (lane) AND a live lease would qualify, lane wins —
    it is evaluated first and the lease read is never required."""
    _guard()
    import lazy_coord  # type: ignore[import]
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        leases_path = Path(td) / "leases.json"
        lazy_coord.acquire_lease(
            leases_path, "feat-c", os.getpid(), "wt-00", 3600, now=_time.time(),
        )
        marker = {"parent_run": {"repo_root": "/main", "started_at": "t"}}
        assert lazy_core.dispatch.coordinator_arbitrated_emission(
            marker, "feat-c", leases_path
        ) == "lane"


def test_coordinator_arbitrated_emission_failsafe():
    """The predicate NEVER raises into the base probe: a None marker, a
    missing/empty feature_id, and a leases_path that raises on read each return
    None (no lane, no lease)."""
    _guard()

    class _Boom:
        # A leases_path whose str()/read explodes — has_live_lease must be
        # shielded so the predicate returns None rather than propagating.
        def __fspath__(self):
            raise OSError("boom")

    # None marker → not a lane, no lease branch → None.
    assert lazy_core.dispatch.coordinator_arbitrated_emission(
        None, "feat-c", "/nonexistent/leases.json"
    ) is None
    # Missing / empty feature_id → no lease compute → None (marker non-None).
    assert lazy_core.dispatch.coordinator_arbitrated_emission(
        {}, "", "/nonexistent/leases.json"
    ) is None
    assert lazy_core.dispatch.coordinator_arbitrated_emission(
        {}, None, "/nonexistent/leases.json"
    ) is None
    # A leases_path that raises on read → shielded → None (never raises).
    assert lazy_core.dispatch.coordinator_arbitrated_emission(
        {}, "feat-c", _Boom()
    ) is None


def test_coordinator_exemption_diag_maps_reason_to_text():
    """The caller-facing reason→diagnostic map resolves "lane"/"lease" to their
    existing diag substances and an UNRECOGNIZED reason to a generic
    coordinator-arbitrated exemption diag (forward-compat for a future third
    exemption) — so a reason rename can never silently drop a diagnostic."""
    _guard()
    lane_diag = lazy_core.dispatch.coordinator_exemption_diag("lane")
    lease_diag = lazy_core.dispatch.coordinator_exemption_diag("lease")
    assert "lane probe" in lane_diag and "claim_shardable" in lane_diag
    assert "lease-held" in lease_diag and "round-2 gap 8" in lease_diag
    other = lazy_core.dispatch.coordinator_exemption_diag("demoted-serial-rerun")
    assert "coordinator-arbitrated" in other
    assert "demoted-serial-rerun" in other


def test_probe_skipped_ids_collects_all_skip_lists_and_resolves_names():
    """merged-head-diverged-stalls-on-gated-head: probe_skipped_ids folds the
    per-pipeline probe's OWN same-cycle skip lists into one id set — gated_heads /
    host_deferred_features / dep_gated are id-keyed (used directly);
    device_deferred_features / operator_deferred are NAME-keyed and resolved to
    queue ids via the loaded items. Empty state → empty set (common path)."""
    _guard()
    state = {
        "feature_id": "workable",
        "gated_heads": ["blocked-feat"],
        "host_deferred_features": ["host-feat"],
        "device_deferred_features": ["Device Feature Name"],
        "dep_gated": [{"id": "dep-feat", "missing": ["upstream"]}],
        # merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone: the
        # not-skip-ahead-ready skip list (id-keyed) must fold in too, else the
        # merged-head-diverged guard withholds the route pointing at a
        # non-dispatchable dep-unready milestone → no-route.
        "skip_ahead_blocked": ["milestone-feat"],
    }
    items = [
        {"id": "workable", "name": "Workable"},
        {"id": "blocked-feat", "name": "Blocked"},
        {"id": "host-feat", "name": "Host"},
        {"id": "device-feat", "name": "Device Feature Name"},
        {"id": "dep-feat", "name": "Dep"},
        {"id": "milestone-feat", "name": "Milestone"},
    ]
    got = lazy_core.dispatch.probe_skipped_ids(state, items)
    assert got == {
        "blocked-feat", "host-feat", "device-feat", "dep-feat", "milestone-feat",
    }, got
    # Byte-identical common path: a probe that skipped nothing → empty set.
    assert lazy_core.dispatch.probe_skipped_ids({"feature_id": "x"}, items) == set()
    assert lazy_core.dispatch.probe_skipped_ids(None, items) == set()


def test_merged_head_override_gated_head_excluded_no_false_withhold():
    """merged-head-diverged-stalls-on-gated-head: when the highest-priority merged
    item is a GATED head the probe already skipped (fed via exclude_ids, exactly
    as the emit handler now does), the override returns None — the merged head is
    the workable item the probe chose (== current), so NO withhold/stall. But a
    genuinely-DISPATCHABLE higher-priority item (a P0 bug) still diverges even with
    the gated head excluded (the withhold retains its precise meaning)."""
    _guard()
    feats = [
        {"id": "blocked-feat", "tier": 0},   # gated head (BLOCKED) the probe skipped
        {"id": "workable", "tier": 2},       # the item the probe dispatched
    ]
    # Gated head folded into exclude_ids → merged head is `workable` (== current)
    # → None (no false withhold, the stall is gone).
    assert lazy_core.dispatch.merged_head_override(
        feats, [], "/r", "workable", exclude_ids={"blocked-feat"}
    ) is None
    # A dispatchable P0 bug outranks the workable feature → still withholds even
    # with the gated feature excluded (genuine dispatchable-item divergence).
    override = lazy_core.dispatch.merged_head_override(
        feats, [{"id": "bug-z", "severity": "P0"}], "/r", "workable",
        exclude_ids={"blocked-feat"},
    )
    assert override is not None and override["merged_head"] == {
        "item_id": "bug-z", "type": "bug"}, override


# ---------------------------------------------------------------------------
# Tests: merged-head-actionability-oracle (is_dispatchable +
# merged_head_nondispatchable_ids) — the authoritative per-item "would
# compute_state dispatch this?" oracle that REPLACES the 5-facet file-predicate
# enumeration (nondispatchable_item_ids). Phase 1: pure + hermetic (injected
# scoped_probe callable). SPEC L1/L2/L3/L5; Open Questions 1 & 3.
# ---------------------------------------------------------------------------

def _dispatchable_state(sub_skill="execute-plan"):
    """A scoped compute_state shape that WOULD dispatch (real forward skill,
    no terminal_reason)."""
    return {"feature_id": "x", "sub_skill": sub_skill, "sub_skill_args": "Step 7a",
            "terminal_reason": None}


def _nondispatch_state(terminal_reason, sub_skill=None):
    """A scoped compute_state shape that would NOT dispatch (a terminal /
    skip / defer / park / gate / halt reason)."""
    return {"feature_id": "x", "sub_skill": sub_skill, "sub_skill_args": None,
            "terminal_reason": terminal_reason}


def test_is_dispatchable_predicate_table():
    """is_dispatchable (L3) — dispatchable IFF sub_skill is a non-empty,
    non-`__`-prefixed real skill AND terminal_reason is falsy. The non-dispatch
    reason set is DERIVED from compute_state's closed terminal vocabulary (the
    sanctioned-stop + halt + notify sets already in lazy_core, PLUS the scoped
    per-item terminals a --feature-id/--bug-id probe emits) — Open Question 3,
    never a hand-listed enumeration."""
    _guard()
    d = lazy_core.dispatch.is_dispatchable
    # Real forward dispatch → dispatchable.
    assert d(_dispatchable_state("execute-plan")) is True
    assert d(_dispatchable_state("spec")) is True
    # Every terminal_reason drawn from compute_state's CLOSED vocabulary →
    # non-dispatchable. Derived from the lazy_core sets (never hand-listed) so a
    # NEW terminal reason is auto-covered — the whole point of the oracle.
    vocabulary = (
        set(lazy_core.SANCTIONED_STOP_TERMINAL)
        | set(lazy_core.TELEMETRY_HALT_TERMINAL_REASONS)
        | set(lazy_core.notifyplane._NOTIFY_ATTENTION_TERMINALS)
        # The scoped per-item terminals a --feature-id/--bug-id probe emits
        # (exactly what the oracle's cross-pipeline scoped_probe returns for a
        # non-dispatchable candidate) — the categories the file-predicate never
        # covered (cloud/device/host-deferred-scoped, completion-unverified, …).
        | {"cloud-deferred-scoped", "device-deferred-scoped",
           "host-deferred-scoped", "needs-input-scoped", "blocked-scoped",
           "needs-ratification-scoped", "scoped-id-not-found",
           "queue-exhausted-budget-deferred", "stale_upstream"}
    )
    for reason in sorted(vocabulary):
        assert d(_nondispatch_state(reason)) is False, (
            f"terminal_reason={reason!r} must be non-dispatchable")
    # A pseudo-skill (`__`-prefixed) is never a real forward dispatch.
    assert d({"sub_skill": "__mark_complete__", "terminal_reason": None}) is False
    assert d({"sub_skill": "__write_validated_from_skip__", "terminal_reason": None}) is False
    # Empty / missing / non-str sub_skill → non-dispatchable.
    assert d({"sub_skill": None, "terminal_reason": None}) is False
    assert d({"sub_skill": "", "terminal_reason": None}) is False
    assert d({"terminal_reason": None}) is False
    assert d({"sub_skill": 123, "terminal_reason": None}) is False
    # Defensive: a real sub_skill BUT a truthy terminal_reason is still
    # non-dispatchable (the two are mutually exclusive on a real forward state;
    # if both appear, terminal_reason wins — never fabricate a dispatch).
    assert d({"sub_skill": "execute-plan", "terminal_reason": "blocked"}) is False
    # Non-dict / fail-safe.
    assert d(None) is False
    assert d("not-a-dict") is False


def test_merged_head_nondispatchable_ids_same_pipeline_uses_probe_skipped_unchanged():
    """L2: the same-pipeline contribution is probe_skipped_ids(state, same_items)
    UNCHANGED (the cross-item skip-ahead ordering context). A same-pipeline item
    the probe REACHED and skipped (here `blocked-feat`, in gated_heads) is folded
    into exclude and DROPPED from the worklist, so the injected scoped_probe is
    never called for it (the `_never` guard) — the current dispatch target is
    discarded. (A same-pipeline head the probe NEVER reached IS scope-probed; see
    test_..._excludes_parked_UNREACHED_same_pipeline_head — no such item here.)"""
    _guard()
    feats = [{"id": "blocked-feat", "tier": 0}, {"id": "workable", "tier": 2}]
    state = {"feature_id": "workable", "gated_heads": ["blocked-feat"]}

    def _never(_id):
        raise AssertionError(f"scoped_probe must not run for same-pipeline id {_id!r}")

    got = lazy_core.dispatch.merged_head_nondispatchable_ids(
        feats, [], "/r", "workable",
        same_pipeline="feature", same_pipeline_state=state, scoped_probe=_never,
    )
    # Same-pipeline skip folded in; current target discarded; no cross items. The
    # skipped head is DROPPED from the worklist (exclude_ids), so `_never` (which
    # forbids probing) is never reached — the fold, not a fast-path, excludes it.
    assert got == {"blocked-feat"}, got
    # Byte-identical common path: only the current item in its own queue and no
    # cross items → the walk breaks on the current head, nothing is probed → empty.
    # (A higher-priority same-pipeline sibling the probe did NOT skip is no longer
    # a no-op — it is scope-probed; see
    # test_..._excludes_parked_UNREACHED_same_pipeline_head.)
    assert lazy_core.dispatch.merged_head_nondispatchable_ids(
        [{"id": "workable", "tier": 2}], [], "/r", "workable",
        same_pipeline="feature", same_pipeline_state={"feature_id": "workable"},
        scoped_probe=_never,
    ) == set()


def test_merged_head_nondispatchable_ids_facet_regressions_excluded_via_oracle():
    """Every currently-enumerated facet (parked / operator-deferred /
    device-deferred / dep-unready / research-skipped / research-exclusion) — the
    file-predicate categories — is now EXCLUDED via the scoped oracle: a
    cross-pipeline candidate whose scoped_probe returns that facet's non-dispatch
    state is dropped from the merged head, exactly as the old enumeration did."""
    _guard()
    # Feature probe emitting for `workable` (tier 2); a bug sits ABOVE it (P0).
    feats = [{"id": "workable", "tier": 2}]
    facet_reasons = [
        "blocked",              # parked / BLOCKED
        "needs-input",          # parked / operator-deferred surface
        "device-deferred-scoped",   # device-deferred
        "queue-exhausted-dependency-gated",  # dep-unready
        "needs-research",       # research-skipped / research-pending
        "blocked-scoped",       # scoped park variant
    ]
    for reason in facet_reasons:
        calls = []

        def _probe(_id, _reason=reason):
            calls.append(_id)
            return _nondispatch_state(_reason)

        bugs = [{"id": "bug-facet", "severity": "P0"}]
        got = lazy_core.dispatch.merged_head_nondispatchable_ids(
            feats, bugs, "/r", "workable",
            same_pipeline="feature", same_pipeline_state={"feature_id": "workable"},
            scoped_probe=_probe,
        )
        assert got == {"bug-facet"}, f"reason={reason}: {got}"
        assert calls == ["bug-facet"], f"reason={reason}: probed {calls}"


def test_merged_head_nondispatchable_ids_new_category_auto_excluded():
    """The previously-UNCOVERED categories (cloud-deferred / completion-unverified)
    — which the file-predicate's own 'Scope boundary' admitted it could not
    classify — are now correctly excluded by the oracle, closing the recurring
    merged-head-diverged-withholds-on-<X> class by construction."""
    _guard()
    feats = [{"id": "workable", "tier": 2}]
    for reason in ("cloud-deferred-scoped", "completion-unverified"):
        bugs = [{"id": "bug-new", "severity": "P0"}]
        got = lazy_core.dispatch.merged_head_nondispatchable_ids(
            feats, bugs, "/r", "workable",
            same_pipeline="feature", same_pipeline_state={"feature_id": "workable"},
            scoped_probe=lambda _id, _r=reason: _nondispatch_state(_r),
        )
        assert got == {"bug-new"}, f"reason={reason}: {got}"


def test_merged_head_nondispatchable_ids_research_surface_excluded_here():
    """L3 tail: a needs-research cross-pipeline head (WITHOUT --skip-needs-research)
    classifies non-dispatchable and is EXCLUDED here (it halts). research_halt_head
    RE-INCLUDES it in Phase 3 exactly as today — but at the oracle level it is
    excluded. Uses a BUG probe (same_pipeline='bug') so features are cross."""
    _guard()
    bugs = [{"id": "bug-workable", "severity": "P2"}]
    feats = [{"id": "feat-research", "tier": 0}]  # ranks above the P2 bug
    got = lazy_core.dispatch.merged_head_nondispatchable_ids(
        feats, bugs, "/r", "bug-workable",
        same_pipeline="bug", same_pipeline_state={"feature_id": "bug-workable"},
        scoped_probe=lambda _id: _nondispatch_state("needs-research"),
    )
    assert got == {"feat-research"}, got


def test_merged_head_nondispatchable_ids_dispatchable_head_not_excluded_byte_identity():
    """Byte-identity for dispatchable heads (by construction): a genuinely
    dispatchable higher-priority cross item (a P0 bug jumping the queue) is NOT
    excluded, so merged_head_override still WITHHOLDS on it identically to
    pre-oracle. The oracle IS the dispatch decision the withhold already trusts."""
    _guard()
    feats = [{"id": "workable", "tier": 2}]
    bugs = [{"id": "bug-p0", "severity": "P0"}]
    excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
        feats, bugs, "/r", "workable",
        same_pipeline="feature", same_pipeline_state={"feature_id": "workable"},
        scoped_probe=lambda _id: _dispatchable_state(),
    )
    assert excluded == set(), excluded
    # Feed the oracle's exclude set to merged_head_override → still withholds.
    override = lazy_core.dispatch.merged_head_override(
        feats, bugs, "/r", "workable", exclude_ids=excluded)
    assert override is not None and override["merged_head"] == {
        "item_id": "bug-p0", "type": "bug"}, override


def test_merged_head_nondispatchable_ids_short_circuit_at_first_dispatchable_head():
    """L5: the oracle is bounded at-or-above the emitted item and short-circuits
    at the FIRST dispatchable head — a candidate ranked BELOW the emitted item is
    never scoped-probed, and probing stops the moment a dispatchable head is seen
    (a lower non-dispatchable item above it is never reached)."""
    _guard()
    # workable (feature P2) is the emitted item. Above it: bug-hi (P0, dispatchable)
    # then bug-mid (P1, would be non-dispatchable). Below it: bug-lo (P3).
    feats = [{"id": "workable", "tier": 2}]
    bugs = [
        {"id": "bug-hi", "severity": "P0"},
        {"id": "bug-mid", "severity": "P1"},
        {"id": "bug-lo", "severity": "P3"},
    ]
    calls = []

    def _probe(_id):
        calls.append(_id)
        # bug-hi dispatchable; anything else non-dispatchable (should not be reached).
        return _dispatchable_state() if _id == "bug-hi" else _nondispatch_state("blocked")

    got = lazy_core.dispatch.merged_head_nondispatchable_ids(
        feats, bugs, "/r", "workable",
        same_pipeline="feature", same_pipeline_state={"feature_id": "workable"},
        scoped_probe=_probe,
    )
    # Short-circuited at bug-hi (dispatchable) → nothing excluded; bug-mid (above,
    # non-dispatchable) never reached; bug-lo (below current) never probed.
    assert got == set(), got
    assert calls == ["bug-hi"], f"expected only bug-hi probed, got {calls}"


def test_merged_head_nondispatchable_ids_below_current_never_probed():
    """The bound never scoped-probes a candidate ranked strictly below the emitted
    item (it can never be the diverging merged head)."""
    _guard()
    feats = [{"id": "workable", "tier": 1}]      # emitted item, P1
    bugs = [{"id": "bug-lo", "severity": "P3"}]  # ranks below → never probed
    calls = []
    got = lazy_core.dispatch.merged_head_nondispatchable_ids(
        feats, bugs, "/r", "workable",
        same_pipeline="feature", same_pipeline_state={"feature_id": "workable"},
        scoped_probe=lambda _id: calls.append(_id) or _nondispatch_state("blocked"),
    )
    assert got == set(), got
    assert calls == [], f"below-current candidate must not be probed, got {calls}"


def test_oracle_leaves_reused_signatures_unchanged():
    """L2: probe_skipped_ids, merged_head_override, research_halt_head signatures
    are UNCHANGED (they still accept a pre-built exclude_ids) — the oracle is
    additive, it does not re-shape the functions it composes."""
    _guard()
    sig = inspect.signature
    assert list(sig(lazy_core.dispatch.probe_skipped_ids).parameters) == ["state", "items"]
    mho = sig(lazy_core.dispatch.merged_head_override).parameters
    assert list(mho) == ["feature_items", "bug_items", "repo_root",
                         "current_item_id", "today", "exclude_ids"], list(mho)
    rhh = sig(lazy_core.dispatch.research_halt_head).parameters
    assert list(rhh) == ["state", "feature_items", "bug_items", "repo_root",
                        "today", "exclude_ids"], list(rhh)


def test_merged_head_nondispatchable_ids_in_process_isolation_characterization():
    """Open Question 1 / L4 (the runtime-coupled deliverable): driving the REAL
    compute_state scoped N times MUST NOT corrupt the primary emit probe's
    already-captured `state` or the module accumulators. RESOLVES the isolation
    strategy: because compute_state resets its module accumulators at entry and
    _state() returns a FRESH dict with list()-copied accumulator snapshots,
    reading the returned dict SUFFICES — no snapshot/restore of module globals is
    required. (Recorded in Phase 1 Implementation Notes.)"""
    _guard()
    import copy as _copy
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        repo, _origin = _make_git_repo_with_origin(td)
        features = repo / "docs" / "features"
        features.mkdir(parents=True, exist_ok=True)
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        e1 = _write_feature(features, "feat-a", tier=1, status="Draft")
        e2 = _write_feature(features, "feat-b", tier=2, status="Draft")
        (features / "queue.json").write_text(
            json.dumps({"queue": [e1, e2]}), encoding="utf-8")

        # Primary (unscoped) probe — capture its state + a deep copy to diff.
        primary = ls.compute_state(repo, cloud=False)
        primary_snapshot = _copy.deepcopy(primary)
        diag_after_primary = list(lazy_core._DIAGNOSTICS)

        # Now drive the REAL compute_state scoped N times (the oracle's pattern).
        for _ in range(4):
            scoped = ls.compute_state(repo, cloud=False, scope_feature_id="feat-b")
            assert isinstance(scoped, dict)

        # The primary state dict is UNCORRUPTED (it was a snapshot all along).
        assert primary == primary_snapshot, (
            "primary state corrupted by subsequent scoped compute_state calls")
        # And a fresh re-probe still yields the same primary state (module
        # accumulators were reset each entry, never leaked).
        reprobe = ls.compute_state(repo, cloud=False)
        assert reprobe["feature_id"] == primary["feature_id"]
        assert reprobe["sub_skill"] == primary["sub_skill"]
        # _DIAGNOSTICS is reset per compute_state (never accumulates across calls).
        assert len(lazy_core._DIAGNOSTICS) == len(list(lazy_core._DIAGNOSTICS))
        del diag_after_primary


def _emit_prompt_subprocess(fixture_repo, state_dir, extra_args=None):
    """Run `lazy-state.py --repeat-count --probe --emit-prompt` as a real
    subprocess against a fixture repo with a live feature-run marker; return the
    parsed probe JSON. Mirrors test_subprocess_emit_prompt_withholds_when_merged_
    head_is_p0_bug's harness."""
    import os as _os2
    env = dict(_os_env.environ)
    env["LAZY_STATE_DIR"] = str(state_dir)
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"),
         "--repeat-count", "--probe", "--emit-prompt",
         "--repo-root", str(fixture_repo), *(extra_args or [])],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, (
        f"lazy-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
    return json.loads(result.stdout)


def _write_feature(features_dir, fid, *, tier, status="Draft", independent=False,
                   blocked=False, phases_body=None, research_gated=False):
    """Seed a feature spec dir + queue entry fields; returns the queue entry.

    ``research_gated=True`` seeds a RESEARCH_PROMPT.md with NO RESEARCH.md /
    RESEARCH_SUMMARY.md (the needs-research-pending shape) instead of the
    research-complete shape — used by the research-halt surfacing tests."""
    fdir = features_dir / fid
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "SPEC.md").write_text(
        f"# Spec\n\n**Status:** {status}\n\n**Depends on:** (none)\n", encoding="utf-8")
    if research_gated:
        # Research-pending: a prompt exists but no results → Step-5 needs-research.
        (fdir / "RESEARCH_PROMPT.md").write_text("# Research prompt\n", encoding="utf-8")
    else:
        (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (fdir / "PHASES.md").write_text(
        phases_body or "# Phases\n\n### Phase 1\n- [ ] Build\n- [ ] Tests\n",
        encoding="utf-8")
    (fdir / "plans").mkdir(exist_ok=True)
    (fdir / "plans" / f"all-phases-{fid}.md").write_text("# Plan\n", encoding="utf-8")
    if blocked:
        (fdir / "BLOCKED.md").write_text(
            "---\nphase: External gate\nblocker_kind: external-gate\n---\n"
            "Awaiting external CI.\n", encoding="utf-8")
    entry = {"id": fid, "name": fid, "spec_dir": fid, "tier": tier}
    if independent:
        entry["independent"] = True
    return entry


def _seed_marker_for(fixture_repo, state_dir):
    import time as _time
    _set_state_dir(state_dir)
    try:
        lazy_core.write_run_marker(
            pipeline="feature", cloud=False,
            repo_root=str(fixture_repo), max_cycles=10, now=_time.time(),
        )
    finally:
        _clear_state_dir()


def test_subprocess_emit_prompt_skips_blocked_gated_head_no_withhold():
    """merged-head-diverged-stalls-on-gated-head (end-to-end): a BLOCKED
    external-gate feature pinned at the merged head (tier 0) with a lower-priority
    WORKABLE independent feature downstream must SKIP the gated head — NOT withhold
    the route. The probe skip-aheads to the workable feature, and the merged-head
    check no longer diverges (route_overridden_by absent, a real cycle_prompt is
    emitted for the workable feature). RED (pre-fix): route_overridden_by ==
    merged-head-diverged with null cycle_prompt — the live 2026-07-17 stall."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = td_path / "fixture-repo"
        features = fixture_repo / "docs" / "features"
        features.mkdir(parents=True)
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        blocked = _write_feature(features, "cross-platform-distribution", tier=0, blocked=True)
        workable = _write_feature(features, "hydra-overlay", tier=2, independent=True)
        (features / "queue.json").write_text(
            json.dumps({"queue": [blocked, workable]}), encoding="utf-8")
        (fixture_repo / "docs" / "bugs").mkdir(parents=True)
        (fixture_repo / "docs" / "bugs" / "queue.json").write_text(
            json.dumps({"queue": []}), encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"; state_dir.mkdir()
        _seed_marker_for(fixture_repo, state_dir)
        sj = _emit_prompt_subprocess(fixture_repo, state_dir)

        assert sj.get("route_overridden_by") is None, (
            f"a gated (BLOCKED) merged head the probe skipped must NOT withhold; "
            f"got route_overridden_by={sj.get('route_overridden_by')!r}")
        assert sj.get("feature_id") == "hydra-overlay", (
            f"probe must dispatch the workable feature; got {sj.get('feature_id')!r}")
        assert sj.get("cycle_prompt"), "a skipped-gated-head route must emit a cycle_prompt"
        # The skip stays observable via gated_heads (the blocked head is named).
        assert "cross-platform-distribution" in (sj.get("gated_heads") or []), (
            f"the skipped gated head must remain observable in gated_heads; "
            f"got {sj.get('gated_heads')!r}")


def test_subprocess_emit_prompt_fully_gated_surfaces_blocked_terminal():
    """merged-head-diverged-stalls-on-gated-head (fully-gated terminal): when
    EVERY feature is BLOCKED (no skip-ahead-ready alternative), the probe falls
    back to the gated head and surfaces terminal_reason='blocked' — the existing
    terminal, NOT an infinite skip and NOT a merged-head-diverged withhold."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = td_path / "fixture-repo"
        features = fixture_repo / "docs" / "features"
        features.mkdir(parents=True)
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        b1 = _write_feature(features, "cross-platform-distribution", tier=0, blocked=True)
        b2 = _write_feature(features, "other-blocked", tier=2, blocked=True)
        (features / "queue.json").write_text(
            json.dumps({"queue": [b1, b2]}), encoding="utf-8")
        (fixture_repo / "docs" / "bugs").mkdir(parents=True)
        (fixture_repo / "docs" / "bugs" / "queue.json").write_text(
            json.dumps({"queue": []}), encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"; state_dir.mkdir()
        _seed_marker_for(fixture_repo, state_dir)
        sj = _emit_prompt_subprocess(fixture_repo, state_dir)

        assert sj.get("route_overridden_by") is None, (
            f"fully-gated queue must NOT withhold on merged-head divergence; "
            f"got {sj.get('route_overridden_by')!r}")
        assert sj.get("terminal_reason") == "blocked", (
            f"fully-gated queue must surface the blocked terminal, not skip forever; "
            f"got terminal_reason={sj.get('terminal_reason')!r}, "
            f"feature_id={sj.get('feature_id')!r}")


def test_subprocess_emit_prompt_single_type_workable_head_unchanged():
    """No-regression: a single-type feature queue whose head IS workable behaves
    byte-identically — normal cycle_prompt, no route_overridden_by, no gated_heads
    (the fix is additive; it only fires when the probe actually skipped a gated
    head)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = td_path / "fixture-repo"
        features = fixture_repo / "docs" / "features"
        features.mkdir(parents=True)
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        w = _write_feature(features, "feat-w", tier=1)
        (features / "queue.json").write_text(
            json.dumps({"queue": [w]}), encoding="utf-8")
        (fixture_repo / "docs" / "bugs").mkdir(parents=True)
        (fixture_repo / "docs" / "bugs" / "queue.json").write_text(
            json.dumps({"queue": []}), encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"; state_dir.mkdir()
        _seed_marker_for(fixture_repo, state_dir)
        sj = _emit_prompt_subprocess(fixture_repo, state_dir)

        assert sj.get("route_overridden_by") is None
        assert sj.get("feature_id") == "feat-w"
        assert sj.get("cycle_prompt"), "a workable single-type head must emit a cycle_prompt"
        assert "gated_heads" not in sj, (
            f"no skip should have happened; got gated_heads={sj.get('gated_heads')!r}")


def test_research_halt_head_surfaces_when_research_head_outranks_bug():
    """research-gated-head-buried-by-skip-ahead-and-merged-fallthrough: a P1
    research-gated head the probe skipped that OUTRANKS the fallthrough (a lower
    P2 bug + a lower feature the probe dispatched) is returned → surface. The
    exclude_ids fed in are exactly what the emit handler builds (nondispatchable ∪
    probe_skipped_ids incl. the research head, current dispatch target removed)."""
    _guard()
    feats = [
        {"id": "inspector", "tier": "pre-release"},  # P1 research-gated, skipped
        {"id": "hydra", "tier": 3},                  # dispatched alternative
    ]
    bugs = [{"id": "drift", "severity": "P2"}]        # the merged fallthrough target
    state = {"feature_id": "hydra", "research_gated_heads": ["inspector"]}
    # exclude = probe_skipped_ids folds the research head in (Round-64 behavior).
    got = lazy_core.dispatch.research_halt_head(
        state, feats, bugs, "/r", exclude_ids={"inspector"}
    )
    assert got == "inspector", got


def test_research_halt_head_none_when_ready_work_outranks_research_head():
    """No over-halt (the task's explicit bound): when the research head is LOWER
    priority than genuinely-independent ready work, the research-inclusive merged
    head is that ready item — not the research head — so None is returned and
    skip-ahead proceeds unchanged."""
    _guard()
    feats = [
        {"id": "ready", "tier": 1},                  # P1 ready feature (dispatched)
        {"id": "low-research", "tier": 5},           # lower-priority research head
    ]
    state = {"feature_id": "ready", "research_gated_heads": ["low-research"]}
    got = lazy_core.dispatch.research_halt_head(
        state, feats, [], "/r", exclude_ids={"low-research"}
    )
    assert got is None, got
    # No research_gated_heads at all → None (byte-identical common path).
    assert lazy_core.dispatch.research_halt_head(
        {"feature_id": "x"}, feats, [], "/r", exclude_ids=set()) is None
    # A BLOCKED (non-research) skipped head is NOT surfaced (only research is).
    assert lazy_core.dispatch.research_halt_head(
        {"feature_id": "ready", "gated_heads": ["blocked-head"]},
        feats, [], "/r", exclude_ids={"blocked-head"}) is None


def test_subprocess_emit_prompt_surfaces_needs_research_over_lower_bug():
    """research-gated-head-buried-by-skip-ahead-and-merged-fallthrough (end-to-end,
    the exact live 2026-07-17 friction): a P1 (pre-release) research-gated feature
    at the queue head + an independent lower feature (realizes the skip) + a
    lower-priority P2 bug. The probe MUST surface terminal_reason='needs-research'
    for the research head instead of routing to the lower bug/feature. RED
    (pre-fix): route_overridden_by='merged-head-diverged' to the bug (or a
    cycle_prompt for the lower feature) with NO research halt."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = td_path / "fixture-repo"
        features = fixture_repo / "docs" / "features"
        features.mkdir(parents=True)
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        research = _write_feature(
            features, "inspector-sample-clip-view", tier="pre-release",
            research_gated=True)
        workable = _write_feature(features, "hydra-overlay", tier=3, independent=True)
        (features / "queue.json").write_text(
            json.dumps({"queue": [research, workable]}), encoding="utf-8")
        bugs_dir = fixture_repo / "docs" / "bugs"
        bug_dir = bugs_dir / "protocol-generic-claims-drift"
        bug_dir.mkdir(parents=True)
        (bug_dir / "SPEC.md").write_text(
            "# Bug\n\n**Severity:** P2\n**Status:** Concluded\n", encoding="utf-8")
        (bugs_dir / "queue.json").write_text(
            json.dumps({"queue": [{
                "id": "protocol-generic-claims-drift", "name": "Drift",
                "spec_dir": "protocol-generic-claims-drift", "severity": "P2"}]}),
            encoding="utf-8")

        state_dir = td_path / "lazy-state-dir"; state_dir.mkdir()
        _seed_marker_for(fixture_repo, state_dir)
        sj = _emit_prompt_subprocess(fixture_repo, state_dir)

        assert sj.get("terminal_reason") == "needs-research", (
            f"a research-gated P1 head outranking the fallthrough must SURFACE a "
            f"needs-research halt; got terminal_reason={sj.get('terminal_reason')!r} "
            f"feature_id={sj.get('feature_id')!r} "
            f"route_overridden_by={sj.get('route_overridden_by')!r}")
        assert sj.get("feature_id") == "inspector-sample-clip-view", sj.get("feature_id")
        assert sj.get("route_overridden_by") == "research-gated-head", (
            sj.get("route_overridden_by"))


def test_spec_dir_would_park_predicate():
    """merged-head-includes-parked-items-deadlocks-park-run: the shared park
    predicate mirrors the compute_state parked[] branches — NEEDS_INPUT under
    --park-needs-input parks; BLOCKED retains precedence; --park-blocked parks a
    BLOCKED.md; no facet → never parks (byte-identical non-park behavior)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ni = root / "needs-input"; ni.mkdir()
        (ni / "NEEDS_INPUT.md").write_text("x", encoding="utf-8")
        bl = root / "blocked"; bl.mkdir()
        (bl / "BLOCKED.md").write_text("x", encoding="utf-8")
        both = root / "both"; both.mkdir()
        (both / "NEEDS_INPUT.md").write_text("x", encoding="utf-8")
        (both / "BLOCKED.md").write_text("x", encoding="utf-8")
        clean = root / "clean"; clean.mkdir()
        (clean / "SPEC.md").write_text("x", encoding="utf-8")

        # No facet active → nothing parks.
        assert not lazy_core.spec_dir_would_park(ni)
        assert not lazy_core.spec_dir_would_park(bl)
        # --park-needs-input parks an unresolved NEEDS_INPUT.md.
        assert lazy_core.spec_dir_would_park(ni, park_needs_input=True)
        # BLOCKED precedence: NEEDS_INPUT+BLOCKED is NOT a needs-input park when
        # --park-blocked is off (it still halts as blocked).
        assert not lazy_core.spec_dir_would_park(both, park_needs_input=True)
        # --park-blocked parks a BLOCKED.md (and the both-dir).
        assert lazy_core.spec_dir_would_park(bl, park_blocked=True)
        assert lazy_core.spec_dir_would_park(both, park_blocked=True)
        # A clean dir never parks; a missing dir fail-safes to False.
        assert not lazy_core.spec_dir_would_park(clean, park_needs_input=True, park_blocked=True)
        assert not lazy_core.spec_dir_would_park(root / "nope", park_needs_input=True)


def test_spec_dir_operator_deferred_predicate():
    """merged-head-excludes-parked-not-operator-deferred-deadlocks: the
    UNCONDITIONAL operator-defer predicate — True iff DEFERRED.md is present,
    independent of any park flag; fail-safe False on a missing/clean dir."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        deferred = root / "deferred"; deferred.mkdir()
        (deferred / "DEFERRED.md").write_text("x", encoding="utf-8")
        clean = root / "clean"; clean.mkdir()
        (clean / "SPEC.md").write_text("x", encoding="utf-8")

        # DEFERRED.md → True with NO park flags (it is unconditional).
        assert lazy_core.spec_dir_operator_deferred(deferred)
        # A clean dir + a missing dir + None → False.
        assert not lazy_core.spec_dir_operator_deferred(clean)
        assert not lazy_core.spec_dir_operator_deferred(root / "nope")
        assert not lazy_core.spec_dir_operator_deferred(None)


def test_spec_dir_research_pending_predicate():
    """merged-head-diverged-withholds-on-research-skipped-head: the pure file
    predicate — NEEDS_RESEARCH.md present, OR RESEARCH_PROMPT.md present with no
    RESEARCH*.md; a completed-research or clean dir is NOT pending; missing/None
    fail-safe to False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        nr = root / "needs-research"; nr.mkdir()
        (nr / "NEEDS_RESEARCH.md").write_text("x", encoding="utf-8")
        rp = root / "research-prompt"; rp.mkdir()
        (rp / "RESEARCH_PROMPT.md").write_text("x", encoding="utf-8")
        # RESEARCH_PROMPT satisfied by RESEARCH.md → NOT pending.
        done = root / "research-done"; done.mkdir()
        (done / "RESEARCH_PROMPT.md").write_text("x", encoding="utf-8")
        (done / "RESEARCH.md").write_text("x", encoding="utf-8")
        # RESEARCH_PROMPT satisfied by RESEARCH_SUMMARY.md → NOT pending.
        summ = root / "research-summary"; summ.mkdir()
        (summ / "RESEARCH_PROMPT.md").write_text("x", encoding="utf-8")
        (summ / "RESEARCH_SUMMARY.md").write_text("x", encoding="utf-8")
        clean = root / "clean"; clean.mkdir()
        (clean / "SPEC.md").write_text("x", encoding="utf-8")

        assert lazy_core.spec_dir_research_pending(nr)
        assert lazy_core.spec_dir_research_pending(rp)
        assert not lazy_core.spec_dir_research_pending(done)
        assert not lazy_core.spec_dir_research_pending(summ)
        assert not lazy_core.spec_dir_research_pending(clean)
        assert not lazy_core.spec_dir_research_pending(root / "nope")
        assert not lazy_core.spec_dir_research_pending(None)


def test_merged_head_nondispatchable_ids_excludes_parked_same_pipeline_head_no_deadlock():
    """merged-head-includes-parked-items-deadlocks-park-run REGRESSION, via the
    ORACLE: two top-priority P0 bugs PARKED (in the probe's own state["parked"]
    list) + a lower-priority actionable bug (current). The oracle folds the
    probe's parked ids into the same-pipeline exclude source, so the parked P0
    heads are EXCLUDED and the merged head is the actionable bug — NO
    merged-head-diverged withhold (the park-mode deadlock is gone). This is the
    same-pipeline parked-fold the retired file predicate used to cover."""
    _guard()
    bugs = [
        {"id": "adhoc-hydra-sidecar-dist-esm-no-frames", "severity": "P0"},
        {"id": "adhoc-hydra-load-code-mcp-tool", "severity": "P0"},
        {"id": "adhoc-incident-hook-deny-a51dde", "severity": "P2"},
    ]
    # The probe's own state: park mode skipped the two P0 bugs (parked[]) and
    # dispatched the actionable P2 bug (current). No cross-pipeline features.
    state = {
        "feature_id": "adhoc-incident-hook-deny-a51dde",
        "parked": [
            {"id": "adhoc-hydra-sidecar-dist-esm-no-frames"},
            {"id": "adhoc-hydra-load-code-mcp-tool"},
        ],
    }

    def _never(_id):
        raise AssertionError(f"no cross-pipeline candidate to probe (got {_id!r})")

    excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
        [], bugs, "/echo", "adhoc-incident-hook-deny-a51dde",
        same_pipeline="bug", same_pipeline_state=state, scoped_probe=_never,
    )
    assert excluded == {
        "adhoc-hydra-sidecar-dist-esm-no-frames", "adhoc-hydra-load-code-mcp-tool",
    }, excluded
    # --next-merged surface: head is the actionable bug, not a parked one.
    head = lazy_core.next_merged([], bugs, "/echo", exclude_ids=excluded)
    assert head["item_id"] == "adhoc-incident-hook-deny-a51dde", head
    # Emit probe for the actionable bug → NO withhold (the deadlock is gone).
    assert lazy_core.dispatch.merged_head_override(
        [], bugs, "/echo", "adhoc-incident-hook-deny-a51dde", exclude_ids=excluded,
    ) is None
    # Without the exclusion the OLD behavior deadlocks: head is a parked P0 bug.
    old = lazy_core.dispatch.merged_head_override(
        [], bugs, "/echo", "adhoc-incident-hook-deny-a51dde",
    )
    assert old is not None and old["merged_head"]["item_id"] == (
        "adhoc-hydra-sidecar-dist-esm-no-frames"
    ), old


def test_merged_head_nondispatchable_ids_excludes_parked_UNREACHED_same_pipeline_head():
    """merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head
    REGRESSION: a PARKED, highest-SEVERITY, same-pipeline head that the emit
    probe's queue-order walk NEVER reached (so it is ABSENT from state["parked"]
    — the walk returned a lower-priority workable item first) is now scope-probed
    and EXCLUDED via per-item re-inference. Previously the `iid in same_ids`
    fast-path treated any same-pipeline head above current as dispatchable,
    leaving byref the merged head → the merged-head-diverged withhold fired on
    every probe → park-mode deadlock (cycle_prompt_ref null, no
    queue-exhausted-all-parked). Distinct from the parked-FOLD regression
    (test_..._excludes_parked_same_pipeline_head_no_deadlock), where the parked
    heads ARE in state["parked"]."""
    _guard()
    bugs = [
        {"id": "byref-unreached", "severity": "P0"},   # highest sev → merged head
        {"id": "adhoc-harness-gate", "severity": "P2"},  # current (dispatchable)
    ]
    # The emit probe dispatched adhoc-harness-gate WITHOUT parking byref (its
    # queue-order walk returned before reaching byref): parked[] is EMPTY, so the
    # only signal for byref's parked state is a scoped re-probe.
    state = {"feature_id": "adhoc-harness-gate", "parked": []}
    calls = []

    def _probe(_id):
        calls.append(_id)
        # byref scope-probes to a needs-input-scoped (parked) non-dispatch state.
        if _id == "byref-unreached":
            return _nondispatch_state("needs-input-scoped")
        raise AssertionError(f"only the unreached head is probed, got {_id!r}")

    excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
        [], bugs, "/echo", "adhoc-harness-gate",
        same_pipeline="bug", same_pipeline_state=state, scoped_probe=_probe,
    )
    assert excluded == {"byref-unreached"}, excluded
    assert calls == ["byref-unreached"], calls
    # Merged head is now the dispatchable item → NO merged-head-diverged withhold.
    assert lazy_core.dispatch.merged_head_override(
        [], bugs, "/echo", "adhoc-harness-gate", exclude_ids=excluded,
    ) is None
    # Without the exclusion the OLD behavior deadlocks: head is the parked P0.
    assert lazy_core.dispatch.merged_head_override(
        [], bugs, "/echo", "adhoc-harness-gate",
    )["merged_head"]["item_id"] == "byref-unreached"

    # Byte-identity for a GENUINE divergence: a DISPATCHABLE same-pipeline head
    # above current is NOT excluded — the withhold still fires for a real P0 bug
    # jumping the queue (the emit path routes to it exactly as before).
    def _probe_dispatchable(_id):
        return _dispatchable_state() if _id == "byref-unreached" \
            else _nondispatch_state("blocked")

    excluded2 = lazy_core.dispatch.merged_head_nondispatchable_ids(
        [], bugs, "/echo", "adhoc-harness-gate",
        same_pipeline="bug",
        same_pipeline_state={"feature_id": "adhoc-harness-gate", "parked": []},
        scoped_probe=_probe_dispatchable,
    )
    assert excluded2 == set(), excluded2
    assert lazy_core.dispatch.merged_head_override(
        [], bugs, "/echo", "adhoc-harness-gate", exclude_ids=excluded2,
    )["merged_head"]["item_id"] == "byref-unreached"


def test_merged_head_nondispatchable_ids_excludes_operator_deferred_cross_pipeline_feature():
    """merged-head-oracle-blind-to-operator-deferred-cross-pipeline-feature
    REGRESSION (Round 102), NOW carried by the PRIMARY mechanism
    (merged-head-oracle-per-signal-supplement-churn Phase 2): a bug-emit probe with
    an operator-deferred FEATURE (DEFERRED.md) ranked ABOVE the dispatchable bug at
    the cross-pipeline merged head. Round 102 patched this with a per-signal
    file-predicate supplement (``spec_dir_operator_deferred`` re-applied inside the
    oracle) because the FEATURE ``compute_state`` had no operator-defer branch and
    ``scoped_probe`` reported the deferred feature DISPATCHABLE. Phase 1 gave the
    FEATURE ``compute_state`` its own bare-``DEFERRED.md`` branch (a scoped
    ``--feature-id`` probe now returns ``terminal_reason: operator-deferred`` →
    non-dispatchable), so ``is_dispatchable(scoped_probe(feature))`` ALONE excludes
    it and Phase 2 RETIRED the supplement. This unit test models that reality: the
    injected ``scoped_probe`` returns the Phase-1 scoped terminal for the deferred
    feature, and the oracle excludes it with NO file-predicate present. The
    serving-path (real state scripts) twin is
    ``test_subprocess_bug_emit_prompt_oracle_excludes_operator_deferred_feature_head_no_withhold``."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        feat_dir = root / "docs" / "features" / "native-android"
        feat_dir.mkdir(parents=True)
        (feat_dir / "DEFERRED.md").write_text(
            "---\nkind: deferred\nreason: operator-excluded\n---\n", encoding="utf-8")
        (feat_dir / "SPEC.md").write_text("**Status:** Draft\n", encoding="utf-8")
        bug_dir = root / "docs" / "bugs" / "adhoc-harness-gate"
        bug_dir.mkdir(parents=True)

        # tier 1 (pre-release) < P2 bug(2) → the feature ranks ABOVE the bug.
        feats = [{"id": "native-android", "tier": 1, "spec_dir": "native-android"}]
        bugs = [{"id": "adhoc-harness-gate", "severity": "P2",
                 "spec_path": str(bug_dir)}]
        # Bug emit probe: dispatched the P2 bug; the cross-pipeline deferred feature
        # is NOT in the bug probe's parked/skip surface (parked: [] — the live JSON).
        state = {"feature_id": "adhoc-harness-gate", "parked": []}

        # Phase 1: the FEATURE compute_state now MODELS operator-defer — a scoped
        # probe on a DEFERRED.md feature returns a scoped operator-deferred terminal
        # (non-dispatchable). The oracle's PRIMARY is_dispatchable(scoped_probe)
        # therefore excludes it with NO file-predicate supplement (Phase 2 retired
        # it). The fake probe consults the real DEFERRED.md so the CONTROL below
        # (delete it → dispatchable) still exercises the boundary.
        def _feature_probe(_id):
            assert _id != "adhoc-harness-gate", "current is never probed (== break)"
            if (feat_dir / "DEFERRED.md").exists():
                return {"feature_id": _id, "feature_name": _id, "sub_skill": None,
                        "terminal_reason": "operator-deferred"}
            return _dispatchable_state("spec")

        excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
            feats, bugs, str(root), "adhoc-harness-gate",
            same_pipeline="bug", same_pipeline_state=state,
            scoped_probe=_feature_probe,
        )
        assert excluded == {"native-android"}, excluded
        # Merged head is the dispatchable bug, not the deferred feature.
        assert lazy_core.next_merged(
            feats, bugs, str(root), exclude_ids=excluded,
        )["item_id"] == "adhoc-harness-gate"
        # Emit probe for the bug → NO withhold (the deadlock is gone).
        assert lazy_core.dispatch.merged_head_override(
            feats, bugs, str(root), "adhoc-harness-gate", exclude_ids=excluded,
        ) is None
        # NON-VACUITY: without the exclusion the OLD behavior deadlocks — the
        # deferred feature is the merged head + withhold fires.
        old = lazy_core.dispatch.merged_head_override(
            feats, bugs, str(root), "adhoc-harness-gate",
        )
        assert old is not None and old["merged_head"]["item_id"] == "native-android", old

        # CONTROL: remove DEFERRED.md → the feature's scoped probe reports
        # DISPATCHABLE and it is NOT excluded (the scoped operator-deferred terminal
        # is the ONLY thing that excluded it), proving the exclusion keys on the
        # feature's OWN compute_state signal, not on its id or type.
        (feat_dir / "DEFERRED.md").unlink()
        not_excluded = lazy_core.dispatch.merged_head_nondispatchable_ids(
            feats, bugs, str(root), "adhoc-harness-gate",
            same_pipeline="bug", same_pipeline_state=state,
            scoped_probe=_feature_probe,
        )
        assert "native-android" not in not_excluded, not_excluded


def test_subprocess_bug_emit_prompt_oracle_excludes_operator_deferred_feature_head_no_withhold():
    """merged-head-oracle-per-signal-supplement-churn Phase 2 (SERVING-PATH
    regression, real state scripts): a bug-emit probe with an operator-deferred
    FEATURE (a bare ``DEFERRED.md``, ``reason: operator-excluded``) ranked ABOVE the
    workable bug at the cross-pipeline merged head must NOT withhold — the deferred
    feature is excluded by the oracle's REAL cross-pipeline scoped
    ``lazy-state.compute_state`` (Phase 1's operator-defer branch), with NO
    file-predicate supplement present (Phase 2 retired it). This is the original
    symptom's actual serving path: the 19-bug deadlock this bug fixes was a real
    ``bug-state.py --emit-prompt`` withholding behind an operator-deferred feature
    head. Coupled twin of
    ``test_subprocess_bug_emit_prompt_oracle_excludes_nondispatchable_feature_head_no_withhold``."""
    _guard()
    bug_state_script = _SCRIPTS_DIR / "bug-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = td_path / "fixture-repo"
        # Workable bug (current, P2).
        bugs = fixture_repo / "docs" / "bugs"
        bug_dir = bugs / "bug-w"
        (bug_dir / "plans").mkdir(parents=True)
        (bugs / "queue.json").write_text(json.dumps({
            "queue": [{"id": "bug-w", "name": "Bug W", "spec_dir": "bug-w", "severity": "P2"}]
        }), encoding="utf-8")
        (bug_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Concluded\n\n**Depends on:** (none)\n", encoding="utf-8")
        (bug_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [ ] Fix\n- [ ] Tests\n", encoding="utf-8")
        (bug_dir / "plans" / "all-phases-w.md").write_text("# Plan\n", encoding="utf-8")

        # Higher-priority OPERATOR-DEFERRED feature at the merged head (tier 0) —
        # a bare DEFERRED.md, no BLOCKED.md. Pre-Phase-1 the feature compute_state
        # reported it dispatchable → withhold deadlock; Phase 1's branch now returns
        # a scoped operator-deferred terminal → excluded by is_dispatchable alone.
        features = fixture_repo / "docs" / "features"
        fdir = features / "feat-def"
        fdir.mkdir(parents=True)
        (features / "queue.json").write_text(json.dumps({
            "queue": [{"id": "feat-def", "name": "Feature Deferred", "spec_dir": "feat-def", "tier": 0}]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        (fdir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (fdir / "DEFERRED.md").write_text(
            "---\nkind: deferred\nfeature_id: feat-def\nreason: operator-excluded\n"
            "deferred_at: 2026-07-19\n---\nOperator parked.\n", encoding="utf-8")

        state_dir = td_path / "bug-state-dir"
        state_dir.mkdir()
        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="bug", cloud=False,
                repo_root=str(fixture_repo), max_cycles=10, now=_time.time())
        finally:
            _clear_state_dir()

        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        result = subprocess.run(
            [sys.executable, str(bug_state_script),
             "--repeat-count", "--probe", "--emit-prompt", "--repo-root", str(fixture_repo)],
            capture_output=True, text=True, env=env)
        assert result.returncode == 0, (
            f"bug-state.py exited {result.returncode}; stderr: {result.stderr[:400]!r}")
        state_json = json.loads(result.stdout)
        assert state_json.get("route_overridden_by") is None, (
            f"operator-deferred feature head must NOT withhold on the bug side; got "
            f"route_overridden_by={state_json.get('route_overridden_by')!r}")
        assert state_json.get("feature_id") == "bug-w", state_json.get("feature_id")
        assert state_json.get("cycle_prompt"), "bug cycle_prompt must be emitted"


def test_nondispatchable_item_ids_helper_is_retired():
    """merged-head-actionability-oracle Phase 3 (WU-4): the file-predicate
    ``nondispatchable_item_ids`` is DELETED — absent from the lazy_core facade AND
    from depdag. The actionability oracle is its sole replacement."""
    _guard()
    assert not hasattr(lazy_core, "nondispatchable_item_ids"), (
        "nondispatchable_item_ids must be retired from the lazy_core facade")
    assert not hasattr(lazy_core.depdag, "nondispatchable_item_ids"), (
        "nondispatchable_item_ids must be deleted from depdag")
    # The replacement exists.
    assert callable(lazy_core.dispatch.merged_head_nondispatchable_ids)
    assert callable(lazy_core.dispatch.is_dispatchable)


def test_merged_worklist_exclude_ids_drops_parked_items():
    """merged_worklist/next_merged honor exclude_ids — a byte-identical drop of
    the named ids from the ordering (empty/None → unchanged)."""
    _guard()
    feats = [{"id": "feat-1", "tier": 1}]
    bugs = [{"id": "bug-1", "severity": "P0"}, {"id": "bug-2", "severity": "P0"}]
    # No exclusion → byte-identical.
    assert [e["item_id"] for e in lazy_core.merged_worklist(feats, bugs, "/r")] == [
        "bug-1", "bug-2", "feat-1",
    ]
    wl = lazy_core.merged_worklist(feats, bugs, "/r", exclude_ids={"bug-1"})
    assert [e["item_id"] for e in wl] == ["bug-2", "feat-1"], wl
    assert lazy_core.next_merged(
        feats, bugs, "/r", exclude_ids={"bug-1", "bug-2"}
    )["item_id"] == "feat-1"


def test_merged_worklist_only_features_matches_listed_order():
    """WU-1/WU-3: only features queued → identical to the feature queue's listed
    order (the head is what lazy-state would return)."""
    _guard()
    feats = [{"id": "feat-1", "tier": 1}, {"id": "feat-2", "tier": 1},
             {"id": "feat-3", "tier": 1}]
    wl = lazy_core.merged_worklist(feats, [], "/r")
    assert [e["item_id"] for e in wl] == ["feat-1", "feat-2", "feat-3"]
    assert all(e["type"] == "feature" for e in wl)
    assert lazy_core.next_merged(feats, [], "/r")["item_id"] == "feat-1"


def test_merged_worklist_only_bugs_matches_listed_order():
    """WU-1/WU-3: only bugs queued → identical to the bug queue's listed order."""
    _guard()
    bugs = [{"id": "bug-1", "severity": "P0"}, {"id": "bug-2", "severity": "P0"}]
    wl = lazy_core.merged_worklist([], bugs, "/r")
    assert [e["item_id"] for e in wl] == ["bug-1", "bug-2"]
    assert all(e["type"] == "bug" for e in wl)
    assert lazy_core.next_merged([], bugs, "/r")["item_id"] == "bug-1"


def test_merged_worklist_both_empty_returns_none():
    """WU-1/WU-3: both empty → no item (None head, empty work-list)."""
    _guard()
    assert lazy_core.merged_worklist([], [], "/r") == []
    assert lazy_core.next_merged([], [], "/r") is None


def test_merged_worklist_stable_within_queue_for_equal_keys():
    """WU-1: stable for equal (priority, type) — each queue's listed order is
    preserved among same-priority same-type items."""
    _guard()
    feats = [{"id": "f-first", "tier": 2}, {"id": "f-second", "tier": 2}]
    bugs = [{"id": "b-first", "severity": "P2"}, {"id": "b-second", "severity": "P2"}]
    # All effective priority 2; features (type-rank 0) precede bugs (type-rank 1)
    # after the 2026-07-17 tie-break flip, and within each type listed order is
    # preserved (non-p0-bug-outranks-p1-feature-on-aged-tie).
    wl = lazy_core.merged_worklist(feats, bugs, "/r")
    assert [e["item_id"] for e in wl] == [
        "f-first", "f-second", "b-first", "b-second"
    ], [e["item_id"] for e in wl]


def test_merged_worklist_skips_idless_entries():
    """A malformed queue entry missing `id` is skipped — never a None-id head."""
    _guard()
    feats = [{"tier": 1}, {"id": "feat-ok", "tier": 1}]  # first is id-less
    wl = lazy_core.merged_worklist(feats, [], "/r")
    assert [e["item_id"] for e in wl] == ["feat-ok"]


def test_age_escalated_rank_quantum_and_floor():
    """bug-queue-aging-backpressure D1-A/D3-A: one notch toward 0 per 7-day
    quantum since `discovered`, floored at rank 1 (P1-equivalent — never
    past a genuine P0)."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    # P2 (rank 2), discovered 21 days ago -> 3 notches -> 2-3=-1 -> floor 1.
    assert lazy_core.age_escalated_rank(2, "2026-06-22", today) == 1
    # P2, discovered 6 days ago -> 0 notches (age_days // 7 == 0) -> unchanged.
    assert lazy_core.age_escalated_rank(2, "2026-07-07", today) == 2
    # P2, discovered exactly 7 days ago -> 1 notch -> 1.
    assert lazy_core.age_escalated_rank(2, "2026-07-06", today) == 1
    # A "Low" bug (rank 3) ages toward the floor but never past it, even after
    # a very long time.
    assert lazy_core.age_escalated_rank(3, "2020-01-01", today) == 1
    # P0/P1 (rank <= floor) never escalate — trivially unchanged.
    assert lazy_core.age_escalated_rank(0, "2020-01-01", today) == 0
    assert lazy_core.age_escalated_rank(1, "2020-01-01", today) == 1


def test_age_escalated_rank_fail_open_cases():
    """Absent/unparseable/future-dated `discovered` all fail open (unchanged
    base_rank) — never a fabricated age, never a crash."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    assert lazy_core.age_escalated_rank(2, None, today) == 2
    assert lazy_core.age_escalated_rank(2, "", today) == 2
    assert lazy_core.age_escalated_rank(2, "not-a-date", today) == 2
    # Future-dated discovery -> negative age -> fail open, unchanged.
    assert lazy_core.age_escalated_rank(2, "2026-08-01", today) == 2
    # today omitted -> uses real date.today() without raising.
    assert isinstance(lazy_core.age_escalated_rank(2, None), int)


def test_pin_is_active_variants():
    """bug-queue-aging-backpressure D2-A: pin_is_active's five branches —
    never-pinned, active-until-future, expired-until-past,
    active-default-age (no pinned_until), expired-default-age, and
    fail-open on a malformed date."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    # Never pinned (no pinned_at) -> not active.
    assert lazy_core.pin_is_active(None, None, today) is False
    # Active: pinned_until in the future.
    assert lazy_core.pin_is_active("2026-07-01", "2026-08-01", today) is True
    # Expired: pinned_until in the past.
    assert lazy_core.pin_is_active("2026-06-01", "2026-06-15", today) is False
    # pinned_until == today -> still active (inclusive).
    assert lazy_core.pin_is_active("2026-07-01", "2026-07-13", today) is True
    # No pinned_until -> default max age (90 days). 10 days old -> active.
    assert lazy_core.pin_is_active("2026-07-03", None, today) is True
    # No pinned_until, 100 days old -> expired (past the 90-day default).
    assert lazy_core.pin_is_active("2026-04-01", None, today) is False
    # Malformed pinned_until -> fail open (treated as expired).
    assert lazy_core.pin_is_active("2026-07-01", "not-a-date", today) is False
    # Malformed pinned_at -> fail open (treated as never-pinned/not active).
    assert lazy_core.pin_is_active("not-a-date", None, today) is False


def test_merged_priority_bug_explicit_severity_ages():
    """An explicit recognized severity ALWAYS age-escalates (independent of
    any pin field)."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    raw = {"severity": "P2", "discovered": "2026-06-22"}
    assert lazy_core.merged_priority("bug", raw, today=today) == 1


def test_merged_priority_bug_active_pin_suppressed():
    """A null-severity bug with an ACTIVE pin stays suppressed at
    MERGED_PRIORITY_DEFAULT — no fallback, no escalation, honoring the
    deliberate deprioritization."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    raw = {
        "severity": None, "pinned_at": "2026-07-10", "pinned_until": "2026-08-01",
        "spec_severity": "P1", "discovered": "2026-06-01",
    }
    assert lazy_core.merged_priority("bug", raw, today=today) == lazy_core.MERGED_PRIORITY_DEFAULT


def test_merged_priority_bug_expired_pin_falls_back_to_spec_severity():
    """Past pin expiry, the merged view falls back to the SPEC's own declared
    severity and resumes age-escalating from there (D2-A)."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    raw = {
        "severity": None, "pinned_at": "2026-06-01", "pinned_until": "2026-06-15",
        "spec_severity": "P2", "discovered": "2026-06-22",
    }
    # Expired pin -> falls back to spec_severity P2 (rank 2), then ages by
    # discovered (21 days -> 3 notches -> floor 1).
    assert lazy_core.merged_priority("bug", raw, today=today) == 1


def test_merged_priority_bug_legacy_null_no_pin_unchanged():
    """A bare `severity: null` with NO `pinned_at` (every real queue entry
    committed before this feature shipped) is byte-identical to before —
    MERGED_PRIORITY_DEFAULT, no fallback, no escalation."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    raw = {"severity": None, "spec_severity": "P1", "discovered": "2020-01-01"}
    assert lazy_core.merged_priority("bug", raw, today=today) == lazy_core.MERGED_PRIORITY_DEFAULT


def test_merged_priority_aged_bug_outranks_tier2_feature_not_p0():
    """SPEC Phase-1 "proven done" fixture: a 3-week-old, expired-pin bug
    whose SPEC declares P2 outranks a tier-2 feature in the merged worklist,
    but a genuine P0 bug still comes first."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    feats = [{"id": "feat-t2", "tier": 2}]
    bugs = [
        {
            "id": "aged-bug", "severity": None, "pinned_at": "2026-06-01",
            "pinned_until": "2026-06-15", "spec_severity": "P2",
            "discovered": "2026-06-22",
        },
        {"id": "real-p0", "severity": "P0", "discovered": "2026-07-12"},
    ]
    wl = lazy_core.merged_worklist(feats, bugs, "/r", today=today)
    ids = [e["item_id"] for e in wl]
    assert ids == ["real-p0", "aged-bug", "feat-t2"], ids


def test_bug_priority_marker_pinned():
    """bug_priority_marker renders the 📌 pinned marker while a pin is active."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    marker = lazy_core.bug_priority_marker(
        severity=None, spec_severity="P1", discovered="2026-06-01",
        pinned_at="2026-07-10", pinned_until="2026-08-01", today=today,
    )
    assert "pinned" in marker and "2026-07-10" in marker


def test_bug_priority_marker_escalated():
    """bug_priority_marker renders the ⏫ escalated marker when the effective
    priority has moved past the declared severity."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    marker = lazy_core.bug_priority_marker(
        severity="P2", spec_severity=None, discovered="2026-06-22",
        pinned_at=None, pinned_until=None, today=today,
    )
    assert "escalated" in marker


def test_bug_priority_marker_none_when_no_pin_no_escalation():
    """bug_priority_marker renders empty when there's no active pin and no
    escalation has occurred yet (a fresh, unescalated bug)."""
    _guard()
    import datetime
    today = datetime.date(2026, 7, 13)
    marker = lazy_core.bug_priority_marker(
        severity="P2", spec_severity=None, discovered="2026-07-10",
        pinned_at=None, pinned_until=None, today=today,
    )
    assert marker == ""


def test_skill_declares_multi_commit_user_level_and_pseudo():
    """adhoc-derive-multi-commit-budget-from-dispatch-sites: `skill_declares_multi_commit`
    replaces the retired `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset. The 6 real
    user-level skills flagged `commit-cadence: multi` (mirroring the exact prior
    frozenset membership minus the dead `retro-feature` row, which correctly drops
    since its own SKILL.md is left unflagged — the missing-row class in reverse) read
    True via the module-relative resolution path; unflagged/pseudo/junk shapes fail
    closed to False, EXCEPT the two forward-advancing terminal pseudo-skills, which
    are answered directly from the bounded `_MULTI_COMMIT_PSEUDO_SKILLS` dict."""
    _guard()
    for name in (
        "execute-plan", "write-plan", "spec", "spec-bug", "plan-feature", "plan-bug",
    ):
        assert lazy_core.skill_declares_multi_commit(name) is True, name
    # spec-phases commits only PHASES.md (genuinely single-commit) → unflagged.
    assert lazy_core.skill_declares_multi_commit("spec-phases") is False
    # retro-feature is DEAD (Step-8 retro unwired 2026-06, dispatched from nowhere) —
    # its SKILL.md carries no commit-cadence flag, so it correctly reverts to the
    # single-commit default instead of keeping stale multi-commit membership forever.
    assert lazy_core.skill_declares_multi_commit("retro-feature") is False
    # The 2 pseudo-skills (no SKILL.md; can never be "newly dispatched" from
    # elsewhere) are answered from the small explicit dict, not a frontmatter read.
    assert lazy_core.skill_declares_multi_commit("__mark_complete__") is True
    assert lazy_core.skill_declares_multi_commit("__mark_fixed__") is True
    # Fail-closed shapes: falsy, unknown, path traversal.
    assert lazy_core.skill_declares_multi_commit(None) is False
    assert lazy_core.skill_declares_multi_commit("") is False
    assert lazy_core.skill_declares_multi_commit("no-such-skill-xyz") is False
    assert lazy_core.skill_declares_multi_commit("../../etc/passwd") is False
    # Leading "/" is tolerated (mirrors skill_declares_subagent_model).
    assert lazy_core.skill_declares_multi_commit("/execute-plan") is True
    # The retired registry symbol is genuinely gone — not just unused.
    assert not hasattr(lazy_core, "_MULTI_COMMIT_DISPATCH_SKILLS")
    # The uniform multi-commit ceiling + single-commit default are still named
    # constants (unchanged by the derivation-mechanism swap).
    assert lazy_core.dispatch._CYCLE_COMMIT_MULTI == 3
    assert lazy_core.dispatch._CYCLE_COMMIT_BUDGET_DEFAULT == 1


def test_skill_declares_multi_commit_repo_scoped():
    """A repo-scoped .claude/skills/<name>/SKILL.md with the commit-cadence: multi
    flag is honored when repo_root is passed (mirrors the real AlgoBooth mcp-test
    skill); without repo_root the same name reads False. Flag-in-prose-only (no
    frontmatter block hit) also reads False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        skill_dir = repo / ".claude" / "skills" / "repo-only-multi-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: repo-only-multi-skill\ncommit-cadence: multi\n---\n# X\n",
            encoding="utf-8",
        )
        assert lazy_core.skill_declares_multi_commit(
            "repo-only-multi-skill", repo_root=repo
        ) is True
        assert lazy_core.skill_declares_multi_commit("repo-only-multi-skill") is False
        prose_dir = repo / ".claude" / "skills" / "prose-only-multi-skill"
        prose_dir.mkdir(parents=True)
        (prose_dir / "SKILL.md").write_text(
            "---\nname: prose-only-multi-skill\n---\n\ncommit-cadence: multi\n",
            encoding="utf-8",
        )
        assert lazy_core.skill_declares_multi_commit(
            "prose-only-multi-skill", repo_root=repo
        ) is False


def test_build_hardening_emit_command_process_friction_binding():
    """WU-3: build_hardening_emit_command given a process-friction oldest entry
    emits trigger_kind=process-friction and binds the friction reason/detail INTO
    the @requires evidence keys (friction_reason → denied_prompt_summary,
    friction_detail → denial_reason) so the dispatch-hardening.md template — which
    @requires those shared keys for every trigger_kind — actually resolves.
    Binding friction-specific context keys instead left the required keys unbound
    and emit_dispatch_prompt refused the whole route (the broken-route defect)."""
    _guard()
    friction_entry = {
        "ts": 1.0,
        "kind": "process-friction",
        "reason_head": "cycle-bracket-break",
        "detail": "run identity changed mid-cycle",
        "acked": False,
    }
    cmd = lazy_core.build_hardening_emit_command(
        "lazy-state.py",
        item_id="my-bug",
        oldest_deny=friction_entry,
        probe_summary="probe",
        registry_summary="empty",
        cwd="/repo",
    )
    assert "trigger_kind=process-friction" in cmd, cmd
    # The friction reason/detail are bound INTO the shared @requires evidence keys.
    assert "denied_prompt_summary=cycle-bracket-break" in cmd, cmd
    assert "denial_reason=" in cmd, cmd
    assert "run identity changed mid-cycle" in cmd, cmd
    # The friction-specific key names must NOT leak (they are not in @requires and
    # would be inert residue / an unbound-token refusal in the template).
    assert "friction_reason=" not in cmd, cmd
    assert "friction_detail=" not in cmd, cmd


def test_process_friction_context_resolves_hardening_template():
    """Regression (broken-hardening-route defect): the context keys
    build_hardening_emit_command produces for a process-friction entry MUST
    satisfy dispatch-hardening.md's @requires so emit_dispatch_prompt resolves the
    route. Before the fix, the friction branch emitted friction_reason/
    friction_detail and emit_dispatch_prompt REFUSED with 'requires context key
    denied_prompt_summary'. This couples build_hardening_emit_command's bindings to
    the template's @requires so the two cannot silently drift again."""
    _guard()
    # The exact context dict the emit command supplies (mirrors the --context
    # bindings build_hardening_emit_command emits for a process-friction entry),
    # routed through normalize_hardening_dispatch_context exactly as the CLI
    # --emit-dispatch hardening handler does — which injects the `blocking`
    # default (n/a (auto-trigger)) the template now @requires
    # (no-mid-run-observed-friction-harden-dispatch §1).
    ctx = lazy_core.normalize_hardening_dispatch_context({
        "trigger_kind": "process-friction",
        "item_id": "hardening-blind-to-process-friction",
        "denied_prompt_summary": "unexpected-commits",
        "denial_reason": "HEAD advanced 2 commits since --cycle-begin",
        "probe_json": "step=Step 9 pending_hardening=1",
        "registry_state": "5 entries, 4 unconsumed",
        "cwd": "/repo",
    })
    res = lazy_core.emit_dispatch_prompt("hardening", ctx, pipeline="feature")
    assert res.get("ok") is True, res  # must NOT refuse
    assert "process-friction" in res["prompt"], res
    assert "unexpected-commits" in res["prompt"], res


def test_build_hardening_emit_command_validate_deny_unchanged():
    """WU-3: a normal deny entry still emits trigger_kind=validate-deny with the
    denied_prompt_summary/denial_reason bindings (no regression)."""
    _guard()
    deny_entry = {
        "ts": 1.0, "tool_use_id": "tu", "denied_sha12": "abc",
        "reason_head": "some deny reason", "prompt_head": "some prompt",
        "acked": False,
    }
    cmd = lazy_core.build_hardening_emit_command(
        "lazy-state.py",
        item_id="feat",
        oldest_deny=deny_entry,
        probe_summary="probe",
        registry_summary="empty",
        cwd="/repo",
    )
    assert "trigger_kind=validate-deny" in cmd, cmd
    assert "denied_prompt_summary=" in cmd, cmd
    assert "denial_reason=" in cmd, cmd


def test_build_hardening_emit_command_observed_friction():
    """no-mid-run-observed-friction-harden-dispatch §1: build_hardening_emit_command
    given an observed_friction dict emits trigger_kind=observed-friction driven by
    ORCHESTRATOR-SUPPLIED context (NOT a deny-ledger entry) — the friction_summary/
    friction_detail/blocking keys, item_id, and cwd. oldest_deny is ignored in this
    mode (there is no ledger entry behind an observed gap)."""
    _guard()
    cmd = lazy_core.build_hardening_emit_command(
        "lazy-state.py",
        item_id="managed-llm-credits",
        oldest_deny=None,
        probe_summary="unused-in-observed-mode",
        registry_summary="unused-in-observed-mode",
        cwd="/repo",
        observed_friction={
            "friction_summary": "scenario-yaml drift carve-out missing",
            "friction_detail": "the gate recognizer rejects a legit '#'-header row",
            "blocking": False,
        },
    )
    assert "trigger_kind=observed-friction" in cmd, cmd
    assert "friction_summary=" in cmd, cmd
    assert "scenario-yaml drift carve-out missing" in cmd, cmd
    assert "friction_detail=" in cmd, cmd
    assert "blocking=false" in cmd, cmd
    assert "item_id=managed-llm-credits" in cmd, cmd
    # The observed-friction branch must NOT emit the auto-trigger kinds.
    assert "trigger_kind=validate-deny" not in cmd, cmd
    assert "trigger_kind=process-friction" not in cmd, cmd


def test_build_hardening_emit_command_observed_friction_blocking_true():
    """A run-blocking observed friction emits blocking=true (the foreground/await
    branch of the §3 block/background policy)."""
    _guard()
    cmd = lazy_core.build_hardening_emit_command(
        "bug-state.py",
        item_id="b1",
        oldest_deny=None,
        probe_summary="",
        registry_summary="",
        cwd="/repo",
        observed_friction={
            "friction_summary": "s", "friction_detail": "d", "blocking": True,
        },
    )
    assert "blocking=true" in cmd, cmd


def test_normalize_hardening_context_observed_friction_rebinds():
    """no-mid-run-observed-friction-harden-dispatch §1: normalize_hardening_dispatch_context
    rebinds an observed-friction context's friction_summary → denied_prompt_summary and
    friction_detail → denial_reason (the SAME rebind the process-friction branch does), and
    injects observed-friction placeholders for probe_json / registry_state so the template's
    @requires keys resolve. The original context is not mutated (non-destructive)."""
    _guard()
    original = {
        "trigger_kind": "observed-friction",
        "item_id": "feat",
        "friction_summary": "missing SPEC-exemption path",
        "friction_detail": "gate-coverage has no exemption for a SKIP_MCP feature",
        "blocking": "false",
        "cwd": "/repo",
    }
    norm = lazy_core.normalize_hardening_dispatch_context(original)
    assert norm["denied_prompt_summary"] == "missing SPEC-exemption path", norm
    assert norm["denial_reason"].startswith("gate-coverage has no exemption"), norm
    assert norm["probe_json"], norm
    assert norm["registry_state"], norm
    assert norm["blocking"] == "false", norm
    # Non-destructive: the caller's dict gains no evidence keys.
    assert "denied_prompt_summary" not in original, original


def test_normalize_hardening_context_auto_trigger_passthrough():
    """A non-observed-friction (auto-trigger) context passes through with ONLY the
    blocking default added — the shared evidence keys are untouched, so the
    auto-trigger paths keep binding denied_prompt_summary/denial_reason exactly as
    before. This is what keeps the shared {blocking} template token bound for the
    auto-triggers (which never supply it)."""
    _guard()
    ctx = lazy_core.normalize_hardening_dispatch_context({
        "trigger_kind": "validate-deny",
        "item_id": "feat",
        "denied_prompt_summary": "some prompt",
        "denial_reason": "hash mismatch",
        "probe_json": "step=1",
        "registry_state": "empty",
        "cwd": "/repo",
    })
    assert ctx["blocking"] == "n/a (auto-trigger)", ctx
    assert ctx["denied_prompt_summary"] == "some prompt", ctx
    assert ctx["denial_reason"] == "hash mismatch", ctx


def test_observed_friction_context_resolves_hardening_template():
    """Coupling regression (no-mid-run-observed-friction-harden-dispatch §1): the context
    the CLI --emit-dispatch hardening handler builds for an observed-friction dispatch —
    the friction keys, run through normalize_hardening_dispatch_context — MUST satisfy
    dispatch-hardening.md's @requires so emit_dispatch_prompt resolves the route (ok=True),
    exactly like the process-friction coupling test. This couples the normalizer's bindings
    to the template's @requires so the two cannot silently drift."""
    _guard()
    ctx = lazy_core.normalize_hardening_dispatch_context({
        "trigger_kind": "observed-friction",
        "item_id": "managed-llm-credits",
        "friction_summary": "verification-row recognizer inconsistency",
        "friction_detail": "the row recognizer misses a valid verification header variant",
        "blocking": "false",
        "cwd": "/repo",
    })
    res = lazy_core.emit_dispatch_prompt("hardening", ctx, pipeline="feature")
    assert res.get("ok") is True, res  # must NOT refuse on a missing @requires key
    assert "observed-friction" in res["prompt"], res
    assert "verification-row recognizer inconsistency" in res["prompt"], res


def test_read_mcp_runtime_decision_required_reason_mentions_not_required():
    """A ``**MCP runtime:** required`` line whose REASON PROSE contains the
    literal 'not-required' must resolve to runtime-up, NOT no-runtime.

    Regression for the first-time-login deadlock (2026-07): the old unanchored
    ``if "not-required" in stripped`` substring test mis-classified a required
    line reading '... not eligible for not-required' as no-runtime, deadlocking
    Step 9 (step_repeat_count=3). The anchored value-token test must ignore the
    reason prose entirely.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        spec.mkdir()
        (spec / "PHASES.md").write_text(
            "# Phases\n\n"
            "**MCP runtime:** required — this feature is not eligible "
            "for not-required and must boot the runtime\n",
            encoding="utf-8",
        )
        variant, reason = lazy_core._read_mcp_runtime_decision(str(spec))
        assert variant == "runtime-up"
        assert reason is None


def test_read_mcp_runtime_decision_not_required_value_token():
    """A genuine ``**MCP runtime:** not-required`` line resolves to no-runtime
    and extracts the post-dash reason. Guards against the anchored fix
    over-tightening and dropping the true not-required case."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        spec.mkdir()
        (spec / "PHASES.md").write_text(
            "# Phases\n\n"
            "**MCP runtime:** not-required — the plan declares no "
            "MCP-reachable surface\n",
            encoding="utf-8",
        )
        variant, reason = lazy_core._read_mcp_runtime_decision(str(spec))
        assert variant == "no-runtime"
        assert reason == "the plan declares no MCP-reachable surface"


# ---------------------------------------------------------------------------
# harness-hardening-retro-fixes Phase 1 (WU-2) — over-fit detector presence gate
# ---------------------------------------------------------------------------
#
# The over-fit detector in harden-harness/SKILL.md Step 3 is LLM-executed prose
# (this repo's MCP gate is operator-exempt), so the verifiable proof is a
# presence gate: assert the four smell signals, the recurrence threshold, the
# generalization-bound discipline, and the /spec-vs-/spec-bug choice rule are all
# findable in the SKILL.md text. RED before WU-1 authored the prose; GREEN after.

def test_harden_harness_overfit_prose_present():
    """harness-hardening-retro-fixes Phase 1 / WU-2 contract: the over-fit
    detector subsection in harden-harness/SKILL.md Step 3 enumerates:
      - all four over-fit smell signals;
      - the recurrence threshold (phrase-match → first occurrence; non-phrase → >=2);
      - the generalization-bound discipline (smallest class + cite instance + name boundary);
      - the /spec vs /spec-bug spin-off choice rule + the adhoc-enqueue front-enqueue path;
      - the no-double-blocking + self-recursion-guard-preserved notes.

    RED reason (before WU-1): none of these strings are present in SKILL.md.
    """
    _guard()  # mirror harness conventions for a consistent failure shape

    assert _HARDEN_SKILL_PATH.exists(), (
        f"harden-harness SKILL.md missing at {_HARDEN_SKILL_PATH}"
    )
    text = _HARDEN_SKILL_PATH.read_text(encoding="utf-8")
    lower = text.lower()

    # --- Over-fit detector subsection exists ---
    assert "over-fit detector" in lower, (
        "SKILL.md Step 3 must contain an 'over-fit detector' subsection (WU-1); "
        "not found"
    )

    # --- Smell signal 1: literal-phrase-to-matcher ---
    assert "literal-phrase-to-matcher" in lower or (
        "literal phrase" in lower and "matcher" in lower
    ), (
        "Over-fit detector must enumerate smell signal 1 "
        "(literal phrase added to a matcher / regex / header list / keyword set)"
    )

    # --- Smell signal 2: class recurred >=2 in the hardening log ---
    assert "recurred" in lower and "hardening log" in lower, (
        "Over-fit detector must enumerate smell signal 2 "
        "(root-cause class recurred >=2 in the hardening log)"
    )

    # --- Smell signal 3: agent self-flags the fix as narrow ---
    assert "self-flag" in lower or "will gap again" in lower, (
        "Over-fit detector must enumerate smell signal 3 "
        "(agent self-flags the fix as narrow — 'this will gap again on the next variant')"
    )

    # --- Smell signal 4: repeated deterministic dance (toolify candidate) ---
    assert "deterministic dance" in lower and "toolify" in lower, (
        "Over-fit detector must enumerate smell signal 4 "
        "(repeated deterministic dance — toolify candidate per the framework's bar)"
    )

    # --- Recurrence threshold (SPEC Open Question 1): phrase-match first; non-phrase >=2 ---
    assert "recurrence threshold" in lower, (
        "Over-fit detector must state the recurrence threshold explicitly"
    )
    assert "first occurrence" in lower, (
        "Recurrence threshold must say a phrase-match patch spins off on the FIRST occurrence"
    )
    assert ">=2" in text or "≥2" in text or ">= 2" in text or "≥ 2" in text, (
        "Recurrence threshold must say a non-phrase recurrence needs >=2 occurrences"
    )

    # --- Generalization bound ("most general within reason") ---
    assert "generalization bound" in lower, (
        "Over-fit detector must state the generalization-bound discipline"
    )
    assert "smallest class" in lower, (
        "Generalization bound must target the smallest class subsuming the instance + neighbors"
    )
    assert "class boundary" in lower, (
        "Generalization bound must require naming the class boundary explicitly"
    )

    # --- Spin-off action + choice rule + adhoc-enqueue front-enqueue ---
    assert "spin-off action" in lower, (
        "Over-fit detector must describe the spin-off action"
    )
    # Choice rule: structural/new-capability -> /spec; defect/regression/toolify -> /spec-bug.
    assert "/spec-bug" in text and "/spec" in text, (
        "Spin-off action must state the /spec vs /spec-bug choice rule"
    )
    assert "front-enqueue" in lower, (
        "Spin-off action must front-enqueue the generalization spec"
    )
    assert "adhoc-enqueue" in lower, (
        "Spin-off action must invoke via the adhoc-enqueue protocol "
        "(references _components/adhoc-enqueue.md --type bug path)"
    )

    # --- No double-blocking + self-recursion guard preserved ---
    assert "no double-blocking" in lower or "never block" in lower, (
        "Over-fit detector must state no-double-blocking (the instance is already fixed, "
        "so the spin-off never blocks the current run)"
    )
    assert "self-recursion guard" in lower, (
        "Over-fit detector must state the self-recursion-guard-preserved note "
        "(a spin-off is an enqueue, not a recursive hardening dispatch)"
    )

    # --- Step 4 round template records BOTH patch AND spin-off ---
    assert "over-fit spin-off" in lower, (
        "Step 4 round template must gain an 'Over-fit spin-off:' record line"
    )
    # --- Return format gains a spinoff field ---
    assert "spinoff" in lower, (
        "Return format must gain a 'spinoff' field (id + reason, or none)"
    )


# ---------------------------------------------------------------------------
# dispatch-guard-denies-workstation-subsubagent-split (decision 4, 2026-07-10)
# — the skill-declared sub-subagent capability predicate, the consumed fence,
# and the cycle-marker stamping the guard's workstation exemption reads.
# ---------------------------------------------------------------------------

def test_skill_declares_subagent_model_user_level():
    """The user-level SKILL.md frontmatter flag drives the predicate: skills
    with a sub-subagent orchestration model read True; single-context skills,
    pseudo-skills, and junk names all fail closed to False."""
    _guard()
    # Flagged: /execute-plan's test-agent/impl-agent split (the Round-9 case)
    # and /spec-phases' phase-writer launch (the Round-11 case).
    assert lazy_core.skill_declares_subagent_model("execute-plan") is True
    assert lazy_core.skill_declares_subagent_model("/spec-phases") is True
    # Not flagged: a single-context skill keeps the deny (no exemption).
    assert lazy_core.skill_declares_subagent_model("realign-spec") is False
    # Fail-closed shapes: falsy, pseudo-skill, unknown, path traversal.
    assert lazy_core.skill_declares_subagent_model(None) is False
    assert lazy_core.skill_declares_subagent_model("") is False
    assert lazy_core.skill_declares_subagent_model("__mark_complete__") is False
    assert lazy_core.skill_declares_subagent_model("no-such-skill-xyz") is False
    assert lazy_core.skill_declares_subagent_model("../../etc/passwd") is False


def test_skill_declares_subagent_model_repo_scoped():
    """A repo-scoped .claude/skills/<name>/SKILL.md with the flag is honored
    when repo_root is passed; without repo_root the same name reads False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        skill_dir = repo / ".claude" / "skills" / "repo-only-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: repo-only-skill\nsubagent-model: true\n---\n# X\n",
            encoding="utf-8",
        )
        assert lazy_core.skill_declares_subagent_model(
            "repo-only-skill", repo_root=repo
        ) is True
        assert lazy_core.skill_declares_subagent_model("repo-only-skill") is False
        # Flag mentioned only in PROSE (no frontmatter block hit) → False.
        prose_dir = repo / ".claude" / "skills" / "prose-only-skill"
        prose_dir.mkdir(parents=True)
        (prose_dir / "SKILL.md").write_text(
            "---\nname: prose-only-skill\n---\n\nsubagent-model: true\n",
            encoding="utf-8",
        )
        assert lazy_core.skill_declares_subagent_model(
            "prose-only-skill", repo_root=repo
        ) is False


def test_emission_consumed_by_nonce_fence():
    """The consumed fence: True only for an existing, consumed registry entry.
    Unconsumed, unknown, and falsy nonces all fail closed to False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            entry = lazy_core.register_emission("cycle prompt body", "cycle")
            nonce = entry["nonce"]
            # Registered but NOT yet dispatched → fence closed.
            assert lazy_core.emission_consumed_by_nonce(nonce) is False
            assert lazy_core.dispatch.consume_nonce(nonce, consumer="toolu_x") is True
            # Dispatch landed → fence open.
            assert lazy_core.emission_consumed_by_nonce(nonce) is True
            # Unknown / falsy nonces fail closed.
            assert lazy_core.emission_consumed_by_nonce("feedbeef") is False
            assert lazy_core.emission_consumed_by_nonce("") is False
        finally:
            _clear_state_dir()


def test_resolve_cycle_worker_nonce_rebinds_fresh_hex():
    """resolve_cycle_worker_nonce rebinds a fresh (unregistered) --cycle-begin
    nonce to this cycle's worker emission (the newest UNCONSUMED cycle entry),
    preserves a nonce the orchestrator already reused from the registry, and
    degrades to the passed value when no unconsumed cycle emission exists.

    This is the consumed-fence wiring fix (dispatch-guard-denies-workstation-
    subsubagent-split, 2026-07-11): the guard exemption keys on the marker nonce,
    which was dead-on-arrival whenever the orchestrator passed a fresh hex."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # No registry yet → passed nonce preserved (safe degradation).
            assert lazy_core.resolve_cycle_worker_nonce("freshhex01") == "freshhex01"
            # Register this cycle's (unconsumed) worker emission.
            entry = lazy_core.register_emission("the cycle prompt", "cycle")
            emission_nonce = entry["nonce"]
            # A fresh, unregistered --nonce rebinds to the emission nonce.
            assert lazy_core.resolve_cycle_worker_nonce("freshhex01") == emission_nonce
            # A reused (already-registered) nonce is preserved unchanged.
            assert lazy_core.resolve_cycle_worker_nonce(emission_nonce) == emission_nonce
            # Once consumed there is no UNCONSUMED cycle emission to bind to →
            # a fresh hex degrades to itself (fence stays closed — the safe
            # pre-fix behavior; in production the rebind happens BEFORE consume).
            lazy_core.dispatch.consume_nonce(emission_nonce, consumer="toolu_w")
            assert lazy_core.resolve_cycle_worker_nonce("freshhex01") == "freshhex01"
        finally:
            _clear_state_dir()


def test_run_end_unacked_hardening_refusal_emits_gate_refusal_bug():
    """bug-state.py mirror of the unacked-hardening refusal emission."""
    _assert_run_end_refusal_emits(
        "bug-state.py", "bug", [], seed_deny=True,
        expected_gate="unacked-hardening",
    )


def test_run_end_efficacy_flush_refusal_emits_gate_refusal_bug():
    """bug-state.py mirror of the efficacy-coverage-missing refusal emission."""
    _assert_run_end_refusal_emits(
        "bug-state.py", "bug", [], seed_deny=False,
        expected_gate="efficacy-coverage-missing",
    )


def _assert_run_end_success_no_gate_refusal(script, pipeline):
    _guard()
    with tempfile.TemporaryDirectory() as td:
        try:
            r, events, marker_exists = _drive_run_end(
                script, pipeline,
                ["--efficacy-skip-authorized",
                 "--terminal-reason", "all-features-complete"],
                seed_deny=False, state_dir=Path(td),
            )
            assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
            assert not marker_exists, "a successful --run-end deletes the marker"
            assert events, "expected a run-end telemetry event"
            assert events[-1].get("event") == "run-end", events
            assert all(e.get("event") != "gate-refusal" for e in events), (
                "a successful --run-end must NOT emit a gate-refusal", events
            )
        finally:
            _clear_state_dir()


def test_run_end_success_emits_run_end_not_gate_refusal_lazy():
    """Over-emission guard: a passing lazy-state.py --run-end emits run-end and
    NO gate-refusal (the emissions sit INSIDE each refusal branch)."""
    _assert_run_end_success_no_gate_refusal("lazy-state.py", "feature")


def test_run_end_success_emits_run_end_not_gate_refusal_bug():
    """Over-emission guard mirror for bug-state.py."""
    _assert_run_end_success_no_gate_refusal("bug-state.py", "bug")


# ---------------------------------------------------------------------------
# harden Round 31 (adhoc-decision-resume-cannot-enact-receipt-exempt-wont-fix)
# — the apply-resolution needs-input path must be able to enact an
# operator-directed receipt-EXEMPT terminal close (Won't-fix / Superseded).
# ---------------------------------------------------------------------------
def test_standard_bindings_split_terminal_statuses():
    """_standard_dispatch_bindings exposes the split receipt-gated vs.
    receipt-exempt terminal statuses per pipeline, and leaves the compound
    forbidden_status UNCHANGED (the other templates still rely on it)."""
    _guard()
    bug = lazy_core._standard_dispatch_bindings("bug")
    feat = lazy_core._standard_dispatch_bindings("feature")
    assert bug["receipt_gated_status"] == "Fixed", bug
    assert bug["receipt_exempt_status"] == "Won't-fix", bug
    assert feat["receipt_gated_status"] == "Complete", feat
    assert feat["receipt_exempt_status"] == "Superseded", feat
    # forbidden_status must remain the compound (other templates depend on it).
    assert bug["forbidden_status"] == "Fixed or Won't-fix", bug
    assert feat["forbidden_status"] == "Complete", feat


def test_apply_resolution_emits_terminal_disposition_close():
    """The emitted apply-resolution prompt carries the needs-input
    terminal-disposition step that SETS the receipt-exempt status
    (Won't-fix for a bug, Superseded for a feature), and the constraint
    permits it — closing the infinite needs-input loop for an operator-chosen
    working-as-designed close (adhoc-decision-resume-cannot-enact-...)."""
    _guard()
    ctx = {
        "item_name": "x", "spec_path": "/tmp/x", "sentinel_path": "/tmp/x/NEEDS_INPUT.md",
        "resolution_summary": "close", "resolution_kind": "needs-input",
        "chosen_path": "Close as working-as-designed", "item_id": "x", "cwd": "/tmp/x",
    }
    r_bug = lazy_core.emit_dispatch_prompt(
        "apply-resolution", ctx, pipeline="bug", template_dir=_REAL_TEMPLATE_DIR,
    )
    assert r_bug.get("ok") is True, r_bug
    pb = r_bug["prompt"]
    assert "**Status:** Won't-fix" in pb, "bug prompt must offer the Won't-fix close"
    assert "TERMINAL DISPOSITION" in pb, "terminal-disposition step missing"
    # The constraint must PERMIT the receipt-exempt terminal, not forbid it.
    assert "receipt-EXEMPT terminal status (Won't-fix)" in pb, pb[-800:]
    assert not _TOKEN_RESIDUE_RE.findall(pb), _TOKEN_RESIDUE_RE.findall(pb)

    r_feat = lazy_core.emit_dispatch_prompt(
        "apply-resolution", ctx, pipeline="feature", template_dir=_REAL_TEMPLATE_DIR,
    )
    assert r_feat.get("ok") is True, r_feat
    assert "**Status:** Superseded" in r_feat["prompt"], "feature prompt must offer the Superseded close"


_TESTS = [
    ("test_load_context_json_valid_long_value", test_load_context_json_valid_long_value),
    ("test_load_context_json_rejects_non_object", test_load_context_json_rejects_non_object),
    ("test_load_context_json_rejects_malformed", test_load_context_json_rejects_malformed),
    ("test_load_context_json_coerces_values_to_str", test_load_context_json_coerces_values_to_str),
    ("test_update_repeat_counts_step_counter_ordered_args_advance_resets", test_update_repeat_counts_step_counter_ordered_args_advance_resets),
    ("test_update_repeat_counts_step_multipart_progress_does_not_trip", test_update_repeat_counts_step_multipart_progress_does_not_trip),
    ("test_update_repeat_counts_step_same_args_oscillation_still_trips", test_update_repeat_counts_step_same_args_oscillation_still_trips),
    ("test_update_repeat_counts_legacy_file_without_step_keys", test_update_repeat_counts_legacy_file_without_step_keys),
    ("test_update_repeat_count_wrapper_still_returns_int", test_update_repeat_count_wrapper_still_returns_int),
    ("test_gap_a_meta_class_consume_does_not_defeat_step_debounce", test_gap_a_meta_class_consume_does_not_defeat_step_debounce),
    ("test_gap_a_meta_class_consume_does_not_defeat_dispatch_tuple_debounce", test_gap_a_meta_class_consume_does_not_defeat_dispatch_tuple_debounce),
    ("test_gap_a_cycle_class_consume_still_trips_despite_intervening_meta", test_gap_a_cycle_class_consume_still_trips_despite_intervening_meta),
    ("test_f1_repeat_count_head_reset_wins_over_debounce", test_f1_repeat_count_head_reset_wins_over_debounce),
    ("test_format_cycle_header_full", test_format_cycle_header_full),
    ("test_format_cycle_header_missing_fields", test_format_cycle_header_missing_fields),
    ("test_emit_cycle_prompt_symbol_present", test_emit_cycle_prompt_symbol_present),
    ("test_emit_cycle_prompt_binding_matrix_real_template", test_emit_cycle_prompt_binding_matrix_real_template),
    ("test_emit_cycle_prompt_mcp_test_variant_anchors_real_template", test_emit_cycle_prompt_mcp_test_variant_anchors_real_template),
    ("test_emit_cycle_prompt_bug_tokens_real_template", test_emit_cycle_prompt_bug_tokens_real_template),
    ("test_emit_cycle_prompt_pseudo_and_idle_return_none", test_emit_cycle_prompt_pseudo_and_idle_return_none),
    ("test_emit_cycle_prompt_loop_append_and_model_flip", test_emit_cycle_prompt_loop_append_and_model_flip),
    ("test_emit_cycle_prompt_mcp_test_cycle_model_haiku", test_emit_cycle_prompt_mcp_test_cycle_model_haiku),
    ("test_emit_cycle_prompt_mcp_test_legacy_md_escalates_sonnet", test_emit_cycle_prompt_mcp_test_legacy_md_escalates_sonnet),
    ("test_emit_cycle_prompt_mcp_test_ready_yaml_stays_haiku", test_emit_cycle_prompt_mcp_test_ready_yaml_stays_haiku),
    ("test_emit_cycle_prompt_mcp_test_loop_cycle_model_sonnet", test_emit_cycle_prompt_mcp_test_loop_cycle_model_sonnet),
    ("test_emit_cycle_prompt_mechanical_part_cycle_model_sonnet", test_emit_cycle_prompt_mechanical_part_cycle_model_sonnet),
    ("test_emit_cycle_prompt_complex_part_cycle_model_opus", test_emit_cycle_prompt_complex_part_cycle_model_opus),
    ("test_emit_cycle_prompt_untagged_part_cycle_model_opus", test_emit_cycle_prompt_untagged_part_cycle_model_opus),
    ("test_emit_cycle_prompt_complex_part_loop_stays_opus", test_emit_cycle_prompt_complex_part_loop_stays_opus),
    ("test_emit_cycle_prompt_untagged_part_loop_stays_opus", test_emit_cycle_prompt_untagged_part_loop_stays_opus),
    ("test_emit_cycle_prompt_mechanical_part_loop_stays_sonnet", test_emit_cycle_prompt_mechanical_part_loop_stays_sonnet),
    ("test_emit_cycle_prompt_non_execute_plan_ignores_complexity", test_emit_cycle_prompt_non_execute_plan_ignores_complexity),
    ("test_emit_cycle_prompt_section_selection_synthetic", test_emit_cycle_prompt_section_selection_synthetic),
    ("test_emit_cycle_prompt_refuses_unknown_token_synthetic", test_emit_cycle_prompt_refuses_unknown_token_synthetic),
    ("test_emit_cycle_prompt_content_braces_in_state_value_do_not_refuse", test_emit_cycle_prompt_content_braces_in_state_value_do_not_refuse),
    ("test_emit_cycle_prompt_mcp_variant_routing_synthetic", test_emit_cycle_prompt_mcp_variant_routing_synthetic),
    ("test_emit_cycle_prompt_work_branch_fallback_non_git", test_emit_cycle_prompt_work_branch_fallback_non_git),
    ("test_emit_cycle_prompt_sub_skill_args_none_binds_empty", test_emit_cycle_prompt_sub_skill_args_none_binds_empty),
    ("test_emit_cycle_prompt_addenda_absent_is_byte_identical", test_emit_cycle_prompt_addenda_absent_is_byte_identical),
    ("test_emit_cycle_prompt_addenda_selected_and_appended_after_base", test_emit_cycle_prompt_addenda_selected_and_appended_after_base),
    ("test_emit_cycle_prompt_addenda_filtered_by_skill_and_pipeline_and_mode", test_emit_cycle_prompt_addenda_filtered_by_skill_and_pipeline_and_mode),
    ("test_emit_cycle_prompt_addenda_tokens_bound", test_emit_cycle_prompt_addenda_tokens_bound),
    ("test_emit_cycle_prompt_addenda_residue_refuses_naming_file", test_emit_cycle_prompt_addenda_residue_refuses_naming_file),
    ("test_emit_cycle_prompt_addenda_before_loop_block", test_emit_cycle_prompt_addenda_before_loop_block),
    ("test_emit_cycle_prompt_hosts_windows_selected_on_win32", test_emit_cycle_prompt_hosts_windows_selected_on_win32),
    ("test_emit_cycle_prompt_hosts_windows_excluded_on_non_windows", test_emit_cycle_prompt_hosts_windows_excluded_on_non_windows),
    ("test_emit_cycle_prompt_hosts_windows_addenda_excluded_on_non_windows", test_emit_cycle_prompt_hosts_windows_addenda_excluded_on_non_windows),
    ("test_env_dialect_section_byte_budget", test_env_dialect_section_byte_budget),
    ("test_bug_state_retro_fresh_routes_past_step8", test_bug_state_retro_fresh_routes_past_step8),
    ("test_normalize_widened_equivalence_pairs", test_normalize_widened_equivalence_pairs),
    ("test_f2b_emdash_hashes_equal_to_hyphen", test_f2b_emdash_hashes_equal_to_hyphen),
    ("test_f2b_curly_quotes_hash_equal_to_straight", test_f2b_curly_quotes_hash_equal_to_straight),
    ("test_f2b_nbsp_hashes_equal_to_space", test_f2b_nbsp_hashes_equal_to_space),
    ("test_f2b_genuine_word_change_still_differs", test_f2b_genuine_word_change_still_differs),
    ("test_single_slot_dispatch_templates", test_single_slot_dispatch_templates),
    ("test_emit_dispatch_cycle_header_marker_gated", test_emit_dispatch_cycle_header_marker_gated),
    ("test_record_decision_cli_and_apply_resolution_binds_end_to_end", test_record_decision_cli_and_apply_resolution_binds_end_to_end),
    ("test_emit_dispatch_always_emits_json_on_error", test_emit_dispatch_always_emits_json_on_error),
    ("test_f1a_default_deny_reason_names_customization_path", test_f1a_default_deny_reason_names_customization_path),
    ("test_f1a_hardening_cap_reason_unchanged", test_f1a_hardening_cap_reason_unchanged),
    ("test_f1b_pure_suffix_cycle_prompt_auto_readmits", test_f1b_pure_suffix_cycle_prompt_auto_readmits),
    ("test_f1b_in_body_edit_still_denies", test_f1b_in_body_edit_still_denies),
    ("test_f1b_auto_readmit_error_falls_through_to_deny", test_f1b_auto_readmit_error_falls_through_to_deny),
    ("test_f1b_register_emission_stores_normalized_prompt_text", test_f1b_register_emission_stores_normalized_prompt_text),
    ("test_registry_register_lookup_consume", test_registry_register_lookup_consume),
    ("test_registry_ttl", test_registry_ttl),
    ("test_crlf_lf_normalization", test_crlf_lf_normalization),
    ("test_advance_run_counters_census_regression_does_not_strand", test_advance_run_counters_census_regression_does_not_strand),
    ("test_subprocess_emit_prompt_with_marker_writes_registry", test_subprocess_emit_prompt_with_marker_writes_registry),
    ("test_repeat_count_peek_does_not_advance_marker_counters", test_repeat_count_peek_does_not_advance_marker_counters),
    ("test_emit_dispatch_symbols_present", test_emit_dispatch_symbols_present),
    ("test_emit_dispatch_real_template_binding_matrix", test_emit_dispatch_real_template_binding_matrix),
    ("test_emit_dispatch_refuses_missing_requires", test_emit_dispatch_refuses_missing_requires),
    ("test_emit_dispatch_refuses_unbound_residue", test_emit_dispatch_refuses_unbound_residue),
    ("test_emit_dispatch_content_braces_in_value_do_not_refuse", test_emit_dispatch_content_braces_in_value_do_not_refuse),
    ("test_emit_dispatch_section_filtering", test_emit_dispatch_section_filtering),
    ("test_emit_dispatch_unknown_class_raises", test_emit_dispatch_unknown_class_raises),
    ("test_emit_dispatch_cli_registry_gating", test_emit_dispatch_cli_registry_gating),
    ("test_emit_dispatch_cli_bug_state_mirror", test_emit_dispatch_cli_bug_state_mirror),
    ("test_hardening_dispatch_class_present", test_hardening_dispatch_class_present),
    ("test_hardening_template_binding", test_hardening_template_binding),
    ("test_hardening_skill_file_contract", test_hardening_skill_file_contract),
    ("test_hardening_cli_emit_and_register", test_hardening_cli_emit_and_register),
    ("test_f2a_register_emission_stores_prompt_raw", test_f2a_register_emission_stores_prompt_raw),
    ("test_f2a_resolve_emission_fresh_nonce_returns_entry", test_f2a_resolve_emission_fresh_nonce_returns_entry),
    ("test_f2a_resolve_emission_consumed_nonce_returns_none", test_f2a_resolve_emission_consumed_nonce_returns_none),
    ("test_f2a_resolve_emission_stale_nonce_returns_none", test_f2a_resolve_emission_stale_nonce_returns_none),
    ("test_resolve_consumed_emission_returns_prompt_raw_for_consumed_nonce", test_resolve_consumed_emission_returns_prompt_raw_for_consumed_nonce),
    ("test_resolve_consumed_emission_unknown_nonce_returns_none", test_resolve_consumed_emission_unknown_nonce_returns_none),
    ("test_resolve_consumed_emission_unconsumed_returns_none", test_resolve_consumed_emission_unconsumed_returns_none),
    ("test_resolve_consumed_emission_ttl_expired_returns_none", test_resolve_consumed_emission_ttl_expired_returns_none),
    ("test_resolve_consumed_emission_predates_run_returns_none", test_resolve_consumed_emission_predates_run_returns_none),
    ("test_resolve_consumed_emission_never_mutates_consumed", test_resolve_consumed_emission_never_mutates_consumed),
    ("test_f2a_append_dispatch_by_reference_event_writes_ledger", test_f2a_append_dispatch_by_reference_event_writes_ledger),
    ("test_governing_file_set_includes_orchestrator_and_components", test_governing_file_set_includes_orchestrator_and_components),
    ("test_merged_priority_normalizes_tier_and_severity", test_merged_priority_normalizes_tier_and_severity),
    ("test_merged_priority_feature_tier_enum_to_int", test_merged_priority_feature_tier_enum_to_int),
    ("test_merged_priority_feature_multi_enum_takes_min", test_merged_priority_feature_multi_enum_takes_min),
    ("test_merged_priority_prerelease_ordering_p0_before_prerelease_before_p2", test_merged_priority_prerelease_ordering_p0_before_prerelease_before_p2),
    ("test_merged_worklist_both_populated_ordered_by_priority", test_merged_worklist_both_populated_ordered_by_priority),
    ("test_merged_worklist_bug_breaks_tie_at_equal_priority", test_merged_worklist_bug_breaks_tie_at_equal_priority),
    ("test_merged_worklist_aged_p2_bug_sorts_behind_p1_feature", test_merged_worklist_aged_p2_bug_sorts_behind_p1_feature),
    ("test_merged_head_override_diverges_when_p0_bug_outranks_current_feature", test_merged_head_override_diverges_when_p0_bug_outranks_current_feature),
    ("test_merged_head_override_diverges_when_higher_sev_bug_jumps_head", test_merged_head_override_diverges_when_higher_sev_bug_jumps_head),
    ("test_merged_head_override_none_when_head_is_current_item", test_merged_head_override_none_when_head_is_current_item),
    ("test_merged_head_override_none_on_empty_queues_or_missing_id", test_merged_head_override_none_on_empty_queues_or_missing_id),
    ("test_coordinator_arbitrated_emission_lane", test_coordinator_arbitrated_emission_lane),
    ("test_coordinator_arbitrated_emission_lease", test_coordinator_arbitrated_emission_lease),
    ("test_coordinator_arbitrated_emission_none", test_coordinator_arbitrated_emission_none),
    ("test_coordinator_arbitrated_emission_lane_precedes_lease", test_coordinator_arbitrated_emission_lane_precedes_lease),
    ("test_coordinator_arbitrated_emission_failsafe", test_coordinator_arbitrated_emission_failsafe),
    ("test_coordinator_exemption_diag_maps_reason_to_text", test_coordinator_exemption_diag_maps_reason_to_text),
    ("test_spec_dir_would_park_predicate", test_spec_dir_would_park_predicate),
    ("test_spec_dir_operator_deferred_predicate", test_spec_dir_operator_deferred_predicate),
    ("test_spec_dir_research_pending_predicate", test_spec_dir_research_pending_predicate),
    ("test_merged_head_nondispatchable_ids_excludes_parked_same_pipeline_head_no_deadlock", test_merged_head_nondispatchable_ids_excludes_parked_same_pipeline_head_no_deadlock),
    ("test_merged_head_nondispatchable_ids_excludes_parked_UNREACHED_same_pipeline_head", test_merged_head_nondispatchable_ids_excludes_parked_UNREACHED_same_pipeline_head),
    ("test_merged_head_nondispatchable_ids_excludes_operator_deferred_cross_pipeline_feature", test_merged_head_nondispatchable_ids_excludes_operator_deferred_cross_pipeline_feature),
    ("test_subprocess_bug_emit_prompt_oracle_excludes_operator_deferred_feature_head_no_withhold", test_subprocess_bug_emit_prompt_oracle_excludes_operator_deferred_feature_head_no_withhold),
    ("test_nondispatchable_item_ids_helper_is_retired", test_nondispatchable_item_ids_helper_is_retired),
    ("test_merged_worklist_exclude_ids_drops_parked_items", test_merged_worklist_exclude_ids_drops_parked_items),
    ("test_subprocess_emit_prompt_withholds_when_merged_head_is_p0_bug", test_subprocess_emit_prompt_withholds_when_merged_head_is_p0_bug),
    ("test_subprocess_emit_prompt_oracle_excludes_nondispatchable_bug_head_no_withhold", test_subprocess_emit_prompt_oracle_excludes_nondispatchable_bug_head_no_withhold),
    ("test_subprocess_bug_emit_prompt_oracle_excludes_nondispatchable_feature_head_no_withhold", test_subprocess_bug_emit_prompt_oracle_excludes_nondispatchable_feature_head_no_withhold),
    ("test_subprocess_emit_prompt_lane_marker_skips_merged_head_withhold", test_subprocess_emit_prompt_lane_marker_skips_merged_head_withhold),
    ("test_subprocess_emit_prompt_serial_tail_lease_held_skips_merged_head_withhold", test_subprocess_emit_prompt_serial_tail_lease_held_skips_merged_head_withhold),
    ("test_subprocess_emit_prompt_serial_tail_no_lease_still_withholds", test_subprocess_emit_prompt_serial_tail_no_lease_still_withholds),
    ("test_probe_skipped_ids_collects_all_skip_lists_and_resolves_names", test_probe_skipped_ids_collects_all_skip_lists_and_resolves_names),
    ("test_merged_head_override_gated_head_excluded_no_false_withhold", test_merged_head_override_gated_head_excluded_no_false_withhold),
    ("test_is_dispatchable_predicate_table", test_is_dispatchable_predicate_table),
    ("test_merged_head_nondispatchable_ids_same_pipeline_uses_probe_skipped_unchanged", test_merged_head_nondispatchable_ids_same_pipeline_uses_probe_skipped_unchanged),
    ("test_merged_head_nondispatchable_ids_facet_regressions_excluded_via_oracle", test_merged_head_nondispatchable_ids_facet_regressions_excluded_via_oracle),
    ("test_merged_head_nondispatchable_ids_new_category_auto_excluded", test_merged_head_nondispatchable_ids_new_category_auto_excluded),
    ("test_merged_head_nondispatchable_ids_research_surface_excluded_here", test_merged_head_nondispatchable_ids_research_surface_excluded_here),
    ("test_merged_head_nondispatchable_ids_dispatchable_head_not_excluded_byte_identity", test_merged_head_nondispatchable_ids_dispatchable_head_not_excluded_byte_identity),
    ("test_merged_head_nondispatchable_ids_short_circuit_at_first_dispatchable_head", test_merged_head_nondispatchable_ids_short_circuit_at_first_dispatchable_head),
    ("test_merged_head_nondispatchable_ids_below_current_never_probed", test_merged_head_nondispatchable_ids_below_current_never_probed),
    ("test_oracle_leaves_reused_signatures_unchanged", test_oracle_leaves_reused_signatures_unchanged),
    ("test_merged_head_nondispatchable_ids_in_process_isolation_characterization", test_merged_head_nondispatchable_ids_in_process_isolation_characterization),
    ("test_subprocess_emit_prompt_skips_blocked_gated_head_no_withhold", test_subprocess_emit_prompt_skips_blocked_gated_head_no_withhold),
    ("test_subprocess_emit_prompt_fully_gated_surfaces_blocked_terminal", test_subprocess_emit_prompt_fully_gated_surfaces_blocked_terminal),
    ("test_subprocess_emit_prompt_single_type_workable_head_unchanged", test_subprocess_emit_prompt_single_type_workable_head_unchanged),
    ("test_research_halt_head_surfaces_when_research_head_outranks_bug", test_research_halt_head_surfaces_when_research_head_outranks_bug),
    ("test_research_halt_head_none_when_ready_work_outranks_research_head", test_research_halt_head_none_when_ready_work_outranks_research_head),
    ("test_subprocess_emit_prompt_surfaces_needs_research_over_lower_bug", test_subprocess_emit_prompt_surfaces_needs_research_over_lower_bug),
    ("test_merged_worklist_only_features_matches_listed_order", test_merged_worklist_only_features_matches_listed_order),
    ("test_merged_worklist_only_bugs_matches_listed_order", test_merged_worklist_only_bugs_matches_listed_order),
    ("test_merged_worklist_both_empty_returns_none", test_merged_worklist_both_empty_returns_none),
    ("test_merged_worklist_stable_within_queue_for_equal_keys", test_merged_worklist_stable_within_queue_for_equal_keys),
    ("test_merged_worklist_skips_idless_entries", test_merged_worklist_skips_idless_entries),
    ("test_age_escalated_rank_quantum_and_floor", test_age_escalated_rank_quantum_and_floor),
    ("test_age_escalated_rank_fail_open_cases", test_age_escalated_rank_fail_open_cases),
    ("test_pin_is_active_variants", test_pin_is_active_variants),
    ("test_merged_priority_bug_explicit_severity_ages", test_merged_priority_bug_explicit_severity_ages),
    ("test_merged_priority_bug_active_pin_suppressed", test_merged_priority_bug_active_pin_suppressed),
    ("test_merged_priority_bug_expired_pin_falls_back_to_spec_severity", test_merged_priority_bug_expired_pin_falls_back_to_spec_severity),
    ("test_merged_priority_bug_legacy_null_no_pin_unchanged", test_merged_priority_bug_legacy_null_no_pin_unchanged),
    ("test_merged_priority_aged_bug_outranks_tier2_feature_not_p0", test_merged_priority_aged_bug_outranks_tier2_feature_not_p0),
    ("test_bug_priority_marker_pinned", test_bug_priority_marker_pinned),
    ("test_bug_priority_marker_escalated", test_bug_priority_marker_escalated),
    ("test_bug_priority_marker_none_when_no_pin_no_escalation", test_bug_priority_marker_none_when_no_pin_no_escalation),
    ("test_skill_declares_multi_commit_user_level_and_pseudo", test_skill_declares_multi_commit_user_level_and_pseudo),
    ("test_skill_declares_multi_commit_repo_scoped", test_skill_declares_multi_commit_repo_scoped),
    ("test_build_hardening_emit_command_process_friction_binding", test_build_hardening_emit_command_process_friction_binding),
    ("test_process_friction_context_resolves_hardening_template", test_process_friction_context_resolves_hardening_template),
    ("test_build_hardening_emit_command_validate_deny_unchanged", test_build_hardening_emit_command_validate_deny_unchanged),
    ("test_build_hardening_emit_command_observed_friction", test_build_hardening_emit_command_observed_friction),
    ("test_build_hardening_emit_command_observed_friction_blocking_true", test_build_hardening_emit_command_observed_friction_blocking_true),
    ("test_normalize_hardening_context_observed_friction_rebinds", test_normalize_hardening_context_observed_friction_rebinds),
    ("test_normalize_hardening_context_auto_trigger_passthrough", test_normalize_hardening_context_auto_trigger_passthrough),
    ("test_observed_friction_context_resolves_hardening_template", test_observed_friction_context_resolves_hardening_template),
    ("test_read_mcp_runtime_decision_required_reason_mentions_not_required", test_read_mcp_runtime_decision_required_reason_mentions_not_required),
    ("test_read_mcp_runtime_decision_not_required_value_token", test_read_mcp_runtime_decision_not_required_value_token),
    ("test_harden_harness_overfit_prose_present", test_harden_harness_overfit_prose_present),
    ("test_skill_declares_subagent_model_user_level", test_skill_declares_subagent_model_user_level),
    ("test_skill_declares_subagent_model_repo_scoped", test_skill_declares_subagent_model_repo_scoped),
    ("test_emission_consumed_by_nonce_fence", test_emission_consumed_by_nonce_fence),
    ("test_resolve_cycle_worker_nonce_rebinds_fresh_hex", test_resolve_cycle_worker_nonce_rebinds_fresh_hex),
    ("test_run_end_unacked_hardening_refusal_emits_gate_refusal_bug", test_run_end_unacked_hardening_refusal_emits_gate_refusal_bug),
    ("test_run_end_efficacy_flush_refusal_emits_gate_refusal_bug", test_run_end_efficacy_flush_refusal_emits_gate_refusal_bug),
    ("test_run_end_success_emits_run_end_not_gate_refusal_lazy", test_run_end_success_emits_run_end_not_gate_refusal_lazy),
    ("test_run_end_success_emits_run_end_not_gate_refusal_bug", test_run_end_success_emits_run_end_not_gate_refusal_bug),
    ("test_standard_bindings_split_terminal_statuses", test_standard_bindings_split_terminal_statuses),
    ("test_apply_resolution_emits_terminal_disposition_close", test_apply_resolution_emits_terminal_disposition_close),
    ("test_spike_dispatch_class_registered", test_spike_dispatch_class_registered),
    ("test_spike_template_binding", test_spike_template_binding),
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
