#!/usr/bin/env python3
"""
test_docmodel.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_docmodel.py
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



from _util import _ModuleMissing, _DESCOPED_PHASE_4, _build_blocked_feature_repo, _build_bug_retro_routing_repo, _build_retro_routing_repo, _load_state_script, _write_not_required_phases  # noqa: E402




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
# Tests: phases_show_implementation — implementation-evidence predicate
# (research-gate-ignores-existing-phases P1, RED-first characterization)
# ---------------------------------------------------------------------------

def test_phases_show_impl_zero_parsed_phases_false():
    """(a) No '## Phase' heading → zero parsed phases → False (stub guard)."""
    _guard()
    text = (
        "# Implementation Phases\n"
        "Some preamble prose with no phase headings.\n"
        "- [ ] a stray top-level box that is NOT inside a phase\n"
    )
    assert lazy_core.phases_show_implementation(text) is False




def test_phases_show_impl_complete_status_true():
    """(b) One phase **Status:** Complete → True."""
    _guard()
    text = (
        "### Phase 1: Do the thing\n"
        "**Status:** Complete\n"
        "- [ ] deliverable\n"
    )
    assert lazy_core.phases_show_implementation(text) is True




def test_phases_show_impl_in_progress_status_true():
    """(c) One phase **Status:** In-progress, zero checked boxes → True."""
    _guard()
    text = (
        "### Phase 1: Do the thing\n"
        "**Status:** In-progress\n"
        "- [ ] not done yet\n"
    )
    assert lazy_core.phases_show_implementation(text) is True




def test_phases_show_impl_checked_box_true():
    """(d) Phases all **Status:** Planned but ≥1 '- [x]' deliverable → True."""
    _guard()
    text = (
        "### Phase 1: Alpha\n"
        "**Status:** Planned\n"
        "- [x] already done\n"
        "### Phase 2: Beta\n"
        "**Status:** Planned\n"
        "- [ ] pending\n"
    )
    assert lazy_core.phases_show_implementation(text) is True




def test_phases_show_impl_implementation_notes_true():
    """(e) Phases all Planned, zero checked, but an Implementation Notes block → True."""
    _guard()
    text = (
        "### Phase 1: Alpha\n"
        "**Status:** Planned\n"
        "- [ ] pending\n"
        "## Implementation Notes\n"
        "Did some work here.\n"
    )
    assert lazy_core.phases_show_implementation(text) is True




def test_phases_show_impl_planned_no_evidence_false():
    """(f) Phases parsed, all Planned, zero checked, no Implementation Notes → False."""
    _guard()
    text = (
        "### Phase 1: Alpha\n"
        "**Status:** Planned\n"
        "- [ ] pending one\n"
        "### Phase 2: Beta\n"
        "**Status:** Planned\n"
        "- [ ] pending two\n"
    )
    assert lazy_core.phases_show_implementation(text) is False




def test_repo_uses_cognito_planner_present_true():
    """A repo with `.claude/skills/write-plan-cognito/` → True (emit the Cognito planner)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / ".claude" / "skills" / "write-plan-cognito"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Cognito planner\n", encoding="utf-8")
        assert lazy_core.repo_uses_cognito_planner(Path(td)) is True




def test_repo_uses_cognito_planner_absent_false():
    """A repo with only the generic `write-plan` skill → False (keep generic planner)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / ".claude" / "skills" / "write-plan"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Generic planner\n", encoding="utf-8")
        assert lazy_core.repo_uses_cognito_planner(Path(td)) is False




def test_repo_uses_cognito_planner_no_skills_dir_false():
    """A repo with no `.claude/skills/` at all → False."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        assert lazy_core.repo_uses_cognito_planner(Path(td)) is False




def test_phases_show_impl_fenced_checkbox_does_not_count_false():
    """(g) The only '- [x]' is inside a fenced block → False (fence-awareness)."""
    _guard()
    text = (
        "### Phase 1: Alpha\n"
        "**Status:** Planned\n"
        "```\n"
        "- [x] illustrative example, not a real deliverable\n"
        "```\n"
        "- [ ] real pending box\n"
    )
    assert lazy_core.phases_show_implementation(text) is False




def test_phases_show_impl_sibling_notes_only_true():
    """(h) Notes live in a sibling IMPLEMENTATION_NOTES.md, NONE embedded in PHASES.md,
    and PHASES.md itself shows no other evidence (all Planned, zero checked) → True.

    The sibling-then-embedded read: a relocated-notes feature must NOT read as
    'not yet implemented' just because PHASES.md is now a thin checklist.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        phases_path = Path(td) / "PHASES.md"
        text = (
            "### Phase 1: Alpha\n"
            "**Status:** Planned\n"
            "- [ ] pending one\n"
        )
        phases_path.write_text(text, encoding="utf-8")
        (Path(td) / "IMPLEMENTATION_NOTES.md").write_text(
            "# Feature — Implementation Notes\n"
            "## Phase 1 — Alpha\n"
            "#### Implementation Notes (Phase 1)\n"
            "**Completed:** 2026-06-29\n"
            "Did some work here.\n",
            encoding="utf-8",
        )
        assert (
            lazy_core.phases_show_implementation(text, phases_path=phases_path) is True
        )




def test_phases_show_impl_embedded_notes_still_true_with_path():
    """(i) Legacy embedded '## Implementation Notes' in PHASES.md (no sibling file),
    path supplied → still True (embedded fallback preserved)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        phases_path = Path(td) / "PHASES.md"
        text = (
            "### Phase 1: Alpha\n"
            "**Status:** Planned\n"
            "- [ ] pending\n"
            "## Implementation Notes\n"
            "Did some work here.\n"
        )
        phases_path.write_text(text, encoding="utf-8")
        # No sibling IMPLEMENTATION_NOTES.md exists.
        assert (
            lazy_core.phases_show_implementation(text, phases_path=phases_path) is True
        )




def test_phases_show_impl_no_sibling_no_embedded_false():
    """(j) Neither a sibling IMPLEMENTATION_NOTES.md nor an embedded heading, and
    PHASES.md shows no other evidence → False (negative case, path supplied)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        phases_path = Path(td) / "PHASES.md"
        text = (
            "### Phase 1: Alpha\n"
            "**Status:** Planned\n"
            "- [ ] pending one\n"
            "### Phase 2: Beta\n"
            "**Status:** Planned\n"
            "- [ ] pending two\n"
        )
        phases_path.write_text(text, encoding="utf-8")
        assert (
            lazy_core.phases_show_implementation(text, phases_path=phases_path) is False
        )




def test_phases_show_impl_empty_sibling_does_not_falsely_pass_false():
    """(k) A sibling IMPLEMENTATION_NOTES.md that holds only a title/preamble (no
    per-phase notes block) does NOT count as evidence → False. A bare scaffold file
    must not falsely suppress research."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        phases_path = Path(td) / "PHASES.md"
        text = (
            "### Phase 1: Alpha\n"
            "**Status:** Planned\n"
            "- [ ] pending one\n"
        )
        phases_path.write_text(text, encoding="utf-8")
        (Path(td) / "IMPLEMENTATION_NOTES.md").write_text(
            "# Feature — Implementation Notes\n"
            "> Per-phase notes relocated out of PHASES.md.\n",
            encoding="utf-8",
        )
        assert (
            lazy_core.phases_show_implementation(text, phases_path=phases_path) is False
        )




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




