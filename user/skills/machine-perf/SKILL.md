---
name: machine-perf
description: Report this Windows machine's live performance — uptime, CPU load, memory, disk, and the top resource-consuming processes. Use when the user asks "how is my machine doing", "what's my uptime", "check performance", "is something hogging CPU/memory", or for a general health snapshot.
argument-hint: "[--json] [--top N]"
model: haiku
plan-mode: never
allowed-tools: [Bash, PowerShell, Read]
---

# Machine Performance Report

Run a read-only diagnostics script and report this machine's current performance, including uptime. The script (`~/.claude/scripts/machine-perf.ps1`) does all collection; this skill runs it and relays the result in a clean summary. It mutates nothing — safe to run anytime.

## Steps

1. **Run the script** via the PowerShell tool:
   ```
   & "C:\Users\Jacob\.claude\scripts\machine-perf.ps1"
   ```
   - Default sampling averages CPU load over a 2-second window. For an instantaneous read, append `-SampleSeconds 0`.
   - To change how many top processes are listed, append `-TopN <n>` (default 5).
   - If the user passed `--json`, append `-Json` and relay the structured object instead of prose.
   - If the user passed `--top N`, translate it to `-TopN N`.

2. **Report back** with a brief summary in the constitution's format — a one-line health verdict, then a short bulleted list. Lead with **uptime** (the user specifically asked for it), then CPU load, memory used/free, disk free, and call out any process that stands out (e.g. a process pinning CPU or consuming a large share of memory).

3. **Flag anything notable** — disk over ~90% used, memory over ~90% used, or sustained high CPU load deserve an explicit callout rather than burying it in the list.

## Notes

- The script is pure PowerShell with no external dependencies and works on Windows PowerShell 5.1.
- "CPU time" in the top-processes table is cumulative CPU-seconds since each process started (so long-lived system processes like `MsMpEng`/`System` naturally top it) — not instantaneous load. The single **Load %** line under CPU is the live utilization figure.
- If the script errors, fall back to reading individual values via `Get-CimInstance Win32_OperatingSystem` (uptime/memory) and `Get-CimInstance Win32_Processor` (CPU), but prefer fixing the script.
