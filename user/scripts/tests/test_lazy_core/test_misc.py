#!/usr/bin/env python3
"""
test_misc.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_misc.py
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



from _util import _ModuleMissing, _CC_E2E_PHASES_VERIF_ONLY, _GUARDED_OPS, _NOW1, _REAL_TEMPLATE_DIR, _STATE_A, _build_blocked_feature_repo, _build_no_plans_verification_only_repo, _build_phase8_fixture_repo, _build_retro_routing_repo, _cc_build_validated_feature, _cc_seed_and_commit, _cc_write_retro_done, _cc_write_validated, _clear_cycle_env, _clear_state_dir, _collect_bare_production_writes, _collect_duplicate_top_level_defs, _collect_orphaned_test_names, _collect_registered_test_names, _commit_dummy, _dispatch_requires, _f1_guard_module, _f1_hook_input, _fresh_started_at, _lint_skills_module, _load_lazy_state_module, _load_state_script, _make_git_repo_with_origin, _make_git_tree, _make_interventions_bearing_repo, _make_laddered_dir, _normalize_smoke_output, _os, _os_env, _phase9_guard_module, _prov_git_commit_file, _prov_git_fixture_repo, _prov_spec_dir, _record_consume, _set_state_dir, _t, _write_marker_in, _write_mcp_test_results, _write_mcp_test_results_with_exemptions, _write_phases_md, _write_skip_mcp_test, _write_spec_md, _write_target_marker, _write_validated_md  # noqa: E402




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
# Tests: _atomic_write
# ---------------------------------------------------------------------------

def test_atomic_write_creates_file():
    """_atomic_write writes the expected content to the target path."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "output.txt"
        lazy_core._monolith._atomic_write(target, "hello world\n")
        content = target.read_text(encoding="utf-8")
    assert content == "hello world\n", f"unexpected content: {content!r}"




def test_atomic_write_creates_parent_dirs():
    """_atomic_write creates missing parent directories."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "nested" / "deep" / "file.txt"
        lazy_core._monolith._atomic_write(target, "nested content\n")
        content = target.read_text(encoding="utf-8")
    assert content == "nested content\n", f"unexpected content: {content!r}"




def test_atomic_write_no_tmp_residue():
    """No .tmp files left after a successful _atomic_write."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "file.txt"
        lazy_core._monolith._atomic_write(target, "data")
        tmp_files = list(Path(td).glob("*.tmp"))
    assert tmp_files == [], f"temp file(s) not cleaned up: {tmp_files}"




def test_derive_stage_done_completed_md():
    """COMPLETED.md present → 'done' (terminal, wins over everything)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "PR.md").write_text("# Pull Request\n", encoding="utf-8")
        (d / "REVIEWED.md").write_text("# Reviewed\n", encoding="utf-8")
        # A valid receipt requires kind + provenance frontmatter (bare-title files no longer count).
        lazy_core.write_completed_receipt(
            d / "COMPLETED.md",
            feature_id="x",
            date="2026-06-01",
            provenance="gated",
        )
        result = lazy_core.derive_stage(d)
    assert result == "done", f"expected 'done', got {result!r}"




def test_derive_stage_done_fixed_md():
    """FIXED.md present (no COMPLETED.md) → 'done'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        # A valid FIXED.md receipt requires kind: fixed + provenance frontmatter.
        lazy_core.write_completed_receipt(
            d / "FIXED.md",
            feature_id="x",
            date="2026-06-01",
            provenance="gated",
            kind="fixed",
        )
        result = lazy_core.derive_stage(d)
    assert result == "done", f"expected 'done' for FIXED.md receipt, got {result!r}"




def test_derive_stage_done_wins_over_blocked():
    """COMPLETED.md + BLOCKED.md coexist → 'done' (receipt is terminal, beats halt sentinels)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = _make_laddered_dir(td)
        (d / "BLOCKED.md").write_text("# Blocked\n", encoding="utf-8")
        # A valid receipt requires kind + provenance frontmatter (bare-title files no longer count).
        lazy_core.write_completed_receipt(
            d / "COMPLETED.md",
            feature_id="x",
            date="2026-06-01",
            provenance="gated",
        )
        result = lazy_core.derive_stage(d)
    assert result == "done", f"expected 'done' (receipt beats BLOCKED.md), got {result!r}"




def test_track_open_creates_wip_md():
    """track_open creates WIP.md; parse_sentinel returns all expected fields with correct values."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.track_open(
            item_dir,
            wi_id=42,
            slug="my-feature",
            branch="p/my-feature",
            host="DEVBOX",
            now=_NOW1,
        )
        wip = item_dir / "WIP.md"
        assert wip.exists(), "WIP.md was not created"
        data = lazy_core.parse_sentinel(wip)
    assert isinstance(data, dict), f"parse_sentinel should return dict, got {type(data)}"
    assert data.get("kind") == "wip", f"kind mismatch: {data}"
    assert data.get("wi_id") == 42, f"wi_id mismatch: {data}"
    assert data.get("slug") == "my-feature", f"slug mismatch: {data}"
    assert data.get("branch") == "p/my-feature", f"branch mismatch: {data}"
    assert data.get("host") == "DEVBOX", f"host mismatch: {data}"
    assert data.get("started_at") == _NOW1, f"started_at mismatch: {data}"
    assert data.get("last_touched") == _NOW1, f"last_touched mismatch: {data}"




def test_track_open_frontmatter_roundtrip():
    """After track_open, file content starts with '---' and parse_sentinel returns all 7 WIP keys."""
    _guard()
    _EXPECTED_KEYS = {"kind", "wi_id", "slug", "branch", "host", "started_at", "last_touched"}
    with tempfile.TemporaryDirectory() as td:
        item_dir = Path(td)
        lazy_core.track_open(
            item_dir, wi_id=3, slug="roundtrip", branch="p/roundtrip", host="HOST", now=_NOW1,
        )
        wip = item_dir / "WIP.md"
        content = wip.read_text(encoding="utf-8")
        data = lazy_core.parse_sentinel(wip)
    assert content.startswith("---"), f"WIP.md must start with '---' fence, got: {content[:30]!r}"
    missing = _EXPECTED_KEYS - set(data.keys())
    assert not missing, f"parse_sentinel missing keys: {missing} in {data}"




# ---------------------------------------------------------------------------
# Tests: clear_diagnostics
# ---------------------------------------------------------------------------

def test_clear_diagnostics_callable():
    """clear_diagnostics() is callable and does not raise."""
    _guard()
    # We can only observe side effects indirectly since _DIAGNOSTICS is module-
    # private. At minimum the function must be callable without error.
    try:
        lazy_core.clear_diagnostics()
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"clear_diagnostics() raised: {exc}") from exc




def test_normalize_smoke_output_is_platform_neutral():
    """_normalize_smoke_output produces identical output for Windows and POSIX
    path forms — making cross-platform correctness a tested contract.

    A Windows-style path and a POSIX-style path that refer to the same logical
    temp location must normalize to the same canonical string.
    """
    # Single backslashes (as in a real Windows path printed to stdout/stderr).
    # Python source uses \\ for each literal backslash character.
    windows_line = (
        '  "path": "C:\\Users\\bob\\AppData\\Local\\Temp\\'
        'lazy-state-fixtures-ab12cd\\enqueue-test\\docs\\features\\queue.json"'
    )
    posix_line = (
        '  "path": "/tmp/claude-1000/'
        'lazy-state-fixtures-zz99/enqueue-test/docs/features/queue.json"'
    )

    normalized_windows = _normalize_smoke_output(windows_line)
    normalized_posix = _normalize_smoke_output(posix_line)

    assert normalized_windows == normalized_posix, (
        f"Windows and POSIX forms did not normalize to the same string:\n"
        f"  Windows normalized: {normalized_windows!r}\n"
        f"  POSIX normalized:   {normalized_posix!r}"
    )

    # Both should land on the canonical form: <TMP>/…-fixtures-XXXXXXXX/…
    expected_canonical = (
        '  "path": "<TMP>/lazy-state-fixtures-XXXXXXXX/'
        'enqueue-test/docs/features/queue.json"'
    )
    assert normalized_windows == expected_canonical, (
        f"Canonical form mismatch:\n"
        f"  expected:  {expected_canonical!r}\n"
        f"  got:       {normalized_windows!r}"
    )




# ---- Test 1 ----

def test_apply_pseudo_validated_from_skip_writes():
    """SKIP_MCP_TEST.md present, no VALIDATED.md yet → VALIDATED.md written with
    kind=validated, ok=True, noop=False; parse_sentinel returns kind=='validated'.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_skip_mcp_test(spec_dir)
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec_dir, date="2026-06-10"
        )
        validated_path = spec_dir / "VALIDATED.md"
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["noop"] is False, f"expected noop=False, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        assert validated_path.exists(), "VALIDATED.md was not created"
        # The written file must be parseable and yield kind == "validated".
        parsed = lazy_core.parse_sentinel(validated_path)
        assert parsed is not None, "parse_sentinel returned None for the written VALIDATED.md"
        assert parsed.get("kind") == "validated", (
            f"expected kind='validated', got {parsed.get('kind')!r} in {parsed}"
        )
        # wrote should contain the VALIDATED.md filename or path
        assert any("VALIDATED.md" in str(w) for w in result["wrote"]), (
            f"'VALIDATED.md' not in wrote: {result['wrote']}"
        )




def test_apply_pseudo_validated_from_skip_operator_granted_writes():
    """SKIP_MCP_TEST.md carrying granted_by: operator is a legitimate
    human-authored waiver → apply_pseudo writes VALIDATED.md (non-regression
    guard for the positive path; absent granted_by = legacy = operator is
    already covered by test_apply_pseudo_validated_from_skip_writes).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "SKIP_MCP_TEST.md").write_text(
            "---\n"
            "kind: skip-mcp-test\n"
            "feature_id: test-feature\n"
            "reason: docs-only change, no runtime surface\n"
            "date: 2026-06-10\n"
            "granted_by: operator\n"
            "---\n\n"
            "# Skip MCP Test\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, (
            f"expected ok=True for granted_by: operator, got {result}"
        )
        assert (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was NOT written for an operator-granted skip"
        )
        parsed = lazy_core.parse_sentinel(spec_dir / "VALIDATED.md")
        assert parsed is not None and parsed.get("kind") == "validated", (
            f"expected kind='validated' in written VALIDATED.md, got {parsed!r}"
        )




# ---- Test 4 ----

def test_apply_pseudo_validated_from_results_copies_scenarios():
    """MCP_TEST_RESULTS.md with scenarios: [a, b] → VALIDATED.md written whose
    mcp_scenarios equals [a, b] (copied from the results file).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(spec_dir, ["scenario-a", "scenario-b"])
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["noop"] is False, f"expected noop=False, got {result}"
        validated_path = spec_dir / "VALIDATED.md"
        assert validated_path.exists(), "VALIDATED.md was not created"
        parsed = lazy_core.parse_sentinel(validated_path)
        assert parsed is not None, "parse_sentinel returned None for VALIDATED.md"
        assert parsed.get("kind") == "validated", (
            f"expected kind='validated', got {parsed.get('kind')!r}"
        )
        # The critical assertion: mcp_scenarios must equal the scenarios from the results file.
        mcp_scenarios = parsed.get("mcp_scenarios")
        assert mcp_scenarios == ["scenario-a", "scenario-b"], (
            f"mcp_scenarios not copied from MCP_TEST_RESULTS.md; got {mcp_scenarios!r}"
        )




def test_apply_pseudo_validated_from_results_promotes_documented_observation_gap():
    """A `result: partial` results file whose MCP-driveable scope is fully passing
    (pass_count == total_count) AND whose remainder is fully covered by documented
    `observation_gap_exemptions` (each with a `spec_class` provenance) PROMOTES to
    VALIDATED.md. The minted receipt carries the exemptions forward so the scoped
    nature of the validation is auditable (it must NOT masquerade as a clean
    all-passing receipt that hides the scope). RED before WU-3: the current gate
    refuses any `result != "all-passing"`.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results_with_exemptions(
            spec_dir,
            ["scenario-a", "scenario-b"],
            exemptions=[
                {
                    "surface": "armStore drive-through (Ctrl+Shift+Enter handler)",
                    "spec_class": "observation-gap — no MCP tool; unit/WDIO tier "
                    "per docs/features/mcp-testing/SPEC.md",
                },
            ],
            result="partial",
            pass_count=2,
            total_count=2,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-30"
        )
        assert result["ok"] is True, (
            f"expected ok=True (observation-gap promotion), got {result}"
        )
        validated_path = spec_dir / "VALIDATED.md"
        assert validated_path.exists(), (
            "VALIDATED.md was not minted for a documented-observation-gap partial"
        )
        parsed = lazy_core.parse_sentinel(validated_path)
        assert parsed is not None and parsed.get("kind") == "validated", (
            f"expected kind='validated', got {parsed!r}"
        )
        # The scope must be carried forward — the receipt is auditable, NOT a
        # silent clean-all-passing impersonation.
        exemptions = parsed.get("observation_gap_exemptions")
        assert isinstance(exemptions, list) and len(exemptions) == 1, (
            f"VALIDATED.md must carry the observation_gap_exemptions block "
            f"forward; got {exemptions!r}"
        )
        assert "spec_class" in exemptions[0], (
            f"each carried exemption must keep its spec_class provenance; "
            f"got {exemptions[0]!r}"
        )




def test_apply_pseudo_validated_from_results_happy_writes_canonical_frontmatter():
    """Happy path: canonical passing results → VALIDATED.md carries the full
    sentinel-frontmatter.md schema (kind/feature_id/date/mcp_scenarios/result)
    and a body noting it was derived from MCP_TEST_RESULTS.md by the gate.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(spec_dir, ["scenario-a", "scenario-b"])
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir,
            date="2026-06-10", feature_id="my-feature",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["wrote"] == ["VALIDATED.md"], (
            f"expected wrote=['VALIDATED.md'], got {result['wrote']}"
        )
        validated_path = spec_dir / "VALIDATED.md"
        parsed = lazy_core.parse_sentinel(validated_path)
        assert parsed is not None, "parse_sentinel returned None for VALIDATED.md"
        assert parsed.get("kind") == "validated", f"kind: {parsed.get('kind')!r}"
        assert parsed.get("feature_id") == "my-feature", (
            f"feature_id: {parsed.get('feature_id')!r}"
        )
        assert str(parsed.get("date")) == "2026-06-10", f"date: {parsed.get('date')!r}"
        assert parsed.get("mcp_scenarios") == ["scenario-a", "scenario-b"], (
            f"mcp_scenarios: {parsed.get('mcp_scenarios')!r}"
        )
        assert parsed.get("result") == "all-passing", (
            f"result: {parsed.get('result')!r}"
        )
        body = validated_path.read_text(encoding="utf-8")
        assert "MCP_TEST_RESULTS.md" in body, (
            "body must note derivation from MCP_TEST_RESULTS.md"
        )
        assert "__write_validated_from_results__" in body, (
            "body must name the deriving gate (__write_validated_from_results__)"
        )




# ---- Test 10 ----

def test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans():
    """VALIDATED.md + RETRO_DONE.md + SPEC.md(In-progress) present, no COMPLETED.md →
    COMPLETED.md written (kind=completed, provenance=gated), SPEC.md Status flipped
    to Complete, VALIDATED.md + RETRO_DONE.md deleted; ok=True, noop=False.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Set up the fixture.
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # Write RETRO_DONE.md (sentinel to be cleaned up).
        retro_path = spec_dir / "RETRO_DONE.md"
        retro_path.write_text(
            "---\nkind: retro-done\nfeature_id: test-feature\ndate: 2026-06-10\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["noop"] is False, f"expected noop=False, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        # COMPLETED.md must exist and parse correctly.
        completed_path = spec_dir / "COMPLETED.md"
        assert completed_path.exists(), "COMPLETED.md was not written"
        parsed = lazy_core.parse_sentinel(completed_path)
        assert parsed is not None, "parse_sentinel returned None for COMPLETED.md"
        assert parsed.get("kind") == "completed", (
            f"expected kind='completed', got {parsed.get('kind')!r}"
        )
        assert parsed.get("provenance") == "gated", (
            f"expected provenance='gated', got {parsed.get('provenance')!r}"
        )
        # SPEC.md Status must now be Complete.
        spec_text = (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert "**Status:** Complete" in spec_text, (
            f"expected SPEC.md Status to be flipped to Complete:\n{spec_text}"
        )
        # VALIDATED.md must be deleted.
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was NOT deleted during __mark_complete__"
        )
        # RETRO_DONE.md must be deleted.
        assert not retro_path.exists(), (
            "RETRO_DONE.md was NOT deleted during __mark_complete__"
        )
        # wrote must include COMPLETED.md.
        assert any("COMPLETED.md" in str(w) for w in result["wrote"]), (
            f"'COMPLETED.md' not in wrote: {result['wrote']}"
        )




# ---- Test 13 ----

def test_apply_pseudo_mark_fixed_writes_fixed_receipt():
    """VALIDATED.md present, no FIXED.md → FIXED.md written (kind=fixed),
    SPEC.md **Status:** flipped to Fixed, ok=True.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_fixed__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["noop"] is False, f"expected noop=False, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        # FIXED.md must exist and parse with kind=fixed.
        fixed_path = spec_dir / "FIXED.md"
        assert fixed_path.exists(), "FIXED.md was not written"
        parsed = lazy_core.parse_sentinel(fixed_path)
        assert parsed is not None, "parse_sentinel returned None for FIXED.md"
        assert parsed.get("kind") == "fixed", (
            f"expected kind='fixed', got {parsed.get('kind')!r}"
        )
        # SPEC.md Status must now read Fixed.
        spec_text = (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert "**Status:** Fixed" in spec_text, (
            f"expected SPEC.md Status to be 'Fixed':\n{spec_text}"
        )
        # wrote must include FIXED.md.
        assert any("FIXED.md" in str(w) for w in result["wrote"]), (
            f"'FIXED.md' not in wrote: {result['wrote']}"
        )


_STATE_B_DIFF_SKILL = {
    "feature_id": "feat-a",
    "sub_skill": "/implement-phase",       # differs from _STATE_A
    "sub_skill_args": "plan-part-1.md",
    "current_step": "Step 7a: execute plan",
}


_STATE_A_PART2 = {
    "feature_id": "feat-a",
    "sub_skill": "/execute-plan",
    "sub_skill_args": "plan-part-2.md",   # differs from _STATE_A (args variant)
    "current_step": "Step 7a: execute plan",
}


# Same feature_id as _STATE_A but a DIFFERENT current_step → a DIFFERENT step
# signature (must reset step_count to 1).
_STATE_A_DIFF_STEP = {
    "feature_id": "feat-a",
    "sub_skill": "/execute-plan",
    "sub_skill_args": "plan-part-1.md",
    "current_step": "Step 8: retro",       # differs from _STATE_A
}




def test_update_repeat_count_first_call_is_one():
    """Fresh signature_path (file does not exist) → returns 1 AND the file is created.

    RED: update_repeat_count missing on lazy_core → AttributeError caught by _run_test.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        assert not sig_path.exists(), "pre-condition: sig.json must not exist before first call"
        result = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        file_created = sig_path.exists()
    assert result == 1, f"expected 1 on first call, got {result!r}"
    assert file_created, "signature file was not created on first call"




def test_update_repeat_count_increments_on_identical():
    """Same state passed 3 times → returns 1, then 2, then 3 in order.

    RED: update_repeat_count missing → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        r2 = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        r3 = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
    assert r1 == 1, f"expected 1 on first call, got {r1!r}"
    assert r2 == 2, f"expected 2 on second (identical) call, got {r2!r}"
    assert r3 == 3, f"expected 3 on third (identical) call, got {r3!r}"




def test_update_repeat_count_resets_on_signature_change():
    """State A → 1; State A → 2; State B (different sub_skill) → 1; State B → 2.

    Proves that changing any signature field resets the counter to 1.
    RED: update_repeat_count missing → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        r2 = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        # Switch to a state with a different sub_skill — must reset.
        r3 = lazy_core.update_repeat_count(Path(td), _STATE_B_DIFF_SKILL, signature_path=sig_path)
        r4 = lazy_core.update_repeat_count(Path(td), _STATE_B_DIFF_SKILL, signature_path=sig_path)
    assert r1 == 1, f"expected 1 (state A first), got {r1!r}"
    assert r2 == 2, f"expected 2 (state A second), got {r2!r}"
    assert r3 == 1, f"expected 1 (reset on state B), got {r3!r} — signature change must reset count"
    assert r4 == 2, f"expected 2 (state B second), got {r4!r}"




def test_update_repeat_count_args_distinguish_signature():
    """sub_skill_args is part of the signature: part-1 vs part-2 are DIFFERENT signatures.

    Sequence: stateA(part-1)→1; stateA_part2(part-2)→1 (NOT 2 — the critical assertion);
    stateA_part2 again→2.

    This test is the load-bearing non-tautological core: it proves that args is
    included in the signature.  A naïve impl that ignores args would return 2
    for the second call, not 1.

    RED: update_repeat_count missing → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        # First call with plan-part-1.md args.
        r1 = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        # Second call with plan-part-2.md args — different signature, must reset to 1.
        r2 = lazy_core.update_repeat_count(Path(td), _STATE_A_PART2, signature_path=sig_path)
        # Third call with plan-part-2.md args again — now increments to 2.
        r3 = lazy_core.update_repeat_count(Path(td), _STATE_A_PART2, signature_path=sig_path)
    assert r1 == 1, f"expected 1 for plan-part-1.md (first call), got {r1!r}"
    assert r2 == 1, (
        f"expected 1 for plan-part-2.md (args changed → reset), got {r2!r}. "
        "sub_skill_args must be part of the signature — a different args value is a NEW signature."
    )
    assert r3 == 2, f"expected 2 for plan-part-2.md (second call), got {r3!r}"




def test_update_repeat_count_corrupt_file_resets():
    """A pre-existing corrupt (invalid JSON) signature file → treated as no prior → returns 1.

    No exception should be raised; the corrupt file is silently replaced.
    RED: update_repeat_count missing → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        # Write invalid JSON to simulate a corrupt signature file.
        sig_path.write_text("{ this is not json", encoding="utf-8")
        assert sig_path.exists(), "pre-condition: corrupt sig.json must exist"
        # Must not raise; must return 1 (treat corrupt as absent/reset).
        try:
            result = lazy_core.update_repeat_count(Path(td), _STATE_A, signature_path=sig_path)
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"update_repeat_count raised on corrupt signature file: {type(exc).__name__}: {exc}"
            ) from exc
    assert result == 1, (
        f"expected 1 when prior signature file is corrupt (reset), got {result!r}"
    )




