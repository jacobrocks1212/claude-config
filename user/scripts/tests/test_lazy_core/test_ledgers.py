#!/usr/bin/env python3
"""
test_ledgers.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_ledgers.py
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



from _util import _ModuleMissing, _NOW1, _assert_run_end_refusal_emits, _build_phase8_fixture_repo, _clear_state_dir, _collect_telemetry_event_literals, _dispatch_requires, _fresh_started_at, _make_interventions_bearing_repo, _make_laddered_dir, _os_env, _prov_git_commit_file, _prov_git_fixture_repo, _prov_spec_dir, _seed_efficacy_breadcrumb, _set_state_dir, _write_target_marker  # noqa: E402




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





def test_stale_and_materialized_symbols_present():
    """All 6 new stale-upstream and materialized-list helpers must be importable from lazy_core."""
    _guard()
    expected = [
        "read_stale_upstream",
        "write_stale_upstream",
        "clear_stale_upstream",
        "read_materialized",
        "append_materialized",
        "update_materialized_changeddate",
    ]
    missing = [sym for sym in expected if not hasattr(lazy_core, sym)]
    assert not missing, f"missing symbols: {missing}"




# ---------------------------------------------------------------------------
# Tests: read_stale_upstream / write_stale_upstream / clear_stale_upstream
# ---------------------------------------------------------------------------

def test_read_stale_upstream_absent():
    """Empty temp dir (no STALE_UPSTREAM.md) → returns None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.read_stale_upstream(Path(td))
    assert result is None, f"expected None, got {result!r}"




def test_write_then_read_stale_upstream():
    """write_stale_upstream then read returns the exact diff body written."""
    _guard()
    diff = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n"
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.write_stale_upstream(item_dir, diff)
        result = lazy_core.read_stale_upstream(item_dir)
    assert result == diff, f"body mismatch:\n  expected: {diff!r}\n  got:      {result!r}"




def test_clear_stale_upstream_removes_file():
    """After write then clear, read returns None and the file no longer exists on disk."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.write_stale_upstream(item_dir, "some diff content\n")
        lazy_core.clear_stale_upstream(item_dir)
        result = lazy_core.read_stale_upstream(item_dir)
        file_exists = (item_dir / "STALE_UPSTREAM.md").exists()
    assert result is None, f"expected None after clear, got {result!r}"
    assert not file_exists, "STALE_UPSTREAM.md still exists on disk after clear"




def test_clear_stale_upstream_absent_is_noop():
    """clear_stale_upstream on a dir with no STALE_UPSTREAM.md does not raise."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        try:
            lazy_core.clear_stale_upstream(Path(td))
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"clear_stale_upstream raised on absent file: {exc}") from exc




# ---------------------------------------------------------------------------
# Tests: read_materialized / append_materialized / update_materialized_changeddate
# ---------------------------------------------------------------------------

def test_read_materialized_absent():
    """Work dir with no materialized.json → returns [] (empty list, not None)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.read_materialized(Path(td))
    assert result == [], f"expected [], got {result!r}"




def test_append_materialized_creates_record():
    """Append once → read returns a 1-element list with correct keys/values."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        lazy_core.append_materialized(work_dir, 1001, "add-widget", "2026-06-01T10:00:00Z")
        result = lazy_core.read_materialized(work_dir)
    assert len(result) == 1, f"expected 1 record, got {len(result)}: {result}"
    record = result[0]
    assert record.get("wi_id") == 1001, f"wi_id mismatch: {record}"
    assert record.get("feature_id") == "add-widget", f"feature_id mismatch: {record}"
    assert record.get("materialized_changedDate") == "2026-06-01T10:00:00Z", f"changedDate mismatch: {record}"




def test_append_materialized_idempotent_on_wi_id():
    """Appending wi_id=1001 twice (different feature_id/date) → exactly ONE entry retaining the original values."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        lazy_core.append_materialized(work_dir, 1001, "add-widget", "2026-06-01T10:00:00Z")
        # Second call with different values — should be a no-op because wi_id already exists
        lazy_core.append_materialized(work_dir, 1001, "different-feature", "2026-07-01T00:00:00Z")
        result = lazy_core.read_materialized(work_dir)
    assert len(result) == 1, f"expected exactly 1 record after idempotent append, got {len(result)}: {result}"
    record = result[0]
    assert record.get("feature_id") == "add-widget", f"original feature_id should be preserved: {record}"
    assert record.get("materialized_changedDate") == "2026-06-01T10:00:00Z", f"original changedDate should be preserved: {record}"




def test_append_materialized_multiple_distinct():
    """Append wi_id 1001 then 1002 → read returns exactly 2 entries."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        lazy_core.append_materialized(work_dir, 1001, "feature-a", "2026-06-01T10:00:00Z")
        lazy_core.append_materialized(work_dir, 1002, "feature-b", "2026-06-02T10:00:00Z")
        result = lazy_core.read_materialized(work_dir)
    assert len(result) == 2, f"expected 2 records, got {len(result)}: {result}"
    wi_ids = {r.get("wi_id") for r in result}
    assert wi_ids == {1001, 1002}, f"expected wi_ids {{1001, 1002}}, got {wi_ids}"




def test_update_materialized_changeddate():
    """Append wi_id 1001 with date 'A', update to 'B' → read returns 1 entry with changedDate == 'B'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        lazy_core.append_materialized(work_dir, 1001, "add-widget", "2026-06-01T10:00:00Z")
        lazy_core.update_materialized_changeddate(work_dir, 1001, "2026-06-15T12:00:00Z")
        result = lazy_core.read_materialized(work_dir)
    assert len(result) == 1, f"expected 1 record, got {len(result)}: {result}"
    assert result[0].get("materialized_changedDate") == "2026-06-15T12:00:00Z", f"changedDate not updated: {result[0]}"




def test_update_materialized_changeddate_absent_wi_is_noop():
    """update_materialized_changeddate for a wi_id not present → no exception, list unchanged."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        work_dir = Path(td)
        lazy_core.append_materialized(work_dir, 1001, "add-widget", "2026-06-01T10:00:00Z")
        try:
            lazy_core.update_materialized_changeddate(work_dir, 9999, "2026-07-01T00:00:00Z")
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"update_materialized_changeddate raised on absent wi_id: {exc}") from exc
        result = lazy_core.read_materialized(work_dir)
    assert len(result) == 1, f"list should be unchanged (1 record), got {len(result)}: {result}"
    assert result[0].get("wi_id") == 1001, f"original record should be preserved: {result[0]}"




def test_derive_stage_missing_dir():
    """Missing directory → 'spec' (documented default)."""
    _guard()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        absent = Path(td) / "does-not-exist"
    # td is now cleaned up, absent definitely does not exist
    result = lazy_core.derive_stage(absent)
    assert result == "spec", f"expected 'spec' for missing dir, got {result!r}"




