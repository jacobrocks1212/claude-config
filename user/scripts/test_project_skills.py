#!/usr/bin/env python3
"""
test_project_skills.py - Tests for project-skills.py

Tests are written against the public API of project-skills.py and are
expected to FAIL until the implementation is written.
"""

import importlib.util
import sys
import pytest
from pathlib import Path


def load_module():
    """Load project-skills.py as a module (hyphen-safe import)."""
    spec = importlib.util.spec_from_file_location(
        "project_skills",
        Path(__file__).parent / "project-skills.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ps():
    """Return the project_skills module."""
    return load_module()


# ---------------------------------------------------------------------------
# resolve_cat_line
# ---------------------------------------------------------------------------

def test_simple_cat_reference_expanded(tmp_path, ps):
    """A !`cat ~/.claude/skills/_components/foo.md` line is replaced with
    foo.md's content wrapped in BEGIN/END comment markers."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)
    (components_dir / "foo.md").write_text("# Foo content\nHello from foo.\n")

    line = "!`cat ~/.claude/skills/_components/foo.md`"
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=tmp_path)

    assert "<!-- BEGIN component: foo.md -->" in result
    assert "Hello from foo." in result
    assert "<!-- END component: foo.md -->" in result
    # Original !cat line must not survive
    assert "!`cat" not in result


def test_nested_cat_resolution(tmp_path, ps):
    """Component A that includes component B is fully resolved recursively."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)

    (components_dir / "b.md").write_text("# B content\nDeep value.\n")
    (components_dir / "a.md").write_text(
        "# A content\n"
        "!`cat ~/.claude/skills/_components/b.md`\n"
        "End of A.\n"
    )

    line = "!`cat ~/.claude/skills/_components/a.md`"
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=tmp_path)

    assert "<!-- BEGIN component: a.md -->" in result
    assert "<!-- BEGIN component: b.md -->" in result
    assert "Deep value." in result
    assert "<!-- END component: b.md -->" in result
    assert "<!-- END component: a.md -->" in result


def test_fallback_cat_resolves_first_path(tmp_path, ps):
    """Fallback pattern resolves to the first (project) path when it exists."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)

    project_dir = tmp_path / "project"
    skill_config = project_dir / ".claude" / "skill-config"
    skill_config.mkdir(parents=True)

    (skill_config / "quality-gates.md").write_text("Project quality gates.\n")
    (components_dir / "quality-gates.md").write_text("Default quality gates.\n")

    line = (
        "!`cat .claude/skill-config/quality-gates.md 2>/dev/null"
        " || cat ~/.claude/skills/_components/quality-gates.md`"
    )
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=project_dir)

    assert "Project quality gates." in result
    assert "Default quality gates." not in result


def test_fallback_cat_resolves_second_path(tmp_path, ps):
    """Fallback pattern falls back to the second path when the first is absent."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    (components_dir / "quality-gates.md").write_text("Default quality gates.\n")

    line = (
        "!`cat .claude/skill-config/quality-gates.md 2>/dev/null"
        " || cat ~/.claude/skills/_components/quality-gates.md`"
    )
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=project_dir)

    assert "Default quality gates." in result


def test_echo_fallback_when_file_missing(tmp_path, ps):
    """Echo fallback returns the echo string when the file doesn't exist."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    line = (
        '!`cat .claude/skill-config/quality-gates.md 2>/dev/null'
        ' || echo "- All tests must pass"`'
    )
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=project_dir)

    assert "- All tests must pass" in result
    assert "!`cat" not in result


def test_echo_fallback_skipped_when_file_exists(tmp_path, ps):
    """Echo fallback is NOT used when the file exists; file content wins."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    project_dir = tmp_path / "project"
    skill_config = project_dir / ".claude" / "skill-config"
    skill_config.mkdir(parents=True)
    (skill_config / "quality-gates.md").write_text("Real gates content.\n")

    line = (
        '!`cat .claude/skill-config/quality-gates.md 2>/dev/null'
        ' || echo "- All tests must pass"`'
    )
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=project_dir)

    assert "Real gates content." in result
    assert "All tests must pass" not in result


