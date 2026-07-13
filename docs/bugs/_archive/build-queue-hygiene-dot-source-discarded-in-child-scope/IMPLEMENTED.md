---
kind: implemented
feature_id: build-queue-hygiene-dot-source-discarded-in-child-scope
date: 2026-07-06
provenance: pipeline-gated
derivation: message-grep
commits: []
decisions: []
---

# Implementation Ledger

**What shipped:** Both `build-queue.ps1` (`:47-49`) and `build-queue-runner.ps1` (`:66-68`) load their shared helpers with `Get-SafeValue { . (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1') }`. `Get-SafeValue` invokes its block via `& $Block`, which runs in a **child scope**; dot-sourcing inside that child scope defines every hygiene function into the child scope, which is then discarded. So `Format-BuildQueueBanner`, `New-BuildJobObject`, `Add-ProcessToBuildJob`, `Stop-BuildJobTree`, `Reset-CompilerServer`, `Get-BuildQueueOccupancy`, `Read-WithRetry`, `Test-BuildLogFailure`, `Stop-DllLockers` — **all of it** — are undefined in the actual script scope of both callers. In the runner, the first undefined-function call (`New-BuildJobObject`) throws `CommandNotFoundException` under `$ErrorActionPreference='Stop'` + `Set-StrictMode`; the `trap`/`continue` abandons the rest of the `try`, so `$proc.WaitForExit()` is **skipped** and the runner exits in ~2s with the real build orphaned and still compiling. In the wrapper, the same undefined `Format-BuildQueueBanner` throws inside the fault-swallowing `Get-SafeValue` at Step 5, so the banner is **silently never printed**. This one bug is the common cause of: "the banner didn't print", the premature/verdict-less `results/<seq>.json`, the wasted re-runs, the broken machine-global one-build-at-a-time invariant, and the complete silent no-op of all build hygiene (VBCSCompiler recycle, Job-Object descendant reap, poisoned-DLL quarantine, fidelity classification) in production.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: skip-mcp-test. Receipt: FIXED.md (provenance: gated).**
