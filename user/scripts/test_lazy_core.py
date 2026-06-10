#!/usr/bin/env python3
"""
test_lazy_core.py — Characterization tests for lazy_core (WU-1.1).

These tests lock in the current behavior of domain-agnostic helpers extracted
from lazy-state.py into the new lazy_core module.

RED STATE (today): import lazy_core fails — the module doesn't exist yet.
GREEN STATE (after refactor): all assertions pass against the extracted module.

Run with: python3 user/scripts/test_lazy_core.py
Exit 0 on pass, non-zero on any failure.
No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Insert the scripts directory on sys.path so `import lazy_core` resolves when
# the module exists (hyphen-free name, so direct import works once extracted).
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Cross-platform smoke-output normalization helper (Task A)
# ---------------------------------------------------------------------------

def _normalize_smoke_output(text: str) -> str:
    """Canonicalize smoke-harness output so Windows and POSIX runs produce
    byte-identical results after normalization.

    Three transforms are applied in order:

    1. Replace the platform-specific absolute temp-root prefix that precedes a
       ``…-fixtures-<suffix>`` directory with the stable placeholder ``<TMP>/``.
       This covers:
         • POSIX form: ``/tmp/claude-1000/lazy-state-fixtures-<suffix>``
           (any ``/…/`` prefix ending just before the fixtures dir name)
         • Windows form (single-backslash, as printed by Python directly):
           ``C:\\Users\\…\\Temp\\lazy-state-fixtures-<suffix>``
         • Windows form (double-backslash, as emitted inside JSON strings):
           ``C:\\\\Users\\\\…\\\\Temp\\\\lazy-state-fixtures-<suffix>``
       The replacement preserves the fixtures-dir name so that step 2 can
       still match and canonicalize its random suffix.

    2. Replace the random fixtures suffix for BOTH scripts:
       ``(lazy-state-fixtures-|bug-state-fixtures-)[A-Za-z0-9_]+``
       → ``\\1XXXXXXXX``

    3. Canonicalize path separators **inside** the normalized temp path tail
       (the segment after ``<TMP>/…-fixtures-XXXXXXXX``): both single and
       double backslashes → forward slashes.  Only tokens that follow
       ``<TMP>/`` are touched, so normal prose is unaffected.

    Applying this function to already-normalized text is idempotent:
    ``<TMP>/`` is not a valid OS temp root, so step 1 is a no-op; step 2
    only rewrites the suffix pattern which after normalization is ``XXXXXXXX``
    (no match); step 3 only applies to segments following ``<TMP>/``.
    """
    # Step 1 — strip the platform-specific temp-root prefix.
    #
    # Character-class note: inside [...] a single \ must be written as \\
    # in a Python raw string.  We use r'...' throughout to keep the regex
    # readable without extra escaping.
    #
    # Windows paths use \ (or \\, when JSON-encoded) as separators.
    # The path segments themselves contain letters, digits, spaces (rare in
    # temp paths), hyphens — but NOT quotes, /, or \.
    # We match: drive-letter colon, then one or more separator chars, then
    # one-or-more (segment + separators) groups, ending immediately before
    # the fixtures dir name.
    #
    # POSIX paths use / and contain no quotes or whitespace.
    _TEMP_ROOT_RE = re.compile(
        r'(?:[A-Za-z]:[/\\]+(?:[^/"\\<>\s]+[/\\]+)+|/(?:[^/\s"]+/)+)'
        r'(?=(?:lazy-state-fixtures-|bug-state-fixtures-))'
    )
    text = _TEMP_ROOT_RE.sub("<TMP>/", text)

    # Step 2 — replace the random fixtures suffix.
    _SUFFIX_RE = re.compile(r'(lazy-state-fixtures-|bug-state-fixtures-)[A-Za-z0-9_]+')
    text = _SUFFIX_RE.sub(r'\1XXXXXXXX', text)

    # Step 3 — canonicalize path separators in the normalized path tail.
    # After steps 1+2 the tail looks like:
    #   <TMP>/lazy-state-fixtures-XXXXXXXX\\sub\\path  (Windows double-bs)
    #   <TMP>/lazy-state-fixtures-XXXXXXXX\sub\path    (Windows single-bs)
    #   <TMP>/lazy-state-fixtures-XXXXXXXX/sub/path    (POSIX — already clean)
    # Replace \\ first (two chars), then any remaining lone \.
    def _fix_sep(m: re.Match) -> str:
        s = m.group(0)
        s = s.replace('\\\\', '/')   # double-backslash (JSON-encoded Windows)
        s = s.replace('\\', '/')     # single-backslash (direct Windows print)
        return s

    # Match from <TMP>/ through to the end of the contiguous path token
    # (no spaces, no " boundary — paths appear inside JSON strings or prose).
    _PATH_TOKEN_RE = re.compile(r'<TMP>/[^\s"]+')
    text = _PATH_TOKEN_RE.sub(_fix_sep, text)

    return text


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


class _ModuleMissing(Exception):
    """Raised inside a test body when lazy_core is not yet importable."""


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
# Tests: importability of each expected symbol
# ---------------------------------------------------------------------------

def test_symbols_present():
    """Every helper the refactor will extract must be importable from lazy_core."""
    _guard()
    expected = [
        "_atomic_write",
        "_die",
        "clear_diagnostics",
        "parse_sentinel",
        "_parse_plan_frontmatter",
        "_plan_status",
        "_plan_lowest_phase",
        "_plan_phase_set",
        "count_deliverables",
        "remaining_unchecked_are_verification_only",
        "write_completed_receipt",
        "has_completion_receipt",
        "spec_status",
    ]
    missing = [sym for sym in expected if not hasattr(lazy_core, sym)]
    assert not missing, f"missing symbols: {missing}"


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
# Tests: count_deliverables — characterize (unchecked, checked) counts
# ---------------------------------------------------------------------------

def test_count_deliverables_empty():
    """Empty text → (0, 0)."""
    _guard()
    result = lazy_core.count_deliverables("")
    assert result == (0, 0), f"expected (0, 0), got {result}"


def test_count_deliverables_mixed():
    """Mix of checked/unchecked rows → correct counts."""
    _guard()
    text = (
        "- [ ] item A\n"
        "- [x] item B\n"
        "- [X] item C\n"
        "- [ ] item D\n"
        "  - [ ] indented\n"
        "some prose line\n"
    )
    # Expected: unchecked=3 (A, D, indented), checked=2 (B, C)
    result = lazy_core.count_deliverables(text)
    assert result == (3, 2), f"expected (3, 2), got {result}"


def test_count_deliverables_only_unchecked():
    """Only unchecked rows → checked count is 0."""
    _guard()
    text = "- [ ] alpha\n- [ ] beta\n"
    result = lazy_core.count_deliverables(text)
    assert result == (2, 0), f"expected (2, 0), got {result}"


def test_count_deliverables_only_checked():
    """Only checked rows → unchecked count is 0."""
    _guard()
    text = "- [x] done one\n- [X] done two\n"
    result = lazy_core.count_deliverables(text)
    assert result == (0, 2), f"expected (0, 2), got {result}"


# ---------------------------------------------------------------------------
# Tests: remaining_unchecked_are_verification_only
# ---------------------------------------------------------------------------

def test_ruvonly_no_unchecked():
    """No unchecked rows at all → False (nothing to verify)."""
    _guard()
    text = "- [x] done\n"
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, f"expected False, got {result}"


def test_ruvonly_all_under_heading():
    """Unchecked rows only under '### Runtime Verification' → True."""
    _guard()
    text = (
        "### Phase 1\n"
        "- [x] Implementation done\n"
        "### Runtime Verification\n"
        "- [ ] MCP smoke test passes\n"
        "- [ ] No dropout\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, f"expected True, got {result}"


def test_ruvonly_mixed_outside():
    """Unchecked row OUTSIDE verification heading → False."""
    _guard()
    text = (
        "### Phase 1\n"
        "- [ ] Real implementation task\n"
        "### Runtime Verification\n"
        "- [ ] MCP smoke test\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, f"expected False, got {result}"


def test_ruvonly_bold_marker_format():
    """Unchecked rows under bold **Runtime Verification** marker → True."""
    _guard()
    text = (
        "**Runtime Verification**\n"
        "- [ ] Verify audio output\n"
        "- [ ] Check MCP assertion\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, f"expected True, got {result}"


def test_ruvonly_mcp_integration_test_heading():
    """'MCP Integration Test' heading is also a verification section."""
    _guard()
    text = (
        "### MCP Integration Test\n"
        "- [ ] assert rms > 0\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, f"expected True, got {result}"


# ---------------------------------------------------------------------------
# Tests: parse_sentinel
# ---------------------------------------------------------------------------

def test_parse_sentinel_absent():
    """Non-existent file → None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        result = lazy_core.parse_sentinel(p)
    assert result is None, f"expected None, got {result}"


