#!/usr/bin/env python3
"""
test_cli_surface_gen.py — Tests for cli_surface.py (shared introspection lib)
and cli_surface_gen.py (aggregator + freshness gate), feature
state-cli-contract-registry Phase 1 (+ the Phase 3 did-you-mean subclass,
which lives in cli_surface.py alongside the introspection helpers).

Covers:
  - cli_surface._describe_action / dump_parser_surface shape on fixture parsers
    (store_true, append, choices, mutually-exclusive group, positional).
  - maybe_handle_dump_cli_surface: None when the flag is absent, JSON print +
    0 when present.
  - cli_surface_gen.generate_registry / check_freshness over a HERMETIC
    fixture roster (a tiny throwaway script in a temp repo) — proves drift
    detection (added/removed/changed flags) without depending on the size or
    runtime of the real 7-script roster.
  - Byte-stable regeneration (two renders of the same registry are identical).
  - A live self-check: the REAL repo's committed docs/cli/cli-surface.json is
    fresh against the REAL 7-script roster (the doc-drift-lint.py
    "self-check that THIS repo is clean" precedent) — this is the test that
    goes red if a roster script's argparse changes without regenerating.
  - Phase 3: DidYouMeanArgumentParser suggests a near-miss flag on
    "unrecognized arguments" while preserving the leading error line + exit
    code 2.

Run with: python -m pytest user/scripts/test_cli_surface_gen.py -q
Stdlib + pytest only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_REPO_ROOT = _SCRIPTS_DIR.parent.parent

import cli_surface
import cli_surface_gen as csg


# ---------------------------------------------------------------------------
# cli_surface.py — introspection shape
# ---------------------------------------------------------------------------

def _fixture_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fixture")
    parser.add_argument("--repo-root", default=".", help="Repo root. Second sentence ignored.")
    parser.add_argument("--verbose", action="store_true", help="Be loud.")
    parser.add_argument("--allow", action="append", default=[], help="Repeatable allow.")
    parser.add_argument("--mode", choices=["fast", "slow"], default="fast", help="Pick a mode.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--a", action="store_true", help="Option A.")
    group.add_argument("--b", action="store_true", help="Option B.")
    parser.add_argument("targets", nargs="*", help="Positional targets.")
    cli_surface.add_dump_cli_surface_flag(parser)
    return parser


def test_dump_parser_surface_shape():
    parser = _fixture_parser()
    result = cli_surface.dump_parser_surface(parser)
    flags = {f["name"]: f for f in result["flags"]}

    assert flags["--repo-root"]["default_kind"] == "value"
    assert flags["--repo-root"]["help_head"] == "Repo root."
    assert flags["--verbose"]["default_kind"] == "const"
    assert flags["--verbose"]["action"] == "_StoreTrueAction"
    assert flags["--allow"]["action"] == "_AppendAction"
    assert flags["--mode"]["choices"] == ["fast", "slow"]
    assert flags["--dump-cli-surface"]["action"] == "_StoreTrueAction"
    # positional
    assert flags["targets"]["positional"] is True
    assert flags["targets"]["aliases"] == []
    # mutually exclusive group id shared between --a/--b, distinct from others
    assert flags["--a"]["group"] is not None
    assert flags["--a"]["group"] == flags["--b"]["group"]
    assert flags["--repo-root"]["group"] is None
    # -h/--help always present (live parser reality)
    assert "--help" in flags
    assert flags["--help"]["aliases"] == ["-h"]


def test_dump_parser_surface_no_default_values_leaked():
    """SPEC: no defaults' VALUES stored — only default_kind. A concrete env-
    dependent default must never appear verbatim in the projection."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-path", default="/should/not/appear/verbatim")
    result = cli_surface.dump_parser_surface(parser)
    rendered = json.dumps(result)
    assert "/should/not/appear/verbatim" not in rendered
    flag = next(f for f in result["flags"] if f["name"] == "--secret-path")
    assert flag["default_kind"] == "value"


def test_maybe_handle_dump_cli_surface_none_when_absent(capsys):
    parser = _fixture_parser()
    args = parser.parse_args(["--verbose"])
    result = cli_surface.maybe_handle_dump_cli_surface(args, parser, "fixture.py")
    assert result is None
    captured = capsys.readouterr()
    assert captured.out == ""