def test_ruvonly_reachability_smoke_bold_subsection():
    """A '**Reachability smoke ...**' sibling bold subsection counts as
    verification-only — its row is a live MCP call owned by /mcp-test, not a
    plannable implementation deliverable.

    Regression for the d8-session-format Phase 8 no-progress loop (2026-06-16
    hardening round): the only non-RuntimeVerification unchecked row sat under a
    bold ``**Reachability smoke (new API surface introduced this phase):**``
    header. Before the fix _VERIFICATION_SECTION_RE did not match
    'Reachability smoke', so the row read as implementation work, the detector
    returned False, and Step 7a looped on write-plan even though every plan part
    was Complete. 'Reachability smoke (new API surface ...)' is a /spec-phases
    authoring convention so this recurs across features.
    """
    _guard()
    text = (
        "### Phase 8: Session format finalize\n"
        "- [x] Implementation complete\n"
        "**Reachability smoke (new API surface introduced this phase):**\n"
        "- [ ] reachability smoke (reachability-smoke — workstation-eligible): "
        "MCP call to trigger_file_menu_action returns a non-error response and "
        "the action is confirmed via get_session_events.\n"
        "**Runtime Verification**\n"
        "- [ ] No console errors on session save\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (reachability-smoke bold subsection is verification-only), got {result}."
    )




def test_ruvonly_reachability_smoke_heading():
    """An '### Reachability Smoke' markdown heading is also a verification
    section (heading-form mirror of the bold-subsection case)."""
    _guard()
    text = (
        "### Reachability Smoke\n"
        "- [ ] MCP call to new tool returns non-error\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, f"expected True, got {result}"




def test_ruvonly_full_chain_seam_audit_bold_subsection():
    """A '**Full-chain seam audit (...):**' sibling bold subsection counts as
    verification-only — its rows are post-fix live-MCP seam re-probes + the
    certifying /mcp-test row, all owned by /mcp-test, not plannable
    implementation deliverables.

    Regression for the d8-session-format Phase 9 no-progress loop (2026-06-16
    hardening round, SECOND consecutive regex-gap class this run after
    'Reachability smoke' / Round 24 / d8d02ef): every implementation deliverable
    was [x] and the only plan was Complete, but the unchecked re-probe seam rows
    + the 'Workstation: /mcp-test ... passes' row sat under the bold
    ``**Full-chain seam audit (HARD — retry_count >= 2 escalation; ...):**``
    header. Before the fix _VERIFICATION_SECTION_RE did not match 'Full-chain
    seam audit' / 'seam audit', so those rows read as implementation work, the
    detector returned False, and Step 7a looped on write-plan forever. The
    'Full-chain seam audit' header is the retry_count>=2 escalation convention
    authored by _components/blocked-resolution.md (step 1a/6), so it recurs on
    EVERY escalated feature.
    """
    _guard()
    text = (
        "### Phase 9: Session format end-to-end\n"
        "- [x] Implementation complete\n"
        "**Full-chain seam audit (HARD — retry_count >= 2 escalation; "
        "consumes INVESTIGATION.md ## Seam Table):**\n"
        "- [ ] seam: user surface → IPC re-probe passes post-fix\n"
        "- [ ] seam: IPC → engine re-probe passes post-fix\n"
        "- [ ] Workstation: /mcp-test session-format-end-to-end passes\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (full-chain seam-audit bold subsection is "
        f"verification-only), got {result}."
    )




def test_ruvonly_seam_audit_heading_variants():
    """The shorter '### Seam Audit' / '### Seam Re-validation' heading forms are
    also verification sections (heading-form mirrors of the escalation
    bold-subsection case)."""
    _guard()
    for header in ("### Seam Audit", "### Seam Re-validation", "### Full-Chain Seam Audit"):
        text = f"{header}\n- [ ] live-probe each seam to final observable\n"
        result = lazy_core.remaining_unchecked_are_verification_only(text)
        assert result is True, f"expected True for header {header!r}, got {result}"




def test_ruvonly_all_remaining_unchecked_in_superseded_phase():
    """When EVERY remaining unchecked row sits inside a Superseded phase, the
    detector returns True (bypass-eligible) — the rows are descoped to a
    successor feature, never remaining implementation work.

    Regression for the split-editor Phase 6 no-progress loop (2026-07-01): every
    implementation plan part was Complete and MCP validation had already written
    VALIDATED.md, but Phase 6 (cross-panel drag) was Superseded — its scope moved
    to the follow-up feature `split-editor-cross-panel-drag` — leaving 6 unchecked
    `- [ ]` deliverables under `**Status:** Superseded`. Before the fix those rows
    were `continue`d WITHOUT setting saw_unchecked, so the function returned
    saw_unchecked=False; the Step-7 workstation bypass never fired and lazy-state
    looped on write-plan against an already-implemented + validated feature (the
    __mark_complete__ gate itself already exempts Superseded, so the bypass was
    the sole hold-out). Superseded phases are a permanent PHASES.md convention
    (descope-to-successor), so this recurs on every such feature.
    """
    _guard()
    text = (
        "### Phase 5: Active-panel routing\n"
        "**Status:** Complete\n"
        "- [x] Implementation complete\n"
        "### Phase 6: Cross-Panel Block Movement\n"
        "**Status:** Superseded\n"
        "> Descoped 2026-07-01 — scope moved to `split-editor-cross-panel-drag`.\n"
        "**Deliverables:**\n"
        "- [ ] Lift drag state to layout scope\n"
        "- [ ] Drop indicators\n"
        "- [ ] Reassignment transaction\n"
        "### Phase 7: Scroll sync\n"
        "**Status:** Complete\n"
        "- [x] Implementation complete\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (all remaining unchecked rows are in a Superseded phase), "
        f"got {result}."
    )




def test_ruvonly_superseded_unchecked_plus_genuine_impl_still_false():
    """A Superseded-phase unchecked row does NOT mask a genuine implementation
    row in a non-Superseded phase — real remaining work still returns False so
    the bypass does not fire and write-plan/execute-plan is kept."""
    _guard()
    text = (
        "### Phase 1: Real work\n"
        "**Status:** In-progress\n"
        "**Deliverables:**\n"
        "- [ ] build the actual feature\n"
        "### Phase 6: Descoped\n"
        "**Status:** Superseded\n"
        "- [ ] descoped deliverable\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, (
        f"expected False (genuine impl row outside the Superseded phase remains), "
        f"got {result}."
    )




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




def test_verification_only_deliverables_after_verification_section_is_false():
    """Implementation **Deliverables:** AFTER a verification subsection → False.

    The escalation-corrective-phase shape /add-phase produces at retry_count >= 2:
    a Full-chain Seam Audit / Runtime Verification subsection FIRST, then a
    **Deliverables:** subsection with genuine implementation rows. Before the
    _DELIVERABLES_SECTION_RE fix, the non-matching **Deliverables:** bold did NOT
    reset in_verification, so the Fix rows under it inherited the verification
    scope and were swept verification-only → True → lazy-state.py misrouted the
    feature straight to the Step-9 MCP gate before the corrective code was
    written (burned on adhoc-clap-live-poly-mod-producer-feed Phase 6, 2026-06-24).

    A **Deliverables:** subsection must END the verification scope, so its
    implementation rows count as remaining work → predicate returns False →
    route to write-plan/execute-plan.
    """
    _guard()
    text = (
        "### Phase 6: Corrective\n"
        "**Full-chain Seam Audit (escalation requirement):**\n"
        "- [ ] <!-- verification-only --> Seam: reset_state clear probed-OK\n"
        "**Deliverables:**\n"
        "- [ ] Fix A (production): add ClapPluginState::clear_poly_mod_diagnostics\n"
        "- [ ] Fix B (scenario): edit both scenario copies\n"
        "**MCP Integration Test Assertions:**\n"
        "- [ ] <!-- verification-only --> a2/a3 PASS — baseline dormant\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, (
        f"expected False (implementation Deliverables after a verification "
        f"subsection must NOT be swept verification-only), got {result}."
    )




def test_verification_only_deliverables_then_verification_still_true():
    """**Deliverables:** with ALL rows checked, then a verification subsection
    with only verification rows → True (no implementation work remains).

    Confirms the _DELIVERABLES_SECTION_RE reset does not over-reach: once the
    implementation rows are ticked, a following verification subsection's
    unchecked rows are still correctly exempt.
    """
    _guard()
    text = (
        "### Phase 6: Corrective\n"
        "**Deliverables:**\n"
        "- [x] Fix A (production): implemented\n"
        "- [x] Fix B (scenario): implemented\n"
        "**Runtime Verification:**\n"
        "- [ ] assert mod_engaged true while sounding\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (only verification rows remain unchecked), got {result}."
    )




# ---------------------------------------------------------------------------
# Tests: descoped-in-place (struck-through **DROPPED**) rows —
# remaining_unchecked_are_verification_only
#   (verification-only-bypass-blind-to-descoped-rows, 2026-07-12)
# ---------------------------------------------------------------------------
def test_verification_only_descoped_dropped_row_is_true():
    """A fully-Complete PHASES whose SOLE unchecked row is a struck-through
    **DROPPED** descope note → True (bypass-eligible).

    Live shape: live-settings-split-brain-... PHASES line 128 — a deliberately
    dropped deliverable authored as `- [ ] ~~<text>~~ **DROPPED** (...)`. Not-to-
    be-done, exactly like a Superseded row, so it must count toward the Step-7
    verification bypass instead of looping write-plan on an already-done item.
    """
    _guard()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "- [ ] ~~`setup.py` gains the parallel live hook/symlink check~~ "
        "**DROPPED** (decision 2, `NEEDS_INPUT.md` resolution, 2026-07-12): "
        "scope note only — no code deliverable here.\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (sole unchecked row is a struck-through DROPPED descope "
        f"note — not remaining work), got {result}."
    )




