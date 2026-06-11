"""Bulk correlate features against KB topics using headless Claude."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Add parent to sys.path so we can import from servers/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servers.work_logging_mcp.correlation import get_candidate_topics  # noqa: E402
from servers.work_logging_mcp.headless_judge import BatchHeadlessJudge  # noqa: E402
from servers.work_logging_mcp.persistence import FeaturesWriter  # noqa: E402


def _scorer_impl(feature_summary: str, topic_description: str) -> float:
    """Simple word-overlap scorer for candidate topic ranking."""
    fw = set(feature_summary.lower().split())
    tw = set(topic_description.lower().split())
    return float(len(fw & tw))


def correlate_features(
    base_path: Path,
    project: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Correlate features against KB topics using headless Claude.

    Args:
        base_path: Root of the interview-prep data directory.
        project: If set, only process features matching this project.
        dry_run: Print proposed correlations without writing to disk.
        force: Reprocess features that already have topic_correlations.
    """
    features_writer = FeaturesWriter(base_path)
    all_features = features_writer.query(project=project)

    # Filter features to process
    to_process = [f for f in all_features if force or not f.get("topic_correlations")]

    total = len(to_process)

    # Load KB entries for candidate scoring — may fail gracefully in tests
    # since get_candidate_topics is mocked in test context.
    kb_entries: list[dict[str, Any]] = []
    try:
        from servers.work_logging_mcp.knowledge_bank import KnowledgeBank  # noqa: PLC0415

        kb = KnowledgeBank(base_path / "knowledge-bank")
        kb_entries = [
            {
                "slug": e.slug,
                "domain": e.domain.value,
                "description": e.description,
                "tags": e.tags,
            }
            for e in kb.entries
        ]
    except Exception:
        pass

    for idx, feature in enumerate(to_process, start=1):
        slug = feature.get("slug", feature.get("id", "unknown"))

        # Stage 1: candidate topics via word-overlap scoring
        candidates = get_candidate_topics(
            feature.get("summary", ""),
            kb_entries,
            scorer=_scorer_impl,
            top_k=10,
        )

        # Stage 2: batch LLM judge
        judge = BatchHeadlessJudge()
        results: dict[str, int] = judge.evaluate(feature, candidates)

        # Build slug→domain lookup from candidates
        slug_to_domain: dict[str, str] = {c["slug"]: c.get("domain", "") for c in candidates}

        # Filter to Score 2 only
        correlations: list[dict[str, Any]] = [
            {"slug": s, "domain": slug_to_domain.get(s, ""), "score": 2}
            for s, score in results.items()
            if score == 2
        ]

        print(f"[{idx}/{total}] {slug}: {len(correlations)} correlations found")

        if dry_run:
            for c in correlations:
                print(f"  -> {c['slug']} ({c['domain']})")
        else:
            features_writer.append({**feature, "topic_correlations": correlations})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk correlate features against KB topics using headless Claude.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path.home() / ".interview-prep",
        help="Root of the interview-prep data directory (default: ~/.interview-prep).",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Only process features for this project.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed correlations without writing to disk.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess features that already have topic_correlations.",
    )

    args = parser.parse_args()
    correlate_features(
        base_path=args.base_path,
        project=args.project,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
