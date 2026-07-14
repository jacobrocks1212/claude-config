#!/usr/bin/env python3
"""
test_markers.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_markers.py
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



from _util import _ModuleMissing, _GUARDED_OPS, _M4_CONFIG, _M4_CONFIG_BOOT, _M4_KEYS, _REAL_TEMPLATE_DIR, _STATE_A, _assert_run_end_refusal_emits, _build_phase8_fixture_repo, _clear_cycle_env, _clear_state_dir, _collect_bare_production_writes, _commit_dummy, _dispatch_requires, _make_git_repo_with_origin, _mrcr_restore_env, _mrcr_with_temp_home, _normalize_smoke_output, _os_env, _owned_lock, _phase9_guard_module, _prov_git_commit_file, _prov_git_fixture_repo, _record_consume, _seed_efficacy_breadcrumb, _set_state_dir, _t, _write_marker_in  # noqa: E402




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
# Tests: --test baseline (zero-behavior-change contract)
# ---------------------------------------------------------------------------

def test_lazy_state_test_output_matches_baseline():
    """lazy-state.py --test output matches the checked-in baseline (byte-for-byte
    after cross-platform normalization via _normalize_smoke_output).

    The baseline file stores paths in canonical form (<TMP>/lazy-state-fixtures-XXXXXXXX/…
    with forward slashes).  Both the live output and the stored baseline are run
    through _normalize_smoke_output before comparison, so the diff is stable
    across platforms (Windows vs POSIX) and across runs (volatile tempdir suffix).

    This is the durable form of the zero-behavior-change contract: any refactor
    that alters observable --test output will cause this test to fail with a
    unified diff.

    NOTE: The baseline has been regenerated in canonical (cross-platform) form
    and this test is the GREEN steady-state zero-behavior-change contract.  Any
    refactor that alters observable --test output will cause this test to fail
    with a unified diff.
    """
    # No _guard() — this test does not require lazy_core to be importable;
    # it tests lazy-state.py's --test harness in isolation.

    # Run lazy-state.py --test, merging stdout+stderr.
    # Pin LAZY_STATE_DIR to an isolated empty temp dir so a live cycle marker /
    # run marker in the real ~/.claude/state/ cannot leak into the harness (its
    # internal `bug-state.py --enqueue-adhoc` subprocess inherits this env, and a
    # leaked cycle marker would trip the C3 refusal and perturb the baseline).
    with tempfile.TemporaryDirectory(prefix="lazy-state-hermetic-") as _isolated_state:
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"), "--test"],
            capture_output=True,
            text=True,
            env={**os.environ, "LAZY_STATE_DIR": _isolated_state},
        )
    live_output = result.stdout + result.stderr

    # Normalize with the shared cross-platform helper.
    normalized_live = _normalize_smoke_output(live_output)

    # Read the (already-normalized or stale) baseline.
    baseline_path = (
        _SCRIPTS_DIR / "tests" / "baselines" / "lazy-state-test-baseline.txt"
    )
    baseline_content = _normalize_smoke_output(
        baseline_path.read_text(encoding="utf-8")
    )

    if normalized_live != baseline_content:
        # Produce a unified diff to make regressions debuggable.
        diff_lines = list(
            difflib.unified_diff(
                baseline_content.splitlines(keepends=True),
                normalized_live.splitlines(keepends=True),
                fromfile="baseline (normalized)",
                tofile="live (normalized)",
            )
        )
        diff_str = "".join(diff_lines)
        raise AssertionError(
            f"lazy-state.py --test output differs from baseline:\n{diff_str}"
        )




def test_bug_state_test_output_matches_baseline():
    """bug-state.py --test output matches the checked-in baseline (byte-for-byte
    after cross-platform normalization via _normalize_smoke_output).

    Mirrors test_lazy_state_test_output_matches_baseline for bug-state.py.

    NOTE: The baseline file user/scripts/tests/baselines/bug-state-test-baseline.txt
    now exists and this is the steady-state GREEN contract.  Any refactor that alters
    observable --test output will cause this test to fail with a unified diff.
    """
    # No _guard() — does not require lazy_core to be importable.

    # Run bug-state.py --test, merging stdout+stderr.
    # Pin LAZY_STATE_DIR to an isolated empty temp dir (see the lazy-state
    # baseline test above) so a live cycle/run marker cannot perturb the harness.
    with tempfile.TemporaryDirectory(prefix="bug-state-hermetic-") as _isolated_state:
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "bug-state.py"), "--test"],
            capture_output=True,
            text=True,
            env={**os.environ, "LAZY_STATE_DIR": _isolated_state},
        )
    live_output = result.stdout + result.stderr

    # Normalize with the shared cross-platform helper.
    normalized_live = _normalize_smoke_output(live_output)

    # Read the (already-normalized) baseline — the file exists; FileNotFoundError
    # here would indicate the baseline was accidentally deleted.
    baseline_path = (
        _SCRIPTS_DIR / "tests" / "baselines" / "bug-state-test-baseline.txt"
    )
    baseline_content = _normalize_smoke_output(
        baseline_path.read_text(encoding="utf-8")
    )

    if normalized_live != baseline_content:
        diff_lines = list(
            difflib.unified_diff(
                baseline_content.splitlines(keepends=True),
                normalized_live.splitlines(keepends=True),
                fromfile="baseline (normalized)",
                tofile="live (normalized)",
            )
        )
        diff_str = "".join(diff_lines)
        raise AssertionError(
            f"bug-state.py --test output differs from baseline:\n{diff_str}"
        )




def test_update_repeat_counts_debounce_holds_step_count_no_consume_between():
    """THE Phase-2 deliverable: with a run marker present, two identical
    ADVANCING probes for the same (feature_id, current_step) and NO registry
    consume between them → step_repeat_count is HELD at 1 (a re-read, not a
    re-attempt). repeat_count is unaffected by the debounce.

    RED: pre-debounce update_repeat_counts increments unconditionally → 1 then 2.
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
        # Two identical advancing probes, NO consume between them.
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 1, (
        f"second identical probe with NO consume (no dispatch) between → HELD at 1 "
        f"(re-read debounce), got {r2!r}"
    )




def test_update_repeat_counts_debounce_increments_with_consume_between():
    """Real oscillation still trips: with a run marker present, two identical
    probes WITH a registry consume recorded between them → step_repeat_count
    INCREMENTS 1 → 2 (a dispatch landed, so this is a genuine re-attempt).

    RED: a debounce that ignores the consume-delta would HOLD at 1 here.
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
        # A real dispatch lands between the two identical probes (consume delta +1).
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"a consume between the two identical probes is a real dispatch → genuine "
        f"oscillation must still trip (1 → 2), got {r2!r}"
    )




def test_update_repeat_counts_debounce_inert_for_foreign_repo_marker():
    """Hardening-log Round 8 (2026-06-13) regression guard: the F2 debounce is a
    GLOBAL marker gating a GLOBAL consume-count, but it must be hermetic to the
    PROBE's repo_root. A run marker bound to a DIFFERENT repo must NOT engage the
    debounce for a probe against THIS repo — otherwise (a) these very step-counter
    unit tests go RED whenever any marked run is live on the machine, and (b) a
    concurrent run in another repo spuriously holds this repo's step counter.

    With a foreign-repo marker present, two identical advancing probes for THIS
    repo must INCREMENT 1 → 2 exactly as the no-marker path does.

    RED: the pre-fix impl read the unscoped global marker, engaged the debounce
    off the foreign run's consume-count, and HELD step_repeat_count at 1.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        this_repo = td_path / "this-repo"
        this_repo.mkdir()
        foreign_repo = td_path / "foreign-repo"
        foreign_repo.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Marker belongs to a DIFFERENT repo than the one being probed.
        _write_marker_in(state_dir, foreign_repo)
        # Make the foreign run's global consume-count non-zero so the only thing
        # keeping the debounce inert is the repo_root mismatch (not an absent
        # consume oracle).
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(this_repo, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(this_repo, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"a marker for a FOREIGN repo must not engage this repo's debounce — the "
        f"step counter must increment 1 → 2 just like the no-marker path, got {r2!r}"
    )




def test_update_repeat_counts_debounce_inert_without_marker():
    """MARKER-GATED: with NO run marker present, the debounce is inert — two
    identical probes with no consume between them still increment (1 → 2), and
    the consume-count key is NOT written, so the no-marker path is byte-identical
    to the pre-Phase-2 behavior that the `--test` baselines pin.

    RED: an impl that debounced or wrote the consume key without a marker would
    leak into the default path and diff the smoke baselines.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"  # empty — no marker written
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"no marker → debounce inert → identical probe increments (1 → 2), got {r2!r}"
    )
    assert "consume_count" not in persisted, (
        f"no marker → the consume-count key must NOT be written (byte-identical "
        f"default path), got {persisted!r}"
    )




def _write_marker_in_at(state_dir: "Path", repo_root: "Path", now: float) -> dict:
    """Write a fresh, bind-pending run marker at a specific epoch `now` (so two
    calls with different `now` values produce markers with distinct
    `started_at` identities — simulating two DIFFERENT runs for the SAME repo).
    Returns the written marker dict."""
    _set_state_dir(state_dir)
    try:
        return lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root=str(repo_root), now=now,
        )
    finally:
        _clear_state_dir()




def test_gap_b_cross_run_streak_resets_on_different_run_identity():
    """Residual gap B: a streak stamped under run A (started_at=T1) must NOT be
    inherited by run B (started_at=T2, a DIFFERENT run for the SAME repo) — the
    classic crashed-run-leaks-into-next-run symptom (symptom 4). The next run's
    first probe on the SAME (feature_id, current_step) tuple must see NO PRIOR
    (fresh streak), not an inherited count.

    RED (pre-fix): the signature file is keyed only on repo_root, so run B's
    probe reads run A's persisted count/step_count unconditionally and
    increments them — a false LOOP-DETECTED at the NEW run's first probe.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Run A: marker started_at=T1, one probe stamps the streak file. Use
        # REAL near-current epochs (not an arbitrary fixed constant) — a marker
        # older than _MARKER_STALE_SECONDS (24h) is treated as stale/absent by
        # read_run_marker(), which would defeat this fixture.
        t0 = _time.time()
        _write_marker_in_at(state_dir, repo_root, now=t0)
        _set_state_dir(state_dir)
        try:
            r_a = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted_a = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
        # Run A crashes — no --run-end, streak file survives untouched.
        # Run B starts fresh: write_run_marker OVERWRITES the marker with a NEW
        # started_at (T2 != T1, a few seconds later — still second-granularity
        # distinct), simulating a genuinely different run.
        _write_marker_in_at(state_dir, repo_root, now=t0 + 5)
        _set_state_dir(state_dir)
        try:
            r_b = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r_a["step_repeat_count"] == 1 and r_a["repeat_count"] == 1, (
        f"run A's first probe → 1/1, got {r_a!r}"
    )
    assert "run_started_at" in persisted_a, (
        f"a marked probe must stamp the record's run identity, got {persisted_a!r}"
    )
    assert r_b["step_repeat_count"] == 1 and r_b["repeat_count"] == 1, (
        f"run B (a DIFFERENT run identity) must see NO PRIOR — fresh streak "
        f"(1/1), NOT an inherited count from run A's dead streak, got {r_b!r}"
    )




def test_gap_b_same_run_streak_still_accumulates():
    """Regression: within the SAME run (unchanged marker started_at), a genuine
    same-step oscillation with an intervening cycle-class dispatch still
    accumulates normally — Residual gap B's cross-run reset must never fire
    for two probes under the SAME live marker."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)  # ONE marker for both probes.
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        _record_consume(state_dir)  # genuine cycle dispatch between probes.
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"same run + genuine intervening dispatch must still accumulate "
        f"(1 → 2) — the cross-run reset must not fire within one run, "
        f"got {r2!r}"
    )




def test_gap_b_legacy_record_without_run_identity_is_not_treated_as_foreign():
    """Legacy tolerance (mirrors the consume_count/head migration precedent): a
    persisted record written with NO run_started_at key at all (predates this
    fix, or a write taken with no live marker) is NOT proof of belonging to a
    different run — absence is never proof. When a marker is now live, the
    record falls through to the pre-existing same-repo streak semantics
    (increments), it is not reset to a fresh streak."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        legacy_sig = [
            _STATE_A["feature_id"], _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"], _STATE_A["current_step"],
        ]
        legacy_step_sig = [_STATE_A["feature_id"], _STATE_A["current_step"]]
        sig_path.write_text(json.dumps({
            "signature": legacy_sig, "count": 1, "head": None,
            "step_signature": legacy_step_sig, "step_count": 1,
        }), encoding="utf-8")
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 2 and r1["repeat_count"] == 2, (
        f"a legacy record with no run_started_at key must NOT be treated as "
        f"foreign — it increments as before (1 → 2), got {r1!r}"
    )




def test_rebaseline_loop_signature_noop_when_absent_or_no_marker():
    """rebaseline_loop_signature_after_registry_reset is a fail-open no-op when no
    signature file exists OR no run marker is present (the debounce it feeds is
    marker-gated). Returns False, creates nothing, never raises."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _set_state_dir(state_dir)
        try:
            # (a) No signature file yet, no marker → no-op, no file created.
            no_file = lazy_core.rebaseline_loop_signature_after_registry_reset(
                repo_root, signature_path=sig_path,
            )
            created = sig_path.exists()
            # (b) Signature file present but NO marker → still a no-op (marker-gated).
            sig_path.write_text(json.dumps({"signature": [None, None, None, None],
                                            "count": 2, "consume_count": 9}), encoding="utf-8")
            no_marker = lazy_core.rebaseline_loop_signature_after_registry_reset(
                repo_root, signature_path=sig_path,
            )
            unchanged = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert no_file is False, "no signature file → no-op returns False"
    assert not created, "no-op must NOT create the signature file"
    assert no_marker is False, "no marker → marker-gated no-op returns False"
    assert unchanged.get("consume_count") == 9, (
        f"no-marker no-op must leave the file untouched, got {unchanged!r}"
    )




# ---------------------------------------------------------------------------
# Tests: update_repeat_counts — F1 (lazy-validation-readiness) double-probe
# debounce for repeat_count (dispatch-tuple streak).
#
# The SAME consume-count re-read oracle that guards step_count (F2) must also
# guard the dispatch-tuple ``count``.  A second advancing probe for the SAME
# dispatch tuple with the SAME HEAD and NO dispatch between the two probes
# must NOT increment repeat_count — without this fix the orchestrator reads
# count=2 and fires a false LOOP DETECTED.
#
# Five invariants (mirrors the F2/step_count battery above):
#   1. Re-read holds: marker present, same tuple, same head, equal
#      consume_counts → repeat_count HELD.
#   2. Real dispatch increments: marker present, same tuple, but consume
#      increased → repeat_count increments.
#   3. HEAD reset wins: new HEAD resets to 1 (forward progress; never
#      suppressed by debounce).
#   4. No-marker path unchanged: identical probe without marker still
#      increments 1 → 2 (debounce inert).
#   5. Legacy-tolerant: prior file with no consume_count key cannot prove a
#      re-read → increments as before.
# ---------------------------------------------------------------------------


def test_f1_repeat_count_debounce_holds_no_consume_between():
    """F1 invariant 1 — Re-read holds repeat_count.

    With a run marker present for this repo, two identical advancing probes
    for the same dispatch tuple + same HEAD and NO registry consume between
    them → repeat_count is HELD at 1 (a re-read, not a genuine re-attempt).

    RED: pre-F1 update_repeat_counts increments unconditionally → 1 then 2,
    which the orchestrator reads as LOOP DETECTED.
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
        # Two identical advancing probes, NO consume between them.
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["repeat_count"] == 1, (
        f"second identical probe with NO consume (no dispatch) between → HELD at 1 "
        f"(F1 re-read debounce), got {r2!r}"
    )




def test_f1_repeat_count_debounce_increments_with_consume_between():
    """F1 invariant 2 — Real dispatch still increments repeat_count.

    With a run marker present, two identical dispatch-tuple probes WITH a
    registry consume between them → repeat_count INCREMENTS 1 → 2 (a dispatch
    landed, so this is a genuine re-attempt and must be counted).

    RED: a debounce that ignores the consume-delta would HOLD at 1 here.
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
        # A real dispatch lands between the two identical probes (consume delta +1).
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["repeat_count"] == 2, (
        f"a consume between the two identical probes is a real dispatch → genuine "
        f"repeat must still increment (1 → 2), got {r2!r}"
    )




def test_f1_repeat_count_debounce_inert_without_marker():
    """F1 invariant 4 — No-marker path is unchanged (debounce inert).

    With NO run marker present, two identical dispatch-tuple probes still
    increment repeat_count 1 → 2 — the consume-count key is never written and
    the debounce is completely inert (byte-identical to the pre-F1 behavior).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"  # no marker
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["repeat_count"] == 2, (
        f"no marker → debounce inert → identical probe increments repeat_count "
        f"(1 → 2), got {r2!r}"
    )
    assert "consume_count" not in persisted, (
        f"no marker → consume-count key must NOT be written, got {persisted!r}"
    )




# ---------------------------------------------------------------------------
# Tests: loop-detected-false-positives-from-probe-and-reboot-churn
#   Phase 1 — regression-pin that symptoms 2 & 4 are ALREADY closed by the
#   landed F1/F2 consume-debounce. These characterize existing CORRECT behavior
#   (green on first run, NO production code) so Phase 2's resolution-reset can be
#   proven NOT to regress the no-dispatch-between-probes HOLD.
# ---------------------------------------------------------------------------


def test_symptom2_reboot_reprobe_no_inflation():
    """SYMPTOM 2 (reboot re-probe, no dispatch) — the F2 debounce HOLDS step_count.

    Models the reboot/restart class: the orchestrator probes the SAME
    (feature_id, current_step) twice with a run marker present and NO registry
    consume (no dispatch / no guard ALLOW) between the two probes — the second
    probe is a pure RE-READ after a reboot, not a re-attempt. step_repeat_count
    must be HELD at 1, never inflated toward the LOOP-DETECTED tripwire.

    This is a CHARACTERIZATION fixture (Proven Finding 1 — symptom 2 already
    closed): it is GREEN against HEAD as-is. It pins the HOLD so the Phase-2
    resolution-reset branch cannot silently re-open the false positive.
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
        # Two identical advancing probes for the SAME step signature, NO consume
        # (no dispatch) between them — the reboot re-probe.
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 1, (
        f"reboot re-probe with the SAME step signature and NO dispatch between "
        f"the probes → step_repeat_count HELD at 1 (F2 re-read debounce), not "
        f"inflated, got {r2!r}"
    )




def test_symptom4_double_probe_hygiene_no_inflation():
    """SYMPTOM 4 (double-probe hygiene) — neither counter inflates on a re-read.

    Models the probe-hygiene double-read class: one cycle reads the state twice
    (e.g. an inspection probe then a dispatch probe for the SAME cycle) with a
    run marker present and NO registry consume between the two reads. BOTH the
    dispatch-tuple repeat_count (F1) and the step-level step_repeat_count (F2)
    must be HELD — a single cycle's hygiene double-read must never read as two
    repeats and trip a false LOOP DETECTED.

    CHARACTERIZATION fixture (Proven Finding 1 — symptom 4 already closed):
    GREEN against HEAD. Pins that the Phase-2 reset preserves the F1+F2 HOLD.
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
        # Two identical probes for ONE cycle (same dispatch tuple AND same step
        # signature), NO consume between them — the hygiene double-read.
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1 and r1["step_repeat_count"] == 1, (
        f"first probe → both counts 1, got {r1!r}"
    )
    assert r2["repeat_count"] == 1, (
        f"double-probe hygiene re-read → repeat_count HELD at 1 (F1 debounce), "
        f"got {r2!r}"
    )
    assert r2["step_repeat_count"] == 1, (
        f"double-probe hygiene re-read → step_repeat_count HELD at 1 (F2 "
        f"debounce), got {r2!r}"
    )




# ---------------------------------------------------------------------------
# Tests: Phase 7 — deny ledger, run-end refusal/override, checkpoint round-trip,
#                  widened normalization, single-slot templates, meta cycle_header
# ---------------------------------------------------------------------------
#
# Hermetic via LAZY_STATE_DIR temp dirs (same discipline as Phase 1).  The
# helpers _set_state_dir / _clear_state_dir are defined below in the Phase 1
# section but resolve at call time (these functions only run from main()).


def test_phase7_symbols_present():
    """All Phase 7 public symbols exist on lazy_core."""
    _guard()
    expected = [
        "append_deny_ledger_entry",
        "read_deny_ledger",
        "pending_hardening",
        "pending_denial_reasons",
        "ack_oldest_deny",
        "write_run_checkpoint",
        "consume_run_checkpoint",
        "DISPATCH_STEP_NAMES",
    ]
    missing = [s for s in expected if not hasattr(lazy_core, s)]
    assert not missing, f"missing Phase 7 symbols: {missing}"




def test_guard_deny_writes_ledger_entry():
    """The guard's deny path (marked run + unregistered prompt) leaves the deny
    output unchanged AND writes a deny-ledger entry in the scoped state dir."""
    _guard()
    assert hasattr(lazy_core, "write_run_marker"), "Phase 1 missing"
    guard_script = _SCRIPTS_DIR / "lazy_guard.py"
    assert guard_script.exists(), "lazy_guard.py missing (Phase 2)"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "guard-state"
        state_dir.mkdir()
        # stale-marker-arms-validate-deny-on-unrelated-dispatches D2 (2026-06-19):
        # the GENERIC default-deny ledger append now requires a BOUND marker (a
        # pre-bind/unbound deny is no-debt by design — WU-3). Bind the marker to
        # an owner session and dispatch AS the owner so this stays a genuine
        # validate-deny that DOES accrue debt (the test's original intent).
        owner_session = "11111111-2222-3333-4444-555555555555"
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=__import__("time").time(),
                session_id=owner_session,
            )
        finally:
            _clear_state_dir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        hook_input = json.dumps({
            "tool_use_id": "tu-deny",
            "session_id": owner_session,
            "tool_input": {"prompt": "HAND-COMPOSED unregistered dispatch"},
        })
        result = subprocess.run(
            [sys.executable, str(guard_script)],
            input=hook_input, capture_output=True, text=True, env=env,
        )
        assert result.returncode == 0, f"guard must exit 0; stderr={result.stderr[:300]!r}"
        out = json.loads(result.stdout)
        decision = out["hookSpecificOutput"]["permissionDecision"]
        assert decision == "deny", f"expected deny, got {decision}"
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason, "deny reason must be non-empty (unchanged corrective recipe)"
        # The ledger entry must now exist.
        ledger_path = state_dir / "lazy-deny-ledger.jsonl"
        assert ledger_path.exists(), "deny must append a ledger entry"
        lines = [ln for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1, f"exactly one ledger line expected, got {len(lines)}"
        entry = json.loads(lines[0])
        assert entry["tool_use_id"] == "tu-deny", entry
        assert entry["acked"] is False, entry
        assert len(entry["denied_sha12"]) == 12, entry




def test_execute_plan_commit_budget_scales_with_phase_count():
    """hardening Round 20 (DEFECT-2): _execute_plan_commit_budget reads the plan
    part's phase count and scales the budget so a normal one-commit-per-phase
    /execute-plan cycle does NOT false-positive; the detector honors the override
    and a true runaway still trips. Non-execute-plan / unreadable / no-phases
    inputs degrade to None (fall back to the fixed table)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan = root / "plan-part-1.md"
        # a 6-phase single-part plan.
        plan.write_text(
            "---\nkind: implementation-plan\nstatus: ready\n"
            "phases: [1, 2, 3, 4, 5, 6]\n---\n\nbody\n",
            encoding="utf-8",
        )
        # scaled budget = 6 phases + slack + bookend (Round 46: the two
        # deterministic In-progress/Complete status-flip commits every cycle makes).
        budget = lazy_core._execute_plan_commit_budget("execute-plan", str(plan))
        assert budget == (
            6
            + lazy_core._EXECUTE_PLAN_PHASE_BUDGET_SLACK
            + lazy_core._EXECUTE_PLAN_BOOKEND_COMMITS
        ), budget

        # trailing flags on the args are tolerated (only the leading token is path).
        assert lazy_core._execute_plan_commit_budget(
            "execute-plan", f"{plan} --batch"
        ) == budget

        # non-execute-plan / blank / unreadable / no-phases → None (table fallback).
        assert lazy_core._execute_plan_commit_budget("mcp-test", str(plan)) is None
        assert lazy_core._execute_plan_commit_budget("execute-plan", None) is None
        assert lazy_core._execute_plan_commit_budget(
            "execute-plan", str(root / "missing.md")
        ) is None
        nophases = root / "nophases.md"
        nophases.write_text("---\nkind: implementation-plan\n---\nbody\n", encoding="utf-8")
        assert lazy_core._execute_plan_commit_budget("execute-plan", str(nophases)) is None

        # detector honors the override: `budget` commits (6 phases + slack +
        # bookend) does NOT trip, but a runaway of budget+1 commits DOES.
        marker = {
            "run_started_at": "2026-06-16T13:31:00Z",
            "begin_head_sha": "d" * 40,
            "kind": "real",
        }
        assert lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="e" * 40, sub_skill="execute-plan",
            commits_since=budget, budget_override=budget,
        ) is None
        runaway = lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="e" * 40, sub_skill="execute-plan",
            commits_since=budget + 1, budget_override=budget,
        )
        assert runaway is not None and runaway["reason"] == "unexpected-commits"

        # WITHOUT the override, the same 6-commit cycle false-positives against the
        # fixed table budget of 3 — proving the override is what fixes the defect.
        false_pos = lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="e" * 40, sub_skill="execute-plan",
            commits_since=6, budget_override=None,
        )
        assert false_pos is not None and false_pos["reason"] == "unexpected-commits"




def test_execute_plan_commit_budget_scales_with_wu_count():
    """WU-scaling follow-up (2026-06-16): /execute-plan commits once per WORK UNIT,
    so a WU-dense plan part (more WUs than phases) must budget by the WU count, not
    the phase count. The live recurrence: cycle-subagent-runs part-1 had 5 WUs
    across 2 phases → 5 commits, but the phase-only budget (2 + slack = 4) tripped
    unexpected-commits. The fix scales by max(phase_count, wu_count) + slack."""
    _guard()
    slack = lazy_core._EXECUTE_PLAN_PHASE_BUDGET_SLACK
    bookend = lazy_core._EXECUTE_PLAN_BOOKEND_COMMITS
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # The recurrence: 2 phases, 5 per-WU checkboxes (1 already checked).
        wu_dense = root / "wu-dense-part-1.md"
        wu_dense.write_text(
            "---\nkind: implementation-plan\nstatus: in-progress\n"
            "phases: [1, 2]\n---\n\n"
            "- [x] WU-1 — first\n"
            "- [ ] WU-2 — second\n"
            "- [ ] WU-3 — third\n"
            "- [ ] WU-4 — fourth\n"
            "- [ ] WU-5 — fifth\n",
            encoding="utf-8",
        )
        # budget scales by WU count (5), NOT phase count (2): 5 + slack + bookend.
        budget = lazy_core._execute_plan_commit_budget("execute-plan", str(wu_dense))
        assert budget == 5 + slack + bookend, budget
        # 5 commits (one per WU) now sits WITHIN budget — no false positive.
        marker = {
            "run_started_at": "2026-06-16T13:31:00Z",
            "begin_head_sha": "a" * 40,
            "kind": "real",
        }
        assert lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="b" * 40, sub_skill="execute-plan",
            commits_since=5, budget_override=budget,
        ) is None
        # a genuine runaway (beyond the declared work + slack + bookend) still trips.
        runaway = lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="b" * 40, sub_skill="execute-plan",
            commits_since=5 + slack + bookend + 1, budget_override=budget,
        )
        assert runaway is not None and runaway["reason"] == "unexpected-commits"

        # phase count still wins when it is the greater signal (phases > WUs).
        phase_heavy = root / "phase-heavy.md"
        phase_heavy.write_text(
            "---\nkind: implementation-plan\nstatus: ready\n"
            "phases: [1, 2, 3, 4]\n---\n\n- [ ] WU-1 — only one\n",
            encoding="utf-8",
        )
        assert lazy_core._execute_plan_commit_budget(
            "execute-plan", str(phase_heavy)
        ) == 4 + slack + bookend

        # a legacy plan with WU checkboxes but NO phases: field now budgets by WUs
        # (previously returned None → fell back to the fixed table of 3).
        no_phases_wus = root / "no-phases-wus.md"
        no_phases_wus.write_text(
            "---\nkind: implementation-plan\nstatus: ready\n---\n\n"
            "- [ ] WU-1 — a\n- [ ] WU-2 — b\n- [ ] WU-3 — c\n",
            encoding="utf-8",
        )
        assert lazy_core._execute_plan_commit_budget(
            "execute-plan", str(no_phases_wus)
        ) == 3 + slack + bookend

        # neither phases: nor WU checkboxes → None (fixed-table fallback preserved).
        empty = root / "empty.md"
        empty.write_text("---\nkind: implementation-plan\n---\nprose only\n", encoding="utf-8")
        assert lazy_core._execute_plan_commit_budget("execute-plan", str(empty)) is None




def test_execute_plan_commit_budget_absorbs_bookend_status_flips():
    """Hardening Round 46 (2026-06-30 recurrence, AlgoBooth bug
    audio-engine-clippy-warnings-fail-rust-gate, Step 7a execute-plan): the budget
    must absorb the TWO deterministic bookend status-flip commits every /execute-plan
    cycle makes (`chore(<id>): mark plan In-progress` at the start + `docs/chore(<id>):
    reconcile — mark plan Complete` at the end), which the per-WU / phase scale_count
    structurally omits.

    Live recurrence (git-confirmed): the plan declared `phases: [1]` + 4 per-WU
    checkboxes → scale_count = max(1, 4) = 4. The cycle authored 7 NON-MERGE commits
    (begin-chore In-progress flip, WU-1/2/3+4, an extra feature-gating lint fix, an
    in-cycle `revert(...)` self-correction, and the end Complete-reconcile). NONE were
    merges (so Round 42's --no-merges exclusion does not help). With the pre-Round-46
    budget of scale_count(4) + slack(2) = 6, the AUTHORED count of 7 tripped
    unexpected-commits (7 > 6, `budget=6` verbatim in the deny detail). The two
    bookend commits are the load-bearing overflow. Round 46 budgets them explicitly:
    scale_count + slack + bookend = 4 + 2 + 2 = 8, so the clean 7-commit cycle no
    longer false-positives, while a genuine runaway (>8) STILL trips."""
    _guard()
    slack = lazy_core._EXECUTE_PLAN_PHASE_BUDGET_SLACK
    bookend = lazy_core._EXECUTE_PLAN_BOOKEND_COMMITS
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Exact live fixture: phases: [1] + 4 WU checkboxes (all checked, as at
        # --cycle-end) → scale_count = max(1, 4) = 4.
        plan = root / "all-phases-audio-engine-clippy-sweep.md"
        plan.write_text(
            "---\nkind: implementation-plan\nstatus: in-progress\n"
            "phases: [1]\n---\n\n"
            "- [x] WU-1 — auto-fixable + single-finding lints\n"
            "- [x] WU-2 — needless_range_loop sweep\n"
            "- [x] WU-3 — manual_clamp + golden-sensitive float lints\n"
            "- [x] WU-4 — wildcard_enum_match_arm + error-size, final gate sweep\n",
            encoding="utf-8",
        )
        budget = lazy_core._execute_plan_commit_budget("execute-plan", str(plan))
        # scale_count(4) + slack + bookend == 4 + 2 + 2 == 8 (was 6 pre-Round-46).
        assert budget == 4 + slack + bookend, budget
        assert budget == 8, budget

        marker = {
            "run_started_at": "2026-06-30T18:00:00Z",
            "begin_head_sha": "e01a97dd6685" + "0" * 28,
            "kind": "real",
        }
        # The live 7-authored-commit cadence (begin-chore + WUs + extra fix + revert
        # + end reconcile) now sits WITHIN budget — no false positive.
        assert lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-30T18:00:00Z",
            current_head_sha="f" * 40, sub_skill="execute-plan",
            commits_since=7, budget_override=budget,
        ) is None
        # Control: with the PRE-Round-46 budget (scale_count + slack = 6), the same
        # 7-commit cycle false-positived — proving the bookend term is load-bearing.
        pre_r46 = 4 + slack
        false_pos = lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-30T18:00:00Z",
            current_head_sha="f" * 40, sub_skill="execute-plan",
            commits_since=7, budget_override=pre_r46,
        )
        assert false_pos is not None and false_pos["reason"] == "unexpected-commits"
        # A genuine runaway (beyond WUs + slack + the 2 bookends) STILL trips — the
        # runaway ceiling is unchanged in KIND (no gate weakened).
        runaway = lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-30T18:00:00Z",
            current_head_sha="f" * 40, sub_skill="execute-plan",
            commits_since=budget + 1, budget_override=budget,
        )
        assert runaway is not None and runaway["reason"] == "unexpected-commits"




def test_checkpoint_round_trip():
    """Subprocess: --run-end --reason checkpoint --next-route X writes the
    checkpoint file (folding the marker counters); the next --run-start echoes
    and consumes it; a plain terminal --run-end writes no checkpoint file.

    Phase 7 note: uses --unattended at --run-start so the checkpoint gate
    (attended=True → must have --operator-authorized) does not block this
    test which is exercising the checkpoint file mechanism, not the auth gate.
    The auth gate is separately covered by test_p7_run_end_checkpoint_*.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "ckpt-state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        # Phase 7: use --unattended so the checkpoint auth gate does not apply.
        assert run(["--run-start", "--max-cycles", "7", "--unattended"]).returncode == 0
        # checkpoint requires --next-route — missing → non-zero exit.
        r_missing = run(["--run-end", "--reason", "checkpoint"])
        assert r_missing.returncode != 0, "checkpoint without --next-route must fail"
        assert (state_dir / "lazy-run-marker.json").exists(), "marker still present after failed checkpoint"

        # Proper checkpoint run-end writes the file + retires the marker.
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "write-plan Phase 14"])
        assert r.returncode == 0, f"checkpoint run-end failed: {r.stdout}{r.stderr}"
        out = json.loads(r.stdout)
        assert out["reason"] == "checkpoint", out
        assert out["checkpoint"]["next_route"] == "write-plan Phase 14", out
        ckpt_path = state_dir / "lazy-run-checkpoint.json"
        assert ckpt_path.exists(), "checkpoint file must be written"
        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        assert ckpt["reason"] == "checkpoint", ckpt
        assert ckpt["next_route"] == "write-plan Phase 14", ckpt
        assert "counters" in ckpt and "max_cycles" in ckpt["counters"], ckpt
        assert not (state_dir / "lazy-run-marker.json").exists(), "marker retired"

        # Next run-start consumes + echoes it.
        r2 = run(["--run-start", "--max-cycles", "7"])
        assert r2.returncode == 0
        out2 = json.loads(r2.stdout)
        assert "resumed_from_checkpoint" in out2, out2
        assert out2["resumed_from_checkpoint"]["next_route"] == "write-plan Phase 14", out2
        assert not ckpt_path.exists(), "checkpoint must be consumed (deleted)"

        # A plain terminal run-end writes NO checkpoint file.
        _seed_efficacy_breadcrumb(state_dir)
        r3 = run(["--run-end"])
        assert r3.returncode == 0
        assert not ckpt_path.exists(), "terminal run-end must not write a checkpoint"




