---
kind: gate-verdict
feature_id: adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move
gate_version: 1
date: 2026-07-19
scope_hit: [user/scripts/harness-gate.py]
checks:
  overfit: flag-justified
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: the per-file-only net computation inside detect_gate_weakening that was structurally blind to a construct moved across files within the same change
override: absent
---

## Adversarial answers

### overfit

`harness-gate.py --range beef5fea~1..beef5fea` flags one literal element appended to a
membership construct in `user/scripts/harness-gate.py` itself: a `"""` triple-quote literal that
is part of the checker's own diff-hunk-body parser (the structural change adds a
`_cross_file_reconciled_net` helper that reads removed/added gate-refusal construct *bodies*
across the whole file set, not one file's slice — the multi-line hunk-body extraction needed a
`"""`-delimited construct in the checker's own source, not an incident-shaped literal).

This is NOT an incident literal (no `docs/{features,bugs}/<slug>` id, no date, no session id
appended to a matcher alternation/allow-list) — it is a structural element of the detector's own
parser, on the manifest's `gate_own` block precedent (the checker's own files are expected to
contain matcher-shaped source). **Nearest recurrence this specific flag does NOT catch:** a
future change that reshapes the cross-file reconciliation to key on a DIFFERENT literal quoting
style (e.g. single-quoted or f-string hunk-body extraction) would trip the same overfit detector
again on a *different* literal — the detector's own overfit rule is diff-SHAPE-keyed
(matcher-literal-append), not incident-keyed, so it correctly re-flags any future literal
addition to `harness-gate.py`'s own membership constructs regardless of shape. The structural
property this flag genuinely keys on is "a literal was appended to a matcher/membership
construct in the diff" — true here, and honestly not reducible further: the detector is doing its
job on the checker's own source, and the justification is that the flagged literal is
PARSER-INTERNAL STRUCTURE (part of `harness-gate.py`'s own construct-detection machinery), not a
scan target keyed on the observed incident (the `shared-hook-lib` `permissionDecision` migration).
Verdict: `flag-justified`.

### tautology

**If this change were BROKEN (over-reconciled — e.g. it accidentally net-zeroed a genuine,
unrelated removal because two unrelated deny constructs happen to share identical body text
across files):** the success metric would look like genuine `gate_weakening` hits silently
ceasing to fire — a DROP in true-positive `hit` results on the existing true-positive fixtures
(`test_gate_weakening_removed_refuse_construct_still_hits`,
`..._genuine_test_removal_still_hits`, both re-run green post-fix) and, in the field, a real
weakening slipping through with no operator sign-off. This is distinguishable in principle from
the intended effect (a false-positive `hit` no longer firing on the cross-file-MOVE shape
specifically) — the two failure directions are opposite and separately observable.

**Independent signal:** the rate of `GATE_VERDICT.md` `overfit`/`gate_weakening` flags later
overridden by the operator as false-positives specifically on cross-file construct moves — an
observable recorded in the GATE_VERDICT/override ledger across FUTURE changes, not emitted or
suppressed by this change itself. Declared in `SPEC.md`'s `## Intervention Hypothesis` block
(`signal_independence: independent`); `harness-gate.py --feature-dir` now reads that block and
reports `tautology: pass`.

### gate_weakening

**Result: pass (`gate_weakening_hit: false`).** This fix REMOVES a false positive in the
detector — it does not delete a `def test_*`, does not change a numeric literal on a gate line,
does not grow a sanction/exemption/allow-list, does not introduce a `*_BYPASS` env-var, and does
not remove a `permissionDecision: deny` / `refuse_*` / `exit 3` branch. The true-positive shape
(a construct removed with NO matching content-identity add anywhere in the diff) still hits —
confirmed by the two true-positive regression fixtures named above staying green. No weakening,
no operator sign-off needed, no `override` recorded.

### complexity

**Retires:** the per-file-only net computation inside `detect_gate_weakening` (`removed_deny[f] -
added_deny.get(f, 0)`, same shape for the `def test_*` tally) — this WAS the false-positive
source; it stops being the sole reconciliation denominator. **Net-new:**
`_cross_file_reconciled_net`, a whole-change content-identity reconciliation helper. It pays for
itself: it eliminates the cross-file-move false positive (the live `shared-hook-lib` incident,
`GATE_VERDICT.md` at commit `1d33c956`) while the same fixtures prove true-positive detection is
preserved — the added surface directly retires the defect class this bug documents, not a
speculative generalization.
