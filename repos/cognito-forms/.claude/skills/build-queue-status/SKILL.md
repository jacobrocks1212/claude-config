---
name: build-queue-status
description: Show the Cognito build-queue status — the active build (op, worktree, PID, elapsed, log), ordered waiters, and a live machine-load summary. Read-only; safe anytime.
model: haiku
allowed-tools: ["Bash"]
---

# Build Queue Status

Show what is running in the machine-global Cognito build queue right now: the active build, any waiting builds, and a fresh machine-load line. Read-only; nothing is mutated.

## Instructions

Run the status reader via Bash and relay the output verbatim — do not reformat or summarize it:

```
powershell.exe -ExecutionPolicy Bypass -File "$HOME/.claude/scripts/build-queue-status.ps1"
```

Relay the complete stdout to the user without modification.
