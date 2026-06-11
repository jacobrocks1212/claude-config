"""Tests for KnowledgeBank — pure unit tests, no network or LLM calls."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from servers.work_logging_mcp.knowledge_bank import (
    Difficulty,
    Domain,
    KnowledgeBank,
    KnowledgeBankEntry,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "knowledge-bank"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bank() -> KnowledgeBank:
    """Return a KnowledgeBank loaded from the shared fixture directory."""
    return KnowledgeBank(FIXTURES_DIR)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_valid_yaml_loads() -> None:
    bank = _bank()
    assert len(bank.entries) == 4


def test_malformed_yaml_skipped() -> None:
    # malformed.yaml is missing the required `slug` field; loader must skip it
    # and NOT raise, leaving exactly the 4 well-formed entries.
    bank = _bank()
    assert len(bank.entries) == 4


def test_empty_directory(tmp_path: Path) -> None:
    bank = KnowledgeBank(tmp_path)
    assert bank.entries == []


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_domain_enum_validation() -> None:
    with pytest.raises(ValidationError):
        KnowledgeBankEntry(
            slug="x",
            name="X",
            domain="invalid",  # type: ignore[arg-type]
            tags=[],
            description="desc",
            interview_questions=[],
            talking_points=[],
            related_topics=[],
            difficulty=Difficulty.BEGINNER,
        )


def test_difficulty_enum_validation_reject() -> None:
    with pytest.raises(ValidationError):
        KnowledgeBankEntry(
            slug="x",
            name="X",
            domain=Domain.ALGORITHMS,
            tags=[],
            description="desc",
            interview_questions=[],
            talking_points=[],
            related_topics=[],
            difficulty="expert",  # type: ignore[arg-type]
        )


def test_difficulty_enum_validation_accept() -> None:
    entry = KnowledgeBankEntry(
        slug="x",
        name="X",
        domain=Domain.ALGORITHMS,
        tags=[],
        description="desc",
        interview_questions=[],
        talking_points=[],
        related_topics=[],
        difficulty=Difficulty.BEGINNER,
    )
    assert entry.difficulty == Difficulty.BEGINNER


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


def test_get_by_slug_and_domain_found() -> None:
    bank = _bank()
    entry = bank.get("observer-pattern", "system-design")
    assert entry is not None
    assert entry.slug == "observer-pattern"
    assert entry.domain == Domain.SYSTEM_DESIGN


def test_get_by_slug_and_domain_not_found() -> None:
    bank = _bank()
    assert bank.get("nonexistent", "system-design") is None


# ---------------------------------------------------------------------------
# query_by_tags()
# ---------------------------------------------------------------------------


def test_query_by_tags_sorted() -> None:
    bank = _bank()
    results = bank.query_by_tags(["observer", "pub-sub"])
    # observer-pattern carries both tags → overlap 2; must be first
    assert results, "expected at least one result"
    top_entry, top_overlap = results[0]
    assert top_entry.slug == "observer-pattern"
    assert top_overlap == 2
    # results must be sorted descending by overlap
    overlaps = [overlap for _, overlap in results]
    assert overlaps == sorted(overlaps, reverse=True)


def test_query_by_tags_threshold() -> None:
    bank = _bank()
    # Only observer-pattern has 2 matching tags from ["observer", "pub-sub"]
    results = bank.query_by_tags(["observer", "pub-sub"], threshold=2)
    assert len(results) == 1
    assert results[0][0].slug == "observer-pattern"


def test_query_by_tags_no_match() -> None:
    bank = _bank()
    results = bank.query_by_tags(["blockchain", "quantum"])
    assert results == []


# ---------------------------------------------------------------------------
# Compound tag matching
# ---------------------------------------------------------------------------


def test_query_by_tags_compound_match() -> None:
    """Hyphenated entry tags match when ALL constituent parts appear in query."""
    bank = _bank()
    # observer-pattern has tags: [observer, pub-sub, event-driven, decoupling, notifications]
    # "pub" + "sub" should compound-match "pub-sub", "observer" is an exact match → overlap 2
    results = bank.query_by_tags(["pub", "sub", "observer"])
    assert results, "expected at least one result"
    top_entry, top_overlap = results[0]
    assert top_entry.slug == "observer-pattern"
    assert top_overlap == 2


def test_query_by_tags_compound_no_partial() -> None:
    """Hyphenated tag must NOT match when only some parts are present."""
    bank = _bank()
    # "pub" alone (missing "sub") should NOT compound-match "pub-sub"
    # Only "observer" matches exactly → overlap 1
    results = bank.query_by_tags(["pub", "observer"])
    assert results, "expected at least one result"
    top_entry, top_overlap = results[0]
    assert top_entry.slug == "observer-pattern"
    assert top_overlap == 1
