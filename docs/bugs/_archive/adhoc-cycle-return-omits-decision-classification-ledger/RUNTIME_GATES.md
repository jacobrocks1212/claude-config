# Runtime Gates — 1 MANUAL RUNTIME GATES PENDING (feature not verified end-to-end)

These runtime-verification rows are DEFERRED — their PHASES.md checkboxes stay `- [ ]` because they cannot run in this environment yet (closed later outside the pipeline; see each row's own closer). This repo declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so **this ledger is the ONLY owner of these rows** — no pipeline gate will hold them; the operator working the ledger is the sole remaining mechanism.

Written by the completion gate (`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when `__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the structural-skip route. Regenerated (not appended) on each completion.

| # | Owning phase | Deferred | Gate row (verbatim) |
|---|---|---|---|
| 1 | ### Phase 1: Add the ledger to the authoritative return contract (root fix) | 2026-07-19 | <!-- verification-only --> A dispatched decision-bearing cycle subagent (`/spec`, `/plan-feature`, `/spec-bug`, or `/plan-bug`) under `--batch`, following the assembled cycle prompt, includes the `### Decision-Classification Ledger` section in its return summary (or the empty-ledger line), so the Step 1d.5 input-audit runs the stronger diff-vs-ledger cross-check (algorithm step 3a/3b) instead of the diff-only fallback (step 3c). (Observable only across a live `/lazy-batch(-bug)` run; the deterministic proxy is the MVB grep above.) |
