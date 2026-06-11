"""Knowledge bank: load, validate, and query YAML-based interview topic entries."""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class Domain(StrEnum):
    SYSTEM_DESIGN = "system-design"
    BEHAVIORAL = "behavioral"
    ALGORITHMS = "algorithms"
    OOD = "ood"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class KnowledgeBankEntry(BaseModel):
    slug: str
    name: str
    domain: Domain
    tags: list[str]
    description: str
    interview_questions: list[str]
    talking_points: list[str]
    related_topics: list[str]
    difficulty: Difficulty


class KnowledgeBank:
    """Loads and indexes all knowledge bank entries from ``base_path/{domain}/*.yaml``."""

    def __init__(self, base_path: Path) -> None:
        self._entries: list[KnowledgeBankEntry] = []
        self._index: dict[tuple[str, str], KnowledgeBankEntry] = {}

        for domain in Domain:
            domain_dir = base_path / domain.value
            if not domain_dir.is_dir():
                continue
            for yaml_file in sorted(domain_dir.glob("*.yaml")):
                self._load_file(yaml_file)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file(self, path: Path) -> None:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            logger.warning("Skipping %s — YAML parse error: %s", path, exc)
            return

        if not isinstance(raw, dict):
            logger.warning("Skipping %s — expected a YAML mapping, got %s", path, type(raw))
            return

        try:
            entry = KnowledgeBankEntry.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Skipping %s — validation error: %s", path, exc)
            return

        key = (entry.slug, entry.domain.value)
        if key in self._index:
            logger.warning(
                "Duplicate slug+domain (%s, %s) in %s — skipping", entry.slug, entry.domain, path
            )
            return

        self._entries.append(entry)
        self._index[key] = entry

    @staticmethod
    def _count_overlaps(query_set: set[str], entry_tags: list[str]) -> int:
        count = 0
        for tag in entry_tags:
            if tag in query_set:
                count += 1
            elif "-" in tag:
                parts = set(tag.split("-"))
                if parts <= query_set:
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def entries(self) -> list[KnowledgeBankEntry]:
        """Return all successfully loaded entries."""
        return list(self._entries)

    def get(self, slug: str, domain: str) -> KnowledgeBankEntry | None:
        """Look up a single entry by slug and domain value."""
        return self._index.get((slug, domain))

    def query_by_tags(
        self, tags: list[str], threshold: int = 1
    ) -> list[tuple[KnowledgeBankEntry, int]]:
        """Return ``(entry, overlap_count)`` pairs sorted descending by overlap.

        Only entries with ``overlap_count >= threshold`` are included.
        """
        query_set = set(tags)
        results: list[tuple[KnowledgeBankEntry, int]] = []
        for entry in self._entries:
            overlap = self._count_overlaps(query_set, entry.tags)
            if overlap >= threshold:
                results.append((entry, overlap))
        results.sort(key=lambda pair: pair[1], reverse=True)
        return results
