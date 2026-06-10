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


def _write_mcp_test_results(spec_dir: Path, scenarios: list) -> Path:
    """Write a minimal valid MCP_TEST_RESULTS.md (kind: mcp-test-results) with the
    given scenarios list.  The YAML list is serialised inline for simplicity.
    """
    p = spec_dir / "MCP_TEST_RESULTS.md"
    scenarios_yaml = "".join(f"  - {s}\n" for s in scenarios)
    p.write_text(
        "---\n"
        "kind: mcp-test-results\n"
        "feature_id: test-feature\n"
        f"scenarios:\n{scenarios_yaml}"
        "date: 2026-06-10\n"
        "---\n\n"
        "# MCP Test Results\n",
        encoding="utf-8",
    )
    return p


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
    # apply_pseudo — WU-2 shared deterministic sentinel/receipt dispatcher
    ("test_apply_pseudo_validated_from_skip_writes", test_apply_pseudo_validated_from_skip_writes),
    ("test_apply_pseudo_validated_from_skip_refuses_when_skip_absent", test_apply_pseudo_validated_from_skip_refuses_when_skip_absent),
    ("test_apply_pseudo_validated_from_skip_idempotent", test_apply_pseudo_validated_from_skip_idempotent),
    ("test_apply_pseudo_validated_from_results_copies_scenarios", test_apply_pseudo_validated_from_results_copies_scenarios),
    ("test_apply_pseudo_validated_from_results_refuses_when_results_absent", test_apply_pseudo_validated_from_results_refuses_when_results_absent),
    ("test_apply_pseudo_deferred_non_cloud_writes_and_idempotent", test_apply_pseudo_deferred_non_cloud_writes_and_idempotent),
    ("test_apply_pseudo_flip_cloud_saturated_flips_in_progress", test_apply_pseudo_flip_cloud_saturated_flips_in_progress),
    ("test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete", test_apply_pseudo_flip_cloud_saturated_idempotent_on_complete),
    ("test_apply_pseudo_flip_cloud_saturated_refuses_no_plan", test_apply_pseudo_flip_cloud_saturated_refuses_no_plan),
    ("test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans", test_apply_pseudo_mark_complete_writes_receipt_flips_and_cleans),
    ("test_apply_pseudo_mark_complete_refuses_without_validation_evidence", test_apply_pseudo_mark_complete_refuses_without_validation_evidence),
    ("test_apply_pseudo_mark_complete_idempotent", test_apply_pseudo_mark_complete_idempotent),
    ("test_apply_pseudo_mark_fixed_writes_fixed_receipt", test_apply_pseudo_mark_fixed_writes_fixed_receipt),
    ("test_apply_pseudo_unknown_name_refuses", test_apply_pseudo_unknown_name_refuses),
    ("test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status", test_apply_pseudo_flip_cloud_saturated_refuses_when_no_frontmatter_status),
    ("test_apply_pseudo_validated_from_results_escapes_special_scenarios", test_apply_pseudo_validated_from_results_escapes_special_scenarios),
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
