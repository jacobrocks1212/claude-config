#!/usr/bin/env python3
"""
test_pseudo.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_pseudo.py
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



from _util import _ModuleMissing, _CC_E2E_PHASES_VERIF_ONLY, _DESCOPED_PHASE_4, _cc_build_validated_feature, _cc_seed_and_commit, _cc_write_retro_done, _cc_write_validated, _clear_cycle_env, _clear_state_dir, _gate_write_manifest, _gate_write_verdict, _git_fixture_commit, _make_git_repo_with_origin, _os, _prov_git_commit_file, _prov_git_fixture_repo, _prov_spec_dir, _set_state_dir, _write_mcp_test_results, _write_mcp_test_results_with_exemptions, _write_not_required_phases, _write_phases_md, _write_skip_mcp_test, _write_spec_md, _write_validated_md  # noqa: E402




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
# Tests: has_completion_receipt
# ---------------------------------------------------------------------------

def test_has_completion_receipt_absent():
    """No COMPLETED.md → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, f"expected False, got {result}"




def test_has_completion_receipt_present():
    """COMPLETED.md present with valid frontmatter (kind: completed + provenance) → True."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "COMPLETED.md"
        # Write a properly formed receipt so the validation gate passes.
        lazy_core.write_completed_receipt(
            receipt_path,
            feature_id="test-feature",
            date="2026-06-10",
            provenance="gated",
        )
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is True, f"expected True, got {result}"




def test_has_completion_receipt_none_path():
    """has_completion_receipt(None) → False."""
    _guard()
    result = lazy_core.has_completion_receipt(None)
    assert result is False, f"expected False, got {result}"




def test_has_completion_receipt_empty_file_is_missing():
    """An empty (zero-byte) COMPLETED.md has no valid frontmatter → False (RED against bare .exists())."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Touch an empty file — the bare .exists() currently returns True for this.
        (Path(td) / "COMPLETED.md").write_text("", encoding="utf-8")
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, (
        f"expected False for empty receipt (no frontmatter), got {result}"
    )




def test_has_completion_receipt_no_frontmatter_is_missing():
    """A COMPLETED.md with only freeform text (no --- fences) is malformed → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "COMPLETED.md").write_text("# Completion Receipt\n", encoding="utf-8")
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, (
        f"expected False for receipt with no frontmatter, got {result}"
    )




def test_has_completion_receipt_kind_absent_is_missing():
    """Frontmatter present but 'kind:' key absent → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Valid fences, but no `kind` field at all.
        (Path(td) / "COMPLETED.md").write_text(
            "---\nprovenance: gated\nfeature_id: foo\n---\n\n# Completion Receipt\n",
            encoding="utf-8",
        )
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, (
        f"expected False when 'kind' is absent from frontmatter, got {result}"
    )




def test_has_completion_receipt_wrong_kind_is_missing():
    """'kind: bogus' (not 'completed' or 'fixed') → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "COMPLETED.md").write_text(
            "---\nkind: bogus\nprovenance: gated\nfeature_id: foo\n---\n\n# Completion Receipt\n",
            encoding="utf-8",
        )
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, (
        f"expected False for 'kind: bogus', got {result}"
    )




def test_has_completion_receipt_no_provenance_is_missing():
    """'kind: completed' present but 'provenance:' absent → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "COMPLETED.md").write_text(
            "---\nkind: completed\nfeature_id: foo\n---\n\n# Completion Receipt\n",
            encoding="utf-8",
        )
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, (
        f"expected False when 'provenance' is absent, got {result}"
    )




def test_has_completion_receipt_empty_provenance_is_missing():
    """'kind: completed' present but 'provenance:' empty string → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "COMPLETED.md").write_text(
            "---\nkind: completed\nprovenance: \nfeature_id: foo\n---\n\n# Completion Receipt\n",
            encoding="utf-8",
        )
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is False, (
        f"expected False when 'provenance' is empty string, got {result}"
    )




def test_has_completion_receipt_malformed_emits_diagnostic():
    """A malformed receipt (no frontmatter) must emit a diagnostic via lazy_core._diag().

    This also asserts the RED diagnostic path — the bare .exists() never calls _diag,
    so this test will FAIL (no diagnostic) until the implementation is updated.
    """
    _guard()
    lazy_core.clear_diagnostics()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "COMPLETED.md").write_text("# Completion Receipt\n", encoding="utf-8")
        _result = lazy_core.has_completion_receipt(Path(td))
    assert len(lazy_core._DIAGNOSTICS) > 0, (
        "expected at least one diagnostic to be emitted for a malformed receipt, "
        f"but _DIAGNOSTICS was empty. result={_result!r}"
    )




def test_has_completion_receipt_valid_with_provenance():
    """kind: completed + non-empty provenance → True (GREEN regression guard).

    NOTE: This test is GREEN even against the current bare .exists() implementation
    because we write a valid receipt file. It serves as a regression guard to ensure
    that a well-formed receipt continues to return True after the implementation
    is tightened.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "COMPLETED.md"
        lazy_core.write_completed_receipt(
            receipt_path,
            feature_id="my-feature",
            date="2026-06-10",
            provenance="gated",
        )
        result = lazy_core.has_completion_receipt(Path(td))
    assert result is True, f"expected True for valid receipt, got {result}"




def test_has_completion_receipt_fixed_md_variant():
    """FIXED.md with kind: fixed + provenance → True (bug receipt convention via filename= kwarg)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "FIXED.md"
        lazy_core.write_completed_receipt(
            receipt_path,
            feature_id="my-bug",
            date="2026-06-10",
            provenance="gated",
            kind="fixed",
        )
        result = lazy_core.has_completion_receipt(Path(td), filename="FIXED.md")
    assert result is True, f"expected True for valid FIXED.md receipt, got {result}"




# ---------------------------------------------------------------------------
# Tests: write_completed_receipt
# ---------------------------------------------------------------------------

def test_write_completed_receipt_minimal():
    """Minimal receipt (required fields only) has correct structure."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "COMPLETED.md"
        lazy_core.write_completed_receipt(
            receipt_path,
            feature_id="my-feature",
            date="2026-06-01",
            provenance="gated",
        )
        content = receipt_path.read_text(encoding="utf-8")
    assert "kind: completed" in content, f"missing 'kind: completed' in:\n{content}"
    assert "feature_id: my-feature" in content, f"missing feature_id in:\n{content}"
    assert "date: 2026-06-01" in content, f"missing date in:\n{content}"
    assert "provenance: gated" in content, f"missing provenance in:\n{content}"
    assert "# Completion Receipt" in content, f"missing title in:\n{content}"




def test_write_completed_receipt_with_optional_fields():
    """Optional fields (completed_commit, validated_via, mcp counts) appear when given."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "COMPLETED.md"
        lazy_core.write_completed_receipt(
            receipt_path,
            feature_id="feat-x",
            date="2026-06-01",
            provenance="gated",
            completed_commit="abc1234",
            validated_via="mcp-test",
            mcp_pass_count=5,
            mcp_total_count=5,
            body_note="All MCP assertions passed.",
        )
        content = receipt_path.read_text(encoding="utf-8")
    assert "completed_commit: abc1234" in content, f"missing completed_commit:\n{content}"
    assert "validated_via: mcp-test" in content, f"missing validated_via:\n{content}"
    assert "mcp_pass_count: 5" in content, f"missing mcp_pass_count:\n{content}"
    assert "mcp_total_count: 5" in content, f"missing mcp_total_count:\n{content}"
    assert "All MCP assertions passed." in content, f"missing body_note:\n{content}"




def test_write_completed_receipt_atomic():
    """write_completed_receipt is atomic: no intermediate .tmp files remain."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        receipt_path = Path(td) / "COMPLETED.md"
        lazy_core.write_completed_receipt(
            receipt_path,
            feature_id="feat-y",
            date="2026-06-01",
            provenance="backfilled-unverified",
        )
        tmp_files = list(Path(td).glob("*.tmp"))
        # Both assertions must run while the temp dir still exists; moving them
        # outside the `with` block would cause receipt_path.exists() to always
        # return False because the directory is deleted on __exit__.
        assert receipt_path.exists(), "COMPLETED.md was not created"
        assert tmp_files == [], f"temp file(s) not cleaned up: {tmp_files}"




def _write_in_progress_plan(plans_dir: Path, filename: str = "plan-phase-1.md") -> Path:
    """Write a minimal implementation plan with status: In-progress.

    Intentionally includes an unrelated frontmatter field (``feature_id``) and a
    body line so tests can prove the flip only changes the ``status:`` line and
    leaves everything else byte-unchanged.
    """
    plans_dir.mkdir(parents=True, exist_ok=True)
    p = plans_dir / filename
    p.write_text(
        "---\n"
        "kind: implementation-plan\n"
        "status: In-progress\n"
        "feature_id: test-feature\n"
        "phases:\n"
        "  - 1\n"
        "---\n\n"
        "# Implementation Plan\n\n"
        "Body line that must survive the flip unchanged.\n",
        encoding="utf-8",
    )
    return p




# ---- Test 2 ----

def test_apply_pseudo_validated_from_skip_refuses_when_skip_absent():
    """No SKIP_MCP_TEST.md present → ok=False, refused is a non-None string."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Deliberately do NOT write SKIP_MCP_TEST.md.
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec_dir, date="2026-06-10"
        )
    assert result["ok"] is False, f"expected ok=False when SKIP absent, got {result}"
    assert result["refused"] is not None, (
        f"expected non-None refused when SKIP absent, got {result!r}"
    )
    assert result["wrote"] == [], f"expected wrote=[], got {result['wrote']}"




# ---- Test 3 ----

def test_apply_pseudo_validated_from_skip_idempotent():
    """Running apply_pseudo twice when VALIDATED.md already exists → second call
    returns noop=True, ok=True, and only ONE VALIDATED.md exists with content
    byte-identical to what the first call wrote (no overwrite/duplication).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_skip_mcp_test(spec_dir)
        # First call — should write VALIDATED.md.
        first = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec_dir, date="2026-06-10"
        )
        assert first["noop"] is False, f"first call must NOT be a noop; got {first}"
        # Capture byte-content after the first call.
        validated_path = spec_dir / "VALIDATED.md"
        content_after_first = validated_path.read_text(encoding="utf-8")
        # Second call — must be idempotent.
        second = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec_dir, date="2026-06-10"
        )
        assert second["ok"] is True, f"expected ok=True on re-run, got {second}"
        assert second["noop"] is True, f"expected noop=True on re-run, got {second}"
        assert second["wrote"] == [], f"expected wrote=[] on noop re-run, got {second['wrote']}"
        # Only one VALIDATED.md must exist (no duplicates).
        md_files = list(spec_dir.glob("VALIDATED*.md"))
        assert len(md_files) == 1, f"expected exactly 1 VALIDATED.md, found {md_files}"
        # Content must be byte-stable (not overwritten).
        content_after_second = validated_path.read_text(encoding="utf-8")
        assert content_after_second == content_after_first, (
            "VALIDATED.md content changed on noop re-run — the file was overwritten"
        )




# ---- Test 3b (D-2: granted_by provenance gate) ----

def test_apply_pseudo_validated_from_skip_refuses_pipeline_granted():
    """SKIP_MCP_TEST.md carrying granted_by: pipeline → apply_pseudo must REFUSE
    (ok=False, non-None refused) and write nothing. The CLI write path must
    mirror compute_state's Step-9 gate: the pipeline cannot self-waive its own
    MCP requirement, so a pipeline-granted skip needs operator confirmation.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Self-granted skip: granted_by: pipeline.
        (spec_dir / "SKIP_MCP_TEST.md").write_text(
            "---\n"
            "kind: skip-mcp-test\n"
            "feature_id: test-feature\n"
            "reason: pipeline self-asserted skip\n"
            "date: 2026-06-10\n"
            "granted_by: pipeline\n"
            "---\n\n"
            "# Skip MCP Test\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for granted_by: pipeline, got {result}"
        )
        assert result["refused"] is not None and "pipeline" in result["refused"], (
            f"expected refusal naming the pipeline grant, got {result!r}"
        )
        assert result["wrote"] == [], f"expected wrote=[], got {result['wrote']}"
        # Nothing must have been written — the vacuous validation must not land.
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was written despite granted_by: pipeline — unsafe!"
        )




# ---- Test 5 ----

def test_apply_pseudo_validated_from_results_refuses_when_results_absent():
    """No MCP_TEST_RESULTS.md → ok=False, refused is non-None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Deliberately do NOT write MCP_TEST_RESULTS.md.
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
    assert result["ok"] is False, (
        f"expected ok=False when MCP_TEST_RESULTS.md absent, got {result}"
    )
    assert result["refused"] is not None, (
        f"expected non-None refused when results absent, got {result!r}"
    )




# ---- Test 5b: __write_validated_from_results__ integrity gates ----
# Hardening (2026-06-11): the last hand-written pseudo-skill became script-
# executed with refusal gates — results-kind, result-literal (all-passing),
# pass_count == total_count, and sha-freshness (validated_commit vs HEAD).
# Gate ORDER under test (load-bearing, mirrors __mark_complete__):
#   evidence gate (presence + kind + scenarios) → VALIDATED.md noop →
#   result-literal + count gate → freshness backstop → write.


def test_apply_pseudo_validated_from_results_refuses_wrong_kind():
    """MCP_TEST_RESULTS.md whose frontmatter ``kind:`` is not
    ``mcp-test-results`` → refused with ZERO writes.  A mis-kinded (or
    frontmatter-less) file must not feed the VALIDATED.md derivation —
    mirrors __mark_complete__'s evidence-kind gate, which rejects a
    content-less ``touch`` satisfying a presence-only check.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(spec_dir, ["scenario-a"], kind="validated")
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for wrong kind, got {result}"
        )
        assert result["refused"] is not None and "mcp-test-results" in result["refused"], (
            f"expected refusal naming the required 'mcp-test-results' kind, got {result!r}"
        )
        assert result["wrote"] == [], f"expected wrote=[], got {result['wrote']}"
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was written despite wrong results kind — unsafe!"
        )




def test_apply_pseudo_validated_from_results_refuses_non_passing_result():
    """``result: partial`` (the real failing literal in AlgoBooth results
    files) → refused; the message MUST name BOTH the expected literal
    ('all-passing') and the found value ('partial') so the orchestrator
    cannot guess-loop.  Zero writes.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(
            spec_dir, ["scenario-a", "scenario-b"],
            result="partial", pass_count=0, total_count=2,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for result: partial, got {result}"
        )
        refused = result["refused"] or ""
        assert "all-passing" in refused, (
            f"refusal must name the expected literal 'all-passing', got {refused!r}"
        )
        assert "partial" in refused, (
            f"refusal must name the found literal 'partial', got {refused!r}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was minted from a partial (failing) run — unsafe!"
        )




def test_apply_pseudo_validated_from_results_refuses_partial_with_non_exempt_failure():
    """REGRESSION GUARD: a `result: partial` whose remainder is NOT fully covered
    by documented `observation_gap_exemptions` (here a genuine MCP-driveable
    failure: pass_count < total_count with no exemption justifying it) STILL
    refuses — the observation-gap path must NOT weaken the genuine-failure refusal.
    Zero writes.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # 1 of 2 MCP-driveable scenarios genuinely FAILED (pass < total) — this is
        # NOT an observation gap, so the single exemption does not cover it.
        _write_mcp_test_results_with_exemptions(
            spec_dir,
            ["scenario-a", "scenario-b"],
            exemptions=[
                {
                    "surface": "per-block visual state",
                    "spec_class": "observation-gap — unit/WDIO tier per "
                    "docs/features/mcp-testing/SPEC.md",
                },
            ],
            result="partial",
            pass_count=1,
            total_count=2,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-30"
        )
        assert result["ok"] is False, (
            f"expected ok=False — a genuine MCP-scope failure must still refuse, "
            f"got {result}"
        )
        assert result["refused"] is not None, (
            f"expected a non-None refusal, got {result!r}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md minted despite a non-exempt MCP-scope failure — the "
            "genuine-failure refusal was weakened!"
        )




def test_apply_pseudo_validated_from_results_refuses_partial_exemptions_without_provenance():
    """A `result: partial` whose MCP scope passes but whose
    `observation_gap_exemptions` entries lack the required `spec_class` provenance
    STILL refuses — the exemption must be provenance-backed (mirrors the
    SKIP_MCP_TEST.md `spec_class`-required discipline), not a bare convenience tag.
    Zero writes.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        p = spec_dir / "MCP_TEST_RESULTS.md"
        # Exemption with NO spec_class provenance.
        p.write_text(
            "---\n"
            "kind: mcp-test-results\n"
            "feature_id: test-feature\n"
            "scenarios:\n  - scenario-a\n"
            "date: 2026-06-30\n"
            "result: partial\n"
            "pass_count: 1\n"
            "total_count: 1\n"
            "observation_gap_exemptions:\n"
            "  - surface: save-as-scene\n"
            "---\n\n# MCP Test Results\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-30"
        )
        assert result["ok"] is False, (
            f"expected ok=False — an exemption without spec_class provenance must "
            f"refuse, got {result}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md minted from a provenance-less exemption — unsafe!"
        )




def test_apply_pseudo_validated_from_results_refuses_missing_result_field():
    """No ``result:`` field at all → refused (a results file that doesn't
    declare its outcome cannot prove a passing run); message names the
    expected literal and the found (None) value.  Zero writes.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(spec_dir, ["scenario-a"], result=None)
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for missing result field, got {result}"
        )
        refused = result["refused"] or ""
        assert "all-passing" in refused and "None" in refused, (
            f"refusal must name expected 'all-passing' vs found None, got {refused!r}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was minted without a result literal — unsafe!"
        )




def test_apply_pseudo_validated_from_results_refuses_count_mismatch():
    """``result: all-passing`` but ``pass_count != total_count`` (13/14 —
    the real hard-state-reload shape) → refused; the literal alone is not
    trusted, the counts are the cross-check.  Message names both counts.
    Zero writes.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(
            spec_dir, ["scenario-a"],
            result="all-passing", pass_count=13, total_count=14,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for 13/14 counts, got {result}"
        )
        refused = result["refused"] or ""
        assert "13" in refused and "14" in refused, (
            f"refusal must name both counts (13 vs 14), got {refused!r}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was minted with pass_count != total_count — unsafe!"
        )




def test_apply_pseudo_validated_from_results_refuses_missing_counts():
    """``result: all-passing`` but pass_count/total_count absent → refused.
    The schema requires both counts; without them the literal has no
    cross-check (None == None must NOT vacuously satisfy the equality gate).
    Zero writes.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(
            spec_dir, ["scenario-a"], pass_count=None, total_count=None,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for missing counts, got {result}"
        )
        refused = result["refused"] or ""
        assert "pass_count" in refused, (
            f"refusal must name the missing pass_count/total_count, got {refused!r}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was minted without pass/total counts — unsafe!"
        )




def test_apply_pseudo_validated_from_results_refuses_stale_commit():
    """``validated_commit`` (all-zeros sha) != current ``git rev-parse HEAD``
    of repo_root → refused; stale results must not mint a fresh VALIDATED.md.
    The message names both shas.  Zero writes.  Mirrors the state scripts'
    Step-9 freshness gate (this is the apply-side second key).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_dir = root / "spec"
        spec_dir.mkdir()
        stale_sha = "0" * 40
        _write_mcp_test_results(
            spec_dir, ["scenario-a"], validated_commit=stale_sha,
        )
        # Real git repo so rev-parse HEAD resolves to a genuine (non-zero) sha.
        head = _git_fixture_commit(root)
        assert head != stale_sha, "fixture error: HEAD cannot be the zeros sha"
        result = lazy_core.apply_pseudo(
            root, "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for stale validated_commit, got {result}"
        )
        refused = result["refused"] or ""
        assert stale_sha in refused and head in refused, (
            f"refusal must name recorded sha vs current HEAD, got {refused!r}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was minted from stale results — unsafe!"
        )