# ---------------------------------------------------------------------------
# operator-checkpoint-resume-counter-reset Phase 1: provenance persistence
#
# write_run_checkpoint records whether the checkpoint was operator-authorized so
# the resume path (Phase 2) can branch on it.  Default False — backward-compatible
# with pre-fix checkpoint files that lack the field.
# ---------------------------------------------------------------------------

def test_write_run_checkpoint_persists_operator_authorized():
    """write_run_checkpoint(..., operator_authorized=True) writes a top-level
    operator_authorized: True that round-trips through consume_run_checkpoint;
    the default (omitted-arg) write reads back operator_authorized: False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            counters = {"forward_cycles": 3, "meta_cycles": 1, "max_cycles": 9}

            # Explicit operator-authorized write → field True, round-trips.
            written = lazy_core.write_run_checkpoint(
                "execute-plan Phase 2", counters, operator_authorized=True,
            )
            assert written["operator_authorized"] is True, written
            consumed = lazy_core.consume_run_checkpoint()
            assert consumed is not None, "checkpoint must be readable"
            assert consumed["operator_authorized"] is True, consumed

            # Default (omitted arg) write → field present and False.
            written2 = lazy_core.write_run_checkpoint("write-plan Phase 5", counters)
            assert written2["operator_authorized"] is False, written2
            consumed2 = lazy_core.consume_run_checkpoint()
            assert consumed2 is not None
            assert consumed2["operator_authorized"] is False, consumed2
        finally:
            _clear_state_dir()




def test_run_end_checkpoint_threads_operator_authorized():
    """Subprocess: --run-end --reason checkpoint --operator-authorized writes a
    checkpoint whose operator_authorized field is True; omitting the flag writes
    False.  Threads args.operator_authorized through the write site."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "auth-ckpt-state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        ckpt_path = state_dir / "lazy-run-checkpoint.json"

        # Operator-authorized checkpoint → field True.
        assert run(["--run-start", "--max-cycles", "9", "--unattended"]).returncode == 0
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "execute-plan Phase 2", "--operator-authorized"])
        assert r.returncode == 0, f"{r.stdout}{r.stderr}"
        ckpt = json.loads(ckpt_path.read_text(encoding="utf-8"))
        assert ckpt["operator_authorized"] is True, ckpt
        # Consume it (run-start deletes the checkpoint).
        assert run(["--run-start", "--max-cycles", "9", "--unattended"]).returncode == 0

        # Non-authorized checkpoint (flag omitted) → field False.
        _seed_efficacy_breadcrumb(state_dir)
        r2 = run(["--run-end", "--reason", "checkpoint",
                  "--next-route", "execute-plan Phase 3"])
        assert r2.returncode == 0, f"{r2.stdout}{r2.stderr}"
        ckpt2 = json.loads(ckpt_path.read_text(encoding="utf-8"))
        assert ckpt2["operator_authorized"] is False, ckpt2




# ---------------------------------------------------------------------------
# Regression: ACCIDENTAL mid-run counter reset (2026-06-14)
#
# HARD CONSTRAINT 8: forward_cycles AND meta_cycles are monotonic for the LIFE
# of a run and must NEVER reset on a within-run transition (feature transition,
# recovery/meta cycle, marker rewrite, post-compaction re-entry, OR a sanctioned
# checkpoint pause/resume).  The live reset bug: a checkpoint resume re-ran
# write_run_marker (which zeros both counters) and echoed the checkpoint WITHOUT
# restoring the paused counts → the running total N reset to 0 mid-run.
# ---------------------------------------------------------------------------

def test_restore_checkpoint_counters_carries_forward():
    """restore_checkpoint_counters re-applies the checkpoint's forward/meta counts
    onto the freshly-written (zeroed) marker so a resume CONTINUES the count.

    Also resets last_advance_consume_count to 0 (the registry is freshly cleared
    on run-start, so the first post-resume dispatch must be able to advance)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Simulate the run-start sequence: write_run_marker zeros the counters.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            zeroed = lazy_core.read_run_marker()
            assert zeroed["forward_cycles"] == 0 and zeroed["meta_cycles"] == 0

            # A checkpoint left by a prior sanctioned pause carrying live counts.
            checkpoint = {
                "reason": "checkpoint",
                "next_route": "execute-plan Phase 3",
                "counters": {"forward_cycles": 7, "meta_cycles": 4, "max_cycles": 25},
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            assert restored is not None, "restore must return the updated marker"
            assert restored["forward_cycles"] == 7, restored
            assert restored["meta_cycles"] == 4, restored
            assert restored["last_advance_consume_count"] == 0, restored

            # The on-disk marker must reflect the restore (not just the return).
            on_disk = lazy_core.read_run_marker()
            assert on_disk["forward_cycles"] == 7, on_disk
            assert on_disk["meta_cycles"] == 4, on_disk
        finally:
            _clear_state_dir()




def test_restore_checkpoint_counters_carries_forward_run_identity():
    """cycle-bracket-break-on-checkpoint-resume (hardening Round 35): a
    non-operator-authorized resume must RESTORE the run identity (started_at) so a
    sanctioned same-run pause/resume does NOT change run identity mid-cycle and
    false-trip detect_cycle_bracket_friction signal (a).

    Covers: (1) carry-forward branch restores the original started_at;
    (2) detect_cycle_bracket_friction does NOT trip after the restore (the live
    identity matches a --cycle-begin run_started_at snapshot taken pre-pause);
    (3) operator-authorized resume does NOT restore identity (genuinely new run);
    (4) a >24h-stale checkpoint identity is NOT restored (age gate preserved);
    (5) a missing/unparseable checkpoint identity leaves the minted started_at."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # A within-24h identity so the age gate in restore_checkpoint_counters
            # accepts it as fresh. MUST be computed relative to the live clock —
            # a hardcoded date silently ages past the 24h gate once wall-clock
            # advances >24h beyond it, false-failing the positive carry-forward
            # assertion (observed 2026-06-24: a hardcoded 2026-06-23 fixture went
            # stale-by-age). Offset 1h into the past keeps it unambiguously inside
            # the window without being "now" (which the minted identity also is).
            import datetime as _ident_dt_mod
            original_identity = (
                (_ident_dt_mod.datetime.now(_ident_dt_mod.timezone.utc)
                 - _ident_dt_mod.timedelta(hours=1))
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            # --- (1) + (2): carry-forward branch restores identity --------------
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            minted = lazy_core.read_run_marker()["started_at"]
            assert minted != original_identity, "marker minted a fresh started_at"
            checkpoint = {
                "reason": "checkpoint",
                "next_route": "execute-plan Phase 3",
                "counters": {"forward_cycles": 7, "meta_cycles": 4, "max_cycles": 25},
                "run_started_at": original_identity,
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            assert restored is not None
            assert restored["started_at"] == original_identity, restored
            on_disk = lazy_core.read_run_marker()
            assert on_disk["started_at"] == original_identity, on_disk

            # (2) The pre-pause --cycle-begin snapshot now matches the live identity
            # → the friction detector does NOT false-trip cycle-bracket-break.
            cycle_marker = {
                "kind": "cycle",
                "run_started_at": original_identity,  # snapshotted pre-pause
                "begin_head_sha": "abc123",
            }
            friction = lazy_core.detect_cycle_bracket_friction(
                cycle_marker,
                current_run_started_at=on_disk["started_at"],
                current_head_sha="abc123",
                sub_skill="mcp-test",
                commits_since=0,
            )
            assert friction is None, ("identity restored → no bracket-break", friction)

            # Negative control: WITHOUT the restore (old behavior, minted identity)
            # the same pre-pause snapshot DOES trip — proving the fix is load-bearing.
            should_trip = lazy_core.detect_cycle_bracket_friction(
                cycle_marker,
                current_run_started_at=minted,
                current_head_sha="abc123",
                sub_skill="mcp-test",
                commits_since=0,
            )
            assert should_trip is not None, should_trip
            assert should_trip["reason"] == "cycle-bracket-break", should_trip
        finally:
            _clear_state_dir()

        # --- (3): operator-authorized resume does NOT restore identity ----------
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            minted = lazy_core.read_run_marker()["started_at"]
            op_ckpt = {
                "reason": "checkpoint",
                "next_route": "x",
                "counters": {"forward_cycles": 7, "meta_cycles": 4, "max_cycles": 25},
                "run_started_at": "2026-06-23T03:15:38Z",
                "operator_authorized": True,
                "ts": 0,
            }
            assert lazy_core.restore_checkpoint_counters(op_ckpt) is None
            # operator-authorized = fresh run → minted identity is kept untouched.
            assert lazy_core.read_run_marker()["started_at"] == minted
        finally:
            _clear_state_dir()

        # --- (4): a >24h-stale checkpoint identity is NOT restored --------------
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            minted = lazy_core.read_run_marker()["started_at"]
            stale_ident = "2020-01-01T00:00:00Z"  # decades old → past the age gate
            stale_ckpt = {
                "reason": "checkpoint",
                "next_route": "x",
                "counters": {"forward_cycles": 1, "meta_cycles": 0, "max_cycles": 25},
                "run_started_at": stale_ident,
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(stale_ckpt)
            assert restored is not None
            # Age gate preserved: the stale identity is REFUSED, minted kept.
            assert restored["started_at"] == minted, restored
        finally:
            _clear_state_dir()

        # --- (5): missing / unparseable identity leaves the minted started_at ---
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            minted = lazy_core.read_run_marker()["started_at"]
            for bad in (None, "", "not-a-timestamp", 12345):
                ckpt = {
                    "reason": "checkpoint",
                    "next_route": "x",
                    "counters": {"forward_cycles": 2, "meta_cycles": 0},
                    "run_started_at": bad,
                    "ts": 0,
                }
                restored = lazy_core.restore_checkpoint_counters(ckpt)
                assert restored is not None
                assert restored["started_at"] == minted, (bad, restored)
        finally:
            _clear_state_dir()




def test_restore_checkpoint_counters_no_checkpoint_is_noop():
    """A genuinely NEW invocation (checkpoint=None) is a no-op — the marker keeps
    its by-design 0/0 start.  Also tolerates malformed/None checkpoints without
    crashing and without touching the marker."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=10,
            )
            # None / non-dict / missing-counters → all no-ops returning None.
            assert lazy_core.restore_checkpoint_counters(None) is None
            assert lazy_core.restore_checkpoint_counters("garbage") is None
            assert lazy_core.restore_checkpoint_counters({}) is None
            assert lazy_core.restore_checkpoint_counters({"counters": "x"}) is None
            # Marker untouched — still the by-design fresh 0/0 start.
            m = lazy_core.read_run_marker()
            assert m["forward_cycles"] == 0 and m["meta_cycles"] == 0, m
        finally:
            _clear_state_dir()




def test_restore_checkpoint_counters_operator_authorized_resets():
    """operator-checkpoint-resume-counter-reset Phase 2: an operator-authorized
    checkpoint resume starts a FRESH budget — restore_checkpoint_counters must NOT
    overwrite the just-written 0/0 marker.  The deliberate /lazy-batch <N> re-invoke
    wants a fresh authorized budget, not the paused counts."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Fresh run-start zeros the marker.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            # An operator-authorized checkpoint carrying live paused counts.
            checkpoint = {
                "reason": "checkpoint",
                "next_route": "execute-plan Phase 3",
                "counters": {"forward_cycles": 7, "meta_cycles": 4, "max_cycles": 25},
                "operator_authorized": True,
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            # Returns None — no overwrite occurred (marker keeps its 0/0 start).
            assert restored is None, (
                "operator-authorized resume must NOT carry counters forward"
            )
            on_disk = lazy_core.read_run_marker()
            assert on_disk["forward_cycles"] == 0, on_disk
            assert on_disk["meta_cycles"] == 0, on_disk
        finally:
            _clear_state_dir()




def test_restore_checkpoint_counters_legacy_file_carries_forward():
    """A pre-fix checkpoint file (no operator_authorized field) takes the
    carry-forward path — backward compatibility.  Same as a falsy field."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            # Legacy checkpoint — NO operator_authorized field at all.
            legacy = {
                "reason": "checkpoint",
                "next_route": "execute-plan Phase 3",
                "counters": {"forward_cycles": 6, "meta_cycles": 2, "max_cycles": 25},
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(legacy)
            assert restored is not None, "legacy file must carry forward"
            assert restored["forward_cycles"] == 6, restored
            assert restored["meta_cycles"] == 2, restored

            # An explicit operator_authorized: False is identical (carry-forward).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            explicit_false = dict(legacy, operator_authorized=False)
            restored2 = lazy_core.restore_checkpoint_counters(explicit_false)
            assert restored2 is not None
            assert restored2["forward_cycles"] == 6, restored2
            assert restored2["meta_cycles"] == 2, restored2
        finally:
            _clear_state_dir()




def test_restore_checkpoint_counters_coerces_garbage_counts():
    """Malformed counter values in the checkpoint (None / strings / negatives)
    coerce to non-negative ints rather than crashing run-start."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=10,
            )
            ckpt = {"counters": {"forward_cycles": None, "meta_cycles": "bad"}}
            restored = lazy_core.restore_checkpoint_counters(ckpt)
            assert restored is not None
            assert restored["forward_cycles"] == 0, restored
            assert restored["meta_cycles"] == 0, restored

            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=10,
            )
            ckpt2 = {"counters": {"forward_cycles": -3, "meta_cycles": 5}}
            restored2 = lazy_core.restore_checkpoint_counters(ckpt2)
            assert restored2["forward_cycles"] == 0, restored2  # negative clamped
            assert restored2["meta_cycles"] == 5, restored2
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# adhoc-checkpoint-resume-field-complete-continuity (2026-06-23)
#
# Phase 1: enumerated continuity/fresh partition SSOT + completeness assertion.
# The two frozensets RUN_CONTINUITY_FIELDS / RUN_FRESH_FIELDS must EXACTLY
# partition the run-scoped key set of a freshly-minted write_run_marker — so a
# newly-added run-scoped marker field can never silently default to the RESET
# side (the structural cause of the field-by-field whack-a-mole this bug closes).
# ---------------------------------------------------------------------------

def test_run_marker_continuity_partition_is_complete_and_disjoint():
    """RUN_CONTINUITY_FIELDS | RUN_FRESH_FIELDS EXACTLY equals the run-scoped key
    set of a freshly-minted marker, and the two sets are disjoint.  This is the
    by-construction completeness invariant: every run-scoped marker key is
    classified as either carried-across-a-sanctioned-resume or reset-on-resume."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            marker = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
                now=0.0,
            )
            minted_keys = set(marker.keys())
            union = set(lazy_core.RUN_CONTINUITY_FIELDS) | set(
                lazy_core.RUN_FRESH_FIELDS
            )
            # Completeness: the partition covers EXACTLY the minted key set.
            assert union == minted_keys, (
                "partition must cover exactly the minted run-scoped keys",
                {"only_in_partition": union - minted_keys,
                 "only_in_marker": minted_keys - union},
            )
            # Disjointness: no key is classified as both carry AND reset.
            assert set(lazy_core.RUN_CONTINUITY_FIELDS).isdisjoint(
                lazy_core.RUN_FRESH_FIELDS
            ), "continuity and fresh sets must be disjoint"
            # Spec-pinned membership: the carry set is exactly the SPEC's list.
            assert set(lazy_core.RUN_CONTINUITY_FIELDS) == {
                "forward_cycles", "meta_cycles", "started_at",
                "per_feature_forward_cycles", "per_feature_corrective_cycles",
            }, lazy_core.RUN_CONTINUITY_FIELDS
            # last_advance_consume_count is deliberately on the RESET side.
            assert "last_advance_consume_count" in lazy_core.RUN_FRESH_FIELDS
        finally:
            _clear_state_dir()




def test_run_marker_continuity_partition_helper_matches_literal():
    """The key-set helper (_run_marker_scoped_keys) returns the SAME key set as a
    freshly-minted marker — so the completeness assertion checks against the live
    literal, not a hand-copied list that could drift."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            marker = lazy_core.write_run_marker(
                pipeline="bug", cloud=True, repo_root="/r", max_cycles=10, now=0.0,
            )
            assert lazy_core._run_marker_scoped_keys() == set(marker.keys())
        finally:
            _clear_state_dir()




def test_run_marker_partition_guard_rejects_unclassified_new_field():
    """Guard (the "new field can't silently reset" proof): a synthetic extra key
    present in the marker-key set but in NEITHER partition set makes the
    completeness predicate FALSE — proving an unclassified new run-scoped field is
    a HARD failure, not a silent default to reset."""
    _guard()
    # The partition predicate the completeness assertion enforces, evaluated
    # against a synthetic key set that includes an unclassified field.
    union = set(lazy_core.RUN_CONTINUITY_FIELDS) | set(lazy_core.RUN_FRESH_FIELDS)
    synthetic_keys = union | {"some_new_run_scoped_field"}
    # The new field is in the minted set but in neither partition → not complete.
    assert union != synthetic_keys
    assert not synthetic_keys.issubset(union), (
        "an unclassified new field must NOT be a subset of the partition union"
    )




# ---------------------------------------------------------------------------
# adhoc-checkpoint-resume-field-complete-continuity Phase 2:
# snapshot the FULL continuity block at checkpoint-write + restore it as one
# unit on resume, preserving every guard + legacy back-compat.
# ---------------------------------------------------------------------------

def test_write_run_checkpoint_snapshots_full_continuity_block():
    """write_run_checkpoint captures EVERY RUN_CONTINUITY_FIELDS key present on the
    live marker into a nested `continuity` block — incl. the two per_feature_* maps
    with non-empty contents — reading the marker RAW (non-destructive on a stale
    marker).  Back-compat keys (reason/next_route/counters/operator_authorized/ts)
    are retained."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Mint a marker (current time → not age-stale), then seed live
            # continuity state directly on it.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            m = lazy_core.read_run_marker()
            m["forward_cycles"] = 7
            m["meta_cycles"] = 4
            m["per_feature_forward_cycles"] = {"feat-a": 5, "feat-b": 2}
            m["per_feature_corrective_cycles"] = {"feat-a": 1}
            mp = Path(td) / "lazy-run-marker.json"
            mp.write_text(json.dumps(m), encoding="utf-8")
            seeded_started_at = m["started_at"]

            ckpt = lazy_core.write_run_checkpoint(
                "execute-plan Phase 3",
                {"forward_cycles": 7, "meta_cycles": 4, "max_cycles": 25},
            )
            cont = ckpt.get("continuity")
            assert isinstance(cont, dict), ("continuity block must exist", ckpt)
            assert cont["forward_cycles"] == 7, cont
            assert cont["meta_cycles"] == 4, cont
            assert cont["started_at"] == seeded_started_at, cont
            assert cont["per_feature_forward_cycles"] == {"feat-a": 5, "feat-b": 2}, cont
            assert cont["per_feature_corrective_cycles"] == {"feat-a": 1}, cont
            # last_advance_consume_count is a RUN_FRESH_FIELD → NOT in continuity.
            assert "last_advance_consume_count" not in cont, cont
            # Back-compat top-level keys retained.
            for k in ("reason", "next_route", "counters", "operator_authorized", "ts"):
                assert k in ckpt, (k, ckpt)
        finally:
            _clear_state_dir()




def test_write_run_checkpoint_raw_read_non_destructive_on_stale_marker():
    """The continuity snapshot reads the marker RAW (never read_run_marker, whose
    path-A age gate DELETES a >24h-stale marker) — so a checkpoint-write on a stale
    marker must NOT delete it."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Mint a marker dated decades ago (well past the 24h age gate).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
                now=0.0,  # 1970 → stale
            )
            mp = Path(td) / "lazy-run-marker.json"
            assert mp.exists()
            lazy_core.write_run_checkpoint(
                "x", {"forward_cycles": 1, "meta_cycles": 0}, now=2000.0,
            )
            # The stale marker must STILL exist (no destructive read).
            assert mp.exists(), "checkpoint-write must not delete the stale marker"
        finally:
            _clear_state_dir()




def test_restore_checkpoint_counters_restores_full_continuity_block():
    """A non-operator-authorized resume restores the ENTIRE continuity block as one
    unit onto the freshly-minted marker — closing the latent third whack-a-mole:
    the two per_feature_* budget maps survive a sanctioned pause verbatim."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            # Within-24h identity computed off the live clock (see the
            # carry-forward test for why a hardcoded date silently ages out of
            # the restore age gate once wall-clock advances >24h past it).
            import datetime as _ident_dt_mod
            original_identity = (
                (_ident_dt_mod.datetime.now(_ident_dt_mod.timezone.utc)
                 - _ident_dt_mod.timedelta(hours=1))
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            checkpoint = {
                "reason": "checkpoint",
                "next_route": "execute-plan Phase 3",
                "counters": {"forward_cycles": 7, "meta_cycles": 4, "max_cycles": 25},
                "continuity": {
                    "forward_cycles": 7,
                    "meta_cycles": 4,
                    "started_at": original_identity,
                    "per_feature_forward_cycles": {"feat-a": 5, "feat-b": 2},
                    "per_feature_corrective_cycles": {"feat-a": 1},
                },
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            assert restored is not None
            assert restored["forward_cycles"] == 7, restored
            assert restored["meta_cycles"] == 4, restored
            assert restored["started_at"] == original_identity, restored
            assert restored["per_feature_forward_cycles"] == {"feat-a": 5, "feat-b": 2}, restored
            assert restored["per_feature_corrective_cycles"] == {"feat-a": 1}, restored
            # RUN_FRESH_FIELD stays reset.
            assert restored["last_advance_consume_count"] == 0, restored
            # On-disk reflects the restore.
            on_disk = lazy_core.read_run_marker()
            assert on_disk["per_feature_forward_cycles"] == {"feat-a": 5, "feat-b": 2}, on_disk
        finally:
            _clear_state_dir()




def test_restore_full_continuity_block_age_gate_preserved():
    """A >24h-stale started_at in the continuity block is NOT restored (the Round-35
    age gate survives the rewrite) — the marker keeps its minted identity, while the
    OTHER continuity fields (counters, per_feature_* maps) still restore."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            minted = lazy_core.read_run_marker()["started_at"]
            checkpoint = {
                "reason": "checkpoint",
                "next_route": "x",
                "counters": {"forward_cycles": 3, "meta_cycles": 1},
                "continuity": {
                    "forward_cycles": 3,
                    "meta_cycles": 1,
                    "started_at": "2020-01-01T00:00:00Z",  # decades stale
                    "per_feature_forward_cycles": {"feat-a": 9},
                    "per_feature_corrective_cycles": {},
                },
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(checkpoint)
            assert restored is not None
            # Stale identity REFUSED → minted kept.
            assert restored["started_at"] == minted, restored
            # The non-identity continuity fields still restore.
            assert restored["forward_cycles"] == 3, restored
            assert restored["per_feature_forward_cycles"] == {"feat-a": 9}, restored
        finally:
            _clear_state_dir()




def test_restore_full_continuity_block_operator_authorized_no_op():
    """An operator_authorized continuity checkpoint still returns None (fresh budget
    + minted identity kept) — the provenance branch is unchanged by the rewrite."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            minted = lazy_core.read_run_marker()["started_at"]
            checkpoint = {
                "reason": "checkpoint",
                "next_route": "x",
                "counters": {"forward_cycles": 7, "meta_cycles": 4},
                "continuity": {
                    "forward_cycles": 7,
                    "meta_cycles": 4,
                    "started_at": "2026-06-23T03:15:38Z",
                    "per_feature_forward_cycles": {"feat-a": 5},
                    "per_feature_corrective_cycles": {},
                },
                "operator_authorized": True,
                "ts": 0,
            }
            assert lazy_core.restore_checkpoint_counters(checkpoint) is None
            on_disk = lazy_core.read_run_marker()
            assert on_disk["forward_cycles"] == 0, on_disk
            assert on_disk["started_at"] == minted, on_disk
            assert on_disk["per_feature_forward_cycles"] == {}, on_disk
        finally:
            _clear_state_dir()




def test_restore_legacy_flat_checkpoint_still_restores_identity():
    """Back-compat: a legacy checkpoint with the flat `run_started_at` + `counters`
    but NO `continuity` block still restores identity + counters via the legacy
    path (a pre-fix / mid-flight checkpoint file resumes correctly)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            # Within-24h identity off the live clock (a hardcoded date silently
            # ages out of the restore age gate once wall-clock advances >24h).
            import datetime as _ident_dt_mod
            legacy_identity = (
                (_ident_dt_mod.datetime.now(_ident_dt_mod.timezone.utc)
                 - _ident_dt_mod.timedelta(hours=1))
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            legacy = {
                "reason": "checkpoint",
                "next_route": "execute-plan Phase 3",
                "counters": {"forward_cycles": 6, "meta_cycles": 2, "max_cycles": 25},
                "run_started_at": legacy_identity,  # flat, no continuity block
                "ts": 0,
            }
            restored = lazy_core.restore_checkpoint_counters(legacy)
            assert restored is not None, "legacy flat checkpoint must carry forward"
            assert restored["forward_cycles"] == 6, restored
            assert restored["meta_cycles"] == 2, restored
            assert restored["started_at"] == legacy_identity, restored
            # No continuity block → per_feature_* maps stay the minted {}.
            assert restored["per_feature_forward_cycles"] == {}, restored
        finally:
            _clear_state_dir()




def test_checkpoint_full_round_trip_continuity_survives():
    """End-to-end: write_run_checkpoint → consume_run_checkpoint →
    restore_checkpoint_counters carries EVERY continuity field (incl. both
    per_feature_* maps) verbatim across a sanctioned same-run pause."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # First run: mint (current time → within the age gate) + seed live
            # continuity state.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            m = lazy_core.read_run_marker()
            seeded_started_at = m["started_at"]
            m["forward_cycles"] = 8
            m["meta_cycles"] = 3
            m["per_feature_forward_cycles"] = {"feat-a": 6, "feat-b": 2}
            m["per_feature_corrective_cycles"] = {"feat-b": 1}
            (Path(td) / "lazy-run-marker.json").write_text(
                json.dumps(m), encoding="utf-8"
            )

            # Pause: write the checkpoint.
            lazy_core.write_run_checkpoint(
                "execute-plan Phase 3",
                {"forward_cycles": 8, "meta_cycles": 3, "max_cycles": 25},
            )

            # Resume: a fresh --run-start re-mints the marker (zeros everything),
            # then consume + restore carries the full continuity block forward.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            consumed = lazy_core.consume_run_checkpoint()
            assert consumed is not None
            restored = lazy_core.restore_checkpoint_counters(consumed)
            assert restored is not None
            assert restored["forward_cycles"] == 8, restored
            assert restored["meta_cycles"] == 3, restored
            assert restored["started_at"] == seeded_started_at, restored
            assert restored["per_feature_forward_cycles"] == {"feat-a": 6, "feat-b": 2}, restored
            assert restored["per_feature_corrective_cycles"] == {"feat-b": 1}, restored
            assert restored["last_advance_consume_count"] == 0, restored
        finally:
            _clear_state_dir()




def test_marker_advance_round_trips_counters_under_rmw():
    """GUARD: every read-modify-write of the marker (advance_run_counters,
    advance_meta_cycle, bind_marker_session) must PRESERVE the other counters and
    last_advance_consume_count — a reserialize that drops a field is the classic
    accidental-reset bug.  This pins the round-trip for all three writers."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", max_cycles=25,
            )
            # Seed live counts directly on the marker.
            m = lazy_core.read_run_marker()
            m["forward_cycles"] = 9
            m["meta_cycles"] = 6
            m["last_advance_consume_count"] = 12
            (Path(td) / "lazy-run-marker.json").write_text(
                json.dumps(m, indent=2) + "\n", encoding="utf-8"
            )

            # bind_marker_session: must preserve BOTH counters + watermark.
            lazy_core._monolith.bind_marker_session("sess-abc")
            after_bind = lazy_core.read_run_marker()
            assert after_bind["forward_cycles"] == 9, after_bind
            assert after_bind["meta_cycles"] == 6, after_bind
            assert after_bind["last_advance_consume_count"] == 12, after_bind
            assert after_bind["session_id"] == "sess-abc", after_bind

            # advance_meta_cycle: meta += 1, forward UNCHANGED.
            lazy_core.advance_meta_cycle()
            after_meta = lazy_core.read_run_marker()
            assert after_meta["meta_cycles"] == 7, after_meta
            assert after_meta["forward_cycles"] == 9, after_meta
        finally:
            _clear_state_dir()




def test_checkpoint_resume_preserves_counters_e2e():
    """Subprocess end-to-end: a checkpoint run-end at fwd=N/meta=M followed by a
    resuming --run-start must echo (and persist) fwd=N/meta=M — NOT 0/0.  This is
    the regression for the operator-observed mid-run reset across a checkpoint
    pause/resume (HARD CONSTRAINT 8)."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "resume-state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        # Start (unattended so the checkpoint auth gate does not block the test).
        assert run(["--run-start", "--max-cycles", "25", "--unattended"]).returncode == 0
        # Seed live counts on the marker (simulating several cycles of progress).
        marker_path = state_dir / "lazy-run-marker.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["forward_cycles"] = 7
        marker["meta_cycles"] = 3
        marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

        # Sanctioned checkpoint pause — folds the live counts into the checkpoint.
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "execute-plan Phase 4"])
        assert r.returncode == 0, f"{r.stdout}{r.stderr}"
        ckpt = json.loads((state_dir / "lazy-run-checkpoint.json").read_text(encoding="utf-8"))
        assert ckpt["counters"]["forward_cycles"] == 7, ckpt
        assert ckpt["counters"]["meta_cycles"] == 3, ckpt

        # Resume: --run-start must RESTORE the counts, not reset to 0/0.
        r2 = run(["--run-start", "--max-cycles", "25", "--unattended"])
        assert r2.returncode == 0
        out2 = json.loads(r2.stdout)
        assert out2["forward_cycles"] == 7, out2
        assert out2["meta_cycles"] == 3, out2
        # And the persisted marker reflects the continued counts.
        resumed_marker = json.loads(marker_path.read_text(encoding="utf-8"))
        assert resumed_marker["forward_cycles"] == 7, resumed_marker
        assert resumed_marker["meta_cycles"] == 3, resumed_marker
        # Watermark resets to 0 (registry was cleared) so the next dispatch advances.
        assert resumed_marker["last_advance_consume_count"] == 0, resumed_marker




def test_operator_authorized_checkpoint_resume_resets_e2e():
    """operator-checkpoint-resume-counter-reset Phase 2 end-to-end: a checkpoint
    run-end with --operator-authorized at fwd=N/meta=M, followed by a resuming
    --run-start, must show fwd=0/meta=0 — a FRESH authorized budget, NOT the
    paused counts.  Contrast with test_checkpoint_resume_preserves_counters_e2e
    (the non-authorized path, which carries forward and stays green)."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "auth-resume-state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        assert run(["--run-start", "--max-cycles", "25", "--unattended"]).returncode == 0
        # Seed live counts on the marker (simulating several cycles of progress).
        marker_path = state_dir / "lazy-run-marker.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["forward_cycles"] = 8
        marker["meta_cycles"] = 5
        marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

        # Operator-authorized checkpoint pause (deliberate stop, fresh budget intended).
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "execute-plan Phase 4", "--operator-authorized"])
        assert r.returncode == 0, f"{r.stdout}{r.stderr}"
        ckpt = json.loads((state_dir / "lazy-run-checkpoint.json").read_text(encoding="utf-8"))
        assert ckpt["operator_authorized"] is True, ckpt
        assert ckpt["counters"]["forward_cycles"] == 8, ckpt

        # Resume: --run-start must RESET to 0/0 (fresh authorized budget).
        r2 = run(["--run-start", "--max-cycles", "25", "--unattended"])
        assert r2.returncode == 0
        out2 = json.loads(r2.stdout)
        # The checkpoint is still echoed as resume context...
        assert "resumed_from_checkpoint" in out2, out2
        # ...but the counters are NOT carried forward.
        resumed_marker = json.loads(marker_path.read_text(encoding="utf-8"))
        assert resumed_marker["forward_cycles"] == 0, resumed_marker
        assert resumed_marker["meta_cycles"] == 0, resumed_marker




