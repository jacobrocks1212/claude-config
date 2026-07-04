#!/usr/bin/env python3
"""
test_skill_usage_miner.py — Tests for skill-usage-miner.py (skill-usage-miner feature).

The miner is an offline, stdlib-only, READ-ONLY session-log analyzer that joins a
skill inventory (user-level + repo-scoped SKILL.md dispatchers) against invocation
signals mined from ``~/.claude/projects`` transcripts via two detectors:

  detector 1 (skill-tool): assistant-turn ``tool_use`` blocks with name == "Skill"
             (value-preserving read of input["skill"], incl. subagents/agent-*.jsonl)
  detector 2 (slash): user-turn text matched by the field-proven
             ``<command-name>(/[\\w:-]+)</command-name>`` regex (digest_sessions.py:125)

These tests lock in (per SPEC docs/features/skill-usage-miner/SPEC.md):

  Phase 1: detectors counted separately; subagent attribution to the parent session;
           distinct-session + last-seen columns; name normalization; user-level
           inventory; markdown+JSON renderers; standing Caveats; empty-corpus
           message; malformed-JSONL tolerance; deterministic output; the
           TWO-TREE READ-ONLY invariant (fixture logs dir AND fixture skills tree
           byte-identical before/after — mirrors test_toolify_miner._dir_hash).
  Phase 2: repo-scoped inventory + heuristic attribution; *-cloud annotation;
           --since; the 30d recency column (anchored to newest corpus timestamp);
           the git-age-gated never-invoked list.
  Phase 3: hygiene sweep (stray file / dangling symlink / case-variant skill.md /
           missing dispatcher); D8 archival proposal blocks (text only, never run).
  Phase 4: toolify-candidate threshold; unknown invocations surfaced.

Run with: python3 user/scripts/test_skill_usage_miner.py   (exit 0 on pass)
Also pytest-discoverable. No third-party dependencies — stdlib only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Import the hyphenated module under a clean name (test_toolify_miner pattern).
# ---------------------------------------------------------------------------
_IMPORT_ERROR = None
sum_mod = None
try:
    _spec = importlib.util.spec_from_file_location(
        "skill_usage_miner", str(_SCRIPTS_DIR / "skill-usage-miner.py")
    )
    sum_mod = importlib.util.module_from_spec(_spec)
    sys.modules["skill_usage_miner"] = sum_mod
    _spec.loader.exec_module(sum_mod)  # type: ignore[union-attr]
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _ModuleMissing(Exception):
    pass


def _guard():
    if _IMPORT_ERROR is not None:
        raise _ModuleMissing(f"skill-usage-miner.py not importable: {_IMPORT_ERROR}")


# ---------------------------------------------------------------------------
# Fixture builders.
# ---------------------------------------------------------------------------

def _assistant_skill_turn(skill, ts="2026-06-01T10:00:00.000Z"):
    """One assistant transcript line invoking the Skill tool for `skill`."""
    return {
        "type": "assistant",
        "timestamp": ts,
        "uuid": "u",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_1", "name": "Skill",
                 "input": {"skill": skill, "args": ""}},
            ],
        },
    }


def _user_slash_turn(cmd, ts="2026-06-01T09:00:00.000Z", as_string=False):
    """One user transcript line carrying a slash-command marker for /cmd."""
    txt = f"<command-name>/{cmd}</command-name>\n<command-args></command-args>"
    content = txt if as_string else [{"type": "text", "text": txt}]
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": "u",
        "message": {"role": "user", "content": content},
    }


def _plain_user_turn(text, ts="2026-06-01T08:00:00.000Z"):
    return {
        "type": "user",
        "timestamp": ts,
        "uuid": "u",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def _mk_skill(repo_root: Path, name, *, repo=None, frontmatter_name=None):
    """Create a SKILL.md dispatcher in the fixture repo (user or repo scope)."""
    if repo is None:
        d = repo_root / "user" / "skills" / name
    else:
        d = repo_root / "repos" / repo / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    fm_name = frontmatter_name if frontmatter_name is not None else name
    (d / "SKILL.md").write_text(
        f"---\ndescription: fixture skill\nname: {fm_name}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return d


def _mk_repo_root(td: Path, skills=("commit", "explain")):
    """A minimal claude-config-shaped fixture checkout."""
    root = td / "cfg"
    (root / "user" / "skills").mkdir(parents=True, exist_ok=True)
    for s in skills:
        _mk_skill(root, s)
    return root


def _basic_logs(td: Path):
    """Fixture corpus: 2 sessions in one project dir.

    session-1: /commit slash marker (x2, one string-content) + Skill(explain)
    session-1/subagents/agent-a: Skill(commit)   -> attributes to session-1
    session-2: /commit slash marker
    Corpus span 2026-05-01 .. 2026-07-01.
    """
    logs = td / "projects"
    proj = logs / "C--Users-x-repos-Foo"
    _write_jsonl(
        proj / "session-1.jsonl",
        [
            _user_slash_turn("commit", ts="2026-05-01T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-05-02T09:00:00.000Z", as_string=True),
            _assistant_skill_turn("explain", ts="2026-05-03T10:00:00.000Z"),
            _plain_user_turn("no markers here", ts="2026-05-04T08:00:00.000Z"),
        ],
    )
    _write_jsonl(
        proj / "session-1" / "subagents" / "agent-abc.jsonl",
        [_assistant_skill_turn("commit", ts="2026-05-05T10:00:00.000Z")],
    )
    _write_jsonl(
        proj / "session-2.jsonl",
        [_user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z")],
    )
    return logs


def _dir_hash(root: Path) -> str:
    """A stable hash of every file's relative path + bytes under root
    (mirrors test_toolify_miner._dir_hash; symlinks hashed by their target string)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root)).replace("\\", "/").encode("utf-8")
        if p.is_symlink():
            h.update(rel)
            h.update(b"\0->")
            h.update(str(os.readlink(p)).encode("utf-8"))
            h.update(b"\0")
        elif p.is_file():
            h.update(rel)
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def _report(root, logs, **kw):
    return sum_mod.build_report(repo_root=root, logs_dir=logs, **kw)