def test_update_repeat_count_pipelines_are_isolated():
    """Interleaved feature/bug probes against the SAME repo_root must not reset
    each other's repeat streaks (the operator runs /lazy-batch and
    /lazy-bug-batch in parallel sessions against one repo).

    Exercises the DEFAULT signature_path derivation (pipeline-namespaced
    filenames in the OS tempdir) rather than an explicit path — that is where
    the isolation lives. The state files are cleaned up afterward.
    RED: shared default path → the bug probe resets the feature streak to 1.
    """
    _guard()
    import hashlib as _hashlib

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        repo_hash = _hashlib.sha1(str(repo.resolve()).encode("utf-8")).hexdigest()[:16]
        feature_file = Path(tempfile.gettempdir()) / f"lazy-state-last-{repo_hash}.json"
        bug_file = Path(tempfile.gettempdir()) / f"bug-state-last-{repo_hash}.json"
        try:
            f1 = lazy_core.update_repeat_count(repo, _STATE_A)  # feature default
            b1 = lazy_core.update_repeat_count(repo, _STATE_A, pipeline="bug")
            f2 = lazy_core.update_repeat_count(repo, _STATE_A)
            b2 = lazy_core.update_repeat_count(repo, _STATE_A, pipeline="bug")
            f3 = lazy_core.update_repeat_count(repo, _STATE_A)
            files_distinct = feature_file.exists() and bug_file.exists()
        finally:
            for leftover in (feature_file, bug_file):
                try:
                    leftover.unlink()
                except OSError:
                    pass
    assert files_distinct, "feature and bug pipelines must persist to DISTINCT default files"
    assert (f1, f2, f3) == (1, 2, 3), (
        f"feature streak must survive interleaved bug probes: expected (1, 2, 3), "
        f"got {(f1, f2, f3)!r}"
    )
    assert (b1, b2) == (1, 2), (
        f"bug streak must survive interleaved feature probes: expected (1, 2), got {(b1, b2)!r}"
    )




def test_update_repeat_count_head_advance_resets():
    """Identical signature probed twice with a REAL commit in between → second
    call returns 1, NOT 2.

    Commits landing between identical probes are mechanical proof of forward
    progress (a re-validation after work landed), so the streak must RESET even
    though the (feature_id, sub_skill, args, step) tuple is unchanged.

    Uses a real git repo_root so HEAD resolves; signature_path is injected into
    the tempdir (not the repo) so the state file does not dirty the tree.
    RED: pre-WU-2 update_repeat_count ignores HEAD → returns 2.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
        # A real commit lands between the two identical probes.
        _commit_dummy(repo_root, "progress.txt")
        r2 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
    assert r1 == 1, f"expected 1 on first call, got {r1!r}"
    assert r2 == 1, (
        f"expected 1 after a commit landed between identical probes (HEAD advanced "
        f"= forward progress, reset the streak), got {r2!r}"
    )




def test_update_repeat_count_same_head_increments():
    """Identical signature, NO commit between calls → 1 then 2.

    Pins that HEAD-awareness does NOT break the genuine-stall case: when the
    tuple repeats AND HEAD has not moved, the streak still increments.
    RED: a naive 'always reset when git repo' impl would return 1, 1.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
        # No commit — HEAD unchanged → genuine stall → increment.
        r2 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
    assert r1 == 1, f"expected 1 on first call, got {r1!r}"
    assert r2 == 2, (
        f"expected 2 on identical probe with unchanged HEAD (genuine stall), got {r2!r}"
    )




def test_update_repeat_count_legacy_file_without_head_increments():
    """A hand-written legacy {signature, count} file (no `head`) + identical
    signature → increments (backward-compat), and the rewritten file now
    carries `head`.

    Proves the pre-Phase-9 file shape is honored (no spurious reset) AND that
    the payload is upgraded to the new shape going forward.
    RED: an impl that REQUIRES `head` to match would reset the legacy file to 1.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        sig_path = Path(td) / "sig.json"
        # Hand-write the OLD shape: signature matching _STATE_A, count 1, NO head.
        legacy_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        sig_path.write_text(
            json.dumps({"signature": legacy_sig, "count": 1}), encoding="utf-8"
        )
        result = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
        persisted = json.loads(sig_path.read_text(encoding="utf-8"))
    assert result == 2, (
        f"expected 2 (legacy file without `head` must increment, not reset), got {result!r}"
    )
    assert "head" in persisted, (
        f"rewritten payload must now carry `head`: {persisted!r}"
    )
    assert persisted["head"] is not None, (
        f"`head` should be the repo HEAD sha (real git repo), got {persisted['head']!r}"
    )




def test_update_repeat_count_peek_does_not_mutate():
    """peek=True computes the would-be count WITHOUT writing the state file.

    Sequence in a NON-git repo_root (head is None on both sides → increment
    path): peek, peek, advance, advance → 1, 1, 1, 2.

    The two peeks neither create nor advance the file; the first real advance
    therefore starts the streak at 1 as if the peeks never happened.
    RED: pre-WU-2 has no `peek` kwarg → TypeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Non-git repo_root → _current_head returns None on every call.
        repo_root = Path(td)
        sig_path = Path(td) / "sig.json"
        p1 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path, peek=True)
        peek1_created = sig_path.exists()
        p2 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path, peek=True)
        a1 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
        a2 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
    assert p1 == 1, f"first peek should compute 1, got {p1!r}"
    assert not peek1_created, "peek must NOT create the state file"
    assert p2 == 1, f"second peek should ALSO compute 1 (no mutation), got {p2!r}"
    assert a1 == 1, (
        f"first real advance must start at 1 (peeks did not advance the streak), got {a1!r}"
    )
    assert a2 == 2, f"second real advance should increment to 2, got {a2!r}"




def test_update_repeat_count_non_git_root_stores_none_head():
    """Non-git repo_root: head stored as None and same-tuple still increments
    exactly as the pre-Phase-9 behavior (None == None → increment).

    Backward-compat guard for the common non-git injected-path tests.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
        persisted1 = json.loads(sig_path.read_text(encoding="utf-8"))
        r2 = lazy_core.update_repeat_count(repo_root, _STATE_A, signature_path=sig_path)
    assert (r1, r2) == (1, 2), f"non-git same-tuple must increment 1→2, got {(r1, r2)!r}"
    assert persisted1.get("head") is None, (
        f"non-git repo_root must store head=None, got {persisted1.get('head')!r}"
    )




# ---------------------------------------------------------------------------
# Tests: update_repeat_counts — Phase 10 WU-2 step-level oscillation counter
#
# The step counter is keyed on (feature_id, current_step) ONLY — no sub_skill /
# sub_skill_args — and has NO head-advance reset (its whole purpose is catching
# "productive-looking" oscillation where each cycle commits, HEAD advances, and
# the dispatch-tuple streak resets every iteration). `update_repeat_counts`
# returns BOTH counts in one read/write pass; `update_repeat_count` stays a
# thin int-returning wrapper for backward compatibility.
# ---------------------------------------------------------------------------

def test_update_repeat_counts_returns_both_counts():
    """update_repeat_counts returns a dict with both repeat_count and
    step_repeat_count; first call → both 1.

    RED: update_repeat_counts missing on lazy_core → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        result = lazy_core.update_repeat_counts(Path(td), _STATE_A, signature_path=sig_path)
    assert isinstance(result, dict), f"expected a dict, got {type(result).__name__}"
    assert result.get("repeat_count") == 1, f"expected repeat_count 1, got {result!r}"
    assert result.get("step_repeat_count") == 1, f"expected step_repeat_count 1, got {result!r}"




def test_update_repeat_counts_step_counter_resets_on_step_change():
    """A different current_step → step_repeat_count resets to 1."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_counts(Path(td), _STATE_A, signature_path=sig_path)
        r2 = lazy_core.update_repeat_counts(Path(td), _STATE_A, signature_path=sig_path)
        # current_step changes → new step signature → reset.
        r3 = lazy_core.update_repeat_counts(Path(td), _STATE_A_DIFF_STEP, signature_path=sig_path)
    assert r1["step_repeat_count"] == 1, f"first → 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, f"second identical step → 2, got {r2!r}"
    assert r3["step_repeat_count"] == 1, (
        f"step counter must RESET to 1 when current_step changes, got {r3!r}"
    )




def test_update_repeat_counts_step_no_head_advance_reset():
    """THE Phase-10 discriminator: probe the same (feature_id, current_step)
    twice with a REAL commit in between.

    - repeat_count RESETS to 1 (Phase-9 HEAD-advance behavior preserved).
    - step_repeat_count goes 1 → 2 (NO head-advance reset — its purpose is
      catching oscillation-with-commits).

    RED: a step counter that copied the HEAD-aware reset would return 1, 1.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        # A real commit lands between the two identical probes (HEAD advances).
        _commit_dummy(repo_root, "progress.txt")
        r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
    assert r1["repeat_count"] == 1 and r1["step_repeat_count"] == 1, f"first: {r1!r}"
    assert r2["repeat_count"] == 1, (
        f"repeat_count must RESET after a commit (HEAD advanced = forward progress), got {r2!r}"
    )
    assert r2["step_repeat_count"] == 2, (
        f"step_repeat_count must INCREMENT despite the commit — the whole point is to "
        f"catch oscillation where each cycle commits. got {r2!r}"
    )




def test_update_repeat_counts_step_peek_does_not_mutate():
    """peek=True returns both would-be counts WITHOUT writing the state file —
    the step counter must not advance under peek either.

    Sequence (non-git root): peek, peek, advance, advance → step counts
    1, 1, 1, 2.
    RED: update_repeat_counts missing → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        sig_path = Path(td) / "sig.json"
        p1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path, peek=True)
        peek1_created = sig_path.exists()
        p2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path, peek=True)
        a1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        a2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
    assert not peek1_created, "peek must NOT create the state file"
    assert p1["step_repeat_count"] == 1, f"first peek → 1, got {p1!r}"
    assert p2["step_repeat_count"] == 1, f"second peek → 1 (no mutation), got {p2!r}"
    assert a1["step_repeat_count"] == 1, (
        f"first real advance starts at 1 (peeks didn't advance), got {a1!r}"
    )
    assert a2["step_repeat_count"] == 2, f"second advance → 2, got {a2!r}"




def test_rebaseline_loop_signature_prevents_false_loop_on_checkpoint_resume():
    """checkpoint-resume-false-loop-flips-complex-part-to-sonnet Gap 1: a checkpoint
    --run-end clears the prompt registry and the resuming --run-start recreates it
    fresh, so the OS-temp signature file's consume_count is stale (registry-relative
    to the PRE-checkpoint run). rebaseline_loop_signature_after_registry_reset
    re-baselines it to the fresh registry count so the FIRST re-probe of the same
    route HOLDS repeat_count instead of inflating to 2 (false LOOP DETECTED). The
    persisted count/step_count are preserved (a genuine streak survives).

    RED (no rebaseline): prior_consume (3, pre-checkpoint) != current (0, fresh
    registry) → the F1 debounce cannot prove the re-read → repeat_count 1 → 2 on a
    route that was NEVER re-dispatched.
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
        # A run that dispatched: several consumes recorded, then a probe of the
        # route persists consume_count = 3 alongside count = 1.
        for _ in range(3):
            _record_consume(state_dir)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            pre = json.loads(sig_path.read_text(encoding="utf-8"))
            # Simulate the checkpoint --run-end/--run-start registry reset: delete
            # the registry so consumed_emission_count() drops back to 0 (the marker
            # is re-written by --run-start; here it simply stays present).
            (state_dir / lazy_core._REGISTRY_FILENAME).unlink(missing_ok=True)
            # The resume re-baselines the signature's consume_count BEFORE the next
            # probe so the debounce recognizes the re-read.
            did = lazy_core.rebaseline_loop_signature_after_registry_reset(
                repo_root, signature_path=sig_path,
            )
            post = json.loads(sig_path.read_text(encoding="utf-8"))
            r2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 1, f"first probe → 1, got {r1!r}"
    assert pre.get("consume_count") == 3, f"pre-checkpoint consume_count should be 3, got {pre!r}"
    assert did is True, "rebaseline should have rewritten the existing signature file"
    assert post.get("consume_count") == 0, (
        f"rebaseline must reset consume_count to the fresh (0) registry count, got {post!r}"
    )
    # count/step_count preserved so a genuine streak survives.
    assert post.get("count") == 1 and post.get("step_count") == 1, (
        f"rebaseline must PRESERVE the persisted streak fields, got {post!r}"
    )
    assert r2["repeat_count"] == 1, (
        f"first re-probe after a checkpoint registry reset must HOLD (a "
        f"probe→checkpoint→probe is not a stall) once re-baselined, got {r2!r}"
    )




# ---------------------------------------------------------------------------
# Tests: git_guard_status — WU-5 single-probe payload (git guards)
# ---------------------------------------------------------------------------

def test_git_guard_status_clean_and_pushed():
    """Fresh repo with one commit pushed → clean_tree=True, head_matches_origin=True, unpushed=False.

    Uses _make_git_repo_with_origin so @{u} resolves.
    RED: git_guard_status missing → AttributeError after _guard().
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        result = lazy_core.git_guard_status(repo_root)
    assert result == {"clean_tree": True, "head_matches_origin": True, "unpushed": False}, (
        f"expected all-green dict for clean pushed repo, got {result!r}"
    )




def test_git_guard_status_dirty_tree():
    """Untracked file present → clean_tree=False (other fields unconstrained).

    After the push, add an untracked file without staging it.  The tree is now
    dirty even though HEAD == @{u}.
    RED: git_guard_status missing → AttributeError after _guard().
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        # Drop an untracked file — do NOT stage or commit.
        (repo_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        result = lazy_core.git_guard_status(repo_root)
    assert result["clean_tree"] is False, (
        f"expected clean_tree=False with an untracked file present, got {result!r}"
    )




def test_git_guard_status_unpushed_commit():
    """Local commit not yet pushed → head_matches_origin=False, unpushed=True, clean_tree=True.

    After the initial push, make a NEW commit (so the working tree is clean but
    HEAD is one commit ahead of @{u}).
    RED: git_guard_status missing → AttributeError after _guard().
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        # Create a new file, commit it — do NOT push.
        (repo_root / "ahead.txt").write_text("unpushed change\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo_root), "add", "ahead.txt"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "commit", "-q", "-m", "unpushed"],
            check=True, capture_output=True,
        )
        result = lazy_core.git_guard_status(repo_root)
    assert result["head_matches_origin"] is False, (
        f"expected head_matches_origin=False when HEAD is ahead of @{{u}}, got {result!r}"
    )
    assert result["unpushed"] is True, (
        f"expected unpushed=True when HEAD is one commit ahead of @{{u}}, got {result!r}"
    )
    assert result["clean_tree"] is True, (
        f"expected clean_tree=True (change was committed, not left dirty), got {result!r}"
    )




def test_git_guard_status_invalid_repo_is_safe_dirty():
    """Plain temp dir (not a git repo) → all three fields are False (safe-dirty).

    git status --short exits 128 with EMPTY stdout for a non-git directory.
    The old code checked only stdout and therefore returned clean_tree=True
    (false-positive).  The fixed code requires returncode==0 AND empty stdout,
    so an invalid repo path → clean_tree=False (safe-dirty), consistent with
    head_matches_origin=False and unpushed=False.

    This test is DISCRIMINATING: it FAILS under the old stdout-only logic and
    PASSES only after the returncode guard is in place.
    RED: old code → clean_tree=True (false-positive clean), assertion fails.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # td is a plain directory — NOT a git repo.
        result = lazy_core.git_guard_status(Path(td))
    assert result["clean_tree"] is False, (
        f"expected clean_tree=False for a non-git directory, got {result!r}"
    )
    assert result["head_matches_origin"] is False, (
        f"expected head_matches_origin=False for a non-git directory, got {result!r}"
    )
    assert result["unpushed"] is False, (
        f"expected unpushed=False for a non-git directory, got {result!r}"
    )


def _build_blocked_bug_repo(root: Path, blocked_frontmatter: str) -> Path:
    """Bug-pipeline mirror of _build_blocked_feature_repo (docs/bugs layout)."""
    bugs = root / "docs" / "bugs"
    bugs.mkdir(parents=True)
    bugs.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "bug-esc", "name": "Bug ESC", "spec_dir": "bug-esc"}
            ]
        }),
        encoding="utf-8",
    )
    bdir = bugs / "bug-esc"
    bdir.mkdir()
    (bdir / "SPEC.md").write_text(
        "# Bug ESC\n\n"
        "**Status:** Investigating\n\n"
        "**Severity:** P1\n\n"
        "**Discovered:** 2026-06-01\n",
        encoding="utf-8",
    )
    (bdir / "BLOCKED.md").write_text(
        "---\n" + blocked_frontmatter + "---\n\n# Blocked\n",
        encoding="utf-8",
    )
    return root




# ---- WU-1a end-to-end: compute_state() blocked-terminal escalation payload ----

def test_lazy_state_blocked_escalation_payload():
    """lazy-state compute_state(): BLOCKED.md with blocker_kind mcp-validation +
    retry_count 2 → state carries validation_escalation: true and the
    notify_message ends with the escalation suffix."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_blocked_feature_repo(
            Path(td),
            "kind: blocked\nfeature_id: feat-esc\nphase: MCP Validation\n"
            "blocker_kind: mcp-validation\nretry_count: 2\n"
            "blocked_at: 2026-06-11T00:00:00Z\n",
        )
        state = ls.compute_state(root, False)
    assert state["terminal_reason"] == "blocked", state
    assert state.get("validation_escalation") is True, (
        f"expected validation_escalation: true at retry_count 2, got {state}"
    )
    assert state["notify_message"].endswith(
        lazy_core.VALIDATION_ESCALATION_SUFFIX
    ), f"notify_message missing escalation suffix: {state['notify_message']!r}"




def test_lazy_state_blocked_no_escalation_retry_1():
    """lazy-state compute_state(): retry_count 1 (mcp-validation) → NO
    validation_escalation key at all (payload byte-identical to pre-Phase-11)
    and an unchanged notify_message."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_blocked_feature_repo(
            Path(td),
            "kind: blocked\nfeature_id: feat-esc\nphase: MCP Validation\n"
            "blocker_kind: mcp-validation\nretry_count: 1\n"
            "blocked_at: 2026-06-11T00:00:00Z\n",
        )
        state = ls.compute_state(root, False)
    assert state["terminal_reason"] == "blocked", state
    assert "validation_escalation" not in state, (
        f"validation_escalation must be ABSENT (not false) at retry_count 1: {state}"
    )
    assert state["notify_message"] == (
        "BLOCKED: Feature ESC — MCP Validation. Awaiting input."
    ), f"non-escalated message must be unchanged: {state['notify_message']!r}"




def test_bug_state_blocked_escalation_payload():
    """bug-state compute_state(): the BLOCKED terminal mirrors lazy-state's
    escalation payload exactly (key + suffixed message at retry_count >= 2)."""
    _guard()
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_blocked_bug_repo(
            Path(td),
            "kind: blocked\nbug_id: bug-esc\nphase: MCP Validation\n"
            "blocker_kind: mcp-validation\nretry_count: 2\n"
            "blocked_at: 2026-06-11T00:00:00Z\n",
        )
        state = bs.compute_state(root, False)
    assert state["terminal_reason"] == bs.TR_BLOCKED, state
    assert state.get("validation_escalation") is True, (
        f"expected validation_escalation: true at retry_count 2, got {state}"
    )
    assert state["notify_message"].endswith(
        lazy_core.VALIDATION_ESCALATION_SUFFIX
    ), f"notify_message missing escalation suffix: {state['notify_message']!r}"




