#!/bin/bash
# Block commands that could kill terminal processes during mobile workflow.
# 4 terminals run 24/7 — accidental termination requires physical laptop access.

command="$TOOL_INPUT_command"

# Block process termination (but allow npx kill-port for /mcp-test)
if echo "$command" | grep -qiE '\b(taskkill|Stop-Process)\b'; then
  echo "BLOCKED: Process termination not allowed during mobile workflow." >&2
  exit 2
fi
if echo "$command" | grep -qiE '\bkill\b' && ! echo "$command" | grep -qi 'kill-port'; then
  echo "BLOCKED: kill commands not allowed. Use npx kill-port for port cleanup." >&2
  exit 2
fi

# Block session/system termination
if echo "$command" | grep -qiE '\b(exit|logout|Stop-Computer|Restart-Computer|shutdown)\b'; then
  echo "BLOCKED: Session/system termination not allowed during mobile workflow." >&2
  exit 2
fi

# Block Windows Terminal management
if echo "$command" | grep -qiE '\bwt\.exe\b'; then
  echo "BLOCKED: Windows Terminal management (wt.exe) not allowed during mobile workflow." >&2
  exit 2
fi

exit 0