def test_emit_dispatch_context_file_long_value():
    """ISSUE 3 (d8-effect-chains live run): a long failure_summary with
    commas/colons/parens/newlines supplied via --context-file produces VALID JSON
    with all fields bound — never the all-None non-JSON failure the live run hit
    with an inline --context value.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    keys = _dispatch_requires("recovery")
    long_summary = (
        "Execute-plan deviated: part-2 (phases:[5], complexity:mechanical) was "
        "dispatched, but its entry criteria (Part 1 complete) were unmet; the "
        "subagent silently executed part-1 (Phase 6, complex audio/IPC), committed "
        "WU-1/WU-2, then died waiting on a backgrounded build.\nNext: route part-1 first."
    ) * 4  # well over 1500 chars, full of shell-hostile punctuation + newlines
    ctx = {k: f"val-{k}" for k in keys}
    ctx["failure_summary"] = long_summary
    if "item_id" not in ctx:
        ctx["item_id"] = "d8-effect-chains"
    with tempfile.TemporaryDirectory() as td:
        cf = Path(td) / "ctx.json"
        cf.write_text(json.dumps(ctx), encoding="utf-8")
        # No marker → peek semantics (no registry write needed for this assertion).
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(Path(td) / "state")
        r = subprocess.run(
            [sys.executable, str(lazy_state), "--emit-dispatch", "recovery",
             "--context-file", str(cf)],
            capture_output=True, text=True, env=env,
        )
        # MUST be parseable JSON regardless of value length/punctuation.
        data = json.loads(r.stdout)
        assert data.get("dispatch_prompt") is not None, (
            f"long context-file value must bind a prompt, got refusal: {data}"
        )
        assert long_summary in data["dispatch_prompt"], (
            "the long failure_summary must appear bound in the prompt"
        )




# ---------------------------------------------------------------------------
# Phase 9 — Bind-at-guard: inject never binds; guard binds on allow
# ---------------------------------------------------------------------------
#
# WU-9.1: lazy_inject.inject() on an UNBOUND marker is a silent no-op (no
# banner, no probe, no registration, no counter advance, no marker mutation).
# WU-9.2: lazy_guard.guard() binds an unbound marker to the caller's session_id
# on ALLOW (both the fresh-consumption and idempotent re-fire paths); DENY never
# binds; a bind failure never changes the allow output (fail-open).


def _phase9_inject_module():
    """Import lazy_inject in-process (it imports lazy_core directly)."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    return importlib.import_module("lazy_inject")




def test_inject_unbound_marker_is_silent_noop():
    """WU-9.1: with an UNBOUND marker (session_id=None), lazy_inject.inject()
    returns None (no banner) AND mutates nothing — the registry is never created,
    the persisted counters never advance, and the marker file stays byte-identical
    (still unbound).  Binding moved to the guard (WU-9.2); inject NEVER binds.
    """
    _guard()
    lazy_inject = _phase9_inject_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _build_phase8_fixture_repo(td_path)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(fixture_repo),
                max_cycles=10, session_id=None, now=_time.time(),
            )
            marker_path = state_dir / "lazy-run-marker.json"
            registry_path = state_dir / "lazy-prompt-registry.json"
            marker_bytes_before = marker_path.read_bytes()
            assert not registry_path.exists(), "pre-condition: no registry yet"

            hook_input = json.dumps({
                "session_id": "session-A",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "what is the current step?",
            })
            result = lazy_inject.inject(hook_input)

            # No banner.
            assert result is None, (
                f"inject on an UNBOUND marker must return None (silent); got {result!r}"
            )
            # Marker byte-identical — no stamp, still unbound.
            assert marker_path.read_bytes() == marker_bytes_before, (
                "WU-9.1: inject must NOT mutate the unbound marker (byte-identical)"
            )
            reread = json.loads(marker_path.read_text(encoding="utf-8"))
            assert reread.get("session_id") is None, "marker must remain unbound"
            assert reread.get("forward_cycles") == 0 and reread.get("meta_cycles") == 0, (
                "WU-9.1: inject must NOT advance persisted run counters"
            )
            # No registry created — the probe must never have run.
            assert not registry_path.exists(), (
                "WU-9.1: inject must NOT run the probe / register any emission"
            )
        finally:
            _clear_state_dir()




def test_inject_bound_owner_still_produces_banner():
    """WU-9.1 regression guard: a BOUND-owner marker (session_id matches the
    hook-input session_id) still produces the LAZY-ROUTE banner — the bound path
    is unchanged.  Drives lazy_inject.inject() in-process against a real fixture
    repo so the probe returns a usable cycle_prompt.
    """
    _guard()
    lazy_inject = _phase9_inject_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _build_phase8_fixture_repo(td_path)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(fixture_repo),
                max_cycles=10, session_id="owner-session", now=_time.time(),
            )
            hook_input = json.dumps({
                "session_id": "owner-session",  # MATCHES the bound marker
                "hook_event_name": "UserPromptSubmit",
                "prompt": "what is the current step?",
            })
            result = lazy_inject.inject(hook_input)
            assert result is not None, "bound-owner inject must produce a banner"
            payload = json.loads(result)
            ctx = payload["hookSpecificOutput"]["additionalContext"]
            assert ctx.startswith("LAZY-ROUTE (hook-injected"), (
                f"bound-owner inject must emit the LAZY-ROUTE banner; got {ctx[:120]!r}"
            )
        finally:
            _clear_state_dir()




def test_guard_unbound_marker_deny_does_not_bind():
    """WU-9.2: a DENY (lookup miss) on an UNBOUND marker must NOT bind — the
    marker stays unbound (session_id=None).  Only an ALLOW binds."""
    _guard()
    lazy_guard = _phase9_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, session_id=None, now=_time.time(),  # UNBOUND
            )
            # Prompt is NEVER registered → guard must deny.
            hook_input = json.dumps({
                "session_id": "denier-session",
                "tool_use_id": "tu-deny",
                "tool_input": {"prompt": "HAND-COMPOSED unregistered prompt"},
            })
            out = lazy_guard.guard(hook_input)
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "deny", out

            # Marker must STAY unbound — a deny never binds.
            marker = json.loads(
                (state_dir / "lazy-run-marker.json").read_text(encoding="utf-8")
            )
            assert marker.get("session_id") is None, (
                f"WU-9.2: a DENY must NOT bind the marker; "
                f"got session_id={marker.get('session_id')!r}"
            )
        finally:
            _clear_state_dir()




def test_guard_bind_failure_is_fail_open():
    """WU-9.2: if bind_marker_session raises during an ALLOW, the allow output is
    unchanged (fail-open).  Monkeypatch bind_marker_session to explode; the
    guard must still ALLOW."""
    _guard()
    lazy_guard = _phase9_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, session_id=None, now=_time.time(),  # UNBOUND
            )
            prompt = "Run the next cycle step with a poisoned bind."
            lazy_core.register_emission(prompt, cls="cycle")

            original = lazy_core._monolith.bind_marker_session
            def _boom(*a, **k):
                raise RuntimeError("bind exploded")
            lazy_core._monolith.bind_marker_session = _boom  # type: ignore[assignment]
            try:
                out = lazy_guard.guard(json.dumps({
                    "session_id": "poison-session",
                    "tool_use_id": "tu-poison",
                    "tool_input": {"prompt": prompt},
                }))
            finally:
                lazy_core._monolith.bind_marker_session = original  # type: ignore[assignment]

            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", (
                "WU-9.2: a bind failure must NEVER change the allow output (fail-open)"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 1: all Phase 1 symbols are present on lazy_core
# ---------------------------------------------------------------------------

def test_run_state_symbols_present():
    """All Phase 1 public symbols exist on lazy_core.

    RED state: none of these attributes exist yet — every name will be missing,
    producing a clear 'missing symbols' AssertionError rather than an AttributeError
    deep in the test body.
    """
    _guard()
    expected = [
        "claude_state_dir",
        "write_run_marker",
        "read_run_marker",
        "delete_run_marker",
        "normalize_prompt_for_hash",
        "prompt_sha256",
        "register_emission",
        "lookup_emission",
        "consume_nonce",
        "register_emission_if_marked",
        "fold_run_counters",
        "advance_run_counters",
        "REGISTRY_ENTRY_TTL_SECONDS",
    ]
    missing = [sym for sym in expected if not hasattr(lazy_core, sym)]
    assert not missing, f"missing Phase 1 symbols: {missing}"




# ---------------------------------------------------------------------------
# Test 2: marker lifecycle — write→read round-trip, ISO-Z, delete idempotent
# ---------------------------------------------------------------------------

def test_marker_write_read_roundtrip():
    """write_run_marker→read_run_marker round-trip preserves all fields;
    started_at is ISO-8601 UTC with trailing 'Z'; delete_run_marker is True
    on first call and idempotent (False) on second.

    RED state: write_run_marker / read_run_marker / delete_run_marker missing.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now_epoch = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root="/tmp/repo",
                max_cycles=10,
                session_id="ses-abc",
                nonce_seed="seed-xyz",
                now=now_epoch,
            )
            marker = lazy_core.read_run_marker(now=now_epoch)
            assert marker is not None, "read_run_marker returned None immediately after write"
            assert marker["pipeline"] == "feature", f"pipeline mismatch: {marker}"
            assert marker["cloud"] is False, f"cloud mismatch: {marker}"
            assert marker["repo_root"] == "/tmp/repo", f"repo_root mismatch: {marker}"
            assert marker["max_cycles"] == 10, f"max_cycles mismatch: {marker}"
            assert marker["session_id"] == "ses-abc", f"session_id mismatch: {marker}"
            assert marker["nonce_seed"] == "seed-xyz", f"nonce_seed mismatch: {marker}"
            assert marker["forward_cycles"] == 0, f"forward_cycles should init at 0: {marker}"
            assert marker["meta_cycles"] == 0, f"meta_cycles should init at 0: {marker}"
            # started_at must be ISO-8601 UTC ending in 'Z'
            started = marker.get("started_at", "")
            assert started.endswith("Z"), (
                f"started_at must end with 'Z' (UTC ISO-8601), got {started!r}"
            )
            # Delete returns True on first call (marker existed)
            first_delete = lazy_core.delete_run_marker()
            assert first_delete is True, (
                f"delete_run_marker must return True when marker exists, got {first_delete!r}"
            )
            # Idempotent: second delete returns False (file already gone)
            second_delete = lazy_core.delete_run_marker()
            assert second_delete is False, (
                f"delete_run_marker must return False when already absent, got {second_delete!r}"
            )
            # read_run_marker after deletion returns None
            after = lazy_core.read_run_marker(now=now_epoch)
            assert after is None, f"read_run_marker must return None after deletion, got {after!r}"
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 3: marker staleness path A — started_at > 24 h → None + file deleted
# ---------------------------------------------------------------------------

def test_marker_staleness_age():
    """A marker whose started_at is 25h before the injected 'now' → read
    returns None AND the marker file is deleted from the state dir.

    RED state: read_run_marker staleness logic not implemented.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            base_epoch = _time.time()
            # Write a marker with now = base_epoch
            lazy_core.write_run_marker(
                pipeline="feature",
                cloud=False,
                repo_root="/tmp/repo",
                max_cycles=5,
                now=base_epoch,
            )
            # Read it 25 hours later — must be stale
            future_now = base_epoch + 25 * 3600
            result = lazy_core.read_run_marker(now=future_now)
            assert result is None, (
                f"read_run_marker must return None for a 25h-old marker, got {result!r}"
            )
            # The file must also be gone (delete-on-stale)
            state_dir = lazy_core.claude_state_dir()
            marker_file = state_dir / "lazy-run-marker.json"
            assert not marker_file.exists(), (
                "marker file must be deleted when stale (age > 24h)"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 4: marker staleness path B — session_id mismatch / match / bind-pending
# ---------------------------------------------------------------------------

def test_marker_staleness_session_id():
    """Session-id staleness: mismatching session_id → None but file SURVIVES
    (Phase 8 WU-8.1 non-destructive path B); matching session_id → returned;
    marker with session_id=None + any session arg → returned (bind-pending
    markers are never session-stale).

    REVISED for Phase 8 WU-8.1: path B was previously delete-on-read; it is now
    NON-DESTRUCTIVE so a concurrent non-owner session never disarms the owner's
    live run.  The owner-still-reads and file-survives legs are asserted in
    test_marker_staleness_session_id_non_destructive below.
    """
    _guard()
    import time as _time
    base_epoch = _time.time()

    # -- Path B1: bound session_id mismatch → None, but file LEFT IN PLACE
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, session_id="ses-aaa", now=base_epoch,
            )
            result = lazy_core.read_run_marker(now=base_epoch, session_id="ses-bbb")
            assert result is None, (
                f"session_id mismatch must return None, got {result!r}"
            )
            state_dir = lazy_core.claude_state_dir()
            assert (state_dir / "lazy-run-marker.json").exists(), (
                "Phase 8 WU-8.1: marker file must SURVIVE a non-owner session "
                "mismatch read (non-destructive path B)"
            )
        finally:
            _clear_state_dir()

    # -- Path B2: matching session_id → returned
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, session_id="ses-aaa", now=base_epoch,
            )
            result = lazy_core.read_run_marker(now=base_epoch, session_id="ses-aaa")
            assert result is not None, (
                "matching session_id must return the marker, got None"
            )
            assert result["session_id"] == "ses-aaa", f"session_id mismatch in result: {result}"
        finally:
            _clear_state_dir()

    # -- Path B3: marker with session_id=None + any session arg → returned (bind-pending)
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # session_id=None means bind-on-first-hook-firing; never stale on session
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, session_id=None, now=base_epoch,
            )
            result = lazy_core.read_run_marker(now=base_epoch, session_id="any-session")
            assert result is not None, (
                "bind-pending marker (session_id=None) must never be session-stale; got None"
            )
        finally:
            _clear_state_dir()




def test_marker_staleness_session_id_non_destructive():
    """Phase 8 WU-8.1: a non-owner read (session mismatch) returns None AND
    leaves the marker on disk; afterwards the OWNER session_id still reads the
    marker successfully.  This is the concurrent-session safety guarantee — an
    interactive session firing the inject/guard hook must never disarm a live
    marked run owned by a different session.
    """
    _guard()
    import time as _time
    base_epoch = _time.time()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, session_id="owner-ses", now=base_epoch,
            )
            marker_path = lazy_core.claude_state_dir() / "lazy-run-marker.json"

            # (a) Non-owner read → None AND file still exists.
            non_owner = lazy_core.read_run_marker(now=base_epoch, session_id="other-ses")
            assert non_owner is None, f"non-owner read must be None, got {non_owner!r}"
            assert marker_path.exists(), (
                "non-owner read must NOT delete the marker (non-destructive path B)"
            )

            # (b) After the non-owner read, the OWNER still reads successfully.
            owner = lazy_core.read_run_marker(now=base_epoch, session_id="owner-ses")
            assert owner is not None, (
                "owner session must still read the marker after a non-owner read"
            )
            assert owner["session_id"] == "owner-ses", owner

            # A second non-owner read is still non-destructive (idempotent).
            assert lazy_core.read_run_marker(now=base_epoch, session_id="x") is None
            assert marker_path.exists(), "repeated non-owner reads must not delete"
        finally:
            _clear_state_dir()




def test_marker_age_and_corrupt_still_delete():
    """Phase 8 WU-8.1 regression guard: path A (age > 24h) and the corrupt-file
    path KEEP delete-on-read — only path B (session mismatch) became
    non-destructive.  This pins the asymmetry so a future edit cannot silently
    make age/corrupt non-destructive too.
    """
    _guard()
    import time as _time
    base_epoch = _time.time()

    # Age-stale (path A) → deleted.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, session_id="owner", now=base_epoch,
            )
            mp = lazy_core.claude_state_dir() / "lazy-run-marker.json"
            assert lazy_core.read_run_marker(now=base_epoch + 25 * 3600) is None
            assert not mp.exists(), "age-stale marker (path A) must still be deleted"
        finally:
            _clear_state_dir()

    # Corrupt → deleted.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            mp = lazy_core.claude_state_dir() / "lazy-run-marker.json"
            mp.write_text("{ not valid json", encoding="utf-8")
            assert lazy_core.read_run_marker(now=base_epoch) is None
            assert not mp.exists(), "corrupt marker must still be deleted"
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 10: fold_run_counters and advance_run_counters
# ---------------------------------------------------------------------------

def test_fold_and_advance_run_counters():
    """fold_run_counters: explicit flags win; fallback to marker values; both
    None when no flags and no marker.

    advance_run_counters: truthy sub_skill not starting with '__' → increments
    forward_cycles only; '__*' or None sub_skill → increments meta_cycles only;
    no marker → returns None.

    ISSUE 5 (d8-effect-chains live run): advance is now CONSUME-GATED — a counter
    advances only when the registry consume-count exceeds the marker's
    last_advance_consume_count. Each advance below is preceded by a simulated
    dispatch consume (register_emission + consume_nonce) so the gate is satisfied;
    a separate test (test_advance_run_counters_consume_gated) covers the no-consume
    no-op path that is the actual fix.

    RED state: fold_run_counters / advance_run_counters not implemented.
    """
    _guard()
    import time as _time

    def _simulate_dispatch_consume():
        """Bump the registry consume-count by one (mimics a guard ALLOW)."""
        entry = lazy_core.register_emission("dispatch prompt", "cycle")
        lazy_core._monolith.consume_nonce(entry["nonce"])

    # --- fold_run_counters ---
    # (1) Explicit flag wins over marker value
    marker_with_counters = {"forward_cycles": 1, "meta_cycles": 2}
    f, m = lazy_core.fold_run_counters(3, None, marker_with_counters)
    assert f == 3, (
        f"explicit forward_flag=3 must win over marker's forward_cycles=1, got f={f!r}"
    )
    assert m == 2, (
        f"meta_flag=None must fall back to marker's meta_cycles=2, got m={m!r}"
    )

    # (2) No flags → use marker values
    f2, m2 = lazy_core.fold_run_counters(None, None, marker_with_counters)
    assert f2 == 1, f"fold with None flags must use marker forward_cycles=1, got {f2!r}"
    assert m2 == 2, f"fold with None flags must use marker meta_cycles=2, got {m2!r}"

    # (3) No flags, no marker → (None, None)
    f3, m3 = lazy_core.fold_run_counters(None, None, None)
    assert f3 is None, f"fold with no marker must return (None, None), got f3={f3!r}"
    assert m3 is None, f"fold with no marker must return (None, None), got m3={m3!r}"

    # --- advance_run_counters ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=10, now=now,
            )
            # Real sub_skill (forward cycle) — preceded by a dispatch consume.
            _simulate_dispatch_consume()
            state_forward = {"sub_skill": "/execute-plan", "feature_id": "feat-x"}
            updated = lazy_core.advance_run_counters(state_forward)
            assert updated is not None, (
                "advance_run_counters must return updated marker for real sub_skill"
            )
            assert updated["forward_cycles"] == 1, (
                f"forward_cycles must increment to 1 after a real sub_skill cycle, "
                f"got {updated['forward_cycles']!r}"
            )
            assert updated["meta_cycles"] == 0, (
                f"meta_cycles must stay 0 for a forward cycle, got {updated['meta_cycles']!r}"
            )

            # Pseudo sub_skill (__mark_complete__) → meta cycle (new consume first).
            _simulate_dispatch_consume()
            state_meta = {"sub_skill": "__mark_complete__", "feature_id": "feat-x"}
            updated2 = lazy_core.advance_run_counters(state_meta)
            assert updated2 is not None, (
                "advance_run_counters must return updated marker for meta sub_skill"
            )
            assert updated2["forward_cycles"] == 1, (
                f"forward_cycles must stay 1 for a meta cycle, got {updated2['forward_cycles']!r}"
            )
            assert updated2["meta_cycles"] == 1, (
                f"meta_cycles must increment to 1 after __mark_complete__, "
                f"got {updated2['meta_cycles']!r}"
            )

            # sub_skill=None → meta (new consume first).
            _simulate_dispatch_consume()
            state_none_skill = {"sub_skill": None, "feature_id": "feat-x"}
            updated3 = lazy_core.advance_run_counters(state_none_skill)
            assert updated3 is not None, "advance_run_counters must return marker"
            assert updated3["meta_cycles"] == 2, (
                f"sub_skill=None must increment meta_cycles (now 2), got {updated3!r}"
            )

        finally:
            _clear_state_dir()

    # No marker → returns None
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            result_no_marker = lazy_core.advance_run_counters(
                {"sub_skill": "/execute-plan", "feature_id": "feat-x"}
            )
            assert result_no_marker is None, (
                f"advance_run_counters must return None when no marker present, "
                f"got {result_no_marker!r}"
            )
        finally:
            _clear_state_dir()




def test_advance_run_counters_consume_gated():
    """ISSUE 5 (d8-effect-chains live run): advance_run_counters is a NO-OP when no
    dispatch (registry consume) has landed since the last advance.

    This is the actual fix for the forward_cycles inflation: the inject hook fires
    the probe with --repeat-count on EVERY UserPromptSubmit turn; without the
    consume gate, each firing advanced the counter (forward_cycles hit 11 after ~2
    real dispatches). With the gate, repeated probes between two dispatches do not
    advance.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=25, now=_time.time(),
            )
            state = {"sub_skill": "/execute-plan", "feature_id": "feat-x"}

            # (1) Bare probe BEFORE any dispatch → no advance (consume-count 0).
            m0 = lazy_core.advance_run_counters(state)
            assert m0 is not None, "marker present → returns marker"
            assert m0["forward_cycles"] == 0, (
                f"no dispatch yet → forward_cycles stays 0, got {m0['forward_cycles']!r}"
            )

            # (2) One dispatch consume → exactly ONE advance, no matter how many
            #     probe firings happen between dispatches.
            entry = lazy_core.register_emission("p", "cycle")
            lazy_core._monolith.consume_nonce(entry["nonce"])
            m1 = lazy_core.advance_run_counters(state)
            assert m1["forward_cycles"] == 1, (
                f"one dispatch → forward_cycles 1, got {m1['forward_cycles']!r}"
            )
            # Three more bare probes (inject firings) with NO new dispatch → no-op.
            for _ in range(3):
                mN = lazy_core.advance_run_counters(state)
                assert mN["forward_cycles"] == 1, (
                    f"bare probe must NOT advance forward_cycles, got "
                    f"{mN['forward_cycles']!r}"
                )

            # (3) A second dispatch consume → advances again (to 2).
            entry2 = lazy_core.register_emission("p2", "cycle")
            lazy_core._monolith.consume_nonce(entry2["nonce"])
            m2 = lazy_core.advance_run_counters(state)
            assert m2["forward_cycles"] == 2, (
                f"second dispatch → forward_cycles 2, got {m2['forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_advance_meta_cycle_increments_meta():
    """ISSUE 5: a meta/recovery dispatch (--emit-dispatch path) advances meta_cycles
    via advance_meta_cycle, and absorbs its own consume so a follow-on forward probe
    does not double-count.

    In the live run meta_cycles stayed 0 through 2 recoveries because recovery goes
    through --emit-dispatch, not the --repeat-count probe. advance_meta_cycle closes
    that gap.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=25, now=_time.time(),
            )
            # No marker-less path: marker present.
            m = lazy_core.advance_meta_cycle()
            assert m is not None and m["meta_cycles"] == 1, (
                f"advance_meta_cycle must increment meta_cycles to 1, got {m!r}"
            )
            assert m["forward_cycles"] == 0, "meta advance must not touch forward_cycles"
            # The watermark was bumped to consume+1 to absorb the meta dispatch's own
            # forthcoming consume. Simulate that consume; a forward probe must NOT
            # advance off it (it belonged to the meta dispatch).
            entry = lazy_core.register_emission("recovery prompt", "recovery")
            lazy_core._monolith.consume_nonce(entry["nonce"])
            m2 = lazy_core.advance_run_counters(
                {"sub_skill": "/execute-plan", "feature_id": "feat-x"}
            )
            assert m2["forward_cycles"] == 0, (
                f"the meta dispatch's own consume must NOT advance forward_cycles, "
                f"got {m2['forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()

    # No marker → returns None.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.advance_meta_cycle() is None, (
                "advance_meta_cycle must return None when no marker present"
            )
        finally:
            _clear_state_dir()



# Compiled regex for @requires first-line marker (reused across tests).
_REQUIRES_LINE_RE = re.compile(r'^<!-- @requires [a-z0-9_,]+ -->$')




def test_emit_dispatch_real_templates_exist_and_declare_requires():
    """For each of the six Phase 3 classes, the template file
    user/skills/_components/lazy-batch-prompts/dispatch-<class>.md must exist
    and its first non-empty line must match '<!-- @requires [a-z0-9_,]+ -->'.

    RED: template files do not yet exist → assertion fails naming the missing file.
    """
    _guard()
    # DISPATCH_CLASSES must be present for this test to be meaningful.
    assert hasattr(lazy_core, "DISPATCH_CLASSES"), (
        "lazy_core.DISPATCH_CLASSES missing — cannot run template-existence test"
    )

    for cls in lazy_core.DISPATCH_CLASSES:
        tpl_path = _REAL_TEMPLATE_DIR / f"dispatch-{cls}.md"
        assert tpl_path.exists(), (
            f"dispatch template missing: {tpl_path}\n"
            f"  Phase 3 requires one dispatch-<class>.md per class in DISPATCH_CLASSES."
        )
        # First non-empty line must be the @requires marker.
        text = tpl_path.read_text(encoding="utf-8")
        first_line = next(
            (ln for ln in text.splitlines() if ln.strip()),
            ""
        )
        assert _REQUIRES_LINE_RE.match(first_line), (
            f"dispatch-{cls}.md first non-empty line must be "
            f"'<!-- @requires key1,key2,... -->' (only [a-z0-9_,] chars); "
            f"got: {first_line!r}"
        )




# ---------------------------------------------------------------------------
# Phase 7 (lazy-validation-readiness) — stop-authorization + attended marker
# ---------------------------------------------------------------------------
# Motivating incident: 2026-06-14 attended /lazy-batch 50 run stopped at 5/50
# via --run-end --reason checkpoint without operator authorization.  These tests
# mechanically enforce the gates that prevent that from recurring.
# ---------------------------------------------------------------------------

import os as _os_env_p7  # alias for Phase 7 env helpers (separate from existing _os_env)




def test_p7_write_run_marker_defaults_attended():
    """write_run_marker stores attended=True by default (no attended kwarg supplied).

    RED until write_run_marker gains the ``attended`` keyword parameter.
    """
    _guard()
    import time as _time_p7
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now_e = _time_p7.time()
            m = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r", now=now_e,
            )
            assert m.get("attended") is True, (
                f"write_run_marker must default attended=True; got {m.get('attended')!r}"
            )
            # Verify persisted value is also True (round-trip)
            on_disk = lazy_core.read_run_marker(now=now_e)
            assert on_disk is not None, "marker must be readable after write"
            assert on_disk.get("attended") is True, (
                f"on-disk marker attended must be True (default); got {on_disk.get('attended')!r}"
            )
        finally:
            _clear_state_dir()




def test_p7_write_run_marker_attended_false():
    """write_run_marker with attended=False records the value as False.

    RED until the attended kwarg is implemented.
    """
    _guard()
    import time as _time_p7
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now_e = _time_p7.time()
            m = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                attended=False, now=now_e,
            )
            assert m.get("attended") is False, (
                f"write_run_marker(attended=False) must record False; got {m.get('attended')!r}"
            )
            on_disk = lazy_core.read_run_marker(now=now_e)
            assert on_disk is not None
            assert on_disk.get("attended") is False, (
                f"on-disk marker attended must be False when attended=False passed; "
                f"got {on_disk.get('attended')!r}"
            )
        finally:
            _clear_state_dir()




def test_p7_marker_missing_attended_defaults_true():
    """A legacy marker dict lacking the 'attended' key is treated as attended
    (the stricter gate is the safe default).  Per the spec, the run-end gate
    reads ``marker.get('attended', True)`` — missing → True.

    This test verifies the gate's default by crafting a bare marker dict and
    checking the gate expression directly.  No subprocess needed.

    RED (trivially) until the spec's marker.get('attended', True) idiom is
    confirmed present in the implementation; this test pins the semantic contract.
    """
    _guard()
    # Simulate a legacy marker that has no 'attended' key.
    legacy_marker = {
        "pipeline": "feature",
        "cloud": False,
        "repo_root": "/tmp/r",
        "started_at": "2024-01-01T00:00:00Z",
        "forward_cycles": 0,
        "meta_cycles": 0,
    }
    # The gate expression the run-end handler uses.
    attended = legacy_marker.get("attended", True)
    assert attended is True, (
        f"A legacy marker without 'attended' must default to True (stricter gate); "
        f"got {attended!r}"
    )




def test_p7_run_end_checkpoint_attended_no_auth_refuses():
    """--run-end --reason checkpoint against an ATTENDED marker WITHOUT
    --operator-authorized must be REFUSED: exit 1, run_marker_deleted=False,
    and the marker file must still be on disk.

    RED until the stop-authorization gate is implemented in lazy-state.py.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-ckpt-attended"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: a hermetic fixture repo
        # root — NEVER the default os.getcwd() (the real claude-config
        # checkout) — so notify_event/flush_cloud_telemetry_segment and any
        # other --repo-root consumer this subprocess reaches never touch the
        # real repo.
        repo_dir = Path(td) / "p7-ckpt-attended-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        # --run-start WITHOUT --unattended → attended=True marker.
        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0, f"run-start failed: {r_start.stderr}"

        # adhoc-run-end-tests-leak-real-repo-state: seed the efficacy-flush
        # breadcrumb FIRST so this --run-end reaches the STOP-AUTHORIZATION
        # (checkpoint) gate under test, not the earlier-positioned efficacy
        # gate (which would otherwise refuse first and mask the assertion
        # below — a distinct refusal reason that happened to satisfy the same
        # loose {exit 1, run_marker_deleted: False, "refused" present} shape).
        _seed_efficacy_breadcrumb(state_dir)

        # --run-end --reason checkpoint WITHOUT --operator-authorized → REFUSE.
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "implement Phase 3"])
        assert r.returncode == 1, (
            f"run-end checkpoint on attended marker must exit 1 (refused); "
            f"got {r.returncode}; stdout={r.stdout!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is False, (
            f"refused run-end must NOT delete the marker; got {out!r}"
        )
        assert "refused" in out, f"refused output must contain 'refused' key; got {out!r}"
        # Pin the refusal to the STOP-AUTHORIZATION (checkpoint) gate
        # specifically — not an incidental earlier gate (e.g. the efficacy
        # breadcrumb gate) that happens to share the same output shape.
        assert "Stop-authorization gate" in out["refused"], (
            f"expected the checkpoint stop-authorization gate to refuse; got {out!r}"
        )
        assert out.get("attended") is True, (
            f"the checkpoint-gate refusal must echo attended=True; got {out!r}"
        )
        # The marker file must still exist on disk (the whole point).
        marker_file = state_dir / "lazy-run-marker.json"
        assert marker_file.exists(), (
            "marker file must remain on disk after a refused --run-end --reason checkpoint"
        )




def test_p7_run_end_checkpoint_attended_with_auth_succeeds():
    """--run-end --reason checkpoint against an attended marker WITH
    --operator-authorized must SUCCEED: exit 0, run_marker_deleted=True.

    RED until --operator-authorized is wired into the run-end handler.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-ckpt-auth"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root.
        repo_dir = Path(td) / "p7-ckpt-auth-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0, f"run-start failed: {r_start.stderr}"

        # --operator-authorized bypasses the attended gate.
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "implement Phase 3",
                 "--operator-authorized"])
        assert r.returncode == 0, (
            f"run-end checkpoint with --operator-authorized must exit 0; "
            f"got {r.returncode}; stdout={r.stdout!r}; stderr={r.stderr!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is True, (
            f"authorized run-end must delete the marker; got {out!r}"
        )
        # Marker file must be gone.
        assert not (state_dir / "lazy-run-marker.json").exists(), (
            "marker file must be deleted after an authorized --run-end --reason checkpoint"
        )




def test_p7_run_end_checkpoint_unattended_no_auth_allowed():
    """--run-end --reason checkpoint against an UNATTENDED marker WITHOUT
    --operator-authorized must SUCCEED: the sanctioned overnight-pause path.

    RED until --unattended is wired into --run-start.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-ckpt-unattended"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root.
        repo_dir = Path(td) / "p7-ckpt-unattended-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        # --run-start --unattended → attended=False marker.
        r_start = run(["--run-start", "--max-cycles", "10", "--unattended"])
        assert r_start.returncode == 0, f"run-start --unattended failed: {r_start.stderr}"
        start_out = json.loads(r_start.stdout)
        assert start_out.get("attended") is False, (
            f"--unattended must write attended=False; got {start_out.get('attended')!r}"
        )

        # --run-end --reason checkpoint on an unattended marker: allowed without auth.
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "checkpoint",
                 "--next-route", "overnight resume route"])
        assert r.returncode == 0, (
            f"run-end checkpoint on UNATTENDED marker must succeed without auth; "
            f"got {r.returncode}; stdout={r.stdout!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is True, (
            f"unattended checkpoint must delete the marker; got {out!r}"
        )




def test_p7_run_end_terminal_sanctioned_reason_allowed():
    """--run-end --reason terminal --terminal-reason all-features-complete is
    a sanctioned stop and must SUCCEED: exit 0, run_marker_deleted=True.

    RED until --terminal-reason is wired into the run-end handler.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-term-sanctioned"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root.
        repo_dir = Path(td) / "p7-term-sanctioned-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "terminal",
                 "--terminal-reason", "all-features-complete"])
        assert r.returncode == 0, (
            f"sanctioned terminal reason must exit 0; got {r.returncode}; "
            f"stdout={r.stdout!r}; stderr={r.stderr!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is True, f"sanctioned terminal must delete marker; {out!r}"




def test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth():
    """--run-end --reason terminal --terminal-reason bogus-reason WITHOUT
    --operator-authorized must REFUSE: exit 1, run_marker_deleted=False,
    marker still on disk.

    RED until the sanctioned-terminal-set validation is implemented.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-term-bogus"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root.
        repo_dir = Path(td) / "p7-term-bogus-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

        # adhoc-run-end-tests-leak-real-repo-state: seed the efficacy-flush
        # breadcrumb so this --run-end reaches the TERMINAL-REASON gate under
        # test, not the earlier-positioned efficacy gate (a distinct refusal
        # that happened to satisfy the same loose output shape).
        _seed_efficacy_breadcrumb(state_dir)

        r = run(["--run-end", "--reason", "terminal",
                 "--terminal-reason", "bogus-reason"])
        assert r.returncode == 1, (
            f"non-sanctioned terminal reason without auth must exit 1; "
            f"got {r.returncode}; stdout={r.stdout!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is False, (
            f"refused terminal run-end must NOT delete the marker; got {out!r}"
        )
        assert "refused" in out, f"refused output must contain 'refused' key; got {out!r}"
        # Pin the refusal to the TERMINAL-REASON gate specifically.
        assert "Stop-authorization gate" in out["refused"], (
            f"expected the terminal-reason stop-authorization gate to refuse; got {out!r}"
        )
        assert "bogus-reason" in out["refused"], (
            f"refusal must name the non-sanctioned reason; got {out!r}"
        )
        # Marker must still exist.
        assert (state_dir / "lazy-run-marker.json").exists(), (
            "marker must remain on disk after non-sanctioned terminal refusal"
        )




def test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed():
    """--run-end --reason terminal --terminal-reason bogus-reason WITH
    --operator-authorized must SUCCEED: exit 0, run_marker_deleted=True.
    Operator authorization overrides the sanctioned-set check.

    RED until --operator-authorized bypasses the terminal-reason gate.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-term-bogus-auth"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root.
        repo_dir = Path(td) / "p7-term-bogus-auth-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "terminal",
                 "--terminal-reason", "bogus-reason",
                 "--operator-authorized"])
        assert r.returncode == 0, (
            f"--operator-authorized must bypass terminal-reason gate; "
            f"got {r.returncode}; stdout={r.stdout!r}; stderr={r.stderr!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is True, (
            f"authorized non-sanctioned terminal must delete marker; got {out!r}"
        )