def test_bug_state_blocked_no_escalation_other_kind():
    """bug-state compute_state(): retry_count 3 but a non-mcp-validation
    blocker_kind → no escalation key, unchanged message."""
    _guard()
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_blocked_bug_repo(
            Path(td),
            "kind: blocked\nbug_id: bug-esc\nphase: Investigation\n"
            "blocker_kind: pre-research-input-required\nretry_count: 3\n"
            "blocked_at: 2026-06-11T00:00:00Z\n",
        )
        state = bs.compute_state(root, False)
    assert state["terminal_reason"] == bs.TR_BLOCKED, state
    assert "validation_escalation" not in state, state
    assert state["notify_message"] == (
        "BLOCKED: Bug ESC — Investigation. Awaiting input."
    ), state["notify_message"]




def test_lazy_state_retro_fresh_routes_past_step8():
    """RETRO_DONE.md whose phase_count_at_retro EQUALS the current phase count →
    fresh retro; routing falls through Step 8 to Step 9 mcp-test as today."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_retro_routing_repo(
            Path(td),
            "kind: retro-done\nfeature_id: feat-retro\ndate: 2026-06-01\n"
            "rounds: 1\nphase_count_at_retro: 3\n",
            phase_count=3,
        )
        state = ls.compute_state(root, False)
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]




def test_lazy_state_retro_stale_design_added_routes_past_step8():
    """RETRO UNWIRED (2026-06): even a stale RETRO_DONE.md with a trailing DESIGN
    phase added post-retro (which historically re-staled the retro) no longer
    re-dispatches retro-feature — retro is removed from the pipeline, so routing
    falls through to Step 9 mcp-test regardless of staleness."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_retro_routing_repo(
            Path(td),
            "kind: retro-done\nfeature_id: feat-retro\ndate: 2026-06-01\n"
            "rounds: 1\nphase_count_at_retro: 1\n",
            phase_count=3,
            phase_kinds=["design", "corrective", "design"],
        )
        state = ls.compute_state(root, False)
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]




def test_lazy_state_no_plans_verification_only_routes_to_mcp():
    """Workstation: NO plans/ dir + verification-only unchecked remainder →
    Step 9 mcp-test, NOT a write-plan loop (the mcp-testing deadlock)."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_no_plans_verification_only_repo(Path(td))
        state = ls.compute_state(root, False)
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]
    assert state["sub_skill"] != "write-plan", state




def test_f2b_find_transcription_slip_entry_matches_near_copy():
    """F2b / F2c: find_transcription_slip_entry must return the registered entry when
    the dispatched prompt differs ONLY by characters that F2b does NOT fold (e.g. a
    word replaced) and the similarity ratio >= threshold.

    RED: find_transcription_slip_entry does not exist yet.
    """
    _guard()
    assert hasattr(lazy_core, "find_transcription_slip_entry"), (
        "lazy_core.find_transcription_slip_entry missing — F2c not yet implemented"
    )
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # Write a marker so find_transcription_slip_entry's run-start gate works.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(state_dir / "fixture-repo"), max_cycles=10,
                now=_time.time(),
            )
            # Register an emission.  Must be long enough (>= ~267 chars) that changing
            # one word ('criteria' → 'CRITERIA', 8 chars) keeps difflib ratio >= 0.97.
            # ratio = (n-8)/n where n is the prompt length; need n >= 267.
            original = (
                "Run the next dispatch cycle step exactly as specified in the "
                "feature implementation plan. Execute all planned tasks in order, "
                "verify each deliverable against the acceptance criteria, record "
                "the observed behavior in your response output section, and note "
                "any deviations from the expected outcome in your analysis."
            )
            lazy_core.register_emission(original, cls="cycle", item_id="feat-x")
            # A near-copy: 'criteria' → 'CRITERIA' (one word changed, 8 chars).
            # High similarity ratio because the body is long and nearly identical.
            near_copy = (
                "Run the next dispatch cycle step exactly as specified in the "
                "feature implementation plan. Execute all planned tasks in order, "
                "verify each deliverable against the acceptance CRITERIA, record "
                "the observed behavior in your response output section, and note "
                "any deviations from the expected outcome in your analysis."
            )
            import difflib as _dl
            _ratio = _dl.SequenceMatcher(
                None,
                lazy_core.normalize_prompt_for_hash(near_copy),
                lazy_core.normalize_prompt_for_hash(original),
            ).ratio()
            assert _ratio >= 0.97, (
                f"test pre-condition: near_copy/original ratio must be >= 0.97; "
                f"got {_ratio:.4f}. Increase the prompt length."
            )
            entry = lazy_core.find_transcription_slip_entry(near_copy)
            assert entry is not None, (
                "find_transcription_slip_entry must return the registered entry for a "
                "near-copy (high similarity ratio, one word changed) — F2c"
            )
        finally:
            _clear_state_dir()




def test_f2b_find_transcription_slip_entry_no_match_for_different_prompt():
    """F2b / F2c: find_transcription_slip_entry must return None when the dispatched
    prompt has low similarity to any registered entry (genuinely unrelated prompt).

    RED: find_transcription_slip_entry does not exist yet.
    """
    _guard()
    assert hasattr(lazy_core, "find_transcription_slip_entry"), (
        "lazy_core.find_transcription_slip_entry missing — F2c not yet implemented"
    )
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(state_dir / "fixture-repo"), max_cycles=10,
                now=_time.time(),
            )
            lazy_core.register_emission(
                "Run the next dispatch cycle step as specified in the plan.",
                cls="cycle", item_id="feat-x",
            )
            # Completely unrelated prompt — low similarity.
            unrelated = "This is a hand-composed prompt about something entirely different."
            entry = lazy_core.find_transcription_slip_entry(unrelated)
            assert entry is None, (
                "find_transcription_slip_entry must return None for a genuinely different "
                "prompt (no close registered match) — F2c"
            )
        finally:
            _clear_state_dir()




def test_f2b_find_transcription_slip_entry_excludes_hardening_class():
    """F2b / F2c: find_transcription_slip_entry must EXCLUDE hardening-class entries
    so the depth-1 hardening cap stays intact.

    RED: find_transcription_slip_entry does not exist yet.
    """
    _guard()
    assert hasattr(lazy_core, "find_transcription_slip_entry"), (
        "lazy_core.find_transcription_slip_entry missing — F2c not yet implemented"
    )
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False,
                repo_root=str(state_dir / "fixture-repo"), max_cycles=10,
                now=_time.time(),
            )
            # Register a hardening-class entry (must never be a slip candidate).
            original = "You are the harden-harness subagent. Analyze and fix the issue."
            lazy_core.register_emission(original, cls="hardening", item_id=None)
            # Near-copy with one word changed — would match by ratio, but class is hardening.
            near_copy = "You are the harden-harness subagent. Analyze and FIX the issue."
            entry = lazy_core.find_transcription_slip_entry(near_copy)
            assert entry is None, (
                "find_transcription_slip_entry must NOT return hardening-class entries "
                "(depth-1 cap must stay intact) — F2c"
            )
        finally:
            _clear_state_dir()




def test_emit_dispatch_cycle_header_summary_fallback():
    """cycle_header summary falls back to item_id when item_name is absent."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            import time as _time
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=4, now=_time.time(),
            )
            ctx = {k: f"v-{k}" for k in _dispatch_requires("recovery")}
            # Provide item_id but NOT item_name → summary should be item_id.
            ctx["item_id"] = "feat-fallback"
            ctx.pop("item_name", None)
            ctx["item_name"] = ""  # falsy → fallback to item_id
            r = lazy_core.emit_dispatch_prompt("recovery", ctx, pipeline="feature")
            assert r["ok"], r
            assert r["cycle_header"] == "### Recover — feat-fallback [meta 1]", (
                r.get("cycle_header")
            )
        finally:
            _clear_state_dir()




def test_guard_allow_acks_on_hardening_class():
    """Phase 8 WU-8.2: simulate the guard ALLOW path on a hardening-class entry
    → oldest deny acked; a cycle-class allow → no ack; allow with empty ledger →
    no error; an internal ack failure → allow output unchanged (fail-open).

    Drives lazy_guard.guard() in-process (it imports lazy_core directly) so the
    allow paths are exercised without spawning bash."""
    _guard()
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    lazy_guard = importlib.import_module("lazy_guard")
    import time as _time

    def _hook_input(prompt, tool_use_id):
        return json.dumps({
            "tool_use_id": tool_use_id,
            "tool_input": {"prompt": prompt},
        })

    # --- hardening-class allow → oldest deny acked ---
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="d", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            prompt = "REAL hardening dispatch prompt"
            lazy_core.register_emission(prompt, cls="hardening")
            assert lazy_core.pending_hardening() == 1
            out = lazy_guard.guard(_hook_input(prompt, "tu-h"))
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", out
            assert lazy_core.pending_hardening() == 0, (
                "a hardening-class allow must ack the oldest deny"
            )
        finally:
            _clear_state_dir()

    # --- cycle-class allow → no ack ---
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="d", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            prompt = "REAL cycle dispatch prompt"
            lazy_core.register_emission(prompt, cls="cycle")
            out = lazy_guard.guard(_hook_input(prompt, "tu-c"))
            assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "allow"
            assert lazy_core.pending_hardening() == 1, (
                "a cycle-class allow must NOT ack the deny ledger"
            )
        finally:
            _clear_state_dir()

    # --- hardening allow with EMPTY ledger → no error, allow unchanged ---
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            prompt = "hardening with no debt"
            lazy_core.register_emission(prompt, cls="hardening")
            out = lazy_guard.guard(_hook_input(prompt, "tu-e"))
            assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "allow", (
                "hardening allow with empty ledger must still allow (no error)"
            )
            assert lazy_core.pending_hardening() == 0
        finally:
            _clear_state_dir()

    # --- ack raising internally → allow output unchanged (fail-open) ---
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="d", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            prompt = "hardening with a poisoned ack"
            lazy_core.register_emission(prompt, cls="hardening")
            # Monkeypatch ack_oldest_deny to raise — _ack_if_hardening must swallow.
            original = lazy_core._monolith.ack_oldest_deny
            def _boom(*a, **k):
                raise RuntimeError("ack exploded")
            lazy_core._monolith.ack_oldest_deny = _boom  # type: ignore[assignment]
            try:
                out = lazy_guard.guard(_hook_input(prompt, "tu-boom"))
            finally:
                lazy_core._monolith.ack_oldest_deny = original  # type: ignore[assignment]
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", (
                "an ack failure must NEVER change the allow output (fail-open)"
            )
        finally:
            _clear_state_dir()




def test_guard_pins_model_on_fresh_allow():
    """mechanize-prose-only-orchestrator-contracts (a) / D1-A: the fresh-
    consumption ALLOW path corrects a mismatched or missing ``model:`` field
    to the registry entry's script-selected tier (pin-by-rewrite), and is a
    complete no-op (no updatedInput at all) both when the model already
    matches and when the entry predates the ``model`` field (legacy
    fail-open — never pin against an unknown tier)."""
    _guard()
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    lazy_guard = importlib.import_module("lazy_guard")
    import time as _time

    def _hook_input(prompt, tool_use_id, model=None):
        tool_input = {"prompt": prompt}
        if model is not None:
            tool_input["model"] = model
        return json.dumps({
            "tool_use_id": tool_use_id,
            "tool_input": tool_input,
        })

    # --- mismatch: opus dispatched, haiku registered -> pinned to haiku ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td) / "state")
        (Path(td) / "state").mkdir()
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            prompt = "cycle dispatch prompt — mismatch case"
            lazy_core.register_emission(prompt, cls="cycle", model="haiku")
            out = json.loads(lazy_guard.guard(
                _hook_input(prompt, "tu-mismatch", model="opus")
            ))
            hso = out["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow"
            assert hso["updatedInput"]["model"] == "haiku", hso
            assert "model pinned" in hso["permissionDecisionReason"]
        finally:
            _clear_state_dir()

    # --- missing: no model in tool_input, sonnet registered -> pinned ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td) / "state")
        (Path(td) / "state").mkdir()
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            prompt = "cycle dispatch prompt — missing case"
            lazy_core.register_emission(prompt, cls="cycle", model="sonnet")
            out = json.loads(lazy_guard.guard(
                _hook_input(prompt, "tu-missing")
            ))
            hso = out["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow"
            assert hso["updatedInput"]["model"] == "sonnet", hso
        finally:
            _clear_state_dir()

    # --- already correct: no updatedInput needed ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td) / "state")
        (Path(td) / "state").mkdir()
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            prompt = "cycle dispatch prompt — already correct"
            lazy_core.register_emission(prompt, cls="cycle", model="opus")
            out = json.loads(lazy_guard.guard(
                _hook_input(prompt, "tu-correct", model="opus")
            ))
            hso = out["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow"
            assert "updatedInput" not in hso, (
                "no correction needed -> no updatedInput key at all"
            )
        finally:
            _clear_state_dir()

    # --- legacy entry (no model field) -> fail-open, no pin, no error ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td) / "state")
        (Path(td) / "state").mkdir()
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            prompt = "cycle dispatch prompt — legacy entry"
            # Register directly via register_emission with model=None (the
            # legacy/pre-migration shape) to simulate an un-migrated entry.
            lazy_core.register_emission(prompt, cls="cycle", model=None)
            out = json.loads(lazy_guard.guard(
                _hook_input(prompt, "tu-legacy", model="opus")
            ))
            hso = out["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow"
            assert "updatedInput" not in hso, (
                "a legacy entry with no model field must never be pinned"
            )
        finally:
            _clear_state_dir()




def test_guard_pins_model_on_by_reference_and_auto_readmit_allows():
    """mechanize-prose-only-orchestrator-contracts (a) / D1-A: the F2a
    by-reference ALLOW (which already returns updatedInput for the resolved
    prompt) ALSO corrects model in the SAME updatedInput; the F1b
    auto-readmit ALLOW (a pure trailing-suffix superset of a fresh cycle
    entry) gains updatedInput for the FIRST time, carrying only the
    corrected model (the dispatched — suffixed — prompt text is unchanged)."""
    _guard()
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    lazy_guard = importlib.import_module("lazy_guard")
    import time as _time

    # --- by-reference (@@lazy-ref) ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td) / "state")
        (Path(td) / "state").mkdir()
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            prompt = "cycle dispatch prompt — by-ref case"
            entry = lazy_core.register_emission(prompt, cls="cycle", model="haiku")
            ref = f"@@lazy-ref nonce={entry['nonce']}"
            hook_input = json.dumps({
                "tool_use_id": "tu-ref",
                "tool_input": {"prompt": ref, "model": "opus"},
            })
            out = json.loads(lazy_guard.guard(hook_input))
            hso = out["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow"
            assert hso["updatedInput"]["prompt"] == prompt
            assert hso["updatedInput"]["model"] == "haiku", hso
        finally:
            _clear_state_dir()

    # --- auto-readmit (F1b pure trailing-suffix superset) ---
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td) / "state")
        (Path(td) / "state").mkdir()
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            base_prompt = "cycle dispatch prompt — auto-readmit base"
            lazy_core.register_emission(base_prompt, cls="cycle", model="sonnet")
            suffixed = base_prompt + "\n\nOrchestrator note: proceeding."
            hook_input = json.dumps({
                "tool_use_id": "tu-readmit",
                "tool_input": {"prompt": suffixed, "model": "opus"},
            })
            out = json.loads(lazy_guard.guard(hook_input))
            hso = out["hookSpecificOutput"]
            assert hso["permissionDecision"] == "allow", out
            assert "auto-readmit" in hso["permissionDecisionReason"]
            assert hso["updatedInput"]["model"] == "sonnet", hso
            # The dispatched (suffixed) prompt text itself is unchanged.
            assert hso["updatedInput"]["prompt"] == suffixed
        finally:
            _clear_state_dir()




def test_dispatch_by_reference_round_trips_every_class():
    """meta-dispatch-not-by-reference-and-ack-overpriced Fix Scope §3: EVERY
    class in DISPATCH_CLASSES round-trips register_emission ->
    dispatch_prompt_ref ('@@lazy-ref nonce=<hex>') -> lazy_guard.guard()
    resolve (allow + updatedInput.prompt == the original text). Half 1 of the
    bug (meta prompts not dispatchable by reference) is fixed in current code
    for every class that exists TODAY — this regression guard is what keeps a
    FUTURE emit path from silently regressing to transcription-only."""
    _guard()
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    lazy_guard = importlib.import_module("lazy_guard")
    import time as _time

    def _hook_input(prompt, tool_use_id):
        return json.dumps({
            "tool_use_id": tool_use_id,
            "tool_input": {"prompt": prompt},
        })

    for cls in lazy_core.DISPATCH_CLASSES:
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td) / "state"
            state_dir.mkdir()
            _set_state_dir(state_dir)
            try:
                lazy_core.write_run_marker(
                    pipeline="feature", cloud=False, repo_root="/r",
                    max_cycles=5, now=_time.time(),
                )
                prompt = f"REAL {cls} dispatch prompt — do the thing"
                entry = lazy_core.register_emission(prompt, cls=cls)
                assert entry.get("nonce"), (cls, entry)
                ref = f"@@lazy-ref nonce={entry['nonce']}"
                out = lazy_guard.guard(_hook_input(ref, f"tu-{cls}"))
                assert out is not None, (cls, "guard returned no output for a ref token")
                data = json.loads(out)
                hso = data["hookSpecificOutput"]
                assert hso["permissionDecision"] == "allow", (cls, out)
                assert hso["updatedInput"]["prompt"] == prompt, (
                    f"class {cls!r} did not round-trip to the original prompt: {out}"
                )
            finally:
                _clear_state_dir()




def test_phase8_mvb_chain():
    """Phase 8 MVB integration chain (the PHASES.md MVB paragraph as one test):
    marked run + 1 unacked deny → `--probe --emit-prompt` returns
    route_overridden_by with NO cycle_prompt and a bound hardening_emit_command;
    running that command registers a hardening-class entry WITHOUT acking; a
    simulated guard ALLOW of that entry acks the ledger; the next probe returns a
    normal forward route.  Separately: read_run_marker(session_id='other')
    returns None while the marker file remains and the owner still reads it."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    lazy_guard = importlib.import_module("lazy_guard")
    import time as _time

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

        # Marked run bound to 'owner', + 1 unacked deny.
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(fixture_repo),
                max_cycles=10, session_id="owner", now=_time.time(),
            )
            lazy_core.append_deny_ledger_entry(
                tool_use_id="d", denied_sha12="a" * 12,
                reason_head="reason head", prompt_head="prompt head", now=1.0,
            )
        finally:
            _clear_state_dir()

        # Probe withholds.
        out1 = json.loads(probe().stdout)
        assert out1.get("route_overridden_by") == "pending-hardening-debt", out1
        assert "cycle_prompt" not in out1, out1
        cmd = out1["hardening_emit_command"]

        # Run the emitted command (parse out the args after the script name).
        # The command is bash-shaped; re-derive the arg list for a direct call.
        keys = _dispatch_requires("hardening")
        ctx_flags = []
        for k in keys:
            ctx_flags += ["--context", f"{k}=test-{k}"]
        if "item_id" not in keys:
            ctx_flags += ["--context", "item_id=feat-c"]
        emit = subprocess.run(
            [sys.executable, str(lazy_state), "--emit-dispatch", "hardening"] + ctx_flags,
            capture_output=True, text=True, env=env,
        )
        assert emit.returncode == 0, emit.stderr
        hardening_prompt = json.loads(emit.stdout)["dispatch_prompt"]

        # Emission registered the entry but did NOT ack.
        _set_state_dir(state_dir)
        try:
            assert lazy_core.pending_hardening() == 1, "emission must not ack"
        finally:
            _clear_state_dir()

        # Simulated guard ALLOW of that hardening entry → acks the ledger.
        _set_state_dir(state_dir)
        try:
            out = lazy_guard.guard(json.dumps({
                "tool_use_id": "tu-h",
                "tool_input": {"prompt": hardening_prompt},
            }))
            assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "allow"
            assert lazy_core.pending_hardening() == 0, "guard allow must ack the debt"
        finally:
            _clear_state_dir()

        # Next probe returns a NORMAL forward route again.
        out2 = json.loads(probe().stdout)
        assert "route_overridden_by" not in out2, out2
        assert "cycle_prompt" in out2, "debt cleared → forward route restored"

        # Concurrent-session leg: non-owner read → None + file survives; owner reads.
        marker_path = state_dir / "lazy-run-marker.json"
        _set_state_dir(state_dir)
        try:
            assert lazy_core.read_run_marker(session_id="other") is None
            assert marker_path.exists(), "non-owner read must not delete the marker"
            owner = lazy_core.read_run_marker(session_id="owner")
            assert owner is not None and owner["session_id"] == "owner", owner
        finally:
            _clear_state_dir()




def test_guard_unbound_marker_binds_on_allow():
    """WU-9.2: with an UNBOUND marker and a REGISTERED prompt, guard ALLOWs and
    binds the marker to the caller's session_id (fresh-consumption path)."""
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
            prompt = "Run the next cycle step exactly as specified."
            lazy_core.register_emission(prompt, cls="cycle")

            hook_input = json.dumps({
                "session_id": "binder-session",
                "tool_use_id": "tu-bind",
                "tool_input": {"prompt": prompt},
            })
            out = lazy_guard.guard(hook_input)
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", out

            # The marker must now be bound to the caller's session_id.
            marker = json.loads(
                (state_dir / "lazy-run-marker.json").read_text(encoding="utf-8")
            )
            assert marker.get("session_id") == "binder-session", (
                f"WU-9.2: guard ALLOW must bind the unbound marker to the caller; "
                f"got session_id={marker.get('session_id')!r}"
            )
        finally:
            _clear_state_dir()




def test_guard_unbound_marker_binds_on_idempotent_refire():
    """WU-9.2: the idempotent re-fire allow path also binds the unbound marker.
    Two successive guard calls with the SAME tool_use_id: the first consumes
    (fresh allow, binds), the second is the idempotent re-fire (allow) — both
    bind paths land the same session_id.  To isolate the re-fire path, the marker
    is reset to unbound between the two calls so the SECOND (re-fire) call is the
    one observed performing the bind.
    """
    _guard()
    lazy_guard = _phase9_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        marker_path = state_dir / "lazy-run-marker.json"
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, session_id=None, now=_time.time(),  # UNBOUND
            )
            prompt = "Execute the planned implementation step."
            lazy_core.register_emission(prompt, cls="cycle")

            hook_input = json.dumps({
                "session_id": "refire-session",
                "tool_use_id": "tu-refire",
                "tool_input": {"prompt": prompt},
            })
            # First call — fresh consumption (allow, binds).
            out1 = lazy_guard.guard(hook_input)
            assert json.loads(out1)["hookSpecificOutput"]["permissionDecision"] == "allow"

            # Reset the marker to UNBOUND so the second (re-fire) call is the one
            # observed binding — proves the idempotent re-fire path binds too.
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["session_id"] = None
            marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

            # Second call — idempotent re-fire (entry already consumed by tu-refire).
            out2 = lazy_guard.guard(hook_input)
            payload2 = json.loads(out2)["hookSpecificOutput"]
            assert payload2["permissionDecision"] == "allow", out2
            assert "idempotent re-fire" in payload2["permissionDecisionReason"], (
                f"second call must take the idempotent re-fire path; got {payload2!r}"
            )

            rebound = json.loads(marker_path.read_text(encoding="utf-8"))
            assert rebound.get("session_id") == "refire-session", (
                f"WU-9.2: the idempotent re-fire allow must also bind the unbound "
                f"marker; got session_id={rebound.get('session_id')!r}"
            )
        finally:
            _clear_state_dir()




def test_guard_bound_non_owner_fast_path_unchanged():
    """WU-9.2 regression guard (Phase 8 behavior preserved): when the marker is
    bound to a DIFFERENT session, the guard sees no marker (path B non-owner),
    fast-path allows with NO output, and the bound marker is untouched."""
    _guard()
    lazy_guard = _phase9_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        marker_path = state_dir / "lazy-run-marker.json"
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, session_id="owner-session", now=_time.time(),
            )
            prompt = "Execute the step from owner-session."
            lazy_core.register_emission(prompt, cls="cycle")
            marker_bytes_before = marker_path.read_bytes()

            out = lazy_guard.guard(json.dumps({
                "session_id": "non-owner-session",  # DIFFERENT from owner
                "tool_use_id": "tu-nonowner",
                "tool_input": {"prompt": prompt},
            }))
            # Non-owner sees no marker → fast-path allow returns None (no output).
            assert out is None, (
                f"bound-non-owner guard must fast-path allow with no output; got {out!r}"
            )
            # The owner's marker is untouched (still bound to owner, byte-identical).
            assert marker_path.read_bytes() == marker_bytes_before, (
                "bound-non-owner guard must not mutate the owner's marker"
            )
        finally:
            _clear_state_dir()




