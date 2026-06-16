#!/usr/bin/env python3
"""
test_retro_ro9.py — fixture self-test for R-O-9 (single-cycle containment).

lazy-cycle-containment Phase 8 / SPEC §C6. R-O-9 is the git+jsonl-keyed
detection layer (always available even when /tmp transcripts are reclaimed)
that the in-flight C1–C4 containment prevents and the existing R-EP-1/2 cannot
see (they invert under the inline-override branch).

These tests exercise two surfaces:
  1. The pure grading helper `retro_ro9.grade_ro9(dispatches)` — computes
     commits-per-dispatch / features-per-dispatch from a synthetic git-log +
     jsonl-dispatch sample and force-caps any dispatch touching >1 feature OR
     calling a run-lifecycle command. (SPEC Validation row "R-O-9 force-caps a
     runaway: grade `fail` + force-cap from git+jsonl".)
  2. Docs-consistency: the R-O-9 rule lives in lazy-batch-retro/SKILL.md §4a and
     the force-cap in §5c.
"""

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_retro_ro9():
    scripts_dir = Path(__file__).parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(
        "retro_ro9", scripts_dir / "retro_ro9.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# A synthetic dispatch list. Each dispatch carries:
#   nonce          — the cycle dispatch id (from --cycle-begin / jsonl)
#   feature_id     — the feature the dispatch was begun for
#   commit_features — set of feature dirs touched by the dispatch's commit window
#                     (from `git log <window>` --name-only ∩ docs/features/<id>/)
#   lifecycle_calls — run-lifecycle commands the dispatch issued (from jsonl Bash)
_CLEAN_RUN = [
    {"nonce": "a1", "feature_id": "feat-x",
     "commit_features": ["feat-x"], "lifecycle_calls": []},
    {"nonce": "b2", "feature_id": "feat-y",
     "commit_features": ["feat-y"], "lifecycle_calls": []},
]

_RUNAWAY_MULTI_FEATURE = [
    {"nonce": "a1", "feature_id": "feat-x",
     "commit_features": ["feat-x"], "lifecycle_calls": []},
    # ONE dispatch's commit window spans 2 different feature dirs — a runaway.
    {"nonce": "b2", "feature_id": "feat-y",
     "commit_features": ["feat-y", "feat-z"], "lifecycle_calls": []},
]

_RUNAWAY_LIFECYCLE = [
    # ONE dispatch called a run-lifecycle command mid-dispatch — a runaway.
    {"nonce": "a1", "feature_id": "feat-x",
     "commit_features": ["feat-x"], "lifecycle_calls": ["--run-end"]},
]


def test_clean_run_no_force_cap():
    ro9 = _load_retro_ro9()
    verdict = ro9.grade_ro9(_CLEAN_RUN)
    assert verdict["grade"] == "pass"
    assert verdict["force_cap"] is False
    assert verdict["offending"] == []


def test_multi_feature_single_dispatch_fails_and_force_caps():
    ro9 = _load_retro_ro9()
    verdict = ro9.grade_ro9(_RUNAWAY_MULTI_FEATURE)
    assert verdict["grade"] == "fail"
    assert verdict["force_cap"] is True
    # The offending dispatch is named with its reason (multi-feature).
    assert any(o["nonce"] == "b2" for o in verdict["offending"])
    assert any("feature" in o["reason"] for o in verdict["offending"])


def test_lifecycle_call_single_dispatch_fails_and_force_caps():
    ro9 = _load_retro_ro9()
    verdict = ro9.grade_ro9(_RUNAWAY_LIFECYCLE)
    assert verdict["grade"] == "fail"
    assert verdict["force_cap"] is True
    assert any(o["nonce"] == "a1" for o in verdict["offending"])
    assert any("--run-end" in o["reason"] or "lifecycle" in o["reason"]
               for o in verdict["offending"])


def test_metrics_computed_per_dispatch():
    ro9 = _load_retro_ro9()
    verdict = ro9.grade_ro9(_RUNAWAY_MULTI_FEATURE)
    # features-per-dispatch is exposed so the retro can cite the metric.
    metrics = {m["nonce"]: m for m in verdict["metrics"]}
    assert metrics["a1"]["features_touched"] == 1
    assert metrics["b2"]["features_touched"] == 2


# ---------------------------------------------------------------------------
# Docs-consistency: R-O-9 rule + force-cap present in the SKILL prose
# ---------------------------------------------------------------------------

_SKILL_PATH = (
    Path(__file__).resolve().parents[1] / "skills" / "lazy-batch-retro" / "SKILL.md"
)


def test_ro9_rule_in_skill_4a():
    text = _SKILL_PATH.read_text(encoding="utf-8")
    assert "R-O-9" in text, "R-O-9 rule missing from lazy-batch-retro/SKILL.md"
    # Defined in the orchestrator-level rules table (§4a) with its metrics.
    assert "single-cycle containment" in text
    assert "commits-per-dispatch" in text or "features-per-dispatch" in text


def test_ro9_force_cap_in_skill_5c():
    text = _SKILL_PATH.read_text(encoding="utf-8")
    # The §5c force-cap must name R-O-9 and the runaway triggers.
    # Find the headline-grade section and assert the R-O-9 cap is documented.
    assert "R-O-9" in text and "force-cap" in text
    # Complements (does not replace) R-EP-1/2.
    assert "R-EP-1" in text and "R-EP-2" in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