def test_p7_run_end_terminal_no_terminal_reason_adds_deprecation():
    """--run-end --reason terminal WITHOUT --terminal-reason (legacy form)
    must SUCCEED with a 'deprecation' note in the output — backward-compatible
    but warns the caller to supply --terminal-reason going forward.

    RED until the deprecation note is added to the terminal path.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-term-legacy"
        state_dir.mkdir()
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root.
        repo_dir = Path(td) / "p7-term-legacy-repo"
        repo_dir.mkdir()
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

        # Legacy: --run-end without --terminal-reason → still exits 0 but adds deprecation.
        _seed_efficacy_breadcrumb(state_dir)
        r = run(["--run-end", "--reason", "terminal"])
        assert r.returncode == 0, (
            f"legacy terminal run-end (no --terminal-reason) must still exit 0; "
            f"got {r.returncode}; stdout={r.stdout!r}; stderr={r.stderr!r}"
        )
        out = json.loads(r.stdout)
        assert out.get("run_marker_deleted") is True, f"legacy terminal must delete marker; {out!r}"
        assert "deprecation" in out, (
            f"legacy terminal (no --terminal-reason) must include 'deprecation' key; got {out!r}"
        )




def test_p7_emit_dispatch_includes_dispatch_prompt_ref():
    """--emit-dispatch with an active marker must include 'dispatch_prompt_ref'
    (a '@@lazy-ref nonce=<hex>' token) in the output JSON alongside
    'dispatch_prompt'.  When no marker is present the field must be null.

    RED until dispatch_prompt_ref is wired into the emit-dispatch output.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "p7-emit-dispatch"
        state_dir.mkdir()
        # Build a minimal fixture repo so emit-dispatch can find a resolution prompt.
        repo_dir = state_dir / "fixture-repo"
        (repo_dir / "docs" / "features").mkdir(parents=True)
        (repo_dir / "docs" / "features" / "queue.json").write_text(
            json.dumps({"queue": [{"id": "feat-1", "name": "Test Feature",
                                   "priority": 1, "cloud": False}]})
        )
        feature_dir = repo_dir / "docs" / "features" / "feat-1"
        feature_dir.mkdir()
        (feature_dir / "SPEC.md").write_text("# Spec\n## Status\nIn-progress\n")
        (feature_dir / "PHASES.md").write_text("### Phase 1\n\n- [ ] Do the thing\n")
        blocked_dir = feature_dir / "mcp-tests"
        blocked_dir.mkdir()
        # Write a BLOCKED.md with resolution context for apply-resolution.
        (feature_dir / "BLOCKED.md").write_text(
            "# Blocked\n**Blocker:** test blocker\n**Resolution:** fix it\n"
        )

        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        # 1. No marker → dispatch_prompt_ref must be null.
        r_no_marker = run([
            "--emit-dispatch", "apply-resolution",
            "--repo-root", str(repo_dir),
            "--context", "item_id=feat-1",
        ])
        # May succeed or refuse (blocked missing context) — the key point is
        # dispatch_prompt_ref field presence when output is valid JSON.
        if r_no_marker.returncode == 0 and r_no_marker.stdout.strip():
            try:
                out_nm = json.loads(r_no_marker.stdout)
                if "dispatch_prompt" in out_nm and out_nm.get("dispatch_prompt") is not None:
                    assert "dispatch_prompt_ref" in out_nm, (
                        "dispatch_prompt_ref key must be present in emit-dispatch output "
                        f"(no marker → null); got {out_nm!r}"
                    )
                    assert out_nm["dispatch_prompt_ref"] is None, (
                        f"dispatch_prompt_ref must be null when no marker; "
                        f"got {out_nm['dispatch_prompt_ref']!r}"
                    )
            except json.JSONDecodeError:
                pass  # Refusal may not be valid JSON in the no-marker path

        # 2. With active marker → dispatch_prompt_ref must be a @@lazy-ref token.
        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0, f"run-start failed: {r_start.stderr}"

        r_with_marker = run([
            "--emit-dispatch", "apply-resolution",
            "--repo-root", str(repo_dir),
            "--context", "item_id=feat-1",
        ])
        # The emit may refuse if the template requires context we haven't provided;
        # test only when it succeeds and produces a dispatch_prompt.
        if r_with_marker.returncode == 0 and r_with_marker.stdout.strip():
            try:
                out_m = json.loads(r_with_marker.stdout)
            except json.JSONDecodeError:
                out_m = {}
            if out_m.get("dispatch_prompt") is not None:
                assert "dispatch_prompt_ref" in out_m, (
                    "dispatch_prompt_ref key must be present in emit-dispatch output "
                    f"(with marker); got {out_m!r}"
                )
                ref = out_m.get("dispatch_prompt_ref")
                assert ref is not None, (
                    f"dispatch_prompt_ref must be a @@lazy-ref token with active marker; "
                    f"got None; full output: {out_m!r}"
                )
                assert isinstance(ref, str) and ref.startswith("@@lazy-ref nonce="), (
                    f"dispatch_prompt_ref must start with '@@lazy-ref nonce='; "
                    f"got {ref!r}"
                )




def test_per_repo_marker_independence_when_unset():
    """Two active repos each hold an independent run marker — neither read sees
    the other's marker."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        prior = _mrcr_with_temp_home(td)
        try:
            lazy_core.set_active_repo_root("/tmp/repoA")
            lazy_core.write_run_marker(pipeline="feature", cloud=False,
                                       repo_root="/tmp/repoA", max_cycles=20)
            lazy_core.set_active_repo_root("/tmp/repoB")
            assert lazy_core.read_run_marker() is None, "repoB sees no marker"
            lazy_core.write_run_marker(pipeline="bug", cloud=False,
                                       repo_root="/tmp/repoB", max_cycles=5)
            mb = lazy_core.read_run_marker()
            assert mb is not None and mb["pipeline"] == "bug", mb
            lazy_core.set_active_repo_root("/tmp/repoA")
            ma = lazy_core.read_run_marker()
            assert ma is not None and ma["pipeline"] == "feature", ma
            # Ending repoA's run must not touch repoB's marker.
            lazy_core.delete_run_marker()
            assert lazy_core.read_run_marker() is None, "repoA marker cleared"
            lazy_core.set_active_repo_root("/tmp/repoB")
            assert lazy_core.read_run_marker() is not None, "repoB marker intact"
        finally:
            _mrcr_restore_env(prior)




def test_marker_present_cli_absent_then_present_and_readonly():
    """lazy-state.py --marker-present exits 1 when no marker, 0 when a live
    marker is present (under a hermetic LAZY_STATE_DIR), and is READ-ONLY — the
    absent probe must NOT create the state dir."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        # Point LAZY_STATE_DIR at a path that does NOT yet exist so the read-only
        # contract (no dir creation) is observable.
        state_dir = Path(td) / "absent-state"
        # adhoc-run-end-tests-leak-real-repo-state: hermetic fixture repo root
        # — never the default os.getcwd() (the real claude-config checkout).
        repo_dir = Path(td) / "absent-state-repo"
        repo_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state), "--repo-root", str(repo_dir)] + args,
                capture_output=True, text=True, env=env,
            )

        # No marker → exit 1, AND the read-only probe must not create the dir.
        r_absent = run(["--marker-present"])
        assert r_absent.returncode == 1, (
            f"--marker-present must exit 1 when absent, got {r_absent.returncode}: "
            f"{r_absent.stdout}{r_absent.stderr}"
        )
        assert not state_dir.exists(), (
            "--marker-present must be read-only — it must not create the state dir"
        )

        # Start a run (this creates the marker), then the probe → exit 0.
        assert run(["--run-start", "--max-cycles", "5"]).returncode == 0
        r_present = run(["--marker-present"])
        assert r_present.returncode == 0, (
            f"--marker-present must exit 0 when a live marker is present, got "
            f"{r_present.returncode}: {r_present.stdout}{r_present.stderr}"
        )

        # Clear it → probe returns to exit 1.
        _seed_efficacy_breadcrumb(state_dir)
        assert run(["--run-end"]).returncode == 0
        assert run(["--marker-present"]).returncode == 1, (
            "--marker-present must exit 1 after the marker is cleared"
        )




def _run_marker_status_cli_never_throws(script_name: str):
    """Shared body for the --marker-status parity fixtures (lazy-state.py /
    bug-state.py): absent marker, live marker, and corrupt marker JSON all
    print {"present": bool} and exit 0 — never a traceback, never nonzero."""
    script = _SCRIPTS_DIR / script_name
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "status-state"
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(script)] + args,
                capture_output=True, text=True, env=env,
            )

        # Absent (no state dir at all yet) → present: false, exit 0, read-only.
        r_absent = run(["--marker-status"])
        assert r_absent.returncode == 0, (
            f"--marker-status must always exit 0, got {r_absent.returncode}: "
            f"{r_absent.stdout}{r_absent.stderr}"
        )
        assert json.loads(r_absent.stdout) == {"present": False}, r_absent.stdout
        assert not state_dir.exists(), (
            "--marker-status must be read-only — it must not create the state dir"
        )

        # Live marker → present: true, exit 0.
        assert run(["--run-start", "--max-cycles", "5"]).returncode == 0
        r_present = run(["--marker-status"])
        assert r_present.returncode == 0
        assert json.loads(r_present.stdout) == {"present": True}, r_present.stdout

        # Corrupt marker JSON → present: false, exit 0, never a traceback.
        marker_path = state_dir / "lazy-run-marker.json"
        marker_path.write_text("{not valid json", encoding="utf-8")
        r_corrupt = run(["--marker-status"])
        assert r_corrupt.returncode == 0, (
            f"corrupt marker must still exit 0, got {r_corrupt.returncode}: "
            f"{r_corrupt.stdout}{r_corrupt.stderr}"
        )
        assert json.loads(r_corrupt.stdout) == {"present": False}, r_corrupt.stdout




def test_marker_status_cli_never_throws_lazy_state():
    """lazy-state.py --marker-status: absent/present/corrupt all resolve to
    {"present": bool} and exit 0 (cycle-prompt-environment-dialect Phase 1)."""
    _guard()
    _run_marker_status_cli_never_throws("lazy-state.py")




def test_marker_status_cli_never_throws_bug_state():
    """bug-state.py --marker-status: parity mirror of the lazy-state.py
    fixture (the marker is shared between the feature and bug pipelines)."""
    _guard()
    _run_marker_status_cli_never_throws("bug-state.py")




def test_cross_script_same_repo_refuses_keyed_dir_unset():
    """WU-3.1 cross-script: with LAZY_STATE_DIR UNSET and a temp HOME, a bug
    --run-start in repo A keys its marker into A's subdir, so a feature
    --run-start in the SAME repo A is REFUSED (different pipeline clobber, exit
    3) — but a feature --run-start in a DIFFERENT repo B succeeds (different
    repo_key → different subdir → no clobber).  This proves bug-state.py and
    lazy-state.py share the per-repo keyed state dir via the common lazy_core
    chokepoint.

    Driven via subprocess (not in-process) so each script's main() binds its own
    active repo from --repo-root and resolves the keyed dir independently — the
    real cross-process isolation that production exercises.
    """
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    bug_state = _SCRIPTS_DIR / "bug-state.py"
    with tempfile.TemporaryDirectory() as td:
        # Two distinct real directories → two distinct repo_keys.  Using real
        # dirs keeps os.path.realpath (inside repo_key) deterministic on every OS.
        repo_a = Path(td) / "repoA"
        repo_b = Path(td) / "repoB"
        repo_a.mkdir()
        repo_b.mkdir()
        home = Path(td) / "home"
        home.mkdir()

        # Hermetic env: LAZY_STATE_DIR UNSET (so the keyed-dir path is exercised)
        # + HOME/USERPROFILE pointed at a throwaway dir (so ~/.claude/state lands
        # under td, never the real machine state).
        env = dict(_os_env.environ)
        env.pop("LAZY_STATE_DIR", None)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)

        def run(script, scriptargs):
            return subprocess.run(
                [sys.executable, str(script)] + scriptargs,
                capture_output=True, text=True, env=env,
            )

        # 1) Bug run-start in repo A → writes the marker into A's keyed subdir.
        r_bug = run(bug_state, ["--run-start", "--repo-root", str(repo_a),
                                "--max-cycles", "5"])
        assert r_bug.returncode == 0, (
            f"bug --run-start in repo A must succeed, got {r_bug.returncode}: "
            f"{r_bug.stdout}{r_bug.stderr}"
        )

        # 2) Feature run-start in the SAME repo A → REFUSED (exit 3) because a
        #    live different-pipeline ("bug") marker occupies A's keyed subdir.
        r_same = run(lazy_state, ["--run-start", "--repo-root", str(repo_a),
                                  "--max-cycles", "5"])
        assert r_same.returncode == 3, (
            f"feature --run-start in the SAME repo must be REFUSED (exit 3), got "
            f"{r_same.returncode}: {r_same.stdout}{r_same.stderr}"
        )
        assert "REFUSED" in r_same.stderr, (
            f"refusal must name the clobber on stderr, got: {r_same.stderr!r}"
        )

        # 3) Feature run-start in a DIFFERENT repo B → SUCCEEDS (different
        #    repo_key → different subdir → no clobber of A's marker).
        r_diff = run(lazy_state, ["--run-start", "--repo-root", str(repo_b),
                                  "--max-cycles", "5"])
        assert r_diff.returncode == 0, (
            f"feature --run-start in a DIFFERENT repo must succeed, got "
            f"{r_diff.returncode}: {r_diff.stdout}{r_diff.stderr}"
        )




# ---------------------------------------------------------------------------
# Phase 2 (lazy-cycle-containment C1) — cycle-subagent marker
#
# The cycle marker (lazy-cycle-active.json) is the sibling of the run marker.
# Hermetic via LAZY_STATE_DIR temp dirs (same discipline as Phase 1/7).
# ---------------------------------------------------------------------------

_CYCLE_MARKER_FILENAME = "lazy-cycle-active.json"




def test_cycle_marker_set_writes_all_fields():
    """write_cycle_marker → file appears with feature_id/nonce/kind/commit_tally
    and a parseable started_at; default kind is 'real'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            marker = lazy_core.write_cycle_marker(feature_id="x", nonce="abc")
            path = Path(td) / _CYCLE_MARKER_FILENAME
            assert path.exists(), "cycle marker file must appear after write"
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            assert on_disk["feature_id"] == "x", on_disk
            assert on_disk["nonce"] == "abc", on_disk
            assert on_disk["kind"] == "real", on_disk
            assert on_disk["commit_tally"] == 0, on_disk
            assert "session_id" in on_disk, on_disk
            # started_at parses as the ISO-8601 UTC 'Z' format we write.
            import datetime as _dt
            _dt.datetime.strptime(on_disk["started_at"], "%Y-%m-%dT%H:%M:%SZ")
            # The returned dict mirrors what was written.
            assert marker["feature_id"] == "x"
            assert marker["nonce"] == "abc"
        finally:
            _clear_state_dir()




def test_cycle_marker_read_returns_dict_then_none_after_clear():
    """read_cycle_marker returns the parsed dict when present and None after a
    clear; the file is gone after clear."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_cycle_marker(feature_id="y", nonce="def")
            got = lazy_core.read_cycle_marker()
            assert got is not None and got["feature_id"] == "y", got
            lazy_core.clear_cycle_marker()
            assert not (Path(td) / _CYCLE_MARKER_FILENAME).exists(), "file gone after clear"
            assert lazy_core.read_cycle_marker() is None, "read returns None after clear"
        finally:
            _clear_state_dir()




def test_cycle_marker_read_none_when_absent():
    """read_cycle_marker returns None when no marker exists (and never creates
    the state dir as a side effect)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"  # does NOT exist
        _set_state_dir(state_dir)
        try:
            assert lazy_core.read_cycle_marker() is None
            assert not state_dir.exists(), "read path must not create the state dir"
        finally:
            _clear_state_dir()




def test_cycle_marker_clear_idempotent():
    """A clear with no marker present is a no-op: returns False, raises nothing.
    A second clear after a real clear is also a no-op."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Clear with nothing present → no-op, no raise.
            assert lazy_core.clear_cycle_marker() is False
            lazy_core.write_cycle_marker(feature_id="z", nonce="0")
            assert lazy_core.clear_cycle_marker() is True, "first clear deletes"
            assert lazy_core.clear_cycle_marker() is False, "re-clear is a no-op"
        finally:
            _clear_state_dir()




def test_cycle_marker_staleness_overwrites_and_logs():
    """write_cycle_marker over an existing marker OVERWRITES (new feature_id/nonce
    win) and logs the overwrite event (orchestrator is single-threaded)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.clear_diagnostics()
            lazy_core.write_cycle_marker(feature_id="first", nonce="111")
            lazy_core.write_cycle_marker(feature_id="second", nonce="222")
            got = lazy_core.read_cycle_marker()
            assert got["feature_id"] == "second", got
            assert got["nonce"] == "222", got
            # The overwrite logged a breadcrumb to the shared diagnostics list.
            diags = "\n".join(lazy_core._DIAGNOSTICS)
            assert "overwr" in diags.lower() or "stale" in diags.lower(), (
                f"expected an overwrite/staleness breadcrumb, got: {diags!r}"
            )
        finally:
            _clear_state_dir()




def test_cycle_marker_kind_meta_round_trips():
    """kind='meta' round-trips through write → read."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_cycle_marker(feature_id="m", nonce="m1", kind="meta")
            got = lazy_core.read_cycle_marker()
            assert got["kind"] == "meta", got
        finally:
            _clear_state_dir()




def test_cycle_marker_corrupt_file_read_returns_none():
    """A corrupt/unparseable cycle marker reads as None (never bricks a caller)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            path = Path(td) / _CYCLE_MARKER_FILENAME
            path.write_text("{ not json", encoding="utf-8")
            assert lazy_core.read_cycle_marker() is None
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# hardening-blind-to-process-friction Phase 2 — process-friction detector
# → deny ledger.  --cycle-begin snapshots run identity + HEAD; --cycle-end
# checks the two D1 signals (bracket-break, unexpected-commits) and on either
# appends a kind: process-friction entry to the SAME lazy-deny-ledger.jsonl so
# pending_hardening()/--run-end consume it identically to a guard deny.
# ---------------------------------------------------------------------------


def test_cycle_marker_run_identity_head_fields_additive():
    """WU-1: write_cycle_marker persists additive run_started_at + begin_head_sha
    fields when passed; existing 6-field callers (omitting them) still write a
    valid marker with those fields defaulting to None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Additive fields supplied.
            marker = lazy_core.write_cycle_marker(
                feature_id="f", nonce="n1",
                run_started_at="2026-06-15T00:00:00Z",
                begin_head_sha="deadbeefcafe",
                sub_skill="execute-plan",
            )
            assert marker["run_started_at"] == "2026-06-15T00:00:00Z", marker
            assert marker["begin_head_sha"] == "deadbeefcafe", marker
            assert marker["sub_skill"] == "execute-plan", marker
            on_disk = json.loads(
                (Path(td) / _CYCLE_MARKER_FILENAME).read_text(encoding="utf-8")
            )
            assert on_disk["run_started_at"] == "2026-06-15T00:00:00Z", on_disk
            assert on_disk["begin_head_sha"] == "deadbeefcafe", on_disk
            assert on_disk["sub_skill"] == "execute-plan", on_disk
            # Legacy 6-field caller: the additive fields default to None,
            # everything else unchanged.
            legacy = lazy_core.write_cycle_marker(feature_id="g", nonce="n2")
            assert legacy["run_started_at"] is None, legacy
            assert legacy["begin_head_sha"] is None, legacy
            assert legacy["sub_skill"] is None, legacy
            assert legacy["feature_id"] == "g" and legacy["commit_tally"] == 0
        finally:
            _clear_state_dir()




def test_detect_friction_clean_bracket_returns_none():
    """WU-2: a clean bracket — run identity unchanged, HEAD within budget —
    returns None (no false positive)."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-15T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-15T00:00:00Z",
        current_head_sha="aaaa1111",
        sub_skill="execute-plan",
        commits_since=0,
    )
    assert got is None, got




def test_detect_friction_torn_bracket_run_identity_changed():
    """WU-2: the run identity present at begin differs at end (a dispatched cycle
    ran --run-end / a new run started) → descriptor with reason cycle-bracket-break."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-15T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-15T09:99:99Z",  # changed
        current_head_sha="aaaa1111",
        sub_skill="execute-plan",
        commits_since=0,
    )
    assert got is not None, "changed run identity must trip"
    assert got["reason"] == "cycle-bracket-break", got




def test_detect_friction_torn_bracket_run_marker_now_absent():
    """WU-2: the run marker was present at begin (non-null run_started_at) but is
    absent at end (current is None) → cycle-bracket-break."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-15T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at=None,  # run marker gone
        current_head_sha="aaaa1111",
        sub_skill="execute-plan",
        commits_since=0,
    )
    assert got is not None and got["reason"] == "cycle-bracket-break", got




def test_detect_friction_over_budget_commits():
    """WU-2: HEAD advanced beyond the conservative per-sub_skill budget → descriptor
    with reason unexpected-commits."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-15T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-15T00:00:00Z",  # identity intact
        current_head_sha="bbbb2222",
        sub_skill="execute-plan",
        commits_since=5,  # well beyond the 1-commit budget
    )
    assert got is not None and got["reason"] == "unexpected-commits", got
    assert "5" in got.get("detail", ""), got




def test_detect_friction_branch_divergence():
    """Harden Round 43 (2026-06-29): a cycle that ends on a branch OTHER than the
    run's work_branch self-announces as kind: process-friction reason
    branch-divergence. Motivating incident: an mcp-test cycle created
    fix/fill-capture-ordering-mcp-visibility, committed there, and reported success
    WITHOUT the R10-mandated STOP; the divergence was caught only by manual
    orchestrator ff-merge reconciliation. The signal makes it routed, not silent."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-29T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }
    # (1) wrong branch → trips with reason branch-divergence; detail names both branches.
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-29T00:00:00Z",  # identity intact
        current_head_sha="bbbb2222",
        sub_skill="mcp-test",
        commits_since=1,  # within budget — divergence is the ONLY signal
        current_branch="fix/fill-capture-ordering-mcp-visibility",
        expected_work_branch="main",
    )
    assert got is not None and got["reason"] == "branch-divergence", got
    assert "fix/fill-capture-ordering-mcp-visibility" in got.get("detail", ""), got
    assert "main" in got.get("detail", ""), got

    # (2) on the work branch → no false positive.
    assert lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-29T00:00:00Z",
        current_head_sha="bbbb2222",
        sub_skill="mcp-test",
        commits_since=1,
        current_branch="main",
        expected_work_branch="main",
    ) is None

    # (3) degraded inputs (detached HEAD / unknown / legacy marker w/o work_branch)
    #     → signal disabled, never a false positive.
    for cb, ewb in (("HEAD", "main"), (None, "main"), ("feat-x", None), (None, None)):
        assert lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-29T00:00:00Z",
            current_head_sha="bbbb2222",
            sub_skill="mcp-test",
            commits_since=1,
            current_branch=cb,
            expected_work_branch=ewb,
        ) is None, (cb, ewb)

    # (4) a META cycle on a wrong branch STILL trips — branch-divergence is NOT
    #     meta-exempt (a wrong branch is always integrity-breaking; the meta
    #     exemption only covers the unbounded-commits signal).
    meta_marker = {**marker, "kind": "meta"}
    meta_div = lazy_core.detect_cycle_bracket_friction(
        meta_marker,
        current_run_started_at="2026-06-29T00:00:00Z",
        current_head_sha="bbbb2222",
        sub_skill=None,
        commits_since=9,  # would be exempt for unexpected-commits, irrelevant here
        current_branch="stray-meta-branch",
        expected_work_branch="main",
    )
    assert meta_div is not None and meta_div["reason"] == "branch-divergence", meta_div




def test_current_branch_snapshot_degrades_to_none():
    """current_branch_snapshot returns None (not the prompt-token fallback string
    "the current branch") on a non-git / degraded read, so the friction equality
    comparison never false-trips. Symbol-presence + non-crash contract."""
    _guard()
    assert hasattr(lazy_core, "current_branch_snapshot")
    import tempfile, pathlib
    # A fresh empty temp dir is not a git tree → None (never raises, never a branch).
    with tempfile.TemporaryDirectory() as d:
        got = lazy_core.current_branch_snapshot(pathlib.Path(d))
    assert got is None, got




def test_detect_friction_mark_complete_meta_cycle_multi_commit_within_budget():
    """Hardening 2026-06-16 recurrence: a `__mark_complete__` completion / meta cycle
    legitimately commits MORE THAN ONCE (the `--apply-pseudo` receipt+flip plus the
    Gate-1 corrective-coverage scenario commit). Round 15 fixed the `execute-plan`
    sibling of this defect but did NOT enumerate the pseudo-skill cycles, so a
    2-commit `__mark_complete__` cycle (budget defaulted to 1) re-tripped
    `unexpected-commits` (begin_head_sha 0a0e928c6711 / 730a4df88d17). With the
    pseudo-skill budget row (__mark_complete__/__mark_fixed__: 3) the legitimate
    multi-commit completion cycle no longer false-positives."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-16T00:00:00Z",
        "begin_head_sha": "0a0e928c6711",
    }
    for ss in ("__mark_complete__", "__mark_fixed__"):
        got = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-16T00:00:00Z",  # identity intact
            current_head_sha="730a4df88d17",
            sub_skill=ss,
            commits_since=2,  # receipt+flip + corrective-coverage commit
        )
        assert got is None, (ss, got)
    # A genuine runaway (>3) on the same pseudo-skill STILL trips — no gate weakened.
    runaway = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-16T00:00:00Z",
        current_head_sha="730a4df88d17",
        sub_skill="__mark_complete__",
        commits_since=7,
    )
    assert runaway is not None and runaway["reason"] == "unexpected-commits", runaway




