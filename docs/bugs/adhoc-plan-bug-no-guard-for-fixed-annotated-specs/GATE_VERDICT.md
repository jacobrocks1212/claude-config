---
kind: gate-verdict
feature_id: adhoc-plan-bug-no-guard-for-fixed-annotated-specs
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/scripts/bug-state.py
  - user/scripts/lazy_core/__init__.py
  - user/scripts/lazy_core/docmodel.py
  - user/scripts/lazy_core/gates.py
checks:
  overfit: flag-justified
  tautology: flag-justified
  gate_weakening: pass
  complexity: declared
retires: net-new — adds `spec_fixed_annotation()` (a `**Fixed:**`-line reader mirroring `spec_status`), `is_fixed_unreconciled()` + `format_fixed_unreconciled_blocker()`, and a `bug-state.py` Step-4 pre-gate that diverts a `**Fixed:**`-annotated, no-`FIXED.md`-receipt `Concluded` bug to a canonical `BLOCKED.md` (`blocker_kind: fixed-unreconciled`) instead of burning a full `/plan-bug`. No rule/surface retired; a NEW fail-fast guard is added to the bug router.
---

## Adversarial answers

Authored via the corrected `gate-verdict` dispatch flow: `bug-state.py --gate-verdict-check
docs/bugs/adhoc-plan-bug-no-guard-for-fixed-annotated-specs` reports `in_scope: true`,
`scope_hit` = the four control-surface files above, `gate_weakening_hit: false`, `item_commits`
= the item's own merged fix commits (`23b3442`, `3b5f2d7`, `66195d8`, `b70b0dd`, `39b4851`).
The prior park's `BLOCKED.md` predicted "overfit/tautology/gate_weakening = pass"; running the
checker over the ACTUAL diff (now possible) shows two `flag`s — recorded honestly below (both
`flag-justified`, neither a `hit`; the ship seam accepts a justified flag).

### overfit
`flag`, not a `hit`. Every `overfit` evidence item is a quoted-STRING DATA line: multi-line
sentinel-template body text and the canonical `BLOCKED.md` prose emitted by
`format_fixed_unreconciled_blocker()`, `**Fixed:**`/`**Status:**` fixture strings in
`bug-state.py`'s test-fixture writers, and docstring/dict-value string literals in
`lazy_core/gates.py`. **Structural property:** NONE is a literal appended to a matcher construct
— no regex alternation, keyword set, or allow-list gains an element; these strings are inert data
the harness never pattern-matches against, and no incident-shaped (`docs/{features,bugs}/<slug>`,
dated, session) literal is added. The nearest-recurrence-not-caught question is moot (there is no
matcher being fitted to observed data). These flags are the KNOWN `detect_overfit` case-(b)
precision gap — it matches any quoted-string line near a `[`/`{`/`(`, where its sibling
`detect_gate_weakening` guards the same class with `_TRIPLE_QUOTE_RE` + `_exemption_opens_collection`
but `detect_overfit` case (b) does not. Spun off (see the hardening round's over-fit spin-off line).

### tautology
`flag` because this bug's SPEC.md carries no `## Intervention Hypothesis` block. Independent signal
(`signal_independence: independent`): the fix's regression tests
(`tests/test_lazy_core/test_docmodel.py` for `spec_fixed_annotation`,
`tests/test_lazy_core/test_gates.py` for `is_fixed_unreconciled`, plus the `bug-state.py --test`
Step-4 divert fixture) fail if the guard mis-classifies a fixed-unreconciled bug — a signal the
change neither emits nor suppresses. The guard's success metric (a `Concluded`+`**Fixed:**`+
no-receipt bug diverts to `BLOCKED` instead of dispatching `/plan-bug`) is observable independently
of the guard's own execution.

### gate_weakening
No gate-weakening hit (`gate_weakening_hit: false`). No `def test_*` deleted, no gate numeric
literal changed, no sanction/exemption set grown, no `*_BYPASS` env-var introduced, no
`permissionDecision: deny` / `refuse_*` / `exit 3` refusal removed. The change ADDS a fail-fast
router guard — it STRENGTHENS the pipeline (stops a burned `/plan-bug` cycle on already-done work).

### complexity
`retires: net-new` (frontmatter). The added surface — one `**Fixed:**`-line reader mirroring the
existing `spec_status`, one `is_fixed_unreconciled` predicate reusing the existing
`has_completion_receipt` seam, one `BLOCKED.md` formatter modeled on the existing
`format_unknown_dependency_blocker`, one bug-router Step-4 pre-gate, and a `tabulated-divergence`
routing-parity row — pays for itself by eliminating the burned `/plan-bug` re-plan of an
already-implemented out-of-pipeline fix (the recurring "fixed-unreconciled" cycle the `docs/bugs/`
OUT-OF-PIPELINE contract also addresses). Bounded and modeled on existing seams; no new engine.
