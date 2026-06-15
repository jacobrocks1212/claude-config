#!/usr/bin/env python3
"""
test_lint_skills.py - Tests for lint-skills.py

Covers lint_projected() false-positive and genuine-directive detection,
and the --check-parity integration via audit_all_pairs().
"""

import importlib.util
import pytest
from pathlib import Path


def load_module():
    """Load lint-skills.py as a module (hyphen-safe import)."""
    spec = importlib.util.spec_from_file_location(
        "lint_skills",
        Path(__file__).parent / "lint-skills.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ls():
    """Return the lint_skills module."""
    return load_module()


# ---------------------------------------------------------------------------
# lint_projected
# ---------------------------------------------------------------------------

def test_lint_projected_ignores_prose_mention(tmp_path, ls):
    """lint_projected() must NOT flag prose that merely mentions !cat as text.

    A line like:
        then `!cat`s this file (prose mention, not a directive).
    is documentation, not a runtime directive, and should produce no issues.

    NOTE: This test is expected to FAIL before the fix — the crude `"!cat" in
    line` check produces a false positive on this prose.
    """
    projected_dir = tmp_path / "projected"
    skill_dir = projected_dir / "some-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Some Skill\n"
        "This is a normal line.\n"
        "then `!cat`s this file (prose mention, not a directive).\n"
    )

    issues = ls.lint_projected(projected_dir)

    assert issues == [], (
        f"Expected no issues for prose mention, but got: {issues}"
    )


def test_lint_projected_flags_genuine_directive(tmp_path, ls):
    """lint_projected() must flag a genuine unexpanded !`cat ...` directive.

    A line like:
        !`cat ~/.claude/skills/_components/foo.md`
    is a runtime directive that the projection script failed to expand and
    must be reported as kind='unexpanded-cat'.

    This test should pass both before and after the fix.
    """
    projected_dir = tmp_path / "projected"
    skill_dir = projected_dir / "some-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Some Skill\n"
        "!`cat ~/.claude/skills/_components/foo.md`\n"
    )

    issues = ls.lint_projected(projected_dir)

    assert len(issues) == 1, (
        f"Expected exactly one issue for genuine directive, but got: {issues}"
    )
    assert issues[0]["kind"] == "unexpanded-cat", (
        f"Expected kind='unexpanded-cat', got: {issues[0]['kind']!r}"
    )


# ---------------------------------------------------------------------------
# --check-parity integration
# ---------------------------------------------------------------------------

def test_check_parity_clean_repo():
    """audit_all_pairs() returns zero findings on the clean repo.

    This mirrors what --check-parity does: calls lazy_parity_audit.audit_all_pairs
    with the repo root (parents[2] of this file's location) and asserts no drift.
    """
    import importlib
    import sys as _sys

    # Ensure user/scripts is on sys.path so the sibling import resolves.
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in _sys.path:
        _sys.path.insert(0, scripts_dir)

    lazy_parity_audit = importlib.import_module("lazy_parity_audit")

    # user/scripts/test_lint_skills.py -> parents[0]=user/scripts, [1]=user, [2]=repo root
    repo_root = Path(__file__).resolve().parents[2]

    findings = lazy_parity_audit.audit_all_pairs(repo_root)

    assert findings == [], (
        f"Expected zero lazy-parity findings on a clean repo, but got:\n"
        + "\n".join(findings)
    )
