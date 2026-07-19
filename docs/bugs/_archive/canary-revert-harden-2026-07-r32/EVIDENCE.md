---
kind: canary-evidence
canary_revert_of: harden-2026-07-r32
intervention_record: docs\interventions\harden-2026-07-r32.md
tripped: 2026-07-16
---

# Canary Trip Evidence — harden-2026-07-r32

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:halt regressed +987.5% vs frozen baseline 1.3333 ev/run (band ±25%, 29 post-ship occurrences over 2 window runs)

### Band numbers

- relative movement: 987.5% (band ±25%)
- post-ship occurrences: 29 (baseline 1.3333 ev/run → post 14.5 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- 879613d1c02afd20f2235fc832885cd46d7e42d7

## Coupled-pair scope

No coupled-pair scope — the commit set touches no parity-guarded pair, so a revert need not span a sibling.

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r32.md
- SPEC: docs/features/harden-2026-07-r32/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r32/GATE_VERDICT.md
