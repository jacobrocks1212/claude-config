#!/usr/bin/env python3
"""Tests for harness-gate.py — the anti-overfit-design-gate mechanical checker.

Feature: anti-overfit-design-gate. Fixtures feed synthetic unified-diff text directly to the
pure detector functions (no real git repo needed) and assert each detector's classification,
including the two NAMED historical regression fixtures the SPEC mandates:
  - the `_VERIFICATION_SECTION_RE` phrase-append (overfit);
  - the GAP-2-shaped exemption-add + gate-test deletion (gate_weakening).
"""

import importlib.util
import json
from pathlib import Path

import pytest

_HG_PATH = Path(__file__).with_name("harness-gate.py")
_spec = importlib.util.spec_from_file_location("harness_gate", _HG_PATH)
hg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hg)


# --- helpers ----------------------------------------------------------------------

def _diff(file: str, added=(), removed=(), context=()):
    """Build a minimal one-hunk unified diff for `file`."""
    lines = [
        f"diff --git a/{file} b/{file}",
        f"--- a/{file}",
        f"+++ b/{file}",
        "@@ -1,3 +1,4 @@",
    ]
    for c in context:
        lines.append(" " + c)
    for r in removed:
        lines.append("-" + r)
    for a in added:
        lines.append("+" + a)
    return "\n".join(lines) + "\n"


DEFAULT_GLOBS = [
    "user/hooks/**",
    "user/scripts/lazy_core.py",
    "user/scripts/lazy-state.py",
    "user/skills/lazy*/**",
    "user/scripts/harness-gate.py",
]


# --- scope trigger (SPEC Validation row 1) ---------------------------------------

def test_scope_in_when_manifest_path_touched():
    hits = hg.scope_hits(["user/scripts/lazy_core.py", "README.md"], DEFAULT_GLOBS)
    assert hits == ["user/scripts/lazy_core.py"]


def test_scope_out_when_no_manifest_path_touched():
    hits = hg.scope_hits(["src/components/Foo.vue", "docs/notes.md"], DEFAULT_GLOBS)
    assert hits == []


def test_glob_double_star_spans_dirs():
    assert hg._glob_match("user/hooks/lazy-cycle-containment.sh", "user/hooks/**")
    assert hg._glob_match("user/skills/lazy-batch/SKILL.md", "user/skills/lazy*/**")
    assert not hg._glob_match("user/skills/spec/SKILL.md", "user/skills/lazy*/**")


def test_out_of_scope_result_shape_and_no_verdict():
    res = hg.run_checker(Path("."), _diff("README.md", added=["hi"]), ["README.md"], None, DEFAULT_GLOBS)
    assert res["in_scope"] is False
    assert res["verdict_required"] is False
    assert res["checks"] == {}


# --- overfit detector (SPEC Validation row 2) ------------------------------------

def test_overfit_verification_section_re_phrase_append():
    """NAMED FIXTURE: another `|seam\\s+audit` alternative appended to _VERIFICATION_SECTION_RE."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        context=["_VERIFICATION_SECTION_RE = re.compile("],
        removed=[r'    r"runtime\s+verification|integration\s+test"'],
        added=[r'    r"runtime\s+verification|integration\s+test|seam\s+audit"'],
    )
    out = hg.detect_overfit(hg.parse_diff(diff))
    assert out["result"] == "flag"
    assert any("alternation" in e for e in out["evidence"])


def test_overfit_list_element_append_flags():
    diff = _diff(
        "user/scripts/lazy_core.py",
        context=["SOME_SET = {", "    'existing-one',"],
        added=["    'new-literal-element',"],
    )
    out = hg.detect_overfit(hg.parse_diff(diff))
    assert out["result"] == "flag"


def test_overfit_incident_slug_literal_flags():
    diff = _diff(
        "user/scripts/lazy-state.py",
        added=['    if slug == "docs/bugs/adhoc-fix-probe-cache":'],
    )
    out = hg.detect_overfit(hg.parse_diff(diff))
    assert out["result"] == "flag"
    assert any("incident-shaped" in e for e in out["evidence"])


def test_overfit_structural_change_passes():
    """A structural refactor (no literal appended to a matcher) does NOT flag."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        added=["    return _classify(value) if value else DEFAULT"],
    )
    out = hg.detect_overfit(hg.parse_diff(diff))
    assert out["result"] == "pass"


# --- gate-weakening detector (SPEC Validation row 3) -----------------------------