def test_apply_pseudo_validated_from_results_fresh_commit_writes():
    """``validated_commit`` == current HEAD → the freshness gate passes and
    VALIDATED.md is written (positive guard for the sha-anchor path); no
    legacy warning is emitted.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_dir = root / "spec"
        spec_dir.mkdir()
        # Commit the tree FIRST so HEAD exists, then write the results file
        # carrying that exact sha (post-commit write dirties the working tree
        # but rev-parse HEAD is unaffected — same shape as the bug-state
        # step9-fresh-mcp-results fixture).
        (spec_dir / "SPEC.md").write_text("# placeholder\n", encoding="utf-8")
        head = _git_fixture_commit(root)
        _write_mcp_test_results(
            spec_dir, ["scenario-a"], validated_commit=head,
        )
        result = lazy_core.apply_pseudo(
            root, "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, (
            f"expected ok=True for fresh validated_commit, got {result}"
        )
        assert result["noop"] is False, f"expected noop=False, got {result}"
        assert (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was not written for fresh results"
        )
        assert not result.get("warnings"), (
            f"expected no warnings for a sha-anchored fresh run, got {result!r}"
        )




def test_apply_pseudo_validated_from_results_legacy_no_commit_warns():
    """Legacy results file with NO ``validated_commit`` field → ALLOWED
    (backward compatibility) but the result carries a warning line naming
    the missing field, so the orchestrator surfaces the unverified freshness.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(spec_dir, ["scenario-a"])  # no validated_commit
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, (
            f"expected ok=True for legacy commit-less results, got {result}"
        )
        assert (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was not written for legacy results"
        )
        warnings = result.get("warnings")
        assert isinstance(warnings, list) and len(warnings) >= 1, (
            f"expected a non-empty warnings list, got {result!r}"
        )
        assert any("validated_commit" in w for w in warnings), (
            f"warning must name the missing validated_commit field, got {warnings!r}"
        )




def test_apply_pseudo_validated_from_results_idempotent_noop():
    """VALIDATED.md already present (kind: validated) → noop-success even when
    the results file is FAILING — the receipt-noop check runs BEFORE the
    result-literal/freshness backstops, mirroring the __mark_complete__
    ordering rule (re-running against an already-validated dir never
    re-refuses).  The existing VALIDATED.md is byte-unchanged.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(
            spec_dir, ["scenario-a"],
            result="partial", pass_count=0, total_count=1,
        )
        validated_path = spec_dir / "VALIDATED.md"
        original = (
            "---\n"
            "kind: validated\n"
            "feature_id: test-feature\n"
            "date: 2026-06-01\n"
            "mcp_scenarios: [scenario-a]\n"
            "result: all-passing\n"
            "---\n\n"
            "# Validated\n"
        )
        validated_path.write_text(original, encoding="utf-8")
        result = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True on noop, got {result}"
        assert result["noop"] is True, f"expected noop=True, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        assert validated_path.read_text(encoding="utf-8") == original, (
            "existing VALIDATED.md was modified during a noop — must be byte-unchanged"
        )




# ---- Test 6 ----

def test_apply_pseudo_deferred_non_cloud_writes_and_idempotent():
    """__write_deferred_non_cloud__ writes DEFERRED_NON_CLOUD.md with
    kind=deferred-non-cloud; re-run returns noop=True.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # First call — should write DEFERRED_NON_CLOUD.md (no gate input required).
        first = lazy_core.apply_pseudo(
            Path(td), "__write_deferred_non_cloud__", spec_dir,
            date="2026-06-10",
            reason="cloud not available",
            deferred_step=8,
        )
        assert first["ok"] is True, f"expected ok=True, got {first}"
        assert first["noop"] is False, f"expected noop=False on first call, got {first}"
        deferred_path = spec_dir / "DEFERRED_NON_CLOUD.md"
        assert deferred_path.exists(), "DEFERRED_NON_CLOUD.md was not created"
        # Parse to verify kind.
        parsed = lazy_core.parse_sentinel(deferred_path)
        assert parsed is not None, "parse_sentinel returned None for DEFERRED_NON_CLOUD.md"
        assert parsed.get("kind") == "deferred-non-cloud", (
            f"expected kind='deferred-non-cloud', got {parsed.get('kind')!r}"
        )
        # Second call — must be idempotent.
        second = lazy_core.apply_pseudo(
            Path(td), "__write_deferred_non_cloud__", spec_dir,
            date="2026-06-10",
            reason="cloud not available",
            deferred_step=8,
        )
        assert second["ok"] is True, f"expected ok=True on re-run, got {second}"
        assert second["noop"] is True, f"expected noop=True on re-run, got {second}"




# ---- Test 7 ----

def test_apply_pseudo_flip_cloud_saturated_flips_in_progress():
    """plan with status: In-progress passed via plan_path → file becomes
    status: Complete; an unrelated frontmatter field (feature_id) and a body
    line are byte-unchanged; ok=True, noop=False.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        plan_path = _write_in_progress_plan(spec_dir / "plans")
        original_content = plan_path.read_text(encoding="utf-8")
        result = lazy_core.apply_pseudo(
            Path(td), "__flip_plan_complete_cloud_saturated__", spec_dir,
            plan_path=plan_path,
            date="2026-06-10",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["noop"] is False, f"expected noop=False, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        # The plan file must now contain status: Complete.
        flipped_content = plan_path.read_text(encoding="utf-8")
        assert "status: Complete" in flipped_content, (
            f"expected 'status: Complete' in flipped plan, got:\n{flipped_content}"
        )
        # The original In-progress line must be gone.
        assert "status: In-progress" not in flipped_content, (
            "status: In-progress should have been replaced, but it is still present"
        )
        # An unrelated frontmatter field (feature_id) must be byte-unchanged.
        assert "feature_id: test-feature" in flipped_content, (
            "unrelated frontmatter field 'feature_id' was altered by the flip"
        )
        # A body line must also survive unchanged.
        assert "Body line that must survive the flip unchanged." in flipped_content, (
            "body line was altered by the flip"
        )
        # wrote should reference the plan path.
        assert any(str(plan_path.name) in str(w) for w in result["wrote"]), (
            f"plan filename not in wrote: {result['wrote']}"
        )




# ---- Test 8 ----

def test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete():
    """plan already has status: Complete (passed via plan_path) → noop=True, ok=True."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Write a plan that is already Complete.
        plans_dir = spec_dir / "plans"
        plans_dir.mkdir(parents=True)
        already_complete = plans_dir / "plan-phase-1.md"
        already_complete.write_text(
            "---\n"
            "kind: implementation-plan\n"
            "status: Complete\n"
            "feature_id: test-feature\n"
            "phases:\n"
            "  - 1\n"
            "---\n\n"
            "# Implementation Plan\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__flip_plan_complete_cloud_saturated__", spec_dir,
            plan_path=already_complete,
            date="2026-06-10",
        )
    assert result["ok"] is True, f"expected ok=True for already-complete plan, got {result}"
    assert result["noop"] is True, (
        f"expected noop=True for already-complete plan, got {result}"
    )




# ---- Test 9 ----

def test_apply_pseudo_flip_cloud_saturated_refuses_no_plan():
    """No plan_path given and no plans/ directory → ok=False, refused is non-None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # No plans/ dir, no plan_path — nothing to flip.
        result = lazy_core.apply_pseudo(
            Path(td), "__flip_plan_complete_cloud_saturated__", spec_dir,
            date="2026-06-10",
        )
    assert result["ok"] is False, (
        f"expected ok=False when no plan is resolvable, got {result}"
    )
    assert result["refused"] is not None, (
        f"expected non-None refused when no plan present, got {result!r}"
    )




# ---- Test 10b: feature-queue trim on completion (queue.no-completed prevention) ----

def _write_features_queue(repo_root: Path, ids: list[str]) -> Path:
    """Write a docs/features/queue.json with one entry per id (id == spec_dir)."""
    features = repo_root / "docs" / "features"
    features.mkdir(parents=True, exist_ok=True)
    p = features / "queue.json"
    p.write_text(
        json.dumps(
            {"queue": [{"id": i, "spec_dir": i, "name": i} for i in ids]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return p




def test_apply_pseudo_mark_complete_trims_feature_queue():
    """__mark_complete__ must remove the completed feature's entry from
    docs/features/queue.json (symmetric to the bug pipeline's archive_fixed
    step-6 trim). Without it, AlgoBooth's check-docs-consistency.ts
    queue.no-completed rule HARD-ERRORS on every feature completion.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        # spec dir name must match the queue entry's spec_dir/id.
        spec_dir = repo_root / "docs" / "features" / "mcp-testing"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # Queue has the completing feature PLUS an unrelated one that must survive.
        queue_path = _write_features_queue(
            repo_root, ["mcp-testing", "other-feature"]
        )

        result = lazy_core.apply_pseudo(
            repo_root,
            "__mark_complete__",
            spec_dir,
            feature_id="mcp-testing",
            date="2026-06-10",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["queue_trimmed"] is True, (
            f"expected queue_trimmed=True, got {result}"
        )
        data = json.loads(queue_path.read_text(encoding="utf-8"))
        ids = [e["id"] for e in data["queue"]]
        assert "mcp-testing" not in ids, (
            f"completed feature still in queue.json: {ids}"
        )
        assert "other-feature" in ids, (
            f"unrelated feature was wrongly removed: {ids}"
        )
        # Valid JSON preserved (re-parse already proved it) + trailing newline.
        assert queue_path.read_text(encoding="utf-8").endswith("\n")




def test_apply_pseudo_mark_complete_queue_trim_behind_receipt_noop():
    """The queue trim never fires on a GENUINELY-DONE (noop) dir: when the dir
    is fully complete (receipt + SPEC Complete + own queue entry already trimmed
    + no cleanup sentinels), the audit short-circuits to noop BEFORE the trim, so
    an unrelated lingering entry is NOT mutated (queue_trimmed False, queue
    byte-identical). mark-complete-partial-apply-noop-unrecoverable: the noop is
    now gated on the FULL post-condition audit, so this fixture must itself be
    genuinely-done (its OWN entry already absent from the queue), not merely
    receipted.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "mcp-testing"
        spec_dir.mkdir(parents=True)
        # Pre-write a valid receipt + flip SPEC to Complete → genuinely done.
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="mcp-testing",
            date="2026-06-10",
            provenance="gated",
        )
        _write_spec_md(spec_dir, status="Complete")
        _write_skip_mcp_test(spec_dir)
        # The queue carries ONLY an unrelated entry (this feature's own entry was
        # already trimmed at completion) — the noop re-run must NOT touch it.
        queue_path = _write_features_queue(repo_root, ["other"])
        before = queue_path.read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="mcp-testing", date="2026-06-10",
        )
        assert result["noop"] is True, f"expected noop=True, got {result}"
        assert result.get("resumed") is False, f"expected resumed=False, got {result}"
        assert result.get("queue_trimmed", False) is False, (
            "queue trim fired on a genuinely-done (noop) dir"
        )
        assert queue_path.read_text(encoding="utf-8") == before, (
            "queue.json was mutated on the noop re-run"
        )




def test_apply_pseudo_mark_fixed_does_not_trim_feature_queue():
    """The bug/fixed path must NOT touch docs/features/queue.json — its queue
    lives at docs/bugs/queue.json and is trimmed by archive_fixed. Guards
    against the trim firing on the wrong pipeline.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "bugs" / "some-bug"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # A features queue that happens to share the spec name must be untouched.
        queue_path = _write_features_queue(repo_root, ["some-bug"])
        before = queue_path.read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_fixed__", spec_dir,
            feature_id="some-bug", date="2026-06-10",
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result.get("queue_trimmed", False) is False, (
            "fixed path wrongly reported a feature-queue trim"
        )
        assert queue_path.read_text(encoding="utf-8") == before, (
            "fixed path wrongly mutated docs/features/queue.json"
        )




def test_apply_pseudo_mark_complete_malformed_queue_warns_not_refuses():
    """A malformed docs/features/queue.json must NOT fail the completion (the
    receipt + status flips are already written). It degrades to a non-fatal
    warning so the completion stands and the operator is told to fix the queue.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "mcp-testing"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        features = repo_root / "docs" / "features"
        features.mkdir(parents=True, exist_ok=True)
        (features / "queue.json").write_text("{ this is not json", encoding="utf-8")

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="mcp-testing", date="2026-06-10",
        )
        # Completion still succeeds.
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        assert (spec_dir / "COMPLETED.md").exists(), "receipt not written"
        assert result["queue_trimmed"] is False
        assert result.get("warnings"), "expected a non-fatal queue warning"
        assert any("queue.json" in w for w in result["warnings"]), (
            f"warning did not mention queue.json: {result['warnings']}"
        )




# ---- Test 11 ----

def test_apply_pseudo_mark_complete_refuses_without_validation_evidence():
    """Neither VALIDATED.md nor SKIP_MCP_TEST.md present →
    ok=False, refused is non-None; no COMPLETED.md written.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # No VALIDATED.md and no SKIP_MCP_TEST.md.
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
    assert result["ok"] is False, (
        f"expected ok=False without validation evidence, got {result}"
    )
    assert result["refused"] is not None, (
        f"expected non-None refused without validation evidence, got {result!r}"
    )
    # Must NOT have written COMPLETED.md.
    assert not (spec_dir / "COMPLETED.md").exists(), (
        "COMPLETED.md was written despite no validation evidence — unsafe!"
    )




# ---- Test 11b (D-1: content-less evidence must not satisfy the gate) ----

def test_apply_pseudo_mark_complete_refuses_contentless_validated():
    """An empty (touch-created) VALIDATED.md has no frontmatter, so
    parse_sentinel returns {} — which is `not None` but carries no
    kind: validated. The __mark_complete__ gate must REFUSE such a file
    (ok=False, non-None refused) and write NO COMPLETED.md, instead of
    minting a provenance: gated receipt off content-less evidence.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_spec_md(spec_dir, status="In-progress")
        # Content-less evidence: `touch VALIDATED.md` equivalent.
        (spec_dir / "VALIDATED.md").write_text("", encoding="utf-8")
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for content-less VALIDATED.md, got {result}"
        )
        assert result["refused"] is not None and "VALIDATED.md" in result["refused"], (
            f"expected refusal naming VALIDATED.md, got {result!r}"
        )
        assert result["wrote"] == [], f"expected wrote=[], got {result['wrote']}"
        assert not (spec_dir / "COMPLETED.md").exists(), (
            "COMPLETED.md was written despite content-less VALIDATED.md — unsafe!"
        )
        # SPEC.md status must NOT have been flipped either.
        spec_text = (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert "**Status:** In-progress" in spec_text, (
            f"SPEC.md status was flipped despite the refusal:\n{spec_text}"
        )




def test_apply_pseudo_mark_complete_refuses_contentless_skip():
    """Same D-1 gate via the SKIP_MCP_TEST.md leg: an empty SKIP_MCP_TEST.md
    (no frontmatter → parse_sentinel returns {}) lacks kind: skip-mcp-test and
    must NOT satisfy the __mark_complete__ evidence gate.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "SKIP_MCP_TEST.md").write_text("", encoding="utf-8")
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"expected ok=False for content-less SKIP_MCP_TEST.md, got {result}"
        )
        assert result["refused"] is not None and "SKIP_MCP_TEST.md" in result["refused"], (
            f"expected refusal naming SKIP_MCP_TEST.md, got {result!r}"
        )
        assert not (spec_dir / "COMPLETED.md").exists(), (
            "COMPLETED.md was written despite content-less SKIP_MCP_TEST.md — unsafe!"
        )




# ---- Test 12 ----

