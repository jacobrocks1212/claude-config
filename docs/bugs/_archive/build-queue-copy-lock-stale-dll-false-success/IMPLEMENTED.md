---
kind: implemented
feature_id: build-queue-copy-lock-stale-dll-false-success
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [dcd1a42, 1854f18, 9cb111e, cadec66, 40e937a, cc4026f, 02926a8]
decisions: []
---

# Implementation Ledger

**What shipped:** An MSB3027 copy-lock failure (obj/ rebuilt fresh, copy to bin/Debug blocked by a leftover locker) makes MSBuild log "Build FAILED" while still exiting 0. The build queue trusts the exit code, records `exit_code: 0`, skips every staleness guard, and `/mstest --no-build` then runs the stale `bin/Debug` DLL — costing agents huge investigation loops. The same "signal can't be trusted" theme has a **test-side twin**: `test-filtered.ps1`'s stale summary regex fails to parse modern `dotnet test` output, so a *passing* run can't be certified green either. Both ends of "did this actually pass?" fail open.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