def test_maybe_handle_dump_cli_surface_prints_json_and_returns_0(capsys):
    parser = _fixture_parser()
    args = parser.parse_args(["--dump-cli-surface"])
    result = cli_surface.maybe_handle_dump_cli_surface(args, parser, "fixture.py")
    assert result == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["script"] == "fixture.py"
    assert payload["schema_version"] == cli_surface.SCHEMA_VERSION
    assert isinstance(payload["flags"], list)


# ---------------------------------------------------------------------------
# Phase 3 — DidYouMeanArgumentParser
# ---------------------------------------------------------------------------

def test_did_you_mean_suggests_near_miss(capsys):
    parser = cli_surface.DidYouMeanArgumentParser(prog="widget")
    parser.add_argument("--emit-prompt", action="store_true")
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--emit-prompts"])  # near-miss typo
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "widget: error: unrecognized arguments: --emit-prompts" in captured.err
    assert "did you mean: --emit-prompt?" in captured.err
    assert "docs/cli/cli-surface.json" in captured.err


def test_did_you_mean_falls_through_with_no_close_match(capsys):
    parser = cli_surface.DidYouMeanArgumentParser(prog="widget")
    parser.add_argument("--emit-prompt", action="store_true")
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--zzz-totally-unrelated-xyz"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "widget: error: unrecognized arguments: --zzz-totally-unrelated-xyz" in captured.err
    assert "did you mean" not in captured.err


def test_did_you_mean_other_errors_unchanged(capsys):
    """A non-'unrecognized arguments' error (e.g. missing required arg) is
    byte-identical to stock argparse — the epilogue is scoped narrowly."""
    parser = cli_surface.DidYouMeanArgumentParser(prog="widget")
    parser.add_argument("--required-thing", required=True)
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "did you mean" not in captured.err
    assert "the following arguments are required: --required-thing" in captured.err


# ---------------------------------------------------------------------------
# cli_surface_gen.py — hermetic fixture roster (drift detection)
# ---------------------------------------------------------------------------

