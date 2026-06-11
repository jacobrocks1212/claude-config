"""Enrich thin feature summaries by extracting text from source markdown files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Add parent to sys.path so we can import from servers/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servers.work_logging_mcp.extract import extract_summary  # noqa: E402
from servers.work_logging_mcp.persistence import FeaturesWriter  # noqa: E402

_DEFAULT_BASE = Path.home() / ".interview-prep"
_THIN_THRESHOLD = 100


def _enrich_features(
    base_path: Path,
    project: str | None,
    dry_run: bool,
    force: bool,
) -> None:
    writer = FeaturesWriter(base_path)
    features: list[dict[str, Any]] = writer.query(project=project)

    candidates = (
        features
        if force
        else [f for f in features if len(str(f.get("summary", ""))) <= _THIN_THRESHOLD]
    )

    total = len(candidates)
    for idx, feature in enumerate(candidates, start=1):
        slug = str(feature.get("slug", ""))
        source_path_raw = feature.get("source_path")
        if not source_path_raw:
            print(f"[{idx}/{total}] {slug}: no source_path, skipping")
            continue

        source_path = Path(str(source_path_raw))
        extracted = extract_summary(source_path)
        char_count = len(extracted)
        print(f"[{idx}/{total}] {slug}: {char_count} chars extracted")

        if not extracted:
            continue

        if not dry_run:
            updated = dict(feature)
            updated["summary"] = extracted
            writer.append(updated)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich thin feature summaries from source markdown files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print proposed summaries without writing.",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Only enrich features for this project.",
    )
    parser.add_argument(
        "--heuristic",
        action="store_true",
        help="Use extraction only (no LLM). This is the default behavior.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enrich even features with >100 char summaries.",
    )
    parser.add_argument(
        "--base-path",
        type=Path,
        default=_DEFAULT_BASE,
        help="Path to the interview-prep data directory.",
    )
    args = parser.parse_args()

    _enrich_features(
        base_path=args.base_path,
        project=args.project,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