def test_parse_sentinel_no_frontmatter():
    """File with no '---' frontmatter → empty dict {} (file exists but freeform)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text("# Blocked\n\nSome prose.\n", encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert result == {}, f"expected {{}}, got {result}"


def test_parse_sentinel_with_frontmatter():
    """File with valid YAML frontmatter → parsed dict."""
    _guard()
    content = (
        "---\n"
        "kind: blocked\n"
        "feature_id: my-feature\n"
        "reason: waiting on external API\n"
        "---\n\n"
        "# Blocked\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result.get("kind") == "blocked", f"kind mismatch: {result}"
    assert result.get("feature_id") == "my-feature", f"feature_id mismatch: {result}"
    assert result.get("reason") == "waiting on external API", f"reason mismatch: {result}"


def test_parse_sentinel_leading_blanks():
    """Leading blank lines before '---' are skipped — frontmatter still parsed."""
    _guard()
    content = "\n\n---\nkind: completed\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "COMPLETED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result.get("kind") == "completed", f"kind mismatch: {result}"


# ---------------------------------------------------------------------------
# Tests: spec_status
# ---------------------------------------------------------------------------

def test_spec_status_none_path():
    """spec_status(None) → None."""
    _guard()
    result = lazy_core.spec_status(None)
    assert result is None, f"expected None, got {result}"


def test_spec_status_no_spec_md():
    """Directory with no SPEC.md → None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        result = lazy_core.spec_status(Path(td))
    assert result is None, f"expected None, got {result}"


