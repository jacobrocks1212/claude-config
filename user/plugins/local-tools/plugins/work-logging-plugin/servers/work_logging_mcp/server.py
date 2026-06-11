from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import anyio
from mcp.server.fastmcp import FastMCP

from servers.work_logging_mcp.extract import extract_summary as _extract_summary
from servers.work_logging_mcp.knowledge_bank import KnowledgeBank
from servers.work_logging_mcp.managed_blocks import write_managed_block as _write_managed_block
from servers.work_logging_mcp.persistence import FeaturesWriter, ImportIndexWriter, WorkLogWriter
from servers.work_logging_mcp.vault_generator import VaultGenerator

_DEFAULT_DATA = Path.home() / ".interview-prep"
_DEFAULT_KB = _DEFAULT_DATA / "knowledge-bank"


def _extract_title(file_path: Path) -> str:
    """Extract the first H1 heading from a markdown file."""
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    except OSError:
        pass
    return file_path.stem


def create_server(
    kb_path: Path | None = None,
    data_path: Path | None = None,
) -> FastMCP:
    resolved_kb = kb_path or _DEFAULT_KB
    resolved_data = data_path or _DEFAULT_DATA

    bank = KnowledgeBank(resolved_kb)
    work_log = WorkLogWriter(resolved_data, auto_commit=False)
    features = FeaturesWriter(resolved_data, auto_commit=False)
    import_index = ImportIndexWriter(resolved_data, auto_commit=False)

    server = FastMCP("work-logging")

    @server.tool()
    def get_kb_index() -> dict[str, Any]:
        """Return a compact index of all knowledge bank topics for semantic scanning."""
        return {
            "topics": [
                {
                    "slug": e.slug,
                    "name": e.name,
                    "domain": e.domain.value,
                    "tags": e.tags,
                    "description": e.description,
                }
                for e in bank.entries
            ],
            "total": len(bank.entries),
        }

    @server.tool()
    def get_kb_topic(slug: str, domain: str) -> dict[str, Any]:
        """Retrieve the full knowledge bank entry for a specific topic."""
        entry = bank.get(slug, domain)
        if entry is None:
            return {"error": f"No entry found for slug={slug!r}, domain={domain!r}"}
        return entry.model_dump()

    @server.tool()
    def read_work_log(
        project: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        feature: str | None = None,
    ) -> dict[str, Any]:
        """Query work-log.jsonl with filters."""
        results = work_log.query(project=project, date_from=date_from, date_to=date_to)
        if feature is not None:
            results = [r for r in results if r.get("feature") == feature]
        return {"entries": results, "count": len(results)}

    @server.tool()
    def read_features(
        project: str | None = None,
        slug: str | None = None,
        has_correlations: bool | None = None,
    ) -> dict[str, Any]:
        """Query features.jsonl with filters."""
        results = features.query(project=project, slug=slug)
        if has_correlations is not None:
            if has_correlations:
                results = [r for r in results if r.get("topic_correlations")]
            else:
                results = [r for r in results if not r.get("topic_correlations")]
        return {"features": results, "count": len(results)}

    @server.tool()
    def evaluate_topic_match(
        feature_summary: str,
        topic_slug: str,
        topic_domain: str,
    ) -> dict[str, Any]:
        """Run LLM judge on a single Feature×Topic pair, return score 0-2."""
        from servers.work_logging_mcp.correlation import TopicJudge
        from servers.work_logging_mcp.correlation import evaluate_topic_match as _eval

        topic_entry = bank.get(topic_slug, topic_domain)
        if topic_entry is None:
            return {"error": f"Topic not found: {topic_slug}/{topic_domain}"}

        feature_dict: dict[str, Any] = {"summary": feature_summary}
        topic_dict: dict[str, Any] = {
            "slug": topic_entry.slug,
            "domain": topic_entry.domain.value,
            "description": topic_entry.description,
        }

        def _judge(feat: dict[str, Any], topic: dict[str, Any]) -> int:
            return 1  # Placeholder until real LLM integration

        score = _eval(feature_dict, topic_dict, judge=cast(TopicJudge, _judge))
        return {"score": score, "topic_slug": topic_slug, "topic_domain": topic_domain}

    @server.tool()
    def write_managed_block(
        file_path: str,
        content: str,
    ) -> dict[str, Any]:
        """Write content into a managed block in a vault file."""
        target = Path(file_path)
        _write_managed_block(target, content)
        return {"status": "ok", "file_path": file_path}

    @server.tool()
    def calculate_hash(
        file_path: str,
    ) -> dict[str, Any]:
        """Compute SHA-256 hash of a file for import deduplication."""
        target = Path(file_path)
        if not target.exists():
            return {"error": f"File not found: {file_path}"}
        content_hash = ImportIndexWriter.compute_hash(target)
        return {"hash": content_hash, "file_path": file_path}

    @server.tool()
    def get_study_context(
        topic_slug: str,
        topic_domain: str,
    ) -> dict[str, Any]:
        """Bundle KB entry, correlated features, and work log refs for a study session."""
        # Get KB entry
        kb_entry = bank.get(topic_slug, topic_domain)
        if kb_entry is None:
            return {"error": f"Topic not found: {topic_slug}/{topic_domain}"}

        # Find features correlated to this topic
        all_features = features.query()
        correlated = []
        for feat in all_features:
            for corr in feat.get("topic_correlations", []):
                if corr.get("slug") == topic_slug and corr.get("domain") == topic_domain:
                    correlated.append(feat)
                    break

        # Gather work log entries referenced by correlated features
        work_log_refs: list[dict[str, Any]] = []
        seen_timestamps: set[str] = set()
        for feat in correlated:
            for ts in feat.get("work_log_refs", []):
                if ts and ts not in seen_timestamps:
                    seen_timestamps.add(ts)
        if seen_timestamps:
            all_log = work_log.query()
            work_log_refs = [e for e in all_log if e.get("timestamp") in seen_timestamps]

        return {
            "topic": kb_entry.model_dump(),
            "correlated_features": correlated,
            "work_log_entries": work_log_refs,
            "summary": {
                "features_count": len(correlated),
                "work_log_count": len(work_log_refs),
            },
        }

    @server.tool()
    async def work_log_append(
        skill: str,
        project: str,
        title: str,
        summary: str,
        files_modified: list[str],
        branch: str | None = None,
        commit: str | None = None,
        phases_md: str | None = None,
        spec_md: str | None = None,
        technologies: list[str] | None = None,
        patterns: list[str] | None = None,
        technical_context: str | None = None,
        extra: dict[str, Any] | None = None,
        feature: str | None = None,
    ) -> dict[str, Any]:
        """Append a work-log entry for a completed skill invocation."""
        entry: dict[str, Any] = {
            "skill": skill,
            "project": project,
            "title": title,
            "summary": summary,
            "files_modified": files_modified,
            "branch": branch,
            "commit": commit,
            "phases_md": phases_md,
            "spec_md": spec_md,
            "technologies": technologies,
            "patterns": patterns,
            "technical_context": technical_context,
            "feature": feature,
        }
        if extra:
            entry.update(extra)
        path = await anyio.to_thread.run_sync(lambda: work_log.append(entry))
        return {"status": "ok", "persisted_to": str(path), "timestamp": entry["timestamp"]}

    @server.tool()
    async def import_artifacts(
        directory: str,
        project: str,
        artifact_types: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Scan a directory recursively for planning artifacts and import them as features."""
        types = artifact_types or ["spec", "phases", "research"]
        target_dir = Path(directory)

        if not target_dir.exists():
            return {"error": f"Directory not found: {directory}"}

        # Map artifact types to filename patterns
        type_to_filename: dict[str, str] = {
            "spec": "SPEC.md",
            "phases": "PHASES.md",
            "research": "RESEARCH.md",
        }

        # Scan for matching files
        found_files: list[tuple[Path, str]] = []
        for atype in types:
            filename = type_to_filename.get(atype)
            if filename:
                for match in target_dir.rglob(filename):
                    found_files.append((match, atype))

        imported: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []

        for file_path, artifact_type in found_files:
            content_hash = ImportIndexWriter.compute_hash(file_path)

            if dry_run:
                title = _extract_title(file_path)
                imported.append(
                    {
                        "title": title,
                        "path": str(file_path),
                        "artifact_type": artifact_type,
                        "content_hash": content_hash,
                    }
                )
                continue

            # Check import index for dedup
            _fp = file_path
            _ch = content_hash
            _proj = project
            _at = artifact_type

            def _add_index(
                fp: Path = _fp,
                ch: str = _ch,
                pr: str = _proj,
                at: str = _at,
            ) -> dict[str, Any]:
                return import_index.add(
                    source_path=str(fp),
                    content_hash=ch,
                    project=pr,
                    artifact_type=at,
                )

            index_result = await anyio.to_thread.run_sync(_add_index)

            if index_result["status"] == "skipped":
                skipped.append(
                    {
                        "path": str(file_path),
                        "reason": "already_imported",
                    }
                )
                continue

            # Extract metadata and create feature
            title = _extract_title(file_path)
            slug = file_path.parent.name or file_path.stem

            feature_entry: dict[str, Any] = {
                "slug": slug,
                "project": project,
                "title": title,
                "summary": (
                    _extract_summary(file_path)
                    or f"Imported from {artifact_type}: {file_path.name}"
                ),
                "artifact_type": artifact_type,
                "source_path": str(file_path),
            }

            def _append_import(e: dict[str, Any] = feature_entry) -> Path:
                return features.append(e)

            await anyio.to_thread.run_sync(_append_import)

            imported.append(
                {
                    "title": title,
                    "path": str(file_path),
                    "artifact_type": artifact_type,
                }
            )

        return {
            "imported": imported,
            "skipped": skipped,
            "total": len(found_files),
            "progress": {
                "files_scanned": len(found_files),
                "files_imported": len(imported),
                "files_skipped": len(skipped),
            },
        }

    @server.tool()
    async def synthesize_features(
        project: str | None = None,
        include_correlations: bool = True,
        use_headless: bool = False,
    ) -> dict[str, Any]:
        """Synthesize feature-level entries from orphaned work log records."""
        from servers.work_logging_mcp.correlation import (
            TopicJudge,
            correlate_feature,
        )

        # Read all work log entries
        all_entries = work_log.query(project=project)

        # Filter to orphaned entries (no feature tag)
        orphaned = [e for e in all_entries if not e.get("feature")]

        if not orphaned:
            return {
                "features_created": 0,
                "orphaned_remaining": 0,
                "correlations_added": 0,
                "progress": {
                    "entries_processed": 0,
                    "groups_found": 0,
                },
            }

        # Group by project
        groups: dict[str, list[dict[str, Any]]] = {}
        for entry in orphaned:
            proj = str(entry.get("project", "unknown"))
            groups.setdefault(proj, []).append(entry)

        features_created = 0
        correlations_added = 0

        # Select judge once before the loop
        judge: TopicJudge
        if use_headless and include_correlations:
            from servers.work_logging_mcp.headless_judge import HeadlessJudge

            judge = cast(TopicJudge, HeadlessJudge())
        else:

            def _judge_impl(feat: dict[str, Any], topic: dict[str, Any]) -> int:
                """Placeholder judge — returns 1 for all (no real LLM yet)."""
                return 1

            judge = cast(TopicJudge, _judge_impl)

        for proj, entries in groups.items():
            # Create one feature per project group
            # Use first entry's title as basis for slug
            first = entries[0]
            title_words = str(first.get("title", "")).lower().split()
            slug = "-".join(title_words[:4]) if title_words else proj

            all_files: list[str] = []
            all_summaries: list[str] = []
            for e in entries:
                all_files.extend(e.get("files_modified", []))
                all_summaries.append(str(e.get("summary", "")))

            feature_entry: dict[str, Any] = {
                "slug": slug,
                "project": proj,
                "title": str(first.get("title", slug)),
                "summary": "; ".join(all_summaries),
                "work_log_refs": [e.get("timestamp") for e in entries],
                "technologies": list({t for e in entries for t in (e.get("technologies") or [])}),
                "patterns": list({p for e in entries for p in (e.get("patterns") or [])}),
                "status": "synthesized",
            }

            # Run topic correlation if requested
            if include_correlations:
                kb_entries = [
                    {
                        "slug": e.slug,
                        "domain": e.domain.value,
                        "description": e.description,
                        "tags": e.tags,
                    }
                    for e in bank.entries
                ]

                def _scorer_impl(feature_summary: str, topic_description: str) -> float:
                    """Simple keyword overlap scorer."""
                    fw = set(feature_summary.lower().split())
                    tw = set(topic_description.lower().split())
                    return float(len(fw & tw))

                correlations = correlate_feature(
                    feature_entry,
                    kb_entries,
                    scorer=_scorer_impl,
                    judge=judge,
                )
                if correlations:
                    feature_entry["topic_correlations"] = correlations
                    correlations_added += len(correlations)

            def _append_feature(e: dict[str, Any] = feature_entry) -> Path:
                return features.append(e)

            await anyio.to_thread.run_sync(_append_feature)
            features_created += 1

        return {
            "features_created": features_created,
            "orphaned_remaining": 0,
            "correlations_added": correlations_added,
            "progress": {
                "entries_processed": len(orphaned),
                "groups_found": len(groups),
            },
        }

    @server.tool()
    async def generate_vault(
        output_dir: str | None = None,
    ) -> dict[str, Any]:
        """Generate the full Obsidian interview prep vault."""
        vault_path = Path(output_dir) if output_dir else resolved_data / "vault"
        generator = VaultGenerator(vault_path)

        # Gather data
        kb_data = [
            {
                "slug": e.slug,
                "name": e.name,
                "domain": e.domain.value,
                "description": e.description,
                "tags": e.tags,
                "difficulty": (
                    e.difficulty.value if hasattr(e.difficulty, "value") else str(e.difficulty)
                ),
                "interview_questions": e.interview_questions,
                "talking_points": e.talking_points,
                "related_topics": e.related_topics,
            }
            for e in bank.entries
        ]
        all_features = features.query()
        all_work_log = work_log.query()

        # Generate all collections (blocking I/O)
        def _generate() -> tuple[int, int, int, int]:
            kb_count = generator.generate_knowledge_bank(kb_data, all_features)
            work_count = generator.generate_work_history(all_work_log, all_features)
            feat_count = generator.generate_features(all_features)
            story_count = generator.generate_interview_stories(all_features, kb_data)
            generator.generate_meta(kb_data, all_features, all_work_log)
            return kb_count, work_count, feat_count, story_count

        kb_count, work_count, feat_count, story_count = await anyio.to_thread.run_sync(_generate)

        return {
            "pages_generated": kb_count + work_count + feat_count,
            "stories_generated": story_count,
            "topics_covered": len(
                {
                    corr.get("slug")
                    for f in all_features
                    for corr in f.get("topic_correlations", [])
                }
            ),
            "output_dir": str(vault_path),
            "progress": {
                "stages_completed": [
                    "knowledge_bank",
                    "work_history",
                    "features",
                    "stories",
                    "meta",
                ],
                "total_stages": 5,
            },
        }

    return server


mcp = create_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
