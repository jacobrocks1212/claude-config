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
        "build_parked_entry",
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
# Tests: fence-awareness — count_deliverables
# ---------------------------------------------------------------------------

def test_count_deliverables_skips_fenced_checkboxes():
    """Fenced - [ ] / - [x] lines inside ```...``` blocks must NOT be counted.

    Real deliverables outside the fence are still counted correctly.
    RED today: the current implementation matches all lines — including those
    inside fences — so it would return unchecked=3, checked=2 instead of
    unchecked=1, checked=1.
    """
    _guard()
    # One real unchecked, one real checked — these are the only real deliverables.
    # Three fenced lines (two unchecked, one checked) — illustrative examples only.
    text = (
        "- [ ] real deliverable\n"
        "- [x] real done\n"
        "```\n"
        "- [ ] fenced unchecked A\n"
        "- [ ] fenced unchecked B\n"
        "- [x] fenced checked\n"
        "```\n"
    )
    result = lazy_core.count_deliverables(text)
    assert result == (1, 1), (
        f"expected (unchecked=1, checked=1) with fenced lines excluded, got {result}. "
        "Fenced checkbox lines should not be counted as deliverables."
    )


def test_count_deliverables_multiple_fences():
    """Multiple code fences are each skipped; lines outside fences are counted."""
    _guard()
    text = (
        "- [ ] outside A\n"
        "```bash\n"
        "- [ ] inside fence 1\n"
        "```\n"
        "- [ ] outside B\n"
        "```\n"
        "- [ ] inside fence 2\n"
        "- [x] inside fence 3\n"
        "```\n"
        "- [x] outside done\n"
    )
    # Expecting: unchecked=2 (outside A, outside B), checked=1 (outside done)
    result = lazy_core.count_deliverables(text)
    assert result == (2, 1), (
        f"expected (unchecked=2, checked=1) with both fences excluded, got {result}."
    )


# ---------------------------------------------------------------------------
# Tests: fence-awareness — remaining_unchecked_are_verification_only
# ---------------------------------------------------------------------------

def test_verification_only_ignores_fenced_rows():
    """A fenced - [ ] inside a code example must not count as a real deliverable.

    If ALL non-fenced unchecked rows are under verification sections, the
    function must return True — even when a fenced block appearing BEFORE the
    verification section contains a - [ ] outside verification scope.

    RED today: the current parser walks every line including fenced ones, so the
    fenced - [ ] is treated as a non-verification deliverable (in_verification
    is False at the fenced line's position) → returns False.
    """
    _guard()
    # The fenced - [ ] appears in the Phase 1 body BEFORE the verification
    # section — at that point in_verification is False.  Without fence tracking,
    # the parser hits the fenced row while in_verification=False and returns
    # False immediately.  With fence tracking the fenced row is skipped and the
    # only real unchecked row (under **Runtime Verification**) is in scope.
    text = (
        "### Phase 1\n"
        "- [x] implementation done\n"
        "```\n"
        "- [ ] fenced example outside verification — not a real deliverable\n"
        "```\n"
        "**Runtime Verification**\n"
        "- [ ] run MCP smoke test\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (fenced row outside verification must be ignored), got {result}."
    )


# ---------------------------------------------------------------------------
# Tests: bold-marker clash fix — remaining_unchecked_are_verification_only
# ---------------------------------------------------------------------------

def test_verification_only_non_verification_bold_not_a_boundary():
    """A non-verification bold marker (e.g. **Assessment:**) inside a Runtime
    Verification section must NOT exit verification scope.

    Current bug: the walker treats ANY bold-lead line as a subsection boundary
    and clears in_verification when the bold text doesn't match the verification
    pattern.  A **Assessment:** line before a - [ ] row inside a verification
    section therefore produces a False return even though the row IS verification.

    RED today (bold-marker clash): the current code will return False because
    **Assessment:** is not a verification pattern, so in_verification becomes
    False before the - [ ] is evaluated.
    """
    _guard()
    text = (
        "## Runtime Verification\n"
        "**Assessment:** this feature meets acceptance criteria\n"
        "- [ ] verify output level is non-zero\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (non-verification bold must not exit verification scope), "
        f"got {result}."
    )


def test_verification_only_bold_marker_format_preserved():
    """BACKWARD-COMPAT: **Runtime Verification** bold marker + - [ ] → True.

    The real AlgoBooth PHASES.md format uses bold markers, NOT ## headings.
    This test must remain GREEN after any fix.
    """
    _guard()
    text = (
        "**Runtime Verification**\n"
        "- [ ] Verify audio output\n"
        "- [ ] Check MCP assertion\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (bold Runtime Verification marker must be respected), got {result}."
    )


def test_verification_only_heading_form_with_assessment_bold():
    """## Runtime Verification heading + **Assessment:** bold + - [ ] → True.

    The anchored form (heading) with a non-verification bold inside should
    also return True, same as the bold-marker form above.

    RED today: same bold-marker-clash bug causes False return.
    """
    _guard()
    text = (
        "### Phase 1\n"
        "- [x] write code\n"
        "### Runtime Verification\n"
        "**MCP Integration Test Assertions:**\n"
        "- [ ] assert rms > 1e-4\n"
        "**Assessment:**\n"
        "- [ ] confirm no DC offset\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (Assessment bold inside verification heading must not "
        f"exit scope), got {result}."
    )


def test_verification_only_real_task_outside_still_false():
    """BACKWARD-COMPAT: a - [ ] outside any verification section → False.

    Discrimination must be preserved — a real implementation task should never
    be mistaken for a verification-only row.
    """
    _guard()
    text = (
        "### Phase 1\n"
        "- [ ] implement the feature\n"
        "### Runtime Verification\n"
        "- [ ] verify output\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, (
        f"expected False (real implementation task outside verification must "
        f"produce False), got {result}."
    )


# ---------------------------------------------------------------------------
# Tests: fence-awareness — _unchecked_wus_in_plan_scope
# ---------------------------------------------------------------------------

def test_unchecked_wus_in_scope_skips_fenced():
    """A fenced - [ ] line inside a scoped phase must NOT appear in the output.

    RED today: the current walker has no fence tracking, so the fenced label
    is included in the returned list.
    """
    _guard()
    text = (
        "### Phase 1\n"
        "- [ ] real WU label\n"
        "```\n"
        "- [ ] fenced example label\n"
        "```\n"
        "- [ ] another real WU\n"
    )
    result = lazy_core._unchecked_wus_in_plan_scope(text, {1})
    assert "fenced example label" not in result, (
        f"fenced label must not appear in scope output; got {result}."
    )
    # Real labels must still be returned.
    assert "real WU label" in result, (
        f"'real WU label' must be in scope output; got {result}."
    )
    assert "another real WU" in result, (
        f"'another real WU' must be in scope output; got {result}."
    )


def test_unchecked_wus_in_scope_real_labels_returned():
    """Non-fenced - [ ] lines in the scoped phase ARE collected (baseline sanity)."""
    _guard()
    text = (
        "### Phase 2\n"
        "- [ ] alpha task\n"
        "- [x] done task\n"
        "- [ ] beta task\n"
    )
    result = lazy_core._unchecked_wus_in_plan_scope(text, {2})
    assert "alpha task" in result, f"'alpha task' must be returned; got {result}."
    assert "beta task" in result, f"'beta task' must be returned; got {result}."
    # Checked items are never returned.
    assert "done task" not in result, (
        f"'done task' (checked) must not be returned; got {result}."
    )


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
# Tests: build_parked_entry
# ---------------------------------------------------------------------------

