---
kind: canary-evidence
canary_revert_of: harden-2026-07-r97
intervention_record: docs\interventions\harden-2026-07-r97.md
tripped: 2026-07-19
---

# Canary Trip Evidence — harden-2026-07-r97

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:halt regressed +75.0% vs frozen baseline 1.0 ev/run (band ±25%, 7 post-ship occurrences over 4 window runs)

### Band numbers

- relative movement: 75.0% (band ±25%)
- post-ship occurrences: 7 (baseline 1.0 ev/run → post 1.75 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- 04ecf9632dc96a0f8b8e476609b071e820399d2b

## Coupled-pair scope

No coupled-pair scope — the commit set touches no parity-guarded pair, so a revert need not span a sibling.

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r97.md
- SPEC: docs/features/harden-2026-07-r97/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r97/GATE_VERDICT.md