_FIXTURE_SCRIPT_TEMPLATE = '''\
import argparse
import sys
from pathlib import Path

sys.path.insert(0, r"{scripts_dir}")
import cli_surface


def build_parser():
    parser = argparse.ArgumentParser()
{extra_args}
    cli_surface.add_dump_cli_surface_flag(parser)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    dump = cli_surface.maybe_handle_dump_cli_surface(args, parser, "fixture_cli.py")
    if dump is not None:
        return dump
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _write_fixture_script(temp_repo: Path, extra_args_src: str) -> None:
    scripts_dir = temp_repo / "user" / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "fixture_cli.py").write_text(
        _FIXTURE_SCRIPT_TEMPLATE.format(
            scripts_dir=str(_SCRIPTS_DIR), extra_args=extra_args_src
        ),
        encoding="utf-8",
    )


_FIXTURE_ROSTER = ({"file": "fixture_cli.py", "needs_repo_root": False},)


def test_generate_registry_hermetic_fixture(tmp_path):
    _write_fixture_script(
        tmp_path, '    parser.add_argument("--alpha", action="store_true")'
    )
    registry = csg.generate_registry(tmp_path, roster=_FIXTURE_ROSTER)
    assert registry["schema_version"] == csg.SCHEMA_VERSION
    names = {f["name"] for f in registry["scripts"]["fixture_cli.py"]["flags"]}
    assert "--alpha" in names
    assert "--dump-cli-surface" in names


def test_byte_stable_regeneration(tmp_path):
    _write_fixture_script(
        tmp_path, '    parser.add_argument("--alpha", action="store_true")'
    )
    first = csg.render_registry(csg.generate_registry(tmp_path, roster=_FIXTURE_ROSTER))
    second = csg.render_registry(csg.generate_registry(tmp_path, roster=_FIXTURE_ROSTER))
    assert first == second


def test_check_freshness_clean_after_write(tmp_path):
    _write_fixture_script(
        tmp_path, '    parser.add_argument("--alpha", action="store_true")'
    )
    registry = csg.generate_registry(tmp_path, roster=_FIXTURE_ROSTER)
    csg.write_registry(tmp_path, registry)
    fresh, findings = csg.check_freshness(tmp_path, roster=_FIXTURE_ROSTER)
    assert fresh is True
    assert findings == []


def test_check_freshness_detects_added_flag(tmp_path):
    _write_fixture_script(
        tmp_path, '    parser.add_argument("--alpha", action="store_true")'
    )
    registry = csg.generate_registry(tmp_path, roster=_FIXTURE_ROSTER)
    csg.write_registry(tmp_path, registry)

    # Now add a flag to the fixture script WITHOUT regenerating — simulates
    # a roster script's argparse changing without a registry regen commit.
    _write_fixture_script(
        tmp_path,
        '    parser.add_argument("--alpha", action="store_true")\n'
        '    parser.add_argument("--beta", action="store_true")',
    )
    fresh, findings = csg.check_freshness(tmp_path, roster=_FIXTURE_ROSTER)
    assert fresh is False
    assert any("added flag(s) --beta" in line for line in findings)


def test_check_freshness_detects_removed_flag(tmp_path):
    _write_fixture_script(
        tmp_path,
        '    parser.add_argument("--alpha", action="store_true")\n'
        '    parser.add_argument("--beta", action="store_true")',
    )
    registry = csg.generate_registry(tmp_path, roster=_FIXTURE_ROSTER)
    csg.write_registry(tmp_path, registry)

    _write_fixture_script(
        tmp_path, '    parser.add_argument("--alpha", action="store_true")'
    )
    fresh, findings = csg.check_freshness(tmp_path, roster=_FIXTURE_ROSTER)
    assert fresh is False
    assert any("removed flag(s) --beta" in line for line in findings)


def test_check_freshness_missing_registry(tmp_path):
    _write_fixture_script(
        tmp_path, '    parser.add_argument("--alpha", action="store_true")'
    )
    fresh, findings = csg.check_freshness(tmp_path, roster=_FIXTURE_ROSTER)
    assert fresh is False
    assert any("does not exist" in line for line in findings)


def test_dump_one_raises_on_missing_script(tmp_path):
    (tmp_path / "user" / "scripts").mkdir(parents=True)
    with pytest.raises(csg.CliSurfaceGenError):
        csg.dump_one(tmp_path, {"file": "nonexistent.py", "needs_repo_root": False})


# ---------------------------------------------------------------------------
# CLI smoke — subprocess round trip on the hermetic fixture repo
# ---------------------------------------------------------------------------

def test_cli_check_exits_1_when_registry_missing(tmp_path):
    """No docs/cli/cli-surface.json at all -> --check exits 1 WITHOUT needing
    the real 7-script roster present (check_freshness short-circuits before
    ever shelling a roster script)."""
    gen_script = _SCRIPTS_DIR / "cli_surface_gen.py"
    result = subprocess.run(
        [sys.executable, str(gen_script), "--repo-root", str(tmp_path), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 1
    assert "does not exist" in (result.stdout + result.stderr)


def test_cli_check_clean_on_real_repo():
    """CLI-level (subprocess, read-only) smoke over the REAL 7-script
    roster: --check exits 0 clean. Never writes — regeneration itself is
    covered by the hermetic fixture tests above; this only exercises the
    CLI argv/exit-code wiring against real scripts."""
    gen_script = _SCRIPTS_DIR / "cli_surface_gen.py"
    result = subprocess.run(
        [sys.executable, str(gen_script), "--repo-root", str(_REPO_ROOT), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Live self-check — the real 7-script roster's committed registry is fresh.
# This is the regression net: it goes RED the moment a roster script's
# argparse changes without `cli_surface_gen.py --repo-root .` being re-run.
# ---------------------------------------------------------------------------

def test_real_repo_registry_is_fresh():
    fresh, findings = csg.check_freshness(_REPO_ROOT)
    assert fresh, "docs/cli/cli-surface.json is stale — regenerate with " \
                   "`python3 user/scripts/cli_surface_gen.py --repo-root .`:\n" \
                   + "\n".join(findings)


def test_real_repo_roster_all_seven_scripts_present():
    registry = json.loads((_REPO_ROOT / "docs" / "cli" / "cli-surface.json").read_text(encoding="utf-8"))
    assert set(registry["scripts"]) == {entry["file"] for entry in csg.ROSTER}
    assert registry["schema_version"] == csg.SCHEMA_VERSION
