"""Tests for the two-stage topic correlation pipeline."""

from __future__ import annotations

from typing import Any

from servers.work_logging_mcp.correlation import (
    correlate_feature,
    evaluate_topic_match,
    get_candidate_topics,
)

_SAMPLE_KB_ENTRIES: list[dict[str, Any]] = [
    {
        "slug": "rate-limiting",
        "domain": "system-design",
        "description": "Token bucket and leaky bucket algorithms for API rate limiting",
    },
    {
        "slug": "caching",
        "domain": "system-design",
        "description": "Cache invalidation strategies and distributed caching patterns",
    },
    {
        "slug": "observer-pattern",
        "domain": "ood",
        "description": "Publish-subscribe and observer patterns for event-driven systems",
    },
    {
        "slug": "sorting",
        "domain": "algorithms",
        "description": "Comparison-based and linear-time sorting algorithms",
    },
    {
        "slug": "leadership",
        "domain": "behavioral",
        "description": "Leading teams through ambiguity and technical disagreements",
    },
]

_SAMPLE_FEATURE: dict[str, Any] = {
    "slug": "auth-rate-limiter",
    "project": "cognito-forms",
    "title": "Auth Service Rate Limiting",
    "summary": (
        "Implemented token bucket rate limiting for the authentication API"
        " to prevent brute force attacks."
    ),
}


def _mock_scorer(feature_summary: str, topic_description: str) -> float:
    """Simple keyword overlap scorer for testing."""
    feature_words = set(feature_summary.lower().split())
    topic_words = set(topic_description.lower().split())
    overlap = len(feature_words & topic_words)
    return float(overlap)


def test_get_candidate_topics_returns_sorted() -> None:
    results = get_candidate_topics(
        "token bucket rate limiting for API",
        _SAMPLE_KB_ENTRIES,
        scorer=_mock_scorer,
        top_k=3,
    )
    assert len(results) <= 3
    scores = [r["relevance_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    # rate-limiting should score highest due to keyword overlap
    assert results[0]["slug"] == "rate-limiting"


def test_get_candidate_topics_respects_top_k() -> None:
    results = get_candidate_topics(
        "some feature",
        _SAMPLE_KB_ENTRIES,
        scorer=_mock_scorer,
        top_k=2,
    )
    assert len(results) == 2


def test_evaluate_topic_match_returns_valid_score() -> None:
    def mock_judge(feature: dict[str, Any], topic: dict[str, Any]) -> int:
        return 2

    score = evaluate_topic_match(_SAMPLE_FEATURE, _SAMPLE_KB_ENTRIES[0], judge=mock_judge)
    assert score in (0, 1, 2)


def test_evaluate_topic_match_clamps_invalid() -> None:
    def mock_judge(feature: dict[str, Any], topic: dict[str, Any]) -> int:
        return 5  # Invalid score, should be clamped

    score = evaluate_topic_match(_SAMPLE_FEATURE, _SAMPLE_KB_ENTRIES[0], judge=mock_judge)
    assert score == 2


def test_correlate_feature_filters_to_score_2() -> None:
    call_count = {"n": 0}

    def mock_judge(feature: dict[str, Any], topic: dict[str, Any]) -> int:
        call_count["n"] += 1
        # Only rate-limiting gets score 2
        if topic.get("slug") == "rate-limiting":
            return 2
        return 1

    results = correlate_feature(
        _SAMPLE_FEATURE,
        _SAMPLE_KB_ENTRIES,
        scorer=_mock_scorer,
        judge=mock_judge,
        top_k=5,
    )
    # Only score-2 entries returned
    assert all(r["score"] == 2 for r in results)
    assert any(r["slug"] == "rate-limiting" for r in results)
    # Judge was called for each candidate
    assert call_count["n"] == 5


def test_correlate_feature_returns_empty_when_no_score_2() -> None:
    def mock_judge(feature: dict[str, Any], topic: dict[str, Any]) -> int:
        return 1  # All tangential

    results = correlate_feature(
        _SAMPLE_FEATURE,
        _SAMPLE_KB_ENTRIES,
        scorer=_mock_scorer,
        judge=mock_judge,
    )
    assert results == []
