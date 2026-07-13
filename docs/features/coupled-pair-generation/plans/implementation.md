---
kind: implementation-plan
feature_id: coupled-pair-generation
status: Complete
covers_phases: [1, 2, 3]
---

# Implementation Plan — Coupled-Pair Generation (Phases 1–3)

Lean, reference-based. Full context in [`SPEC.md`](../SPEC.md),
[`RESEARCH_SUMMARY.md`](../RESEARCH_SUMMARY.md), [`PHASES.md`](../PHASES.md). Phase 4 is DEFERRED
(gated on the [`NEEDS_INPUT_PROVISIONAL.md`](../NEEDS_INPUT_PROVISIONAL.md) decision) and is NOT
covered here.

## Work units

- [x] **WU-1 — Generator (`user/scripts/generate-coupled-skills.py`).** Stdlib. Import
  `apply_tokens` from `lazy_parity_audit` (single substitution impl). `split_blocks` reuses the
  audit's `^#{2,3} .*$` heading model; concat-of-blocks == source (identity). CRLF-safe IO
  (`open(..., newline="")`). Modes `--extract` / `--write` / `--check` (default) / `--report`;
  `--pair` / `--repo-root`. Directive model: `canonical` (restate via token subs) / `verbatim`
  (byte-exact `"\n"`-split line array); deletion by omission. Extract downgrades to `verbatim`
  whenever token-sub does not reproduce the derived block exactly → byte-faithful by construction.

- [x] **WU-2 — Overlays (`user/scripts/coupled-overlays/*.overlay.json`).** `--extract` for all 5
  pairs. Centralized under `scripts/` (not the skills tree). Schema: `{schema_version, canonical,
  derived, generator, note, directives[]}`; `validate_overlay` checks required keys, ops, verbatim
  `lines` typing, and (C4-successor) that every `canonical` directive keys a live canonical heading.

- [x] **WU-3 — Drift gate + manifest wiring.** `--check` = regen-byte-diff vs committed derived
  (exit 1 + first-divergent-section on mismatch). Add additive `"overlay"` key per pair to
  `lazy-parity-manifest.json`. Confirm `lazy_parity_audit.py`, `doc-drift-lint.py` stay exit 0.
  Byte-faithful migration proof: `--write` leaves derived files byte-identical (`git status` clean
  for the 5 derived SKILL.md).

- [x] **WU-4 — Tests (`user/scripts/test_generate_coupled_skills.py`).** Round-trip identity,
  golden byte-comparison per real pair (committed overlay + fresh extract), `--check` drift
  detection (clean-tree / hand-edit / write-repairs), determinism, schema validation, canonical-edit
  propagation. Run `test_lazy_parity.py` + `test_doc_drift_lint.py` to confirm the manifest edit is
  safe.

## Gates (all green)

`pytest test_generate_coupled_skills.py` (34) · `lazy_parity_audit.py --repo-root .` (0) ·
`doc-drift-lint.py --repo-root .` (0) · `generate-coupled-skills.py --check` (0) ·
`lint-skills.py --check-projected --check-capabilities` (0) · `project-skills.py` (clean) ·
`test_lazy_parity.py` + `test_doc_drift_lint.py` (81).