def test_f1b_hardening_class_suffix_never_auto_readmits():
    """F1b hard exclusion: a pure-suffix superset of a HARDENING-class entry is
    NEVER auto-readmitted (the depth-1 cap stays intact) — it DENIES and the
    entry's nonce is left unconsumed."""
    _guard()
    lazy_guard = _f1_guard_module()
    import time as _time

    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        # D2 (stale-marker-arms-validate-deny-on-unrelated-dispatches, 2026-06-19):
        # the dispatched suffix changes the hash, so this is a GENERIC no-route
        # default-deny (NOT the hardening-cap branch) — no-debt under an UNBOUND
        # marker (WU-3). Bind the marker + pass the owner session so the deny still
        # ledgers, preserving this test's assertion that a ledger event is written.
        _f1b_owner = "11111111-2222-3333-4444-555555555555"
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(), session_id=_f1b_owner,
            )
            base = "You are the harden-harness subagent. Analyze and fix the gap."
            entry = lazy_core.register_emission(base, cls="hardening")
            nonce = entry["nonce"]

            dispatched = base + "\n\nORCHESTRATOR NOTE: also bump the version."
            out = lazy_guard.guard(_f1_hook_input(dispatched, "tu-hard-suffix", session_id=_f1b_owner))
            assert out is not None
            payload = json.loads(out)
            assert payload["hookSpecificOutput"]["permissionDecision"] == "deny", (
                "a hardening-class suffix must NEVER auto-readmit — it must DENY"
            )
            # nonce must remain unconsumed (no auto-readmit consume).
            registry = json.loads(
                (state_dir / "lazy-prompt-registry.json").read_text(encoding="utf-8")
            )
            match = [e for e in registry["entries"] if e.get("nonce") == nonce]
            assert match and match[0].get("consumed") is False, (
                "a hardening-class entry must never be consumed by auto-readmit"
            )
            ledger = state_dir / "lazy-deny-ledger.jsonl"
            events = [
                json.loads(ln)
                for ln in ledger.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
            assert all(not e.get("auto_readmit") for e in events), (
                "a hardening-class suffix must never write an auto_readmit event"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 7: ring cap — 65 entries → 64 kept, oldest evicted
# ---------------------------------------------------------------------------

def test_registry_ring_cap():
    """Registering 65 entries → the registry file holds exactly 64 entries;
    the first-registered entry's nonce is absent (oldest evicted by ring cap).

    RED state: ring-cap eviction not implemented.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            first_nonce = None
            for i in range(65):
                prompt = f"ring-cap dispatch prompt number {i}"
                entry = lazy_core.register_emission(prompt, cls="cycle", now=now + i)
                if i == 0:
                    first_nonce = entry["nonce"]

            # Read the registry file directly to count entries
            state_dir = lazy_core.claude_state_dir()
            registry_file = state_dir / "lazy-prompt-registry.json"
            assert registry_file.exists(), "lazy-prompt-registry.json must exist after 65 writes"
            data = json.loads(registry_file.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            assert len(entries) == 64, (
                f"ring cap is 64 — expected 64 entries after 65 writes, got {len(entries)}"
            )

            # The first entry's nonce must have been evicted
            remaining_nonces = {e["nonce"] for e in entries}
            assert first_nonce not in remaining_nonces, (
                f"oldest entry (nonce={first_nonce!r}) must be evicted by ring cap"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 9: marker gating — register_emission_if_marked no-ops without marker
# ---------------------------------------------------------------------------

def test_register_emission_if_marked_gating():
    """register_emission_if_marked with NO marker present → returns None and
    lazy-prompt-registry.json does NOT exist; with marker → entry written with
    the given class.

    RED state: register_emission_if_marked not implemented.
    """
    _guard()
    import time as _time

    # Without a marker: must return None and write nothing
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            result = lazy_core.register_emission_if_marked(
                "some cycle prompt", cls="cycle", now=now
            )
            assert result is None, (
                f"register_emission_if_marked must return None when no marker present, "
                f"got {result!r}"
            )
            registry_file = lazy_core.claude_state_dir() / "lazy-prompt-registry.json"
            assert not registry_file.exists(), (
                "lazy-prompt-registry.json must NOT exist when register_emission_if_marked "
                "is called without a marker"
            )
        finally:
            _clear_state_dir()

    # With a marker: must write an entry with the given class
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=5, now=now,
            )
            entry = lazy_core.register_emission_if_marked(
                "a real cycle dispatch prompt", cls="cycle", now=now
            )
            assert entry is not None, (
                "register_emission_if_marked must return an entry when marker is present"
            )
            assert entry["class"] == "cycle", f"class mismatch: {entry}"
            registry_file = lazy_core.claude_state_dir() / "lazy-prompt-registry.json"
            assert registry_file.exists(), (
                "lazy-prompt-registry.json must exist after register_emission_if_marked "
                "with marker present"
            )
        finally:
            _clear_state_dir()




def test_forward_cycles_survive_ring_cap_crossing_with_meta_interleave():
    """Phase 3 (byref-dispatch-undercounts-forward-cycles) — the LONG-RUN regression
    net the hermetic single-advance fixtures missed.

    Simulates a long /lazy-batch run that CROSSES the 64-entry ring cap (≥65
    emissions) with interleaved meta dispatches, asserting `forward_cycles` keeps
    advancing once per REAL-skill state change — reproducing and defeating the SPEC's
    "stuck at 16 / frozen at 50" signature (the forward counter freezing at a plateau
    once cumulative emissions outrun the ring cap and the consume census stops rising).

    Dual property asserted:
      (1) FORWARD CORRECT (Phase 1): N distinct real-skill state-change cycles, driven
          through the consume-INDEPENDENT `advance_forward_cycle` (the Phase-1 wired
          path), yield `forward_cycles == N` — NOT frozen at a plateau. This is RED
          against pre-Part-1 code (where the real-skill path advanced only via the
          consume-gated `advance_run_counters`, which freezes once the ring-capped
          census plateaus/drops past entry 64).
      (2) WATERMARK NOT STRANDED (Phase 2): the consume-gated `advance_run_counters`
          gate, exercised across the same ring-cap crossing, never permanently strands
          (the re-arm-on-drop clamp).
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            now = _time.time()
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=200, now=now,
            )

            n_real_cycles = 40          # 80 cumulative emissions — well past the 64 cap
            steps = ["spec", "phases", "plan", "execute-plan", "mcp-test"]
            t = 0  # monotone emission clock offset

            for i in range(n_real_cycles):
                # --- meta dispatch interleaved before each real cycle ---
                # (recovery / hardening etc. go through advance_meta_cycle; each also
                #  registers + consumes a registry entry — driving the ring cap.)
                meta_entry = lazy_core.register_emission(
                    f"meta dispatch {i}", "recovery", now=now + t
                )
                lazy_core._monolith.consume_nonce(meta_entry["nonce"])
                t += 1
                lazy_core.advance_meta_cycle()

                # --- a real-skill dispatch consume (drives the registry past the cap) ---
                real_entry = lazy_core.register_emission(
                    f"real dispatch {i}", "cycle", now=now + t
                )
                lazy_core._monolith.consume_nonce(real_entry["nonce"])
                t += 1

                # --- the Phase-1 forward authority: advance on a DISTINCT state tuple ---
                # Each real cycle carries a distinct [feature_id, current_step, sub_skill]
                # so advance_forward_cycle advances exactly once per real cycle,
                # INDEPENDENT of the (now plateaued/dropping) consume census.
                state = {
                    "feature_id": f"feat-{i}",
                    "current_step": steps[i % len(steps)],
                    "sub_skill": "/execute-plan",
                }
                # Production wiring (Part 1): the real-skill probe path advances
                # forward via advance_forward_cycle ALONE — advance_run_counters was
                # REPLACED, not run alongside, so there is no double-count.
                lazy_core.advance_forward_cycle(state)

            marker = lazy_core.read_run_marker()

            # Sanity: the registry actually crossed the ring cap (≥65 cumulative
            # emissions; the live registry is capped at 64).
            registry = lazy_core._load_registry()
            assert len(registry.get("entries", [])) == lazy_core._REGISTRY_RING_CAP, (
                f"the run must have crossed the ring cap — registry should hold exactly "
                f"{lazy_core._REGISTRY_RING_CAP} entries, got "
                f"{len(registry.get('entries', []))}"
            )
            assert 2 * n_real_cycles > lazy_core._REGISTRY_RING_CAP, (
                "test design: cumulative emissions must exceed the ring cap"
            )

            # (1) FORWARD CORRECT — once per real-skill state change, NOT frozen.
            assert marker["forward_cycles"] == n_real_cycles, (
                f"forward_cycles must advance once per real-skill state change across "
                f"the ring-cap crossing (expected {n_real_cycles}); got "
                f"{marker['forward_cycles']!r}. A value frozen below {n_real_cycles} is "
                f"the SPEC's 'stuck at 16 / frozen at 50' signature — the bug."
            )

            # (2a) Every interleaved meta dispatch advanced meta_cycles (advance_meta_cycle
            #      is not consume-gated, so it always advances).
            assert marker["meta_cycles"] == n_real_cycles, (
                f"each interleaved meta dispatch must advance meta_cycles (expected "
                f"{n_real_cycles}), got {marker['meta_cycles']!r}"
            )

            # (2b) WATERMARK NOT STRANDED (Phase 2) — across the crossing, the meta +1
            #      over-absorb ratcheted last_advance_consume_count, and ring-cap eviction
            #      dropped the live census below it (Contributor A + B together). Pre-clamp
            #      the consume-gated advance_run_counters would now be PERMANENTLY wedged.
            #      Prove it re-arms: a fresh legitimate consume + an advance_run_counters
            #      call (a still-extant watermark consumer) must advance forward_cycles.
            fc_before = marker["forward_cycles"]
            live_census = lazy_core.consumed_emission_count()
            persisted_watermark = int(marker.get("last_advance_consume_count", 0))
            assert live_census < persisted_watermark, (
                f"test design: after the meta +1 ratchet + ring-cap eviction the live "
                f"census ({live_census}) must sit BELOW the persisted watermark "
                f"({persisted_watermark}) — the exact strand condition this asserts no "
                f"longer freezes"
            )
            post_entry = lazy_core.register_emission("post-crossing dispatch", "cycle")
            lazy_core._monolith.consume_nonce(post_entry["nonce"])
            m_post = lazy_core.advance_run_counters(
                {"feature_id": "feat-post", "current_step": "execute-plan",
                 "sub_skill": "/execute-plan"}
            )
            assert m_post["forward_cycles"] == fc_before + 1, (
                f"the consume-gated watermark gate must NOT be permanently stranded by "
                f"the meta +1 ratchet + ring-cap eviction — a fresh consume after the "
                f"crossing must still advance (expected {fc_before + 1}), got "
                f"{m_post['forward_cycles']!r}. Pre-Phase-2 this wedged forever."
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Test 12: corrupt marker on disk → read_run_marker returns None + file deleted
# ---------------------------------------------------------------------------

def test_corrupt_marker_returns_none_and_deletes():
    """A corrupt (non-JSON) marker file on disk → read_run_marker returns None
    AND the corrupt file is deleted so subsequent calls start clean.

    This test exercises the 'crashed write protection' path documented in
    read_run_marker's docstring.
    """
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            # Write garbage (not valid JSON) directly into the marker file.
            state_dir = lazy_core.claude_state_dir()
            marker_path = state_dir / "lazy-run-marker.json"
            marker_path.write_text("{ this is not valid JSON !!!", encoding="utf-8")
            assert marker_path.exists(), "pre-condition: corrupt marker must exist before read"

            now = _time.time()
            result = lazy_core.read_run_marker(now=now)

            assert result is None, (
                f"read_run_marker must return None for a corrupt marker file, got {result!r}"
            )
            assert not marker_path.exists(), (
                "corrupt marker file must be deleted by read_run_marker "
                "(delete-on-corrupt protection)"
            )
        finally:
            _clear_state_dir()




def test_host_present_capabilities_cache_per_run_and_reprobe():
    """Cache writes once per run marker; a NEW run marker re-probes."""
    _guard()
    counter = {"n": 0}

    def gpu_probe():
        counter["n"] += 1
        return True

    probes = {"gpu": gpu_probe}
    import time as _time

    base = _time.time()
    with tempfile.TemporaryDirectory() as td:
        os.environ["LAZY_STATE_DIR"] = td
        try:
            # Run marker #1 (fresh started_at so read_run_marker keeps it) —
            # first call probes + caches, second call hits cache.
            lazy_core.write_run_marker("feature", False, td, max_cycles=10, now=base)
            first = lazy_core.host_present_capabilities(probes=probes, cache=True)
            assert first == {"gpu"}
            assert counter["n"] == 1
            lazy_core.host_present_capabilities(probes=probes, cache=True)
            assert counter["n"] == 1, "second call within a run must hit the cache"
            # New run marker (distinct started_at, still fresh) — must re-probe.
            lazy_core.delete_run_marker()
            lazy_core.write_run_marker("feature", False, td, max_cycles=10, now=base + 5)
            lazy_core.host_present_capabilities(probes=probes, cache=True)
            assert counter["n"] == 2, "a new run marker must re-probe"
        finally:
            os.environ.pop("LAZY_STATE_DIR", None)




def test_write_deferred_requires_host_emits_valid_sentinel():
    """The writer emits a frontmatter-valid DEFERRED_REQUIRES_HOST.md carrying
    the (sorted) missing_capabilities + kind: deferred-requires-host."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "DEFERRED_REQUIRES_HOST.md"
        lazy_core.write_deferred_requires_host(
            path,
            feature_id="feat-x",
            missing_capabilities=["zimtohrli-toolchain", "gpu"],
            deferred_by="lazy-batch",
            date="2026-06-20",
        )
        meta = lazy_core.parse_sentinel(path)
    assert meta is not None
    assert meta.get("kind") == "deferred-requires-host"
    assert meta.get("feature_id") == "feat-x"
    # Sorted (deterministic on-disk shape).
    assert meta.get("missing_capabilities") == ["gpu", "zimtohrli-toolchain"]
    assert meta.get("deferred_by") == "lazy-batch"
    assert meta.get("date") == "2026-06-20"




def test_f2a_resolve_emission_missing_nonce_returns_none():
    """F2a: resolve_emission_by_nonce returns None for a nonce that does not
    exist in the registry at all (unknown/garbage nonce).

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
            bogus_nonce = "deadbeef" * 4  # 32-char hex, not in registry

            resolved = lazy_core.resolve_emission_by_nonce(bogus_nonce)
            assert resolved is None, (
                "resolve_emission_by_nonce must return None for a missing nonce; "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()




# ---------------------------------------------------------------------------
# Phase 1 (lazy-cycle-containment) — Self-edit reload discipline (C8).
#
# self_edit_mode(repo_root): True iff ~/.claude/{skills,scripts,hooks} ALL
# resolve (after symlink resolution) UNDER the run's git toplevel — i.e. the
# run is editing the harness it executes from. Semantically-correct (robust to
# the repo cloned elsewhere); NOT a cwd-basename match.
#
# GOVERNING_FILE_SET: the orchestrator's in-context governing-prose files that
# must be re-Read on self-edit (they do NOT auto-refresh from a fresh
# subprocess / disk read). The auto-refresh surfaces (lazy_core.py,
# cycle-base-prompt.md, hook .sh bodies, downstream skill prose) are NOT in it.
# ---------------------------------------------------------------------------


def _restore_env(key: str, prev: "str | None") -> None:
    """Restore an environment variable to its prior value (or remove it)."""
    if prev is None:
        _os.environ.pop(key, None)
    else:
        _os.environ[key] = prev




def _symlinks_supported(td: str) -> bool:
    """Best-effort probe: can this host create a directory symlink in `td`?

    On Windows, symlink creation needs Developer Mode or elevation; when it is
    unavailable we skip the symlink-dependent self-edit tests rather than fail.
    """
    target = Path(td) / "_symlink_probe_target"
    link = Path(td) / "_symlink_probe_link"
    target.mkdir()
    try:
        _os.symlink(str(target), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        return False
    finally:
        try:
            if link.is_symlink():
                link.unlink()
        except OSError:
            pass
    return True




def _make_self_edit_fixture(td: str, *, inside: bool) -> tuple:
    """Build a fake git toplevel + a fake HOME whose ~/.claude/{skills,scripts,
    hooks} are symlinks.

    inside=True  → the three symlinks resolve UNDER the git toplevel (self-edit).
    inside=False → they resolve into a sibling dir OUTSIDE the toplevel.

    Returns (toplevel: Path, fake_home: Path).
    """
    toplevel = Path(td) / "toplevel"
    toplevel.mkdir()
    # Make it a real git repo so `git rev-parse --show-toplevel` succeeds.
    subprocess.run(["git", "init", "-q", str(toplevel)], check=True,
                   capture_output=True)

    fake_home = Path(td) / "home"
    (fake_home / ".claude").mkdir(parents=True)

    if inside:
        # Mirror the live layout: repo holds user/{skills,scripts,hooks}; the
        # ~/.claude/* names are symlinks pointing INTO the toplevel.
        src_base = toplevel / "user"
    else:
        src_base = Path(td) / "elsewhere"
    for name in ("skills", "scripts", "hooks"):
        real = src_base / name
        real.mkdir(parents=True)
        _os.symlink(str(real), str(fake_home / ".claude" / name),
                   target_is_directory=True)
    return toplevel, fake_home




def test_self_edit_mode_symbol_present():
    """self_edit_mode + GOVERNING_FILE_SET are exported by lazy_core."""
    _guard()
    assert hasattr(lazy_core, "self_edit_mode"), "lazy_core.self_edit_mode missing"
    assert hasattr(lazy_core, "GOVERNING_FILE_SET"), (
        "lazy_core.GOVERNING_FILE_SET missing"
    )




def test_self_edit_mode_true_inside_toplevel(monkeypatch=None):
    """All three ~/.claude/* symlinks resolve UNDER git toplevel → True."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        if not _symlinks_supported(td):
            return  # host cannot make symlinks — skip (treated as pass)
        toplevel, fake_home = _make_self_edit_fixture(td, inside=True)
        _orig_home = _os.environ.get("HOME")
        _orig_userprofile = _os.environ.get("USERPROFILE")
        _os.environ["HOME"] = str(fake_home)
        _os.environ["USERPROFILE"] = str(fake_home)
        try:
            assert lazy_core.self_edit_mode(toplevel) is True
        finally:
            _restore_env("HOME", _orig_home)
            _restore_env("USERPROFILE", _orig_userprofile)




def test_self_edit_mode_false_outside_toplevel():
    """Symlinks resolve OUTSIDE the git toplevel → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        if not _symlinks_supported(td):
            return
        toplevel, fake_home = _make_self_edit_fixture(td, inside=False)
        _orig_home = _os.environ.get("HOME")
        _orig_userprofile = _os.environ.get("USERPROFILE")
        _os.environ["HOME"] = str(fake_home)
        _os.environ["USERPROFILE"] = str(fake_home)
        try:
            assert lazy_core.self_edit_mode(toplevel) is False
        finally:
            _restore_env("HOME", _orig_home)
            _restore_env("USERPROFILE", _orig_userprofile)




def test_self_edit_mode_false_normal_repo_no_symlinks():
    """A plain git repo, ~/.claude/* are real dirs (not symlinks into it) → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        toplevel = Path(td) / "toplevel"
        toplevel.mkdir()
        subprocess.run(["git", "init", "-q", str(toplevel)], check=True,
                       capture_output=True)
        fake_home = Path(td) / "home"
        for name in ("skills", "scripts", "hooks"):
            (fake_home / ".claude" / name).mkdir(parents=True)
        _orig_home = _os.environ.get("HOME")
        _orig_userprofile = _os.environ.get("USERPROFILE")
        _os.environ["HOME"] = str(fake_home)
        _os.environ["USERPROFILE"] = str(fake_home)
        try:
            assert lazy_core.self_edit_mode(toplevel) is False
        finally:
            _restore_env("HOME", _orig_home)
            _restore_env("USERPROFILE", _orig_userprofile)




def test_self_edit_mode_false_not_a_git_repo():
    """repo_root is not a git repo (rev-parse --show-toplevel fails) → False, no raise."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        not_a_repo = Path(td) / "plain"
        not_a_repo.mkdir()
        fake_home = Path(td) / "home"
        for name in ("skills", "scripts", "hooks"):
            (fake_home / ".claude" / name).mkdir(parents=True)
        _orig_home = _os.environ.get("HOME")
        _orig_userprofile = _os.environ.get("USERPROFILE")
        _os.environ["HOME"] = str(fake_home)
        _os.environ["USERPROFILE"] = str(fake_home)
        try:
            assert lazy_core.self_edit_mode(not_a_repo) is False
        finally:
            _restore_env("HOME", _orig_home)
            _restore_env("USERPROFILE", _orig_userprofile)




def test_self_edit_mode_false_one_missing_path():
    """If only some of the three ~/.claude/* paths resolve under toplevel → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        if not _symlinks_supported(td):
            return
        toplevel, fake_home = _make_self_edit_fixture(td, inside=True)
        # Remove one of the three symlinks so the predicate cannot be all-true.
        (fake_home / ".claude" / "hooks").unlink()
        _orig_home = _os.environ.get("HOME")
        _orig_userprofile = _os.environ.get("USERPROFILE")
        _os.environ["HOME"] = str(fake_home)
        _os.environ["USERPROFILE"] = str(fake_home)
        try:
            assert lazy_core.self_edit_mode(toplevel) is False
        finally:
            _restore_env("HOME", _orig_home)
            _restore_env("USERPROFILE", _orig_userprofile)




def test_governing_file_set_excludes_auto_refresh_surfaces():
    """The governing set EXCLUDES auto-refreshing surfaces (no false 'reload')."""
    _guard()
    gset = lazy_core.GOVERNING_FILE_SET
    excludes = [
        "user/scripts/lazy_core.py",
        "user/scripts/lazy-state.py",
        "user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md",
        "user/hooks/lazy-cycle-containment.sh",
    ]
    for rel in excludes:
        assert rel not in gset, (
            f"auto-refresh surface {rel} must NOT be in the governing set"
        )




def test_governing_files_touched_intersects_commit():
    """governing_files_touched(repo_root) returns the last commit's governing hits."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email",
                        "t@t.local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "T"],
                       check=True, capture_output=True)
        # Initial commit (a non-governing file).
        (root / "README.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                       check=True, capture_output=True)
        # Second commit touches a governing file + a non-governing file.
        gov = root / "user" / "skills" / "lazy-batch" / "SKILL.md"
        gov.parent.mkdir(parents=True)
        gov.write_text("edit\n", encoding="utf-8")
        (root / "user" / "scripts").mkdir(parents=True)
        (root / "user" / "scripts" / "lazy_core.py").write_text("y\n",
                                                                 encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "edit"],
                       check=True, capture_output=True)
        touched = lazy_core.governing_files_touched(root)
        assert "user/skills/lazy-batch/SKILL.md" in touched
        assert "user/scripts/lazy_core.py" not in touched




def test_lazy_batch_skill_carries_reload_discipline_prose():
    """WU-2: lazy-batch/SKILL.md documents the governing-file reload discipline."""
    _guard()
    skill = (_SCRIPTS_DIR.parent / "skills" / "lazy-batch" / "SKILL.md")
    text = skill.read_text(encoding="utf-8")
    assert "self_edit_mode" in text, "reload discipline must reference self_edit_mode"
    assert "governing-file" in text.lower(), "must name the governing-file set"
    # New-hook-registration restart surfacing (T6).
    assert "settings.json hook wiring changed" in text, (
        "must carry the new-hook-registration ⚠ restart surfacing"
    )
    # Auto-refresh boundary documented no-ops.
    assert "cycle-base-prompt.md" in text, (
        "must document cycle-base-prompt.md as an auto-refresh no-op"
    )




# ---------------------------------------------------------------------------
# unified-pipeline-orchestrator Phase 1 — merged work-list view
# ---------------------------------------------------------------------------
#
# WU-1: merged-view helper + ordering comparator.
# WU-2: ordering-field source normalization (feature `tier` vs bug `severity`).
# WU-3: fixtures covering both-populated / bug-breaks-tie / only-features /
#       only-bugs / both-empty, plus the live --next-merged CLI over a two-queue
#       temp-dir fixture.
#
# These characterize lazy_core.merged_priority / merged_worklist / next_merged
# directly (the helper symbols did not exist before this WU — the RED state is
# an AttributeError on lazy_core, which _guard()/the assertions encode as the
# ordering contract, not mere absence).


def test_merged_symbols_present():
    """The merged-view public surface exists in lazy_core."""
    _guard()
    for sym in ("merged_priority", "merged_worklist", "next_merged",
                "MERGED_PRIORITY_DEFAULT"):
        assert hasattr(lazy_core, sym), f"lazy_core.{sym} must exist"




def test_next_merged_cli_over_two_queue_fixture():
    """WU-3 live integration: `lazy-state.py --next-merged --repo-root <fixture>`
    over a temp dir with one tier-1 feature and one P0 bug prints the bug as the
    head (bugs break ties / higher priority). Exercises the real loaders +
    importlib bug-queue load end-to-end."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        feats_dir = root / "docs" / "features"
        bugs_dir = root / "docs" / "bugs"
        feats_dir.mkdir(parents=True)
        bugs_dir.mkdir(parents=True)
        # Feature queue: one tier-1 feature.
        (feats_dir / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": "feat-x", "name": "Feature X", "spec_dir": "feat-x", "tier": 1}
            ]}), encoding="utf-8"
        )
        # The bug loader resolves spec_dir to an on-disk dir, so seed it.
        bug_x = bugs_dir / "bug-x"
        bug_x.mkdir()
        (bug_x / "SPEC.md").write_text(
            "# Bug X\n\n**Severity:** P0\n**Status:** Concluded\n", encoding="utf-8"
        )
        (bugs_dir / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": "bug-x", "name": "Bug X", "spec_dir": "bug-x", "severity": "P0"}
            ]}), encoding="utf-8"
        )
        # Also seed a feature spec dir so load_queue's downstream is sane (the
        # merged head only needs ordering, but keep the fixture realistic).
        (feats_dir / "feat-x").mkdir()

        cp = subprocess.run(
            [sys.executable, str(lazy_state), "--next-merged",
             "--repo-root", str(root)],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0, (cp.returncode, cp.stdout, cp.stderr)
        head = json.loads(cp.stdout.strip())
        assert head is not None, "head must not be null with both queues populated"
        assert head["type"] == "bug", head   # P0 bug (rank 0) beats tier-1 feature
        assert head["item_id"] == "bug-x", head
        assert "repo_root" in head and head["repo_root"], head




def test_next_merged_cli_only_features_matches_single_head():
    """WU-3: --next-merged with ONLY features queued returns the same feature
    lazy-state's single-current head would — single-type behavior unchanged."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        feats_dir = root / "docs" / "features"
        feats_dir.mkdir(parents=True)
        (root / "docs" / "bugs").mkdir(parents=True)  # empty bug queue dir
        (feats_dir / "queue.json").write_text(
            json.dumps({"queue": [
                {"id": "feat-only", "name": "Only", "spec_dir": "feat-only", "tier": 1}
            ]}), encoding="utf-8"
        )
        (feats_dir / "feat-only").mkdir()
        cp = subprocess.run(
            [sys.executable, str(lazy_state), "--next-merged",
             "--repo-root", str(root)],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0, (cp.returncode, cp.stdout, cp.stderr)
        head = json.loads(cp.stdout.strip())
        assert head["type"] == "feature" and head["item_id"] == "feat-only", head




def test_next_merged_cli_both_empty_prints_null():
    """WU-3: --next-merged over empty queues prints JSON null (exit 0)."""
    _guard()
    lazy_state = _SCRIPTS_DIR / "lazy-state.py"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs" / "features").mkdir(parents=True)
        (root / "docs" / "bugs").mkdir(parents=True)
        cp = subprocess.run(
            [sys.executable, str(lazy_state), "--next-merged",
             "--repo-root", str(root)],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0, (cp.returncode, cp.stdout, cp.stderr)
        assert json.loads(cp.stdout.strip()) is None, cp.stdout




def test_pin_bug_severity_updates_existing_entry():
    """--pin on an ALREADY-queued bug overwrites its pin fields in place
    (re-pinning is not additive — the latest call is authoritative)."""
    _guard()
    import datetime
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bug_dir = root / "docs" / "bugs" / "existing-bug"
        bug_dir.mkdir(parents=True)
        (bug_dir / "SPEC.md").write_text(
            "# Existing Bug\n\n**Status:** Concluded\n**Severity:** P1\n",
            encoding="utf-8",
        )
        queue_path = root / "docs" / "bugs" / "queue.json"
        queue_path.write_text(json.dumps({
            "queue": [{"id": "existing-bug", "name": "Existing Bug",
                       "spec_dir": "existing-bug", "severity": "P1"}]
        }), encoding="utf-8")
        result = bs.pin_bug_severity(
            root, "existing-bug", until="2026-09-01", reason="re-pin",
            today=datetime.date(2026, 7, 13),
        )
        assert result["status"] == "updated"
        queue = json.loads(queue_path.read_text())
        assert len(queue["queue"]) == 1
        entry = queue["queue"][0]
        assert entry["severity"] is None
        assert entry["pinned_until"] == "2026-09-01"
        assert entry["pin_reason"] == "re-pin"




def test_pin_bug_severity_malformed_until_refuses():
    """A malformed --until date refuses (_die, exit 2 semantics) with ZERO
    mutation — the queue.json is untouched."""
    _guard()
    import pytest as _pytest
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bug_dir = root / "docs" / "bugs" / "some-bug"
        bug_dir.mkdir(parents=True)
        (bug_dir / "SPEC.md").write_text("# Some Bug\n", encoding="utf-8")
        with _pytest.raises(SystemExit):
            bs.pin_bug_severity(root, "some-bug", until="not-a-date")
        assert not (root / "docs" / "bugs" / "queue.json").exists()




def test_pin_bug_severity_unknown_bug_refuses():
    """--pin against a bug id with no on-disk dir refuses (_die) rather than
    fabricating a queue entry for a bug that doesn't exist."""
    _guard()
    import pytest as _pytest
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs" / "bugs").mkdir(parents=True)
        with _pytest.raises(SystemExit):
            bs.pin_bug_severity(root, "ghost-bug")




def test_load_bug_queue_populates_aging_fields():
    """load_bug_queue populates discovered/spec_severity/pinned_at/
    pinned_until on BOTH queued and on-disk (auto-discovered) bug entries, so
    merged_priority's fallback-past-expired-pin branch has what it needs."""
    _guard()
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        queued_dir = root / "docs" / "bugs" / "queued-bug"
        queued_dir.mkdir(parents=True)
        (queued_dir / "SPEC.md").write_text(
            "# Queued Bug\n\n**Status:** Concluded\n**Severity:** P2\n"
            "**Discovered:** 2026-06-22\n", encoding="utf-8",
        )
        (root / "docs" / "bugs" / "queue.json").write_text(json.dumps({
            "queue": [{"id": "queued-bug", "name": "Queued Bug",
                       "spec_dir": "queued-bug", "severity": None,
                       "pinned_at": "2026-07-01", "pinned_until": "2026-07-20"}]
        }), encoding="utf-8")
        ondisk_dir = root / "docs" / "bugs" / "ondisk-bug"
        ondisk_dir.mkdir(parents=True)
        (ondisk_dir / "SPEC.md").write_text(
            "# Ondisk Bug\n\n**Status:** Concluded\n**Severity:** P1\n"
            "**Discovered:** 2026-05-01\n", encoding="utf-8",
        )
        queue = bs.load_bug_queue(root)
        by_id = {e["id"]: e for e in queue}
        assert by_id["queued-bug"]["discovered"] == "2026-06-22"
        assert by_id["queued-bug"]["spec_severity"] == "P2"
        assert by_id["queued-bug"]["pinned_at"] == "2026-07-01"
        assert by_id["queued-bug"]["pinned_until"] == "2026-07-20"
        assert by_id["ondisk-bug"]["discovered"] == "2026-05-01"
        assert by_id["ondisk-bug"]["spec_severity"] == "P1"
        assert by_id["ondisk-bug"]["pinned_at"] is None




def test_find_open_bug_dirs_age_escalates_sort_order():
    """_find_open_bug_dirs's sort key mirrors merged_priority's age
    escalation — an old P2 bug sorts AHEAD of a fresh P1 bug once escalated
    past it (bug-side mirror of the merged view)."""
    _guard()
    import datetime
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bugs_dir = root / "docs" / "bugs"
        old_p2 = bugs_dir / "old-p2-bug"
        old_p2.mkdir(parents=True)
        (old_p2 / "SPEC.md").write_text(
            "# Old P2 Bug\n\n**Status:** Concluded\n**Severity:** P2\n"
            "**Discovered:** 2026-05-01\n", encoding="utf-8",
        )
        fresh_p1 = bugs_dir / "fresh-p1-bug"
        fresh_p1.mkdir(parents=True)
        (fresh_p1 / "SPEC.md").write_text(
            "# Fresh P1 Bug\n\n**Status:** Concluded\n**Severity:** P1\n"
            "**Discovered:** 2026-07-12\n", encoding="utf-8",
        )
        today = datetime.date(2026, 7, 13)
        dirs = bs._find_open_bug_dirs(bugs_dir, set(), today=today)
        names = [d.name for d in dirs]
        # old-p2-bug: rank 2, ~73 days old -> 10 notches -> floor 1 (beats
        # fresh-p1-bug's unescalated rank 1? No -- P1 is ALREADY at the floor
        # (rank 1 <= _AGE_ESCALATION_FLOOR_RANK), so it never escalates past
        # rank 1 either. Both land at effective rank 1; Discovered date is
        # the tiebreaker (ascending) -> old-p2-bug (older) sorts first.
        assert names == ["old-p2-bug", "fresh-p1-bug"], names




def test_planner_resolution_internal_repos_derives_from_script_location():
    """The internal repos dir must be derived from lint-skills.py's own location
    (<claude-config>/repos), so the fix is machine-independent."""
    mod = _lint_skills_module()
    from pathlib import Path as _P
    internal = _P(mod.__file__).resolve().parents[2] / "repos"
    assert (internal / "cognito-forms" / ".claude" / "skills" /
            "write-plan-cognito" / "SKILL.md").exists(), (
        f"expected canonical write-plan-cognito under {internal}; the D1 rename "
        "must be present in the git-tracked internal repos/ tree"
    )




def test_cycle_marker_symbols_present():
    """Phase 2 public symbols exist on lazy_core."""
    _guard()
    for name in ("read_cycle_marker", "write_cycle_marker", "clear_cycle_marker"):
        assert hasattr(lazy_core, name), f"Phase 2 missing {name}"




def test_cycle_end_friction_check_no_marker_is_noop(tmp_path):
    """WU-4: --cycle-end with no marker present is a safe no-op — None, no crash,
    no ledger entry."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            assert lazy_core.cycle_end_friction_check(repo_root=Path(td)) is None
            assert lazy_core.pending_hardening() == 0
        finally:
            _clear_state_dir()




def test_efficacy_breadcrumb_run_scoped_stale_does_not_satisfy():
    """RUN-SCOPING: a breadcrumb whose run_started_at differs from the LIVE
    marker's started_at (a stale breadcrumb left by a crashed prior run) does NOT
    satisfy the gate — efficacy_breadcrumb_present returns False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=td, max_cycles=5,
            )
            # Hand-write a breadcrumb from a DIFFERENT (prior) run identity.
            crumb = Path(td) / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            crumb.write_text(
                json.dumps({"run_started_at": "1999-01-01T00:00:00Z", "ts": 1.0}),
                encoding="utf-8",
            )
            assert lazy_core.efficacy_breadcrumb_present() is False, (
                "a prior-run breadcrumb must not satisfy this run's gate"
            )
        finally:
            _clear_state_dir()




def test_refuse_guard_symbol_present():
    """refuse_if_cycle_active exists on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "refuse_if_cycle_active"), "Phase 3 missing refuse_if_cycle_active"




def test_refuse_guard_op_set_matches_spec():
    """The refused-op set is exactly the C3 set (kept in lockstep with the C2
    hook deny-set — Phase 4)."""
    _guard()
    assert set(lazy_core.CYCLE_REFUSED_OPS) == set(_GUARDED_OPS), (
        f"refused-op set drift: {sorted(lazy_core.CYCLE_REFUSED_OPS)}"
    )




def test_run_start_clobber_symbol_present():
    """refuse_run_start_clobber exists on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "refuse_run_start_clobber"), "D-B missing refuse_run_start_clobber"




def test_apply_pseudo_direct_call_allowed_with_orchestrator_env_under_marker():
    """GAP-1 orchestrator immunity: the SAME direct ``apply_pseudo`` call under an
    active cycle marker but WITH ``LAZY_ORCHESTRATOR=1`` set (the real orchestrator
    context, which the CLI wrappers export) must NOT be refused — the internal guard
    is transparent to the orchestrator, so completion proceeds and COMPLETED.md is
    written. Proves the backstop discriminates the rogue subagent from the
    orchestrator on the same LAZY_ORCHESTRATOR signal every other guarded op uses.
    """
    _guard()
    _clear_cycle_env()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # Fully coherent PHASES: one phase, all boxes checked, Status Complete —
        # so completion sails past the coherence gate once the containment guard
        # allows the call.
        _write_phases_md(
            spec_dir,
            "## Phase 1 — Foundations\n\n**Status:** Complete\n\n- [x] Build the thing\n",
        )
        os.environ["LAZY_ORCHESTRATOR"] = "1"
        try:
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            result = lazy_core.apply_pseudo(
                Path(td), "__mark_complete__", spec_dir, date="2026-07-03"
            )
            assert result["ok"] is True, (
                f"orchestrator-context completion must succeed, got {result!r}"
            )
            assert result["refused"] is None, (
                f"orchestrator call must NOT be refused, got {result['refused']!r}"
            )
            assert (spec_dir / "COMPLETED.md").exists(), (
                "COMPLETED.md must be written for the orchestrator-context completion"
            )
        finally:
            _clear_cycle_env()
            _clear_state_dir()




def test_marker_mutation_guard_symbol_present():
    """refuse_cycle_marker_mutation_if_subagent exists on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "refuse_cycle_marker_mutation_if_subagent"), (
        "Phase 2 missing refuse_cycle_marker_mutation_if_subagent"
    )


def test_no_orphaned_test_functions():
    """WU-5(a) + WU-2 split generalization: the dead-coverage guard PASSES on
    every sibling test_*.py in this split package — every top-level
    ``def test_*`` in EACH file is present in THAT file's own ``_TESTS``. If a
    future edit adds a ``def test_*`` to any split file but forgets to
    register it, this guard FAILS naming the offending file + orphan (the
    Round-24 dead-coverage class is now mechanically impossible to land
    silently, across the whole split package, not just one module).

    Self-checking: this function is itself a ``def test_*`` registered in its
    own file's ``_TESTS``, so it is collected and run by the same harness it
    guards.
    """
    _guard()
    all_orphans: list[str] = []
    for sibling in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        module_source = sibling.read_text(encoding="utf-8")
        registered_names = _collect_registered_test_names(module_source)
        orphans = _collect_orphaned_test_names(module_source, registered_names)
        if orphans:
            all_orphans.append(f"{sibling.name}: {orphans}")
    assert all_orphans == [], (
        "dead-coverage guard: the following test_* function(s) are defined but "
        f"NOT registered in their file's _TESTS (they never execute): "
        f"{all_orphans}. Append each to its file's _TESTS list."
    )




def test_advance_run_counters_increments_per_feature():
    """P1 RED: the consume-oracle trigger (advance_run_counters) ALSO increments
    the per-feature counter on a forward dispatch (both triggers carry it)."""
    _guard()
    import time as _time
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/tmp/r",
                max_cycles=20, now=_time.time(),
            )
            # Register one consumed dispatch so the consume oracle advances.
            _entry = lazy_core.register_emission("pf", "cycle")
            lazy_core._monolith.consume_nonce(_entry["nonce"])
            m = lazy_core.advance_run_counters({
                "sub_skill": "/execute-plan", "feature_id": "feat-C",
                "current_step": "execute-plan",
            })
            assert m["forward_cycles"] == 1, m
            assert m["per_feature_forward_cycles"].get("feat-C") == 1, (
                f"advance_run_counters must also carry the per-feature increment, "
                f"got {m['per_feature_forward_cycles']!r}"
            )
        finally:
            _clear_state_dir()




def test_record_resolution_signal_marker_gated():
    """WU-3: record_resolution_signal is marker-gated — returns None and writes
    nothing when no run marker is present (an ordinary cycle never leaves the
    signal asserted)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))  # empty — no marker
        try:
            result = lazy_core.record_resolution_signal(
                {"feature_id": "f", "current_step": "s"}
            )
            assert result is None, (
                f"record_resolution_signal must return None when no marker present, "
                f"got {result!r}"
            )
            assert not (Path(td) / lazy_core._MARKER_FILENAME).exists(), (
                "no marker → no marker file created as a side effect"
            )
        finally:
            _clear_state_dir()




def test_load_bug_queue_for_merged_no_breadcrumb_on_clean_load():
    """WU-3 negative: a clean load (no exception) emits NO breadcrumb — the
    breadcrumb is for genuine failures only, not the expected early-outs."""
    _guard()
    ls = _load_lazy_state_module()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # No docs/bugs/queue.json → load_bug_queue returns its own result cleanly
        # (an on-disk-fallback walk over an empty tree → []). No exception, so no
        # breadcrumb.
        (root / "docs" / "bugs").mkdir(parents=True)
        lazy_core.clear_diagnostics()
        result = ls._load_bug_queue_for_merged(root)
        assert isinstance(result, list), result
        failure_crumbs = [d for d in lazy_core._DIAGNOSTICS
                          if "bug-side load failed" in d
                          or "merged-view bug-side load" in d]
        assert not failure_crumbs, (
            f"a clean load must not emit a failure breadcrumb; got {failure_crumbs!r}"
        )




def test_mark_complete_validated_verif_only_ticks_and_mints():
    """Validated feature, only verification rows unchecked → __mark_complete__
    mints COMPLETED.md, ticks the rows, records auto_ticked_rows in the receipt
    AND the JSON result, NO refusal, ok True.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _cc_build_validated_feature(
            repo_root, phases_body=_CC_E2E_PHASES_VERIF_ONLY
        )
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="cc-e2e", date="2026-06-19",
        )
        assert result["ok"] is True, result
        assert result["refused"] is None, result
        assert result["auto_ticked_rows"] == 2, result
        completed = spec_dir / "COMPLETED.md"
        assert completed.exists(), "COMPLETED.md not minted"
        parsed = lazy_core.parse_sentinel(completed)
        assert parsed.get("auto_ticked_rows") == 2, parsed
        phases_text = (spec_dir / "PHASES.md").read_text(encoding="utf-8")
        assert "- [x] pytest green" in phases_text, phases_text
        assert "- [x] parity clean" in phases_text, phases_text
        assert "auto-ticked: validated_commit=" in phases_text, phases_text




def test_verify_ledger_and_completion_agree_on_verif_only():
    """verify_ledger.deliverables_done (which exempts verification rows) and the
    completion gate AGREE on a verification-only feature: verify_ledger passes
    deliverables_done, and __mark_complete__ does NOT refuse.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _cc_build_validated_feature(
            repo_root, phases_body=_CC_E2E_PHASES_VERIF_ONLY
        )
        # verify_ledger over the whole feature (no --plan): deliverables_done
        # exempts the verification-only remainder → True. (spec_path is the
        # feature DIR, not SPEC.md — verify_ledger reads <dir>/PHASES.md.)
        ledger = lazy_core.verify_ledger(repo_root, spec_dir, None)
        assert ledger["checks"]["deliverables_done"] is True, ledger
        # Completion gate agrees: no refusal.
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="cc-e2e", date="2026-06-19",
        )
        assert result["ok"] is True, result




