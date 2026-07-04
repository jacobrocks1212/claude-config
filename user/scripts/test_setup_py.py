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


# ---------------------------------------------------------------------------
# Phase 2 — mapping expansion
# ---------------------------------------------------------------------------


def _fixture_manifest(repos_path_base):
    """A miniature manifest exercising every expansion feature."""
    return {
        "User": [
            {"Live": "~\\.claude\\skills", "Repo": "user\\skills", "Type": "Directory"},
            {"Live": "~\\.claude\\CLAUDE.md", "Repo": "user\\CLAUDE.md", "Type": "File"},
        ],
        "Personal": [
            {"Live": "~\\.claude-personal\\CLAUDE.md", "Repo": "personal\\CLAUDE.md",
             "Type": "File"},
        ],
        "Workspace": [
            {"Live": "~\\source\\repos\\CLAUDE.md", "Repo": "workspace\\CLAUDE.md",
             "Type": "File"},
        ],
        "Repos": {
            "my-repo": {
                "Path": f"{repos_path_base}\\My Repo",
                "RootFiles": ["CLAUDE.local.md", "sub\\CLAUDE.local.md"],
                "DotClaudeFiles": ["settings.json", "hooks\\h.ps1"],
                "DotClaudeDirs": ["skills"],
            },
            "my-repo-B": {
                "Path": f"{repos_path_base}\\My Repo-B",
                "Alias": "my-repo",
            },
            "minimal": {
                "Path": f"{repos_path_base}\\minimal",
                "DotClaudeFiles": ["settings.local.json"],
            },
        },
    }


class TestExpandLivePath:
    def test_tilde_expands_to_home(self, tmp_path):
        out = setup_mod.expand_live_path("~\\.claude\\skills", home=str(tmp_path))
        assert out == os.path.join(str(tmp_path), ".claude", "skills")

    def test_no_tilde_passes_through_normalized(self, tmp_path):
        out = setup_mod.expand_live_path("C:\\src\\repo\\file.md", home=str(tmp_path))
        assert "\\" not in out or os.sep == "\\"