def test_build_parked_entry_well_formed_sentinel():
    """Well-formed NEEDS_INPUT.md with 2 decisions and a date → all 4 keys correct."""
    _guard()
    content = (
        "---\n"
        "kind: needs-input\n"
        "feature_id: some-feature\n"
        "written_by: some-skill\n"
        "decisions:\n"
        "  - Choose auth strategy\n"
        "  - Pick database backend\n"
        "date: 2026-06-10\n"
        "---\n\n"
        "# Needs Input\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "NEEDS_INPUT.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.build_parked_entry("some-feature", p)
    assert result["id"] == "some-feature", f"id mismatch: {result}"
    assert result["sentinel"] == str(p), f"sentinel mismatch: {result}"
    assert result["decision_count"] == 2, f"decision_count should be 2, got {result['decision_count']}"
    assert result["parked_since"] == "2026-06-10", f"parked_since mismatch: {result}"


def test_build_parked_entry_missing_decisions_is_zero():
    """NEEDS_INPUT.md with no decisions: key → decision_count == 0."""
    _guard()
    content = (
        "---\n"
        "kind: needs-input\n"
        "feature_id: feat-no-decisions\n"
        "written_by: some-skill\n"
        "date: 2026-06-10\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "NEEDS_INPUT.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.build_parked_entry("feat-no-decisions", p)
    assert result["decision_count"] == 0, (
        f"missing decisions: key must yield decision_count 0, got {result['decision_count']}"
    )


def test_build_parked_entry_missing_date_is_none():
    """NEEDS_INPUT.md with no date: key → parked_since is None."""
    _guard()
    content = (
        "---\n"
        "kind: needs-input\n"
        "feature_id: feat-no-date\n"
        "written_by: some-skill\n"
        "decisions:\n"
        "  - Some decision\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "NEEDS_INPUT.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.build_parked_entry("feat-no-date", p)
    assert result["parked_since"] is None, (
        f"missing date: key must yield parked_since None, got {result['parked_since']!r}"
    )


def test_build_parked_entry_malformed_decisions_is_zero():
    """decisions: present but a scalar (not a list) → decision_count == 0 and no exception."""
    _guard()
    content = (
        "---\n"
        "kind: needs-input\n"
        "feature_id: feat-bad-decisions\n"
        "written_by: some-skill\n"
        "decisions: not-a-list\n"
        "date: 2026-06-10\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "NEEDS_INPUT.md"
        p.write_text(content, encoding="utf-8")
        # Must not raise — malformed decisions field is handled defensively
        result = lazy_core.build_parked_entry("feat-bad-decisions", p)
    assert result["decision_count"] == 0, (
        f"scalar decisions: must yield decision_count 0, got {result['decision_count']}"
    )


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
# Tests: verify_ledger — WU-1 completion-ledger verdict
# ---------------------------------------------------------------------------

def _make_git_repo_with_origin(td: str) -> tuple:
    """Helper: create a real git repo with a bare-repo origin so @{u} resolves.

    Returns (repo_root: Path, origin_path: Path).

    Steps:
      1. git init <repo_root>
      2. git init --bare <origin_path>
      3. git remote add origin <origin_path>
      4. set user.email + user.name in repo config
      5. create a minimal initial commit
      6. git push -u origin <branch>  so @{u} is set

    After this call the working tree is clean, HEAD == @{u}.
    """
    root = Path(td) / "repo"
    origin = Path(td) / "origin.git"
    root.mkdir()
    origin.mkdir()

    def _run(cmd: list, cwd=None) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if result.returncode != 0:
            raise RuntimeError(
                f"git fixture setup failed (cmd={cmd!r}): {result.stderr.strip()}"
            )

    _run(["git", "init", "-q", str(root)])
    _run(["git", "init", "--bare", "-q", str(origin)])
    _run(["git", "-C", str(root), "remote", "add", "origin", str(origin)])
    _run(["git", "-C", str(root), "config", "user.email", "test@test.local"])
    _run(["git", "-C", str(root), "config", "user.name", "Test"])

    # Create a minimal initial file and commit so the branch exists.
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    _run(["git", "-C", str(root), "add", "README.md"])
    _run(["git", "-C", str(root), "commit", "-q", "-m", "init"])

    # Detect branch name (could be "main" or "master" depending on git config).
    branch_result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    branch = branch_result.stdout.strip() or "main"

    _run(["git", "-C", str(root), "push", "-u", "origin", branch])
    return root, origin


def _write_complete_plan(plans_dir: Path, filename: str = "plan-phase-1.md") -> Path:
    """Write a minimal Complete implementation plan into plans_dir."""
    plans_dir.mkdir(parents=True, exist_ok=True)
    p = plans_dir / filename
    p.write_text(
        "---\n"
        "kind: implementation-plan\n"
        "status: Complete\n"
        "phases:\n"
        "  - 1\n"
        "---\n\n"
        "# Implementation Plan\n",
        encoding="utf-8",
    )
    return p


def _write_all_checked_phases(spec_dir: Path) -> Path:
    """Write a PHASES.md where every deliverable row is checked."""
    p = spec_dir / "PHASES.md"
    p.write_text(
        "### Phase 1\n"
        "- [x] Implement feature\n"
        "- [x] Wire into production\n",
        encoding="utf-8",
    )
    return p


def test_verify_ledger_all_green_passes():
    """All four checks true → ok=True, failing_check=None, all checks True.

    Fixture: clean tree, HEAD == @{u} (pushed), one plan with status Complete,
    PHASES.md with every deliverable checked.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        # Commit the feature files so the tree is clean and HEAD == @{u}.
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        # Push so HEAD == upstream.
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)

        result = lazy_core.verify_ledger(repo_root, spec_dir)

    assert result["ok"] is True, f"expected ok=True, got {result}"
    assert result["failing_check"] is None, (
        f"expected failing_check=None, got {result['failing_check']!r}"
    )
    checks = result["checks"]
    assert checks["clean_tree"] is True, f"clean_tree should be True: {checks}"
    assert checks["head_matches_origin"] is True, (
        f"head_matches_origin should be True: {checks}"
    )
    assert checks["plan_complete"] is True, f"plan_complete should be True: {checks}"
    assert checks["deliverables_done"] is True, (
        f"deliverables_done should be True: {checks}"
    )


def test_verify_ledger_dirty_tree_fails():
    """Untracked file in repo → ok=False, failing_check='clean_tree', clean_tree=False.

    All other conditions are green; clean_tree is the first check in order so
    it must be reported as the first failing check.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        # Commit and push so HEAD == @{u} and plan/phases are in the repo.
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)
        # NOW dirty the tree with an untracked file (after the push).
        (repo_root / "dirty.txt").write_text("untracked\n", encoding="utf-8")

        result = lazy_core.verify_ledger(repo_root, spec_dir)

    assert result["ok"] is False, f"expected ok=False with dirty tree, got {result}"
    assert result["failing_check"] == "clean_tree", (
        f"expected failing_check='clean_tree', got {result['failing_check']!r}"
    )
    assert result["checks"]["clean_tree"] is False, (
        f"clean_tree check should be False: {result['checks']}"
    )


def test_verify_ledger_behind_origin_fails():
    """HEAD ahead of @{u} (local commit not pushed) → ok=False, failing_check='head_matches_origin'.

    The tree is clean (the change is committed), so clean_tree passes.
    head_matches_origin is the second check and must be the failing_check.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        # Commit and push the feature files.
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)
        # Make a NEW local commit that is NOT pushed → HEAD ahead of @{u}, tree clean.
        (repo_root / "extra.txt").write_text("unpushed change\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "extra.txt"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "unpushed commit"], check=True, capture_output=True)

        result = lazy_core.verify_ledger(repo_root, spec_dir)

    assert result["ok"] is False, (
        f"expected ok=False when HEAD is ahead of @{{u}}, got {result}"
    )
    assert result["failing_check"] == "head_matches_origin", (
        f"expected failing_check='head_matches_origin', "
        f"got {result['failing_check']!r}"
    )
    # clean_tree must pass (the change was committed, not left staged/untracked).
    assert result["checks"]["clean_tree"] is True, (
        f"clean_tree should be True (committed, not dirty): {result['checks']}"
    )
    assert result["checks"]["head_matches_origin"] is False, (
        f"head_matches_origin should be False: {result['checks']}"
    )


def test_verify_ledger_plan_not_complete_fails():
    """Plan with status: Ready → ok=False, failing_check='plan_complete'.

    Git state is green (clean tree, HEAD == @{u}), deliverables all checked.
    plan_complete is the third check and must be the first failing check.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        # Write a plan with status: Ready (not Complete).
        plans_dir = spec_dir / "plans"
        plans_dir.mkdir(parents=True)
        ready_plan = plans_dir / "plan-phase-1.md"
        ready_plan.write_text(
            "---\n"
            "kind: implementation-plan\n"
            "status: Ready\n"
            "phases:\n"
            "  - 1\n"
            "---\n\n"
            "# Implementation Plan\n",
            encoding="utf-8",
        )
        _write_all_checked_phases(spec_dir)
        # Commit and push so git state is clean.
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)

        result = lazy_core.verify_ledger(repo_root, spec_dir)

    assert result["ok"] is False, (
        f"expected ok=False with plan status Ready, got {result}"
    )
    assert result["failing_check"] == "plan_complete", (
        f"expected failing_check='plan_complete', got {result['failing_check']!r}"
    )
    assert result["checks"]["clean_tree"] is True, (
        f"clean_tree should be True: {result['checks']}"
    )
    assert result["checks"]["head_matches_origin"] is True, (
        f"head_matches_origin should be True: {result['checks']}"
    )
    assert result["checks"]["plan_complete"] is False, (
        f"plan_complete should be False (status=Ready): {result['checks']}"
    )


def test_verify_ledger_unchecked_nonverification_deliverable_fails():
    """Real unchecked deliverable outside verification → ok=False, failing_check='deliverables_done'.

    Git state green, plan Complete; PHASES.md has a real `- [ ]` item that is
    NOT under a Runtime Verification heading.
    deliverables_done is the fourth (last) check and must be the failing check.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        # PHASES.md with a real (non-verification) unchecked deliverable.
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Implement feature\n"
            "- [ ] Wire into production context\n",  # real unchecked — NOT verification
            encoding="utf-8",
        )
        # Commit and push so git state is clean.
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)

        result = lazy_core.verify_ledger(repo_root, spec_dir)

    assert result["ok"] is False, (
        f"expected ok=False with unchecked non-verification deliverable, got {result}"
    )
    assert result["failing_check"] == "deliverables_done", (
        f"expected failing_check='deliverables_done', got {result['failing_check']!r}"
    )
    assert result["checks"]["clean_tree"] is True, (
        f"clean_tree should be True: {result['checks']}"
    )
    assert result["checks"]["head_matches_origin"] is True, (
        f"head_matches_origin should be True: {result['checks']}"
    )
    assert result["checks"]["plan_complete"] is True, (
        f"plan_complete should be True: {result['checks']}"
    )
    assert result["checks"]["deliverables_done"] is False, (
        f"deliverables_done should be False: {result['checks']}"
    )


def test_verify_ledger_unchecked_verification_only_passes():
    """PHASES.md whose only unchecked rows are under Runtime Verification → ok=True.

    This is the non-tautological discriminator: a blunt `grep -c '- [ ]'` count
    would wrongly fail this fixture because it ignores the verification heading.
    The refined deliverables_done check correctly treats these as done.

    Git state green, plan Complete, PHASES.md has checked implementation rows
    plus unchecked rows only under a ## Runtime Verification heading.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        # PHASES.md: implementation rows all checked; only unchecked rows are
        # under the Runtime Verification heading.
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Implement feature\n"
            "- [x] Wire into production context\n"
            "### Runtime Verification\n"
            "- [ ] MCP smoke test passes\n"
            "- [ ] No audio dropout under load\n",
            encoding="utf-8",
        )
        # Commit and push so git state is clean.
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)

        result = lazy_core.verify_ledger(repo_root, spec_dir)

    assert result["ok"] is True, (
        f"expected ok=True when only unchecked rows are under Runtime Verification, "
        f"got {result}"
    )
    assert result["failing_check"] is None, (
        f"expected failing_check=None, got {result['failing_check']!r}"
    )
    assert result["checks"]["deliverables_done"] is True, (
        f"deliverables_done should be True (only verification unchecked): {result['checks']}"
    )


# ---------------------------------------------------------------------------
# Tests: verify_ledger — Phase 9 WU-3 plan-scoped mode
# ---------------------------------------------------------------------------

def _write_plan(plans_dir: Path, filename: str, status: str, phases: list) -> Path:
    """Write an implementation plan with the given status + phases: list."""
    plans_dir.mkdir(parents=True, exist_ok=True)
    p = plans_dir / filename
    phases_yaml = "".join(f"  - {n}\n" for n in phases) if phases else ""
    body = (
        "---\n"
        "kind: implementation-plan\n"
        f"status: {status}\n"
    )
    if phases:
        body += "phases:\n" + phases_yaml
    body += "---\n\n# Implementation Plan\n"
    p.write_text(body, encoding="utf-8")
    return p


# A two-part PHASES.md: phases 1-2 fully ticked, phase 3 has an unchecked
# non-verification WU plus an unchecked verification row.
_PHASES_PART1_DONE_PART2_PENDING = (
    "### Phase 1\n"
    "- [x] Implement part-1 thing A\n"
    "- [x] Implement part-1 thing B\n"
    "### Phase 2\n"
    "- [x] Implement part-2-of-scope thing\n"
    "### Phase 3\n"
    "- [ ] Implement phase-3 production wiring\n"
    "**Runtime Verification**\n"
    "- [ ] Phase 3 MCP smoke test passes\n"
)


def _commit_and_push_spec(repo_root: Path) -> None:
    """Stage/commit/push everything so clean_tree + head_matches_origin pass."""
    subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", "spec"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                   capture_output=True)


def test_verify_ledger_feature_level_fails_when_part2_pending():
    """Feature-level (no --plan) on a part-1-complete/part-2-pending feature →
    plan_complete False (part-2 plan still Ready) — the false-alarm baseline.

    Discriminator: the SAME spec passes plan-scoped on part-1 (next test) but
    feature-level fails because later parts are legitimately pending.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        _write_plan(plans, "plan-part-1.md", "Complete", [1, 2])
        _write_plan(plans, "plan-part-2.md", "Ready", [3])
        (spec_dir / "PHASES.md").write_text(_PHASES_PART1_DONE_PART2_PENDING,
                                            encoding="utf-8")
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)
    assert result["ok"] is False, f"feature-level should fail (part-2 pending): {result}"
    assert result["checks"]["plan_complete"] is False, (
        f"feature-level plan_complete should be False (part-2 Ready): {result['checks']}"
    )


def test_verify_ledger_plan_scoped_part1_passes():
    """Plan-scoped on part-1 (phases [1,2], status Complete) → ok=True.

    plan_complete = part-1's own status (Complete); deliverables_done = no
    unchecked in-scope WUs (phases 1-2 fully ticked). Part-3's pending rows are
    OUT of scope and must not fail the scoped verdict.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        part1 = _write_plan(plans, "plan-part-1.md", "Complete", [1, 2])
        _write_plan(plans, "plan-part-2.md", "Ready", [3])
        (spec_dir / "PHASES.md").write_text(_PHASES_PART1_DONE_PART2_PENDING,
                                            encoding="utf-8")
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["ok"] is True, f"plan-scoped part-1 should pass: {result}"
    assert result["checks"]["plan_complete"] is True, (
        f"part-1 status is Complete → plan_complete True: {result['checks']}"
    )
    assert result["checks"]["deliverables_done"] is True, (
        f"in-scope phases 1-2 fully ticked → deliverables_done True: {result['checks']}"
    )


