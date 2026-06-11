"""Tests for vault generation engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from servers.work_logging_mcp.vault_generator import VaultGenerator

_SAMPLE_KB: list[dict[str, Any]] = [
    {
        "slug": "rate-limiting",
        "name": "Rate Limiting",
        "domain": "system-design",
        "description": "Token bucket and leaky bucket algorithms",
        "tags": ["distributed-systems", "api"],
        "difficulty": "medium",
        "interview_questions": ["How would you implement rate limiting?"],
        "talking_points": [
            "Token bucket allows bursty traffic while maintaining average rate",
            "Leaky bucket enforces strict constant-rate output",
            "Distributed rate limiting requires shared state via Redis or similar",
        ],
        "related_topics": ["load-balancing", "cdn", "api-gateway"],
    },
    {
        "slug": "observer-pattern",
        "name": "Observer Pattern",
        "domain": "ood",
        "description": "Publish-subscribe pattern for decoupled communication",
        "tags": ["design-patterns"],
        "difficulty": "easy",
        "interview_questions": [],
    },
]

_SAMPLE_FEATURES: list[dict[str, Any]] = [
    {
        "id": "feat-1",
        "slug": "auth-rate-limiter",
        "project": "cognito-forms",
        "title": "Auth Rate Limiter",
        "summary": "Implemented token bucket for auth API",
        "work_log_refs": ["2026-04-01T10:00:00Z"],
        "topic_correlations": [
            {"slug": "rate-limiting", "domain": "system-design", "score": 2},
        ],
    },
]

_SAMPLE_WORK_LOG: list[dict[str, Any]] = [
    {
        "skill": "fix",
        "project": "cognito-forms",
        "title": "Fix auth timeout",
        "summary": "Fixed token expiry causing auth timeouts",
        "files_modified": ["src/auth.cs", "tests/auth_test.cs"],
        "timestamp": "2026-04-01T10:00:00Z",
        "feature": "auth-rate-limiter",
    },
    {
        "skill": "implement-phase",
        "project": "algobooth",
        "title": "Audio pipeline refactor",
        "summary": "Refactored audio pipeline for lower latency",
        "files_modified": ["src/audio.rs"],
        "timestamp": "2026-04-02T14:30:00Z",
    },
]


def test_generate_knowledge_bank_creates_pages(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    count = gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    assert count == 2
    assert (tmp_path / "01_Knowledge_Bank" / "system-design" / "rate-limiting.md").exists()
    assert (tmp_path / "01_Knowledge_Bank" / "ood" / "observer-pattern.md").exists()


def test_knowledge_bank_has_frontmatter(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    page = tmp_path / "01_Knowledge_Bank" / "system-design" / "rate-limiting.md"
    content = page.read_text(encoding="utf-8")
    assert content.startswith("---")
    assert "type: knowledge-bank" in content
    assert "domain: system-design" in content


def test_knowledge_bank_includes_correlated_stories(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    page = tmp_path / "01_Knowledge_Bank" / "system-design" / "rate-limiting.md"
    content = page.read_text(encoding="utf-8")
    assert "[[auth-rate-limiter]]" in content


def test_generate_work_history_creates_pages(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    count = gen.generate_work_history(_SAMPLE_WORK_LOG, _SAMPLE_FEATURES)
    assert count == 2
    files = list((tmp_path / "02_Work_History").glob("*.md"))
    assert len(files) == 2


def test_work_history_has_frontmatter(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_work_history(_SAMPLE_WORK_LOG, _SAMPLE_FEATURES)
    files = list((tmp_path / "02_Work_History").glob("*.md"))
    content = files[0].read_text(encoding="utf-8")
    assert content.startswith("---")
    assert "type: work-history" in content


def test_work_history_links_to_feature_only(tmp_path: Path) -> None:
    """DAG rule: Work History links only to parent Feature, not KB topics."""
    gen = VaultGenerator(tmp_path)
    gen.generate_work_history(_SAMPLE_WORK_LOG, _SAMPLE_FEATURES)
    files = list((tmp_path / "02_Work_History").glob("*.md"))
    for f in files:
        content = f.read_text(encoding="utf-8")
        # Should NOT link directly to KB topics
        assert "[[rate-limiting]]" not in content
        assert "[[observer-pattern]]" not in content


def test_work_history_links_to_parent_feature(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_work_history(_SAMPLE_WORK_LOG, _SAMPLE_FEATURES)
    # First entry has feature tag "auth-rate-limiter"
    files = sorted((tmp_path / "02_Work_History").glob("*.md"))
    content = files[0].read_text(encoding="utf-8")
    assert "[[auth-rate-limiter]]" in content


_SAMPLE_KB_FOR_STORIES: list[dict[str, Any]] = [
    {
        "slug": "rate-limiting",
        "name": "Rate Limiting",
        "domain": "system-design",
        "description": "Token bucket algorithms",
        "tags": ["api"],
        "difficulty": "medium",
    },
    {
        "slug": "leadership",
        "name": "Leadership",
        "domain": "behavioral",
        "description": "Leading teams through ambiguity",
        "tags": ["soft-skills"],
        "difficulty": "hard",
    },
]

_FEATURES_WITH_CORRELATIONS: list[dict[str, Any]] = [
    {
        "id": "feat-1",
        "slug": "auth-rate-limiter",
        "project": "cognito-forms",
        "title": "Auth Rate Limiter",
        "summary": "Implemented token bucket for auth API",
        "technologies": ["C#", "Redis"],
        "patterns": ["token-bucket"],
        "status": "complete",
        "topic_correlations": [
            {"slug": "rate-limiting", "domain": "system-design", "score": 2},
        ],
    },
    {
        "id": "feat-2",
        "slug": "team-restructure",
        "project": "cognito-forms",
        "title": "Team Restructure Initiative",
        "summary": "Led cross-team initiative during org restructure",
        "technologies": [],
        "patterns": [],
        "status": "complete",
        "topic_correlations": [
            {"slug": "leadership", "domain": "behavioral", "score": 2},
        ],
    },
]


def test_generate_features_creates_pages(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    count = gen.generate_features(_FEATURES_WITH_CORRELATIONS)
    assert count == 2
    assert (tmp_path / "03_Features" / "auth-rate-limiter.md").exists()
    assert (tmp_path / "03_Features" / "team-restructure.md").exists()


def test_features_have_frontmatter(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_features(_FEATURES_WITH_CORRELATIONS)
    content = (tmp_path / "03_Features" / "auth-rate-limiter.md").read_text(encoding="utf-8")
    assert "type: feature" in content
    assert "project: cognito-forms" in content


def test_features_link_to_stories(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_features(_FEATURES_WITH_CORRELATIONS)
    content = (tmp_path / "03_Features" / "auth-rate-limiter.md").read_text(encoding="utf-8")
    assert "[[story-auth-rate-limiter-rate-limiting]]" in content


def _story_path(tmp_path: Path, slug: str) -> Path:
    return tmp_path / "04_Interview_Stories" / f"{slug}.md"


def test_generate_stories_creates_pages(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    count = gen.generate_interview_stories(_FEATURES_WITH_CORRELATIONS, _SAMPLE_KB_FOR_STORIES)
    assert count == 2
    assert _story_path(tmp_path, "story-auth-rate-limiter-rate-limiting").exists()
    assert _story_path(tmp_path, "story-team-restructure-leadership").exists()


def test_stories_use_domain_specific_template(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_interview_stories(_FEATURES_WITH_CORRELATIONS, _SAMPLE_KB_FOR_STORIES)
    # System design story should use ADR format
    sd_content = _story_path(tmp_path, "story-auth-rate-limiter-rate-limiting").read_text(
        encoding="utf-8"
    )
    assert "## Context & Constraints" in sd_content
    assert "## Bottleneck Identification" in sd_content
    # Behavioral story should use ISTART format
    bh_content = _story_path(tmp_path, "story-team-restructure-leadership").read_text(
        encoding="utf-8"
    )
    assert "## Introduction" in bh_content
    assert "## Takeaway" in bh_content


def test_stories_have_srs_flashcards(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_interview_stories(_FEATURES_WITH_CORRELATIONS, _SAMPLE_KB_FOR_STORIES)
    content = _story_path(tmp_path, "story-auth-rate-limiter-rate-limiting").read_text(
        encoding="utf-8"
    )
    assert "::" in content  # SRS flashcard syntax


def test_stories_have_managed_blocks(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_interview_stories(_FEATURES_WITH_CORRELATIONS, _SAMPLE_KB_FOR_STORIES)
    content = _story_path(tmp_path, "story-auth-rate-limiter-rate-limiting").read_text(
        encoding="utf-8"
    )
    assert "<!-- BEGIN MANAGED -->" in content
    assert "<!-- END MANAGED -->" in content


def test_stories_link_to_kb_topic(tmp_path: Path) -> None:
    """DAG rule: Stories link to KB topics (outbound)."""
    gen = VaultGenerator(tmp_path)
    gen.generate_interview_stories(_FEATURES_WITH_CORRELATIONS, _SAMPLE_KB_FOR_STORIES)
    content = _story_path(tmp_path, "story-auth-rate-limiter-rate-limiting").read_text(
        encoding="utf-8"
    )
    assert "[[rate-limiting]]" in content


def test_stories_link_to_source_feature(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_interview_stories(_FEATURES_WITH_CORRELATIONS, _SAMPLE_KB_FOR_STORIES)
    content = _story_path(tmp_path, "story-auth-rate-limiter-rate-limiting").read_text(
        encoding="utf-8"
    )
    assert "[[auth-rate-limiter]]" in content


def test_generate_meta_creates_dashboard(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_meta(_SAMPLE_KB_FOR_STORIES, _FEATURES_WITH_CORRELATIONS, [])
    assert (tmp_path / "Meta" / "dashboard.md").exists()


def test_meta_has_coverage_stats(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_meta(_SAMPLE_KB_FOR_STORIES, _FEATURES_WITH_CORRELATIONS, [])
    content = (tmp_path / "Meta" / "dashboard.md").read_text(encoding="utf-8")
    assert "Topics covered:" in content
    assert "Features:" in content


def test_knowledge_bank_renders_talking_points(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    page = tmp_path / "01_Knowledge_Bank" / "system-design" / "rate-limiting.md"
    content = page.read_text(encoding="utf-8")
    assert "## Key Concepts" in content
    assert "- Token bucket allows bursty traffic while maintaining average rate" in content
    assert "- Leaky bucket enforces strict constant-rate output" in content
    assert "- Distributed rate limiting requires shared state via Redis or similar" in content


def test_generate_meta_creates_vault_claude_md(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_meta(_SAMPLE_KB_FOR_STORIES, _FEATURES_WITH_CORRELATIONS, [])
    claude_md = tmp_path / "CLAUDE.md"
    assert claude_md.exists()
    content = claude_md.read_text(encoding="utf-8")
    assert "# Interview Prep Vault" in content
    assert "## Vault Structure" in content
    assert "## Study Workflow" in content


def test_vault_claude_md_has_coverage_stats(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_meta(_SAMPLE_KB_FOR_STORIES, _FEATURES_WITH_CORRELATIONS, [])
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    # _FEATURES_WITH_CORRELATIONS has 2 features, each with 1 correlation
    # _SAMPLE_KB_FOR_STORIES has 2 topics, both covered
    assert "2 of 2 topics" in content
    assert "2 features" in content
    assert "2 interview stories" in content


def test_knowledge_bank_omits_key_concepts_when_empty(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    page = tmp_path / "01_Knowledge_Bank" / "ood" / "observer-pattern.md"
    content = page.read_text(encoding="utf-8")
    assert "## Key Concepts" not in content


def test_knowledge_bank_renders_related_topics(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    page = tmp_path / "01_Knowledge_Bank" / "system-design" / "rate-limiting.md"
    content = page.read_text(encoding="utf-8")
    assert "## Related Topics" in content
    assert "[[load-balancing]]" in content
    assert "[[cdn]]" in content
    assert "[[api-gateway]]" in content


def test_knowledge_bank_omits_related_topics_when_empty(tmp_path: Path) -> None:
    gen = VaultGenerator(tmp_path)
    gen.generate_knowledge_bank(_SAMPLE_KB, _SAMPLE_FEATURES)
    page = tmp_path / "01_Knowledge_Bank" / "ood" / "observer-pattern.md"
    content = page.read_text(encoding="utf-8")
    assert "## Related Topics" not in content