def test_apply_pseudo_mark_complete_idempotent():
    """A GENUINELY-DONE dir (valid COMPLETED.md receipt + SPEC.md Status already
    Complete, no cleanup sentinels lingering, evidence via a kept
    SKIP_MCP_TEST.md) → noop=True, ok=True, resumed=False, zero writes/deletes.

    mark-complete-partial-apply-noop-unrecoverable: the receipt-EXISTENCE-only
    noop was replaced by a full post-condition audit. A dir with a lingering
    VALIDATED.md + In-progress status is now a crash-window partial-apply RESUME
    (see test_apply_pseudo_mark_complete_resumes_partial_apply), NOT a noop.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Write a valid COMPLETED.md directly (simulates prior completion).
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="test-feature",
            date="2026-06-10",
            provenance="gated",
        )
        # SPEC.md already flipped to Complete; SKIP_MCP_TEST.md is the (kept)
        # evidence so the validation gate passes on the re-run; no VALIDATED.md /
        # RETRO_DONE.md / DEFERRED_NON_CLOUD.md linger → every post-condition met.
        _write_spec_md(spec_dir, status="Complete")
        _write_skip_mcp_test(spec_dir)
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True on noop re-run, got {result}"
        assert result["noop"] is True, f"expected noop=True for a done dir, got {result}"
        assert result.get("resumed") is False, f"expected resumed=False, got {result}"
        assert result["wrote"] == [] and result["deleted"] == [], (
            f"a genuinely-done noop must not write or delete anything: {result}"
        )
        # The kept SKIP_MCP_TEST.md must survive the noop untouched.
        assert (spec_dir / "SKIP_MCP_TEST.md").exists(), (
            "SKIP_MCP_TEST.md was deleted on a noop re-run — must NOT be deleted"
        )




# ---- Crash-window RESUME (mark-complete-partial-apply-noop-unrecoverable) ----

def test_apply_pseudo_mark_complete_resumes_partial_apply():
    """The headline reproduction: a dir left in the EXACT partial state a kill
    between the receipt write (step 3) and the SPEC status flip (step 5)
    produces — COMPLETED.md receipt present, **Status:** In-progress, VALIDATED.md
    still present, queue entry present, ROADMAP row unstruck — must RESUME and
    converge to fully-applied, not noop.

    Pre-fix (regression documentation): the receipt-EXISTENCE-only noop returned
    noop=True with ZERO writes, leaving Status In-progress → the state machine
    re-routed to __mark_complete__ every probe, an unrecoverable loop.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "mcp-testing"
        spec_dir.mkdir(parents=True)
        # Materialize the crash state directly (the partial disk state IS the
        # observable the loop routed on — no crash injection needed).
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="mcp-testing",
            date="2026-06-10",
            provenance="gated",
        )
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n**Status:** In-progress\n\n"
            "### Phase 1\n**Status:** Complete\n- [x] A\n",
            encoding="utf-8",
        )
        _write_validated_md(spec_dir)  # cleanup sentinel not yet deleted
        queue_path = _write_features_queue(repo_root, ["mcp-testing", "other"])
        roadmap_path = repo_root / "docs" / "features" / "ROADMAP.md"
        roadmap_path.write_text(
            "# Roadmap\n\n- mcp-testing: do the thing\n- other: unrelated\n",
            encoding="utf-8",
        )

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="mcp-testing", date="2026-06-10",
        )
        # RESUME, not noop, not refused.
        assert result["ok"] is True, result
        assert result["refused"] is None, result
        assert result.get("resumed") is True, f"expected resumed=True, got {result}"
        assert result["noop"] is False, result
        # Converged to fully-applied on every post-condition.
        spec_text = (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert "**Status:** Complete" in spec_text and "In-progress" not in spec_text, spec_text
        phases_text = (spec_dir / "PHASES.md").read_text(encoding="utf-8")
        assert phases_text.startswith("# Phases\n\n**Status:** Complete"), phases_text
        assert not (spec_dir / "VALIDATED.md").exists(), "VALIDATED.md not cleaned on resume"
        ids = [e["id"] for e in json.loads(queue_path.read_text(encoding="utf-8"))["queue"]]
        assert "mcp-testing" not in ids and "other" in ids, ids
        assert result.get("queue_trimmed") is True, result
        assert lazy_core._ROADMAP_COMPLETE_TOKEN in roadmap_path.read_text(encoding="utf-8"), (
            "ROADMAP row not struck on resume"
        )
        assert result.get("roadmap_struck") is True, result
        # A now-converged dir yields the SANCTIONED post-condition set: further
        # audit finds nothing missing (proves convergence — the loop is broken).
        assert lazy_core._completion_postconditions_missing(
            spec_dir, repo_root, "mcp-testing", "Complete", is_fixed=False
        ) == [], "post-conditions still missing after resume"




def test_apply_pseudo_mark_complete_resume_then_clean_noop():
    """A skip-validated crash window (SKIP_MCP_TEST.md is the KEPT evidence, so it
    survives completion): receipt present, Status In-progress, a lingering
    RETRO_DONE.md cleanup sentinel → RESUME converges (flips status, deletes
    RETRO_DONE, keeps SKIP), and a SECOND invocation is then a clean noop
    (SPEC Fix Scope item 4c)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "skip-feat"
        spec_dir.mkdir(parents=True)
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="skip-feat",
            date="2026-06-10",
            provenance="gated",
        )
        _write_spec_md(spec_dir, status="In-progress")
        _write_skip_mcp_test(spec_dir)  # kept evidence — survives completion
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: skip-feat\ndate: 2026-06-01\n---\n",
            encoding="utf-8",
        )

        first = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="skip-feat", date="2026-06-10",
        )
        assert first.get("resumed") is True, first
        assert first["noop"] is False and first["refused"] is None, first
        assert "**Status:** Complete" in (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert not (spec_dir / "RETRO_DONE.md").exists(), "RETRO_DONE not cleaned"
        assert (spec_dir / "SKIP_MCP_TEST.md").exists(), "kept SKIP evidence wrongly deleted"

        # Second invocation → clean noop, no writes.
        second = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="skip-feat", date="2026-06-10",
        )
        assert second["noop"] is True, f"expected clean noop after convergence, got {second}"
        assert second.get("resumed") is False, second
        assert second["wrote"] == [] and second["deleted"] == [], second




def test_apply_pseudo_mark_fixed_resumes_partial_apply():
    """The bug-pipeline mirror: __mark_fixed__ shares the same apply_pseudo
    branch, so the crash window exists between the FIXED.md receipt and the SPEC
    flip too. FIXED.md present + Status In-progress + a lingering VALIDATED.md →
    RESUME flips Status to Fixed and deletes VALIDATED.md (no feature queue-trim /
    ROADMAP-strike on the bug path); a second call is a clean noop. Uses a kept
    SKIP_MCP_TEST.md so the validation gate still passes after VALIDATED cleanup.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "bugs" / "some-bug"
        spec_dir.mkdir(parents=True)
        lazy_core.write_completed_receipt(
            spec_dir / "FIXED.md",
            feature_id="some-bug",
            date="2026-06-10",
            provenance="gated",
            kind="fixed",
        )
        _write_spec_md(spec_dir, status="In-progress")
        _write_validated_md(spec_dir)   # cleanup sentinel to be deleted on resume
        _write_skip_mcp_test(spec_dir)  # kept evidence so the re-run gate passes

        first = lazy_core.apply_pseudo(
            repo_root, "__mark_fixed__", spec_dir,
            feature_id="some-bug", date="2026-06-10",
        )
        assert first.get("resumed") is True, first
        assert first["noop"] is False and first["refused"] is None, first
        spec_text = (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert "**Status:** Fixed" in spec_text, spec_text
        assert not (spec_dir / "VALIDATED.md").exists(), "VALIDATED not cleaned on fixed resume"
        # The bug path never reports a feature-queue trim / ROADMAP strike.
        assert first.get("queue_trimmed") is False and first.get("roadmap_struck") is False, first

        second = lazy_core.apply_pseudo(
            repo_root, "__mark_fixed__", spec_dir,
            feature_id="some-bug", date="2026-06-10",
        )
        assert second["noop"] is True, f"expected clean noop after fixed convergence, got {second}"
        assert second.get("resumed") is False, second




# ---- Test 14 ----

def test_apply_pseudo_unknown_name_refuses():
    """name='__bogus__' → ok=False, refused is non-None; must not raise an
    uncaught exception (i.e. AttributeError / KeyError must be caught internally).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        result = lazy_core.apply_pseudo(
            Path(td), "__bogus__", spec_dir, date="2026-06-10"
        )
    assert result["ok"] is False, (
        f"expected ok=False for unknown pseudo-skill name, got {result}"
    )
    assert result["refused"] is not None, (
        f"expected non-None refused for unknown name, got {result!r}"
    )




# ---- Test 15 ----

def test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status():
    """A plan whose frontmatter has NO ``status:`` key but whose body contains
    a line ``status: deployed and running`` must be refused — the body line
    must remain byte-unchanged and ``status: Complete`` must NOT appear anywhere
    in the file.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        plans_dir = spec_dir / "plans"
        plans_dir.mkdir(parents=True)
        plan_path = plans_dir / "plan-phase-1.md"
        # Frontmatter has NO ``status:`` key; body contains a line starting
        # ``status:`` which must NOT be mistaken for a frontmatter status.
        plan_path.write_text(
            "---\n"
            "kind: implementation-plan\n"
            "feature_id: test-feature\n"
            "phases:\n"
            "  - 1\n"
            "---\n"
            "\n"
            "# Implementation Plan\n"
            "\n"
            "status: deployed and running\n",
            encoding="utf-8",
        )
        original_content = plan_path.read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            Path(td), "__flip_plan_complete_cloud_saturated__", spec_dir,
            plan_path=plan_path,
            date="2026-06-10",
        )

        # Must be refused — no status: field in frontmatter.
        assert result["ok"] is False, (
            f"expected ok=False (refused) when frontmatter has no status: key, got {result}"
        )
        assert result["refused"] is not None, (
            f"expected non-None refused, got {result!r}"
        )

        # The file must be byte-unchanged — the body line must not have been altered.
        current_content = plan_path.read_text(encoding="utf-8")
        assert current_content == original_content, (
            "plan file was modified even though the pseudo-skill should have refused:\n"
            f"original:\n{original_content}\ncurrent:\n{current_content}"
        )
        # Specifically: the body line must still be present.
        assert "status: deployed and running" in current_content, (
            "body status line was corrupted or removed"
        )
        # And status: Complete must NOT have been injected anywhere.
        assert "status: Complete" not in current_content, (
            "status: Complete was written into the file despite refusing"
        )




def test_apply_pseudo_coherence_autoflips_all_ticked_phases():
    """All-ticked phases carrying a non-Complete Status are auto-flipped to
    Complete in place, the receipt is written, the top-level PHASES/SPEC Status
    are flipped, and every byte OUTSIDE the flipped per-phase Status lines is
    unchanged (byte-compared against the expected post-flip text).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        phase_body = (
            "## Phase 1 — Foundations\n"
            "\n"
            "**Status:** In-progress\n"
            "\n"
            "- [x] Build the thing\n"
            "- [x] Wire it up\n"
            "\n"
            "## Phase 2 — Polish\n"
            "\n"
            "**Status:** In-progress\n"
            "\n"
            "- [x] Finish polish\n"
        )
        phases_path = _write_phases_md(spec_dir, phase_body)

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result}"
        assert result["noop"] is False, f"expected noop=False, got {result}"

        # Receipt written.
        assert (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md was not written"
        # Top-level flips happened.
        assert "**Status:** Complete" in (spec_dir / "SPEC.md").read_text(encoding="utf-8")

        # The flipped phases are reported.
        flipped = result.get("flipped_phases")
        assert flipped is not None, f"expected flipped_phases key in result: {result!r}"
        assert any("Phase 1" in h for h in flipped), f"Phase 1 not reported flipped: {flipped!r}"
        assert any("Phase 2" in h for h in flipped), f"Phase 2 not reported flipped: {flipped!r}"

        # Byte-exact post-flip PHASES body: ONLY the two per-phase Status lines
        # changed In-progress -> Complete; the top-level Status line ALSO flips
        # (existing __mark_complete__ behavior). Every other byte is identical.
        expected_phases_text = (
            "# PHASES — Test Feature\n"
            "\n"
            "**Status:** Complete\n"   # top-level flip (count=1 sub)
            "\n"
            "## Phase 1 — Foundations\n"
            "\n"
            "**Status:** Complete\n"   # auto-flip
            "\n"
            "- [x] Build the thing\n"
            "- [x] Wire it up\n"
            "\n"
            "## Phase 2 — Polish\n"
            "\n"
            "**Status:** Complete\n"   # auto-flip
            "\n"
            "- [x] Finish polish\n"
        )
        actual = phases_path.read_text(encoding="utf-8")
        assert actual == expected_phases_text, (
            "PHASES.md body diverged from the expected per-phase-flip-only result:\n"
            f"--- expected ---\n{expected_phases_text!r}\n--- actual ---\n{actual!r}"
        )




def test_apply_pseudo_coherence_refuses_unchecked_verification_row():
    """A phase whose Runtime Verification row is still unchecked at completion
    time → REFUSE: no COMPLETED.md, no top-level Status flip, and VALIDATED.md
    (a sentinel that would normally be deleted) is left untouched. The refusal
    message names the offending phase.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        phase_body = (
            "## Phase 1 — Foundations\n"
            "\n"
            "**Status:** Complete\n"
            "\n"
            "- [x] Build the thing\n"
            "\n"
            "**Runtime Verification:**\n"
            "- [ ] mcp dropout check (still pending)\n"
        )
        _write_phases_md(spec_dir, phase_body)

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, f"expected ok=False (refused), got {result}"
        assert result["refused"] is not None, f"expected non-None refused, got {result!r}"
        assert "Phase 1" in result["refused"], (
            f"refusal should name the offending phase, got: {result['refused']!r}"
        )
        assert result["wrote"] == [], f"expected wrote=[], got {result['wrote']}"
        assert result["deleted"] == [], f"expected deleted=[], got {result['deleted']}"
        # ZERO writes: no receipt, no top-level flip, no sentinel deletion.
        assert not (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md written despite refusal"
        assert "**Status:** In-progress" in (spec_dir / "SPEC.md").read_text(encoding="utf-8"), (
            "SPEC.md status flipped despite the refusal"
        )
        assert (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was deleted despite the refusal — must be untouched"
        )




def test_apply_pseudo_coherence_advisory_prints_genuine_row_excerpts():
    """completion-gate-refusal-opacity Fix Scope §2: the coherence-gate
    refusal's advisory previously printed the shim-row excerpts but only a
    COUNT for genuine rows (the list was collected and discarded). Now both
    classes carry line-numbered excerpts in the refusal message."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        phase_body = (
            "## Phase 1 — Foundations\n"
            "\n"
            "**Status:** Complete\n"
            "\n"
            "**Deliverables:**\n"
            "- [ ] genuinely incomplete deliverable\n"
            "\n"
            "**Runtime Verification:**\n"
            "- [ ] mcp dropout check (still pending)\n"
        )
        _write_phases_md(spec_dir, phase_body)

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, f"expected ok=False (refused), got {result}"
        refused = result["refused"] or ""
        assert "Genuine rows:" in refused, (
            f"expected the genuine-row excerpts to be printed, not just the "
            f"count: {refused!r}"
        )
        assert "genuinely incomplete deliverable" in refused, refused
        # Both classes carry a line-number prefix (Fix Scope §2).
        assert re.search(r"L\d+: .*genuinely incomplete deliverable", refused), refused
        assert "Shim rows:" in refused, refused
        assert re.search(r"L\d+: .*mcp dropout check", refused), refused




def test_apply_pseudo_coherence_refuses_zero_checkbox_in_progress_phase():
    """A zero-checkbox phase carrying ``**Status:** In-progress`` has no mechanical
    flip signal → REFUSE (the refusal names the phase + the bad status).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        phase_body = (
            "## Phase 1 — Empty but in-progress\n"
            "\n"
            "**Status:** In-progress\n"
            "\n"
            "Some prose, no checkboxes.\n"
        )
        _write_phases_md(spec_dir, phase_body)

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, f"expected ok=False (refused), got {result}"
        assert result["refused"] is not None, f"expected non-None refused, got {result!r}"
        assert "Phase 1" in result["refused"], (
            f"refusal should name the offending phase, got: {result['refused']!r}"
        )
        assert not (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md written despite refusal"




def test_apply_pseudo_coherence_superseded_phase_with_unchecked_not_refused():
    """A Superseded phase is terminal: its unchecked boxes are acceptable (the
    repo checker's complete-but-unchecked / spec-complete-phases-not rules accept
    Superseded). So a Superseded phase with unchecked rows does NOT refuse and is
    NOT flipped — completion proceeds.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        phase_body = (
            "## Phase 1 — Done\n"
            "\n"
            "**Status:** Complete\n"
            "\n"
            "- [x] real item\n"
            "\n"
            "## Phase 2 — Abandoned\n"
            "\n"
            "**Status:** Superseded\n"
            "\n"
            "- [ ] never finished, superseded by Phase 1\n"
        )
        phases_path = _write_phases_md(spec_dir, phase_body)
        before = phases_path.read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True (Superseded is terminal), got {result}"
        assert result["refused"] is None, f"expected refused=None, got {result!r}"
        assert (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md not written"
        # The Superseded phase's Status line must NOT have been flipped to Complete.
        after = phases_path.read_text(encoding="utf-8")
        assert "**Status:** Superseded" in after, (
            "Superseded phase status was altered — it must remain Superseded"
        )
        # No phase should be reported as flipped (Phase 1 already Complete; Phase 2
        # Superseded and untouched).
        assert not result.get("flipped_phases"), (
            f"no phase should have been flipped, got: {result.get('flipped_phases')!r}"
        )
        # Sanity: only the top-level Status flipped relative to `before`.
        assert before.replace("**Status:** In-progress", "**Status:** Complete", 1) == after, (
            "more than the top-level Status line changed"
        )




def test_apply_pseudo_coherence_mark_fixed_refuses_on_unchecked():
    """The same coherence refusal applies to the bug pipeline's __mark_fixed__:
    an unchecked non-Superseded phase → refuse, no FIXED.md, no flips.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="Investigating")
        phase_body = (
            "## Phase 1 — Repro + fix\n"
            "\n"
            "**Status:** In-progress\n"
            "\n"
            "- [x] reproduce\n"
            "- [ ] land the fix\n"
        )
        _write_phases_md(spec_dir, phase_body)

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_fixed__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, f"expected ok=False (refused), got {result}"
        assert result["refused"] is not None and "Phase 1" in result["refused"], (
            f"expected refusal naming Phase 1, got {result!r}"
        )
        assert not (spec_dir / "FIXED.md").exists(), "FIXED.md written despite refusal"
        assert (spec_dir / "VALIDATED.md").exists(), "VALIDATED.md deleted despite refusal"




def test_apply_pseudo_coherence_no_phases_md_preserves_behavior():
    """When PHASES.md is ABSENT the coherence gate is a no-op — the existing
    __mark_complete__ behavior (receipt + SPEC flip) is preserved.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # Deliberately no PHASES.md.
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True (no PHASES.md), got {result}"
        assert (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md not written"




def test_apply_pseudo_coherence_no_status_phase_all_checked_proceeds():
    """A phase with NO Status line whose boxes are all checked is ignored by the
    status-straggler check (canonical-null = non-straggler, matching the repo
    checker) — and having no unchecked boxes, it does not trip the box rule
    either. Completion proceeds; the phase is NOT auto-flipped (no Status line to
    flip).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        _write_phases_md(
            spec_dir,
            "## Phase 1 — No status, all done\n\n- [x] item a\n- [x] item b\n",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md not written"
        assert not result.get("flipped_phases"), (
            f"no-status phase should not be flipped, got {result.get('flipped_phases')!r}"
        )




def test_apply_pseudo_coherence_no_status_phase_with_unchecked_still_refuses():
    """JUDGMENT CALL (completeness-first / D7): a phase with NO Status line but an
    UNCHECKED box still refuses. The deliverable's box rule says "any phase with
    >=1 unchecked checkbox" refuses; the no-status "ignore" carve-out applies
    only to the status-straggler check (canonical-null is a non-straggler), not
    to genuinely-incomplete deliverables. The stricter option is chosen so a
    feature cannot be completed with visibly-unfinished work hiding under a
    status-less phase.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        _write_phases_md(
            spec_dir,
            "## Phase 1 — No status, not done\n\n- [x] done\n- [ ] NOT done\n",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, f"expected ok=False (refused), got {result}"
        assert "Phase 1" in (result["refused"] or ""), (
            f"refusal should name the offending phase, got {result['refused']!r}"
        )
        assert not (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md written despite refusal"




def test_apply_pseudo_coherence_descoped_phase_completes():
    """End-to-end: __mark_complete__ writes the receipt for a feature whose only
    remaining unchecked rows are descoped (the deadlock is broken at the ship
    seam, not just in the unit predicate)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        _write_phases_md(
            spec_dir,
            "## Phase 1 — done\n\n**Status:** Complete\n\n- [x] real\n\n"
            + _DESCOPED_PHASE_4,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True (descoped exempt), got {result}"
        assert result["refused"] is None, f"expected no refusal, got {result!r}"
        assert (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md not written"




def test_apply_pseudo_coherence_mark_fixed_descoped_phase_completes():
    """Bug-pipeline mirror: __mark_fixed__ likewise completes a descoped-phase
    PHASES.md (the fix lives in shared lazy_core, so both pipelines inherit it)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="Investigating")
        _write_phases_md(
            spec_dir,
            "## Phase 1 — repro+fix\n\n**Status:** Complete\n\n- [x] fixed\n\n"
            + _DESCOPED_PHASE_4,
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_fixed__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert (spec_dir / "FIXED.md").exists(), "FIXED.md not written"




# --- completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo -----------
# A legitimately-DEFERRED verification-only row in a no-MCP structural-skip repo
# completes with an honest RUNTIME_GATES.md ledger (the row stays `- [ ]`), while
# every strict case (genuine row, app repo, kill-switch) still refuses.

def _pseudo_write_structural_skip(spec_dir: Path) -> None:
    (spec_dir / "SKIP_MCP_TEST.md").write_text(
        "---\nkind: skip-mcp-test\nfeature_id: test-feature\n"
        "reason: repo has no MCP-reachable surface\ndate: 2026-07-14\n"
        "skipped_by: pipeline\ngranted_by: pipeline-structural\n"
        "spec_class: standalone — no app surface\n---\n\n# Skip (structural)\n",
        encoding="utf-8",
    )


_DEFERRED_PHASES_BODY = (
    "# Phases\n\n"
    "### Phase 1: Impl\n\n**Status:** Complete\n\n- [x] implementation done\n\n"
    "### Phase 2: Validation\n\n**Status:** In-progress\n\n- [x] validated\n\n"
    "**Runtime Verification** *(deferred — closed outside /execute-plan)*:\n"
    "- [ ] <!-- verification-only --> Cloud compatibility run — closed by the "
    "first cloud-session run\n"
)


def test_apply_pseudo_deferred_runtime_row_completes_on_structural_skip():
    """The new route: a no-MCP structural-skip feature with a DEFERRED
    verification-only row completes — receipt written, RUNTIME_GATES.md ledgered,
    runtime_gates_pending surfaced, and the deferred row is NOT ticked (stays
    `- [ ]`; the ledger is the honest tracker)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)  # no src-tauri/, no package.json → no app surface
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _pseudo_write_structural_skip(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(_DEFERRED_PHASES_BODY, encoding="utf-8")

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir, date="2026-07-14"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert result["refused"] is None, f"expected no refusal, got {result!r}"
        assert (spec_dir / "COMPLETED.md").exists(), "COMPLETED.md not written"
        assert result["runtime_gates_pending"] == 1, (
            f"expected 1 pending runtime gate, got {result.get('runtime_gates_pending')}"
        )
        # The ledger exists and is the honest tracker.
        ledger = spec_dir / "RUNTIME_GATES.md"
        assert ledger.exists(), "RUNTIME_GATES.md was not written"
        assert "MANUAL RUNTIME GATES PENDING" in ledger.read_text(encoding="utf-8")
        # The deferred row is NOT ticked — it stays `- [ ]` (auto_ticked stayed 0).
        assert result["auto_ticked_rows"] == 0, (
            f"deferred rows must NOT be auto-ticked, got {result['auto_ticked_rows']}"
        )
        phases_after = (spec_dir / "PHASES.md").read_text(encoding="utf-8")
        assert "- [ ] <!-- verification-only -->" in phases_after, (
            "the deferred verification-only row must remain unchecked (deferred, "
            "not certified)"
        )


def test_apply_pseudo_deferred_runtime_mark_fixed_completes_on_structural_skip():
    """Bug-pipeline mirror: __mark_fixed__ inherits the exemption via shared
    lazy_core (no script mirror owed) — a deferred verification-only row in a
    no-MCP repo completes with FIXED.md + RUNTIME_GATES.md."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _pseudo_write_structural_skip(spec_dir)
        _write_spec_md(spec_dir, status="Investigating")
        (spec_dir / "PHASES.md").write_text(_DEFERRED_PHASES_BODY, encoding="utf-8")

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_fixed__", spec_dir, date="2026-07-14"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        assert (spec_dir / "FIXED.md").exists(), "FIXED.md not written"
        assert (spec_dir / "RUNTIME_GATES.md").exists(), "ledger not written"


def test_apply_pseudo_deferred_runtime_genuine_impl_row_still_refuses():
    """NON-REGRESSION: a structural skip does NOT exempt a genuine unchecked
    implementation row (no verification-only marker) — completion still refuses
    naming the offending phase."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _pseudo_write_structural_skip(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1: Impl\n\n**Status:** In-progress\n\n"
            "- [x] one done\n"
            "- [ ] genuine implementation NOT done\n"
            "- [ ] <!-- verification-only --> deferred cloud run\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir, date="2026-07-14"
        )
        assert result["ok"] is False, f"expected refusal, got {result}"
        assert "Phase 1" in (result["refused"] or ""), result
        assert not (spec_dir / "COMPLETED.md").exists()


def test_apply_pseudo_deferred_runtime_no_exemption_in_app_repo():
    """NON-REGRESSION: a verification-only row in an APP repo (package.json
    present) does NOT complete on this route — the structural waiver re-verifies
    False, so the deferred exemption never fires and completion refuses (real MCP
    evidence is still required there)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        (repo_root / "package.json").write_text("{}\n", encoding="utf-8")
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _pseudo_write_structural_skip(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(_DEFERRED_PHASES_BODY, encoding="utf-8")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir, date="2026-07-14"
        )
        assert result["ok"] is False, f"expected refusal in an app repo, got {result}"
        assert not (spec_dir / "RUNTIME_GATES.md").exists(), (
            "the ledger must NOT be written when the exemption does not apply"
        )


def test_apply_pseudo_deferred_runtime_killswitch_restores_strict():
    """The kill-switch (LAZY_STRICT_EVIDENCE_GATE) disables the deferred-runtime
    exemption too — frictionless rollback to the strict path: the deferred row
    blocks and no ledger is written."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _pseudo_write_structural_skip(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(_DEFERRED_PHASES_BODY, encoding="utf-8")
        _os.environ["LAZY_STRICT_EVIDENCE_GATE"] = "1"
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir, date="2026-07-14"
            )
        finally:
            _os.environ.pop("LAZY_STRICT_EVIDENCE_GATE", None)
        assert result["ok"] is False, f"kill-switch must restore strict, got {result}"
        assert not (spec_dir / "RUNTIME_GATES.md").exists()




def test_apply_pseudo_coherence_idempotent_skips_check_when_receipted():
    """Idempotency takes precedence over the coherence check: a receipted dir
    NEVER re-refuses on an incoherent PHASES.md. mark-complete-partial-apply-
    noop-unrecoverable: a receipt with a lingering VALIDATED.md + In-progress
    PHASES is now a crash-window RESUME (the coherence gate is SKIPPED on resume,
    so the incoherent unchecked row can NOT cause a re-refusal) — the load-bearing
    property (receipt beats coherence re-check) is preserved via resume-not-noop.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        # Pre-existing valid receipt.
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="test-feature",
            date="2026-06-10",
            provenance="gated",
        )
        _write_validated_md(spec_dir)
        # An INCOHERENT PHASES.md (unchecked row) that WOULD refuse on a fresh run.
        _write_phases_md(
            spec_dir,
            "## Phase 1\n\n**Status:** In-progress\n\n- [ ] still pending\n",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True, got {result}"
        # Never re-refuses despite the incoherent PHASES (coherence skipped on resume).
        assert result["refused"] is None, f"expected refused=None, got {result!r}"
        assert result.get("resumed") is True, (
            f"expected a resume (receipt + lingering VALIDATED + In-progress), got {result}"
        )




# ---------------------------------------------------------------------------
# Tests: neutralize_sentinel — WU-3 rename-to-resolved helper
# ---------------------------------------------------------------------------

def test_neutralize_sentinel_basic_rename():
    """NEEDS_INPUT.md present, no collision → renames to NEEDS_INPUT_RESOLVED_2026-06-10.md.

    Asserts:
    - ok is True
    - renamed_to == "NEEDS_INPUT_RESOLVED_2026-06-10.md"
    - renamed_from == "NEEDS_INPUT.md"
    - collision_suffix is None
    - new file exists at the resolved path
    - original NEEDS_INPUT.md is gone
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "NEEDS_INPUT.md"
        src.write_text("needs input content\n", encoding="utf-8")

        result = lazy_core.neutralize_sentinel(src, date="2026-06-10")

        resolved = d / "NEEDS_INPUT_RESOLVED_2026-06-10.md"
        src_gone = not src.exists()
        resolved_exists = resolved.exists()

    assert result["ok"] is True, f"expected ok=True, got {result}"
    assert result["renamed_to"] == "NEEDS_INPUT_RESOLVED_2026-06-10.md", (
        f"expected renamed_to='NEEDS_INPUT_RESOLVED_2026-06-10.md', got {result['renamed_to']!r}"
    )
    assert result["renamed_from"] == "NEEDS_INPUT.md", (
        f"expected renamed_from='NEEDS_INPUT.md', got {result['renamed_from']!r}"
    )
    assert result["collision_suffix"] is None, (
        f"expected collision_suffix=None, got {result['collision_suffix']!r}"
    )
    assert resolved_exists, "NEEDS_INPUT_RESOLVED_2026-06-10.md was not created"
    assert src_gone, "original NEEDS_INPUT.md still exists after rename"




def test_neutralize_sentinel_refuses_when_absent():
    """Path to a non-existent file → ok=False, refused non-None, no file created.

    The function must NOT create any file when the source path does not exist.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        missing = d / "NEEDS_INPUT.md"
        # Confirm precondition: file does not exist.
        assert not missing.exists(), "pre-condition: NEEDS_INPUT.md must not exist"

        result = lazy_core.neutralize_sentinel(missing, date="2026-06-10")

        files_after = list(d.iterdir())

    assert result["ok"] is False, f"expected ok=False for absent path, got {result}"
    assert result["refused"] is not None, (
        f"expected refused to be non-None for absent path, got {result['refused']!r}"
    )
    assert result["renamed_from"] is None, (
        f"expected renamed_from=None for absent path, got {result['renamed_from']!r}"
    )
    assert result["renamed_to"] is None, (
        f"expected renamed_to=None for absent path, got {result['renamed_to']!r}"
    )
    assert result["collision_suffix"] is None, (
        f"expected collision_suffix=None for absent path, got {result['collision_suffix']!r}"
    )
    assert files_after == [], (
        f"no files should have been created in temp dir, found: {files_after}"
    )




def test_neutralize_sentinel_collision_appends_suffix():
    """NEEDS_INPUT.md present AND NEEDS_INPUT_RESOLVED_2026-06-10.md already exists.

    The function MUST NOT clobber the pre-existing resolved file.
    It must rename to NEEDS_INPUT_RESOLVED_2026-06-10_2.md instead.

    Asserts:
    - ok is True
    - renamed_to == "NEEDS_INPUT_RESOLVED_2026-06-10_2.md"
    - collision_suffix == 2
    - the _2 file's content is "NEW" (the original NEEDS_INPUT.md content)
    - NEEDS_INPUT_RESOLVED_2026-06-10.md still contains exactly "OLD-PRESERVE-ME" (not clobbered)
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "NEEDS_INPUT.md"
        src.write_text("NEW", encoding="utf-8")
        pre_existing = d / "NEEDS_INPUT_RESOLVED_2026-06-10.md"
        pre_existing.write_text("OLD-PRESERVE-ME", encoding="utf-8")

        result = lazy_core.neutralize_sentinel(src, date="2026-06-10")

        resolved_2 = d / "NEEDS_INPUT_RESOLVED_2026-06-10_2.md"
        resolved_2_exists = resolved_2.exists()
        resolved_2_content = resolved_2.read_text(encoding="utf-8") if resolved_2_exists else None
        pre_existing_content = pre_existing.read_text(encoding="utf-8")

    assert result["ok"] is True, f"expected ok=True, got {result}"
    assert result["renamed_to"] == "NEEDS_INPUT_RESOLVED_2026-06-10_2.md", (
        f"expected renamed_to='NEEDS_INPUT_RESOLVED_2026-06-10_2.md', got {result['renamed_to']!r}"
    )
    assert result["collision_suffix"] == 2, (
        f"expected collision_suffix=2, got {result['collision_suffix']!r}"
    )
    assert resolved_2_exists, "NEEDS_INPUT_RESOLVED_2026-06-10_2.md was not created"
    assert resolved_2_content == "NEW", (
        f"_2 file content should be 'NEW' (original NEEDS_INPUT content), got {resolved_2_content!r}"
    )
    assert pre_existing_content == "OLD-PRESERVE-ME", (
        f"pre-existing NEEDS_INPUT_RESOLVED_2026-06-10.md was clobbered! "
        f"content is now {pre_existing_content!r}, expected 'OLD-PRESERVE-ME'"
    )




def test_neutralize_sentinel_double_collision_increments():
    """Both ..._2026-06-10.md AND ..._2026-06-10_2.md already exist → renames to ..._2026-06-10_3.md.

    Asserts:
    - ok is True
    - renamed_to == "NEEDS_INPUT_RESOLVED_2026-06-10_3.md"
    - collision_suffix == 3
    - both prior files are untouched (content preserved)
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "NEEDS_INPUT.md"
        src.write_text("NEWEST", encoding="utf-8")
        prior_1 = d / "NEEDS_INPUT_RESOLVED_2026-06-10.md"
        prior_1.write_text("FIRST-RESOLVED", encoding="utf-8")
        prior_2 = d / "NEEDS_INPUT_RESOLVED_2026-06-10_2.md"
        prior_2.write_text("SECOND-RESOLVED", encoding="utf-8")

        result = lazy_core.neutralize_sentinel(src, date="2026-06-10")

        resolved_3 = d / "NEEDS_INPUT_RESOLVED_2026-06-10_3.md"
        resolved_3_exists = resolved_3.exists()
        prior_1_content = prior_1.read_text(encoding="utf-8")
        prior_2_content = prior_2.read_text(encoding="utf-8")

    assert result["ok"] is True, f"expected ok=True, got {result}"
    assert result["renamed_to"] == "NEEDS_INPUT_RESOLVED_2026-06-10_3.md", (
        f"expected renamed_to='NEEDS_INPUT_RESOLVED_2026-06-10_3.md', got {result['renamed_to']!r}"
    )
    assert result["collision_suffix"] == 3, (
        f"expected collision_suffix=3, got {result['collision_suffix']!r}"
    )
    assert resolved_3_exists, "NEEDS_INPUT_RESOLVED_2026-06-10_3.md was not created"
    assert prior_1_content == "FIRST-RESOLVED", (
        f"prior _1 file was mutated; expected 'FIRST-RESOLVED', got {prior_1_content!r}"
    )
    assert prior_2_content == "SECOND-RESOLVED", (
        f"prior _2 file was mutated; expected 'SECOND-RESOLVED', got {prior_2_content!r}"
    )




def test_neutralize_sentinel_refuses_already_resolved():
    """Calling neutralize_sentinel on an already-resolved file is refused.

    A file whose basename already contains '_RESOLVED_' must not be double-neutralized.

    Asserts:
    - ok is False
    - refused is non-None
    - the file still exists at its original path (not renamed)
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        already_resolved = d / "BLOCKED_RESOLVED_2026-06-09.md"
        already_resolved.write_text("already resolved content\n", encoding="utf-8")

        result = lazy_core.neutralize_sentinel(already_resolved, date="2026-06-10")

        still_exists = already_resolved.exists()

    assert result["ok"] is False, (
        f"expected ok=False when path already contains '_RESOLVED_', got {result}"
    )
    assert result["refused"] is not None, (
        f"expected refused to be non-None for already-resolved path, got {result['refused']!r}"
    )
    assert still_exists, (
        "BLOCKED_RESOLVED_2026-06-09.md was renamed/deleted — must stay at its original path"
    )




def test_neutralize_sentinel_blocked_form():
    """BLOCKED.md → BLOCKED_RESOLVED_2026-06-10.md (canonical stem + extension preserved).

    Asserts:
    - ok is True
    - renamed_to == "BLOCKED_RESOLVED_2026-06-10.md"
    - original BLOCKED.md is gone
    - new file exists
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "BLOCKED.md"
        src.write_text("blocked content\n", encoding="utf-8")

        result = lazy_core.neutralize_sentinel(src, date="2026-06-10")

        resolved = d / "BLOCKED_RESOLVED_2026-06-10.md"
        resolved_exists = resolved.exists()
        src_gone = not src.exists()

    assert result["ok"] is True, f"expected ok=True, got {result}"
    assert result["renamed_to"] == "BLOCKED_RESOLVED_2026-06-10.md", (
        f"expected renamed_to='BLOCKED_RESOLVED_2026-06-10.md', got {result['renamed_to']!r}"
    )
    assert resolved_exists, "BLOCKED_RESOLVED_2026-06-10.md was not created"
    assert src_gone, "original BLOCKED.md still exists after rename"




# ---------------------------------------------------------------------------
# Tests: archive_fixed — scripted __mark_fixed__ archive mechanics
# (mark-fixed-archive.md Steps 1–5, moved from prose to code after the
# 2026-06-10 incident: unstaged sentinel deletions broke `git mv`, a Windows
# lock broke the rename, and a repo-wide grep crawled node_modules).
# ---------------------------------------------------------------------------

def _make_fixed_bug_repo(td: str, *, receipt: bool = True,
                         status: str = "Fixed") -> tuple:
    """Build a real git repo with a committed docs/bugs/my-bug/ directory,
    an inbound reference, and a queue.json entry. Returns (repo_root, bug_dir).
    """
    repo_root, _origin = _make_git_repo_with_origin(td)
    bug_dir = repo_root / "docs" / "bugs" / "my-bug"
    bug_dir.mkdir(parents=True)
    (bug_dir / "SPEC.md").write_text(
        "# My Bug — Bug Specification\n\n"
        f"**Status:** {status}\n\n"
        "**Severity:** P2 (nuisance)\n\n"
        "**Discovered:** 2026-06-01\n\n"
        "## Description\n\nA bug.\n",
        encoding="utf-8",
    )
    if receipt:
        (bug_dir / "FIXED.md").write_text(
            "---\n"
            "kind: fixed\n"
            "feature_id: my-bug\n"
            "date: 2026-06-10\n"
            "provenance: gated\n"
            "---\n\n# Fixed\n",
            encoding="utf-8",
        )
    # A sentinel that apply_pseudo would later DELETE without staging — the
    # exact precondition that broke the prose `git mv`.
    (bug_dir / "VALIDATED.md").write_text(
        "---\nkind: validated\nfeature_id: my-bug\ndate: 2026-06-09\n---\n",
        encoding="utf-8",
    )
    # Inbound root-relative reference from another doc.
    (repo_root / "docs" / "bugs" / "CLAUDE.md").write_text(
        "# Bugs\n\nSee docs/bugs/my-bug/SPEC.md for details.\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "bugs" / "queue.json").write_text(
        json.dumps({"queue": [
            {"id": "my-bug", "name": "My Bug", "spec_dir": "my-bug",
             "severity": "P2"},
            {"id": "other-bug", "name": "Other Bug", "spec_dir": "other-bug",
             "severity": "P1"},
        ]}, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                    "add bug files"], check=True, capture_output=True)
    return repo_root, bug_dir




def test_archive_fixed_happy_path_with_unstaged_deletion():
    """End-to-end: archive succeeds even with an UNSTAGED tracked-file deletion
    inside the bug dir (the 2026-06-10 `git mv` failure), repoints the inbound
    reference, trims queue.json, adds the evidence header lines, and commits."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, bug_dir = _make_fixed_bug_repo(td)
        # Simulate apply_pseudo's post-commit sentinel deletion (unstaged).
        (bug_dir / "VALIDATED.md").unlink()

        result = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")

        assert result["ok"] is True, f"expected ok, got {result}"
        assert result["archived_to"] == "docs/bugs/_archive/my-bug"
        dest = repo_root / "docs" / "bugs" / "_archive" / "my-bug"
        assert dest.exists() and not bug_dir.exists()
        assert (dest / "FIXED.md").exists()
        assert not (dest / "VALIDATED.md").exists(), (
            "the unstaged deletion must be honored, not resurrected"
        )
        # Evidence header lines, in canonical order after **Discovered:**.
        spec_text = (dest / "SPEC.md").read_text(encoding="utf-8")
        assert "**Fixed:** 2026-06-10" in spec_text
        assert "**Fix commit:** " in spec_text
        assert spec_text.index("**Discovered:**") < spec_text.index("**Fixed:**")
        # Inbound reference repointed.
        claude_md = (repo_root / "docs" / "bugs" / "CLAUDE.md").read_text(
            encoding="utf-8")
        assert "docs/bugs/_archive/my-bug/SPEC.md" in claude_md
        assert "docs/bugs/my-bug/SPEC.md" not in claude_md
        assert "docs/bugs/CLAUDE.md" in result["repointed"]
        # Queue trimmed — other entries intact.
        queue = json.loads((repo_root / "docs" / "bugs" / "queue.json")
                           .read_text(encoding="utf-8"))
        ids = [e["id"] for e in queue["queue"]]
        assert ids == ["other-bug"]
        assert result["queue_removed"] is True
        # Committed, clean tree.
        assert result["committed"]
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True, text=True,
        )
        assert status.stdout.strip() == "", (
            f"expected clean tree, got: {status.stdout}"
        )
        # Canonical commit message.
        log = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%s"],
            capture_output=True, text=True,
        )
        assert log.stdout.strip() == (
            "fix(my-bug): mark fixed and archive — FIXED.md receipt gated"
        )




def test_archive_fixed_refuses_without_receipt():
    """No FIXED.md and SPEC not Won't-fix → refused, nothing moved."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, bug_dir = _make_fixed_bug_repo(td, receipt=False)
        result = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")
        assert result["ok"] is False
        assert "FIXED.md" in result["refused"]
        assert bug_dir.exists(), "refusal must not move anything"




def test_archive_fixed_wont_fix_archives_without_receipt():
    """Won't-fix bugs are receipt-EXEMPT (mark-fixed-archive.md) — archived
    with no FIXED.md and no evidence header lines."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, bug_dir = _make_fixed_bug_repo(
            td, receipt=False, status="Won't-fix")
        result = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")
        assert result["ok"] is True, f"expected ok, got {result}"
        dest = repo_root / "docs" / "bugs" / "_archive" / "my-bug"
        assert dest.exists() and not bug_dir.exists()
        spec_text = (dest / "SPEC.md").read_text(encoding="utf-8")
        assert "**Fix commit:**" not in spec_text, (
            "Won't-fix carries no fix-commit evidence"
        )