def test_verify_ledger_plan_scoped_part2_pending_fails():
    """Plan-scoped on part-2 (phases [3], status Ready) → plan_complete False.

    Part-2 is legitimately pending; its scoped verdict must reflect that.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        _write_plan(plans, "plan-part-1.md", "Complete", [1, 2])
        part2 = _write_plan(plans, "plan-part-2.md", "Ready", [3])
        (spec_dir / "PHASES.md").write_text(_PHASES_PART1_DONE_PART2_PENDING,
                                            encoding="utf-8")
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part2)
    assert result["ok"] is False, f"plan-scoped part-2 should fail (Ready): {result}"
    assert result["checks"]["plan_complete"] is False, (
        f"part-2 status Ready → plan_complete False: {result['checks']}"
    )


def test_verify_ledger_plan_scoped_catches_unflipped_status():
    """All in-scope WUs ticked but the plan frontmatter is still In-progress →
    plan_complete False.

    Proves the scoped check reads THIS plan's status (not just deliverables) —
    a stale, unflipped status line is caught.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        # part-1 covers phases 1-2 (both fully ticked) but status is In-progress.
        part1 = _write_plan(plans, "plan-part-1.md", "In-progress", [1, 2])
        _write_plan(plans, "plan-part-2.md", "Ready", [3])
        (spec_dir / "PHASES.md").write_text(_PHASES_PART1_DONE_PART2_PENDING,
                                            encoding="utf-8")
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["ok"] is False, f"unflipped status should fail: {result}"
    assert result["checks"]["plan_complete"] is False, (
        f"In-progress status → plan_complete False even with WUs ticked: {result['checks']}"
    )
    assert result["checks"]["deliverables_done"] is True, (
        f"in-scope WUs are ticked → deliverables_done True: {result['checks']}"
    )


def test_verify_ledger_plan_scoped_catches_in_scope_unchecked_wu():
    """Plan frontmatter Complete but an in-scope NON-verification WU is unchecked
    → deliverables_done False (verification rows in scope remain exempt).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        # part-1 claims Complete for phases [1] but phase 1 has an unchecked WU.
        part1 = _write_plan(plans, "plan-part-1.md", "Complete", [1])
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Implement thing A\n"
            "- [ ] Implement thing B (still pending)\n"
            "**Runtime Verification**\n"
            "- [ ] Phase 1 smoke test\n",  # verification row stays exempt
            encoding="utf-8",
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["ok"] is False, f"in-scope unchecked WU should fail: {result}"
    assert result["checks"]["plan_complete"] is True, (
        f"plan status Complete → plan_complete True: {result['checks']}"
    )
    assert result["checks"]["deliverables_done"] is False, (
        f"in-scope non-verification WU unchecked → deliverables_done False: {result['checks']}"
    )


def test_verify_ledger_plan_scoped_verification_only_in_scope_passes():
    """Plan Complete; in-scope unchecked rows are ALL verification → passes.

    Mirrors the feature-level verification-exemption, but scoped to the plan's
    phases — proving the scoped path preserves mid-feature verification semantics.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        part1 = _write_plan(plans, "plan-part-1.md", "Complete", [1])
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Implement thing A\n"
            "- [x] Implement thing B\n"
            "**Runtime Verification**\n"
            "- [ ] Phase 1 smoke test passes\n",  # only unchecked is verification
            encoding="utf-8",
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["ok"] is True, f"verification-only in-scope unchecked should pass: {result}"
    assert result["checks"]["deliverables_done"] is True, (
        f"only verification rows unchecked in scope → deliverables_done True: {result['checks']}"
    )


def test_verify_ledger_plan_scoped_empty_phases_falls_back_to_feature_level():
    """A plan with no `phases:` set → deliverables_done falls back to the
    feature-level semantics (unknown scope must NOT vacuously pass).

    Here the feature has a real unchecked non-verification WU somewhere, so the
    fallback correctly yields deliverables_done False.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        # No phases: field → unknown scope.
        no_phases = _write_plan(plans, "plan-all.md", "Complete", [])
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Implement thing A\n"
            "### Phase 2\n"
            "- [ ] Implement thing B (still pending, real WU)\n",
            encoding="utf-8",
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=no_phases)
    assert result["checks"]["plan_complete"] is True, (
        f"plan status Complete → plan_complete True: {result['checks']}"
    )
    assert result["checks"]["deliverables_done"] is False, (
        f"empty phases → feature-level fallback catches the real unchecked WU: {result['checks']}"
    )
    assert result["ok"] is False, f"fallback must not vacuously pass: {result}"


def test_verify_ledger_plan_scoped_missing_plan_file_fails():
    """A non-existent plan_path → plan_complete False (cannot be Complete)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        _write_plan(plans, "plan-part-1.md", "Complete", [1])
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n- [x] Implement thing A\n", encoding="utf-8"
        )
        _commit_and_push_spec(repo_root)
        missing = plans / "does-not-exist.md"
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=missing)
    assert result["checks"]["plan_complete"] is False, (
        f"missing plan file → plan_complete False: {result['checks']}"
    )
    assert result["ok"] is False, f"missing plan must fail: {result}"


# ---------------------------------------------------------------------------
# Tests: apply_pseudo — WU-2 shared deterministic sentinel/receipt dispatcher
# ---------------------------------------------------------------------------

# ---- Helpers shared across apply_pseudo tests ----

def _write_skip_mcp_test(spec_dir: Path) -> Path:
    """Write a minimal valid SKIP_MCP_TEST.md (kind: skip-mcp-test) into spec_dir."""
    p = spec_dir / "SKIP_MCP_TEST.md"
    p.write_text(
        "---\n"
        "kind: skip-mcp-test\n"
        "feature_id: test-feature\n"
        "reason: no audio path to test\n"
        "date: 2026-06-10\n"
        "---\n\n"
        "# Skip MCP Test\n",
        encoding="utf-8",
    )
    return p


def _write_mcp_test_results(
    spec_dir: Path,
    scenarios: list,
    *,
    kind: str = "mcp-test-results",
    result: str | None = "all-passing",
    pass_count="auto",
    total_count="auto",
    validated_commit: str | None = None,
) -> Path:
    """Write an MCP_TEST_RESULTS.md per the sentinel-frontmatter.md schema.

    Defaults produce a canonical PASSING run (``result: all-passing``,
    ``pass_count == total_count == len(scenarios)``) so happy-path fixtures
    satisfy the ``__write_validated_from_results__`` result-literal and count
    gates.  Keyword overrides shape the refusal fixtures:

    - ``kind`` — frontmatter ``kind:`` value (wrong-kind gate fixtures).
    - ``result=None`` / ``pass_count=None`` / ``total_count=None`` — OMIT the
      corresponding frontmatter line entirely (missing-field fixtures).
    - ``pass_count`` / ``total_count`` default to the sentinel string
      ``"auto"`` meaning ``len(scenarios)``.
    - ``validated_commit`` — omitted unless given (legacy results files
      predate the sha-freshness anchor; the schema requires it going forward).
    """
    p = spec_dir / "MCP_TEST_RESULTS.md"
    scenarios_yaml = "".join(f"  - {s}\n" for s in scenarios)
    if pass_count == "auto":
        pass_count = len(scenarios)
    if total_count == "auto":
        total_count = len(scenarios)
    lines = [
        "---",
        f"kind: {kind}",
        "feature_id: test-feature",
        f"scenarios:\n{scenarios_yaml.rstrip()}".rstrip(),
        "date: 2026-06-10",
    ]
    if result is not None:
        lines.append(f"result: {result}")
    if pass_count is not None:
        lines.append(f"pass_count: {pass_count}")
    if total_count is not None:
        lines.append(f"total_count: {total_count}")
    if validated_commit is not None:
        # Quoted: an UNQUOTED all-zeros sha would YAML-parse as int 0 (falsy),
        # silently downgrading freshness fixtures to the legacy-absent path.
        lines.append(f'validated_commit: "{validated_commit}"')
    lines += ["---", "", "# MCP Test Results"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _git_fixture_commit(root: Path) -> str:
    """Init a git repo at ``root``, commit the current tree, return HEAD's sha.

    Mirrors bug-state.py's ``step9-fresh-mcp-results`` fixture setup (init -q,
    add -A, commit -q with inline identity; ``commit.gpgsign=false`` added for
    robustness on hosts with global signing enabled) so the freshness-gate
    tests run against a genuine ``git rev-parse HEAD`` resolution.
    """
    for cmd in [
        ["git", "-C", str(root), "init", "-q"],
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
         "add", "-A"],
        ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
         "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(
                f"git fixture setup failed (cmd={cmd!r}): {r.stderr.strip()}"
            )
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    )
    if head.returncode != 0 or not head.stdout.strip():
        raise RuntimeError(f"git fixture rev-parse failed: {head.stderr.strip()}")
    return head.stdout.strip()


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


def _write_validated_md(spec_dir: Path) -> Path:
    """Write a minimal valid VALIDATED.md (kind: validated) into spec_dir."""
    p = spec_dir / "VALIDATED.md"
    p.write_text(
        "---\n"
        "kind: validated\n"
        "feature_id: test-feature\n"
        "date: 2026-06-10\n"
        "mcp_scenarios: []\n"
        "result: all-passing\n"
        "---\n\n"
        "# Validated\n",
        encoding="utf-8",
    )
    return p


def _write_spec_md(spec_dir: Path, status: str = "In-progress") -> Path:
    """Write a minimal SPEC.md with the given **Status:** line."""
    p = spec_dir / "SPEC.md"
    p.write_text(
        f"# Feature Spec\n\n"
        f"**Status:** {status}\n\n"
        "## Overview\n\n"
        "Some content.\n",
        encoding="utf-8",
    )
    return p


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
    """COMPLETED.md already present → noop=True, ok=True; a still-present
    VALIDATED.md is NOT deleted on the no-op re-run.
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
        # Also leave VALIDATED.md present — must NOT be deleted by the noop re-run.
        _write_validated_md(spec_dir)
        result = lazy_core.apply_pseudo(
            Path(td), "__mark_complete__", spec_dir, date="2026-06-10"
        )
        assert result["ok"] is True, f"expected ok=True on noop re-run, got {result}"
        assert result["noop"] is True, f"expected noop=True when COMPLETED.md exists, got {result}"
        # The leftover VALIDATED.md must NOT have been deleted.
        assert (spec_dir / "VALIDATED.md").exists(), (
            "VALIDATED.md was deleted on a noop re-run — must NOT be deleted"
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


# ---- Test 16 ----

def test_apply_pseudo_validated_from_results_escapes_special_scenarios():
    """Scenarios containing a colon (``audio: no dropout``) and a comma
    (``load, stress``) must round-trip through VALIDATED.md without corruption:
    - The colon element must remain a single string (not parsed as a mapping).
    - The comma element must not be split into two list items.
    - parse_sentinel must return exactly the original list.

    We write MCP_TEST_RESULTS.md manually with properly quoted YAML strings so
    parse_sentinel yields the intended Python list, then verify apply_pseudo
    re-emits the list in a way that round-trips correctly from VALIDATED.md.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        special_scenarios = ["audio: no dropout", "load, stress"]
        # Write MCP_TEST_RESULTS.md with YAML-quoted strings so that
        # parse_sentinel returns the scenarios as a proper Python list of strings
        # (a bare ``- audio: no dropout`` would be parsed as a mapping by YAML).
        results_path = spec_dir / "MCP_TEST_RESULTS.md"
        import yaml as _yaml
        scenarios_yaml_block = _yaml.safe_dump(
            special_scenarios, default_flow_style=False
        )
        # scenarios_yaml_block is a block-sequence string like:
        #   - 'audio: no dropout'\n- 'load, stress'\n
        # Indent each line by 2 spaces so it nests under the ``scenarios:`` key.
        indented = "".join(f"  {line}\n" if line.strip() else "" for line in scenarios_yaml_block.splitlines())
        results_path.write_text(
            "---\n"
            "kind: mcp-test-results\n"
            "feature_id: test-feature\n"
            f"scenarios:\n{indented}"
            "date: 2026-06-10\n"
            # Canonical passing fields so the hardened result-literal + count
            # gates pass — this test is about YAML round-tripping, not gating.
            "result: all-passing\n"
            "pass_count: 2\n"
            "total_count: 2\n"
            "---\n\n"
            "# MCP Test Results\n",
            encoding="utf-8",
        )
        # Confirm parse_sentinel reads them back as the right Python list before
        # we test apply_pseudo — this guards the test setup itself.
        parsed_results = lazy_core.parse_sentinel(results_path)
        assert parsed_results is not None and parsed_results.get("scenarios") == special_scenarios, (
            f"test setup error: parse_sentinel returned {parsed_results!r} "
            "for MCP_TEST_RESULTS.md — the scenarios were not serialised correctly"
        )

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

        mcp_scenarios = parsed.get("mcp_scenarios")
        # The full list must round-trip unchanged.
        assert mcp_scenarios == special_scenarios, (
            f"mcp_scenarios did not round-trip correctly; got {mcp_scenarios!r}, "
            f"expected {special_scenarios!r}"
        )
        # Colon element: must be a plain string, not a dict (yaml colon-split guard).
        assert isinstance(mcp_scenarios[0], str), (
            f"colon-containing element was parsed as {type(mcp_scenarios[0]).__name__}, "
            "expected str (yaml colon must be quoted)"
        )
        # Comma element: must be a single string, not split at the comma.
        assert isinstance(mcp_scenarios[1], str), (
            f"comma-containing element was parsed as {type(mcp_scenarios[1]).__name__}, "
            "expected str"
        )
        assert len(mcp_scenarios) == 2, (
            f"expected 2 scenarios but got {len(mcp_scenarios)}: {mcp_scenarios!r}"
        )