def test_gate_weakening_gap2_exemption_add_plus_test_deletion():
    """NAMED FIXTURE: GAP-2 — an exemption-set add + a passing gate test deleted together."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        context=["SANCTIONED_STOP_TERMINAL = {", "    'all-features-complete',"],
        removed=[
            "def test_weakening_is_refused():",
            "    assert refuse_run_start_clobber(marker) is True",
        ],
        added=["    'newly-exempted-terminal',"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"
    assert any("gate-test definition removed" in e for e in out["evidence"])
    assert any("exemption/sanction-set membership added" in e for e in out["evidence"])


def test_gate_weakening_new_bypass_env_var():
    diff = _diff(
        "user/hooks/build-queue-enforce.sh",
        added=['if [ "$HARNESS_GATE_BYPASS" = "1" ]; then exit 0; fi'],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"
    assert any("bypass env-var" in e for e in out["evidence"])


def test_gate_weakening_deny_branch_removal():
    diff = _diff(
        "user/hooks/lazy-cycle-containment.sh",
        removed=['  echo \'{"permissionDecision": "deny"}\'', "  exit 3"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"


def test_gate_weakening_numeric_literal_change():
    diff = _diff(
        "user/scripts/lazy_core.py",
        removed=["    CANARY_WINDOW_RUNS_DEFAULT = 10"],
        added=["    CANARY_WINDOW_RUNS_DEFAULT = 50"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"
    assert any("numeric-literal change" in e for e in out["evidence"])


def test_gate_weakening_clean_change_passes():
    diff = _diff(
        "user/scripts/lazy_core.py",
        added=["    new_helper = compute_thing(x)"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "pass"


# --- gate-weakening FALSE-POSITIVE regressions (gap 2 — rename + docstring/fixture) ---

def test_gate_weakening_renamed_test_def_not_flagged():
    """FP FIXTURE: a pure test-def rename (test_old removed + test_new added, body
    unchanged) preserves coverage — must NOT hit (net removed-added == 0)."""
    diff = _diff(
        "user/scripts/tests/test_lazy_core/test_markers.py",
        context=["    assert refuse_run_start_clobber(marker) is True"],
        removed=["def test_weakening_is_refused_old():"],
        added=["def test_weakening_is_refused_new():"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "pass", out["evidence"]
    assert out.get("evidence") == []


def test_gate_weakening_split_test_def_strengthening_not_flagged():
    """FP FIXTURE: one test def removed, TWO added (coverage strengthened) — no hit."""
    diff = _diff(
        "user/scripts/tests/test_lazy_core/test_markers.py",
        removed=["def test_broad_case():"],
        added=["def test_case_a():", "def test_case_b():"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "pass", out["evidence"]


def test_gate_weakening_added_docstring_not_membership():
    """FP FIXTURE: an added docstring line sitting next to an exemption-set opening
    must NOT be misread as a membership-set addition (the recurring `membership
    added: \"\"\"` false positive, hardening-log Round 67)."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        context=["SANCTIONED_STOP_TERMINAL = {", "    'all-features-complete',"],
        added=['    """A docstring that happens to sit near the set."""'],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "pass", out["evidence"]


def test_gate_weakening_bare_triple_quote_line_not_membership():
    """FP FIXTURE: a bare `\"\"\"` docstring-delimiter line is not a membership element."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        context=["_FAIL_CLOSED_EVIDENCE_SENTINELS = frozenset({"],
        added=['    """'],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "pass", out["evidence"]


def test_gate_weakening_fixture_list_near_bare_reference_not_membership():
    """FP FIXTURE: a test-fixture list element added beside a BARE reference to an
    exemption name (not a collection-opening of that set) must NOT hit."""
    diff = _diff(
        "user/scripts/tests/test_lazy_core/test_markers.py",
        context=["    # exercises SANCTIONED_STOP_TERMINAL membership", "    fixture = ["],
        added=["    'some-fixture-value',"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "pass", out["evidence"]


# --- gate-weakening TRUE-POSITIVE regressions (must STILL hit after the fix) --------

def test_gate_weakening_exemption_add_to_real_set_still_hits():
    """TP FIXTURE: an element genuinely appended to an exemption set being defined."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        context=["SANCTIONED_STOP_TERMINAL = {", "    'all-features-complete',"],
        added=["    'newly-exempted-terminal',"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"
    assert any("exemption/sanction-set membership added" in e for e in out["evidence"])


def test_gate_weakening_genuine_test_removal_still_hits():
    """TP FIXTURE: a gate test removed with NO replacement (net removal) still HITs."""
    diff = _diff(
        "user/scripts/tests/test_lazy_core/test_markers.py",
        removed=["def test_important_gate():", "    assert something"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"
    assert any("gate-test definition removed" in e for e in out["evidence"])


def test_gate_weakening_removed_refuse_construct_still_hits():
    """TP FIXTURE: a removed `refuse_*(...)` / `exit 3` gate-refusal construct still HITs."""
    diff = _diff(
        "user/scripts/lazy_core.py",
        removed=["    refuse_run_start_clobber(marker)", "    exit 3"],
    )
    out = hg.detect_gate_weakening(hg.parse_diff(diff))
    assert out["result"] == "hit"


# --- tautology detector (SPEC D2 / D6) -------------------------------------------

def test_tautology_missing_hypothesis_flags(tmp_path):
    (tmp_path / "SPEC.md").write_text("# Feature\n\nNo hypothesis here.\n", encoding="utf-8")
    out = hg.detect_tautology(tmp_path)
    assert out["result"] == "flag"


def test_tautology_self_emitted_flags(tmp_path):
    (tmp_path / "SPEC.md").write_text(
        "# Feature\n\n## Intervention Hypothesis\n\n- signal_independence: self-emitted\n",
        encoding="utf-8",
    )
    out = hg.detect_tautology(tmp_path)
    assert out["result"] == "self-emitted"


def test_tautology_independent_passes(tmp_path):
    (tmp_path / "SPEC.md").write_text(
        "# Feature\n\n## Intervention Hypothesis\n\n- signal_independence: independent — counted by X\n",
        encoding="utf-8",
    )
    out = hg.detect_tautology(tmp_path)
    assert out["result"] == "pass"


def test_tautology_no_feature_dir_passes_with_note():
    out = hg.detect_tautology(None)
    assert out["result"] == "pass"
    assert "ship seam" in out["note"]


# --- complexity + integration (SPEC Validation rows 4/5/7) -----------------------

def test_complexity_declaration_required_when_in_scope(tmp_path):
    (tmp_path / "SPEC.md").write_text(
        "## Intervention Hypothesis\n- signal_independence: independent\n", encoding="utf-8"
    )
    res = hg.run_checker(
        Path("."),
        _diff("user/scripts/lazy_core.py", added=["    x = clean_change()"]),
        ["user/scripts/lazy_core.py"],
        tmp_path,
        DEFAULT_GLOBS,
    )
    assert res["in_scope"] is True
    assert res["checks"]["complexity"]["result"] == "declaration-required"
    # complexity is always declaration-required in scope => verdict is required even on a clean diff
    assert res["verdict_required"] is True


def test_gate_weakening_hit_surfaces_flag_in_run_checker(tmp_path):
    (tmp_path / "SPEC.md").write_text(
        "## Intervention Hypothesis\n- signal_independence: independent\n", encoding="utf-8"
    )
    diff = _diff(
        "user/scripts/lazy_core.py",
        removed=["def test_x():", "    assert True"],
    )
    res = hg.run_checker(Path("."), diff, ["user/scripts/lazy_core.py"], tmp_path, DEFAULT_GLOBS)
    assert res["gate_weakening_hit"] is True
    assert res["verdict_required"] is True


# --- manifest loading + self-inclusion (SPEC Validation row 6 "self-application") -

def test_manifest_loads_and_gate_is_self_included():
    repo_root = Path(__file__).resolve().parents[2]
    manifest = hg.load_manifest(repo_root)
    globs = manifest["globs"]
    # editing the checker itself is in scope (self-application)
    assert hg.scope_hits(["user/scripts/harness-gate.py"], globs)
    # editing the manifest itself is in scope
    assert hg.scope_hits(["docs/gate/control-surfaces.json"], globs)
    # editing the gate component is in scope
    assert hg.scope_hits(["user/skills/_components/harness-change-gate.md"], globs)


def test_manifest_malformed_raises(tmp_path):
    (tmp_path / "docs" / "gate").mkdir(parents=True)
    (tmp_path / "docs" / "gate" / "control-surfaces.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        hg.load_manifest(tmp_path)


def test_manifest_wrong_shape_raises(tmp_path):
    (tmp_path / "docs" / "gate").mkdir(parents=True)
    (tmp_path / "docs" / "gate" / "control-surfaces.json").write_text(
        json.dumps({"control_surfaces": "not-a-list"}), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        hg.load_manifest(tmp_path)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
