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
    # Body content is made per-skill unique so git's --follow rename detection
    # can never map one fixture skill's SKILL.md onto another's (age-gate tests).
    body = "\n".join(f"{name}-fixture-line-{i}" for i in range(20))
    (d / "SKILL.md").write_text(
        f"---\ndescription: fixture skill\nname: {fm_name}\n---\n\n# {name}\n\n{body}\n",
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


# ===========================================================================
# Phase 2 — repo scope + attribution + cloud annotation + windows + age gate
# ===========================================================================

def _git(cwd, *args, env_extra=None):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    })
    if env_extra:
        env.update(env_extra)
    res = subprocess.run(["git", "-C", str(cwd), *args],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 0, f"git {args}: {res.stderr}"
    return res.stdout


def _git_repo_root(td: Path, dated_skills):
    """A fixture checkout that is a real git repo; dated_skills is a list of
    (skill_name, commit_date) committed with backdated author/committer dates."""
    root = td / "cfg"
    (root / "user" / "skills").mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    for name, date in dated_skills:
        _mk_skill(root, name)
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"add {name}",
             env_extra={"GIT_AUTHOR_DATE": f"{date}T12:00:00",
                        "GIT_COMMITTER_DATE": f"{date}T12:00:00"})
    return root


def test_repo_scoped_inventory_and_attribution_note():
    """Repo-scoped skills inventory with scope repo:<name>; hits from project
    dirs containing the repo slug counted in the heuristic attribution note."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=())
        _mk_skill(root, "mcp-test", repo="algobooth")
        logs = td / "projects"
        _write_jsonl(logs / "C--Users-x-repos-AlgoBooth" / "s1.jsonl",
                     [_user_slash_turn("mcp-test")])
        _write_jsonl(logs / "C--Users-x-repos-Other" / "s2.jsonl",
                     [_user_slash_turn("mcp-test")])
        rep = _report(root, logs)
        row = _usage_row(rep, "mcp-test")
        assert row is not None and row["scope"] == "repo:algobooth", row
        notes = "; ".join(row["notes"])
        assert "1/2" in notes and "heuristic" in notes, notes


def test_cloud_variant_annotated():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("lazy-cloud",))
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [_user_slash_turn("lazy-cloud")])
        rep = _report(root, logs)
        row = _usage_row(rep, "lazy-cloud")
        assert any("cloud-biased undercount" in n for n in row["notes"]), row


def test_since_filter_excludes_older_hits():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("commit",))
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-03-01T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-06-15T09:00:00.000Z"),
        ])
        rep = _report(root, logs, since="2026-06-01")
        row = _usage_row(rep, "commit")
        assert row["slash"] == 1, row
        assert rep["meta"]["since"] == "2026-06-01"
        assert rep["meta"]["observation_floor"] == "2026-06-01"


def test_recency_column_anchored_to_corpus_max():
    """30d column counts hits within RECENT_WINDOW_DAYS of the NEWEST corpus
    timestamp — not wall clock (byte-stable reports)."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("commit",))
        logs = td / "projects"
        # corpus max = 2026-07-01; window start = 2026-06-01.
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-04-01T09:00:00.000Z"),  # outside
            _user_slash_turn("commit", ts="2026-06-01T09:00:00.000Z"),  # boundary: inside
            _user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z"),  # inside
        ])
        rep = _report(root, logs)
        row = _usage_row(rep, "commit")
        assert row["recent"] == 2, row
        assert rep["meta"]["recent_window_start"] == "2026-06-01"


def test_age_gate_old_flagged_young_not():
    """D3: zero-count skill created BEFORE the corpus floor (corpus ≥30d) is
    flagged never-invoked with its age; one created after is NOT."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _git_repo_root(td, [("old-skill", "2026-01-01"),
                                   ("young-skill", "2026-06-15"),
                                   ("commit", "2026-01-01")])
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-05-01T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z"),
        ])
        rep = _report(root, logs)
        flagged = {r["skill"] for r in rep["never_invoked"]}
        assert "old-skill" in flagged, rep["never_invoked"]
        assert "young-skill" not in flagged, rep["never_invoked"]
        old = next(r for r in rep["never_invoked"] if r["skill"] == "old-skill")
        assert old["created"] == "2026-01-01" and old["age_days"] > 0, old
        young = next(r for r in rep["zero_unaged"] if r["skill"] == "young-skill")
        assert "younger than the observation floor" in young["reason"], young


def test_age_gate_degrades_when_not_a_git_checkout():
    """A non-git fixture checkout -> 'age unknown — age gate not applied',
    zero-count skill NOT proposed, no crash."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("orphan", "commit"))
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-05-01T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z"),
        ])
        rep = _report(root, logs)
        assert rep["never_invoked"] == [], rep["never_invoked"]
        orphan = next(r for r in rep["zero_unaged"] if r["skill"] == "orphan")
        assert "age unknown — age gate not applied" in orphan["reason"], orphan


