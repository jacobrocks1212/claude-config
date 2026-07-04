# Friction KPI Scorecard

> Pure-read render of `docs/kpi/registry.json` by `user/scripts/kpi-scorecard.py` — script-computed values only, no embedded wall-clock (freshness is this file's git commit time). An absent/unrecordable signal renders NO-DATA, never a fabricated zero; a `pending` baseline renders PENDING-BASELINE.

## build-queue

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| False-green build rate `[cognito-forms]` | — | pending | — | NO-DATA |
| Queue wait time p50 `[cognito-forms]` | — | pending | — | NO-DATA |
| Raw-invocation deny recurrence `[cognito-forms]` | — | pending | — | NO-DATA |

## containment

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Runaway containment trip rate | — | pending | — | NO-DATA |

## halt-handling

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Halt dwell time p50 | — | pending | — | NO-DATA |

## pipeline-efficiency

| KPI | current | baseline | band (warn/breach) | status |
|-----|---------|----------|--------------------|--------|
| Cycles per completion | — | pending | — | NO-DATA |

## Regressions

- (none)

## Registry health

- (none)

## Notes

- `build-queue-false-green-rate`: build-queue results dir absent (~/.claude/state/build-queue/results) — no build-queue state on this machine
- `build-queue-wait-time-p50`: build-queue results dir absent (~/.claude/state/build-queue/results) — no build-queue state on this machine
- `build-queue-raw-invocation-deny-recurrence`: deny ledger absent — no denies recorded for this repo
- `containment-runaway-trip-rate`: telemetry ledger absent — no run has emitted events for this repo yet
- `halt-dwell-p50`: telemetry ledger absent — no run has emitted events for this repo yet
- `cycles-per-completion`: telemetry ledger absent — no run has emitted events for this repo yet
