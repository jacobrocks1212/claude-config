---
kind: implementation-plan
feature_id: plan-structure-authoring-gate
status: Complete
created: 2026-07-12
complexity: complex
phases: [1, 2, 3]
---

> **Plan** — single self-contained part covering Phases 1-3 (the SKILLS-lane scope). Phase 4
> (the state-script pickup backstop) is explicitly out of this lane's scope — see PHASES.md and
> NEEDS_INPUT_PROVISIONAL.md — and is not covered by this plan.
> To execute: worked inline by this lane (SKILLS-lane implementation session, 2026-07-12).

# Implementation Plan — plan-structure-authoring-gate (Phases 1-3)

**PHASES.md:** `docs/features/plan-structure-authoring-gate/PHASES.md` (4 phases; this plan
covers 1-3)
**SPEC.md:** `docs/features/plan-structure-authoring-gate/SPEC.md`

## Work Units

- [x] WU-1 — `validate-plan.py` `--structural` CLI mode + rules 1/2/3/4/6 + exception-safe
  frontmatter helpers
- [x] WU-2 — `test_validate_plan.py` per-rule fixtures + scope/IO edge cases
- [x] WU-3 — Real 252-file corpus scan; narrow rules 2 and 3 to eliminate false positives found
- [x] WU-4 — Rule 5 (series-vs-dependency order) + fixtures (inversion, valid high-phase
  prerequisite, forward-mention non-flag, single-part N/A)
- [x] WU-5 — `_components/plan-structural-gate.md` + injection into `/write-plan`,
  `/spec-phases`, `/spec-phases-batch`
- [x] WU-6 — Confirm `/plan-feature`/`/plan-bug` inherit for free; document the
  `/write-plan-cloud` exclusion
- [x] WU-7 — Re-projection + skill lint + coupled-skills check + parity audit, all green
- [x] WU-8 — `TestRealCorpusCheck` allowlist test (regression net against future corpus drift)

## Reference — component reuse

Reused `lazy_core.py` (imported, never edited): `_plan_wu_checkbox_counts`,
`remaining_unchecked_are_verification_only`, `_VERIFICATION_ONLY_MARKER`,
`_VERIFICATION_SECTION_RE`, `_DELIVERABLES_SECTION_RE`, `_PLAN_PART_RE`. Modeled the new
`_components/plan-structural-gate.md` component's shape on
`~/.claude/skills/_components/mcp-coverage-audit.md` (why / when-it-runs / what-it-checks /
residency-note / coupling-note).

## Completion Evidence

- `python3 -m pytest user/scripts/test_validate_plan.py -q` → 29 passed (includes the live
  252-file real-corpus scan).
- `python3 user/scripts/generate-coupled-skills.py --check --repo-root .` → all pairs
  byte-identical (this feature does not touch any coupled pair; confirms no collateral drift).
- `python3 user/scripts/lazy_parity_audit.py --repo-root .` → exit 0 (this feature does not
  touch either state script; confirms no collateral drift).
- `python3 user/scripts/project-skills.py` → clean re-projection (88 skills, 100 components, 0
  errors, all 3 repo projections); spot-checked `write-plan`, `spec-phases`, `spec-phases-batch`
  projected output — the new component expands correctly at each new step heading.
- `python3 user/scripts/lint-skills.py --check-projected --check-capabilities` → clean.
- `python3 user/scripts/doc-drift-lint.py --repo-root .` → 0 new drift findings (informational —
  not a required gate for this feature, run as an extra sanity check).

**Completion (gate-owned, cross-lane — NOT this plan's WU):** this feature is NOT flipped to
`**Status:** Complete` and no `COMPLETED.md` is written — a `NEEDS_INPUT_PROVISIONAL.md` is on
disk (Phase 4 cross-lane scope + two provisional adaptations), which per the park-provisional
protocol withholds the completion flip until operator ratification.
