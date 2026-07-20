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


# ---------------------------------------------------------------------------
# Assembled-cycle-prompt profile measurement (cycle-prompt-deflation Phase 1)
# ---------------------------------------------------------------------------

def _write_fixture_template(tmp_path: Path, *, with_unbound: bool = False) -> Path:
    """Write a minimal sectioned cycle-base-prompt.md the real emitter parses.

    Uses ONLY bindable tokens ({item_id}/{sub_skill}/{work_branch}/{cwd}/
    {sub_skill_args}) unless with_unbound is set (then a genuine unbound token is
    injected so the emitter's residue guard refuses)."""
    tdir = tmp_path / "lazy-batch-prompts"
    tdir.mkdir(parents=True, exist_ok=True)
    extra = " {this_token_is_not_bound}" if with_unbound else ""
    (tdir / "cycle-base-prompt.md").write_text(
        "template metadata before the first section\n"
        "<!-- @section task pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
        f"Task {{item_id}}: run {{sub_skill}} on {{work_branch}}.{extra}\n"
        "<!-- @section execute pipelines=feature,bug modes=workstation skills=execute-plan -->\n"
        "Execute {sub_skill_args} at {cwd}.\n",
        encoding="utf-8",
    )
    return tdir


def test_enumerate_profiles_derives_from_matrix(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    profiles = ratchet.enumerate_profiles(tdir)
    ids = {ratchet._profile_id(p) for p in profiles}
    # 4 generic (skills=all shape) + execute-plan where its workstation section matches.
    assert "feature/workstation/spec-phases" in ids   # generic shape
    assert "bug/cloud/spec-phases" in ids
    assert "feature/workstation/execute-plan" in ids
    assert "bug/workstation/execute-plan" in ids
    # execute section is workstation-only → no cloud execute-plan profile.
    assert "feature/cloud/execute-plan" not in ids


def test_measure_assembled_profile_positive_bytes(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    profile = {"pipeline": "feature", "mode": "workstation", "skill": "execute-plan"}
    byte_count, long_lines, note = ratchet.measure_assembled_profile(
        tmp_path, profile, template_dir=tdir
    )
    assert note is None
    assert byte_count > 0
    assert long_lines == 0


def test_measure_assembled_profile_refuse_surfaced_honestly(tmp_path):
    """An emitter refusal is reported as (None, None, note) — never a bogus 0."""
    tdir = _write_fixture_template(tmp_path, with_unbound=True)
    profile = {"pipeline": "feature", "mode": "workstation", "skill": "execute-plan"}
    byte_count, long_lines, note = ratchet.measure_assembled_profile(
        tmp_path, profile, template_dir=tdir
    )
    assert byte_count is None
    assert long_lines is None
    assert note and "refused" in note


def test_measure_assembled_profile_is_repo_root_independent(tmp_path):
    """The measurement must not vary with the repo path (deterministic ceilings)."""
    tdir = _write_fixture_template(tmp_path)
    profile = {"pipeline": "feature", "mode": "workstation", "skill": "execute-plan"}
    a = ratchet.measure_assembled_profile(Path("/short"), profile, template_dir=tdir)
    b = ratchet.measure_assembled_profile(
        Path("/a/much/longer/checkout/path/root"), profile, template_dir=tdir
    )
    assert a == b


def test_check_profiles_flags_over_ceiling(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    baseline = {
        "schema_version": 1, "files": {},
        "profiles": {
            "feature/workstation/execute-plan": {"byte_ceiling": 1, "long_line_ceiling": 0},
        },
    }
    findings = ratchet.check_profiles(tmp_path, baseline, template_dir=tdir)
    assert len(findings) == 1
    assert findings[0]["profile"] == "feature/workstation/execute-plan"
    assert findings[0]["metric"] == "byte_ceiling"
    assert findings[0]["current"] > findings[0]["ceiling"]


def test_check_profiles_skips_metadata_keys(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    baseline = {"schema_version": 1, "files": {}, "profiles": {"_notes": "meta"}}
    # An `_`-prefixed key must never be parsed as a profile id (no crash).
    assert ratchet.check_profiles(tmp_path, baseline, template_dir=tdir) == []


def test_lock_in_profile_only_lowers(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    bp = tmp_path / "baseline.json"
    pid = "feature/workstation/execute-plan"
    baseline = {
        "schema_version": 1, "files": {},
        "profiles": {pid: {"byte_ceiling": 100000, "long_line_ceiling": 50}},
    }
    lowered = ratchet.lock_in_profile(tmp_path, bp, baseline, pid, template_dir=tdir)
    assert lowered["action"] == "lowered"
    assert lowered["byte_ceiling"] < 100000
    # A profile already at/below its (tiny) ceiling never raises it.
    baseline2 = {
        "schema_version": 1, "files": {},
        "profiles": {pid: {"byte_ceiling": 1, "long_line_ceiling": 0}},
    }
    noop = ratchet.lock_in_profile(tmp_path, bp, baseline2, pid, template_dir=tdir)
    assert noop["action"] == "noop"
    assert baseline2["profiles"][pid]["byte_ceiling"] == 1


def test_lock_in_profile_seeds_new_only_with_flag(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    bp = tmp_path / "baseline.json"
    pid = "feature/workstation/execute-plan"
    baseline = {"schema_version": 1, "files": {}, "profiles": {}}
    refused = ratchet.lock_in_profile(tmp_path, bp, baseline, pid, template_dir=tdir)
    assert refused["action"] == "refused"
    seeded = ratchet.lock_in_profile(tmp_path, bp, baseline, pid, seed_new=True, template_dir=tdir)
    assert seeded["action"] == "seeded"
    assert baseline["profiles"][pid]["byte_ceiling"] == seeded["byte_ceiling"]


def test_real_baseline_profiles_are_clean():
    """Live self-check: every seeded assembled profile is within its ceiling on
    the real committed baseline + template (the assembled analog of the per-file
    self-check above)."""
    repo_root = _SCRIPTS_DIR.resolve().parents[1]
    baseline = ratchet.load_baseline(ratchet.default_baseline_path())
    assert baseline.get("profiles"), "real baseline carries no assembled profiles"
    findings = ratchet.check_profiles(repo_root, baseline)
    assert findings == [], f"real-repo assembled-profile findings: {findings}"