class TestExpandMappings:
    @pytest.fixture()
    def env(self, tmp_path):
        home = tmp_path / "home"
        repo_root = tmp_path / "claude-config"
        repos_root = tmp_path / "repos"
        for d in (home, repo_root, repos_root):
            d.mkdir()
        # my-repo + my-repo-B present on disk; 'minimal' left absent
        (repos_root / "My Repo").mkdir()
        (repos_root / "My Repo-B").mkdir()
        manifest = _fixture_manifest("C:\\Users\\x\\source\\repos")
        return manifest, str(repo_root), str(repos_root), str(home)

    def test_user_scope(self, env):
        manifest, repo_root, repos_root, home = env
        maps = setup_mod.expand_mappings(manifest, repo_root, target="User", home=home)
        assert len(maps) == 2
        m = maps[0]
        assert m.section == "User"
        assert m.live == os.path.join(home, ".claude", "skills")
        assert m.repo == os.path.join(repo_root, "user", "skills")
        assert m.type == "Directory"
        assert not m.skip_absent

    def test_target_filter_and_all(self, env):
        manifest, repo_root, repos_root, home = env
        for target, count in (("Personal", 1), ("Workspace", 1)):
            maps = setup_mod.expand_mappings(manifest, repo_root, target=target, home=home)
            assert len(maps) == 1 and maps[0].section == target, target
        all_maps = setup_mod.expand_mappings(
            manifest, repo_root, target="All", repos_root=repos_root, home=home)
        # 2 User + 1 Personal + 1 Workspace + my-repo(5) + my-repo-B(5) + minimal(1)
        assert len(all_maps) == 15

    def test_repos_root_remap_and_kinds(self, env):
        manifest, repo_root, repos_root, home = env
        maps = setup_mod.expand_mappings(
            manifest, repo_root, target="Repos", repos_root=repos_root, home=home)
        mine = [m for m in maps if m.section == "Repo:my-repo"]
        assert len(mine) == 5
        by_live_tail = {os.path.relpath(m.live, os.path.join(repos_root, "My Repo")): m
                        for m in mine}
        assert by_live_tail["CLAUDE.local.md"].type == "File"
        assert by_live_tail[os.path.join("sub", "CLAUDE.local.md")].repo == os.path.join(
            repo_root, "repos", "my-repo", "sub", "CLAUDE.local.md")
        assert by_live_tail[os.path.join(".claude", "hooks", "h.ps1")].type == "File"
        assert by_live_tail[os.path.join(".claude", "skills")].type == "Directory"

    def test_alias_repo_resolves_source_config_own_live_base(self, env):
        manifest, repo_root, repos_root, home = env
        maps = setup_mod.expand_mappings(
            manifest, repo_root, target="Repos", repos_root=repos_root, home=home)
        b = [m for m in maps if m.section == "Repo:my-repo-B"]
        assert len(b) == 5  # alias inherits the full source config
        for m in b:
            # live under the ALIAS entry's own worktree…
            assert m.live.startswith(os.path.join(repos_root, "My Repo-B"))
            # …repo side shared with the alias TARGET's config dir
            assert os.path.join("repos", "my-repo") in m.repo
            assert "my-repo-B" not in m.repo

    def test_absent_repo_flagged_skip_absent(self, env):
        manifest, repo_root, repos_root, home = env
        maps = setup_mod.expand_mappings(
            manifest, repo_root, target="Repos", repos_root=repos_root, home=home)
        minimal = [m for m in maps if m.section == "Repo:minimal"]
        assert len(minimal) == 1
        assert minimal[0].skip_absent
        assert os.path.join(repos_root, "minimal") in minimal[0].skip_reason

    def test_windows_paths_absent_on_posix_without_repos_root(self, env):
        manifest, repo_root, repos_root, home = env
        maps = setup_mod.expand_mappings(manifest, repo_root, target="Repos", home=home)
        assert maps and all(m.skip_absent for m in maps)

    def test_repos_iterated_in_sorted_order(self, env):
        manifest, repo_root, repos_root, home = env
        maps = setup_mod.expand_mappings(
            manifest, repo_root, target="Repos", repos_root=repos_root, home=home)
        sections = [m.section for m in maps]
        assert sections == sorted(sections, key=lambda s: s.split(":", 1)[1]) or \
            sections == [s for s in sections]  # stable grouping
        first_of = {s: sections.index(s) for s in dict.fromkeys(sections)}
        assert list(first_of) == ["Repo:minimal", "Repo:my-repo", "Repo:my-repo-B"]


class TestExpandRealManifest:
    def test_user_scope_of_real_manifest(self, manifest, tmp_path):
        maps = setup_mod.expand_mappings(
            manifest, str(REPO_ROOT), target="User", home=str(tmp_path))
        assert len(maps) == 11
        assert all(m.section == "User" for m in maps)
        skills = [m for m in maps if m.live.endswith(os.path.join(".claude", "skills"))]
        assert skills and skills[0].repo == os.path.join(str(REPO_ROOT), "user", "skills")


# ---------------------------------------------------------------------------
# Phase 2 — link primitives (D3)
# ---------------------------------------------------------------------------


class TestLinkPrimitivesPosix:
    def test_create_and_detect_symlink(self, tmp_path):
        repo = tmp_path / "repo-side.txt"
        repo.write_text("x")
        live = tmp_path / "live-side.txt"
        kind = setup_mod._create_link(str(live), str(repo), is_dir=False)
        assert kind == "symlink"
        assert setup_mod._is_link(str(live))
        assert not setup_mod._is_link(str(repo))
        assert setup_mod._read_link_target(str(live)) == str(repo)

    def test_resolve_target_relative_link(self, tmp_path):
        (tmp_path / "repo").mkdir()
        target_file = tmp_path / "repo" / "f.txt"
        target_file.write_text("x")
        (tmp_path / "live").mkdir()
        live = tmp_path / "live" / "f.txt"
        os.symlink(os.path.join("..", "repo", "f.txt"), str(live))
        assert setup_mod._targets_equal(str(live), str(target_file))
        assert not setup_mod._targets_equal(str(live), str(tmp_path / "other"))


