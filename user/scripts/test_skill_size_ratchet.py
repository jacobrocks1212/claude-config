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


# ---------------------------------------------------------------------------
# Standing anti-bloat guard — war-story detector + per-section ceiling
# (cycle-prompt-residual-deflation-and-bloat-guard Phase 2, D1-D4)
# ---------------------------------------------------------------------------

# A minimal dispatched-prompt template (real @section grammar) the emitter parses.
_CLEAN_SECTION = (
    "<!-- @section role pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
    "You are running a cycle. Do the work and commit. No provenance here.\n"
)


def _war_story_template(body_line: str) -> str:
    """A dispatched-prompt template whose one selectable section body carries
    *body_line* as EMITTED prose (not a comment)."""
    return (
        "leading metadata dropped before the first @section marker\n"
        "<!-- @section role pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
        f"{body_line}\n"
    )


def test_war_story_flags_iso_date(tmp_path):
    findings = ratchet.scan_war_stories(
        _war_story_template("Fixed since 2026-06-15 in the recovery path."),
        "dispatch-recovery.md",
    )
    assert any(f["shape"] == "iso-date" and f["file"] == "dispatch-recovery.md"
               for f in findings), findings
    assert any(f["match"] == "2026-06-15" for f in findings)


def test_war_story_flags_issue_round_and_d8(tmp_path):
    for body, expect in (
        ("Do X (HARD — ISSUE 2, blah).", "ISSUE 2"),
        ("Per Round 44 the route broke.", "Round 44"),
        ("Burned on the d8-effect-chains run.", "d8-effect-chains"),
    ):
        findings = ratchet.scan_war_stories(_war_story_template(body), "cycle-base-prompt.md")
        assert any(f["shape"] == "issue-round-marker" for f in findings), (body, findings)
        assert any(f["match"] == expect for f in findings), (body, findings)


def test_war_story_flags_live_incident(tmp_path):
    findings = ratchet.scan_war_stories(
        _war_story_template("(Live incident: the subagent died resultless.)"),
        "cycle-base-prompt.md",
    )
    assert any(f["shape"] == "live-incident" for f in findings), findings


def test_war_story_flags_bare_docs_incident_literal(tmp_path):
    findings = ratchet.scan_war_stories(
        _war_story_template("This exists because of docs/bugs/some-incident-slug."),
        "dispatch-recovery.md",
    )
    assert any(f["shape"] == "docs-incident-literal" for f in findings), findings
    assert any(f["match"].startswith("docs/bugs/some-incident-slug") for f in findings)


def test_war_story_operational_docs_path_not_flagged(tmp_path):
    """A legit operational reference into a features/bugs dir (a doc FILE, not a
    bare incident-dir literal) is NOT a war-story — shape 4 is bare-dir-only."""
    findings = ratchet.scan_war_stories(
        _war_story_template("Verify against docs/features/mcp-testing/SPEC.md first."),
        "cycle-base-prompt.md",
    )
    assert findings == [], findings


def test_war_story_provenance_in_comment_not_flagged(tmp_path):
    """War-story provenance living in an HTML comment inside a section body is
    NOT dispatched-as-imperative-prose — the emitter emits it but the contract
    permits WHY-in-comments, so the detector excludes comment spans."""
    template = (
        "<!-- @section role pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
        "Do the work. <!-- history: burned on 2026-06-14, ISSUE 3 -->\n"
    )
    assert ratchet.scan_war_stories(template, "cycle-base-prompt.md") == []


def test_war_story_multiline_authoring_comment_not_flagged(tmp_path):
    """A multi-line leading authoring comment (research-halt-announcement.md
    shape) is stripped wholesale — an interior 'Burned on d8-effect-chains,
    2026-06-14' line does not leak into the scan."""
    template = (
        "# title\n"
        "<!-- big authoring note\n"
        "     spanning lines\n"
        "     Burned on d8-effect-chains, 2026-06-14. -->\n"
        "```\nOperator-facing block, no provenance.\n```\n"
    )
    assert ratchet.scan_war_stories(template, "research-halt-announcement.md") == []


def test_war_story_allowlist_rescues_load_bearing_literal(tmp_path):
    """A reason-required inline allowlist marker rescues a genuine load-bearing
    literal that would otherwise match a shape; an EMPTY reason does not."""
    rescued = (
        "<!-- @section role pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
        "See docs/bugs/known-canonical-dir <!-- war-story-allow: canonical dir, load-bearing not incident -->\n"
    )
    assert ratchet.scan_war_stories(rescued, "cycle-base-prompt.md") == []

    empty_reason = (
        "<!-- @section role pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
        "See docs/bugs/known-canonical-dir <!-- war-story-allow: -->\n"
    )
    assert ratchet.scan_war_stories(empty_reason, "cycle-base-prompt.md") != []


def test_war_story_never_selected_section_not_flagged(tmp_path):
    """A DORMANT / never-selected @section (a modes value the emitter can never
    dispatch) is NOT scanned — the detector honors emitter selectability."""
    template = (
        "<!-- @section live pipelines=feature,bug modes=workstation,cloud skills=all -->\n"
        "Clean imperative rule.\n"
        "<!-- @section ghost pipelines=feature,bug modes=disabled skills=all -->\n"
        "Never dispatched: Live incident: 2026-01-01 Round 9 d8-effect-chains.\n"
    )
    assert ratchet.scan_war_stories(template, "cycle-base-prompt.md") == []