def test_circular_include_detected(tmp_path, ps):
    """A circular include chain (A → B → A) must not loop infinitely and
    must raise an error or return a safe sentinel string."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)

    (components_dir / "a.md").write_text(
        "A start\n!`cat ~/.claude/skills/_components/b.md`\nA end\n"
    )
    (components_dir / "b.md").write_text(
        "B start\n!`cat ~/.claude/skills/_components/a.md`\nB end\n"
    )

    line = "!`cat ~/.claude/skills/_components/a.md`"

    # Should not raise RecursionError or loop forever; either raises a
    # domain error or returns content that flags the cycle.
    try:
        result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=tmp_path)
        assert "circular" in result.lower() or "cycle" in result.lower(), (
            "Expected circular-include indicator in output"
        )
    except Exception as exc:
        assert "circular" in str(exc).lower() or "cycle" in str(exc).lower(), (
            f"Expected circular-include error, got: {exc}"
        )


def test_non_cat_lines_unchanged(tmp_path, ps):
    """Regular markdown lines pass through resolve_cat_line unmodified."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    regular_lines = [
        "## A heading",
        "Some plain text.",
        "- bullet point",
        "```python\ncode block\n```",
        "",
    ]
    for line in regular_lines:
        result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=project_dir)
        assert result == line, f"Expected line unchanged, got: {result!r}"


# ---------------------------------------------------------------------------
# resolve_skill_file
# ---------------------------------------------------------------------------

def test_frontmatter_preserved(tmp_path, ps):
    """YAML frontmatter between --- delimiters survives resolve_skill_file unchanged."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)
    (components_dir / "comp.md").write_text("Component text.\n")

    skill_dir = skills_dir / "my-skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "name: my-skill\n"
        "version: 1\n"
        "---\n"
        "Body text.\n"
        "!`cat ~/.claude/skills/_components/comp.md`\n"
    )

    result = ps.resolve_skill_file(skill_file, skills_dir=skills_dir, project_dir=tmp_path)

    assert "---\nname: my-skill\nversion: 1\n---" in result
    assert "Body text." in result
    assert "Component text." in result


# ---------------------------------------------------------------------------
# project_skills (main entry point)
# ---------------------------------------------------------------------------

def test_output_directory_structure(tmp_path, ps):
    """Output mirrors source structure: output/<skill-name>/SKILL.md per skill dir."""
    skills_dir = tmp_path / "skills"
    for name in ("alpha", "beta"):
        d = skills_dir / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\nContent.\n")

    output_dir = tmp_path / "output"
    ps.project_skills(
        skills_dir=skills_dir,
        output_dir=output_dir,
        project_dir=tmp_path,
    )

    assert (output_dir / "alpha" / "SKILL.md").exists()
    assert (output_dir / "beta" / "SKILL.md").exists()


def test_components_excluded_from_output(tmp_path, ps):
    """_components/ directory is NOT written as a skill in the output."""
    skills_dir = tmp_path / "skills"
    comp_dir = skills_dir / "_components"
    comp_dir.mkdir(parents=True)
    (comp_dir / "shared.md").write_text("Shared component.\n")

    real_skill = skills_dir / "real-skill"
    real_skill.mkdir()
    (real_skill / "SKILL.md").write_text("# Real\nContent.\n")

    output_dir = tmp_path / "output"
    ps.project_skills(
        skills_dir=skills_dir,
        output_dir=output_dir,
        project_dir=tmp_path,
    )

    assert not (output_dir / "_components").exists()
    assert (output_dir / "real-skill" / "SKILL.md").exists()


def test_project_skills_summary(tmp_path, ps):
    """project_skills() returns a summary dict with expected keys and counts."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)
    (components_dir / "comp.md").write_text("Component.\n")

    for name in ("skill-one", "skill-two"):
        d = skills_dir / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"# {name}\n!`cat ~/.claude/skills/_components/comp.md`\n"
        )

    output_dir = tmp_path / "output"
    summary = ps.project_skills(
        skills_dir=skills_dir,
        output_dir=output_dir,
        project_dir=tmp_path,
    )

    assert isinstance(summary, dict)
    assert "skills_projected" in summary
    assert "components_resolved" in summary
    assert "errors" in summary
    assert summary["skills_projected"] == 2
    assert summary["components_resolved"] >= 2  # one comp resolved per skill
    assert isinstance(summary["errors"], list)
    assert len(summary["errors"]) == 0