class TestCreateLinkWindowsSelection:
    """Windows branch — mocked platform (exercised for real on Windows only)."""

    def test_symlink_success_on_nt(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(setup_mod, "_WINDOWS", True)
        monkeypatch.setattr(setup_mod, "_symlink",
                            lambda t, l, d: calls.append(("symlink", t, l, d)))
        kind = setup_mod._create_link(str(tmp_path / "l"), str(tmp_path / "r"), is_dir=True)
        assert kind == "symlink" and calls

    def test_privilege_error_dir_falls_back_to_junction(self, tmp_path, monkeypatch):
        junctions = []
        monkeypatch.setattr(setup_mod, "_WINDOWS", True)
        monkeypatch.setattr(setup_mod, "_symlink",
                            lambda t, l, d: (_ for _ in ()).throw(OSError(1314, "priv")))
        monkeypatch.setattr(setup_mod, "_create_junction",
                            lambda t, l: junctions.append((t, l)))
        kind = setup_mod._create_link(str(tmp_path / "l"), str(tmp_path / "r"), is_dir=True)
        assert kind == "junction"
        assert junctions == [(str(tmp_path / "r"), str(tmp_path / "l"))]

    def test_privilege_error_file_dies_actionably(self, tmp_path, monkeypatch):
        monkeypatch.setattr(setup_mod, "_WINDOWS", True)
        monkeypatch.setattr(setup_mod, "_symlink",
                            lambda t, l, d: (_ for _ in ()).throw(OSError(1314, "priv")))
        with pytest.raises(setup_mod.SetupError) as exc:
            setup_mod._create_link(str(tmp_path / "l"), str(tmp_path / "r"), is_dir=False)
        assert "Developer Mode" in str(exc.value)

    def test_posix_never_touches_junction(self, tmp_path, monkeypatch):
        monkeypatch.setattr(setup_mod, "_WINDOWS", False)
        monkeypatch.setattr(setup_mod, "_create_junction",
                            lambda t, l: pytest.fail("junction on POSIX"))
        repo = tmp_path / "r"
        repo.write_text("x")
        assert setup_mod._create_link(str(tmp_path / "l"), str(repo), False) == "symlink"

    def test_is_link_junction_probe_on_nt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(setup_mod, "_WINDOWS", True)
        monkeypatch.setattr(setup_mod, "_readlink", lambda p: "X:\\somewhere")
        assert setup_mod._is_link(str(tmp_path / "junction-like"))
        monkeypatch.setattr(setup_mod, "_readlink",
                            lambda p: (_ for _ in ()).throw(OSError(22, "not a link")))
        assert not setup_mod._is_link(str(tmp_path / "plain"))


# ---------------------------------------------------------------------------
# Phase 3 — bootstrap / check / repair verbs (parity table rows)
# ---------------------------------------------------------------------------


def _mk(live, repo, mtype="File", section="User", skip_absent=False, skip_reason=""):
    return setup_mod.Mapping(live=str(live), repo=str(repo), type=mtype,
                             section=section, skip_absent=skip_absent,
                             skip_reason=skip_reason)


@pytest.fixture()
def fx(tmp_path):
    """live/ and repo/ dirs for verb fixtures."""
    live = tmp_path / "live"
    repo = tmp_path / "repo"
    live.mkdir()
    repo.mkdir()
    return live, repo


class TestBootstrap:
    def test_correct_link_skips(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        os.symlink(str(repo / "f.md"), str(live / "f.md"))
        rc = setup_mod.cmd_bootstrap([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "SKIP" in out
        assert "Bootstrap: 0 moved, 0 linked, 1 skipped, 0 warnings" in out

    def test_wrong_link_repo_exists_relinks(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("repo")
        (repo / "other.md").write_text("other")
        os.symlink(str(repo / "other.md"), str(live / "f.md"))
        rc = setup_mod.cmd_bootstrap([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "RELINK" in out
        assert (live / "f.md").read_text() == "repo"

    def test_wrong_link_repo_missing_copylinks_referent(self, fx, capsys):
        live, repo = fx
        (live / "elsewhere.md").write_text("content")
        os.symlink(str(live / "elsewhere.md"), str(live / "f.md"))
        rc = setup_mod.cmd_bootstrap([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "COPYLINK" in out
        assert (repo / "f.md").read_text() == "content"
        assert os.path.islink(str(live / "f.md"))
        assert setup_mod._targets_equal(str(live / "f.md"), str(repo / "f.md"))

    def test_real_file_repo_missing_moves_and_links(self, fx, capsys):
        live, repo = fx
        (live / "f.md").write_text("moved")
        rc = setup_mod.cmd_bootstrap([_mk(live / "f.md", repo / "sub" / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "MOVE" in out
        assert (repo / "sub" / "f.md").read_text() == "moved"  # repo parent created
        assert os.path.islink(str(live / "f.md"))
        assert "Bootstrap: 1 moved, 0 linked, 0 skipped, 0 warnings" in out

    def test_real_dir_repo_missing_moves_and_links(self, fx, capsys):
        live, repo = fx
        (live / "skills").mkdir()
        (live / "skills" / "a.md").write_text("a")
        rc = setup_mod.cmd_bootstrap(
            [_mk(live / "skills", repo / "skills", mtype="Directory")])
        assert rc == 0
        assert (repo / "skills" / "a.md").read_text() == "a"
        assert os.path.islink(str(live / "skills"))

    def test_both_exist_warns_untouched(self, fx, capsys):
        live, repo = fx
        (live / "f.md").write_text("live")
        (repo / "f.md").write_text("repo")
        rc = setup_mod.cmd_bootstrap([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "WARN" in out and "both live and repo exist" in out
        assert (live / "f.md").read_text() == "live"
        assert (repo / "f.md").read_text() == "repo"
        assert "1 warnings" in out

    def test_live_missing_repo_exists_recovery_link(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        rc = setup_mod.cmd_bootstrap([_mk(live / "deep" / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "LINK" in out and "recovery" in out
        assert os.path.islink(str(live / "deep" / "f.md"))  # live parent created

    def test_both_missing_none(self, fx, capsys):
        live, repo = fx
        rc = setup_mod.cmd_bootstrap([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "NONE" in out

    def test_skip_absent_repo_never_materialized(self, fx, capsys):
        live, repo = fx
        rc = setup_mod.cmd_bootstrap([_mk(
            live / "wt" / "f.md", repo / "f.md", section="Repo:gone",
            skip_absent=True, skip_reason="repo absent: /nope")])
        out = capsys.readouterr().out
        assert rc == 0 and "SKIP" in out and "repo absent: /nope" in out
        assert not (live / "wt").exists()


class TestCheck:
    def test_ok_and_exit_0(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        os.symlink(str(repo / "f.md"), str(live / "f.md"))
        rc = setup_mod.cmd_check([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "OK" in out
        assert "Check: 1 OK, 0 broken, 0 absent" in out

    def test_missing_is_broken_exit_1(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        rc = setup_mod.cmd_check([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 1 and "MISSING" in out

    def test_absent_not_broken(self, fx, capsys):
        live, repo = fx
        rc = setup_mod.cmd_check([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "ABSENT" in out
        assert "Check: 0 OK, 0 broken, 1 absent" in out

    def test_real_file_is_broken(self, fx, capsys):
        live, repo = fx
        (live / "f.md").write_text("real")
        (repo / "f.md").write_text("x")
        rc = setup_mod.cmd_check([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 1 and "REAL" in out and "not symlinked" in out

    def test_wrong_target_is_broken_and_named(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        (repo / "other.md").write_text("y")
        os.symlink(str(repo / "other.md"), str(live / "f.md"))
        rc = setup_mod.cmd_check([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 1 and "WRONG" in out and "other.md" in out

    def test_skip_absent_repo_not_broken(self, fx, capsys):
        live, repo = fx
        rc = setup_mod.cmd_check([_mk(
            live / "wt" / "f.md", repo / "f.md", section="Repo:gone",
            skip_absent=True, skip_reason="repo absent: /nope")])
        out = capsys.readouterr().out
        assert rc == 0 and "repo absent: /nope" in out


class TestRepair:
    def test_repo_missing_skips(self, fx, capsys):
        live, repo = fx
        rc = setup_mod.cmd_repair([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "Repair: 0 fixed, 1 OK" in out

    def test_correct_link_skips(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        os.symlink(str(repo / "f.md"), str(live / "f.md"))
        rc = setup_mod.cmd_repair([_mk(live / "f.md", repo / "f.md")])
        assert rc == 0 and "Repair: 0 fixed, 1 OK" in capsys.readouterr().out

    def test_wrong_link_relinked(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("repo")
        (repo / "other.md").write_text("y")
        os.symlink(str(repo / "other.md"), str(live / "f.md"))
        rc = setup_mod.cmd_repair([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "REPAIR" in out
        assert (live / "f.md").read_text() == "repo"

    def test_real_file_backed_up_then_linked(self, fx, capsys):
        live, repo = fx
        (live / "f.md").write_text("precious")
        (repo / "f.md").write_text("repo")
        rc = setup_mod.cmd_repair([_mk(live / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "BACKUP" in out and "REPAIR" in out
        assert (live / "f.md.bak").read_text() == "precious"
        assert (live / "f.md").read_text() == "repo"

    def test_missing_live_linked(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        rc = setup_mod.cmd_repair([_mk(live / "deep" / "f.md", repo / "f.md")])
        out = capsys.readouterr().out
        assert rc == 0 and "REPAIR" in out
        assert os.path.islink(str(live / "deep" / "f.md"))

    def test_repair_then_check_roundtrip(self, fx, capsys):
        live, repo = fx
        (repo / "f.md").write_text("x")
        (live / "f.md").write_text("real")
        maps = [_mk(live / "f.md", repo / "f.md")]
        assert setup_mod.cmd_check(maps) == 1
        assert setup_mod.cmd_repair(maps) == 0
        assert setup_mod.cmd_check(maps) == 0


# ---------------------------------------------------------------------------
# Phase 3 — CLI + end-to-end
# ---------------------------------------------------------------------------


def _run_cli(args, home):
    import subprocess
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    return subprocess.run([sys.executable, str(SETUP_PY)] + args,
                          capture_output=True, text=True, env=env)


class TestCli:
    def test_setup_error_maps_to_exit_2(self, monkeypatch, capsys):
        monkeypatch.setattr(setup_mod, "parse_psd1",
                            lambda text: setup_mod._die("boom", 3))
        rc = setup_mod.main(["check"])
        assert rc == 2
        assert "line 3: boom" in capsys.readouterr().err

    def test_unknown_command_exits_2(self, tmp_path):
        proc = _run_cli(["frobnicate"], tmp_path)
        assert proc.returncode == 2

    def test_check_header_and_honest_exit_on_empty_home(self, tmp_path):
        proc = _run_cli(["check", "--target", "User"], tmp_path)
        assert proc.returncode == 1  # empty container HOME -> MISSING rows
        assert "Command: check | Target: User" in proc.stdout
        assert "MISSING" in proc.stdout
        assert "Check:" in proc.stdout

    def test_repos_root_must_exist(self, tmp_path):
        proc = _run_cli(
            ["check", "--target", "Repos", "--repos-root", str(tmp_path / "nope")],
            tmp_path)
        assert proc.returncode == 2
        assert "repos-root" in proc.stderr


class TestEndToEnd:
    """SPEC D5: fresh (container-like) HOME -> bootstrap User self-hosts."""

    def test_bootstrap_user_then_check_green(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        boot = _run_cli(["bootstrap", "--target", "User"], home)
        assert boot.returncode == 0, boot.stdout + boot.stderr
        # links materialized from the clone
        skills = home / ".claude" / "skills"
        assert os.path.islink(str(skills))
        assert os.path.realpath(str(skills)) == os.path.realpath(
            str(REPO_ROOT / "user" / "skills"))
        claude_md = home / ".claude" / "CLAUDE.md"
        assert os.path.islink(str(claude_md))
        # write-through identity: live path and repo path are the same file
        assert claude_md.read_text() == (REPO_ROOT / "user" / "CLAUDE.md").read_text()
        check = _run_cli(["check", "--target", "User"], home)
        assert check.returncode == 0, check.stdout
        assert "0 broken" in check.stdout

    def test_bootstrap_is_idempotent(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        assert _run_cli(["bootstrap", "--target", "User"], home).returncode == 0
        second = _run_cli(["bootstrap", "--target", "User"], home)
        assert second.returncode == 0
        assert "0 moved" in second.stdout and "0 linked" in second.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"] + sys.argv[1:]))