def _usage_row(report, skill):
    for row in report["usage"]:
        if row["skill"] == skill:
            return row
    return None


# ===========================================================================
# Phase 1 — detectors / inventory / renderers / read-only / robustness
# ===========================================================================

def test_module_importable():
    _guard()
    assert sum_mod is not None


def test_detectors_counted_separately_with_sessions_and_last_seen():
    """Per-skill skill-tool vs slash counts are separate columns; distinct
    sessions and last-seen come from per-line timestamps; the subagent
    transcript attributes to its PARENT session."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        rep = _report(root, logs)
        commit = _usage_row(rep, "commit")
        assert commit is not None, rep["usage"]
        # 2 slash in session-1 + 1 slash in session-2; 1 skill-tool via subagent.
        assert commit["slash"] == 3, commit
        assert commit["skill_tool"] == 1, commit
        # Subagent hit belongs to session-1 -> distinct sessions == 2, not 3.
        assert commit["sessions"] == 2, commit
        assert commit["last_seen"] == "2026-07-01", commit
        explain = _usage_row(rep, "explain")
        assert explain["skill_tool"] == 1 and explain["slash"] == 0, explain
        # Corpus meta
        assert rep["meta"]["sessions"] == 2, rep["meta"]
        assert rep["meta"]["corpus_start"] == "2026-05-01"
        assert rep["meta"]["corpus_end"] == "2026-07-01"


def test_skill_name_normalization():
    """Leading '/' and plugin: prefixes on Skill-tool values normalize to the
    bare skill name; slash-marker names keep their [\\w:-] form minus the '/'."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("commit",))
        logs = td / "projects"
        _write_jsonl(
            logs / "P" / "s1.jsonl",
            [
                _assistant_skill_turn("/commit"),
                _assistant_skill_turn("myplugin:commit"),
                _assistant_skill_turn("commit"),
            ],
        )
        rep = _report(root, logs)
        commit = _usage_row(rep, "commit")
        assert commit is not None and commit["skill_tool"] == 3, rep["usage"]