# ---------------------------------------------------------------------------
# Tests: parse_phases — Phase 9 WU-1 per-phase PHASES.md parser
#
# parse_phases(phases_text) -> list[dict], one dict per phase section:
#   {"heading": str, "status": str | None, "unchecked": int, "checked": int}
# A phase starts at a heading matching ^##{1,2} Phase\b (## or ### Phase ...)
# and runs to the next phase heading or EOF. status = the first **Status:**
# line value inside the section (None if absent). Checkbox counts are
# fence-aware. Content before the first phase heading is NOT a phase.
# ---------------------------------------------------------------------------

def test_parse_phases_basic_multi_phase():
    """Two phases with Status lines + mixed checkbox counts are parsed into two
    dicts with the right heading text, status, and per-section checkbox counts.
    """
    _guard()
    text = (
        "# PHASES — Feature\n"
        "\n"
        "**Status:** In-progress\n"
        "\n"
        "## Phase 1 — Foundations\n"
        "\n"
        "**Status:** Complete\n"
        "\n"
        "- [x] Build the thing\n"
        "- [x] Wire it up\n"
        "\n"
        "## Phase 2 — Polish\n"
        "\n"
        "**Status:** In-progress\n"
        "\n"
        "- [x] Done item\n"
        "- [ ] Pending item\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 2, f"expected 2 phases, got {len(phases)}: {phases!r}"
    p1, p2 = phases
    assert p1["heading"] == "## Phase 1 — Foundations", f"p1 heading: {p1['heading']!r}"
    assert p1["status"] == "Complete", f"p1 status: {p1['status']!r}"
    assert (p1["checked"], p1["unchecked"]) == (2, 0), f"p1 counts: {p1!r}"
    assert p2["heading"] == "## Phase 2 — Polish", f"p2 heading: {p2['heading']!r}"
    assert p2["status"] == "In-progress", f"p2 status: {p2['status']!r}"
    assert (p2["checked"], p2["unchecked"]) == (1, 1), f"p2 counts: {p2!r}"


def test_parse_phases_h3_headings_recognized():
    """A ``### Phase N`` heading (three-hash) is recognized as a phase start
    (the spec allows ## or ### Phase headings).
    """
    _guard()
    text = (
        "### Phase 1: Spike\n"
        "**Status:** Complete\n"
        "- [x] spike done\n"
        "### Phase 2: Build\n"
        "**Status:** Ready\n"
        "- [ ] build it\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 2, f"expected 2 phases, got {len(phases)}: {phases!r}"
    assert phases[0]["heading"] == "### Phase 1: Spike"
    assert phases[0]["status"] == "Complete"
    assert (phases[0]["checked"], phases[0]["unchecked"]) == (1, 0)
    assert phases[1]["status"] == "Ready"
    assert (phases[1]["checked"], phases[1]["unchecked"]) == (0, 1)


def test_parse_phases_fence_aware():
    """Checkbox lines inside a ``` code fence are illustrative examples and must
    NOT be counted toward the enclosing phase's checked/unchecked totals.
    """
    _guard()
    text = (
        "## Phase 1 — Demo\n"
        "**Status:** In-progress\n"
        "- [x] real done item\n"
        "\n"
        "```md\n"
        "- [ ] fenced example unchecked (must be ignored)\n"
        "- [x] fenced example checked (must be ignored)\n"
        "```\n"
        "- [ ] real pending item\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 1, f"expected 1 phase, got {len(phases)}: {phases!r}"
    p = phases[0]
    # Only the two NON-fenced rows count: 1 checked, 1 unchecked.
    assert (p["checked"], p["unchecked"]) == (1, 1), (
        f"fenced rows leaked into counts: {p!r}"
    )


def test_parse_phases_fence_with_lang_tag():
    """A fence opened with a language tag (```text) is still tracked so its rows
    are excluded.
    """
    _guard()
    text = (
        "## Phase 1\n"
        "**Status:** Complete\n"
        "```text\n"
        "- [ ] not a real deliverable\n"
        "```\n"
        "- [x] genuine deliverable\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 1
    assert (phases[0]["checked"], phases[0]["unchecked"]) == (1, 0), phases[0]


def test_parse_phases_phase_without_status_line():
    """A phase section with no ``**Status:**`` line yields status=None (canonical
    null — the caller ignores such phases for coherence purposes).
    """
    _guard()
    text = (
        "## Phase 1 — No status here\n"
        "- [x] item one\n"
        "- [ ] item two\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 1
    assert phases[0]["status"] is None, f"expected status=None, got {phases[0]['status']!r}"
    assert (phases[0]["checked"], phases[0]["unchecked"]) == (1, 1)


def test_parse_phases_top_level_status_not_captured():
    """A top-of-doc ``**Status:**`` line (before the first phase heading) must NOT
    be captured as a phase, nor leak into the first phase's status.
    """
    _guard()
    text = (
        "# PHASES — Feature\n"
        "\n"
        "**Status:** Draft\n"
        "\n"
        "Some preamble prose.\n"
        "- [ ] a stray top-level checkbox (not in any phase)\n"
        "\n"
        "## Phase 1 — First\n"
        "**Status:** Complete\n"
        "- [x] real item\n"
    )
    phases = lazy_core.parse_phases(text)
    # Exactly one phase — the top-level Status/checkbox are NOT a phase.
    assert len(phases) == 1, f"top-level content captured as a phase: {phases!r}"
    assert phases[0]["heading"] == "## Phase 1 — First"
    # The phase's status must be its OWN Complete, not the top-level Draft.
    assert phases[0]["status"] == "Complete", f"top-level Draft leaked: {phases[0]!r}"
    assert (phases[0]["checked"], phases[0]["unchecked"]) == (1, 0)


def test_parse_phases_empty_text_no_phases():
    """Text with no phase headings yields an empty list."""
    _guard()
    text = "# A doc\n\n**Status:** Draft\n\nNo phases here.\n- [ ] orphan\n"
    phases = lazy_core.parse_phases(text)
    assert phases == [], f"expected no phases, got {phases!r}"


# ---------------------------------------------------------------------------
# Tests: apply_pseudo completion-coherence enforcement — Phase 9 WU-1
#
# At __mark_complete__ / __mark_fixed__ time (AFTER the evidence gate and the
# already-has-receipt noop check, BEFORE any write):
#   (auto-flip) a phase with >=1 checkbox, zero unchecked, and a present
#     non-Complete/non-Superseded Status line is flipped to Complete in place.
#   (refuse) if any phase would remain incoherent after the auto-flips:
#     - any unchecked checkbox in any non-Superseded phase, OR
#     - any phase whose (post-flip) Status is present but not Complete/Superseded
#       (incl. zero-checkbox phases — no mechanical signal to flip on),
#   the action refuses with ZERO writes (no receipt, no status flips, no
#   sentinel deletions) and a refusal message naming each offending phase.
# Phases with NO Status line are ignored.
# ---------------------------------------------------------------------------

def _write_phases_md(spec_dir: Path, body: str) -> Path:
    """Write a PHASES.md with a top-of-doc Status line + the given phase body."""
    p = spec_dir / "PHASES.md"
    p.write_text(
        "# PHASES — Test Feature\n"
        "\n"
        "**Status:** In-progress\n"
        "\n" + body,
        encoding="utf-8",
    )
    return p


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


def test_apply_pseudo_coherence_idempotent_skips_check_when_receipted():
    """Idempotency takes precedence over the coherence check: if a valid
    COMPLETED.md already exists, the action is a noop EVEN IF PHASES.md is
    incoherent (the check runs only on the receipt-minting path). This pins the
    ordering: already-has-receipt noop BEFORE the coherence gate.
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
        assert result["ok"] is True, f"expected ok=True (noop), got {result}"
        assert result["noop"] is True, (
            f"expected noop=True (receipt present, coherence check skipped), got {result}"
        )
        assert result["refused"] is None, f"expected refused=None on noop, got {result!r}"


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
# Tests: update_repeat_count — WU-4 persisted probe signature / loop detection
# ---------------------------------------------------------------------------

# Representative state used across several tests.
_STATE_A = {
    "feature_id": "feat-a",
    "sub_skill": "/execute-plan",
    "sub_skill_args": "plan-part-1.md",
    "current_step": "Step 7a: execute plan",
}
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


# ---------------------------------------------------------------------------
# Tests: update_repeat_count — Phase 9 WU-2 HEAD-aware streak + peek mode
# ---------------------------------------------------------------------------

def _commit_dummy(repo_root: Path, name: str) -> None:
    """Make a real (no-op-ish) commit in a git repo fixture so HEAD advances."""
    (repo_root / name).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_root), "add", name], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", name],
                   check=True, capture_output=True)


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


def test_update_repeat_counts_step_counter_ignores_sub_skill_args():
    """The step signature is (feature_id, current_step) ONLY: a probe with the
    same step but a DIFFERENT sub_skill / sub_skill_args still INCREMENTS the
    step counter (while the dispatch-tuple repeat_count resets to 1).

    This is the load-bearing discriminator: a naïve impl reusing the dispatch
    tuple for the step signature would reset step_repeat_count to 1 here.
    RED: update_repeat_counts missing → AttributeError.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Non-git root → repeat_count head path is None==None (increment), so the
        # only thing resetting repeat_count below is the signature change.
        sig_path = Path(td) / "sig.json"
        r1 = lazy_core.update_repeat_counts(Path(td), _STATE_A, signature_path=sig_path)
        # Same (feature_id, current_step) but different sub_skill + args.
        r2 = lazy_core.update_repeat_counts(
            Path(td), _STATE_A_SAME_STEP_DIFF_ARGS, signature_path=sig_path
        )
    assert r1["step_repeat_count"] == 1, f"first step count should be 1, got {r1!r}"
    assert r2["step_repeat_count"] == 2, (
        f"step counter must INCREMENT when (feature_id, current_step) is unchanged "
        f"even though sub_skill/args differ, got {r2!r}"
    )
    assert r2["repeat_count"] == 1, (
        f"dispatch-tuple repeat_count must RESET when sub_skill/args change, got {r2!r}"
    )


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


# ---------------------------------------------------------------------------
# Tests: format_cycle_header — WU-5 single-probe payload (cycle header)
# ---------------------------------------------------------------------------

def test_format_cycle_header_full():
    """All counters provided, state has feature_id and sub_skill → exact pinned string.

    The 2*max_cycles arithmetic (2*8==16) is part of the contract and must be
    computed by the function, not hard-coded by the caller.
    RED: format_cycle_header missing → AttributeError after _guard().
    """
    _guard()
    state = {"feature_id": "audio-engine", "sub_skill": "/execute-plan", "other": "ignored"}
    result = lazy_core.format_cycle_header(
        state, forward_cycles=2, max_cycles=8, meta_cycles=3
    )
    expected = "### Cycle fwd 2/8 · meta 3/16 · audio-engine · /execute-plan"
    assert result == expected, (
        f"format_cycle_header returned wrong string.\n"
        f"  expected: {expected!r}\n"
        f"  got:      {result!r}"
    )


def test_format_cycle_header_missing_fields():
    """state={} and all counters None → feature/sub_skill render as —, counters as ?.

    The exact placeholder contract: counters None → '?', missing feature_id/sub_skill → '—'.
    Also verifies that 2*max_cycles renders as '?' when max_cycles is None.
    RED: format_cycle_header missing → AttributeError after _guard().
    """
    _guard()
    state = {}
    result = lazy_core.format_cycle_header(
        state, forward_cycles=None, max_cycles=None, meta_cycles=None
    )
    expected = "### Cycle fwd ?/? · meta ?/? · — · —"
    assert result == expected, (
        f"format_cycle_header returned wrong string for all-None/empty state.\n"
        f"  expected: {expected!r}\n"
        f"  got:      {result!r}"
    )


# ---------------------------------------------------------------------------
# Tests: skip_waiver_refusal — SKIP_MCP_TEST.md provenance gate (single source
# of truth for the Step-9 gates in lazy-state.py / bug-state.py and for
# apply_pseudo's __write_validated_from_skip__).
# ---------------------------------------------------------------------------

def test_skip_waiver_refusal_operator_accepts():
    """granted_by: operator is a human-reviewed waiver — accepted (None)."""
    _guard()
    assert lazy_core.skip_waiver_refusal(
        {"granted_by": "operator", "skipped_by": "operator"}
    ) is None


def test_skip_waiver_refusal_legacy_no_provenance_accepts():
    """Files with NEITHER granted_by NOR a pipeline skipped_by are
    grandfathered (pre-WU-5 legacy sentinels keep validating)."""
    _guard()
    assert lazy_core.skip_waiver_refusal({}) is None
    assert lazy_core.skip_waiver_refusal(None) is None
    # approved_by is not a provenance field — still legacy-accepted.
    assert lazy_core.skip_waiver_refusal({"approved_by": "human"}) is None
    # skipped_by: operator with no granted_by — human-authored, accepted.
    assert lazy_core.skip_waiver_refusal({"skipped_by": "operator"}) is None


def test_skip_waiver_refusal_pipeline_refuses():
    """granted_by: pipeline is a self-grant — refused with the operator-
    confirmation message (the WU-5 contract)."""
    _guard()
    reason = lazy_core.skip_waiver_refusal({"granted_by": "pipeline"})
    assert reason is not None
    assert "granted_by: pipeline" in reason
    assert "operator" in reason


def test_skip_waiver_refusal_unknown_value_refuses():
    """An unrecognized granted_by value is untrusted — refused like pipeline."""
    _guard()
    reason = lazy_core.skip_waiver_refusal({"granted_by": "subagent-7"})
    assert reason is not None
    assert "granted_by: subagent-7" in reason


def test_skip_waiver_refusal_mcp_test_with_class_accepts():
    """granted_by: mcp-test + a non-empty spec_class citation is a verified
    structural assessment by the validation step — accepted."""
    _guard()
    assert lazy_core.skip_waiver_refusal({
        "granted_by": "mcp-test",
        "spec_class": "raw-PCM injection into the Rust callback thread",
    }) is None


def test_skip_waiver_refusal_mcp_test_missing_class_refuses():
    """granted_by: mcp-test WITHOUT spec_class (absent, empty, or whitespace)
    is an unverified claim — refused."""
    _guard()
    for meta in (
        {"granted_by": "mcp-test"},
        {"granted_by": "mcp-test", "spec_class": ""},
        {"granted_by": "mcp-test", "spec_class": "   "},
        {"granted_by": "mcp-test", "spec_class": None},
    ):
        reason = lazy_core.skip_waiver_refusal(meta)
        assert reason is not None, f"expected refusal for {meta!r}"
        assert "spec_class" in reason


def test_skip_waiver_refusal_pipeline_authored_omission_refuses():
    """The omission side-door: skipped_by identifies a pipeline author but
    granted_by is absent — refused (observed 2026-06-10: an mcp-test cycle
    omitted granted_by and the skip auto-validated unconfirmed)."""
    _guard()
    for author in ("lazy", "lazy-cloud", "pipeline"):
        reason = lazy_core.skip_waiver_refusal({"skipped_by": author})
        assert reason is not None, f"expected refusal for skipped_by={author!r}"
        assert author in reason


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


# ---------------------------------------------------------------------------
# Tests: emit_cycle_prompt — Phase 8 WU-2 script-assembled cycle dispatch prompt
# ---------------------------------------------------------------------------
#
# Two flavors of test below:
#   * MATRIX tests run against the REAL template dir (the default — passing
#     template_dir=None) so any drift between the emitter and the on-disk
#     `cycle-base-prompt.md` / `loop-block.md` fails LOUDLY here.
#   * PARSER-BEHAVIOR unit tests write synthetic templates into a tmpdir and
#     pass that dir explicitly, exercising selection/refusal logic in isolation.

import os as _os  # noqa: E402  (module-level import already present; alias for clarity here)

# The real template dir, resolved the same way the emitter's default does
# (validated against the ~/.claude symlink chain in the PHASES Validated
# Assumptions table). Used by the matrix tests.
_REAL_TEMPLATE_DIR = (
    Path(__file__).resolve().parent
    / "skills" / "_components" / "lazy-batch-prompts"
)
# Fallback: when the test file is run from the canonical scripts dir, __file__'s
# parent IS user/scripts, so the template dir is parent.parent/skills/... — match
# the emitter's own default exactly.
if not _REAL_TEMPLATE_DIR.exists():
    _REAL_TEMPLATE_DIR = (
        Path(__file__).resolve().parent.parent
        / "skills" / "_components" / "lazy-batch-prompts"
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
                # Mode-specific load-bearing override anchor.
                if cloud:
                    assert "CLOUD OVERRIDE — LOAD-BEARING" in prompt, f"{ctx}: missing cloud override anchor"
                else:
                    assert "INLINE OVERRIDE — LOAD-BEARING" in prompt, f"{ctx}: missing inline override anchor"
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
    """
    _guard()
    repo = Path("/nonexistent/repo")
    state = _emit_state(sub_skill="/execute-plan")

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
    assert r["model"] == "sonnet", f"loop block still flips model to sonnet, got {r['model']!r}"


# ---------------------------------------------------------------------------
# Phase 11 WU-1a — validation_escalation(): BLOCKED.md escalation predicate
# Phase 11 WU-5c/d — retro_staleness(): retro-vs-PHASES staleness predicate
#
# These tests cover the SHARED lazy_core helpers directly, plus end-to-end
# compute_state() routing through both state scripts. The end-to-end tests
# deliberately live HERE (loaded via importlib) rather than as new smoke
# fixtures inside the scripts' own `--test` harnesses: the smoke output is
# byte-pinned to tests/baselines/*.txt, and the flag-gated byte-identity
# discipline forbids regenerating those baselines. Loading the hyphen-named
# scripts as modules lets us drive compute_state() against temp fixtures
# without touching the pinned smoke output.
# ---------------------------------------------------------------------------

# Cache of importlib-loaded state-script modules (filename → module). The
# scripts guard their CLI under `if __name__ == "__main__"`, so exec_module
# only defines functions/constants — no side effects.
_SCRIPT_MODULES: dict = {}


def _load_state_script(filename: str):
    """Load a hyphen-named state script (lazy-state.py / bug-state.py) as a module.

    Direct `import` can't resolve hyphenated filenames, so we go through
    importlib.util.spec_from_file_location. The module is cached so repeated
    tests don't re-exec the (large) script bodies. `import lazy_core` inside
    the scripts resolves via the sys.path insertion at the top of this file.
    """
    if filename not in _SCRIPT_MODULES:
        import importlib.util

        modname = filename.replace("-", "_").rsplit(".", 1)[0]
        spec = importlib.util.spec_from_file_location(
            modname, _SCRIPTS_DIR / filename
        )
        assert spec is not None and spec.loader is not None, (
            f"cannot build import spec for {filename}"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SCRIPT_MODULES[filename] = mod
    return _SCRIPT_MODULES[filename]


def _build_blocked_feature_repo(root: Path, blocked_frontmatter: str) -> Path:
    """Build a minimal feature repo whose single queue item carries BLOCKED.md.

    `blocked_frontmatter` is the raw YAML body (between the --- fences) so each
    test controls exactly which escalation fields are present/absent.
    Returns the repo root (pass to compute_state).
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    features.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "feat-esc", "name": "Feature ESC",
                 "spec_dir": "feat-esc", "tier": 1}
            ]
        }),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-esc"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "BLOCKED.md").write_text(
        "---\n" + blocked_frontmatter + "---\n\n# Blocked\n",
        encoding="utf-8",
    )
    return root


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


def _build_retro_routing_repo(
    root: Path,
    retro_done_frontmatter: str | None,
    phase_count: int = 3,
) -> Path:
    """Build a feature repo that reaches the Step 8/9 retro→MCP gate.

    Shape mirrors the `workstation-verification-only-retro-done` smoke fixture:
    all impl plans Complete + the only unchecked PHASES.md rows are Runtime
    Verification rows, so compute_state falls through Step 7 to the retro gate.
    `phase_count` controls how many `### Phase N` sections PHASES.md carries
    (the quantity retro_staleness compares against phase_count_at_retro).
    `retro_done_frontmatter` is the raw YAML body for RETRO_DONE.md, or None to
    omit the sentinel entirely (→ plain Step 8 retro dispatch).
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    features.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "feat-retro", "name": "Feature RETRO",
                 "spec_dir": "feat-retro", "tier": 1}
            ]
        }),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-retro"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
    phases_body = "# Phases\n\n"
    for n in range(1, phase_count + 1):
        phases_body += f"### Phase {n}\n- [x] Done\n\n"
    phases_body += "### Runtime Verification\n- [ ] MCP test only\n"
    (fdir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    plans = fdir / "plans"
    plans.mkdir()
    (plans / "all-phases-retro.md").write_text(
        "---\nkind: implementation-plan\nfeature_id: feat-retro\n"
        "status: Complete\ncreated: 2026-06-01\n"
        f"phases: [{', '.join(str(n) for n in range(1, phase_count + 1))}]\n"
        "---\n\n# Plan (complete)\n",
        encoding="utf-8",
    )
    if retro_done_frontmatter is not None:
        (fdir / "RETRO_DONE.md").write_text(
            "---\n" + retro_done_frontmatter + "---\n\n# Retro done\n",
            encoding="utf-8",
        )
    return root


def _build_bug_retro_routing_repo(
    root: Path,
    retro_done_frontmatter: str | None,
    phase_count: int = 3,
) -> Path:
    """Bug-pipeline mirror of _build_retro_routing_repo (docs/bugs layout).

    Builds a bug whose PHASES.md deliverables are ALL checked (unchecked == 0),
    so bug-state's compute_state falls straight through Step 7 to the Step 8
    retro gate — no Complete plan / verification-only carve-out needed.
    `phase_count` controls how many `### Phase N` sections PHASES.md carries
    (the quantity retro_staleness compares against phase_count_at_retro).
    `retro_done_frontmatter` is the raw YAML body for RETRO_DONE.md, or None to
    omit the sentinel entirely (→ plain Step 8 retro dispatch).
    """
    bugs = root / "docs" / "bugs"
    bugs.mkdir(parents=True)
    bugs.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "bug-retro", "name": "Bug RETRO", "spec_dir": "bug-retro"}
            ]
        }),
        encoding="utf-8",
    )
    bdir = bugs / "bug-retro"
    bdir.mkdir()
    (bdir / "SPEC.md").write_text(
        "# Bug RETRO\n\n"
        "**Status:** In-progress\n\n"
        "**Severity:** P1\n\n"
        "**Discovered:** 2026-06-01\n",
        encoding="utf-8",
    )
    phases_body = "# Phases\n\n"
    for n in range(1, phase_count + 1):
        phases_body += f"### Phase {n}\n- [x] Done\n\n"
    (bdir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    if retro_done_frontmatter is not None:
        (bdir / "RETRO_DONE.md").write_text(
            "---\n" + retro_done_frontmatter + "---\n\n# Retro done\n",
            encoding="utf-8",
        )
    return root


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


# ---- retro_staleness() unit tests (shared predicate) ----

def test_retro_staleness_stale_counts_returned():
    """phase_count_at_retro: 2 + PHASES.md with 3 phases → stale, returns (3, 2)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n\n"
            "### Phase 3\n- [x] C\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) == (3, 2)


def test_retro_staleness_string_digit_count():
    """phase_count_at_retro as a quoted digit string is tolerated (int coercion)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n\n"
            "### Phase 3\n- [x] C\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: \"2\"\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) == (3, 2)


def test_retro_staleness_equal_counts_fresh():
    """Equal (or fewer) phases than recorded at retro → fresh, returns None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) is None
        # Fewer phases than recorded (e.g. phases consolidated) is also fresh.
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 5\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) is None


