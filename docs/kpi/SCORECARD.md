# Friction KPI Scorecard

> Pure-read render of `docs/kpi/registry.json` by `user/scripts/kpi-scorecard.py` — script-computed values only, no embedded wall-clock (freshness is this file's git commit time). An absent/unrecordable signal renders NO-DATA, never a fabricated zero; a `pending` baseline renders PENDING-BASELINE; a signal unobservable from this repo/host renders WRONG-VANTAGE.

## build-queue

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| False-green build rate `[cognito-forms]` | — | pending | — | NO-DATA |
| Queue wait time p50 `[cognito-forms]` | — | pending | — | NO-DATA |
| Raw-invocation deny recurrence `[cognito-forms]` | 0/30d | pending | — | PENDING-BASELINE |

## containment

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Runaway containment trip rate | 3660/30d | pending | — | PENDING-BASELINE |

## halt-handling

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Halt dwell time p50 | 10862.4s (30d) | pending | — | PENDING-BASELINE |

## pipeline-efficiency

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Cycles per completion | 6.74 (30d) | pending | — | PENDING-BASELINE |
| MCP-validation round trips per feature | — | pending | — | NO-DATA |

## harness-canary

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Canary trip precision | 0% (90d) | pending | — | PENDING-BASELINE |
| Canary closure latency p50 | 4 (90d) | pending | — | PENDING-BASELINE |

## skill-config

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Failed Reads / dangling references on .claude/skill-config/ paths `[all]` | 3 (30d) | pending | — | PENDING-BASELINE |

## efficacy-loop

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Conclusive efficacy verdicts produced | 0/90d | pending | — | PENDING-BASELINE |
| Confounded-verdict ratio | 10.8% (90d) | pending | — | PENDING-BASELINE |

## anti-overfit-gate

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Design-gate scoped-change hit rate `[claude-config]` | — | pending | — | NO-DATA |
| Gate-weakening override rate `[claude-config]` | — | pending | — | NO-DATA |
| Design-gate false-positive burden `[claude-config]` | — | pending | — | NO-DATA |
| Verdict-vs-efficacy disagreement `[claude-config]` | — | pending | — | NO-DATA |

## bug-pipeline

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Age in days of the oldest open docs/bugs/ item `[claude-config]` | 11 (1d) | 17 (measured 2026-07-11) | — | PENDING-BASELINE |
| Count of docs/bugs/ items at Status: Concluded (investigated, never fixed) `[claude-config]` | 14 (1d) | 23 (measured 2026-07-11) | — | PENDING-BASELINE |

## lazy-core

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Monolith-induced drag on lazy_core interventions `[claude-config]` | 3 (30d) | 1 (measured 2026-07-13) | — | PENDING-BASELINE |

## generalized-runner

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Raw heavy-gate invocation deny recurrence (AlgoBooth) `[algobooth]` | 0/30d | pending | — | PENDING-BASELINE |
| Premature turn-end on in-flight gate batteries (non-Cognito) `[claude-config]` | 3/30d | pending | — | PENDING-BASELINE |

## subagent-wedge-backstop

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Wedged-subagent pipeline-strand recurrence `[claude-config]` | 3/30d | pending | — | PENDING-BASELINE |

## hook-plane

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Hook-plane duplicated scaffolding lines | 697 (1d) | 467 (retro-derived 2026-07-11) | — | PENDING-BASELINE |

## cycle-prompt-deflation

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Max assembled cycle-prompt bytes across dispatchable profiles `[claude-config]` | 20265 (30d) | 20843 (measured 2026-07-19) | — | PENDING-BASELINE |

## orchestrator-tool-search

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Share of tool-gap harden dispatches NOT preceded by a --tool-search in the same cycle `[claude-config]` | 1 (30d) | pending | — | PENDING-BASELINE |

## claude-md-maintenance

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Cognito CLAUDE.local.md auto-loaded corpus size `[cognito-forms]` | 40830 (1d) | 40830 (measured 2026-07-17) | 44000 / 48000 | OK ▼ |

## Regressions

- (none)

## Registry health

- (none)

## Canary health

- 21 canaries open, oldest 3d, 0 will no-data-close within 7d

## Notes

- `build-queue-false-green-rate`: no build records carrying hygiene.build_fidelity in the window
- `build-queue-wait-time-p50`: results records carry no queued_at/started_at pair — runner timestamp add is a workstation-deferred follow-up
- `mcp-validation-round-trips-per-feature`: unknown telemetry selector 'mcp-validation-round-trips-per-feature'
- `anti-overfit-gate-hit-rate`: no computation registered for 'harness-gate'/'hit-rate'
- `anti-overfit-gate-override-rate`: no computation registered for 'harness-gate'/'override-rate'
- `anti-overfit-gate-false-positive-rate`: no computation registered for 'harness-gate'/'false-positive-rate'
- `anti-overfit-gate-verdict-efficacy-disagreement`: no computation registered for 'harness-gate'/'verdict-efficacy-disagreement'