def test_age_gate_requires_min_corpus_span():
    """A corpus spanning < 30 days can never produce a never-invoked proposal."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _git_repo_root(td, [("old-skill", "2026-01-01"),
                                   ("commit", "2026-01-01")])
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-06-20T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z"),
        ])
        rep = _report(root, logs)
        assert rep["never_invoked"] == [], rep["never_invoked"]
        old = next(r for r in rep["zero_unaged"] if r["skill"] == "old-skill")
        assert "corpus span" in old["reason"], old


# ===========================================================================
# Phase 3 — hygiene sweep + archival proposal blocks
# ===========================================================================

def test_hygiene_sweep_flags_all_four_classes():
    """Stray file, dangling symlink, case-variant skill.md, dispatcher-less dir
    all flagged; a healthy skill and _components/ are NOT; repo trees swept too."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("healthy",))
        tree = root / "user" / "skills"
        (tree / "_components").mkdir()
        (tree / "_components" / "x.md").write_text("c", encoding="utf-8")
        (tree / "sh.exe.stackdump").write_text("dump", encoding="utf-8")
        os.symlink("C:/Users/nobody/nonexistent", tree / "remotion")
        (tree / "local-site").mkdir()
        (tree / "local-site" / "skill.md").write_text("x", encoding="utf-8")
        (tree / "empty-dir").mkdir()
        # repo-scoped stray
        rtree = root / "repos" / "somerepo" / ".claude" / "skills"
        rtree.mkdir(parents=True)
        (rtree / "junk.txt").write_text("x", encoding="utf-8")
        findings = sum_mod.hygiene_sweep(root)
        by_path = {f["path"]: f for f in findings}
        assert by_path["user/skills/sh.exe.stackdump"]["kind"] == "stray-file"
        assert by_path["user/skills/remotion"]["kind"] == "dangling-symlink"
        # Windows os.readlink() normalizes the reparse point's stored target to
        # backslashes (and strips the NT extended-length prefix, per
        # hygiene_sweep's own stripping) even when the symlink was created
        # from a forward-slash target — compare separator-insensitively.
        detail = by_path["user/skills/remotion"]["detail"].replace("\\", "/")
        assert "C:/Users/nobody/nonexistent" in detail
        assert by_path["user/skills/local-site"]["kind"] == "case-variant-dispatcher"
        assert by_path["user/skills/empty-dir"]["kind"] == "missing-dispatcher"
        assert by_path["repos/somerepo/.claude/skills/junk.txt"]["kind"] == "stray-file"
        assert "user/skills/healthy" not in by_path
        assert not any("_components" in p for p in by_path), by_path.keys()
        # deterministic ordering by path
        assert [f["path"] for f in findings] == sorted(f["path"] for f in findings)


