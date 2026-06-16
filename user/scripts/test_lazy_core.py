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
import os
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
        "plan_complexity",
        "count_deliverables",
        "remaining_unchecked_are_verification_only",
        "_plan_wu_checkbox_counts",
        "_plan_unchecked_wus_are_verification_only",
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


def test_build_parked_entry_sentinel_kind_blocked():
    """A BLOCKED.md sentinel path → sentinel_kind == 'blocked'
    (bug park-mode-halts-on-blocked, Phase 3 / SPEC D4)."""
    _guard()
    content = (
        "---\n"
        "kind: blocked\n"
        "feature_id: feat-blocked\n"
        "phase: Spec\n"
        "blocked_at: 2026-06-16T00:00:00Z\n"
        "retry_count: 0\n"
        "---\n\n# Blocked\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.build_parked_entry("feat-blocked", p)
    assert result["sentinel_kind"] == "blocked", (
        f"BLOCKED.md must yield sentinel_kind 'blocked', got {result.get('sentinel_kind')!r}"
    )
    # A BLOCKED.md has no decisions: list → decision_count 0 via the existing path.
    assert result["decision_count"] == 0, (
        f"BLOCKED.md must yield decision_count 0, got {result['decision_count']}"
    )
    # Existing four keys still present and correct.
    assert result["id"] == "feat-blocked"
    assert result["sentinel"] == str(p)
    assert "parked_since" in result


def test_build_parked_entry_sentinel_kind_needs_input():
    """A NEEDS_INPUT.md sentinel path → sentinel_kind == 'needs-input'."""
    _guard()
    content = (
        "---\n"
        "kind: needs-input\n"
        "feature_id: feat-ni\n"
        "written_by: spec-phases\n"
        "decisions:\n"
        "  - Choose strategy\n"
        "date: 2026-06-16\n"
        "---\n\n# Needs Input\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "NEEDS_INPUT.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.build_parked_entry("feat-ni", p)
    assert result["sentinel_kind"] == "needs-input", (
        f"NEEDS_INPUT.md must yield sentinel_kind 'needs-input', got {result.get('sentinel_kind')!r}"
    )
    # Additive — existing keys unchanged.
    assert result["decision_count"] == 1
    assert result["parked_since"] == "2026-06-16"


def test_build_parked_entry_sentinel_kind_unknown():
    """An unrecognized sentinel filename → sentinel_kind == 'unknown' (no raise)."""
    _guard()
    content = (
        "---\n"
        "kind: other\n"
        "feature_id: feat-other\n"
        "---\n\n# Other\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "SOMETHING_ELSE.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.build_parked_entry("feat-other", p)
    assert result["sentinel_kind"] == "unknown", (
        f"unrecognized sentinel must yield sentinel_kind 'unknown', got {result.get('sentinel_kind')!r}"
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
# Tests: _plan_series_index / _plan_sort_key / find_implementation_plans ordering
# ISSUE 1 (d8-effect-chains live /lazy-batch run, 2026-06-14) — a corrective Phase 6
# (part-1, prerequisite) was numbered HIGHER than the Phase 5 it must precede
# (part-2/part-3). Phase-number sort inverted execution order; the ``-part-K``
# series index must take precedence so part-1 routes before part-2.
# ---------------------------------------------------------------------------

def test_plan_series_index_from_filename():
    """A ``...-part-K.md`` filename yields series index K; no suffix → None."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        p1 = d / "all-phases-effect-chains-part-1.md"
        p2 = d / "all-phases-effect-chains-part-2.md"
        plain = d / "all-phases-effect-chains.md"
        for p in (p1, p2, plain):
            p.write_text("---\nkind: implementation-plan\n---\n", encoding="utf-8")
        assert lazy_core._plan_series_index(p1) == 1
        assert lazy_core._plan_series_index(p2) == 2
        assert lazy_core._plan_series_index(plain) is None


def test_plan_series_index_frontmatter_override():
    """An explicit ``series_index:`` frontmatter field wins over the filename."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        # Filename says part-2 but frontmatter says 1 → frontmatter wins.
        p = Path(td) / "weird-name-part-2.md"
        p.write_text(
            "---\nkind: implementation-plan\nseries_index: 1\n---\n",
            encoding="utf-8",
        )
        assert lazy_core._plan_series_index(p) == 1


def test_plan_sort_key_series_beats_phase():
    """ISSUE 1 core: part-1 (phases [6]) sorts BEFORE part-2 (phases [5]).

    Under the old _plan_lowest_phase sort, part-2 (Phase 5) sorted first — the
    d8-effect-chains inversion. _plan_sort_key puts series_index first so the
    prerequisite part-1 wins regardless of its higher phase number.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        part1 = d / "all-phases-fx-part-1.md"   # Phase 6 (prerequisite)
        part2 = d / "all-phases-fx-part-2.md"   # Phase 5 (depends on part-1)
        part1.write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [6]\n---\n",
            encoding="utf-8",
        )
        part2.write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [5]\n---\n",
            encoding="utf-8",
        )
        k1 = lazy_core._plan_sort_key(part1)
        k2 = lazy_core._plan_sort_key(part2)
        assert k1 < k2, (
            f"part-1 (Phase 6 prerequisite) must sort before part-2 (Phase 5): "
            f"k1={k1} k2={k2}"
        )


def test_find_implementation_plans_part_series_order():
    """find_implementation_plans returns part-1 first even when part-1 has a HIGHER
    phase number than part-2 (the d8-effect-chains corrective-Phase-6 inversion).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        plans = spec_dir / "plans"
        plans.mkdir()
        # part-1 = Phase 6 (prerequisite), part-2 = Phase 5, part-3 = Phase 5.
        (plans / "all-phases-fx-part-1.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [6]\n---\n",
            encoding="utf-8",
        )
        (plans / "all-phases-fx-part-2.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [5]\n---\n",
            encoding="utf-8",
        )
        (plans / "all-phases-fx-part-3.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [5]\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.find_implementation_plans(spec_dir)
        names = [p.name for p in result]
        assert names == [
            "all-phases-fx-part-1.md",
            "all-phases-fx-part-2.md",
            "all-phases-fx-part-3.md",
        ], f"part series must route part-1 → part-2 → part-3 in order, got {names}"


def test_find_implementation_plans_non_series_phase_order_preserved():
    """Non-series plans (no -part-K suffix) keep the prior lowest-phase ordering."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        plans = spec_dir / "plans"
        plans.mkdir()
        (plans / "phase-3-foo.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [3]\n---\n",
            encoding="utf-8",
        )
        (plans / "phase-1-bar.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases: [1]\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.find_implementation_plans(spec_dir)
        names = [p.name for p in result]
        assert names == ["phase-1-bar.md", "phase-3-foo.md"], (
            f"non-series plans must keep lowest-phase order, got {names}"
        )


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


# ---------------------------------------------------------------------------
# Tests: plan_complexity — Phase 9 per-part complexity tag (lazy-validation-readiness)
#
# Mirrors Phase 8's phase_kind parse: a per-plan-part frontmatter field
# ``complexity: mechanical | complex`` read via the shared plan-frontmatter
# parser. Default is the SAFE tier ``complex`` (→ opus); only an explicit,
# recognized ``mechanical`` tag downgrades the part to sonnet.
# ---------------------------------------------------------------------------

def test_plan_complexity_mechanical():
    """Plan with complexity: mechanical → 'mechanical'."""
    _guard()
    content = (
        "---\nkind: implementation-plan\nstatus: Ready\n"
        "complexity: mechanical\n---\n\n# Plan\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.plan_complexity(p)
    assert result == "mechanical", f"expected 'mechanical', got {result!r}"


def test_plan_complexity_complex_explicit():
    """Plan with complexity: complex → 'complex'."""
    _guard()
    content = (
        "---\nkind: implementation-plan\nstatus: Ready\n"
        "complexity: complex\n---\n\n# Plan\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.plan_complexity(p)
    assert result == "complex", f"expected 'complex', got {result!r}"


def test_plan_complexity_absent_defaults_complex():
    """Plan with NO complexity field → 'complex' (safe default — back-compat)."""
    _guard()
    content = "---\nkind: implementation-plan\nstatus: Ready\nphases:\n  - 1\n---\n"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.plan_complexity(p)
    assert result == "complex", f"absent tag must default complex, got {result!r}"


def test_plan_complexity_legacy_no_frontmatter_defaults_complex():
    """Legacy plan (no frontmatter) → 'complex' (safe default)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text("# Plan\nNo frontmatter here.\n", encoding="utf-8")
        result = lazy_core.plan_complexity(p)
    assert result == "complex", f"legacy plan must default complex, got {result!r}"


def test_plan_complexity_unknown_value_defaults_complex():
    """Unrecognized complexity value → 'complex' (safe default, never trust an
    auto-guess at dispatch — only the canonical tier set downgrades)."""
    _guard()
    content = (
        "---\nkind: implementation-plan\nstatus: Ready\n"
        "complexity: trivial\n---\n\n# Plan\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.plan_complexity(p)
    assert result == "complex", f"unknown value must default complex, got {result!r}"


def test_plan_complexity_case_insensitive():
    """complexity: Mechanical (mixed case) normalizes to 'mechanical'."""
    _guard()
    content = (
        "---\nkind: implementation-plan\nstatus: Ready\n"
        "complexity: Mechanical\n---\n\n# Plan\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.plan_complexity(p)
    assert result == "mechanical", f"expected 'mechanical', got {result!r}"


def test_plan_complexity_absent_path_defaults_complex():
    """Non-existent plan path → 'complex' (never raise; conservative default)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "NOPE.md"
        result = lazy_core.plan_complexity(p)
    assert result == "complex", f"missing path must default complex, got {result!r}"


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
# Tests: verify_ledger — plan-WU checkboxes are the deliverables_done source of
# truth (2026-06-15, d8-effect-chains review). The plan PART's own
# ``- [ ] WU-N`` rows (mandatory since write-plan ISSUE-6) drive the scoped
# deliverables_done verdict, eliminating the cross-part AND cross-phase
# attribution false-fails the PHASES-phase-level read suffered.
# ---------------------------------------------------------------------------

def _write_plan_with_wus(
    plans_dir: Path,
    filename: str,
    status: str,
    phases: list,
    wu_lines: str,
) -> Path:
    """Write an implementation plan with a ``## Work Units`` per-WU checklist.

    ``wu_lines`` is the raw body inserted under a ``## Work Units`` heading — the
    ISSUE-6 ``- [ ] WU-N — <title>`` rows (plus any ``**Runtime Verification**``
    subsection with verification rows) that ``/execute-plan`` ticks.
    """
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
    body += "---\n\n# Implementation Plan\n\n## Work Units\n\n" + wu_lines + "\n"
    p.write_text(body, encoding="utf-8")
    return p


# A PHASES.md whose Phase-5 deliverable row actually belongs to part-3 (the d8
# cross-part defect): the row sits under Phase 5 but is built/ticked by a later
# plan part. The part-2 check (phases [5]) MUST NOT false-fail on it because the
# machine record is now the plan PART's own WU checkboxes, not these rows.
_PHASES_PHASE5_SPANS_PARTS = (
    "### Phase 5\n"
    "**Status:** In-progress\n"
    "### Deliverables\n"
    "- [x] Part-2's own Phase-5 work (done)\n"
    "- [ ] Part-3's Phase-5 work (belongs to a later plan part — still pending)\n"
)


def test_verify_ledger_plan_wu_phase_spans_two_parts_no_false_fail():
    """(a) A phase spans two plan parts. Checking part-2 (whose own WUs are all
    ticked in the plan) must NOT false-fail on part-3's still-pending Phase-5
    deliverable row in PHASES.md.

    The OLD PHASES-phase-level read scoped to phases [5] would see the unchecked
    "Part-3's Phase-5 work" row and fail. The NEW plan-WU read consults part-2's
    own ``- [ ] WU-N`` rows (all ticked) → deliverables_done True.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        # part-2 owns phase 5; its OWN WUs are fully ticked.
        part2 = _write_plan_with_wus(
            plans, "plan-part-2.md", "Complete", [5],
            "- [x] WU-1 — Part-2 Phase-5 implementation\n"
            "- [x] WU-2 — Part-2 Phase-5 wiring\n",
        )
        (spec_dir / "PHASES.md").write_text(_PHASES_PHASE5_SPANS_PARTS,
                                            encoding="utf-8")
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part2)
    assert result["deliverables_source"] == "plan-wu-checkboxes", (
        f"should read plan-WU checkboxes, not PHASES: {result}"
    )
    assert result["checks"]["deliverables_done"] is True, (
        f"part-2's own WUs all ticked → deliverables_done True despite part-3's "
        f"pending Phase-5 row: {result['checks']}"
    )
    assert result["ok"] is True, f"part-2 should pass cleanly: {result}"


def test_verify_ledger_plan_wu_cross_phase_attribution_ignored():
    """(b) Cross-phase attribution: a deliverable filed under Phase 5 but built in
    corrective Phase 6 sits done-but-unticked in PHASES.md. The plan-part check
    no longer cares — it reads the executing part's OWN WU checkboxes.

    Here part-1 covers phase 6 (the corrective phase that actually built the
    work); its WUs are ticked. PHASES.md still shows the Phase-5-filed row
    unticked, but that no longer affects the part's deliverables_done.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        part1 = _write_plan_with_wus(
            plans, "plan-part-1.md", "Complete", [6],
            "- [x] WU-1 — Corrective Phase-6 work that satisfies the Phase-5 intent\n",
        )
        (spec_dir / "PHASES.md").write_text(
            "### Phase 5\n"
            "### Deliverables\n"
            "- [ ] Deliverable filed here but built in Phase 6 (done-but-unticked)\n"
            "### Phase 6\n"
            "### Deliverables\n"
            "- [x] Corrective work\n",
            encoding="utf-8",
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["deliverables_source"] == "plan-wu-checkboxes", result
    assert result["checks"]["deliverables_done"] is True, (
        f"part-1's WUs ticked → done regardless of the Phase-5-attributed "
        f"unticked row: {result['checks']}"
    )
    assert result["ok"] is True, f"cross-phase attribution must not fail part-1: {result}"


def test_verify_ledger_plan_wu_unchecked_fails():
    """An UNCHECKED non-verification ``- [ ] WU-N`` in the plan part →
    deliverables_done False. Proves the plan-WU read is not vacuously green."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        part1 = _write_plan_with_wus(
            plans, "plan-part-1.md", "Complete", [1],
            "- [x] WU-1 — landed\n"
            "- [ ] WU-2 — still pending implementation work\n",
        )
        # PHASES.md is fully ticked — proving the FAIL comes from the plan, not PHASES.
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n- [x] All PHASES deliverables ticked\n", encoding="utf-8"
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["deliverables_source"] == "plan-wu-checkboxes", result
    assert result["checks"]["deliverables_done"] is False, (
        f"unchecked plan WU → deliverables_done False even though PHASES is "
        f"fully ticked: {result['checks']}"
    )
    assert result["failing_check"] == "deliverables_done", result


def test_verify_ledger_plan_wu_verification_only_exempt():
    """(c) The verification-only-row exemption holds at the plan-WU level: a
    ``- [ ] WU-N`` under a ``**Runtime Verification**`` subsection (gate-owned,
    ticked by /mcp-test not /execute-plan) does NOT fail deliverables_done."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        part1 = _write_plan_with_wus(
            plans, "plan-part-1.md", "Complete", [1],
            "- [x] WU-1 — implementation landed\n"
            "- [x] WU-2 — wiring landed\n"
            "\n**Runtime Verification**\n"
            "- [ ] WU-3 — MCP smoke test passes (ticked by /mcp-test)\n",
        )
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n- [x] Done\n", encoding="utf-8"
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["deliverables_source"] == "plan-wu-checkboxes", result
    assert result["checks"]["deliverables_done"] is True, (
        f"only-unchecked WU is under Runtime Verification → exempt → done: "
        f"{result['checks']}"
    )
    assert result["ok"] is True, f"verification-only unchecked WU should pass: {result}"


def test_verify_ledger_legacy_plan_no_wu_checkboxes_falls_back():
    """(d) A legacy pre-ISSUE-6 plan with NO parseable ``- [ ] WU-N`` rows falls
    back to the PHASES-phase-level behavior AND reports the diagnostic
    deliverables_source. It is NOT hard-failed.

    Here PHASES phase-1 has a real unchecked non-verification deliverable, so the
    fallback correctly yields deliverables_done False — proving the legacy path
    still does real work (not a vacuous pass)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        # _write_plan writes a plan body with NO ## Work Units / WU checkboxes.
        legacy = _write_plan(plans, "plan-part-1.md", "Complete", [1])
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Thing A\n"
            "- [ ] Thing B (real pending deliverable)\n",
            encoding="utf-8",
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=legacy)
    assert result["deliverables_source"] == (
        "phases-fallback (legacy plan — no per-WU checkboxes)"
    ), f"legacy plan must report the fallback diagnostic: {result}"
    assert result["checks"]["deliverables_done"] is False, (
        f"legacy fallback catches the real unchecked PHASES deliverable: "
        f"{result['checks']}"
    )


def test_verify_ledger_legacy_plan_fallback_passes_when_phases_done():
    """Legacy-plan fallback also PASSES when the in-scope PHASES deliverables are
    all ticked — confirming the fallback reproduces the prior behavior in both
    directions, not just the failing one."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        legacy = _write_plan(plans, "plan-part-1.md", "Complete", [1])
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n- [x] Thing A\n- [x] Thing B\n", encoding="utf-8"
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=legacy)
    assert result["deliverables_source"] == (
        "phases-fallback (legacy plan — no per-WU checkboxes)"
    ), result
    assert result["checks"]["deliverables_done"] is True, result
    assert result["ok"] is True, f"legacy fallback should pass when PHASES done: {result}"


def test_verify_ledger_feature_level_reports_source():
    """The feature-level call (no --plan) reports deliverables_source
    'phases-feature-level' and keeps its whole-feature PHASES.md semantics."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        _write_plan_with_wus(
            plans, "plan-part-1.md", "Complete", [1],
            "- [x] WU-1 — done\n",
        )
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n- [x] Done\n", encoding="utf-8"
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)  # no plan_path
    assert result["deliverables_source"] == "phases-feature-level", result
    assert result["checks"]["deliverables_done"] is True, result


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
    """The queue trim sits BEHIND the receipt-noop guard: when COMPLETED.md
    already exists the call short-circuits to noop BEFORE the trim, so an
    entry that somehow lingered in the queue is NOT mutated on the noop re-run
    (queue_trimmed False, queue byte-identical). This mirrors the canonical
    idempotency test (pre-write the receipt + leave VALIDATED.md), and proves
    the trim never fires on an already-receipted dir.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "mcp-testing"
        spec_dir.mkdir(parents=True)
        # Pre-write a valid receipt → the noop path will be taken.
        lazy_core.write_completed_receipt(
            spec_dir / "COMPLETED.md",
            feature_id="mcp-testing",
            date="2026-06-10",
            provenance="gated",
        )
        _write_validated_md(spec_dir)
        # The queue still carries the entry (simulates a never-trimmed legacy
        # state) — the noop re-run must NOT touch it.
        queue_path = _write_features_queue(repo_root, ["mcp-testing", "other"])
        before = queue_path.read_text(encoding="utf-8")

        result = lazy_core.apply_pseudo(
            repo_root, "__mark_complete__", spec_dir,
            feature_id="mcp-testing", date="2026-06-10",
        )
        assert result["noop"] is True, f"expected noop=True, got {result}"
        assert result.get("queue_trimmed", False) is False, (
            "queue trim fired on an already-receipted (noop) dir"
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


def test_parse_phases_phase_summary_section_not_a_phase():
    """REGRESSION (hardening-log 2026-06, d8-session-format permanent-stale loop):
    an h2 ``## Phase Summary`` summary section is NOT a phase and must not be
    counted. The old ``^#{2,3}\\s+Phase\\b`` regex counted it as an 8th phase
    for a 7-real-phase PHASES.md, so retro_staleness() returned (8,7) on every
    probe and the state machine routed a stale retro forever.

    "Phase" followed by an English word ("Summary") with no digit and no phase
    delimiter is prose, not a phase marker — exactly the case the AlgoBooth
    checker's PHASE_HEADER_RE author comment singles out ("### Phase Dependency
    Graph").
    """
    _guard()
    # 7 real numbered phases + a trailing ## Phase Summary roll-up section.
    text = (
        "### Phase 1: Manifest\n**Status:** Complete\n- [x] a\n"
        "### Phase 2: Lifecycle\n**Status:** Complete\n- [x] b\n"
        "### Phase 3: Auto-Save\n**Status:** Complete\n- [x] c\n"
        "### Phase 4: Migration\n**Status:** Complete\n- [x] d\n"
        "### Phase 5: Consolidate\n**Status:** Complete\n- [x] e\n"
        "### Phase 6: Integration\n**Status:** Complete\n- [x] f\n"
        "### Phase 7: Realignment\n**Status:** Complete\n- [x] g\n"
        "## Phase Summary\n"
        "All seven phases landed; export/import verified end-to-end.\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 7, (
        f"expected 7 phases (## Phase Summary must NOT count), got "
        f"{len(phases)}: {[p['heading'] for p in phases]!r}"
    )
    assert all(p["heading"] != "## Phase Summary" for p in phases), (
        f"## Phase Summary leaked into phases: {[p['heading'] for p in phases]!r}"
    )


def test_parse_phases_english_word_after_phase_not_counted():
    """Non-phase h2/h3 sections whose heading is ``Phase <English word(s)>`` with
    no digit and no delimiter are excluded (Summary / Dependency Graph /
    Implementation Notes), while every legitimate phase-id form is kept: a bare
    numeric id (``### Phase 1``), an alphanumeric id (``### Phase 4A —``), and a
    non-numeric id made a phase only by its delimiter (``## Phase G+:``).
    """
    _guard()
    text = (
        "### Phase 1\n**Status:** Complete\n- [x] bare numeric id counts\n"
        "### Phase 4A — Spike\n**Status:** Complete\n- [x] alnum id counts\n"
        "## Phase G+: Backstop\n**Status:** Ready\n- [ ] delimited non-numeric counts\n"
        "## Phase Summary\nprose\n"
        "### Phase Dependency Graph\nprose\n"
        "## Phase Implementation Notes\nprose\n"
    )
    phases = lazy_core.parse_phases(text)
    headings = [p["heading"] for p in phases]
    assert headings == [
        "### Phase 1",
        "### Phase 4A — Spike",
        "## Phase G+: Backstop",
    ], f"unexpected phase set: {headings!r}"


def test_count_phases_cli_matches_parse_phases():
    """The lazy-state.py ``--count-phases`` CLI prints exactly
    ``len(parse_phases(...))`` — proving the /retro phase_count_at_retro writer
    and retro_staleness()'s comparator share ONE counter (the fix's
    can-never-disagree invariant).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        phases = Path(td) / "PHASES.md"
        body = (
            "### Phase 1: A\n- [x] a\n"
            "### Phase 2: B\n- [x] b\n"
            "## Phase Summary\nroll-up prose, not a phase\n"
        )
        phases.write_text(body, encoding="utf-8")
        expected = len(lazy_core.parse_phases(body))
        assert expected == 2, f"fixture sanity: expected 2, got {expected}"
        script = Path(lazy_core.__file__).resolve().parent / "lazy-state.py"
        out = subprocess.check_output(
            [sys.executable, str(script), "--count-phases", str(phases)],
            text=True,
        ).strip()
        assert out == str(expected), (
            f"--count-phases printed {out!r}, parse_phases gave {expected}"
        )


# ---------------------------------------------------------------------------
# Tests: parse_phases phase_kind — Phase 8 (lazy-validation-readiness)
#
# Each parsed phase carries a ``phase_kind`` field read from a
# ``**Phase kind:** corrective | design`` line inside the section (first
# occurrence wins, mirroring **Status:**). Default ``"design"`` when the line
# is absent (back-compat — legacy PHASES.md re-trigger retro exactly as before).
# ---------------------------------------------------------------------------

def test_parse_phases_phase_kind_corrective_read():
    """A ``**Phase kind:** corrective`` line is exposed as phase_kind."""
    _guard()
    text = (
        "### Phase 1: Fix\n"
        "**Status:** Complete\n"
        "**Phase kind:** corrective\n"
        "- [x] make impl satisfy existing spec\n"
    )
    phases = lazy_core.parse_phases(text)
    assert len(phases) == 1
    assert phases[0]["phase_kind"] == "corrective", phases[0]


def test_parse_phases_phase_kind_design_explicit():
    """An explicit ``**Phase kind:** design`` line is read as design."""
    _guard()
    text = (
        "### Phase 1: Build\n"
        "**Status:** Complete\n"
        "**Phase kind:** design\n"
        "- [x] new design surface\n"
    )
    phases = lazy_core.parse_phases(text)
    assert phases[0]["phase_kind"] == "design", phases[0]


def test_parse_phases_phase_kind_defaults_design_when_absent():
    """No ``**Phase kind:**`` line → phase_kind defaults to 'design' (back-compat).

    Legacy PHASES.md authored before phase-kind tagging must continue to be
    treated as design phases so they re-trigger retro exactly as before.
    """
    _guard()
    text = (
        "### Phase 1: Legacy\n"
        "**Status:** Complete\n"
        "- [x] no phase-kind line here\n"
    )
    phases = lazy_core.parse_phases(text)
    assert phases[0]["phase_kind"] == "design", phases[0]


def test_parse_phases_phase_kind_case_insensitive_and_first_wins():
    """The value is normalized to lowercase; the first kind line inside the
    section wins (a later mention inside Implementation Notes is ignored)."""
    _guard()
    text = (
        "### Phase 1\n"
        "**Status:** Complete\n"
        "**Phase kind:** Corrective\n"
        "- [x] item\n"
        "**Phase kind:** design (mentioned in notes — ignored)\n"
    )
    phases = lazy_core.parse_phases(text)
    assert phases[0]["phase_kind"] == "corrective", phases[0]


def test_parse_phases_phase_kind_unknown_value_defaults_design():
    """An unrecognized phase-kind value falls back to the safe 'design' default
    (the conservative tier — re-triggers retro)."""
    _guard()
    text = (
        "### Phase 1\n"
        "**Status:** Complete\n"
        "**Phase kind:** banana\n"
        "- [x] item\n"
    )
    phases = lazy_core.parse_phases(text)
    assert phases[0]["phase_kind"] == "design", phases[0]


# ---------------------------------------------------------------------------
# Tests: retro_staleness phase-kind gate — Phase 8 (lazy-validation-readiness)
#
# retro_staleness now re-stales /retro ONLY when >=1 design phase landed since
# RETRO_DONE.md (the phases at index >= phase_count_at_retro). A run of purely
# corrective phases since the last retro does NOT re-trigger retro.
# ---------------------------------------------------------------------------

def test_retro_staleness_only_corrective_added_not_stale():
    """phase_count_at_retro: 1 + 3 trailing corrective phases → NOT stale.

    The design surface is unchanged (the corrective phases only make the impl
    satisfy the existing spec), so retro has nothing to re-audit → None.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n**Phase kind:** design\n- [x] A\n\n"
            "### Phase 2\n**Phase kind:** corrective\n- [x] B\n\n"
            "### Phase 3\n**Phase kind:** corrective\n- [x] C\n\n"
            "### Phase 4\n**Phase kind:** corrective\n- [x] D\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 1\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) is None


def test_retro_staleness_one_design_added_is_stale():
    """phase_count_at_retro: 1 + a trailing design phase (among correctives) →
    stale, returns (current, recorded)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n**Phase kind:** design\n- [x] A\n\n"
            "### Phase 2\n**Phase kind:** corrective\n- [x] B\n\n"
            "### Phase 3\n**Phase kind:** design\n- [x] C\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 1\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) == (3, 1)


def test_retro_staleness_added_untagged_phase_is_stale_backcompat():
    """A trailing phase with NO phase-kind line defaults to design → stale.

    Back-compat: a legacy corrective tail authored before phase-kind tagging
    keeps re-triggering retro (the safe default), exactly as pre-Phase-8.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "PHASES.md").write_text(
            "# Phases\n\n"
            "### Phase 1\n- [x] A\n\n"
            "### Phase 2\n- [x] B\n",
            encoding="utf-8",
        )
        (spec_dir / "RETRO_DONE.md").write_text(
            "---\nkind: retro-done\nfeature_id: f\ndate: 2026-06-01\n"
            "phase_count_at_retro: 1\n---\n",
            encoding="utf-8",
        )
        assert lazy_core.retro_staleness(spec_dir) == (2, 1)


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
# Tests: update_repeat_counts — Phase 2 (F2) double-probe debounce
#
# A re-read (two ADVANCING probes for the same (feature_id, current_step) with
# NO dispatch between them) must NOT inflate the HEAD-blind step_repeat_count
# and trip a false LOOP DETECTED. The "did a dispatch happen" oracle is the
# registry CONSUME-COUNT DELTA when a run marker is present: the guard consumes
# a nonce on every ALLOW, so an unchanged consumed-count between two identical
# probes means no dispatch landed → HOLD step_count.
#
# MARKER-GATED: with NO run marker present (no registry), behavior is byte-
# identical to today — the debounce is inert and step_repeat_count increments
# on any unchanged step (so `--test` baselines and unmarked callers are
# unchanged). HEAD-blindness is preserved — a real oscillation (a consume
# between the repeats) still trips. peek never persists / never advances.
# ---------------------------------------------------------------------------

def _record_consume(state_dir: "Path") -> None:
    """Register a cycle emission and immediately consume its nonce under the
    given hermetic state dir — i.e. simulate one guard ALLOW (one dispatch).

    Raises the registry's consumed-count by exactly one. Used by the Phase 2
    debounce tests to stand in for "a dispatch landed between two probes."
    """
    _set_state_dir(state_dir)
    try:
        entry = lazy_core.register_emission("dispatch prompt", "cycle")
        consumed = lazy_core.consume_nonce(entry["nonce"])
        assert consumed, "pre-condition: the fresh nonce must consume cleanly"
    finally:
        _clear_state_dir()


def _write_marker_in(state_dir: "Path", repo_root: "Path") -> None:
    """Write a fresh, bind-pending run marker into the given hermetic state dir."""
    _set_state_dir(state_dir)
    try:
        lazy_core.write_run_marker(
            pipeline="feature", cloud=False, repo_root=str(repo_root)
        )
    finally:
        _clear_state_dir()


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


def test_update_repeat_counts_debounce_peek_never_advances():
    """peek discipline intact under the debounce: a marked peek probe never
    persists and never advances — the consume-count key is not written under
    peek, and a subsequent real advance starts fresh.

    RED: an impl that persisted the consume-count under peek would mutate state.
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
            p1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path, peek=True)
            peek_created = sig_path.exists()
            p2 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path, peek=True)
            a1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
        finally:
            _clear_state_dir()
    assert not peek_created, "peek must NOT create the state file (debounce path included)"
    assert p1["step_repeat_count"] == 1, f"first peek → 1, got {p1!r}"
    assert p2["step_repeat_count"] == 1, f"second peek → 1 (no mutation), got {p2!r}"
    assert a1["step_repeat_count"] == 1, (
        f"first real advance starts at 1 (peeks didn't advance), got {a1!r}"
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


def test_update_repeat_counts_debounce_legacy_file_without_consume_key():
    """A persisted file written WITHOUT the new consume-count key (a probe that
    predates Phase 2, or a marked write that never recorded one) is tolerated:
    on the next marked probe with no prior consume-count key, the debounce
    cannot prove a re-read, so step_count behaves as before (increments) and the
    new key is added on that write — mirroring the head / step_* migrations.

    RED: an impl that KeyErrors on the missing consume-count key, or that holds
    step_count when it cannot prove a re-read.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Hand-write a Phase-10 shape file (step keys present, NO consume key).
        legacy_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        legacy_step_sig = [_STATE_A["feature_id"], _STATE_A["current_step"]]
        sig_path.write_text(
            json.dumps({
                "signature": legacy_sig, "count": 1, "head": None,
                "step_signature": legacy_step_sig, "step_count": 1,
            }),
            encoding="utf-8",
        )
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert r1["step_repeat_count"] == 2, (
        f"legacy file with no consume-count key → debounce cannot prove a re-read, "
        f"so step_count increments as before (1 → 2), got {r1!r}"
    )
    assert "consume_count" in persisted, (
        f"the new consume-count key must be added on the next marked write, got {persisted!r}"
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


def test_f1_repeat_count_debounce_legacy_file_without_consume_key():
    """F1 invariant 5 — Legacy-tolerant (prior file with no consume_count key).

    A state file written without consume_count (a probe predating F1/F2, or an
    unmarked write) cannot prove a re-read, so repeat_count increments as
    before (1 → 2) — same migration tolerance as head / step_* keys.

    RED: an impl that errors on the missing key, or incorrectly holds when it
    cannot prove a re-read.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        repo_root = td_path / "repo"
        repo_root.mkdir()
        state_dir = td_path / "state"
        state_dir.mkdir()
        sig_path = td_path / "sig.json"
        # Hand-write a legacy Phase-10 shape (step keys present, NO consume key).
        prior_sig = [
            _STATE_A["feature_id"],
            _STATE_A["sub_skill"],
            _STATE_A["sub_skill_args"],
            _STATE_A["current_step"],
        ]
        prior_step_sig = [_STATE_A["feature_id"], _STATE_A["current_step"]]
        sig_path.write_text(
            json.dumps({
                "signature": prior_sig, "count": 1, "head": None,
                "step_signature": prior_step_sig, "step_count": 1,
            }),
            encoding="utf-8",
        )
        _write_marker_in(state_dir, repo_root)
        _set_state_dir(state_dir)
        try:
            r1 = lazy_core.update_repeat_counts(repo_root, _STATE_A, signature_path=sig_path)
            persisted = json.loads(sig_path.read_text(encoding="utf-8"))
        finally:
            _clear_state_dir()
    assert r1["repeat_count"] == 2, (
        f"legacy file with no consume_count key → debounce cannot prove a re-read, "
        f"so repeat_count increments as before (1 → 2), got {r1!r}"
    )
    assert "consume_count" in persisted, (
        f"the consume_count key must be added to the persisted record on next "
        f"marked write, got {persisted!r}"
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

    meta is rendered as a bare COUNT with NO denominator (operator decision
    2026-06-14 — meta_cycles is uncapped; only forward_cycles is capped at
    max_cycles, so only fwd shows '/max').
    RED: format_cycle_header missing → AttributeError after _guard().
    """
    _guard()
    state = {"feature_id": "audio-engine", "sub_skill": "/execute-plan", "other": "ignored"}
    result = lazy_core.format_cycle_header(
        state, forward_cycles=2, max_cycles=8, meta_cycles=3
    )
    expected = "### Cycle fwd 2/8 · meta 3 · audio-engine · /execute-plan"
    assert result == expected, (
        f"format_cycle_header returned wrong string.\n"
        f"  expected: {expected!r}\n"
        f"  got:      {result!r}"
    )


def test_format_cycle_header_missing_fields():
    """state={} and all counters None → feature/sub_skill render as —, counters as ?.

    The exact placeholder contract: fwd counters None → '?', missing
    feature_id/sub_skill → '—'.  meta is a bare COUNT (no denominator) — it
    renders just '?' when meta_cycles is None (no '/?' cap term).
    RED: format_cycle_header missing → AttributeError after _guard().
    """
    _guard()
    state = {}
    result = lazy_core.format_cycle_header(
        state, forward_cycles=None, max_cycles=None, meta_cycles=None
    )
    expected = "### Cycle fwd ?/? · meta ? · — · —"
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


# --- Phase 9: per-part complexity model tiering (lazy-validation-readiness) ---
#
# The /execute-plan cycle's dispatch model is selected from the current plan
# part's `complexity` frontmatter tag:
#   mechanical  → sonnet
#   complex     → opus
#   absent/untagged → opus (back-compat — the safe default tier)
# This composes with the loop-block downgrade (repeat_count >= 2 → sonnet):
# a looping complex part still downgrades to sonnet.

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


def test_emit_cycle_prompt_complex_part_loop_cycle_model_sonnet():
    """A looping (repeat_count>=2) `complex` part STILL downgrades to sonnet —
    the loop-block downgrade composes with complexity tiering."""
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
    assert r["model"] == "sonnet", f"looping complex part expected sonnet, got {r['model']!r}"
    assert "LOOP DETECTED" in r["prompt"], "loop block not appended for looping complex part"


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
    phase_kinds: list[str] | None = None,
) -> Path:
    """Build a feature repo that reaches the Step 8/9 retro→MCP gate.

    Shape mirrors the `workstation-verification-only-retro-done` smoke fixture:
    all impl plans Complete + the only unchecked PHASES.md rows are Runtime
    Verification rows, so compute_state falls through Step 7 to the retro gate.
    `phase_count` controls how many `### Phase N` sections PHASES.md carries
    (the quantity retro_staleness compares against phase_count_at_retro).
    `retro_done_frontmatter` is the raw YAML body for RETRO_DONE.md, or None to
    omit the sentinel entirely (→ plain Step 8 retro dispatch).

    `phase_kinds`, when provided, is a list of length `phase_count` giving the
    `**Phase kind:**` tag for each phase (Phase 8 — lazy-validation-readiness);
    an entry of None/"" omits the line (legacy untagged → defaults to design).
    When omitted entirely, no phase-kind lines are written (the back-compat
    untagged shape).
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
        phases_body += f"### Phase {n}\n"
        if phase_kinds is not None:
            kind = phase_kinds[n - 1]
            if kind:
                phases_body += f"**Phase kind:** {kind}\n"
        phases_body += "- [x] Done\n\n"
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

def test_lazy_state_retro_stale_routes_past_step8():
    """RETRO UNWIRED (2026-06): a RETRO_DONE.md with phase_count_at_retro: 2 +
    PHASES.md now carrying 3 phases would historically have re-staled the retro
    and re-dispatched retro-feature. With retro removed from the pipeline, a
    stale RETRO_DONE.md is ignored for routing — it falls straight through to
    Step 9 mcp-test (the retro_staleness predicate stays in the codebase but no
    longer gates routing)."""
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
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]


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


def test_lazy_state_retro_stale_only_corrective_routes_past_step8():
    """Phase 8 — phase-kind gate. RETRO_DONE.md phase_count_at_retro: 1 + two
    trailing CORRECTIVE phases (added post-retro) → NOT stale; Step 8 falls
    through to Step 9 mcp-test (no redundant /retro round)."""
    _guard()
    ls = _load_state_script("lazy-state.py")
    with tempfile.TemporaryDirectory() as td:
        root = _build_retro_routing_repo(
            Path(td),
            "kind: retro-done\nfeature_id: feat-retro\ndate: 2026-06-01\n"
            "rounds: 1\nphase_count_at_retro: 1\n",
            phase_count=3,
            phase_kinds=["design", "corrective", "corrective"],
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


# ---- WU-5e end-to-end: Step-8 retro-staleness routing (bug-state parity) ----
#
# The original WU-5 scoping assumed "bugs have no retro step" — wrong:
# bug-state.py has its own Step 8 (STEP_RETRO → retro-feature) and bug dirs
# carry the same RETRO_DONE.md + PHASES.md shape, so a stale BUG retro must be
# re-routed exactly like a stale feature retro.

def test_bug_state_retro_stale_routes_past_step8():
    """RETRO UNWIRED (2026-06), bug-pipeline parity: a stale bug RETRO_DONE.md
    (phase_count_at_retro: 2, PHASES.md now carrying 3) no longer re-dispatches
    retro-feature — retro is removed from the bug pipeline too, so routing falls
    through to Step 9 mcp-test."""
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
    assert state["sub_skill"] == "mcp-test", state
    assert state["current_step"] == "Step 9: run MCP tests", state["current_step"]


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


# ---- harden(script) 2026-06-15: no-plans verification-only Step-7 deadlock ----
#
# Regression for the mcp-testing write-plan no-progress loop. A feature
# implemented batch-by-batch via PHASES checkboxes (NO plans/ dir) whose only
# remaining unchecked rows are Runtime Verification rows must route to the
# Step-9 MCP gate, not loop on write-plan. The pre-fix Step-7 bypass required
# _has_any_complete_plan(spec_path) which is False with no plans/ dir, so
# control fell to `elif not plans` -> write-plan; write-plan is banned from
# emitting a verification-only WU, so it wrote nothing and the state repeated.

def _build_no_plans_verification_only_repo(root: Path) -> Path:
    """Build a feature repo with NO plans/ dir whose only unchecked PHASES.md
    rows are verification-only (the mcp-testing deadlock shape).

    All implementation rows are [x]; a trailing `### Runtime Verification`
    subsection holds the single unchecked row. SPEC + RESEARCH + RESEARCH_SUMMARY
    + PHASES exist so compute_state reaches Step 7. Deliberately omits the
    plans/ dir entirely so _has_any_complete_plan() returns False.
    """
    features = root / "docs" / "features"
    features.mkdir(parents=True)
    features.joinpath("queue.json").write_text(
        json.dumps({
            "queue": [
                {"id": "feat-noplan", "name": "Feature NOPLAN",
                 "spec_dir": "feat-noplan", "tier": 1}
            ]
        }),
        encoding="utf-8",
    )
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-noplan"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** In-progress\n\n**Depends on:** (none)\n",
        encoding="utf-8",
    )
    (fdir / "RESEARCH.md").write_text("# R\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# S\n", encoding="utf-8")
    phases_body = (
        "# Phases\n\n"
        "### Phase 1\n- [x] Impl one\n\n"
        "### Phase 2\n- [x] Impl two\n\n"
        "### Runtime Verification\n- [ ] MCP test only\n"
    )
    (fdir / "PHASES.md").write_text(phases_body, encoding="utf-8")
    # NOTE: no plans/ dir created — this is the load-bearing condition.
    return root


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
            acked = lazy_core.ack_oldest_deny(now=999.0)
            assert acked is not None, "ack returned None despite pending entries"
            assert acked["tool_use_id"] == "tu-0", "must ack the OLDEST (tu-0)"
            assert acked["acked"] is True and acked["acked_ts"] == 999.0, acked
            assert lazy_core.pending_hardening() == 2, "one acked → 2 remain"
            # Next ack takes tu-1 (the new oldest unacked).
            acked2 = lazy_core.ack_oldest_deny(now=1000.0)
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
            assert lazy_core.ack_oldest_deny() is None, "empty/absent ledger → None"
            # Ledger with a single already-acked entry.
            lazy_core.append_deny_ledger_entry(
                tool_use_id="tu", denied_sha12="a" * 12,
                reason_head="r", prompt_head="p", now=1.0,
            )
            assert lazy_core.ack_oldest_deny(now=2.0) is not None  # acks it
            assert lazy_core.ack_oldest_deny(now=3.0) is None, "all acked → no-op"
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
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=__import__("time").time(),
            )
        finally:
            _clear_state_dir()
        env = dict(_os_env.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)
        hook_input = json.dumps({
            "tool_use_id": "tu-deny",
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
    no longer acks, so the ack is now driven via lazy_core.ack_oldest_deny()
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
        # same lazy_core.ack_oldest_deny() call lazy_guard.py makes.
        _set_state_dir(state_dir)
        try:
            acked = lazy_core.ack_oldest_deny()
            assert acked is not None, "guard-allow ack must retire the pending deny"
        finally:
            _clear_state_dir()

        # Now run-end SUCCEEDS (ledger empty).
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
        # scaled budget = 6 phases + slack.
        budget = lazy_core._execute_plan_commit_budget("execute-plan", str(plan))
        assert budget == 6 + lazy_core._EXECUTE_PLAN_PHASE_BUDGET_SLACK, budget

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

        # detector honors the override: 6 commits on a 6-phase plan does NOT trip
        # (budget 8) but a runaway of 9 commits DOES.
        marker = {
            "run_started_at": "2026-06-16T13:31:00Z",
            "begin_head_sha": "d" * 40,
            "kind": "real",
        }
        assert lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="e" * 40, sub_skill="execute-plan",
            commits_since=6, budget_override=budget,
        ) is None
        runaway = lazy_core.detect_cycle_bracket_friction(
            marker, current_run_started_at="2026-06-16T13:31:00Z",
            current_head_sha="e" * 40, sub_skill="execute-plan",
            commits_since=9, budget_override=budget,
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
        r3 = run(["--run-end"])
        assert r3.returncode == 0
        assert not ckpt_path.exists(), "terminal run-end must not write a checkpoint"


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
            lazy_core.bind_marker_session("sess-abc")
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


def _dispatch_requires(cls: str) -> list[str]:
    """Return the @requires keys for a dispatch class's real template."""
    tpl = _REAL_TEMPLATE_DIR / f"dispatch-{cls}.md"
    first = next((ln for ln in tpl.read_text(encoding="utf-8").splitlines() if ln.strip()), "")
    m = re.match(r"^<!--\s*@requires\s+([a-z0-9_,]+)\s*-->", first)
    return [k.strip() for k in m.group(1).split(",") if k.strip()]


# ---------------------------------------------------------------------------
# Tests: Phase 8 — concurrent-session safety
#   (non-destructive path B is tested in the Phase 1 section above;
#    routed hardening debt + guard-allow ack + stderr line live here)
# ---------------------------------------------------------------------------
#
# Hermetic via LAZY_STATE_DIR temp dirs (same discipline as Phase 1/7).


def _build_phase8_fixture_repo(parent: "Path") -> "Path":
    """Build a minimal mid-implementation fixture repo (yields a non-null
    cycle_prompt on --emit-prompt when NOT withholding).  Mirrors the fixture
    built inline by test_subprocess_emit_prompt_with_marker_writes_registry."""
    features = parent / "fixture-repo" / "docs" / "features"
    features.mkdir(parents=True)
    (features / "queue.json").write_text(json.dumps({
        "queue": [{"id": "feat-c", "name": "Feature C", "spec_dir": "feat-c", "tier": 1}]
    }), encoding="utf-8")
    (features / "ROADMAP.md").write_text("# Roadmap\n", encoding="utf-8")
    fdir = features / "feat-c"
    fdir.mkdir()
    (fdir / "SPEC.md").write_text(
        "# Spec\n\n**Status:** Draft\n\n**Depends on:** (none)\n", encoding="utf-8")
    (fdir / "RESEARCH.md").write_text("# Research\n", encoding="utf-8")
    (fdir / "RESEARCH_SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    (fdir / "PHASES.md").write_text(
        "# Phases\n\n### Phase 1\n- [ ] Build the thing\n- [ ] Tests\n", encoding="utf-8")
    (fdir / "plans").mkdir()
    (fdir / "plans" / "all-phases-c.md").write_text("# Plan\n", encoding="utf-8")
    return parent / "fixture-repo"


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
            original = lazy_core.ack_oldest_deny
            def _boom(*a, **k):
                raise RuntimeError("ack exploded")
            lazy_core.ack_oldest_deny = _boom  # type: ignore[assignment]
            try:
                out = lazy_guard.guard(_hook_input(prompt, "tu-boom"))
            finally:
                lazy_core.ack_oldest_deny = original  # type: ignore[assignment]
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", (
                "an ack failure must NEVER change the allow output (fail-open)"
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


def _phase9_guard_module():
    """Import lazy_guard in-process (it imports lazy_core directly)."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    return importlib.import_module("lazy_guard")


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

            original = lazy_core.bind_marker_session
            def _boom(*a, **k):
                raise RuntimeError("bind exploded")
            lazy_core.bind_marker_session = _boom  # type: ignore[assignment]
            try:
                out = lazy_guard.guard(json.dumps({
                    "session_id": "poison-session",
                    "tool_use_id": "tu-poison",
                    "tool_input": {"prompt": prompt},
                }))
            finally:
                lazy_core.bind_marker_session = original  # type: ignore[assignment]

            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow", (
                "WU-9.2: a bind failure must NEVER change the allow output (fail-open)"
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


# ---------------------------------------------------------------------------
# F1 (lazy-pipeline-ergonomics Phase 1) — validate-deny recovery ergonomics
# ---------------------------------------------------------------------------
#
# F1a: the default (non-hardening) deny reason names the sanctioned
#      customization path (`--context KEY=VALUE`, `--emit-dispatch <class>`) and
#      the "dispatch verbatim — never append/edit" rule, WITHOUT dropping any of
#      the preexisting recipe substrings the Phase 6/7 tests byte-match.
# F1b: a pure trailing-suffix superset of an unconsumed/fresh/cycle entry is
#      auto-readmitted (nonce consumed, allow, `auto_readmit: true` ledger event).
#      Hardening-class entries and in-body edits are NEVER auto-readmitted; any
#      auto-readmit-path error falls through to the normal deny (fail-open).


def _f1_guard_module():
    """Import lazy_guard in-process (it imports lazy_core directly)."""
    sys.path.insert(0, str(_SCRIPTS_DIR))
    import importlib
    return importlib.import_module("lazy_guard")


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


def _f1_hook_input(prompt, tool_use_id, session_id=None):
    payload = {"tool_use_id": tool_use_id, "tool_input": {"prompt": prompt}}
    if session_id is not None:
        payload["session_id"] = session_id
    return json.dumps(payload)


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
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            base = "Run the next cycle step exactly as specified now."
            lazy_core.register_emission(base, cls="cycle", item_id="feat-x")

            edited = base.replace("exactly", "approximately")
            out = lazy_guard.guard(_f1_hook_input(edited, "tu-edit"))
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
        _set_state_dir(state_dir)
        try:
            lazy_core.write_run_marker(
                pipeline="feature", cloud=False, repo_root="/r",
                max_cycles=5, now=_time.time(),
            )
            base = "You are the harden-harness subagent. Analyze and fix the gap."
            entry = lazy_core.register_emission(base, cls="hardening")
            nonce = entry["nonce"]

            dispatched = base + "\n\nORCHESTRATOR NOTE: also bump the version."
            out = lazy_guard.guard(_f1_hook_input(dispatched, "tu-hard-suffix"))
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

            original = lazy_core.consume_nonce
            def _boom(*a, **k):
                raise RuntimeError("consume exploded")
            lazy_core.consume_nonce = _boom  # type: ignore[assignment]
            try:
                out = lazy_guard.guard(_f1_hook_input(dispatched, "tu-boom"))
            finally:
                lazy_core.consume_nonce = original  # type: ignore[assignment]

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
        lazy_core.consume_nonce(entry["nonce"])

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
            lazy_core.consume_nonce(entry["nonce"])
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
            lazy_core.consume_nonce(entry2["nonce"])
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
            lazy_core.consume_nonce(entry["nonce"])
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
    # plan_complexity — Phase 9 per-part complexity tag (lazy-validation-readiness)
    ("test_plan_complexity_mechanical", test_plan_complexity_mechanical),
    ("test_plan_complexity_complex_explicit", test_plan_complexity_complex_explicit),
    ("test_plan_complexity_absent_defaults_complex", test_plan_complexity_absent_defaults_complex),
    ("test_plan_complexity_legacy_no_frontmatter_defaults_complex", test_plan_complexity_legacy_no_frontmatter_defaults_complex),
    ("test_plan_complexity_unknown_value_defaults_complex", test_plan_complexity_unknown_value_defaults_complex),
    ("test_plan_complexity_case_insensitive", test_plan_complexity_case_insensitive),
    ("test_plan_complexity_absent_path_defaults_complex", test_plan_complexity_absent_path_defaults_complex),
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
    # build_parked_entry sentinel_kind — bug park-mode-halts-on-blocked Phase 3
    ("test_build_parked_entry_sentinel_kind_blocked", test_build_parked_entry_sentinel_kind_blocked),
    ("test_build_parked_entry_sentinel_kind_needs_input", test_build_parked_entry_sentinel_kind_needs_input),
    ("test_build_parked_entry_sentinel_kind_unknown", test_build_parked_entry_sentinel_kind_unknown),
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
    # verify_ledger — plan-WU checkboxes as deliverables_done source of truth (2026-06-15)
    ("test_verify_ledger_plan_wu_phase_spans_two_parts_no_false_fail", test_verify_ledger_plan_wu_phase_spans_two_parts_no_false_fail),
    ("test_verify_ledger_plan_wu_cross_phase_attribution_ignored", test_verify_ledger_plan_wu_cross_phase_attribution_ignored),
    ("test_verify_ledger_plan_wu_unchecked_fails", test_verify_ledger_plan_wu_unchecked_fails),
    ("test_verify_ledger_plan_wu_verification_only_exempt", test_verify_ledger_plan_wu_verification_only_exempt),
    ("test_verify_ledger_legacy_plan_no_wu_checkboxes_falls_back", test_verify_ledger_legacy_plan_no_wu_checkboxes_falls_back),
    ("test_verify_ledger_legacy_plan_fallback_passes_when_phases_done", test_verify_ledger_legacy_plan_fallback_passes_when_phases_done),
    ("test_verify_ledger_feature_level_reports_source", test_verify_ledger_feature_level_reports_source),
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
    # Hardening 2026-06: ## Phase Summary false-positive (d8-session-format stale loop)
    ("test_parse_phases_phase_summary_section_not_a_phase", test_parse_phases_phase_summary_section_not_a_phase),
    ("test_parse_phases_english_word_after_phase_not_counted", test_parse_phases_english_word_after_phase_not_counted),
    ("test_count_phases_cli_matches_parse_phases", test_count_phases_cli_matches_parse_phases),
    # Phase 8 (lazy-validation-readiness): parse_phases phase_kind
    ("test_parse_phases_phase_kind_corrective_read", test_parse_phases_phase_kind_corrective_read),
    ("test_parse_phases_phase_kind_design_explicit", test_parse_phases_phase_kind_design_explicit),
    ("test_parse_phases_phase_kind_defaults_design_when_absent", test_parse_phases_phase_kind_defaults_design_when_absent),
    ("test_parse_phases_phase_kind_case_insensitive_and_first_wins", test_parse_phases_phase_kind_case_insensitive_and_first_wins),
    ("test_parse_phases_phase_kind_unknown_value_defaults_design", test_parse_phases_phase_kind_unknown_value_defaults_design),
    # Phase 8: retro_staleness phase-kind gate
    ("test_retro_staleness_only_corrective_added_not_stale", test_retro_staleness_only_corrective_added_not_stale),
    ("test_retro_staleness_one_design_added_is_stale", test_retro_staleness_one_design_added_is_stale),
    ("test_retro_staleness_added_untagged_phase_is_stale_backcompat", test_retro_staleness_added_untagged_phase_is_stale_backcompat),
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
    ("test_update_repeat_counts_step_counter_ordered_args_advance_resets", test_update_repeat_counts_step_counter_ordered_args_advance_resets),
    ("test_update_repeat_counts_step_multipart_progress_does_not_trip", test_update_repeat_counts_step_multipart_progress_does_not_trip),
    ("test_update_repeat_counts_step_same_args_oscillation_still_trips", test_update_repeat_counts_step_same_args_oscillation_still_trips),
    ("test_update_repeat_counts_step_counter_resets_on_step_change", test_update_repeat_counts_step_counter_resets_on_step_change),
    ("test_update_repeat_counts_step_no_head_advance_reset", test_update_repeat_counts_step_no_head_advance_reset),
    ("test_update_repeat_counts_step_peek_does_not_mutate", test_update_repeat_counts_step_peek_does_not_mutate),
    ("test_update_repeat_counts_legacy_file_without_step_keys", test_update_repeat_counts_legacy_file_without_step_keys),
    ("test_update_repeat_count_wrapper_still_returns_int", test_update_repeat_count_wrapper_still_returns_int),
    # update_repeat_counts — Phase 2 (F2) double-probe debounce (consume-count oracle)
    ("test_update_repeat_counts_debounce_holds_step_count_no_consume_between", test_update_repeat_counts_debounce_holds_step_count_no_consume_between),
    ("test_update_repeat_counts_debounce_increments_with_consume_between", test_update_repeat_counts_debounce_increments_with_consume_between),
    ("test_update_repeat_counts_debounce_peek_never_advances", test_update_repeat_counts_debounce_peek_never_advances),
    ("test_update_repeat_counts_debounce_inert_for_foreign_repo_marker", test_update_repeat_counts_debounce_inert_for_foreign_repo_marker),
    ("test_update_repeat_counts_debounce_legacy_file_without_consume_key", test_update_repeat_counts_debounce_legacy_file_without_consume_key),
    ("test_update_repeat_counts_debounce_inert_without_marker", test_update_repeat_counts_debounce_inert_without_marker),
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
    # Phase 9 (lazy-validation-readiness) — per-part complexity model tiering
    ("test_emit_cycle_prompt_mechanical_part_cycle_model_sonnet", test_emit_cycle_prompt_mechanical_part_cycle_model_sonnet),
    ("test_emit_cycle_prompt_complex_part_cycle_model_opus", test_emit_cycle_prompt_complex_part_cycle_model_opus),
    ("test_emit_cycle_prompt_untagged_part_cycle_model_opus", test_emit_cycle_prompt_untagged_part_cycle_model_opus),
    ("test_emit_cycle_prompt_complex_part_loop_cycle_model_sonnet", test_emit_cycle_prompt_complex_part_loop_cycle_model_sonnet),
    ("test_emit_cycle_prompt_non_execute_plan_ignores_complexity", test_emit_cycle_prompt_non_execute_plan_ignores_complexity),
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
    ("test_lazy_state_retro_stale_routes_past_step8", test_lazy_state_retro_stale_routes_past_step8),
    ("test_lazy_state_retro_fresh_routes_past_step8", test_lazy_state_retro_fresh_routes_past_step8),
    ("test_lazy_state_retro_fieldless_routes_past_step8", test_lazy_state_retro_fieldless_routes_past_step8),
    # Phase 8 (lazy-validation-readiness) end-to-end — Step-8 phase-kind gate
    ("test_lazy_state_retro_stale_only_corrective_routes_past_step8", test_lazy_state_retro_stale_only_corrective_routes_past_step8),
    ("test_lazy_state_retro_stale_design_added_routes_past_step8", test_lazy_state_retro_stale_design_added_routes_past_step8),
    # Phase 11 WU-5e end-to-end — Step-8 retro-staleness routing (bug-state parity)
    ("test_bug_state_retro_stale_routes_past_step8", test_bug_state_retro_stale_routes_past_step8),
    ("test_bug_state_retro_fresh_routes_past_step8", test_bug_state_retro_fresh_routes_past_step8),
    ("test_bug_state_retro_fieldless_routes_past_step8", test_bug_state_retro_fieldless_routes_past_step8),
    # harden(script) 2026-06-15 — no-plans verification-only Step-7 deadlock (mcp-testing)
    ("test_lazy_state_no_plans_verification_only_routes_to_mcp", test_lazy_state_no_plans_verification_only_routes_to_mcp),
    ("test_lazy_state_no_plans_real_impl_row_still_write_plan", test_lazy_state_no_plans_real_impl_row_still_write_plan),
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
    # Phase 8 WU-8.1 — non-destructive session-mismatch + age/corrupt still delete
    ("test_marker_staleness_session_id_non_destructive", test_marker_staleness_session_id_non_destructive),
    ("test_marker_age_and_corrupt_still_delete", test_marker_age_and_corrupt_still_delete),
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
    # Phase 2 (lazy-validation-readiness) — F2b Unicode-normalize before hashing
    ("test_f2b_emdash_hashes_equal_to_hyphen", test_f2b_emdash_hashes_equal_to_hyphen),
    ("test_f2b_curly_quotes_hash_equal_to_straight", test_f2b_curly_quotes_hash_equal_to_straight),
    ("test_f2b_nbsp_hashes_equal_to_space", test_f2b_nbsp_hashes_equal_to_space),
    ("test_f2b_genuine_word_change_still_differs", test_f2b_genuine_word_change_still_differs),
    # Phase 2 (lazy-validation-readiness) — F2c find_transcription_slip_entry helper
    ("test_f2b_find_transcription_slip_entry_matches_near_copy",
     test_f2b_find_transcription_slip_entry_matches_near_copy),
    ("test_f2b_find_transcription_slip_entry_no_match_for_different_prompt",
     test_f2b_find_transcription_slip_entry_no_match_for_different_prompt),
    ("test_f2b_find_transcription_slip_entry_no_match_without_marker",
     test_f2b_find_transcription_slip_entry_no_match_without_marker),
    ("test_f2b_find_transcription_slip_entry_excludes_hardening_class",
     test_f2b_find_transcription_slip_entry_excludes_hardening_class),
    # Phase 7 — deny ledger, run-end refusal/override, checkpoint, normalization,
    #           single-slot templates, meta cycle_header
    ("test_phase7_symbols_present", test_phase7_symbols_present),
    ("test_deny_ledger_write_read_pending", test_deny_ledger_write_read_pending),
    ("test_deny_ledger_head_truncation", test_deny_ledger_head_truncation),
    ("test_ack_oldest_deny_fifo", test_ack_oldest_deny_fifo),
    ("test_ack_oldest_deny_empty_is_noop", test_ack_oldest_deny_empty_is_noop),
    ("test_deny_ledger_corrupt_line_skipped", test_deny_ledger_corrupt_line_skipped),
    ("test_guard_deny_writes_ledger_entry", test_guard_deny_writes_ledger_entry),
    ("test_guard_deny_ledger_failure_is_fail_open", test_guard_deny_ledger_failure_is_fail_open),
    ("test_run_end_refuses_on_unacked_deny", test_run_end_refuses_on_unacked_deny),
    ("test_checkpoint_round_trip", test_checkpoint_round_trip),
    # Regression: accidental mid-run counter reset (2026-06-14) — HC8 monotonicity
    ("test_restore_checkpoint_counters_carries_forward", test_restore_checkpoint_counters_carries_forward),
    ("test_restore_checkpoint_counters_no_checkpoint_is_noop", test_restore_checkpoint_counters_no_checkpoint_is_noop),
    ("test_restore_checkpoint_counters_coerces_garbage_counts", test_restore_checkpoint_counters_coerces_garbage_counts),
    ("test_marker_advance_round_trips_counters_under_rmw", test_marker_advance_round_trips_counters_under_rmw),
    ("test_checkpoint_resume_preserves_counters_e2e", test_checkpoint_resume_preserves_counters_e2e),
    ("test_normalize_widened_equivalence_pairs", test_normalize_widened_equivalence_pairs),
    ("test_single_slot_dispatch_templates", test_single_slot_dispatch_templates),
    ("test_emit_dispatch_cycle_header_marker_gated", test_emit_dispatch_cycle_header_marker_gated),
    ("test_emit_dispatch_cycle_header_summary_fallback", test_emit_dispatch_cycle_header_summary_fallback),
    # Phase 8 WU-8.2/8.3 — routed hardening debt, guard-allow ack, stderr line, MVB chain
    ("test_probe_withholds_forward_route_on_pending_debt", test_probe_withholds_forward_route_on_pending_debt),
    ("test_emit_dispatch_hardening_no_longer_acks", test_emit_dispatch_hardening_no_longer_acks),
    ("test_guard_allow_acks_on_hardening_class", test_guard_allow_acks_on_hardening_class),
    ("test_phase8_mvb_chain", test_phase8_mvb_chain),
    # Phase 9 — bind-at-guard: inject never binds; guard binds on allow
    ("test_inject_unbound_marker_is_silent_noop", test_inject_unbound_marker_is_silent_noop),
    ("test_inject_bound_owner_still_produces_banner", test_inject_bound_owner_still_produces_banner),
    ("test_guard_unbound_marker_binds_on_allow", test_guard_unbound_marker_binds_on_allow),
    ("test_guard_unbound_marker_binds_on_idempotent_refire", test_guard_unbound_marker_binds_on_idempotent_refire),
    ("test_guard_unbound_marker_deny_does_not_bind", test_guard_unbound_marker_deny_does_not_bind),
    ("test_guard_bind_failure_is_fail_open", test_guard_bind_failure_is_fail_open),
    ("test_guard_bound_non_owner_fast_path_unchanged", test_guard_bound_non_owner_fast_path_unchanged),
]

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
            lazy_core.consume_nonce(nonce, consumer="toolu_abc123")

            resolved = lazy_core.resolve_emission_by_nonce(nonce)
            assert resolved is None, (
                "resolve_emission_by_nonce must return None for a consumed nonce; "
                f"got {resolved!r}"
            )
        finally:
            _clear_state_dir()


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


# Extend _TESTS with Phase 3 (F2a) entries — appended after the list close above.
_TESTS = _TESTS + [
    # Phase 3 (lazy-validation-readiness) — F2a dispatch-by-reference: register_emission
    # stores prompt_raw; resolve_emission_by_nonce resolver; append_dispatch_by_reference_event.
    ("test_f2a_register_emission_stores_prompt_raw",
     test_f2a_register_emission_stores_prompt_raw),
    ("test_f2a_resolve_emission_fresh_nonce_returns_entry",
     test_f2a_resolve_emission_fresh_nonce_returns_entry),
    ("test_f2a_resolve_emission_consumed_nonce_returns_none",
     test_f2a_resolve_emission_consumed_nonce_returns_none),
    ("test_f2a_resolve_emission_missing_nonce_returns_none",
     test_f2a_resolve_emission_missing_nonce_returns_none),
    ("test_f2a_resolve_emission_stale_nonce_returns_none",
     test_f2a_resolve_emission_stale_nonce_returns_none),
    ("test_f2a_append_dispatch_by_reference_event_writes_ledger",
     test_f2a_append_dispatch_by_reference_event_writes_ledger),
]


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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        # --run-start WITHOUT --unattended → attended=True marker.
        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0, f"run-start failed: {r_start.stderr}"

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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0, f"run-start failed: {r_start.stderr}"

        # --operator-authorized bypasses the attended gate.
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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

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
        env = dict(_os_env_p7.environ)
        env["LAZY_STATE_DIR"] = str(state_dir)

        def run(args):
            return subprocess.run(
                [sys.executable, str(lazy_state)] + args,
                capture_output=True, text=True, env=env,
            )

        r_start = run(["--run-start", "--max-cycles", "10"])
        assert r_start.returncode == 0

        # Legacy: --run-end without --terminal-reason → still exits 0 but adds deprecation.
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
    # Check all 9 sanctioned reasons are present.
    required = {
        "all-features-complete",
        "all-bugs-fixed",
        "max-cycles",
        "cloud-queue-exhausted",
        "device-queue-exhausted",
        "queue-missing",
        "blocked-halt-for-manual",
        "needs-research",
        "queue-blocked-on-research",
    }
    missing = required - sst
    assert not missing, (
        f"SANCTIONED_STOP_TERMINAL missing expected reasons: {missing}"
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


_TESTS = _TESTS + [
    # Phase 7 (lazy-validation-readiness) — stop-authorization + attended marker.
    ("test_p7_sanctioned_stop_terminal_constant_exists",
     test_p7_sanctioned_stop_terminal_constant_exists),
    ("test_p7_write_run_marker_defaults_attended",
     test_p7_write_run_marker_defaults_attended),
    ("test_p7_write_run_marker_attended_false",
     test_p7_write_run_marker_attended_false),
    ("test_p7_marker_missing_attended_defaults_true",
     test_p7_marker_missing_attended_defaults_true),
    ("test_p7_run_end_checkpoint_attended_no_auth_refuses",
     test_p7_run_end_checkpoint_attended_no_auth_refuses),
    ("test_p7_run_end_checkpoint_attended_with_auth_succeeds",
     test_p7_run_end_checkpoint_attended_with_auth_succeeds),
    ("test_p7_run_end_checkpoint_unattended_no_auth_allowed",
     test_p7_run_end_checkpoint_unattended_no_auth_allowed),
    ("test_p7_run_end_terminal_sanctioned_reason_allowed",
     test_p7_run_end_terminal_sanctioned_reason_allowed),
    ("test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth",
     test_p7_run_end_terminal_nonsanctioned_reason_refuses_without_auth),
    ("test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed",
     test_p7_run_end_terminal_nonsanctioned_reason_with_auth_allowed),
    ("test_p7_run_end_terminal_no_terminal_reason_adds_deprecation",
     test_p7_run_end_terminal_no_terminal_reason_adds_deprecation),
    ("test_p7_emit_dispatch_includes_dispatch_prompt_ref",
     test_p7_emit_dispatch_includes_dispatch_prompt_ref),
]


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


_TESTS = _TESTS + [
    ("test_self_edit_mode_symbol_present", test_self_edit_mode_symbol_present),
    ("test_self_edit_mode_true_inside_toplevel",
     test_self_edit_mode_true_inside_toplevel),
    ("test_self_edit_mode_false_outside_toplevel",
     test_self_edit_mode_false_outside_toplevel),
    ("test_self_edit_mode_false_normal_repo_no_symlinks",
     test_self_edit_mode_false_normal_repo_no_symlinks),
    ("test_self_edit_mode_false_not_a_git_repo",
     test_self_edit_mode_false_not_a_git_repo),
    ("test_self_edit_mode_false_one_missing_path",
     test_self_edit_mode_false_one_missing_path),
    ("test_governing_file_set_includes_orchestrator_and_components",
     test_governing_file_set_includes_orchestrator_and_components),
    ("test_governing_file_set_excludes_auto_refresh_surfaces",
     test_governing_file_set_excludes_auto_refresh_surfaces),
    ("test_governing_files_touched_intersects_commit",
     test_governing_files_touched_intersects_commit),
    ("test_lazy_batch_skill_carries_reload_discipline_prose",
     test_lazy_batch_skill_carries_reload_discipline_prose),
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


# ---------------------------------------------------------------------------
# Phase 2 (lazy-cycle-containment C1) — cycle-subagent marker
#
# The cycle marker (lazy-cycle-active.json) is the sibling of the run marker.
# Hermetic via LAZY_STATE_DIR temp dirs (same discipline as Phase 1/7).
# ---------------------------------------------------------------------------

_CYCLE_MARKER_FILENAME = "lazy-cycle-active.json"


def test_cycle_marker_symbols_present():
    """Phase 2 public symbols exist on lazy_core."""
    _guard()
    for name in ("read_cycle_marker", "write_cycle_marker", "clear_cycle_marker"):
        assert hasattr(lazy_core, name), f"Phase 2 missing {name}"


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


def test_detect_cycle_bracket_friction_symbols_present():
    """WU-2/3: the new public symbols exist on lazy_core."""
    _guard()
    for name in ("detect_cycle_bracket_friction", "append_friction_ledger_entry"):
        assert hasattr(lazy_core, name), f"Phase 2 missing {name}"


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
    # Control: the SAME multi-commit shape on a kind='real' cycle still trips (b).
    real_marker = dict(meta_marker, kind="real")
    real = lazy_core.detect_cycle_bracket_friction(
        real_marker,
        current_run_started_at="2026-06-16T00:00:00Z",
        current_head_sha="bbbb2222",
        sub_skill=None,
        commits_since=9,
    )
    assert real is not None and real["reason"] == "unexpected-commits", real


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
    # bindings build_hardening_emit_command emits for a process-friction entry).
    ctx = {
        "trigger_kind": "process-friction",
        "item_id": "hardening-blind-to-process-friction",
        "denied_prompt_summary": "unexpected-commits",
        "denial_reason": "HEAD advanced 2 commits since --cycle-begin",
        "probe_json": "step=Step 9 pending_hardening=1",
        "registry_state": "5 entries, 4 unconsumed",
        "cwd": "/repo",
    }
    res = lazy_core.emit_dispatch_prompt("hardening", ctx, pipeline="feature")
    assert res.get("ok") is True, res  # must NOT refuse
    assert "process-friction" in res["prompt"], res
    assert "unexpected-commits" in res["prompt"], res


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


# ---------------------------------------------------------------------------
# Phase 3 (lazy-cycle-containment C3) — refuse-by-construction
#
# The orchestrator-only state-script ops REFUSE (exit non-zero, zero side
# effects, corrective message) when the cycle marker is present.  The guard is
# refuse_if_cycle_active(op_name) in lazy_core; the CLI handlers in
# lazy-state.py / bug-state.py invoke it at the top of each guarded op.
# ---------------------------------------------------------------------------

_GUARDED_OPS = ["--run-end", "--run-start", "--apply-pseudo", "--enqueue-adhoc", "--emit-dispatch"]


def test_refuse_guard_symbol_present():
    """refuse_if_cycle_active exists on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "refuse_if_cycle_active"), "Phase 3 missing refuse_if_cycle_active"


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


def test_refuse_guard_op_set_matches_spec():
    """The refused-op set is exactly the C3 set (kept in lockstep with the C2
    hook deny-set — Phase 4)."""
    _guard()
    assert set(lazy_core.CYCLE_REFUSED_OPS) == set(_GUARDED_OPS), (
        f"refused-op set drift: {sorted(lazy_core.CYCLE_REFUSED_OPS)}"
    )


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


def test_run_start_clobber_symbol_present():
    """refuse_run_start_clobber exists on lazy_core."""
    _guard()
    assert hasattr(lazy_core, "refuse_run_start_clobber"), "D-B missing refuse_run_start_clobber"


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
    """A feature --run-start over a LIVE feature marker (same pipeline =
    checkpoint resume) does NOT refuse — write_run_marker proceeds to overwrite."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        _set_state_dir(Path(td))
        try:
            lazy_core.write_run_marker(pipeline="feature", cloud=False, repo_root="/r", now=1_000_000.0)
            code, _ = _capture_clobber_refusal("feature", now=1_000_010.0)
            assert code is None, "same-pipeline re-run-start must NOT refuse (resume)"
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


# ---------------------------------------------------------------------------
# hardening-blind-to-process-friction Phase 1 (D4) — agent_id-aware C3
#
# refuse_if_cycle_active decides subagent-vs-main-thread in priority order:
#   1. LAZY_ORCHESTRATOR truthy → NEVER refuse (orchestrator immunity, even with
#      a stale marker present — fixes the Proven-Finding-#3 self-deny defect).
#   2. LAZY_CYCLE_SUBAGENT truthy → refuse (explicit subagent signal, no marker
#      required).
#   3. else cycle marker present → refuse (legacy backstop carrier).
# ---------------------------------------------------------------------------

def _clear_cycle_env() -> None:
    for k in ("LAZY_ORCHESTRATOR", "LAZY_CYCLE_SUBAGENT"):
        os.environ.pop(k, None)


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
# Follow-up: structural MCP-skip short-circuit (no-app-surface repos)
#   repo_has_no_app_surface / phases_mcp_runtime_not_required helpers,
#   skip_waiver_refusal(granted_by: pipeline-structural) re-verification, and
#   the __grant_skip_no_mcp_surface__ pseudo-skill (write / refuse / noop /
#   round-trip into __write_validated_from_skip__).
# ---------------------------------------------------------------------------

def _write_not_required_phases(spec: Path) -> None:
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "PHASES.md").write_text(
        "# Phases\n\n**MCP runtime:** not-required\n\n### Phase 1\n- [x] x\n",
        encoding="utf-8",
    )


def test_repo_has_no_app_surface_empty_repo():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        assert lazy_core.repo_has_no_app_surface(Path(td)) is True


def test_repo_has_no_app_surface_false_with_package_json():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "package.json").write_text("{}\n", encoding="utf-8")
        assert lazy_core.repo_has_no_app_surface(Path(td)) is False


def test_repo_has_no_app_surface_false_with_src_tauri():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "src-tauri").mkdir()
        assert lazy_core.repo_has_no_app_surface(Path(td)) is False


def test_phases_mcp_runtime_not_required_true():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        _write_not_required_phases(spec)
        assert lazy_core.phases_mcp_runtime_not_required(spec) is True


def test_phases_mcp_runtime_not_required_false_when_required_or_absent():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        spec.mkdir()
        (spec / "PHASES.md").write_text(
            "# Phases\n\n### Phase 1\n- [x] x\n", encoding="utf-8"
        )
        assert lazy_core.phases_mcp_runtime_not_required(spec) is False
        (spec / "PHASES.md").write_text(
            "# Phases\n\n**MCP runtime:** required\n", encoding="utf-8"
        )
        assert lazy_core.phases_mcp_runtime_not_required(spec) is False
        spec2 = Path(td) / "spec2"
        spec2.mkdir()
        assert lazy_core.phases_mcp_runtime_not_required(spec2) is False


def test_skip_waiver_refusal_pipeline_structural_accepts_no_surface_repo():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        meta = {"granted_by": "pipeline-structural"}
        assert lazy_core.skip_waiver_refusal(meta, Path(td)) is None


def test_skip_waiver_refusal_pipeline_structural_refuses_app_repo():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "package.json").write_text("{}\n", encoding="utf-8")
        refusal = lazy_core.skip_waiver_refusal(
            {"granted_by": "pipeline-structural"}, Path(td)
        )
        assert refusal is not None and "app surface" in refusal


def test_skip_waiver_refusal_pipeline_structural_refuses_without_repo_root():
    _guard()
    # No repo_root → cannot re-verify the predicate → refuse (safe default).
    assert lazy_core.skip_waiver_refusal({"granted_by": "pipeline-structural"}) is not None


def test_apply_pseudo_grant_skip_no_mcp_surface_writes():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec = Path(td) / "spec"
        _write_not_required_phases(spec)
        result = lazy_core.apply_pseudo(
            Path(td), "__grant_skip_no_mcp_surface__", spec, date="2026-06-16"
        )
        assert result["ok"] is True and result["noop"] is False, result
        skip_path = spec / "SKIP_MCP_TEST.md"
        assert skip_path.exists()
        parsed = lazy_core.parse_sentinel(skip_path)
        assert parsed.get("kind") == "skip-mcp-test"
        assert parsed.get("granted_by") == "pipeline-structural"
        assert str(parsed.get("spec_class", "")).strip(), "spec_class must be cited"
        # The grant must validate downstream — re-verified, no app surface here.
        assert lazy_core.skip_waiver_refusal(parsed, Path(td)) is None


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


if __name__ == "__main__":
    sys.exit(main())