def test_detect_friction_mcp_test_cycle_multi_commit_within_budget():
    """Hardening 2026-06-16 recurrence (mcp-audio-quality-observability) + 2026-06-26
    magnitude recurrence (pattern-abstractions): the Step-9 `/mcp-test` validation
    cycle legitimately commits MORE THAN ONCE — the engine's audited mechanics-only
    self-heal (a `heals[]` scenario/tool-methods edit) lands separately from the
    terminal sentinel + PHASES reconcile. Round 23 added `mcp-test` to the
    multi-commit set (uniform ceiling 3), closing the MEMBERSHIP gap. But the real
    worst-case cadence exceeds 3: the `pattern-abstractions` cycle
    (`begin_head_sha=0dd654ae39ce`, budget=3, HEAD advanced 4) committed FOUR
    legitimate mcp-test-owned units — self-heal (`4b9b3ddaa`) + a 2-part PHASES
    reconcile (`0db5974e4` sub-phase RV ticks, `7b119b512` top-level Complete) +
    an engine-VALIDATED.md schema correction (`d744204da`). The
    `_MULTI_COMMIT_CEILING_OVERRIDE["mcp-test"] = 4` row closes that MAGNITUDE gap
    while leaving every OTHER multi-commit skill at the uniform ceiling of 3. A
    genuine mcp-test runaway still trips — no gate weakened.

    adhoc-derive-multi-commit-budget-from-dispatch-sites (2026-07-12): membership is
    now DERIVED from a repo-scoped `commit-cadence: multi` SKILL.md frontmatter flag
    (mirroring the real `repos/algobooth/.claude/skills/mcp-test/SKILL.md`), not the
    retired `_MULTI_COMMIT_DISPATCH_SKILLS` frozenset — so this test builds a hermetic
    repo_root fixture and threads it through. adhoc-align-cycle-commit-count-with-
    budget-population (2026-07-12) then adds the shared `_CYCLE_COMMIT_NOISE_ALLOWANCE`
    cushion on top of every registry-derived ceiling — mcp-test's effective budget is
    now `4 + 1 = 5`; `spec`'s is `3 + 1 = 4`."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        skill_dir = repo / ".claude" / "skills" / "mcp-test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: mcp-test\ncommit-cadence: multi\n---\n# MCP Test\n",
            encoding="utf-8",
        )
        marker = {
            "feature_id": "mcp-audio-quality-observability", "nonce": "n",
            "run_started_at": "2026-06-16T00:00:00Z",
            "begin_head_sha": "a28085bb938e",
        }
        # Round-23 2-commit cadence (self-heal + sentinel/PHASES-reconcile) — clean.
        got = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-16T00:00:00Z",  # identity intact
            current_head_sha="730a4df88d17",
            sub_skill="mcp-test",
            commits_since=2,  # self-heal commit + sentinel/PHASES-reconcile commit
            repo_root=repo,
        )
        assert got is None, got
        # 2026-06-26 pattern-abstractions 4-commit cadence (self-heal + 2-part PHASES
        # reconcile + VALIDATED.md correction) — within the cushioned ceiling of 5, clean.
        pa_marker = {
            "feature_id": "pattern-abstractions", "nonce": "n",
            "run_started_at": "2026-06-26T00:00:00Z",
            "begin_head_sha": "0dd654ae39ce",
        }
        pa_got = lazy_core.detect_cycle_bracket_friction(
            pa_marker,
            current_run_started_at="2026-06-26T00:00:00Z",  # identity intact
            current_head_sha="d744204da000",
            sub_skill="mcp-test",
            commits_since=4,
            repo_root=repo,
        )
        assert pa_got is None, pa_got
        # A genuine runaway STILL trips — no gate weakened.
        runaway = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-16T00:00:00Z",
            current_head_sha="730a4df88d17",
            sub_skill="mcp-test",
            commits_since=7,
            repo_root=repo,
        )
        assert runaway is not None and runaway["reason"] == "unexpected-commits", runaway
        # Without repo_root, mcp-test's repo-scoped flag cannot be resolved — it falls
        # to the single-commit default (fail-closed, never a crash, never a silent
        # escalation) — proving the derivation genuinely reads the frontmatter, not a
        # hardcoded name.
        no_repo_root = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-16T00:00:00Z",
            current_head_sha="730a4df88d17",
            sub_skill="mcp-test",
            commits_since=3,
        )
        assert (
            no_repo_root is not None
            and no_repo_root["reason"] == "unexpected-commits"
        ), no_repo_root
    # The per-skill override is mcp-test-ONLY: another multi-commit member (spec, a
    # real user-level skill resolved module-relatively with no repo_root needed) at
    # 5 commits STILL trips against its cushioned ceiling of 4 — the override does
    # not leak the higher ceiling to other skills.
    marker = {
        "feature_id": "mcp-audio-quality-observability", "nonce": "n",
        "run_started_at": "2026-06-16T00:00:00Z",
        "begin_head_sha": "a28085bb938e",
    }
    other_skill_5 = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-16T00:00:00Z",
        current_head_sha="730a4df88d17",
        sub_skill="spec",
        commits_since=5,
    )
    assert (
        other_skill_5 is not None
        and other_skill_5["reason"] == "unexpected-commits"
    ), other_skill_5




def test_detect_friction_planning_cycle_multi_commit_within_budget():
    """Hardening 2026-06-22 recurrence (d2-sample-import-ui): the planning dispatch
    (consolidated Step-6 /plan-feature, or the direct Step-7a /write-plan) legitimately
    commits MORE THAN ONCE — /plan-feature runs /spec-phases (commits PHASES.md) THEN
    /write-plan back-to-back, and /write-plan may emit a multi-part plan series
    (`-part-1.md`, `-part-2.md`, … per the 8-WU partition cap) committing once per part.
    With the planning skills absent from the budget table they defaulted to 1, so a
    normal 2-commit planning cycle re-tripped `unexpected-commits`
    (`begin_head_sha=08d33d580cfe, sub_skill='write-plan', budget=1`, HEAD advanced 2
    commits). This is the SAME missing-row defect class Round 15 fixed for `execute-plan`,
    Rounds 16/17 for the pseudo-skills, and the `mcp-test` row; the write-plan/plan-feature/
    plan-bug:3 rows close it. A genuine runaway (>3) still trips — no gate weakened."""
    _guard()
    marker = {
        "feature_id": "d2-sample-import-ui", "nonce": "n",
        "run_started_at": "2026-06-22T00:00:00Z",
        "begin_head_sha": "08d33d580cfe",
    }
    for ss in ("write-plan", "plan-feature", "plan-bug"):
        got = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-22T00:00:00Z",  # identity intact
            current_head_sha="730a4df88d17",
            sub_skill=ss,
            commits_since=2,  # spec-phases PHASES.md + write-plan plan-part commit
        )
        assert got is None, (ss, got)
    # A genuine runaway (>3) on the same sub_skill STILL trips — no gate weakened.
    runaway = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-22T00:00:00Z",
        current_head_sha="730a4df88d17",
        sub_skill="write-plan",
        commits_since=7,
    )
    assert runaway is not None and runaway["reason"] == "unexpected-commits", runaway




def test_detect_friction_spec_cycle_multi_commit_within_budget():
    """Hardening 2026-06-25 recurrence (key-detection): the /spec authoring dispatch
    legitimately commits MORE THAN ONCE — /spec is multi-phase, and a STUB feature's
    Phase 1 commits the baseline-lock SPEC over the auto-generated stub AND then retires
    the stub markers / advances to needs-research (two commits in one dispatched cycle:
    `9def1bfab /spec Phase 1 — lock in baseline over auto-generated stub` + `a96d51df4
    retire stub markers — baseline locked, advance to needs-research`). With `spec`
    absent from `_MULTI_COMMIT_DISPATCH_SKILLS` it defaulted to budget 1, so a normal
    2-commit spec cycle tripped `unexpected-commits` (`begin_head_sha=641e96163faa,
    sub_skill='spec', budget=1`, HEAD advanced 2 commits). This is the SAME missing-row
    defect class Round 15 fixed for `execute-plan`, Rounds 16/17 for the pseudo-skills,
    the `mcp-test` row, and Round 31's planning rows; the spec/spec-bug membership closes
    it. /spec-bug is the bug-pipeline investigation analog, covered alongside per the
    Round 31 plan-feature/plan-bug precedent. A genuine runaway (>3) still trips."""
    _guard()
    marker = {
        "feature_id": "key-detection", "nonce": "n",
        "run_started_at": "2026-06-25T00:00:00Z",
        "begin_head_sha": "641e96163faa",
    }
    for ss in ("spec", "spec-bug"):
        got = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-25T00:00:00Z",  # identity intact
            current_head_sha="a96d51df4000",
            sub_skill=ss,
            commits_since=2,  # baseline-lock commit + stub-marker-retire commit
        )
        assert got is None, (ss, got)
    # A genuine runaway (>3) on the same sub_skill STILL trips — no gate weakened.
    runaway = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-25T00:00:00Z",
        current_head_sha="a96d51df4000",
        sub_skill="spec",
        commits_since=7,
    )
    assert runaway is not None and runaway["reason"] == "unexpected-commits", runaway




def test_count_authored_commits_since_excludes_merge_commits():
    """Hardening Round 42 (2026-06-29 recurrence, AlgoBooth algorithmic-fill-buffer,
    Step 7a execute-plan): `_count_authored_commits_since` counts authored commits but
    EXCLUDES merge commits, so a sibling PR merged into main during the cycle window
    does NOT inflate the unexpected-commits count past the per-WU budget.

    Live recurrence: the part-3 plan declared 5 WUs (budget 5 + slack 2 = 7) and the
    cycle authored exactly 5 WU commits, but begin..HEAD ALSO spanned a merge commit
    (PR #107 d7b867a81 pre-release-roadmap integration), so the bare
    `rev-list --count begin..HEAD` returned 8 > 7 and false-tripped unexpected-commits.
    `--no-merges` brings the count to the 5 authored commits (the merge was the
    load-bearing overflow). A merge commit is NEVER an authored work unit, for any
    sub_skill — so excluding it is structural, not a phrase/threshold weakening.

    Fixture: build a real repo, branch, author commits on each side, then `git merge
    --no-ff` to force a real merge commit on the main line. begin = the pre-merge HEAD
    on main. Assert the helper counts only authored commits (merge excluded) and that a
    bare count would have over-counted by exactly the one merge commit."""
    _guard()

    def _run(cmd, cwd):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if r.returncode != 0:
            raise RuntimeError(f"git fixture failed (cmd={cmd!r}): {r.stderr.strip()}")
        return r

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        _run(["git", "init", "-q", str(root)], cwd=None)
        _run(["git", "config", "user.email", "t@t.local"], cwd=str(root))
        _run(["git", "config", "user.name", "T"], cwd=str(root))
        _run(["git", "config", "commit.gpgsign", "false"], cwd=str(root))

        def _commit(msg, fname):
            (root / fname).write_text(msg + "\n", encoding="utf-8")
            _run(["git", "add", fname], cwd=str(root))
            _run(["git", "commit", "-q", "-m", msg], cwd=str(root))

        _commit("init", "README.md")
        branch = _run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root)
        ).stdout.strip() or "main"

        # The --cycle-begin snapshot point.
        begin_sha = _run(["git", "rev-parse", "HEAD"], cwd=str(root)).stdout.strip()

        # 5 authored WU commits on the main line (mirrors the 5-WU part-3 cadence).
        for i in range(1, 6):
            _commit(f"feat: P5 WU-{i}", f"wu{i}.txt")

        # A sibling branch with its own commit, merged back with --no-ff so a REAL
        # merge commit lands on main (mirrors PR #107 integration mid-cycle).
        _run(["git", "checkout", "-q", "-b", "sibling", begin_sha], cwd=str(root))
        _commit("docs: pre-release roadmap (off-plan)", "roadmap.md")
        _run(["git", "checkout", "-q", branch], cwd=str(root))
        _run(
            ["git", "merge", "--no-ff", "-q", "-m", "Merge pull request #107", "sibling"],
            cwd=str(root),
        )

        # Bare count (the OLD behavior) includes the merge commit + the sibling's
        # authored commit → over-counts.
        bare = int(_run(
            ["git", "rev-list", "--count", f"{begin_sha}..HEAD"], cwd=str(root)
        ).stdout.strip())
        authored = lazy_core._count_authored_commits_since(root, begin_sha)

        # The merge commit is excluded; the sibling's authored commit is NOT (the fix
        # is deliberately narrow — only merges are excluded). bare counts the merge,
        # authored does not, so authored == bare - 1 (exactly the one merge commit).
        assert authored == bare - 1, (authored, bare)
        # And the merge-excluded count of the 5 main-line WU commits + 1 sibling
        # authored commit is 6 — under a 7 budget — whereas the bare count of 7
        # (6 authored + 1 merge) plus any further merge would breach it. The merge
        # exclusion is what keeps the honest cadence under budget.
        assert authored == 6, authored
        assert bare == 7, bare

    # Degraded inputs: no begin sha → None (signal disabled, never a false positive).
    assert lazy_core._count_authored_commits_since(Path(td), None) is None




def test_detect_friction_within_commit_budget_returns_none():
    """WU-2: a single commit (within the conservative budget) and intact identity
    → None."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-15T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at="2026-06-15T00:00:00Z",
        current_head_sha="bbbb2222",
        sub_skill="execute-plan",
        commits_since=1,
    )
    assert got is None, got




def test_detect_friction_degraded_inputs_return_none():
    """WU-2: null run_started_at / begin_head_sha in the marker (degraded snapshot)
    → None, never a false positive, no crash."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": None,
        "begin_head_sha": None,
    }
    got = lazy_core.detect_cycle_bracket_friction(
        marker,
        current_run_started_at=None,
        current_head_sha=None,
        sub_skill="execute-plan",
        commits_since=99,
    )
    assert got is None, got
    # An entirely empty marker also degrades gracefully.
    assert lazy_core.detect_cycle_bracket_friction(
        {}, current_run_started_at="x", current_head_sha="y",
        sub_skill="execute-plan", commits_since=0,
    ) is None




def test_detect_friction_meta_cycle_exempt_from_unexpected_commits():
    """D-A (2026-06-16): a kind='meta' cycle (hardening/input-audit/recovery/
    apply-resolution) is an orchestrator-driven remediation dispatch that
    legitimately commits an unbounded number of times and carries sub_skill=None.
    Signal (b) unexpected-commits MUST be exempt for it — otherwise every meta
    cycle (e.g. a hardening cycle committing a script fix + a hardening-log
    append) re-trips at its own --cycle-end, a self-perpetuating loop. Signal (a)
    bracket-break is NOT exempt (a meta cycle that tears the run bracket is real
    corruption)."""
    _guard()
    meta_marker = {
        "feature_id": "f", "nonce": "n", "kind": "meta",
        "run_started_at": "2026-06-16T00:00:00Z", "begin_head_sha": "aaaa1111",
    }
    # Many commits, sub_skill=None (the meta default) → NO unexpected-commits trip.
    got = lazy_core.detect_cycle_bracket_friction(
        meta_marker,
        current_run_started_at="2026-06-16T00:00:00Z",  # identity intact
        current_head_sha="bbbb2222",
        sub_skill=None,  # meta cycles carry no sub_skill
        commits_since=9,  # far beyond the default budget of 1
    )
    assert got is None, got
    # Signal (a) bracket-break STILL trips for a meta cycle (run identity changed
    # — exactly the D-B clobber). The exemption is signal (b) only.
    torn = lazy_core.detect_cycle_bracket_friction(
        meta_marker,
        current_run_started_at="2026-06-16T99:99:99Z",  # identity changed
        current_head_sha="bbbb2222",
        sub_skill=None,
        commits_since=9,
    )
    assert torn is not None and torn["reason"] == "cycle-bracket-break", torn
    # Control: the SAME multi-commit shape on a kind='real' cycle with a RECORDED
    # sub_skill still trips (b) — a single-commit skill (budget 1) with 9 commits
    # is a genuine runaway, and its budget IS derivable, so detection is intact.
    real_marker = dict(meta_marker, kind="real")
    real = lazy_core.detect_cycle_bracket_friction(
        real_marker,
        current_run_started_at="2026-06-16T00:00:00Z",
        current_head_sha="bbbb2222",
        sub_skill="some-single-commit-skill",  # recorded → budget derivable (1)
        commits_since=9,
    )
    assert real is not None and real["reason"] == "unexpected-commits", real
    # Regression (skip-mcp-test-frontmatter-unquoted-colon, harden 2026-07-04): a
    # kind='real' cycle whose sub_skill was NEVER recorded (--cycle-begin omitted
    # --sub-skill) is BUDGET-INDETERMINATE — the dispatch identity that selects the
    # multi-commit ceiling is unknown, so signal (b) is fail-open-disabled rather
    # than false-tripping on the sanctioned multi-commit work the (unknown) real
    # skill legitimately did. This is the exact false positive that fired for an
    # /execute-plan cycle: 3 per-WU commits, marker sub_skill=None, mis-derived
    # budget=1. Signals (a)/(a.5) — the integrity signals — are sub_skill-
    # independent and still fire (a torn bracket / stray branch always self-
    # announces); only the budget-dependent commit signal is spared.
    real_null = lazy_core.detect_cycle_bracket_friction(
        real_marker,
        current_run_started_at="2026-06-16T00:00:00Z",
        current_head_sha="bbbb2222",
        sub_skill=None,  # NOT recorded → indeterminate budget → fail-open, no trip
        commits_since=9,
    )
    assert real_null is None, real_null




def test_detect_friction_registry_known_skill_budgeted_without_literal_row():
    """adhoc-derive-cycle-commit-budget WU-3 (class-closure regression), updated for
    adhoc-derive-multi-commit-budget-from-dispatch-sites: the per-sub_skill commit
    budget is DERIVED from `skill_declares_multi_commit` (SKILL.md frontmatter), not
    from any hand-maintained literal table or frozenset. This proves the missing-row
    defect CLASS is closed: a NEW flagged skill is budgeted multi-commit with ZERO
    `lazy_core.py` edits beyond the helper itself, and a skill ABSENT from the
    flagged set still defaults to budget 1 so genuine runaways still trip. Every
    budget below also carries the `_CYCLE_COMMIT_NOISE_ALLOWANCE` cushion
    (adhoc-align-cycle-commit-count-with-budget-population)."""
    _guard()
    marker = {
        "feature_id": "f", "nonce": "n", "run_started_at": "2026-06-22T00:00:00Z",
        "begin_head_sha": "aaaa1111",
    }

    def _friction(sub_skill, commits, repo_root=None):
        return lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-22T00:00:00Z",  # identity intact
            current_head_sha="bbbb2222",
            sub_skill=sub_skill,
            commits_since=commits,
            repo_root=repo_root,
        )

    allowance = lazy_core._CYCLE_COMMIT_NOISE_ALLOWANCE

    # (1) A user-level flagged multi-commit skill is budgeted multi-commit via the
    # DERIVATION, with no literal dict row or frozenset backing it.
    assert _friction("execute-plan", 2) is None
    assert _friction("execute-plan", lazy_core._monolith._CYCLE_COMMIT_MULTI + allowance) is None

    # (2) A skill ABSENT from the flagged set still defaults to budget
    # 1 + allowance → a genuine runaway beyond it still trips.
    within = _friction("brand-new-skill", 1 + allowance)
    assert within is None, within
    absent = _friction("brand-new-skill", 1 + allowance + 1)
    assert absent is not None and absent["reason"] == "unexpected-commits", absent

    # (3) Class-closure, rebuilt against the NEW derivation mechanism: a skill that
    # exists ONLY as a fresh SKILL.md fixture (never mentioned anywhere in
    # lazy_core.py) still gets the multi-commit ceiling purely from its own
    # frontmatter flag — proving the fix is a general mechanism, not a name check.
    # One flagged fixture models a plain multi-commit skill (uniform ceiling); a
    # second, repo-scoped fixture models a HIGHER per-skill override by reusing the
    # real `mcp-test` identity (the only name present in
    # `_MULTI_COMMIT_CEILING_OVERRIDE`), proving the override composes with the
    # frontmatter-derived membership rather than being bypassed by it.
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        plain_dir = repo / ".claude" / "skills" / "brand-new-multi-skill"
        plain_dir.mkdir(parents=True)
        (plain_dir / "SKILL.md").write_text(
            "---\nname: brand-new-multi-skill\ncommit-cadence: multi\n---\n# X\n",
            encoding="utf-8",
        )
        ceiling = lazy_core._monolith._CYCLE_COMMIT_MULTI + allowance
        assert _friction("brand-new-multi-skill", ceiling, repo_root=repo) is None, ceiling
        over = _friction("brand-new-multi-skill", ceiling + 1, repo_root=repo)
        assert over is not None and over["reason"] == "unexpected-commits", over

        override_dir = repo / ".claude" / "skills" / "mcp-test"
        override_dir.mkdir(parents=True)
        (override_dir / "SKILL.md").write_text(
            "---\nname: mcp-test\ncommit-cadence: multi\n---\n# X\n",
            encoding="utf-8",
        )
        override_ceiling = lazy_core._MULTI_COMMIT_CEILING_OVERRIDE["mcp-test"] + allowance
        assert _friction("mcp-test", override_ceiling, repo_root=repo) is None, override_ceiling
        override_over = _friction("mcp-test", override_ceiling + 1, repo_root=repo)
        assert (
            override_over is not None
            and override_over["reason"] == "unexpected-commits"
        ), override_over




def test_cycle_end_friction_check_symbol_present():
    """WU-4: the --cycle-end I/O wiring helper exists on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "cycle_end_friction_check"), (
        "Phase 2 missing cycle_end_friction_check"
    )




def test_cycle_end_friction_check_clean_bracket_no_entry(tmp_path):
    """WU-4: a clean bracket (run identity intact, HEAD unchanged) appends NO
    ledger entry; the helper returns None and pending_hardening() stays 0."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Write a marker whose begin-snapshot matches the live values.  We
            # can't easily fake a live run marker here, so use the degraded path:
            # null begin run identity + null begin head → both signals off → None.
            lazy_core.write_cycle_marker(
                feature_id="f", nonce="n",
                run_started_at=None, begin_head_sha=None,
            )
            desc = lazy_core.cycle_end_friction_check(repo_root=Path(td))
            assert desc is None, desc
            assert lazy_core.pending_hardening() == 0
        finally:
            _clear_state_dir()




def test_cycle_end_friction_check_torn_bracket_appends_entry(tmp_path):
    """WU-4: a torn bracket — begin snapshot had a run identity that is absent at
    --cycle-end (no live run marker) — appends a kind: process-friction ledger
    entry and pending_hardening() ≥ 1.  The helper resolves the CURRENT run
    identity itself (None, since no run marker is on disk)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Simulate --cycle-begin having snapshotted a live run identity that
            # is now gone (the dispatched cycle ran --run-end).
            lazy_core.write_cycle_marker(
                feature_id="f", nonce="n",
                run_started_at="2026-06-15T00:00:00Z",
                begin_head_sha="aaaa1111",
            )
            assert lazy_core.read_run_marker() is None, "no run marker on disk"
            desc = lazy_core.cycle_end_friction_check(repo_root=Path(td))
            assert desc is not None and desc["reason"] == "cycle-bracket-break", desc
            assert lazy_core.pending_hardening() == 1
            entry = lazy_core.read_deny_ledger()[0]
            assert entry["kind"] == "process-friction", entry
            assert entry["acked"] is False, entry
        finally:
            _clear_state_dir()




def _init_temp_git_repo(root: Path) -> str:
    """Init a hermetic git repo at root with one initial commit; return its HEAD sha.

    Used by the process-friction false-positive regression test below, which needs
    cycle_end_friction_check to compute a REAL commits_since via git.
    """
    lazy_core._git(root, "init", "-q")
    lazy_core._git(root, "config", "user.email", "t@t.t")
    lazy_core._git(root, "config", "user.name", "t")
    lazy_core._git(root, "config", "commit.gpgsign", "false")
    (root / "f0.txt").write_text("0", encoding="utf-8")
    lazy_core._git(root, "add", "-A")
    lazy_core._git(root, "commit", "-q", "-m", "c0")
    proc = lazy_core._git(root, "rev-parse", "HEAD")
    return (proc.stdout or "").strip()




def _git_commit_file(root: Path, name: str) -> None:
    (root / name).write_text(name, encoding="utf-8")
    lazy_core._git(root, "add", "-A")
    lazy_core._git(root, "commit", "-q", "-m", name)




def test_cycle_end_friction_check_no_false_positive_on_execute_plan_multi_commit(tmp_path):
    """Regression (process-friction false-positive defect): a normal execute-plan
    cycle that legitimately commits TWICE (test commit + impl commit) must NOT trip
    unexpected-commits. The marker now persists sub_skill='execute-plan' (budget 3),
    so cycle_end_friction_check recovers the correct budget instead of forcing
    sub_skill=None → default budget 1, which flagged every multi-commit cycle."""
    _guard()
    with tempfile.TemporaryDirectory() as repo_td, \
            tempfile.TemporaryDirectory() as state_td:
        _set_state_dir(Path(state_td))
        try:
            repo = Path(repo_td)
            begin_sha = _init_temp_git_repo(repo)
            # --cycle-begin snapshot: degraded run identity (no live run marker →
            # bracket-break signal off, isolating the unexpected-commits signal),
            # the real begin HEAD, and the dispatched sub_skill.
            lazy_core.write_cycle_marker(
                feature_id="f", nonce="n",
                run_started_at=None, begin_head_sha=begin_sha,
                sub_skill="execute-plan",
            )
            # Two legitimate commits (test + impl) — within execute-plan's budget 3.
            _git_commit_file(repo, "test.txt")
            _git_commit_file(repo, "impl.txt")
            desc = lazy_core.cycle_end_friction_check(repo_root=repo)
            assert desc is None, (
                "execute-plan budget (3) must absorb a 2-commit cycle; got "
                f"false-positive: {desc}"
            )
            assert lazy_core.pending_hardening() == 0
        finally:
            _clear_state_dir()




def test_cycle_end_friction_check_runaway_commits_still_trips(tmp_path):
    """Inverse guard: a genuine runaway (commits beyond even the execute-plan
    budget of 3) STILL trips unexpected-commits — the fix raises the correct
    budget, it does not disable the signal."""
    _guard()
    with tempfile.TemporaryDirectory() as repo_td, \
            tempfile.TemporaryDirectory() as state_td:
        _set_state_dir(Path(state_td))
        try:
            repo = Path(repo_td)
            begin_sha = _init_temp_git_repo(repo)
            lazy_core.write_cycle_marker(
                feature_id="f", nonce="n",
                run_started_at=None, begin_head_sha=begin_sha,
                sub_skill="execute-plan",
            )
            for i in range(5):  # 5 > execute-plan budget 3
                _git_commit_file(repo, f"runaway{i}.txt")
            desc = lazy_core.cycle_end_friction_check(repo_root=repo)
            assert desc is not None and desc["reason"] == "unexpected-commits", desc
            assert lazy_core.pending_hardening() == 1
        finally:
            _clear_state_dir()




def _capture_refusal(op):
    """Invoke the guard, capturing (exit_code_or_None, stderr_text).

    Returns (code, msg): code is the SystemExit code (None if the guard did NOT
    exit), msg is whatever the guard wrote to stderr.
    """
    import io as _io
    buf = _io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = buf
    code = None
    try:
        lazy_core.refuse_if_cycle_active(op)
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
    finally:
        sys.stderr = real_stderr
    return code, buf.getvalue()




def test_refuse_guard_fires_with_marker_present():
    """refuse_if_cycle_active(op) with a cycle marker present exits non-zero and
    prints a corrective message to stderr — for EVERY guarded op."""
    _guard()
    for op in _GUARDED_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            try:
                lazy_core.write_cycle_marker(feature_id="f", nonce="n")
                code, msg = _capture_refusal(op)
                assert code is not None and code != 0, f"{op} must exit non-zero under marker"
                assert op in msg, f"{op} corrective message must name the op, got: {msg!r}"
                assert "cycle" in msg.lower(), f"{op} message must mention the cycle marker"
            finally:
                _clear_state_dir()




def test_refuse_guard_noop_without_marker():
    """refuse_if_cycle_active(op) with NO marker present returns normally (no
    raise, no exit) so the orchestrator flow is unaffected — for every op."""
    _guard()
    for op in _GUARDED_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            try:
                # No marker written. Guard must be a silent no-op.
                lazy_core.refuse_if_cycle_active(op)  # must NOT raise / exit
            finally:
                _clear_state_dir()




def test_refuse_guard_leaves_run_marker_untouched():
    """A refused op leaves state untouched: the run marker on disk before the
    refusal is identical after it (zero side effects)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False, repo_root="/r")
            run_path = Path(td) / "lazy-run-marker.json"
            before = run_path.read_text(encoding="utf-8")
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            code, _ = _capture_refusal("--run-end")
            assert code is not None and code != 0, "guard must refuse"
            after = run_path.read_text(encoding="utf-8")
            assert before == after, "refused op must not mutate the run marker"
        finally:
            _clear_state_dir()




def test_refuse_guard_allow_listed_ops_not_guarded():
    """Allow-listed ops (--neutralize-sentinel, --verify-ledger) are NOT in the
    refusal set — invoking the guard for them is a no-op even with a marker
    present (a legitimately-dispatched subagent needs them)."""
    _guard()
    for op in ("--neutralize-sentinel", "--verify-ledger"):
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            try:
                lazy_core.write_cycle_marker(feature_id="f", nonce="n")
                # The guard is only invoked for the orchestrator-only ops; these
                # ops never call it, so we assert membership in the guarded set.
                assert op not in lazy_core.CYCLE_REFUSED_OPS, (
                    f"{op} must NOT be a refused op (allow-listed)"
                )
            finally:
                _clear_state_dir()




# ---------------------------------------------------------------------------
# D-B (hardening-blind-to-process-friction, 2026-06-16) — refuse_run_start_clobber
#
# --run-start must REFUSE overwriting a live run marker owned by a DIFFERENT
# pipeline (a nested feature --run-start clobbering an active bug run marker).
# Same-pipeline re-run-start (checkpoint resume) is ALLOWED. A >24h-stale marker
# is a presumed-dead run and may be overwritten. Reads the marker RAW so the
# session-id staleness path cannot mask the live owner.
# ---------------------------------------------------------------------------

def _capture_clobber_refusal(incoming_pipeline, now=None):
    """Invoke refuse_run_start_clobber, capturing (exit_code_or_None, stderr)."""
    import io as _io
    buf = _io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = buf
    code = None
    try:
        if now is None:
            lazy_core.refuse_run_start_clobber(incoming_pipeline)
        else:
            lazy_core.refuse_run_start_clobber(incoming_pipeline, now=now)
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
    finally:
        sys.stderr = real_stderr
    return code, buf.getvalue()




def test_run_start_clobber_refuses_cross_pipeline_live_marker():
    """A feature --run-start over a LIVE bug marker (different pipeline) refuses
    (exit 3, names both pipelines) and leaves the existing marker untouched."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Live bug run marker (now-ish started_at).
            lazy_core.write_run_marker(pipeline="bug", cloud=False, repo_root="/r", now=1_000_000.0)
            run_path = Path(td) / "lazy-run-marker.json"
            before = run_path.read_text(encoding="utf-8")
            code, msg = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code == 3, f"cross-pipeline clobber must exit 3, got {code}"
            assert "bug" in msg and "feature" in msg, msg
            assert run_path.read_text(encoding="utf-8") == before, "marker must be untouched"
        finally:
            _clear_state_dir()




def test_run_start_clobber_allows_same_pipeline_resume():
    """A feature --run-start over a LIVE feature marker WITH a checkpoint file
    present (a sanctioned resume) does NOT refuse — write_run_marker overwrites.

    concurrent-same-branch-walkers-no-arbitration P1: the same-pipeline branch is
    now checkpoint-discriminated, so this fixture must seed lazy-run-checkpoint.json
    (the resume signal). WITHOUT a checkpoint the identical setup now correctly
    REFUSES (see test_run_start_clobber_refuses_same_pipeline_concurrent_no_checkpoint)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0)
            # Seed the resume signal: a legitimate checkpoint-resume always has
            # lazy-run-checkpoint.json on disk (written by --run-end --reason checkpoint).
            lazy_core.write_run_checkpoint(
                "Step 7a: execute plan",
                {"forward_cycles": 3, "meta_cycles": 0, "max_cycles": 20},
                now=1_000_000.0,
            )
            code, _ = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code is None, "same-pipeline re-run-start WITH checkpoint must NOT refuse (resume)"
        finally:
            _clear_state_dir()




def test_run_start_clobber_refuses_same_pipeline_concurrent_no_checkpoint():
    """A feature --run-start over a LIVE feature marker with NO checkpoint file is
    a genuinely-concurrent SECOND walker (not a resume) → REFUSE (exit 3), names
    the in-flight run, leaves the marker byte-for-byte untouched.

    concurrent-same-branch-walkers-no-arbitration P1: the core new behavior. The
    pre-fix code returned None unconditionally on the same-pipeline branch (defect)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0)
            run_path = Path(td) / "lazy-run-marker.json"
            before = run_path.read_text(encoding="utf-8")
            # No checkpoint file seeded → a second concurrent walker.
            code, msg = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code == 3, f"same-pipeline concurrent (no checkpoint) must exit 3, got {code}"
            # The diagnostic names the in-flight run (started_at and/or feature).
            assert "feature" in msg, msg
            assert "1970-01-12T13:46:40Z" in msg or "started_at" in msg, msg
            assert run_path.read_text(encoding="utf-8") == before, "marker must be untouched (zero side effects)"
        finally:
            _clear_state_dir()




def test_run_start_clobber_allows_same_pipeline_with_checkpoint_present():
    """A LIVE same-pipeline marker AND a checkpoint file present is a sanctioned
    resume → allow (code None). The refuse path must read the checkpoint
    NON-destructively (existence only) — the file must STILL EXIST afterward."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0)
            lazy_core.write_run_checkpoint(
                "Step 7a: execute plan",
                {"forward_cycles": 3, "meta_cycles": 0, "max_cycles": 20},
                now=1_000_000.0,
            )
            ckpt_path = Path(td) / "lazy-run-checkpoint.json"
            assert ckpt_path.exists(), "precondition: checkpoint seeded"
            code, _ = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code is None, "same-pipeline WITH checkpoint must NOT refuse (sanctioned resume)"
            assert ckpt_path.exists(), "refuse path must read checkpoint NON-destructively (file still present)"
        finally:
            _clear_state_dir()




def test_run_start_clobber_allows_same_pipeline_age_stale():
    """A same-pipeline marker >24h old with NO checkpoint is a presumed-dead run
    and may be overwritten — no refusal. The age gate runs BEFORE the pipeline
    check, so this never reaches the new same-pipeline-concurrent branch."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0)
            # now is >24h (86400s) after started_at → age-stale → reclaim, no refusal.
            code, _ = _capture_clobber_refusal("feature", now=1_000_000.0 + 90_000.0)
            assert code is None, "age-stale same-pipeline marker must not refuse (reclaim preserved)"
        finally:
            _clear_state_dir()




def test_run_start_clobber_cross_pipeline_unchanged_with_checkpoint():
    """Regression guard: a checkpoint file present does NOT excuse a CROSS-pipeline
    clobber. A LIVE bug marker + a checkpoint file, feature --run-start → still
    REFUSES (exit 3). The new checkpoint discriminator must not leak cross-pipeline."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="bug", cloud=False, repo_root="/r", now=1_000_000.0)
            lazy_core.write_run_checkpoint(
                "Step 7a: execute plan",
                {"forward_cycles": 3, "meta_cycles": 0, "max_cycles": 20},
                now=1_000_000.0,
            )
            code, msg = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code == 3, f"cross-pipeline clobber must exit 3 even with checkpoint, got {code}"
            assert "bug" in msg and "feature" in msg, msg
        finally:
            _clear_state_dir()




def test_run_start_clobber_allows_when_no_marker():
    """No existing marker → no refusal (the normal first --run-start)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            code, _ = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code is None, "no marker must not refuse"
        finally:
            _clear_state_dir()




def test_run_start_clobber_allows_over_age_stale_marker():
    """A >24h-stale cross-pipeline marker is a presumed-dead crashed run and may
    be overwritten — no refusal (mirrors read_run_marker age-staleness path A)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Bug marker started_at far in the past relative to `now`.
            lazy_core.write_run_marker(pipeline="bug", cloud=False, repo_root="/r", now=1_000_000.0)
            # now is >24h (86400s) after started_at → age-stale → no refusal.
            code, _ = _capture_clobber_refusal("feature", now=1_000_000.0 + 90_000.0)
            assert code is None, "age-stale cross-pipeline marker must not refuse"
        finally:
            _clear_state_dir()




def test_run_start_clobber_corrupt_marker_fails_open():
    """A corrupt/unparseable marker fails open (no refusal) — write_run_marker
    overwrites it (mirrors the corrupt-file handling in read_run_marker)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            (Path(td) / "lazy-run-marker.json").write_text("{ not json", encoding="utf-8")
            code, _ = _capture_clobber_refusal("feature")
            assert code is None, "corrupt marker must fail open (no refusal)"
        finally:
            _clear_state_dir()




def test_refuse_guard_orchestrator_env_never_refuses_even_with_marker():
    """LAZY_ORCHESTRATOR truthy → the guard NEVER refuses, even with a (stale)
    cycle marker present. This is the structural immunity to the self-deny
    defect: a lingering marker from a crashed prior dispatch can no longer
    self-refuse the orchestrator."""
    _guard()
    _clear_cycle_env()
    for op in _GUARDED_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            os.environ["LAZY_ORCHESTRATOR"] = "1"
            try:
                lazy_core.write_cycle_marker(feature_id="stale", nonce="n")
                # Must NOT raise / exit despite the marker being present.
                lazy_core.refuse_if_cycle_active(op)
            finally:
                _clear_cycle_env()
                _clear_state_dir()




def test_refuse_guard_explicit_subagent_env_refuses_without_marker():
    """LAZY_CYCLE_SUBAGENT truthy → refuse for every guarded op even with NO
    cycle marker armed (arming-free subagent containment)."""
    _guard()
    _clear_cycle_env()
    for op in _GUARDED_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            os.environ["LAZY_CYCLE_SUBAGENT"] = "1"
            try:
                # No marker written.
                code, msg = _capture_refusal(op)
                assert code is not None and code != 0, (
                    f"{op} must refuse for an explicit subagent (no marker)"
                )
                assert op in msg, f"{op} corrective message must name the op"
            finally:
                _clear_cycle_env()
                _clear_state_dir()




def test_refuse_guard_orchestrator_env_overrides_explicit_subagent():
    """LAZY_ORCHESTRATOR takes priority over LAZY_CYCLE_SUBAGENT (the orchestrator
    assertion wins) — never refuse."""
    _guard()
    _clear_cycle_env()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        os.environ["LAZY_ORCHESTRATOR"] = "1"
        os.environ["LAZY_CYCLE_SUBAGENT"] = "1"
        try:
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            lazy_core.refuse_if_cycle_active("--run-end")  # must NOT raise / exit
        finally:
            _clear_cycle_env()
            _clear_state_dir()




def test_refuse_guard_falsey_orchestrator_env_does_not_grant_immunity():
    """A falsey LAZY_ORCHESTRATOR (e.g. "0", "false", "") must NOT grant immunity —
    the marker backstop still refuses a subagent."""
    _guard()
    _clear_cycle_env()
    for falsey in ("0", "false", "", "off", "no"):
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            os.environ["LAZY_ORCHESTRATOR"] = falsey
            try:
                lazy_core.write_cycle_marker(feature_id="f", nonce="n")
                code, _ = _capture_refusal("--run-end")
                assert code is not None and code != 0, (
                    f"falsey LAZY_ORCHESTRATOR={falsey!r} must NOT grant immunity"
                )
            finally:
                _clear_cycle_env()
                _clear_state_dir()




