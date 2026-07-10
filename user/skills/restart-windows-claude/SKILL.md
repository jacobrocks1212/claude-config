---
name: restart-windows-claude
description: Relaunch the native Windows phone-steerable Remote Control Claude session in the AlgoBooth repo, from the WSL side. Use when the native Windows Remote Control session has dropped and you want it back without being at the laptop.
---

# Restart the native Windows Remote Control session

Use this when the **native Windows** Claude Code session — the one steered from the
phone via Remote Control — has dropped, and you want to resurrect it from the
reliable WSL side.

This works because WSL runs inside the Windows interactive logon session, so a
process it launches via interop lands in that same session, which is where Remote
Control actually connects. (A direct SSH-into-Windows launch would land in a
*non-interactive* session and silently stall at startup — that's why we go
through WSL.)

## What it does
Calls the Windows-side launcher via WSL→Windows interop. That script starts a
fresh, Remote-Control-enabled `claude` session in `C:/Users/Jacob/repos/AlgoBooth`
(so the symlinked claude-config skills load), recycling any prior session of the
same name. The AlgoBooth folder is pre-trusted in the native config, so the
session gets past startup and registers with the relay on its own.

## Run it
Run exactly this from the Bash tool. It returns immediately; the new session takes
~10–15s to register with the relay. **Use forward slashes** in the path — a
backslash path gets mangled passing through the WSL→Windows interop layer.

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/Jacob/restart-windows-claude.ps1
```

Optional args (append after the path): `-Name <name>` for a different RC session
name (default `algobooth`); `-NoRecycle` to leave an existing same-named session
running instead of recycling it; `-Model <id>` to pin the session's model (injects
`--model <id>`; empty = session default).

> **SAFEGUARD — confirm the exact model code before dispatching with `-Model`.**
> Model IDs drift between releases and the 1M-context variant carries a bracket
> suffix. NEVER guess or reuse a remembered id. Read the current environment's
> stated exact model ID (e.g. the harness reports Opus 4.8 / 1M as
> `claude-opus-4-8[1m]`) and confirm it with the user (AskUserQuestion) before
> launching. Passing a stale or wrong id silently launches the session on the
> wrong model.

> **Spawning vs. restarting:** the default `-Name algobooth` *recycles* (kills)
> any existing same-named RC session — including possibly the one issuing this
> command. To spawn an *additional* session, pass a distinct `-Name`
> (e.g. `-Name algobooth-opus1m`) so nothing is recycled.

Example — spawn an additional Opus-1M session alongside the default one:

```bash
powershell.exe -NoProfile -File C:/Users/Jacob/restart-windows-claude.ps1 -Name algobooth-opus1m -Model "claude-opus-4-8[1m]"
```

## Verify
The authoritative check is the user's phone: ~15s after running, a session named
**`algobooth`** should appear in the Claude app and be steerable. Tell the user to
look for it.

If it does NOT appear, the launch stalled at startup — almost always because the
AlgoBooth folder lost its trusted status. Check that `C:/Users/Jacob/.claude.json`
still has, under `projects`, an entry `"C:/Users/Jacob/repos/AlgoBooth"` with
`"hasTrustDialogAccepted": true`. Re-add it if missing, then re-run.
