---
kind: gate-verdict
feature_id: lean-plan-files
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
retires: Verbose, fully-inlined plan-file content — replaced by lean, reference-based plan files (context pulled from SPEC/PHASES/components at execution time rather than duplicated into each plan).
---

## Adversarial answers

**Smeared scope (how handled).** No isolable commit: implementation landed in the shared chore commit
`1a3dffd1`, co-mingled with three sibling plan-skills features, lazy-cycle-containment, and a mass
description-tightening touch. Feature is Complete with only a SPEC.md. Its plan-file leanness work is
largely in write-plan/plan-template surfaces that are NOT control surfaces; its manifest footprint is the
lazy* SKILL.md description-tightening + `lazy_core.py`. `harness-gate.py` run over `00b210a3..1a3dffd1`;
unrelated hunks subtracted below.

### overfit
The scope-file changes are leaner SKILL.md descriptions and a small `lazy_core.py` delta — no incident
literal appended to any matcher. The "lean plan" mechanism is a documentation/authoring convention
(reference instead of inline), not a rule fitted to an instance. Structural property: plan files point at
canonical sources rather than duplicating them; nothing keys on a slug/date. No incident matcher exists to
reshape.

### tautology
No `## Intervention Hypothesis` block → checker flags. If leanness were broken, plan files would be bloated
again — directly measurable by plan-file byte size and the presence of duplicated (rather than referenced)
context. Independent signal: measured plan-file size + reference density, not self-emitted.
`signal_independence: independent`.

### gate_weakening
Verified: no `def test_*` deletion, no `permissionDecision: deny` / `refuse_*` / `exit 3` removal, no
`*_BYPASS`, no sanction/exemption-set growth in this feature's own hunks. ⚠ SUBTRACTION: the shared commit
`1a3dffd1` removes a deny branch (`recursive-agent-dispatch`) from `lazy-cycle-containment.sh`, but that
belongs to the lazy-cycle-containment feature (`docs/bugs/adhoc-containment-denies-mandated-explore-fanout`),
NOT lean-plan-files (this SPEC makes zero mention of containment/deny). Subtracted as an unrelated
co-committed hunk. No weakening in scope. Pass.

### complexity
Retires the verbose fully-inlined plan-file convention, replaced by lean reference-based plans. The retire
is real — plans now reference canonical sources instead of duplicating them, so the duplicated-context
surface stops being authored.