def test_ranked_table_deterministic_ordering():
    """Usage rows order by total count desc, then name asc — stable."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("aaa", "bbb", "ccc"))
        logs = td / "projects"
        _write_jsonl(
            logs / "P" / "s1.jsonl",
            [_user_slash_turn("bbb"), _user_slash_turn("bbb"),
             _user_slash_turn("aaa"), _user_slash_turn("ccc")],
        )
        rep = _report(root, logs)
        names = [r["skill"] for r in rep["usage"]]
        assert names == ["bbb", "aaa", "ccc"], names


def test_markdown_report_shape_and_caveats():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        rep = _report(root, logs)
        md = sum_mod.render_markdown(rep)
        assert "## Skill usage" in md
        assert "| rank | skill | scope | skill-tool | slash | sessions | last seen | 30d |" in md
        assert "## Caveats (standing)" in md
        # The three honest-blind-spot caveats (D2) are always present.
        assert "Component-injected" in md
        assert "Cloud sessions" in md
        assert "never proof of deadness" in md


def test_json_report_schema():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        rep = _report(root, logs)
        parsed = json.loads(sum_mod.render_json(rep))
        for key in ("meta", "usage", "never_invoked", "zero_unaged", "hygiene",
                    "toolify_candidates", "unknown_invocations", "caveats"):
            assert key in parsed, f"missing schema key {key}"
        row = parsed["usage"][0]
        for key in ("skill", "scope", "skill_tool", "slash", "sessions",
                    "last_seen", "recent", "notes"):
            assert key in row, f"missing usage field {key}"


def test_read_only_over_both_trees():
    """THE LOAD-BEARING INVARIANT (D9): a full run never mutates the logs dir
    OR the skills trees. Hash both before/after; must be byte-identical."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        before_logs, before_tree = _dir_hash(logs), _dir_hash(root)
        rep = _report(root, logs)
        sum_mod.render_markdown(rep)
        sum_mod.render_json(rep)
        assert _dir_hash(logs) == before_logs, "miner MUST NOT mutate the logs dir"
        assert _dir_hash(root) == before_tree, "miner MUST NOT mutate the skills trees"


def test_malformed_lines_skipped_gracefully():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("commit",))
        logs = td / "projects"
        p = logs / "P" / "s1.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            fh.write("{not valid json\n")
            fh.write("42\n")
            fh.write(json.dumps(_user_slash_turn("commit")) + "\n")
        rep = _report(root, logs)  # must not raise
        assert _usage_row(rep, "commit")["slash"] == 1


def test_missing_corpus_explicit_message():
    """A missing/empty logs dir yields an explicit 'no corpus found' report,
    never a bare empty table."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        missing = td / "does-not-exist"
        rep = _report(root, missing)
        assert rep["meta"]["corpus_found"] is False
        md = sum_mod.render_markdown(rep)
        assert f"no corpus found at {missing}" in md, md


def test_deterministic_output_two_runs_byte_identical():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        a = sum_mod.render_markdown(_report(root, logs))
        b = sum_mod.render_markdown(_report(root, logs))
        aj = sum_mod.render_json(_report(root, logs))
        bj = sum_mod.render_json(_report(root, logs))
        assert a == b and aj == bj


def test_cli_smoke_json_and_readonly():
    """End-to-end CLI: --json parses, exit 0, logs dir byte-unchanged."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        before = _dir_hash(logs)
        res = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "skill-usage-miner.py"),
             "--logs", str(logs), "--repo-root", str(root), "--json"],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        json.loads(res.stdout)
        assert _dir_hash(logs) == before, "CLI run mutated the logs dir"


def test_cli_out_writes_named_file_only():
    """--out saves exactly the report text; stdout stays quiet apart from the
    confirmation-free contract (file content == no-out stdout)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        out = td / "report.md"
        res1 = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "skill-usage-miner.py"),
             "--logs", str(logs), "--repo-root", str(root), "--markdown",
             "--out", str(out)],
            capture_output=True, text=True,
        )
        assert res1.returncode == 0, res1.stderr
        res2 = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "skill-usage-miner.py"),
             "--logs", str(logs), "--repo-root", str(root), "--markdown"],
            capture_output=True, text=True,
        )
        assert out.read_text(encoding="utf-8") == res2.stdout, \
            "--out content must equal the stdout report"


def test_both_formats_when_neither_flag():
    """SPEC UX: both markdown and JSON are emitted when neither flag is given."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td)
        logs = _basic_logs(td)
        res = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "skill-usage-miner.py"),
             "--logs", str(logs), "--repo-root", str(root)],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stderr
        assert "## Skill usage" in res.stdout and '"usage"' in res.stdout


# ---------------------------------------------------------------------------
# Self-contained runner (mirrors test_toolify_miner.py's pattern).
# ---------------------------------------------------------------------------

_TESTS = [(n, f) for n, f in sorted(globals().items())
          if n.startswith("test_") and callable(f)]

_PASSES: list[str] = []
_FAILURES: list[str] = []


def _run_test(name, fn):
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


def main() -> int:
    print("=" * 60)
    print("test_skill_usage_miner.py — skill usage miner tests")
    print("=" * 60)
    if _IMPORT_ERROR is not None:
        print(f"\nMODULE NOT YET PRESENT (expected RED): {_IMPORT_ERROR}\n")
    print()
    for name, fn in _TESTS:
        _run_test(name, fn)
    total, passed, failed = len(_TESTS), len(_PASSES), len(_FAILURES)
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if _FAILURES:
        print("\nFailed tests:")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
