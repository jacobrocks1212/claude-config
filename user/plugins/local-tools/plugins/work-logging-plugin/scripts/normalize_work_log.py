#!/usr/bin/env python3
"""Normalize work-log.jsonl field names: date→timestamp, repo→project."""

import json
import sys
from pathlib import Path


def main() -> None:
    log_file = Path.home() / ".interview-prep" / "work-log.jsonl"

    if not log_file.exists():
        print(f"Work log not found: {log_file}")
        sys.exit(1)

    records: list[dict[str, object]] = []
    date_renames = 0
    repo_renames = 0

    for line in log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record: dict[str, object] = json.loads(line)

        if "date" in record and "timestamp" not in record:
            record["timestamp"] = record.pop("date")
            date_renames += 1

        if "repo" in record and "project" not in record:
            record["project"] = record.pop("repo")
            repo_renames += 1

        records.append(record)

    with log_file.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record) + "\n")

    print(f"Processed {len(records)} records")
    print(f"  date → timestamp: {date_renames}")
    print(f"  repo → project:   {repo_renames}")


if __name__ == "__main__":
    main()
