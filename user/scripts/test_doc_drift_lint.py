"""Tests for doc-drift-lint.py (feature: doc-drift-linter).

Hermetic tmp-tree fixtures per check class: drift-present and clean cases,
divergence-marker exemption, malformed-input exit 2, plus a self-check that
THIS repo is clean.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent.parent
LINT_PATH = SCRIPTS_DIR / "doc-drift-lint.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("doc_drift_lint", LINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ddl():
    return _load_module()


def run_lint(repo_root):
    return subprocess.run(
        [sys.executable, str(LINT_PATH), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------

CLEAN_HOOKS_TABLE = """\
| Hook | Trigger | Purpose |
|------|---------|---------|
| `a-hook.sh` | PreToolUse (Bash) | blocks stuff |
| `multi-hook.sh` | PreToolUse (Bash, Agent, Skill) | containment |
| `pair-hook.sh` | PreToolUse (Write, Edit) | sentinel guard |
| `session-hook.sh` | SessionStart (startup, resume, clear, compact) | context loader |
| `unwired.ps1` | **NOT registered** (script exists; `user/settings.json` `PostToolUse` is `[]`) | manual normalizer |
"""

CLEAN_SCRIPTS_TABLE = """\
| Script | Purpose |
|--------|---------|
| `tool.py` | does things |
| `viz/` | dashboard package |
"""

CLEAN_PAIRS_TABLE = """\
| Pair | Files | Coupling rule |
|------|-------|---------------|
| `/a` ↔ `/a-cloud` | `user/skills/a/SKILL.md` ↔ `repos/x/.claude/skills/a-cloud/SKILL.md` | mirror both |
"""

CLEAN_SCRIPTS_DIR_TABLE = """\
| File | Role |
|------|------|
| `tool.py` | the thing |
"""

CLEAN_PSD1 = """\
@{
    User = @(
        @{ Live = '~\\.claude\\skills'; Repo = 'user\\skills'; Type = 'Directory' }
    )
    Repos = @{
        # ordinary comment
        'x' = @{
            Path           = 'C:\\repos\\x'
            DotClaudeFiles = @('settings.json', 'a.md')
            DotClaudeDirs  = @('skills')
        }
        'x-B' = @{
            Path  = 'C:\\repos\\x-B'
            Alias = 'x'
        }
    }
}
"""


def default_settings():
    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ~/.claude/hooks/session-hook.sh",
                        }
                    ],
                },
                {
                    "matcher": "compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash -c 'echo inline command, no hooks path'",
                        }
                    ],
                },
            ],
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "bash ~/.claude/hooks/a-hook.sh"},
                        {"type": "command", "command": "bash ~/.claude/hooks/multi-hook.sh"},
                    ],
                },
                {
                    "matcher": "Agent",
                    "hooks": [
                        {"type": "command", "command": "bash ~/.claude/hooks/multi-hook.sh"}
                    ],
                },
                {
                    "matcher": "Skill",
                    "hooks": [
                        {"type": "command", "command": "bash ~/.claude/hooks/multi-hook.sh"}
                    ],
                },
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {"type": "command", "command": "bash ~/.claude/hooks/pair-hook.sh"}
                    ],
                },
            ],
            "PostToolUse": [],
        }
    }


def make_repo(
    tmp_path,
    *,
    hooks_table=CLEAN_HOOKS_TABLE,
    scripts_table=CLEAN_SCRIPTS_TABLE,
    pairs_table=CLEAN_PAIRS_TABLE,
    pairs_section_extra="",
    scripts_dir_table=CLEAN_SCRIPTS_DIR_TABLE,
    settings=None,
    settings_text=None,
    psd1=CLEAN_PSD1,
    parity_pairs=None,
    parity_text=None,
    hook_files=("a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh"),
    script_files=("tool.py", "unwired.ps1"),
    script_dirs=("viz",),
    repo_dirs=("x",),
    root_claude=None,
):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    if root_claude is None:
        root_claude = (
            "# fixture repo\n\n"
            "## Hooks\n\nprose before table.\n\n" + hooks_table + "\n"
            "## Scripts\n\n" + scripts_table + "\n"
            "### Coupled Skill Pairs\n\n"
            + pairs_table
            + pairs_section_extra
            + "\n## Something Else\n"
        )
    (repo / "CLAUDE.md").write_text(root_claude, encoding="utf-8")

    user = repo / "user"
    (user / "hooks").mkdir(parents=True)
    for name in hook_files:
        (user / "hooks" / name).write_text("#!/bin/bash\n", encoding="utf-8")
    scripts = user / "scripts"
    scripts.mkdir()
    for name in script_files:
        (scripts / name).write_text("# fixture\n", encoding="utf-8")
    for name in script_dirs:
        (scripts / name).mkdir()
    (scripts / "CLAUDE.md").write_text(
        "# scripts\n\n## Files in this directory\n\n" + scripts_dir_table,
        encoding="utf-8",
    )
    if settings_text is None:
        settings_text = json.dumps(settings if settings is not None else default_settings())
    (user / "settings.json").write_text(settings_text, encoding="utf-8")

    if parity_text is None:
        if parity_pairs is None:
            parity_pairs = [
                {
                    "canonical": "user/skills/a/SKILL.md",
                    "derived": "repos/x/.claude/skills/a-cloud/SKILL.md",
                }
            ]
        parity_text = json.dumps({"pairs": parity_pairs})
    (scripts / "lazy-parity-manifest.json").write_text(parity_text, encoding="utf-8")

    (repo / "manifest.psd1").write_text(psd1, encoding="utf-8")
    repos = repo / "repos"
    repos.mkdir()
    (repos / "CLAUDE.md").write_text("# repos\n", encoding="utf-8")
    for name in repo_dirs:
        (repos / name).mkdir()
    return repo


# ---------------------------------------------------------------------------
# Clean tree / CLI contract
# ---------------------------------------------------------------------------


def test_clean_tree_exit_0(tmp_path):
    repo = make_repo(tmp_path)
    res = run_lint(repo)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 drift findings" in res.stdout


def test_output_is_byte_stable(tmp_path):
    repo = make_repo(tmp_path)
    a, b = run_lint(repo), run_lint(repo)
    assert a.stdout == b.stdout
    assert a.returncode == b.returncode


def test_summary_names_four_checks(tmp_path):
    repo = make_repo(tmp_path)
    res = run_lint(repo)
    assert "4 checks" in res.stdout


# ---------------------------------------------------------------------------
# Markdown table extraction (unit level)
# ---------------------------------------------------------------------------


def test_parse_markdown_tables_skips_separator_and_keeps_raw(ddl):
    text = "| A | B |\n|---|---|\n| `x.py` | y |\n"
    tables = ddl.parse_markdown_tables(text)
    assert len(tables) == 1
    rows = tables[0]
    assert rows[0].cells == ["A", "B"]
    assert rows[1].cells[0] == "`x.py`"
    assert "`x.py`" in rows[1].raw


def test_find_section_table_missing_heading_is_none(ddl):
    assert ddl.find_section_table("# nope\n", "## Hooks") is None


def test_backtick_tokens(ddl):
    assert ddl.backtick_tokens("`a/b.md` ↔ `c/d.md`") == ["a/b.md", "c/d.md"]


# ---------------------------------------------------------------------------
# Hooks check
# ---------------------------------------------------------------------------


def test_hooks_documented_but_unregistered(tmp_path):
    table = CLEAN_HOOKS_TABLE + "| `ghost.sh` | PreToolUse (Bash) | phantom |\n"
    repo = make_repo(tmp_path, hooks_table=table, hook_files=(
        "a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh", "ghost.sh"))
    res = run_lint(repo)
    assert res.returncode == 1
    assert "ghost.sh" in res.stdout
    assert "registered nowhere" in res.stdout


def test_hooks_registered_but_undocumented(tmp_path):
    settings = default_settings()
    settings["hooks"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": "bash ~/.claude/hooks/stealth.sh"}
    )
    repo = make_repo(tmp_path, settings=settings, hook_files=(
        "a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh", "stealth.sh"))
    res = run_lint(repo)
    assert res.returncode == 1
    assert "stealth.sh" in res.stdout
    assert "no Hooks-table row" in res.stdout


def test_hooks_matcher_mismatch(tmp_path):
    # doc claims Bash; register a-hook.sh under Read instead
    settings = default_settings()
    settings["hooks"]["PreToolUse"][0]["hooks"] = [
        {"type": "command", "command": "bash ~/.claude/hooks/multi-hook.sh"}
    ]
    settings["hooks"]["PreToolUse"].append(
        {
            "matcher": "Read",
            "hooks": [{"type": "command", "command": "bash ~/.claude/hooks/a-hook.sh"}],
        }
    )
    repo = make_repo(tmp_path, settings=settings)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "a-hook.sh" in res.stdout
    # message names both sides
    assert "Bash" in res.stdout and "Read" in res.stdout


def test_hooks_event_mismatch(tmp_path):
    settings = default_settings()
    # move session-hook.sh from SessionStart to PostToolUse
    settings["hooks"]["SessionStart"] = []
    settings["hooks"]["PostToolUse"] = [
        {
            "matcher": "startup|resume|clear|compact",
            "hooks": [
                {"type": "command", "command": "bash ~/.claude/hooks/session-hook.sh"}
            ],
        }
    ]
    repo = make_repo(tmp_path, settings=settings)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "session-hook.sh" in res.stdout
    assert "SessionStart" in res.stdout and "PostToolUse" in res.stdout


def test_hooks_not_registered_row_clean(tmp_path):
    repo = make_repo(tmp_path)
    res = run_lint(repo)
    assert res.returncode == 0  # unwired.ps1 stays clean while unregistered


def test_hooks_not_registered_row_actually_registered(tmp_path):
    settings = default_settings()
    settings["hooks"]["PostToolUse"] = [
        {
            "matcher": "Write",
            "hooks": [
                {"type": "command", "command": "pwsh ~/.claude/hooks/unwired.ps1"}
            ],
        }
    ]
    repo = make_repo(tmp_path, settings=settings)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "unwired.ps1" in res.stdout
    assert "NOT registered" in res.stdout


def test_hooks_documented_file_missing_on_disk(tmp_path):
    repo = make_repo(
        tmp_path,
        hook_files=("multi-hook.sh", "pair-hook.sh", "session-hook.sh"),  # a-hook.sh absent
    )
    res = run_lint(repo)
    assert res.returncode == 1
    assert "a-hook.sh" in res.stdout
    assert "disk" in res.stdout


def test_hooks_marker_exempts_row_but_not_siblings(tmp_path, ddl):
    marker = ddl.DIVERGENCE_MARKER
    table = (
        CLEAN_HOOKS_TABLE
        + f"| `ghost.sh` | PreToolUse (Bash) | phantom <!-- {marker}: wired live-only --> |\n"
    )
    repo = make_repo(tmp_path, hooks_table=table, hook_files=(
        "a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh", "ghost.sh"))
    res = run_lint(repo)
    assert res.returncode == 0
    assert "exempted" in res.stdout and "ghost.sh" in res.stdout
    # sibling drift on another row must still trip even with ghost.sh exempted
    table2 = table + "| `ghost2.sh` | PreToolUse (Bash) | phantom2 |\n"
    repo2 = make_repo(tmp_path / "second", hooks_table=table2, hook_files=(
        "a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh", "ghost.sh", "ghost2.sh"))
    res2 = run_lint(repo2)
    assert res2.returncode == 1
    assert "ghost2.sh" in res2.stdout


def test_hooks_registered_undocumented_exempt_via_section_comment(tmp_path, ddl):
    marker = ddl.DIVERGENCE_MARKER
    settings = default_settings()
    settings["hooks"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": "bash ~/.claude/hooks/stealth.sh"}
    )
    table = CLEAN_HOOKS_TABLE + f"\n<!-- {marker}: stealth.sh is intentionally undocumented -->\n"
    repo = make_repo(tmp_path, hooks_table=table, settings=settings, hook_files=(
        "a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh", "stealth.sh"))
    res = run_lint(repo)
    assert res.returncode == 0
    assert "exempted" in res.stdout


# ---------------------------------------------------------------------------
# Hooks check — multi-event hooks (a hook wired under >1 event)
# ---------------------------------------------------------------------------

# route.sh mirrors the real lazy-route-inject.sh: UserPromptSubmit (matches-all) +
# SessionStart matcher `compact` + PostCompact (matches-all).
MULTI_EVENT_HOOK_FILES = (
    "a-hook.sh", "multi-hook.sh", "pair-hook.sh", "session-hook.sh", "route.sh")


def multi_event_settings(*, events=("UserPromptSubmit", "SessionStart", "PostCompact")):
    """default_settings() plus route.sh registered under the given events."""
    settings = default_settings()
    cmd = {"type": "command", "command": "bash ~/.claude/hooks/route.sh"}
    if "UserPromptSubmit" in events:
        settings["hooks"]["UserPromptSubmit"] = [{"hooks": [dict(cmd)]}]
    if "SessionStart" in events:
        settings["hooks"]["SessionStart"].append(
            {"matcher": "compact", "hooks": [dict(cmd)]})
    if "PostCompact" in events:
        settings["hooks"]["PostCompact"] = [{"hooks": [dict(cmd)]}]
    return settings


# _fmt_events sort order (by event name): PostCompact, SessionStart, UserPromptSubmit.
MULTI_EVENT_ROW = (
    "| `route.sh` | PostCompact (*); SessionStart (compact); UserPromptSubmit (*) "
    "| multi-event injector |\n")


def test_hooks_multi_event_all_documented_clean(tmp_path):
    table = CLEAN_HOOKS_TABLE + MULTI_EVENT_ROW
    repo = make_repo(
        tmp_path, hooks_table=table, settings=multi_event_settings(),
        hook_files=MULTI_EVENT_HOOK_FILES)
    res = run_lint(repo)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 drift findings" in res.stdout


def test_hooks_multi_event_documented_event_not_registered(tmp_path):
    # doc lists all three, but PostCompact is NOT registered -> drift.
    table = CLEAN_HOOKS_TABLE + MULTI_EVENT_ROW
    repo = make_repo(
        tmp_path, hooks_table=table,
        settings=multi_event_settings(events=("UserPromptSubmit", "SessionStart")),
        hook_files=MULTI_EVENT_HOOK_FILES)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "route.sh" in res.stdout
    assert "PostCompact" in res.stdout
    assert "documented under events" in res.stdout


def test_hooks_multi_event_registered_event_not_documented(tmp_path):
    # settings register all three; doc omits PostCompact -> drift.
    row = ("| `route.sh` | SessionStart (compact); UserPromptSubmit (*) "
           "| multi-event injector |\n")
    table = CLEAN_HOOKS_TABLE + row
    repo = make_repo(
        tmp_path, hooks_table=table, settings=multi_event_settings(),
        hook_files=MULTI_EVENT_HOOK_FILES)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "route.sh" in res.stdout
    assert "PostCompact" in res.stdout


def test_hooks_multi_event_matcher_mismatch(tmp_path):
    # events match, but doc claims SessionStart (startup) while it is registered `compact`.
    row = ("| `route.sh` | PostCompact (*); SessionStart (startup); UserPromptSubmit (*) "
           "| multi-event injector |\n")
    table = CLEAN_HOOKS_TABLE + row
    repo = make_repo(
        tmp_path, hooks_table=table, settings=multi_event_settings(),
        hook_files=MULTI_EVENT_HOOK_FILES)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "route.sh" in res.stdout
    assert "startup" in res.stdout and "compact" in res.stdout
    assert "SessionStart" in res.stdout


# ---------------------------------------------------------------------------
# Scripts check
# ---------------------------------------------------------------------------


def test_scripts_documented_file_missing(tmp_path):
    table = CLEAN_SCRIPTS_TABLE + "| `gone.py` | vanished |\n"
    repo = make_repo(tmp_path, scripts_table=table)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "gone.py" in res.stdout


def test_scripts_dir_row_checks_directory(tmp_path):
    repo = make_repo(tmp_path, script_dirs=())  # viz/ documented but dir absent
    res = run_lint(repo)
    assert res.returncode == 1
    assert "viz/" in res.stdout


def test_scripts_dir_claude_table_checked(tmp_path):
    table = CLEAN_SCRIPTS_DIR_TABLE + "| `phantom.py` | gone |\n"
    repo = make_repo(tmp_path, scripts_dir_table=table)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "phantom.py" in res.stdout
    assert "user/scripts/CLAUDE.md" in res.stdout


def test_scripts_marker_exempts(tmp_path, ddl):
    marker = ddl.DIVERGENCE_MARKER
    table = CLEAN_SCRIPTS_TABLE + f"| `gone.py` | vanished <!-- {marker}: kept as doc row --> |\n"
    repo = make_repo(tmp_path, scripts_table=table)
    res = run_lint(repo)
    assert res.returncode == 0
    assert "exempted" in res.stdout


# ---------------------------------------------------------------------------
# Coupled-pairs check
# ---------------------------------------------------------------------------


def test_pairs_manifest_pair_missing_from_doc(tmp_path):
    pairs = [
        {
            "canonical": "user/skills/a/SKILL.md",
            "derived": "repos/x/.claude/skills/a-cloud/SKILL.md",
        },
        {"canonical": "user/skills/a/SKILL.md", "derived": "user/skills/a-bug/SKILL.md"},
    ]
    repo = make_repo(tmp_path, parity_pairs=pairs)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "a-bug/SKILL.md" in res.stdout
    assert "missing from" in res.stdout


def test_pairs_doc_pair_missing_from_manifest(tmp_path):
    table = (
        CLEAN_PAIRS_TABLE
        + "| `/b` ↔ `/b-cloud` | `user/skills/b/SKILL.md` ↔ `repos/x/.claude/skills/b-cloud/SKILL.md` | mirror |\n"
    )
    repo = make_repo(tmp_path, pairs_table=table)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "b/SKILL.md" in res.stdout


def test_pairs_unordered_match(tmp_path):
    # manifest reversed relative to doc order — still clean
    pairs = [
        {
            "canonical": "repos/x/.claude/skills/a-cloud/SKILL.md",
            "derived": "user/skills/a/SKILL.md",
        }
    ]
    repo = make_repo(tmp_path, parity_pairs=pairs)
    res = run_lint(repo)
    assert res.returncode == 0


def test_pairs_missing_row_exempt_via_section_comment(tmp_path, ddl):
    marker = ddl.DIVERGENCE_MARKER
    pairs = [
        {
            "canonical": "user/skills/a/SKILL.md",
            "derived": "repos/x/.claude/skills/a-cloud/SKILL.md",
        },
        {"canonical": "user/skills/a/SKILL.md", "derived": "user/skills/a-bug/SKILL.md"},
    ]
    extra = f"\n<!-- {marker}: user/skills/a-bug/SKILL.md tabulated elsewhere -->\n"
    repo = make_repo(tmp_path, parity_pairs=pairs, pairs_section_extra=extra)
    res = run_lint(repo)
    assert res.returncode == 0
    assert "exempted" in res.stdout


def test_pairs_malformed_manifest_json_exit_2(tmp_path):
    repo = make_repo(tmp_path, parity_text="{not json")
    res = run_lint(repo)
    assert res.returncode == 2


# ---------------------------------------------------------------------------
# Manifest check
# ---------------------------------------------------------------------------


def test_manifest_entry_without_dir(tmp_path):
    repo = make_repo(tmp_path, repo_dirs=())  # 'x' entry, no repos/x/
    res = run_lint(repo)
    assert res.returncode == 1
    assert "repos/x/" in res.stdout


def test_manifest_alias_needs_no_dir(tmp_path):
    repo = make_repo(tmp_path)  # x-B alias has no repos/x-B/ dir — clean
    res = run_lint(repo)
    assert res.returncode == 0


def test_manifest_alias_to_missing_key(tmp_path):
    psd1 = CLEAN_PSD1.replace("Alias = 'x'", "Alias = 'nope'")
    repo = make_repo(tmp_path, psd1=psd1)
    res = run_lint(repo)
    assert res.returncode == 1
    assert "nope" in res.stdout


def test_manifest_dir_without_entry(tmp_path):
    repo = make_repo(tmp_path, repo_dirs=("x", "orphan"))
    res = run_lint(repo)
    assert res.returncode == 1
    assert "orphan" in res.stdout


def test_manifest_dir_without_entry_exempt_via_psd1_comment(tmp_path, ddl):
    marker = ddl.DIVERGENCE_MARKER
    psd1 = CLEAN_PSD1.replace(
        "    Repos = @{",
        f"    # {marker}: orphan — dir kept deliberately\n    Repos = @{{",
    )
    repo = make_repo(tmp_path, psd1=psd1, repo_dirs=("x", "orphan"))
    res = run_lint(repo)
    assert res.returncode == 0
    assert "exempted" in res.stdout


def test_manifest_malformed_psd1_exit_2(tmp_path):
    psd1 = "@{\n    Repos = @{\n        'x' = @{\n"  # unbalanced
    repo = make_repo(tmp_path, psd1=psd1)
    res = run_lint(repo)
    assert res.returncode == 2


def test_manifest_missing_repos_block_exit_2(tmp_path):
    repo = make_repo(tmp_path, psd1="@{\n    User = @()\n}\n")
    res = run_lint(repo)
    assert res.returncode == 2


# ---------------------------------------------------------------------------
# Malformed inputs (shared)
# ---------------------------------------------------------------------------


def test_missing_settings_json_exit_2(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "user" / "settings.json").unlink()
    res = run_lint(repo)
    assert res.returncode == 2


def test_bad_settings_json_exit_2(tmp_path):
    repo = make_repo(tmp_path, settings_text="{broken")
    res = run_lint(repo)
    assert res.returncode == 2


def test_missing_hooks_heading_exit_2(tmp_path):
    repo = make_repo(tmp_path)
    text = (repo / "CLAUDE.md").read_text(encoding="utf-8").replace("## Hooks", "## Hoax")
    (repo / "CLAUDE.md").write_text(text, encoding="utf-8")
    res = run_lint(repo)
    assert res.returncode == 2


def test_missing_root_claude_exit_2(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "CLAUDE.md").unlink()
    res = run_lint(repo)
    assert res.returncode == 2


# ---------------------------------------------------------------------------
# --live mode (WU-5)
#
# NOT YET IMPLEMENTED — these tests are RED by design (strict TDD). They pin
# the contract for a new `check_live_settings` / `live_settings_status` API
# plus a `--live`/`--live-path` CLI surface on doc-drift-lint.py, none of
# which exist yet. They will go GREEN once the impl agent adds the API.
# ---------------------------------------------------------------------------


def run_lint_live(repo_root, live_path):
    return subprocess.run(
        [
            sys.executable,
            str(LINT_PATH),
            "--repo-root",
            str(repo_root),
            "--live",
            "--live-path",
            str(live_path),
        ],
        capture_output=True,
        text=True,
    )


def test_live_symlink_to_tracked_is_clean(ddl, tmp_path):
    repo = make_repo(tmp_path)
    tracked = repo / "user" / "settings.json"
    live_dir = tmp_path / "live-symlink-tracked"
    live_dir.mkdir()
    live_path = live_dir / "settings.json"
    try:
        os.symlink(tracked, live_path)
    except OSError:
        pytest.skip("symlinks unavailable on this host")

    findings = ddl.check_live_settings(repo, live_path)
    assert findings == []

    ok, detail = ddl.live_settings_status(repo, live_path)
    assert ok is True, detail

    res = run_lint_live(repo, live_path)
    assert res.returncode == 0, res.stdout + res.stderr


def test_live_real_file_content_differs_is_drift(ddl, tmp_path):
    repo = make_repo(tmp_path)
    tracked = repo / "user" / "settings.json"
    live_dir = tmp_path / "live-content-differs"
    live_dir.mkdir()
    live_path = live_dir / "settings.json"

    tracked_obj = json.loads(tracked.read_text(encoding="utf-8"))
    live_obj = json.loads(tracked.read_text(encoding="utf-8"))
    live_obj["hooks"]["PreToolUse"][0]["hooks"][0]["command"] += " --extra-flag"
    assert live_obj != tracked_obj  # sanity: genuinely different content
    live_path.write_text(json.dumps(live_obj), encoding="utf-8")

    findings = ddl.check_live_settings(repo, live_path)
    assert len(findings) >= 1
    assert all(f.check == "live" for f in findings)
    combined = " ".join(f.message.lower() for f in findings)
    assert "setup" in combined
    assert "repair" in combined

    ok, detail = ddl.live_settings_status(repo, live_path)
    assert ok is False, detail

    res = run_lint_live(repo, live_path)
    assert res.returncode == 1, res.stdout + res.stderr


def test_live_symlink_to_other_target_is_drift(ddl, tmp_path):
    repo = make_repo(tmp_path)
    other = tmp_path / "other-settings.json"
    other.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    live_dir = tmp_path / "live-symlink-other"
    live_dir.mkdir()
    live_path = live_dir / "settings.json"
    try:
        os.symlink(other, live_path)
    except OSError:
        pytest.skip("symlinks unavailable on this host")

    findings = ddl.check_live_settings(repo, live_path)
    assert len(findings) >= 1

    ok, detail = ddl.live_settings_status(repo, live_path)
    assert ok is False, detail

    res = run_lint_live(repo, live_path)
    assert res.returncode == 1, res.stdout + res.stderr


def test_live_real_file_identical_content_is_pass(ddl, tmp_path):
    """Copy-based / cloud-host case: a real (non-symlink) file whose content is
    byte-identical to TRACKED is a legitimate pass, NOT drift."""
    repo = make_repo(tmp_path)
    tracked = repo / "user" / "settings.json"
    live_dir = tmp_path / "live-identical-copy"
    live_dir.mkdir()
    live_path = live_dir / "settings.json"
    live_path.write_bytes(tracked.read_bytes())

    findings = ddl.check_live_settings(repo, live_path)
    assert findings == []

    ok, detail = ddl.live_settings_status(repo, live_path)
    assert ok is True, detail

    res = run_lint_live(repo, live_path)
    assert res.returncode == 0, res.stdout + res.stderr


def test_live_missing_file_is_drift(ddl, tmp_path):
    repo = make_repo(tmp_path)
    live_path = tmp_path / "live-missing" / "settings.json"  # parent never created

    findings = ddl.check_live_settings(repo, live_path)
    assert len(findings) >= 1

    ok, detail = ddl.live_settings_status(repo, live_path)
    assert ok is False, detail

    res = run_lint_live(repo, live_path)
    assert res.returncode == 1, res.stdout + res.stderr


def test_live_flag_absent_stays_exit_0_on_clean_tree(tmp_path):
    """Leak guard: --live must be opt-in. A clean fixture with no --live flag
    stays exit 0 regardless of what a real live settings.json would say."""
    repo = make_repo(tmp_path)
    res = run_lint(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_live_check_name_not_in_default_check_names(ddl):
    assert "live" not in ddl.CHECK_NAMES


def test_default_run_checks_never_emits_live_finding(ddl):
    """The default check tuple must never fold in the live check — referencing
    the new function object directly (not just its absence from CHECK_NAMES)
    so this fails loudly (AttributeError) until the API exists, and keeps
    failing if it is ever silently added to the default run_checks() walk."""
    assert ddl.check_live_settings not in (
        ddl.check_hooks,
        ddl.check_scripts,
        ddl.check_coupled_pairs,
        ddl.check_manifest,
    )
    findings = ddl.run_checks(REPO_ROOT)
    assert not any(f.check == "live" for f in findings)


# ---------------------------------------------------------------------------
# Self-check: this repo must be drift-clean (Phase 2 acceptance — WU-2.3)
# ---------------------------------------------------------------------------


def test_this_repo_is_clean():
    """The linter gates its own home: any genuine doc drift in claude-config fails here.

    Deliberate divergences carry DIVERGENCE_MARKER (currently: the algobooth
    Repos-entry omission in manifest.psd1) and do not affect the exit code.
    """
    res = run_lint(REPO_ROOT)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "0 drift findings" in res.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
