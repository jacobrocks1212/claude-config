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

`build-queue.ps1 -Status` is an equivalent shortcut — it delegates to this same reader and returns immediately without enqueuing. Use it if you already have `build-queue.ps1` in hand; either form is read-only.

## Enqueue-and-return vs. blocking foreground

A foreground `build-queue.ps1 -Op <op>` call BLOCKS until the build/test COMPLETES, not merely until it enqueues — so run it with `timeout: 600000` (the build skills already specify this). To only enqueue and return immediately (e.g. you intend to do other work while it runs), invoke the same command with `run_in_background: true`, capture the `build-queue: enqueued as seq=N` line, and follow it to its authoritative result with `build-queue-await.ps1 -Seq <N>`. Never treat the `enqueued as seq=N` line as an outcome.

## Shell-crash recovery

This skill is the recovery entry point after a shell-level crash around a build-queue call (Git Bash `sh.exe` segfault / exit 139 / a `sh.exe.stackdump` in the repo root): the detached build usually ran to completion regardless of the shell's exit signal. Run the status reader first, then read the affected seq's `~/.claude/state/build-queue/logs/<seq>.log` / `<seq>.build.log` / `results/<seq>.json` for the real outcome — never re-run a build based on the shell crash alone.
