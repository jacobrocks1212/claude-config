"""Study wrapper — launches Claude with surfacing context for the triggered topic."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    os.environ["CLAUDE_CONFIG_DIR"] = str(Path.home() / ".claude-personal")

    slug = sys.argv[1] if len(sys.argv) > 1 else ""
    if not slug:
        os.execvp("claude", ["claude", "--dangerously-skip-permissions", "--model", "claude-opus-4-6"])

    context = _load_surfacing_context(slug)
    prompt = f"{context}/interview-study {slug}" if context else f"/interview-study {slug}"

    os.execvp(
        "claude",
        ["claude", "--dangerously-skip-permissions", "--model", "claude-opus-4-6", prompt],
    )


def _load_surfacing_context(slug: str) -> str:
    log_path = Path.home() / ".interview-prep" / "surfacing-log.jsonl"
    if not log_path.exists():
        return ""
    try:
        entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        matches = [e for e in entries if e.get("topic_slug") == slug and e.get("surfaced")]
        if not matches:
            return ""
        e = matches[-1]
        title = e.get("work_title", "")
        project = e.get("work_project", "")
        summary = e.get("summary", "")
        parts = [f'Your recent work "{title}"']
        if project:
            parts[0] += f" ({project})"
        parts[0] += f' surfaced the topic "{slug}".'
        if summary:
            parts.append(f"Why it matched: {summary}")
        parts.append("Ground the study session in this specific work.\n\n")
        return "\n".join(parts)
    except Exception:
        return ""


if __name__ == "__main__":
    main()
