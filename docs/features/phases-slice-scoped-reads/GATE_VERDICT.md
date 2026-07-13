---
kind: gate-verdict
feature_id: phases-slice-scoped-reads
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
retires: The prose grep-then-ranged-Read PHASES.md mandate in `source-reread.md` (measurably ignored in the field — sessions still read 40–65KB PHASES.md whole) — replaced by the deterministic `phases-slice.py` scoped reader.
---

## Adversarial answers

**Smeared scope (how handled).** No isolable commit: implementation landed in the shared chore commit
`1a3dffd1`, co-mingled with three sibling plan-skills features, lazy-cycle-containment, and a mass
description-tightening touch. Feature is Complete with only a SPEC.md. Its headline deliverable —
`phases-slice.py` (209 new lines) — is NOT a control surface (not in the manifest's script list), and
`source-reread.md` is not in the component allowlist, so its manifest footprint is the lazy* SKILL.md
touch + `lazy_core.py`. `harness-gate.py` run over `00b210a3..1a3dffd1`; unrelated hunks subtracted.

### overfit
The scope-file changes are leaner SKILL.md descriptions and 9 lines of `lazy_core.py`. `phases-slice.py`
reuses the canonical `lazy_core._PHASE_HEADING_RE` byte-identically for phase boundaries — it does NOT
introduce a new incident-fitted matcher; it copies the existing structural marker. No incident-shaped
literal appended to a production matcher. Structural property: phase slices are keyed on the canonical
`^### Phase` heading regex, not on any slug/date.

### tautology
No `## Intervention Hypothesis` block → checker flags. If scoped reads were broken, orchestrators would
read whole 40–65KB PHASES.md files again — the exact field-measured regression the SPEC cites — observable
in session-log read sizes. Independent signal: mined per-session PHASES.md read byte counts (the toolify /
mine-sessions corpus), which this feature does not itself emit. `signal_independence: independent`.

### gate_weakening
Verified over this feature's own hunks: no `def test_*` deletion, no `permissionDecision: deny` /
`refuse_*` / `exit 3` removal, no `*_BYPASS`, no sanction/exemption-set growth. `phases-slice.py` is a pure
read (never writes). ⚠ SUBTRACTION: the shared commit `1a3dffd1` removes a deny branch
(`recursive-agent-dispatch`) from `lazy-cycle-containment.sh`, belonging to the lazy-cycle-containment
feature (`docs/bugs/adhoc-containment-denies-mandated-explore-fanout`), NOT phases-slice-scoped-reads (this
SPEC makes zero mention of containment/deny). Subtracted as an unrelated co-committed hunk. No weakening in
scope. Pass.

### complexity
Retires the prose grep-then-ranged-Read PHASES.md mandate in `source-reread.md`, replaced by the
deterministic `phases-slice.py` reader. The retire is real and load-bearing: the SPEC notes the prose
mandate was measurably ignored in the field, so the script IS the mandate now — the ignorable prose surface
is replaced by a deterministic tool.
