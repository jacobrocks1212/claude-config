"""Tests for skill-size-ratchet.py (lazy-batch-skill-deflation Phase 3, D3).

Hermetic: every test writes fixture skill files + a fixture baseline JSON under
tmp_path, never touching the real repo tree or the real skill-size-baseline.json.
"""

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "skill_size_ratchet", _SCRIPTS_DIR / "skill-size-ratchet.py"
)
ratchet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratchet)


def _write_skill(repo_root: Path, rel_path: str, text: str) -> None:
    full = repo_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")


def _baseline(files: dict) -> dict:
    return {"schema_version": 1, "files": files}


def test_check_clean_when_within_ceilings(tmp_path):
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/foo/SKILL.md", "short line\n" * 5)
    baseline = _baseline({
        "user/skills/foo/SKILL.md": {"byte_ceiling": 1000, "long_line_ceiling": 0},
    })
    findings = ratchet.check(repo, baseline)
    assert findings == []


def test_check_flags_byte_ceiling_regression(tmp_path):
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/foo/SKILL.md", "x" * 2000)
    baseline = _baseline({
        "user/skills/foo/SKILL.md": {"byte_ceiling": 1000, "long_line_ceiling": 5},
    })
    findings = ratchet.check(repo, baseline)
    assert len(findings) == 1
    assert findings[0]["file"] == "user/skills/foo/SKILL.md"
    assert findings[0]["metric"] == "byte_ceiling"
    assert findings[0]["current"] > findings[0]["ceiling"]


def test_check_flags_long_line_ceiling_regression(tmp_path):
    repo = tmp_path / "repo"
    long_line = "y" * 600
    _write_skill(repo, "user/skills/foo/SKILL.md", long_line + "\n" + long_line + "\n")
    baseline = _baseline({
        "user/skills/foo/SKILL.md": {"byte_ceiling": 100000, "long_line_ceiling": 1},
    })
    findings = ratchet.check(repo, baseline)
    assert len(findings) == 1
    assert findings[0]["metric"] == "long_line_ceiling"
    assert findings[0]["current"] == 2
    assert findings[0]["ceiling"] == 1


def test_check_flags_missing_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    baseline = _baseline({
        "user/skills/gone/SKILL.md": {"byte_ceiling": 100, "long_line_ceiling": 0},
    })
    findings = ratchet.check(repo, baseline)
    assert len(findings) == 1
    assert findings[0]["metric"] == "missing"


def test_check_ignores_files_not_in_baseline_opt_in(tmp_path):
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/untracked/SKILL.md", "x" * 999999)
    baseline = _baseline({})
    findings = ratchet.check(repo, baseline)
    assert findings == []


def test_lock_in_lowers_ceiling_on_improvement(tmp_path):
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/foo/SKILL.md", "short\n")
    baseline_path = tmp_path / "baseline.json"
    baseline = _baseline({
        "user/skills/foo/SKILL.md": {"byte_ceiling": 100000, "long_line_ceiling": 50},
    })
    result = ratchet.lock_in(repo, baseline_path, baseline, "user/skills/foo/SKILL.md")
    assert result["action"] == "lowered"
    assert result["byte_ceiling"] < 100000
    assert result["long_line_ceiling"] == 0
    # Persisted to disk.
    on_disk = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert on_disk["files"]["user/skills/foo/SKILL.md"]["byte_ceiling"] == result["byte_ceiling"]


def test_lock_in_never_raises_ceiling(tmp_path):
    """A file that GREW past its ceiling must not have --lock-in bail it out by
    raising the ceiling to match — that would defeat the entire ratchet."""
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/foo/SKILL.md", "x" * 5000)
    baseline_path = tmp_path / "baseline.json"
    baseline = _baseline({
        "user/skills/foo/SKILL.md": {"byte_ceiling": 1000, "long_line_ceiling": 0},
    })
    result = ratchet.lock_in(repo, baseline_path, baseline, "user/skills/foo/SKILL.md")
    # min(current=5000, existing=1000) == 1000 -> unchanged -> noop, never 5000.
    assert result["action"] == "noop"
    on_disk_ceiling = baseline["files"]["user/skills/foo/SKILL.md"]["byte_ceiling"]
    assert on_disk_ceiling == 1000


def test_lock_in_refuses_unlisted_file_without_new_flag(tmp_path):
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/foo/SKILL.md", "short\n")
    baseline_path = tmp_path / "baseline.json"
    baseline = _baseline({})
    result = ratchet.lock_in(repo, baseline_path, baseline, "user/skills/foo/SKILL.md")
    assert result["action"] == "refused"


def test_lock_in_seeds_new_file_with_new_flag(tmp_path):
    repo = tmp_path / "repo"
    _write_skill(repo, "user/skills/foo/SKILL.md", "short\n")
    baseline_path = tmp_path / "baseline.json"
    baseline = _baseline({})
    result = ratchet.lock_in(repo, baseline_path, baseline, "user/skills/foo/SKILL.md", seed_new=True)
    assert result["action"] == "seeded"
    assert baseline["files"]["user/skills/foo/SKILL.md"]["byte_ceiling"] == result["byte_ceiling"]


def test_load_baseline_missing_file_returns_empty_schema(tmp_path):
    baseline = ratchet.load_baseline(tmp_path / "does-not-exist.json")
    assert baseline == {"schema_version": ratchet.SCHEMA_VERSION, "files": {}}


def test_load_baseline_malformed_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"not_files": {}}), encoding="utf-8")
    try:
        ratchet.load_baseline(p)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_real_baseline_and_repo_are_clean():
    """The gate must actually pass on the real committed baseline + repo tree —
    this is the fixture that would catch the ratchet lying about its own subject."""
    repo_root = _SCRIPTS_DIR.resolve().parents[1]
    baseline = ratchet.load_baseline(ratchet.default_baseline_path())
    findings = ratchet.check(repo_root, baseline)
    assert findings == [], f"real-repo ratchet findings: {findings}"
