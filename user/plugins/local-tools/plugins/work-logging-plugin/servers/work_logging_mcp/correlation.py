"""Two-stage topic correlation: semantic candidates + LLM-as-a-judge evaluation."""

from __future__ import annotations

from typing import Any, Protocol


class TopicScorer(Protocol):
    """Protocol for scoring topic relevance to a feature."""

    def __call__(self, feature_summary: str, topic_description: str) -> float: ...


class TopicJudge(Protocol):
    """Protocol for LLM-as-a-judge evaluation of a feature×topic pair."""

    def __call__(self, feature: dict[str, Any], topic: dict[str, Any]) -> int: ...


def get_candidate_topics(
    feature_summary: str,
    kb_entries: list[dict[str, Any]],
    scorer: TopicScorer,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Rank KB topics by semantic similarity, return top-k candidates.

    Each returned entry is augmented with a 'relevance_score' key.
    """
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in kb_entries:
        score = scorer(feature_summary, entry.get("description", ""))
        scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    results: list[dict[str, Any]] = []
    for score, entry in scored[:top_k]:
        results.append({**entry, "relevance_score": score})
    return results


def evaluate_topic_match(
    feature: dict[str, Any],
    topic: dict[str, Any],
    judge: TopicJudge,
) -> int:
    """Evaluate a single Feature×Topic pair using the LLM judge.

    Returns 0 (irrelevant), 1 (tangential), or 2 (strong match).
    Clamps output to valid range.
    """
    raw_score = judge(feature, topic)
    return max(0, min(2, raw_score))


def correlate_feature(
    feature: dict[str, Any],
    kb_entries: list[dict[str, Any]],
    scorer: TopicScorer,
    judge: TopicJudge,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Full two-stage pipeline: candidates → judge → Score 2 only.

    Returns list of KB entries that scored 2 (strong match).
    """
    candidates = get_candidate_topics(
        feature.get("summary", ""),
        kb_entries,
        scorer=scorer,
        top_k=top_k,
    )
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        score = evaluate_topic_match(feature, candidate, judge=judge)
        if score == 2:
            results.append(
                {
                    "slug": candidate.get("slug", ""),
                    "domain": candidate.get("domain", ""),
                    "score": score,
                }
            )
    return results