def test_archive_fixed_collision_appends_suffix():
    """A same-name directory already in _archive/ → -archived-<date> suffix."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, bug_dir = _make_fixed_bug_repo(td)
        prior = repo_root / "docs" / "bugs" / "_archive" / "my-bug"
        prior.mkdir(parents=True)
        (prior / "SPEC.md").write_text("# Old duplicate\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "prior archive"], check=True, capture_output=True)

        result = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")

        assert result["ok"] is True, f"expected ok, got {result}"
        assert result["archived_to"] == (
            "docs/bugs/_archive/my-bug-archived-2026-06-10"
        )
        assert (repo_root / "docs" / "bugs" / "_archive" /
                "my-bug-archived-2026-06-10" / "FIXED.md").exists()
        # Inbound refs repoint to the ACTUAL (suffixed) destination.
        claude_md = (repo_root / "docs" / "bugs" / "CLAUDE.md").read_text(
            encoding="utf-8")
        assert "docs/bugs/_archive/my-bug-archived-2026-06-10/SPEC.md" in claude_md




def test_archive_fixed_rerun_is_noop():
    """A second run after a fully-completed archive is ok+noop (no new commit)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, bug_dir = _make_fixed_bug_repo(td)
        first = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")
        assert first["ok"] is True
        sha_before = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

        second = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")

        assert second["ok"] is True, f"expected ok, got {second}"
        assert second["noop"] is True
        sha_after = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()
        assert sha_before == sha_after, "noop re-run must not create a commit"




