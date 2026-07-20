---
kind: canary-evidence
canary_revert_of: harden-2026-07-r48
intervention_record: docs\interventions\harden-2026-07-r48.md
tripped: 2026-07-18
---

# Canary Trip Evidence — harden-2026-07-r48

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:containment-refusal regressed +334.1% vs frozen baseline 72.85 ev/run (band ±25%, 1265 post-ship occurrences over 4 window runs)

### Band numbers

- relative movement: 334.1% (band ±25%)
- post-ship occurrences: 1265 (baseline 72.85 ev/run → post 316.25 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- 251187c8d620446d363c4477f31f89964d426f17

## Coupled-pair scope

No coupled-pair scope — the commit set touches no parity-guarded pair, so a revert need not span a sibling.

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r48.md
- SPEC: docs/features/harden-2026-07-r48/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r48/GATE_VERDICT.md