def test_mark_fixed_validated_verif_only_ticks_and_mints():
    """Mirror the __mark_complete__ auto-tick path for the bug pipeline's
    __mark_fixed__: FIXED.md minted, rows ticked, auto_ticked_rows recorded.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "bugs" / "cc-bug"
        spec_dir.mkdir(parents=True)
        _cc_write_validated(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        _cc_write_retro_done(spec_dir)
        (spec_dir / "PHASES.md").write_text(
            _CC_E2E_PHASES_VERIF_ONLY, encoding="utf-8"
        )
        _write_mcp_test_results(spec_dir, ["s1", "s2"])
        head = _cc_seed_and_commit(repo_root)
        _write_mcp_test_results(spec_dir, ["s1", "s2"], validated_commit=head)
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_fixed__", spec_dir,
            feature_id="cc-bug", date="2026-06-19",
        )
        assert result["ok"] is True, result
        assert result["auto_ticked_rows"] == 2, result
        fixed = spec_dir / "FIXED.md"
        assert fixed.exists(), "FIXED.md not minted"
        parsed = lazy_core.parse_sentinel(fixed)
        assert parsed.get("auto_ticked_rows") == 2, parsed




def test_reconcile_does_not_false_trip_cycle_end_friction():
    """Composition: a torn-build delta neutralized at --cycle-begin does NOT
    subsequently cause detect_cycle_bracket_friction to report unexpected-commits
    or cycle-bracket-break at --cycle-end. Asserted against the REAL detector.

    The reconciliation removes a stale lock + git-cleans an UNCOMMITTED staging
    delta — it makes NO commits and does NOT touch the run marker — so HEAD is
    unchanged and the run identity is intact. The detector therefore sees zero
    advanced commits and an unchanged run identity → no friction."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo = _make_git_tree(Path(td))
        lock = repo / ".git" / "index.lock"
        lock.write_text("", encoding="utf-8")
        os.utime(lock, (1_000.0, 1_000.0))
        staging = repo / "target" / "release_staging"
        staging.mkdir(parents=True)
        (staging / "torn.bin").write_text("partial", encoding="utf-8")

        head_before = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

        lazy_core.reconcile_cycle_begin_git_consistency(
            repo, boot_stamp=2_000_000_000.0, staging_dir=str(staging),
        )

        head_after = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        assert head_before == head_after, (
            "the reconciliation must NOT advance HEAD (it cleans uncommitted "
            "delta only) — otherwise it would false-trip unexpected-commits"
        )

        # Build a cycle marker as --cycle-begin would have snapshotted it: the
        # run identity present, begin_head_sha == HEAD. commits_since == 0.
        marker = {
            "kind": "real",
            "run_started_at": "2026-06-20T00:00:00Z",
            "begin_head_sha": head_after,
            "sub_skill": "execute-plan",
        }
        descriptor = lazy_core.detect_cycle_bracket_friction(
            marker,
            current_run_started_at="2026-06-20T00:00:00Z",  # unchanged run identity
            current_head_sha=head_after,
            sub_skill="execute-plan",
            commits_since=0,  # reconciliation committed nothing
        )
        assert descriptor is None, (
            "a reconciled torn-build delta must NOT false-trip the --cycle-end "
            f"friction detector; got {descriptor!r}"
        )