def test_refuse_guard_marker_backstop_still_refuses_no_env():
    """With NO env signals set, the legacy marker backstop still refuses (the
    pre-D4 behavior is preserved as the fallback carrier)."""
    _guard()
    _clear_cycle_env()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            code, msg = _capture_refusal("--run-end")
            assert code is not None and code != 0, "marker backstop must refuse"
            assert "cycle" in msg.lower()
        finally:
            _clear_state_dir()




def test_env_truthy_helper():
    """_env_truthy treats unset / falsey strings as False and other values True."""
    _guard()
    _clear_cycle_env()
    try:
        assert lazy_core._env_truthy("LAZY_ORCHESTRATOR") is False  # unset
        for falsey in ("", "0", "false", "FALSE", "no", "off", "  "):
            os.environ["LAZY_ORCHESTRATOR"] = falsey
            assert lazy_core._env_truthy("LAZY_ORCHESTRATOR") is False, falsey
        for truthy in ("1", "true", "yes", "on", "agent_abc"):
            os.environ["LAZY_ORCHESTRATOR"] = truthy
            assert lazy_core._env_truthy("LAZY_ORCHESTRATOR") is True, truthy
    finally:
        _clear_cycle_env()




# ---------------------------------------------------------------------------
# cycle-subagent-runs-orchestrator-work Phase 2 (KEYSTONE) —
# refuse_cycle_marker_mutation_if_subagent
#
# --cycle-end / --cycle-begin are the ops the orchestrator runs WHILE its own
# cycle marker is present (begin arms it, end clears it). So the plain
# refuse_if_cycle_active marker-fallback (refuse anyone-with-a-marker) cannot be
# reused — it would refuse the orchestrator's own bracket. This dedicated guard
# keys on the POSITIVE signal:
#   1. LAZY_ORCHESTRATOR truthy → return silently (orchestrator clears/arms under
#      its own live marker — legitimate).
#   2. else LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent).
#   3. else cycle marker present (without orchestrator env) → refuse (the
#      reachable subagent-context signal — a subagent mid-dispatch sees the
#      orchestrator's marker but has no LAZY_ORCHESTRATOR export).
#   4. else (no marker, no subagent env) → return silently (genuinely-uncontained
#      main thread with no marker).
# A refusal exits 3 with ZERO side effects (the marker is NOT mutated).
# ---------------------------------------------------------------------------

_MARKER_MUTATION_OPS = ["--cycle-end", "--cycle-begin"]




def _capture_marker_mutation_refusal(op):
    """Invoke refuse_cycle_marker_mutation_if_subagent, capturing (code, stderr)."""
    import io as _io
    buf = _io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = buf
    code = None
    try:
        lazy_core.refuse_cycle_marker_mutation_if_subagent(op)
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
    finally:
        sys.stderr = real_stderr
    return code, buf.getvalue()




def test_marker_mutation_guard_orchestrator_allowed_with_marker():
    """LAZY_ORCHESTRATOR truthy → NEVER refuse, even with the marker present (the
    orchestrator legitimately clears/arms its own bracket)."""
    _guard()
    _clear_cycle_env()
    for op in _MARKER_MUTATION_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            os.environ["LAZY_ORCHESTRATOR"] = "1"
            try:
                lazy_core.write_cycle_marker(feature_id="f", nonce="n")
                # Must NOT raise / exit.
                lazy_core.refuse_cycle_marker_mutation_if_subagent(op)
            finally:
                _clear_cycle_env()
                _clear_state_dir()




def test_marker_mutation_guard_refuses_explicit_subagent_no_marker():
    """LAZY_CYCLE_SUBAGENT truthy → refuse for every mutation op even with NO
    marker armed."""
    _guard()
    _clear_cycle_env()
    for op in _MARKER_MUTATION_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            os.environ["LAZY_CYCLE_SUBAGENT"] = "1"
            try:
                code, msg = _capture_marker_mutation_refusal(op)
                assert code == 3, f"{op} must exit 3 for explicit subagent; got {code}"
                assert op in msg, f"{op} corrective message must name the op: {msg!r}"
            finally:
                _clear_cycle_env()
                _clear_state_dir()




def test_marker_mutation_guard_refuses_marker_present_without_orchestrator_env():
    """The reachable subagent signal: a cycle marker present + NO LAZY_ORCHESTRATOR
    → refuse (a subagent mid-dispatch sees the orchestrator's marker but never
    inherits the orchestrator export)."""
    _guard()
    _clear_cycle_env()
    for op in _MARKER_MUTATION_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            try:
                lazy_core.write_cycle_marker(feature_id="f", nonce="n")
                code, msg = _capture_marker_mutation_refusal(op)
                assert code == 3, f"{op} must exit 3 (marker present, no orch env)"
                assert op in msg, f"{op} corrective message must name the op"
            finally:
                _clear_state_dir()




def test_marker_mutation_guard_noop_no_marker_no_subagent_env():
    """No marker AND no subagent env signal → return silently (the genuinely
    uncontained main-thread case with no marker armed yet)."""
    _guard()
    _clear_cycle_env()
    for op in _MARKER_MUTATION_OPS:
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            try:
                # No marker, no env signals.
                lazy_core.refuse_cycle_marker_mutation_if_subagent(op)  # must NOT raise
            finally:
                _clear_state_dir()




def test_marker_mutation_guard_falsey_orchestrator_does_not_grant_immunity():
    """A falsey LAZY_ORCHESTRATOR must NOT grant immunity — the marker backstop
    still refuses a subagent."""
    _guard()
    _clear_cycle_env()
    for falsey in ("0", "false", "", "off", "no"):
        with tempfile.TemporaryDirectory() as td:
            _set_state_dir(Path(td))
            os.environ["LAZY_ORCHESTRATOR"] = falsey
            try:
                lazy_core.write_cycle_marker(feature_id="f", nonce="n")
                code, _ = _capture_marker_mutation_refusal("--cycle-end")
                assert code == 3, (
                    f"falsey LAZY_ORCHESTRATOR={falsey!r} must NOT grant immunity"
                )
            finally:
                _clear_cycle_env()
                _clear_state_dir()




def test_marker_mutation_guard_zero_side_effects_on_refusal():
    """A refused mutation leaves the marker file ON DISK, byte-identical (the
    guard runs BEFORE any clear/overwrite)."""
    _guard()
    _clear_cycle_env()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        marker_path = Path(td) / _CYCLE_MARKER_FILENAME
        try:
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            before = marker_path.read_text(encoding="utf-8")
            code, _ = _capture_marker_mutation_refusal("--cycle-end")
            assert code == 3, "guard must refuse"
            assert marker_path.exists(), "refused --cycle-end must NOT delete the marker"
            after = marker_path.read_text(encoding="utf-8")
            assert before == after, "refused op must not mutate the marker"
        finally:
            _clear_state_dir()




def test_marker_mutation_guard_orchestrator_overrides_explicit_subagent():
    """LAZY_ORCHESTRATOR takes priority over LAZY_CYCLE_SUBAGENT (the orchestrator
    assertion wins)."""
    _guard()
    _clear_cycle_env()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        os.environ["LAZY_ORCHESTRATOR"] = "1"
        os.environ["LAZY_CYCLE_SUBAGENT"] = "1"
        try:
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            lazy_core.refuse_cycle_marker_mutation_if_subagent("--cycle-begin")  # no raise
        finally:
            _clear_cycle_env()
            _clear_state_dir()




def test_marker_mutation_ops_not_in_cycle_refused_ops():
    """--cycle-end / --cycle-begin are guarded by the dedicated marker-mutation
    helper, NOT added to CYCLE_REFUSED_OPS (whose members use the plain
    marker-fallback that --cycle-end cannot use). Lockstep documentation check."""
    _guard()
    for op in _MARKER_MUTATION_OPS:
        assert op not in lazy_core.CYCLE_REFUSED_OPS, (
            f"{op} must NOT be in CYCLE_REFUSED_OPS — it uses the dedicated guard"
        )




def _ensure_runtime_via_marker(repo_root, marker_session_id, **inject):
    """Mirror the lazy-state.py --ensure-runtime handler wiring in-process:
    derive live_session_id from a marker session_id, then call ensure_runtime.
    (The handler itself is a thin marker-read + delegate; this asserts the same
    contract hermetically without firing the real urllib probe / dev:restart.)"""
    return lazy_core.ensure_runtime(
        Path(repo_root), live_session_id=marker_session_id, **inject
    )




def test_ensure_runtime_handler_wiring_emits_m4_verdict_all_states():
    """The handler's marker-session→live_session_id→ensure_runtime wiring yields a
    JSON-serializable verdict carrying ALL five M4 keys, and the `state` tracks the
    injected scenario across READY/STALE/HIJACKED/DEAD/BLOCKED."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sid = "live-run-session"
        # An owned lock whose controller_session_id IS the marker session id (the
        # handler threads the marker session as live_session_id).
        owned = {**_owned_lock(start_time=100.0), "controller_session_id": sid}

        # READY: owned + current + healthy.
        ready = _ensure_runtime_via_marker(
            td, sid, config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True, stale_check=lambda: False,
            read_lock=lambda: owned, kernel_start_time_fn=lambda p, **k: 100.0,
            sleep=lambda s: None,
        )
        # HIJACKED: foreign session + live divergent owner answering health.
        hijacked = _ensure_runtime_via_marker(
            td, sid, config=_M4_CONFIG,
            probe=lambda: (200, {"tools": ["render_chart"]}),
            restart=lambda: True, stale_check=lambda: False,
            read_lock=lambda: {**owned, "controller_session_id": "foreign"},
            kernel_start_time_fn=lambda p, **k: 999.0, sleep=lambda s: None,
        )
        # BLOCKED: owned DEAD that never recovers (genuinely dead: Vite also down,
        # so the cold-compile discriminator classifies `dead` deterministically —
        # the default config now carries the :1420 key, so an explicit down probe
        # keeps this hermetic).
        blocked = _ensure_runtime_via_marker(
            td, sid, config=_M4_CONFIG,
            probe=lambda: (0, None),
            restart=lambda: True, stale_check=lambda: False,
            read_lock=lambda: owned, kernel_start_time_fn=lambda p, **k: 100.0,
            sleep=lambda s: None, frontend_probe=lambda: False,
        )
        for verdict in (ready, hijacked, blocked):
            assert _M4_KEYS.issubset(verdict.keys()), verdict
            # JSON-serializable (the handler json.dumps it).
            json.dumps(verdict)
        assert ready["state"] == "READY", ready
        assert hijacked["state"] == "HIJACKED", hijacked
        assert blocked["state"] == "BLOCKED", blocked




def test_ensure_runtime_handler_wiring_threads_frontend_probe_for_compiling():
    """ensure-runtime-recovery-starves-cold-compile Phase 3 (WU-5): the handler's
    marker→ensure_runtime delegate threads the frontend signal through to the M4
    path so a `compiling` runtime (backend down, Vite up) reaches READY via the
    patient wait — WITHOUT the handler doing any manual re-classification. Asserts
    the production discriminator is reachable through the same thin pass-through
    wiring the handler uses (config-driven default binding + no new handler arg)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sid = "live-run-session"
        owned = {**_owned_lock(start_time=100.0), "controller_session_id": sid}
        calls = {"restart": 0, "probe": 0}

        def probe():
            calls["probe"] += 1
            # Backend answers 200 from the 3rd probe (a cold compile finishing).
            return (200, {"tools": ["render_chart"]}) if calls["probe"] >= 3 else (0, None)

        compiling = _ensure_runtime_via_marker(
            td, sid, config=_M4_CONFIG,
            probe=probe,
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: owned, kernel_start_time_fn=lambda p, **k: 100.0,
            sleep=lambda s: None,
            frontend_probe=lambda: True,  # Vite up → compiling, the handler waits
        )
        assert compiling["state"] == "READY", compiling
        assert calls["restart"] == 0, (
            f"a compiling runtime reaching the handler must be waited, not restarted: {calls}"
        )
        assert _M4_KEYS.issubset(compiling.keys()), compiling
        json.dumps(compiling)  # handler json.dumps it




def test_ensure_runtime_handler_wiring_threads_boot_alive_for_pre_vite():
    """ensure-runtime-starves-pre-vite-sidecar-build Phase 3 (WU-5): the handler's
    marker→ensure_runtime delegate threads the boot-liveness signal through to the
    M4 path so a pre-Vite runtime (BOTH ports down, boot process alive) reaches
    READY via the patient wait — WITHOUT the handler doing any manual
    re-classification. Asserts the production pre-Vite discriminator is reachable
    through the same thin pass-through wiring (config-driven binding, no new
    handler arg)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sid = "live-run-session"
        owned = {**_owned_lock(start_time=100.0), "controller_session_id": sid}
        calls = {"restart": 0, "probe": 0}

        def probe():
            calls["probe"] += 1
            # Backend answers 200 from the 3rd probe (a cold pre-Vite boot finishing).
            return (200, {"tools": ["render_chart"]}) if calls["probe"] >= 3 else (0, None)

        pre_vite = _ensure_runtime_via_marker(
            td, sid, config=_M4_CONFIG_BOOT,
            probe=probe,
            restart=lambda: calls.__setitem__("restart", calls["restart"] + 1) or True,
            stale_check=lambda: False,
            read_lock=lambda: owned, kernel_start_time_fn=lambda p, **k: 100.0,
            sleep=lambda s: None,
            frontend_probe=lambda: False,  # Vite NOT yet up (pre-Vite window)
            boot_alive=lambda: True,       # boot process alive → the handler waits
        )
        assert pre_vite["state"] == "READY", pre_vite
        assert calls["restart"] == 0, (
            f"a pre-Vite live boot reaching the handler must be waited, not restarted: {calls}"
        )
        assert _M4_KEYS.issubset(pre_vite.keys()), pre_vite
        json.dumps(pre_vite)  # handler json.dumps it




def test_ensure_runtime_cli_handler_emits_m4_json_subprocess():
    """End-to-end: `lazy-state.py --ensure-runtime` prints valid JSON carrying the
    M4 keys. Uses the HIJACKED scenario (a planted marker + a foreign-session lock
    whose recorded PID is this live test process) so the handler returns IMMEDIATELY
    — never entering the recovery loop (no real dev:restart, no 7.5-min health
    poll) — while still exercising the real handler + marker-read + verdict print."""
    _guard()
    import datetime
    with tempfile.TemporaryDirectory(prefix="ensure-rt-cli-") as state_dir, \
            tempfile.TemporaryDirectory(prefix="ensure-rt-repo-") as repo_root:
        sid = "cli-live-run"
        # Plant a run marker (session_id = sid) in the pinned state dir. Use a
        # current-ish ISO-8601 'Z' started_at so the 24h age-staleness path does
        # not delete it before the handler reads it.
        _started_at = (
            datetime.datetime.now(datetime.timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        marker = {
            "session_id": sid,
            "started_at": _started_at,
            "pipeline": "feature",
            "repo_root": str(repo_root),
        }
        (Path(state_dir) / "lazy-run-marker.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )
        # Plant `.runtime.lock.json`: FOREIGN controller_session_id (≠ marker sid)
        # + recorded PID = THIS live process (kernel_start_time resolves to a real
        # float) + a recorded start_time that will NOT match it (1.0) → ownership
        # fails on session AND start_time, live PID → HIJACKED (immediate return).
        (Path(repo_root) / ".runtime.lock.json").write_text(
            json.dumps({
                "controller_session_id": "foreign-session",
                "pid": os.getpid(),
                "start_time": 1.0,
                "port": 3333,
                "artifact_hash": "x",
            }),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"),
             "--ensure-runtime", "--repo-root", str(repo_root)],
            capture_output=True, text=True,
            env={**os.environ, "LAZY_STATE_DIR": state_dir},
            timeout=60,
        )
        assert result.returncode == 0, (result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        assert _M4_KEYS.issubset(payload.keys()), payload
        assert payload["state"] == "HIJACKED", payload
        assert payload["ownership_verified"] is False, payload
        assert payload["terminal_blocker"], payload




# ---------------------------------------------------------------------------
# lazy-batch-unified-driver-parity-and-accounting Phase 1 (Fix-A) — Item 1.
# ---------------------------------------------------------------------------
#
# advance_forward_cycle(state): a CONSUME-INDEPENDENT forward/meta advance keyed
# on a change in the marker-recorded (feature_id, current_step, sub_skill)
# tuple. Inline pseudo-skills (__mark_complete__/__mark_fixed__/__write_validated_*
# /__grant_skip_no_mcp_surface__/__flip_plan_complete_cloud_saturated__) run via
# --apply-pseudo, dispatch no Agent, trigger no guard ALLOW, and increment no
# registry consume — so the consume-gated advance_run_counters never advances for
# them. Fix-A advances on a genuine (feature_id, current_step, sub_skill) state
# change persisted in last_advance_state_key, independent of the consume oracle.
# This also closes Theory-1b (a verbatim real-skill dispatch that misses a consume
# still advances on the state change).


def test_advance_forward_cycle_state_change_no_consume_advances():
    """WU-1 RED test (item-1 regression): a forward-advancing pseudo-skill apply
    with a CHANGED (feature_id, current_step, sub_skill) tuple and NO consume
    increment still advances forward_cycles by exactly 1.

    Against pre-fix advance_run_counters this FAILS (it gates on
    current_consume <= prior_consume → no consume → returns the marker unchanged,
    forward_cycles stays 0). advance_forward_cycle advances on the state change.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="bug", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            # NO dispatch consume — the inline pseudo-skill path is consume-free.
            state = {
                "sub_skill": "__mark_fixed__",
                "feature_id": "bug-x",
                "current_step": "mark-fixed",
            }
            # __mark_fixed__ is a forward-advancing pseudo-skill: it advances the
            # pipeline (writes the FIXED receipt + archives), so it counts toward
            # forward_cycles (the forward budget), NOT meta_cycles.
            updated = lazy_core.advance_forward_cycle(state)
            assert updated is not None, (
                "advance_forward_cycle must return the updated marker when a marker "
                "is present"
            )
            assert updated["forward_cycles"] == 1, (
                f"a forward-advancing pseudo-skill state change with no consume must "
                f"advance forward_cycles to 1, got {updated['forward_cycles']!r}"
            )
            assert updated.get("last_advance_state_key") == [
                "bug-x", "mark-fixed", "__mark_fixed__",
            ], (
                f"the advance must persist the (feature_id, current_step, sub_skill) "
                f"key, got {updated.get('last_advance_state_key')!r}"
            )
        finally:
            _clear_state_dir()

    # No marker → returns None (marker-gated, mirrors advance_meta_cycle).
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.advance_forward_cycle(
                {"sub_skill": "__mark_fixed__", "feature_id": "b", "current_step": "s"}
            ) is None, "advance_forward_cycle must return None when no marker present"
        finally:
            _clear_state_dir()




