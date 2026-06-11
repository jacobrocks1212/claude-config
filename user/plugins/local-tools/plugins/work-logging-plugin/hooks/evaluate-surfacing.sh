#!/usr/bin/env bash
# PostToolUse hook for work_log_append
# Matcher pre-filters by tool name; this script extracts tool_input and spawns evaluation.

INPUT=$(cat)

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_DIR/.venv/Scripts/python.exe"
PYTHONW="$REPO_DIR/.venv/Scripts/pythonw.exe"

TEMP_FILE=$(mktemp /tmp/eval-XXXXXX.json)
echo "$INPUT" | "$PYTHON" -c "
import sys, json
data = json.load(sys.stdin)
json.dump(data.get('tool_input', {}), open(sys.argv[1], 'w'))
" "$TEMP_FILE" 2>/dev/null

CLAUDE_CONFIG_DIR="$HOME/.claude-personal" "$PYTHONW" "$REPO_DIR/scripts/evaluate_and_notify.py" "$TEMP_FILE" &

exit 0
