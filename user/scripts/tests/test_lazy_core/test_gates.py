#!/usr/bin/env python3
"""
test_gates.py — split shard of test_lazy_core.py (lazy-core-package-decomposition
WU-2). One of 12 per-seam test files under user/scripts/tests/test_lazy_core/;
see conftest.py and the sibling files for the rest of the split.

Run under pytest (collected automatically), or standalone via:
    python3 user/scripts/tests/test_lazy_core/test_gates.py
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



from _util import _ModuleMissing, _build_retro_routing_repo, _cc_seed_and_commit, _cc_write_validated, _collect_duplicate_top_level_defs, _gate_write_manifest, _gate_write_verdict, _git_fixture_commit, _lint_skills_module, _load_state_script, _make_git_repo_with_origin, _prov_git_commit_file, _prov_git_fixture_repo, _prov_spec_dir, _write_mcp_test_results, _write_mcp_test_results_with_exemptions, _write_skip_mcp_test  # noqa: E402




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




def test_verify_ledger_spec_md_file_arg_normalizes_to_parent_dir():
    """A SPEC.md FILE arg yields the SAME verdict as passing the spec DIRECTORY.

    Regression for bug `verify-ledger-planning-scope-and-file-arg`: verify_ledger
    contractually takes the spec DIRECTORY (it computes `spec_path / 'PHASES.md'`),
    but the cycle-prompt metavar reads as the SPEC.md FILE, so callers pass the
    file. Passing the file used to yield a MISLEADING verdict against a phantom
    `.../SPEC.md/PHASES.md`. The function now normalizes a `.md` arg to its parent
    directory at the source, so a file arg and its parent dir agree exactly.

    Fixture: the same all-green tree as test_verify_ledger_all_green_passes, plus a
    SPEC.md file in the spec dir. Both `verify_ledger(root, dir)` and
    `verify_ledger(root, dir / "SPEC.md")` must return ok=True with identical checks.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        (spec_dir / "SPEC.md").write_text("# my-feat\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "add feature files"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "push"], check=True,
                       capture_output=True)

        dir_result = lazy_core.verify_ledger(repo_root, spec_dir)
        file_result = lazy_core.verify_ledger(repo_root, spec_dir / "SPEC.md")

    assert dir_result["ok"] is True, f"dir arg should be ok=True, got {dir_result}"
    assert file_result["ok"] is True, (
        f"SPEC.md file arg should normalize to the dir and be ok=True, got {file_result}"
    )
    assert file_result["checks"] == dir_result["checks"], (
        "file-arg and dir-arg checks must be identical after normalization: "
        f"file={file_result['checks']} dir={dir_result['checks']}"
    )


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
# Tests: verify_ledger — harness-hardening-retro-fixes Phase 3 (WU-2)
# plan_complete absent-by-design (plan-less / realign-only) vs incomplete
# ---------------------------------------------------------------------------
#
# A plan-less or realign-only feature has NO implementation plan and never
# needed one. The pre-fix feature-level rule
# (``plan_complete = any_complete AND no_incomplete``) returns False for such a
# feature (any_complete is False because there is no Complete *implementation*
# plan), producing a benign-but-noisy false-alarm ``plan_complete:false`` and a
# recovery chase. The fix treats "no implementation plan present and none
# required" as absent-by-design → True, while preserving the incomplete-plan
# regression (a real incomplete implementation plan still returns False).
#
# TDD note: tests (a) + (b) below assert ``plan_complete:true`` for the
# plan-less / realign-only fixtures — RED before WU-1 (the pre-fix branch
# returns False); GREEN once WU-1 adds the absent-by-design branch. Test (c) is
# the regression guard and is GREEN both before and after (the fix must not
# vacuously pass a real incomplete plan).


def test_verify_ledger_plan_less_feature_absent_by_design_passes():
    """(a) Plan-less feature: PHASES.md present, all deliverables checked, NO
    implementation plan on disk (no ``plans/`` dir at all) →
    ``plan_complete:true`` (absent-by-design) and ``ok:true``."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        # NO plans/ directory — genuinely plan-less.
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)  # feature-level
    assert result["checks"]["plan_complete"] is True, (
        f"plan-less feature must be absent-by-design plan_complete=True: "
        f"{result['checks']}"
    )
    assert result["ok"] is True, (
        f"plan-less feature with all deliverables checked + clean git should be "
        f"ok=True: {result}"
    )




def test_verify_ledger_realign_only_feature_absent_by_design_passes():
    """(b) Realign-only feature: only ``plans/realign-*.md`` present (no
    implementation plan) → ``plan_complete:true`` (absent-by-design)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        plans.mkdir(parents=True)
        # Only a realign plan — find_implementation_plans skips realign-*.md, so
        # there is no IMPLEMENTATION plan: absent-by-design.
        (plans / "realign-2026-06-17.md").write_text(
            "---\n"
            "kind: realign-plan\n"
            "status: Complete\n"
            "---\n\n"
            "# Realign\n",
            encoding="utf-8",
        )
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)  # feature-level
    assert result["checks"]["plan_complete"] is True, (
        f"realign-only feature must be absent-by-design plan_complete=True: "
        f"{result['checks']}"
    )




def test_verify_ledger_incomplete_plan_still_fails_regression_guard():
    """(c) Regression guard: a feature WITH an incomplete (status: Ready)
    implementation plan still returns ``plan_complete:false`` — the
    absent-by-design fix must NOT vacuously pass a real incomplete plan."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans = spec_dir / "plans"
        plans.mkdir(parents=True)
        # A real implementation plan that is NOT Complete — there IS a plan on
        # disk, so the absent-by-design branch must not fire.
        (plans / "plan-phase-1.md").write_text(
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
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)  # feature-level
    assert result["checks"]["plan_complete"] is False, (
        f"a real incomplete implementation plan must still fail plan_complete: "
        f"{result['checks']}"
    )
    assert result["failing_check"] == "plan_complete", (
        f"incomplete-plan regression must report failing_check='plan_complete': "
        f"{result['failing_check']!r}"
    )




# ---------------------------------------------------------------------------
# Tests: verify_ledger `failing_detail` (completion-gate-refusal-opacity) —
# every False check names the offending items, not just the boolean.
# ---------------------------------------------------------------------------

def test_verify_ledger_failing_detail_empty_when_ok():
    """ok=True → failing_detail is an empty dict (additive, never gates)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)
    assert result["ok"] is True, result
    assert result["failing_detail"] == {}, result["failing_detail"]




def test_verify_ledger_failing_detail_clean_tree_names_dirty_files():
    """clean_tree=False → failing_detail['clean_tree'] carries the dirty file
    list (from the already-captured `git status --short` stdout) + total_count."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        (repo_root / "dirty.txt").write_text("untracked\n", encoding="utf-8")
        result = lazy_core.verify_ledger(repo_root, spec_dir)
    assert result["failing_check"] == "clean_tree", result
    detail = result["failing_detail"]["clean_tree"]
    assert detail["total_count"] == 1, detail
    assert any("dirty.txt" in f for f in detail["dirty_files"]), detail




def test_verify_ledger_failing_detail_head_matches_origin_ahead_behind():
    """head_matches_origin=False (unpushed local commit) → failing_detail names
    the short shas + ahead/behind counts, no_upstream False (a genuine
    divergence, not the unconfigured-upstream branch)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        (repo_root / "extra.txt").write_text("unpushed change\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_root), "add", "extra.txt"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m",
                        "unpushed commit"], check=True, capture_output=True)
        result = lazy_core.verify_ledger(repo_root, spec_dir)
    assert result["failing_check"] == "head_matches_origin", result
    detail = result["failing_detail"]["head_matches_origin"]
    assert detail["no_upstream"] is False, detail
    assert detail.get("head_sha") and detail.get("upstream_sha"), detail
    assert detail["head_sha"] != detail["upstream_sha"], detail
    assert detail.get("ahead") == 1, detail
    assert detail.get("behind") == 0, detail




def test_verify_ledger_failing_detail_no_upstream_configured():
    """head_matches_origin=False with NO upstream configured at all →
    failing_detail['head_matches_origin']['no_upstream'] is True, distinct
    from a genuine divergence (no ahead/behind computed)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@test.local"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"],
                       check=True, capture_output=True)
        spec_dir = root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        _write_all_checked_phases(spec_dir)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"],
                       check=True, capture_output=True)
        result = lazy_core.verify_ledger(root, spec_dir)
    assert result["failing_check"] == "head_matches_origin", result
    detail = result["failing_detail"]["head_matches_origin"]
    assert detail["no_upstream"] is True, detail
    assert "ahead" not in detail and "behind" not in detail, detail




def test_verify_ledger_failing_detail_plan_complete_feature_level():
    """plan_complete=False (feature-level) → failing_detail names each
    incomplete plan's file + parsed status."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans_dir = spec_dir / "plans"
        plans_dir.mkdir(parents=True)
        (plans_dir / "plan-phase-1.md").write_text(
            "---\nkind: implementation-plan\nstatus: Ready\nphases:\n  - 1\n---\n\n"
            "# Implementation Plan\n",
            encoding="utf-8",
        )
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)
    assert result["failing_check"] == "plan_complete", result
    detail = result["failing_detail"]["plan_complete"]
    assert detail["total_count"] == 1, detail
    assert detail["incomplete_plans"][0]["file"] == "plan-phase-1.md", detail
    assert detail["incomplete_plans"][0]["status"] == "Ready", detail




def test_verify_ledger_failing_detail_plan_complete_scoped():
    """plan_complete=False (plan-scoped) → failing_detail names the scoped
    plan's own file + status (not the feature-level incomplete_plans list)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans_dir = spec_dir / "plans"
        plans_dir.mkdir(parents=True)
        part1 = plans_dir / "plan-part-1.md"
        part1.write_text(
            "---\nkind: implementation-plan\nstatus: In-progress\nphases:\n  - 1\n---\n\n"
            "- [x] WU-1 — done\n",
            encoding="utf-8",
        )
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["failing_check"] == "plan_complete", result
    detail = result["failing_detail"]["plan_complete"]
    assert detail == {"plan_file": "plan-part-1.md", "plan_status": "In-progress"}, detail




def test_verify_ledger_failing_detail_deliverables_done_feature_level():
    """deliverables_done=False (feature-level PHASES.md) → failing_detail
    carries the unchecked row's line number + excerpt, and the total count."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        _write_complete_plan(spec_dir / "plans")
        (spec_dir / "PHASES.md").write_text(
            "### Phase 1\n"
            "- [x] Implement feature\n"
            "- [ ] Wire into production context\n",
            encoding="utf-8",
        )
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir)
    assert result["failing_check"] == "deliverables_done", result
    detail = result["failing_detail"]["deliverables_done"]
    assert detail["total"] == 1, detail
    assert detail["rows"][0]["line"] == 3, detail
    assert "Wire into production context" in detail["rows"][0]["text"], detail