def test_advance_forward_cycle_idempotent_across_refires():
    """WU-2 case (b): a repeated identical (feature_id, current_step, sub_skill)
    with no consume does NOT advance again — idempotent across re-fires (preserves
    the consume-gated no-op invariant for bare probe/inject re-fires)."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            state = {
                "sub_skill": "/execute-plan",
                "feature_id": "feat-x",
                "current_step": "execute-plan",
            }
            m1 = lazy_core.advance_forward_cycle(state)
            assert m1["forward_cycles"] == 1, m1
            # Same tuple, three re-fires → no further advance.
            for _ in range(3):
                mN = lazy_core.advance_forward_cycle(state)
                assert mN["forward_cycles"] == 1, (
                    f"identical state key must NOT advance again, got "
                    f"{mN['forward_cycles']!r}"
                )
        finally:
            _clear_state_dir()




def test_advance_forward_cycle_pseudo_cleanup_routes_meta():
    """WU-2 case (c): a __-prefixed cleanup-class pseudo-skill that is NOT a
    forward-advancing terminal routes to meta_cycles, not forward_cycles.

    The classifier mirrors advance_run_counters: a forward-advancing pseudo-skill
    is one in lazy_core._FORWARD_ADVANCING_PSEUDO_SKILLS; any other __-prefixed or
    falsy sub_skill is meta."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            state = {
                "sub_skill": "__neutralize_sentinel__",
                "feature_id": "feat-x",
                "current_step": "cleanup",
            }
            m = lazy_core.advance_forward_cycle(state)
            assert m["meta_cycles"] == 1, (
                f"a non-forward __-prefixed cleanup pseudo-skill must route to "
                f"meta_cycles, got meta={m['meta_cycles']!r} fwd={m['forward_cycles']!r}"
            )
            assert m["forward_cycles"] == 0, (
                f"forward_cycles must stay 0 for a meta cleanup, got "
                f"{m['forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_advance_forward_cycle_verbatim_real_skill_theory_1b():
    """WU-2 case (d) — Theory-1b closure: a real-skill sub_skill change advances
    forward_cycles once even on a verbatim (consume-missed) dispatch.

    No consume is simulated (the verbatim dispatch missed the guard ALLOW), yet the
    state change drives the advance."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            # First real cycle.
            s1 = {"sub_skill": "/plan-feature", "feature_id": "feat-x",
                  "current_step": "plan-feature"}
            m1 = lazy_core.advance_forward_cycle(s1)
            assert m1["forward_cycles"] == 1, m1
            # Second real cycle — different current_step → advances again, no consume.
            s2 = {"sub_skill": "/execute-plan", "feature_id": "feat-x",
                  "current_step": "execute-plan"}
            m2 = lazy_core.advance_forward_cycle(s2)
            assert m2["forward_cycles"] == 2, (
                f"a verbatim real-skill state change must advance forward_cycles to "
                f"2 with no consume (Theory-1b), got {m2['forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_advance_forward_cycle_legacy_marker_no_state_key_advances():
    """A legacy marker lacking last_advance_state_key defaults to None → the first
    state-change always advances (consistent with the legacy-watermark treatment in
    advance_run_counters)."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            # Simulate a legacy marker: strip the new field if present.
            marker_path = Path(td) / lazy_core._MARKER_FILENAME
            m = json.loads(marker_path.read_text(encoding="utf-8"))
            m.pop("last_advance_state_key", None)
            marker_path.write_text(json.dumps(m) + "\n", encoding="utf-8")
            updated = lazy_core.advance_forward_cycle(
                {"sub_skill": "/execute-plan", "feature_id": "f", "current_step": "x"}
            )
            assert updated["forward_cycles"] == 1, (
                f"legacy marker (no last_advance_state_key) must advance on first "
                f"state change, got {updated['forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Tests: feature-budget-guard-and-skip-ahead Phase 1 — per-feature forward-cycle
#   counter (per_feature_forward_cycles: {feature_id: int} run-marker map).
#
# The per-feature increment is a SIBLING write inside the SAME marker mutation
# that advances the run-level forward_cycles, gated by the EXACT same
# forward-vs-meta classifier (a real non-`__` skill OR a member of
# _FORWARD_ADVANCING_PSEUDO_SKILLS). It rides BOTH forward-advance triggers
# (advance_run_counters consume-oracle + advance_forward_cycle state-change) and
# is keyed on state["feature_id"]. Meta-only advances must NOT increment it.
# A legacy marker lacking the key defaults to {} on read (no KeyError).
# ---------------------------------------------------------------------------


def test_write_run_marker_initializes_per_feature_map():
    """P1 RED: write_run_marker seeds per_feature_forward_cycles: {} alongside
    forward_cycles: 0 / meta_cycles: 0."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            m = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            assert m.get("per_feature_forward_cycles") == {}, (
                f"write_run_marker must seed an empty per_feature_forward_cycles "
                f"map, got {m.get('per_feature_forward_cycles')!r}"
            )
            # Round-trips through the read path too.
            on_disk = lazy_core.read_run_marker(now=_time.time())
            assert on_disk.get("per_feature_forward_cycles") == {}, on_disk
        finally:
            _clear_state_dir()




def test_advance_forward_cycle_increments_per_feature():
    """P1 RED: advance_forward_cycle increments per_feature_forward_cycles[id] by
    1 on a forward-advancing state change, keyed on state['feature_id'], in the
    SAME marker mutation as forward_cycles."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            # Cycle 1 — real skill on feat-A.
            m = lazy_core.advance_forward_cycle({
                "sub_skill": "/execute-plan", "feature_id": "feat-A",
                "current_step": "execute-plan",
            })
            assert m["forward_cycles"] == 1, m
            assert m["per_feature_forward_cycles"].get("feat-A") == 1, (
                f"per_feature_forward_cycles[feat-A] must be 1 after one forward "
                f"cycle, got {m['per_feature_forward_cycles']!r}"
            )
            # Cycle 2 — forward-advancing pseudo-skill on the SAME feature.
            m = lazy_core.advance_forward_cycle({
                "sub_skill": "__mark_complete__", "feature_id": "feat-A",
                "current_step": "mark-complete",
            })
            assert m["forward_cycles"] == 2, m
            assert m["per_feature_forward_cycles"].get("feat-A") == 2, (
                f"per-feature count must equal the run-level forward count for the "
                f"feature, got {m['per_feature_forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_advance_forward_cycle_meta_does_not_increment_per_feature():
    """P1 RED: a meta-only advance (non-forward __-prefixed cleanup) advances
    meta_cycles but does NOT touch per_feature_forward_cycles."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            m = lazy_core.advance_forward_cycle({
                "sub_skill": "__neutralize_sentinel__", "feature_id": "feat-A",
                "current_step": "cleanup",
            })
            assert m["meta_cycles"] == 1, m
            assert m["per_feature_forward_cycles"].get("feat-A", 0) == 0, (
                f"a meta-only advance must NOT increment the per-feature counter, "
                f"got {m['per_feature_forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_per_feature_counter_independent_keys():
    """P1 RED: a second feature gets its own independent per-feature key."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            lazy_core.advance_forward_cycle({
                "sub_skill": "/execute-plan", "feature_id": "feat-A",
                "current_step": "execute-plan",
            })
            lazy_core.advance_forward_cycle({
                "sub_skill": "/spec", "feature_id": "feat-A",
                "current_step": "spec",
            })
            m = lazy_core.advance_forward_cycle({
                "sub_skill": "/execute-plan", "feature_id": "feat-B",
                "current_step": "execute-plan",
            })
            assert m["per_feature_forward_cycles"].get("feat-A") == 2, m
            assert m["per_feature_forward_cycles"].get("feat-B") == 1, (
                f"a second feature must accrue its own independent count, got "
                f"{m['per_feature_forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_per_feature_counter_legacy_marker_tolerance():
    """P1 RED: a legacy marker lacking per_feature_forward_cycles defaults to {}
    on the advance path — never KeyErrors, and starts the map from the advance."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            # Simulate a legacy marker: strip the new key.
            marker_path = Path(td) / lazy_core._MARKER_FILENAME
            m = json.loads(marker_path.read_text(encoding="utf-8"))
            m.pop("per_feature_forward_cycles", None)
            marker_path.write_text(json.dumps(m) + "\n", encoding="utf-8")
            updated = lazy_core.advance_forward_cycle({
                "sub_skill": "/execute-plan", "feature_id": "feat-L",
                "current_step": "execute-plan",
            })
            assert updated["per_feature_forward_cycles"].get("feat-L") == 1, (
                f"a legacy marker (no per_feature_forward_cycles) must default to "
                f"{{}} and start the count, got "
                f"{updated.get('per_feature_forward_cycles')!r}"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Tests: feature-budget-guard-and-skip-ahead Phase 2 — compute_per_feature_ceiling
#   Dynamic fair-share ceiling (Locked Decision 4):
#     L_task = max(6, min(C*4//10, (C//Q)*2))  (integer floor division)
#   override (the --per-feature-cycle-cap path) short-circuits to the override.
#   Q<=0 → returns the 6 floor (no div-by-zero). Pure + side-effect-free.
# ---------------------------------------------------------------------------


def test_compute_per_feature_ceiling_override_short_circuits():
    """Default-off contract: an explicit override returns verbatim, bypassing
    the now-default-off (None) path. This is the OFF-by-default OPT-IN."""
    _guard()
    assert lazy_core.compute_per_feature_ceiling(20, 5, override=3) == 3
    assert lazy_core.compute_per_feature_ceiling(20, 5, override=99) == 99
    # override=0 is a deliberate cap of 0 (falsy but not None) — honored verbatim.
    assert lazy_core.compute_per_feature_ceiling(20, 5, override=0) == 0




def test_compute_per_feature_ceiling_six_floor_small_run():
    """Default-off contract: no override → None (guard OFF by default).
    Formerly returned the 6 floor for C=12, Q=2; the budget block in
    lazy-state.py now short-circuits on the None ceiling."""
    _guard()
    assert lazy_core.compute_per_feature_ceiling(12, 2) is None




def test_compute_per_feature_ceiling_deep_queue_six():
    """Default-off contract: no override → None (guard OFF by default).
    The RESEARCH_SUMMARY deep-queue example C=32, Q=10 formerly returned 6."""
    _guard()
    assert lazy_core.compute_per_feature_ceiling(32, 10) is None




def test_compute_per_feature_ceiling_forty_percent_cap_arm():
    """Default-off contract: no override → None even where the 40%-cap arm
    formerly armed (C=50, Q=2 → 20). The OPT-IN re-arms a fixed ceiling:
    override=20 → 20 (keeps the opt-in fixed-ceiling characterized)."""
    _guard()
    assert lazy_core.compute_per_feature_ceiling(50, 2) is None
    assert lazy_core.compute_per_feature_ceiling(50, 2, override=20) == 20




def test_compute_per_feature_ceiling_zero_queue_no_div_by_zero():
    """Default-off contract: no override → None. The default-off path computes
    nothing, so the old Q<=0 div-by-zero branch is unreachable by default; the
    override path never divides either. The guard never arms by default."""
    _guard()
    assert lazy_core.compute_per_feature_ceiling(20, 0) is None
    # Negative is also None by default (no compute path runs).
    assert lazy_core.compute_per_feature_ceiling(20, -1) is None




def test_compute_per_feature_ceiling_pure_no_side_effects():
    """Default-off contract: identical no-override inputs → identical outputs
    (both None), repeatable (pure fn)."""
    _guard()
    a = lazy_core.compute_per_feature_ceiling(25, 4)
    b = lazy_core.compute_per_feature_ceiling(25, 4)
    assert a == b
    assert a is None




# ---------------------------------------------------------------------------
# Tests: budget-guard-defers-near-complete-feature Phase 1 — near-completion
#   predicate + corrective-cycle accounting + composite trip-signal evaluator.
#
#   WU-1 feature_is_near_complete(feature_dir, repo_root) -> bool
#       True iff PHASES.md present AND remaining_unchecked_are_verification_only
#       is True AND >=1 plan part status: Complete AND no BLOCKED.md. Tolerant of
#       missing PHASES.md / plans dir (returns False, never raises).
#   WU-2 count_validation_corrective_cycles(marker, feature_id) -> int (legacy 0)
#        record_corrective_cycle(marker, feature_id) (increment by 1)
#        write_run_marker seeds per_feature_corrective_cycles: {}.
#   WU-3 budget_trip_signals(forward_count, corrective_count, ceiling,
#        near_complete) -> {should_defer, effective_count, reason} (pure).
# ---------------------------------------------------------------------------


def _write_near_complete_feature_dir(td_root, *, verification_only=True,
                                     plan_complete=True, blocked=False,
                                     phases_present=True):
    """Build a docs/bugs|features-style feature dir for feature_is_near_complete
    fixtures. Returns the feature dir Path."""
    feat = Path(td_root) / "feat"
    feat.mkdir(parents=True, exist_ok=True)
    if phases_present:
        if verification_only:
            phases = (
                "# Phases\n\n"
                "### Phase 1\n"
                "- [x] Implemented the thing\n\n"
                "**Runtime Verification** <!-- verification-only -->\n"
                "- [ ] runtime check <!-- verification-only -->\n"
            )
        else:
            phases = (
                "# Phases\n\n"
                "### Phase 1\n"
                "- [ ] An unchecked IMPLEMENTATION row (not verification)\n"
            )
        (feat / "PHASES.md").write_text(phases, encoding="utf-8")
    plans = feat / "plans"
    plans.mkdir(exist_ok=True)
    status = "Complete" if plan_complete else "In-progress"
    (plans / "all-phases-part-1.md").write_text(
        f"---\nkind: implementation-plan\nstatus: {status}\n---\n\n# plan\n",
        encoding="utf-8",
    )
    if blocked:
        (feat / "BLOCKED.md").write_text(
            "---\nkind: blocked\n---\n\n# blocked\n", encoding="utf-8"
        )
    return feat




def test_feature_is_near_complete_true_verification_only_plan_complete():
    """P1 RED: verification-only PHASES + a Complete plan part + no BLOCKED.md
    ⇒ near-complete True."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        feat = _write_near_complete_feature_dir(td)
        assert lazy_core.feature_is_near_complete(feat, Path(td)) is True




def test_feature_is_near_complete_false_unchecked_impl_row():
    """P1 RED: an unchecked IMPLEMENTATION row (no verification-only marker) ⇒
    False (work remains, not just validation)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        feat = _write_near_complete_feature_dir(td, verification_only=False)
        assert lazy_core.feature_is_near_complete(feat, Path(td)) is False




def test_feature_is_near_complete_false_blocked():
    """P1 RED: a BLOCKED.md on disk ⇒ False even when otherwise near-complete."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        feat = _write_near_complete_feature_dir(td, blocked=True)
        assert lazy_core.feature_is_near_complete(feat, Path(td)) is False




def test_feature_is_near_complete_false_no_plan_complete():
    """P1 RED: no plan part is Complete ⇒ False (not yet ready to validate)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        feat = _write_near_complete_feature_dir(td, plan_complete=False)
        assert lazy_core.feature_is_near_complete(feat, Path(td)) is False




def test_feature_is_near_complete_false_missing_phases_no_raise():
    """P1 RED: a missing PHASES.md / plans dir returns False and never raises."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        feat = Path(td) / "empty"
        feat.mkdir()
        # No PHASES.md, no plans dir at all.
        assert lazy_core.feature_is_near_complete(feat, Path(td)) is False
        # A nonexistent dir is also tolerated.
        assert lazy_core.feature_is_near_complete(
            Path(td) / "does-not-exist", Path(td)
        ) is False




def test_count_validation_corrective_cycles_legacy_absent_zero():
    """P1 RED: a legacy/absent per_feature_corrective_cycles map ⇒ 0 (mirrors
    read_per_feature_forward_cycles legacy tolerance)."""
    _guard()
    assert lazy_core.count_validation_corrective_cycles(None, "feat-A") == 0
    assert lazy_core.count_validation_corrective_cycles({}, "feat-A") == 0
    assert lazy_core.count_validation_corrective_cycles(
        {"per_feature_corrective_cycles": {}}, "feat-A"
    ) == 0
    assert lazy_core.count_validation_corrective_cycles(
        {"per_feature_corrective_cycles": {"feat-A": 3}}, "feat-A"
    ) == 3




def test_record_corrective_cycle_increments_by_one():
    """P1 RED: record_corrective_cycle increments per_feature_corrective_cycles
    [id] by 1 per call, keyed on feature_id."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            m = lazy_core.record_corrective_cycle(
                lazy_core.read_run_marker(), "feat-A"
            )
            assert m["per_feature_corrective_cycles"].get("feat-A") == 1, m
            m = lazy_core.record_corrective_cycle(m, "feat-A")
            assert m["per_feature_corrective_cycles"].get("feat-A") == 2, m
            # A second feature gets its own independent key.
            m = lazy_core.record_corrective_cycle(m, "feat-B")
            assert m["per_feature_corrective_cycles"].get("feat-B") == 1, m
            assert m["per_feature_corrective_cycles"].get("feat-A") == 2, m
        finally:
            _clear_state_dir()




def test_record_corrective_cycle_legacy_marker_tolerance():
    """P1 RED: a marker lacking per_feature_corrective_cycles defaults to {} and
    starts the count — never KeyErrors."""
    _guard()
    legacy = {"pipeline": "feature"}
    m = lazy_core.record_corrective_cycle(legacy, "feat-L")
    assert m["per_feature_corrective_cycles"].get("feat-L") == 1, m




def test_write_run_marker_seeds_per_feature_corrective_map():
    """P1 RED: write_run_marker seeds per_feature_corrective_cycles: {} alongside
    the per_feature_forward_cycles seed."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            m = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            assert m.get("per_feature_corrective_cycles") == {}, m
            on_disk = lazy_core.read_run_marker(now=_time.time())
            assert on_disk.get("per_feature_corrective_cycles") == {}, on_disk
        finally:
            _clear_state_dir()




def test_budget_trip_signals_over_ceiling_defers():
    """P1 RED: effective_count >= ceiling AND NOT near_complete ⇒ should_defer
    True, reason over-ceiling."""
    _guard()
    r = lazy_core.budget_trip_signals(6, 0, 6, False)
    assert r["should_defer"] is True
    assert r["effective_count"] == 6
    assert r["reason"] == "over-ceiling"




def test_budget_trip_signals_near_complete_grace():
    """P1 RED: near_complete True ⇒ should_defer False even at/over ceiling
    (grace), reason near-complete-grace."""
    _guard()
    r = lazy_core.budget_trip_signals(6, 0, 6, True)
    assert r["should_defer"] is False
    assert r["effective_count"] == 6
    assert r["reason"] == "near-complete-grace"




def test_budget_trip_signals_corrective_discount():
    """P1 RED: corrective work is subtracted; effective_count < ceiling ⇒
    should_defer False, reason corrective-discount."""
    _guard()
    r = lazy_core.budget_trip_signals(8, 2, 6, False)
    assert r["effective_count"] == 6  # 8 - 2 = 6 >= ceiling → over-ceiling
    assert r["should_defer"] is True
    assert r["reason"] == "over-ceiling"
    # Now discount enough to drop below the ceiling.
    r = lazy_core.budget_trip_signals(7, 2, 6, False)
    assert r["effective_count"] == 5  # 7 - 2 = 5 < 6
    assert r["should_defer"] is False
    assert r["reason"] == "corrective-discount"




def test_budget_trip_signals_effective_count_clamped_at_zero():
    """P1 RED: corrective_count > forward_count clamps effective_count at 0."""
    _guard()
    r = lazy_core.budget_trip_signals(2, 5, 6, False)
    assert r["effective_count"] == 0
    assert r["should_defer"] is False




def test_budget_trip_signals_pure_no_io():
    """P1 RED: identical inputs → identical dict, repeatable (pure fn)."""
    _guard()
    a = lazy_core.budget_trip_signals(6, 1, 6, False)
    b = lazy_core.budget_trip_signals(6, 1, 6, False)
    assert a == b




# ---------------------------------------------------------------------------
# Tests: feature-budget-guard-and-skip-ahead Phase 3 — two-key readiness
#   predicates (Locked Decision 5).
#     parse_independent_marker(spec_text, queue_entry) -> bool
#       True for explicit `independent: true` in SPEC frontmatter OR queue entry;
#       True for the `no_shared_state: true` alias; False when absent (default).
#       Deterministic on-disk read; no LLM judgment.
#     skip_ahead_ready(deps, gated_ids, independent) -> bool
#       Two-key predicate: False if any HARD dep feature_id is in gated_ids;
#       else require `independent` truthy. soft/composes deps never block.
# ---------------------------------------------------------------------------


def test_parse_independent_marker_spec_frontmatter_true():
    """P3 RED: `independent: true` in the SPEC frontmatter → True."""
    _guard()
    spec = (
        "---\nindependent: true\n---\n\n# Spec\n\n**Status:** Draft\n"
    )
    assert lazy_core.parse_independent_marker(spec, {}) is True




def test_parse_independent_marker_queue_entry_true():
    """P3 RED: `independent: true` in the queue entry (no SPEC marker) → True."""
    _guard()
    spec = "# Spec\n\n**Status:** Draft\n"
    assert lazy_core.parse_independent_marker(spec, {"independent": True}) is True




def test_parse_independent_marker_no_shared_state_alias():
    """P3 RED: the `no_shared_state: true` alias (SPEC or queue) → True."""
    _guard()
    spec = "---\nno_shared_state: true\n---\n\n# Spec\n"
    assert lazy_core.parse_independent_marker(spec, {}) is True
    assert lazy_core.parse_independent_marker(
        "# Spec\n", {"no_shared_state": True}
    ) is True




def test_parse_independent_marker_absent_default_false():
    """P3 RED: no marker anywhere → False (the safe default)."""
    _guard()
    spec = "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n"
    assert lazy_core.parse_independent_marker(spec, {}) is False
    # An explicitly-false marker is also False (not just absent).
    assert lazy_core.parse_independent_marker(
        "---\nindependent: false\n---\n", {}
    ) is False




# ---------------------------------------------------------------------------
# Tests: loop-detected-false-positives-from-probe-and-reboot-churn
#   Phase 2 — resolution-aware step_count reset (symptom 3).
#
# WU-3: record_resolution_signal persists a one-shot run-marker field
#       (last_resolution_step_key = [feature_id, current_step]) at the
#       needs-input resolution dispatch bracket. update_repeat_counts keys on it.
# WU-4: a step_count reset branch in update_repeat_counts that fires ONCE across
#       a resolution meta-cycle (a dispatch lands between two same-step probes,
#       so the F2 consume-debounce does NOT hold) — resetting step_count to 1 and
#       clearing the signal (one-shot). Ordered AFTER the ordered-advance
#       exemption and BEFORE the F2 debounce branch.
# ---------------------------------------------------------------------------


def test_record_resolution_signal_persists_step_key():
    """WU-3: record_resolution_signal writes last_resolution_step_key =
    [feature_id, current_step] to the run marker and returns the updated marker.

    RED: record_resolution_signal missing on lazy_core → AttributeError.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            state = {
                "feature_id": "feat-res",
                "current_step": "Step 7a: execute plan",
            }
            updated = lazy_core.record_resolution_signal(state)
            assert updated is not None, (
                "record_resolution_signal must return the updated marker when a "
                "marker is present"
            )
            assert updated.get("last_resolution_step_key") == [
                "feat-res", "Step 7a: execute plan",
            ], (
                f"the resolution signal must persist the [feature_id, current_step] "
                f"step key, got {updated.get('last_resolution_step_key')!r}"
            )
            # Persisted to disk (re-read confirms it survives).
            marker_path = Path(td) / lazy_core._MARKER_FILENAME
            on_disk = json.loads(marker_path.read_text(encoding="utf-8"))
            assert on_disk.get("last_resolution_step_key") == [
                "feat-res", "Step 7a: execute plan",
            ], f"signal must be on disk, got {on_disk!r}"
        finally:
            _clear_state_dir()




def test_symptom3_resolution_reset():
    """WU-4 / SYMPTOM 3 (the residual fix): a needs-input resolution meta-cycle
    is an Agent dispatch (consume-count RISES), so the F2 debounce does NOT hold
    the step counter across it. Without the reset, step_repeat_count survives a
    LEGITIMATELY-resolved blocker and keeps marching toward LOOP-DETECTED.

    With the resolution signal recorded (record_resolution_signal) and the step
    signature unchanged across the resolution, step_repeat_count must RESET to 1.

    RED: pre-fix update_repeat_counts increments 1 → 2 here (a consume landed
    between the two same-step probes, so the F2 hold does not apply and there is
    no reset branch). GREEN: the new resolution-reset branch resets to 1.
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
        # First probe: establishes step_count = 1 for this step signature.
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        # A needs-input resolution meta-cycle runs: it is an Agent dispatch, so a
        # registry consume lands (the F2 debounce will NOT hold), AND the
        # resolution bracket records the signal keyed on this step signature.
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            lazy_core.record_resolution_signal(
                {"feature_id": _STATE_A["feature_id"],
                 "current_step": _STATE_A["current_step"]}
            )
            # Next probe: SAME step signature, a dispatch DID land between (so F2
            # cannot hold). The resolution signal must reset step_count to 1.
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 1, (
        f"a needs-input resolution between two same-step probes must RESET "
        f"step_repeat_count to 1 (the resolution is a legitimately-resolved "
        f"blocker, not oscillation), got {r2!r}"
    )




def test_symptom3_resolution_reset_is_one_shot():
    """WU-4: the resolution reset fires ONCE across the resolution — the signal is
    cleared after it is honored. A SUBSEQUENT same-step probe with a fresh
    dispatch (consume rises) and NO new resolution signal must INCREMENT (the
    reset does not latch and permanently suppress the tripwire).

    RED: an impl that left the signal asserted would reset on every subsequent
    probe, re-introducing the d8 HEAD-advance immunity for the resolved step.
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
        # Resolution meta-cycle: consume + signal.
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            lazy_core.record_resolution_signal(
                {"feature_id": _STATE_A["feature_id"],
                 "current_step": _STATE_A["current_step"]}
            )
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        # A FURTHER dispatch on the SAME step with NO new resolution signal → the
        # reset must NOT fire again (one-shot); step_count climbs.
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r3 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r2["step_repeat_count"] == 1, (
        f"resolution reset fires once → 1, got {r2!r}"
    )
    assert r3["step_repeat_count"] == 2, (
        f"the reset is ONE-SHOT — a subsequent same-step dispatch with no fresh "
        f"resolution signal must INCREMENT (1 → 2), not stay reset, got {r3!r}"
    )




def test_resolution_signal_no_repeat_count_reset_head_aware():
    """WU-4 / Open Question 2 confirmation: the resolution reset is
    step_repeat_count-ONLY. The HEAD-aware dispatch-tuple repeat_count already
    resets on its own when a resolution commits (HEAD advances), so no separate
    repeat_count reset is added — and a resolution that does NOT advance HEAD must
    leave repeat_count to its normal HEAD/debounce logic (the resolution signal
    must NOT touch repeat_count).

    This pins that record_resolution_signal + the reset branch leave repeat_count
    governed solely by its existing (head-aware + F1-debounce) path.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()  # non-git → current_head is None==None
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        # Resolution meta-cycle: consume + signal. HEAD does NOT advance (non-git
        # repo → head None both probes), so repeat_count is NOT reset by HEAD; the
        # consume rose so the F1 debounce does NOT hold → repeat_count increments.
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            lazy_core.record_resolution_signal(
                {"feature_id": _STATE_A["feature_id"],
                 "current_step": _STATE_A["current_step"]}
            )
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    # step_count reset by the resolution branch...
    assert r2["step_repeat_count"] == 1, (
        f"resolution reset applies to step_repeat_count, got {r2!r}"
    )
    # ...but repeat_count is untouched by the resolution signal: a real dispatch
    # landed (consume rose) with the same tuple + same (None) head → it increments
    # per its existing F1 logic. The resolution signal must NOT spuriously reset it.
    assert r2["repeat_count"] == 2, (
        f"the resolution signal must NOT reset the HEAD-aware repeat_count — with a "
        f"dispatch landed (consume rose), same tuple, same head, it follows its "
        f"existing increment path (1 → 2), got {r2!r}"
    )




# ---------------------------------------------------------------------------
# Tests: loop-detected-false-positives-from-probe-and-reboot-churn
#   Phase 3 — NEGATIVE fixtures. Prove the Phase-2 resolution reset did NOT
#   re-introduce HEAD-advance immunity for the general oscillation case, and that
#   the reset is strictly SIGNAL-GATED (never fires on a missing/legacy signal).
# ---------------------------------------------------------------------------


def test_symptom5_d8_commit_masked_loop_still_trips():
    """SYMPTOM 5 / d8 design constraint (Proven Finding 3): a genuine
    commit-masked oscillation loop — SAME (feature_id, current_step), HEAD
    ADVANCING each iteration (each spurious cycle commits a file → the
    dispatch-tuple repeat_count resets every iteration and never catches the
    loop), with NO resolution signal present — must STILL inflate
    step_repeat_count and reach the >=3 tripwire.

    This is the inverse of the Phase-2 positive fixture: it asserts the
    resolution-reset branch is NOT taken when there is no signal, so the
    HEAD-blind masking detection the step counter exists for is preserved.

    RED for the Phase-2 fix done wrong: if the reset fired without a signal (or
    keyed on HEAD/commits), this would stay flat at 1 and the loop would go
    undetected.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # A real git repo so HEAD advances on each commit; a run marker present
        # (so the reset branch's machinery is fully active) but NO resolution
        # signal is ever recorded — the discriminator must keep the loop tripping.
        repo_root, _origin = _make_git_repo_with_origin(str(td_path))
        _write_marker_in(state_dir, repo_root)
        state = {
            "feature_id": "d8-stuck",
            "sub_skill": "/write-plan",
            "sub_skill_args": "plan.md",          # UNCHANGED across all repeats
            "current_step": "Step 7a: execute plan",
        }
        step_counts = []
        for i in range(4):
            _set_state_dir(state_dir)
            try:
                r = lazy_core.update_repeat_counts(repo_root, state, signature_path=sig_path)
            finally:
                _clear_state_dir()
            step_counts.append(r["step_repeat_count"])
            # Each oscillation cycle COMMITS (HEAD advances) AND a dispatch lands
            # (a real consume) — exactly the d8 masking signature, but with NO
            # resolution signal: the reset must NOT fire.
            _commit_dummy(repo_root, f"osc-{i}.txt")
            _record_consume(state_dir)
    assert step_counts == [1, 2, 3, 4], (
        f"a commit-masked oscillation loop with NO resolution signal must keep "
        f"climbing step_repeat_count (the reset branch is NOT taken — HEAD-advance "
        f"immunity is preserved), got {step_counts!r}"
    )
    assert max(step_counts) >= 3, (
        f"the >=3 oscillation tripwire MUST still fire for the d8 commit-masked "
        f"loop after the Phase-2 resolution reset, got {step_counts!r}"
    )




def test_resolution_reset_inert_without_signal():
    """The resolution reset is SIGNAL-GATED — a marked probe with the resolution
    signal ABSENT (a normal/legacy marker that never recorded
    last_resolution_step_key) and an unchanged step signature must follow the
    NORMAL path (here: a dispatch landed between the probes → increment), NOT the
    reset path. Mirrors the ordered-advance "known prior" guard discipline: the
    reset never fires on a missing signal.

    RED: an impl that reset whenever the marker was merely present (not gated on
    the recorded signal) would hold/reset here.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Marker present, but NO record_resolution_signal call — the signal is
        # absent (the normal-cycle case).
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
        # A real dispatch lands between the two same-step probes (consume rises),
        # so the F2 debounce can NOT hold — and with NO resolution signal, the
        # reset must NOT fire either → the counter increments normally.
        _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"with the resolution signal ABSENT and a dispatch landed between the two "
        f"same-step probes, the reset must NOT fire (signal-gated) → step_count "
        f"increments normally (1 → 2), got {r2!r}"
    )




# ---------------------------------------------------------------------------
# cycle-subagent-fabricates-policy-or-stray-branch — Phase 2
#   marker work_branch field + lazy_core read helper (WU-2)
#   --marker-work-branch CLI query on lazy-state.py + bug-state.py (WU-3)
#
# The marker did NOT carry a work_branch until this fix. The Phase-3 write-time
# stray-branch hook needs a reference branch to compare HEAD against; Python owns
# branch identity (same contract as --marker-present), so the marker captures it
# at run-start and a read-only CLI query exposes it.
# ---------------------------------------------------------------------------


def test_marker_work_branch_field_written(_real_time=None):
    """write_run_marker stamps a `work_branch` field, resolved via
    _emit_work_branch on the marker's repo_root. RED before the field exists."""
    import time as _t
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "wb-state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            marker = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td,
                max_cycles=5, now=_t.time(),
            )
            assert "work_branch" in marker, (
                "write_run_marker must stamp a work_branch field "
                f"(keys: {sorted(marker)})"
            )
            # _emit_work_branch on a non-git temp dir returns the documented
            # fallback string — non-empty, never a crash.
            assert isinstance(marker["work_branch"], str) and marker["work_branch"], (
                f"work_branch must be a non-empty str, got {marker['work_branch']!r}"
            )
            # The on-disk marker JSON carries the same value.
            on_disk = lazy_core.read_run_marker(now=_t.time())
            assert on_disk is not None and on_disk.get("work_branch") == marker["work_branch"], (
                "read_run_marker must echo the stamped work_branch"
            )
        finally:
            _clear_state_dir()




def test_marker_work_branch_helper_reads_value():
    """lazy_core.marker_work_branch() returns the marker's work_branch."""
    import time as _t
    assert hasattr(lazy_core, "marker_work_branch"), (
        "lazy_core.marker_work_branch read helper is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "wb-helper-state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            written = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td,
                max_cycles=5, now=_t.time(),
            )
            got = lazy_core.marker_work_branch(now=_t.time())
            assert got == written["work_branch"], (
                f"helper returned {got!r}, expected {written['work_branch']!r}"
            )
        finally:
            _clear_state_dir()




def test_marker_work_branch_helper_legacy_marker_returns_none():
    """A legacy marker dict lacking work_branch → helper returns None (no KeyError)."""
    import time as _t
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "wb-legacy-state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            written = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td,
                max_cycles=5, now=_t.time(),
            )
            # Simulate a legacy marker: strip the field on disk.
            marker_path = state_dir / "lazy-run-marker.json"
            data = json.loads(marker_path.read_text(encoding="utf-8"))
            data.pop("work_branch", None)
            marker_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
            got = lazy_core.marker_work_branch(now=_t.time())
            assert got is None, f"legacy marker must yield None, got {got!r}"
        finally:
            _clear_state_dir()




def test_marker_work_branch_helper_no_marker_returns_none():
    """No marker present → helper returns None (no crash)."""
    import time as _t
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "wb-absent-state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            got = lazy_core.marker_work_branch(now=_t.time())
            assert got is None, f"absent marker must yield None, got {got!r}"
        finally:
            _clear_state_dir()




def _run_marker_work_branch_cli(script_name: str):
    """Shared body: --marker-work-branch on the named state script (parity).

    Writes a marker carrying a known work_branch in-process (hermetic, no real
    git), then runs the script's --marker-work-branch and asserts present/absent/
    legacy/read-only behavior.
    """
    import time as _t
    script = _SCRIPTS_DIR / script_name
    assert script.exists(), f"{script_name} missing"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "cli-state"
        # NOTE: do NOT mkdir state_dir — the read-only probe must not create it.
        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(script)] + args,
                capture_output=True, text=True, env=env,
            )

        # (a) ABSENT marker → exit 1, no stdout branch, and the read-only probe
        #     must NOT create the state dir.
        r = run(["--repo-root", str(repo_root), "--marker-work-branch"])
        assert r.returncode == 1, (
            f"{script_name} --marker-work-branch with no marker must exit 1, "
            f"got {r.returncode}; stderr={r.stderr[:300]!r}"
        )
        assert not state_dir.exists(), (
            "an absent --marker-work-branch probe must not create the state dir "
            "(read-only invariant)"
        )

        # Now write a marker carrying a known work_branch (in-process).
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline=("bug" if "bug" in script_name else "feature"),
                cloud=False, repo_root=str(repo_root),
                max_cycles=5, now=_t.time(),
            )
            # Force a deterministic, recognizable branch value on disk.
            marker_path = state_dir / "lazy-run-marker.json"
            data = json.loads(marker_path.read_text(encoding="utf-8"))
            data["work_branch"] = "main"
            marker_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        finally:
            _clear_state_dir()

        # (b) PRESENT marker with branch → exit 0, prints the branch.
        r = run(["--repo-root", str(repo_root), "--marker-work-branch"])
        assert r.returncode == 0, (
            f"{script_name} --marker-work-branch with a live marker must exit 0, "
            f"got {r.returncode}; stderr={r.stderr[:300]!r}"
        )
        assert r.stdout.strip() == "main", (
            f"{script_name} must print the stored work_branch 'main', "
            f"got {r.stdout!r}"
        )

        # (c) LEGACY marker (no work_branch field) → exit 1, no crash.
        marker_path = state_dir / "lazy-run-marker.json"
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        data.pop("work_branch", None)
        marker_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        r = run(["--repo-root", str(repo_root), "--marker-work-branch"])
        assert r.returncode == 1, (
            f"{script_name} --marker-work-branch on a legacy marker must exit 1, "
            f"got {r.returncode}; stderr={r.stderr[:300]!r}"
        )




def test_marker_work_branch_cli_lazy_state():
    """lazy-state.py --marker-work-branch: present/absent/legacy/read-only."""
    _run_marker_work_branch_cli("lazy-state.py")




def test_marker_work_branch_cli_bug_state_parity():
    """bug-state.py --marker-work-branch behaves identically (parity)."""
    _run_marker_work_branch_cli("bug-state.py")




# ---------------------------------------------------------------------------
# single-slot-marker-ownership-race-disarms-owning-run
#   Phase 1 — run-start owner bind (close the bind-pending window)
#   Phase 2 — owner-side detect + re-arm backstop
#
# Hermetic fixtures over the real write_run_marker / read_run_marker /
# bind_marker_session / marker_owner_status / reassert_marker_owner producers,
# using the existing _set_state_dir temp-dir override (no mocks beyond it).
# The wrong-bind ordering is injected directly (call bind_marker_session(foreign)
# after the owner-bound run-start) — a deterministic stand-in for the real race.
# ---------------------------------------------------------------------------


def test_run_start_owner_bind_closes_repro_a():
    """Repro A closed: a marker born owner-bound survives a foreign bind.

    write_run_marker(session_id="OWNER") then bind_marker_session("FOREIGN")
    returns False (already bound) AND the on-disk session_id is STILL "OWNER";
    read_run_marker(session_id="OWNER") returns the marker (owner is NOT
    disarmed). Pre-fix the run-start wrote session_id=None, letting the foreign
    bind win — this fixture is RED against that code.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="OWNER", now=_t.time(),
            )
            # A concurrent non-owner reaches bind_marker_session BEFORE any
            # owner allow. The slot was never None → first-writer-wins protects
            # the CORRECT owner: the foreign bind is refused.
            bound = lazy_core._monolith.bind_marker_session("FOREIGN")
            assert bound is False, (
                "a foreign bind against an owner-bound marker must be refused "
                "(first-writer-wins now protects the correct owner)"
            )
            marker_path = Path(td) / "lazy-run-marker.json"
            data = json.loads(marker_path.read_text(encoding="utf-8"))
            assert data["session_id"] == "OWNER", (
                f"the slot must STILL hold the owner, got {data['session_id']!r}"
            )
            # The owner reads its OWN run successfully (path B does not disarm it).
            m = lazy_core.read_run_marker(session_id="OWNER")
            assert m is not None and m["session_id"] == "OWNER", (
                "the owner must read its own marker — not be silently disarmed"
            )
        finally:
            _clear_state_dir()




def test_run_start_legacy_unbound_preserved():
    """Legacy unbound preserved: no session_id → bind-pending, foreign bind wins.

    write_run_marker() with NO session_id still writes session_id=None, and a
    subsequent bind_marker_session("FOREIGN") returns True (the documented legacy
    bind path). Proves the Phase-1 fix is additive, not a silent semantic change
    for the no-`--session-id` caller.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=_t.time(),
            )
            marker_path = Path(td) / "lazy-run-marker.json"
            data = json.loads(marker_path.read_text(encoding="utf-8"))
            assert data["session_id"] is None, (
                "legacy run-start (no session_id) must still write None "
                "(bind-pending), preserving the documented legacy path"
            )
            bound = lazy_core._monolith.bind_marker_session("FOREIGN")
            assert bound is True, (
                "the legacy bind-pending path must still allow the first bind"
            )
        finally:
            _clear_state_dir()




def test_run_start_cli_threads_session_id_lazy_state():
    """lazy-state.py --run-start --session-id OWNER writes an owner-bound marker."""
    _run_start_cli_owner_bind("lazy-state.py", "feature")




def test_run_start_cli_threads_session_id_bug_state_parity():
    """bug-state.py --run-start --session-id OWNER writes an owner-bound marker."""
    _run_start_cli_owner_bind("bug-state.py", "bug")




def _run_start_cli_owner_bind(script_name: str, pipeline: str) -> None:
    """The --run-start CLI handler threads --session-id into the marker (coupled
    pair). With --session-id the on-disk marker is born owner-bound; without it
    the marker stays bind-pending (session_id=None)."""
    _guard()
    script = _SCRIPTS_DIR / script_name
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "cli-state"
        state_dir.mkdir()
        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        # Orchestrator immunity so --run-start's refuse_if_cycle_active does not
        # trip on any ambient marker.
        env["LAZY_ORCHESTRATOR"] = "1"

        r = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root),
             "--run-start", "--session-id", "OWNER"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, (
            f"{script_name} --run-start --session-id must exit 0, got "
            f"{r.returncode}; stderr={r.stderr[:300]!r}"
        )
        marker_path = state_dir / "lazy-run-marker.json"
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "OWNER", (
            f"{script_name} --run-start must thread --session-id into the marker; "
            f"got session_id={data.get('session_id')!r}"
        )
        assert data["pipeline"] == pipeline, data.get("pipeline")




# --- Phase 2: detect + re-arm helpers --------------------------------------


def test_marker_owner_status_detect_three_way():
    """marker_owner_status returns absent / owned-by-me / foreign-stamped and is
    NON-destructive on foreign-stamped (the file survives the call)."""
    _guard()
    now = _t.time()
    # (a) absent — no marker at all.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.marker_owner_status("OWNER", now=now) == "absent"
        finally:
            _clear_state_dir()
    # (b) absent — age-stale marker (older than the 24h staleness window).
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            stale_now = now - (48 * 3600)
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="FOREIGN", now=stale_now,
            )
            assert lazy_core.marker_owner_status("OWNER", now=now) == "absent", (
                "a stale foreign marker must read as absent, not foreign-stamped"
            )
        finally:
            _clear_state_dir()
    # (c) owned-by-me — bind-pending (session_id None) reads as the owner's.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=now,
            )
            assert lazy_core.marker_owner_status("OWNER", now=now) == "owned-by-me"
        finally:
            _clear_state_dir()
    # (d) owned-by-me — slot equals the caller.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="OWNER", now=now,
            )
            assert lazy_core.marker_owner_status("OWNER", now=now) == "owned-by-me"
        finally:
            _clear_state_dir()
    # (e) foreign-stamped — live marker, non-None foreign session; NON-destructive.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="FOREIGN", now=now,
            )
            assert lazy_core.marker_owner_status("OWNER", now=now) == "foreign-stamped"
            marker_path = Path(td) / "lazy-run-marker.json"
            assert marker_path.exists(), (
                "marker_owner_status must NOT delete the marker on foreign-stamped "
                "(non-destructive — re-introducing delete here is the silent disarm)"
            )
        finally:
            _clear_state_dir()




def test_reassert_marker_owner_re_arms_foreign_stamped():
    """reassert_marker_owner re-claims a foreign-stamped slot, is idempotent, and
    is a no-op on absent / owned-by-me."""
    _guard()
    now = _t.time()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="FOREIGN", now=now,
            )
            # First re-arm: foreign-stamped → re-claim, return True.
            assert lazy_core.reassert_marker_owner("OWNER", now=now) is True
            marker_path = Path(td) / "lazy-run-marker.json"
            data = json.loads(marker_path.read_text(encoding="utf-8"))
            assert data["session_id"] == "OWNER", (
                f"re-arm must re-stamp the slot to the owner; got "
                f"{data['session_id']!r}"
            )
            # Second call: now owned-by-me → no-op, return False (idempotent).
            assert lazy_core.reassert_marker_owner("OWNER", now=now) is False
            assert marker_path.exists()
        finally:
            _clear_state_dir()
    # absent → no-op, False.
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.reassert_marker_owner("OWNER", now=now) is False
        finally:
            _clear_state_dir()




def test_reassert_marker_owner_repro_b_resume_owner_bound():
    """Repro B closed: a checkpoint-resume --run-start carrying a session_id is
    owner-bound (the resume window no longer re-opens for an owner that passes
    --session-id). Simulated via write_run_checkpoint / consume_run_checkpoint
    then write_run_marker(session_id=owner)."""
    _guard()
    now = _t.time()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Live run, then checkpoint it (the pause).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="OWNER", now=now,
            )
            lazy_core.write_run_checkpoint(
                "Step 7a: execute plan",
                {"forward_cycles": 3, "meta_cycles": 1, "max_cycles": 20},
            )
            consumed = lazy_core.consume_run_checkpoint()
            assert consumed is not None, "checkpoint must be consumable on resume"
            # Resume --run-start re-writes the marker WITH the owner session_id.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                session_id="OWNER", now=now,
            )
            assert lazy_core.marker_owner_status("OWNER", now=now) == "owned-by-me", (
                "a resumed run that carries --session-id is owner-bound — the "
                "Repro-B re-bind window no longer re-opens"
            )
        finally:
            _clear_state_dir()




def test_legacy_disarm_detected_and_re_armed():
    """The legacy path (run-start with NO session_id → bind-pending → foreign bind
    wins) is DETECTED as foreign-stamped and RE-ARMED — proving Phase 2 backstops
    the path Phase 1 leaves open."""
    _guard()
    now = _t.time()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Legacy run-start: bind-pending.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=now,
            )
            # A foreign session wins the bind in the open window.
            assert lazy_core._monolith.bind_marker_session("FOREIGN") is True
            # The true owner can SEE the wrong stamp (not just "absent").
            assert lazy_core.marker_owner_status("OWNER", now=now) == "foreign-stamped"
            # And re-claim it.
            assert lazy_core.reassert_marker_owner("OWNER", now=now) is True
            assert lazy_core.marker_owner_status("OWNER", now=now) == "owned-by-me"
        finally:
            _clear_state_dir()




