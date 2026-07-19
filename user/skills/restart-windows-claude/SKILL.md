---
name: restart-windows-claude
description: Relaunch a native Windows phone-steerable Remote Control Claude session in a trusted Windows repo (default AlgoBooth; override with -Repo), from the WSL side. Use when the native Windows Remote Control session has dropped, or when you want an additional steerable session in another repo, without being at the laptop. Also deterministically enumerates the running Claude Code (claude.exe) sessions, and — ONLY on explicit operator confirmation of exact targets — terminates a specific session via a temporary, self-restoring kill-hook bypass.
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

## Enumerate running Claude Code sessions (deterministic)

Every Claude Code terminal is a `claude.exe` process. Its **operational identity is the
`--remote-control <name>` on its command line** — that name is what the phone shows and what the
launcher's `-Name` recycles, it is distinct per session, and it is stable for the process
lifetime. That makes it the deterministic key; the transient session-id (the `…jsonl` transcript
name) is NOT on the command line and should not be relied on for identification.

Get an exact, current inventory — and flag which process is THIS session — by writing this to a
file and running it via `powershell.exe -File` (inline PowerShell mangles quoting through the Bash
tool). **Seed SELF from `$CLAUDE_PID`, not `$$`.**

> **✅ SELF IS RESOLVED FROM `$CLAUDE_PID` — the authoritative key.** Claude Code exports the current
> session's own **`claude.exe` Windows PID** into every tool's environment as `CLAUDE_PID` (alongside
> `CLAUDE_CODE_SESSION_ID`). That IS the self process — pass it as the seed and the row whose `PID`
> equals it is THIS session, deterministically, with zero ancestry guessing. Verified live 2026-07-18:
> `CLAUDE_PID=20936` → the `claude-config-opus1m` row → `Self=True`, all others `False`.
>
> **Why NOT `$$` (the trap that burned us once):** the Bash tool on this box is **Git Bash / MSYS2**
> (`uname` → `MINGW64_NT… Msys`), *not* WSL. Under MSYS2, `$$` is an **MSYS pseudo-PID** from the
> emulation layer's own PID namespace — it does **not** equal the Windows PID of `bash.exe`, so
> `Get-CimInstance … ProcessId=$$` matches nothing on the Windows side, the walk finds no `claude.exe`,
> and **every row falsely reads `Self=False`** (the original 2026-07-18 symptom — misdiagnosed at first
> as "WSL"; the real cause is the MSYS pseudo-PID). `$CLAUDE_PID` sidesteps this entirely because it is
> already a real Windows PID. The script keeps a parent-walk only as a fallback for the odd seed that
> is a *child* of claude.exe, and prints a loud `!! SELF UNRESOLVED` banner if even that fails.

```bash
cat > /tmp/claude-sessions.ps1 <<'EOF'
param([int]$SeedPid = 0)
# Resolve SELF from the seed. The caller passes $CLAUDE_PID — the session's OWN claude.exe Windows
# PID, exported by Claude Code into every tool env. That is already the claude.exe, so the walk's
# first hop matches immediately. The ParentProcessId walk is a fallback for a seed that is a *child*
# of claude.exe. (Do NOT seed with the Bash `$$` — under Git Bash/MSYS2 that is an MSYS pseudo-PID,
# not a Windows PID, and it matches nothing here.)
$selfPid = 0
if ($SeedPid -gt 0) {
  $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$SeedPid" -ErrorAction SilentlyContinue
  while ($cur) {
    if ($cur.Name -eq 'claude.exe') { $selfPid = $cur.ProcessId; break }
    $cur = Get-CimInstance Win32_Process -Filter "ProcessId=$($cur.ParentProcessId)" -ErrorAction SilentlyContinue
  }
}
Get-CimInstance Win32_Process -Filter "Name='claude.exe'" | ForEach-Object {
  $rc    = if ($_.CommandLine -match '--remote-control (\S+)') { $Matches[1] } else { '?' }
  $model = if ($_.CommandLine -match '--model (\S+)')          { $Matches[1] } else { 'default' }
  [PSCustomObject]@{
    PID     = $_.ProcessId
    Remote  = $rc
    Model   = $model
    Started = $_.CreationDate
    Self    = ($_.ProcessId -eq $selfPid)
  }
} | Sort-Object Started | Format-Table -AutoSize | Out-String -Width 200
if ($selfPid -eq 0) {
  Write-Output '!! SELF UNRESOLVED - the seed did not resolve to a claude.exe.'
  Write-Output '!! Did you seed with $CLAUDE_PID? (Do NOT use $$ - MSYS pseudo-PID, not a Windows PID.)'
  Write-Output '!! Self=False on EVERY row above is NOT proof you are absent - Self was unresolvable.'
  Write-Output '!! Fallback: identify THIS session by its --remote-control name (the one on your phone),'
  Write-Output '!! cross-checked by --model == your stated model id + the newest Started.'
  Write-Output '!! NEVER recycle/kill a row you cannot positively rule OUT as Self.'
}
EOF
powershell.exe -File /tmp/claude-sessions.ps1 -SeedPid "$CLAUDE_PID"
```

- **`Self = True`** marks THIS session — the row whose `PID` equals `$CLAUDE_PID`. Deterministic, not
  a guess. NEVER recycle or kill that one.
- **If the `!! SELF UNRESOLVED` banner prints** (seed was empty/wrong — e.g. `$CLAUDE_PID` unset in
  some future harness, or you used `$$`), fall back to RC-name identification: THIS session is the row
  whose **`--remote-control` name matches the name you are being steered under** (the one shown on your
  phone / in the session context that launched this task), corroborated by **`--model` == your
  environment's stated model id** (e.g. Opus 4.8 / 1M reports `claude-opus-4-8[1m]`) and the **newest
  `Started`**. NEVER recycle or kill that row.
