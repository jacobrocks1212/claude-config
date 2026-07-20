# Runtime Gates — 2 MANUAL RUNTIME GATES PENDING (feature not verified end-to-end)

These runtime-verification rows are DEFERRED — their PHASES.md checkboxes stay `- [ ]` because they cannot run in this environment yet (closed later outside the pipeline; see each row's own closer). This repo declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so **this ledger is the ONLY owner of these rows** — no pipeline gate will hold them; the operator working the ledger is the sole remaining mechanism.

Written by the completion gate (`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when `__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the structural-skip route. Regenerated (not appended) on each completion.

| # | Owning phase | Deferred | Gate row (verbatim) |
|---|---|---|---|
| 1 | ### Phase 3: Wire the re-route into both state scripts (coupled pair) + regression fixtures | 2026-07-19 | <!-- verification-only --> The full `--test` harness is GREEN on both scripts (`python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test`), and `pytest user/scripts/tests/test_lazy_core/` passes. |
| 2 | ### Phase 3: Wire the re-route into both state scripts (coupled pair) + regression fixtures | 2026-07-19 | <!-- verification-only --> The parity audit is exit 0: `python3 user/scripts/lazy_parity_audit.py --repo-root .` (the coupled-pair mirror is registered/clean). |
