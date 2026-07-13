---
kind: fixed
feature_id: build-queue-nxbuild-false-no-output-fail
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: Pester (build-queue-hygiene.Tests.ps1, build-queue-runner.Tests.ps1, build-queue.Tests.ps1, build-queue-await.Tests.ps1) -- NOT pipeline-gated
auto_ticked_rows: 0
---

# Completion Receipt

build-queue-nxbuild-false-no-output-fail marked fixed on 2026-07-12 by an operator-directed
interactive bug-fix subagent session (BUILD-QUEUE lane). This receipt was written directly by the
subagent, not the pipeline's `__mark_fixed__` gate -- provenance is deliberately
`operator-directed-interactive`, mirroring `docs/bugs/_archive/worktree-claude-doc-drift/FIXED.md`.

## Notes

Both SPEC Fix Scope deliverables landed together in Phase 1 of `PHASES.md`:

1. **Widened the classify-time retry window.** `build-queue-runner.ps1`'s no-output classify
   `Read-WithRetry` call (the one feeding `Test-BuildProducedNoOutput` at the build-log check)
   now passes `-MaxAttempts 10 -DelayMs 100` (~1s ceiling) instead of the library default 3x/50ms
   (~100ms ceiling) that was too tight for an npx/node/rspack process tree. Scoped to that ONE
   call site -- the test-counts parse and the `active.lock` re-read in the same file are
   unchanged.
2. **Made the no-output banner remedy op-aware.** `build-queue-hygiene.ps1`'s
   `Format-BuildQueueBanner` now keys the no-output remedy text off `$Op` (`^nx` -> nx-appropriate
   remedy; everything else, including `msbuild` and any unrecognized op, keeps the original
   dotnet-oriented "delete obj/bin and rebuild" text -- a safe, non-worsening default).

**TDD:** the retry-window fix has a genuine RED-for-the-right-reason Pester case (a 150ms-delayed
build log misclassifies no-output under the OLD 100ms budget) that goes GREEN under the widened
budget, using the real `Read-WithRetry`/`Test-BuildProducedNoOutput` functions against a
controlled background-thread file write -- the SPEC's own fixture repro found the real
`Start-Process` OS-level race unreproducible on this machine even with a real node child, so this
is the correct and honest level to prove the fix's arithmetic at, not a shortcut.

**Gate (exact counts):**
- `build-queue-hygiene.Tests.ps1`: **178/178** (was 175/175; +3 op-aware-remedy cases)
- `build-queue-runner.Tests.ps1`: **9/9** (was 4/4; +5 retry-window cases)
- `build-queue.Tests.ps1`: **2/2** (unchanged -- regression check)
- `build-queue-await.Tests.ps1`: **8/8** (unchanged -- regression check)
- Total: **197/197**, 0 failures.

**Deferred to work laptop:** the SPEC's own still-open instrumented confirmation (logging the
real `.build.log` byte-length across `Read-WithRetry` attempts during an actual `/nxbuild` against
a live Cognito worktree, to catch the real `0 -> 732`-byte transition and identify which extra
process hop -- npx shim, Nx daemon, or per-task worker fan-out -- causes the lag, and to confirm
the ~1s ceiling holds under load) requires a Cognito worktree + installed `nx`/`npx` toolchain,
both absent on this machine. Ship-safe un-instrumented per the SPEC's own closing argument: a
bounded retry widening can only help, never regress a genuinely-broken build.

**No provisional fork.** The SPEC's Fix Scope recommendation (a) was adopted verbatim (widen the
call-site-local retry parameters for all build ops, no per-op manifest knob needed yet) and the
remedy op-keying was a direct, low-risk implementation of Fix Scope item 2 -- no genuine design
fork arose that required operator input.
