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
| Runaway containment trip rate | 2194/30d | pending | — | PENDING-BASELINE |

## halt-handling

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Halt dwell time p50 | 240.75s (30d) | pending | — | PENDING-BASELINE |

## pipeline-efficiency

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Cycles per completion | 10.6 (30d) | pending | — | PENDING-BASELINE |
| MCP-validation round trips per feature | — | pending | — | NO-DATA |

## harness-canary

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Canary trip precision | — | pending | — | NO-DATA |
| Canary closure latency p50 | — | pending | — | NO-DATA |

## skill-config

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Failed Reads / dangling references on .claude/skill-config/ paths `[all]` | 1 (30d) | pending | — | PENDING-BASELINE |

## efficacy-loop

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Conclusive efficacy verdicts produced | — | pending | — | NO-DATA |
| Confounded-verdict ratio | — | pending | — | NO-DATA |

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
| Age in days of the oldest open docs/bugs/ item `[claude-config]` | 13 (1d) | 17 (measured 2026-07-11) | — | PENDING-BASELINE |
| Count of docs/bugs/ items at Status: Concluded (investigated, never fixed) `[claude-config]` | 15 (1d) | 23 (measured 2026-07-11) | — | PENDING-BASELINE |

## Regressions

- (none)

## Registry health

- (none)

## Canary health

- 29 canaries open, oldest 8d, 0 will no-data-close within 7d

## Notes

- `build-queue-false-green-rate`: build-queue results dir absent (~\.claude\state\build-queue\results) — no build-queue state on this machine
- `build-queue-wait-time-p50`: build-queue results dir absent (~\.claude\state\build-queue\results) — no build-queue state on this machine
- `mcp-validation-round-trips-per-feature`: unknown telemetry selector 'mcp-validation-round-trips-per-feature'
- `canary-trip-precision`: no canary trips in the window — precision is undefined until the canary has tripped (never a fabricated zero)
- `canary-closure-latency-p50`: no canary closures (excluding no-data) in the window
- `efficacy-verdicts-produced`: no reviews recorded in the window
- `confounded-verdict-ratio`: no due reviews in the window — ratio is undefined
- `anti-overfit-gate-hit-rate`: no computation registered for 'harness-gate'/'hit-rate'
- `anti-overfit-gate-override-rate`: no computation registered for 'harness-gate'/'override-rate'
- `anti-overfit-gate-false-positive-rate`: no computation registered for 'harness-gate'/'false-positive-rate'
- `anti-overfit-gate-verdict-efficacy-disagreement`: no computation registered for 'harness-gate'/'verdict-efficacy-disagreement'