def test_archive_fixed_resume_after_partial_move():
    """If a prior run moved the directory but died before repoint/commit,
    re-running resumes: repoints, trims the queue, and commits."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, bug_dir = _make_fixed_bug_repo(td)
        # Simulate the partial state: the mv happened, nothing else did.
        archive_parent = repo_root / "docs" / "bugs" / "_archive"
        archive_parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "-C", str(repo_root), "mv", str(bug_dir),
             str(archive_parent / "my-bug")],
            check=True, capture_output=True,
        )

        result = lazy_core.archive_fixed(repo_root, bug_dir, date="2026-06-10")

        assert result["ok"] is True, f"expected ok, got {result}"
        assert result["archived_to"] == "docs/bugs/_archive/my-bug"
        claude_md = (repo_root / "docs" / "bugs" / "CLAUDE.md").read_text(
            encoding="utf-8")
        assert "docs/bugs/_archive/my-bug/SPEC.md" in claude_md
        assert result["queue_removed"] is True
        assert result["committed"]
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True, text=True,
        )
        assert status.stdout.strip() == ""




def test_archive_fixed_accepts_relative_spec_path():
    """Regression (archive-fixed-relative-spec-path-valueerror): archive_fixed
    must accept a REPO-RELATIVE spec_path (the `docs/bugs/<id>` form the CLI
    passes straight through as `Path(args.archive_fixed)`) against an absolute
    repo_root, anchoring it at repo_root — NOT crash with an uncaught ValueError
    from `spec_path.relative_to(repo_root)` (gates.py:2104) nor refuse "nothing to
    archive" because a CWD-anchored relative path does not exist.

    Red before the fix: `spec_path` was used un-normalized while repo_root was
    resolved to absolute, so a relative `spec_path` either (a) raised ValueError in
    the per-file git-mv fallback, or (b) — as here, with CWD != repo_root — resolved
    to a non-existent directory and refused. Green after: spec_path is anchored at
    repo_root and the archive completes exactly as the absolute-path invocation."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _bug_dir = _make_fixed_bug_repo(td)
        # The CLI passes the repo-relative dir through un-resolved; repo_root is
        # absolute. Deliberately do NOT chdir into repo_root, so a CWD-anchored
        # relative path would miss — proving the anchor is repo_root, not CWD.
        rel_spec = Path("docs/bugs/my-bug")

        result = lazy_core.archive_fixed(repo_root, rel_spec, date="2026-06-10")

        assert result["ok"] is True, f"expected ok, got {result}"
        assert result["archived_to"] == "docs/bugs/_archive/my-bug"
        dest = repo_root / "docs" / "bugs" / "_archive" / "my-bug"
        assert dest.exists() and not (repo_root / "docs" / "bugs" / "my-bug").exists()
        assert result["queue_removed"] is True
        assert result["committed"]
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True, text=True,
        )
        assert status.stdout.strip() == "", (
            f"expected clean tree, got: {status.stdout}"
        )




# ---- validation_escalation() unit tests (shared predicate) ----

def test_validation_escalation_retry_1_not_escalated():
    """blocker_kind mcp-validation + retry_count 1 → below the threshold, no escalation."""
    _guard()
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": 1}
    ) is False




def test_validation_escalation_retry_2_escalated():
    """blocker_kind mcp-validation + retry_count 2 → escalation fires (>= 2)."""
    _guard()
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": 2}
    ) is True
    # And anything above the threshold also escalates.
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": 3}
    ) is True




def test_validation_escalation_other_blocker_kind_not_escalated():
    """retry_count 3 but a NON-mcp-validation blocker_kind → never escalates.

    The escalation policy is specific to repeated MCP-validation failures (the
    d8 serial-discovery pattern); other blocker kinds retrying is normal flow.
    """
    _guard()
    assert lazy_core.validation_escalation(
        {"blocker_kind": "pre-research-input-required", "retry_count": 3}
    ) is False




def test_validation_escalation_missing_fields_not_escalated():
    """Missing blocker_kind / missing retry_count / malformed retry_count →
    no escalation (backward compatibility with pre-Phase-11 sentinels)."""
    _guard()
    # Missing blocker_kind entirely.
    assert lazy_core.validation_escalation({"retry_count": 5}) is False
    # Missing retry_count entirely.
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation"}
    ) is False
    # Malformed retry_count (non-numeric string).
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": "many"}
    ) is False
    # None meta (defensive caller convenience).
    assert lazy_core.validation_escalation(None) is False
    # Empty meta.
    assert lazy_core.validation_escalation({}) is False




def test_validation_escalation_string_digit_retry_count():
    """retry_count as a string of digits is tolerated ("2" escalates, "1" not).

    YAML normally types bare digits as int, but hand-written/quoted sentinels
    may carry strings — the predicate must not silently lose the signal."""
    _guard()
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": "2"}
    ) is True
    assert lazy_core.validation_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": "1"}
    ) is False




# ---- spike_escalation() unit tests (spike-pipeline-role WU-2) ----
#
# Faithful shape-mirror of validation_escalation() above — same threshold
# (retry_count >= 2) and the same int / string-digit / bool-reject / missing
# tolerances, but keyed on blocker_kind == "runtime-spike-verdict-pending"
# instead of "mcp-validation". A completely independent predicate (its own
# blocker_kind never fires the mcp-validation one and vice versa).

def test_spike_escalation_retry_1_not_escalated():
    """blocker_kind runtime-spike-verdict-pending + retry_count 1 → below
    the threshold, no escalation."""
    _guard()
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": 1}
    ) is False


def test_spike_escalation_retry_0_not_escalated():
    """retry_count 0 (or missing) is also below the threshold."""
    _guard()
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": 0}
    ) is False
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending"}
    ) is False


def test_spike_escalation_retry_2_escalated():
    """blocker_kind runtime-spike-verdict-pending + retry_count 2 →
    escalation fires (>= 2)."""
    _guard()
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": 2}
    ) is True
    # And anything above the threshold also escalates.
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": 3}
    ) is True


def test_spike_escalation_other_blocker_kind_not_escalated():
    """retry_count 5 but a NON-spike blocker_kind (e.g. the mcp-validation
    escalation's own kind) → never escalates. spike_escalation fires ONLY
    on its own blocker_kind."""
    _guard()
    assert lazy_core.spike_escalation(
        {"blocker_kind": "mcp-validation", "retry_count": 5}
    ) is False


def test_spike_escalation_missing_fields_not_escalated():
    """Missing blocker_kind / missing retry_count / malformed retry_count /
    None / empty meta → no escalation (mirrors validation_escalation's
    backward-compatibility tolerances)."""
    _guard()
    # Missing blocker_kind entirely.
    assert lazy_core.spike_escalation({"retry_count": 5}) is False
    # Missing retry_count entirely.
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending"}
    ) is False
    # Malformed retry_count (non-numeric string).
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": "many"}
    ) is False
    # None meta (defensive caller convenience).
    assert lazy_core.spike_escalation(None) is False
    # Empty meta.
    assert lazy_core.spike_escalation({}) is False


def test_spike_escalation_string_digit_retry_count():
    """retry_count as a string of digits is tolerated ("2" escalates, "1"
    not)."""
    _guard()
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": "2"}
    ) is True
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": "1"}
    ) is False


def test_spike_escalation_bool_retry_count_rejected():
    """YAML booleans are ints in Python (True == 1) — retry_count: true must
    NOT coerce to 1 and must not escalate, even though bool is an int
    subclass."""
    _guard()
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": True}
    ) is False
    assert lazy_core.spike_escalation(
        {"blocker_kind": "runtime-spike-verdict-pending", "retry_count": False}
    ) is False




# ---- WU-5d: apply_pseudo __mark_complete__ retro-staleness backstop ----

def test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes():
    """__mark_complete__ with a STALE RETRO_DONE.md (phase_count_at_retro 2,
    PHASES.md now 3 phases) → refusal naming both counts, with ZERO writes:
    PHASES.md/SPEC.md bytes unchanged, no COMPLETED.md, sentinels untouched."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # Three fully-coherent phases so ONLY the staleness gate can refuse.
        phases_text = (
            "# Phases\n\n**Status:** In-progress\n\n"
            "### Phase 1\n**Status:** Complete\n- [x] A\n\n"
            "### Phase 2\n**Status:** Complete\n- [x] B\n\n"
            "### Phase 3\n**Status:** Complete\n- [x] C\n"
        )
        (spec_dir / "PHASES.md").write_text(phases_text, encoding="utf-8")
        retro_text = (
            "---\nkind: retro-done\nfeature_id: test-feature\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n"
        )
        (spec_dir / "RETRO_DONE.md").write_text(retro_text, encoding="utf-8")
        spec_text_before = (spec_dir / "SPEC.md").read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-11"
        )

        # Refusal dict matches the Phase-9 refusal convention exactly.
        assert result["ok"] is False, result
        assert isinstance(result["refused"], str), result
        assert result["wrote"] == [], result
        assert result["deleted"] == [], result
        assert result["noop"] is False, result
        # Message names the counts in the agreed shape.
        assert "retro is stale: 3 phases now vs 2 at retro" in result["refused"], (
            result["refused"]
        )
        assert "route a retro round before completion" in result["refused"], (
            result["refused"]
        )
        # ZERO writes: every byte on disk is exactly as before.
        assert (spec_dir / "PHASES.md").read_text(encoding="utf-8") == phases_text
        assert (spec_dir / "SPEC.md").read_text(encoding="utf-8") == spec_text_before
        assert not (spec_dir / "COMPLETED.md").exists(), "receipt must NOT be minted"
        assert (spec_dir / "RETRO_DONE.md").read_text(encoding="utf-8") == retro_text
        assert (spec_dir / "VALIDATED.md").exists(), "sentinels must be untouched"




def test_apply_pseudo_mark_complete_grandfathered_retro_completes():
    """__mark_complete__ with a field-less RETRO_DONE.md (pre-Phase-11) →
    completes exactly as today: receipt minted, status flipped, sentinels cleaned."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n**Status:** In-progress\n\n"
            "### Phase 1\n**Status:** Complete\n- [x] A\n\n"
            "### Phase 2\n**Status:** Complete\n- [x] B\n\n"
            "### Phase 3\n**Status:** Complete\n- [x] C\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: test-feature\ndate: 2026-06-01\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-11"
        )
        # Assert on-disk effects while the temp dir still exists.
        assert (spec_dir / "COMPLETED.md").exists(), "receipt must be minted"
        assert not (spec_dir / "RETRO_DONE.md").exists(), (
            "RETRO_DONE.md must be cleaned up on completion"
        )
    assert result["ok"] is True, result
    assert result["refused"] is None, result
    assert any("COMPLETED.md" in str(w) for w in result["wrote"]), result
    assert "RETRO_DONE.md" in result["deleted"], result




def test_apply_pseudo_mark_complete_receipted_noop_beats_stale_retro():
    """An already-receipted dir with a STALE RETRO_DONE.md never re-refuses. The
    staleness backstop is SKIPPED on a crash-window RESUME (it sits after the
    audit and, once a receipt exists, it already passed pre-receipt on the
    crashed run) — so a lingering VALIDATED.md + stale RETRO_DONE.md drives a
    RESUME (convergence + cleanup), not a re-refusal.
    mark-complete-partial-apply-noop-unrecoverable replaced the pre-fix noop
    here with resume-not-refuse; the load-bearing property (never re-refuse a
    receipted dir) is preserved."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="Complete")
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n\n"
            "### Phase 3\n- [x] C\n",
            encoding="utf-8",
        )
        # Stale retro + an existing valid receipt.
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: test-feature\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n",
            encoding="utf-8",
        )
        (spec_dir / "COMPLETED.md").write_text(
            "---\nkind: completed\nfeature_id: test-feature\ndate: 2026-06-01\n"
            "provenance: gated\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-11"
        )
        # Never re-refuses (the load-bearing property), and the staleness gate is
        # bypassed on the resume rather than firing.
        assert result["ok"] is True, result
        assert result["refused"] is None, result
        assert result.get("resumed") is True, result
        # The resume cleaned up the lingering cleanup sentinels.
        assert not (spec_dir / "VALIDATED.md").exists(), result
        assert not (spec_dir / "RETRO_DONE.md").exists(), result




def test_apply_pseudo_mark_fixed_refuses_stale_retro_zero_writes():
    """__mark_fixed__ (bug pipeline) gets the SAME staleness backstop as
    __mark_complete__ — the original WU-5 scoping assumed bugs have no retro
    step, but bug-state.py has Step 8 (retro-feature) and bug dirs carry the
    identical RETRO_DONE.md + PHASES.md shape, so a stale retro must refuse the
    FIXED.md receipt with ZERO writes (Phase 11 WU-5e bug-pipeline parity)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # Three fully-coherent phases so ONLY the staleness gate can refuse.
        phases_text = (
            "# Phases\n\n**Status:** In-progress\n\n"
            "### Phase 1\n**Status:** Complete\n- [x] A\n\n"
            "### Phase 2\n**Status:** Complete\n- [x] B\n\n"
            "### Phase 3\n**Status:** Complete\n- [x] C\n"
        )
        (spec_dir / "PHASES.md").write_text(phases_text, encoding="utf-8")
        retro_text = (
            "---\nkind: retro-done\nbug_id: test-bug\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n"
        )
        (spec_dir / "RETRO_DONE.md").write_text(retro_text, encoding="utf-8")
        spec_text_before = (spec_dir / "SPEC.md").read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            Path(td), "__mark_fixed__", spec_dir, date="2026-06-11"
        )

        # Refusal dict matches the Phase-9 refusal convention exactly.
        assert result["ok"] is False, result
        assert isinstance(result["refused"], str), result
        assert result["wrote"] == [], result
        assert result["deleted"] == [], result
        assert result["noop"] is False, result
        # Message names the counts in the same shape as __mark_complete__.
        assert "retro is stale: 3 phases now vs 2 at retro" in result["refused"], (
            result["refused"]
        )
        assert "route a retro round before completion" in result["refused"], (
            result["refused"]
        )
        # ZERO writes: every byte on disk is exactly as before.
        assert (spec_dir / "PHASES.md").read_text(encoding="utf-8") == phases_text
        assert (spec_dir / "SPEC.md").read_text(encoding="utf-8") == spec_text_before
        assert not (spec_dir / "FIXED.md").exists(), "receipt must NOT be minted"
        assert (spec_dir / "RETRO_DONE.md").read_text(encoding="utf-8") == retro_text
        assert (spec_dir / "VALIDATED.md").exists(), "sentinels must be untouched"




def test_apply_pseudo_mark_fixed_grandfathered_retro_completes():
    """__mark_fixed__ with a field-less RETRO_DONE.md (pre-Phase-11) → the
    FIXED.md receipt is minted exactly as today: every existing bug dir without
    phase_count_at_retro keeps completing byte-identically."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n\n"
            "### Phase 3\n- [x] C\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nbug_id: test-bug\ndate: 2026-06-01\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_fixed__", spec_dir, date="2026-06-11"
        )
        # Assert on-disk effects while the temp dir still exists.
        assert (spec_dir / "FIXED.md").exists(), "receipt must be minted"
        assert not (spec_dir / "RETRO_DONE.md").exists(), (
            "RETRO_DONE.md must be cleaned up on fix"
        )
    assert result["ok"] is True, result
    assert result["refused"] is None, result
    assert any("FIXED.md" in str(w) for w in result["wrote"]), result
    assert "RETRO_DONE.md" in result["deleted"], result




def test_apply_pseudo_mark_fixed_receipted_noop_beats_stale_retro():
    """The bug-pipeline mirror of the __mark_complete__ case: an already-receipted
    bug dir with a STALE RETRO_DONE.md never re-refuses. The staleness backstop is
    SKIPPED on a crash-window RESUME (a lingering VALIDATED.md + stale RETRO_DONE.md
    drives a resume/cleanup, not a re-refusal).
    mark-complete-partial-apply-noop-unrecoverable: resume-not-refuse preserves
    the never-re-refuse-a-receipted-dir property on the bug axis too."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="Fixed")
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n\n"
            "### Phase 3\n- [x] C\n",
            encoding="utf-8",
        )
        # Stale retro + an existing valid FIXED.md receipt.
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nbug_id: test-bug\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n",
            encoding="utf-8",
        )
        (spec_dir / "FIXED.md").write_text(
            "---\nkind: fixed\nfeature_id: test-bug\ndate: 2026-06-01\n"
            "provenance: gated\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_fixed__", spec_dir, date="2026-06-11"
        )
        assert result["ok"] is True, result
        assert result["refused"] is None, result
        assert result.get("resumed") is True, result
        assert not (spec_dir / "VALIDATED.md").exists(), result
        assert not (spec_dir / "RETRO_DONE.md").exists(), result




