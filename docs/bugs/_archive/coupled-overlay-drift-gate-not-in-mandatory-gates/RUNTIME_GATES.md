# Runtime Gates — 2 MANUAL RUNTIME GATES PENDING (feature not verified end-to-end)

These runtime-verification rows are DEFERRED — their PHASES.md checkboxes stay `- [ ]` because they cannot run in this environment yet (closed later outside the pipeline; see each row's own closer). This repo declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so **this ledger is the ONLY owner of these rows** — no pipeline gate will hold them; the operator working the ledger is the sole remaining mechanism.

Written by the completion gate (`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when `__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the structural-skip route. Regenerated (not appended) on each completion.

| # | Owning phase | Deferred | Gate row (verbatim) |
|---|---|---|---|
| 1 | ### Phase 1: Register the coupled-overlay drift gate in the mandatory battery (+ prose + count + recurrence guard) | 2026-07-19 | <!-- verification-only --> After adding the gate row, running the full battery reports `cmds=8` and `RESULT=PASS` on the clean committed tree (baseline stays green — the gate catches future drift, not the current tree). |
| 2 | ### Phase 1: Register the coupled-overlay drift gate in the mandatory battery (+ prose + count + recurrence guard) | 2026-07-19 | <!-- verification-only --> Drift is now caught by the mandatory battery: deliberately mutate a canonical coupled SKILL.md WITHOUT re-extracting its overlay (or otherwise induce overlay drift), run the battery, and confirm it now FAILS naming the `coupled-overlay-drift` gate — then revert the deliberate mutation. This is the SPEC's reproduction step 3-5, now expected to fail-fast instead of passing green. |
