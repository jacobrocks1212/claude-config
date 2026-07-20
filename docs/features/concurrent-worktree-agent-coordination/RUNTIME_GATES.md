# Runtime Gates — 2 MANUAL RUNTIME GATES PENDING (feature not verified end-to-end)

These runtime-verification rows are DEFERRED — their PHASES.md checkboxes stay `- [ ]` because they cannot run in this environment yet (closed later outside the pipeline; see each row's own closer). This repo declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so **this ledger is the ONLY owner of these rows** — no pipeline gate will hold them; the operator working the ledger is the sole remaining mechanism.

Written by the completion gate (`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when `__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the structural-skip route. Regenerated (not appended) on each completion.

| # | Owning phase | Deferred | Gate row (verbatim) |
|---|---|---|---|
| 1 | ### Phase 3: Cross-platform FIFO file-lock (per-queue-item grain, two conforming implementations) | 2026-07-19 | <!-- verification-only --> Two real concurrent processes acquiring the SAME per-item lock proceed in FIFO order (second blocks until first releases), observed on the workstation via the PowerShell plane. (Cross-platform two-implementation parity — workstation-eligible.) |
| 2 | ### Phase 5: Temp-worktree merge-back + cross-agent commit-message-trailer channel | 2026-07-19 | <!-- verification-only --> A real large non-semantic conflict on the workstation: the temp worktree is created, work merges back, the run CONTINUES (no halt), and the conflicting agent's next fetch/rebase surfaces the `Concurrent-Merge-Back:` trailer. (Workstation-eligible integration observation.) |