def test_retro_staleness_missing_field_grandfathered():
    """RETRO_DONE.md without phase_count_at_retro (pre-Phase-11) → None.

    Also covers a malformed (non-numeric) field value — both grandfather to
    current behavior so existing sentinels keep routing byte-identically."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] A\n\n### Phase 2\n- [x] B\n",
            encoding="utf-8",
        )
        # Field absent entirely.
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) is None
        # Field present but malformed (not an int / digit string).
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: some\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) is None
        # RETRO_DONE.md absent entirely → no signal.
        (spec_dir / "RETRO_DONE.md").unlink()
        assert lazy_core.retro_staleness(spec_dir) is None


def test_retro_staleness_no_phases_md_no_signal():
    """RETRO_DONE.md carries the field but there is no PHASES.md → None (no signal)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 2\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) is None


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


def test_lazy_state_blocked_no_escalation_missing_fields():
    """lazy-state compute_state(): BLOCKED.md without blocker_kind/retry_count
    (legacy sentinel) → no escalation key, unchanged message (backward compat)."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_blocked_feature_repo(
            Path(td),
            "kind: blocked\nfeature_id: feat-esc\nphase: MCP Validation\n"
            "blocked_at: 2026-06-11T00:00:00Z\n",
        )
        state = ls.compute_state(root, False)
    assert state["terminal_reason"] == "blocked", state
    assert "validation_escalation" not in state, state
    assert state["notify_message"] == (
        "BLOCKED: Feature ESC — MCP Validation. Awaiting input."
    ), state["notify_message"]


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


# ---- WU-5c end-to-end: Step-8 retro-staleness routing (lazy-state only) ----

def test_lazy_state_retro_stale_routes_retro_feature():
    """RETRO_DONE.md with phase_count_at_retro: 2 + PHASES.md now carrying 3
    phases → the retro is STALE; Step 8 re-dispatches retro-feature with the
    same args as the not-exists branch and a stale-annotated current_step."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_retro_routing_repo(
            Path(td),
            "kind: retro-done\nfeature_id: feat-retro\ndate: 2026-06-01\n"
            "rounds: 1\nphase_count_at_retro: 2\n",
            phase_count=3,
        )
        state = ls.compute_state(root, False)
        spec_dir = str(root / "docs" / "features" / "feat-retro")
    assert state["sub_skill"] == "retro-feature", state
    assert state["sub_skill_args"] == f"{spec_dir} --batch", state
    assert state["current_step"] == (
        "Step 8: retro phase (stale — 1 phases added since retro)"
    ), state["current_step"]


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


