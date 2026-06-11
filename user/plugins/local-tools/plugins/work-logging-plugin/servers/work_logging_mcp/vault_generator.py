"""Obsidian vault generation engine.

Generates interlinked markdown pages across 5 collections:
    01_Knowledge_Bank/ — canonical topic references
    02_Work_History/   — granular work log entries
    03_Features/       — initiative-level narratives
    04_Interview_Stories/ — domain-specific study artifacts
    Meta/              — dashboard and coverage data
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from servers.work_logging_mcp.managed_blocks import write_managed_block


class VaultGenerator:
    """Orchestrates full Obsidian vault generation."""

    def __init__(self, output_dir: Path) -> None:
        self._output = output_dir

    def generate_knowledge_bank(
        self,
        kb_entries: list[dict[str, Any]],
        features: list[dict[str, Any]],
    ) -> int:
        """Generate 01_Knowledge_Bank/{domain}/{slug}.md pages.

        Returns count of pages generated.
        """
        count = 0
        for entry in kb_entries:
            domain = str(entry.get("domain", "unknown"))
            slug = str(entry.get("slug", "untitled"))
            page_dir = self._output / "01_Knowledge_Bank" / domain
            page_dir.mkdir(parents=True, exist_ok=True)
            page_path = page_dir / f"{slug}.md"

            # Find correlated stories
            correlated_stories: list[str] = []
            for feat in features:
                for corr in feat.get("topic_correlations", []):
                    if corr.get("slug") == slug and corr.get("domain") == domain:
                        correlated_stories.append(feat.get("slug", ""))

            frontmatter = _format_frontmatter(
                {
                    "id": f"kb-{domain}-{slug}",
                    "type": "knowledge-bank",
                    "domain": domain,
                    "tags": entry.get("tags", []),
                    "difficulty": entry.get("difficulty", "medium"),
                    "created": _now_iso(),
                    "updated": _now_iso(),
                }
            )

            body_lines = [
                frontmatter,
                f"# {entry.get('name', slug)}\n",
                f"{entry.get('description', '')}\n",
            ]

            if entry.get("talking_points"):
                body_lines.append("## Key Concepts\n")
                for point in entry["talking_points"]:
                    body_lines.append(f"- {point}")
                body_lines.append("")

            if correlated_stories:
                body_lines.append("## Related Stories\n")
                for story_slug in correlated_stories:
                    body_lines.append(f"- [[{story_slug}]]")
                body_lines.append("")

            if entry.get("interview_questions"):
                body_lines.append("## Interview Questions\n")
                for q in entry["interview_questions"]:
                    body_lines.append(f"- {q}")
                body_lines.append("")

            if entry.get("related_topics"):
                body_lines.append("## Related Topics\n")
                for topic in entry["related_topics"]:
                    body_lines.append(f"- [[{topic}]]")
                body_lines.append("")

            page_path.write_text("\n".join(body_lines), encoding="utf-8")
            count += 1
        return count

    def generate_work_history(
        self,
        work_log: list[dict[str, Any]],
        features: list[dict[str, Any]],
    ) -> int:
        """Generate 02_Work_History/{date}-{slug}.md pages.

        Links only to parent Feature (outbound). No direct KB links.
        Returns count of pages generated.
        """
        count = 0
        hist_dir = self._output / "02_Work_History"
        hist_dir.mkdir(parents=True, exist_ok=True)

        for entry in work_log:
            ts = str(entry.get("timestamp", ""))
            date_str = ts[:10] if len(ts) >= 10 else "unknown"
            title = str(entry.get("title", "untitled"))
            slug = title.lower().replace(" ", "-")[:40]
            page_path = hist_dir / f"{date_str}-{slug}.md"

            # Find parent feature
            parent_feature: str | None = None
            feature_tag = entry.get("feature")
            if feature_tag:
                parent_feature = str(feature_tag)
            else:
                # Check if any feature references this timestamp
                for feat in features:
                    refs = feat.get("work_log_refs", [])
                    if ts in refs:
                        parent_feature = feat.get("slug")
                        break

            frontmatter = _format_frontmatter(
                {
                    "id": f"work-{date_str}-{slug}",
                    "type": "work-history",
                    "project": entry.get("project", "unknown"),
                    "date": date_str,
                    "parent_feature": f"[[{parent_feature}]]" if parent_feature else None,
                    "created": _now_iso(),
                    "updated": _now_iso(),
                }
            )

            body_lines = [
                frontmatter,
                f"# {title}\n",
                f"**Project:** {entry.get('project', 'unknown')}  ",
                f"**Date:** {date_str}  ",
                f"**Skill:** {entry.get('skill', 'unknown')}\n",
            ]

            if parent_feature:
                body_lines.append(f"**Feature:** [[{parent_feature}]]\n")

            summary = entry.get("summary", "")
            if summary:
                body_lines.append(f"## Summary\n\n{summary}\n")

            files = entry.get("files_modified", [])
            if files:
                body_lines.append("## Files Modified\n")
                for f in files:
                    body_lines.append(f"- `{f}`")
                body_lines.append("")

            page_path.write_text("\n".join(body_lines), encoding="utf-8")
            count += 1
        return count

    def generate_features(self, features: list[dict[str, Any]]) -> int:
        """Generate 03_Features/{slug}.md pages.

        Links to Interview Stories generated from this feature (outbound).
        Returns count of pages generated.
        """
        count = 0
        feat_dir = self._output / "03_Features"
        feat_dir.mkdir(parents=True, exist_ok=True)

        for feat in features:
            slug = str(feat.get("slug", "untitled"))
            page_path = feat_dir / f"{slug}.md"

            # Stories are named after the feature
            story_links: list[str] = []
            for corr in feat.get("topic_correlations", []):
                story_slug = f"story-{slug}-{corr.get('slug', '')}"
                story_links.append(story_slug)

            frontmatter = _format_frontmatter(
                {
                    "id": f"feat-{slug}",
                    "type": "feature",
                    "project": feat.get("project", "unknown"),
                    "status": feat.get("status", "unknown"),
                    "technologies": feat.get("technologies", []),
                    "created": _now_iso(),
                    "updated": _now_iso(),
                }
            )

            body_lines = [
                frontmatter,
                f"# {feat.get('title', slug)}\n",
                f"**Project:** {feat.get('project', 'unknown')}  ",
                f"**Status:** {feat.get('status', 'unknown')}\n",
                "## Summary\n",
                f"{feat.get('summary', '')}\n",
            ]

            technologies = feat.get("technologies", [])
            if technologies:
                body_lines.append("## Technologies\n")
                for tech in technologies:
                    body_lines.append(f"- {tech}")
                body_lines.append("")

            patterns = feat.get("patterns", [])
            if patterns:
                body_lines.append("## Patterns\n")
                for p in patterns:
                    body_lines.append(f"- {p}")
                body_lines.append("")

            if story_links:
                body_lines.append("## Interview Stories\n")
                for story in story_links:
                    body_lines.append(f"- [[{story}]]")
                body_lines.append("")

            page_path.write_text("\n".join(body_lines), encoding="utf-8")
            count += 1
        return count

    def generate_interview_stories(
        self,
        features: list[dict[str, Any]],
        kb_entries: list[dict[str, Any]],
    ) -> int:
        """Generate 04_Interview_Stories/{slug}.md pages.

        Uses domain-specific narrative templates. Managed blocks for generated content.
        SRS flashcard formatting. Links to KB topic (outbound) and source Feature (outbound).
        Returns count of stories generated.
        """
        count = 0
        stories_dir = self._output / "04_Interview_Stories"
        stories_dir.mkdir(parents=True, exist_ok=True)

        for feat in features:
            feat_slug = str(feat.get("slug", ""))
            for corr in feat.get("topic_correlations", []):
                topic_slug = str(corr.get("slug", ""))
                topic_domain = str(corr.get("domain", ""))
                story_slug = f"story-{feat_slug}-{topic_slug}"
                page_path = stories_dir / f"{story_slug}.md"

                # Find the KB entry for this topic
                kb_entry: dict[str, Any] = {}
                for kb in kb_entries:
                    if kb.get("slug") == topic_slug and kb.get("domain") == topic_domain:
                        kb_entry = kb
                        break

                frontmatter = _format_frontmatter(
                    {
                        "id": story_slug,
                        "type": "interview-story",
                        "domain": topic_domain,
                        "source_feature": f"[[{feat_slug}]]",
                        "correlated_topics": [f"[[{topic_slug}]]"],
                        "difficulty": kb_entry.get("difficulty", "medium"),
                        "tags": ["#review", f"interview/{topic_domain}"],
                        "created": _now_iso(),
                        "updated": _now_iso(),
                    }
                )

                # Generate domain-specific narrative
                narrative = _generate_narrative(feat, kb_entry, topic_domain)

                # Build page with managed block
                header = "\n".join(
                    [
                        frontmatter,
                        f"# {feat.get('title', '')} × {kb_entry.get('name', topic_slug)}\n",
                        f"**Feature:** [[{feat_slug}]]  ",
                        f"**Topic:** [[{topic_slug}]]\n",
                    ]
                )

                # Write header first, then managed block
                page_path.write_text(header, encoding="utf-8")
                write_managed_block(page_path, narrative)
                count += 1
        return count

    def generate_meta(
        self,
        kb_entries: list[dict[str, Any]],
        features: list[dict[str, Any]],
        work_log: list[dict[str, Any]],
    ) -> None:
        """Generate Meta/dashboard.md with coverage data."""
        meta_dir = self._output / "Meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        dashboard = meta_dir / "dashboard.md"

        # Coverage analysis
        topics_with_stories: set[str] = set()
        for feat in features:
            for corr in feat.get("topic_correlations", []):
                topics_with_stories.add(str(corr.get("slug", "")))

        total_topics = len(kb_entries)
        covered = len(topics_with_stories)
        coverage_pct = (covered / total_topics * 100) if total_topics > 0 else 0

        frontmatter = _format_frontmatter(
            {
                "id": "meta-dashboard",
                "type": "meta",
                "created": _now_iso(),
                "updated": _now_iso(),
            }
        )

        body_lines = [
            frontmatter,
            "# Interview Prep Dashboard\n",
            "## Coverage\n",
            f"- **Topics covered:** {covered}/{total_topics} ({coverage_pct:.0f}%)",
            f"- **Features:** {len(features)}",
            f"- **Work log entries:** {len(work_log)}",
            f"- **Stories generated:** "
            f"{sum(len(f.get('topic_correlations', [])) for f in features)}\n",
            "## Gaps\n",
        ]

        uncovered = [kb for kb in kb_entries if str(kb.get("slug", "")) not in topics_with_stories]
        if uncovered:
            for kb in uncovered[:10]:
                name = kb.get("name", kb.get("slug", ""))
                domain_str = kb.get("domain", "")
                body_lines.append(f"- {name} ({domain_str})")
            if len(uncovered) > 10:
                body_lines.append(f"- ... and {len(uncovered) - 10} more")
        else:
            body_lines.append("- All topics covered!")

        body_lines.append("")
        dashboard.write_text("\n".join(body_lines), encoding="utf-8")

        # Generate vault-level CLAUDE.md for study sessions
        n_stories = sum(len(f.get("topic_correlations", [])) for f in features)
        claude_md = self._output / "CLAUDE.md"
        claude_lines = [
            "# Interview Prep Vault\n",
            "Obsidian vault for interview preparation, generated from real work.\n",
            "## Vault Structure\n",
            "| Directory | Purpose | Navigation |",
            "|-----------|---------|------------|",
            "| `01_Knowledge_Bank/{domain}/` | Topic references | Topic deep-dives |",
            "| `02_Work_History/` | Granular work log entries | Browse chronologically |",
            "| `03_Features/` | Initiative-level summaries | Strongest examples |",
            "| `04_Interview_Stories/` | Study artifacts | Primary study material |",
            "| `Meta/` | Dashboard with coverage stats | Track progress |\n",
            "## Coverage\n",
            f"- **{covered} of {total_topics} topics** have correlated stories from your work",
            f"- **{len(features)} features** synthesized from work log",
            f"- **{n_stories} interview stories** generated across domains\n",
            "## Study Workflow\n",
            "1. Pick a topic from `01_Knowledge_Bank/` — read Key Concepts and Questions",
            "2. Follow `## Related Stories` links to `04_Interview_Stories/` pages",
            "3. Each story has a `<!-- BEGIN MANAGED -->` block — ask Claude to elaborate",
            "4. Use `get_study_context` to load all context for a topic",
            "5. Practice answering Interview Questions using your stories as ammunition\n",
            "## MCP Tools Available\n",
            "| Tool | Use For |",
            "|------|---------|",
            "| `get_study_context` | KB entry + correlated features + work log |",
            "| `get_kb_topic` | Full KB entry by slug and domain |",
            "| `read_features` | Query features with filters |",
            "| `read_work_log` | Query work log with filters |",
            "| `write_managed_block` | Write content into story managed blocks |\n",
            "## Domains\n",
            "- **system-design** — ADR format (Context, Baseline, Bottleneck, Decision, Ops)",
            "- **behavioral** — (I)STAR(T) format (Intro, Situation, Task, Action, Result)",
            "- **ood** — Entity-Pattern-Extensibility format",
            "- **algorithms** — Problem-Approach-Complexity-Usage format",
            "",
        ]
        claude_md.write_text("\n".join(claude_lines), encoding="utf-8")


def _format_frontmatter(data: dict[str, Any]) -> str:
    """Format a dict as YAML frontmatter."""
    lines = ["---"]
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---\n")
    return "\n".join(lines)


def _now_iso() -> str:
    """Return current date in ISO format."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _generate_narrative(
    feature: dict[str, Any],
    topic: dict[str, Any],
    domain: str,
) -> str:
    """Generate domain-specific narrative with SRS flashcards."""
    title = str(feature.get("title", ""))
    summary = str(feature.get("summary", ""))
    topic_name = str(topic.get("name", topic.get("slug", "")))

    if domain == "behavioral":
        return _format_behavioral(title, summary, topic_name)
    elif domain == "system-design":
        return _format_system_design(title, summary, topic_name)
    elif domain == "ood":
        return _format_ood(title, summary, topic_name)
    else:
        return _format_algorithm(title, summary, topic_name)


