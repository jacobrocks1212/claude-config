#!/usr/bin/env python3
"""
test_cli_surface_lint.py — Tests for cli-surface-lint.py (state-cli-contract-
registry Phase 2 / D2-A): the prose/fence lint of `--flag` mentions against
the committed CLI-surface registry.

Covers the Validation Criteria table:
  - Stale skill prose goes red: a fixture documenting a nonexistent flag
    (incl. the `lazy_parity_audit.py --report` Gotcha-shaped case) is an
    ERROR naming file:line + nearest flag.
  - Attribution-rule false-positive control: a bare `--flag` with no roster
    script on the same sentence is ignored; a sentence mentioning MORE THAN
    ONE roster script is ambiguous and ignored.
  - The exemption marker (`<!-- cli-surface: historical -->`) suppresses a
    finding on its line.
  - A live self-check that the REAL registry + real scan surface parse
    without malformed-input errors (smoke, not a zero-findings assertion —
    the real tree currently carries known findings the dispatching agent's
    scope excludes fixing, see docs/features/state-cli-contract-registry).

Run with: python -m pytest user/scripts/test_cli_surface_lint.py -q
Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent


def _load_module():
    """Import the dash-named module via importlib (not a valid identifier)."""
    path = _SCRIPTS_DIR / "cli-surface-lint.py"
    spec = importlib.util.spec_from_file_location("cli_surface_lint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


csl = _load_module()


_FIXTURE_REGISTRY = {
    "schema_version": 1,
    "generated_by": "cli_surface_gen.py",
    "scripts": {
        "surface_resolver.py": {
            "flags": [
                {"name": "--repo-root", "aliases": [], "action": "_StoreAction",
                 "nargs": None, "required": True, "choices": None, "metavar": "ROOT",
                 "help_head": None, "group": None, "positional": False, "default_kind": "none"},
                {"name": "--lint", "aliases": [], "action": "_StoreTrueAction",
                 "nargs": 0, "required": False, "choices": None, "metavar": None,
                 "help_head": None, "group": None, "positional": False, "default_kind": "const"},
            ]
        },
        "lazy_parity_audit.py": {
            "flags": [
                {"name": "--repo-root", "aliases": [], "action": "_StoreAction",
                 "nargs": None, "required": True, "choices": None, "metavar": None,
                 "help_head": None, "group": None, "positional": False, "default_kind": "none"},
                {"name": "--pair", "aliases": [], "action": "_StoreAction",
                 "nargs": None, "required": False, "choices": None, "metavar": None,
                 "help_head": None, "group": None, "positional": False, "default_kind": "value"},
            ]
        },
        "lazy-state.py": {
            "flags": [
                {"name": "--cloud", "aliases": [], "action": "_StoreTrueAction",
                 "nargs": 0, "required": False, "choices": None, "metavar": None,
                 "help_head": None, "group": None, "positional": False, "default_kind": "const"},
            ]
        },
        "bug-state.py": {
            "flags": [
                {"name": "--cloud", "aliases": [], "action": "_StoreTrueAction",
                 "nargs": 0, "required": False, "choices": None, "metavar": None,
                 "help_head": None, "group": None, "positional": False, "default_kind": "const"},
            ]
        },
    },
}


def _pattern():
    return csl._roster_pattern(list(_FIXTURE_REGISTRY["scripts"].keys()))


def _lint(text: str):
    return csl.lint_text("fixture.md", text, _FIXTURE_REGISTRY, _pattern())


# ---------------------------------------------------------------------------
# Stale-flag detection
# ---------------------------------------------------------------------------

def test_stale_flag_in_prose_is_flagged():
    text = "See `surface_resolver.py --route-mcp-test-tier` for details.\n"
    findings = _lint(text)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.script == "surface_resolver.py"
    assert finding.flag == "--route-mcp-test-tier"
    assert finding.nearest == "--repo-root"
    assert finding.line_no == 1
    rendered = finding.render()
    assert "surface_resolver.py has no flag --route-mcp-test-tier" in rendered
    assert "nearest: --repo-root" in rendered


def test_gotcha_shaped_report_mention_is_flagged():
    """Regression fixture modeled on the real user/scripts/CLAUDE.md Gotcha
    block (SPEC D2 worked example): a same-clause `lazy_parity_audit.py
    --report` mention must be caught."""
    text = 'Gotcha: `lazy_parity_audit.py --report` fails with "unrecognized arguments".\n'
    findings = _lint(text)
    assert len(findings) == 1
    assert findings[0].script == "lazy_parity_audit.py"
    assert findings[0].flag == "--report"


def test_known_flag_is_not_flagged():
    text = "Run `surface_resolver.py --lint --repo-root .` to check.\n"
    findings = _lint(text)
    assert findings == []


# ---------------------------------------------------------------------------
# Attribution rule — false-positive control
# ---------------------------------------------------------------------------

def test_bare_flag_with_no_roster_script_is_ignored():
    text = "Pass `--some-random-flag` to the tool.\n"
    findings = _lint(text)
    assert findings == []


def test_ambiguous_multi_script_sentence_is_ignored():
    text = "Both lazy-state.py and bug-state.py accept --nonexistent-flag here.\n"
    findings = _lint(text)
    assert findings == []


def test_flag_checked_against_the_one_script_named_in_its_unit():
    """--pair belongs to lazy_parity_audit.py's surface, not lazy-state.py's.
    When lazy-state.py is the ONLY roster script named in this sentence,
    the attribution rule (by design) checks --pair against lazy-state.py's
    registry entry — which lacks it — and correctly flags it. The rule is
    "whichever script is named nearby", not "whichever script really owns
    the flag" (that's unknowable from prose alone)."""
    text = "lazy-state.py workflow note (unrelated to --pair).\n"
    findings = _lint(text)
    assert len(findings) == 1
    assert findings[0].script == "lazy-state.py"
    assert findings[0].flag == "--pair"