def test_check_war_stories_scope_excludes_skills_and_docs(tmp_path):
    """Scope = dispatched-prompt template family ONLY. An ordinary SKILL.md or a
    docs/ file carrying a date/incident literal is NOT flagged."""
    repo = tmp_path / "repo"
    fam = repo / "user/skills/_components/lazy-batch-prompts"
    fam.mkdir(parents=True)
    (fam / "cycle-base-prompt.md").write_text(_CLEAN_SECTION, encoding="utf-8")
    # Ordinary skill + docs carrying obvious war-story shapes — MUST be ignored.
    (repo / "user/skills/some-skill").mkdir(parents=True)
    (repo / "user/skills/some-skill/SKILL.md").write_text(
        "Landed 2026-06-15 in Round 5. Live incident: docs/bugs/x-y-z.\n", encoding="utf-8"
    )
    (repo / "docs/bugs/foo").mkdir(parents=True)
    (repo / "docs/bugs/foo/SPEC.md").write_text("Discovered 2026-07-20.\n", encoding="utf-8")
    assert ratchet.check_war_stories(repo) == []


def test_check_war_stories_excludes_family_claude_md(tmp_path):
    """The lazy-batch-prompts/CLAUDE.md contract doc necessarily QUOTES the
    detector patterns — it is excluded from the scan (a self-match)."""
    repo = tmp_path / "repo"
    fam = repo / "user/skills/_components/lazy-batch-prompts"
    fam.mkdir(parents=True)
    (fam / "cycle-base-prompt.md").write_text(_CLEAN_SECTION, encoding="utf-8")
    (fam / "CLAUDE.md").write_text(
        "The lint flags Live incident: / 2026-06-14 / Round 3 / d8-effect-chains / "
        "docs/bugs/some-slug shapes.\n", encoding="utf-8"
    )
    assert ratchet.check_war_stories(repo) == []


def test_check_war_stories_flags_family_file(tmp_path):
    """A dispatched-prompt template in the family carrying an emitted war-story
    IS flagged, named by file."""
    repo = tmp_path / "repo"
    fam = repo / "user/skills/_components/lazy-batch-prompts"
    fam.mkdir(parents=True)
    (fam / "dispatch-recovery.md").write_text(
        "<!-- @section role pipelines=feature,bug modes=workstation,cloud -->\n"
        "Reconcile since the 2026-06-15 review.\n", encoding="utf-8"
    )
    findings = ratchet.check_war_stories(repo)
    assert any(f["file"] == "dispatch-recovery.md" and f["shape"] == "iso-date"
               for f in findings), findings


# --- per-section byte ceiling ----------------------------------------------

def _sectioned_baseline(sections: dict) -> dict:
    return {"schema_version": 1, "files": {}, "sections": sections}


def test_check_sections_flags_over_ceiling(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    # _write_fixture_template's base has a "task" section (skills=all) + "execute".
    baseline = _sectioned_baseline({
        "task": {"byte_ceiling": 1, "long_line_ceiling": 0},
    })
    findings = ratchet.check_sections(tmp_path, baseline, template_dir=tdir)
    assert len(findings) == 1
    assert findings[0]["section"] == "task"
    assert findings[0]["metric"] == "byte_ceiling"
    assert findings[0]["current"] > findings[0]["ceiling"]


def test_check_sections_clean_when_within_ceiling(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    baseline = _sectioned_baseline({
        "task": {"byte_ceiling": 100000, "long_line_ceiling": 50},
    })
    assert ratchet.check_sections(tmp_path, baseline, template_dir=tdir) == []


def test_check_sections_skips_metadata_keys(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    baseline = _sectioned_baseline({"_notes": "meta"})
    assert ratchet.check_sections(tmp_path, baseline, template_dir=tdir) == []


def test_lock_in_section_only_lowers(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    bp = tmp_path / "baseline.json"
    baseline = _sectioned_baseline({"task": {"byte_ceiling": 100000, "long_line_ceiling": 50}})
    lowered = ratchet.lock_in_section(tmp_path, bp, baseline, "task", template_dir=tdir)
    assert lowered["action"] == "lowered"
    assert lowered["byte_ceiling"] < 100000
    baseline2 = _sectioned_baseline({"task": {"byte_ceiling": 1, "long_line_ceiling": 0}})
    noop = ratchet.lock_in_section(tmp_path, bp, baseline2, "task", template_dir=tdir)
    assert noop["action"] == "noop"
    assert baseline2["sections"]["task"]["byte_ceiling"] == 1


def test_lock_in_section_seeds_new_only_with_flag(tmp_path):
    tdir = _write_fixture_template(tmp_path)
    bp = tmp_path / "baseline.json"
    baseline = _sectioned_baseline({})
    refused = ratchet.lock_in_section(tmp_path, bp, baseline, "task", template_dir=tdir)
    assert refused["action"] == "refused"
    seeded = ratchet.lock_in_section(tmp_path, bp, baseline, "task", seed_new=True, template_dir=tdir)
    assert seeded["action"] == "seeded"
    assert baseline["sections"]["task"]["byte_ceiling"] == seeded["byte_ceiling"]


def test_real_family_war_stories_clean():
    """Live self-check: the real dispatched-prompt template family carries no
    emitted war-story prose (the family-wide cleanup landed)."""
    repo_root = _SCRIPTS_DIR.resolve().parents[1]
    findings = ratchet.check_war_stories(repo_root)
    assert findings == [], f"real-family war-story findings: {findings}"


def test_real_baseline_sections_clean():
    """Live self-check: every seeded cycle-base @section is within its ceiling."""
    repo_root = _SCRIPTS_DIR.resolve().parents[1]
    baseline = ratchet.load_baseline(ratchet.default_baseline_path())
    assert baseline.get("sections"), "real baseline carries no per-section ceilings"
    findings = ratchet.check_sections(repo_root, baseline)
    assert findings == [], f"real-repo per-section findings: {findings}"
