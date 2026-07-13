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
| Runaway containment trip rate | 2138/30d | pending | — | PENDING-BASELINE |

## halt-handling

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Halt dwell time p50 | 240.75s (30d) | pending | — | PENDING-BASELINE |

## pipeline-efficiency

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Cycles per completion | 10.6 (30d) | pending | — | PENDING-BASELINE |

## harness-canary

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Canary trip precision | — | pending | — | NO-DATA |
| Canary closure latency p50 | — | pending | — | NO-DATA |

## skill-config

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Failed Reads / dangling references on .claude/skill-config/ paths `[all]` | 0 (30d) | pending | — | PENDING-BASELINE |

## efficacy-loop

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Conclusive efficacy verdicts produced | — | pending | — | NO-DATA |
| Confounded-verdict ratio | — | pending | — | NO-DATA |

## Regressions

- (none)

## Registry health

- (none)

## Canary health

- 28 canaries open, oldest 7d, 0 will no-data-close within 7d

## Notes

- `build-queue-false-green-rate`: build-queue results dir absent (~\.claude\state\build-queue\results) — no build-queue state on this machine
- `build-queue-wait-time-p50`: build-queue results dir absent (~\.claude\state\build-queue\results) — no build-queue state on this machine
- `canary-trip-precision`: no canary trips in the window — precision is undefined until the canary has tripped (never a fabricated zero)
- `canary-closure-latency-p50`: no canary closures (excluding no-data) in the window
- `efficacy-verdicts-produced`: no reviews recorded in the window
- `confounded-verdict-ratio`: no due reviews in the window — ratio is undefined