def test_spec_status_complete():
    """SPEC.md with '**Status:** Complete' → 'Complete'."""
    _guard()
    spec_text = (
        "# My Feature\n\n"
        "**Status:** Complete\n\n"
        "## Overview\n\n"
        "Some content.\n"
    )
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        (spec_dir / "SPEC.md").write_text(spec_text, encoding="utf-8")
        result = lazy_core.spec_status(spec_dir)
    assert result == "Complete", f"expected 'Complete', got {result!r}"


def test_spec_status_in_progress():
    """SPEC.md with '**Status:** In Progress' → 'In Progress'."""
    _guard()
    spec_text = "**Status:** In Progress\n\n# Feature\n"
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        (spec_dir / "SPEC.md").write_text(spec_text, encoding="utf-8")
        result = lazy_core.spec_status(spec_dir)
    assert result == "In Progress", f"expected 'In Progress', got {result!r}"


def test_spec_status_first_occurrence_wins():
    """Only the FIRST **Status:** line is used (later occurrences are ignored)."""
    _guard()
    # Simulates a SPEC.md where Implementation Notes repeat a prior status line.
    spec_text = (
        "**Status:** In Progress\n\n"
        "## Implementation Notes\n\n"
        "Previously: **Status:** Complete\n"
    )
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        (spec_dir / "SPEC.md").write_text(spec_text, encoding="utf-8")
        result = lazy_core.spec_status(spec_dir)
    assert result == "In Progress", f"expected 'In Progress', got {result!r}"


def test_spec_status_superseded():
    """'**Status:** Superseded' → 'Superseded'."""
    _guard()
    spec_text = "**Status:** Superseded\n"
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        (spec_dir / "SPEC.md").write_text(spec_text, encoding="utf-8")
        result = lazy_core.spec_status(spec_dir)
    assert result == "Superseded", f"expected 'Superseded', got {result!r}"


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


