# Runtime Gates — 1 MANUAL RUNTIME GATES PENDING (feature not verified end-to-end)

These runtime-verification rows are DEFERRED — their PHASES.md checkboxes stay `- [ ]` because they cannot run in this environment yet (closed later outside the pipeline; see each row's own closer). This repo declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so **this ledger is the ONLY owner of these rows** — no pipeline gate will hold them; the operator working the ledger is the sole remaining mechanism.

Written by the completion gate (`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when `__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the structural-skip route. Regenerated (not appended) on each completion.

| # | Owning phase | Deferred | Gate row (verbatim) |
|---|---|---|---|
| 1 | ### Phase 1: Exempt `--record-intervention` for a dispatched hardening-class cycle subagent | 2026-07-18 | <!-- verification-only --> The exit-3 → exit-0 behavior change on the `--record-intervention` false-refusal subset is proven by the serving-path regression test `test_record_intervention_permitted_for_hardening_cycle_subagent` (cases a/b/c) passing, AND the guarded-lifecycle ops (`--run-end` etc.) still refuse under a hardening marker (case b). SEAM-B symptom-reproduction: the original symptom (containment refuses the mandated capture op) is gone at its reported surface while no genuinely-dangerous op was un-gated. |