def test_reassert_owner_cli_cycle_refusal_lazy_state():
    """lazy-state.py --reassert-owner is refused (exit 3, zero side effects) for a
    cycle subagent and re-claims for the orchestrator."""
    _run_reassert_owner_cli("lazy-state.py", "feature")




def test_reassert_owner_cli_cycle_refusal_bug_state_parity():
    """bug-state.py --reassert-owner behaves identically (coupled pair)."""
    _run_reassert_owner_cli("bug-state.py", "bug")




def _run_reassert_owner_cli(script_name: str, pipeline: str) -> None:
    """--reassert-owner: cycle-subagent refused exit 3 / zero side effects; the
    orchestrator path re-claims a foreign-stamped slot."""
    _guard()
    script = _SCRIPTS_DIR / script_name
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "cli-state"
        state_dir.mkdir()
        repo_root = Path(td) / "repo"
        repo_root.mkdir()
        # Seed a live FOREIGN-stamped marker in-process.
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline=pipeline, cloud=False, repo_root=str(repo_root),
                session_id="FOREIGN", now=_t.time(),
            )
        finally:
            _clear_state_dir()
        marker_path = state_dir / "lazy-run-marker.json"

        base_env = dict(_os_env.environ)
        base_env["LAZY_STATE_DIR"] = str(state_dir)
        for k in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT"):
            base_env.pop(k, None)

        # (1) Cycle subagent → refused exit 3, marker UNCHANGED (zero side effects).
        sub_env = dict(base_env)
        sub_env["LAZY_CYCLE_SUBAGENT"] = "1"
        r = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root),
             "--reassert-owner", "--session-id", "OWNER"],
            capture_output=True, text=True, env=sub_env,
        )
        assert r.returncode == 3, (
            f"{script_name} --reassert-owner must refuse a cycle subagent with "
            f"exit 3, got {r.returncode}; stderr={r.stderr[:300]!r}"
        )
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "FOREIGN", (
            "a refused --reassert-owner must leave the marker UNCHANGED "
            "(zero side effects)"
        )

        # (2) Orchestrator → re-claims; verdict JSON reports the prior status.
        orch_env = dict(base_env)
        orch_env["LAZY_ORCHESTRATOR"] = "1"
        r = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root),
             "--reassert-owner", "--session-id", "OWNER"],
            capture_output=True, text=True, env=orch_env,
        )
        assert r.returncode == 0, (
            f"{script_name} --reassert-owner must succeed for the orchestrator, "
            f"got {r.returncode}; stderr={r.stderr[:300]!r}"
        )
        verdict = json.loads(r.stdout)
        assert verdict["reasserted"] is True, verdict
        assert verdict["prior_status"] == "foreign-stamped", verdict
        data = json.loads(marker_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "OWNER", (
            "the orchestrator re-claim must re-stamp the slot to OWNER"
        )

        # (3) --reassert-owner without --session-id dies (exit 2).
        r = subprocess.run(
            [sys.executable, str(script), "--repo-root", str(repo_root),
             "--reassert-owner"],
            capture_output=True, text=True, env=orch_env,
        )
        assert r.returncode == 2, (
            f"{script_name} --reassert-owner without --session-id must _die "
            f"(exit 2), got {r.returncode}"
        )




def test_telemetry_emit_nondestructive_on_stale_marker():
    """The emitter's marker gate must be NON-destructive: an age-stale marker
    gates the emit (False) but is NOT deleted (read_run_marker would delete it —
    the emitter must not, because refusal paths promise zero side effects)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            import time as _time
            now = _time.time()
            # Marker started >24h ago → age-stale.
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                now=now - (25 * 3600),
            )
            marker_path = Path(td) / lazy_core._MARKER_FILENAME
            assert marker_path.exists()
            ok = lazy_core.append_telemetry_event("run-start", now=now)
            assert ok is False, "age-stale marker must gate the emit"
            assert marker_path.exists(), (
                "the emitter must NOT delete a stale marker (non-destructive read)"
            )
            ledger = Path(td) / lazy_core._monolith._TELEMETRY_LEDGER_FILENAME
            assert not ledger.exists(), "gated emit must write nothing"
        finally:
            _clear_state_dir()




def test_mark_complete_receipt_carries_completed_commit():
    """In a git repo, the gated receipt records completed_commit == HEAD
    (write_completed_receipt supported the field; the call site now passes it)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        head = _prov_git_fixture_repo(repo_root)
        spec_dir = repo_root / "docs" / "features" / "feat-cc"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="feat-cc", date="2026-07-04",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        parsed = lazy_core.parse_sentinel(spec_dir / "COMPLETED.md")
        assert parsed is not None
        assert str(parsed.get("completed_commit") or "") == head, (
            f"receipt must anchor completed_commit to HEAD {head[:8]}, "
            f"got {parsed.get('completed_commit')!r}"
        )




def test_mark_complete_receipt_non_git_omits_completed_commit():
    """A non-git repo_root resolves no HEAD → the field is omitted (legacy
    byte-shape preserved), never a crash."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir, date="2026-07-04",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        parsed = lazy_core.parse_sentinel(spec_dir / "COMPLETED.md")
        assert parsed is not None
        assert "completed_commit" not in parsed, (
            f"non-git completion must omit completed_commit, got {parsed!r}"
        )




def test_write_provenance_no_locked_decisions_is_honest():
    """A SPEC with no Locked-Decision surface → decisions: [] + a body note
    (never fabricated ids)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _prov_spec_dir(
            repo_root, "feat-bare",
            spec_md="# Spec\n\n> Bare summary line.\n\n**Status:** In-progress\n")
        result = lazy_core.write_provenance(
            repo_root, spec_dir, "feat-bare", "feature", [], [],
            date="2026-07-04")
        assert result["ok"] is True, f"got {result}"
        meta = lazy_core.parse_sentinel(spec_dir / "IMPLEMENTED.md")
        assert meta.get("decisions") == [], f"expected [], got {meta.get('decisions')!r}"
        body = (spec_dir / "IMPLEMENTED.md").read_text(encoding="utf-8")
        assert "no Locked-Decision surface" in body




def test_mark_complete_emits_provenance_from_brackets():
    """The pipeline trigger: __mark_complete__ with recorded brackets emits the
    distillate (derivation: commit-brackets) + index rows matching the
    bracket-diff union, and reports provenance_written: true."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        spec_dir = _prov_spec_dir(repo_root, "feat-gate")
        _write_validated_md(spec_dir)
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", "specs"],
                       check=True, capture_output=True)
        bracket_begin = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True).stdout.strip()
        end = _prov_git_commit_file(repo_root, "src/impl.py", "implement feat-gate")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            assert lazy_core.append_commit_bracket("feat-gate", bracket_begin, end)
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-gate", date="2026-07-04",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is True, f"got {result}"
        assert result.get("provenance_written") is True, f"got {result}"
        meta = lazy_core.parse_sentinel(spec_dir / "IMPLEMENTED.md")
        assert meta is not None and meta.get("kind") == "implemented"
        assert meta.get("provenance") == "pipeline-gated"
        assert meta.get("derivation") == "commit-brackets"
        assert [str(c) for c in meta.get("commits")] == [end[:7]]
        index = json.loads(
            (repo_root / "docs" / "provenance-index.json").read_text(encoding="utf-8"))
        # Index keys == the bracket window's `git diff --name-only` union.
        assert list(index.keys()) == ["src/impl.py"], f"got {index}"
        assert index["src/impl.py"][0]["provenance"] == "pipeline-gated"




def test_mark_complete_provenance_falls_back_to_message_grep():
    """No recorded brackets → the gate derives via message-grep and records the
    honest degraded derivation label."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        spec_dir = _prov_spec_dir(repo_root, "feat-grep")
        _write_validated_md(spec_dir)
        end = _prov_git_commit_file(repo_root, "src/g.py", "fix(feat-grep): work")
        state_dir = Path(td) / "state"
        state_dir.mkdir()  # hermetic + EMPTY: no brackets recorded
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-grep", date="2026-07-04",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is True, f"got {result}"
        assert result.get("provenance_written") is True, f"got {result}"
        meta = lazy_core.parse_sentinel(spec_dir / "IMPLEMENTED.md")
        assert meta.get("derivation") == "message-grep", f"got {meta}"
        assert [str(c) for c in meta.get("commits")] == [end[:7]]
        index = json.loads(
            (repo_root / "docs" / "provenance-index.json").read_text(encoding="utf-8"))
        assert "src/g.py" in index




def test_item_scope_excludes_foreign_harden_commits():
    """gate-scope-folds-concurrent-harden-commits: an item's completion-gate
    scope EXCLUDES foreground harden-workstream commits (subject `harden(...)`)
    that a cycle bracket's range diff swept in — the item answers only for its
    OWN commits' touched files."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        seed = _prov_git_fixture_repo(repo_root)
        spec_dir = repo_root / "docs" / "features" / "feat-scope"
        spec_dir.mkdir(parents=True)
        # The item's OWN commit touches only docs (zero control surfaces).
        _prov_git_commit_file(
            repo_root, "docs/features/feat-scope/PHASES.md",
            "chore(feat-scope): mark plan complete")
        # A foreign observed-friction harden commit lands mid-run on a control
        # surface, inside the same begin..end bracket window.
        end = _prov_git_commit_file(
            repo_root, "user/scripts/lazy_core.py",
            "harden(script): fix scope derivation")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            assert lazy_core.append_commit_bracket("feat-scope", seed, end)
            files = lazy_core._item_commit_touched_files(spec_dir, repo_root)
        finally:
            _clear_state_dir()
        assert "docs/features/feat-scope/PHASES.md" in files, f"got {files}"
        assert "user/scripts/lazy_core.py" not in files, (
            f"foreign harden commit's control-surface file leaked into item "
            f"scope: {files}")




def test_mark_fixed_emits_provenance_bug_type():
    """The bug pipeline trigger: __mark_fixed__ emits type: bug index rows via
    the SAME producer (no coupled-pair fork)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        spec_dir = _prov_spec_dir(repo_root, "bug-prov", docs_kind="bugs")
        _write_validated_md(spec_dir)
        _prov_git_commit_file(repo_root, "src/fix.py", "fix(bug-prov): repair")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_fixed__", spec_dir,
                feature_id="bug-prov", date="2026-07-04",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is True, f"got {result}"
        assert result.get("provenance_written") is True
        meta = lazy_core.parse_sentinel(spec_dir / "IMPLEMENTED.md")
        assert meta.get("kind") == "implemented"
        index = json.loads(
            (repo_root / "docs" / "provenance-index.json").read_text(encoding="utf-8"))
        assert index["src/fix.py"][0]["type"] == "bug", f"got {index}"




def test_link_provenance_creates_minimal_decision_record_dir():
    """Linked work with NO existing docs dir gets a minimal decision-record
    dir (docs/features/<slug>/ with the distillate as its primary doc, D8) —
    never a fabricated SPEC."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        begin = _prov_git_fixture_repo(repo_root)
        end = _prov_git_commit_file(repo_root, "src/new.py", "unspecced work")
        result = lazy_core.link_provenance(
            repo_root, "adhoc-teammate-work",
            commit_range=f"{begin}..{end}", date="2026-07-04",
        )
        assert result["ok"] is True, f"got {result}"
        item_dir = repo_root / "docs" / "features" / "adhoc-teammate-work"
        assert (item_dir / "IMPLEMENTED.md").exists()
        assert not (item_dir / "SPEC.md").exists(), "must NOT invent a fake SPEC"
        meta = lazy_core.parse_sentinel(item_dir / "IMPLEMENTED.md")
        assert meta.get("decisions") == []




# ---------------------------------------------------------------------------
# code-doc-provenance-linkage — Phase 5: --backfill-provenance + --lint-provenance
# ---------------------------------------------------------------------------

def test_backfill_provenance_honest_and_idempotent():
    """Backfill walks receipted items (features + ARCHIVED bugs), emits
    provenance: backfilled + derivation: message-grep distillates, and is
    idempotent (existing IMPLEMENTED.md → skipped, index byte-stable)."""
    _guard()
    assert hasattr(lazy_core, "backfill_provenance"), (
        "lazy_core.backfill_provenance is missing"
    )
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        # Receipted feature + receipted archived bug, seeded BEFORE the git
        # fixture so the slug-named commits are the only touched-file source.
        feat_dir = _prov_spec_dir(repo_root, "feat-done")
        lazy_core.write_completed_receipt(
            feat_dir / "COMPLETED.md", "feat-done", "2026-06-01",
            provenance="gated")
        arch_dir = repo_root / "docs" / "bugs" / "_archive" / "bug-old"
        arch_dir.mkdir(parents=True)
        lazy_core.write_completed_receipt(
            arch_dir / "FIXED.md", "bug-old", "2026-06-01",
            provenance="gated", kind="fixed")
        _prov_git_fixture_repo(repo_root)
        _prov_git_commit_file(repo_root, "src/f.py", "feat(feat-done): impl")
        _prov_git_commit_file(repo_root, "src/b.py", "fix(bug-old): repair")
        result = lazy_core.backfill_provenance(repo_root, date="2026-07-04")
        assert result["ok"] is True, f"got {result}"
        assert sorted(result["backfilled"]) == ["bug-old", "feat-done"], f"got {result}"
        feat_meta = lazy_core.parse_sentinel(feat_dir / "IMPLEMENTED.md")
        assert feat_meta.get("provenance") == "backfilled"
        assert feat_meta.get("derivation") == "message-grep"
        bug_meta = lazy_core.parse_sentinel(arch_dir / "IMPLEMENTED.md")
        assert bug_meta.get("provenance") == "backfilled"
        index_path = repo_root / "docs" / "provenance-index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["src/f.py"][0] == {
            "id": "feat-done", "type": "feature", "provenance": "backfilled"}
        assert index["src/b.py"][0]["type"] == "bug"
        # Idempotency: second run skips both; index byte-stable.
        before = index_path.read_bytes()
        result2 = lazy_core.backfill_provenance(repo_root, date="2026-07-04")
        assert sorted(result2["skipped_existing"]) == ["bug-old", "feat-done"], (
            f"got {result2}")
        assert result2["backfilled"] == []
        assert index_path.read_bytes() == before




def test_backfill_provenance_zero_hit_still_distills():
    """A receipted item whose slug matches NO commit message still gets an
    honest distillate (commits: []) and contributes no index rows."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        feat_dir = _prov_spec_dir(repo_root, "feat-ancient")
        lazy_core.write_completed_receipt(
            feat_dir / "COMPLETED.md", "feat-ancient", "2026-06-01",
            provenance="backfilled-unverified")
        _prov_git_fixture_repo(repo_root)
        result = lazy_core.backfill_provenance(repo_root, date="2026-07-04")
        assert result["ok"] is True and result["backfilled"] == ["feat-ancient"]
        assert "feat-ancient" in result.get("no_commit_matches", []), f"got {result}"
        meta = lazy_core.parse_sentinel(feat_dir / "IMPLEMENTED.md")
        assert meta.get("commits") == [], f"got {meta}"
        index_path = repo_root / "docs" / "provenance-index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            assert all(
                not any(r.get("id") == "feat-ancient" for r in rows)
                for rows in index.values()
            ), f"zero-hit item must contribute no rows: {index}"




