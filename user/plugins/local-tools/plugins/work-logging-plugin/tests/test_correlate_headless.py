from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from scripts.correlate_headless import correlate_features

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_CANDIDATES = [
    {"slug": "rate-limiting", "domain": "system-design", "description": "Token bucket"},
    {"slug": "caching", "domain": "system-design", "description": "Cache patterns"},
]

_BASE_FEATURE: dict[str, Any] = {
    "id": "feat-001",
    "slug": "my-feature",
    "project": "algobooth",
    "title": "My Feature",
    "summary": "A feature about rate limiting and caching strategies.",
}


def _seed_features(tmp_path: Path, features: list[dict[str, Any]]) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    with (tmp_path / "features.jsonl").open("w", encoding="utf-8") as fh:
        for f in features:
            fh.write(json.dumps(f) + "\n")


def _read_features(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "features.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("scripts.correlate_headless.get_candidate_topics", return_value=_MOCK_CANDIDATES)
@patch("scripts.correlate_headless.BatchHeadlessJudge")
def test_correlate_skips_already_correlated(
    mock_judge_cls: MagicMock,
    mock_candidates: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange — feature already has topic_correlations
    feature = {
        **_BASE_FEATURE,
        "topic_correlations": [{"slug": "rate-limiting", "domain": "system-design"}],
    }
    _seed_features(tmp_path, [feature])
    mock_judge = mock_judge_cls.return_value

    # Act
    correlate_features(base_path=tmp_path)

    # Assert — judge.evaluate never called because feature was skipped
    mock_judge.evaluate.assert_not_called()


@patch("scripts.correlate_headless.get_candidate_topics", return_value=_MOCK_CANDIDATES)
@patch("scripts.correlate_headless.BatchHeadlessJudge")
def test_correlate_dry_run_no_writes(
    mock_judge_cls: MagicMock,
    mock_candidates: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange — feature without correlations
    _seed_features(tmp_path, [_BASE_FEATURE])
    mock_judge = mock_judge_cls.return_value
    mock_judge.evaluate.return_value = {"rate-limiting": 2, "caching": 1}
    original_lines = _read_features(tmp_path)

    # Act
    correlate_features(base_path=tmp_path, dry_run=True)

    # Assert — features.jsonl has same number of lines (no new records written)
    after_lines = _read_features(tmp_path)
    assert len(after_lines) == len(original_lines)
    assert all("topic_correlations" not in r for r in after_lines)


@patch("scripts.correlate_headless.get_candidate_topics", return_value=_MOCK_CANDIDATES)
@patch("scripts.correlate_headless.BatchHeadlessJudge")
def test_correlate_force_reprocesses(
    mock_judge_cls: MagicMock,
    mock_candidates: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange — feature that already has correlations
    feature = {
        **_BASE_FEATURE,
        "topic_correlations": [{"slug": "caching", "domain": "system-design"}],
    }
    _seed_features(tmp_path, [feature])
    mock_judge = mock_judge_cls.return_value
    mock_judge.evaluate.return_value = {"rate-limiting": 2, "caching": 2}

    # Act
    correlate_features(base_path=tmp_path, force=True)

    # Assert — judge.evaluate was called because force=True bypassed skip logic
    mock_judge.evaluate.assert_called_once()


@patch("scripts.correlate_headless.get_candidate_topics", return_value=_MOCK_CANDIDATES)
@patch("scripts.correlate_headless.BatchHeadlessJudge")
def test_correlate_upserts_results(
    mock_judge_cls: MagicMock,
    mock_candidates: MagicMock,
    tmp_path: Path,
) -> None:
    # Arrange — feature without correlations
    _seed_features(tmp_path, [_BASE_FEATURE])
    mock_judge = mock_judge_cls.return_value
    mock_judge.evaluate.return_value = {"rate-limiting": 2, "caching": 1}

    # Act
    correlate_features(base_path=tmp_path)

    # Assert — latest record for feat-001 has topic_correlations with Score 2 entry only
    records = _read_features(tmp_path)
    # last-wins dedup: find the most recent record for our feature id
    feat_records = [r for r in records if r.get("id") == "feat-001"]
    assert feat_records, "expected at least one record for feat-001"
    latest = feat_records[-1]
    assert "topic_correlations" in latest, "upserted record should have topic_correlations"
    correlated_slugs = [tc["slug"] for tc in latest["topic_correlations"]]
    assert "rate-limiting" in correlated_slugs, "Score 2 topic should appear in correlations"
    assert "caching" not in correlated_slugs, "Score 1 topic should be excluded"