# ---------------------------------------------------------------------------
# Tests: _atomic_write
# ---------------------------------------------------------------------------

def test_atomic_write_creates_file():
    """_atomic_write writes the expected content to the target path."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "output.txt"
        lazy_core._atomic_write(target, "hello world\n")
        content = target.read_text(encoding="utf-8")
    assert content == "hello world\n", f"unexpected content: {content!r}"


def test_atomic_write_creates_parent_dirs():
    """_atomic_write creates missing parent directories."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "nested" / "deep" / "file.txt"
        lazy_core._atomic_write(target, "nested content\n")
        content = target.read_text(encoding="utf-8")
    assert content == "nested content\n", f"unexpected content: {content!r}"


def test_atomic_write_no_tmp_residue():
    """No .tmp files left after a successful _atomic_write."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "file.txt"
        lazy_core._atomic_write(target, "data")
        tmp_files = list(Path(td).glob("*.tmp"))
    assert tmp_files == [], f"temp file(s) not cleaned up: {tmp_files}"


# ---------------------------------------------------------------------------
# Tests: _parse_plan_frontmatter / _plan_status / _plan_lowest_phase / _plan_phase_set
# ---------------------------------------------------------------------------

def test_parse_plan_frontmatter_absent():
    """Non-existent plan file → None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        result = lazy_core._parse_plan_frontmatter(p)
    assert result is None, f"expected None, got {result}"


def test_parse_plan_frontmatter_no_fence():
    """Plan with no '---' → empty dict {} (treated as legacy)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text("# Plan\n\nSome prose.\n", encoding="utf-8")
        result = lazy_core._parse_plan_frontmatter(p)
    assert result == {}, f"expected {{}}, got {result}"


def test_parse_plan_frontmatter_with_data():
    """Plan with frontmatter → parsed dict including phases list."""
    _guard()
    content = (
        "---\n"
        "kind: implementation-plan\n"
        "status: Ready\n"
        "phases:\n"
        "  - 1\n"
        "  - 2\n"
        "---\n\n"
        "# Implementation Plan\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core._parse_plan_frontmatter(p)
    assert result is not None
    assert result.get("kind") == "implementation-plan"
    assert result.get("status") == "Ready"
    assert result.get("phases") == [1, 2]


def test_plan_status_legacy_no_frontmatter():
    """Legacy plan (no frontmatter) → 'Ready' default."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text("# Plan\nNo frontmatter here.\n", encoding="utf-8")
        result = lazy_core._plan_status(p)
    assert result == "Ready", f"expected 'Ready', got {result!r}"


def test_plan_status_in_progress():
    """Plan with status: In-progress → 'In-progress'."""
    _guard()
    content = "---\nkind: implementation-plan\nstatus: In-progress\n---\n\n# Plan\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core._plan_status(p)
    assert result == "In-progress", f"expected 'In-progress', got {result!r}"


def test_plan_status_complete():
    """Plan with status: Complete → 'Complete'."""
    _guard()
    content = "---\nkind: implementation-plan\nstatus: Complete\n---\n\n# Plan\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core._plan_status(p)
    assert result == "Complete", f"expected 'Complete', got {result!r}"


def test_plan_lowest_phase_numeric():
    """Plan with phases: [3, 1, 2] → lowest is 1."""
    _guard()
    content = "---\nkind: implementation-plan\nphases:\n  - 3\n  - 1\n  - 2\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        lowest, name = lazy_core._plan_lowest_phase(p)
    assert lowest == 1, f"expected 1, got {lowest}"
    assert name == "PLAN.md", f"expected 'PLAN.md', got {name!r}"


def test_plan_lowest_phase_no_phases_field():
    """Plan without phases field → (sys.maxsize, name) so it sorts last."""
    _guard()
    import sys as _sys
    content = "---\nkind: implementation-plan\nstatus: Ready\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        lowest, name = lazy_core._plan_lowest_phase(p)
    assert lowest == _sys.maxsize, f"expected sys.maxsize, got {lowest}"