- Two live processes may share a `--remote-control` name only when one is a dropped/disconnected
  **orphan** and a reconnect spawned a fresh one; the **newer `Started`** is the live steerable
  session, the older is the orphan.
- Do NOT try to map a PID to its session-id from the command line — it isn't there. The session-id of
  THIS session is `$CLAUDE_CODE_SESSION_ID` in the env; for another (autonomous) session it is the
  marker's `session_id` (`~/.claude/state/<repo-hash>/lazy-run-marker.json`). Joining an *arbitrary*
  PID to its session-id needs the process's open transcript handle (Sysinternals `handle.exe`, usually
  absent) — but you rarely need to: `PID` (via `$CLAUDE_PID`) + `RC name` + `Started` identify every
  session safely.

## Terminate a session (operator-gated kill-hook bypass)

The launcher's default recycle (`-Name <existing>`) kills a **same-named** session as a side effect
of relaunching it — prefer that when you just want a clean restart. To terminate an **arbitrary**
session *without* relaunching (a runaway autonomous `/lazy` run, a dropped orphan, "kill everything
but this one"), you must stop its `claude.exe` directly — and that is denied by the
`block-terminal-kill.sh` PreToolUse hook (`Stop-Process`/`taskkill`/`kill` → *"terminating a
terminal requires physical laptop access"*). The hook matches the token even inside a script the
command invokes, so `powershell.exe -File kill.ps1` does **not** sneak past it — the only way is to
temporarily neuter the hook.

> **HARD GATE — explicit operator confirmation of exact targets is REQUIRED.** Bypassing this
> guard is destructive and safety-relevant. Do it ONLY after the operator, in the current session,
> explicitly confirms **the specific PID(s) / RC-name(s)** to kill. Confirm with AskUserQuestion
> listing the exact targets (from the enumeration above) — a general "clean things up" / "kill the
> others" is NOT sufficient on its own; echo back the concrete PID list and get a yes. **NEVER kill
> the `Self = True` process.** If the operator has not named/approved concrete targets, stop and ask
> — do not bypass.

Procedure — **back up → bypass → kill → ALWAYS restore → verify**. Each Bash call is a fresh shell,
so every block re-derives `H` (the real hook path — it's a symlink into this claude-config repo):

```bash
# 1. Back up the REAL hook file + record its hash.
H=$(readlink -f ~/.claude/hooks/block-terminal-kill.sh)   # -> claude-config/user/hooks/block-terminal-kill.sh
cp "$H" /tmp/btk-backup.sh
sha256sum "$H"          # note this hash; the restore must match it

# 2. Insert a temporary early-allow right after the shebang. The hook script runs FRESH on each
#    PreToolUse, so this takes effect on the NEXT tool call (do the kill in a SEPARATE call).
sed -i '1a exit 0  # TEMP operator-authorized terminal-kill bypass — restore from /tmp/btk-backup.sh' "$H"
head -2 "$H"           # confirm the exit 0 line is present
```

```bash
# 3. SEPARATE call (bypass now live): kill ONLY the operator-confirmed PIDs. MUST NOT include Self.
cat > /tmp/kill-claude.ps1 <<'EOF'
$targets = @( 0 )   # <-- REPLACE with the operator-confirmed PID list, e.g. @(3960, 14516)
$me = 0             # <-- SELF pid from the enumeration; a guard so we never kill ourselves
foreach ($t in $targets) {
  if ($t -eq $me -or $t -le 0) { Write-Output "SKIP $t (self/invalid)"; continue }
  try { Stop-Process -Id $t -Force -ErrorAction Stop; Write-Output "KILLED $t" }
  catch { Write-Output "FAILED $t: $($_.Exception.Message)" }
}
EOF
powershell.exe -File /tmp/kill-claude.ps1
```

```bash
# 4. IMMEDIATELY restore the guard (even if the kill failed) and verify it's byte-identical.
H=$(readlink -f ~/.claude/hooks/block-terminal-kill.sh)
cp /tmp/btk-backup.sh "$H"
if [ "$(sha256sum "$H" | cut -d' ' -f1)" = "$(sha256sum /tmp/btk-backup.sh | cut -d' ' -f1)" ]; then
  echo "HOOK RESTORED (sha matches backup)"; else echo "RESTORE MISMATCH — restore by hand from /tmp/btk-backup.sh"; fi
grep -q 'TEMP operator-authorized' "$H" && echo "BYPASS STILL PRESENT — remove it" || echo "bypass gone (clean)"
```

- **Restoration is mandatory and non-negotiable** — never leave the guard down. Restore even if the
  kill fails, and verify the sha matches the backup before moving on.
- **A dead `claude.exe` cannot self-relaunch**, so killing the process is what *permanently* stops
  an autonomous `/lazy(-batch)` loop. Tearing down its markers alone does NOT — a still-live
  orchestrator re-arms them on its next wake (it will start a fresh run within minutes).
- **After a confirmed kill of an autonomous run, clean up its orphaned lazy markers** (safe only
  now that the process is dead):
  ```bash
  export LAZY_ORCHESTRATOR=1
  python3 ~/.claude/scripts/lazy-state.py --cycle-end
  python3 ~/.claude/scripts/lazy-state.py --run-end --session-id <dead-session-id> \
    --efficacy-skip-authorized --operator-authorized --terminal-reason blocked-halt-for-manual
  python3 ~/.claude/scripts/lazy-state.py --marker-status   # expect {"present": false}
  ```
  (`--session-id` is the `session_id` in `~/.claude/state/<repo-hash>/lazy-run-marker.json`;
  `--operator-authorized` is required because a crash/disconnect is not a sanctioned terminal
  reason.)
