#!/usr/bin/env python3
"""One-shot migration: ~/.claude/work-log.jsonl -> ~/.interview-prep/work-log.jsonl"""

import json
import sys
from pathlib import Path


def main() -> None:
    src = Path.home() / ".claude" / "work-log.jsonl"
    dst = Path.home() / ".interview-prep" / "work-log.jsonl"

    if not src.exists():
        print(f"Source not found: {src}")
        sys.exit(1)

    if dst.exists():
        print(f"Destination already exists: {dst} — aborting to prevent duplicates")
        sys.exit(1)

    dst.parent.mkdir(parents=True, exist_ok=True)

    lines = [line for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    with dst.open("w", encoding="utf-8") as f:
        for line in lines:
            json.loads(line)  # validate JSON
            f.write(line + "\n")

    print(f"Migrated {len(lines)} entries from {src} to {dst}")

    dst_lines = [line for line in dst.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(dst_lines) != len(lines):
        print(f"Count mismatch: {len(dst_lines)} != {len(lines)}")
        sys.exit(1)
    print("Verification passed.")


if __name__ == "__main__":
    main()