def _run_cycle_end_records_bracket_cli(script_name: str, id_flag: str):
    """Shared body: the --cycle-end handler records the bracket AND clears the
    marker (coupled pair — both state scripts)."""
    script = _SCRIPTS_DIR / script_name
    assert script.exists(), f"{script_name} missing"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo = td_path / "repo"
        repo.mkdir()
        _prov_git_fixture_repo(repo)
        state_dir = td_path / "state"
        state_dir.mkdir()
        env = {k: v for k, v in _os_env.environ.items()
               if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
        env["LAZY_STATE_DIR"] = str(state_dir)
        env["LAZY_ORCHESTRATOR"] = "1"

        def run(args):
            return subprocess.run(
                [sys.executable, str(script)] + args,
                capture_output=True, text=True, env=env,
            )

        # --cycle-begin --kind real (the default) now REQUIRES --sub-skill
        # (cycle-begin-real-requires-sub-skill) — pass one like a real
        # orchestrator dispatch does.
        r = run(["--cycle-begin", id_flag, "feat-cli-br", "--nonce", "cafe",
                 "--sub-skill", "execute-plan", "--repo-root", str(repo)])
        assert r.returncode == 0, f"--cycle-begin failed: {r.stderr[:300]}"
        end = _prov_git_commit_file(repo, "src/b.py", "cycle work")
        r = run(["--cycle-end", "--repo-root", str(repo)])
        assert r.returncode == 0, f"--cycle-end failed: {r.stderr[:300]}"
        out = json.loads(r.stdout)
        assert out.get("cycle_marker_cleared") is True
        # The bracket landed in the ledger with the cycle's HEAD advance.
        ledger = state_dir / "lazy-commit-brackets.jsonl"
        assert ledger.exists(), (
            f"{script_name} --cycle-end must append the commit bracket"
        )
        entries = [json.loads(ln) for ln in
                   ledger.read_text(encoding="utf-8").strip().splitlines()]
        assert any(
            e.get("feature_id") == "feat-cli-br" and e.get("end_sha") == end
            for e in entries
        ), f"bracket for feat-cli-br/{end[:8]} not found: {entries}"




def test_cycle_end_records_bracket_cli_lazy_state():
    """lazy-state.py --cycle-end appends the cycle's commit bracket."""
    _guard()
    _run_cycle_end_records_bracket_cli("lazy-state.py", "--feature-id")




def test_cycle_end_records_bracket_cli_bug_state_parity():
    """bug-state.py --cycle-end appends the bracket identically (parity)."""
    _guard()
    _run_cycle_end_records_bracket_cli("bug-state.py", "--bug-id")




# parallel-worktree-batch-execution Phase 2 — the `parent_run` lane-marker
# identity field (D2-A) + per-worktree repo_key isolation.
#
# A lane marker is an ordinary run marker written at a WORKTREE root, born
# owner-bound to the coordinator session, additionally carrying
# `parent_run: {repo_root, started_at}` so audits (and --run-end sweeps) can
# prove the marker sanctioned.  The field is run-invariant identity re-derived
# at run-start ⇒ classified into RUN_FRESH_FIELDS — the continuity-partition
# completeness test (above) is the designed tripwire that FAILS the moment the
# marker gains the key until this classification lands.
# ---------------------------------------------------------------------------

def test_write_run_marker_parent_run_default_none_and_explicit():
    """`write_run_marker` ALWAYS mints the `parent_run` key: None on a serial
    run (byte-shape stability — the partition helper sees the key), the caller's
    identity dict verbatim on a lane run; the on-disk marker matches."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            serial = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=0.0,
            )
            assert "parent_run" in serial, "key must ALWAYS be minted"
            assert serial["parent_run"] is None, "serial run ⇒ parent_run: null"
            identity = {"repo_root": "/main", "started_at": "2026-07-04T00:00:00Z"}
            lane = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/main-lanes/wt-00",
                session_id="coordinator-session", parent_run=identity, now=0.0,
            )
            assert lane["parent_run"] == identity
            on_disk = json.loads(
                (Path(td) / "lazy-run-marker.json").read_text(encoding="utf-8")
            )
            assert on_disk["parent_run"] == identity
            assert on_disk["session_id"] == "coordinator-session", (
                "lane marker is born owner-bound to the coordinator session"
            )
        finally:
            _clear_state_dir()




def test_parent_run_classified_into_run_fresh_fields():
    """`parent_run` is run-invariant identity re-derived at run-start ⇒ it MUST
    be classified into RUN_FRESH_FIELDS (never carried by a checkpoint resume —
    the resuming --run-start re-supplies it), keeping the completeness partition
    green with the new key."""
    _guard()
    assert "parent_run" in lazy_core.RUN_FRESH_FIELDS
    assert "parent_run" not in lazy_core.RUN_CONTINUITY_FIELDS




def test_write_cycle_marker_stamps_subagent_model():
    """--cycle-begin's marker write copies the skill capability: a flagged
    sub_skill stamps subagent_model=True, an unflagged one False, and an
    explicit override wins over the computed value."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            m = lazy_core.write_cycle_marker(
                feature_id="f", nonce="a1", sub_skill="execute-plan"
            )
            assert m["subagent_model"] is True, m
            on_disk = json.loads(
                (Path(td) / _CYCLE_MARKER_FILENAME).read_text(encoding="utf-8")
            )
            assert on_disk["subagent_model"] is True, on_disk
            m2 = lazy_core.write_cycle_marker(
                feature_id="f", nonce="a2", sub_skill="realign-spec"
            )
            assert m2["subagent_model"] is False, m2
            # Explicit override wins (tests / emergency escape hatch).
            m3 = lazy_core.write_cycle_marker(
                feature_id="f", nonce="a3", sub_skill="realign-spec",
                subagent_model=True,
            )
            assert m3["subagent_model"] is True, m3
            # Meta/pseudo dispatches never stamp the capability.
            m4 = lazy_core.write_cycle_marker(
                feature_id="f", nonce="a4", kind="meta",
                sub_skill="__mark_complete__",
            )
            assert m4["subagent_model"] is False, m4
        finally:
            _clear_state_dir()




def test_write_cycle_marker_rebinds_nonce_for_subagent_model():
    """The consumed-fence wiring fix at the write site: a subagent-model cycle
    written with a FRESH (unregistered) --nonce has its marker nonce rebound to
    this cycle's worker emission so the guard exemption's nonce-exact fence can
    match it; a non-subagent-model cycle keeps the passed nonce byte-identically."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            entry = lazy_core.register_emission("cycle prompt body", "cycle")
            emission_nonce = entry["nonce"]
            # Production order: emission registered + UNCONSUMED at --cycle-begin.
            m = lazy_core.write_cycle_marker(
                feature_id="f", nonce="deadfreshbeef", sub_skill="execute-plan",
            )
            assert m["subagent_model"] is True, m
            assert m["nonce"] == emission_nonce, (
                "subagent-model marker must rebind a fresh nonce to the cycle "
                f"worker emission; got {m['nonce']!r}"
            )
            # A non-subagent-model cycle keeps the passed nonce untouched (zero
            # behavior change off the exemption path).
            m2 = lazy_core.write_cycle_marker(
                feature_id="f", nonce="keepme123", sub_skill="realign-spec",
            )
            assert m2["subagent_model"] is False, m2
            assert m2["nonce"] == "keepme123", m2
        finally:
            _clear_state_dir()




def test_run_end_unacked_hardening_refusal_emits_gate_refusal_lazy():
    """lazy-state.py --run-end with pending unacked hardening debt refuses
    (exit 1, marker kept) AND appends gate=unacked-hardening."""
    _assert_run_end_refusal_emits(
        "lazy-state.py", "feature", [], seed_deny=True,
        expected_gate="unacked-hardening",
    )




def test_run_end_checkpoint_auth_refusal_emits_gate_refusal_lazy():
    """lazy-state.py --run-end --reason checkpoint on an attended run without
    --operator-authorized (gates 1 & 2 cleared) refuses AND appends
    gate=checkpoint-auth."""
    _assert_run_end_refusal_emits(
        "lazy-state.py", "feature",
        ["--reason", "checkpoint", "--efficacy-skip-authorized"],
        seed_deny=False, expected_gate="checkpoint-auth",
    )




def test_run_end_checkpoint_auth_refusal_emits_gate_refusal_bug():
    """bug-state.py mirror of the checkpoint-auth refusal emission."""
    _assert_run_end_refusal_emits(
        "bug-state.py", "bug",
        ["--reason", "checkpoint", "--efficacy-skip-authorized"],
        seed_deny=False, expected_gate="checkpoint-auth",
    )




def test_no_bare_production_sentinel_writes():
    """Self-checking meta-test: the LIVE production regions of lazy-state.py,
    bug-state.py, and lazy_core.py carry ZERO bare ``.write_text(``/
    ``open(..., "w")`` calls — every production sentinel/queue/doc write goes
    through ``lazy_core._monolith._atomic_write`` (production-sentinel-writes-bypass-
    atomic-write). GREEN today (the sweep this bug performed: `_write_yaml_
    sentinel`/`_write_yaml_blocked_sentinel` in both state scripts,
    `_write_step10_needs_input`, the ROADMAP append, the ad-hoc brief/spec
    writes). FAILS — naming the file + line — if a future production write
    bypasses `_atomic_write`.
    """
    _guard()
    scripts_dir = Path(__file__).resolve().parents[2]
    lazy_core_dir = scripts_dir / "lazy_core"
    # lazy-core-package-decomposition WU-1: lazy_core.py moved into the
    # lazy_core/ package (lazy_core/_monolith.py + lazy_core/__init__.py); every
    # module in that package is checked under the SAME "lazy_core.py" exempt-
    # region marker key (Phase 1 has no exempt region there — production-scoped).
    module_paths = [(p, "lazy_core.py") for p in sorted(lazy_core_dir.glob("*.py"))]
    for filename in ("lazy-state.py", "bug-state.py"):
        module_paths.append((scripts_dir / filename, filename))
    for path, marker_key in module_paths:
        source = path.read_text(encoding="utf-8")
        hits = _collect_bare_production_writes(source, marker_key)
        assert hits == [], (
            f"{path.name}: bare production write(s) bypassing _atomic_write: "
            f"{hits} — route through lazy_core._monolith._atomic_write instead"
        )




def test_bare_write_lint_guard_detects_planted_violation():
    """Negative fixture — non-vacuity proof: a synthetic 'lazy-state.py' source
    with a bare `path.write_text(...)` call BEFORE the fixture-region marker
    must be CAUGHT (by line), and a sibling call AFTER the marker (inside the
    designated fixture region) must NOT be — proving the collector is scoped,
    not a blanket ban."""
    _guard()
    synthetic_source = (
        "def production_writer(path, text):\n"
        "    path.write_text(text, encoding='utf-8')\n"  # line 2 — production, BAD
        "\n"
        "# Fixture smoke tests\n"                          # line 4 — the marker
        "\n"
        "def _build_fixture(path, text):\n"
        "    path.write_text(text, encoding='utf-8')\n"    # line 7 — fixture, OK
    )
    hits = _collect_bare_production_writes(synthetic_source, "lazy-state.py")
    assert hits == [(2, "write_text")], (
        f"expected exactly the production-region bare write at line 2 to be "
        f"caught, and the fixture-region one at line 7 to be exempt; got {hits}"
    )




def test_ctx_mutation_visible_through_facade():
    """A mutation via any one view of _DIAGNOSTICS must be visible through
    every other view, and clear_diagnostics() must clear the SAME object IN
    PLACE (never rebind a fresh empty list) — verified by asserting the
    list's identity survives the clear."""
    _guard()
    marker = f"__wu2_ctx_marker_{id(object())}__"
    lazy_core._DIAGNOSTICS.append(marker)
    try:
        assert marker in lazy_core._ctx._DIAGNOSTICS, (
            "append via lazy_core._DIAGNOSTICS not visible via "
            "lazy_core._ctx._DIAGNOSTICS"
        )
        assert marker in lazy_core._monolith._DIAGNOSTICS, (
            "append via lazy_core._DIAGNOSTICS not visible via "
            "lazy_core._monolith._DIAGNOSTICS"
        )
        original_id = id(lazy_core._DIAGNOSTICS)
        lazy_core.clear_diagnostics()
        assert lazy_core._DIAGNOSTICS == [], "facade view not cleared"
        assert lazy_core._ctx._DIAGNOSTICS == [], "_ctx view not cleared"
        assert lazy_core._monolith._DIAGNOSTICS == [], "_monolith view not cleared"
        assert id(lazy_core._DIAGNOSTICS) == original_id, (
            "clear_diagnostics() must clear the list IN PLACE (.clear()), not "
            "rebind a fresh list — the three views would silently diverge on "
            "a rebind"
        )
    finally:
        # Best-effort cleanup regardless of where the assertions above failed
        # (or whether _ctx raised before any assertion ran).
        lazy_core._monolith._DIAGNOSTICS.clear()


_TESTS = [
    ("test_lazy_state_test_output_matches_baseline", test_lazy_state_test_output_matches_baseline),
    ("test_bug_state_test_output_matches_baseline", test_bug_state_test_output_matches_baseline),
    ("test_update_repeat_counts_debounce_holds_step_count_no_consume_between", test_update_repeat_counts_debounce_holds_step_count_no_consume_between),
    ("test_update_repeat_counts_debounce_increments_with_consume_between", test_update_repeat_counts_debounce_increments_with_consume_between),
    ("test_update_repeat_counts_debounce_inert_for_foreign_repo_marker", test_update_repeat_counts_debounce_inert_for_foreign_repo_marker),
    ("test_update_repeat_counts_debounce_inert_without_marker", test_update_repeat_counts_debounce_inert_without_marker),
    ("test_gap_b_cross_run_streak_resets_on_different_run_identity", test_gap_b_cross_run_streak_resets_on_different_run_identity),
    ("test_gap_b_same_run_streak_still_accumulates", test_gap_b_same_run_streak_still_accumulates),
    ("test_gap_b_legacy_record_without_run_identity_is_not_treated_as_foreign", test_gap_b_legacy_record_without_run_identity_is_not_treated_as_foreign),
    ("test_rebaseline_loop_signature_noop_when_absent_or_no_marker", test_rebaseline_loop_signature_noop_when_absent_or_no_marker),
    ("test_f1_repeat_count_debounce_holds_no_consume_between", test_f1_repeat_count_debounce_holds_no_consume_between),
    ("test_f1_repeat_count_debounce_increments_with_consume_between", test_f1_repeat_count_debounce_increments_with_consume_between),
    ("test_f1_repeat_count_debounce_inert_without_marker", test_f1_repeat_count_debounce_inert_without_marker),
    ("test_symptom2_reboot_reprobe_no_inflation", test_symptom2_reboot_reprobe_no_inflation),
    ("test_symptom4_double_probe_hygiene_no_inflation", test_symptom4_double_probe_hygiene_no_inflation),
    ("test_phase7_symbols_present", test_phase7_symbols_present),
    ("test_guard_deny_writes_ledger_entry", test_guard_deny_writes_ledger_entry),
    ("test_execute_plan_commit_budget_scales_with_phase_count", test_execute_plan_commit_budget_scales_with_phase_count),
    ("test_execute_plan_commit_budget_scales_with_wu_count", test_execute_plan_commit_budget_scales_with_wu_count),
    ("test_execute_plan_commit_budget_absorbs_bookend_status_flips", test_execute_plan_commit_budget_absorbs_bookend_status_flips),
    ("test_checkpoint_round_trip", test_checkpoint_round_trip),
    ("test_write_run_checkpoint_persists_operator_authorized", test_write_run_checkpoint_persists_operator_authorized),
    ("test_run_end_checkpoint_threads_operator_authorized", test_run_end_checkpoint_threads_operator_authorized),
    ("test_restore_checkpoint_counters_carries_forward", test_restore_checkpoint_counters_carries_forward),
    ("test_restore_checkpoint_counters_carries_forward_run_identity", test_restore_checkpoint_counters_carries_forward_run_identity),
    ("test_restore_checkpoint_counters_no_checkpoint_is_noop", test_restore_checkpoint_counters_no_checkpoint_is_noop),
    ("test_restore_checkpoint_counters_operator_authorized_resets", test_restore_checkpoint_counters_operator_authorized_resets),
    ("test_restore_checkpoint_counters_legacy_file_carries_forward", test_restore_checkpoint_counters_legacy_file_carries_forward),
    ("test_restore_checkpoint_counters_coerces_garbage_counts", test_restore_checkpoint_counters_coerces_garbage_counts),
    ("test_run_marker_continuity_partition_is_complete_and_disjoint", test_run_marker_continuity_partition_is_complete_and_disjoint),
    ("test_run_marker_continuity_partition_helper_matches_literal", test_run_marker_continuity_partition_helper_matches_literal),
    ("test_run_marker_partition_guard_rejects_unclassified_new_field", test_run_marker_partition_guard_rejects_unclassified_new_field),
    ("test_write_run_checkpoint_snapshots_full_continuity_block", test_write_run_checkpoint_snapshots_full_continuity_block),
    ("test_write_run_checkpoint_raw_read_non_destructive_on_stale_marker", test_write_run_checkpoint_raw_read_non_destructive_on_stale_marker),
    ("test_restore_checkpoint_counters_restores_full_continuity_block", test_restore_checkpoint_counters_restores_full_continuity_block),
    ("test_restore_full_continuity_block_age_gate_preserved", test_restore_full_continuity_block_age_gate_preserved),
    ("test_restore_full_continuity_block_operator_authorized_no_op", test_restore_full_continuity_block_operator_authorized_no_op),
    ("test_restore_legacy_flat_checkpoint_still_restores_identity", test_restore_legacy_flat_checkpoint_still_restores_identity),
    ("test_checkpoint_full_round_trip_continuity_survives", test_checkpoint_full_round_trip_continuity_survives),
    ("test_marker_advance_round_trips_counters_under_rmw", test_marker_advance_round_trips_counters_under_rmw),
    ("test_checkpoint_resume_preserves_counters_e2e", test_checkpoint_resume_preserves_counters_e2e),
    ("test_operator_authorized_checkpoint_resume_resets_e2e", test_operator_authorized_checkpoint_resume_resets_e2e),
    ("test_emit_dispatch_context_file_long_value", test_emit_dispatch_context_file_long_value),
    ("test_inject_unbound_marker_is_silent_noop", test_inject_unbound_marker_is_silent_noop),
    ("test_inject_bound_owner_still_produces_banner", test_inject_bound_owner_still_produces_banner),
    ("test_guard_unbound_marker_deny_does_not_bind", test_guard_unbound_marker_deny_does_not_bind),
    ("test_guard_bind_failure_is_fail_open", test_guard_bind_failure_is_fail_open),
    ("test_run_state_symbols_present", test_run_state_symbols_present),
    ("test_marker_write_read_roundtrip", test_marker_write_read_roundtrip),
    ("test_marker_staleness_age", test_marker_staleness_age),
    ("test_marker_staleness_session_id", test_marker_staleness_session_id),
    ("test_marker_staleness_session_id_non_destructive", test_marker_staleness_session_id_non_destructive),
    ("test_marker_age_and_corrupt_still_delete", test_marker_age_and_corrupt_still_delete),
    ("test_fold_and_advance_run_counters", test_fold_and_advance_run_counters),
    ("test_advance_run_counters_consume_gated", test_advance_run_counters_consume_gated),
    ("test_advance_meta_cycle_increments_meta", test_advance_meta_cycle_increments_meta),
    ("test_emit_dispatch_real_templates_exist_and_declare_requires", test_emit_dispatch_real_templates_exist_and_declare_requires),
    ("test_p7_write_run_marker_defaults_attended", test_p7_write_run_marker_defaults_attended),
    ("test_p7_write_run_marker_attended_false", test_p7_write_run_marker_attended_false),
    ("test_p7_marker_missing_attended_defaults_true", test_p7_marker_missing_attended_defaults_true),
    ("test_p7_run_end_checkpoint_attended_no_auth_refuses", test_p7_run_end_checkpoint_attended_no_auth_refuses),
    ("test_p7_run_end_checkpoint_attended_with_auth_succeeds", test_p7_run_end_checkpoint_attended_with_auth_succeeds),
    ("test_p7_run_end_checkpoint_unattended_no_auth_allowed", test_p7_run_end_checkpoint_unattended_no_auth_allowed),
    ("test_p7_run_end_terminal_sanctioned_reason_allowed", test_p7_run_end_terminal_sanctioned_reason_allowed),
    ("test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth", test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth),
    ("test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed", test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed),
    ("test_p7_run_end_terminal_no_terminal_reason_adds_deprecation", test_p7_run_end_terminal_no_terminal_reason_adds_deprecation),
    ("test_p7_emit_dispatch_includes_dispatch_prompt_ref", test_p7_emit_dispatch_includes_dispatch_prompt_ref),
    ("test_per_repo_marker_independence_when_unset", test_per_repo_marker_independence_when_unset),
    ("test_marker_present_cli_absent_then_present_and_readonly", test_marker_present_cli_absent_then_present_and_readonly),
    ("test_marker_status_cli_never_throws_lazy_state", test_marker_status_cli_never_throws_lazy_state),
    ("test_marker_status_cli_never_throws_bug_state", test_marker_status_cli_never_throws_bug_state),
    ("test_cross_script_same_repo_refuses_keyed_dir_unset", test_cross_script_same_repo_refuses_keyed_dir_unset),
    ("test_cycle_marker_set_writes_all_fields", test_cycle_marker_set_writes_all_fields),
    ("test_cycle_marker_read_returns_dict_then_none_after_clear", test_cycle_marker_read_returns_dict_then_none_after_clear),
    ("test_cycle_marker_read_none_when_absent", test_cycle_marker_read_none_when_absent),
    ("test_cycle_marker_clear_idempotent", test_cycle_marker_clear_idempotent),
    ("test_cycle_marker_staleness_overwrites_and_logs", test_cycle_marker_staleness_overwrites_and_logs),
    ("test_cycle_marker_kind_meta_round_trips", test_cycle_marker_kind_meta_round_trips),
    ("test_cycle_marker_corrupt_file_read_returns_none", test_cycle_marker_corrupt_file_read_returns_none),
    ("test_cycle_marker_run_identity_head_fields_additive", test_cycle_marker_run_identity_head_fields_additive),
    ("test_detect_friction_clean_bracket_returns_none", test_detect_friction_clean_bracket_returns_none),
    ("test_detect_friction_torn_bracket_run_identity_changed", test_detect_friction_torn_bracket_run_identity_changed),
    ("test_detect_friction_torn_bracket_run_marker_now_absent", test_detect_friction_torn_bracket_run_marker_now_absent),
    ("test_detect_friction_over_budget_commits", test_detect_friction_over_budget_commits),
    ("test_detect_friction_branch_divergence", test_detect_friction_branch_divergence),
    ("test_current_branch_snapshot_degrades_to_none", test_current_branch_snapshot_degrades_to_none),
    ("test_detect_friction_mark_complete_meta_cycle_multi_commit_within_budget", test_detect_friction_mark_complete_meta_cycle_multi_commit_within_budget),
    ("test_detect_friction_mcp_test_cycle_multi_commit_within_budget", test_detect_friction_mcp_test_cycle_multi_commit_within_budget),
    ("test_detect_friction_planning_cycle_multi_commit_within_budget", test_detect_friction_planning_cycle_multi_commit_within_budget),
    ("test_detect_friction_spec_cycle_multi_commit_within_budget", test_detect_friction_spec_cycle_multi_commit_within_budget),
    ("test_count_authored_commits_since_excludes_merge_commits", test_count_authored_commits_since_excludes_merge_commits),
    ("test_detect_friction_within_commit_budget_returns_none", test_detect_friction_within_commit_budget_returns_none),
    ("test_detect_friction_degraded_inputs_return_none", test_detect_friction_degraded_inputs_return_none),
    ("test_detect_friction_meta_cycle_exempt_from_unexpected_commits", test_detect_friction_meta_cycle_exempt_from_unexpected_commits),
    ("test_detect_friction_registry_known_skill_budgeted_without_literal_row", test_detect_friction_registry_known_skill_budgeted_without_literal_row),
    ("test_cycle_end_friction_check_symbol_present", test_cycle_end_friction_check_symbol_present),
    ("test_refuse_guard_fires_with_marker_present", test_refuse_guard_fires_with_marker_present),
    ("test_refuse_guard_noop_without_marker", test_refuse_guard_noop_without_marker),
    ("test_refuse_guard_leaves_run_marker_untouched", test_refuse_guard_leaves_run_marker_untouched),
    ("test_refuse_guard_allow_listed_ops_not_guarded", test_refuse_guard_allow_listed_ops_not_guarded),
    ("test_run_start_clobber_refuses_cross_pipeline_live_marker", test_run_start_clobber_refuses_cross_pipeline_live_marker),
    ("test_run_start_clobber_allows_same_pipeline_resume", test_run_start_clobber_allows_same_pipeline_resume),
    ("test_run_start_clobber_refuses_same_pipeline_concurrent_no_checkpoint", test_run_start_clobber_refuses_same_pipeline_concurrent_no_checkpoint),
    ("test_run_start_clobber_allows_same_pipeline_with_checkpoint_present", test_run_start_clobber_allows_same_pipeline_with_checkpoint_present),
    ("test_run_start_clobber_allows_same_pipeline_age_stale", test_run_start_clobber_allows_same_pipeline_age_stale),
    ("test_run_start_clobber_cross_pipeline_unchanged_with_checkpoint", test_run_start_clobber_cross_pipeline_unchanged_with_checkpoint),
    ("test_run_start_clobber_allows_when_no_marker", test_run_start_clobber_allows_when_no_marker),
    ("test_run_start_clobber_allows_over_age_stale_marker", test_run_start_clobber_allows_over_age_stale_marker),
    ("test_run_start_clobber_corrupt_marker_fails_open", test_run_start_clobber_corrupt_marker_fails_open),
    ("test_refuse_guard_orchestrator_env_never_refuses_even_with_marker", test_refuse_guard_orchestrator_env_never_refuses_even_with_marker),
    ("test_refuse_guard_explicit_subagent_env_refuses_without_marker", test_refuse_guard_explicit_subagent_env_refuses_without_marker),
    ("test_refuse_guard_orchestrator_env_overrides_explicit_subagent", test_refuse_guard_orchestrator_env_overrides_explicit_subagent),
    ("test_refuse_guard_falsey_orchestrator_env_does_not_grant_immunity", test_refuse_guard_falsey_orchestrator_env_does_not_grant_immunity),
    ("test_refuse_guard_marker_backstop_still_refuses_no_env", test_refuse_guard_marker_backstop_still_refuses_no_env),
    ("test_env_truthy_helper", test_env_truthy_helper),
    ("test_marker_mutation_guard_orchestrator_allowed_with_marker", test_marker_mutation_guard_orchestrator_allowed_with_marker),
    ("test_marker_mutation_guard_refuses_explicit_subagent_no_marker", test_marker_mutation_guard_refuses_explicit_subagent_no_marker),
    ("test_marker_mutation_guard_refuses_marker_present_without_orchestrator_env", test_marker_mutation_guard_refuses_marker_present_without_orchestrator_env),
    ("test_marker_mutation_guard_noop_no_marker_no_subagent_env", test_marker_mutation_guard_noop_no_marker_no_subagent_env),
    ("test_marker_mutation_guard_falsey_orchestrator_does_not_grant_immunity", test_marker_mutation_guard_falsey_orchestrator_does_not_grant_immunity),
    ("test_marker_mutation_guard_zero_side_effects_on_refusal", test_marker_mutation_guard_zero_side_effects_on_refusal),
    ("test_marker_mutation_guard_orchestrator_overrides_explicit_subagent", test_marker_mutation_guard_orchestrator_overrides_explicit_subagent),
    ("test_marker_mutation_ops_not_in_cycle_refused_ops", test_marker_mutation_ops_not_in_cycle_refused_ops),
    ("test_ensure_runtime_handler_wiring_emits_m4_verdict_all_states", test_ensure_runtime_handler_wiring_emits_m4_verdict_all_states),
    ("test_ensure_runtime_handler_wiring_threads_frontend_probe_for_compiling", test_ensure_runtime_handler_wiring_threads_frontend_probe_for_compiling),
    ("test_ensure_runtime_handler_wiring_threads_boot_alive_for_pre_vite", test_ensure_runtime_handler_wiring_threads_boot_alive_for_pre_vite),
    ("test_ensure_runtime_cli_handler_emits_m4_json_subprocess", test_ensure_runtime_cli_handler_emits_m4_json_subprocess),
    ("test_advance_forward_cycle_state_change_no_consume_advances", test_advance_forward_cycle_state_change_no_consume_advances),
    ("test_advance_forward_cycle_idempotent_across_refires", test_advance_forward_cycle_idempotent_across_refires),
    ("test_advance_forward_cycle_pseudo_cleanup_routes_meta", test_advance_forward_cycle_pseudo_cleanup_routes_meta),
    ("test_advance_forward_cycle_verbatim_real_skill_theory_1b", test_advance_forward_cycle_verbatim_real_skill_theory_1b),
    ("test_advance_forward_cycle_legacy_marker_no_state_key_advances", test_advance_forward_cycle_legacy_marker_no_state_key_advances),
    ("test_write_run_marker_initializes_per_feature_map", test_write_run_marker_initializes_per_feature_map),
    ("test_advance_forward_cycle_increments_per_feature", test_advance_forward_cycle_increments_per_feature),
    ("test_advance_forward_cycle_meta_does_not_increment_per_feature", test_advance_forward_cycle_meta_does_not_increment_per_feature),
    ("test_per_feature_counter_independent_keys", test_per_feature_counter_independent_keys),
    ("test_per_feature_counter_legacy_marker_tolerance", test_per_feature_counter_legacy_marker_tolerance),
    ("test_compute_per_feature_ceiling_override_short_circuits", test_compute_per_feature_ceiling_override_short_circuits),
    ("test_compute_per_feature_ceiling_six_floor_small_run", test_compute_per_feature_ceiling_six_floor_small_run),
    ("test_compute_per_feature_ceiling_deep_queue_six", test_compute_per_feature_ceiling_deep_queue_six),
    ("test_compute_per_feature_ceiling_forty_percent_cap_arm", test_compute_per_feature_ceiling_forty_percent_cap_arm),
    ("test_compute_per_feature_ceiling_zero_queue_no_div_by_zero", test_compute_per_feature_ceiling_zero_queue_no_div_by_zero),
    ("test_compute_per_feature_ceiling_pure_no_side_effects", test_compute_per_feature_ceiling_pure_no_side_effects),
    ("test_feature_is_near_complete_true_verification_only_plan_complete", test_feature_is_near_complete_true_verification_only_plan_complete),
    ("test_feature_is_near_complete_false_unchecked_impl_row", test_feature_is_near_complete_false_unchecked_impl_row),
    ("test_feature_is_near_complete_false_blocked", test_feature_is_near_complete_false_blocked),
    ("test_feature_is_near_complete_false_no_plan_complete", test_feature_is_near_complete_false_no_plan_complete),
    ("test_feature_is_near_complete_false_missing_phases_no_raise", test_feature_is_near_complete_false_missing_phases_no_raise),
    ("test_count_validation_corrective_cycles_legacy_absent_zero", test_count_validation_corrective_cycles_legacy_absent_zero),
    ("test_record_corrective_cycle_increments_by_one", test_record_corrective_cycle_increments_by_one),
    ("test_record_corrective_cycle_legacy_marker_tolerance", test_record_corrective_cycle_legacy_marker_tolerance),
    ("test_write_run_marker_seeds_per_feature_corrective_map", test_write_run_marker_seeds_per_feature_corrective_map),
    ("test_budget_trip_signals_over_ceiling_defers", test_budget_trip_signals_over_ceiling_defers),
    ("test_budget_trip_signals_near_complete_grace", test_budget_trip_signals_near_complete_grace),
    ("test_budget_trip_signals_corrective_discount", test_budget_trip_signals_corrective_discount),
    ("test_budget_trip_signals_effective_count_clamped_at_zero", test_budget_trip_signals_effective_count_clamped_at_zero),
    ("test_budget_trip_signals_pure_no_io", test_budget_trip_signals_pure_no_io),
    ("test_parse_independent_marker_spec_frontmatter_true", test_parse_independent_marker_spec_frontmatter_true),
    ("test_parse_independent_marker_queue_entry_true", test_parse_independent_marker_queue_entry_true),
    ("test_parse_independent_marker_no_shared_state_alias", test_parse_independent_marker_no_shared_state_alias),
    ("test_parse_independent_marker_absent_default_false", test_parse_independent_marker_absent_default_false),
    ("test_record_resolution_signal_persists_step_key", test_record_resolution_signal_persists_step_key),
    ("test_symptom3_resolution_reset", test_symptom3_resolution_reset),
    ("test_symptom3_resolution_reset_is_one_shot", test_symptom3_resolution_reset_is_one_shot),
    ("test_resolution_signal_no_repeat_count_reset_head_aware", test_resolution_signal_no_repeat_count_reset_head_aware),
    ("test_symptom5_d8_commit_masked_loop_still_trips", test_symptom5_d8_commit_masked_loop_still_trips),
    ("test_resolution_reset_inert_without_signal", test_resolution_reset_inert_without_signal),
    ("test_marker_work_branch_helper_reads_value", test_marker_work_branch_helper_reads_value),
    ("test_marker_work_branch_helper_legacy_marker_returns_none", test_marker_work_branch_helper_legacy_marker_returns_none),
    ("test_marker_work_branch_helper_no_marker_returns_none", test_marker_work_branch_helper_no_marker_returns_none),
    ("test_marker_work_branch_cli_lazy_state", test_marker_work_branch_cli_lazy_state),
    ("test_marker_work_branch_cli_bug_state_parity", test_marker_work_branch_cli_bug_state_parity),
    ("test_run_start_owner_bind_closes_repro_a", test_run_start_owner_bind_closes_repro_a),
    ("test_run_start_legacy_unbound_preserved", test_run_start_legacy_unbound_preserved),
    ("test_run_start_cli_threads_session_id_lazy_state", test_run_start_cli_threads_session_id_lazy_state),
    ("test_run_start_cli_threads_session_id_bug_state_parity", test_run_start_cli_threads_session_id_bug_state_parity),
    ("test_marker_owner_status_detect_three_way", test_marker_owner_status_detect_three_way),
    ("test_reassert_marker_owner_re_arms_foreign_stamped", test_reassert_marker_owner_re_arms_foreign_stamped),
    ("test_reassert_marker_owner_repro_b_resume_owner_bound", test_reassert_marker_owner_repro_b_resume_owner_bound),
    ("test_legacy_disarm_detected_and_re_armed", test_legacy_disarm_detected_and_re_armed),
    ("test_cycle_end_records_bracket_cli_lazy_state", test_cycle_end_records_bracket_cli_lazy_state),
    ("test_cycle_end_records_bracket_cli_bug_state_parity", test_cycle_end_records_bracket_cli_bug_state_parity),
    ("test_write_run_marker_parent_run_default_none_and_explicit", test_write_run_marker_parent_run_default_none_and_explicit),
    ("test_parent_run_classified_into_run_fresh_fields", test_parent_run_classified_into_run_fresh_fields),
    ("test_write_cycle_marker_stamps_subagent_model", test_write_cycle_marker_stamps_subagent_model),
    ("test_write_cycle_marker_rebinds_nonce_for_subagent_model", test_write_cycle_marker_rebinds_nonce_for_subagent_model),
    ("test_run_end_unacked_hardening_refusal_emits_gate_refusal_lazy", test_run_end_unacked_hardening_refusal_emits_gate_refusal_lazy),
    ("test_run_end_checkpoint_auth_refusal_emits_gate_refusal_lazy", test_run_end_checkpoint_auth_refusal_emits_gate_refusal_lazy),
    ("test_run_end_checkpoint_auth_refusal_emits_gate_refusal_bug", test_run_end_checkpoint_auth_refusal_emits_gate_refusal_bug),
    ("test_no_bare_production_sentinel_writes", test_no_bare_production_sentinel_writes),
    ("test_bare_write_lint_guard_detects_planted_violation", test_bare_write_lint_guard_detects_planted_violation),
    ("test_ctx_mutation_visible_through_facade", test_ctx_mutation_visible_through_facade),
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
