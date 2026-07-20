---
kind: canary-evidence
canary_revert_of: harden-2026-07-r44
intervention_record: docs\interventions\harden-2026-07-r44.md
tripped: 2026-07-16
---

# Canary Trip Evidence — harden-2026-07-r44

Flag-and-enqueue only — NOTHING was reverted automatically (D4). Triage this like any bug: revert (covering the pair scope + parity audit below), redesign, or close-as-noise (itself a signal for tuning the canary bands).

## Trip reason

targeted signal event:gate-refusal regressed +50.0% vs frozen baseline 4.0 ev/run (band ±25%, 6 post-ship occurrences over 1 window runs)

### Band numbers

- relative movement: 50.0% (band ±25%)
- post-ship occurrences: 6 (baseline 4.0 ev/run → post 6.0 ev/run)

### Attributed fresh incidents (verbatim)

```
(none — band-only trip)
```

## Commit set (revert target)

- c8a05bf7a509634b6c4f3535987ba4ba0a701d9f

## Coupled-pair scope

This change touches a parity-guarded coupled pair. Any revert MUST cover the WHOLE pair and END with `python3 user/scripts/lazy_parity_audit.py --repo-root .` green — reverting one half breaks the audit.

- user/skills/lazy-batch/SKILL.md
- user/skills/lazy-bug-batch/SKILL.md
- repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md

## Degraded-revert note

none — a plain `git revert` of the commit set is expected to back the change out.

## Linked docs

- Intervention record: docs\interventions\harden-2026-07-r44.md
- SPEC: docs/features/harden-2026-07-r44/SPEC.md
- Gate verdict (if present): docs/features/harden-2026-07-r44/GATE_VERDICT.md