def test_verify_ledger_failing_detail_deliverables_done_plan_wu():
    """deliverables_done=False (plan-scoped, plan-wu-checkboxes source) →
    failing_detail reads the PLAN's own unchecked WU rows, not PHASES.md."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root, _origin = _make_git_repo_with_origin(td)
        spec_dir = repo_root / "docs" / "features" / "my-feat"
        spec_dir.mkdir(parents=True)
        plans_dir = spec_dir / "plans"
        plans_dir.mkdir(parents=True)
        part1 = plans_dir / "plan-part-1.md"
        part1.write_text(
            "---\nkind: implementation-plan\nstatus: Complete\nphases:\n  - 1\n---\n\n"
            "- [x] WU-1 — done\n"
            "- [ ] WU-2 — not done\n",
            encoding="utf-8",
        )
        _write_all_checked_phases(spec_dir)
        _commit_and_push_spec(repo_root)
        result = lazy_core.verify_ledger(repo_root, spec_dir, plan_path=part1)
    assert result["failing_check"] == "deliverables_done", result
    assert result["deliverables_source"] == "plan-wu-checkboxes", result
    detail = result["failing_detail"]["deliverables_done"]
    assert detail["total"] == 1, detail
    assert detail["rows"][0]["line"] == 9, detail
    assert "WU-2" in detail["rows"][0]["text"], detail




# ---------------------------------------------------------------------------
# Tests: summarize_failing_detail (completion-gate-refusal-opacity Fix Scope
# §3 — the compact `detail_head` telemetry string).
# ---------------------------------------------------------------------------

def test_summarize_failing_detail_clean_tree():
    _guard()
    result = {
        "failing_check": "clean_tree",
        "failing_detail": {"clean_tree": {"dirty_files": ["M foo.py"], "total_count": 3}},
    }
    head = lazy_core.summarize_failing_detail(result)
    assert head == "dirty tree: 3 file(s) (first: M foo.py)", head




def test_summarize_failing_detail_head_no_upstream():
    _guard()
    result = {
        "failing_check": "head_matches_origin",
        "failing_detail": {"head_matches_origin": {"no_upstream": True}},
    }
    assert lazy_core.summarize_failing_detail(result) == "no upstream configured"




def test_summarize_failing_detail_head_ahead_behind():
    _guard()
    result = {
        "failing_check": "head_matches_origin",
        "failing_detail": {
            "head_matches_origin": {"no_upstream": False, "ahead": 2, "behind": 1}
        },
    }
    assert lazy_core.summarize_failing_detail(result) == "2 ahead / 1 behind upstream"




def test_summarize_failing_detail_deliverables_done():
    _guard()
    result = {
        "failing_check": "deliverables_done",
        "failing_detail": {
            "deliverables_done": {"total": 4, "rows": [{"line": 12, "text": "- [ ] foo"}]}
        },
    }
    head = lazy_core.summarize_failing_detail(result)
    assert head == "4 unchecked row(s) (first: - [ ] foo)", head




def test_summarize_failing_detail_ok_is_empty_string():
    """ok=True (failing_check=None) → "" — never a spurious summary."""
    _guard()
    result = {"ok": True, "failing_check": None, "failing_detail": {}}
    assert lazy_core.summarize_failing_detail(result) == ""




def test_summarize_failing_detail_malformed_never_raises():
    """A legacy/malformed payload (missing failing_detail keys) degrades to
    "" rather than raising — the telemetry path must never crash the gate."""
    _guard()
    assert lazy_core.summarize_failing_detail({}) == ""
    assert lazy_core.summarize_failing_detail({"failing_check": "clean_tree"}) == ""
    assert lazy_core.summarize_failing_detail(
        {"failing_check": "clean_tree", "failing_detail": {"clean_tree": {}}}
    ) == "dirty tree: 0 file(s)"




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




def test_planner_resolution_resolves_via_internal_repos_when_passed_repos_empty():
    """With an EMPTY passed repos_dir (the bug scenario: no sibling checkouts under
    ~/source/repos), the D1 gate must STILL resolve write-plan-cognito via the
    canonical internal <claude-config>/repos/ — no 'planner-resolution' finding.
    The internal scan is now an EXPLICIT parameter (production main() passes
    resolve_internal_repos_root()); this test passes it the same way to mirror
    the production call — see the skill_repos.py consolidation (harden Round 26)."""
    mod = _lint_skills_module()
    with tempfile.TemporaryDirectory() as td:
        empty_repos = Path(td) / "empty-source-repos"
        empty_repos.mkdir()
        empty_user_skills = Path(td) / "empty-user-skills"
        empty_user_skills.mkdir()

        issues = mod.lint_planner_resolution(
            empty_repos, empty_user_skills, mod.resolve_internal_repos_root()
        )
        kinds = {i["kind"] for i in issues}
        # The false-RED finding this bug is about must NOT appear: the internal
        # repos/ resolution fills in for the empty passed repos_dir.
        assert "planner-resolution" not in kinds, (
            "write-plan-cognito must resolve via internal <claude-config>/repos/ "
            f"even with an empty passed repos_dir; got issues: {issues}"
        )
        # And no spurious executor-fork false positive from the internal scan.
        assert "executor-fork" not in kinds, (
            f"unexpected execute-plan-cognito fork finding: {issues}"
        )




# ---- WU-2: gate_coverage (symlink-resolving) ----

def _write_spec_with_locked_decisions(spec_dir: Path, decisions: list[tuple[str, str]]):
    """Write a SPEC.md with a ## Locked Decisions table. Each decision is
    (id, title)."""
    rows = "\n".join(f"| {did} | {title} |" for did, title in decisions)
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "SPEC.md").write_text(
        "# Spec\n\n"
        "**Status:** In-progress\n\n"
        "## Locked Decisions\n\n"
        "| ID | Decision |\n"
        "|----|----------|\n"
        f"{rows}\n",
        encoding="utf-8",
    )




def test_gate_coverage_symbol_present():
    _guard()
    assert hasattr(lazy_core, "gate_coverage"), "lazy_core.gate_coverage is missing"




def test_gate_coverage_covered_and_uncovered_verdict():
    """A SPEC with one covered + one uncovered Locked Decision returns the
    correct per-decision verdict."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        _write_spec_with_locked_decisions(
            spec_dir,
            [("L1", "tempo sync uses bars"), ("L2", "quantize on export only")],
        )
        mcp = spec_dir / "mcp-tests"
        mcp.mkdir()
        # Scenario covers L1 (literal id) but not L2.
        (mcp / "scenario-a.md").write_text(
            "Validates L1: the tempo sync uses bars decision is exercised.\n",
            encoding="utf-8",
        )
        result = lazy_core.gate_coverage(spec_dir)
        assert result["ok"] is True, result
        by_id = {d["id"]: d for d in result["decisions"]}
        assert by_id["L1"]["covered"] is True, result
        assert by_id["L2"]["covered"] is False, result
        assert "L2" in result["uncovered"], result
        assert "L1" not in result["uncovered"], result




