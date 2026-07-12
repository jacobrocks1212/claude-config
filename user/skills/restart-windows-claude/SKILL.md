---
name: restart-windows-claude
description: Relaunch a native Windows phone-steerable Remote Control Claude session in a trusted Windows repo (default AlgoBooth; override with -Repo), from the WSL side. Use when the native Windows Remote Control session has dropped, or when you want an additional steerable session in another repo, without being at the laptop.
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
fresh, Remote-Control-enabled `claude` session in the target repo — by default
`C:\Users\Jacob\repos\AlgoBooth` (so the symlinked claude-config skills load),
overridable with `-Repo <path>` — recycling any prior session of the *same name*.
The working directory just has to be **pre-trusted** in the native config (see
Verify), so the session gets past startup and registers with the relay on its own.
AlgoBooth and `C:/Users/Jacob/source/repos/claude-config` are both already trusted.

The launcher also rebuilds `PATH` from the registry (so python/node/cargo resolve
in the fresh session) and injects two device-local User env vars —
`ALGOBOOTH_REAL_AUDIO_DEVICE` and `PYTHONUTF8`. These are AlgoBooth-oriented but
harmless in any repo; `PYTHONUTF8=1` is in fact useful for claude-config's Python
scripts (lazy-state.py etc. print Unicode arrows/em-dashes).

## Run it
Run exactly this from the Bash tool. It returns immediately; the new session takes
~10–15s to register with the relay. **Use forward slashes** in the path — a
backslash path gets mangled passing through the WSL→Windows interop layer.

```bash
powershell.exe -NoProfile -File C:/Users/Jacob/restart-windows-claude.ps1
```

Optional args (append after the path):
- `-Repo <path>` — the working directory / repo to open the session in (default
  `C:\Users\Jacob\repos\AlgoBooth`). The target MUST be trusted in `.claude.json`
  (see Verify) or the launch stalls at the trust dialog. Pass a distinct `-Name`
  alongside it so you don't recycle the default `algobooth` session.
- `-Name <name>` — RC session name (default `algobooth`). Determines both what
  appears on the phone and which prior session gets recycled.
- `-NoRecycle` — leave an existing same-named session running instead of killing it.
- `-Model <id>` — pin the session's model (injects `--model <id>`; empty = session
  default). See the SAFEGUARD below.

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

Example — spawn a session in the claude-config repo (already trusted) on Opus-1M,
without recycling the default `algobooth` session:

```bash
powershell.exe -NoProfile -File C:/Users/Jacob/restart-windows-claude.ps1 -Repo "C:/Users/Jacob/source/repos/claude-config" -Name claude-config -Model "claude-opus-4-8[1m]"
```

## Verify
The authoritative check is the user's phone: ~15s after running, a session named
after your **`-Name`** (default **`algobooth`**) should appear in the Claude app
and be steerable. Tell the user to look for that name.

If it does NOT appear, the launch stalled at startup — almost always because the
target repo lost (or never had) its trusted status. In `C:/Users/Jacob/.claude.json`,
under `projects`, the target repo needs an entry keyed by its **forward-slash** path
with `"hasTrustDialogAccepted": true` — e.g. `"C:/Users/Jacob/repos/AlgoBooth"` or
`"C:/Users/Jacob/source/repos/claude-config"` (both are present as of 2026-07-11).
Note the keys are stored with forward slashes even though `-Repo` accepts either
slash style (claude.exe normalizes). Re-add the entry if missing, then re-run.