# ---------------------------------------------------------------------------
# Tests: detect_noncanonical_blocker — read-time stray-blocker detector
#   (noncanonical-blocker-filename-invisible-to-state-machine, Phase 1)
# ---------------------------------------------------------------------------

def test_detect_noncanonical_blocker_stray_alone():
    """A stray BLOCKED_<date>-foo.md alone → returns that path."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        stray = d / "BLOCKED_2026-06-09-foo.md"
        stray.write_text("stray blocker\n", encoding="utf-8")
        result = lazy_core.detect_noncanonical_blocker(d)
    assert result is not None, "expected the stray path, got None"
    assert result.name == "BLOCKED_2026-06-09-foo.md", (
        f"expected the stray basename, got {result.name!r}"
    )




def test_detect_noncanonical_blocker_resolved_excluded():
    """A neutralized BLOCKED_RESOLVED_<date>.md alone → None (excluded)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "BLOCKED_RESOLVED_2026-06-09.md").write_text("resolved\n", encoding="utf-8")
        result = lazy_core.detect_noncanonical_blocker(d)
    assert result is None, f"expected None (resolved excluded), got {result!r}"




def test_detect_noncanonical_blocker_canonical_alone():
    """Canonical BLOCKED.md alone → None (canonical is not a stray)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "BLOCKED.md").write_text("canonical\n", encoding="utf-8")
        result = lazy_core.detect_noncanonical_blocker(d)
    assert result is None, f"expected None (canonical not a stray), got {result!r}"




def test_detect_noncanonical_blocker_canonical_plus_stray():
    """Both canonical + stray present → None (canonical Step-3 check owns it)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "BLOCKED.md").write_text("canonical\n", encoding="utf-8")
        (d / "BLOCKED_2026-06-09-foo.md").write_text("stray\n", encoding="utf-8")
        result = lazy_core.detect_noncanonical_blocker(d)
    assert result is None, (
        f"expected None (canonical precedence), got {result!r}"
    )




def test_detect_noncanonical_blocker_lowercase_variant():
    """Lowercase blocked.md → returns that path (case-insensitive match)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "blocked.md").write_text("lowercase stray\n", encoding="utf-8")
        result = lazy_core.detect_noncanonical_blocker(d)
    assert result is not None, "expected the lowercase stray path, got None"
    assert result.name == "blocked.md", f"expected 'blocked.md', got {result.name!r}"




def test_detect_noncanonical_blocker_empty_and_missing_dir():
    """Empty dir AND a non-existent dir → None each (never raises)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # (1) empty dir
        assert lazy_core.detect_noncanonical_blocker(d) is None, (
            "expected None for an empty dir"
        )
        # (2) non-existent dir
        missing = d / "does-not-exist"
        assert lazy_core.detect_noncanonical_blocker(missing) is None, (
            "expected None for a missing dir (must not raise)"
        )




def test_write_deferred_requires_host_empty_missing_raises():
    """missing_capabilities is load-bearing — an empty list raises (a blanket
    whole-feature deferral with no scope is malformed)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "DEFERRED_REQUIRES_HOST.md"
        raised = False
        try:
            lazy_core.write_deferred_requires_host(
                path, feature_id="feat-x", missing_capabilities=[]
            )
        except ValueError:
            raised = True
        assert raised, "empty missing_capabilities must raise ValueError"
        assert not path.exists(), "no sentinel must be written on the raise path"




def test_apply_pseudo_direct_call_refused_under_cycle_marker_without_orchestrator():
    """GAP-1 integrity backstop (hardening round 2026-07): a DIRECT in-process
    ``lazy_core.apply_pseudo("__mark_complete__", ...)`` call under an active cycle
    marker WITHOUT the ``LAZY_ORCHESTRATOR=1`` export (the rogue-subagent context)
    must be refused by the internal ``refuse_if_cycle_active`` guard — exit 3, ZERO
    filesystem side effects (no COMPLETED.md, SPEC/PHASES status untouched,
    VALIDATED.md untouched). This closes the direct-import side-door around the
    CLI-only guard that let an mcp-test subagent self-complete first-time-login on
    partial evidence.
    """
    _guard()
    _clear_cycle_env()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        _write_phases_md(
            spec_dir,
            "## Phase 1 — Foundations\n\n**Status:** Complete\n\n- [x] Build the thing\n",
        )
        try:
            # Arm the cycle marker; do NOT set LAZY_ORCHESTRATOR (subagent context).
            lazy_core.write_cycle_marker(feature_id="f", nonce="n")
            code = None
            try:
                lazy_core.apply_pseudo(
                    Path(td), "__mark_complete__", spec_dir, date="2026-07-03"
                )
            except SystemExit as exc:
                code = exc.code if exc.code is not None else 0
            assert code == 3, (
                f"direct apply_pseudo under a cycle marker (no LAZY_ORCHESTRATOR) "
                f"must exit 3, got exit code {code!r}"
            )
            # ZERO side effects: no receipt written, no status flips, sentinel intact.
            assert not (spec_dir / "COMPLETED.md").exists(), (
                "COMPLETED.md written despite the cycle-containment refusal"
            )
            assert "**Status:** In-progress" in (
                spec_dir / "SPEC.md"
            ).read_text(encoding="utf-8"), "SPEC.md status flipped despite refusal"
            assert (spec_dir / "VALIDATED.md").exists(), (
                "VALIDATED.md deleted despite refusal — must be untouched"
            )
        finally:
            _clear_cycle_env()
            _clear_state_dir()




def test_apply_pseudo_grant_skip_refuses_with_app_surface():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "package.json").write_text("{}\n", encoding="utf-8")
        spec = Path(td) / "spec"
        _write_not_required_phases(spec)
        result = lazy_core.apply_pseudo(
            Path(td), "__grant_skip_no_mcp_surface__", spec, date="2026-06-16"
        )
        assert result["ok"] is False and result["refused"], result
        assert not (spec / "SKIP_MCP_TEST.md").exists()




def test_apply_pseudo_grant_skip_refuses_without_not_required():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        spec.mkdir()
        (spec / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] x\n", encoding="utf-8"
        )
        result = lazy_core.apply_pseudo(
            Path(td), "__grant_skip_no_mcp_surface__", spec, date="2026-06-16"
        )
        assert result["ok"] is False and result["refused"], result
        assert not (spec / "SKIP_MCP_TEST.md").exists()




def test_apply_pseudo_grant_skip_idempotent_noop():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        _write_not_required_phases(spec)
        first = lazy_core.apply_pseudo(
            Path(td), "__grant_skip_no_mcp_surface__", spec, date="2026-06-16"
        )
        assert first["noop"] is False
        content1 = (spec / "SKIP_MCP_TEST.md").read_text(encoding="utf-8")
        second = lazy_core.apply_pseudo(
            Path(td), "__grant_skip_no_mcp_surface__", spec, date="2026-06-16"
        )
        assert second["ok"] is True and second["noop"] is True, second
        assert (spec / "SKIP_MCP_TEST.md").read_text(encoding="utf-8") == content1




def test_apply_pseudo_grant_skip_then_validated_roundtrip():
    """grant structural skip → __write_validated_from_skip__ accepts it
    (re-verified) and writes VALIDATED.md."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        _write_not_required_phases(spec)
        grant = lazy_core.apply_pseudo(
            Path(td), "__grant_skip_no_mcp_surface__", spec, date="2026-06-16"
        )
        assert grant["ok"] is True
        validated = lazy_core.apply_pseudo(
            Path(td), "__write_validated_from_skip__", spec, date="2026-06-16"
        )
        assert validated["ok"] is True and validated["refused"] is None, validated
        assert (spec / "VALIDATED.md").exists()




# ---- WU-3: apply_pseudo __mark_complete__ — ROADMAP strike + resolved-spec_dir trim ----

def _write_roadmap(repo_root: Path, rows: list[str]) -> Path:
    """Write docs/features/ROADMAP.md with the given lines (each a table row or
    bullet referencing a feature)."""
    features = repo_root / "docs" / "features"
    features.mkdir(parents=True, exist_ok=True)
    p = features / "ROADMAP.md"
    p.write_text("# Roadmap\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p




def test_apply_pseudo_mark_complete_strikes_roadmap_row():
    """Marking a feature complete strikes its ROADMAP row (strikethrough +
    COMPLETE token), leaving unrelated rows intact."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "my-feature"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        roadmap = _write_roadmap(
            repo_root,
            [
                "| my-feature | Build the thing | tier 1 |",
                "| other-feature | Build other | tier 2 |",
            ],
        )
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="my-feature", date="2026-06-17",
        )
        assert result["ok"] is True, result
        assert result.get("roadmap_struck") is True, result
        text = roadmap.read_text(encoding="utf-8")
        # The my-feature row must be struck (contains ~~ strikethrough) and
        # carry a COMPLETE marker.
        my_line = [ln for ln in text.splitlines() if "my-feature" in ln][0]
        assert "~~" in my_line, f"my-feature row not struck: {my_line!r}"
        assert "COMPLETE" in my_line.upper(), f"no COMPLETE token: {my_line!r}"
        # The unrelated row is untouched.
        other_line = [ln for ln in text.splitlines() if "other-feature" in ln][0]
        assert "~~" not in other_line, f"other-feature wrongly struck: {other_line!r}"
        assert "ROADMAP.md" in [str(w) for w in result["wrote"]] or any(
            "ROADMAP.md" in str(w) for w in result["wrote"]
        ), result




def test_apply_pseudo_mark_complete_no_roadmap_is_noop_strike():
    """No ROADMAP.md present → roadmap_struck False, completion still succeeds."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "my-feature"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="my-feature", date="2026-06-17",
        )
        assert result["ok"] is True, result
        assert result.get("roadmap_struck") is False, result




