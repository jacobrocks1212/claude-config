---
kind: canary-evidence
canary_revert_of: harden-2026-07-r54
intervention_record: docs\interventions\harden-2026-07-r54.md
tripped: 2026-07-18
---

# Canary Trip Evidence — harden-2026-07-r54

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:gate-refusal regressed +59.6% vs frozen baseline 4.7 ev/run (band ±25%, 30 post-ship occurrences over 4 window runs)

### Band numbers

- relative movement: 59.6% (band ±25%)
- post-ship occurrences: 30 (baseline 4.7 ev/run → post 7.5 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- 1af48e1d655098e74019bf35b9bf0b37c58ccee5

## Coupled-pair scope

No coupled-pair scope — the commit set touches no parity-guarded pair, so a revert need not span a sibling.

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r54.md
- SPEC: docs/features/harden-2026-07-r54/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r54/GATE_VERDICT.md
