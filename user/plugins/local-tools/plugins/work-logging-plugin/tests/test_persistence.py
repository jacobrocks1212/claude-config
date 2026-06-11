"""Tests for persistence module — pure unit tests using tmp_path, no real FS side-effects."""

import json
import re
from pathlib import Path

import pytest

from servers.work_logging_mcp.persistence import (
    ConfigReader,
    FeaturesWriter,
    ImportIndexWriter,
    WorkLogWriter,
)

# ---------------------------------------------------------------------------
# WorkLogWriter
# ---------------------------------------------------------------------------

_VALID_ENTRY = {
    "skill": "fix",
    "project": "algobooth",
    "title": "Square wave near DC",
    "summary": "Fixed pw=0 default causing DC output",
    "files_modified": ["src/voice.rs"],
}

ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_work_log_writer_creates_file(tmp_path: Path) -> None:
    WorkLogWriter(tmp_path).append(dict(_VALID_ENTRY))
    assert (tmp_path / "work-log.jsonl").exists()


def test_work_log_writer_auto_timestamps(tmp_path: Path) -> None:
    entry = dict(_VALID_ENTRY)
    WorkLogWriter(tmp_path).append(entry)
    record = json.loads((tmp_path / "work-log.jsonl").read_text().strip())
    assert ISO_TIMESTAMP.match(record["timestamp"])


def test_work_log_writer_overwrites_caller_timestamp(tmp_path: Path) -> None:
    entry = {**_VALID_ENTRY, "timestamp": "1999-01-01T00:00:00Z"}
    WorkLogWriter(tmp_path).append(entry)
    record = json.loads((tmp_path / "work-log.jsonl").read_text().strip())
    assert not record["timestamp"].startswith("1999")


def test_work_log_writer_required_fields(tmp_path: Path) -> None:
    writer = WorkLogWriter(tmp_path)
    for field in ("skill", "project", "title", "summary", "files_modified"):
        incomplete = {k: v for k, v in _VALID_ENTRY.items() if k != field}
        with pytest.raises(ValueError, match="Missing required"):
            writer.append(incomplete)


def test_work_log_writer_rejects_empty_required_field(tmp_path: Path) -> None:
    entry = {**_VALID_ENTRY, "title": ""}
    with pytest.raises(ValueError, match="empty"):
        WorkLogWriter(tmp_path).append(entry)


def test_work_log_writer_preserves_extras(tmp_path: Path) -> None:
    entry = {**_VALID_ENTRY, "bug_summary": "DC output", "root_cause": "pw=0"}
    WorkLogWriter(tmp_path).append(entry)
    record = json.loads((tmp_path / "work-log.jsonl").read_text().strip())
    assert record["bug_summary"] == "DC output"
    assert record["root_cause"] == "pw=0"


def test_work_log_writer_multiple_entries(tmp_path: Path) -> None:
    writer = WorkLogWriter(tmp_path)
    for i in range(3):
        writer.append({**_VALID_ENTRY, "title": f"Entry {i}"})
    lines = (tmp_path / "work-log.jsonl").read_text().splitlines()
    assert len(lines) == 3


def test_work_log_writer_query_by_skill(tmp_path: Path) -> None:
    writer = WorkLogWriter(tmp_path)
    for skill in ("fix", "fix", "spec", "fix"):
        writer.append({**_VALID_ENTRY, "skill": skill})
    assert len(writer.query(skill="fix")) == 3
    assert len(writer.query(skill="spec")) == 1


def test_work_log_writer_query_by_project(tmp_path: Path) -> None:
    writer = WorkLogWriter(tmp_path)
    for project in ("algobooth", "cognito", "algobooth"):
        writer.append({**_VALID_ENTRY, "project": project})
    assert len(writer.query(project="algobooth")) == 2


def test_work_log_writer_query_by_date_range(tmp_path: Path) -> None:
    writer = WorkLogWriter(tmp_path)
    writer.append(dict(_VALID_ENTRY))
    results = writer.query(date_from="2020-01-01", date_to="2099-12-31")
    assert len(results) == 1
    results = writer.query(date_from="2099-01-01")
    assert len(results) == 0


def test_work_log_writer_count(tmp_path: Path) -> None:
    writer = WorkLogWriter(tmp_path)
    assert writer.count() == 0
    for _ in range(5):
        writer.append(dict(_VALID_ENTRY))
    assert writer.count() == 5


def test_work_log_writer_returns_path(tmp_path: Path) -> None:
    result = WorkLogWriter(tmp_path).append(dict(_VALID_ENTRY))
    assert isinstance(result, Path)
    assert result == tmp_path / "work-log.jsonl"


# ---------------------------------------------------------------------------
# ConfigReader
# ---------------------------------------------------------------------------


def test_config_reader_defaults(tmp_path: Path) -> None:
    config = ConfigReader(tmp_path).load()
    assert config == {"relevance_threshold": 0.7, "stale_days": 30}


def test_config_reader_loads_existing(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({"relevance_threshold": 0.9}))
    config = ConfigReader(tmp_path).load()
    assert config == {"relevance_threshold": 0.9}


# ---------------------------------------------------------------------------
# WorkLogWriter auto-commit
# ---------------------------------------------------------------------------


