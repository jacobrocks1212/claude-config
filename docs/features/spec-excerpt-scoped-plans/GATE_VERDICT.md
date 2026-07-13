---
kind: gate-verdict
feature_id: spec-excerpt-scoped-plans
gate_version: 1
date: 2026-07-13
scope_hit:
  - user/scripts/lazy_core.py
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: Full-SPEC inlining into plan files — replaced by scoped SPEC excerpts (only the SPEC slice a plan part needs, rather than the whole SPEC duplicated into each plan).
---

## Adversarial answers

**Smeared scope (how handled).** No isolable commit: implementation landed in the shared chore commit
`1a3dffd1`, co-mingled with three sibling plan-skills features, lazy-cycle-containment, and a mass
description-tightening touch. Feature is Complete with only a SPEC.md. Its SPEC-excerpt mechanism lives in
write-plan/plan-authoring surfaces that are NOT control surfaces; its manifest footprint is the lazy*
SKILL.md description touch + `lazy_core.py`. `harness-gate.py` run over `00b210a3..1a3dffd1`; unrelated
hunks subtracted.

### overfit
The scope-file changes are leaner SKILL.md descriptions and a small `lazy_core.py` delta. The SPEC-excerpt
mechanism is an authoring convention (carve the relevant SPEC slice into a plan instead of the whole file),
not a rule fitted to an instance. No incident-shaped literal appended to any matcher. Structural property:
excerpts are scoped by plan-part relevance, not keyed on any slug/date. No incident matcher exists to
reshape.

### tautology
No `## Intervention Hypothesis` block → checker flags. If excerpt-scoping were broken, plans would inline
whole SPECs again — measurable by plan-file SPEC-duplication size. Independent signal: measured
plan-file/SPEC-duplication byte count, not self-emitted. `signal_independence: independent`.

### gate_weakening
Verified over this feature's own hunks: no `def test_*` deletion, no `permissionDecision: deny` /
`refuse_*` / `exit 3` removal, no `*_BYPASS`, no sanction/exemption-set growth. ⚠ SUBTRACTION: the shared
commit `1a3dffd1` removes a deny branch (`recursive-agent-dispatch`) from `lazy-cycle-containment.sh`,
belonging to the lazy-cycle-containment feature (`docs/bugs/adhoc-containment-denies-mandated-explore-fanout`),
NOT spec-excerpt-scoped-plans (this SPEC makes zero mention of containment/deny). Subtracted as an unrelated
co-committed hunk. No weakening in scope. Pass.

### complexity
Retires full-SPEC inlining into plans, replaced by scoped SPEC excerpts. The retire is real — plans now
carry only the SPEC slice a part needs, so the whole-SPEC-duplication surface stops being authored.
