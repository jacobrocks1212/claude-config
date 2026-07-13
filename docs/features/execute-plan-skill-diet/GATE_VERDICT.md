---
kind: gate-verdict
feature_id: execute-plan-skill-diet
gate_version: 1
date: 2026-07-13
scope_hit:
  - user/scripts/lazy_core.py
  - user/hooks/execute-plan-compact-reorient.sh
  - user/skills/lazy-batch/SKILL.md
  - user/skills/lazy-bug-batch/SKILL.md
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: Excised inline prose from `execute-plan/SKILL.md` (a 433-line net reduction — the "diet"), replaced by referenced components (`execution-completion-summary.md`) and scoped reads.
---

## Adversarial answers

**Smeared scope (how handled).** This feature has NO isolable commit: its implementation landed in
the shared chore commit `1a3dffd1` ("in-flight harness work committed alongside the 2026-07-09
orchestration"), which co-mingles four plan-skills features (execute-plan-skill-diet, lean-plan-files,
phases-slice-scoped-reads, spec-excerpt-scoped-plans), the separate lazy-cycle-containment work, and a
mass description-tightening touch across every skill. The feature is marked Complete but carries only a
SPEC.md (no PHASES/plans/receipt). Its headline deliverable — the `execute-plan/SKILL.md` 433-line diet
— is NOT itself a control surface (`execute-plan` is not `lazy*`/`harden-harness`), so its manifest
footprint is thin: `lazy_core.py` (9-line), the new `execute-plan-compact-reorient.sh` hook, and the
lazy* SKILL.md description-tightening. `harness-gate.py` was run over `00b210a3..1a3dffd1`; unrelated
co-committed hunks are subtracted below.

### overfit
The scope-file changes are a leaner SKILL.md description field, a new compact-reorient hook that
re-injects the active plan path on a compaction boundary (keyed on a per-repo run marker, not any
incident literal), and 9 lines of `lazy_core.py`. No incident-shaped literal appended to a production
matcher. Structural property: the hook keys on run-marker presence + plan `status`, not on a slug/date.

### tautology
No `## Intervention Hypothesis` block → checker flags. If the diet were broken, `execute-plan/SKILL.md`
would still be bloated — directly measurable by byte count — and a broken compact-reorient hook would
fail to re-orient a compacted run (observable as a lost in-flight plan). Independent signal: the file
byte size + the hook's observable re-injection behavior, neither self-emitted. `signal_independence:
independent`.

### gate_weakening
Verified over the feature's own hunks: no `def test_*` deletion, no `permissionDecision: deny` /
`refuse_*` / `exit 3` removal, no `*_BYPASS`, no sanction/exemption-set growth. The new
`execute-plan-compact-reorient.sh` is documented as add-context-only (never denies), fail-OPEN.
⚠ IMPORTANT SUBTRACTION: the shared commit `1a3dffd1` DOES remove a deny branch
(`_deny(CORRECTIVE, "recursive-agent-dispatch")`) from `lazy-cycle-containment.sh` — but that hunk
belongs to the **lazy-cycle-containment** feature (`docs/bugs/adhoc-containment-denies-mandated-explore-fanout`,
2026-07-09, already documented in CLAUDE.md as correct behavior), NOT to execute-plan-skill-diet (this
feature's SPEC makes zero mention of containment/deny/recursive-agent). It is mentally subtracted as an
unrelated co-committed hunk. This feature's own scope contains no weakening. Pass.

### complexity
Retires inline execute-plan prose (the 433-line diet), replaced by referenced components. The retire is
real: the excised prose is gone from the SKILL.md and moved into `execution-completion-summary.md` +
scoped reads.
