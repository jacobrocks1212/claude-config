#!/usr/bin/env python3
"""Initialize ~/.interview-prep/ as a git repository."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    data_dir = Path.home() / ".interview-prep"
    data_dir.mkdir(parents=True, exist_ok=True)

    if (data_dir / ".git").exists():
        print(f"Already a git repo: {data_dir}")
        sys.exit(0)

    subprocess.run(["git", "init"], cwd=data_dir, check=True)

    gitignore = data_dir / ".gitignore"
    gitignore.write_text("vault/\n", encoding="utf-8")

    subprocess.run(["git", "add", ".gitignore"], cwd=data_dir, check=True)

    work_log = data_dir / "work-log.jsonl"
    if work_log.exists():
        subprocess.run(["git", "add", "work-log.jsonl"], cwd=data_dir, check=True)

    subprocess.run(
        ["git", "commit", "-m", "init: interview-prep data repository"],
        cwd=data_dir,
        check=True,
    )

    print(f"Initialized git repo at {data_dir}")


if __name__ == "__main__":
    main()