def test_apply_pseudo_mark_complete_idempotent_no_reroite_strike():
    """A GENUINELY-DONE dir short-circuits to noop BEFORE the strike — an
    already-struck ROADMAP row is NOT re-mutated. mark-complete-partial-apply-
    noop-unrecoverable: the noop is now gated on the full post-condition audit,
    so the fixture must itself be genuinely-done (SPEC Complete, kept SKIP
    evidence, no cleanup sentinels, ROADMAP row already carrying the COMPLETE
    token) — otherwise it would be a partial-apply resume."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "my-feature"
        spec_dir.mkdir(parents=True)
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="my-feature", date="2026-06-17", provenance="gated",
        )
        _write_spec_md(spec_dir, status="Complete")
        _write_skip_mcp_test(spec_dir)
        # ROADMAP row already struck (carries the COMPLETE token) → post-condition met.
        roadmap = _write_roadmap(
            repo_root, [f"| my-feature | thing | {lazy_core._ROADMAP_COMPLETE_TOKEN} |"]
        )
        before = roadmap.read_text(encoding="utf-8")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="my-feature", date="2026-06-17",
        )
        assert result["noop"] is True, result
        assert result.get("resumed") is False, result
        assert roadmap.read_text(encoding="utf-8") == before, (
            "ROADMAP mutated on the noop re-run"
        )




def test_apply_pseudo_mark_complete_trims_by_resolved_spec_dir_followups():
    """REGRESSION (-followups class): a queue entry whose stored spec_dir is a
    PATH (or differs from the dir basename) must STILL be trimmed by matching
    the RESOLVED spec_dir — not just the basename. Kills the
    -followups queue-trim-miss / queue.no-completed class."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        # The spec dir basename is "my-feature-followups".
        spec_dir = repo_root / "docs" / "features" / "my-feature-followups"
        spec_dir.mkdir(parents=True)
        _write_validated_md(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        # The queue entry's spec_dir is stored as a PATH-form value that does
        # NOT equal the basename, AND its id does NOT equal the feature_id
        # passed to apply_pseudo — so the OLD match (spec_dir == spec_path.name
        # OR id == feature_id) MISSES it entirely, leaving the entry and
        # tripping queue.no-completed. Only a RESOLVED-spec_dir match catches it.
        features = repo_root / "docs" / "features"
        queue_path = features / "queue.json"
        queue_path.write_text(
            json.dumps(
                {
                    "queue": [
                        {
                            "id": "different-queue-id",
                            "spec_dir": "docs/features/my-feature-followups",
                            "name": "Follow-ups",
                        },
                        {"id": "survivor", "spec_dir": "survivor", "name": "Other"},
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="my-feature-followups", date="2026-06-17",
        )
        assert result["ok"] is True, result
        assert result["queue_trimmed"] is True, (
            f"-followups entry (path-form spec_dir) was NOT trimmed: {result}"
        )
        data = json.loads(queue_path.read_text(encoding="utf-8"))
        ids = [e["id"] for e in data["queue"]]
        assert "different-queue-id" not in ids, f"entry lingered: {ids}"
        assert "survivor" in ids, f"unrelated entry wrongly removed: {ids}"




def test_skip_ahead_ready_independent_no_hard_dep_on_gated_true():
    """P3 RED: independent AND no hard dep on a gated id → True."""
    _guard()
    deps = [{"feature_id": "other", "kind": "hard", "reason": "x"}]
    assert lazy_core.skip_ahead_ready(
        deps, gated_ids={"head"}, independent=True
    ) is True




def test_skip_ahead_ready_hard_dep_on_gated_false_even_if_marked():
    """P3 RED: a HARD dep on a currently-gated id → False even when marked."""
    _guard()
    deps = [{"feature_id": "head", "kind": "hard", "reason": "needs it"}]
    assert lazy_core.skip_ahead_ready(
        deps, gated_ids={"head"}, independent=True
    ) is False




def test_skip_ahead_ready_soft_composes_dep_on_gated_does_not_block():
    """P3 RED: soft/composes deps on a gated id do NOT block (need exist, not Complete)."""
    _guard()
    deps = [
        {"feature_id": "head", "kind": "soft", "reason": "x"},
        {"feature_id": "head", "kind": "composes", "reason": "y"},
    ]
    assert lazy_core.skip_ahead_ready(
        deps, gated_ids={"head"}, independent=True
    ) is True




def test_skip_ahead_ready_unmarked_but_dep_free_false():
    """P3 RED: dep-free but NOT marked independent → False (degrades to strict halt)."""
    _guard()
    assert lazy_core.skip_ahead_ready(
        [], gated_ids={"head"}, independent=False
    ) is False




# ---------------------------------------------------------------------------
# lazy-batch-unified-driver-parity-and-accounting Phase 3 (item 2) — WU-6.
# ---------------------------------------------------------------------------
#
# lazy_parity_audit.audit_merged_view_dispatch_parity asserts BOTH the unified
# driver (lazy-batch) AND its cloud mirror (lazy-batch-cloud) carry the merged-
# view dispatch branch. WU-6 adds a (r"--archive-fixed", ...) predicate to
# _MERGED_VIEW_PREDICATES so the audit ALSO asserts both drivers chain the
# --archive-fixed follow-up for the bug __mark_fixed__ terminal — the SPEC
# Coupling/parity requirement. A driver dropping the chain becomes a finding.


def _write_merged_view_fixture(repo_root, lazy_batch_text, cloud_text):
    """Seed a temp repo-root with the two driver SKILL.md files at the exact
    repo-relative paths lazy_parity_audit._MERGED_VIEW_DRIVER_FILES expects."""
    lb = repo_root / "user" / "skills" / "lazy-batch" / "SKILL.md"
    cl = (repo_root / "repos" / "algobooth" / ".claude" / "skills"
          / "lazy-batch-cloud" / "SKILL.md")
    lb.parent.mkdir(parents=True, exist_ok=True)
    cl.parent.mkdir(parents=True, exist_ok=True)
    lb.write_text(lazy_batch_text, encoding="utf-8")
    cl.write_text(cloud_text, encoding="utf-8")




# A minimal driver-SKILL body satisfying every PRE-EXISTING merged-view predicate
# (--next-merged, __mark_complete__, __mark_fixed__, bug-state.py, single-type) so
# the ONLY variable under test is the --archive-fixed chain.
_MV_BASE = (
    "Unified driver: probe `lazy-state.py --next-merged`. feature → "
    "`__mark_complete__`; bug → `bug-state.py` + `__mark_fixed__`. "
    "single-type runs unchanged.\n"
)




def test_archive_fixed_predicate_present_in_audit():
    """WU-6 (RED against the pre-WU-6 audit): _MERGED_VIEW_PREDICATES carries an
    --archive-fixed predicate. Pre-fix the predicate is absent → this fails."""
    _guard()
    import lazy_parity_audit
    patterns = [p for p, _ in lazy_parity_audit._MERGED_VIEW_PREDICATES]
    assert r"--archive-fixed" in patterns, (
        "the merged-view parity audit must assert the --archive-fixed chain; "
        f"patterns={patterns!r}"
    )




def test_archive_fixed_chain_missing_produces_finding():
    """WU-6: a driver MISSING the --archive-fixed chain produces a merged-view
    finding naming it; both drivers WITH the chain produce zero archive findings."""
    _guard()
    import lazy_parity_audit

    with_chain = _MV_BASE + "Then run `bug-state.py --archive-fixed {spec_path}`.\n"

    # (1) Cloud driver MISSING the chain → a finding against lazy-batch-cloud.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_merged_view_fixture(root, with_chain, _MV_BASE)  # cloud lacks chain
        findings = lazy_parity_audit.audit_merged_view_dispatch_parity(root)
        archive_findings = [f for f in findings if "archive" in f.lower()]
        assert archive_findings, (
            "a cloud driver missing the --archive-fixed chain must produce an "
            f"archive finding; all findings={findings!r}"
        )
        assert any("lazy-batch-cloud" in f for f in archive_findings), (
            f"the finding must name lazy-batch-cloud; got {archive_findings!r}"
        )

    # (2) BOTH drivers carry the chain → zero archive findings.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_merged_view_fixture(root, with_chain, with_chain)
        findings = lazy_parity_audit.audit_merged_view_dispatch_parity(root)
        archive_findings = [f for f in findings if "archive" in f.lower()]
        assert not archive_findings, (
            f"both drivers carry the chain — no archive finding expected; got "
            f"{archive_findings!r}"
        )




def test_archive_fixed_real_drivers_pass_audit():
    """WU-6 integration: the REAL lazy-batch + lazy-batch-cloud SKILLs (post-WU-5)
    both carry the --archive-fixed chain — the full merged-view audit is clean."""
    _guard()
    import lazy_parity_audit
    # Resolve __file__ through the ~/.claude/scripts SYMLINK before walking up to
    # the repo root. When this module is invoked AS the symlink
    # (~/.claude/scripts/test_lazy_core.py), a raw `Path(__file__).parent.parent`
    # resolves to the symlink's PARENT tree (e.g. ~/), not the real claude-config
    # checkout — so the merged-view audit then can't find the real SKILL.md files
    # and reports spurious "cannot read" findings. .resolve() follows the symlink
    # to the on-disk <claude-config>/user/scripts, whose .parent.parent IS the
    # repo root. (Preexisting symlink-invocation defect — fixed inline.)
    repo_root = Path(__file__).resolve().parents[4]  # user/scripts/tests/test_lazy_core → repo root
    findings = lazy_parity_audit.audit_merged_view_dispatch_parity(repo_root)
    assert findings == [], (
        f"the real drivers must pass the merged-view parity audit (incl. "
        f"--archive-fixed); findings={findings!r}"
    )




def test_apply_pseudo_validated_from_results_accepts_docs_only_drift():
    """2026-06-23 DEADLOCK fix: validated_commit (A) != HEAD (B) but the A→B
    drift is PURE DOCS-ONLY (*.md) → VALIDATED.md IS minted (with a warning),
    NOT refused. This is the structurally-unavoidable one-commit lag from the
    /mcp-test cycle committing its own MCP_TEST_RESULTS.md. RED against pre-fix
    code (strict validated_commit != HEAD refused → deadlock)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_dir = root / "spec"
        spec_dir.mkdir()
        (spec_dir / "SPEC.md").write_text("# placeholder\n", encoding="utf-8")
        first = _cc_seed_and_commit(root)
        # Second commit changes ONLY a markdown file → docs-only drift.
        (root / "NOTES.md").write_text("docs change\n", encoding="utf-8")
        second = _git_fixture_commit(root)
        assert first != second
        _write_mcp_test_results(spec_dir, ["scenario-a"], validated_commit=first)
        result = lazy_core.apply_pseudo(
            root, "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, (
            f"docs-only drift must mint VALIDATED.md (deadlock fix), got {result}"
        )
        assert (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md not written for docs-only drift — deadlock not fixed"
        )
        warnings = result.get("warnings") or []
        assert any("docs-only" in w for w in warnings), (
            f"expected a docs-only acceptance warning, got {result!r}"
        )




def test_apply_pseudo_validated_from_results_refuses_non_docs_drift():
    """Non-.md (source) drift between validated_commit and HEAD STILL refuses
    (the TOCTOU guard is preserved — the deadlock fix is docs-only-scoped)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_dir = root / "spec"
        spec_dir.mkdir()
        (spec_dir / "SPEC.md").write_text("# placeholder\n", encoding="utf-8")
        first = _cc_seed_and_commit(root)
        # Second commit changes a SOURCE file → must refuse-and-revalidate.
        (root / "mod.py").write_text("x = 1\n", encoding="utf-8")
        second = _git_fixture_commit(root)
        assert first != second
        _write_mcp_test_results(spec_dir, ["scenario-a"], validated_commit=first)
        result = lazy_core.apply_pseudo(
            root, "__write_validated_from_results__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is False, (
            f"source drift must refuse (TOCTOU preserved), got {result}"
        )
        assert not (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md minted despite source drift — TOCTOU guard weakened!"
        )



# A PHASES.md with a GENUINE unchecked implementation row (no marker).
_CC_E2E_PHASES_REAL_OPEN = (
    "# Phases\n\n"
    "### Phase 1: Impl\n\n"
    "**Status:** In-progress\n\n"
    "- [x] partly done\n"
    "- [ ] real unfinished implementation work\n"
)




def test_mark_complete_real_unchecked_row_refuses_zero_writes():
    """A real (non-verification) unchecked implementation row → refuse naming the
    phase, PHASES.md byte-unchanged, no COMPLETED.md.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _cc_build_validated_feature(
            repo_root, phases_body=_CC_E2E_PHASES_REAL_OPEN
        )
        before = (spec_dir / "PHASES.md").read_text(encoding="utf-8")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="cc-e2e", date="2026-06-19",
        )
        assert result["ok"] is False, result
        assert result["refused"], result
        assert "Phase 1" in result["refused"], result
        assert not (spec_dir / "COMPLETED.md").exists(), "receipt minted on refusal"
        assert (spec_dir / "PHASES.md").read_text(encoding="utf-8") == before, (
            "PHASES.md mutated on a refusal"
        )




def test_mark_complete_kill_switch_legacy_refusal_zero_mutation():
    """LAZY_STRICT_EVIDENCE_GATE set → legacy strict path: verification rows are
    INCLUDED in refusals, the auto-tick is skipped, PHASES.md byte-unchanged.
    """
    _guard()
    import os as _os
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _cc_build_validated_feature(
            repo_root, phases_body=_CC_E2E_PHASES_VERIF_ONLY
        )
        before = (spec_dir / "PHASES.md").read_text(encoding="utf-8")
        prev = _os.environ.get("LAZY_STRICT_EVIDENCE_GATE")
        _os.environ["LAZY_STRICT_EVIDENCE_GATE"] = "1"
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="cc-e2e", date="2026-06-19",
            )
        finally:
            if prev is None:
                _os.environ.pop("LAZY_STRICT_EVIDENCE_GATE", None)
            else:
                _os.environ["LAZY_STRICT_EVIDENCE_GATE"] = prev
        assert result["ok"] is False, result
        assert result["refused"], result
        assert (spec_dir / "PHASES.md").read_text(encoding="utf-8") == before, (
            "kill-switch path mutated PHASES.md"
        )
        assert not (spec_dir / "COMPLETED.md").exists(), result




def test_mark_complete_zero_test_evidence_refuses():
    """Passing-literal results but pass==total==0 (zero-test) → refuse, no tick."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "cc-zero"
        spec_dir.mkdir(parents=True)
        _cc_write_validated(spec_dir)
        _write_spec_md(spec_dir, status="In-progress")
        _cc_write_retro_done(spec_dir)
        (spec_dir / "PHASES.md").write_text(
            _CC_E2E_PHASES_VERIF_ONLY, encoding="utf-8"
        )
        _write_mcp_test_results(spec_dir, [], pass_count=0, total_count=0)
        head = _cc_seed_and_commit(repo_root)
        _write_mcp_test_results(
            spec_dir, [], pass_count=0, total_count=0, validated_commit=head
        )
        before = (spec_dir / "PHASES.md").read_text(encoding="utf-8")
        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="cc-zero", date="2026-06-19",
        )
        assert result["ok"] is False, result
        assert (spec_dir / "PHASES.md").read_text(encoding="utf-8") == before, result
        assert not (spec_dir / "COMPLETED.md").exists(), result




# ---------------------------------------------------------------------------
# reorder_queue helper (no-sanctioned-queue-reorder-command — Phase 1)
# ---------------------------------------------------------------------------

def _write_temp_queue(td: "Path", ids: "list[str]") -> "Path":
    """Write a docs/features/queue.json-shaped file with the given ids in order."""
    qp = Path(td) / "queue.json"
    qp.write_text(
        json.dumps({"queue": [{"id": i, "name": i} for i in ids]}, indent=2) + "\n",
        encoding="utf-8",
    )
    return qp




def _queue_ids(qp: "Path") -> "list[str]":
    data = json.loads(qp.read_text(encoding="utf-8"))
    return [e["id"] for e in data["queue"]]




def test_reorder_queue_to_tail_moves_entry_last():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_queue(td, ["a", "b", "c"])
        result = lazy_core.reorder_queue(qp, "a", to="tail")
        assert _queue_ids(qp) == ["b", "c", "a"], _queue_ids(qp)
        # file remains valid JSON (re-read above proves it)
        assert result["reordered"] is True
        assert result["item_id"] == "a"
        assert result["operation"] == "tail"
        assert result["new_position"] == 2
        assert result["queue_length"] == 3
        # JSON-serializable
        json.dumps(result)




def test_reorder_queue_to_head_moves_entry_first():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_queue(td, ["a", "b", "c"])
        result = lazy_core.reorder_queue(qp, "c", to="head")
        assert _queue_ids(qp) == ["c", "a", "b"], _queue_ids(qp)
        assert result["new_position"] == 0
        assert result["operation"] == "head"




def test_reorder_queue_to_int_index_moves_entry_to_index():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_queue(td, ["a", "b", "c"])
        result = lazy_core.reorder_queue(qp, "a", to=1)
        assert _queue_ids(qp) == ["b", "a", "c"], _queue_ids(qp)
        assert result["new_position"] == 1
        assert result["operation"] == "index:1"




def test_reorder_queue_remove_deletes_entry():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_queue(td, ["a", "b", "c"])
        result = lazy_core.reorder_queue(qp, "b", to="remove")
        assert _queue_ids(qp) == ["a", "c"], _queue_ids(qp)
        assert "b" not in _queue_ids(qp)
        assert result["operation"] == "remove"
        assert result["new_position"] is None
        assert result["queue_length"] == 2




def test_reorder_queue_missing_entry_dies():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_queue(td, ["a", "b", "c"])
        raised = False
        try:
            lazy_core.reorder_queue(qp, "zzz", to="tail")
        except SystemExit:
            raised = True
        assert raised, "missing item_id must raise SystemExit via _die"
        # queue untouched
        assert _queue_ids(qp) == ["a", "b", "c"], _queue_ids(qp)




def test_reorder_queue_idempotent_noop_byte_stable():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_queue(td, ["a", "b", "c"])
        before = qp.read_bytes()
        result = lazy_core.reorder_queue(qp, "a", to="head")  # already at head
        assert result["reordered"] is True
        assert result["noop"] is True
        assert qp.read_bytes() == before, "no-op must leave the file byte-stable"
        assert _queue_ids(qp) == ["a", "b", "c"]
        # tail no-op
        before2 = qp.read_bytes()
        result2 = lazy_core.reorder_queue(qp, "c", to="tail")  # already at tail
        assert result2["noop"] is True
        assert qp.read_bytes() == before2




def test_reorder_queue_malformed_json_dies():
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "queue.json"
        qp.write_text("{ not valid json", encoding="utf-8")
        raised = False
        try:
            lazy_core.reorder_queue(qp, "a", to="tail")
        except SystemExit:
            raised = True
        assert raised, "malformed queue JSON must raise SystemExit via _die"




# ---------------------------------------------------------------------------
# clear_queue_stub helper (stub-spec-route-loops-until-queue-stub-cleared — Phase 1)
# ---------------------------------------------------------------------------

def _write_temp_stub_queue(td: "Path", entries: "list[dict]") -> "Path":
    """Write a docs/features/queue.json-shaped file from raw entry dicts."""
    qp = Path(td) / "queue.json"
    qp.write_text(
        json.dumps({"queue": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    return qp




def test_clear_queue_stub_removes_stub_when_present():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_stub_queue(td, [
            {"id": "a", "name": "A", "stub": True},
            {"id": "b", "name": "B"},
        ])
        result = lazy_core.clear_queue_stub(qp, "a")
        assert result["cleared"] is True
        assert result["feature_id"] == "a"
        assert result["queue_length"] == 2
        data = json.loads(qp.read_text(encoding="utf-8"))
        entry = next(e for e in data["queue"] if e["id"] == "a")
        assert "stub" not in entry, "the stub key must be popped"
        # JSON-serializable
        json.dumps(result)




def test_clear_queue_stub_absent_is_byte_stable_noop():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_stub_queue(td, [
            {"id": "a", "name": "A"},
            {"id": "b", "name": "B"},
        ])
        before = qp.read_bytes()
        result = lazy_core.clear_queue_stub(qp, "a")
        assert result["cleared"] is False
        assert qp.read_bytes() == before, "absent-stub no-op must leave the file byte-stable"




def test_clear_queue_stub_missing_feature_id_dies():
    with tempfile.TemporaryDirectory() as td:
        qp = _write_temp_stub_queue(td, [{"id": "a", "name": "A", "stub": True}])
        before = qp.read_bytes()
        raised = False
        try:
            lazy_core.clear_queue_stub(qp, "zzz")
        except SystemExit:
            raised = True
        assert raised, "missing feature_id must raise SystemExit via _die"
        assert qp.read_bytes() == before, "die path must leave the queue untouched"




def test_clear_queue_stub_malformed_json_dies():
    with tempfile.TemporaryDirectory() as td:
        qp = Path(td) / "queue.json"
        qp.write_text("{ not valid json", encoding="utf-8")
        raised = False
        try:
            lazy_core.clear_queue_stub(qp, "a")
        except SystemExit:
            raised = True
        assert raised, "malformed queue JSON must raise SystemExit via _die"




def test_mark_complete_refused_gate_writes_no_provenance():
    """A refused completion (no evidence sentinel) writes NOTHING — no
    distillate, no index."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _prov_spec_dir(repo_root, "feat-refused")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-refused", date="2026-07-04",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is False and result["refused"]
        assert not (spec_dir / "IMPLEMENTED.md").exists()
        assert not (repo_root / "docs" / "provenance-index.json").exists()




def test_mark_complete_receipt_noop_writes_no_provenance():
    """Re-running a completion (receipt-noop path) writes nothing — the noop
    early-return sits BEFORE the provenance write."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _prov_spec_dir(repo_root, "feat-noop")
        _write_validated_md(spec_dir)
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            first = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-noop", date="2026-07-04",
            )
            assert first["ok"] is True
            dist_path = spec_dir / "IMPLEMENTED.md"
            assert dist_path.exists()
            dist_path.unlink()  # remove so a re-write would be visible
            # Add a KEPT evidence sentinel (SKIP_MCP_TEST.md survives completion,
            # unlike VALIDATED.md which the first completion deleted) so the re-run
            # reaches the genuinely-done noop audit — NOT a partial-apply resume.
            # (mark-complete-partial-apply-noop-unrecoverable: re-adding VALIDATED.md
            # would itself be a missing post-condition → a resume that re-writes.)
            _write_skip_mcp_test(spec_dir)
            second = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-noop", date="2026-07-04",
            )
        finally:
            _clear_state_dir()
        assert second["noop"] is True
        assert not dist_path.exists(), (
            "receipt-noop re-run must not re-write the distillate"
        )




def test_mark_complete_index_failure_degrades_to_warning():
    """An induced index-write failure (a DIRECTORY squats on the index path)
    still completes — receipt + flips land; the result carries warnings[] and
    provenance_written: false. Completion is never blocked by bookkeeping."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = _prov_spec_dir(repo_root, "feat-warn")
        _write_validated_md(spec_dir)
        # Squat a directory on the index path so its atomic write fails, and
        # plant a real touched-file set via message-grep in a git repo.
        (repo_root / "docs" / "provenance-index.json").mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo_root), "init", "-q"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "config", "user.email", "t@t"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "config", "user.name", "t"],
                       check=True, capture_output=True)
        _prov_git_commit_file(repo_root, "src/w.py", "feat(feat-warn): work")
        state_dir = Path(td) / "state"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-warn", date="2026-07-04",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is True, f"completion must stand, got {result}"
        assert (spec_dir / "COMPLETED.md").exists()
        assert "**Status:** Complete" in (spec_dir / "SPEC.md").read_text(encoding="utf-8")
        assert result.get("provenance_written") is False, f"got {result}"
        warnings = result.get("warnings") or []
        assert any("provenance" in w for w in warnings), f"got warnings={warnings}"




def test_apply_pseudo_capture_flag_on_and_byte_identical_off():
    """The completion-gate wiring (D1-A): a flagged repo's __mark_complete__
    writes the record AFTER the receipt and reports intervention_recorded;
    an unflagged/no-block repo's result carries NO intervention keys and NO
    record file (byte-identical elsewhere); a hypothesis block captures even
    without the flag; a receipt-noop re-completion never re-captures."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        _set_state_dir(state)
        try:
            def _mk_repo(name: str, flag: bool, block: bool) -> "tuple[Path, Path]":
                repo = Path(td) / name
                spec_dir = repo / "docs" / "features" / "feat-a"
                spec_dir.mkdir(parents=True)
                spec_text = "# Feat A\n\n**Status:** In Progress\n"
                if block:
                    spec_text += (
                        "\n## Intervention Hypothesis\n\n"
                        "- target_signal: event:gate-refusal\n"
                        "- expected_direction: decrease\n"
                    )
                (spec_dir / "SPEC.md").write_text(spec_text, encoding="utf-8")
                # SKIP_MCP_TEST.md (KEPT by the completion cleanup, unlike
                # VALIDATED.md) so the re-completion below reaches the
                # receipt-noop path instead of the evidence-gate refusal.
                (spec_dir / "SKIP_MCP_TEST.md").write_text(
                    "---\nkind: skip-mcp-test\nfeature_id: feat-a\n---\n\n# S\n",
                    encoding="utf-8",
                )
                qdata: dict = {"queue": [{"id": "feat-a", "name": "Feat A",
                                          "spec_dir": "feat-a"}]}
                if flag:
                    qdata["interventions"] = True
                qdir = repo / "docs" / "features"
                (qdir / "queue.json").write_text(
                    json.dumps(qdata, indent=2) + "\n", encoding="utf-8")
                return repo, spec_dir

            # Flag ON → capture fires, record written, keys present.
            repo1, spec1 = _mk_repo("flag-on", flag=True, block=False)
            res1 = lazy_core.apply_pseudo(
                repo1, "__mark_complete__", spec1, date="2026-07-04")
            assert res1["ok"] is True, res1
            assert res1.get("intervention_recorded") is True, res1
            rec1 = repo1 / "docs" / "interventions" / "feat-a.md"
            assert rec1.exists()
            meta1 = lazy_core.parse_sentinel(rec1)
            assert meta1["target_signal"] == "undeclared"  # flag-on, no block
            assert meta1["pipeline"] == "feature"
            assert meta1["provenance"] == "gated"

            # Receipt-noop re-completion: no re-capture, no intervention keys.
            res1b = lazy_core.apply_pseudo(
                repo1, "__mark_complete__", spec1, date="2026-07-04")
            assert res1b["noop"] is True
            assert "intervention_recorded" not in res1b

            # Flag OFF + no block → byte-identical result keys, no record dir.
            repo2, spec2 = _mk_repo("flag-off", flag=False, block=False)
            res2 = lazy_core.apply_pseudo(
                repo2, "__mark_complete__", spec2, date="2026-07-04")
            assert res2["ok"] is True, res2
            assert "intervention_recorded" not in res2
            assert "intervention_record" not in res2
            assert not (repo2 / "docs" / "interventions").exists()

            # Hypothesis block WITHOUT the flag → capture still fires (D2-A).
            repo3, spec3 = _mk_repo("block-only", flag=False, block=True)
            res3 = lazy_core.apply_pseudo(
                repo3, "__mark_complete__", spec3, date="2026-07-04")
            assert res3["ok"] is True, res3
            assert res3.get("intervention_recorded") is True, res3
            meta3 = lazy_core.parse_sentinel(
                repo3 / "docs" / "interventions" / "feat-a.md")
            assert meta3["target_signal"] == "event:gate-refusal"
        finally:
            _clear_state_dir()




def test_apply_pseudo_mark_complete_refuses_scoped_change_missing_gate_verdict():
    """End-to-end: __mark_complete__ on a scoped item with no GATE_VERDICT.md
    refuses (zero writes beyond what already existed — no receipt)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-e2e-missing")
        _write_validated_md(spec_dir)
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-e2e-missing): work")
        state_dir = repo_root / "state-e2e-missing"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-e2e-missing", date="2026-07-12",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is False, result
        assert "harness-change design gate" in result.get("refused", ""), result
        assert not (spec_dir / "COMPLETED.md").exists(), (
            "a ship-seam refusal must write ZERO completion artifacts"
        )




def test_apply_pseudo_mark_complete_succeeds_with_clean_gate_verdict():
    """End-to-end: the SAME scoped item WITH a clean GATE_VERDICT.md
    completes normally (receipt written, Status flips)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-e2e-clean")
        _write_validated_md(spec_dir)
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-e2e-clean): work")
        _gate_write_verdict(spec_dir, {"overfit": "pass"})
        state_dir = repo_root / "state-e2e-clean"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_complete__", spec_dir,
                feature_id="feat-e2e-clean", date="2026-07-12",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is True, result
        assert (spec_dir / "COMPLETED.md").exists()




def test_apply_pseudo_mark_fixed_refuses_scoped_change_missing_gate_verdict():
    """Parity: the bug-pipeline __mark_fixed__ arm shares the SAME
    apply_pseudo branch, so the ship seam applies identically there — a
    scoped bug fix with no GATE_VERDICT.md refuses."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = repo_root / "docs" / "bugs" / "bug-e2e-missing"
        spec_dir.mkdir(parents=True)
        _write_spec_md(spec_dir, status="In-progress")
        _write_skip_mcp_test(spec_dir)
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(bug-e2e-missing): work")
        state_dir = repo_root / "state-bug-e2e-missing"
        state_dir.mkdir()
        _set_state_dir(state_dir)
        try:
            result = lazy_core.apply_pseudo(
                repo_root, "__mark_fixed__", spec_dir,
                feature_id="bug-e2e-missing", date="2026-07-12",
            )
        finally:
            _clear_state_dir()
        assert result["ok"] is False, result
        assert "harness-change design gate" in result.get("refused", ""), result
        assert not (spec_dir / "FIXED.md").exists()


_TESTS = [
    ("test_has_completion_receipt_absent", test_has_completion_receipt_absent),
    ("test_has_completion_receipt_present", test_has_completion_receipt_present),
    ("test_has_completion_receipt_none_path", test_has_completion_receipt_none_path),
    ("test_has_completion_receipt_empty_file_is_missing", test_has_completion_receipt_empty_file_is_missing),
    ("test_has_completion_receipt_no_frontmatter_is_missing", test_has_completion_receipt_no_frontmatter_is_missing),
    ("test_has_completion_receipt_kind_absent_is_missing", test_has_completion_receipt_kind_absent_is_missing),
    ("test_has_completion_receipt_wrong_kind_is_missing", test_has_completion_receipt_wrong_kind_is_missing),
    ("test_has_completion_receipt_no_provenance_is_missing", test_has_completion_receipt_no_provenance_is_missing),
    ("test_has_completion_receipt_empty_provenance_is_missing", test_has_completion_receipt_empty_provenance_is_missing),
    ("test_has_completion_receipt_malformed_emits_diagnostic", test_has_completion_receipt_malformed_emits_diagnostic),
    ("test_has_completion_receipt_valid_with_provenance", test_has_completion_receipt_valid_with_provenance),
    ("test_has_completion_receipt_fixed_md_variant", test_has_completion_receipt_fixed_md_variant),
    ("test_write_completed_receipt_minimal", test_write_completed_receipt_minimal),
    ("test_write_completed_receipt_with_optional_fields", test_write_completed_receipt_with_optional_fields),
    ("test_write_completed_receipt_atomic", test_write_completed_receipt_atomic),
    ("test_apply_pseudo_validated_from_skip_refuses_when_skip_absent", test_apply_pseudo_validated_from_skip_refuses_when_skip_absent),
    ("test_apply_pseudo_validated_from_skip_idempotent", test_apply_pseudo_validated_from_skip_idempotent),
    ("test_apply_pseudo_validated_from_skip_refuses_pipeline_granted", test_apply_pseudo_validated_from_skip_refuses_pipeline_granted),
    ("test_apply_pseudo_validated_from_results_refuses_when_results_absent", test_apply_pseudo_validated_from_results_refuses_when_results_absent),
    ("test_apply_pseudo_validated_from_results_refuses_wrong_kind", test_apply_pseudo_validated_from_results_refuses_wrong_kind),
    ("test_apply_pseudo_validated_from_results_refuses_non_passing_result", test_apply_pseudo_validated_from_results_refuses_non_passing_result),
    ("test_apply_pseudo_validated_from_results_refuses_partial_with_non_exempt_failure", test_apply_pseudo_validated_from_results_refuses_partial_with_non_exempt_failure),
    ("test_apply_pseudo_validated_from_results_refuses_partial_exemptions_without_provenance", test_apply_pseudo_validated_from_results_refuses_partial_exemptions_without_provenance),
    ("test_apply_pseudo_validated_from_results_refuses_missing_result_field", test_apply_pseudo_validated_from_results_refuses_missing_result_field),
    ("test_apply_pseudo_validated_from_results_refuses_count_mismatch", test_apply_pseudo_validated_from_results_refuses_count_mismatch),
    ("test_apply_pseudo_validated_from_results_refuses_missing_counts", test_apply_pseudo_validated_from_results_refuses_missing_counts),
    ("test_apply_pseudo_validated_from_results_refuses_stale_commit", test_apply_pseudo_validated_from_results_refuses_stale_commit),
    ("test_apply_pseudo_validated_from_results_fresh_commit_writes", test_apply_pseudo_validated_from_results_fresh_commit_writes),
    ("test_apply_pseudo_validated_from_results_legacy_no_commit_warns", test_apply_pseudo_validated_from_results_legacy_no_commit_warns),
    ("test_apply_pseudo_validated_from_results_idempotent_noop", test_apply_pseudo_validated_from_results_idempotent_noop),
    ("test_apply_pseudo_deferred_non_cloud_writes_and_idempotent", test_apply_pseudo_deferred_non_cloud_writes_and_idempotent),
    ("test_apply_pseudo_flip_cloud_saturated_flips_in_progress", test_apply_pseudo_flip_cloud_saturated_flips_in_progress),
    ("test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete", test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete),
    ("test_apply_pseudo_flip_cloud_saturated_refuses_no_plan", test_apply_pseudo_flip_cloud_saturated_refuses_no_plan),
    ("test_apply_pseudo_mark_complete_trims_feature_queue", test_apply_pseudo_mark_complete_trims_feature_queue),
    ("test_apply_pseudo_mark_complete_queue_trim_behind_receipt_noop", test_apply_pseudo_mark_complete_queue_trim_behind_receipt_noop),
    ("test_apply_pseudo_mark_fixed_does_not_trim_feature_queue", test_apply_pseudo_mark_fixed_does_not_trim_feature_queue),
    ("test_apply_pseudo_mark_complete_malformed_queue_warns_not_refuses", test_apply_pseudo_mark_complete_malformed_queue_warns_not_refuses),
    ("test_apply_pseudo_mark_complete_refuses_without_validation_evidence", test_apply_pseudo_mark_complete_refuses_without_validation_evidence),
    ("test_apply_pseudo_mark_complete_refuses_contentless_validated", test_apply_pseudo_mark_complete_refuses_contentless_validated),
    ("test_apply_pseudo_mark_complete_refuses_contentless_skip", test_apply_pseudo_mark_complete_refuses_contentless_skip),
    ("test_apply_pseudo_mark_complete_idempotent", test_apply_pseudo_mark_complete_idempotent),
    ("test_apply_pseudo_mark_complete_resumes_partial_apply", test_apply_pseudo_mark_complete_resumes_partial_apply),
    ("test_apply_pseudo_mark_complete_resume_then_clean_noop", test_apply_pseudo_mark_complete_resume_then_clean_noop),
    ("test_apply_pseudo_mark_fixed_resumes_partial_apply", test_apply_pseudo_mark_fixed_resumes_partial_apply),
    ("test_apply_pseudo_unknown_name_refuses", test_apply_pseudo_unknown_name_refuses),
    ("test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status", test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status),
    ("test_apply_pseudo_coherence_autoflips_all_ticked_phases", test_apply_pseudo_coherence_autoflips_all_ticked_phases),
    ("test_apply_pseudo_coherence_refuses_unchecked_verification_row", test_apply_pseudo_coherence_refuses_unchecked_verification_row),
    ("test_apply_pseudo_coherence_advisory_prints_genuine_row_excerpts", test_apply_pseudo_coherence_advisory_prints_genuine_row_excerpts),
    ("test_apply_pseudo_coherence_refuses_zero_checkbox_in_progress_phase", test_apply_pseudo_coherence_refuses_zero_checkbox_in_progress_phase),
    ("test_apply_pseudo_coherence_superseded_phase_with_unchecked_not_refused", test_apply_pseudo_coherence_superseded_phase_with_unchecked_not_refused),
    ("test_apply_pseudo_coherence_mark_fixed_refuses_on_unchecked", test_apply_pseudo_coherence_mark_fixed_refuses_on_unchecked),
    ("test_apply_pseudo_coherence_no_phases_md_preserves_behavior", test_apply_pseudo_coherence_no_phases_md_preserves_behavior),
    ("test_apply_pseudo_coherence_no_status_phase_all_checked_proceeds", test_apply_pseudo_coherence_no_status_phase_all_checked_proceeds),
    ("test_apply_pseudo_coherence_no_status_phase_with_unchecked_still_refuses", test_apply_pseudo_coherence_no_status_phase_with_unchecked_still_refuses),
    ("test_apply_pseudo_coherence_descoped_phase_completes", test_apply_pseudo_coherence_descoped_phase_completes),
    ("test_apply_pseudo_coherence_mark_fixed_descoped_phase_completes", test_apply_pseudo_coherence_mark_fixed_descoped_phase_completes),
    ("test_apply_pseudo_deferred_runtime_row_completes_on_structural_skip", test_apply_pseudo_deferred_runtime_row_completes_on_structural_skip),
    ("test_apply_pseudo_deferred_runtime_mark_fixed_completes_on_structural_skip", test_apply_pseudo_deferred_runtime_mark_fixed_completes_on_structural_skip),
    ("test_apply_pseudo_deferred_runtime_genuine_impl_row_still_refuses", test_apply_pseudo_deferred_runtime_genuine_impl_row_still_refuses),
    ("test_apply_pseudo_deferred_runtime_no_exemption_in_app_repo", test_apply_pseudo_deferred_runtime_no_exemption_in_app_repo),
    ("test_apply_pseudo_deferred_runtime_killswitch_restores_strict", test_apply_pseudo_deferred_runtime_killswitch_restores_strict),
    ("test_apply_pseudo_coherence_idempotent_skips_check_when_receipted", test_apply_pseudo_coherence_idempotent_skips_check_when_receipted),
    ("test_neutralize_sentinel_basic_rename", test_neutralize_sentinel_basic_rename),
    ("test_neutralize_sentinel_refuses_when_absent", test_neutralize_sentinel_refuses_when_absent),
    ("test_neutralize_sentinel_collision_appends_suffix", test_neutralize_sentinel_collision_appends_suffix),
    ("test_neutralize_sentinel_double_collision_increments", test_neutralize_sentinel_double_collision_increments),
    ("test_neutralize_sentinel_refuses_already_resolved", test_neutralize_sentinel_refuses_already_resolved),
    ("test_neutralize_sentinel_blocked_form", test_neutralize_sentinel_blocked_form),
    ("test_archive_fixed_happy_path_with_unstaged_deletion", test_archive_fixed_happy_path_with_unstaged_deletion),
    ("test_archive_fixed_refuses_without_receipt", test_archive_fixed_refuses_without_receipt),
    ("test_archive_fixed_wont_fix_archives_without_receipt", test_archive_fixed_wont_fix_archives_without_receipt),
    ("test_archive_fixed_collision_appends_suffix", test_archive_fixed_collision_appends_suffix),
    ("test_archive_fixed_rerun_is_noop", test_archive_fixed_rerun_is_noop),
    ("test_archive_fixed_resume_after_partial_move", test_archive_fixed_resume_after_partial_move),
    ("test_archive_fixed_accepts_relative_spec_path", test_archive_fixed_accepts_relative_spec_path),
    ("test_validation_escalation_retry_1_not_escalated", test_validation_escalation_retry_1_not_escalated),
    ("test_validation_escalation_retry_2_escalated", test_validation_escalation_retry_2_escalated),
    ("test_validation_escalation_other_blocker_kind_not_escalated", test_validation_escalation_other_blocker_kind_not_escalated),
    ("test_validation_escalation_missing_fields_not_escalated", test_validation_escalation_missing_fields_not_escalated),
    ("test_validation_escalation_string_digit_retry_count", test_validation_escalation_string_digit_retry_count),
    ("test_spike_escalation_retry_1_not_escalated", test_spike_escalation_retry_1_not_escalated),
    ("test_spike_escalation_retry_0_not_escalated", test_spike_escalation_retry_0_not_escalated),
    ("test_spike_escalation_retry_2_escalated", test_spike_escalation_retry_2_escalated),
    ("test_spike_escalation_other_blocker_kind_not_escalated", test_spike_escalation_other_blocker_kind_not_escalated),
    ("test_spike_escalation_missing_fields_not_escalated", test_spike_escalation_missing_fields_not_escalated),
    ("test_spike_escalation_string_digit_retry_count", test_spike_escalation_string_digit_retry_count),
    ("test_spike_escalation_bool_retry_count_rejected", test_spike_escalation_bool_retry_count_rejected),
    ("test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes", test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes),
    ("test_apply_pseudo_mark_complete_grandfathered_retro_completes", test_apply_pseudo_mark_complete_grandfathered_retro_completes),
    ("test_apply_pseudo_mark_complete_receipted_noop_beats_stale_retro", test_apply_pseudo_mark_complete_receipted_noop_beats_stale_retro),
    ("test_apply_pseudo_mark_fixed_refuses_stale_retro_zero_writes", test_apply_pseudo_mark_fixed_refuses_stale_retro_zero_writes),
    ("test_apply_pseudo_mark_fixed_grandfathered_retro_completes", test_apply_pseudo_mark_fixed_grandfathered_retro_completes),
    ("test_apply_pseudo_mark_fixed_receipted_noop_beats_stale_retro", test_apply_pseudo_mark_fixed_receipted_noop_beats_stale_retro),
    ("test_detect_noncanonical_blocker_stray_alone", test_detect_noncanonical_blocker_stray_alone),
    ("test_detect_noncanonical_blocker_resolved_excluded", test_detect_noncanonical_blocker_resolved_excluded),
    ("test_detect_noncanonical_blocker_canonical_alone", test_detect_noncanonical_blocker_canonical_alone),
    ("test_detect_noncanonical_blocker_canonical_plus_stray", test_detect_noncanonical_blocker_canonical_plus_stray),
    ("test_detect_noncanonical_blocker_lowercase_variant", test_detect_noncanonical_blocker_lowercase_variant),
    ("test_detect_noncanonical_blocker_empty_and_missing_dir", test_detect_noncanonical_blocker_empty_and_missing_dir),
    ("test_write_deferred_requires_host_empty_missing_raises", test_write_deferred_requires_host_empty_missing_raises),
    ("test_apply_pseudo_direct_call_refused_under_cycle_marker_without_orchestrator", test_apply_pseudo_direct_call_refused_under_cycle_marker_without_orchestrator),
    ("test_apply_pseudo_grant_skip_refuses_with_app_surface", test_apply_pseudo_grant_skip_refuses_with_app_surface),
    ("test_apply_pseudo_grant_skip_refuses_without_not_required", test_apply_pseudo_grant_skip_refuses_without_not_required),
    ("test_apply_pseudo_grant_skip_idempotent_noop", test_apply_pseudo_grant_skip_idempotent_noop),
    ("test_apply_pseudo_grant_skip_then_validated_roundtrip", test_apply_pseudo_grant_skip_then_validated_roundtrip),
    ("test_apply_pseudo_mark_complete_strikes_roadmap_row", test_apply_pseudo_mark_complete_strikes_roadmap_row),
    ("test_apply_pseudo_mark_complete_no_roadmap_is_noop_strike", test_apply_pseudo_mark_complete_no_roadmap_is_noop_strike),
    ("test_apply_pseudo_mark_complete_idempotent_no_reroite_strike", test_apply_pseudo_mark_complete_idempotent_no_reroite_strike),
    ("test_apply_pseudo_mark_complete_trims_by_resolved_spec_dir_followups", test_apply_pseudo_mark_complete_trims_by_resolved_spec_dir_followups),
    ("test_skip_ahead_ready_independent_no_hard_dep_on_gated_true", test_skip_ahead_ready_independent_no_hard_dep_on_gated_true),
    ("test_skip_ahead_ready_hard_dep_on_gated_false_even_if_marked", test_skip_ahead_ready_hard_dep_on_gated_false_even_if_marked),
    ("test_skip_ahead_ready_soft_composes_dep_on_gated_does_not_block", test_skip_ahead_ready_soft_composes_dep_on_gated_does_not_block),
    ("test_skip_ahead_ready_unmarked_but_dep_free_false", test_skip_ahead_ready_unmarked_but_dep_free_false),
    ("test_archive_fixed_predicate_present_in_audit", test_archive_fixed_predicate_present_in_audit),
    ("test_archive_fixed_chain_missing_produces_finding", test_archive_fixed_chain_missing_produces_finding),
    ("test_archive_fixed_real_drivers_pass_audit", test_archive_fixed_real_drivers_pass_audit),
    ("test_apply_pseudo_validated_from_results_accepts_docs_only_drift", test_apply_pseudo_validated_from_results_accepts_docs_only_drift),
    ("test_apply_pseudo_validated_from_results_refuses_non_docs_drift", test_apply_pseudo_validated_from_results_refuses_non_docs_drift),
    ("test_mark_complete_real_unchecked_row_refuses_zero_writes", test_mark_complete_real_unchecked_row_refuses_zero_writes),
    ("test_mark_complete_kill_switch_legacy_refusal_zero_mutation", test_mark_complete_kill_switch_legacy_refusal_zero_mutation),
    ("test_mark_complete_zero_test_evidence_refuses", test_mark_complete_zero_test_evidence_refuses),
    ("test_reorder_queue_to_tail_moves_entry_last", test_reorder_queue_to_tail_moves_entry_last),
    ("test_reorder_queue_to_head_moves_entry_first", test_reorder_queue_to_head_moves_entry_first),
    ("test_reorder_queue_to_int_index_moves_entry_to_index", test_reorder_queue_to_int_index_moves_entry_to_index),
    ("test_reorder_queue_remove_deletes_entry", test_reorder_queue_remove_deletes_entry),
    ("test_reorder_queue_missing_entry_dies", test_reorder_queue_missing_entry_dies),
    ("test_reorder_queue_idempotent_noop_byte_stable", test_reorder_queue_idempotent_noop_byte_stable),
    ("test_reorder_queue_malformed_json_dies", test_reorder_queue_malformed_json_dies),
    ("test_clear_queue_stub_removes_stub_when_present", test_clear_queue_stub_removes_stub_when_present),
    ("test_clear_queue_stub_absent_is_byte_stable_noop", test_clear_queue_stub_absent_is_byte_stable_noop),
    ("test_clear_queue_stub_missing_feature_id_dies", test_clear_queue_stub_missing_feature_id_dies),
    ("test_clear_queue_stub_malformed_json_dies", test_clear_queue_stub_malformed_json_dies),
    ("test_mark_complete_refused_gate_writes_no_provenance", test_mark_complete_refused_gate_writes_no_provenance),
    ("test_mark_complete_receipt_noop_writes_no_provenance", test_mark_complete_receipt_noop_writes_no_provenance),
    ("test_mark_complete_index_failure_degrades_to_warning", test_mark_complete_index_failure_degrades_to_warning),
    ("test_apply_pseudo_capture_flag_on_and_byte_identical_off", test_apply_pseudo_capture_flag_on_and_byte_identical_off),
    ("test_apply_pseudo_mark_complete_refuses_scoped_change_missing_gate_verdict", test_apply_pseudo_mark_complete_refuses_scoped_change_missing_gate_verdict),
    ("test_apply_pseudo_mark_complete_succeeds_with_clean_gate_verdict", test_apply_pseudo_mark_complete_succeeds_with_clean_gate_verdict),
    ("test_apply_pseudo_mark_fixed_refuses_scoped_change_missing_gate_verdict", test_apply_pseudo_mark_fixed_refuses_scoped_change_missing_gate_verdict),
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
