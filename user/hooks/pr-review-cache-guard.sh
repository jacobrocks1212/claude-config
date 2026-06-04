#!/bin/bash
# pr-review-cache-guard.sh
# Warns about Read operations outside the PR cache directory during reviews
# This is a WARNING hook, not a blocker - the consistency checker legitimately
# needs to read baseline files from the repo. Stage 3.6 filtering handles
# removing any findings for files not in the PR.

# Read hook input from stdin
input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name')

# Only intercept Read tool
if [ "$tool_name" != "Read" ]; then
    exit 0
fi

# Check for marker file (created by review-pr.md orchestrator)
# Located in project's .claude/pr-cache/ to avoid triggering "modify settings" prompts
marker_file=".claude/pr-cache/pr-review-active.json"
if [ ! -f "$marker_file" ]; then
    # Not in PR review mode - allow all reads
    exit 0
fi

file_path=$(echo "$input" | jq -r '.tool_input.file_path')

# Always allow reads within .claude/pr-cache/ or .claude.local/reviews/
if [[ "$file_path" == *"/.claude/pr-cache/"* ]] || [[ "$file_path" == *"/.claude.local/reviews/"* ]]; then
    exit 0
fi

# Always allow reading plugin files (agent instructions, rules, etc.)
if [[ "$file_path" == *"/.claude/plugins/"* ]]; then
    exit 0
fi

# Always allow reading cog-docs (review artifacts and work-item docs live there)
if [[ "$file_path" == *"/cog-docs/"* ]]; then
    exit 0
fi

# Always allow reading knowledge files
if [[ "$file_path" == *"/knowledge/"* ]]; then
    exit 0
fi

# Always allow reading CLAUDE.md files
if [[ "$file_path" == *"CLAUDE.md"* ]] || [[ "$file_path" == *"CLAUDE.local.md"* ]]; then
    exit 0
fi

# Always allow reading memory files
if [[ "$file_path" == *"/.claude/projects/"* ]] || [[ "$file_path" == *"/memory/"* ]]; then
    exit 0
fi

# Log warning for reads outside cache (but don't block - consistency checker needs this)
# The warning helps with debugging cross-branch contamination issues
# Stage 3.6 filtering will remove any findings for files not in the manifest
>&2 echo "[pr-review-cache-guard] Warning: Reading file outside PR cache: $file_path"

# Exit 0 to allow the read (no JSON output = allow)
exit 0
