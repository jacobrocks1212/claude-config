"""Tests for tool-search.py (orchestrator-tool-search).

Hermetic, fixture-driven: every corpus loader is exercised against a small
temp-dir fixture corpus, never the live repo, per the house test conventions
(user/scripts/CLAUDE.md). The hyphenated module is imported via importlib
(the toolify-promote.py `_load_miner()` precedent).
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _load_tool_search():
    if "tool_search" in sys.modules:
        return sys.modules["tool_search"]
    spec = importlib.util.spec_from_file_location(
        "tool_search", str(_SCRIPTS_DIR / "tool-search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["tool_search"] = mod
    spec.loader.exec_module(mod)
    return mod


ts = _load_tool_search()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fake_cli_surface(path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "scripts": {
            "cli_surface_gen.py": {
                "flags": [
                    {"name": "--check", "help_head": "Regenerate to memory and "
                     "diff against the committed registry (freshness gate)."},
                    {"name": "--repo-root", "help_head": "Operate on a repo."},
                ]
            },
            "lint-skills.py": {
                "flags": [
                    {"name": "--check-projected", "help_head":
                     "Validate the projected skills tree."},
                ]
            },
        },
    }
    return _write(path, json.dumps(payload))


# ---------------------------------------------------------------------------
# WU-1 — corpus loaders
# ---------------------------------------------------------------------------

class TestCorpusLoaders:
    def test_cli_surface_loader_records(self, tmp_path):
        p = _fake_cli_surface(tmp_path / "cli-surface.json")
        recs = ts.load_cli_surface_corpus(p)
        assert recs, "expected non-empty records"
        for r in recs:
            assert set(r) >= {"source", "name", "invocation", "help_head"}
            assert r["source"] == ts.SOURCE_CLI_SURFACE
        # a record carries both the script name and the flag token so a search
        # for the script can rank it.
        names = " ".join(r["name"] for r in recs)
        assert "cli_surface_gen.py" in names
        assert "--check" in names

    def test_scripts_table_loader_records(self, tmp_path):
        md = (
            "# CLAUDE.md\n\n"
            "| Script | Purpose |\n"
            "|--------|---------|\n"
            "| `project-skills.py` | Expands !cat component refs. |\n"
            "| `kpi-scorecard.py` | Friction KPI registry lint + scorecard. |\n"
        )
        p = _write(tmp_path / "CLAUDE.md", md)
        recs = ts.load_scripts_table_corpus([p])
        names = {r["name"] for r in recs}
        assert "project-skills.py" in names
        assert "kpi-scorecard.py" in names
        for r in recs:
            assert r["source"] == ts.SOURCE_SCRIPTS_TABLE
            assert r["help_head"]

    def test_skill_catalog_loader_records(self, tmp_path):
        skills = tmp_path / "skills"
        _write(skills / "lazy-status" / "SKILL.md",
               "---\nname: lazy-status\ndescription: Read-only progress "
               "dashboard.\n---\n\n# Lazy Status\n")
        recs = ts.load_skill_catalog_corpus([skills])
        assert any("lazy-status" in r["name"] for r in recs)
        r = next(r for r in recs if "lazy-status" in r["name"])
        assert r["source"] == ts.SOURCE_SKILL_CATALOG
        assert "dashboard" in (r["help_head"] or "").lower()

    def test_host_capability_loader_records(self):
        recs = ts.load_host_capability_corpus(["real-audio-device", "gpu"])
        names = {r["name"] for r in recs}
        assert names == {"real-audio-device", "gpu"}
        for r in recs:
            assert r["source"] == ts.SOURCE_HOST_CAPABILITY

    def test_mcp_tool_catalog_absent_is_empty_not_error(self, tmp_path):
        # claude-config's real case: no per-repo mcp-tool-catalog.md.
        recs = ts.load_mcp_tool_catalog_corpus(tmp_path / "nope.md")
        assert recs == []

    def test_mcp_tool_catalog_present_records(self, tmp_path):
        md = (
            "# MCP tool catalog\n\n"
            "| Tool | Purpose |\n"
            "|------|---------|\n"
            "| `play_deck` | Start playback on a deck. |\n"
        )
        p = _write(tmp_path / "mcp-tool-catalog.md", md)
        recs = ts.load_mcp_tool_catalog_corpus(p)
        assert any(r["name"] == "play_deck" for r in recs)
        assert all(r["source"] == ts.SOURCE_MCP_TOOL_CATALOG for r in recs)

    def test_build_corpus_composes_all_sources(self, tmp_path):
        _fake_cli_surface(tmp_path / "docs" / "cli" / "cli-surface.json")
        _write(tmp_path / "CLAUDE.md",
               "| Script | Purpose |\n|--|--|\n"
               "| `setup.py` | Symlink setup. |\n")
        _write(tmp_path / "user" / "skills" / "commit" / "SKILL.md",
               "---\nname: commit\ndescription: Stage and commit.\n---\n")
        corpus = ts.build_corpus(tmp_path)
        sources = {r["source"] for r in corpus}
        assert ts.SOURCE_CLI_SURFACE in sources
        assert ts.SOURCE_SCRIPTS_TABLE in sources
        assert ts.SOURCE_SKILL_CATALOG in sources
        # mcp-tool-catalog absent for this fixture repo -> no records, no crash.
        assert ts.SOURCE_MCP_TOOL_CATALOG not in sources


# ---------------------------------------------------------------------------
# WU-2 — ranking + MISS
# ---------------------------------------------------------------------------

def _corpus():
    return [
        {"source": "cli-surface", "name": "cli_surface_gen.py --check",
         "invocation": "python3 user/scripts/cli_surface_gen.py --check",
         "help_head": "Regenerate and diff the committed registry."},
        {"source": "scripts-table", "name": "kpi-scorecard.py",
         "invocation": "kpi-scorecard.py",
         "help_head": "Friction KPI registry lint and scorecard render."},
        {"source": "skill-catalog", "name": "/commit",
         "invocation": "/commit", "help_head": "Stage and commit changes."},
    ]


class TestRanking:
    def test_hit_ranks_strong_overlap_first(self):
        ranked = ts.rank_corpus(_corpus(), "regenerate the cli surface registry")
        assert ranked
        assert ranked[0]["name"] == "cli_surface_gen.py --check"
        assert ranked[0]["score"] >= 2

    def test_zero_overlap_returns_empty_and_miss(self):
        ranked = ts.rank_corpus(_corpus(),
                                "frobnicate the quantum flux capacitor")
        assert ranked == []
        assert ts.search_verdict(ranked) == "MISS"

    def test_top_n_truncates(self):
        ranked = ts.rank_corpus(_corpus(), "registry commit scorecard", top_n=1)
        assert len(ranked) == 1

    def test_record_shape_and_json_roundtrip(self):
        ranked = ts.rank_corpus(_corpus(), "kpi registry")
        blob = json.dumps(ranked)
        back = json.loads(blob)
        for r in back:
            assert set(r) >= {"source", "name", "invocation",
                              "help_head", "score"}

    def test_near_miss_difflib_fallback(self):
        # typo query with no substring token match still resolves via difflib.
        corpus = [{"source": "scripts-table", "name": "regenerate-registry",
                   "invocation": "regenerate-registry", "help_head": None}]
        ranked = ts.rank_corpus(corpus, "regenrate regstry")
        assert ranked, "near-miss fallback should surface the close name"
        assert ranked[0]["name"] == "regenerate-registry"

    def test_render_last_line_is_miss_on_miss(self):
        out = ts.render_search_result([], "no such tool", 5)
        assert out.splitlines()[-1] == "MISS"

    def test_render_last_line_is_summary_on_hit(self):
        ranked = ts.rank_corpus(_corpus(), "kpi registry")
        out = ts.render_search_result(ranked, "kpi registry", 5)
        assert out.splitlines()[-1] != "MISS"
        assert "kpi-scorecard.py" in out


# ---------------------------------------------------------------------------
# WU-3 — CLI scaffold, roster conformance, telemetry breadcrumb
# ---------------------------------------------------------------------------

def _fixture_repo(tmp_path: Path) -> Path:
    _fake_cli_surface(tmp_path / "docs" / "cli" / "cli-surface.json")
    _write(tmp_path / "CLAUDE.md",
           "| Script | Purpose |\n|--|--|\n"
           "| `kpi-scorecard.py` | Friction KPI registry lint + scorecard. |\n")
    return tmp_path


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, event, *, item_id=None, data=None, now=None):
        self.calls.append((event, data))
        return True


class TestCliRosterAndTelemetry:
    def test_dump_cli_surface_schema_v1(self, capsys):
        rc = ts.main(["--dump-cli-surface"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["script"] == "tool-search.py"
        assert payload["schema_version"] == 1
        assert "flags" in payload
        flag_names = {f["name"] for f in payload["flags"]}
        assert "--tool-search" in flag_names

    def test_unrecognized_flag_suggests(self, capsys):
        with pytest.raises(SystemExit) as exc:
            ts.main(["--tool-serch", "x"])
        assert exc.value.code == 2
        err = capsys.readouterr().err.lower()
        assert "did you mean" in err

    def test_telemetry_called_once_on_hit_and_miss_not_on_dump(
            self, tmp_path, monkeypatch):
        repo = _fixture_repo(tmp_path)
        rec = _Recorder()
        monkeypatch.setattr(ts.lazy_core, "append_telemetry_event", rec)

        ts.main(["--tool-search", "kpi registry", "--repo-root", str(repo)])
        assert len(rec.calls) == 1
        event, data = rec.calls[0]
        assert event == "tool-search-invocation"
        assert data["query"] == "kpi registry"
        assert data["verdict"] == "hit"
        assert isinstance(data["top_score"], int)

        ts.main(["--tool-search", "frobnicate quantum flux",
                 "--repo-root", str(repo)])
        assert len(rec.calls) == 2
        assert rec.calls[1][1]["verdict"] == "miss"
        assert rec.calls[1][1]["top_score"] is None

        # --dump-cli-surface is not a real invocation -> no breadcrumb.
        ts.main(["--dump-cli-surface"])
        assert len(rec.calls) == 2

    def test_telemetry_failure_is_fail_open(self, tmp_path, monkeypatch, capsys):
        repo = _fixture_repo(tmp_path)

        def _boom(*a, **k):
            raise RuntimeError("ledger unwritable")

        monkeypatch.setattr(ts.lazy_core, "append_telemetry_event", _boom)
        rc = ts.main(["--tool-search", "kpi registry", "--repo-root", str(repo)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "kpi-scorecard.py" in out  # search output unaffected

    def test_json_output_roundtrips(self, tmp_path, capsys):
        repo = _fixture_repo(tmp_path)
        ts.main(["--tool-search", "kpi registry", "--json",
                 "--repo-root", str(repo)])
        payload = json.loads(capsys.readouterr().out)
        assert payload["verdict"] == "hit"
        assert payload["matches"]
        for m in payload["matches"]:
            assert set(m) >= {"source", "name", "invocation",
                              "help_head", "score"}
