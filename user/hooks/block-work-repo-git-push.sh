#!/bin/bash
# Block git push in work repos unless explicitly approved via /push skill.
# Allows git commit (local checkpoints are fine).
# Bypass: command prefixed with CLAUDE_PUSH_APPROVED=1

command="$TOOL_INPUT_command"

# Only care about git push commands
if ! echo "$command" | grep -qiE '\bgit\s+push\b'; then
  exit 0
fi

# Allow if bypass token is present (set by /push skill)
if echo "$command" | grep -qE '^CLAUDE_PUSH_APPROVED=1\b'; then
  exit 0
fi

# Block in work repos (identified by work email via includeIf)
email=$(git config user.email 2>/dev/null)
if [[ "$email" == "jacob@cognitoforms.com" ]]; then
  echo "BLOCKED: git push is not allowed in work repos (detected work email: $email)." >&2
  echo "Use /push to squash-push when ready, or ask Jacob to push manually." >&2
  exit 2
fi

exit 0
