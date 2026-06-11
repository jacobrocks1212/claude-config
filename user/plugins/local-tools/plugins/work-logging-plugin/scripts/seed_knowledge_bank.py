"""Seed and validate the interview-prep knowledge bank."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

# Add parent to sys.path so we can import from servers/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servers.work_logging_mcp.knowledge_bank import Domain, KnowledgeBank  # noqa: E402


def validate_entries(path: Path) -> list[str]:
    """Load KnowledgeBank from *path* and return a list of error/warning strings.

    Returns an empty list when everything looks healthy.
    """
    errors: list[str] = []

    kb = KnowledgeBank(path)
    entries = kb.entries

    if not entries:
        errors.append("ERROR: No entries loaded — knowledge bank is empty.")
        return errors

    # Per-domain counts
    domain_counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        domain_counts[entry.domain.value] += 1

    for domain in Domain:
        count = domain_counts.get(domain.value, 0)
        if count == 0:
            errors.append(f"WARNING: Domain '{domain.value}' has no entries.")

    # Duplicate slug detection (slug alone, ignoring domain — cross-domain collisions are
    # confusing even though the KB permits them as distinct keys)
    slug_seen: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        slug_seen[entry.slug].append(entry.domain.value)

    for slug, domains in slug_seen.items():
        if len(domains) > 1:
            domain_list = ", ".join(sorted(domains))
            errors.append(f"WARNING: Slug '{slug}' appears in multiple domains: {domain_list}.")

    return errors


def parse_notion_export(path: Path) -> list[dict[str, object]]:
    """Parse a Notion export directory and return a list of raw entry dicts.

    Not yet implemented — returns an empty list.
    """
    print("Notion export parsing not yet implemented.")
    return []


def write_yaml_entries(entries: list[dict[str, object]], output_path: Path) -> int:
    """Write each entry dict as a YAML file at ``output_path/{domain}/{slug}.yaml``.

    Returns the number of files written.
    """
    written = 0
    for entry in entries:
        domain = str(entry.get("domain", "unknown"))
        slug = str(entry.get("slug", "unknown"))
        dest_dir = output_path / domain
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{slug}.yaml"
        dest_file.write_text(
            yaml.dump(entry, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed and validate the interview-prep knowledge bank.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate existing YAML entries in a knowledge-bank directory.",
    )
    validate_parser.add_argument(
        "path",
        type=Path,
        help="Path to the knowledge-bank root directory (contains domain subdirs).",
    )

    # seed-from-notion subcommand
    seed_parser = subparsers.add_parser(
        "seed-from-notion",
        help="Parse a Notion export and write YAML entry files.",
    )
    seed_parser.add_argument(
        "notion_path",
        type=Path,
        help="Path to the Notion export directory.",
    )
    seed_parser.add_argument(
        "output_path",
        type=Path,
        help="Destination knowledge-bank root directory for generated YAML files.",
    )

    args = parser.parse_args()

    if args.command == "validate":
        issues = validate_entries(args.path)
        if not issues:
            print("OK: All knowledge-bank entries are valid.")
        else:
            for issue in issues:
                print(issue)
            has_errors = any(i.startswith("ERROR") for i in issues)
            sys.exit(1 if has_errors else 0)

    elif args.command == "seed-from-notion":
        entries = parse_notion_export(args.notion_path)
        if not entries:
            print("No entries to write.")
            return
        count = write_yaml_entries(entries, args.output_path)
        print(f"Wrote {count} YAML file(s) to {args.output_path}.")


if __name__ == "__main__":
    main()