def test_gate_coverage_resolves_symlink_pointer_file():
    """When an mcp-tests/*.md entry is a SYMLINK (or a 64-byte Windows pointer
    file) whose TARGET carries the decision keyword, coverage must resolve
    through the pointer rather than missing it."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        _write_spec_with_locked_decisions(spec_dir, [("L1", "loudness normalization target")])
        mcp = spec_dir / "mcp-tests"
        mcp.mkdir()
        # The real scenario lives elsewhere; mcp-tests/ holds only a pointer.
        target_dir = Path(td) / "canonical"
        target_dir.mkdir()
        target = target_dir / "real-scenario.md"
        target.write_text(
            "Asserts L1: loudness normalization target met across the run.\n",
            encoding="utf-8",
        )
        link = mcp / "scenario.md"
        made_real_symlink = False
        try:
            link.symlink_to(target)
            made_real_symlink = True
        except (OSError, NotImplementedError):
            # Windows without privilege: simulate the 64-byte pointer file that
            # git writes when symlink support is off — a tiny text file whose
            # content is the relative target path.
            rel = os.path.relpath(target, mcp)
            link.write_text(rel, encoding="utf-8")
        result = lazy_core.gate_coverage(spec_dir)
        by_id = {d["id"]: d for d in result["decisions"]}
        assert by_id["L1"]["covered"] is True, (
            f"symlink/pointer target not resolved (made_real_symlink="
            f"{made_real_symlink}): {result}"
        )




def test_gate_coverage_resolves_pointer_file_unconditionally():
    """The 64-byte Windows pointer-file case explicitly (no real symlink, ever):
    an mcp-tests/*.md whose CONTENT is a relative path to the real scenario must
    resolve through the pointer. Guarantees coverage of the Windows blindspot
    even on hosts where symlinks succeed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        _write_spec_with_locked_decisions(spec_dir, [("L7", "sidechain ducking curve")])
        mcp = spec_dir / "mcp-tests"
        mcp.mkdir()
        target_dir = Path(td) / "canonical"
        target_dir.mkdir()
        target = target_dir / "real.md"
        target.write_text(
            "Covers L7: sidechain ducking curve verified.\n", encoding="utf-8"
        )
        # ALWAYS a plain text pointer file (the git-on-Windows form), never a
        # real symlink.
        rel = os.path.relpath(target, mcp).replace("\\", "/")
        (mcp / "scenario.md").write_text(rel, encoding="utf-8")
        result = lazy_core.gate_coverage(spec_dir)
        by_id = {d["id"]: d for d in result["decisions"]}
        assert by_id["L7"]["covered"] is True, (
            f"pointer-file target not resolved: {result}"
        )




def test_gate_coverage_no_locked_decisions_passes_vacuously():
    """A SPEC with no Locked-Decision surface passes vacuously (ok, empty
    decisions, empty uncovered)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir()
        (spec_dir / "SPEC.md").write_text(
            "# Spec\n\n**Status:** In-progress\n\nNo decisions here.\n",
            encoding="utf-8",
        )
        result = lazy_core.gate_coverage(spec_dir)
        assert result["ok"] is True, result
        assert result["decisions"] == [], result
        assert result["uncovered"] == [], result




def test_gate_coverage_empty_mcp_tests_all_uncovered():
    """A SPEC with Locked Decisions but an empty/absent mcp-tests dir → all
    decisions uncovered."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        _write_spec_with_locked_decisions(
            spec_dir, [("L1", "alpha beta decision"), ("L2", "gamma delta decision")]
        )
        result = lazy_core.gate_coverage(spec_dir)
        assert result["ok"] is True, result
        assert set(result["uncovered"]) == {"L1", "L2"}, result




def test_gate_coverage_skips_hash_decision_table_header():
    """harden 2026-07: a '| # | Decision | Choice | Source |' header row (first
    cell '#', not 'id') must NOT parse as a phantom decision id='#'. RED against
    the pre-fix id-only skip which let '#' through → Gate 1 unsatisfiable."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "SPEC.md").write_text(
            "# Spec\n\n## Locked Decisions\n\n"
            "| # | Decision | Choice | Source |\n"
            "|---|----------|--------|--------|\n"
            "| D1 | Business-model shape | Hybrid | research |\n"
            "| D2 | Pricing baseline | $15 pack | research |\n",
            encoding="utf-8",
        )
        result = lazy_core.gate_coverage(spec_dir)
        ids = {d["id"] for d in result["decisions"]}
        assert ids == {"D1", "D2"}, result
        assert "#" not in ids, result
        assert "#" not in result["uncovered"], result




def test_parse_mcp_coverage_exemptions_requires_rationale():
    """The exemptions parser recognizes '- D4: rationale' (and '- D4 — r') but
    IGNORES a bare '- D5' with no rationale (an empty stub cannot exempt)."""
    _guard()
    spec_md = (
        "## MCP Coverage Exemptions\n\n"
        "- D4: backend/miniflare — verified by Workers integration tests\n"
        "- D5 — orthogonal fuel policy, no Tauri MCP surface\n"
        "- D6\n"                       # bare, no rationale → ignored
        "- D7:   \n"                   # whitespace-only rationale → ignored
        "\n## Next Section\n"
        "- D8: this is AFTER the section and must NOT be parsed\n"
    )
    ex = lazy_core._parse_mcp_coverage_exemptions(spec_md)
    assert set(ex.keys()) == {"D4", "D5"}, ex
    assert "backend" in ex["D4"].lower(), ex
    assert "D6" not in ex and "D7" not in ex and "D8" not in ex, ex




def test_gate_coverage_honors_spec_exemption():
    """A Locked Decision with no scenario coverage but listed in
    '## MCP Coverage Exemptions' with a rationale is NOT uncovered; its entry
    carries exempt=True + rationale. A scenario-covered decision stays
    covered=True (not exempt)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td) / "spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "SPEC.md").write_text(
            "# Spec\n\n## Locked Decisions\n\n"
            "| # | Decision | Choice | Source |\n"
            "|---|----------|--------|--------|\n"
            "| D1 | Balance UI | categorized costs | brainstorm |\n"
            "| D4 | Backend identity scope | Workers proxy | research |\n\n"
            "## MCP Coverage Exemptions\n\n"
            "- D4: backend/miniflare Workers runtime — outside the Tauri MCP "
            "surface; verified by Workers integration tests\n",
            encoding="utf-8",
        )
        mcp = spec_dir / "mcp-tests"
        mcp.mkdir()
        (mcp / "s.md").write_text("Validates D1 balance UI.\n", encoding="utf-8")
        result = lazy_core.gate_coverage(spec_dir)
        by_id = {d["id"]: d for d in result["decisions"]}
        assert by_id["D1"]["covered"] is True, result
        assert by_id["D1"].get("exempt") is not True, result
        assert by_id["D4"]["covered"] is False, result
        assert by_id["D4"].get("exempt") is True, result
        assert "backend" in by_id["D4"].get("rationale", "").lower(), result
        assert result["uncovered"] == [], result




def test_eval_evidence_exempt_and_tick_happy_path():
    """VALIDATED.md + passing MCP_TEST_RESULTS.md (validated_commit == HEAD) →
    verdict 'exempt-and-tick', pass_count surfaced, validated_commit surfaced.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "docs" / "features" / "cc-feature"
        spec_dir.mkdir(parents=True)
        _cc_write_validated(spec_dir)
        _write_mcp_test_results(spec_dir, ["s1", "s2"])  # pass==total==2
        head = _cc_seed_and_commit(repo_root)
        # Re-stamp results with the real HEAD now that the tree is committed.
        _write_mcp_test_results(spec_dir, ["s1", "s2"], validated_commit=head)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "exempt-and-tick", v
        assert v["pass_count"] == 2, v
        assert v["validated_commit"] == head, v




def test_eval_evidence_forged_attestation_results_missing_refuses():
    """VALIDATED.md present but MCP_TEST_RESULTS.md absent → refuse (forged)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _cc_seed_and_commit(repo_root)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_results_without_validated_refuses():
    """MCP_TEST_RESULTS.md present, VALIDATED.md absent → refuse (no VSA)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_mcp_test_results(spec_dir, ["s1"])
        head = _cc_seed_and_commit(repo_root)
        _write_mcp_test_results(spec_dir, ["s1"], validated_commit=head)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_skip_fail_closed_refuses():
    """SKIP_MCP_TEST.md present + no passing results → refuse, no tick."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_skip_mcp_test(spec_dir)
        _cc_seed_and_commit(repo_root)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_deferred_fail_closed_refuses():
    """DEFERRED_NON_CLOUD.md present + no passing results → refuse, no tick."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        (spec_dir / "DEFERRED_NON_CLOUD.md").write_text(
            "---\nkind: deferred-non-cloud\nfeature_id: cc-feature\n"
            "date: 2026-06-19\n---\n", encoding="utf-8",
        )
        _cc_seed_and_commit(repo_root)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_zero_test_refuses():
    """VALIDATED.md + results with pass==total==0 → refuse (CI false-positive)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        # zero scenarios → pass_count == total_count == 0.
        _write_mcp_test_results(spec_dir, [], pass_count=0, total_count=0)
        head = _cc_seed_and_commit(repo_root)
        _write_mcp_test_results(
            spec_dir, [], pass_count=0, total_count=0, validated_commit=head
        )
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_observation_gap_partial_promotes():
    """Gap 1 coupling: VALIDATED.md + a `result: partial` MCP_TEST_RESULTS.md whose
    MCP-driveable scope is fully passing (pass==total>0) AND whose remainder is
    fully covered by provenance-backed `observation_gap_exemptions` →
    exempt-and-tick (NOT refuse). Without this the scoped VALIDATED.md minted by
    __write_validated_from_results__ would still be re-refused at the completion
    gate, perpetuating the deadlock one layer deeper.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _write_mcp_test_results_with_exemptions(
            spec_dir, ["s1", "s2"],
            exemptions=[{
                "surface": "armStore drive-through",
                "spec_class": "observation-gap — unit/WDIO tier per "
                "docs/features/mcp-testing/SPEC.md",
            }],
            result="partial", pass_count=2, total_count=2,
        )
        head = _cc_seed_and_commit(repo_root)
        # Re-stamp with HEAD + exemptions so freshness passes.
        p = spec_dir / "MCP_TEST_RESULTS.md"
        p.write_text(
            p.read_text(encoding="utf-8").replace(
                "result: partial\n",
                f"validated_commit: \"{head}\"\nresult: partial\n",
            ),
            encoding="utf-8",
        )
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] in {"exempt-and-tick", "warn-exempt"}, v
        assert v["pass_count"] == 2, v




def test_eval_evidence_observation_gap_partial_with_failure_refuses():
    """REGRESSION GUARD for the completion gate: a `result: partial` whose
    pass_count < total_count (a genuine MCP-scope failure, NOT an observation gap)
    STILL refuses even when an exemptions block is present — the genuine-failure
    refusal is not weakened by the observation-gap coupling.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _write_mcp_test_results_with_exemptions(
            spec_dir, ["s1", "s2"],
            exemptions=[{
                "surface": "per-block visual state",
                "spec_class": "observation-gap — unit/WDIO tier per "
                "docs/features/mcp-testing/SPEC.md",
            }],
            result="partial", pass_count=1, total_count=2,  # genuine failure
        )
        _cc_seed_and_commit(repo_root)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_observation_gap_partial_no_provenance_refuses():
    """A `result: partial` whose exemptions lack `spec_class` provenance STILL
    refuses at the completion gate (provenance-required, mirroring the apply gate).
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        (spec_dir / "MCP_TEST_RESULTS.md").write_text(
            "---\nkind: mcp-test-results\nfeature_id: cc-feature\n"
            "scenarios:\n  - s1\ndate: 2026-06-30\nresult: partial\n"
            "pass_count: 1\ntotal_count: 1\n"
            "observation_gap_exemptions:\n  - surface: save-as-scene\n"
            "---\n\n# MCP Test Results\n",
            encoding="utf-8",
        )
        _cc_seed_and_commit(repo_root)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_observation_gap_promotable_shared_predicate():
    """The SHARED observation_gap_promotable helper — the SINGLE home for the
    scoped observation-gap partial rule now used by the apply gate, the
    completion-integrity gate, AND the Step-9 routing in lazy-state.py /
    bug-state.py. This is the regression that closes the Step-9 no-route deadlock
    (community-sharing: result partial, 10/10 MCP-driveable scope, 3 spec_class'd
    exemptions re-dispatched /mcp-test every cycle because the routing accepted
    ONLY result=='all-passing'). If any of the three sites drifts from this
    predicate the deadlock reopens — so the predicate itself is pinned here.
    """
    _guard()
    ogp = lazy_core.observation_gap_promotable

    # PROMOTES — the live community-sharing shape: partial + non-empty exemptions
    # each carrying a non-empty spec_class provenance.
    assert ogp(
        {
            "result": "partial",
            "observation_gap_exemptions": [
                {"surface": "import-share", "spec_class": "clipboard-io"},
                {"surface": "export-share", "spec_class": "clipboard-io"},
                {"surface": "share-link", "spec_class": "os-share-sheet"},
            ],
        }
    ) is True

    # all-passing is NOT a 'partial' — the helper is the partial-promotion
    # predicate only; the callers OR it with the all-passing literal.
    assert ogp({"result": "all-passing"}) is False

    # partial with NO exemptions key → not promotable.
    assert ogp({"result": "partial"}) is False

    # partial with an EMPTY exemptions list → not promotable.
    assert ogp({"result": "partial", "observation_gap_exemptions": []}) is False

    # partial with a provenance-LESS exemption (no spec_class) → not promotable
    # (the citation is what distinguishes a verified assessment from a skip).
    assert ogp(
        {
            "result": "partial",
            "observation_gap_exemptions": [{"surface": "import-share"}],
        }
    ) is False

    # partial with an empty/whitespace spec_class → not promotable.
    assert ogp(
        {
            "result": "partial",
            "observation_gap_exemptions": [
                {"surface": "s", "spec_class": "   "}
            ],
        }
    ) is False

    # partial with a non-dict exemption entry → not promotable.
    assert ogp(
        {"result": "partial", "observation_gap_exemptions": ["not-a-dict"]}
    ) is False

    # A genuine MCP-scope FAILURE still returns True HERE (the helper is HALF the
    # AND — the pass==total cross-check is the callers' responsibility). This
    # pins the contract: the helper does NOT read pass/total.
    assert ogp(
        {
            "result": "partial",
            "pass_count": 4,
            "total_count": 10,
            "observation_gap_exemptions": [{"surface": "s", "spec_class": "c"}],
        }
    ) is True


def test_observation_gap_promotable_admits_build_artifact_deferred_class():
    """Decision #13 (turn-routing-enforcement NEEDS_INPUT, harden Round 61):
    ``build-artifact-deferred`` is an ADMISSIBLE observation-gap ``spec_class``.

    The promotion predicate keys on a NON-EMPTY ``spec_class`` provenance STRING,
    not on a closed class vocabulary — so admitting ``build-artifact-deferred``
    (an assertion MCP-driveable only against a packaged production build, absent
    from a dev session, already covered by the Rust/unit tier and pre-classified
    in PHASES) needs NO gate code change; the mcp-test SKILL prose is what makes
    it reachable. This test LOCKS that contract: if a future change closes the
    ``spec_class`` vocabulary, it must keep ``build-artifact-deferred`` (and the
    "Cannot Prove" no-MCP-tool class) admissible or this regression fails.
    See docs/bugs/partial-mcp-results-all-exempt-rows-no-authorable-validated-path/.
    """
    _guard()
    ogp = lazy_core.observation_gap_promotable

    # The sidecar-integrity-gate-blocks-user-modified-sidecar shape: a partial
    # whose two uncovered rows are (row 1) a Tauri command with no registered
    # MCP-tool mirror ("Cannot Prove") and (row 2) build-artifact-deferred.
    assert ogp(
        {
            "result": "partial",
            "pass_count": 4,
            "total_count": 4,
            "observation_gap_exemptions": [
                {"surface": "sidecar-integrity-command",
                 "spec_class": "cannot-prove — no registered MCP-tool mirror per "
                               "docs/features/mcp-testing/SPEC.md"},
                {"surface": "sidecar-mismatch-branch",
                 "spec_class": "build-artifact-deferred — reachable only against a "
                               "packaged production build; Rust-covered, PHASES-classified"},
            ],
        }
    ) is True

    # An all-build-artifact-deferred partial promotes identically (the class is
    # admissible on its own, not only when paired with cannot-prove).
    assert ogp(
        {
            "result": "partial",
            "observation_gap_exemptions": [
                {"surface": "packaged-only-branch",
                 "spec_class": "build-artifact-deferred"},
            ],
        }
    ) is True


def test_eval_evidence_head_drift_docs_only_warn_exempt():
    """validated_commit != HEAD, drift is *.md only → warn-exempt."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _write_mcp_test_results(spec_dir, ["s1", "s2"])
        first = _cc_seed_and_commit(repo_root)
        # Second commit changes ONLY a markdown file.
        (repo_root / "NOTES.md").write_text("docs change\n", encoding="utf-8")
        second = _git_fixture_commit(repo_root)
        assert first != second
        # Results recorded the FIRST (validated) commit; HEAD is now the second.
        _write_mcp_test_results(spec_dir, ["s1", "s2"], validated_commit=first)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "warn-exempt", v
        assert v["pass_count"] == 2, v




def test_eval_evidence_head_drift_source_refuses():
    """validated_commit != HEAD, drift includes a .py file → refuse-and-revalidate."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _write_mcp_test_results(spec_dir, ["s1", "s2"])
        first = _cc_seed_and_commit(repo_root)
        # Second commit changes a SOURCE file.
        (repo_root / "mod.py").write_text("x = 1\n", encoding="utf-8")
        second = _git_fixture_commit(repo_root)
        assert first != second
        _write_mcp_test_results(spec_dir, ["s1", "s2"], validated_commit=first)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




def test_eval_evidence_neither_present_refuses():
    """Neither VALIDATED.md nor MCP_TEST_RESULTS.md → refuse (no evidence)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_seed_and_commit(repo_root)
        v = lazy_core.evaluate_completion_evidence(spec_dir, repo_root)
        assert v["verdict"] == "refuse", v




# ---------------------------------------------------------------------------
# evaluate_deferred_runtime_exemption + write_runtime_gates_ledger
#   (completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo).
# ---------------------------------------------------------------------------

def _write_structural_skip(spec_dir: Path) -> None:
    """A structural SKIP_MCP_TEST.md (granted_by: pipeline-structural)."""
    (spec_dir / "SKIP_MCP_TEST.md").write_text(
        "---\n"
        "kind: skip-mcp-test\n"
        "feature_id: cc-feature\n"
        "reason: repo has no MCP-reachable surface\n"
        "date: 2026-07-14\n"
        "skipped_by: pipeline\n"
        "granted_by: pipeline-structural\n"
        "spec_class: standalone — no app surface\n"
        "---\n\n# Skip (structural)\n",
        encoding="utf-8",
    )


def test_deferred_runtime_exemption_structural_skip_ok():
    """VALIDATED.md + a re-verified structural skip in a no-app-surface repo →
    ok: True (the honest deferred-runtime route is authorized)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)  # empty repo: no src-tauri/, no package.json
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _write_structural_skip(spec_dir)
        r = lazy_core.evaluate_deferred_runtime_exemption(spec_dir, repo_root)
        assert r["ok"] is True, r


def test_deferred_runtime_exemption_app_repo_refuses():
    """The KEY confinement: an APP repo (package.json present) makes the
    structural waiver re-verify False → ok: False. A verification-only row in an
    MCP repo still needs real MCP evidence — this route cannot fire there."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        (repo_root / "package.json").write_text("{}\n", encoding="utf-8")
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        _write_structural_skip(spec_dir)
        r = lazy_core.evaluate_deferred_runtime_exemption(spec_dir, repo_root)
        assert r["ok"] is False, r
        assert "re-verify" in r["reason"], r


def test_deferred_runtime_exemption_missing_validated_refuses():
    """Structural skip present but NO VALIDATED.md → ok: False (a bare skip
    without the attestation envelope cannot certify a deferral)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _write_structural_skip(spec_dir)
        r = lazy_core.evaluate_deferred_runtime_exemption(spec_dir, repo_root)
        assert r["ok"] is False and "VALIDATED.md" in r["reason"], r


def test_deferred_runtime_exemption_non_structural_skip_refuses():
    """A non-structural (operator) skip → ok: False — the deferred-runtime route
    is confined to a structural no-app-surface skip; other skips earn their rows
    the ordinary way."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        spec_dir = repo_root / "spec"
        spec_dir.mkdir()
        _cc_write_validated(spec_dir)
        (spec_dir / "SKIP_MCP_TEST.md").write_text(
            "---\nkind: skip-mcp-test\nfeature_id: cc-feature\nreason: x\n"
            "date: 2026-07-14\ngranted_by: operator\n---\n\n# Skip\n",
            encoding="utf-8",
        )
        r = lazy_core.evaluate_deferred_runtime_exemption(spec_dir, repo_root)
        assert r["ok"] is False and "pipeline-structural" in r["reason"], r


def test_write_runtime_gates_ledger_writes_and_bytestable():
    """The ledger writer emits RUNTIME_GATES.md (led by the PENDING line + the
    sole-owner declaration), one row per deferred gate, and is byte-stable on a
    re-run (regenerated, never appended). Empty rows → no file."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        fd = Path(td)
        rows = [
            {"phase": "### Phase 4: Validation", "lineno": 42,
             "text": "- [ ] <!-- verification-only --> cloud run deferred"},
        ]
        r1 = lazy_core.write_runtime_gates_ledger(fd, rows, date="2026-07-14")
        assert r1["written"] is True and r1["count"] == 1, r1
        led = fd / "RUNTIME_GATES.md"
        body = led.read_text(encoding="utf-8")
        assert "MANUAL RUNTIME GATES PENDING" in body, body
        assert "ONLY owner" in body, body
        assert "cloud run deferred" in body, body
        first = led.read_bytes()
        lazy_core.write_runtime_gates_ledger(fd, rows, date="2026-07-14")
        assert led.read_bytes() == first, "ledger must be byte-stable on re-run"
        # Empty rows → nothing written.
        fd2 = Path(td) / "empty"
        fd2.mkdir()
        r2 = lazy_core.write_runtime_gates_ledger(fd2, [], date="2026-07-14")
        assert r2["written"] is False, r2
        assert not (fd2 / "RUNTIME_GATES.md").exists()




# ---------------------------------------------------------------------------
# commit_drift_verdict — the SHARED docs-only carve-out helper (2026-06-23
# DEADLOCK fix, hardening-log Round 36). The Step-9 state-script gates, the
# __write_validated_from_results__ apply gate, and evaluate_completion_evidence
# all route through this ONE helper so they cannot diverge (the divergence that
# produced the infinite Step-9 re-verify loop). These pin the helper directly.
# ---------------------------------------------------------------------------

def test_commit_drift_verdict_equal_is_fresh():
    """validated_commit == head → 'fresh' WITHOUT running git diff."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _cc_seed_and_commit(repo_root)
        sha = lazy_core._current_head(repo_root)
        v = lazy_core.commit_drift_verdict(repo_root, sha, sha)
        assert v["verdict"] == "fresh", v




def test_commit_drift_verdict_none_or_blank_is_fresh():
    """A None / blank validated_commit or head → 'fresh' (legacy-permissive;
    the caller owns the missing-field / non-git path)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        assert lazy_core.commit_drift_verdict(repo_root, None, "abc")["verdict"] == "fresh"
        assert lazy_core.commit_drift_verdict(repo_root, "abc", None)["verdict"] == "fresh"
        assert lazy_core.commit_drift_verdict(repo_root, "", "abc")["verdict"] == "fresh"
        assert lazy_core.commit_drift_verdict(repo_root, "  ", "abc")["verdict"] == "fresh"




def test_commit_drift_verdict_docs_only():
    """validated_commit (A) != head (B), A→B drift is *.md only → 'docs-only'.

    This is the STRUCTURALLY-UNAVOIDABLE one-commit lag: the /mcp-test cycle
    commits its own MCP_TEST_RESULTS.md (a *.md), advancing HEAD one past the
    validated_commit it just recorded. Strict equality would deadlock here."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        first = _cc_seed_and_commit(repo_root)
        (repo_root / "NOTES.md").write_text("docs change\n", encoding="utf-8")
        second = _git_fixture_commit(repo_root)
        assert first != second
        v = lazy_core.commit_drift_verdict(repo_root, first, second)
        assert v["verdict"] == "docs-only", v
        assert v["non_docs"] == [], v




def test_commit_drift_verdict_non_docs_drift():
    """validated_commit (A) != head (B), A→B drift includes a .py → 'non-docs-
    drift' with the offending path listed (genuine TOCTOU — must re-verify)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        first = _cc_seed_and_commit(repo_root)
        (repo_root / "mod.py").write_text("x = 1\n", encoding="utf-8")
        second = _git_fixture_commit(repo_root)
        assert first != second
        v = lazy_core.commit_drift_verdict(repo_root, first, second)
        assert v["verdict"] == "non-docs-drift", v
        assert any(p.endswith("mod.py") for p in v["non_docs"]), v




def test_is_noninvalidating_drift_path_classes():
    """Unit-pin the structural predicate: *.md and mcp-test SCENARIO
    *.yaml/*.yml (under an mcp-test(s) segment) are non-invalidating; a
    product .yaml with no mcp-test segment, and a .py, are invalidating."""
    _guard()
    f = lazy_core._is_noninvalidating_drift_path
    # docs
    assert f("docs/features/x/MCP_TEST_RESULTS.md") is True
    assert f("docs/features/x/PHASES.md") is True
    # mcp-test scenario corpus (the harden-2026-07 addition)
    assert f("docs/testing/mcp-tests/corpus/live/managed-credits-client.yaml") is True
    assert f("docs/features/x/mcp-tests/scenario.yml") is True
    assert f("DOCS/TESTING/MCP-TESTS/S.YAML") is True          # case-insensitive
    assert f("docs\\testing\\mcp-tests\\s.yaml") is True        # backslash-normalized
    # NOT carved out — product yaml with no mcp-test segment
    assert f("config.yaml") is False
    assert f(".github/workflows/ci.yml") is False
    assert f("docs/testing/other/plain.yaml") is False
    # code-under-test always invalidating
    assert f("src/mod.py") is False




def test_commit_drift_verdict_mcp_scenario_yaml_is_docs_only():
    """harden 2026-07: a first-run results-commit that adds an mcp-test SCENARIO
    *.yaml under the mcp-tests corpus ALONGSIDE the *.md results is
    NON-INVALIDATING drift → 'docs-only'. RED against the pre-fix .md-only
    carve-out (the scenario .yaml made non_docs non-empty → 'non-docs-drift' →
    a wasted Step-9 re-verify cycle)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        first = _cc_seed_and_commit(repo_root)
        # Mirror the observed first-run commit: an .md results file + a scenario
        # .yaml under docs/testing/mcp-tests/corpus/live/.
        (repo_root / "MCP_TEST_RESULTS.md").write_text("results\n", encoding="utf-8")
        scen = repo_root / "docs" / "testing" / "mcp-tests" / "corpus" / "live"
        scen.mkdir(parents=True, exist_ok=True)
        (scen / "managed-credits-client.yaml").write_text(
            "name: scenario\n", encoding="utf-8"
        )
        second = _git_fixture_commit(repo_root)
        assert first != second
        v = lazy_core.commit_drift_verdict(repo_root, first, second)
        assert v["verdict"] == "docs-only", v
        assert v["non_docs"] == [], v




def test_commit_drift_verdict_non_mcp_yaml_still_non_docs():
    """A .yaml WITHOUT an mcp-test(s) path segment (a product config) still
    classifies as 'non-docs-drift' — the carve-out is scoped to the scenario
    corpus, so a genuine config change cannot launder a stale validation."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        first = _cc_seed_and_commit(repo_root)
        (repo_root / "app.config.yaml").write_text("k: v\n", encoding="utf-8")
        second = _git_fixture_commit(repo_root)
        assert first != second
        v = lazy_core.commit_drift_verdict(repo_root, first, second)
        assert v["verdict"] == "non-docs-drift", v
        assert any(p.endswith("app.config.yaml") for p in v["non_docs"]), v




def test_commit_drift_verdict_unresolvable():
    """An unknown validated_commit (not in the repo) → 'unresolvable' (the
    caller refuses conservatively — cannot prove docs-only)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        head = _cc_seed_and_commit(repo_root)
        v = lazy_core.commit_drift_verdict(repo_root, "0" * 40, head)
        assert v["verdict"] == "unresolvable", v




# ===========================================================================
# completion-coherence-gate-reconciliation — Phase 2
#   autotick_verification_rows — atomic, line-anchored, audited rewrite.
# ===========================================================================

_CC_PHASES_TWO_MARKERS = (
    "# Phases\n\n"
    "### Phase 1: Impl\n\n"
    "**Status:** Complete\n\n"
    "- [x] real implementation row done\n"
    "- [ ] still-open implementation row\n\n"
    "**Runtime Verification**\n\n"
    "- [ ] pytest suite green <!-- verification-only -->\n"
    "- [ ] parity audit clean <!-- verification-only -->\n\n"
    "```\n"
    "- [ ] fenced example box (must NOT be ticked)\n"
    "```\n"
)




def test_autotick_happy_path_ticks_only_marker_rows():
    """Two verification-marked rows + one fenced + one plain impl row: after
    autotick(pass_count=2) exactly the two marker rows are - [x] each carrying
    the audit comment; fenced + impl rows byte-unchanged; ticked_count == 2.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PHASES.md"
        p.write_text(_CC_PHASES_TWO_MARKERS, encoding="utf-8")
        sha = "deadbeefcafe"
        res = lazy_core.autotick_verification_rows(p, sha, 2)
        assert res["ok"] is True, res
        assert res["ticked_count"] == 2, res
        text = p.read_text(encoding="utf-8")
        assert text.count(f"<!-- auto-ticked: validated_commit={sha} -->") == 2, text
        assert "- [x] pytest suite green" in text, text
        assert "- [x] parity audit clean" in text, text
        assert "- [ ] fenced example box (must NOT be ticked)" in text, text
        assert "- [ ] still-open implementation row" in text, text




def test_autotick_variable_whitespace_marker_matched():
    """A '- [  ]' (two-space) marker row IS matched and ticked."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PHASES.md"
        p.write_text(
            "### Phase 1: X\n\n**Runtime Verification**\n\n"
            "- [  ] wide gap row <!-- verification-only -->\n",
            encoding="utf-8",
        )
        res = lazy_core.autotick_verification_rows(p, "abc123", 1)
        assert res["ok"] is True, res
        assert res["ticked_count"] == 1, res
        text = p.read_text(encoding="utf-8")
        assert "- [x] wide gap row" in text, text




def test_autotick_cardinality_abort_writes_nothing():
    """pass_count=1 against a 2-marker-row file → ok: False, file byte-unmodified."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PHASES.md"
        before = _CC_PHASES_TWO_MARKERS
        p.write_text(before, encoding="utf-8")
        res = lazy_core.autotick_verification_rows(p, "sha9", 1)
        assert res["ok"] is False, res
        assert p.read_text(encoding="utf-8") == before, "file was mutated on abort"




def test_autotick_superseded_phase_row_untouched():
    """An unchecked marker row under a Superseded phase is left alone + not counted."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PHASES.md"
        text = (
            "### Phase 1: Old\n\n**Status:** Superseded\n\n"
            "- [ ] superseded verification row <!-- verification-only -->\n\n"
            "### Phase 2: New\n\n**Status:** Complete\n\n"
            "**Runtime Verification**\n\n"
            "- [ ] active verification row <!-- verification-only -->\n"
        )
        p.write_text(text, encoding="utf-8")
        res = lazy_core.autotick_verification_rows(p, "shaS", 1)
        assert res["ok"] is True, res
        assert res["ticked_count"] == 1, res
        out = p.read_text(encoding="utf-8")
        assert "- [ ] superseded verification row" in out, out
        assert "- [x] active verification row" in out, out




def test_autotick_idempotent_rerun_no_double_comment():
    """Re-running over already-ticked rows: ticked_count == 0, no duplicate audit
    comment, rows unchanged.
    """
    _guard()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "PHASES.md"
        p.write_text(_CC_PHASES_TWO_MARKERS, encoding="utf-8")
        sha = "idem01"
        first = lazy_core.autotick_verification_rows(p, sha, 2)
        assert first["ticked_count"] == 2, first
        after_first = p.read_text(encoding="utf-8")
        second = lazy_core.autotick_verification_rows(p, sha, 2)
        assert second["ok"] is True, second
        assert second["ticked_count"] == 0, second
        after_second = p.read_text(encoding="utf-8")
        assert after_second == after_first, "idempotent re-run mutated the file"
        assert after_second.count(
            f"<!-- auto-ticked: validated_commit={sha} -->"
        ) == 2, "duplicate audit comment appeared"




def test_commit_subject_is_foreign_harden_classifies_and_fails_open():
    """_commit_subject_is_foreign_harden: True for a `harden(...)` subject,
    False for an item commit, and False (fail-open) for an unreadable sha."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        sha_harden = _prov_git_commit_file(
            repo_root, "user/hooks/h.sh", "harden(hook): tighten guard")
        sha_item = _prov_git_commit_file(
            repo_root, "src/x.py", "fix(feat-x): real work")
        assert lazy_core._commit_subject_is_foreign_harden(repo_root, sha_harden)
        assert not lazy_core._commit_subject_is_foreign_harden(repo_root, sha_item)
        # Bad sha → fail-open False (never drops a real item commit).
        assert not lazy_core._commit_subject_is_foreign_harden(
            repo_root, "deadbeefdeadbeef")




# ---------------------------------------------------------------------------
# plan-structure-authoring-gate Phase 4 — pickup backstop
# (lazy_core.plan_structural_backstop / format_plan_structural_blocker).
# In-process import of validate-plan.py's run_structural_checks (never a
# subprocess, never a rule-function hoist — see the STATE-lane seam docstring
# on plan_structural_backstop for why).
# ---------------------------------------------------------------------------

def test_plan_structural_backstop_clean_plan_ok():
    """A structurally clean, fresh (zero ticked WUs) plan passes."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        plan = Path(td) / "plans" / "all-phases-foo.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
            "phases: [1]\n---\n\n## Work Units\n- [ ] WU-1 — do the thing\n",
            encoding="utf-8",
        )
        result = lazy_core.plan_structural_backstop(plan)
    assert result["ok"] is True, result
    assert result["mid_execution"] is False, result




def test_plan_structural_backstop_fresh_invalid_plan_refuses():
    """A FRESH plan (zero ticked WUs) carrying a structural ERROR (an
    unfilled WU template-row placeholder) refuses (ok: False), naming the
    finding."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        plan = Path(td) / "plans" / "all-phases-foo.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
            "phases: [1]\n---\n\n## Work Units\n- [ ] WU-N — <short title>\n",
            encoding="utf-8",
        )
        result = lazy_core.plan_structural_backstop(plan)
    assert result["ok"] is False, result
    assert result["mid_execution"] is False, result
    assert result["findings"], "a refusal must carry findings text"
    assert any("template-row" in f for f in result["findings"]), result["findings"]




def test_plan_structural_backstop_mid_execution_warns_not_refuses():
    """The SAME structural ERROR on a plan with >= 1 ticked WU (mid-execution
    — already in flight) does NOT refuse (ok: True) — WARN-only, findings
    still surfaced for visibility."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        plan = Path(td) / "plans" / "all-phases-foo.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "---\nkind: implementation-plan\nfeature_id: foo\nstatus: In-progress\n"
            "phases: [1]\n---\n\n## Work Units\n"
            "- [x] WU-1 — did something real\n"
            "- [ ] WU-N — <short title>\n",
            encoding="utf-8",
        )
        result = lazy_core.plan_structural_backstop(plan)
    assert result["ok"] is True, (
        f"a mid-execution plan must WARN, never refuse; got {result}"
    )
    assert result["mid_execution"] is True, result
    assert any("template-row" in f for f in result["findings"]), (
        "findings must still surface for visibility even when WARN-only"
    )




def test_plan_structural_backstop_missing_file_fails_open():
    """A nonexistent plan path degrades to ok: True (fail-open — a backstop
    must never itself become a new failure surface)."""
    _guard()
    result = lazy_core.plan_structural_backstop(
        Path("/definitely/does/not/exist/plan.md"))
    assert result["ok"] is True, result
    assert result["findings"] == []




def test_plan_structural_backstop_infrastructure_failure_fresh_refuses_loudly():
    """A validate-plan.py LOADER crash (gate machinery broken — e.g. the
    module file deleted/unimportable) on a FRESH plan degrades to a LOUD
    infrastructure ERROR finding + refusal — NEVER the silent {'ok': True,
    'findings': []} that disarmed the gate repo-wide when the flat
    lazy_core.py was deleted (docs/bugs/plan-structural-backstop-silent-
    disarm-on-infrastructure-failure)."""
    _guard()
    import lazy_core.gates as _mono  # Phase-4 WU-1: _load_validate_plan_module lives in gates now

    def _boom():
        raise FileNotFoundError("validate-plan.py: gone")

    with tempfile.TemporaryDirectory() as td:
        plan = Path(td) / "plans" / "all-phases-foo.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "---\nkind: implementation-plan\nfeature_id: foo\nstatus: Ready\n"
            "phases: [1]\n---\n\n## Work Units\n- [ ] WU-1 — do the thing\n",
            encoding="utf-8",
        )
        real_loader = _mono._load_validate_plan_module
        _mono._load_validate_plan_module = _boom
        try:
            result = lazy_core.plan_structural_backstop(plan)
        finally:
            _mono._load_validate_plan_module = real_loader
    assert result["ok"] is False, (
        f"a machinery failure on a FRESH plan must refuse, not silently "
        f"pass; got {result}"
    )
    assert result.get("infrastructure_error") is True, result
    assert any("(infrastructure)" in f for f in result["findings"]), result




def test_plan_structural_backstop_infrastructure_failure_mid_execution_warns():
    """The SAME machinery failure on a MID-EXECUTION plan (>= 1 ticked WU)
    keeps the deliberate warns-not-refuses fail-open (ok: True) but is still
    LOUD — findings carry the infrastructure ERROR, never an empty list."""
    _guard()
    import lazy_core.gates as _mono  # Phase-4 WU-1: _load_validate_plan_module lives in gates now

    def _boom():
        raise ImportError("lazy_core flat file retired")

    with tempfile.TemporaryDirectory() as td:
        plan = Path(td) / "plans" / "all-phases-foo.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "---\nkind: implementation-plan\nfeature_id: foo\nstatus: In-progress\n"
            "phases: [1]\n---\n\n## Work Units\n"
            "- [x] WU-1 — did something real\n"
            "- [ ] WU-2 — still to do\n",
            encoding="utf-8",
        )
        real_loader = _mono._load_validate_plan_module
        _mono._load_validate_plan_module = _boom
        try:
            result = lazy_core.plan_structural_backstop(plan)
        finally:
            _mono._load_validate_plan_module = real_loader
    assert result["ok"] is True, (
        f"mid-execution keeps warns-not-refuses even for machinery failure; "
        f"got {result}"
    )
    assert result["mid_execution"] is True, result
    assert result.get("infrastructure_error") is True, result
    assert any("(infrastructure)" in f for f in result["findings"]), (
        f"machinery failure must be loud (findings non-empty); got {result}"
    )




def test_format_plan_structural_blocker_names_findings():
    """The BLOCKED.md body names the plan path, the findings, and the
    blocker_kind classification."""
    _guard()
    body = lazy_core.format_plan_structural_blocker(
        "/repo/plans/all-phases-foo.md",
        ["[ERROR] (wu-checklist) missing WU checklist"],
    )
    assert "/repo/plans/all-phases-foo.md" in body
    assert "wu-checklist" in body
    assert "blocker_kind: plan-structural-invalid" in body




def test_gate_verdict_ok_no_manifest_out_of_scope():
    """No docs/gate/control-surfaces.json at all -> {ok: True, in_scope:
    False} unconditionally (every repo without the manifest is unaffected,
    including claude-config itself pre-D1/post-redirect)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        spec_dir = _prov_spec_dir(repo_root, "feat-nogate")
        _prov_git_commit_file(repo_root, "src/x.py", "work on feat-nogate")
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result == {"ok": True, "in_scope": False, "reason": "no control-surface manifest"}




def test_gate_verdict_ok_manifest_present_but_change_out_of_scope():
    """Manifest present, but the item's commits touch no matching glob ->
    in_scope: False, ok: True (no GATE_VERDICT.md needed)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-unscoped")
        _prov_git_commit_file(repo_root, "src/unrelated.py", "fix(feat-unscoped): work")
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result["ok"] is True and result["in_scope"] is False, result




def test_gate_verdict_ok_scoped_missing_verdict_refuses():
    """Manifest present + item touches a scoped path + no GATE_VERDICT.md ->
    refuses, naming the missing file."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-missingverdict")
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-missingverdict): work")
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result["ok"] is False and result["in_scope"] is True, result
    assert "GATE_VERDICT.md" in result["reason"]




def test_gate_verdict_ok_scoped_clean_verdict_ok():
    """A scoped item with a clean (all-pass) GATE_VERDICT.md completes."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-cleanverdict")
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-cleanverdict): work")
        _gate_write_verdict(spec_dir, {"overfit": "pass", "gate_weakening": "pass"})
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result == {"ok": True, "in_scope": True, "reason": "gate verdict clean"}




def test_gate_verdict_ok_failing_check_refuses():
    """A GATE_VERDICT.md with any `fail` check refuses, naming it."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-failcheck")
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-failcheck): work")
        _gate_write_verdict(spec_dir, {"overfit": "fail", "gate_weakening": "pass"})
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result["ok"] is False and result["in_scope"] is True, result
    assert "overfit" in result["reason"]




def test_gate_verdict_ok_unsigned_gate_weakening_refuses():
    """A `gate_weakening: hit-signed` check with NO `override:` field refuses
    (D4 — the sign-off round is mandatory)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-unsigned")
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-unsigned): work")
        _gate_write_verdict(spec_dir, {"gate_weakening": "hit-signed"})
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result["ok"] is False and result["in_scope"] is True, result
    assert "override" in result["reason"]




def test_gate_verdict_ok_signed_gate_weakening_ok():
    """The SAME hit-signed gate_weakening WITH an `override:` field completes
    (the D4 operator sign-off round)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-signed")
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-signed): work")
        _gate_write_verdict(
            spec_dir, {"gate_weakening": "hit-signed"},
            override="operator-approved 2026-07-12 — reviewed and accepted",
        )
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result["ok"] is True, result




def test_gate_verdict_ok_malformed_verdict_refuses_not_crashes():
    """A GATE_VERDICT.md with unparseable frontmatter (parse_sentinel's
    _die() path) refuses gracefully rather than crashing the ship seam."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        repo_root = Path(td)
        _prov_git_fixture_repo(repo_root)
        _gate_write_manifest(repo_root, ["scoped/**"])
        spec_dir = _prov_spec_dir(repo_root, "feat-malformed")
        _prov_git_commit_file(
            repo_root, "scoped/thing.py", "fix(feat-malformed): work")
        (spec_dir / "GATE_VERDICT.md").write_text(
            "---\nkind: gate-verdict\nchecks: [this is not a mapping\n---\n",
            encoding="utf-8",
        )
        result = lazy_core.gate_verdict_ok(spec_dir, repo_root)
    assert result["ok"] is False and result["in_scope"] is True, result




def test_no_duplicate_top_level_defs_in_state_scripts():
    """Self-checking meta-test: every lazy_core/ package module, lazy-state.py,
    and bug-state.py each carry ZERO duplicate top-level def/class names (the
    `_current_head` defect this bug found and fixed — one definition silently
    shadowed the other, undetected because this repo has no F811/pyflakes-class
    lint gate at all). GREEN today. FAILS — naming the file + duplicate names —
    if a future edit reintroduces a shadowed top-level definition.

    Checked PER MODULE (lazy-core-package-decomposition WU-1): lazy_core.py was
    split into the lazy_core/ package (12 seam submodules + lazy_core/__init__.py
    + any future submodules). A same-named def/class in TWO DIFFERENT modules is
    legal (module scoping); the F811 class this guard pins is a duplicate WITHIN
    one module.
    """
    _guard()
    scripts_dir = Path(__file__).resolve().parents[2]
    lazy_core_dir = scripts_dir / "lazy_core"
    module_paths = sorted(lazy_core_dir.glob("*.py"))
    for filename in ("lazy-state.py", "bug-state.py"):
        module_paths.append(scripts_dir / filename)
    for path in module_paths:
        source = path.read_text(encoding="utf-8")
        dups = _collect_duplicate_top_level_defs(source)
        assert dups == [], f"{path.name}: duplicate top-level definitions: {dups}"


# ---------------------------------------------------------------------------
# uncovered_verification_rows_remain — the shared Step-10 re-route predicate
# (decision-2-6-uncovered-row-reroute-to-mcp-test WU-2)
# ---------------------------------------------------------------------------

_TWO_RV_ROWS_PHASES = (
    "# Phases\n\n"
    "### Phase 1\n\n"
    "**Status:** In-progress\n\n"
    "**Deliverables:**\n\n"
    "- [x] implement the thing\n\n"
    "**Runtime Verification** <!-- verification-only -->\n\n"
    "- [ ] <!-- verification-only --> scenario A passes\n"
    "- [ ] <!-- verification-only --> scenario B passes\n"
)


def test_uncovered_rows_partial_evidence_reroutes_true():
    """≥2 verification rows, evidence covers only 1 (subset all-passing) →
    autotick's cardinality lock would abort, leaving both uncovered →
    reroute is True and both rows are listed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        _cc_write_validated(spec_dir)
        _write_mcp_test_results(
            spec_dir, ["scenario-a"], result="all-passing",
            pass_count=1, total_count=1,
        )
        res = lazy_core.uncovered_verification_rows_remain(
            spec_dir, _TWO_RV_ROWS_PHASES, spec_dir,
        )
        assert res["reroute"] is True, res
        assert len(res["uncovered"]) == 2, res


def test_uncovered_rows_full_evidence_terminates():
    """All verification rows covered (pass_count >= row count) → autotick
    would tick them all → reroute is False (TERMINATION)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        _cc_write_validated(spec_dir)
        _write_mcp_test_results(
            spec_dir, ["a", "b"], result="all-passing",
            pass_count=2, total_count=2,
        )
        res = lazy_core.uncovered_verification_rows_remain(
            spec_dir, _TWO_RV_ROWS_PHASES, spec_dir,
        )
        assert res["reroute"] is False, res
        assert res["uncovered"] == [], res


def test_uncovered_host_deferred_row_excluded_terminates():
    """The only uncovered verification row carries `<!-- requires-host: <cap> -->`
    → excluded from the re-route (clause b — a host-deferred row can never pass
    here) → reroute is False (would otherwise loop /mcp-test forever)."""
    _guard()
    phases = (
        "# Phases\n\n### Phase 1\n\n**Status:** In-progress\n\n"
        "- [x] implement\n\n"
        "**Runtime Verification** <!-- verification-only -->\n\n"
        "- [ ] <!-- verification-only --> <!-- requires-host: real-audio-device --> "
        "sustained-timing on a real device\n"
    )
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        _cc_write_validated(spec_dir)
        # No MCP_TEST_RESULTS.md → evaluate_completion_evidence refuses →
        # pass_count coerced to 0 → the single row is uncovered but host-deferred.
        res = lazy_core.uncovered_verification_rows_remain(
            spec_dir, phases, spec_dir,
        )
        assert res["reroute"] is False, res
        assert res["uncovered"] == [], res


def test_uncovered_observation_gap_partial_excluded_terminates():
    """A sanctioned observation-gap partial (result: partial + every exemption
    carries a spec_class) exempts its scope wholesale → reroute is False even
    with an uncovered verification row present (clause a)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        _cc_write_validated(spec_dir)
        _write_mcp_test_results_with_exemptions(
            spec_dir, ["a"],
            exemptions=[{"surface": "ui-only", "spec_class": "unit-tier-locked"}],
            result="partial", pass_count=1, total_count=1,
        )
        res = lazy_core.uncovered_verification_rows_remain(
            spec_dir, _TWO_RV_ROWS_PHASES, spec_dir,
        )
        assert res["reroute"] is False, res


def test_uncovered_superseded_and_descoped_rows_terminate():
    """Unchecked verification rows that live only inside a Superseded phase or
    under a `<!-- descoped -->` header are not-to-be-done → collected as zero
    candidates → reroute is False."""
    _guard()
    phases = (
        "# Phases\n\n"
        "### Phase 1\n\n**Status:** Superseded\n\n"
        "**Runtime Verification** <!-- verification-only -->\n\n"
        "- [ ] <!-- verification-only --> superseded RV row\n\n"
        "### Phase 2\n\n**Status:** In-progress\n\n"
        "**Dropped work** <!-- descoped -->\n\n"
        "- [ ] <!-- verification-only --> descoped RV row\n"
    )
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)
        _cc_write_validated(spec_dir)
        res = lazy_core.uncovered_verification_rows_remain(
            spec_dir, phases, spec_dir,
        )
        assert res["reroute"] is False, res
        assert res["uncovered"] == [], res


def test_uncovered_predicate_is_evidence_driven_not_validated_gated():
    """CALLER PRECONDITION (documentation test): "no VALIDATED.md" is the
    Step-10 ENTRY gate's concern, NOT this predicate's. The predicate reasons
    purely over PHASES + recorded MCP evidence — with no VALIDATED.md AND no
    passing results, an uncovered matrix still yields reroute True (evidence,
    not VALIDATED presence, drives it). It always returns the three keys and
    never raises."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        spec_dir = Path(td)  # deliberately NO VALIDATED.md, NO results
        res = lazy_core.uncovered_verification_rows_remain(
            spec_dir, _TWO_RV_ROWS_PHASES, spec_dir,
        )
        assert set(res.keys()) >= {"reroute", "uncovered", "reason"}, res
        assert res["reroute"] is True, res


_TESTS = [
    ("test_uncovered_rows_partial_evidence_reroutes_true", test_uncovered_rows_partial_evidence_reroutes_true),
    ("test_uncovered_rows_full_evidence_terminates", test_uncovered_rows_full_evidence_terminates),
    ("test_uncovered_host_deferred_row_excluded_terminates", test_uncovered_host_deferred_row_excluded_terminates),
    ("test_uncovered_observation_gap_partial_excluded_terminates", test_uncovered_observation_gap_partial_excluded_terminates),
    ("test_uncovered_superseded_and_descoped_rows_terminate", test_uncovered_superseded_and_descoped_rows_terminate),
    ("test_uncovered_predicate_is_evidence_driven_not_validated_gated", test_uncovered_predicate_is_evidence_driven_not_validated_gated),
    ("test_verify_ledger_spec_md_file_arg_normalizes_to_parent_dir", test_verify_ledger_spec_md_file_arg_normalizes_to_parent_dir),
    ("test_verify_ledger_all_green_passes", test_verify_ledger_all_green_passes),
    ("test_verify_ledger_dirty_tree_fails", test_verify_ledger_dirty_tree_fails),
    ("test_verify_ledger_behind_origin_fails", test_verify_ledger_behind_origin_fails),
    ("test_verify_ledger_plan_not_complete_fails", test_verify_ledger_plan_not_complete_fails),
    ("test_verify_ledger_unchecked_nonverification_deliverable_fails", test_verify_ledger_unchecked_nonverification_deliverable_fails),
    ("test_verify_ledger_unchecked_verification_only_passes", test_verify_ledger_unchecked_verification_only_passes),
    ("test_verify_ledger_feature_level_fails_when_part2_pending", test_verify_ledger_feature_level_fails_when_part2_pending),
    ("test_verify_ledger_plan_scoped_part1_passes", test_verify_ledger_plan_scoped_part1_passes),
    ("test_verify_ledger_plan_scoped_part2_pending_fails", test_verify_ledger_plan_scoped_part2_pending_fails),
    ("test_verify_ledger_plan_scoped_catches_unflipped_status", test_verify_ledger_plan_scoped_catches_unflipped_status),
    ("test_verify_ledger_plan_scoped_catches_in_scope_unchecked_wu", test_verify_ledger_plan_scoped_catches_in_scope_unchecked_wu),
    ("test_verify_ledger_plan_scoped_verification_only_in_scope_passes", test_verify_ledger_plan_scoped_verification_only_in_scope_passes),
    ("test_verify_ledger_plan_scoped_empty_phases_falls_back_to_feature_level", test_verify_ledger_plan_scoped_empty_phases_falls_back_to_feature_level),
    ("test_verify_ledger_plan_scoped_missing_plan_file_fails", test_verify_ledger_plan_scoped_missing_plan_file_fails),
    ("test_verify_ledger_plan_wu_phase_spans_two_parts_no_false_fail", test_verify_ledger_plan_wu_phase_spans_two_parts_no_false_fail),
    ("test_verify_ledger_plan_wu_cross_phase_attribution_ignored", test_verify_ledger_plan_wu_cross_phase_attribution_ignored),
    ("test_verify_ledger_plan_wu_unchecked_fails", test_verify_ledger_plan_wu_unchecked_fails),
    ("test_verify_ledger_plan_wu_verification_only_exempt", test_verify_ledger_plan_wu_verification_only_exempt),
    ("test_verify_ledger_legacy_plan_no_wu_checkboxes_falls_back", test_verify_ledger_legacy_plan_no_wu_checkboxes_falls_back),
    ("test_verify_ledger_legacy_plan_fallback_passes_when_phases_done", test_verify_ledger_legacy_plan_fallback_passes_when_phases_done),
    ("test_verify_ledger_feature_level_reports_source", test_verify_ledger_feature_level_reports_source),
    ("test_verify_ledger_plan_less_feature_absent_by_design_passes", test_verify_ledger_plan_less_feature_absent_by_design_passes),
    ("test_verify_ledger_realign_only_feature_absent_by_design_passes", test_verify_ledger_realign_only_feature_absent_by_design_passes),
    ("test_verify_ledger_incomplete_plan_still_fails_regression_guard", test_verify_ledger_incomplete_plan_still_fails_regression_guard),
    ("test_verify_ledger_failing_detail_empty_when_ok", test_verify_ledger_failing_detail_empty_when_ok),
    ("test_verify_ledger_failing_detail_clean_tree_names_dirty_files", test_verify_ledger_failing_detail_clean_tree_names_dirty_files),
    ("test_verify_ledger_failing_detail_head_matches_origin_ahead_behind", test_verify_ledger_failing_detail_head_matches_origin_ahead_behind),
    ("test_verify_ledger_failing_detail_no_upstream_configured", test_verify_ledger_failing_detail_no_upstream_configured),
    ("test_verify_ledger_failing_detail_plan_complete_feature_level", test_verify_ledger_failing_detail_plan_complete_feature_level),
    ("test_verify_ledger_failing_detail_plan_complete_scoped", test_verify_ledger_failing_detail_plan_complete_scoped),
    ("test_verify_ledger_failing_detail_deliverables_done_feature_level", test_verify_ledger_failing_detail_deliverables_done_feature_level),
    ("test_verify_ledger_failing_detail_deliverables_done_plan_wu", test_verify_ledger_failing_detail_deliverables_done_plan_wu),
    ("test_summarize_failing_detail_clean_tree", test_summarize_failing_detail_clean_tree),
    ("test_summarize_failing_detail_head_no_upstream", test_summarize_failing_detail_head_no_upstream),
    ("test_summarize_failing_detail_head_ahead_behind", test_summarize_failing_detail_head_ahead_behind),
    ("test_summarize_failing_detail_deliverables_done", test_summarize_failing_detail_deliverables_done),
    ("test_summarize_failing_detail_ok_is_empty_string", test_summarize_failing_detail_ok_is_empty_string),
    ("test_summarize_failing_detail_malformed_never_raises", test_summarize_failing_detail_malformed_never_raises),
    ("test_lazy_state_retro_stale_only_corrective_routes_past_step8", test_lazy_state_retro_stale_only_corrective_routes_past_step8),
    ("test_planner_resolution_resolves_via_internal_repos_when_passed_repos_empty", test_planner_resolution_resolves_via_internal_repos_when_passed_repos_empty),
    ("test_gate_coverage_symbol_present", test_gate_coverage_symbol_present),
    ("test_gate_coverage_covered_and_uncovered_verdict", test_gate_coverage_covered_and_uncovered_verdict),
    ("test_gate_coverage_resolves_symlink_pointer_file", test_gate_coverage_resolves_symlink_pointer_file),
    ("test_gate_coverage_resolves_pointer_file_unconditionally", test_gate_coverage_resolves_pointer_file_unconditionally),
    ("test_gate_coverage_no_locked_decisions_passes_vacuously", test_gate_coverage_no_locked_decisions_passes_vacuously),
    ("test_gate_coverage_empty_mcp_tests_all_uncovered", test_gate_coverage_empty_mcp_tests_all_uncovered),
    ("test_gate_coverage_skips_hash_decision_table_header", test_gate_coverage_skips_hash_decision_table_header),
    ("test_parse_mcp_coverage_exemptions_requires_rationale", test_parse_mcp_coverage_exemptions_requires_rationale),
    ("test_gate_coverage_honors_spec_exemption", test_gate_coverage_honors_spec_exemption),
    ("test_eval_evidence_exempt_and_tick_happy_path", test_eval_evidence_exempt_and_tick_happy_path),
    ("test_eval_evidence_forged_attestation_results_missing_refuses", test_eval_evidence_forged_attestation_results_missing_refuses),
    ("test_eval_evidence_results_without_validated_refuses", test_eval_evidence_results_without_validated_refuses),
    ("test_eval_evidence_skip_fail_closed_refuses", test_eval_evidence_skip_fail_closed_refuses),
    ("test_eval_evidence_deferred_fail_closed_refuses", test_eval_evidence_deferred_fail_closed_refuses),
    ("test_eval_evidence_zero_test_refuses", test_eval_evidence_zero_test_refuses),
    ("test_eval_evidence_observation_gap_partial_promotes", test_eval_evidence_observation_gap_partial_promotes),
    ("test_eval_evidence_observation_gap_partial_with_failure_refuses", test_eval_evidence_observation_gap_partial_with_failure_refuses),
    ("test_eval_evidence_observation_gap_partial_no_provenance_refuses", test_eval_evidence_observation_gap_partial_no_provenance_refuses),
    ("test_observation_gap_promotable_shared_predicate", test_observation_gap_promotable_shared_predicate),
    ("test_observation_gap_promotable_admits_build_artifact_deferred_class", test_observation_gap_promotable_admits_build_artifact_deferred_class),
    ("test_eval_evidence_head_drift_docs_only_warn_exempt", test_eval_evidence_head_drift_docs_only_warn_exempt),
    ("test_eval_evidence_head_drift_source_refuses", test_eval_evidence_head_drift_source_refuses),
    ("test_eval_evidence_neither_present_refuses", test_eval_evidence_neither_present_refuses),
    ("test_deferred_runtime_exemption_structural_skip_ok", test_deferred_runtime_exemption_structural_skip_ok),
    ("test_deferred_runtime_exemption_app_repo_refuses", test_deferred_runtime_exemption_app_repo_refuses),
    ("test_deferred_runtime_exemption_missing_validated_refuses", test_deferred_runtime_exemption_missing_validated_refuses),
    ("test_deferred_runtime_exemption_non_structural_skip_refuses", test_deferred_runtime_exemption_non_structural_skip_refuses),
    ("test_write_runtime_gates_ledger_writes_and_bytestable", test_write_runtime_gates_ledger_writes_and_bytestable),
    ("test_commit_drift_verdict_equal_is_fresh", test_commit_drift_verdict_equal_is_fresh),
    ("test_commit_drift_verdict_none_or_blank_is_fresh", test_commit_drift_verdict_none_or_blank_is_fresh),
    ("test_commit_drift_verdict_docs_only", test_commit_drift_verdict_docs_only),
    ("test_commit_drift_verdict_non_docs_drift", test_commit_drift_verdict_non_docs_drift),
    ("test_is_noninvalidating_drift_path_classes", test_is_noninvalidating_drift_path_classes),
    ("test_commit_drift_verdict_mcp_scenario_yaml_is_docs_only", test_commit_drift_verdict_mcp_scenario_yaml_is_docs_only),
    ("test_commit_drift_verdict_non_mcp_yaml_still_non_docs", test_commit_drift_verdict_non_mcp_yaml_still_non_docs),
    ("test_commit_drift_verdict_unresolvable", test_commit_drift_verdict_unresolvable),
    ("test_autotick_happy_path_ticks_only_marker_rows", test_autotick_happy_path_ticks_only_marker_rows),
    ("test_autotick_variable_whitespace_marker_matched", test_autotick_variable_whitespace_marker_matched),
    ("test_autotick_cardinality_abort_writes_nothing", test_autotick_cardinality_abort_writes_nothing),
    ("test_autotick_superseded_phase_row_untouched", test_autotick_superseded_phase_row_untouched),
    ("test_autotick_idempotent_rerun_no_double_comment", test_autotick_idempotent_rerun_no_double_comment),
    ("test_commit_subject_is_foreign_harden_classifies_and_fails_open", test_commit_subject_is_foreign_harden_classifies_and_fails_open),
    ("test_plan_structural_backstop_clean_plan_ok", test_plan_structural_backstop_clean_plan_ok),
    ("test_plan_structural_backstop_fresh_invalid_plan_refuses", test_plan_structural_backstop_fresh_invalid_plan_refuses),
    ("test_plan_structural_backstop_mid_execution_warns_not_refuses", test_plan_structural_backstop_mid_execution_warns_not_refuses),
    ("test_plan_structural_backstop_missing_file_fails_open", test_plan_structural_backstop_missing_file_fails_open),
    ("test_plan_structural_backstop_infrastructure_failure_fresh_refuses_loudly", test_plan_structural_backstop_infrastructure_failure_fresh_refuses_loudly),
    ("test_plan_structural_backstop_infrastructure_failure_mid_execution_warns", test_plan_structural_backstop_infrastructure_failure_mid_execution_warns),
    ("test_format_plan_structural_blocker_names_findings", test_format_plan_structural_blocker_names_findings),
    ("test_gate_verdict_ok_no_manifest_out_of_scope", test_gate_verdict_ok_no_manifest_out_of_scope),
    ("test_gate_verdict_ok_manifest_present_but_change_out_of_scope", test_gate_verdict_ok_manifest_present_but_change_out_of_scope),
    ("test_gate_verdict_ok_scoped_missing_verdict_refuses", test_gate_verdict_ok_scoped_missing_verdict_refuses),
    ("test_gate_verdict_ok_scoped_clean_verdict_ok", test_gate_verdict_ok_scoped_clean_verdict_ok),
    ("test_gate_verdict_ok_failing_check_refuses", test_gate_verdict_ok_failing_check_refuses),
    ("test_gate_verdict_ok_unsigned_gate_weakening_refuses", test_gate_verdict_ok_unsigned_gate_weakening_refuses),
    ("test_gate_verdict_ok_signed_gate_weakening_ok", test_gate_verdict_ok_signed_gate_weakening_ok),
    ("test_gate_verdict_ok_malformed_verdict_refuses_not_crashes", test_gate_verdict_ok_malformed_verdict_refuses_not_crashes),
    ("test_no_duplicate_top_level_defs_in_state_scripts", test_no_duplicate_top_level_defs_in_state_scripts),
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