def test_hygiene_flags_malformed_frontmatter():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=())
        bad = root / "user" / "skills" / "badfm"
        bad.mkdir(parents=True)
        (bad / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
        findings = sum_mod.hygiene_sweep(root)
        assert any(f["path"] == "user/skills/badfm"
                   and f["kind"] == "malformed-frontmatter" for f in findings), findings


def test_archival_proposal_block_text_user_scope():
    """D8: a never-invoked user skill carries the ready-to-paste git mv +
    archived/CLAUDE.md row + evidence line; nothing is executed."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _git_repo_root(td, [("dead-skill", "2026-01-01"),
                                   ("commit", "2026-01-01")])
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-05-01T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z"),
        ])
        before = _dir_hash(root)
        rep = _report(root, logs)
        row = next(r for r in rep["never_invoked"] if r["skill"] == "dead-skill")
        assert row["git_mv"] == \
            "git mv user/skills/dead-skill archived/user-skills/dead-skill", row
        assert row["archived_row"].startswith("| `user-skills/dead-skill` | "), row
        assert "(none — retired unused)" in row["archived_row"], row
        assert "0 invocations across 1 sessions spanning 2026-05-01..2026-07-01" \
            in row["evidence"], row
        assert "created 2026-01-01" in row["evidence"], row
        md = sum_mod.render_markdown(rep)
        assert "propose: git mv user/skills/dead-skill" in md
        assert "archived/CLAUDE.md row: | `user-skills/dead-skill` |" in md
        assert _dir_hash(root) == before, "proposal must never be executed"


def test_archival_proposal_block_repo_scope_destination():
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _git_repo_root(td, [("commit", "2026-01-01")])
        _mk_skill(root, "dead-repo-skill", repo="somerepo")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "add repo skill",
             env_extra={"GIT_AUTHOR_DATE": "2026-01-02T12:00:00",
                        "GIT_COMMITTER_DATE": "2026-01-02T12:00:00"})
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("commit", ts="2026-05-01T09:00:00.000Z"),
            _user_slash_turn("commit", ts="2026-07-01T09:00:00.000Z"),
        ])
        rep = _report(root, logs)
        row = next(r for r in rep["never_invoked"] if r["skill"] == "dead-repo-skill")
        assert row["git_mv"] == ("git mv repos/somerepo/.claude/skills/dead-repo-skill "
                                 "archived/repo-skills/somerepo/dead-repo-skill"), row
        assert "`repo-skills/somerepo/dead-repo-skill`" in row["archived_row"], row


def test_display_name_frontmatter_keys_by_dir_and_flags_mismatch():
    """Live-repo finding: some real skills carry a human-title frontmatter name
    (e.g. `name: Error Resolver`). The DIR name is the invocation identity
    (`/error-resolver`), so the inventory keys by dir name — the join still
    counts hits, proposals emit valid paths — and the mismatch is a Hygiene
    finding."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=())
        _mk_skill(root, "error-resolver", frontmatter_name="Error Resolver")
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [_user_slash_turn("error-resolver")])
        rep = _report(root, logs)
        row = _usage_row(rep, "error-resolver")
        assert row is not None and row["slash"] == 1, rep["usage"]
        assert any(f["path"] == "user/skills/error-resolver"
                   and f["kind"] == "frontmatter-name-mismatch"
                   and "Error Resolver" in f["detail"]
                   for f in rep["hygiene"]), rep["hygiene"]


# ===========================================================================
# Phase 4 — toolify candidates (D7, annotate-only) + unknown invocations
# ===========================================================================

def test_toolify_candidate_threshold_boundary():
    """A skill at/above TOOLIFY_CANDIDATE_THRESHOLD total invocations is listed
    with the bar-doc cross-link; one below is not."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("hot", "cold"))
        logs = td / "projects"
        thr = sum_mod.TOOLIFY_CANDIDATE_THRESHOLD
        _write_jsonl(logs / "P" / "s1.jsonl",
                     [_user_slash_turn("hot") for _ in range(thr)]
                     + [_user_slash_turn("cold") for _ in range(thr - 1)])
        rep = _report(root, logs)
        names = {r["skill"] for r in rep["toolify_candidates"]}
        assert "hot" in names and "cold" not in names, rep["toolify_candidates"]
        hot = next(r for r in rep["toolify_candidates"] if r["skill"] == "hot")
        assert "toolify-bar.md" in hot["note"] and "toolify-miner.py" in hot["note"]
        md = sum_mod.render_markdown(rep)
        assert "## Toolify candidates" in md and "hot" in md


def test_unknown_invocations_surfaced_not_dropped():
    """A log-seen skill absent from the inventory lands in the Unknown
    invocations section with its per-detector counts."""
    _guard()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = _mk_repo_root(td, skills=("commit",))
        logs = td / "projects"
        _write_jsonl(logs / "P" / "s1.jsonl", [
            _user_slash_turn("ghost-skill"),
            _assistant_skill_turn("ghost-skill"),
            _user_slash_turn("commit"),
        ])
        rep = _report(root, logs)
        assert rep["unknown_invocations"] == [
            {"skill": "ghost-skill", "skill_tool": 1, "slash": 1}
        ], rep["unknown_invocations"]
        assert _usage_row(rep, "ghost-skill") is None
        md = sum_mod.render_markdown(rep)
        assert "ghost-skill — skill-tool 1, slash 1" in md


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