def test_work_log_writer_auto_commit_creates_git_commit(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    WorkLogWriter(tmp_path).append(dict(_VALID_ENTRY))
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() != ""


def test_work_log_writer_auto_commit_skips_when_not_git_repo(tmp_path: Path) -> None:
    WorkLogWriter(tmp_path).append(dict(_VALID_ENTRY))
    assert (tmp_path / "work-log.jsonl").exists()


def test_work_log_writer_auto_commit_includes_title_in_message(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    WorkLogWriter(tmp_path).append(dict(_VALID_ENTRY))
    result = subprocess.run(
        ["git", "log", "--format=%s", "-1"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Square wave near DC" in result.stdout


# ---------------------------------------------------------------------------
# FeaturesWriter
# ---------------------------------------------------------------------------

_VALID_FEATURE: dict[str, object] = {
    "slug": "cognito-pay",
    "project": "cognito-forms",
    "title": "Cognito Pay — Payment Processing",
    "summary": "Designed and implemented multi-provider payment processing.",
}


def test_features_writer_creates_file(tmp_path: Path) -> None:
    FeaturesWriter(tmp_path).append(_VALID_FEATURE.copy())
    assert (tmp_path / "features.jsonl").exists()


def test_features_writer_uuid_generation(tmp_path: Path) -> None:
    import uuid

    FeaturesWriter(tmp_path).append(_VALID_FEATURE.copy())
    record = json.loads((tmp_path / "features.jsonl").read_text(encoding="utf-8").strip())
    # Should have a valid UUID v4
    parsed = uuid.UUID(record["id"])
    assert parsed.version == 4


def test_features_writer_query_by_slug(tmp_path: Path) -> None:
    writer = FeaturesWriter(tmp_path)
    features = [
        {**_VALID_FEATURE, "slug": "cognito-pay"},
        {**_VALID_FEATURE, "slug": "auth-service"},
        {**_VALID_FEATURE, "slug": "cognito-pay"},
    ]
    for f in features:
        writer.append(dict(f))
    results = writer.query(slug="cognito-pay")
    assert len(results) == 2


def test_features_writer_query_by_project(tmp_path: Path) -> None:
    writer = FeaturesWriter(tmp_path)
    for project in ("cognito-forms", "algobooth", "cognito-forms"):
        writer.append({**_VALID_FEATURE, "project": project})
    results = writer.query(project="cognito-forms")
    assert len(results) == 2


def test_features_writer_query_by_id(tmp_path: Path) -> None:
    writer = FeaturesWriter(tmp_path)
    writer.append(_VALID_FEATURE.copy())
    record = json.loads((tmp_path / "features.jsonl").read_text(encoding="utf-8").strip())
    feature_id = record["id"]
    results = writer.query(feature_id=feature_id)
    assert len(results) == 1
    assert results[0]["id"] == feature_id


def test_features_writer_upsert_by_id(tmp_path: Path) -> None:
    writer = FeaturesWriter(tmp_path)
    writer.append(_VALID_FEATURE.copy())
    record = json.loads((tmp_path / "features.jsonl").read_text(encoding="utf-8").strip())
    feature_id = record["id"]
    # Upsert with same id but updated title
    writer.append({**_VALID_FEATURE, "id": feature_id, "title": "Updated Title"})
    results = writer.query(feature_id=feature_id)
    assert len(results) == 1
    assert results[0]["title"] == "Updated Title"


def test_features_writer_required_fields(tmp_path: Path) -> None:
    writer = FeaturesWriter(tmp_path)
    for field in ("slug", "project", "title", "summary"):
        incomplete = {k: v for k, v in _VALID_FEATURE.items() if k != field}
        with pytest.raises(ValueError, match="Missing required"):
            writer.append(incomplete)


def test_features_writer_auto_commit(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    FeaturesWriter(tmp_path).append(_VALID_FEATURE.copy())
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() != ""


# ---------------------------------------------------------------------------
# ImportIndexWriter
# ---------------------------------------------------------------------------


def test_import_index_writer_new_entry(tmp_path: Path) -> None:
    import uuid

    writer = ImportIndexWriter(tmp_path)
    result = writer.add(
        source_path="/repos/algobooth/docs/SPEC.md",
        content_hash="sha256:abc123",
        project="algobooth",
        artifact_type="spec",
    )
    assert result["status"] == "created"
    parsed = uuid.UUID(result["uuid"])
    assert parsed.version == 4


def test_import_index_writer_dedup_exact_hash(tmp_path: Path) -> None:
    writer = ImportIndexWriter(tmp_path)
    writer.add(
        source_path="/repos/algobooth/docs/SPEC.md",
        content_hash="sha256:abc123",
        project="algobooth",
        artifact_type="spec",
    )
    result = writer.add(
        source_path="/repos/algobooth/docs/SPEC.md",
        content_hash="sha256:abc123",
        project="algobooth",
        artifact_type="spec",
    )
    assert result["status"] == "skipped"


def test_import_index_writer_evolution(tmp_path: Path) -> None:
    writer = ImportIndexWriter(tmp_path)
    first = writer.add(
        source_path="/repos/algobooth/docs/SPEC.md",
        content_hash="sha256:abc123",
        project="algobooth",
        artifact_type="spec",
    )
    second = writer.add(
        source_path="/repos/algobooth/docs/SPEC.md",
        content_hash="sha256:def456",
        project="algobooth",
        artifact_type="spec",
    )
    assert second["status"] == "evolved"
    assert second["uuid"] == first["uuid"]


def test_import_index_writer_hash_computation(tmp_path: Path) -> None:
    test_file = tmp_path / "test.md"
    test_file.write_text("hello world", encoding="utf-8")
    computed = ImportIndexWriter.compute_hash(test_file)
    assert computed.startswith("sha256:")
    assert len(computed) == 71  # "sha256:" + 64 hex chars


def test_import_index_writer_auto_commit(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    writer = ImportIndexWriter(tmp_path)
    writer.add(
        source_path="/repos/test/SPEC.md",
        content_hash="sha256:abc123",
        project="test",
        artifact_type="spec",
    )
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() != ""
