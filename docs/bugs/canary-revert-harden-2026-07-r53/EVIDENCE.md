---
kind: canary-evidence
canary_revert_of: harden-2026-07-r53
intervention_record: docs\interventions\harden-2026-07-r53.md
tripped: 2026-07-18
---

# Canary Trip Evidence — harden-2026-07-r53

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:containment-refusal regressed +333.8% vs frozen baseline 72.9 ev/run (band ±25%, 1265 post-ship occurrences over 4 window runs)

### Band numbers

- relative movement: 333.8% (band ±25%)
- post-ship occurrences: 1265 (baseline 72.9 ev/run → post 316.25 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- 8a7bc738c9dfae0ec6079d5930086de54a558ca6

## Coupled-pair scope

This change touches a parity-guarded coupled pair. Any revert MUST cover the WHOLE pair and END with `python3 user/scripts/lazy_parity_audit.py --repo-root .` green — reverting one half breaks the audit.

- user/skills/lazy-batch/SKILL.md
- user/skills/lazy-bug-batch/SKILL.md
- repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r53.md
- SPEC: docs/features/harden-2026-07-r53/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r53/GATE_VERDICT.md
