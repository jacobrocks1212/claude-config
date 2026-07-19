---
kind: canary-evidence
canary_revert_of: harden-2026-07-r64
intervention_record: docs\interventions\harden-2026-07-r64.md
tripped: 2026-07-17
---

# Canary Trip Evidence — harden-2026-07-r64

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:halt regressed +325.0% vs frozen baseline 1.0 ev/run (band ±25%, 34 post-ship occurrences over 8 window runs)

### Band numbers

- relative movement: 325.0% (band ±25%)
- post-ship occurrences: 34 (baseline 1.0 ev/run → post 4.25 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- 3add529d6a8cd29a62aca708cf2c956ea70b0b87

## Coupled-pair scope

No coupled-pair scope — the commit set touches no parity-guarded pair, so a revert need not span a sibling.

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r64.md
- SPEC: docs/features/harden-2026-07-r64/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r64/GATE_VERDICT.md