# ---------------------------------------------------------------------------
# intervention-efficacy-tracking Phase 1 — the hypothesis-ledger capture half.
#
# `parse_intervention_hypothesis` (the `## Intervention Hypothesis` SPEC-block
# reader), `record_intervention` (baseline freeze over the REAL telemetry
# ledger + atomic frontmatter-sentinel record write to
# docs/interventions/<id>.md), and the `apply_pseudo`
# __mark_complete__/__mark_fixed__ capture wiring (repo-opt-in via a top-level
# `"interventions": true` in docs/features/queue.json OR a present hypothesis
# block; byte-identical result keys otherwise). Hermetic via LAZY_STATE_DIR
# temp dirs; fixture ledgers are written by the REAL emitter under REAL run
# markers (never hand-rolled envelopes).
# ---------------------------------------------------------------------------


def _seed_intervention_ledger(runs: int, events_per_run: int,
                              event: str = "containment-refusal",
                              base_now: float = 1_700_000_000.0) -> list[str]:
    """Write `runs` fixture runs into the (LAZY_STATE_DIR) telemetry ledger via
    the REAL write_run_marker + append_telemetry_event, `events_per_run`
    matching events each. Returns the run_ids oldest-first. Leaves the LAST
    run's marker in place (live marker — the capture path never needs it, but
    a live ledger usually has one)."""
    run_ids: list[str] = []
    for i in range(runs):
        now = base_now + i * 3600.0
        marker = lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root="/r",
            max_cycles=5, now=now,
        )
        run_ids.append(marker["started_at"])
        for j in range(events_per_run):
            ok = lazy_core.append_telemetry_event(
                event, item_id=f"item-{i}", data={"n": j}, now=now + 1.0 + j,
            )
            assert ok is True, f"fixture emit failed (run {i}, ev {j})"
    return run_ids




def test_record_intervention_writes_record_and_freezes_baseline():
    """Capture freezes the baseline from the REAL ledger into a nested
    `baseline:` map that round-trips through parse_sentinel (the SPEC's
    formerly-deferred empirical check), and the record lands at
    docs/interventions/<id>.md with the D3 field set."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            repo = Path(td) / "repo"
            spec_dir = repo / "docs" / "features" / "feat-x"
            spec_dir.mkdir(parents=True)
            (spec_dir / "SPEC.md").write_text(
                "# Feat X\n\n**Status:** In Progress\n\n"
                "## Intervention Hypothesis\n\n"
                "- target_signal: event:containment-refusal\n"
                "- expected_direction: decrease\n"
                "- signal_independence: independent — counted by the guard\n"
                "- review_after_runs: 4\n",
                encoding="utf-8",
            )
            run_ids = _seed_intervention_ledger(3, 2)
            res = lazy_core.record_intervention(
                repo, "feat-x", pipeline="feature", spec_path=spec_dir,
                date="2026-07-04",
            )
            assert res["recorded"] is True, res
            record_path = repo / "docs" / "interventions" / "feat-x.md"
            assert record_path.exists()
            meta = lazy_core.parse_sentinel(record_path)
            assert meta["kind"] == "intervention"
            assert meta["intervention_id"] == "feat-x"
            assert meta["pipeline"] == "feature"
            assert meta["provenance"] == "gated"
            assert meta["target_signal"] == "event:containment-refusal"
            assert meta["expected_direction"] == "decrease"
            assert meta["signal_independence"] == "independent"
            assert meta["review_after_runs"] == 4
            assert meta["review_count"] == 0
            assert meta["status"] == "open"
            assert meta["escalated"] is False
            assert meta["reconsideration_enqueued"] is None
            # Nested baseline map — parse_sentinel (yaml.safe_load) handles it;
            # run-id strings survive as STRINGS (never YAML timestamps).
            base = meta["baseline"]
            assert isinstance(base, dict), base
            assert base["status"] == "frozen"
            assert base["runs"] == 3
            assert base["events"] == 6
            assert base["value"] == 2.0
            assert base["last_run_id"] == run_ids[-1]
            assert isinstance(base["last_run_id"], str)
            # shipped_date defaults to the capture date; commit_set is v1-shaped.
            assert meta["shipped_date"] == "2026-07-04"
            assert "commit_set" in meta
        finally:
            _clear_state_dir()




def test_record_intervention_backfill_and_hardening_provenance():
    """D9 backfill: explicit shipped_commit/shipped_date land verbatim with
    provenance: backfilled. Phase-4 hardening path: pipeline: hardening +
    hypothesis_overrides carry the round's targeted signal (no SPEC needed)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            repo = Path(td) / "repo"
            repo.mkdir()
            res = lazy_core.record_intervention(
                repo, "old-halt-tweak", pipeline="feature",
                shipped_commit="abc1234", shipped_date="2026-01-01",
                provenance="backfilled",
            )
            assert res["recorded"] is True
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / "old-halt-tweak.md")
            assert meta["provenance"] == "backfilled"
            assert meta["shipped_commit"] == "abc1234"
            assert meta["shipped_date"] == "2026-01-01"

            res2 = lazy_core.record_intervention(
                repo, "harden-2026-07-r3", pipeline="hardening",
                provenance="manual",
                hypothesis_overrides={
                    "target_signal": "event:containment-refusal",
                    "expected_direction": "decrease",
                    "review_after_runs": 8,
                },
            )
            assert res2["recorded"] is True
            meta2 = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / "harden-2026-07-r3.md")
            assert meta2["pipeline"] == "hardening"
            assert meta2["target_signal"] == "event:containment-refusal"
            assert meta2["review_after_runs"] == 8
        finally:
            _clear_state_dir()




def _canary_repo_with_change(td: "Path", relpath: str, item_id: str,
                             spec_body: str | None = None) -> "Path":
    """git repo touching `relpath` in one commit past the seed, a recorded
    commit bracket (seed..change) keyed by `item_id`, and an optional SPEC.md
    at docs/features/<item_id>/SPEC.md. Returns the repo root."""
    repo = Path(td) / f"repo-{item_id}"
    repo.mkdir()
    seed = _prov_git_fixture_repo(repo)
    change = _prov_git_commit_file(repo, relpath, f"touch {relpath}")
    ok = lazy_core.append_commit_bracket(item_id, seed, change)
    assert ok is True, "fixture bracket append failed"
    if spec_body is not None:
        spec_dir = repo / "docs" / "features" / item_id
        spec_dir.mkdir(parents=True)
        (spec_dir / "SPEC.md").write_text(spec_body, encoding="utf-8")
    return repo




def test_record_intervention_canary_arms_on_control_surface():
    """A control-surface change registers a `canary:` sub-map (status open) with
    the matched surfaces, the derived commit set, and the coupled-pair scope
    (both halves); the whole map round-trips through parse_sentinel."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            item = "canary-feat"
            repo = _canary_repo_with_change(
                Path(td), "user/skills/lazy/SKILL.md", item, spec_body="# F\n")
            res = lazy_core.record_intervention(
                repo, item, pipeline="feature",
                spec_path=repo / "docs" / "features" / item,
                date="2026-07-04",
            )
            assert res["recorded"] is True, res
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / f"{item}.md")
            canary = meta["canary"]
            assert isinstance(canary, dict), canary
            assert canary["status"] == "open"
            assert "user/skills/lazy/SKILL.md" in canary["surfaces"]
            assert isinstance(canary["surfaces"], list)
            assert canary["commit_set"], "commit_set must be non-empty"
            assert isinstance(canary["commit_set"], list)
            # Pair scope carries BOTH halves of every pair the change hits.
            ps = canary["pair_scope"]
            assert isinstance(ps, list)
            assert "user/skills/lazy/SKILL.md" in ps
            assert "user/skills/lazy-bug/SKILL.md" in ps
            assert "repos/algobooth/.claude/skills/lazy-cloud/SKILL.md" in ps
            assert canary["window_runs"] == 10  # default
            assert canary["degraded_revert_note"] is None
            assert canary["opened"] == "2026-07-04"
        finally:
            _clear_state_dir()




def test_record_intervention_no_canary_for_nonscoped():
    """A change touching only non-control-surface files registers NO canary
    (byte-identical to today — the record simply has no `canary` key)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            item = "canary-nonscoped"
            repo = _canary_repo_with_change(
                Path(td), "docs/notes/random.md", item, spec_body="# F\n")
            res = lazy_core.record_intervention(
                repo, item, pipeline="feature",
                spec_path=repo / "docs" / "features" / item,
            )
            assert res["recorded"] is True
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / f"{item}.md")
            assert "canary" not in meta, meta.get("canary")
        finally:
            _clear_state_dir()




def test_record_intervention_canary_window_override():
    """A per-record `canary_window_runs` override in the SPEC's Intervention
    Hypothesis block is honored over the default 10."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            item = "canary-window"
            spec = (
                "# F\n\n## Intervention Hypothesis\n\n"
                "- target_signal: event:gate-refusal\n"
                "- expected_direction: decrease\n"
                "- canary_window_runs: 5\n"
            )
            repo = _canary_repo_with_change(
                Path(td), "user/scripts/lazy_core/_monolith.py", item,
                spec_body=spec)
            lazy_core.record_intervention(
                repo, item, pipeline="feature",
                spec_path=repo / "docs" / "features" / item,
            )
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / f"{item}.md")
            assert meta["canary"]["window_runs"] == 5
        finally:
            _clear_state_dir()




def test_record_intervention_canary_degraded_note():
    """A change flagged revert-unsafe records a non-null degraded_revert_note;
    the default (unflagged) note is null (asserted in the arm test above)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            item = "canary-unsafe"
            spec = (
                "# F\n\n## Intervention Hypothesis\n\n"
                "- target_signal: event:gate-refusal\n"
                "- canary_revert_unsafe: true\n"
            )
            repo = _canary_repo_with_change(
                Path(td), "user/scripts/bug-state.py", item, spec_body=spec)
            lazy_core.record_intervention(
                repo, item, pipeline="feature",
                spec_path=repo / "docs" / "features" / item,
            )
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / f"{item}.md")
            assert meta["canary"]["degraded_revert_note"] is not None
            assert isinstance(meta["canary"]["degraded_revert_note"], str)
        finally:
            _clear_state_dir()




def test_drop_efficacy_breadcrumb_records_covered_scope_and_interventions_flag():
    """drop_efficacy_breadcrumb(covered_repo_root) records the covered repo's
    key in covered_scopes and sets interventions_covered True when that repo
    opts in. RED today: the current payload has neither key."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as covered_td:
        base = Path(base_td)
        covered_root = Path(covered_td)
        _set_state_dir(base)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(base),
                max_cycles=5,
            )
            _make_interventions_bearing_repo(covered_root)

            assert lazy_core.drop_efficacy_breadcrumb(str(covered_root)) is True

            crumb_path = base / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            crumb = json.loads(crumb_path.read_text(encoding="utf-8"))
            covered_key = lazy_core.repo_key(str(covered_root))
            assert covered_key in crumb.get("covered_scopes", []), crumb
            assert crumb.get("interventions_covered") is True, crumb
        finally:
            _clear_state_dir()




def test_drop_efficacy_breadcrumb_accumulates_two_scopes():
    """Two drop_efficacy_breadcrumb calls for the SAME run_started_at
    ACCUMULATE covered_scopes (union) and OR the interventions_covered flag —
    the claude-config-second-flush case where the trio flushes once per repo
    scope within one run. RED today: no covered_scopes key exists at all."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as non_iv_td, \
         tempfile.TemporaryDirectory() as iv_td:
        base = Path(base_td)
        non_interventions_root = Path(non_iv_td)
        interventions_root = Path(iv_td)
        _set_state_dir(base)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(base),
                max_cycles=5,
            )
            _make_interventions_bearing_repo(interventions_root)

            assert lazy_core.drop_efficacy_breadcrumb(
                str(non_interventions_root)
            ) is True
            assert lazy_core.drop_efficacy_breadcrumb(
                str(interventions_root)
            ) is True

            crumb_path = base / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            crumb = json.loads(crumb_path.read_text(encoding="utf-8"))
            covered = set(crumb.get("covered_scopes", []))
            assert lazy_core.repo_key(str(non_interventions_root)) in covered, crumb
            assert lazy_core.repo_key(str(interventions_root)) in covered, crumb
            assert crumb.get("interventions_covered") is True, crumb
        finally:
            _clear_state_dir()




def test_drop_efficacy_breadcrumb_non_interventions_scope_flag_false():
    """A single call covering a NON-interventions-bearing repo records that
    repo's key but leaves interventions_covered False. RED today: neither key
    exists."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as non_iv_td:
        base = Path(base_td)
        non_interventions_root = Path(non_iv_td)
        _set_state_dir(base)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(base),
                max_cycles=5,
            )

            assert lazy_core.drop_efficacy_breadcrumb(
                str(non_interventions_root)
            ) is True

            crumb_path = base / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            crumb = json.loads(crumb_path.read_text(encoding="utf-8"))
            assert lazy_core.repo_key(str(non_interventions_root)) in crumb.get(
                "covered_scopes", []
            ), crumb
            assert crumb.get("interventions_covered") is False, crumb
        finally:
            _clear_state_dir()




def test_drop_efficacy_breadcrumb_writes_into_run_marker_dir_when_active_has_none():
    """CROSS-DIR case: the active (flat) state dir holds NO live marker, but a
    keyed sibling subdir does. The breadcrumb must be written into the RUN
    MARKER's dir (the keyed sibling), NOT the flat active dir — the
    claude-config-second-flush scenario where the orchestrator's active repo
    differs from the run's originating target. RED today: drop_efficacy_
    breadcrumb only ever reads/writes claude_state_dir() (the active dir) and
    returns False here (no marker found there) instead of falling back."""
    _guard()
    with tempfile.TemporaryDirectory() as base_td, \
         tempfile.TemporaryDirectory() as target_td, \
         tempfile.TemporaryDirectory() as iv_td:
        base = Path(base_td)
        target_root = Path(target_td)
        interventions_root = Path(iv_td)
        _set_state_dir(base)
        try:
            keyed_dir = _write_target_marker(
                base, target_root, started_at=_fresh_started_at()
            )
            _make_interventions_bearing_repo(interventions_root)

            assert lazy_core.drop_efficacy_breadcrumb(
                str(interventions_root)
            ) is True

            target_crumb_path = keyed_dir / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            flat_crumb_path = base / lazy_core._EFFICACY_BREADCRUMB_FILENAME
            assert target_crumb_path.exists(), (
                f"breadcrumb must land in the run marker's keyed dir: {keyed_dir}"
            )
            assert not flat_crumb_path.exists(), (
                "breadcrumb must NOT be written into the marker-less active dir"
            )
            crumb = json.loads(target_crumb_path.read_text(encoding="utf-8"))
            assert lazy_core.repo_key(str(interventions_root)) in crumb.get(
                "covered_scopes", []
            ), crumb
            assert crumb.get("interventions_covered") is True, crumb
        finally:
            _clear_state_dir()




def test_record_intervention_sub_signal_baseline_counts_matching_signature_only():
    """Capture-time baseline freeze for a sub-signal target counts ONLY
    ledger events whose data.gate matches the declared signature — a
    gate-refusal/gate-coverage hypothesis must not absorb unrelated
    gate-refusal/verify-ledger events into its frozen baseline."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            repo = Path(td) / "repo"
            run_ids: list[str] = []
            for i in range(3):
                now = 1_700_100_000.0 + i * 3600.0
                marker = lazy_core.write_run_marker(
                    pipeline="feature", cloud=False, repo_root="/r",
                    max_cycles=5, now=now,
                )
                run_ids.append(marker["started_at"])
                lazy_core.append_telemetry_event(
                    "gate-refusal", item_id=f"item-{i}",
                    data={"gate": "gate-coverage"}, now=now + 1.0,
                )
                lazy_core.append_telemetry_event(
                    "gate-refusal", item_id=f"item-{i}",
                    data={"gate": "verify-ledger"}, now=now + 2.0,
                )
            res = lazy_core.record_intervention(
                repo, "feat-subsig", pipeline="feature",
                hypothesis_overrides={
                    "target_signal": "event:gate-refusal/gate-coverage",
                    "expected_direction": "decrease",
                },
                date="2026-07-12",
            )
            assert res["recorded"] is True, res
            meta = lazy_core.parse_sentinel(
                repo / "docs" / "interventions" / "feat-subsig.md")
            assert meta["target_signal"] == "event:gate-refusal/gate-coverage", (
                "the sub-signal target must NOT degrade to undeclared at capture"
            )
            base = meta["baseline"]
            assert base["status"] == "frozen", base
            assert base["runs"] == 3
            assert base["events"] == 3, (
                "baseline must count ONLY the gate-coverage sub-signal events "
                f"(1/run), not the co-occurring verify-ledger events; got {base}"
            )
        finally:
            _clear_state_dir()




def test_guard_plane_heartbeat_none_before_min_cycles():
    """A live marker with fewer than _GUARD_PLANE_HEARTBEAT_MIN_CYCLES total
    cycles is too early to assess -> None (a fresh run legitimately has zero
    guard events)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=20, now=1_700_000_000.0,
            )
            marker_path = state_dir / lazy_core._MARKER_FILENAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["forward_cycles"] = 1
            marker["meta_cycles"] = 1
            marker_path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            assert lazy_core.guard_plane_heartbeat(now=1_700_000_010.0) is None
        finally:
            _clear_state_dir()




def test_guard_plane_heartbeat_quiet_true_when_zero_events():
    """Past the min-cycle threshold with ZERO hook-events.jsonl entries ->
    quiet: True, events_this_run: 0 (the literal "guards executed 0 times"
    surface — advisory, never a halt)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=20, now=1_700_000_000.0,
            )
            marker_path = state_dir / lazy_core._MARKER_FILENAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["forward_cycles"] = 5
            marker["meta_cycles"] = 0
            marker_path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            result = lazy_core.guard_plane_heartbeat(now=1_700_000_600.0)
        finally:
            _clear_state_dir()
    assert result == {
        "events_this_run": 0, "cycles_this_run": 5, "quiet": True,
    }