# ---------------------------------------------------------------------------
# project_all (repo-specific projection)
# ---------------------------------------------------------------------------

def test_repo_discovery_finds_skill_config_dirs(tmp_path, ps):
    """project_all() discovers only repos that have .claude/skill-config/."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# My Skill\nContent.\n")

    repos_dir = tmp_path / "repos"
    for repo in ("repo-a", "repo-b", "repo-c"):
        (repos_dir / repo).mkdir(parents=True)

    # repo-a and repo-c get .claude/skill-config/ with a file
    for repo in ("repo-a", "repo-c"):
        sc = repos_dir / repo / ".claude" / "skill-config"
        sc.mkdir(parents=True)
        (sc / "quality-gates.md").write_text(f"Gates for {repo}.\n")

    output_dir = tmp_path / "output"
    summary = ps.project_all(
        skills_dir=skills_dir,
        output_dir=output_dir,
        repos_dir=repos_dir,
    )

    assert summary["repos_discovered"] == 2
    assert "repo-a" in summary["repos"]
    assert "repo-c" in summary["repos"]
    assert "repo-b" not in summary["repos"]


def test_per_repo_projection_uses_overrides(tmp_path, ps):
    """_default/ uses the component default; per-repo dir uses repo override."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)
    (components_dir / "quality-gates.md").write_text("Default quality gates.\n")

    skill_dir = skills_dir / "gated-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# Gated Skill\n"
        "!`cat .claude/skill-config/quality-gates.md 2>/dev/null"
        " || cat ~/.claude/skills/_components/quality-gates.md`\n"
    )

    repos_dir = tmp_path / "repos"
    sc = repos_dir / "my-repo" / ".claude" / "skill-config"
    sc.mkdir(parents=True)
    (sc / "quality-gates.md").write_text("Repo-specific gates.\n")

    output_dir = tmp_path / "output"
    ps.project_all(
        skills_dir=skills_dir,
        output_dir=output_dir,
        repos_dir=repos_dir,
    )

    default_content = (output_dir / "_default" / "gated-skill" / "SKILL.md").read_text()
    repo_content = (output_dir / "my-repo" / "gated-skill" / "SKILL.md").read_text()

    assert "Default quality gates." in default_content
    assert "Repo-specific gates." not in default_content

    assert "Repo-specific gates." in repo_content
    assert "Default quality gates." not in repo_content


def test_default_output_always_produced(tmp_path, ps):
    """_default/ is produced even when no repos have .claude/skill-config/."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "plain-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Plain\nNo cat lines.\n")

    repos_dir = tmp_path / "repos"
    (repos_dir / "bare-repo").mkdir(parents=True)  # no .claude/skill-config/

    output_dir = tmp_path / "output"
    summary = ps.project_all(
        skills_dir=skills_dir,
        output_dir=output_dir,
        repos_dir=repos_dir,
    )

    assert (output_dir / "_default" / "plain-skill" / "SKILL.md").exists()
    assert summary["repos"] == {}
    assert summary["repos_discovered"] == 0


def test_repos_without_overrides_skipped(tmp_path, ps):
    """No per-repo output directories are created when repos lack .claude/skill-config/."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "some-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Some Skill\n")

    repos_dir = tmp_path / "repos"
    for repo in ("no-config-a", "no-config-b"):
        (repos_dir / repo).mkdir(parents=True)

    output_dir = tmp_path / "output"
    ps.project_all(
        skills_dir=skills_dir,
        output_dir=output_dir,
        repos_dir=repos_dir,
    )

    output_children = {p.name for p in output_dir.iterdir() if p.is_dir()}
    assert output_children == {"_default"}


