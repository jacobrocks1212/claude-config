---
kind: blocked
feature_id: build-queue-copy-lock-stale-dll-false-success
phase: "Step 10 mark-fixed — Phase 1/2/3 verification-only rows require Windows-runtime observation"
blocked_at: 2026-07-06T05:15:00Z
retry_count: 0
blocker_kind: requires-host
recovery_suggestion: "Re-run /lazy-bug on a Windows host with a PowerShell build runtime + a real Cognito worktree to satisfy the three manual runtime spikes, tick their PHASES.md verification-only rows with the recorded evidence, then re-run __mark_fixed__."
---

## Details

All four plan parts (`plans/all-phases-copy-lock-part-1..3.md`) are `status: Complete`
and every code-authorable PHASES.md deliverable is `[x]`. The fix landed out-of-band
via the sibling `build-queue-false-green-on-silent-build-failure` work (commits
`08c67f9`, `1880012`, and others) and its Pester suites were recorded green on Windows
(32/3 hygiene, 10/10 test-filtered). The structural MCP-skip is granted
(`SKIP_MCP_TEST.md` + `VALIDATED.md` present — claude-config has no Tauri/npm app surface).

The `__mark_fixed__` completion gate refuses because three `<!-- verification-only -->`
rows (Phases 1–3) remain unchecked, and the 2026-07-06 coherence-recovery cycle
(`9cb111e`) correctly declined to blind-tick them: they are **manual Windows-runtime
spike observations**, not covered by the structural-skip waiver, with NO on-disk
evidence artifact on this host:

1. **Phase 1 (line ~44)** — locked-DLL build exit-code repro: observe a build whose
   output DLL is held by a live locker and confirm the runner reports failure (not a
   stale-DLL false pass).
2. **Phase 2 (line ~86)** — DLL-locker-reap runtime spike: run a build with a
   pre-held DLL locker, capture the reaped locker's PID + timestamps from
   `lockers_reaped`.
3. **Phase 3 (line ~122)** — live `/mstest` transcript: run a real `/mstest`, capture
   unfiltered `dotnet test` output, confirm the modern `Passed!/Failed!` summary regex
   matches real output (not a fabricated fixture).

**Missing host capability:** a **Windows PowerShell build runtime** (`pwsh` /
`powershell.exe` + `dotnet`) and a **real Cognito worktree**. This repo runs in a
Linux cloud container (`command -v pwsh powershell dotnet` → empty), so the three
spikes cannot be observed here. Implementation is complete; only host-gated runtime
verification remains.

## Resolution

*Recorded on 2026-07-06 05:15:00 UTC.*

**Chosen path:** Defer this bug; continue the rest of the queue
**Notes:** Sequencing-only host-capability gap (completeness-policy §3, `resolved_by: completeness-policy`). Implementation landed + Pester-green on Windows; only the three manual Windows runtime spikes remain, which require a Windows host. Deferred to the queue tail — re-opens on a capability-bearing host.