def test_verification_only_plain_unchecked_row_still_false():
    """CONSERVATISM: a plain unchecked row (no strikethrough, no descope marker)
    still → False. The descope carve-out must not over-exempt genuine work."""
    _guard()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "- [ ] setup.py gains the parallel live hook/symlink check\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, (
        f"expected False (a plain unchecked row is genuine remaining work), "
        f"got {result}."
    )




def test_verification_only_struck_without_descope_marker_still_false():
    """CONSERVATISM: a struck-through row WITHOUT an explicit descope marker
    still → False. Strikethrough alone (e.g. reformatting) must not exempt —
    BOTH the strikethrough AND a descope marker are required."""
    _guard()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "- [ ] ~~`setup.py` gains the parallel live hook/symlink check~~ "
        "(still owed — struck for readability, not dropped)\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is False, (
        f"expected False (struck-through but NOT descope-marked — still owed "
        f"work), got {result}."
    )




def test_verification_only_descoped_marker_only_row_is_true():
    """The canonical structural descope marker `_DESCOPED_MARKER` alone (no
    free-text keyword like **DROPPED**, no strikethrough) must exempt a row —
    mirroring `_VERIFICATION_ONLY_MARKER`, which needs no accompanying regex.

    RED today: `lazy_core._DESCOPED_MARKER` does not exist yet, and the
    marker-primary detection path is unimplemented.
    """
    _guard()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "- [ ] <!-- descoped --> some deliverable dropped by decision 2\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (row carries the canonical descope marker alone — "
        f"no free-text keyword or strikethrough required), got {result}."
    )




def test_verification_only_legacy_dropped_row_still_true_with_migration_diagnostic():
    """Legacy path (struck-through **DROPPED**, NO `<!-- descoped -->` marker)
    must still exempt (no regression) — but the deprecation shim must now
    record a migration diagnostic naming the un-migrated descope gap, mirroring
    `_VERIFICATION_SECTION_RE`'s existing shim-diagnostic precedent.

    RED today: no migration diagnostic is emitted for the legacy descope path.
    """
    _guard()
    lazy_core.clear_diagnostics()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "- [ ] ~~`setup.py` gains the parallel live hook/symlink check~~ "
        "**DROPPED** (decision 2, `NEEDS_INPUT.md` resolution, 2026-07-12): "
        "scope note only — no code deliverable here.\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (legacy struck-through DROPPED descope note — no "
        f"regression), got {result}."
    )
    diags = lazy_core._DIAGNOSTICS
    assert any(
        "descope" in d.lower()
        and (
            "un-migrated" in d.lower()
            or "unmigrated" in d.lower()
            or "deprecat" in d.lower()
            or "marker" in d.lower()
        )
        for d in diags
    ), (
        f"expected a migration diagnostic naming the un-migrated descope gap "
        f"(legacy free-text path, no canonical marker), got {diags!r}"
    )




def test_verification_only_descoped_marker_no_diagnostic():
    """The marker-only row (canonical `_DESCOPED_MARKER` present) must NOT
    emit a descope migration diagnostic — the marker path is primary and
    non-deprecated, so no warning belongs there.

    RED today: the marker path doesn't exist, so this assertion cannot yet be
    meaningfully satisfied by design (it will fail alongside the others until
    the marker-primary detection is implemented without a spurious warning).
    """
    _guard()
    lazy_core.clear_diagnostics()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "- [ ] <!-- descoped --> some deliverable dropped by decision 2\n"
    )
    lazy_core.remaining_unchecked_are_verification_only(text)
    assert not any(
        "descope" in d.lower()
        and (
            "un-migrated" in d.lower()
            or "unmigrated" in d.lower()
            or "deprecat" in d.lower()
        )
        for d in lazy_core._DIAGNOSTICS
    ), (
        f"marker path must not warn; got {lazy_core._DIAGNOSTICS!r}"
    )