def test_lazy_state_retro_fieldless_routes_past_step8():
    """A field-less (pre-Phase-11) RETRO_DONE.md is grandfathered: routing is
    byte-identical to current behavior (Step 9 mcp-test), regardless of how
    many phases PHASES.md carries now."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_retro_routing_repo(
            Path(td),
            "kind: retro-done\nfeature_id: feat-retro\ndate: 2026-06-01\n"
            "rounds: 1\n",
            phase_count=3,
        )
        state = ls.compute_state(root, False)
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]


# ---- WU-5e end-to-end: Step-8 retro-staleness routing (bug-state parity) ----
#
# The original WU-5 scoping assumed "bugs have no retro step" — wrong:
# bug-state.py has its own Step 8 (STEP_RETRO → retro-feature) and bug dirs
# carry the same RETRO_DONE.md + PHASES.md shape, so a stale BUG retro must be
# re-routed exactly like a stale feature retro.

def test_bug_state_retro_stale_routes_retro_feature():
    """bug-state: RETRO_DONE.md with phase_count_at_retro: 2 + PHASES.md now
    carrying 3 phases → the retro is STALE; Step 8 re-dispatches retro-feature
    with the same args as the not-exists branch and a stale-annotated
    current_step (exact mirror of lazy-state's Step-8 staleness branch)."""
    _guard()
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_bug_retro_routing_repo(
            Path(td),
            "kind: retro-done\nbug_id: bug-retro\ndate: 2026-06-01\n"
            "rounds: 1\nphase_count_at_retro: 2\n",
            phase_count=3,
        )
        state = bs.compute_state(root, False)
        spec_dir = str(root / "docs" / "bugs" / "bug-retro")
    assert state["sub_skill"] == "retro-feature", state
    assert state["sub_skill_args"] == f"{spec_dir} --batch", state
    assert state["current_step"] == (
        "Step 8: retro phase (stale — 1 phases added since retro)"
    ), state["current_step"]


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


def test_bug_state_retro_fieldless_routes_past_step8():
    """bug-state: a field-less (pre-Phase-11) RETRO_DONE.md is grandfathered —
    routing is byte-identical to current behavior (Step 9 mcp-test), regardless
    of how many phases PHASES.md carries now. Locks every existing smoke
    fixture (none carry phase_count_at_retro) to unchanged baselines."""
    _guard()
    bs = _load_state_script("bug-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_bug_retro_routing_repo(
            Path(td),
            "kind: retro-done\nbug_id: bug-retro\ndate: 2026-06-01\nrounds: 1\n",
            phase_count=3,
        )
        state = bs.compute_state(root, False)
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]


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
    """An already-receipted dir is a clean noop even when its RETRO_DONE.md is
    stale — the staleness backstop sits AFTER the receipt-noop (matching the
    Phase-9 coherence-gate ordering): re-completing a done feature never
    re-refuses."""
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
    assert result["ok"] is True, result
    assert result["noop"] is True, result
    assert result["refused"] is None, result


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
    """An already-receipted bug dir is a clean noop even when its RETRO_DONE.md
    is stale — the staleness backstop keeps its position AFTER the receipt-noop
    (matching the __mark_complete__ ordering): re-fixing a done bug never
    re-refuses."""
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
    assert result["noop"] is True, result
    assert result["refused"] is None, result


# ---------------------------------------------------------------------------
# Test registry — defines run order and test names.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests: Phase 1 — Run-state core (marker, prompt registry, persisted counters)
# ---------------------------------------------------------------------------
#
# ALL tests in this section are RED until lazy_core.py gains the Phase 1
# symbols.  The failure reason for each test is documented inline.
#
# Isolation discipline: every test that touches the state dir MUST set
# LAZY_STATE_DIR in os.environ to a temp dir and delete it afterward so that
# tests are hermetically isolated and never touch ~/.claude/state/.


import os as _os_env  # alias to avoid shadowing the existing `_os` alias


def _set_state_dir(path: "Path") -> None:
    """Point LAZY_STATE_DIR at the given temp dir for hermetic test isolation."""
    _os_env.environ["LAZY_STATE_DIR"] = str(path)


def _clear_state_dir() -> None:
    """Remove the LAZY_STATE_DIR override so subsequent tests are unaffected."""
    _os_env.environ.pop("LAZY_STATE_DIR", None)


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
    """Session-id staleness: mismatching session_id → None + deleted; matching
    session_id → returned; marker with session_id=None + any session arg →
    returned (bind-pending markers are never session-stale).

    RED state: read_run_marker session-id staleness not implemented.
    """
    _guard()
    import time as _time
    base_epoch = _time.time()

    # -- Path B1: bound session_id mismatch → None + file deleted
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
            assert not (state_dir / "lazy-run-marker.json").exists(), (
                "marker file must be deleted on session_id mismatch"
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
            consumed_ok = lazy_core.consume_nonce(nonce)
            assert consumed_ok is True, (
                f"consume_nonce must return True on first consumption, got {consumed_ok!r}"
            )
            after_consume = lazy_core.lookup_emission(prompt, now=now)
            assert after_consume is None, (
                "lookup_emission must return None after nonce consumed"
            )

            # second consume → False
            second = lazy_core.consume_nonce(nonce)
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


# ---------------------------------------------------------------------------
# Test 10: fold_run_counters and advance_run_counters
# ---------------------------------------------------------------------------

def test_fold_and_advance_run_counters():
    """fold_run_counters: explicit flags win; fallback to marker values; both
    None when no flags and no marker.

    advance_run_counters: truthy sub_skill not starting with '__' → increments
    forward_cycles only; '__*' or None sub_skill → increments meta_cycles only;
    no marker → returns None.

    RED state: fold_run_counters / advance_run_counters not implemented.
    """
    _guard()
    import time as _time

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
            # Real sub_skill (forward cycle)
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

            # Pseudo sub_skill (__mark_complete__) → meta cycle
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

            # sub_skill=None → meta
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

# Compiled regex for @requires first-line marker (reused across tests).
_REQUIRES_LINE_RE = re.compile(r'^<!-- @requires [a-z0-9_,]+ -->$')


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
# The 7 @requires keys the hardening dispatch template MUST declare (spec
# §"The harness-hardening stage" full contract + PHASES.md Phase 4
# deliverables).  Read dynamically from the real template where possible;
# this tuple is used as the ground-truth set to assert against.
_HARDENING_REQUIRED_KEYS: frozenset[str] = frozenset({
    "denied_prompt_summary",
    "denial_reason",
    "probe_json",
    "registry_state",
    "trigger_kind",
    "item_id",
    "cwd",
})

# Resolve the harden-harness SKILL.md path relative to the repo root inferred
# from _SCRIPTS_DIR (user/scripts).
_HARDEN_SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills" / "harden-harness" / "SKILL.md"
)


