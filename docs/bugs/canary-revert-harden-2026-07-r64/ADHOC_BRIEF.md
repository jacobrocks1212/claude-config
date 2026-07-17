---
kind: adhoc-brief
bug_id: canary-revert-harden-2026-07-r64
enqueued_by: lazy-adhoc
date: 2026-07-17
---

# Ad-hoc bug: Revert-or-redesign canary trip: harden-2026-07-r64

Canary tripped for a shipped control-surface change — evidence attached (EVIDENCE.md in this dir).

- Intervention record: docs\interventions\harden-2026-07-r64.md
- Canary: harden-2026-07-r64

Question for /spec-bug: REVERT (covering the coupled-pair scope + a green parity audit), REDESIGN, or close-as-noise? Nothing was reverted automatically — the canary only flags and enqueues; this item flows through spec, plan, and normal triage under full gates.