# ---------------------------------------------------------------------------
# Exemption marker
# ---------------------------------------------------------------------------

def test_exemption_marker_suppresses_finding():
    text = ("`surface_resolver.py --route-mcp-test-tier` no longer exists. "
            "<!-- cli-surface: historical -->\n")
    findings = _lint(text)
    assert findings == []


def test_exemption_marker_only_suppresses_its_own_line():
    text = (
        "`surface_resolver.py --route-mcp-test-tier` no longer exists. "
        "<!-- cli-surface: historical -->\n"
        "`surface_resolver.py --another-fake-flag` still broken.\n"
    )
    findings = _lint(text)
    assert len(findings) == 1
    assert findings[0].flag == "--another-fake-flag"
    assert findings[0].line_no == 2


# ---------------------------------------------------------------------------
# Sentence-boundary attribution grain (dense multi-clause lines)
# ---------------------------------------------------------------------------

def test_sentence_split_scopes_attribution_within_one_line():
    """A single markdown line packing two clauses about two DIFFERENT
    scripts must not cross-attribute a flag from one clause to the other
    script's registry entry."""
    text = ("The tool takes --unrelated-thing for other purposes; "
            "it then shells `lazy-state.py --cloud` internally.\n")
    findings = _lint(text)
    # --unrelated-thing has no roster script in ITS clause -> ignored;
    # --cloud IS a real lazy-state.py flag -> no finding either.
    assert findings == []


def test_multiline_shell_continuation_joins_into_one_unit():
    text = (
        "```\n"
        "python3 lazy-state.py \\\n"
        "  --nonexistent-continuation-flag\n"
        "```\n"
    )
    findings = _lint(text)
    assert len(findings) == 1
    assert findings[0].flag == "--nonexistent-continuation-flag"
    assert findings[0].line_no == 2


# ---------------------------------------------------------------------------
# lint_repo integration — hermetic fixture tree
# ---------------------------------------------------------------------------

def test_lint_repo_hermetic_fixture(tmp_path):
    (tmp_path / "docs" / "cli").mkdir(parents=True)
    (tmp_path / "docs" / "cli" / "cli-surface.json").write_text(
        json.dumps(_FIXTURE_REGISTRY), encoding="utf-8"
    )
    skills_dir = tmp_path / "user" / "skills" / "demo"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "Invoke `surface_resolver.py --route-mcp-test-tier` here.\n", encoding="utf-8"
    )
    findings = csl.lint_repo(tmp_path)
    assert len(findings) == 1
    assert findings[0].path == "user/skills/demo/SKILL.md"


def test_lint_repo_scans_components_and_scripts_claude_md(tmp_path):
    (tmp_path / "docs" / "cli").mkdir(parents=True)
    (tmp_path / "docs" / "cli" / "cli-surface.json").write_text(
        json.dumps(_FIXTURE_REGISTRY), encoding="utf-8"
    )
    comp_dir = tmp_path / "user" / "skills" / "_components"
    comp_dir.mkdir(parents=True)
    (comp_dir / "foo.md").write_text(
        "`bug-state.py --totally-fake` mentioned here.\n", encoding="utf-8"
    )
    scripts_dir = tmp_path / "user" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "CLAUDE.md").write_text(
        "`lazy-state.py --also-fake` documented.\n", encoding="utf-8"
    )
    findings = csl.lint_repo(tmp_path)
    flagged = {(f.path, f.flag) for f in findings}
    assert ("user/skills/_components/foo.md", "--totally-fake") in flagged
    assert ("user/scripts/CLAUDE.md", "--also-fake") in flagged


def test_main_exit_codes(tmp_path, capsys):
    # Missing registry -> exit 2.
    assert csl.main(["--repo-root", str(tmp_path)]) == 2

    (tmp_path / "docs" / "cli").mkdir(parents=True)
    (tmp_path / "docs" / "cli" / "cli-surface.json").write_text(
        json.dumps(_FIXTURE_REGISTRY), encoding="utf-8"
    )
    # No skills/components present -> clean -> exit 0.
    assert csl.main(["--repo-root", str(tmp_path)]) == 0

    skills_dir = tmp_path / "user" / "skills" / "demo"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "`surface_resolver.py --route-mcp-test-tier` here.\n", encoding="utf-8"
    )
    assert csl.main(["--repo-root", str(tmp_path)]) == 1


# ---------------------------------------------------------------------------
# Live smoke over the real repo (parses cleanly; not a zero-findings gate)
# ---------------------------------------------------------------------------

def test_real_repo_lints_without_malformed_input():
    findings = csl.lint_repo(_REPO_ROOT)
    assert isinstance(findings, list)
    for finding in findings:
        assert finding.path
        assert finding.line_no > 0
        assert finding.flag.startswith("--")