def test_guard_plane_heartbeat_counts_events_since_run_start_only():
    """Events BEFORE the run's started_at (a prior run's stale trace) do NOT
    count; events at-or-after started_at do -> quiet: False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # A prior-run event BEFORE this run started — must be excluded.
            (state_dir / "hook-events.jsonl").write_text(
                '{"ts": 1699999000.0, "kind": "error", "hook": "old", '
                '"repo_root": "", "signature": "", "detail": "stale"}\n',
                encoding="utf-8",
            )
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=20, now=1700000000.0,
            )
            marker_path = state_dir / lazy_core._MARKER_FILENAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["forward_cycles"] = 5
            marker["meta_cycles"] = 0
            marker_path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            # An in-run event AFTER started_at — must be counted.
            with (state_dir / "hook-events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(
                    '{"ts": 1700000500.0, "kind": "deny", "hook": "live", '
                    '"repo_root": "", "signature": "sig", "detail": "d"}\n'
                )
            result = lazy_core.guard_plane_heartbeat(now=1700000600.0)
        finally:
            _clear_state_dir()
    assert result == {
        "events_this_run": 1, "cycles_this_run": 5, "quiet": False,
    }




def test_compute_state_surfaces_guard_plane_heartbeat_end_to_end():
    """Integration: lazy-state.py's compute_state() folds
    guard_plane_heartbeat into the probe output once the run marker has
    reached the min-cycle threshold (zero hook events -> quiet: True); a
    fresh marker (below threshold) leaves the key entirely absent."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo = ls._build_fixture(td_path, "fresh-queue")
        state_dir = td_path / "gph-state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            # Below threshold: key absent (byte-identical default output).
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root=str(repo),
                max_cycles=20, now=_t.time() - 60,
            )
            result_early = ls.compute_state(repo, cloud=False)
            assert "guard_plane_heartbeat" not in result_early, result_early

            # Past threshold, zero hook events -> quiet: True.
            marker_path = state_dir / lazy_core._MARKER_FILENAME
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["forward_cycles"] = 6
            marker["meta_cycles"] = 0
            marker_path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            result = ls.compute_state(repo, cloud=False)
        finally:
            _clear_state_dir()
    assert result.get("guard_plane_heartbeat") == {
        "events_this_run": 0, "cycles_this_run": 6, "quiet": True,
    }, result




def test_bare_write_lint_guard_catches_open_write_mode_and_ignores_read():
    """The `open(path, "w"...)` leg of the same guard: a write/append-mode open
    in production is caught; a read-mode (or mode-less) open is never flagged —
    proving the collector targets the corruption class (a truncatable write),
    not every filesystem open."""
    _guard()
    synthetic_source = (
        "def production_writer(path):\n"
        "    with open(path, 'w', encoding='utf-8') as fh:\n"  # line 2 — BAD
        "        fh.write('x')\n"
        "def production_reader(path):\n"
        "    with open(path, encoding='utf-8') as fh:\n"        # mode-less, OK
        "        return fh.read()\n"
    )
    hits = _collect_bare_production_writes(synthetic_source, "lazy-state.py")
    assert hits == [(2, "open-write-mode")], (
        f"expected only the write-mode open at line 2 to be caught; got {hits}"
    )




def test_duplicate_def_guard_detects_planted_violation():
    """Negative fixture — non-vacuity proof: a synthetic module defining the
    same top-level function name twice must be CAUGHT by name; a module with no
    duplicates must report an empty list."""
    _guard()
    synthetic_dup = (
        "def _current_head(x):\n"
        "    return 1\n"
        "\n"
        "def other(x):\n"
        "    return 2\n"
        "\n"
        "def _current_head(x):\n"  # shadowing duplicate
        "    return 3\n"
    )
    assert _collect_duplicate_top_level_defs(synthetic_dup) == ["_current_head"]

    synthetic_clean = (
        "def _current_head(x):\n"
        "    return 1\n"
        "\n"
        "def other(x):\n"
        "    return 2\n"
    )
    assert _collect_duplicate_top_level_defs(synthetic_clean) == []




# ---------------------------------------------------------------------------
# lazy-core-package-decomposition WU-2 — lazy_core/_ctx.py contract pins
# (RED-first / TDD Phase A). WU-1 moved the former lazy_core.py monolith body
# into lazy_core/_monolith.py behind a PEP 562 lazy facade
# (lazy_core/__init__.py, __getattr__-forwarding). WU-2 (not yet implemented)
# will extract a new lazy_core/_ctx.py module owning the shared kernel
# (_DIAGNOSTICS / _diag / clear_diagnostics / _atomic_write) plus
# accessor-based storage for the two rebindable globals _active_repo_root and
# _legacy_state_migrated.
#
# These four tests pin that contract BEFORE _ctx.py exists. The first three
# are RED today — lazy_core._ctx has no submodule yet, so any attribute
# access on it raises AttributeError via __init__.py's __getattr__ fallback
# ("module 'lazy_core' has no attribute '_ctx'"), which is the CORRECT red
# reason (it proves _ctx is the missing piece, not some other regression).
# The fourth is a permanent regression pin for the module-attribute
# patch-target mechanism and is expected to already be GREEN — everything
# still lives in _monolith.py today.
# ---------------------------------------------------------------------------

def test_ctx_diagnostics_identity():
    """Canonical-list-object contract: lazy_core._DIAGNOSTICS,
    lazy_core._ctx._DIAGNOSTICS, and lazy_core._monolith._DIAGNOSTICS must all
    be the SAME list object. lazy-state.py / bug-state.py mutate this list IN
    PLACE (append via _diag(), .clear() via clear_diagnostics()); if _ctx.py
    ever held its own separate list instead of sharing the one _monolith.py
    (or its eventual successor) owns, a diagnostic appended through one view
    would be invisible through another."""
    _guard()
    assert lazy_core._DIAGNOSTICS is lazy_core._ctx._DIAGNOSTICS, (
        "lazy_core._DIAGNOSTICS and lazy_core._ctx._DIAGNOSTICS must be the "
        "same list object"
    )
    assert lazy_core._ctx._DIAGNOSTICS is lazy_core._monolith._DIAGNOSTICS, (
        "lazy_core._ctx._DIAGNOSTICS and lazy_core._monolith._DIAGNOSTICS must "
        "be the same list object"
    )


_TESTS = [
    ("test_atomic_write_creates_file", test_atomic_write_creates_file),
    ("test_atomic_write_creates_parent_dirs", test_atomic_write_creates_parent_dirs),
    ("test_atomic_write_no_tmp_residue", test_atomic_write_no_tmp_residue),
    ("test_derive_stage_done_completed_md", test_derive_stage_done_completed_md),
    ("test_derive_stage_done_fixed_md", test_derive_stage_done_fixed_md),
    ("test_derive_stage_done_wins_over_blocked", test_derive_stage_done_wins_over_blocked),
    ("test_track_open_creates_wip_md", test_track_open_creates_wip_md),
    ("test_track_open_frontmatter_roundtrip", test_track_open_frontmatter_roundtrip),
    ("test_clear_diagnostics_callable", test_clear_diagnostics_callable),
    ("test_normalize_smoke_output_is_platform_neutral", test_normalize_smoke_output_is_platform_neutral),
    ("test_apply_pseudo_validated_from_skip_writes", test_apply_pseudo_validated_from_skip_writes),
    ("test_apply_pseudo_validated_from_skip_operator_granted_writes", test_apply_pseudo_validated_from_skip_operator_granted_writes),
    ("test_apply_pseudo_validated_from_results_copies_scenarios", test_apply_pseudo_validated_from_results_copies_scenarios),
    ("test_apply_pseudo_validated_from_results_promotes_documented_observation_gap", test_apply_pseudo_validated_from_results_promotes_documented_observation_gap),
    ("test_apply_pseudo_validated_from_results_happy_writes_canonical_frontmatter", test_apply_pseudo_validated_from_results_happy_writes_canonical_frontmatter),
    ("test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans", test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans),
    ("test_apply_pseudo_mark_fixed_writes_fixed_receipt", test_apply_pseudo_mark_fixed_writes_fixed_receipt),
    ("test_update_repeat_count_first_call_is_one", test_update_repeat_count_first_call_is_one),
    ("test_update_repeat_count_increments_on_identical", test_update_repeat_count_increments_on_identical),
    ("test_update_repeat_count_resets_on_signature_change", test_update_repeat_count_resets_on_signature_change),
    ("test_update_repeat_count_args_distinguish_signature", test_update_repeat_count_args_distinguish_signature),
    ("test_update_repeat_count_corrupt_file_resets", test_update_repeat_count_corrupt_file_resets),
    ("test_update_repeat_count_pipelines_are_isolated", test_update_repeat_count_pipelines_are_isolated),
    ("test_update_repeat_count_head_advance_resets", test_update_repeat_count_head_advance_resets),
    ("test_update_repeat_count_same_head_increments", test_update_repeat_count_same_head_increments),
    ("test_update_repeat_count_legacy_file_without_head_increments", test_update_repeat_count_legacy_file_without_head_increments),
    ("test_update_repeat_count_peek_does_not_mutate", test_update_repeat_count_peek_does_not_mutate),
    ("test_update_repeat_count_non_git_root_stores_none_head", test_update_repeat_count_non_git_root_stores_none_head),
    ("test_update_repeat_counts_returns_both_counts", test_update_repeat_counts_returns_both_counts),
    ("test_update_repeat_counts_step_counter_resets_on_step_change", test_update_repeat_counts_step_counter_resets_on_step_change),
    ("test_update_repeat_counts_step_no_head_advance_reset", test_update_repeat_counts_step_no_head_advance_reset),
    ("test_update_repeat_counts_step_peek_does_not_mutate", test_update_repeat_counts_step_peek_does_not_mutate),
    ("test_rebaseline_loop_signature_prevents_false_loop_on_checkpoint_resume", test_rebaseline_loop_signature_prevents_false_loop_on_checkpoint_resume),
    ("test_git_guard_status_clean_and_pushed", test_git_guard_status_clean_and_pushed),
    ("test_git_guard_status_dirty_tree", test_git_guard_status_dirty_tree),
    ("test_git_guard_status_unpushed_commit", test_git_guard_status_unpushed_commit),
    ("test_git_guard_status_invalid_repo_is_safe_dirty", test_git_guard_status_invalid_repo_is_safe_dirty),
    ("test_lazy_state_blocked_escalation_payload", test_lazy_state_blocked_escalation_payload),
    ("test_lazy_state_blocked_no_escalation_retry_1", test_lazy_state_blocked_no_escalation_retry_1),
    ("test_bug_state_blocked_escalation_payload", test_bug_state_blocked_escalation_payload),
    ("test_bug_state_blocked_no_escalation_other_kind", test_bug_state_blocked_no_escalation_other_kind),
    ("test_lazy_state_retro_fresh_routes_past_step8", test_lazy_state_retro_fresh_routes_past_step8),
    ("test_lazy_state_retro_stale_design_added_routes_past_step8", test_lazy_state_retro_stale_design_added_routes_past_step8),
    ("test_lazy_state_no_plans_verification_only_routes_to_mcp", test_lazy_state_no_plans_verification_only_routes_to_mcp),
    ("test_f2b_find_transcription_slip_entry_matches_near_copy", test_f2b_find_transcription_slip_entry_matches_near_copy),
    ("test_f2b_find_transcription_slip_entry_no_match_for_different_prompt", test_f2b_find_transcription_slip_entry_no_match_for_different_prompt),
    ("test_f2b_find_transcription_slip_entry_excludes_hardening_class", test_f2b_find_transcription_slip_entry_excludes_hardening_class),
    ("test_emit_dispatch_cycle_header_summary_fallback", test_emit_dispatch_cycle_header_summary_fallback),
    ("test_guard_allow_acks_on_hardening_class", test_guard_allow_acks_on_hardening_class),
    ("test_guard_pins_model_on_fresh_allow", test_guard_pins_model_on_fresh_allow),
    ("test_guard_pins_model_on_by_reference_and_auto_readmit_allows", test_guard_pins_model_on_by_reference_and_auto_readmit_allows),
    ("test_dispatch_by_reference_round_trips_every_class", test_dispatch_by_reference_round_trips_every_class),
    ("test_phase8_mvb_chain", test_phase8_mvb_chain),
    ("test_guard_unbound_marker_binds_on_allow", test_guard_unbound_marker_binds_on_allow),
    ("test_guard_unbound_marker_binds_on_idempotent_refire", test_guard_unbound_marker_binds_on_idempotent_refire),
    ("test_guard_bound_non_owner_fast_path_unchanged", test_guard_bound_non_owner_fast_path_unchanged),
    ("test_f1b_hardening_class_suffix_never_auto_readmits", test_f1b_hardening_class_suffix_never_auto_readmits),
    ("test_registry_ring_cap", test_registry_ring_cap),
    ("test_register_emission_if_marked_gating", test_register_emission_if_marked_gating),
    ("test_forward_cycles_survive_ring_cap_crossing_with_meta_interleave", test_forward_cycles_survive_ring_cap_crossing_with_meta_interleave),
    ("test_corrupt_marker_returns_none_and_deletes", test_corrupt_marker_returns_none_and_deletes),
    ("test_host_present_capabilities_cache_per_run_and_reprobe", test_host_present_capabilities_cache_per_run_and_reprobe),
    ("test_write_deferred_requires_host_emits_valid_sentinel", test_write_deferred_requires_host_emits_valid_sentinel),
    ("test_f2a_resolve_emission_missing_nonce_returns_none", test_f2a_resolve_emission_missing_nonce_returns_none),
    ("test_self_edit_mode_symbol_present", test_self_edit_mode_symbol_present),
    ("test_self_edit_mode_false_outside_toplevel", test_self_edit_mode_false_outside_toplevel),
    ("test_self_edit_mode_false_normal_repo_no_symlinks", test_self_edit_mode_false_normal_repo_no_symlinks),
    ("test_self_edit_mode_false_not_a_git_repo", test_self_edit_mode_false_not_a_git_repo),
    ("test_self_edit_mode_false_one_missing_path", test_self_edit_mode_false_one_missing_path),
    ("test_governing_file_set_excludes_auto_refresh_surfaces", test_governing_file_set_excludes_auto_refresh_surfaces),
    ("test_governing_files_touched_intersects_commit", test_governing_files_touched_intersects_commit),
    ("test_lazy_batch_skill_carries_reload_discipline_prose", test_lazy_batch_skill_carries_reload_discipline_prose),
    ("test_merged_symbols_present", test_merged_symbols_present),
    ("test_next_merged_cli_over_two_queue_fixture", test_next_merged_cli_over_two_queue_fixture),
    ("test_next_merged_cli_only_features_matches_single_head", test_next_merged_cli_only_features_matches_single_head),
    ("test_next_merged_cli_both_empty_prints_null", test_next_merged_cli_both_empty_prints_null),
    ("test_pin_bug_severity_updates_existing_entry", test_pin_bug_severity_updates_existing_entry),
    ("test_pin_bug_severity_malformed_until_refuses", test_pin_bug_severity_malformed_until_refuses),
    ("test_pin_bug_severity_unknown_bug_refuses", test_pin_bug_severity_unknown_bug_refuses),
    ("test_load_bug_queue_populates_aging_fields", test_load_bug_queue_populates_aging_fields),
    ("test_find_open_bug_dirs_age_escalates_sort_order", test_find_open_bug_dirs_age_escalates_sort_order),
    ("test_planner_resolution_internal_repos_derives_from_script_location", test_planner_resolution_internal_repos_derives_from_script_location),
    ("test_cycle_marker_symbols_present", test_cycle_marker_symbols_present),
    ("test_efficacy_breadcrumb_run_scoped_stale_does_not_satisfy", test_efficacy_breadcrumb_run_scoped_stale_does_not_satisfy),
    ("test_refuse_guard_symbol_present", test_refuse_guard_symbol_present),
    ("test_refuse_guard_op_set_matches_spec", test_refuse_guard_op_set_matches_spec),
    ("test_run_start_clobber_symbol_present", test_run_start_clobber_symbol_present),
    ("test_apply_pseudo_direct_call_allowed_with_orchestrator_env_under_marker", test_apply_pseudo_direct_call_allowed_with_orchestrator_env_under_marker),
    ("test_marker_mutation_guard_symbol_present", test_marker_mutation_guard_symbol_present),
    ("test_no_orphaned_test_functions", test_no_orphaned_test_functions),
    ("test_advance_run_counters_increments_per_feature", test_advance_run_counters_increments_per_feature),
    ("test_record_resolution_signal_marker_gated", test_record_resolution_signal_marker_gated),
    ("test_load_bug_queue_for_merged_no_breadcrumb_on_clean_load", test_load_bug_queue_for_merged_no_breadcrumb_on_clean_load),
    ("test_mark_complete_validated_verif_only_ticks_and_mints", test_mark_complete_validated_verif_only_ticks_and_mints),
    ("test_verify_ledger_and_completion_agree_on_verif_only", test_verify_ledger_and_completion_agree_on_verif_only),
    ("test_mark_fixed_validated_verif_only_ticks_and_mints", test_mark_fixed_validated_verif_only_ticks_and_mints),
    ("test_reconcile_does_not_false_trip_cycle_end_friction", test_reconcile_does_not_false_trip_cycle_end_friction),
    ("test_reassert_owner_cli_cycle_refusal_lazy_state", test_reassert_owner_cli_cycle_refusal_lazy_state),
    ("test_reassert_owner_cli_cycle_refusal_bug_state_parity", test_reassert_owner_cli_cycle_refusal_bug_state_parity),
    ("test_telemetry_emit_nondestructive_on_stale_marker", test_telemetry_emit_nondestructive_on_stale_marker),
    ("test_mark_complete_receipt_carries_completed_commit", test_mark_complete_receipt_carries_completed_commit),
    ("test_mark_complete_receipt_non_git_omits_completed_commit", test_mark_complete_receipt_non_git_omits_completed_commit),
    ("test_write_provenance_no_locked_decisions_is_honest", test_write_provenance_no_locked_decisions_is_honest),
    ("test_mark_complete_emits_provenance_from_brackets", test_mark_complete_emits_provenance_from_brackets),
    ("test_mark_complete_provenance_falls_back_to_message_grep", test_mark_complete_provenance_falls_back_to_message_grep),
    ("test_item_scope_excludes_foreign_harden_commits", test_item_scope_excludes_foreign_harden_commits),
    ("test_mark_fixed_emits_provenance_bug_type", test_mark_fixed_emits_provenance_bug_type),
    ("test_link_provenance_creates_minimal_decision_record_dir", test_link_provenance_creates_minimal_decision_record_dir),
    ("test_backfill_provenance_honest_and_idempotent", test_backfill_provenance_honest_and_idempotent),
    ("test_backfill_provenance_zero_hit_still_distills", test_backfill_provenance_zero_hit_still_distills),
    ("test_record_intervention_writes_record_and_freezes_baseline", test_record_intervention_writes_record_and_freezes_baseline),
    ("test_record_intervention_backfill_and_hardening_provenance", test_record_intervention_backfill_and_hardening_provenance),
    ("test_record_intervention_canary_arms_on_control_surface", test_record_intervention_canary_arms_on_control_surface),
    ("test_record_intervention_no_canary_for_nonscoped", test_record_intervention_no_canary_for_nonscoped),
    ("test_record_intervention_canary_window_override", test_record_intervention_canary_window_override),
    ("test_record_intervention_canary_degraded_note", test_record_intervention_canary_degraded_note),
    ("test_drop_efficacy_breadcrumb_records_covered_scope_and_interventions_flag", test_drop_efficacy_breadcrumb_records_covered_scope_and_interventions_flag),
    ("test_drop_efficacy_breadcrumb_accumulates_two_scopes", test_drop_efficacy_breadcrumb_accumulates_two_scopes),
    ("test_drop_efficacy_breadcrumb_non_interventions_scope_flag_false", test_drop_efficacy_breadcrumb_non_interventions_scope_flag_false),
    ("test_drop_efficacy_breadcrumb_writes_into_run_marker_dir_when_active_has_none", test_drop_efficacy_breadcrumb_writes_into_run_marker_dir_when_active_has_none),
    ("test_record_intervention_sub_signal_baseline_counts_matching_signature_only", test_record_intervention_sub_signal_baseline_counts_matching_signature_only),
    ("test_guard_plane_heartbeat_none_before_min_cycles", test_guard_plane_heartbeat_none_before_min_cycles),
    ("test_guard_plane_heartbeat_quiet_true_when_zero_events", test_guard_plane_heartbeat_quiet_true_when_zero_events),
    ("test_guard_plane_heartbeat_counts_events_since_run_start_only", test_guard_plane_heartbeat_counts_events_since_run_start_only),
    ("test_compute_state_surfaces_guard_plane_heartbeat_end_to_end", test_compute_state_surfaces_guard_plane_heartbeat_end_to_end),
    ("test_bare_write_lint_guard_catches_open_write_mode_and_ignores_read", test_bare_write_lint_guard_catches_open_write_mode_and_ignores_read),
    ("test_duplicate_def_guard_detects_planted_violation", test_duplicate_def_guard_detects_planted_violation),
    ("test_ctx_diagnostics_identity", test_ctx_diagnostics_identity),
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