def _format_behavioral(title: str, summary: str, topic_name: str) -> str:
    """(I)STAR(T) framework for behavioral narratives."""
    return f"""## Introduction

{title} — demonstrating {topic_name}.

## Situation

{summary}

## Task

Engineering mandate within this context.

## Action

First-person execution narrative.

## Result

Quantifiable outcomes and metrics.

## Takeaway

Retrospective insight demonstrating growth.

What did you learn from {title}?
:: {summary}"""


def _format_system_design(title: str, summary: str, topic_name: str) -> str:
    """ADR format for system design narratives."""
    return f"""## Context & Constraints

{summary}

## Baseline Design

Initial approach before optimization.

## Bottleneck Identification

Specific point of failure at scale.

## Decision & Tradeoffs

Architectural pivot with explicitly accepted costs.

## Operational Reality

Instrumentation and post-deployment maintenance.

What tradeoff did you accept in {title}?
:: {summary}"""


def _format_ood(title: str, summary: str, topic_name: str) -> str:
    """Entity-Pattern-Extensibility format for OOD narratives."""
    return f"""## Core Entities

Primary objects and state within {title}.

## Pattern Applied

{topic_name} — canonical pattern utilized.

## Extensibility Justification

How the design enables future expansion.

How does {topic_name} apply to {title}?
:: {summary}"""


def _format_algorithm(title: str, summary: str, topic_name: str) -> str:
    """Problem-Approach-Complexity-Usage format for algorithm narratives."""
    return f"""## Problem

{summary}

## Approach

Algorithm or data structure applied: {topic_name}.

## Complexity

Time and space complexity analysis.

## Your Usage

How you applied this in {title}.

How did you use {topic_name} in practice?
:: {summary}"""
