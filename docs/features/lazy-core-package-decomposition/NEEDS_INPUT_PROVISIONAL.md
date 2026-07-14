---
kind: needs-input
feature_id: lazy-core-package-decomposition
decisions:
  - id: P5-GATE-WEAKENING-SIGNOFF
    summary: harness-gate flagged the Phase-5 WU-1/WU-2 move commits gate_weakening HIT (refusal defs left _monolith.py; sanction-set literals re-appeared in markers.py). Justified as the two sides of a byte-verbatim MOVE (receipts in GATE_VERDICT.md Phase 5) — zero sanction-set members added/removed, refusal tests green against the moved code, suite 2230 -> 2231 (no deletions). D4 makes gate-weakening operator-sign-off-only; recommended option (ratify the move-shape justification) adopted provisionally, run not halted.
divergence: product
written_by: execute-plan
date: 2026-07-13
next_skill: none
---

# Provisional decisions — lazy-core-package-decomposition (Phase 5)

The anti-overfit design gate's mechanical half flagged the Phase-5 marker/pseudo
extraction commits (a9e0581a / 4bd51536) `gate_weakening: hit` — structurally
correct detection (a refusal `def` left `_monolith.py`; membership constructs
appeared in `markers.py`), semantically a byte-verbatim MOVE (receipts in
GATE_VERDICT.md Phase-5 entry). D4 makes gate-weakening operator-sign-off-only,
so this file records the pending ratification instead of halting the run
(park-provisional directive).

**Operator action:** confirm the GATE_VERDICT.md Phase-5 `gate_weakening`
justification (or direct a revert). No code change is expected either way —
the moved refusals are pinned by the existing exit-3 / zero-side-effect test
population, which is green. WU-3 (147fd912) and WU-4 pass gate_weakening.