def test_hardening_dispatch_class_present():
    """Phase 4 contract: DISPATCH_CLASSES is a 7-tuple with 'hardening' as the
    last entry; DISPATCH_MODELS['hardening'] == 'opus'; calling
    emit_dispatch_prompt('hardening', ...) does NOT raise ValueError.

    RED reasons:
      - DISPATCH_CLASSES is a 6-tuple (Phase 3) → set-mismatch AssertionError.
      - DISPATCH_MODELS['hardening'] absent → KeyError.
      - emit_dispatch_prompt('hardening') raises ValueError → AssertionError.
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
    assert len(classes) == 7, (
        f"DISPATCH_CLASSES must have 7 entries after Phase 4 adds 'hardening'; "
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
            # Supply dummy values for all 7 required keys so binding can proceed
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
    declares all 7 required @requires keys, binds cleanly for feature and bug
    pipelines, and the emitted prompt satisfies the content contract.

    @requires contract (all 7 must appear in the declared set):
      denied_prompt_summary, denial_reason, probe_json, registry_state,
      trigger_kind, item_id, cwd

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
        f"dispatch-hardening.md @requires must declare all 7 required keys; "
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
# End of Phase 4 test definitions
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
    # fence-awareness: count_deliverables
    ("test_count_deliverables_skips_fenced_checkboxes", test_count_deliverables_skips_fenced_checkboxes),
    ("test_count_deliverables_multiple_fences", test_count_deliverables_multiple_fences),
    # fence-awareness: remaining_unchecked_are_verification_only
    ("test_verification_only_ignores_fenced_rows", test_verification_only_ignores_fenced_rows),
    # bold-marker clash fix: remaining_unchecked_are_verification_only
    ("test_verification_only_non_verification_bold_not_a_boundary", test_verification_only_non_verification_bold_not_a_boundary),
    ("test_verification_only_bold_marker_format_preserved", test_verification_only_bold_marker_format_preserved),
    ("test_verification_only_heading_form_with_assessment_bold", test_verification_only_heading_form_with_assessment_bold),
    ("test_verification_only_real_task_outside_still_false", test_verification_only_real_task_outside_still_false),
    # fence-awareness: _unchecked_wus_in_plan_scope
    ("test_unchecked_wus_in_scope_skips_fenced", test_unchecked_wus_in_scope_skips_fenced),
    ("test_unchecked_wus_in_scope_real_labels_returned", test_unchecked_wus_in_scope_real_labels_returned),
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
    # build_parked_entry — park-and-continue mode (WU-1 Phase 4)
    ("test_build_parked_entry_well_formed_sentinel", test_build_parked_entry_well_formed_sentinel),
    ("test_build_parked_entry_missing_decisions_is_zero", test_build_parked_entry_missing_decisions_is_zero),
    ("test_build_parked_entry_missing_date_is_none", test_build_parked_entry_missing_date_is_none),
    ("test_build_parked_entry_malformed_decisions_is_zero", test_build_parked_entry_malformed_decisions_is_zero),
    # verify_ledger — WU-1 completion-ledger verdict (Phase 5)
    ("test_verify_ledger_all_green_passes", test_verify_ledger_all_green_passes),
    ("test_verify_ledger_dirty_tree_fails", test_verify_ledger_dirty_tree_fails),
    ("test_verify_ledger_behind_origin_fails", test_verify_ledger_behind_origin_fails),
    ("test_verify_ledger_plan_not_complete_fails", test_verify_ledger_plan_not_complete_fails),
    ("test_verify_ledger_unchecked_nonverification_deliverable_fails", test_verify_ledger_unchecked_nonverification_deliverable_fails),
    ("test_verify_ledger_unchecked_verification_only_passes", test_verify_ledger_unchecked_verification_only_passes),
    # verify_ledger — Phase 9 WU-3 plan-scoped mode
    ("test_verify_ledger_feature_level_fails_when_part2_pending", test_verify_ledger_feature_level_fails_when_part2_pending),
    ("test_verify_ledger_plan_scoped_part1_passes", test_verify_ledger_plan_scoped_part1_passes),
    ("test_verify_ledger_plan_scoped_part2_pending_fails", test_verify_ledger_plan_scoped_part2_pending_fails),
    ("test_verify_ledger_plan_scoped_catches_unflipped_status", test_verify_ledger_plan_scoped_catches_unflipped_status),
    ("test_verify_ledger_plan_scoped_catches_in_scope_unchecked_wu", test_verify_ledger_plan_scoped_catches_in_scope_unchecked_wu),
    ("test_verify_ledger_plan_scoped_verification_only_in_scope_passes", test_verify_ledger_plan_scoped_verification_only_in_scope_passes),
    ("test_verify_ledger_plan_scoped_empty_phases_falls_back_to_feature_level", test_verify_ledger_plan_scoped_empty_phases_falls_back_to_feature_level),
    ("test_verify_ledger_plan_scoped_missing_plan_file_fails", test_verify_ledger_plan_scoped_missing_plan_file_fails),
    # apply_pseudo — WU-2 shared deterministic sentinel/receipt dispatcher
    ("test_apply_pseudo_validated_from_skip_writes", test_apply_pseudo_validated_from_skip_writes),
    ("test_apply_pseudo_validated_from_skip_refuses_when_skip_absent", test_apply_pseudo_validated_from_skip_refuses_when_skip_absent),
    ("test_apply_pseudo_validated_from_skip_idempotent", test_apply_pseudo_validated_from_skip_idempotent),
    # D-2: granted_by provenance gate on the CLI write path
    ("test_apply_pseudo_validated_from_skip_refuses_pipeline_granted", test_apply_pseudo_validated_from_skip_refuses_pipeline_granted),
    ("test_apply_pseudo_validated_from_skip_operator_granted_writes", test_apply_pseudo_validated_from_skip_operator_granted_writes),
    ("test_apply_pseudo_validated_from_results_copies_scenarios", test_apply_pseudo_validated_from_results_copies_scenarios),
    ("test_apply_pseudo_validated_from_results_refuses_when_results_absent", test_apply_pseudo_validated_from_results_refuses_when_results_absent),
    ("test_apply_pseudo_validated_from_results_refuses_wrong_kind", test_apply_pseudo_validated_from_results_refuses_wrong_kind),
    ("test_apply_pseudo_validated_from_results_refuses_non_passing_result", test_apply_pseudo_validated_from_results_refuses_non_passing_result),
    ("test_apply_pseudo_validated_from_results_refuses_missing_result_field", test_apply_pseudo_validated_from_results_refuses_missing_result_field),
    ("test_apply_pseudo_validated_from_results_refuses_count_mismatch", test_apply_pseudo_validated_from_results_refuses_count_mismatch),
    ("test_apply_pseudo_validated_from_results_refuses_missing_counts", test_apply_pseudo_validated_from_results_refuses_missing_counts),
    ("test_apply_pseudo_validated_from_results_refuses_stale_commit", test_apply_pseudo_validated_from_results_refuses_stale_commit),
    ("test_apply_pseudo_validated_from_results_fresh_commit_writes", test_apply_pseudo_validated_from_results_fresh_commit_writes),
    ("test_apply_pseudo_validated_from_results_legacy_no_commit_warns", test_apply_pseudo_validated_from_results_legacy_no_commit_warns),
    ("test_apply_pseudo_validated_from_results_idempotent_noop", test_apply_pseudo_validated_from_results_idempotent_noop),
    ("test_apply_pseudo_validated_from_results_happy_writes_canonical_frontmatter", test_apply_pseudo_validated_from_results_happy_writes_canonical_frontmatter),
    ("test_apply_pseudo_deferred_non_cloud_writes_and_idempotent", test_apply_pseudo_deferred_non_cloud_writes_and_idempotent),
    ("test_apply_pseudo_flip_cloud_saturated_flips_in_progress", test_apply_pseudo_flip_cloud_saturated_flips_in_progress),
    ("test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete", test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete),
    ("test_apply_pseudo_flip_cloud_saturated_refuses_no_plan", test_apply_pseudo_flip_cloud_saturated_refuses_no_plan),
    ("test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans", test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans),
    ("test_apply_pseudo_mark_complete_refuses_without_validation_evidence", test_apply_pseudo_mark_complete_refuses_without_validation_evidence),
    # D-1: content-less (touch-created) evidence must not satisfy the receipt gate
    ("test_apply_pseudo_mark_complete_refuses_contentless_validated", test_apply_pseudo_mark_complete_refuses_contentless_validated),
    ("test_apply_pseudo_mark_complete_refuses_contentless_skip", test_apply_pseudo_mark_complete_refuses_contentless_skip),
    ("test_apply_pseudo_mark_complete_idempotent", test_apply_pseudo_mark_complete_idempotent),
    ("test_apply_pseudo_mark_fixed_writes_fixed_receipt", test_apply_pseudo_mark_fixed_writes_fixed_receipt),
    ("test_apply_pseudo_unknown_name_refuses", test_apply_pseudo_unknown_name_refuses),
    ("test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status", test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status),
    ("test_apply_pseudo_validated_from_results_escapes_special_scenarios", test_apply_pseudo_validated_from_results_escapes_special_scenarios),
    # Phase 9 WU-1: parse_phases per-phase PHASES.md parser
    ("test_parse_phases_basic_multi_phase", test_parse_phases_basic_multi_phase),
    ("test_parse_phases_h3_headings_recognized", test_parse_phases_h3_headings_recognized),
    ("test_parse_phases_fence_aware", test_parse_phases_fence_aware),
    ("test_parse_phases_fence_with_lang_tag", test_parse_phases_fence_with_lang_tag),
    ("test_parse_phases_phase_without_status_line", test_parse_phases_phase_without_status_line),
    ("test_parse_phases_top_level_status_not_captured", test_parse_phases_top_level_status_not_captured),
    ("test_parse_phases_empty_text_no_phases", test_parse_phases_empty_text_no_phases),
    # Phase 9 WU-1: apply_pseudo completion-coherence enforcement
    ("test_apply_pseudo_coherence_autoflips_all_ticked_phases", test_apply_pseudo_coherence_autoflips_all_ticked_phases),
    ("test_apply_pseudo_coherence_refuses_unchecked_verification_row", test_apply_pseudo_coherence_refuses_unchecked_verification_row),
    ("test_apply_pseudo_coherence_refuses_zero_checkbox_in_progress_phase", test_apply_pseudo_coherence_refuses_zero_checkbox_in_progress_phase),
    ("test_apply_pseudo_coherence_superseded_phase_with_unchecked_not_refused", test_apply_pseudo_coherence_superseded_phase_with_unchecked_not_refused),
    ("test_apply_pseudo_coherence_mark_fixed_refuses_on_unchecked", test_apply_pseudo_coherence_mark_fixed_refuses_on_unchecked),
    ("test_apply_pseudo_coherence_no_phases_md_preserves_behavior", test_apply_pseudo_coherence_no_phases_md_preserves_behavior),
    ("test_apply_pseudo_coherence_no_status_phase_all_checked_proceeds", test_apply_pseudo_coherence_no_status_phase_all_checked_proceeds),
    ("test_apply_pseudo_coherence_no_status_phase_with_unchecked_still_refuses", test_apply_pseudo_coherence_no_status_phase_with_unchecked_still_refuses),
    ("test_apply_pseudo_coherence_idempotent_skips_check_when_receipted", test_apply_pseudo_coherence_idempotent_skips_check_when_receipted),
    # neutralize_sentinel — WU-3 rename-to-resolved helper
    ("test_neutralize_sentinel_basic_rename", test_neutralize_sentinel_basic_rename),
    ("test_neutralize_sentinel_refuses_when_absent", test_neutralize_sentinel_refuses_when_absent),
    ("test_neutralize_sentinel_collision_appends_suffix", test_neutralize_sentinel_collision_appends_suffix),
    ("test_neutralize_sentinel_double_collision_increments", test_neutralize_sentinel_double_collision_increments),
    ("test_neutralize_sentinel_refuses_already_resolved", test_neutralize_sentinel_refuses_already_resolved),
    ("test_neutralize_sentinel_blocked_form", test_neutralize_sentinel_blocked_form),
    # update_repeat_count — WU-4 persisted probe signature / loop detection
    ("test_update_repeat_count_first_call_is_one", test_update_repeat_count_first_call_is_one),
    ("test_update_repeat_count_increments_on_identical", test_update_repeat_count_increments_on_identical),
    ("test_update_repeat_count_resets_on_signature_change", test_update_repeat_count_resets_on_signature_change),
    ("test_update_repeat_count_args_distinguish_signature", test_update_repeat_count_args_distinguish_signature),
    ("test_update_repeat_count_corrupt_file_resets", test_update_repeat_count_corrupt_file_resets),
    ("test_update_repeat_count_pipelines_are_isolated", test_update_repeat_count_pipelines_are_isolated),
    # update_repeat_count — Phase 9 WU-2 HEAD-aware streak + peek mode
    ("test_update_repeat_count_head_advance_resets", test_update_repeat_count_head_advance_resets),
    ("test_update_repeat_count_same_head_increments", test_update_repeat_count_same_head_increments),
    ("test_update_repeat_count_legacy_file_without_head_increments", test_update_repeat_count_legacy_file_without_head_increments),
    ("test_update_repeat_count_peek_does_not_mutate", test_update_repeat_count_peek_does_not_mutate),
    ("test_update_repeat_count_non_git_root_stores_none_head", test_update_repeat_count_non_git_root_stores_none_head),
    # update_repeat_counts — Phase 10 WU-2 step-level oscillation counter
    ("test_update_repeat_counts_returns_both_counts", test_update_repeat_counts_returns_both_counts),
    ("test_update_repeat_counts_step_counter_ignores_sub_skill_args", test_update_repeat_counts_step_counter_ignores_sub_skill_args),
    ("test_update_repeat_counts_step_counter_resets_on_step_change", test_update_repeat_counts_step_counter_resets_on_step_change),
    ("test_update_repeat_counts_step_no_head_advance_reset", test_update_repeat_counts_step_no_head_advance_reset),
    ("test_update_repeat_counts_step_peek_does_not_mutate", test_update_repeat_counts_step_peek_does_not_mutate),
    ("test_update_repeat_counts_legacy_file_without_step_keys", test_update_repeat_counts_legacy_file_without_step_keys),
    ("test_update_repeat_count_wrapper_still_returns_int", test_update_repeat_count_wrapper_still_returns_int),
    # git_guard_status — WU-5 single-probe payload (git guards)
    ("test_git_guard_status_clean_and_pushed", test_git_guard_status_clean_and_pushed),
    ("test_git_guard_status_dirty_tree", test_git_guard_status_dirty_tree),
    ("test_git_guard_status_unpushed_commit", test_git_guard_status_unpushed_commit),
    ("test_git_guard_status_invalid_repo_is_safe_dirty", test_git_guard_status_invalid_repo_is_safe_dirty),
    # format_cycle_header — WU-5 single-probe payload (cycle header)
    ("test_format_cycle_header_full", test_format_cycle_header_full),
    ("test_format_cycle_header_missing_fields", test_format_cycle_header_missing_fields),
    # skip_waiver_refusal — SKIP_MCP_TEST.md provenance gate
    ("test_skip_waiver_refusal_operator_accepts", test_skip_waiver_refusal_operator_accepts),
    ("test_skip_waiver_refusal_legacy_no_provenance_accepts", test_skip_waiver_refusal_legacy_no_provenance_accepts),
    ("test_skip_waiver_refusal_pipeline_refuses", test_skip_waiver_refusal_pipeline_refuses),
    ("test_skip_waiver_refusal_unknown_value_refuses", test_skip_waiver_refusal_unknown_value_refuses),
    ("test_skip_waiver_refusal_mcp_test_with_class_accepts", test_skip_waiver_refusal_mcp_test_with_class_accepts),
    ("test_skip_waiver_refusal_mcp_test_missing_class_refuses", test_skip_waiver_refusal_mcp_test_missing_class_refuses),
    ("test_skip_waiver_refusal_pipeline_authored_omission_refuses", test_skip_waiver_refusal_pipeline_authored_omission_refuses),
    # archive_fixed — scripted __mark_fixed__ archive mechanics
    ("test_archive_fixed_happy_path_with_unstaged_deletion", test_archive_fixed_happy_path_with_unstaged_deletion),
    ("test_archive_fixed_refuses_without_receipt", test_archive_fixed_refuses_without_receipt),
    ("test_archive_fixed_wont_fix_archives_without_receipt", test_archive_fixed_wont_fix_archives_without_receipt),
    ("test_archive_fixed_collision_appends_suffix", test_archive_fixed_collision_appends_suffix),
    ("test_archive_fixed_rerun_is_noop", test_archive_fixed_rerun_is_noop),
    ("test_archive_fixed_resume_after_partial_move", test_archive_fixed_resume_after_partial_move),
    # emit_cycle_prompt — Phase 8 WU-2 script-assembled cycle dispatch prompt
    ("test_emit_cycle_prompt_symbol_present", test_emit_cycle_prompt_symbol_present),
    ("test_emit_cycle_prompt_binding_matrix_real_template", test_emit_cycle_prompt_binding_matrix_real_template),
    ("test_emit_cycle_prompt_mcp_test_variant_anchors_real_template", test_emit_cycle_prompt_mcp_test_variant_anchors_real_template),
    ("test_emit_cycle_prompt_bug_tokens_real_template", test_emit_cycle_prompt_bug_tokens_real_template),
    ("test_emit_cycle_prompt_pseudo_and_idle_return_none", test_emit_cycle_prompt_pseudo_and_idle_return_none),
    ("test_emit_cycle_prompt_loop_append_and_model_flip", test_emit_cycle_prompt_loop_append_and_model_flip),
    ("test_emit_cycle_prompt_section_selection_synthetic", test_emit_cycle_prompt_section_selection_synthetic),
    ("test_emit_cycle_prompt_refuses_unknown_token_synthetic", test_emit_cycle_prompt_refuses_unknown_token_synthetic),
    ("test_emit_cycle_prompt_mcp_variant_routing_synthetic", test_emit_cycle_prompt_mcp_variant_routing_synthetic),
    ("test_emit_cycle_prompt_work_branch_fallback_non_git", test_emit_cycle_prompt_work_branch_fallback_non_git),
    ("test_emit_cycle_prompt_sub_skill_args_none_binds_empty", test_emit_cycle_prompt_sub_skill_args_none_binds_empty),
    # emit_cycle_prompt repo prompt addenda — Phase 10 WU-3
    ("test_emit_cycle_prompt_addenda_absent_is_byte_identical", test_emit_cycle_prompt_addenda_absent_is_byte_identical),
    ("test_emit_cycle_prompt_addenda_selected_and_appended_after_base", test_emit_cycle_prompt_addenda_selected_and_appended_after_base),
    ("test_emit_cycle_prompt_addenda_filtered_by_skill_and_pipeline_and_mode", test_emit_cycle_prompt_addenda_filtered_by_skill_and_pipeline_and_mode),
    ("test_emit_cycle_prompt_addenda_tokens_bound", test_emit_cycle_prompt_addenda_tokens_bound),
    ("test_emit_cycle_prompt_addenda_residue_refuses_naming_file", test_emit_cycle_prompt_addenda_residue_refuses_naming_file),
    ("test_emit_cycle_prompt_addenda_before_loop_block", test_emit_cycle_prompt_addenda_before_loop_block),
    # validation_escalation — Phase 11 WU-1a shared BLOCKED.md escalation predicate
    ("test_validation_escalation_retry_1_not_escalated", test_validation_escalation_retry_1_not_escalated),
    ("test_validation_escalation_retry_2_escalated", test_validation_escalation_retry_2_escalated),
    ("test_validation_escalation_other_blocker_kind_not_escalated", test_validation_escalation_other_blocker_kind_not_escalated),
    ("test_validation_escalation_missing_fields_not_escalated", test_validation_escalation_missing_fields_not_escalated),
    ("test_validation_escalation_string_digit_retry_count", test_validation_escalation_string_digit_retry_count),
    # retro_staleness — Phase 11 WU-5c/d shared staleness predicate
    ("test_retro_staleness_stale_counts_returned", test_retro_staleness_stale_counts_returned),
    ("test_retro_staleness_string_digit_count", test_retro_staleness_string_digit_count),
    ("test_retro_staleness_equal_counts_fresh", test_retro_staleness_equal_counts_fresh),
    ("test_retro_staleness_missing_field_grandfathered", test_retro_staleness_missing_field_grandfathered),
    ("test_retro_staleness_no_phases_md_no_signal", test_retro_staleness_no_phases_md_no_signal),
    # Phase 11 WU-1a end-to-end — blocked-terminal escalation payload (both scripts)
    ("test_lazy_state_blocked_escalation_payload", test_lazy_state_blocked_escalation_payload),
    ("test_lazy_state_blocked_no_escalation_retry_1", test_lazy_state_blocked_no_escalation_retry_1),
    ("test_lazy_state_blocked_no_escalation_missing_fields", test_lazy_state_blocked_no_escalation_missing_fields),
    ("test_bug_state_blocked_escalation_payload", test_bug_state_blocked_escalation_payload),
    ("test_bug_state_blocked_no_escalation_other_kind", test_bug_state_blocked_no_escalation_other_kind),
    # Phase 11 WU-5c end-to-end — Step-8 retro-staleness routing (lazy-state)
    ("test_lazy_state_retro_stale_routes_retro_feature", test_lazy_state_retro_stale_routes_retro_feature),
    ("test_lazy_state_retro_fresh_routes_past_step8", test_lazy_state_retro_fresh_routes_past_step8),
    ("test_lazy_state_retro_fieldless_routes_past_step8", test_lazy_state_retro_fieldless_routes_past_step8),
    # Phase 11 WU-5e end-to-end — Step-8 retro-staleness routing (bug-state parity)
    ("test_bug_state_retro_stale_routes_retro_feature", test_bug_state_retro_stale_routes_retro_feature),
    ("test_bug_state_retro_fresh_routes_past_step8", test_bug_state_retro_fresh_routes_past_step8),
    ("test_bug_state_retro_fieldless_routes_past_step8", test_bug_state_retro_fieldless_routes_past_step8),
    # Phase 11 WU-5d/5e — apply_pseudo __mark_complete__/__mark_fixed__ retro-staleness backstop
    ("test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes", test_apply_pseudo_mark_complete_refuses_stale_retro_zero_writes),
    ("test_apply_pseudo_mark_complete_grandfathered_retro_completes", test_apply_pseudo_mark_complete_grandfathered_retro_completes),
    ("test_apply_pseudo_mark_complete_receipted_noop_beats_stale_retro", test_apply_pseudo_mark_complete_receipted_noop_beats_stale_retro),
    ("test_apply_pseudo_mark_fixed_refuses_stale_retro_zero_writes", test_apply_pseudo_mark_fixed_refuses_stale_retro_zero_writes),
    ("test_apply_pseudo_mark_fixed_grandfathered_retro_completes", test_apply_pseudo_mark_fixed_grandfathered_retro_completes),
    ("test_apply_pseudo_mark_fixed_receipted_noop_beats_stale_retro", test_apply_pseudo_mark_fixed_receipted_noop_beats_stale_retro),
    # Phase 1 — run-state core (marker, registry, counters)
    ("test_run_state_symbols_present", test_run_state_symbols_present),
    ("test_marker_write_read_roundtrip", test_marker_write_read_roundtrip),
    ("test_marker_staleness_age", test_marker_staleness_age),
    ("test_marker_staleness_session_id", test_marker_staleness_session_id),
    ("test_registry_register_lookup_consume", test_registry_register_lookup_consume),
    ("test_registry_ttl", test_registry_ttl),
    ("test_registry_ring_cap", test_registry_ring_cap),
    ("test_crlf_lf_normalization", test_crlf_lf_normalization),
    ("test_register_emission_if_marked_gating", test_register_emission_if_marked_gating),
    ("test_fold_and_advance_run_counters", test_fold_and_advance_run_counters),
    ("test_subprocess_emit_prompt_with_marker_writes_registry", test_subprocess_emit_prompt_with_marker_writes_registry),
    # Phase 1 review fixes: corrupt-marker delete + peek-no-advance + freshness-leg
    ("test_corrupt_marker_returns_none_and_deletes", test_corrupt_marker_returns_none_and_deletes),
    ("test_repeat_count_peek_does_not_advance_marker_counters", test_repeat_count_peek_does_not_advance_marker_counters),
    # Phase 3 — emit_dispatch_prompt (--emit-dispatch <class>)
    ("test_emit_dispatch_symbols_present", test_emit_dispatch_symbols_present),
    ("test_emit_dispatch_real_templates_exist_and_declare_requires", test_emit_dispatch_real_templates_exist_and_declare_requires),
    ("test_emit_dispatch_real_template_binding_matrix", test_emit_dispatch_real_template_binding_matrix),
    ("test_emit_dispatch_refuses_missing_requires", test_emit_dispatch_refuses_missing_requires),
    ("test_emit_dispatch_refuses_unbound_residue", test_emit_dispatch_refuses_unbound_residue),
    ("test_emit_dispatch_section_filtering", test_emit_dispatch_section_filtering),
    ("test_emit_dispatch_unknown_class_raises", test_emit_dispatch_unknown_class_raises),
    ("test_emit_dispatch_cli_registry_gating", test_emit_dispatch_cli_registry_gating),
    ("test_emit_dispatch_cli_bug_state_mirror", test_emit_dispatch_cli_bug_state_mirror),
    # Phase 4 — /harden-harness skill + hardening dispatch class
    ("test_hardening_dispatch_class_present", test_hardening_dispatch_class_present),
    ("test_hardening_template_binding", test_hardening_template_binding),
    ("test_hardening_skill_file_contract", test_hardening_skill_file_contract),
    ("test_hardening_cli_emit_and_register", test_hardening_cli_emit_and_register),
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