def test_plan_lowest_phase_alpha_with_leading_digit():
    """Phase '3a' contributes 3 to the sort key."""
    _guard()
    content = "---\nkind: implementation-plan\nphases:\n  - '3a'\n  - '5b'\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        lowest, _ = lazy_core._plan_lowest_phase(p)
    assert lowest == 3, f"expected 3, got {lowest}"


def test_plan_phase_set_numeric():
    """phases: [1, 2, 3] → {1, 2, 3}."""
    _guard()
    content = "---\nphases:\n  - 1\n  - 2\n  - 3\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core._plan_phase_set(p)
    assert result == {1, 2, 3}, f"expected {{1, 2, 3}}, got {result}"


def test_plan_phase_set_no_phases():
    """No phases field → empty set."""
    _guard()
    content = "---\nkind: implementation-plan\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core._plan_phase_set(p)
    assert result == set(), f"expected empty set, got {result}"


def test_plan_phase_set_alpha_entries_skipped():
    """Pure-string 'all' skipped; '3a' → 3; numeric 2 → 2."""
    _guard()
    content = "---\nphases:\n  - 'all'\n  - '3a'\n  - 2\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core._plan_phase_set(p)
    # 'all' has no leading digit → skipped; '3a' → 3; 2 → 2
    assert result == {3, 2}, f"expected {{3, 2}}, got {result}"


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


# ---------------------------------------------------------------------------
# Tests: derive_stage — maps artifact ladder to a stage label
# ---------------------------------------------------------------------------

def _make_laddered_dir(td: str) -> Path:
    """Helper: build a fully-laddered item dir (spec→research→phases→plan→implement)."""
    d = Path(td)
    (d / "SPEC.md").write_text("# Feature Spec\n", encoding="utf-8")
    (d / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
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
    return d


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


def test_derive_stage_symbol_present():
    """derive_stage must be an attribute of the lazy_core module."""
    _guard()
    assert hasattr(lazy_core, "derive_stage"), (
        "lazy_core.derive_stage does not exist — implement the function"
    )


# ---------------------------------------------------------------------------
# Tests: track_open / track_touch / track_close
# ---------------------------------------------------------------------------

_NOW1 = "2026-06-03T10:00:00Z"
_NOW2 = "2026-06-03T11:30:00Z"
_NOW3 = "2026-06-03T12:45:00Z"


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


def test_track_symbols_present():
    """track_open, track_touch, and track_close must be attributes of lazy_core."""
    _guard()
    assert hasattr(lazy_core, "track_open"), "lazy_core.track_open does not exist"
    assert hasattr(lazy_core, "track_touch"), "lazy_core.track_touch does not exist"
    assert hasattr(lazy_core, "track_close"), "lazy_core.track_close does not exist"


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
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / "lazy-state.py"), "--test"],
        capture_output=True,
        text=True,
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
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS_DIR / "bug-state.py"), "--test"],
        capture_output=True,
        text=True,
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


# ---------------------------------------------------------------------------
# Test registry — defines run order and test names.
# ---------------------------------------------------------------------------

