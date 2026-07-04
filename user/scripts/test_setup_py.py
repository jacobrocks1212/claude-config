"""Tests for the repo-root setup.py — cross-platform port of setup.ps1.

Feature: docs/features/cross-platform-setup/ (SPEC D1-D6).

Hermetic: every filesystem test runs against a temp HOME / temp repo fixture —
never the session's real ~/.claude. The Windows link-selection branch is covered
with a mocked platform (it is exercised for real on Windows only).
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_PY = REPO_ROOT / "setup.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("cps_setup", SETUP_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


setup_mod = _load_setup_module()


# ---------------------------------------------------------------------------
# Phase 1 — psd1 parser
# ---------------------------------------------------------------------------


class TestParsePsd1Grammar:
    def test_flat_hashtable_single_quoted_values(self):
        d = setup_mod.parse_psd1("@{ Name = 'value'; Other = 'x' }")
        assert d == {"Name": "value", "Other": "x"}

    def test_nested_hashtables_and_arrays(self):
        text = """
        @{
            User = @(
                @{ Live = '~\\.claude\\skills'; Repo = 'user\\skills'; Type = 'Directory' }
                @{ Live = '~\\.claude\\CLAUDE.md'; Repo = 'user\\CLAUDE.md'; Type = 'File' }
            )
            Repos = @{
                'my-repo' = @{
                    Path = 'C:\\src\\my-repo'
                    DotClaudeDirs = @('skills')
                }
            }
        }
        """
        d = setup_mod.parse_psd1(text)
        assert len(d["User"]) == 2
        assert d["User"][0]["Type"] == "Directory"
        assert d["Repos"]["my-repo"]["Path"] == "C:\\src\\my-repo"
        assert d["Repos"]["my-repo"]["DotClaudeDirs"] == ["skills"]

    def test_array_comma_and_newline_mix(self):
        text = """
        @{
            Files = @(
                'a.md', 'b.md',
                'c.md'
                'd.md'
            )
        }
        """
        d = setup_mod.parse_psd1(text)
        assert d["Files"] == ["a.md", "b.md", "c.md", "d.md"]

    def test_empty_array_and_empty_hashtable(self):
        d = setup_mod.parse_psd1("@{ A = @(); B = @{} }")
        assert d == {"A": [], "B": {}}

    def test_single_quote_escape(self):
        d = setup_mod.parse_psd1("@{ Msg = 'it''s linked' }")
        assert d["Msg"] == "it's linked"

    def test_double_quoted_string_without_interpolation(self):
        d = setup_mod.parse_psd1('@{ Msg = "plain text" }')
        assert d["Msg"] == "plain text"

    def test_comments_full_line_and_trailing(self):
        text = """
        @{
            # a full-line comment
            Name = 'v'  # a trailing comment
        }
        """
        d = setup_mod.parse_psd1(text)
        assert d == {"Name": "v"}

    def test_hash_inside_string_is_not_a_comment(self):
        d = setup_mod.parse_psd1("@{ Name = 'value # not comment' }")
        assert d["Name"] == "value # not comment"

    def test_quoted_keys(self):
        d = setup_mod.parse_psd1("@{ 'cognito-forms-B' = @{ Alias = 'cognito-forms' } }")
        assert d["cognito-forms-B"]["Alias"] == "cognito-forms"


class TestParsePsd1Dies:
    def _die_line(self, text):
        with pytest.raises(setup_mod.SetupError) as exc:
            setup_mod.parse_psd1(text)
        return str(exc.value)

    def test_dies_on_variable(self):
        msg = self._die_line("@{\n Name = $env:HOME\n}")
        assert "line 2" in msg

    def test_dies_on_here_string(self):
        msg = self._die_line("@{\n Doc = @'\nstuff\n'@\n}")
        assert "line 2" in msg

    def test_dies_on_expression(self):
        msg = self._die_line("@{\n N = (1+2)\n}")
        assert "line 2" in msg

    def test_dies_on_unterminated_string(self):
        msg = self._die_line("@{\n Name = 'oops\n}")
        assert "line 2" in msg

    def test_dies_on_interpolating_double_quote(self):
        msg = self._die_line('@{\n Name = "has $var inside"\n}')
        assert "line 2" in msg

    def test_dies_on_bare_word_value(self):
        # psd1 allows unquoted numbers/booleans; this manifest never uses them —
        # the parser refuses rather than guessing.
        msg = self._die_line("@{\n N = 42\n}")
        assert "line 2" in msg

    def test_dies_on_garbage_after_document(self):
        msg = self._die_line("@{ A = 'x' } %%%")
        assert "line 1" in msg


@pytest.fixture(scope="module")
def manifest():
    return setup_mod.parse_psd1((REPO_ROOT / "manifest.psd1").read_text())


class TestParsePsd1RealManifest:
    """The REAL manifest.psd1 is a pinned fixture (SPEC D1)."""

    def test_four_scopes_present(self, manifest):
        assert set(manifest) == {"User", "Personal", "Workspace", "Repos"}

    def test_user_section_shape(self, manifest):
        user = manifest["User"]
        assert len(user) == 11
        types = [e["Type"] for e in user]
        assert types.count("Directory") == 6
        assert types.count("File") == 5
        assert user[0]["Live"] == "~\\.claude\\skills"
        assert user[0]["Repo"] == "user\\skills"

    def test_personal_and_workspace(self, manifest):
        assert manifest["Personal"][0]["Repo"] == "personal\\CLAUDE.md"
        assert manifest["Workspace"][0]["Live"] == "~\\source\\repos\\CLAUDE.md"

    def test_cognito_alias_chain(self, manifest):
        repos = manifest["Repos"]
        for name in ("cognito-forms-B", "cognito-forms-C", "cognito-forms-D"):
            assert repos[name]["Alias"] == "cognito-forms"
            assert "RootFiles" not in repos[name]

    def test_nested_rootfiles_subpaths(self, manifest):
        rf = manifest["Repos"]["cognito-forms"]["RootFiles"]
        assert "Cognito.Web.Client\\apps\\spa\\CLAUDE.local.md" in rf
        assert manifest["Repos"]["cognito-forms"]["DotClaudeDirs"] == [
            "skill-config", "skills", "knowledge"]

    def test_cognito_docs_optional_keys_absent(self, manifest):
        cd = manifest["Repos"]["cognito-docs"]
        assert cd["DotClaudeFiles"] == ["settings.local.json"]
        assert "RootFiles" not in cd
        assert "DotClaudeDirs" not in cd


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"] + sys.argv[1:]))