def test_derive_stage_spec_only():
    """Dir with only SPEC.md → 'spec'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "spec", f"expected 'spec', got {result!r}"




def test_derive_stage_research_md():
    """SPEC.md + RESEARCH.md (no PHASES) → 'research'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
        (d / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "research", f"expected 'research', got {result!r}"




def test_derive_stage_research_summary_md():
    """SPEC.md + RESEARCH_SUMMARY.md (no PHASES, no RESEARCH.md) → 'research'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
        (d / "RESEARCH_SUMMARY.md").write_text("# Research Summary\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "research", f"expected 'research', got {result!r}"




def test_derive_stage_phases_only():
    """SPEC.md + PHASES.md (no plans/) → 'phases'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
        (d / "PHASES.md").write_text("# Phases\n\n- [ ] Phase 1\n- [ ] Phase 2\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "phases", f"expected 'phases', got {result!r}"




def test_derive_stage_plan_no_checked_deliverables():
    """PHASES.md (zero checked deliverables) + plans/*.md → 'plan'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
        (d / "PHASES.md").write_text("# Phases\n\n- [ ] Phase 1\n- [ ] Phase 2\n", encoding="utf-8")
        plans_dir = d / "plans"
        plans_dir.mkdir()
        (plans_dir / "plan-phase-1.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases:\n  - 1\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.derive_stage(d)
    assert result == "plan", f"expected 'plan', got {result!r}"




def test_derive_stage_implement_checked_deliverable():
    """PHASES.md with ≥1 checked deliverable + plans/*.md → 'implement'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "SPEC.md").write_text("# Spec\n", encoding="utf-8")
        (d / "PHASES.md").write_text(
            "# Phases\n\n- [x] Phase 1 done\n- [ ] Phase 2 todo\n",
            encoding="utf-8",
        )
        plans_dir = d / "plans"
        plans_dir.mkdir()
        (plans_dir / "plan-phase-1.md").write_text(
            "---\nkind: implementation-plan\nstatus: Complete\nphases:\n  - 1\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.derive_stage(d)
    assert result == "implement", f"expected 'implement', got {result!r}"




def test_derive_stage_review():
    """PR.md + PHASES.md present (impl-complete), no receipt/halt sentinels → 'review'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "PR.md").write_text("# Pull Request\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "review", f"expected 'review', got {result!r}"




def test_derive_stage_reviewed():
    """REVIEWED.md present (fully laddered dir) → 'reviewed'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "PR.md").write_text("# Pull Request\n", encoding="utf-8")
        (d / "REVIEWED.md").write_text("# Reviewed\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "reviewed", f"expected 'reviewed', got {result!r}"




def test_derive_stage_stale_upstream_wins_over_ladder():
    """STALE_UPSTREAM.md + full artifact ladder → 'stale-upstream' (halt beats ladder)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "STALE_UPSTREAM.md").write_text("upstream changed\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "stale-upstream", f"expected 'stale-upstream', got {result!r}"




def test_derive_stage_blocked_wins_over_ladder():
    """BLOCKED.md + full artifact ladder → 'blocked'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "BLOCKED.md").write_text("# Blocked\n\nWaiting on external API.\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "blocked", f"expected 'blocked', got {result!r}"




def test_derive_stage_needs_input_wins_over_ladder():
    """NEEDS_INPUT.md + full artifact ladder → 'needs-input'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "NEEDS_INPUT.md").write_text("# Needs Input\n", encoding="utf-8")
        result = lazy_core.derive_stage(d)
    assert result == "needs-input", f"expected 'needs-input', got {result!r}"




def test_derive_stage_symbol_present():
    """derive_stage must be an attribute of the lazy_core module."""
    _guard()
    assert hasattr(lazy_core, "derive_stage"), (
        "lazy_core.derive_stage does not exist — implement the function"
    )


_NOW2 = "2026-06-03T11:30:00Z"


_NOW3 = "2026-06-03T12:45:00Z"




def test_track_open_idempotent_preserves_started_at():
    """Second track_open with a different now: exactly one WIP.md, started_at preserved, last_touched advanced."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.track_open(
            item_dir, wi_id=42, slug="my-feature", branch="p/my-feature", host="DEVBOX", now=_NOW1,
        )
        lazy_core.track_open(
            item_dir, wi_id=42, slug="my-feature", branch="p/my-feature", host="DEVBOX", now=_NOW2,
        )
        wip_files = list(item_dir.glob("WIP*.md"))
        assert len(wip_files) == 1, f"expected exactly 1 WIP.md, found {wip_files}"
        data = lazy_core.parse_sentinel(item_dir / "WIP.md")
    assert data.get("started_at") == _NOW1, f"started_at should be preserved (now1): {data}"
    assert data.get("last_touched") == _NOW2, f"last_touched should advance to now2: {data}"




def test_track_open_creates_dir_if_absent():
    """track_open creates the item dir if it does not exist, then writes WIP.md."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td) / "new-item"
        assert not item_dir.exists(), "pre-condition: item_dir must not exist"
        lazy_core.track_open(
            item_dir, wi_id=99, slug="new-item", branch="p/new-item", host="DEVBOX", now=_NOW1,
        )
        assert item_dir.exists(), "item_dir was not created by track_open"
        assert (item_dir / "WIP.md").exists(), "WIP.md was not created in new item_dir"




def test_track_touch_refreshes_last_touched():
    """track_touch on an existing WIP.md refreshes last_touched; started_at and other fields preserved."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.track_open(
            item_dir, wi_id=7, slug="touch-test", branch="p/touch-test", host="BOX", now=_NOW1,
        )
        lazy_core.track_touch(item_dir, now=_NOW3)
        data = lazy_core.parse_sentinel(item_dir / "WIP.md")
    assert data.get("last_touched") == _NOW3, f"last_touched should be now3: {data}"
    assert data.get("started_at") == _NOW1, f"started_at should be preserved (now1): {data}"
    assert data.get("kind") == "wip", f"kind should be unchanged: {data}"
    assert data.get("wi_id") == 7, f"wi_id should be unchanged: {data}"
    assert data.get("slug") == "touch-test", f"slug should be unchanged: {data}"
    assert data.get("branch") == "p/touch-test", f"branch should be unchanged: {data}"
    assert data.get("host") == "BOX", f"host should be unchanged: {data}"




def test_track_touch_absent_wip_is_noop():
    """track_touch when WIP.md is absent: no file is created, no exception raised."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        try:
            lazy_core.track_touch(item_dir, now=_NOW1)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"track_touch raised on absent WIP.md: {exc}") from exc
        assert not (item_dir / "WIP.md").exists(), "track_touch must NOT create WIP.md when absent"




def test_track_close_removes_wip_md():
    """track_close removes an existing WIP.md."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.track_open(
            item_dir, wi_id=5, slug="close-test", branch="p/close-test", host="BOX", now=_NOW1,
        )
        assert (item_dir / "WIP.md").exists(), "pre-condition: WIP.md must exist before close"
        lazy_core.track_close(item_dir)
        assert not (item_dir / "WIP.md").exists(), "WIP.md should be gone after track_close"




def test_track_close_absent_is_noop():
    """track_close when WIP.md is absent: no exception, file still absent."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        try:
            lazy_core.track_close(item_dir)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"track_close raised on absent WIP.md: {exc}") from exc
        assert not (item_dir / "WIP.md").exists(), "WIP.md should remain absent after no-op close"




def test_track_symbols_present():
    """track_open, track_touch, and track_close must be attributes of lazy_core."""
    _guard()
    assert hasattr(lazy_core, "track_open"), "lazy_core.track_open does not exist"
    assert hasattr(lazy_core, "track_touch"), "lazy_core.track_touch does not exist"
    assert hasattr(lazy_core, "track_close"), "lazy_core.track_close does not exist"




def test_deny_ledger_write_read_pending():
    """append → read returns entries in FIFO order; pending counts unacked only."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.read_deny_ledger() == [], "empty ledger must read as []"
            assert lazy_core.pending_hardening() == 0, "no ledger → 0 pending"
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-1", denied_sha12="abc123def456",
                reason_head="reason one", prompt_head="prompt one", now=100.0,
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-2", denied_sha12="ffffffffffff",
                reason_head="reason two", prompt_head="prompt two", now=200.0,
            )
            entries = lazy_core.read_deny_ledger()
            assert len(entries) == 2, f"expected 2 entries, got {entries}"
            # FIFO order preserved.
            assert entries[0]["tool_use_id"] == "tu-1", entries
            assert entries[1]["tool_use_id"] == "tu-2", entries
            assert entries[0]["denied_sha12"] == "abc123def456", entries
            assert entries[0]["acked"] is False, entries
            assert lazy_core.pending_hardening() == 2, "both entries unacked"
            reasons = lazy_core.pending_denial_reasons()
            assert reasons == ["reason one", "reason two"], reasons
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Tests: loop-detector-false-positives-probes-and-cross-run-state
# Residual gap B (deny-ledger half) — run-scoping of the routed hardening debt.
# ---------------------------------------------------------------------------


def test_deny_ledger_entries_stamped_with_run_identity():
    """append_deny_ledger_entry / append_friction_ledger_entry stamp the new
    entry with the LIVE run marker's started_at (None when no marker)."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _set_state_dir(state_dir)
        try:
            marker = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=_time.time(),
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            lazy_core.append_friction_ledger_entry(
                "unexpected-commits", "detail", now=2.0,
            )
            entries = lazy_core.read_deny_ledger()
        finally:
            _clear_state_dir()
    assert len(entries) == 2, entries
    assert entries[0]["run_started_at"] == marker["started_at"], entries[0]
    assert entries[1]["run_started_at"] == marker["started_at"], entries[1]




def test_pending_hardening_excludes_prior_run_debt():
    """Residual gap B (deny-ledger half — symptom 4): an unacked entry stamped
    under a PRIOR run (a crashed run's leftover) must NOT force the NEXT run to
    dispatch a hardening round. pending_hardening()/pending_denial_reasons()
    default to current_run_only=True; prior_run_pending_hardening() surfaces
    the leftover informationally.

    RED (pre-fix): pending_hardening() counted ALL unacked entries machine-wide
    regardless of which run wrote them, so a crashed run's undrained denial
    forced --run-end/probe-withholding for a run that never saw it.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _set_state_dir(state_dir)
        try:
            # Run A: marker + one unacked deny stamped with run A's identity.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0,
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-a", denied_sha12="a" * 12,
                reason_head="run-a reason", prompt_head="p", now=1.0,
            )
        finally:
            _clear_state_dir()
        # Run A "crashes" (no --run-end — the ledger entry is left unacked).
        # Run B starts fresh: a NEW marker with a DIFFERENT started_at.
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=2_000_000.0,
            )
            # Run B's own mandatory debt is 0 (it has not denied anything yet).
            pending_b = lazy_core.pending_hardening()
            reasons_b = lazy_core.pending_denial_reasons()
            prior_b = lazy_core.prior_run_pending_hardening()
            # Total (informational/retro) count still sees both.
            total = lazy_core.pending_hardening(current_run_only=False)
        finally:
            _clear_state_dir()
    assert pending_b == 0, (
        f"run B must NOT owe run A's undrained denial as mandatory debt, "
        f"got pending_hardening={pending_b}"
    )
    assert reasons_b == [], f"run B's mandatory denial reasons must be empty, got {reasons_b!r}"
    assert prior_b == 1, (
        f"run A's leftover denial must surface as informational prior-run debt, "
        f"got prior_run_pending_hardening={prior_b}"
    )
    assert total == 1, f"the unfiltered/retro total must still see it, got {total}"




def test_oldest_unacked_deny_scopes_to_current_run():
    """oldest_unacked_deny() mirrors pending_hardening()'s run-scoping: a
    prior-run entry is skipped so the command bound into the hardening-dispatch
    prompt always names an entry that actually drove the CURRENT run's debt."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0,
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-a", denied_sha12="a" * 12,
                reason_head="run-a reason", prompt_head="p", now=1.0,
            )
        finally:
            _clear_state_dir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=2_000_000.0,
            )
            oldest_default = lazy_core.oldest_unacked_deny()
            oldest_unscoped = lazy_core.oldest_unacked_deny(current_run_only=False)
        finally:
            _clear_state_dir()
    assert oldest_default is None, (
        f"the only unacked entry belongs to run A — current-run-scoped lookup "
        f"must find nothing for run B, got {oldest_default!r}"
    )
    assert oldest_unscoped is not None and oldest_unscoped["reason_head"] == "run-a reason", (
        f"unscoped lookup still finds run A's entry, got {oldest_unscoped!r}"
    )




def test_pending_hardening_no_marker_fallback_stays_unfiltered():
    """No live marker at all → pending_hardening()/pending_denial_reasons()
    fall back to the unfiltered total (no established run identity to scope
    against) — byte-identical to every existing no-marker caller/test."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            pending = lazy_core.pending_hardening()
            reasons = lazy_core.pending_denial_reasons()
            prior = lazy_core.prior_run_pending_hardening()
        finally:
            _clear_state_dir()
    assert pending == 1, f"no marker → unfiltered fallback, got {pending}"
    assert reasons == ["r"], reasons
    assert prior == 0, (
        f"no marker → no established run identity to compare against, "
        f"prior_run_pending_hardening must be 0, got {prior}"
    )




def test_deny_ledger_head_truncation():
    """reason_head / prompt_head are truncated to the head-char cap."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            long_reason = "R" * 500
            long_prompt = "P" * 500
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="0" * 12,
                reason_head=long_reason, prompt_head=long_prompt, now=1.0,
            )
            entry = lazy_core.read_deny_ledger()[0]
            cap = lazy_core._LEDGER_HEAD_CHARS
            assert len(entry["reason_head"]) == cap, len(entry["reason_head"])
            assert len(entry["prompt_head"]) == cap, len(entry["prompt_head"])
        finally:
            _clear_state_dir()




def test_ack_oldest_deny_fifo():
    """ack_oldest_deny flips the OLDEST unacked entry first (FIFO)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            for i in range(3):
                lazy_core.append_deny_ledger_entry(
                    tool_use_id=f"tu-{i}", denied_sha12=f"{i}" * 12,
                    reason_head=f"reason {i}", prompt_head=f"prompt {i}",
                    now=float(i),
                )
            assert lazy_core.pending_hardening() == 3
            acked = lazy_core.ledgers.ack_oldest_deny(now=999.0)
            assert acked is not None, "ack returned None despite pending entries"
            assert acked["tool_use_id"] == "tu-0", "must ack the OLDEST (tu-0)"
            assert acked["acked"] is True and acked["acked_ts"] == 999.0, acked
            assert lazy_core.pending_hardening() == 2, "one acked → 2 remain"
            # Next ack takes tu-1 (the new oldest unacked).
            acked2 = lazy_core.ledgers.ack_oldest_deny(now=1000.0)
            assert acked2["tool_use_id"] == "tu-1", acked2
            assert lazy_core.pending_hardening() == 1
            # The first entry stays acked across re-reads (persisted).
            entries = lazy_core.read_deny_ledger()
            assert entries[0]["acked"] is True, entries
            assert entries[1]["acked"] is True, entries
            assert entries[2]["acked"] is False, entries
        finally:
            _clear_state_dir()




def test_ack_oldest_deny_empty_is_noop():
    """ack_oldest_deny with no pending entries returns None (no-op, not error)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # No ledger at all.
            assert lazy_core.ledgers.ack_oldest_deny() is None, "empty/absent ledger → None"
            # Ledger with a single already-acked entry.
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            assert lazy_core.ledgers.ack_oldest_deny(now=2.0) is not None  # acks it
            assert lazy_core.ledgers.ack_oldest_deny(now=3.0) is None, "all acked → no-op"
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_oldest_requires_resolution():
    """meta-dispatch-not-by-reference-and-ack-overpriced Fix Scope §1: a blank
    resolution refuses with ZERO writes — the ledger stays untouched."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            result = lazy_core.ack_deny_by_selector("oldest", "")
            assert result["ok"] is False, result
            assert "resolution" in result["error"], result
            assert lazy_core.pending_hardening() == 1, "blank resolution must not ack"
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_oldest_fifo():
    """selector='oldest' acks the FIFO-oldest unacked entry, recording
    ack_method='manual-ack' + the resolution note — distinct from the
    hardening-round ack_oldest_deny() path."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            for i in range(2):
                lazy_core.append_deny_ledger_entry(
                    tool_use_id=f"tu-{i}", denied_sha12=f"{i}{'a'*11}",
                    reason_head=f"reason {i}", prompt_head=f"prompt {i}",
                    now=float(i),
                )
            result = lazy_core.ack_deny_by_selector(
                "oldest", "already fixed by round 1 this run", now=999.0
            )
            assert result["ok"] is True, result
            assert result["acked"]["tool_use_id"] == "tu-0", result
            assert result["acked"]["ack_method"] == "manual-ack", result
            assert result["acked"]["resolution"] == "already fixed by round 1 this run", result
            assert result["deduped"] == [], result
            assert lazy_core.pending_hardening() == 1, "one acked → one remains"
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_sha_prefix_match():
    """A denied_sha12 prefix selector acks the matching unacked entry, not the
    FIFO-oldest — addressed acks, not just FIFO."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-0", denied_sha12="aaaaaaaaaaaa",
                reason_head="r0", prompt_head="p0", now=0.0,
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-1", denied_sha12="bbbbbbbbbbbb",
                reason_head="r1", prompt_head="p1", now=1.0,
            )
            result = lazy_core.ack_deny_by_selector("bbbb", "no-fix — cosmetic", now=5.0)
            assert result["ok"] is True, result
            assert result["acked"]["tool_use_id"] == "tu-1", result
            entries = lazy_core.read_deny_ledger()
            assert entries[0]["acked"] is False, "tu-0 (non-matching) must stay unacked"
            assert entries[1]["acked"] is True, entries
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_no_match_refuses():
    """A selector matching no unacked entry refuses with a named error and
    ZERO writes."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            result = lazy_core.ack_deny_by_selector("zzzzzz", "no-fix")
            assert result["ok"] is False, result
            assert "zzzzzz" in result["error"], result
            assert lazy_core.pending_hardening() == 1, "no match → no ack"
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_dedups_same_sha_cause():
    """Fix Scope §2: acking one entry also acks every OTHER unacked entry
    sharing the same denied_sha12 (a byte-identical repeat denial) — one
    oscillating cause never costs more than one unit of retirement effort."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            for i in range(3):
                lazy_core.append_deny_ledger_entry(
                    tool_use_id=f"tu-{i}", denied_sha12="c" * 12,
                    reason_head="same cause", prompt_head="same prompt",
                    now=float(i),
                )
            # An UNRELATED entry with a different sha must NOT be swept in.
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-other", denied_sha12="d" * 12,
                reason_head="different", prompt_head="different", now=9.0,
            )
            result = lazy_core.ack_deny_by_selector(
                "oldest", "root cause fixed in round 1", now=999.0
            )
            assert result["ok"] is True, result
            assert result["acked"]["tool_use_id"] == "tu-0", result
            deduped_ids = {e["tool_use_id"] for e in result["deduped"]}
            assert deduped_ids == {"tu-1", "tu-2"}, result["deduped"]
            for e in result["deduped"]:
                assert e["ack_method"] == "manual-ack-dedup", e
            assert lazy_core.pending_hardening() == 1, (
                "only the unrelated (different-sha) entry should remain unacked"
            )
            entries = {e["tool_use_id"]: e for e in lazy_core.read_deny_ledger()}
            assert entries["tu-other"]["acked"] is False, entries
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_dedups_reason_head_fallback_no_sha():
    """Fix Scope §2 fallback: entries with NO denied_sha12 (e.g. a
    process-friction entry) dedup on identical (kind, reason_head) instead."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_friction_ledger_entry(
                reason_head="torn cycle bracket", detail="d1", now=1.0,
            )
            lazy_core.append_friction_ledger_entry(
                reason_head="torn cycle bracket", detail="d2", now=2.0,
            )
            result = lazy_core.ack_deny_by_selector("oldest", "acknowledged, no fix needed", now=9.0)
            assert result["ok"] is True, result
            assert len(result["deduped"]) == 1, result
            assert lazy_core.pending_hardening() == 0, (
                "both same-cause (kind+reason_head) entries acked in one call"
            )
        finally:
            _clear_state_dir()




def test_ack_deny_by_selector_refused_for_cycle_subagent():
    """The CLI layer's refuse_if_cycle_active guard (mirroring
    --backfill-receipts/--link-provenance) must deny a cycle subagent calling
    --ack-deny — invoked here at the CLI subprocess level."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            lazy_core.write_cycle_marker(feature_id="some-feature", nonce="deadbeef")
        finally:
            _clear_state_dir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        env["LAZY_CYCLE_SUBAGENT"] = "1"
        result = subprocess.run(
            [sys.executable, str(lazy_state), "--ack-deny", "oldest",
             "--resolution", "sneaky", "--repo-root", "."],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 3, (
            f"a cycle subagent must be refused exit 3, got {result.returncode}: "
            f"{result.stderr[:300]!r}"
        )
        _set_state_dir(state_dir)
        try:
            assert lazy_core.pending_hardening() == 1, (
                "refused --ack-deny must leave the ledger untouched"
            )
        finally:
            _clear_state_dir()




def test_deny_ledger_corrupt_line_skipped():
    """A corrupt (unparseable) line in the ledger is skipped, not fatal."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            ledger_path = Path(td) / "lazy-deny-ledger.jsonl"
            good = json.dumps({
                "ts": 1.0, "tool_use_id": "ok", "denied_sha12": "a" * 12,
                "reason_head": "good", "prompt_head": "p", "acked": False,
            })
            # Mix a valid line, a torn/garbage line, and a blank line.
            ledger_path.write_text(
                good + "\n" + "{not valid json" + "\n" + "\n",
                encoding="utf-8",
            )
            entries = lazy_core.read_deny_ledger()
            assert len(entries) == 1, f"corrupt line must be skipped, got {entries}"
            assert entries[0]["tool_use_id"] == "ok", entries
            assert lazy_core.pending_hardening() == 1, "the one good entry counts"
        finally:
            _clear_state_dir()




def test_guard_deny_ledger_failure_is_fail_open():
    """A ledger-write failure must NOT change the guard's deny output (fail-open).

    Simulated by pointing LAZY_STATE_DIR at a path whose ledger location cannot
    be written (a FILE exists where the ledger directory's append would land —
    here we make the state dir itself a regular file so any state-dir write
    raises, yet the in-process guard still returns its deny JSON)."""
    _guard()
    assert hasattr(lazy_core, "append_deny_ledger_entry"), "Phase 7 missing"
    with tempfile.TemporaryDirectory() as td:
        # Make a path that is a FILE, then point the ledger there: append will
        # raise.  append_deny_ledger_entry must swallow it and return False.
        bad_dir = Path(td) / "not-a-dir"
        bad_dir.write_text("i am a file, not a directory\n", encoding="utf-8")
        _set_state_dir(bad_dir)
        try:
            # claude_state_dir(create=True) would try to mkdir over a file →
            # the writer swallows the error and returns False (fail-open).
            ok = lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            assert ok is False, "unwritable ledger path must fail-open (return False)"
            # Reading from the same broken path must also be non-fatal.
            assert lazy_core.read_deny_ledger() == [], "broken read → [] not raise"
            assert lazy_core.pending_hardening() == 0
        finally:
            _clear_state_dir()




def test_run_end_refuses_on_unacked_deny():
    """Subprocess: marked run + 1 unacked deny → --run-end exits 1 with the
    marker still present; after the GUARD-ALLOW ack retires it, --run-end
    succeeds; --ack-unhardened overrides and notes the override.

    REVISED for Phase 8 WU-8.2: the debt is now acked at GUARD-ALLOW time (a
    hardening dispatch reaching execution), NOT at --emit-dispatch hardening
    emission time.  The middle leg of this test previously called
    `--emit-dispatch hardening` to drain the ledger; under Phase 8 that emission
    no longer acks, so the ack is now driven via lazy_core.ledgers.ack_oldest_deny()
    in-process — exactly what lazy_guard.py's _ack_if_hardening does on a
    hardening-class allow.  (A separate test, test_emit_dispatch_hardening_no_
    longer_acks, pins that the emission itself does NOT ack.)"""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "rend-state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        # run-start
        assert run(["--run-start", "--max-cycles", "5"]).returncode == 0
        # seed one unacked deny directly into the ledger (scoped)
        _set_state_dir(state_dir)
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
        finally:
            _clear_state_dir()

        # run-end REFUSES (exit 1), marker LEFT IN PLACE.
        r = run(["--run-end"])
        assert r.returncode == 1, f"run-end must refuse (exit 1), got {r.returncode}"
        out = json.loads(r.stdout)
        assert out["run_marker_deleted"] is False, out
        assert "refused" in out and out["pending_hardening"] == 1, out
        assert (state_dir / "lazy-run-marker.json").exists(), "marker must remain"

        # Ack via the GUARD-ALLOW path (Phase 8): a hardening dispatch reaching
        # execution acks the oldest unacked deny.  Simulated in-process by the
        # same lazy_core.ledgers.ack_oldest_deny() call lazy_guard.py makes.
        _set_state_dir(state_dir)
        try:
            acked = lazy_core.ledgers.ack_oldest_deny()
            assert acked is not None, "guard-allow ack must retire the pending deny"
        finally:
            _clear_state_dir()

        # Now run-end SUCCEEDS (ledger empty + efficacy breadcrumb seeded).
        _seed_efficacy_breadcrumb(state_dir)
        r2 = run(["--run-end"])
        assert r2.returncode == 0, f"run-end must succeed after ack: {r2.stdout}"
        out2 = json.loads(r2.stdout)
        assert out2["run_marker_deleted"] is True, out2
        assert not (state_dir / "lazy-run-marker.json").exists(), "marker deleted"

        # --- override path: fresh marked run + unacked deny + --ack-unhardened
        assert run(["--run-start", "--max-cycles", "5"]).returncode == 0
        _set_state_dir(state_dir)
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu2", denied_sha12="b" * 12,
                reason_head="r2", prompt_head="p2", now=2.0,
            )
        finally:
            _clear_state_dir()
        _seed_efficacy_breadcrumb(state_dir)
        r3 = run(["--run-end", "--ack-unhardened"])
        assert r3.returncode == 0, f"override run-end must succeed: {r3.stdout}"
        out3 = json.loads(r3.stdout)
        assert out3["run_marker_deleted"] is True, out3
        assert "override" in out3 and "OVERRIDE" in out3["override"], out3
        # hardening Round 20 (DEFECT-1): the override must ACTUALLY CLEAR the debt,
        # not merely note it. After --ack-unhardened, pending_hardening() must be 0
        # so the NEXT run's advancing probe does not keep withholding the route.
        _set_state_dir(state_dir)
        try:
            assert lazy_core.pending_hardening() == 0, (
                "operator-authorized --ack-unhardened must clear ALL pending "
                "hardening debt, not just bypass the gate"
            )
        finally:
            _clear_state_dir()




def test_ack_all_unacked_denies_clears_sessionless_friction():
    """ack_all_unacked_denies() flips EVERY unacked entry to acked — including a
    kind: process-friction entry that has NO session_id (the unclearable-debt
    case, hardening Round 20 DEFECT-1). Mixed validate-deny + process-friction
    are all cleared; an already-acked entry is left untouched; empty → 0."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "ackall-state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # empty ledger → 0, no-op.
            assert lazy_core.ack_all_unacked_denies() == 0

            # session-less process-friction entry (exactly what --cycle-end writes:
            # append_friction_ledger_entry stamps NO session_id field).
            assert lazy_core.append_friction_ledger_entry(
                "unexpected-commits", "HEAD advanced 6 commits", now=1.0,
            ) is True
            # a normal validate-deny entry too.
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="c" * 12,
                reason_head="r", prompt_head="p", now=2.0,
            )
            assert lazy_core.pending_hardening() == 2

            # confirm the friction entry truly has no session_id on disk.
            ledger = lazy_core.read_deny_ledger()
            friction = [e for e in ledger if e.get("kind") == "process-friction"]
            assert len(friction) == 1
            assert "session_id" not in friction[0], (
                "the friction entry must be session-less (the deadlock trigger)"
            )

            # blanket ack clears BOTH regardless of kind/session.
            n = lazy_core.ack_all_unacked_denies(now=9.0)
            assert n == 2, f"expected 2 entries acked, got {n}"
            assert lazy_core.pending_hardening() == 0

            # idempotent: a second call acks nothing (all already acked).
            assert lazy_core.ack_all_unacked_denies() == 0
        finally:
            _clear_state_dir()




def test_run_end_ack_unhardened_clears_sessionless_friction():
    """Subprocess end-to-end (hardening Round 20 DEFECT-1): a marked run with a
    SESSION-LESS kind: process-friction entry refuses --run-end without the
    override, and --run-end --ack-unhardened both deletes the marker AND drains
    the ledger so the NEXT run's probe no longer withholds the forward route."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "ackfric-state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        assert run(["--run-start", "--max-cycles", "5"]).returncode == 0
        # seed a session-less process-friction entry (the --cycle-end shape).
        _set_state_dir(state_dir)
        try:
            assert lazy_core.append_friction_ledger_entry(
                "unexpected-commits", "torn cycle / commits", now=1.0,
            ) is True
            assert lazy_core.pending_hardening() == 1
        finally:
            _clear_state_dir()

        # without the override, --run-end refuses (debt remains).
        r = run(["--run-end"])
        assert r.returncode == 1, r.stdout
        assert json.loads(r.stdout)["pending_hardening"] == 1

        # operator override: deletes the marker AND clears the debt.
        _seed_efficacy_breadcrumb(state_dir)
        r2 = run(["--run-end", "--ack-unhardened"])
        assert r2.returncode == 0, r2.stdout
        out2 = json.loads(r2.stdout)
        assert out2["run_marker_deleted"] is True, out2
        assert "override" in out2 and "OVERRIDE" in out2["override"], out2
        _set_state_dir(state_dir)
        try:
            assert lazy_core.pending_hardening() == 0, (
                "session-less process-friction debt must be cleared by the "
                "operator override (the unclearable-debt deadlock fix)"
            )
        finally:
            _clear_state_dir()




def test_f2b_find_transcription_slip_entry_no_match_without_marker():
    """F2b / F2c: find_transcription_slip_entry must return None when no run marker
    is present (it is a marked-run concern — fail-safe for unmarked runs).

    RED: find_transcription_slip_entry does not exist yet.
    """
    _guard()
    assert hasattr(lazy_core, "find_transcription_slip_entry"), (
        "lazy_core.find_transcription_slip_entry missing — F2c not yet implemented"
    )
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # NO marker — slip check should be inert.
            # Register an entry anyway (tests that the gate is on the marker, not the registry).
            # We need to skip the marker-gated write path, so write via internal registry directly.
            # Actually: register_emission works without a marker (peek/test mode).
            import time as _time
            lazy_core.register_emission(
                "Run the next dispatch cycle step as specified in the plan.",
                cls="cycle", item_id="feat-x", now=_time.time(),
            )
            near_copy = "Run the next dispatch cycle step as specified in the PLAN."
            entry = lazy_core.find_transcription_slip_entry(near_copy)
            assert entry is None, (
                "find_transcription_slip_entry must return None when no run marker is present "
                "(F2c is a marked-run concern)"
            )
        finally:
            _clear_state_dir()




def test_probe_withholds_forward_route_on_pending_debt():
    """Phase 8 WU-8.2/8.3: a marked run + 1 unacked deny → a real
    `--repeat-count --probe --emit-prompt` subprocess returns probe JSON with:
      - route_overridden_by == 'pending-hardening-debt'
      - NO 'cycle_prompt' key (forward route withheld)
      - a hardening_emit_command embedding trigger_kind=validate-deny, the
        item_id, and the shell-quoted denial reason_head
      - the '⚠ pending_hardening' warning on STDERR (not stdout)
    With debt but NO marker → no withholding, no new fields."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _build_phase8_fixture_repo(td_path)
        state_dir = td_path / "state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def probe():
            return subprocess.run(
                [sys.executable, str(lazy_state),
                 "--repeat-count", "--probe", "--emit-prompt",
                 "--repo-root", str(fixture_repo)],
                capture_output=True, text=True, env=env,
            )

        # --- (1) marker present but NO debt → normal forward route emitted ---
        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(fixture_repo),
                max_cycles=10, now=_time.time(),
            )
        finally:
            _clear_state_dir()
        r0 = probe()
        assert r0.returncode == 0, f"probe failed: {r0.stderr[:400]!r}"
        out0 = json.loads(r0.stdout)
        assert "cycle_prompt" in out0, (
            "with no debt the probe must emit the forward route (cycle_prompt)"
        )
        assert "route_overridden_by" not in out0, out0.get("route_overridden_by")
        assert out0.get("pending_hardening") == 0, out0

        # --- (2) seed one unacked deny, re-probe → withheld ---
        # Snapshot the cycle-entry count from step (1) so we can assert the
        # WITHHELD probe adds NO new cycle registration (step 1 legitimately
        # registered one — the SAME state dir is reused here).
        reg_path = state_dir / "lazy-prompt-registry.json"
        def _cycle_count():
            if not reg_path.exists():
                return 0
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            return sum(1 for e in reg.get("entries", []) if e.get("class") == "cycle")
        cycle_before = _cycle_count()

        weird_reason = "deny because the prompt had a 'quote' and spaces"
        _set_state_dir(state_dir)
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-x", denied_sha12="a" * 12,
                reason_head=weird_reason, prompt_head="HAND-COMPOSED dispatch",
                now=1.0,
            )
        finally:
            _clear_state_dir()

        r1 = probe()
        assert r1.returncode == 0, f"probe failed: {r1.stderr[:400]!r}"
        out1 = json.loads(r1.stdout)
        assert out1.get("route_overridden_by") == "pending-hardening-debt", out1
        assert "cycle_prompt" not in out1, (
            "withheld probe must NOT carry a cycle_prompt key"
        )
        assert "cycle_model" not in out1, (
            "withheld probe must NOT carry a cycle_model key"
        )
        cmd = out1.get("hardening_emit_command", "")
        assert "--emit-dispatch hardening" in cmd, cmd
        assert "trigger_kind=validate-deny" in cmd, cmd
        assert "item_id=feat-c" in cmd, cmd
        # The reason_head is shell-quoted in the command (contains a single quote
        # so shlex.quote produces the '"'"' escape sequence).
        import shlex as _shlex
        assert _shlex.quote(weird_reason) in cmd, (
            f"reason_head must appear shell-quoted in the command.\ncmd={cmd!r}"
        )
        # No NEW forward-route registration happened during the withheld probe.
        assert _cycle_count() == cycle_before, (
            "withheld probe must not register a new cycle emission "
            f"(before={cycle_before}, after={_cycle_count()})"
        )
        # STDERR carries the debt warning; stdout stayed parseable (asserted above).
        assert "pending_hardening" in r1.stderr and "withheld" in r1.stderr, (
            f"⚠ debt line must go to STDERR; got stderr={r1.stderr!r}"
        )

        # --- (3) debt present but NO marker → no withholding, no new fields ---
        state_dir_b = td_path / "state-b"
        state_dir_b.mkdir()
        env_b = dict(_os_env.environ)
        env_b["LAZY_STATE_DIR"] = str(state_dir_b)
        # Seed a deny in the no-marker dir (debt is marked-run scoped: without a
        # marker the probe never surfaces or withholds).
        _set_state_dir(state_dir_b)
        try:
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu-y", denied_sha12="b" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
        finally:
            _clear_state_dir()
        r2 = subprocess.run(
            [sys.executable, str(lazy_state),
             "--repeat-count", "--probe", "--emit-prompt",
             "--repo-root", str(fixture_repo)],
            capture_output=True, text=True, env=env_b,
        )
        assert r2.returncode == 0, f"no-marker probe failed: {r2.stderr[:400]!r}"
        out2 = json.loads(r2.stdout)
        assert "route_overridden_by" not in out2, out2
        assert "hardening_emit_command" not in out2, out2
        assert "pending_hardening" not in out2, (
            "no-marker probe must stay byte-identical — no debt enrichment"
        )
        assert "cycle_prompt" in out2, "no-marker probe must still emit forward route"
        assert r2.stderr.strip() == "", (
            f"no-marker probe must not emit the debt warning; stderr={r2.stderr!r}"
        )




def test_probe_withholds_forward_route_on_audit_obligation():
    """mechanize-prose-only-orchestrator-contracts (b) / D2-A: a marked run
    with an outstanding audit_obligation → a `--repeat-count --probe
    --emit-prompt` subprocess withholds the forward route
    (route_overridden_by == 'audit-obligation', NO cycle_prompt/cycle_model
    key) and surfaces a ready-to-run input_audit_emit_command naming the
    obligated item + cycle_kind. Discharging via `--emit-dispatch
    input-audit` (a REGISTERED, marker-present emission) clears the
    obligation so the NEXT probe emits the forward route again."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_repo = _build_phase8_fixture_repo(td_path)
        state_dir = td_path / "state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def probe():
            return subprocess.run(
                [sys.executable, str(lazy_state),
                 "--repeat-count", "--probe", "--emit-prompt",
                 "--repo-root", str(fixture_repo)],
                capture_output=True, text=True, env=env,
            )

        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(fixture_repo),
                max_cycles=10, now=_time.time(),
            )
        finally:
            _clear_state_dir()

        # --- (1) no obligation -> normal forward route ---
        r0 = probe()
        assert r0.returncode == 0, f"probe failed: {r0.stderr[:400]!r}"
        out0 = json.loads(r0.stdout)
        assert "cycle_prompt" in out0
        assert "route_overridden_by" not in out0, out0.get("route_overridden_by")

        # --- (2) arm the obligation directly on the marker (simulating a
        # --cycle-end after a /spec cycle that COMMITTED — a non-empty delta),
        # then re-probe -> withheld ---
        _set_state_dir(state_dir)
        try:
            lazy_core.record_audit_obligation(
                item_id="feat-c", cycle_kind="spec",
                begin_head_sha="begin000", end_sha="end111feat",
                cycle_summary="spec: feat-c baseline",
            )
        finally:
            _clear_state_dir()

        r1 = probe()
        assert r1.returncode == 0, f"probe failed: {r1.stderr[:400]!r}"
        out1 = json.loads(r1.stdout)
        assert out1.get("route_overridden_by") == "audit-obligation", out1
        assert "cycle_prompt" not in out1, (
            "withheld probe must NOT carry a cycle_prompt key"
        )
        assert "cycle_model" not in out1, (
            "withheld probe must NOT carry a cycle_model key"
        )
        cmd = out1.get("input_audit_emit_command", "")
        assert "--emit-dispatch input-audit" in cmd, cmd
        assert "item_id=feat-c" in cmd, cmd
        assert "cycle_kind=spec" in cmd, cmd
        # adhoc-audit-obligation-fires-on-zero-commit-failed-cycle P2: the emit
        # command binds the bracket's ACTUAL recorded end commit, never the
        # positional HEAD~1 proxy.
        assert "cycle_commit_sha=end111feat" in cmd, cmd
        assert "HEAD~1" not in cmd, (
            "a recorded end sha must replace the HEAD~1 proxy: " + cmd
        )

        # --- (3) discharge via a REGISTERED --emit-dispatch input-audit ---
        r_discharge = subprocess.run(
            [sys.executable, str(lazy_state),
             "--emit-dispatch", "input-audit",
             "--context", "item_name=Feature C",
             "--context", "spec_path=" + str(fixture_repo / "docs" / "features" / "feat-c"),
             "--context", "cycle_kind=spec",
             "--context", "cycle_summary=did the thing",
             "--context", "cycle_commit_sha=HEAD~1",
             "--context", "item_id=feat-c",
             "--context", "cwd=" + str(fixture_repo)],
            capture_output=True, text=True, env=env,
        )
        assert r_discharge.returncode == 0, r_discharge.stdout + r_discharge.stderr
        discharge_out = json.loads(r_discharge.stdout)
        assert discharge_out.get("dispatch_prompt"), discharge_out

        _set_state_dir(state_dir)
        try:
            assert lazy_core.pending_audit_obligation() is None, (
                "a registered --emit-dispatch input-audit must discharge the "
                "obligation"
            )
        finally:
            _clear_state_dir()

        # --- (4) next probe emits the forward route again ---
        r2 = probe()
        assert r2.returncode == 0, f"probe failed: {r2.stderr[:400]!r}"
        out2 = json.loads(r2.stdout)
        assert "route_overridden_by" not in out2, out2
        assert "cycle_prompt" in out2, (
            "discharged obligation must let the forward route emit again"
        )


def test_input_audit_emit_names_pending_audit_item_not_next_queued():
    """GAP 4 (adhoc-harden-bug-pipeline-gate-verdict-and-detector-gaps): when the
    audit obligation is owed for a PRIOR item while the current probe emits for a
    DIFFERENT (next-queued) item, the input_audit_emit_command must carry the
    PENDING-AUDIT item's own identity — not the next-queued item's name. The
    spec_path/item_id already branched on this; item_name used to be the wrong
    (current-probe) item's name."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        features = td_path / "fixture-repo" / "docs" / "features"
        features.mkdir(parents=True)
        # Two features: feat-c already COMPLETE (receipt) so the probe head is
        # feat-d; the obligation is armed for feat-c (the prior item).
        (features / "queue.json").write_text(json.dumps({
            "queue": [
                {"id": "feat-d", "name": "Feature D", "spec_dir": "feat-d", "tier": 1},
                {"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 2},
            ]
        }), encoding="utf-8")
        (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
        # feat-d: fresh Draft head (yields a forward route).
        dd = features / "feat-d"
        dd.mkdir()
        (dd / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
        (dd / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
        (dd / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
        # feat-c: the obligated (prior) item — just needs a dir for spec_path.
        cd = features / "feat-c"
        cd.mkdir()
        (cd / "SPEC.md").write_text(
            "# Spec\n\n**Status:** Draft\n", encoding="utf-8")
        fixture_repo = td_path / "fixture-repo"
        state_dir = td_path / "state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(fixture_repo),
                max_cycles=10, now=_time.time(),
            )
            lazy_core.record_audit_obligation(
                item_id="feat-c", cycle_kind="spec",
                begin_head_sha="begin000", end_sha="end111feat",
                cycle_summary="spec: feat-c baseline",
            )
        finally:
            _clear_state_dir()

        r = subprocess.run(
            [sys.executable, str(lazy_state),
             "--repeat-count", "--probe", "--emit-prompt",
             "--repo-root", str(fixture_repo)],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, f"probe failed: {r.stderr[:400]!r}"
        out = json.loads(r.stdout)
        assert out.get("route_overridden_by") == "audit-obligation", out
        cmd = out.get("input_audit_emit_command", "")
        # The obligated item's OWN identity — never the next-queued item's name.
        assert "item_id=feat-c" in cmd, cmd
        assert "item_name=feat-c" in cmd, cmd
        assert "Feature D" not in cmd, (
            "item_name must NOT be the next-queued (current-probe) item's name: " + cmd
        )


def test_audit_obligation_helpers_no_marker_and_non_audited_kind():
    """record_audit_obligation / pending_audit_obligation / discharge are all
    no-ops (never raise, write nothing) without a live run marker; a
    non-audited cycle_kind (e.g. execute-plan) never arms the obligation."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # No marker at all.
            assert lazy_core.record_audit_obligation("f1", "spec") is None
            assert lazy_core.pending_audit_obligation() is None
            assert lazy_core.discharge_audit_obligation() is False

            import time as _time
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            # Non-audited sub_skill never arms the obligation.
            lazy_core.record_audit_obligation("f1", "execute-plan")
            assert lazy_core.pending_audit_obligation() is None

            # plan-bug is DELIBERATELY excluded (lazy-bug-batch/SKILL.md Step
            # 1d.5 skip-condition prose: "plan-bug is a planning step, not a
            # SPEC/PHASES-authoring cycle — skip audit for plan-bug") — only
            # spec-bug/spec-phases are audited on the bug pipeline.
            # adhoc-audit-obligation-fires-on-zero-commit-failed-cycle: arming now
            # ALSO requires a non-empty commit delta (begin != end) — a real commit
            # landed. The armed obligation carries the end sha + subject.
            lazy_core.record_audit_obligation(
                "bug-1", "plan-bug", begin_head_sha="b0", end_sha="b1",
            )
            assert lazy_core.pending_audit_obligation() is None
            lazy_core.record_audit_obligation(
                "bug-1", "spec-bug",
                begin_head_sha="b0", end_sha="b1", cycle_summary="fix the thing",
            )
            assert lazy_core.pending_audit_obligation() == {
                "item_id": "bug-1", "cycle_kind": "spec-bug",
                "cycle_commit_sha": "b1", "cycle_summary": "fix the thing",
            }
            assert lazy_core.discharge_audit_obligation() is True

            # An audited kind on a real delta arms it; discharge clears it; a
            # second discharge is a no-op (False, not an error).
            lazy_core.record_audit_obligation(
                "f1", "plan-feature", begin_head_sha="c0", end_sha="c1",
            )
            obligation = lazy_core.pending_audit_obligation()
            assert obligation == {
                "item_id": "f1", "cycle_kind": "plan-feature",
                "cycle_commit_sha": "c1", "cycle_summary": "",
            }
            assert lazy_core.discharge_audit_obligation() is True
            assert lazy_core.pending_audit_obligation() is None
            assert lazy_core.discharge_audit_obligation() is False
        finally:
            _clear_state_dir()




def test_build_input_audit_emit_command_binds_supplied_cycle_commit_sha():
    """adhoc-audit-obligation-fires-on-zero-commit-failed-cycle P2: when the
    obligation supplies cycle_commit_sha (+ cycle_summary), the emit command
    binds them and does NOT emit the positional HEAD~1 proxy — closing the
    mis-targeted-diff half of the defect."""
    _guard()
    cmd = lazy_core.build_input_audit_emit_command(
        "lazy-state.py",
        item_id="feat-a", item_name="Feature A",
        spec_path="/repo/docs/features/feat-a", cycle_kind="spec",
        cwd="/repo",
        cycle_commit_sha="deadbeefcafe",
        cycle_summary="spec: feat-a baseline",
    )
    assert "cycle_commit_sha=deadbeefcafe" in cmd, cmd
    assert "HEAD~1" not in cmd, (
        "a supplied end sha must REPLACE the positional HEAD~1 proxy: " + cmd
    )
    assert "cycle_summary=" in cmd and "feat-a baseline" in cmd, cmd


def test_build_input_audit_emit_command_falls_back_to_head1_without_sha():
    """adhoc-audit-obligation-fires-on-zero-commit-failed-cycle P2: with no
    cycle_commit_sha supplied (a legacy/partial obligation), the command retains
    the ready-to-run HEAD~1 default + the git-log latest-subject fallback so it
    stays runnable."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # A non-git cwd → the latest-subject git call fails gracefully (empty
        # summary), but the HEAD~1 default is still emitted so the command runs.
        cmd = lazy_core.build_input_audit_emit_command(
            "lazy-state.py",
            item_id="feat-a", item_name="Feature A",
            spec_path="/repo/docs/features/feat-a", cycle_kind="spec",
            cwd=td,
        )
    assert "HEAD~1" in cmd, ("absent-sha fallback must keep HEAD~1: " + cmd)
    assert "cycle_summary=" in cmd, cmd


def test_record_decision_and_read_round_trip():
    """mechanize-prose-only-orchestrator-contracts (c) / D3-A:
    record_decision writes an atomic record read back verbatim by
    read_decision_record; re-recording OVERWRITES (not appends); the
    sentinel-path key normalizes across relative/absolute and backslash/
    forward-slash spellings of the SAME path; a never-recorded sentinel
    reads back None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            sentinel = str(Path(td) / "feat-1" / "NEEDS_INPUT.md")
            assert lazy_core.read_decision_record(sentinel) is None

            rec = lazy_core.record_decision(
                sentinel, "Option A", summary="picked A over B", now=1000.0,
            )
            assert rec["chosen_path"] == "Option A"
            assert rec["resolution_summary"] == "picked A over B"

            got = lazy_core.read_decision_record(sentinel)
            assert got is not None
            assert got["chosen_path"] == "Option A"
            assert got["resolution_summary"] == "picked A over B"

            # Path-spelling normalization: forward-slash lookup of the SAME
            # path still round-trips.
            alt_spelling = sentinel.replace("\\", "/")
            got_alt = lazy_core.read_decision_record(alt_spelling)
            assert got_alt is not None
            assert got_alt["chosen_path"] == "Option A"

            # Re-recording OVERWRITES, does not append a second entry.
            lazy_core.record_decision(sentinel, "Option B", now=2000.0)
            got2 = lazy_core.read_decision_record(sentinel)
            assert got2["chosen_path"] == "Option B"

            # A different, never-recorded sentinel is still None.
            other = str(Path(td) / "feat-2" / "NEEDS_INPUT.md")
            assert lazy_core.read_decision_record(other) is None
        finally:
            _clear_state_dir()


def test_record_decision_key_reconciles_relative_and_absolute():
    """adhoc-decision-key-relative-absolute-mismatch: a decision recorded with a
    REPRESENTATIVE relative sentinel path must be found by a lookup that passes the
    ABSOLUTE form of the same file, and vice versa — the exact record/emit
    disagreement that produced 'no recorded decision for sentinel'. Red on the
    prior pure-string normpath key (relative != absolute), green on the abspath
    key. No filesystem I/O beyond the state dir (record_decision never touches the
    sentinel file); abspath is resolved against the test process cwd on BOTH sides,
    so relative and absolute reconcile deterministically."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            rel_sentinel = os.path.join("feat-rel", "NEEDS_INPUT.md")  # relative
            abs_sentinel = os.path.abspath(rel_sentinel)               # its absolute form
            assert rel_sentinel != abs_sentinel  # the two spellings genuinely differ

            # Record RELATIVE → look up ABSOLUTE reconciles.
            lazy_core.record_decision(rel_sentinel, "Option R", now=1000.0)
            got_abs = lazy_core.read_decision_record(abs_sentinel)
            assert got_abs is not None, (
                "an absolute lookup must find a relatively-recorded decision"
            )
            assert got_abs["chosen_path"] == "Option R"

            # Record ABSOLUTE (overwrites the SAME key) → look up RELATIVE reconciles.
            lazy_core.record_decision(abs_sentinel, "Option A2", now=2000.0)
            got_rel = lazy_core.read_decision_record(rel_sentinel)
            assert got_rel is not None, (
                "a relative lookup must find an absolutely-recorded decision"
            )
            assert got_rel["chosen_path"] == "Option A2", (
                "the two spellings must map to ONE key (overwrite, not a 2nd entry)"
            )
        finally:
            _clear_state_dir()


def test_bind_decision_record_context_refuses_without_record_and_binds_when_present():
    """bind_decision_record_context (D3-A binding seam): non-apply-resolution
    classes and an apply-resolution context with no sentinel_path pass
    through unchanged; a sentinel_path with NO recorded decision raises
    ValueError naming the exact --record-decision command; a recorded
    decision REPLACES chosen_path/resolution_summary (record wins over any
    orchestrator-typed values already in context)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # Non-apply-resolution class -> pass through unchanged.
            ctx = {"sentinel_path": "/x/NEEDS_INPUT.md"}
            assert lazy_core.bind_decision_record_context(
                "hardening", ctx, "lazy-state.py"
            ) is ctx

            # apply-resolution with no sentinel_path -> pass through unchanged.
            ctx2 = {"item_id": "f1"}
            assert lazy_core.bind_decision_record_context(
                "apply-resolution", ctx2, "lazy-state.py"
            ) is ctx2

            # apply-resolution WITH sentinel_path but no record -> refuses.
            sentinel = str(Path(td) / "feat-1" / "NEEDS_INPUT.md")
            ctx3 = {"sentinel_path": sentinel, "item_id": "f1"}
            try:
                lazy_core.bind_decision_record_context(
                    "apply-resolution", ctx3, "lazy-state.py"
                )
                assert False, "expected ValueError with no recorded decision"
            except ValueError as exc:
                assert "--record-decision" in str(exc)
                assert sentinel in str(exc)

            # Record the decision, then binding replaces the two fields
            # (overriding any hand-typed values already in context).
            lazy_core.record_decision(
                sentinel, "Option A", summary="the operator's reasoning",
            )
            ctx4 = {
                "sentinel_path": sentinel,
                "item_id": "f1",
                "chosen_path": "STALE hand-typed value",
                "resolution_summary": "STALE",
            }
            bound = lazy_core.bind_decision_record_context(
                "apply-resolution", ctx4, "lazy-state.py"
            )
            assert bound["chosen_path"] == "Option A"
            assert bound["resolution_summary"] == "the operator's reasoning"
            assert bound["item_id"] == "f1"  # unrelated keys untouched
        finally:
            _clear_state_dir()




def test_emit_dispatch_hardening_no_longer_acks():
    """Phase 8 WU-8.2: `--emit-dispatch hardening` no longer acks the deny
    ledger.  Subprocess: marked run + 1 unacked deny → emit hardening → the
    ledger entry remains UNACKED (pending_hardening stays 1)."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        import time as _time
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            assert lazy_core.pending_hardening() == 1
        finally:
            _clear_state_dir()

        # Emit a hardening dispatch (registers, but must NOT ack).
        keys = _dispatch_requires("hardening")
        ctx_flags = []
        for k in keys:
            ctx_flags += ["--context", f"{k}=test-{k}"]
        if "item_id" not in keys:
            ctx_flags += ["--context", "item_id=feat-x"]
        r = subprocess.run(
            [sys.executable, str(lazy_state), "--emit-dispatch", "hardening"] + ctx_flags,
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, f"emit hardening failed: {r.stdout}{r.stderr}"

        _set_state_dir(state_dir)
        try:
            assert lazy_core.pending_hardening() == 1, (
                "emission must NOT ack the ledger (Phase 8 moves ack to guard-allow)"
            )
        finally:
            _clear_state_dir()




def test_detect_cycle_bracket_friction_symbols_present():
    """WU-2/3: the new public symbols exist on lazy_core."""
    _guard()
    for name in ("detect_cycle_bracket_friction", "append_friction_ledger_entry"):
        assert hasattr(lazy_core, name), f"Phase 2 missing {name}"




def test_append_friction_ledger_entry_round_trips():
    """WU-3: append_friction_ledger_entry appends a kind: process-friction,
    acked: false line to the SAME deny ledger; pending_hardening() then ≥1 and
    the entry is readable via read_deny_ledger."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.pending_hardening() == 0
            ok = lazy_core.append_friction_ledger_entry(
                "cycle-bracket-break",
                "run identity changed mid-cycle",
                now=123.0,
            )
            assert ok is True
            assert lazy_core.pending_hardening() == 1
            entries = lazy_core.read_deny_ledger()
            assert len(entries) == 1, entries
            e = entries[0]
            assert e["kind"] == "process-friction", e
            assert e["acked"] is False, e
            assert e["reason_head"] == "cycle-bracket-break", e
            assert "run identity changed" in e["detail"], e
        finally:
            _clear_state_dir()




def test_append_friction_ledger_entry_shares_ledger_with_denies():
    """WU-3: friction entries and deny entries co-exist in the SAME ledger and
    both count toward pending_hardening()."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_deny_ledger_entry(
                "tu1", "abc123abc123", "validate-deny reason", "prompt head",
            )
            lazy_core.append_friction_ledger_entry(
                "unexpected-commits", "HEAD advanced 4 beyond budget",
            )
            assert lazy_core.pending_hardening() == 2
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# efficacy-future-check-unenforced-orchestrator-prose (D1) — the end-of-run
# efficacy-flush breadcrumb + the --run-end gate.
# ---------------------------------------------------------------------------


def test_efficacy_breadcrumb_marker_gated_and_moot():
    """drop_efficacy_breadcrumb is MARKER-GATED (no live run marker → no write,
    returns False, no file). efficacy_breadcrumb_present with no marker returns
    True — the gate is MOOT (a --run-end with no marker is an idempotent no-op
    that must not be refused)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.drop_efficacy_breadcrumb() is False
            crumb = Path(td) / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            assert not crumb.exists(), "no marker → no breadcrumb file"
            assert lazy_core.efficacy_breadcrumb_present() is True, "no marker → moot"
        finally:
            _clear_state_dir()




def test_efficacy_breadcrumb_absent_present_false_then_drop_true():
    """With a live run marker: efficacy_breadcrumb_present is False BEFORE the
    trio runs (the gate would REFUSE), and True AFTER drop_efficacy_breadcrumb
    (the gate PASSES). This is the refuse-without / pass-with pair at the helper
    level that the --run-end gate wires.

    Coverage-aware update: the marker's own repo_root (`td`) is made
    INTERVENTIONS-BEARING so that after the drop, interventions_covered is True
    and the gate is satisfied under the new coverage-aware semantics."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td, max_cycles=5,
            )
            _make_interventions_bearing_repo(Path(td))
            # Before the flush: no breadcrumb → gate would refuse.
            assert lazy_core.efficacy_breadcrumb_present() is False
            # Trio runs, covering the interventions-bearing repo_root → gate passes.
            assert lazy_core.drop_efficacy_breadcrumb() is True
            assert lazy_core.efficacy_breadcrumb_present() is True
        finally:
            _clear_state_dir()




def test_efficacy_breadcrumb_present_requires_interventions_coverage():
    """RED: efficacy_breadcrumb_present must be COVERAGE-AWARE, not just
    presence-aware. A breadcrumb dropped for a scope that is NOT
    interventions-bearing must NOT satisfy the gate (interventions_covered is
    False) — the interventions-bearing scope was never actually covered. Once a
    SEPARATE interventions-bearing scope is covered for the SAME run
    (accumulating into the same breadcrumb), the gate is satisfied."""
    _guard()
    with tempfile.TemporaryDirectory() as td, \
         tempfile.TemporaryDirectory() as iv_td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td, max_cycles=5,
            )
            # `td` itself is NOT interventions-bearing (no queue.json opt-in).
            assert lazy_core.drop_efficacy_breadcrumb() is True, (
                "breadcrumb write must still succeed (marker-gated only)"
            )
            assert lazy_core.efficacy_breadcrumb_present() is False, (
                "a breadcrumb covering only a non-interventions-bearing scope "
                "must NOT satisfy the gate"
            )

            # Now cover a SEPARATE interventions-bearing scope for the SAME run.
            interventions_root = Path(iv_td)
            _make_interventions_bearing_repo(interventions_root)
            assert lazy_core.drop_efficacy_breadcrumb(str(interventions_root)) is True
            assert lazy_core.efficacy_breadcrumb_present() is True, (
                "once an interventions-bearing scope is covered this run, "
                "the gate must pass"
            )
        finally:
            _clear_state_dir()




def test_efficacy_breadcrumb_clear_removes_file():
    """clear_efficacy_breadcrumb removes the breadcrumb (best-effort) — called by
    --run-end after teardown so the next run starts clean."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td, max_cycles=5,
            )
            assert lazy_core.drop_efficacy_breadcrumb() is True
            crumb = Path(td) / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            assert crumb.exists()
            lazy_core.clear_efficacy_breadcrumb()
            assert not crumb.exists()
        finally:
            _clear_state_dir()




def _run_end_efficacy_gate_cli(script_name: str):
    """Shared CLI subprocess exercise for the --run-end efficacy-flush gate on
    either state script: (1) marker present + NO breadcrumb → REFUSE (exit 1,
    marker kept); (2) marker present + breadcrumb → PASS (exit 0, marker gone);
    (3) marker present + NO breadcrumb + --efficacy-skip-authorized → PASS (exit
    0, efficacy_skip note)."""
    _guard()
    state_script = _SCRIPTS_DIR / script_name
    pipeline = "bug" if script_name == "bug-state.py" else "feature"
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo = td_path / "repo"
        repo.mkdir()
        # interventions-telemetry-split-brain WU-3: the run-end efficacy gate is
        # coverage-aware — the breadcrumb discharges it only when it covered an
        # interventions-bearing scope.  The marker's repo_root IS this fixture
        # repo, so make it interventions-bearing so drop_efficacy_breadcrumb()
        # (which now prefers the marker's own repo_root) records
        # interventions_covered=True and the WITH-breadcrumb case exits 0.
        _make_interventions_bearing_repo(repo)
        state_dir = td_path / "state"
        state_dir.mkdir()
        marker_file = state_dir / lazy_core._MARKER_FILENAME

        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def _write_marker():
            _set_state_dir(state_dir)
            try:
                lazy_core.write_run_marker(
                    pipeline=pipeline, cloud=False, repo_root=str(repo),
                    max_cycles=5,
                )
            finally:
                _clear_state_dir()

        def _run_end(*extra):
            return subprocess.run(
                [sys.executable, str(state_script), "--run-end",
                 "--repo-root", str(repo), *extra],
                capture_output=True, text=True, env=env,
            )

        # (1) No breadcrumb → refuse, marker kept.
        _write_marker()
        r1 = _run_end()
        assert r1.returncode == 1, (
            f"{script_name} --run-end without breadcrumb must exit 1; "
            f"got {r1.returncode}; stdout={r1.stdout[:400]!r}"
        )
        out1 = json.loads(r1.stdout)
        assert out1.get("run_marker_deleted") is False, out1
        assert "efficacy-flush breadcrumb" in out1.get("refused", ""), out1
        assert marker_file.exists(), "refused run-end must LEAVE the marker in place"

        # (2) Breadcrumb present → pass, marker deleted.
        _set_state_dir(state_dir)
        try:
            assert lazy_core.drop_efficacy_breadcrumb() is True
        finally:
            _clear_state_dir()
        r2 = _run_end()
        assert r2.returncode == 0, (
            f"{script_name} --run-end WITH breadcrumb must exit 0; "
            f"got {r2.returncode}; stdout={r2.stdout[:400]!r}"
        )
        out2 = json.loads(r2.stdout)
        assert out2.get("run_marker_deleted") is True, out2
        assert not marker_file.exists(), "passed run-end must delete the marker"

        # (3) No breadcrumb + --efficacy-skip-authorized → pass with note.
        _write_marker()
        r3 = _run_end("--efficacy-skip-authorized")
        assert r3.returncode == 0, (
            f"{script_name} --run-end --efficacy-skip-authorized must exit 0; "
            f"got {r3.returncode}; stdout={r3.stdout[:400]!r}"
        )
        out3 = json.loads(r3.stdout)
        assert out3.get("run_marker_deleted") is True, out3
        assert "efficacy_skip" in out3, out3




def test_run_end_efficacy_gate_lazy_state_cli():
    """lazy-state.py --run-end enforces the efficacy-flush gate: refuse without
    breadcrumb, pass with, override via --efficacy-skip-authorized."""
    _run_end_efficacy_gate_cli("lazy-state.py")




def test_run_end_efficacy_gate_bug_state_cli():
    """bug-state.py --run-end mirrors the efficacy-flush gate (coupled-pair)."""
    _run_end_efficacy_gate_cli("bug-state.py")




# ---------------------------------------------------------------------------
# harness-telemetry-ledger Phase 1 — the telemetry emitter substrate.
#
# One shared fail-open writer (`append_telemetry_event`, D2-A) cloned from the
# deny-ledger contract, marker-gated (D3-A) via a RAW NON-DESTRUCTIVE marker
# read (a failed emit must never delete a stale marker — the exit-3 refusal
# paths promise zero side effects), a torn-line/unknown-`v`-tolerant reader
# (D1-A), size-based rotation (D6-B), and the D5-B cloud run-end segment flush.
# Hermetic via LAZY_STATE_DIR temp dirs (the Phase-1 discipline throughout this
# file).
# ---------------------------------------------------------------------------


def test_telemetry_symbols_present():
    """All harness-telemetry-ledger Phase 1 public symbols exist on lazy_core."""
    _guard()
    expected = [
        "_TELEMETRY_LEDGER_FILENAME",
        "_TELEMETRY_SCHEMA_VERSION",
        "_TELEMETRY_ROTATE_BYTES",
        "_TELEMETRY_ROTATED_SEGMENTS",
        "TELEMETRY_HALT_TERMINAL_REASONS",
        "append_telemetry_event",
        "read_telemetry_events",
        "flush_cloud_telemetry_segment",
    ]
    missing = [s for s in expected if not hasattr(lazy_core, s)]
    assert not missing, f"missing telemetry symbols: {missing}"
    assert lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME == "lazy-telemetry.jsonl"
    # The D4-B halt vocabulary (dispatches whose terminal_reason is a halt).
    for reason in ("blocked", "needs-input", "needs-spec-input", "needs-research",
                   "completion-unverified", "blocked-misnamed"):
        assert reason in lazy_core.TELEMETRY_HALT_TERMINAL_REASONS, reason




def test_telemetry_append_envelope_shape_and_now_injection():
    """append → read: the D1 envelope, marker-derived run identity, FIFO order,
    injectable `now` for a deterministic epoch `ts`."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            import time as _time
            now0 = _time.time()
            marker = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=9, now=now0,
            )
            ok1 = lazy_core.append_telemetry_event(
                "run-start", data={"cloud": False, "max_cycles": 9}, now=now0 + 1.0,
            )
            ok2 = lazy_core.append_telemetry_event(
                "cycle-begin", item_id="feat-x", data={"kind": "real"},
                now=now0 + 2.0,
            )
            assert ok1 is True and ok2 is True, (ok1, ok2)
            events = lazy_core.read_telemetry_events()
            assert len(events) == 2, events
            first, second = events
            # Envelope shape (D1-A): v / ts / run_id / pipeline / event /
            # item_id / data — exactly these keys.
            assert set(first) == {"v", "ts", "run_id", "pipeline", "event",
                                  "item_id", "data"}, first
            assert first["v"] == lazy_core._TELEMETRY_SCHEMA_VERSION, first
            assert first["ts"] == now0 + 1.0, first
            assert first["run_id"] == marker["started_at"], first
            assert first["pipeline"] == "feature", first
            assert first["event"] == "run-start", first
            assert first["item_id"] is None, first
            assert first["data"] == {"cloud": False, "max_cycles": 9}, first
            # FIFO order + item_id threading.
            assert second["event"] == "cycle-begin", second
            assert second["item_id"] == "feat-x", second
            assert second["run_id"] == first["run_id"], "one run → one run_id"
        finally:
            _clear_state_dir()




def test_telemetry_marker_gated_no_marker_no_emit():
    """D3-A: no run marker → no ledger file, no line, emitter returns False.
    Bare probes / unmarked interactive invocations must stay side-effect-free."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            ok = lazy_core.append_telemetry_event("run-start", now=1000.0)
            assert ok is False, "no marker must gate the emit (False)"
            ledger = Path(td) / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME
            assert not ledger.exists(), "no marker → no ledger file created"
            assert lazy_core.read_telemetry_events() == []
        finally:
            _clear_state_dir()




def test_telemetry_fail_open_unwritable_dir():
    """D2-A: an unwritable state dir → emitter swallows and returns False; the
    reader is equally non-fatal. (Same shape as the deny-ledger fail-open test.)"""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        bad_dir = Path(td) / "not-a-dir"
        bad_dir.write_text("i am a file, not a directory\n", encoding="utf-8")
        _set_state_dir(bad_dir)
        try:
            ok = lazy_core.append_telemetry_event("run-start", now=1.0)
            assert ok is False, "unwritable state dir must fail-open (False)"
            assert lazy_core.read_telemetry_events() == []
        finally:
            _clear_state_dir()




def test_telemetry_reader_tolerates_torn_and_unknown_v():
    """D1-A reader contract: blank lines, torn appends, non-dict JSON, and
    unknown schema versions are skipped — never fatal."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            ledger = Path(td) / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME
            good = json.dumps({
                "v": 1, "ts": 1.0, "run_id": "2026-07-04T00:00:00Z",
                "pipeline": "feature", "event": "run-start",
                "item_id": None, "data": {},
            })
            unknown_v = json.dumps({"v": 99, "ts": 2.0, "event": "future-thing"})
            non_dict = json.dumps(["not", "a", "dict"])
            torn = '{"v": 1, "ts": 3.0, "event": "cycle-b'
            ledger.write_text(
                "\n".join([good, unknown_v, non_dict, torn, ""]) + "\n",
                encoding="utf-8",
            )
            events = lazy_core.read_telemetry_events()
            assert len(events) == 1, f"only the good v1 line must survive: {events}"
            assert events[0]["event"] == "run-start", events
        finally:
            _clear_state_dir()




def test_telemetry_read_with_provenance():
    """with_provenance=True stamps _source/_line (1-based physical line number)
    for the retro's per-figure ledger citations (D8)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            ledger = Path(td) / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME
            line1 = json.dumps({"v": 1, "ts": 1.0, "run_id": "r", "pipeline":
                                "feature", "event": "run-start", "item_id": None,
                                "data": {}})
            line3 = json.dumps({"v": 1, "ts": 2.0, "run_id": "r", "pipeline":
                                "feature", "event": "run-end", "item_id": None,
                                "data": {}})
            # Line 2 is torn → skipped, but physical numbering must be preserved.
            ledger.write_text(line1 + "\n" + '{"torn' + "\n" + line3 + "\n",
                              encoding="utf-8")
            events = lazy_core.read_telemetry_events(with_provenance=True)
            assert len(events) == 2, events
            assert events[0]["_line"] == 1 and events[1]["_line"] == 3, events
            assert events[0]["_source"].endswith(
                lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME), events
            # Default read stays provenance-free (envelope purity).
            plain = lazy_core.read_telemetry_events()
            assert all("_line" not in e and "_source" not in e for e in plain)
        finally:
            _clear_state_dir()




def test_telemetry_rotation_shift_and_reader_order():
    """D6-B: an over-cap active file rotates active → .1 (shifting .1→.2 …,
    dropping the oldest beyond the segment count) BEFORE the append; the reader
    walks rotated segments oldest-first then the active file."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            import time as _time
            now = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r", now=now,
            )
            ledger = Path(td) / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME
            # Pre-seed the full rotated chain so the shift + oldest-drop is
            # observable in one append.
            seg = lambda i: Path(str(ledger) + f".{i}")  # noqa: E731
            for i in range(1, lazy_core._TELEMETRY_ROTATED_SEGMENTS + 1):
                seg(i).write_text(
                    json.dumps({"v": 1, "ts": float(-i), "run_id": "old",
                                "pipeline": "feature", "event": f"seg-{i}",
                                "item_id": None, "data": {}}) + "\n",
                    encoding="utf-8",
                )
            active_line = json.dumps({"v": 1, "ts": 0.5, "run_id": "old",
                                      "pipeline": "feature", "event": "active-old",
                                      "item_id": None, "data": {}})
            ledger.write_text(active_line + "\n", encoding="utf-8")
            # Shrink the cap so the seeded active file is over it.
            orig_cap = lazy_core.ledgers._TELEMETRY_ROTATE_BYTES
            lazy_core.ledgers._TELEMETRY_ROTATE_BYTES = 8
            try:
                ok = lazy_core.append_telemetry_event("cycle-begin",
                                                      item_id="f", now=now + 1)
            finally:
                lazy_core.ledgers._TELEMETRY_ROTATE_BYTES = orig_cap
            assert ok is True
            n = lazy_core._TELEMETRY_ROTATED_SEGMENTS
            # active rotated to .1; old .1 shifted to .2; …; old .N dropped.
            assert json.loads(seg(1).read_text(encoding="utf-8"))["event"] == \
                "active-old", ".1 must be the pre-rotation active file"
            assert json.loads(seg(2).read_text(encoding="utf-8"))["event"] == \
                "seg-1", ".2 must be the old .1"
            assert json.loads(seg(n).read_text(encoding="utf-8"))["event"] == \
                f"seg-{n-1}", f".{n} must be the old .{n-1} (old .{n} dropped)"
            # The fresh active file holds only the new event.
            active_events = [json.loads(l) for l in
                             ledger.read_text(encoding="utf-8").splitlines() if l]
            assert [e["event"] for e in active_events] == ["cycle-begin"]
            # Reader order: oldest segment first … then the active file last.
            order = [e["event"] for e in lazy_core.read_telemetry_events()]
            assert order == [f"seg-{n-1}"] + \
                [f"seg-{i}" for i in range(n - 2, 0, -1)] + \
                ["active-old", "cycle-begin"], order
        finally:
            _clear_state_dir()




def test_flush_cloud_telemetry_segment_writes_colon_stripped_segment():
    """D5-B: a cloud run's flush writes docs/telemetry/cloud/<run_id minus
    colons>.jsonl containing ONLY this run's lines; returns {path, events}."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        repo = Path(td) / "repo"
        repo.mkdir()
        _set_state_dir(state)
        try:
            import time as _time
            now = _time.time()
            marker = lazy_core.write_run_marker(
                pipeline="feature", cloud=True, repo_root=str(repo), now=now,
            )
            run_id = marker["started_at"]
            # A foreign (previous-run) line must NOT be flushed.
            ledger = state / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME
            ledger.write_text(
                json.dumps({"v": 1, "ts": 1.0, "run_id": "2020-01-01T00:00:00Z",
                            "pipeline": "feature", "event": "run-start",
                            "item_id": None, "data": {}}) + "\n",
                encoding="utf-8",
            )
            lazy_core.append_telemetry_event("run-start", now=now + 1)
            lazy_core.append_telemetry_event("run-end", now=now + 2)
            result = lazy_core.flush_cloud_telemetry_segment(repo, now=now + 3)
            assert isinstance(result, dict), "cloud flush must report its segment"
            assert result["events"] == 2, result
            seg_path = Path(result["path"])
            assert seg_path.parent == repo / "docs" / "telemetry" / "cloud"
            assert ":" not in seg_path.name, (
                "segment filename must be Windows-checkout-safe (no colons)"
            )
            assert seg_path.name == run_id.replace(":", "") + ".jsonl", seg_path
            lines = [json.loads(l) for l in
                     seg_path.read_text(encoding="utf-8").splitlines() if l]
            assert [e["event"] for e in lines] == ["run-start", "run-end"], lines
            assert all(e["run_id"] == run_id for e in lines), (
                "only the live run's lines may flush (run_id field unchanged)"
            )
        finally:
            _clear_state_dir()




def test_flush_cloud_telemetry_segment_noop_cases():
    """D5-B gating: no marker / non-cloud marker / zero matching events → None,
    nothing written under docs/telemetry/."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        repo = Path(td) / "repo"
        repo.mkdir()
        _set_state_dir(state)
        try:
            import time as _time
            now = _time.time()
            # (a) No marker.
            assert lazy_core.flush_cloud_telemetry_segment(repo, now=now) is None
            # (b) Workstation (non-cloud) marker with events.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(repo), now=now,
            )
            lazy_core.append_telemetry_event("run-start", now=now + 1)
            assert lazy_core.flush_cloud_telemetry_segment(repo, now=now + 2) is None
            # (c) Cloud marker but no events for THIS run (fresh started_at).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=True, repo_root=str(repo), now=now + 100,
            )
            assert lazy_core.flush_cloud_telemetry_segment(repo, now=now + 101) is None
            assert not (repo / "docs" / "telemetry").exists(), (
                "no-op flush must not create docs/telemetry/"
            )
        finally:
            _clear_state_dir()




def test_append_commit_bracket_roundtrip():
    """append_commit_bracket writes one JSONL record; read_commit_brackets
    returns it filtered by item id (foreign ids invisible)."""
    _guard()
    assert hasattr(lazy_core, "append_commit_bracket"), (
        "lazy_core.append_commit_bracket is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            ok = lazy_core.append_commit_bracket("feat-a", "aaa111", "bbb222", now=1000.0)
            assert ok is True, "append must return True on success"
            ok2 = lazy_core.append_commit_bracket("feat-b", "ccc333", "ddd444", now=1001.0)
            assert ok2 is True
            got = lazy_core.read_commit_brackets("feat-a")
            assert len(got) == 1, f"expected 1 bracket for feat-a, got {got}"
            assert got[0]["begin_sha"] == "aaa111" and got[0]["end_sha"] == "bbb222"
            assert got[0]["feature_id"] == "feat-a"
            assert lazy_core.read_commit_brackets("feat-none") == []
            # The ledger is JSONL — one JSON object per line.
            lines = (state_dir / "lazy-commit-brackets.jsonl").read_text(
                encoding="utf-8").strip().splitlines()
            assert len(lines) == 2
            for ln in lines:
                json.loads(ln)
        finally:
            _clear_state_dir()




def test_append_commit_bracket_fail_open():
    """A ledger path that cannot be opened (a DIRECTORY squats on the JSONL
    name) → append returns False, never raises (fail-open — the --cycle-end
    clear must always proceed). read_commit_brackets likewise degrades to []."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        # Squat a directory on the ledger filename so open(..., "a") fails.
        (state_dir / "lazy-commit-brackets.jsonl").mkdir()
        _set_state_dir(state_dir)
        try:
            ok = lazy_core.append_commit_bracket("feat-a", "aaa", "bbb")
            assert ok is False, "append must return False (not raise) on a write failure"
            assert lazy_core.read_commit_brackets("feat-a") == []
        finally:
            _clear_state_dir()




def test_record_cycle_commit_bracket_appends_real_bracket():
    """With a live cycle marker snapshotting begin_head_sha and HEAD advanced
    past it, record_cycle_commit_bracket appends {feature_id, begin, end}."""
    _guard()
    assert hasattr(lazy_core, "record_cycle_commit_bracket"), (
        "lazy_core.record_cycle_commit_bracket is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo = td_path / "repo"
        repo.mkdir()
        begin = _prov_git_fixture_repo(repo)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_cycle_marker(
                feature_id="feat-br", nonce="n1", begin_head_sha=begin,
            )
            end = _prov_git_commit_file(repo, "src/a.py", "work")
            rec = lazy_core.record_cycle_commit_bracket(repo_root=repo)
            assert rec is not None, "a real bracket must be recorded"
            assert rec["feature_id"] == "feat-br"
            assert rec["begin_sha"] == begin and rec["end_sha"] == end
            got = lazy_core.read_commit_brackets("feat-br")
            assert len(got) == 1 and got[0]["end_sha"] == end
        finally:
            _clear_state_dir()




def test_record_cycle_commit_bracket_skips_empty():
    """begin == HEAD (no commits this cycle) → nothing appended, returns None.
    No cycle marker at all → None. Both degrade silently (fail-open)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo = td_path / "repo"
        repo.mkdir()
        head = _prov_git_fixture_repo(repo)
        state_dir = td_path / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # (a) no marker → None.
            assert lazy_core.record_cycle_commit_bracket(repo_root=repo) is None
            # (b) marker with begin == current HEAD → empty bracket skipped.
            lazy_core.write_cycle_marker(
                feature_id="feat-empty", nonce="n1", begin_head_sha=head,
            )
            assert lazy_core.record_cycle_commit_bracket(repo_root=repo) is None
            assert lazy_core.read_commit_brackets("feat-empty") == []
            # (c) marker without begin_head_sha (degraded snapshot) → None.
            lazy_core.write_cycle_marker(feature_id="feat-nogit", nonce="n2")
            assert lazy_core.record_cycle_commit_bracket(repo_root=repo) is None
        finally:
            _clear_state_dir()




def test_write_provenance_distillate_and_index_deterministic():
    """write_provenance emits the D2-A distillate (frontmatter + deterministic
    body) and the D3-A index (sorted POSIX keys); re-running is byte-stable."""
    _guard()
    assert hasattr(lazy_core, "write_provenance"), (
        "lazy_core.write_provenance is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _prov_spec_dir(repo_root, "feat-prov")
        result = lazy_core.write_provenance(
            repo_root, spec_dir, "feat-prov", "feature",
            ["abc1234", "def5678"],
            ["user/scripts/lazy_core.py", "src/a.py"],
            provenance="pipeline-gated", derivation="commit-brackets",
            date="2026-07-04",
            validated_line="Validated via: mcp (2/2). Receipt: COMPLETED.md (provenance: gated).",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        dist_path = spec_dir / "IMPLEMENTED.md"
        assert dist_path.exists(), "IMPLEMENTED.md was not written"
        meta = lazy_core.parse_sentinel(dist_path)
        assert meta.get("kind") == "implemented"
        assert meta.get("feature_id") == "feat-prov"
        assert meta.get("provenance") == "pipeline-gated"
        assert meta.get("derivation") == "commit-brackets"
        assert [str(c) for c in meta.get("commits")] == ["abc1234", "def5678"]
        assert [str(d) for d in meta.get("decisions")] == ["L1", "L2"]
        body = dist_path.read_text(encoding="utf-8")
        # What-shipped = the SPEC's leading `>` summary, verbatim (unwrapped).
        assert "Distill each completed item into a durable ledger artifact" in body
        assert "L1 — one writer, two triggers" in body
        assert "Validated via: mcp (2/2)" in body
        # Index: sorted POSIX keys → per-file entry rows.
        index_path = repo_root / "docs" / "provenance-index.json"
        assert index_path.exists(), "docs/provenance-index.json was not written"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert list(index.keys()) == sorted(index.keys())
        assert index["user/scripts/lazy_core.py"] == [
            {"id": "feat-prov", "type": "feature", "provenance": "pipeline-gated"}
        ]
        assert "src/a.py" in index
        # Idempotency: re-running the SAME write is byte-stable.
        dist_before = dist_path.read_bytes()
        index_before = index_path.read_bytes()
        result2 = lazy_core.write_provenance(
            repo_root, spec_dir, "feat-prov", "feature",
            ["abc1234", "def5678"],
            ["user/scripts/lazy_core.py", "src/a.py"],
            provenance="pipeline-gated", derivation="commit-brackets",
            date="2026-07-04",
            validated_line="Validated via: mcp (2/2). Receipt: COMPLETED.md (provenance: gated).",
        )
        assert result2["ok"] is True
        assert dist_path.read_bytes() == dist_before, "distillate must be byte-stable"
        assert index_path.read_bytes() == index_before, "index must be byte-stable"




def test_write_provenance_replaces_item_rows_not_duplicates():
    """Re-writing the SAME item with a different file set REPLACES that item's
    rows (no duplicates, stale rows dropped); other items' rows survive."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_a = _prov_spec_dir(repo_root, "feat-a")
        spec_b = _prov_spec_dir(repo_root, "feat-b")
        assert lazy_core.write_provenance(
            repo_root, spec_a, "feat-a", "feature", ["aaa1111"],
            ["src/one.py", "src/two.py"], date="2026-07-04")["ok"]
        assert lazy_core.write_provenance(
            repo_root, spec_b, "feat-b", "feature", ["bbb2222"],
            ["src/one.py"], date="2026-07-04")["ok"]
        # Re-link feat-a with a NARROWER set: src/two.py row must disappear.
        assert lazy_core.write_provenance(
            repo_root, spec_a, "feat-a", "feature", ["aaa1111"],
            ["src/one.py"], date="2026-07-04")["ok"]
        index = json.loads(
            (repo_root / "docs" / "provenance-index.json").read_text(encoding="utf-8"))
        one_ids = [(e["id"], e["type"]) for e in index["src/one.py"]]
        assert one_ids.count(("feat-a", "feature")) == 1, f"duplicated rows: {index}"
        assert ("feat-b", "feature") in one_ids, "other item's rows must survive"
        assert "src/two.py" not in index, f"stale row must be dropped: {index}"




def test_write_provenance_dry_run_mutates_nothing():
    """dry_run computes the full result (preview included) and writes NOTHING."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _prov_spec_dir(repo_root, "feat-dry")
        result = lazy_core.write_provenance(
            repo_root, spec_dir, "feat-dry", "feature", ["abc1234"],
            ["src/a.py"], date="2026-07-04", dry_run=True)
        assert result["ok"] is True and result.get("dry_run") is True
        assert result.get("files") == ["src/a.py"]
        assert "distillate_preview" in result and "kind: implemented" in result["distillate_preview"]
        assert not (spec_dir / "IMPLEMENTED.md").exists(), "dry_run must not write"
        assert not (repo_root / "docs" / "provenance-index.json").exists()




def test_item_scope_byte_identical_without_foreign_commits():
    """No foreign harden commit → the pre-existing range-derived file set is
    returned unchanged (byte-identical common-case behavior)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        seed = _prov_git_fixture_repo(repo_root)
        spec_dir = repo_root / "docs" / "features" / "feat-plain"
        spec_dir.mkdir(parents=True)
        end = _prov_git_commit_file(
            repo_root, "docs/features/feat-plain/PHASES.md",
            "chore(feat-plain): mark plan complete")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            assert lazy_core.append_commit_bracket("feat-plain", seed, end)
            files = lazy_core._item_commit_touched_files(spec_dir, repo_root)
            range_files = lazy_core.derive_touched_from_range(
                repo_root, f"{seed}..{end}")["files"]
        finally:
            _clear_state_dir()
        assert files == range_files, f"expected {range_files}, got {files}"
        assert "docs/features/feat-plain/PHASES.md" in files




# ---------------------------------------------------------------------------
# code-doc-provenance-linkage — Phase 3: manual path (--link-provenance)
# ---------------------------------------------------------------------------

def test_link_provenance_manual_entry_shape_matches_pipeline():
    """One writer, two triggers (D1-B/D8): a manual link of a commit range
    produces index rows byte-identical in SHAPE to pipeline rows (same keys),
    differing only in provenance; the distillate carries provenance: manual +
    derivation: commit-range + linked_by."""
    _guard()
    assert hasattr(lazy_core, "link_provenance"), (
        "lazy_core.link_provenance is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        begin = _prov_git_fixture_repo(repo_root)
        _prov_spec_dir(repo_root, "feat-man")
        end = _prov_git_commit_file(repo_root, "src/man.py", "teammate work")
        body_file = repo_root / "body.md"
        body_file.write_text("Operator-approved summary of the teammate PR.\n",
                             encoding="utf-8")
        result = lazy_core.link_provenance(
            repo_root, "feat-man",
            commit_range=f"{begin}..{end}",
            body_file=body_file, linked_by="operator", date="2026-07-04",
        )
        assert result["ok"] is True, f"got {result}"
        meta = lazy_core.parse_sentinel(
            repo_root / "docs" / "features" / "feat-man" / "IMPLEMENTED.md")
        assert meta.get("provenance") == "manual"
        assert meta.get("derivation") == "commit-range"
        assert meta.get("linked_by") == "operator"
        assert [str(c) for c in meta.get("commits")] == [end[:7]]
        body = (repo_root / "docs" / "features" / "feat-man" /
                "IMPLEMENTED.md").read_text(encoding="utf-8")
        assert "Operator-approved summary of the teammate PR." in body
        index = json.loads(
            (repo_root / "docs" / "provenance-index.json").read_text(encoding="utf-8"))
        entry = index["src/man.py"][0]
        # SHAPE parity with pipeline entries: exactly {id, type, provenance}.
        assert sorted(entry.keys()) == ["id", "provenance", "type"], f"got {entry}"
        assert entry["provenance"] == "manual"




def test_link_provenance_dry_run_mutates_nothing():
    """--dry-run derives + previews and writes NOTHING (index bytes + mtime
    unchanged, no distillate)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        # Spec dir seeded BEFORE the fixture's seed commit so the linked range
        # contains ONLY the src file.
        spec_dir = _prov_spec_dir(repo_root, "feat-mandry")
        begin = _prov_git_fixture_repo(repo_root)
        end = _prov_git_commit_file(repo_root, "src/dry.py", "dry work")
        # Seed an index so purity is observable on a real file.
        index_path = repo_root / "docs" / "provenance-index.json"
        index_path.write_text('{\n  "src/seed.py": []\n}\n', encoding="utf-8")
        before = index_path.read_bytes()
        mtime_before = index_path.stat().st_mtime_ns
        result = lazy_core.link_provenance(
            repo_root, "feat-mandry",
            commit_range=f"{begin}..{end}", dry_run=True, date="2026-07-04",
        )
        assert result["ok"] is True, f"got {result}"
        assert result.get("dry_run") is True
        assert result.get("files") == ["src/dry.py"]
        assert not (spec_dir / "IMPLEMENTED.md").exists()
        assert index_path.read_bytes() == before
        assert index_path.stat().st_mtime_ns == mtime_before




def test_link_provenance_unresolvable_range_refuses_with_no_writes():
    """An unresolvable range aborts with the producer's refusal text; nothing
    is half-written."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        spec_dir = _prov_spec_dir(repo_root, "feat-badrange")
        result = lazy_core.link_provenance(
            repo_root, "feat-badrange",
            commit_range="deadbeef..cafebabe", date="2026-07-04",
        )
        assert result["ok"] is False and result["refused"], f"got {result}"
        assert not (spec_dir / "IMPLEMENTED.md").exists()
        assert not (repo_root / "docs" / "provenance-index.json").exists()




def test_link_provenance_resolves_bug_and_archive_residency():
    """An existing docs/bugs/_archive/<slug>/ dir is resolved as the item dir
    (type: bug) — the archive walk the backfill relies on."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        begin = _prov_git_fixture_repo(repo_root)
        arch_dir = repo_root / "docs" / "bugs" / "_archive" / "old-bug"
        arch_dir.mkdir(parents=True)
        (arch_dir / "SPEC.md").write_text(
            "# Bug\n\n> Old archived bug.\n\n**Status:** Fixed\n", encoding="utf-8")
        end = _prov_git_commit_file(repo_root, "src/ob.py", "fix(old-bug): fix")
        result = lazy_core.link_provenance(
            repo_root, "old-bug", commit_range=f"{begin}..{end}",
            date="2026-07-04",
        )
        assert result["ok"] is True, f"got {result}"
        assert (arch_dir / "IMPLEMENTED.md").exists(), (
            "the archived bug dir must be resolved as the item dir"
        )
        index = json.loads(
            (repo_root / "docs" / "provenance-index.json").read_text(encoding="utf-8"))
        assert index["src/ob.py"][0]["type"] == "bug"




def _run_link_provenance_cli(script_name: str):
    """Shared body: --link-provenance on the named state script (parity)."""
    script = _SCRIPTS_DIR / script_name
    assert script.exists(), f"{script_name} missing"
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        begin = _prov_git_fixture_repo(repo_root)
        end = _prov_git_commit_file(repo_root, "src/cli.py", "cli work")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        env = {k: v for k, v in _os_env.environ.items()
               if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(script)] + args,
                capture_output=True, text=True, env=env,
            )

        # (a) --dry-run: exit 0, derivation surfaced, nothing written.
        r = run(["--repo-root", str(repo_root), "--link-provenance",
                 "--id", "feat-cli-link", "--commits", f"{begin}..{end}",
                 "--dry-run"])
        assert r.returncode == 0, f"{script_name} dry-run failed: {r.stderr[:300]}"
        out = json.loads(r.stdout)
        assert out.get("dry_run") is True and out.get("files") == ["src/cli.py"]
        assert not (repo_root / "docs" / "provenance-index.json").exists()
        # (b) real link: exit 0, distillate + index written.
        r = run(["--repo-root", str(repo_root), "--link-provenance",
                 "--id", "feat-cli-link", "--commits", f"{begin}..{end}"])
        assert r.returncode == 0, f"{script_name} link failed: {r.stderr[:300]}"
        assert (repo_root / "docs" / "features" / "feat-cli-link" /
                "IMPLEMENTED.md").exists()
        assert (repo_root / "docs" / "provenance-index.json").exists()
        # (c) missing --id → argparse-level die (exit 2).
        r = run(["--repo-root", str(repo_root), "--link-provenance",
                 "--commits", f"{begin}..{end}"])
        assert r.returncode == 2, f"missing --id must exit 2, got {r.returncode}"
        # (d) unresolvable range → refusal (exit 1), no half-writes.
        r = run(["--repo-root", str(repo_root), "--link-provenance",
                 "--id", "feat-cli-bad", "--commits", "deadbeef..cafebabe"])
        assert r.returncode == 1, f"bad range must exit 1, got {r.returncode}"
        assert not (repo_root / "docs" / "features" / "feat-cli-bad").exists()




def test_link_provenance_cli_lazy_state():
    """lazy-state.py --link-provenance: dry-run / link / missing-id / bad-range."""
    _guard()
    _run_link_provenance_cli("lazy-state.py")




def test_link_provenance_cli_bug_state_parity():
    """bug-state.py --link-provenance behaves identically (parity)."""
    _guard()
    _run_link_provenance_cli("bug-state.py")




# ---------------------------------------------------------------------------
# code-doc-provenance-linkage — Phase 4: --provenance-lookup (pure read, D6-A)
# ---------------------------------------------------------------------------

def _seed_provenance_fixture(repo_root: "Path") -> "Path":
    """Seed an index + two distillates (one feature, one ARCHIVED bug) so the
    lookup's row resolution + archive residency are both observable."""
    feat_dir = _prov_spec_dir(repo_root, "feat-x")
    assert lazy_core.write_provenance(
        repo_root, feat_dir, "feat-x", "feature", ["abc1234"],
        ["user/scripts/core.py", "src/a.py"], date="2026-07-04")["ok"]
    arch_dir = repo_root / "docs" / "bugs" / "_archive" / "bug-y"
    arch_dir.mkdir(parents=True)
    assert lazy_core.write_provenance(
        repo_root, arch_dir, "bug-y", "bug", ["bbb5678"],
        ["user/scripts/core.py"], provenance="backfilled",
        derivation="message-grep", date="2026-07-04")["ok"]
    return repo_root / "docs" / "provenance-index.json"




def test_provenance_lookup_returns_governing_rows():
    """Lookup returns {path, governed_by:[{id,type,doc,decisions,provenance}]}
    with the doc path resolving ARCHIVE residency and decisions read from the
    distillate frontmatter."""
    _guard()
    assert hasattr(lazy_core, "provenance_lookup"), (
        "lazy_core.provenance_lookup is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _seed_provenance_fixture(repo_root)
        got = lazy_core.provenance_lookup(repo_root, "user/scripts/core.py")
        assert got["path"] == "user/scripts/core.py"
        by_id = {g["id"]: g for g in got["governed_by"]}
        assert set(by_id) == {"feat-x", "bug-y"}, f"got {got}"
        feat = by_id["feat-x"]
        assert feat["type"] == "feature"
        assert feat["doc"] == "docs/features/feat-x/IMPLEMENTED.md"
        assert feat["decisions"] == ["L1", "L2"]
        assert feat["provenance"] == "pipeline-gated"
        bug = by_id["bug-y"]
        assert bug["doc"] == "docs/bugs/_archive/bug-y/IMPLEMENTED.md", (
            f"archive residency must resolve, got {bug['doc']}"
        )
        assert bug["provenance"] == "backfilled"




def test_provenance_lookup_is_pure_read():
    """Lookup mutates NOTHING (index bytes + mtime unchanged) and normalizes
    the query path (backslashes, leading ./, absolute-under-root)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        index_path = _seed_provenance_fixture(repo_root)
        before = index_path.read_bytes()
        mtime_before = index_path.stat().st_mtime_ns
        for query in ("./src/a.py", "src\\a.py", str(repo_root / "src" / "a.py")):
            got = lazy_core.provenance_lookup(repo_root, query)
            assert [g["id"] for g in got["governed_by"]] == ["feat-x"], (
                f"query {query!r} must normalize to src/a.py, got {got}"
            )
        assert index_path.read_bytes() == before
        assert index_path.stat().st_mtime_ns == mtime_before




def test_provenance_lookup_missing_index_degrades_to_empty():
    """No index on disk → empty governed_by (a no-op consumer step), never a
    crash, never a state-dir/docs-dir creation."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        got = lazy_core.provenance_lookup(repo_root, "src/nothing.py")
        assert got == {"path": "src/nothing.py", "governed_by": []}
        assert not (repo_root / "docs").exists(), "lookup must not create dirs"




def _run_provenance_lookup_cli(script_name: str):
    """Shared body: --provenance-lookup on the named state script (parity)."""
    script = _SCRIPTS_DIR / script_name
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        _seed_provenance_fixture(repo_root)
        index_path = repo_root / "docs" / "provenance-index.json"
        before = index_path.read_bytes()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(Path(td) / "state")
        r = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root),
             "--provenance-lookup", "src/a.py"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0, f"{script_name} lookup failed: {r.stderr[:300]}"
        out = json.loads(r.stdout)
        assert out["path"] == "src/a.py"
        assert [g["id"] for g in out["governed_by"]] == ["feat-x"]
        assert index_path.read_bytes() == before, "CLI lookup must be a pure read"
        # Unknown path → empty result, still exit 0 (a no-op consumer step).
        r = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root),
             "--provenance-lookup", "src/unknown.py"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0
        assert json.loads(r.stdout)["governed_by"] == []




def test_provenance_lookup_cli_lazy_state():
    """lazy-state.py --provenance-lookup: rows + purity + unknown-path no-op."""
    _guard()
    _run_provenance_lookup_cli("lazy-state.py")




def test_provenance_lookup_cli_bug_state_parity():
    """bug-state.py --provenance-lookup behaves identically (parity)."""
    _guard()
    _run_provenance_lookup_cli("bug-state.py")




def test_lint_provenance_catches_rot_and_is_pure():
    """The D10 lint flags (a) dead rows, (b) hot un-provenanced files,
    (c) cross-orphans — and mutates NOTHING."""
    _guard()
    assert hasattr(lazy_core, "lint_provenance"), (
        "lazy_core.lint_provenance is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        # (b) churn a non-indexed file past the threshold.
        for i in range(5):
            _prov_git_commit_file(repo_root, "src/hot.py", f"churn {i}")
        # (a) an index row whose path no longer exists + (c) a row citing a
        # missing distillate.
        index_path = repo_root / "docs" / "provenance-index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps({
            "src/gone.py": [
                {"id": "feat-ghost", "type": "feature", "provenance": "manual"}],
        }, indent=2) + "\n", encoding="utf-8")
        # (c) a distillate (non-empty commits) with NO index rows.
        orphan_dir = repo_root / "docs" / "features" / "feat-orphan"
        orphan_dir.mkdir(parents=True)
        (orphan_dir / "IMPLEMENTED.md").write_text(
            "---\nkind: implemented\nfeature_id: feat-orphan\ndate: 2026-07-04\n"
            "provenance: manual\nderivation: commit-range\ncommits: [abc1234]\n"
            "decisions: []\n---\n\n# Implementation Ledger\n", encoding="utf-8")
        before = index_path.read_bytes()
        mtime_before = index_path.stat().st_mtime_ns
        report = lazy_core.lint_provenance(repo_root, churn_days=90, churn_threshold=5)
        assert report["ok"] is True, f"got {report}"
        assert [d["path"] for d in report["dead_rows"]] == ["src/gone.py"], f"got {report}"
        assert any(h["path"] == "src/hot.py" and h["commits"] >= 5
                   for h in report["churn_hotspots"]), f"got {report}"
        orphans = report["cross_orphans"]
        assert "docs/features/feat-orphan/IMPLEMENTED.md" in orphans[
            "distillates_without_rows"], f"got {report}"
        assert any(r["id"] == "feat-ghost"
                   for r in orphans["rows_without_distillate"]), f"got {report}"
        # Report only — nothing mutated.
        assert index_path.read_bytes() == before
        assert index_path.stat().st_mtime_ns == mtime_before
        assert (orphan_dir / "IMPLEMENTED.md").exists()




def _run_lint_backfill_cli(script_name: str):
    """Shared body: --lint-provenance / --backfill-provenance CLI (parity)."""
    script = _SCRIPTS_DIR / script_name
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        feat_dir = _prov_spec_dir(repo_root, "feat-cli-bf")
        lazy_core.write_completed_receipt(
            feat_dir / "COMPLETED.md", "feat-cli-bf", "2026-06-01",
            provenance="gated")
        _prov_git_fixture_repo(repo_root)
        _prov_git_commit_file(repo_root, "src/bf.py", "feat(feat-cli-bf): impl")
        env = {k: v for k, v in _os_env.environ.items()
               if k not in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT")}
        env["LAZY_STATE_DIR"] = str(Path(td) / "state")

        def run(args):
            return subprocess.run(
                [sys.executable, str(script)] + args,
                capture_output=True, text=True, env=env,
            )

        r = run(["--repo-root", str(repo_root), "--backfill-provenance"])
        assert r.returncode == 0, f"{script_name} backfill failed: {r.stderr[:300]}"
        out = json.loads(r.stdout)
        assert out["backfilled"] == ["feat-cli-bf"], f"got {out}"
        assert (feat_dir / "IMPLEMENTED.md").exists()
        index_path = repo_root / "docs" / "provenance-index.json"
        before = index_path.read_bytes()
        r = run(["--repo-root", str(repo_root), "--lint-provenance"])
        assert r.returncode == 0, f"{script_name} lint failed: {r.stderr[:300]}"
        report = json.loads(r.stdout)
        assert report["ok"] is True and "dead_rows" in report
        assert index_path.read_bytes() == before, "lint must be a pure read"




def test_lint_backfill_cli_lazy_state():
    """lazy-state.py --backfill-provenance / --lint-provenance round-trip."""
    _guard()
    _run_lint_backfill_cli("lazy-state.py")




def test_lint_backfill_cli_bug_state_parity():
    """bug-state.py --backfill-provenance / --lint-provenance parity."""
    _guard()
    _run_lint_backfill_cli("bug-state.py")




def test_intervention_symbols_present():
    """All intervention-efficacy-tracking Phase 1 symbols exist on lazy_core,
    with the D5-A default constants (20 / 20 / 5 / 20%)."""
    _guard()
    expected = [
        "INTERVENTION_BASELINE_RUNS",
        "INTERVENTION_REVIEW_AFTER_RUNS",
        "INTERVENTION_MIN_SAMPLE",
        "INTERVENTION_BAND_PCT",
        "_INTERVENTIONS_DIRNAME",
        "parse_intervention_hypothesis",
        "read_intervention_telemetry",
        "record_intervention",
    ]
    missing = [s for s in expected if not hasattr(lazy_core, s)]
    assert not missing, f"missing intervention symbols: {missing}"
    assert lazy_core.ledgers.INTERVENTION_BASELINE_RUNS == 20
    assert lazy_core.ledgers.INTERVENTION_REVIEW_AFTER_RUNS == 20
    assert lazy_core.ledgers.INTERVENTION_MIN_SAMPLE == 5
    assert lazy_core.ledgers.INTERVENTION_BAND_PCT == 20
    assert lazy_core.ledgers._INTERVENTIONS_DIRNAME == "interventions"




def test_parse_intervention_hypothesis_block_and_absent():
    """The `## Intervention Hypothesis` reader: full block (incl. the wrapped
    signal_independence justification from the SPEC's UX example), absent
    heading → None, malformed int degrades (key omitted, never raises),
    optional D5 overrides parsed."""
    _guard()
    text = (
        "# Some Feature\n\n"
        "## Intervention Hypothesis\n\n"
        "- target_signal: event:containment-refusal\n"
        "- expected_direction: decrease\n"
        "- signal_independence: independent — trips are counted by the containment hook's deny\n"
        "  ledger, which this change does not touch\n"
        "- review_after_runs: 10\n\n"
        "## Next Section\n\n- target_signal: event:not-this-one\n"
    )
    hyp = lazy_core.parse_intervention_hypothesis(text)
    assert hyp is not None
    assert hyp["target_signal"] == "event:containment-refusal"
    assert hyp["expected_direction"] == "decrease"
    # Enum head extracted; the wrapped justification is folded into the note.
    assert hyp["signal_independence"] == "independent"
    assert "does not touch" in hyp.get("signal_independence_note", "")
    assert hyp["review_after_runs"] == 10

    # Absent heading → None (the degrade-on-absence discriminator, D2-A).
    assert lazy_core.parse_intervention_hypothesis("# No block here\n") is None

    # Malformed int degrades: the key is omitted, nothing raises.
    bad = (
        "## Intervention Hypothesis\n\n"
        "- target_signal: event:halt\n"
        "- review_after_runs: soonish\n"
    )
    hyp2 = lazy_core.parse_intervention_hypothesis(bad)
    assert hyp2 is not None and hyp2["target_signal"] == "event:halt"
    assert "review_after_runs" not in hyp2

    # Optional D5 overrides (baseline_runs / min_sample / band_pct) parse.
    ov = (
        "## Intervention Hypothesis\n\n"
        "- target_signal: event:halt\n"
        "- baseline_runs: 6\n"
        "- min_sample: 2\n"
        "- band_pct: 30\n"
    )
    hyp3 = lazy_core.parse_intervention_hypothesis(ov)
    assert hyp3["baseline_runs"] == 6
    assert hyp3["min_sample"] == 2
    assert hyp3["band_pct"] == 30




def test_record_intervention_no_ledger_baseline_unavailable_and_idempotent():
    """Missing ledger → baseline recorded `unavailable` honestly (never an
    error); an existing record is NEVER clobbered (noop); an undeclared
    hypothesis records target_signal: undeclared + a not-computable baseline."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            repo = Path(td) / "repo"
            spec_dir = repo / "docs" / "features" / "feat-y"
            spec_dir.mkdir(parents=True)
            (spec_dir / "SPEC.md").write_text(
                "# Feat Y\n\n## Intervention Hypothesis\n\n"
                "- target_signal: event:halt\n"
                "- expected_direction: decrease\n",
                encoding="utf-8",
            )
            res = lazy_core.record_intervention(
                repo, "feat-y", pipeline="feature", spec_path=spec_dir,
            )
            assert res["recorded"] is True
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / "feat-y.md")
            assert meta["baseline"]["status"] == "unavailable"

            # Idempotent: second capture is a noop, file byte-unchanged.
            before = (repo / "docs" / "interventions" / "feat-y.md").read_bytes()
            res2 = lazy_core.record_intervention(
                repo, "feat-y", pipeline="feature", spec_path=spec_dir,
            )
            assert res2["noop"] is True and res2["recorded"] is False
            after = (repo / "docs" / "interventions" / "feat-y.md").read_bytes()
            assert before == after

            # Undeclared: no hypothesis block anywhere → degrade, never block.
            spec2 = repo / "docs" / "features" / "feat-z"
            spec2.mkdir(parents=True)
            (spec2 / "SPEC.md").write_text("# Feat Z\n", encoding="utf-8")
            res3 = lazy_core.record_intervention(
                repo, "feat-z", pipeline="feature", spec_path=spec2,
            )
            assert res3["recorded"] is True
            meta3 = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / "feat-z.md")
            assert meta3["target_signal"] == "undeclared"
            assert meta3["baseline"]["status"] == "not-computable"
        finally:
            _clear_state_dir()




# ===========================================================================
# harness-change-canary-rollback Phase 1 — registration + revertibility metadata
#
# WU-1: control-surface manifest resolution (fallback glob constant vs. present
#       docs/gate/control-surfaces.json), touched-file derivation from the
#       provenance commit-set, and the manifest-intersection arm decision.
# WU-2: coupled-pair scope computation over lazy-parity-manifest.json + the
#       CLAUDE.md pairs-table folded in as data.
# WU-3: the record_intervention canary post-step (arms a canary: sub-map on a
#       control-surface change; non-scoped change registers none).
# ===========================================================================


def test_canary_control_surfaces_fallback_and_manifest():
    """`_canary_control_surfaces` returns the canary-owned fallback glob
    constant when docs/gate/control-surfaces.json is absent, and the parsed
    globs (manifest precedence) when the file is present."""
    _guard()
    assert hasattr(lazy_core, "_canary_control_surfaces")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        # Absent manifest → fallback constant (mirrors the anti-overfit set).
        fallback = lazy_core._canary_control_surfaces(repo)
        assert isinstance(fallback, (list, tuple))
        assert "user/scripts/lazy_core/**" in fallback
        assert "user/hooks/**" in fallback
        assert tuple(fallback) == tuple(lazy_core._CANARY_CONTROL_SURFACES_FALLBACK)
        # Present manifest → its globs take precedence.
        gate_dir = repo / "docs" / "gate"
        gate_dir.mkdir(parents=True)
        (gate_dir / "control-surfaces.json").write_text(
            json.dumps({"globs": ["custom/only/**", "one_file.py"]}) + "\n",
            encoding="utf-8",
        )
        present = lazy_core._canary_control_surfaces(repo)
        assert list(present) == ["custom/only/**", "one_file.py"]
        assert "user/scripts/lazy_core/**" not in present




def test_canary_touched_files_from_commit():
    """`_canary_touched_files` derives repo-relative POSIX paths from a commit
    set by reusing the provenance git helper (never re-shelling ad hoc)."""
    _guard()
    assert hasattr(lazy_core, "_canary_touched_files")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        repo.mkdir()
        _prov_git_fixture_repo(repo)
        sha = _prov_git_commit_file(
            repo, "user/scripts/lazy_core.py", "touch control surface")
        touched = lazy_core._canary_touched_files(repo, [sha])
        assert "user/scripts/lazy_core.py" in touched
        # POSIX, repo-relative, no backslashes / leading ./
        assert all("\\" not in f and not f.startswith("./") for f in touched)
        # A non-git tree / empty commit set → empty, never raises.
        nongit = Path(td) / "nongit"
        nongit.mkdir()
        assert lazy_core._canary_touched_files(nongit, ["deadbeef"]) == []
        assert lazy_core._canary_touched_files(repo, []) == []




def test_canary_intersects_arm_decision():
    """`_canary_intersects` arms (True + matched surfaces) iff a touched file
    matches a control-surface glob; a non-intersecting set does not."""
    _guard()
    assert hasattr(lazy_core, "_canary_intersects")
    surfaces = lazy_core._CANARY_CONTROL_SURFACES_FALLBACK
    # Exact-path match.
    arm, hits = lazy_core._canary_intersects(
        ["user/scripts/lazy_core/markers.py", "docs/foo.md"], surfaces)
    assert arm is True
    assert hits == ["user/scripts/lazy_core/markers.py"]
    # ** glob match (segment-crossing).
    arm2, hits2 = lazy_core._canary_intersects(["user/hooks/x.sh"], surfaces)
    assert arm2 is True and hits2 == ["user/hooks/x.sh"]
    # lazy*/** skill glob.
    arm3, hits3 = lazy_core._canary_intersects(
        ["user/skills/lazy-batch/SKILL.md"], surfaces)
    assert arm3 is True
    # Non-intersecting → no arm.
    arm4, hits4 = lazy_core._canary_intersects(
        ["docs/foo.md", "README.md"], surfaces)
    assert arm4 is False and hits4 == []




def test_compute_pair_scope():
    """`_compute_pair_scope` returns BOTH halves of every coupled pair a
    touched file hits (over lazy-parity-manifest.json), de-duplicated; a touched
    file in no pair yields an empty scope; the CLAUDE.md pairs-table entries are
    folded in as data for any pair absent from the manifest."""
    _guard()
    assert hasattr(lazy_core, "_compute_pair_scope")
    with tempfile.TemporaryDirectory() as td:
        manifest = Path(td) / "parity.json"
        # Synthetic manifest: ONE lazy-batch pair; the lazy-status pair is
        # deliberately ABSENT so the CLAUDE.md fold must supply it.
        manifest.write_text(json.dumps({
            "mechanic_sets": {},
            "pairs": [
                {"canonical": "user/skills/lazy-batch/SKILL.md",
                 "derived": "user/skills/lazy-bug-batch/SKILL.md"},
                {"canonical": "user/skills/lazy-batch/SKILL.md",
                 "derived": "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md"},
            ],
        }) + "\n", encoding="utf-8")

        # Touch the canonical half → both halves of BOTH pairs it belongs to,
        # canonical listed once (de-duplicated).
        scope = lazy_core._compute_pair_scope(
            ["user/skills/lazy-batch/SKILL.md"], manifest)
        assert "user/skills/lazy-batch/SKILL.md" in scope
        assert "user/skills/lazy-bug-batch/SKILL.md" in scope
        assert "repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md" in scope
        assert scope.count("user/skills/lazy-batch/SKILL.md") == 1

        # Touch a DERIVED half → the same pair returns both halves.
        scope2 = lazy_core._compute_pair_scope(
            ["user/skills/lazy-bug-batch/SKILL.md"], manifest)
        assert set(scope2) >= {
            "user/skills/lazy-batch/SKILL.md",
            "user/skills/lazy-bug-batch/SKILL.md",
        }

        # Touch a file in NO pair → empty scope.
        assert lazy_core._compute_pair_scope(["docs/foo.md"], manifest) == []

        # CLAUDE.md-only pair (folded as data, absent from this manifest):
        # touching one half still yields both halves of that pair.
        scope3 = lazy_core._compute_pair_scope(
            ["user/skills/lazy-status/SKILL.md"], manifest)
        assert "user/skills/lazy-status/SKILL.md" in scope3
        assert "user/skills/lazy-bug-status/SKILL.md" in scope3

        # A missing/malformed manifest degrades to the CLAUDE.md fold only,
        # never raises.
        missing = Path(td) / "nope.json"
        scope4 = lazy_core._compute_pair_scope(
            ["user/skills/lazy/SKILL.md"], missing)
        assert "user/skills/lazy/SKILL.md" in scope4
        assert "user/skills/lazy-bug/SKILL.md" in scope4




def test_run_end_efficacy_flush_refusal_emits_gate_refusal_lazy():
    """lazy-state.py --run-end with no interventions-bearing-scope efficacy-flush
    breadcrumb (gate 1 clear: zero pending) refuses AND appends
    gate=efficacy-coverage-missing (interventions-telemetry-split-brain WU-3
    made the gate coverage-aware — a flush that never covered an
    interventions-bearing scope no longer discharges it)."""
    _assert_run_end_refusal_emits(
        "lazy-state.py", "feature", [], seed_deny=False,
        expected_gate="efficacy-coverage-missing",
    )




# ---------------------------------------------------------------------------
# read_intervention_telemetry — merged cross-repo originating-target read.
#
# `read_intervention_telemetry(repo_root)` today reads only (a) the ACTIVE
# repo's state-dir telemetry ledger (`read_telemetry_events()`) and (b)
# committed cloud segments under `<repo_root>/docs/telemetry/cloud/*.jsonl`.
# It does NOT see the telemetry of the run's ORIGINATING TARGET repo, whose
# events append to a DIFFERENT `repo_key`-keyed state dir sibling of the
# current repo's flat ledger (both live under the same `LAZY_STATE_DIR` base
# when the env override is set — see `claude_state_dir`'s override branch).
#
# These tests characterize the fix: after its existing reads,
# `read_intervention_telemetry` ALSO merges the telemetry ledger of the run's
# originating TARGET repo, resolved as the MOST-RECENT live (age <= 24h) run
# marker found in a keyed sibling state dir (an immediate subdirectory of the
# `LAZY_STATE_DIR` base, named `repo_key(<that repo's root>)`) whose
# `repo_root` differs from the repo_root passed in. Merge is deduped on the
# existing `(run_id, ts, event, item_id)` key and sorted by `(run_id, ts)`.
# Fail-open (any resolution/read error contributes nothing, never raises).
# Byte-identical to today when no originating foreign marker exists.
# ---------------------------------------------------------------------------

def _write_telemetry_line(path: "Path", *, run_id: str, ts: float,
                           event: str = "cycle-begin",
                           item_id: str = "x") -> None:
    """Append one well-formed telemetry JSONL line (schema v1) to `path`."""
    line = {
        "v": lazy_core._TELEMETRY_SCHEMA_VERSION,
        "ts": ts,
        "run_id": run_id,
        "event": event,
        "item_id": item_id,
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")




def _stale_started_at(now: float | None = None) -> str:
    """A `started_at` timestamp > 24h old (STALE per _MARKER_STALE_SECONDS)."""
    import time as _time
    import datetime as _datetime
    if now is None:
        now = _time.time()
    return _datetime.datetime.fromtimestamp(
        now - lazy_core._MARKER_STALE_SECONDS - 3600.0, tz=_datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S") + "Z"




def test_read_intervention_telemetry_merges_originating_target_ledger():
    """A LIVE foreign run marker's keyed-sibling telemetry ledger is merged in
    alongside the current repo's flat ledger — RED today: the target repo's
    run_id is entirely absent from the result."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as current_td, \
         tempfile.TemporaryDirectory() as target_td:
        base = Path(base_td)
        current_root = Path(current_td)
        target_root = Path(target_td)
        _set_state_dir(base)
        try:
            # Current repo's flat ledger (today's read path).
            _write_telemetry_line(
                base / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RC", ts=1.0, item_id="cur-item",
            )
            # Target repo's keyed-sibling ledger, behind a LIVE marker.
            keyed_dir = _write_target_marker(
                base, target_root, started_at=_fresh_started_at()
            )
            _write_telemetry_line(
                keyed_dir / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RT", ts=2.0, item_id="target-item",
            )

            events = lazy_core.read_intervention_telemetry(current_root)
            run_ids = {e.get("run_id") for e in events}
            assert "RC" in run_ids, f"current-repo event missing: {run_ids}"
            assert "RT" in run_ids, (
                f"originating-target event NOT merged (RED today): {run_ids}"
            )
        finally:
            _clear_state_dir()




def test_read_intervention_telemetry_dedups_overlapping_target_event():
    """The SAME (run_id, ts, event, item_id) event present in BOTH the
    current flat ledger and the target keyed ledger appears exactly ONCE in
    the merged result. A second, target-UNIQUE event is also asserted present
    so this test genuinely reds today (without the merge, BOTH the dedup
    outcome would be vacuously "1" AND the unique event would be silently
    absent — the unique-event assertion is what pins the merge actually ran)."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as current_td, \
         tempfile.TemporaryDirectory() as target_td:
        base = Path(base_td)
        current_root = Path(current_td)
        target_root = Path(target_td)
        _set_state_dir(base)
        try:
            shared_kwargs = dict(run_id="SHARED", ts=5.0, item_id="dup-item")
            _write_telemetry_line(
                base / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME, **shared_kwargs
            )
            keyed_dir = _write_target_marker(
                base, target_root, started_at=_fresh_started_at()
            )
            _write_telemetry_line(
                keyed_dir / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME, **shared_kwargs
            )
            # Target-unique event: absent today (no merge) -> proves RED.
            _write_telemetry_line(
                keyed_dir / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RT-UNIQUE", ts=6.0, item_id="target-only-item",
            )

            events = lazy_core.read_intervention_telemetry(current_root)
            matches = [e for e in events if e.get("run_id") == "SHARED"]
            assert len(matches) == 1, (
                f"expected exactly one deduped SHARED event, got {len(matches)}: {matches}"
            )
            assert any(e.get("run_id") == "RT-UNIQUE" for e in events), (
                "target-unique event NOT merged (RED today): "
                f"{[e.get('run_id') for e in events]}"
            )
        finally:
            _clear_state_dir()




def test_read_intervention_telemetry_failopen_unreadable_target_ledger():
    """A live target marker whose telemetry ledger path is unreadable (a
    directory sits where the file should be) must never raise — the call
    still returns the current repo's own events."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as current_td, \
         tempfile.TemporaryDirectory() as target_td:
        base = Path(base_td)
        current_root = Path(current_td)
        target_root = Path(target_td)
        _set_state_dir(base)
        try:
            _write_telemetry_line(
                base / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RC", ts=1.0, item_id="cur-item",
            )
            keyed_dir = _write_target_marker(
                base, target_root, started_at=_fresh_started_at()
            )
            # Ledger path is a DIRECTORY, not a file -> unreadable as JSONL.
            (keyed_dir / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME).mkdir()

            events = lazy_core.read_intervention_telemetry(current_root)  # must not raise
            run_ids = {e.get("run_id") for e in events}
            assert "RC" in run_ids, f"current-repo events lost on fail-open: {run_ids}"
        finally:
            _clear_state_dir()




def test_read_intervention_telemetry_noop_when_no_originating_marker():
    """Byte-identical-to-today regression guard: with NO live foreign marker
    (no keyed subdir at all, or only a STALE one), the merged result equals
    exactly the current repo's flat-ledger events (today's behavior)."""
    _guard()
    # Case A: no keyed subdirs at all.
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as current_td:
        base = Path(base_td)
        current_root = Path(current_td)
        _set_state_dir(base)
        try:
            _write_telemetry_line(
                base / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RC", ts=1.0, item_id="cur-item",
            )
            baseline = list(lazy_core.read_telemetry_events())
            events = lazy_core.read_intervention_telemetry(current_root)
            assert events == baseline, (
                f"no-keyed-subdir case must be byte-identical to today: "
                f"{events} != {baseline}"
            )
        finally:
            _clear_state_dir()

    # Case B: a keyed subdir exists, but its marker is STALE (>24h old).
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as current_td, \
         tempfile.TemporaryDirectory() as target_td:
        base = Path(base_td)
        current_root = Path(current_td)
        target_root = Path(target_td)
        _set_state_dir(base)
        try:
            _write_telemetry_line(
                base / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RC2", ts=1.0, item_id="cur-item-2",
            )
            keyed_dir = _write_target_marker(
                base, target_root, started_at=_stale_started_at()
            )
            _write_telemetry_line(
                keyed_dir / lazy_core.ledgers._TELEMETRY_LEDGER_FILENAME,
                run_id="RT-STALE", ts=2.0, item_id="should-not-appear",
            )

            baseline = list(lazy_core.read_telemetry_events())
            events = lazy_core.read_intervention_telemetry(current_root)
            assert events == baseline, (
                f"stale-marker case must be byte-identical to today: "
                f"{events} != {baseline}"
            )
            assert not any(e.get("run_id") == "RT-STALE" for e in events), (
                "stale target's events must NOT be merged in"
            )
        finally:
            _clear_state_dir()




def test_drop_efficacy_breadcrumb_marker_gated_returns_false():
    """With NO live marker anywhere (neither the active flat dir nor any keyed
    sibling subdir), drop_efficacy_breadcrumb(covered_repo_root) returns False
    and writes no breadcrumb file — marker-gated, unchanged from today."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as any_td:
        base = Path(base_td)
        any_root = Path(any_td)
        _set_state_dir(base)
        try:
            assert lazy_core.drop_efficacy_breadcrumb(str(any_root)) is False
            flat_crumb_path = base / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            assert not flat_crumb_path.exists()
            # No keyed subdir should have been created/written either.
            for child in base.iterdir():
                assert not (child / lazy_core._EFFICACY_BREADCRUMB_FILENAME).exists()
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# WU-1 (harden-degrade-test / intervention-target-signal-validation) — RED
# tests for symbols that do not exist yet:
#   - lazy_core._INTERVENTION_EVENT_VOCABULARY (frozenset)
#   - lazy_core.validate_intervention_target_signal(target_signal) -> str|None
#   - a degrade-to-"undeclared" branch inside record_intervention() for an
#     unknown event:<type> target (Verified Symptom (a): currently the
#     literal target_signal is kept and a bogus baseline is frozen/unavailable
#     against a nonexistent event type instead of degrading honestly).
# ---------------------------------------------------------------------------

# The 10 documented KNOWN event types (the live emit set minus
# "containment-refusal"/"gate-refusal" duplication concerns — this list is
# checked for membership only; Group C separately proves this list truly
# matches every append_telemetry_event(...) call site across the three
# source files via AST, so it can never silently drift from the emitters).
_KNOWN_INTERVENTION_EVENTS = [
    "run-start",
    "run-end",
    "cycle-begin",
    "cycle-end",
    "pseudo-applied",
    "dispatch",
    "halt",
    "sentinel-resolved",
    "gate-refusal",
    "containment-refusal",
]




def test_validate_intervention_target_signal_accepts_known_events():
    """Group A: every documented event:<type> target with a KNOWN type
    validates as None (no error)."""
    _guard()
    for ev in _KNOWN_INTERVENTION_EVENTS:
        target = f"event:{ev}"
        result = lazy_core.validate_intervention_target_signal(target)
        assert result is None, (
            f"{target!r} is a known event and should validate as None; "
            f"got {result!r}"
        )




def test_validate_intervention_target_signal_accepts_kpi_and_undeclared():
    """Group A: a kpi:<sys>.<id> target and the literal 'undeclared' both
    validate as None (they are not event: types and are valid regardless)."""
    _guard()
    assert lazy_core.validate_intervention_target_signal("kpi:foo.bar") is None
    assert lazy_core.validate_intervention_target_signal("undeclared") is None




def test_validate_intervention_target_signal_rejects_event_no_route():
    """Group A: 'event:no-route' is NOT in the known vocabulary — must
    return a non-None error string that NAMES the valid set (proven here by
    asserting a real known event name appears as a substring)."""
    _guard()
    result = lazy_core.validate_intervention_target_signal("event:no-route")
    assert result is not None, "event:no-route must be rejected, not accepted"
    assert isinstance(result, str), f"error must be a string; got {result!r}"
    assert any(name in result for name in ("gate-refusal", "containment-refusal")), (
        f"error message must NAME the valid event set; got: {result!r}"
    )




def test_validate_intervention_target_signal_rejects_event_route_loop():
    """Group A: 'event:route-loop' is likewise NOT in the known vocabulary —
    must return a non-None error string naming the valid set."""
    _guard()
    result = lazy_core.validate_intervention_target_signal("event:route-loop")
    assert result is not None, "event:route-loop must be rejected, not accepted"
    assert isinstance(result, str), f"error must be a string; got {result!r}"
    assert any(name in result for name in ("gate-refusal", "containment-refusal")), (
        f"error message must NAME the valid event set; got: {result!r}"
    )




# ---------------------------------------------------------------------------
# efficacy-signal-integrity D1 (STATE-lane capture seam) — sub-signal target
# grammar (event:<type>/<signature>) on the CAPTURE-side validator. The
# feature's evaluator half (efficacy-eval.py's _target_signature /
# _event_matches_target / _GATE_REFUSAL_SIGNATURES) already counts these
# sub-signals correctly at review time; this closes the reported cross-lane
# gap where a sub-signal target degraded to "undeclared" at CAPTURE because
# validate_intervention_target_signal / _intervention_signal_event did not
# parse the '/<signature>' component at all.
# ---------------------------------------------------------------------------

def test_validate_intervention_target_signal_accepts_known_sub_signal():
    """A sub-signal target event:<type>/<signature> validates as None when
    the bare <type> is known AND <signature> is in that type's closed
    sub-signal vocabulary (v1: gate-refusal only, DUPLICATED from
    efficacy-eval.py's _GATE_REFUSAL_SIGNATURES — that module is not
    importable here, capture and evaluation are separate lanes)."""
    _guard()
    for sig in sorted(lazy_core._GATE_REFUSAL_SIGNATURES):
        target = f"event:gate-refusal/{sig}"
        result = lazy_core.validate_intervention_target_signal(target)
        assert result is None, f"{target!r} should validate as None; got {result!r}"




def test_validate_intervention_target_signal_rejects_unknown_sub_signal():
    """An unrecognized <signature> on a KNOWN event type still degrades
    honestly (a named error, never a silent accept)."""
    _guard()
    result = lazy_core.validate_intervention_target_signal(
        "event:gate-refusal/not-a-real-gate")
    assert result is not None, "an unknown gate-refusal sub-signal must be rejected"
    assert "not-a-real-gate" in result or "gate-coverage" in result, (
        f"error message must name the offending/valid sub-signal set; got {result!r}"
    )




def test_validate_intervention_target_signal_rejects_sub_signal_on_unsupported_type():
    """A sub-signal component on an event type with NO declared sub-signal
    vocabulary (e.g. run-start) is rejected — only gate-refusal carries a
    verified sub-signal vocabulary in v1."""
    _guard()
    result = lazy_core.validate_intervention_target_signal("event:run-start/foo")
    assert result is not None, (
        "event:run-start/foo must be rejected — run-start has no sub-signal vocabulary"
    )




def test_validate_intervention_target_signal_still_accepts_bare_event():
    """Bare event:<type> targets (no sub-signal) are byte-unaffected by the
    sub-signal grammar addition."""
    _guard()
    assert lazy_core.validate_intervention_target_signal("event:gate-refusal") is None
    assert lazy_core.validate_intervention_target_signal(
        "event:containment-refusal") is None




def test_intervention_signal_event_resolves_sub_signal_to_bare_type():
    """_intervention_signal_event resolves a sub-signal target to the SAME
    bare <type> a bare event:<type> target resolves to (mirrors
    efficacy-eval.py's _resolve_target_signal contract) — the '/<signature>'
    suffix must never leak into the ledger event-type counting key."""
    _guard()
    assert (lazy_core._intervention_signal_event("event:gate-refusal/gate-coverage")
            == "gate-refusal")
    assert (lazy_core._intervention_signal_event("event:gate-refusal")
            == "gate-refusal")




def test_record_intervention_degrades_unknown_event_target(tmp_path):
    """Group B (pytest-only, tmp_path — NOT in the manual _TESTS runner):
    serving-path regression for the bug's Verified Symptom (a). An unknown
    event:<type> hypothesis target must DEGRADE to target_signal:
    "undeclared" with baseline_status "not-computable" (never a frozen bogus
    zero-count / unavailable baseline against a type that was never a real
    telemetry event), and the degrade must emit a diagnostic naming the
    rejected type.

    RED today: the current record_intervention keeps the literal
    "event:no-route" as target_signal and computes/`unavailable`s a baseline
    against that nonexistent event type instead of degrading — so
    target_signal/baseline_status assertions below fail, and no diagnostic
    naming "no-route" is ever appended (record_intervention has no degrade
    branch at all yet).
    """
    _guard()
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _set_state_dir(state_dir)
    lazy_core._DIAGNOSTICS.clear()
    try:
        res = lazy_core.record_intervention(
            tmp_path,
            "harden-degrade-test",
            pipeline="hardening",
            hypothesis_overrides={"target_signal": "event:no-route"},
        )
        assert res["recorded"] is True, res
        assert res["target_signal"] == "undeclared", (
            f"unknown event type must degrade target_signal to 'undeclared'; "
            f"got {res.get('target_signal')!r}"
        )
        assert res["baseline_status"] == "not-computable", (
            f"a degraded target must record baseline_status 'not-computable', "
            f"never a frozen/unavailable count against a bogus event type; "
            f"got {res.get('baseline_status')!r}"
        )

        record_path = tmp_path / "docs" / "interventions" / "harden-degrade-test.md"
        assert record_path.exists(), f"record file missing at {record_path}"
        text = record_path.read_text(encoding="utf-8")
        assert "target_signal: undeclared" in text, (
            f"on-disk record must carry target_signal: undeclared; got:\n{text}"
        )
        assert "not-computable" in text, (
            f"on-disk record must carry a not-computable baseline status; got:\n{text}"
        )

        assert any("no-route" in entry for entry in lazy_core._DIAGNOSTICS), (
            "the degrade must emit a _diag() entry naming the rejected "
            f"'no-route' type; got _DIAGNOSTICS={lazy_core._DIAGNOSTICS}"
        )
    finally:
        _clear_state_dir()




# ---------------------------------------------------------------------------
# guard-fail-open-leaves-no-trace item 4 (STATE-lane descoped residual) —
# lazy_core.read_hook_events / guard_plane_heartbeat. Report-only advisory;
# never gates or halts anything.
# ---------------------------------------------------------------------------

def test_read_hook_events_empty_missing_and_corrupt_tolerant():
    """read_hook_events: missing file -> []; a torn/corrupt line is skipped,
    not fatal."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            assert lazy_core.read_hook_events() == []
            events_path = state_dir / "hook-events.jsonl"
            events_path.write_text(
                '{"ts": 1000.0, "kind": "error", "hook": "h1", "repo_root": "", '
                '"signature": "", "detail": "boom"}\n'
                "{not valid json\n"
                '{"ts": 1001.0, "kind": "deny", "hook": "h2", "repo_root": "", '
                '"signature": "sig", "detail": "d"}\n',
                encoding="utf-8",
            )
            got = lazy_core.read_hook_events()
            assert len(got) == 2, got
            assert got[0]["hook"] == "h1" and got[1]["hook"] == "h2"
        finally:
            _clear_state_dir()




def test_guard_plane_heartbeat_none_without_marker():
    """No live run marker -> None (nothing to assess)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            assert lazy_core.guard_plane_heartbeat() is None
        finally:
            _clear_state_dir()




def test_intervention_event_vocabulary_matches_live_emit_set():
    """Group C: `lazy_core._INTERVENTION_EVENT_VOCABULARY` must SET-EQUAL the
    live emit set collected via AST from lazy_core.py + lazy-state.py +
    bug-state.py — the constant can never silently drift from the actual
    emitters. RED today: `_INTERVENTION_EVENT_VOCABULARY` does not exist yet.
    """
    _guard()
    scripts_dir = Path(__file__).resolve().parents[2]
    sources = sorted((scripts_dir / "lazy_core").glob("*.py")) + [
        scripts_dir / "lazy-state.py",
        scripts_dir / "bug-state.py",
    ]
    collected: "set[str]" = set()
    for path in sources:
        collected |= _collect_telemetry_event_literals(
            path.read_text(encoding="utf-8")
        )
    assert collected, "collector found zero append_telemetry_event(...) literals"
    vocabulary = lazy_core._INTERVENTION_EVENT_VOCABULARY
    assert collected == vocabulary, (
        f"live emit set {sorted(collected)} != "
        f"_INTERVENTION_EVENT_VOCABULARY {sorted(vocabulary)} "
        f"(missing from constant: {sorted(collected - vocabulary)}; "
        f"extra in constant: {sorted(vocabulary - collected)})"
    )


# ---------------------------------------------------------------------------
# flush_commit_artifacts (end-of-run-flush-commit-absorbs-concurrent-writer-
# staged-files): the end-of-run efficacy flush must stage + commit ONLY its own
# explicit artifacts, never absorb a concurrent writer's staged files.
# ---------------------------------------------------------------------------

def _fca_git_head_files(root: "Path") -> "list[str]":
    r = subprocess.run(
        ["git", "-C", str(root), "show", "--name-only", "--pretty=format:", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def _fca_git_staged(root: "Path") -> "list[str]":
    r = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only"],
        check=True, capture_output=True, text=True,
    )
    return [l.strip() for l in r.stdout.splitlines() if l.strip()]


def test_flush_commit_artifacts_does_not_absorb_foreign_staged_file():
    """The MEASURABLE gap-3 regression: a foreign staged file (a concurrent harden
    agent's spec) is NOT absorbed into the flush commit — the pathspec commit
    captures ONLY the explicit flush artifacts; the foreign file stays staged."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _prov_git_fixture_repo(root)
        # The flush's own artifacts.
        (root / "docs" / "interventions").mkdir(parents=True)
        (root / "docs" / "interventions" / "harden-x.md").write_text(
            "---\nkind: intervention\n---\n", encoding="utf-8")
        (root / "docs" / "kpi").mkdir(parents=True)
        (root / "docs" / "kpi" / "SCORECARD.md").write_text("# scorecard\n", encoding="utf-8")
        # A CONCURRENT writer's file, ALREADY STAGED (a harden agent mid-write).
        (root / "docs" / "bugs" / "some-harden-bug").mkdir(parents=True)
        foreign = root / "docs" / "bugs" / "some-harden-bug" / "SPEC.md"
        foreign.write_text("# concurrent harden spec\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", "docs/bugs/some-harden-bug/SPEC.md"],
            check=True, capture_output=True, text=True,
        )
        assert "docs/bugs/some-harden-bug/SPEC.md" in _fca_git_staged(root)

        result = lazy_core.flush_commit_artifacts(
            root,
            ["docs/interventions/harden-x.md", "docs/kpi/SCORECARD.md"],
            "docs(interventions): efficacy verdicts — test",
        )

        assert result["ok"] is True, result
        committed = _fca_git_head_files(root)
        # The flush artifacts ARE committed …
        assert "docs/interventions/harden-x.md" in committed
        assert "docs/kpi/SCORECARD.md" in committed
        # … and the foreign staged file is NOT absorbed into the flush commit …
        assert "docs/bugs/some-harden-bug/SPEC.md" not in committed
        # … and remains staged for its owner (uncommitted, not lost).
        assert "docs/bugs/some-harden-bug/SPEC.md" in _fca_git_staged(root)


def test_flush_commit_artifacts_skips_missing_and_noops_when_empty():
    """A no-op flush (no artifacts present) commits nothing and reports skips."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        head0 = _prov_git_fixture_repo(root)
        result = lazy_core.flush_commit_artifacts(
            root, ["docs/interventions/absent.md"], "docs(interventions): none",
        )
        assert result["ok"] is True
        assert result["committed"] == []
        assert "docs/interventions/absent.md" in result["skipped_missing"]
        head1 = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        assert head1 == head0, "no-op flush must not create a commit"


# ---------------------------------------------------------------------------
# WU-1 — concurrent-activity commit-sha ledger substrate
# (adhoc-process-friction-detector-counts-concurrent-session-commits Phase 1):
# append_concurrent_commit_sha / read_concurrent_commit_entries mirror the
# deny-ledger fail-open plain-append pattern. Script-owned commit sites (Phase 2)
# record their produced sha here so a concurrent same-identity session's commits
# are subtractable at the friction detector.
# ---------------------------------------------------------------------------

def _cca_raw_lines(state_dir: "Path") -> "list[dict]":
    p = state_dir / "lazy-concurrent-activity.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def test_append_concurrent_commit_sha_writes_entry():
    """A single append writes one compact JSON line {sha, run_started_at, ts} to
    lazy-concurrent-activity.jsonl and returns True."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _set_state_dir(state_dir)
        try:
            ok = lazy_core.append_concurrent_commit_sha(
                "abc123", run_started_at="R1", now=7.0,
            )
            assert ok is True
            lines = _cca_raw_lines(state_dir)
        finally:
            _clear_state_dir()
    assert len(lines) == 1, lines
    entry = lines[0]
    assert entry["sha"] == "abc123"
    assert entry["run_started_at"] == "R1"
    assert entry["ts"] == 7.0


def test_read_concurrent_commit_entries_roundtrip():
    """read_concurrent_commit_entries returns the appended entries as a
    {sha: run_started_at} map."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.append_concurrent_commit_sha("s1", run_started_at="A", now=1.0)
            lazy_core.append_concurrent_commit_sha("s2", run_started_at="B", now=2.0)
            got = lazy_core.read_concurrent_commit_entries()
        finally:
            _clear_state_dir()
    assert got == {"s1": "A", "s2": "B"}, got


def test_read_concurrent_commit_entries_missing_file_empty():
    """A missing ledger file returns an empty map, never raises."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            got = lazy_core.read_concurrent_commit_entries()
        finally:
            _clear_state_dir()
    assert got == {}, got


def test_read_concurrent_commit_entries_tolerates_torn_line():
    """A torn/partial final line is skipped; the valid lines still parse."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        _set_state_dir(state_dir)
        try:
            lazy_core.append_concurrent_commit_sha("good", run_started_at="A", now=1.0)
            # Simulate a torn final append (a crash mid-write).
            with (state_dir / "lazy-concurrent-activity.jsonl").open(
                "a", encoding="utf-8"
            ) as fh:
                fh.write('{"sha": "torn", "run_started')  # no newline, invalid JSON
            got = lazy_core.read_concurrent_commit_entries()
        finally:
            _clear_state_dir()
    assert got == {"good": "A"}, got


def test_append_concurrent_commit_sha_run_started_at_none_roundtrips():
    """run_started_at=None (interactive, no live marker) records null and
    round-trips as None (the conservative, never-subtracted identity)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            ok = lazy_core.append_concurrent_commit_sha(
                "nullid", run_started_at=None, now=3.0,
            )
            assert ok is True
            got = lazy_core.read_concurrent_commit_entries()
        finally:
            _clear_state_dir()
    assert got == {"nullid": None}, got


def test_append_concurrent_commit_sha_fail_open_unwritable():
    """An unwritable state dir makes append return False WITHOUT raising
    (fail-open — identical contract to append_deny_ledger_entry)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Point LAZY_STATE_DIR at a FILE, not a dir — claude_state_dir's mkdir
        # then raises, and the fail-open append swallows it.
        blocker = Path(td) / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        _set_state_dir(blocker)
        try:
            ok = lazy_core.append_concurrent_commit_sha("x", run_started_at="A", now=1.0)
        finally:
            _clear_state_dir()
    assert ok is False


# ---------------------------------------------------------------------------
# WU-4 — flush_commit_artifacts producer instrumentation + the end-to-end seam
# (adhoc-process-friction-detector-counts-concurrent-session-commits Phase 2):
# the shared script-owned flush commit records its sha too, and the motivating
# incident (a concurrent same-identity session's commits) is exercised hermetic
# through the real producer + the WU-2 detector.
# ---------------------------------------------------------------------------

def test_flush_commit_artifacts_appends_commit_sha():
    """A real flush commit appends its resolved commit_sha to the concurrent-
    activity ledger stamped with the live-run identity."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as td_state:
        root = Path(td)
        _prov_git_fixture_repo(root)
        _set_state_dir(Path(td_state))
        try:
            marker = lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(root),
                now=_time.time(),
            )
            (root / "docs" / "kpi").mkdir(parents=True)
            (root / "docs" / "kpi" / "SCORECARD.md").write_text("# s\n", encoding="utf-8")
            result = lazy_core.flush_commit_artifacts(
                root, ["docs/kpi/SCORECARD.md"], "docs(kpi): scorecard — test",
            )
            assert result["ok"] is True and result["commit_sha"], result
            ledger = lazy_core.read_concurrent_commit_entries()
        finally:
            _clear_state_dir()
    assert result["commit_sha"] in ledger, (result["commit_sha"], ledger)
    assert ledger[result["commit_sha"]] == marker["started_at"], ledger


def test_flush_commit_artifacts_noop_appends_nothing():
    """The 'no flush artifacts present' path commits nothing and appends nothing
    to the concurrent-activity ledger."""
    _guard()
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as td_state:
        root = Path(td)
        _prov_git_fixture_repo(root)
        _set_state_dir(Path(td_state))
        try:
            result = lazy_core.flush_commit_artifacts(
                root, ["docs/interventions/absent.md"], "docs: none",
            )
            assert result["ok"] is True and result["commit_sha"] is None
            ledger = lazy_core.read_concurrent_commit_entries()
        finally:
            _clear_state_dir()
    assert ledger == {}, ledger


def test_concurrent_session_commits_seam_no_false_friction():
    """END-TO-END SEAM (the 2026-07-18 motivating incident, hermetic): a
    concurrent session's automated commits — recorded through the REAL producer
    under a DISTINCT run identity — are subtracted at cycle_end_friction_check,
    so no `unexpected-commits` process-friction entry lands when the REMAINDER
    is within budget; a genuine same-run runaway (commits NOT in the ledger)
    still trips."""
    _guard()
    budget = (
        lazy_core.markers._CYCLE_COMMIT_MULTI
        + lazy_core.markers._CYCLE_COMMIT_NOISE_ALLOWANCE
    )  # execute-plan derived budget (no sub_skill_args) == 4
    m = 3  # concurrent-session commits recorded in the ledger
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as td_state:
        root = Path(td)
        _set_state_dir(Path(td_state))
        try:
            begin = _prov_git_fixture_repo(root)
            # run_started_at=None (no live run marker) → bracket-break signal off,
            # isolating the unexpected-commits signal; a ledger identity of "OTHER"
            # (present, != None) is a DISTINCT concurrent identity, so it subtracts.
            lazy_core.write_cycle_marker(
                feature_id="f", nonce="n", run_started_at=None,
                begin_head_sha=begin, sub_skill="execute-plan",
            )
            # budget + m commits in the window; record m of them (the concurrent
            # session's) through the REAL producer under a distinct identity.
            shas = [
                _prov_git_commit_file(root, f"c{i}.txt", f"c{i}")
                for i in range(budget + m)
            ]
            for s in shas[:m]:
                lazy_core.append_concurrent_commit_sha(s, run_started_at="OTHER")

            desc = lazy_core.cycle_end_friction_check(repo_root=root)
            assert desc is None, (
                f"chargeable={budget} must be within budget; got {desc}")
            assert lazy_core.pending_hardening() == 0, "no friction entry expected"

            # Genuine runaway: one MORE own commit (NOT in the ledger) pushes the
            # remainder to budget+1 → still trips.
            _prov_git_commit_file(root, "runaway.txt", "runaway")
            desc2 = lazy_core.cycle_end_friction_check(repo_root=root)
            assert desc2 is not None and desc2["reason"] == "unexpected-commits", desc2
            assert lazy_core.pending_hardening() == 1
        finally:
            _clear_state_dir()


_TESTS = [
    ("test_stale_and_materialized_symbols_present", test_stale_and_materialized_symbols_present),
    ("test_read_stale_upstream_absent", test_read_stale_upstream_absent),
    ("test_write_then_read_stale_upstream", test_write_then_read_stale_upstream),
    ("test_clear_stale_upstream_removes_file", test_clear_stale_upstream_removes_file),
    ("test_clear_stale_upstream_absent_is_noop", test_clear_stale_upstream_absent_is_noop),
    ("test_read_materialized_absent", test_read_materialized_absent),
    ("test_append_materialized_creates_record", test_append_materialized_creates_record),
    ("test_append_materialized_idempotent_on_wi_id", test_append_materialized_idempotent_on_wi_id),
    ("test_append_materialized_multiple_distinct", test_append_materialized_multiple_distinct),
    ("test_update_materialized_changeddate", test_update_materialized_changeddate),
    ("test_update_materialized_changeddate_absent_wi_is_noop", test_update_materialized_changeddate_absent_wi_is_noop),
    ("test_derive_stage_missing_dir", test_derive_stage_missing_dir),
    ("test_derive_stage_spec_only", test_derive_stage_spec_only),
    ("test_derive_stage_research_md", test_derive_stage_research_md),
    ("test_derive_stage_research_summary_md", test_derive_stage_research_summary_md),
    ("test_derive_stage_phases_only", test_derive_stage_phases_only),
    ("test_derive_stage_plan_no_checked_deliverables", test_derive_stage_plan_no_checked_deliverables),
    ("test_derive_stage_implement_checked_deliverable", test_derive_stage_implement_checked_deliverable),
    ("test_derive_stage_review", test_derive_stage_review),
    ("test_derive_stage_reviewed", test_derive_stage_reviewed),
    ("test_derive_stage_stale_upstream_wins_over_ladder", test_derive_stage_stale_upstream_wins_over_ladder),
    ("test_derive_stage_blocked_wins_over_ladder", test_derive_stage_blocked_wins_over_ladder),
    ("test_derive_stage_needs_input_wins_over_ladder", test_derive_stage_needs_input_wins_over_ladder),
    ("test_derive_stage_symbol_present", test_derive_stage_symbol_present),
    ("test_track_open_idempotent_preserves_started_at", test_track_open_idempotent_preserves_started_at),
    ("test_track_open_creates_dir_if_absent", test_track_open_creates_dir_if_absent),
    ("test_track_touch_refreshes_last_touched", test_track_touch_refreshes_last_touched),
    ("test_track_touch_absent_wip_is_noop", test_track_touch_absent_wip_is_noop),
    ("test_track_close_removes_wip_md", test_track_close_removes_wip_md),
    ("test_track_close_absent_is_noop", test_track_close_absent_is_noop),
    ("test_track_symbols_present", test_track_symbols_present),
    ("test_deny_ledger_write_read_pending", test_deny_ledger_write_read_pending),
    ("test_deny_ledger_entries_stamped_with_run_identity", test_deny_ledger_entries_stamped_with_run_identity),
    ("test_pending_hardening_excludes_prior_run_debt", test_pending_hardening_excludes_prior_run_debt),
    ("test_oldest_unacked_deny_scopes_to_current_run", test_oldest_unacked_deny_scopes_to_current_run),
    ("test_pending_hardening_no_marker_fallback_stays_unfiltered", test_pending_hardening_no_marker_fallback_stays_unfiltered),
    ("test_deny_ledger_head_truncation", test_deny_ledger_head_truncation),
    ("test_ack_oldest_deny_fifo", test_ack_oldest_deny_fifo),
    ("test_ack_oldest_deny_empty_is_noop", test_ack_oldest_deny_empty_is_noop),
    ("test_ack_deny_by_selector_oldest_requires_resolution", test_ack_deny_by_selector_oldest_requires_resolution),
    ("test_ack_deny_by_selector_oldest_fifo", test_ack_deny_by_selector_oldest_fifo),
    ("test_ack_deny_by_selector_sha_prefix_match", test_ack_deny_by_selector_sha_prefix_match),
    ("test_ack_deny_by_selector_no_match_refuses", test_ack_deny_by_selector_no_match_refuses),
    ("test_ack_deny_by_selector_dedups_same_sha_cause", test_ack_deny_by_selector_dedups_same_sha_cause),
    ("test_ack_deny_by_selector_dedups_reason_head_fallback_no_sha", test_ack_deny_by_selector_dedups_reason_head_fallback_no_sha),
    ("test_ack_deny_by_selector_refused_for_cycle_subagent", test_ack_deny_by_selector_refused_for_cycle_subagent),
    ("test_deny_ledger_corrupt_line_skipped", test_deny_ledger_corrupt_line_skipped),
    ("test_guard_deny_ledger_failure_is_fail_open", test_guard_deny_ledger_failure_is_fail_open),
    ("test_run_end_refuses_on_unacked_deny", test_run_end_refuses_on_unacked_deny),
    ("test_ack_all_unacked_denies_clears_sessionless_friction", test_ack_all_unacked_denies_clears_sessionless_friction),
    ("test_run_end_ack_unhardened_clears_sessionless_friction", test_run_end_ack_unhardened_clears_sessionless_friction),
    ("test_f2b_find_transcription_slip_entry_no_match_without_marker", test_f2b_find_transcription_slip_entry_no_match_without_marker),
    ("test_probe_withholds_forward_route_on_pending_debt", test_probe_withholds_forward_route_on_pending_debt),
    ("test_probe_withholds_forward_route_on_audit_obligation", test_probe_withholds_forward_route_on_audit_obligation),
    ("test_input_audit_emit_names_pending_audit_item_not_next_queued", test_input_audit_emit_names_pending_audit_item_not_next_queued),
    ("test_audit_obligation_helpers_no_marker_and_non_audited_kind", test_audit_obligation_helpers_no_marker_and_non_audited_kind),
    ("test_build_input_audit_emit_command_binds_supplied_cycle_commit_sha", test_build_input_audit_emit_command_binds_supplied_cycle_commit_sha),
    ("test_build_input_audit_emit_command_falls_back_to_head1_without_sha", test_build_input_audit_emit_command_falls_back_to_head1_without_sha),
    ("test_record_decision_and_read_round_trip", test_record_decision_and_read_round_trip),
    ("test_record_decision_key_reconciles_relative_and_absolute",
     test_record_decision_key_reconciles_relative_and_absolute),
    ("test_bind_decision_record_context_refuses_without_record_and_binds_when_present", test_bind_decision_record_context_refuses_without_record_and_binds_when_present),
    ("test_emit_dispatch_hardening_no_longer_acks", test_emit_dispatch_hardening_no_longer_acks),
    ("test_detect_cycle_bracket_friction_symbols_present", test_detect_cycle_bracket_friction_symbols_present),
    ("test_append_friction_ledger_entry_round_trips", test_append_friction_ledger_entry_round_trips),
    ("test_append_friction_ledger_entry_shares_ledger_with_denies", test_append_friction_ledger_entry_shares_ledger_with_denies),
    ("test_efficacy_breadcrumb_marker_gated_and_moot", test_efficacy_breadcrumb_marker_gated_and_moot),
    ("test_efficacy_breadcrumb_absent_present_false_then_drop_true", test_efficacy_breadcrumb_absent_present_false_then_drop_true),
    ("test_efficacy_breadcrumb_present_requires_interventions_coverage", test_efficacy_breadcrumb_present_requires_interventions_coverage),
    ("test_efficacy_breadcrumb_clear_removes_file", test_efficacy_breadcrumb_clear_removes_file),
    ("test_run_end_efficacy_gate_lazy_state_cli", test_run_end_efficacy_gate_lazy_state_cli),
    ("test_run_end_efficacy_gate_bug_state_cli", test_run_end_efficacy_gate_bug_state_cli),
    ("test_telemetry_symbols_present", test_telemetry_symbols_present),
    ("test_telemetry_append_envelope_shape_and_now_injection", test_telemetry_append_envelope_shape_and_now_injection),
    ("test_telemetry_marker_gated_no_marker_no_emit", test_telemetry_marker_gated_no_marker_no_emit),
    ("test_telemetry_fail_open_unwritable_dir", test_telemetry_fail_open_unwritable_dir),
    ("test_telemetry_reader_tolerates_torn_and_unknown_v", test_telemetry_reader_tolerates_torn_and_unknown_v),
    ("test_telemetry_read_with_provenance", test_telemetry_read_with_provenance),
    ("test_telemetry_rotation_shift_and_reader_order", test_telemetry_rotation_shift_and_reader_order),
    ("test_flush_cloud_telemetry_segment_writes_colon_stripped_segment", test_flush_cloud_telemetry_segment_writes_colon_stripped_segment),
    ("test_flush_cloud_telemetry_segment_noop_cases", test_flush_cloud_telemetry_segment_noop_cases),
    ("test_append_commit_bracket_roundtrip", test_append_commit_bracket_roundtrip),
    ("test_append_commit_bracket_fail_open", test_append_commit_bracket_fail_open),
    ("test_record_cycle_commit_bracket_appends_real_bracket", test_record_cycle_commit_bracket_appends_real_bracket),
    ("test_record_cycle_commit_bracket_skips_empty", test_record_cycle_commit_bracket_skips_empty),
    ("test_write_provenance_distillate_and_index_deterministic", test_write_provenance_distillate_and_index_deterministic),
    ("test_write_provenance_replaces_item_rows_not_duplicates", test_write_provenance_replaces_item_rows_not_duplicates),
    ("test_write_provenance_dry_run_mutates_nothing", test_write_provenance_dry_run_mutates_nothing),
    ("test_item_scope_byte_identical_without_foreign_commits", test_item_scope_byte_identical_without_foreign_commits),
    ("test_link_provenance_manual_entry_shape_matches_pipeline", test_link_provenance_manual_entry_shape_matches_pipeline),
    ("test_link_provenance_dry_run_mutates_nothing", test_link_provenance_dry_run_mutates_nothing),
    ("test_link_provenance_unresolvable_range_refuses_with_no_writes", test_link_provenance_unresolvable_range_refuses_with_no_writes),
    ("test_link_provenance_resolves_bug_and_archive_residency", test_link_provenance_resolves_bug_and_archive_residency),
    ("test_link_provenance_cli_lazy_state", test_link_provenance_cli_lazy_state),
    ("test_link_provenance_cli_bug_state_parity", test_link_provenance_cli_bug_state_parity),
    ("test_provenance_lookup_returns_governing_rows", test_provenance_lookup_returns_governing_rows),
    ("test_provenance_lookup_is_pure_read", test_provenance_lookup_is_pure_read),
    ("test_provenance_lookup_missing_index_degrades_to_empty", test_provenance_lookup_missing_index_degrades_to_empty),
    ("test_provenance_lookup_cli_lazy_state", test_provenance_lookup_cli_lazy_state),
    ("test_provenance_lookup_cli_bug_state_parity", test_provenance_lookup_cli_bug_state_parity),
    ("test_lint_provenance_catches_rot_and_is_pure", test_lint_provenance_catches_rot_and_is_pure),
    ("test_lint_backfill_cli_lazy_state", test_lint_backfill_cli_lazy_state),
    ("test_lint_backfill_cli_bug_state_parity", test_lint_backfill_cli_bug_state_parity),
    ("test_intervention_symbols_present", test_intervention_symbols_present),
    ("test_parse_intervention_hypothesis_block_and_absent", test_parse_intervention_hypothesis_block_and_absent),
    ("test_record_intervention_no_ledger_baseline_unavailable_and_idempotent", test_record_intervention_no_ledger_baseline_unavailable_and_idempotent),
    ("test_canary_control_surfaces_fallback_and_manifest", test_canary_control_surfaces_fallback_and_manifest),
    ("test_canary_touched_files_from_commit", test_canary_touched_files_from_commit),
    ("test_canary_intersects_arm_decision", test_canary_intersects_arm_decision),
    ("test_compute_pair_scope", test_compute_pair_scope),
    ("test_run_end_efficacy_flush_refusal_emits_gate_refusal_lazy", test_run_end_efficacy_flush_refusal_emits_gate_refusal_lazy),
    ("test_read_intervention_telemetry_merges_originating_target_ledger", test_read_intervention_telemetry_merges_originating_target_ledger),
    ("test_read_intervention_telemetry_dedups_overlapping_target_event", test_read_intervention_telemetry_dedups_overlapping_target_event),
    ("test_read_intervention_telemetry_failopen_unreadable_target_ledger", test_read_intervention_telemetry_failopen_unreadable_target_ledger),
    ("test_read_intervention_telemetry_noop_when_no_originating_marker", test_read_intervention_telemetry_noop_when_no_originating_marker),
    ("test_drop_efficacy_breadcrumb_marker_gated_returns_false", test_drop_efficacy_breadcrumb_marker_gated_returns_false),
    ("test_validate_intervention_target_signal_accepts_known_events", test_validate_intervention_target_signal_accepts_known_events),
    ("test_validate_intervention_target_signal_accepts_kpi_and_undeclared", test_validate_intervention_target_signal_accepts_kpi_and_undeclared),
    ("test_validate_intervention_target_signal_rejects_event_no_route", test_validate_intervention_target_signal_rejects_event_no_route),
    ("test_validate_intervention_target_signal_rejects_event_route_loop", test_validate_intervention_target_signal_rejects_event_route_loop),
    ("test_validate_intervention_target_signal_accepts_known_sub_signal", test_validate_intervention_target_signal_accepts_known_sub_signal),
    ("test_validate_intervention_target_signal_rejects_unknown_sub_signal", test_validate_intervention_target_signal_rejects_unknown_sub_signal),
    ("test_validate_intervention_target_signal_rejects_sub_signal_on_unsupported_type", test_validate_intervention_target_signal_rejects_sub_signal_on_unsupported_type),
    ("test_validate_intervention_target_signal_still_accepts_bare_event", test_validate_intervention_target_signal_still_accepts_bare_event),
    ("test_intervention_signal_event_resolves_sub_signal_to_bare_type", test_intervention_signal_event_resolves_sub_signal_to_bare_type),
    ("test_read_hook_events_empty_missing_and_corrupt_tolerant", test_read_hook_events_empty_missing_and_corrupt_tolerant),
    ("test_guard_plane_heartbeat_none_without_marker", test_guard_plane_heartbeat_none_without_marker),
    ("test_intervention_event_vocabulary_matches_live_emit_set", test_intervention_event_vocabulary_matches_live_emit_set),
    ("test_flush_commit_artifacts_does_not_absorb_foreign_staged_file", test_flush_commit_artifacts_does_not_absorb_foreign_staged_file),
    ("test_flush_commit_artifacts_skips_missing_and_noops_when_empty", test_flush_commit_artifacts_skips_missing_and_noops_when_empty),
    ("test_append_concurrent_commit_sha_writes_entry", test_append_concurrent_commit_sha_writes_entry),
    ("test_read_concurrent_commit_entries_roundtrip", test_read_concurrent_commit_entries_roundtrip),
    ("test_read_concurrent_commit_entries_missing_file_empty", test_read_concurrent_commit_entries_missing_file_empty),
    ("test_read_concurrent_commit_entries_tolerates_torn_line", test_read_concurrent_commit_entries_tolerates_torn_line),
    ("test_append_concurrent_commit_sha_run_started_at_none_roundtrips", test_append_concurrent_commit_sha_run_started_at_none_roundtrips),
    ("test_append_concurrent_commit_sha_fail_open_unwritable", test_append_concurrent_commit_sha_fail_open_unwritable),
    ("test_flush_commit_artifacts_appends_commit_sha", test_flush_commit_artifacts_appends_commit_sha),
    ("test_flush_commit_artifacts_noop_appends_nothing", test_flush_commit_artifacts_noop_appends_nothing),
    ("test_concurrent_session_commits_seam_no_false_friction", test_concurrent_session_commits_seam_no_false_friction),
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