def test_project_all_output_structure(tmp_path, ps):
    """project_all() writes _default/<skill>/SKILL.md and <repo>/<skill>/SKILL.md."""
    skills_dir = tmp_path / "skills"
    for name in ("alpha", "beta"):
        d = skills_dir / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\nContent.\n")

    repos_dir = tmp_path / "repos"
    sc = repos_dir / "test-repo" / ".claude" / "skill-config"
    sc.mkdir(parents=True)
    (sc / "dummy.md").write_text("Dummy.\n")

    output_dir = tmp_path / "output"
    ps.project_all(
        skills_dir=skills_dir,
        output_dir=output_dir,
        repos_dir=repos_dir,
    )

    assert (output_dir / "_default" / "alpha" / "SKILL.md").exists()
    assert (output_dir / "_default" / "beta" / "SKILL.md").exists()
    assert (output_dir / "test-repo" / "alpha" / "SKILL.md").exists()
    assert (output_dir / "test-repo" / "beta" / "SKILL.md").exists()


def test_project_all_summary_structure(tmp_path, ps):
    """project_all() returns a dict with 'default', 'repos', and 'repos_discovered'."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "check-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Check\nContent.\n")

    repos_dir = tmp_path / "repos"
    sc = repos_dir / "summary-repo" / ".claude" / "skill-config"
    sc.mkdir(parents=True)
    (sc / "gates.md").write_text("Gates.\n")

    output_dir = tmp_path / "output"
    summary = ps.project_all(
        skills_dir=skills_dir,
        output_dir=output_dir,
        repos_dir=repos_dir,
    )

    assert "default" in summary
    assert "repos" in summary
    assert "repos_discovered" in summary

    for key in ("skills_projected", "components_resolved", "errors"):
        assert key in summary["default"], f"'default' missing key '{key}'"

    for repo_name, repo_summary in summary["repos"].items():
        for key in ("skills_projected", "components_resolved", "errors"):
            assert key in repo_summary, f"repo '{repo_name}' summary missing key '{key}'"


def test_fallback_cat_recurses_into_override(tmp_path, ps):
    """When a project-override file exists and itself contains a nested !cat include,
    the nested include must be recursively expanded (not left as a raw directive)."""
    skills_dir = tmp_path / "skills"
    components_dir = skills_dir / "_components"
    components_dir.mkdir(parents=True)
    (components_dir / "shared-core.md").write_text(
        "SHARED_CORE_BODY_SENTINEL\n"
    )

    project_dir = tmp_path / "project"
    skill_config = project_dir / ".claude" / "skill-config"
    skill_config.mkdir(parents=True)
    (skill_config / "wrapper.md").write_text(
        "WRAPPER_SENTINEL\n"
        "!`cat ~/.claude/skills/_components/shared-core.md`\n"
        "End of wrapper.\n"
    )

    line = (
        "!`cat .claude/skill-config/wrapper.md 2>/dev/null"
        " || cat ~/.claude/skills/_components/wrapper.md`"
    )
    result = ps.resolve_cat_line(line, skills_dir=skills_dir, project_dir=project_dir)

    assert "WRAPPER_SENTINEL" in result
    assert "SHARED_CORE_BODY_SENTINEL" in result
    assert "<!-- BEGIN component: shared-core.md -->" in result
    assert "!`cat" not in result