_TESTS = [
    ("test_symbols_present", test_symbols_present),
    # count_deliverables
    ("test_count_deliverables_empty", test_count_deliverables_empty),
    ("test_count_deliverables_mixed", test_count_deliverables_mixed),
    ("test_count_deliverables_only_unchecked", test_count_deliverables_only_unchecked),
    ("test_count_deliverables_only_checked", test_count_deliverables_only_checked),
    # remaining_unchecked_are_verification_only
    ("test_ruvonly_no_unchecked", test_ruvonly_no_unchecked),
    ("test_ruvonly_all_under_heading", test_ruvonly_all_under_heading),
    ("test_ruvonly_mixed_outside", test_ruvonly_mixed_outside),
    ("test_ruvonly_bold_marker_format", test_ruvonly_bold_marker_format),
    ("test_ruvonly_mcp_integration_test_heading", test_ruvonly_mcp_integration_test_heading),
    # parse_sentinel
    ("test_parse_sentinel_absent", test_parse_sentinel_absent),
    ("test_parse_sentinel_no_frontmatter", test_parse_sentinel_no_frontmatter),
    ("test_parse_sentinel_with_frontmatter", test_parse_sentinel_with_frontmatter),
    ("test_parse_sentinel_leading_blanks", test_parse_sentinel_leading_blanks),
    # spec_status
    ("test_spec_status_none_path", test_spec_status_none_path),
    ("test_spec_status_no_spec_md", test_spec_status_no_spec_md),
    ("test_spec_status_complete", test_spec_status_complete),
    ("test_spec_status_in_progress", test_spec_status_in_progress),
    ("test_spec_status_first_occurrence_wins", test_spec_status_first_occurrence_wins),
    ("test_spec_status_superseded", test_spec_status_superseded),
    # has_completion_receipt
    ("test_has_completion_receipt_absent", test_has_completion_receipt_absent),
    ("test_has_completion_receipt_present", test_has_completion_receipt_present),
    ("test_has_completion_receipt_none_path", test_has_completion_receipt_none_path),
    # has_completion_receipt — Phase-2 receipt-validation RED tests (WU-1)
    ("test_has_completion_receipt_empty_file_is_missing", test_has_completion_receipt_empty_file_is_missing),
    ("test_has_completion_receipt_no_frontmatter_is_missing", test_has_completion_receipt_no_frontmatter_is_missing),
    ("test_has_completion_receipt_kind_absent_is_missing", test_has_completion_receipt_kind_absent_is_missing),
    ("test_has_completion_receipt_wrong_kind_is_missing", test_has_completion_receipt_wrong_kind_is_missing),
    ("test_has_completion_receipt_no_provenance_is_missing", test_has_completion_receipt_no_provenance_is_missing),
    ("test_has_completion_receipt_empty_provenance_is_missing", test_has_completion_receipt_empty_provenance_is_missing),
    ("test_has_completion_receipt_malformed_emits_diagnostic", test_has_completion_receipt_malformed_emits_diagnostic),
    ("test_has_completion_receipt_valid_with_provenance", test_has_completion_receipt_valid_with_provenance),
    ("test_has_completion_receipt_fixed_md_variant", test_has_completion_receipt_fixed_md_variant),
    # write_completed_receipt
    ("test_write_completed_receipt_minimal", test_write_completed_receipt_minimal),
    ("test_write_completed_receipt_with_optional_fields", test_write_completed_receipt_with_optional_fields),
    ("test_write_completed_receipt_atomic", test_write_completed_receipt_atomic),
    # _atomic_write
    ("test_atomic_write_creates_file", test_atomic_write_creates_file),
    ("test_atomic_write_creates_parent_dirs", test_atomic_write_creates_parent_dirs),
    ("test_atomic_write_no_tmp_residue", test_atomic_write_no_tmp_residue),
    # _parse_plan_frontmatter / _plan_status / _plan_lowest_phase / _plan_phase_set
    ("test_parse_plan_frontmatter_absent", test_parse_plan_frontmatter_absent),
    ("test_parse_plan_frontmatter_no_fence", test_parse_plan_frontmatter_no_fence),
    ("test_parse_plan_frontmatter_with_data", test_parse_plan_frontmatter_with_data),
    ("test_plan_status_legacy_no_frontmatter", test_plan_status_legacy_no_frontmatter),
    ("test_plan_status_in_progress", test_plan_status_in_progress),
    ("test_plan_status_complete", test_plan_status_complete),
    ("test_plan_lowest_phase_numeric", test_plan_lowest_phase_numeric),
    ("test_plan_lowest_phase_no_phases_field", test_plan_lowest_phase_no_phases_field),
    ("test_plan_lowest_phase_alpha_with_leading_digit", test_plan_lowest_phase_alpha_with_leading_digit),
    ("test_plan_phase_set_numeric", test_plan_phase_set_numeric),
    ("test_plan_phase_set_no_phases", test_plan_phase_set_no_phases),
    ("test_plan_phase_set_alpha_entries_skipped", test_plan_phase_set_alpha_entries_skipped),
    # derive_stage
    ("test_derive_stage_symbol_present", test_derive_stage_symbol_present),
    ("test_derive_stage_missing_dir", test_derive_stage_missing_dir),
    ("test_derive_stage_spec_only", test_derive_stage_spec_only),
    ("test_derive_stage_research_md", test_derive_stage_research_md),
    ("test_derive_stage_research_summary_md", test_derive_stage_research_summary_md),
    ("test_derive_stage_phases_only", test_derive_stage_phases_only),
    ("test_derive_stage_plan_no_checked_deliverables", test_derive_stage_plan_no_checked_deliverables),
    ("test_derive_stage_implement_checked_deliverable", test_derive_stage_implement_checked_deliverable),
    ("test_derive_stage_review", test_derive_stage_review),
    ("test_derive_stage_reviewed", test_derive_stage_reviewed),
    ("test_derive_stage_done_completed_md", test_derive_stage_done_completed_md),
    ("test_derive_stage_done_fixed_md", test_derive_stage_done_fixed_md),
    ("test_derive_stage_stale_upstream_wins_over_ladder", test_derive_stage_stale_upstream_wins_over_ladder),
    ("test_derive_stage_blocked_wins_over_ladder", test_derive_stage_blocked_wins_over_ladder),
    ("test_derive_stage_needs_input_wins_over_ladder", test_derive_stage_needs_input_wins_over_ladder),
    ("test_derive_stage_done_wins_over_blocked", test_derive_stage_done_wins_over_blocked),
    # track_open / track_touch / track_close
    ("test_track_symbols_present", test_track_symbols_present),
    ("test_track_open_creates_wip_md", test_track_open_creates_wip_md),
    ("test_track_open_idempotent_preserves_started_at", test_track_open_idempotent_preserves_started_at),
    ("test_track_open_creates_dir_if_absent", test_track_open_creates_dir_if_absent),
    ("test_track_touch_refreshes_last_touched", test_track_touch_refreshes_last_touched),
    ("test_track_touch_absent_wip_is_noop", test_track_touch_absent_wip_is_noop),
    ("test_track_close_removes_wip_md", test_track_close_removes_wip_md),
    ("test_track_close_absent_is_noop", test_track_close_absent_is_noop),
    ("test_track_open_frontmatter_roundtrip", test_track_open_frontmatter_roundtrip),
    # clear_diagnostics
    ("test_clear_diagnostics_callable", test_clear_diagnostics_callable),
    # --test baseline (zero-behavior-change contract)
    ("test_lazy_state_test_output_matches_baseline", test_lazy_state_test_output_matches_baseline),
    # bug-state --test baseline (WU-1) — RED until baseline file is created
    ("test_bug_state_test_output_matches_baseline", test_bug_state_test_output_matches_baseline),
    # cross-platform normalization helper guard — should be GREEN
    ("test_normalize_smoke_output_is_platform_neutral", test_normalize_smoke_output_is_platform_neutral),
    # bug-state AlgoBooth snapshot well-formedness (WU-2) — RED until snapshot file is created
    ("test_bug_state_algobooth_baseline_wellformed", test_bug_state_algobooth_baseline_wellformed),
    # stale_upstream / materialized — new symbol coverage
    ("test_stale_and_materialized_symbols_present", test_stale_and_materialized_symbols_present),
    # read_stale_upstream / write_stale_upstream / clear_stale_upstream
    ("test_read_stale_upstream_absent", test_read_stale_upstream_absent),
    ("test_write_then_read_stale_upstream", test_write_then_read_stale_upstream),
    ("test_clear_stale_upstream_removes_file", test_clear_stale_upstream_removes_file),
    ("test_clear_stale_upstream_absent_is_noop", test_clear_stale_upstream_absent_is_noop),
    # read_materialized / append_materialized / update_materialized_changeddate
    ("test_read_materialized_absent", test_read_materialized_absent),
    ("test_append_materialized_creates_record", test_append_materialized_creates_record),
    ("test_append_materialized_idempotent_on_wi_id", test_append_materialized_idempotent_on_wi_id),
    ("test_append_materialized_multiple_distinct", test_append_materialized_multiple_distinct),
    ("test_update_materialized_changeddate", test_update_materialized_changeddate),
    ("test_update_materialized_changeddate_absent_wi_is_noop", test_update_materialized_changeddate_absent_wi_is_noop),
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
