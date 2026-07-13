"""Tests for lint-skill-config.py (feature: skill-config-schema-and-reference-lint).

Covers:
  - Phase 1: MANIFEST.json schema validation + bidirectional provides check;
    build-queue-ops.json structural checker (green real files, red per fixture violation).
  - Phase 2: the reference sweep — dangling reference, fallback-less-pointer (the
    long-build-ownership.md class), intended-absent-with-fallback OK, suppression
    downgrades error->warning without losing the finding, repo-scoped skills checked only
    against their own repo.
  - A self-check that THIS repo's real manifests + real skill trees lint clean (0 errors).

Hermetic tmp_path fixtures build a minimal repo_root tree (repos/<name>/.claude/skill-config,
user/skills/**) rather than touching the real tree, except for the final self-check.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent.parent
LINT_PATH = SCRIPTS_DIR / "lint-skill-config.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("lint_skill_config", LINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lsc():
    return _load_module()


def run_lint(repo_root):
    return subprocess.run(
        [sys.executable, str(LINT_PATH), "--repo-root", str(repo_root)],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Fixture builder — a minimal claude-config-shaped tree
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_minimal_tree(tmp_path: Path, *, repo_a_manifest: dict | None = None,
                        repo_b_manifest: dict | None = None) -> Path:
    """A repo_root with two config repos (repo-a, repo-b) and a small user-level
    skills tree carrying a handful of skill-config references."""
    root = tmp_path / "cc"

    # user-level skill sources
    _write(root / "user" / "skills" / "quality" / "SKILL.md", (
        "---\nname: quality\n---\n\n"
        "!`cat .claude/skill-config/quality-gates.md 2>/dev/null || "
        "cat ~/.claude/skills/_components/quality-gates.md`\n"
    ))
    _write(root / "user" / "skills" / "_components" / "quality-gates.md", "generic fallback\n")

    _write(root / "user" / "skills" / "onlyecho" / "SKILL.md", (
        "---\nname: onlyecho\n---\n\n"
        "!`cat .claude/skill-config/opt-in.md 2>/dev/null || echo \"no override configured\"`\n"
    ))

    _write(root / "user" / "skills" / "barepointer" / "SKILL.md", (
        "---\nname: barepointer\n---\n\n"
        "Full rule: `.claude/skill-config/repo-only.md`.\n"
    ))

    # repo-a: provides quality-gates.md + repo-only.md; declares opt-in.md intended_absent
    _write(root / "repos" / "repo-a" / ".claude" / "skill-config" / "quality-gates.md", "a\n")
    _write(root / "repos" / "repo-a" / ".claude" / "skill-config" / "repo-only.md", "a\n")
    manifest_a = repo_a_manifest if repo_a_manifest is not None else {
        "schema_version": 1,
        "provides": ["quality-gates.md", "repo-only.md"],
        "intended_absent": [{"file": "opt-in.md", "reason": "not needed for repo-a"}],
        "json_schemas": {},
    }
    _write(
        root / "repos" / "repo-a" / ".claude" / "skill-config" / "MANIFEST.json",
        json.dumps(manifest_a),
    )

    # repo-b: provides only quality-gates.md; does NOT provide repo-only.md and does NOT
    # declare it intended_absent (repo-only.md is a bare prose pointer -> fallback-less).
    _write(root / "repos" / "repo-b" / ".claude" / "skill-config" / "quality-gates.md", "b\n")
    manifest_b = repo_b_manifest if repo_b_manifest is not None else {
        "schema_version": 1,
        "provides": ["quality-gates.md"],
        "intended_absent": [{"file": "opt-in.md", "reason": "not needed for repo-b"}],
        "json_schemas": {},
    }
    _write(
        root / "repos" / "repo-b" / ".claude" / "skill-config" / "MANIFEST.json",
        json.dumps(manifest_b),
    )

    return root


# ---------------------------------------------------------------------------
# D1 — manifest schema
# ---------------------------------------------------------------------------

def test_validate_manifest_clean(lsc):
    data = {
        "schema_version": 1,
        "provides": ["a.md", "b.json"],
        "intended_absent": [{"file": "c.md", "reason": "not needed"}],
        "json_schemas": {"b.json": "build-queue-ops"},
    }
    assert lsc.validate_manifest(data) == []


def test_validate_manifest_bad_schema_version(lsc):
    errors = lsc.validate_manifest({"schema_version": 2, "provides": []})
    assert any("schema_version" in e for e in errors)


def test_validate_manifest_provides_not_list(lsc):
    errors = lsc.validate_manifest({"schema_version": 1, "provides": "nope"})
    assert any("provides must be a list" in e for e in errors)


def test_validate_manifest_duplicate_provides(lsc):
    errors = lsc.validate_manifest({"schema_version": 1, "provides": ["a.md", "a.md"]})
    assert any("duplicate" in e for e in errors)


def test_validate_manifest_intended_absent_missing_reason(lsc):
    errors = lsc.validate_manifest({
        "schema_version": 1, "provides": [],
        "intended_absent": [{"file": "x.md", "reason": "   "}],
    })
    assert any("missing a non-empty 'reason'" in e for e in errors)


def test_validate_manifest_intended_absent_duplicate(lsc):
    errors = lsc.validate_manifest({
        "schema_version": 1, "provides": [],
        "intended_absent": [
            {"file": "x.md", "reason": "r1"},
            {"file": "x.md", "reason": "r2"},
        ],
    })
    assert any("duplicate entry" in e for e in errors)


def test_validate_manifest_provides_intended_absent_overlap(lsc):
    errors = lsc.validate_manifest({
        "schema_version": 1,
        "provides": ["x.md"],
        "intended_absent": [{"file": "x.md", "reason": "r"}],
    })
    assert any("BOTH provides and intended_absent" in e for e in errors)


def test_validate_manifest_unknown_json_schema_key(lsc):
    errors = lsc.validate_manifest({
        "schema_version": 1, "provides": ["x.json"],
        "json_schemas": {"x.json": "not-a-real-schema"},
    })
    assert any("unknown schema" in e for e in errors)


def test_bidirectional_provides_check(tmp_path, lsc):
    scdir = tmp_path / "skill-config"
    scdir.mkdir()
    (scdir / "present.md").write_text("x", encoding="utf-8")
    (scdir / "MANIFEST.json").write_text("{}", encoding="utf-8")
    manifest = {"provides": ["present.md", "ghost.md"]}
    errors = lsc.bidirectional_provides_check(scdir, manifest)
    assert any("ghost.md" in e and "not found on disk" in e for e in errors)
    assert not any("present.md" in e for e in errors)

    # present-but-undeclared
    (scdir / "undeclared.md").write_text("y", encoding="utf-8")
    errors2 = lsc.bidirectional_provides_check(scdir, {"provides": ["present.md"]})
    assert any("undeclared.md" in e and "not declared in provides" in e for e in errors2)


# ---------------------------------------------------------------------------
# D2 — build-queue-ops.json structural checker
# ---------------------------------------------------------------------------

VALID_OPS = {
    "version": 1,
    "ops": {
        "msbuild": {
            "exec": ".claude/scripts/build-filtered.ps1",
            "kind": "build",
            "hygiene": "dotnet",
            "skill": "/msbuild",
            "deny": ["dotnet build"],
            "lane": "heavy",
        }
    },
}


def test_build_queue_ops_valid_is_clean(lsc):
    assert lsc.check_build_queue_ops(VALID_OPS) == []


def test_build_queue_ops_bad_version(lsc):
    data = json.loads(json.dumps(VALID_OPS))
    data["version"] = 2
    errors = lsc.check_build_queue_ops(data)
    assert any("version" in e for e in errors)


def test_build_queue_ops_bad_kind(lsc):
    data = json.loads(json.dumps(VALID_OPS))
    data["ops"]["msbuild"]["kind"] = "lint"
    errors = lsc.check_build_queue_ops(data)
    assert any("kind" in e for e in errors)


def test_build_queue_ops_missing_exec(lsc):
    data = json.loads(json.dumps(VALID_OPS))
    del data["ops"]["msbuild"]["exec"]
    errors = lsc.check_build_queue_ops(data)
    assert any("exec" in e for e in errors)


def test_build_queue_ops_bad_lane(lsc):
    data = json.loads(json.dumps(VALID_OPS))
    data["ops"]["msbuild"]["lane"] = "medium"
    errors = lsc.check_build_queue_ops(data)
    assert any("lane" in e for e in errors)


def test_build_queue_ops_empty_deny(lsc):
    data = json.loads(json.dumps(VALID_OPS))
    data["ops"]["msbuild"]["deny"] = []
    errors = lsc.check_build_queue_ops(data)
    assert any("deny" in e for e in errors)


def test_build_queue_ops_skill_missing_slash(lsc):
    data = json.loads(json.dumps(VALID_OPS))
    data["ops"]["msbuild"]["skill"] = "msbuild"
    errors = lsc.check_build_queue_ops(data)
    assert any("skill" in e for e in errors)


def test_build_queue_ops_malformed_ops(lsc):
    errors = lsc.check_build_queue_ops({"version": 1, "ops": {}})
    assert any("non-empty object" in e for e in errors)


# ---------------------------------------------------------------------------
# D3 — reference sweep (end-to-end via run())
# ---------------------------------------------------------------------------

def test_reference_sweep_clean_minimal_tree(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    errors, warnings = lsc.run(root)
    # repo-only.md is absent from repo-b and not declared at all -> dangling-reference ERROR.
    assert any(e.kind == "dangling-reference" and "repo-only.md" in e.detail for e in errors), \
        [e.render(root) for e in errors]


def test_reference_sweep_dangling_undeclared(tmp_path, lsc):
    # repo-b doesn't declare opt-in.md intended_absent at all -> becomes a
    # dangling-reference error once we drop the declaration.
    manifest_b = {
        "schema_version": 1,
        "provides": ["quality-gates.md"],
        "intended_absent": [],
        "json_schemas": {},
    }
    root = build_minimal_tree(tmp_path, repo_b_manifest=manifest_b)
    errors, warnings = lsc.run(root)
    assert any(
        e.kind == "dangling-reference" and "opt-in.md" in e.detail and e.repo == "repo-b"
        for e in errors
    ), [e.render(root) for e in errors]


def test_reference_sweep_intended_absent_with_fallback_is_ok(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    errors, warnings = lsc.run(root)
    # opt-in.md is declared intended_absent by BOTH repos and the reference has an
    # echo-fallback form -> never an error for opt-in.md.
    assert not any("opt-in.md" in e.detail for e in errors)


def test_reference_sweep_declared_but_no_fallback_still_errors(tmp_path, lsc):
    # Declaring repo-only.md intended_absent for repo-b does NOT rescue it, because
    # the only reference is a bare prose pointer with no fallback form.
    manifest_b = {
        "schema_version": 1,
        "provides": ["quality-gates.md"],
        "intended_absent": [
            {"file": "opt-in.md", "reason": "not needed"},
            {"file": "repo-only.md", "reason": "repo-b doesn't need this either"},
        ],
        "json_schemas": {},
    }
    root = build_minimal_tree(tmp_path, repo_b_manifest=manifest_b)
    errors, warnings = lsc.run(root)
    assert any(
        e.kind == "fallback-less-pointer" and "repo-only.md" in e.detail and e.repo == "repo-b"
        for e in errors
    ), [e.render(root) for e in errors]


def test_suppression_downgrades_error_to_warning(tmp_path, lsc, monkeypatch):
    manifest_b = {
        "schema_version": 1,
        "provides": ["quality-gates.md"],
        "intended_absent": [{"file": "opt-in.md", "reason": "not needed"}],
        "json_schemas": {},
    }
    root = build_minimal_tree(tmp_path, repo_b_manifest=manifest_b)
    key = ("user/skills/barepointer/SKILL.md", "repo-only.md")
    monkeypatch.setitem(lsc.SUPPRESSIONS, key, "known gap, tracked elsewhere")
    try:
        errors, warnings = lsc.run(root)
        assert not any("repo-only.md" in e.detail for e in errors)
        assert any(
            w.kind == "dangling-reference" and "repo-only.md" in w.detail
            and "known gap, tracked elsewhere" in w.detail
            for w in warnings
        ), [w.render(root) for w in warnings]
    finally:
        lsc.SUPPRESSIONS.pop(key, None)


def test_missing_manifest_is_an_error(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    (root / "repos" / "repo-b" / ".claude" / "skill-config" / "MANIFEST.json").unlink()
    errors, warnings = lsc.run(root)
    assert any(e.kind == "missing-manifest" and e.repo == "repo-b" for e in errors)


def test_malformed_manifest_json_is_an_error(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    (root / "repos" / "repo-b" / ".claude" / "skill-config" / "MANIFEST.json").write_text(
        "{not json", encoding="utf-8"
    )
    errors, warnings = lsc.run(root)
    assert any(e.kind == "malformed-manifest" and e.repo == "repo-b" for e in errors)


def test_unregistered_json_is_a_warning_not_an_error(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    _write(root / "repos" / "repo-a" / ".claude" / "skill-config" / "extra.json", "{}")
    manifest_a = {
        "schema_version": 1,
        "provides": ["quality-gates.md", "repo-only.md", "extra.json"],
        "intended_absent": [{"file": "opt-in.md", "reason": "not needed for repo-a"}],
        "json_schemas": {},
    }
    (root / "repos" / "repo-a" / ".claude" / "skill-config" / "MANIFEST.json").write_text(
        json.dumps(manifest_a), encoding="utf-8"
    )
    errors, warnings = lsc.run(root)
    assert not any("extra.json" in e.detail for e in errors)
    assert any(w.kind == "unregistered-json" and "extra.json" in w.detail for w in warnings)


def test_build_queue_ops_json_schema_error_surfaces_through_run(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    _write(
        root / "repos" / "repo-a" / ".claude" / "skill-config" / "build-queue-ops.json",
        json.dumps({"version": 1, "ops": {"bad": {"exec": "", "kind": "lint"}}}),
    )
    manifest_a = {
        "schema_version": 1,
        "provides": ["quality-gates.md", "repo-only.md", "build-queue-ops.json"],
        "intended_absent": [{"file": "opt-in.md", "reason": "not needed for repo-a"}],
        "json_schemas": {"build-queue-ops.json": "build-queue-ops"},
    }
    (root / "repos" / "repo-a" / ".claude" / "skill-config" / "MANIFEST.json").write_text(
        json.dumps(manifest_a), encoding="utf-8"
    )
    errors, warnings = lsc.run(root)
    assert any(e.kind == "json-schema:build-queue-ops" and "exec" in e.detail for e in errors)


def test_repo_scoped_skill_checked_only_against_own_repo(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    # repo-a-scoped skill references a file that exists ONLY in repo-a -- must NOT be
    # flagged against repo-b (repo-scoped skills are checked only against their own repo).
    _write(
        root / "repos" / "repo-a" / ".claude" / "skills" / "myskill" / "SKILL.md",
        "Full rule: `.claude/skill-config/repo-only.md`.\n",
    )
    errors, warnings = lsc.run(root)
    assert not any(
        e.repo == "repo-a" and "repo-only.md" in e.detail and e.kind != "unregistered-json"
        for e in errors
    )


def test_self_referential_component_prose_is_not_a_dangling_reference(tmp_path, lsc):
    root = build_minimal_tree(tmp_path)
    _write(
        root / "user" / "skills" / "_components" / "opt-in.md",
        "The project-specific version lives at .claude/skill-config/opt-in.md, which is "
        "cat'd in place of this file.\n",
    )
    errors, warnings = lsc.run(root)
    assert not any("opt-in.md" in e.detail and "_components/opt-in.md" in e.detail for e in errors)


# ---------------------------------------------------------------------------
# Self-check: THIS repo's real manifests + skill trees must lint clean
# ---------------------------------------------------------------------------

def test_this_repo_is_clean():
    res = run_lint(REPO_ROOT)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "OK — skill-config schema + reference lint clean." in res.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
