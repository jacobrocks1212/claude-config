# Runtime Gates — 9 MANUAL RUNTIME GATES PENDING (feature not verified end-to-end)

These runtime-verification rows are DEFERRED — their PHASES.md checkboxes stay `- [ ]` because they cannot run in this environment yet (closed later outside the pipeline; see each row's own closer). This repo declares `MCP runtime: not-required` (no `/mcp-test` step downstream), so **this ledger is the ONLY owner of these rows** — no pipeline gate will hold them; the operator working the ledger is the sole remaining mechanism.

Written by the completion gate (`completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`) when `__mark_complete__`/`__mark_fixed__` exempted these deferred rows on the structural-skip route. Regenerated (not appended) on each completion.

| # | Owning phase | Deferred | Gate row (verbatim) |
|---|---|---|---|
| 1 | ### Phase 1: `--tool-search` CLI + corpus aggregation | 2026-07-19 | <!-- verification-only --> `python -m pytest user/scripts/test_tool_search.py -q` passes: hit-ranking, MISS-verdict, `--json` shape, telemetry breadcrumb, and `--dump-cli-surface` conformance assertions all green. |
| 2 | ### Phase 1: `--tool-search` CLI + corpus aggregation | 2026-07-19 | <!-- verification-only --> `python3 user/scripts/cli_surface_gen.py --check --repo-root .` passes after `tool-search.py` is registered on the ROSTER and the registry is regenerated (freshness gate). |
| 3 | ### Phase 2: Miss protocol glue (dedup + correctness-gated recommendation) | 2026-07-19 | <!-- verification-only --> `python -m pytest user/scripts/test_tool_search.py -q` (extended in this phase) passes all Phase-2 dedup/host-capability/classification fixtures. |
| 4 | ### Phase 3: Prose wiring (coupled-pair) | 2026-07-19 | <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0. |
| 5 | ### Phase 3: Prose wiring (coupled-pair) | 2026-07-19 | <!-- verification-only --> `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` exits 0. |
| 6 | ### Phase 3: Prose wiring (coupled-pair) | 2026-07-19 | <!-- verification-only --> `python3 user/scripts/skill-size-ratchet.py --check --repo-root .` exits 0 (or ceilings are deliberately re-locked via `--lock-in`, never silently exceeded). |
| 7 | ### Phase 3: Prose wiring (coupled-pair) | 2026-07-19 | <!-- verification-only --> `python user/scripts/project-skills.py` re-expands cleanly (no circular-include/missing-component errors) and `python user/scripts/lint-skills.py --check-projected --check-capabilities` passes. |
| 8 | ### Phase 4: KPI selector registration (code-complete now; baseline value deferred) | 2026-07-19 | <!-- verification-only --> `python3 user/scripts/kpi-scorecard.py --lint` exits 0. |
| 9 | ### Phase 4: KPI selector registration (code-complete now; baseline value deferred) | 2026-07-19 | <!-- verification-only --> New unit tests for the selector's computation function pass (synthetic-fixture ratio + NO-DATA path). |
