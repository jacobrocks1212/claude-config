# Implementation Phases — build-queue-runner.Tests.ps1 has two top-level BeforeAll blocks — Pester 6 refuses discovery

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure PowerShell test-file fix, verified by running the suite
itself (`Invoke-Pester`). No `mcp-tool-catalog.md` in this repo; the planning-time MCP
tool-existence audit no-ops.

## Validated Assumptions

- **The two top-level `BeforeAll` blocks define disjoint helper sets** (confirmed in SPEC.md
  Evidence — block #1 lines 33–124, block #2 lines 126–291; the only overlap is three
  idempotent duplicate statements). A single merged `BeforeAll` preserving both bodies is
  behavior-identical under both Pester 5 and Pester 6.

## Cross-feature Integration Notes

No `**Depends on:**` block. Surfaced by `generalized-build-test-runner-skills` Phase 4 (which
could not touch the file — byte-untouched L6 guard). Self-contained test-file fix.

---

### Phase 1: Merge the two top-level `BeforeAll` blocks into one

**Scope:** Merge block #2's unique variables + helper definitions into block #1, dropping
block #2's three duplicate idempotent statements (`$script:RunnerPath`/`$script:HygienePath`
re-assignments + the second `. $script:HygienePath`). No `Describe`/`It`/`AfterEach`/test-body
changes. Pester 6 requires one `BeforeAll` per block; one is legal under Pester 5 too.

**TDD:** verification-by-runner — the suite's own discovery+run IS the test (it was 0-discovered
before the fix, green after).

**Status:** Fixed

**Deliverables:**
- [x] `user/scripts/build-queue-runner.Tests.ps1` — single top-level `BeforeAll` (was two at
      lines 33 and 126). Confirmed: `grep -nE "^BeforeAll"` reports exactly one match (line 33).
- [x] All helper definitions from both former blocks preserved (block #1's `Get-SafeValue`
      et al. + block #2's `New-RunnerSandbox` / `Get-ResultJson` / `Invoke-Await` et al.); the
      three duplicate statements dropped.

**Minimum Verifiable Behavior:**
`powershell.exe -NoProfile -Command "Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1"`
DISCOVERS and RUNS the suite (was: discovery-aborted with "BeforeAll is already defined in this
block", 0 tests run).

**MCP Integration Test Assertions:** N/A — PowerShell test-file fix, no MCP-observable surface.

**Prerequisites:** None (only phase).

**Files likely modified:**
- `user/scripts/build-queue-runner.Tests.ps1`

**Testing Strategy:** Run the merged suite under the machine's installed Pester 6.0.0.

**Runtime Verification** *(checked by running the suite — the suite's own execution IS the runtime)*:
- [x] <!-- verification-only --> The suite discovers and runs green under Pester 6.
  **Verified 2026-07-14:** `Invoke-Pester -Path user/scripts/build-queue-runner.Tests.ps1
  -Output Minimal` → **Tests Passed: 17, Failed: 0** in 25.28s (was 0 discovered / container
  failed at discovery pre-fix).

**Integration Notes for Next Phase:** None — only phase. Fixed out-of-pipeline by `harden-harness`
(commit resolving this bug); receipt written via the gated `__mark_fixed__` chain.

---

## Review Notes

_(Fix landed out-of-pipeline via harden-harness; receipt-gated through the structural no-MCP skip.)_
