#!/bin/bash
# Block git commit/push in work repos (identified by work email in git config).
# Claude should only make code changes in work repos — Jacob handles git operations.

command="$TOOL_INPUT_command"

# Check if command contains git commit or git push
if ! echo "$command" | grep -qiE '\bgit\s+(commit|push)\b'; then
  exit 0
fi

# Check if we're in a work repo (identified by work email via includeIf)
email=$(git config user.email 2>/dev/null)
if [[ "$email" == "jacob@cognitoforms.com" ]]; then
  echo "BLOCKED: git commit/push is not allowed in work repos (detected work email: $email)." >&2
  echo "Make code changes only — Jacob handles commits and pushes for work repos." >&2
  exit 2
fi

exit 0