def test_verification_only_descoped_header_scope_marker_exempts_rows_beneath():
    """A bold subsection header carrying `<!-- descoped -->` must exempt every
    plain `- [ ]` row beneath it (no per-row marker, no free-text keyword) —
    mirroring `section_has_marker` for verification rows.

    RED today: no header-scope descope marker detection exists.
    """
    _guard()
    text = (
        "### Phase 4\n"
        "- [x] warn-pass extension shipped\n"
        "**Descoped:** <!-- descoped -->\n"
        "- [ ] first dropped deliverable\n"
        "- [ ] second dropped deliverable\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"expected True (header-scope descope marker exempts every plain row "
        f"beneath it), got {result}."
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
# Tests: parse_sentinel tolerance for unquoted colon-space scalar values
# (skip-mcp-test-frontmatter-unquoted-colon — WU-1)
# ---------------------------------------------------------------------------

def test_parse_sentinel_unquoted_colon_space_reason():
    """An unquoted colon-space in a scalar `reason` value → read as a literal
    string (no _die/SystemExit). This is the exact bug: an operator-authored
    SKIP_MCP_TEST.md `reason` carrying a colon-space hard-halted parse_sentinel."""
    _guard()
    content = (
        "---\n"
        "kind: skip-mcp-test\n"
        "granted_by: operator\n"
        "reason: untestable on this host: no real audio device\n"
        "---\n\n"
        "# Skip\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "SKIP_MCP_TEST.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result.get("kind") == "skip-mcp-test", f"kind mismatch: {result}"
    assert result.get("granted_by") == "operator", f"granted_by mismatch: {result}"
    assert result.get("reason") == "untestable on this host: no real audio device", (
        f"reason should be the literal full string, got: {result.get('reason')!r}"
    )




def test_parse_sentinel_value_naming_key_value_pair():
    """A scalar value that itself names a `key: value` pair → parses to the
    literal string (no nested mapping, no _die)."""
    _guard()
    content = (
        "---\n"
        "kind: blocked\n"
        "skipped_by: deferred because config: value was missing\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result.get("skipped_by") == "deferred because config: value was missing", (
        f"skipped_by should be the literal string, got: {result.get('skipped_by')!r}"
    )




def test_parse_sentinel_trailing_colon_value():
    """A value ending in a bare colon → read as a literal (no _die)."""
    _guard()
    content = (
        "---\n"
        "kind: blocked\n"
        "reason: waiting on:\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result.get("reason") == "waiting on:", (
        f"reason should be the literal 'waiting on:', got: {result.get('reason')!r}"
    )




def test_parse_sentinel_colon_no_space_is_plain_scalar_control():
    """CONTROL: a colon with NO following space (`build:step`) is already a
    valid plain scalar — the result is byte-identical to today (the tolerant
    path is never reached because yaml.safe_load succeeds)."""
    _guard()
    content = (
        "---\n"
        "kind: blocked\n"
        "reason: build:step\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert result.get("reason") == "build:step", f"reason mismatch: {result}"




def test_parse_sentinel_malformed_non_scalar_still_dies():
    """NON-VACUITY: a genuinely-malformed frontmatter that is NOT a flat-scalar
    colon case (an unclosed flow collection) must STILL _die/SystemExit — the
    tolerant path must not mask real malformation."""
    _guard()
    import pytest as _pytest
    content = (
        "---\n"
        "kind: blocked\n"
        "reason: [unclosed, flow, collection\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "BLOCKED.md"
        p.write_text(content, encoding="utf-8")
        with _pytest.raises(SystemExit):
            lazy_core.parse_sentinel(p)




def test_parse_sentinel_well_formed_no_colon_unchanged():
    """REGRESSION GUARD: a well-formed, no-colon sentinel is byte-identical to
    pre-change (the tolerant path is never entered)."""
    _guard()
    content = (
        "---\n"
        "kind: validated\n"
        "feature_id: my-feature\n"
        "validated_commit: abc123\n"
        "pass_count: 5\n"
        "---\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "VALIDATED.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert result == {
        "kind": "validated",
        "feature_id": "my-feature",
        "validated_commit": "abc123",
        "pass_count": 5,
    }, f"well-formed parse drifted: {result}"




# ---------------------------------------------------------------------------
# Tests: _yaml_fallback_scalar — quote-on-write hardening for the no-PyYAML
# manual frontmatter fallback (skip-mcp-test-frontmatter-unquoted-colon — WU-3)
# ---------------------------------------------------------------------------

def test_yaml_fallback_scalar_quotes_colon_bearing_roundtrips():
    """The no-PyYAML manual fallback quotes a colon-bearing scalar value so the
    emitted `key: value` line is valid YAML, and parse_sentinel round-trips it to
    the literal string (parity with what yaml.safe_dump emits)."""
    _guard()
    colon_reason = "untestable on this host: no real audio device"
    rendered = lazy_core._yaml_fallback_scalar(colon_reason)
    assert rendered.startswith("'") and rendered.endswith("'"), (
        f"colon-bearing value must be single-quoted, got: {rendered!r}"
    )
    # Round-trip: build frontmatter exactly as the hardened fallback does.
    content = (
        "---\n"
        "kind: skip-mcp-test\n"
        f"reason: {rendered}\n"
        "---\n\n# Sentinel\n"
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "SKIP_MCP_TEST.md"
        p.write_text(content, encoding="utf-8")
        result = lazy_core.parse_sentinel(p)
    assert result.get("reason") == colon_reason, (
        f"round-trip failed: {result.get('reason')!r}"
    )
    # A trailing-colon value is also quoted.
    assert lazy_core._yaml_fallback_scalar("waiting on:").startswith("'"), (
        "a trailing-colon value must be quoted"
    )




def test_yaml_fallback_scalar_leaves_plain_value_unchanged():
    """A colon-free scalar value — and a colon-WITHOUT-space value (a valid plain
    scalar) and a non-string — is rendered unchanged: no spurious quoting that
    would drift the fallback's pre-existing output for the common case."""
    _guard()
    assert lazy_core._yaml_fallback_scalar("operator") == "operator"
    # `build:step` (colon, no following space) is a valid plain scalar — safe_dump
    # leaves it unquoted, so must the fallback.
    assert lazy_core._yaml_fallback_scalar("build:step") == "build:step"
    assert lazy_core._yaml_fallback_scalar(5) == "5"




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
        script = Path(lazy_core._SCRIPTS_DIR) / "lazy-state.py"
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




def test_parse_phases_counts_unchecked_descoped():
    """parse_phases exposes an additive `unchecked_descoped` sub-count of
    `unchecked` — row-scope marker, header-scope marker, and legacy struck-through
    shim all count; `unchecked` itself stays a full tally for existing callers."""
    text = (
        "## Phase 1 — done\n\n**Status:** Complete\n\n- [x] real\n\n"
        + _DESCOPED_PHASE_4
    )
    parsed = lazy_core.parse_phases(text)
    p4 = parsed[1]
    assert p4["unchecked"] == 2, f"unchecked must tally every box, got {p4['unchecked']}"
    assert p4["unchecked_descoped"] == 2, (
        f"both rows are descoped (row+header scope), got {p4['unchecked_descoped']}"
    )
    # Existing callers unaffected: Phase 1 has no descoped rows.
    assert parsed[0]["unchecked_descoped"] == 0




def test_phase_completion_plan_descoped_phase_not_refused():
    """The repro: a fully-descoped phase (row+header scope, no Status) produces
    ZERO refusals — the deadlock class this bug fixes."""
    parsed = lazy_core.parse_phases(_DESCOPED_PHASE_4)
    _flip, refusals = lazy_core._phase_completion_plan(parsed)
    assert refusals == [], f"a fully-descoped phase must not refuse, got {refusals!r}"




def test_phase_completion_plan_header_scope_descope_exempts():
    """Header-scope only: the rows lack the row marker but sit under a bold header
    carrying `<!-- descoped -->` — still exempt."""
    text = (
        "### Phase 6: deferred\n\n**Descoped:** <!-- descoped -->\n"
        "- [ ] a\n- [ ] b\n"
    )
    parsed = lazy_core.parse_phases(text)
    assert parsed[0]["unchecked_descoped"] == 2
    _flip, refusals = lazy_core._phase_completion_plan(parsed)
    assert refusals == [], f"header-scope descope must exempt all rows, got {refusals!r}"




def test_phase_completion_plan_mixed_descoped_and_genuine_still_refuses():
    """OVER-EXEMPTION GUARD: a phase with a genuine unchecked row alongside a
    descoped one still refuses — and names ONLY the genuine (blocking) count."""
    text = (
        "### Phase 5: mixed\n\n**Deliverables:**\n"
        "- [ ] genuine work not done\n"
        "- [ ] dropped one <!-- descoped -->\n"
    )
    parsed = lazy_core.parse_phases(text)
    assert parsed[0]["unchecked"] == 2 and parsed[0]["unchecked_descoped"] == 1
    _flip, refusals = lazy_core._phase_completion_plan(parsed)
    assert len(refusals) == 1 and "1 unchecked box(es)" in refusals[0], (
        f"must refuse the 1 genuine box (not 2), got {refusals!r}"
    )




def test_phase_completion_plan_descoped_phase_with_status_flips():
    """A descoped-only phase carrying a non-terminal Status line auto-flips to
    Complete (like an all-ticked phase) instead of tripping the status-straggler
    refusal."""
    text = (
        "### Phase 7: deferred with status\n\n**Status:** In-progress\n\n"
        "**Deliverables:** all dropped <!-- descoped -->\n"
        "- [ ] a <!-- descoped -->\n"
    )
    parsed = lazy_core.parse_phases(text)
    flip, refusals = lazy_core._phase_completion_plan(parsed)
    assert refusals == [], f"expected no refusal, got {refusals!r}"
    assert flip and flip[0]["heading"].startswith("### Phase 7"), (
        f"the descoped phase should flip to Complete, got flip={flip!r}"
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




def test_deferred_requires_host_is_fail_closed_evidence_sentinel():
    """DEFERRED_REQUIRES_HOST.md is a member of _FAIL_CLOSED_EVIDENCE_SENTINELS
    (the completion gate treats it as defer-not-evidence, parallel to the device
    sentinel) so a host-deferred feature never reaches Complete here."""
    _guard()
    assert "DEFERRED_REQUIRES_HOST.md" in lazy_core._FAIL_CLOSED_EVIDENCE_SENTINELS




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




def test_classify_blocking_unchecked_rows_shim_vs_genuine():
    """harden 2026-07: the completion-refusal classifier splits still-unchecked
    rows into un-migrated verification-shim (under a Runtime-Verification
    subsection, no canonical marker) vs genuine incomplete deliverables;
    canonical-marked rows and Superseded-phase rows are excluded (not blocking)."""
    _guard()
    phases = (
        "### Phase 1: Foo\n"
        "**Status:** In-progress\n"
        "**Deliverables:**\n"
        "- [ ] genuine incomplete deliverable\n"
        "**Runtime Verification**\n"
        "- [ ] shim row under a verification subsection no marker\n"
        "- [ ] already canonical row <!-- verification-only -->\n"
        "### Phase 2: Bar\n"
        "**Status:** Superseded\n"
        "- [ ] superseded row excluded\n"
    )
    cls = lazy_core.classify_blocking_unchecked_rows(phases)
    assert len(cls["genuine"]) == 1, cls
    assert "genuine incomplete" in cls["genuine"][0], cls
    assert len(cls["shim"]) == 1, cls
    assert "shim row" in cls["shim"][0], cls
    joined = " ".join(cls["shim"] + cls["genuine"])
    assert "already canonical" not in joined, cls   # canonical → auto-ticked, not blocking
    assert "superseded" not in joined.lower(), cls   # Superseded phase → excluded




# ---------------------------------------------------------------------------
# harness-hardening-retro-fixes Phase 2 (WU-5) — verification-only canonical
# marker: novel-header (a), un-migrated-warning (b), lockstep (c).
# ---------------------------------------------------------------------------
#
# These exercise the structural canonical marker (`_VERIFICATION_ONLY_MARKER`)
# that replaces the growing free-text `_VERIFICATION_SECTION_RE`. The detector
# keys off the marker; the regex is demoted to a deprecation shim that emits a
# `_DIAGNOSTICS` warning when it WOULD have matched but the marker is absent.
#
# TDD note: test (a) was authored RED before WU-3 — a NEVER-BEFORE-SEEN
# verification header is invisible to the regex, so without marker support the
# gate returns False (the regression). After WU-3 keys off the marker, it
# returns True with no regex growth.

# Paths to the two Phase-2 producer components (WU-4) for the lockstep test.
_PHASES_RUNTIME_VERIFICATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills" / "_components" / "phases-runtime-verification.md"
)


_BLOCKED_RESOLUTION_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills" / "_components" / "blocked-resolution.md"
)


_COMPLETENESS_POLICY_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills" / "_components" / "completeness-policy.md"
)




def test_verification_only_marker_constant_present():
    """WU-3: the SSOT marker constant exists and is the per-row HTML comment form
    resolved for Open Question 2."""
    _guard()
    assert hasattr(lazy_core, "_VERIFICATION_ONLY_MARKER"), (
        "lazy_core must define the SSOT constant _VERIFICATION_ONLY_MARKER (WU-3)"
    )
    assert lazy_core.docmodel._VERIFICATION_ONLY_MARKER == "<!-- verification-only -->", (
        "Open Question 2 resolved toward the per-row HTML comment form; "
        f"got {lazy_core.docmodel._VERIFICATION_ONLY_MARKER!r}"
    )




def test_ruvonly_novel_header_with_marker_passes():
    """WU-5(a): a verification subsection with a NEVER-BEFORE-SEEN header text +
    the canonical marker present → gate returns True via the marker (no regex
    growth). The header text deliberately matches NONE of the legacy regex
    alternatives."""
    _guard()
    text = (
        "### Phase 1\n"
        "- [x] Implementation done\n"
        "### Quantum Flux Capacitor Calibration\n"  # never-before-seen header
        "- [ ] <!-- verification-only --> live probe returns a non-error response\n"
        "- [ ] <!-- verification-only --> sustained run shows no dropout\n"
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    assert result is True, (
        f"novel header + per-row marker must pass via the marker; got {result}"
    )




def test_ruvonly_novel_header_without_marker_warns_and_fails():
    """WU-5(b): a verification subsection whose header DOES match the legacy regex
    but whose rows carry NO marker (un-migrated producer) → the deprecation shim
    emits a _DIAGNOSTICS warning naming the un-migrated case AND still exempts the
    rows (no regression for un-migrated PHASES.md). Does NOT silently pass clean."""
    _guard()
    lazy_core.clear_diagnostics()
    text = (
        "### Phase 1\n"
        "- [x] Implementation done\n"
        "### Runtime Verification\n"  # matches the legacy regex
        "- [ ] live probe returns a non-error response\n"  # NO marker
    )
    result = lazy_core.remaining_unchecked_are_verification_only(text)
    # Still exempts (no regression) — the rows are under a regex-matched header.
    assert result is True, (
        f"un-migrated regex-matched header must still exempt its rows; got {result}"
    )
    # But the gap is surfaced — at least one diagnostic names the un-migrated case.
    diags = lazy_core._DIAGNOSTICS
    assert any(
        "verification-only" in d.lower() and (
            "un-migrated" in d.lower() or "unmigrated" in d.lower()
            or "deprecat" in d.lower() or "marker" in d.lower()
        )
        for d in diags
    ), (
        "deprecation shim must append a _DIAGNOSTICS warning naming the "
        f"un-migrated (no-marker) verification subsection; got {diags!r}"
    )




def test_ruvonly_marker_lockstep_producers_match_ssot():
    """WU-5(c): the canonical marker referenced in BOTH producer components
    (phases-runtime-verification.md, blocked-resolution.md) equals the
    lazy_core SSOT constant — string equality, no divergent hardcoding."""
    _guard()
    marker = lazy_core.docmodel._VERIFICATION_ONLY_MARKER

    assert _PHASES_RUNTIME_VERIFICATION_PATH.exists(), (
        f"missing producer component: {_PHASES_RUNTIME_VERIFICATION_PATH}"
    )
    assert _BLOCKED_RESOLUTION_PATH.exists(), (
        f"missing producer component: {_BLOCKED_RESOLUTION_PATH}"
    )
    prv = _PHASES_RUNTIME_VERIFICATION_PATH.read_text(encoding="utf-8")
    bres = _BLOCKED_RESOLUTION_PATH.read_text(encoding="utf-8")

    assert marker in prv, (
        "phases-runtime-verification.md must reference the canonical marker "
        f"{marker!r} by value (WU-4); not found"
    )
    assert marker in bres, (
        "blocked-resolution.md must reference the canonical marker "
        f"{marker!r} by value (WU-4); not found"
    )
    # SSOT discipline: each producer must point back at the lazy_core constant
    # (by name), not silently re-hardcode a divergent string.
    assert "_VERIFICATION_ONLY_MARKER" in prv, (
        "phases-runtime-verification.md must name the SSOT constant "
        "lazy_core:_VERIFICATION_ONLY_MARKER so future edits track the source"
    )
    assert "_VERIFICATION_ONLY_MARKER" in bres, (
        "blocked-resolution.md must name the SSOT constant "
        "lazy_core:_VERIFICATION_ONLY_MARKER so future edits track the source"
    )




def test_descoped_marker_lockstep_producer_matches_ssot():
    """The descope-authoring guidance in completeness-policy.md references the
    canonical marker lazy_core._DESCOPED_MARKER BY VALUE — no divergent
    hardcoding. Mirrors test_ruvonly_marker_lockstep_producers_match_ssot."""
    _guard()
    marker = lazy_core._DESCOPED_MARKER

    assert _COMPLETENESS_POLICY_PATH.exists(), (
        f"missing producer component: {_COMPLETENESS_POLICY_PATH}"
    )
    text = _COMPLETENESS_POLICY_PATH.read_text(encoding="utf-8")

    assert marker in text, (
        "completeness-policy.md must reference the canonical descope marker "
        f"{marker!r} by value; not found"
    )




def test_ctx_rebindable_globals_via_accessors():
    """The two rebindable globals _active_repo_root / _legacy_state_migrated
    must be reachable through lazy_core._ctx's accessor functions, AND a
    direct module-attribute patch on lazy_core._ctx must ALSO be observed by
    the getter — i.e. the getter reads the live module global on every call;
    it must not cache or close over a stale value at import time."""
    _guard()
    original_legacy = lazy_core._ctx._legacy_state_migrated
    original_repo_root = lazy_core._ctx._active_repo_root
    try:
        # --- _legacy_state_migrated ---
        lazy_core._ctx.set_legacy_state_migrated(True)
        assert lazy_core._ctx.legacy_state_migrated() is True, (
            "set_legacy_state_migrated(True) must be observed by "
            "legacy_state_migrated()"
        )
        lazy_core._ctx._legacy_state_migrated = False  # direct attribute patch
        assert lazy_core._ctx.legacy_state_migrated() is False, (
            "a direct lazy_core._ctx._legacy_state_migrated patch must be "
            "observed by legacy_state_migrated() — the getter must read the "
            "live module global, not a cached/closed-over value"
        )

        # --- _active_repo_root ---
        sentinel_a = "/tmp/wu2-ctx-accessor-sentinel-repo"
        lazy_core._ctx.set_active_repo_root_value(sentinel_a)
        assert lazy_core._ctx.get_active_repo_root() == sentinel_a, (
            "set_active_repo_root_value(...) must be observed by "
            "get_active_repo_root()"
        )
        sentinel_b = "/tmp/wu2-ctx-accessor-direct-patch-repo"
        lazy_core._ctx._active_repo_root = sentinel_b  # direct attribute patch
        assert lazy_core._ctx.get_active_repo_root() == sentinel_b, (
            "a direct lazy_core._ctx._active_repo_root patch must be observed "
            "by get_active_repo_root() — the getter must read the live module "
            "global"
        )
    finally:
        lazy_core._ctx._legacy_state_migrated = original_legacy
        lazy_core._ctx._active_repo_root = original_repo_root


_TESTS = [
    ("test_symbols_present", test_symbols_present),
    ("test_count_deliverables_empty", test_count_deliverables_empty),
    ("test_count_deliverables_mixed", test_count_deliverables_mixed),
    ("test_count_deliverables_only_unchecked", test_count_deliverables_only_unchecked),
    ("test_count_deliverables_only_checked", test_count_deliverables_only_checked),
    ("test_phases_show_impl_zero_parsed_phases_false", test_phases_show_impl_zero_parsed_phases_false),
    ("test_phases_show_impl_complete_status_true", test_phases_show_impl_complete_status_true),
    ("test_phases_show_impl_in_progress_status_true", test_phases_show_impl_in_progress_status_true),
    ("test_phases_show_impl_checked_box_true", test_phases_show_impl_checked_box_true),
    ("test_phases_show_impl_implementation_notes_true", test_phases_show_impl_implementation_notes_true),
    ("test_phases_show_impl_planned_no_evidence_false", test_phases_show_impl_planned_no_evidence_false),
    ("test_repo_uses_cognito_planner_present_true", test_repo_uses_cognito_planner_present_true),
    ("test_repo_uses_cognito_planner_absent_false", test_repo_uses_cognito_planner_absent_false),
    ("test_repo_uses_cognito_planner_no_skills_dir_false", test_repo_uses_cognito_planner_no_skills_dir_false),
    ("test_phases_show_impl_fenced_checkbox_does_not_count_false", test_phases_show_impl_fenced_checkbox_does_not_count_false),
    ("test_phases_show_impl_sibling_notes_only_true", test_phases_show_impl_sibling_notes_only_true),
    ("test_phases_show_impl_embedded_notes_still_true_with_path", test_phases_show_impl_embedded_notes_still_true_with_path),
    ("test_phases_show_impl_no_sibling_no_embedded_false", test_phases_show_impl_no_sibling_no_embedded_false),
    ("test_phases_show_impl_empty_sibling_does_not_falsely_pass_false", test_phases_show_impl_empty_sibling_does_not_falsely_pass_false),
    ("test_ruvonly_no_unchecked", test_ruvonly_no_unchecked),
    ("test_ruvonly_all_under_heading", test_ruvonly_all_under_heading),
    ("test_ruvonly_mixed_outside", test_ruvonly_mixed_outside),
    ("test_ruvonly_bold_marker_format", test_ruvonly_bold_marker_format),
    ("test_ruvonly_mcp_integration_test_heading", test_ruvonly_mcp_integration_test_heading),
    ("test_ruvonly_reachability_smoke_bold_subsection", test_ruvonly_reachability_smoke_bold_subsection),
    ("test_ruvonly_reachability_smoke_heading", test_ruvonly_reachability_smoke_heading),
    ("test_ruvonly_full_chain_seam_audit_bold_subsection", test_ruvonly_full_chain_seam_audit_bold_subsection),
    ("test_ruvonly_seam_audit_heading_variants", test_ruvonly_seam_audit_heading_variants),
    ("test_ruvonly_all_remaining_unchecked_in_superseded_phase", test_ruvonly_all_remaining_unchecked_in_superseded_phase),
    ("test_ruvonly_superseded_unchecked_plus_genuine_impl_still_false", test_ruvonly_superseded_unchecked_plus_genuine_impl_still_false),
    ("test_count_deliverables_skips_fenced_checkboxes", test_count_deliverables_skips_fenced_checkboxes),
    ("test_count_deliverables_multiple_fences", test_count_deliverables_multiple_fences),
    ("test_verification_only_ignores_fenced_rows", test_verification_only_ignores_fenced_rows),
    ("test_verification_only_non_verification_bold_not_a_boundary", test_verification_only_non_verification_bold_not_a_boundary),
    ("test_verification_only_bold_marker_format_preserved", test_verification_only_bold_marker_format_preserved),
    ("test_verification_only_heading_form_with_assessment_bold", test_verification_only_heading_form_with_assessment_bold),
    ("test_verification_only_real_task_outside_still_false", test_verification_only_real_task_outside_still_false),
    ("test_verification_only_deliverables_after_verification_section_is_false", test_verification_only_deliverables_after_verification_section_is_false),
    ("test_verification_only_deliverables_then_verification_still_true", test_verification_only_deliverables_then_verification_still_true),
    ("test_verification_only_descoped_dropped_row_is_true", test_verification_only_descoped_dropped_row_is_true),
    ("test_verification_only_plain_unchecked_row_still_false", test_verification_only_plain_unchecked_row_still_false),
    ("test_verification_only_struck_without_descope_marker_still_false", test_verification_only_struck_without_descope_marker_still_false),
    ("test_verification_only_descoped_marker_only_row_is_true", test_verification_only_descoped_marker_only_row_is_true),
    ("test_verification_only_legacy_dropped_row_still_true_with_migration_diagnostic", test_verification_only_legacy_dropped_row_still_true_with_migration_diagnostic),
    ("test_verification_only_descoped_marker_no_diagnostic", test_verification_only_descoped_marker_no_diagnostic),
    ("test_verification_only_descoped_header_scope_marker_exempts_rows_beneath", test_verification_only_descoped_header_scope_marker_exempts_rows_beneath),
    ("test_unchecked_wus_in_scope_skips_fenced", test_unchecked_wus_in_scope_skips_fenced),
    ("test_unchecked_wus_in_scope_real_labels_returned", test_unchecked_wus_in_scope_real_labels_returned),
    ("test_parse_sentinel_absent", test_parse_sentinel_absent),
    ("test_parse_sentinel_no_frontmatter", test_parse_sentinel_no_frontmatter),
    ("test_parse_sentinel_with_frontmatter", test_parse_sentinel_with_frontmatter),
    ("test_parse_sentinel_leading_blanks", test_parse_sentinel_leading_blanks),
    ("test_parse_sentinel_unquoted_colon_space_reason", test_parse_sentinel_unquoted_colon_space_reason),
    ("test_parse_sentinel_value_naming_key_value_pair", test_parse_sentinel_value_naming_key_value_pair),
    ("test_parse_sentinel_trailing_colon_value", test_parse_sentinel_trailing_colon_value),
    ("test_parse_sentinel_colon_no_space_is_plain_scalar_control", test_parse_sentinel_colon_no_space_is_plain_scalar_control),
    ("test_parse_sentinel_malformed_non_scalar_still_dies", test_parse_sentinel_malformed_non_scalar_still_dies),
    ("test_parse_sentinel_well_formed_no_colon_unchanged", test_parse_sentinel_well_formed_no_colon_unchanged),
    ("test_yaml_fallback_scalar_quotes_colon_bearing_roundtrips", test_yaml_fallback_scalar_quotes_colon_bearing_roundtrips),
    ("test_yaml_fallback_scalar_leaves_plain_value_unchanged", test_yaml_fallback_scalar_leaves_plain_value_unchanged),
    ("test_build_parked_entry_well_formed_sentinel", test_build_parked_entry_well_formed_sentinel),
    ("test_build_parked_entry_missing_decisions_is_zero", test_build_parked_entry_missing_decisions_is_zero),
    ("test_build_parked_entry_missing_date_is_none", test_build_parked_entry_missing_date_is_none),
    ("test_build_parked_entry_malformed_decisions_is_zero", test_build_parked_entry_malformed_decisions_is_zero),
    ("test_build_parked_entry_sentinel_kind_blocked", test_build_parked_entry_sentinel_kind_blocked),
    ("test_build_parked_entry_sentinel_kind_needs_input", test_build_parked_entry_sentinel_kind_needs_input),
    ("test_build_parked_entry_sentinel_kind_unknown", test_build_parked_entry_sentinel_kind_unknown),
    ("test_spec_status_none_path", test_spec_status_none_path),
    ("test_spec_status_no_spec_md", test_spec_status_no_spec_md),
    ("test_spec_status_complete", test_spec_status_complete),
    ("test_spec_status_in_progress", test_spec_status_in_progress),
    ("test_spec_status_first_occurrence_wins", test_spec_status_first_occurrence_wins),
    ("test_spec_status_superseded", test_spec_status_superseded),
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
    ("test_plan_series_index_from_filename", test_plan_series_index_from_filename),
    ("test_plan_series_index_frontmatter_override", test_plan_series_index_frontmatter_override),
    ("test_plan_sort_key_series_beats_phase", test_plan_sort_key_series_beats_phase),
    ("test_find_implementation_plans_part_series_order", test_find_implementation_plans_part_series_order),
    ("test_find_implementation_plans_non_series_phase_order_preserved", test_find_implementation_plans_non_series_phase_order_preserved),
    ("test_plan_complexity_mechanical", test_plan_complexity_mechanical),
    ("test_plan_complexity_complex_explicit", test_plan_complexity_complex_explicit),
    ("test_plan_complexity_absent_defaults_complex", test_plan_complexity_absent_defaults_complex),
    ("test_plan_complexity_legacy_no_frontmatter_defaults_complex", test_plan_complexity_legacy_no_frontmatter_defaults_complex),
    ("test_plan_complexity_unknown_value_defaults_complex", test_plan_complexity_unknown_value_defaults_complex),
    ("test_plan_complexity_case_insensitive", test_plan_complexity_case_insensitive),
    ("test_plan_complexity_absent_path_defaults_complex", test_plan_complexity_absent_path_defaults_complex),
    ("test_apply_pseudo_validated_from_results_escapes_special_scenarios", test_apply_pseudo_validated_from_results_escapes_special_scenarios),
    ("test_parse_phases_basic_multi_phase", test_parse_phases_basic_multi_phase),
    ("test_parse_phases_h3_headings_recognized", test_parse_phases_h3_headings_recognized),
    ("test_parse_phases_fence_aware", test_parse_phases_fence_aware),
    ("test_parse_phases_fence_with_lang_tag", test_parse_phases_fence_with_lang_tag),
    ("test_parse_phases_phase_without_status_line", test_parse_phases_phase_without_status_line),
    ("test_parse_phases_top_level_status_not_captured", test_parse_phases_top_level_status_not_captured),
    ("test_parse_phases_empty_text_no_phases", test_parse_phases_empty_text_no_phases),
    ("test_parse_phases_phase_summary_section_not_a_phase", test_parse_phases_phase_summary_section_not_a_phase),
    ("test_parse_phases_english_word_after_phase_not_counted", test_parse_phases_english_word_after_phase_not_counted),
    ("test_count_phases_cli_matches_parse_phases", test_count_phases_cli_matches_parse_phases),
    ("test_parse_phases_phase_kind_corrective_read", test_parse_phases_phase_kind_corrective_read),
    ("test_parse_phases_phase_kind_design_explicit", test_parse_phases_phase_kind_design_explicit),
    ("test_parse_phases_phase_kind_defaults_design_when_absent", test_parse_phases_phase_kind_defaults_design_when_absent),
    ("test_parse_phases_phase_kind_case_insensitive_and_first_wins", test_parse_phases_phase_kind_case_insensitive_and_first_wins),
    ("test_parse_phases_phase_kind_unknown_value_defaults_design", test_parse_phases_phase_kind_unknown_value_defaults_design),
    ("test_retro_staleness_only_corrective_added_not_stale", test_retro_staleness_only_corrective_added_not_stale),
    ("test_retro_staleness_one_design_added_is_stale", test_retro_staleness_one_design_added_is_stale),
    ("test_retro_staleness_added_untagged_phase_is_stale_backcompat", test_retro_staleness_added_untagged_phase_is_stale_backcompat),
    ("test_parse_phases_counts_unchecked_descoped", test_parse_phases_counts_unchecked_descoped),
    ("test_phase_completion_plan_descoped_phase_not_refused", test_phase_completion_plan_descoped_phase_not_refused),
    ("test_phase_completion_plan_header_scope_descope_exempts", test_phase_completion_plan_header_scope_descope_exempts),
    ("test_phase_completion_plan_mixed_descoped_and_genuine_still_refuses", test_phase_completion_plan_mixed_descoped_and_genuine_still_refuses),
    ("test_phase_completion_plan_descoped_phase_with_status_flips", test_phase_completion_plan_descoped_phase_with_status_flips),
    ("test_skip_waiver_refusal_operator_accepts", test_skip_waiver_refusal_operator_accepts),
    ("test_skip_waiver_refusal_legacy_no_provenance_accepts", test_skip_waiver_refusal_legacy_no_provenance_accepts),
    ("test_skip_waiver_refusal_pipeline_refuses", test_skip_waiver_refusal_pipeline_refuses),
    ("test_skip_waiver_refusal_unknown_value_refuses", test_skip_waiver_refusal_unknown_value_refuses),
    ("test_skip_waiver_refusal_mcp_test_with_class_accepts", test_skip_waiver_refusal_mcp_test_with_class_accepts),
    ("test_skip_waiver_refusal_mcp_test_missing_class_refuses", test_skip_waiver_refusal_mcp_test_missing_class_refuses),
    ("test_skip_waiver_refusal_pipeline_authored_omission_refuses", test_skip_waiver_refusal_pipeline_authored_omission_refuses),
    ("test_retro_staleness_stale_counts_returned", test_retro_staleness_stale_counts_returned),
    ("test_retro_staleness_string_digit_count", test_retro_staleness_string_digit_count),
    ("test_retro_staleness_equal_counts_fresh", test_retro_staleness_equal_counts_fresh),
    ("test_retro_staleness_missing_field_grandfathered", test_retro_staleness_missing_field_grandfathered),
    ("test_retro_staleness_no_phases_md_no_signal", test_retro_staleness_no_phases_md_no_signal),
    ("test_lazy_state_blocked_no_escalation_missing_fields", test_lazy_state_blocked_no_escalation_missing_fields),
    ("test_lazy_state_retro_stale_routes_past_step8", test_lazy_state_retro_stale_routes_past_step8),
    ("test_lazy_state_retro_fieldless_routes_past_step8", test_lazy_state_retro_fieldless_routes_past_step8),
    ("test_bug_state_retro_stale_routes_past_step8", test_bug_state_retro_stale_routes_past_step8),
    ("test_bug_state_retro_fieldless_routes_past_step8", test_bug_state_retro_fieldless_routes_past_step8),
    ("test_deferred_requires_host_is_fail_closed_evidence_sentinel", test_deferred_requires_host_is_fail_closed_evidence_sentinel),
    ("test_repo_has_no_app_surface_empty_repo", test_repo_has_no_app_surface_empty_repo),
    ("test_repo_has_no_app_surface_false_with_package_json", test_repo_has_no_app_surface_false_with_package_json),
    ("test_repo_has_no_app_surface_false_with_src_tauri", test_repo_has_no_app_surface_false_with_src_tauri),
    ("test_phases_mcp_runtime_not_required_true", test_phases_mcp_runtime_not_required_true),
    ("test_phases_mcp_runtime_not_required_false_when_required_or_absent", test_phases_mcp_runtime_not_required_false_when_required_or_absent),
    ("test_skip_waiver_refusal_pipeline_structural_accepts_no_surface_repo", test_skip_waiver_refusal_pipeline_structural_accepts_no_surface_repo),
    ("test_skip_waiver_refusal_pipeline_structural_refuses_app_repo", test_skip_waiver_refusal_pipeline_structural_refuses_app_repo),
    ("test_skip_waiver_refusal_pipeline_structural_refuses_without_repo_root", test_skip_waiver_refusal_pipeline_structural_refuses_without_repo_root),
    ("test_apply_pseudo_grant_skip_no_mcp_surface_writes", test_apply_pseudo_grant_skip_no_mcp_surface_writes),
    ("test_classify_blocking_unchecked_rows_shim_vs_genuine", test_classify_blocking_unchecked_rows_shim_vs_genuine),
    ("test_verification_only_marker_constant_present", test_verification_only_marker_constant_present),
    ("test_ruvonly_novel_header_with_marker_passes", test_ruvonly_novel_header_with_marker_passes),
    ("test_ruvonly_novel_header_without_marker_warns_and_fails", test_ruvonly_novel_header_without_marker_warns_and_fails),
    ("test_ruvonly_marker_lockstep_producers_match_ssot", test_ruvonly_marker_lockstep_producers_match_ssot),
    ("test_descoped_marker_lockstep_producer_matches_ssot", test_descoped_marker_lockstep_producer_matches_ssot),
    ("test_ctx_rebindable_globals_via_accessors", test_ctx_rebindable_globals_via_accessors),
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
