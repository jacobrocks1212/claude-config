# `test_real_seeded_registry_lints_green` hardcodes the registry's KPI row count — Investigation Spec

> Discovered during unrelated work (not caused by it): `python3 -m pytest
> user/scripts/test_kpi_scorecard.py -q` fails with `assert 26 == 25` in
> `TestLintGreen::test_real_seeded_registry_lints_green`. `/harden-harness` invoked directly by the
> operator against this isolated, pre-existing defect.

**Status:** Concluded
**Priority:** P3
**Discovered:** 2026-07-20
**Related:** `docs/features/friction-kpi-registry/` (owns `kpi-scorecard.py` + the registry);
`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Round 41 (the SAME class recurring
— that round's fix bumped this identical literal 18→19 as a drive-by side effect of an unrelated
promotion, evidence the count needed hand-maintenance even then).

## Verified Symptom

```
$ python3 -m pytest user/scripts/test_kpi_scorecard.py -q
...
>       assert len(registry["kpis"]) == 25
E       AssertionError: assert 26 == 25
E        +  where 26 = len([...])
user/scripts/test_kpi_scorecard.py:155: AssertionError
1 failed, 144 passed in 6.08s
```

`docs/kpi/registry.json` (the real, committed registry) legitimately carries 26 KPI rows — every
shipped friction-reduction feature since `friction-kpi-registry` landed appends its own row(s) via
the sanctioned `--lint --spec` / `--promote-drafted-rows` gate path. The test's expected count is a
frozen literal (`25`) that must be hand-bumped, in lockstep with a growing explanatory comment
block (`user/scripts/test_kpi_scorecard.py:121-154`, ~34 lines) narrating every historical bump, on
every single legitimate registry addition.

## Root Cause

**Classification: `script-defect` (test-hygiene / brittle-assertion).** The assertion pins an
*incidental* fact (today's row count) rather than an *invariant* (the registry is well-formed and
non-empty). Nothing in `kpi-scorecard.py`'s write paths (`_cmd_capture_baseline`,
`promote_drafted_rows`, the `spec-friction-kpi-gate.md`-driven Step 8.5 exit-0 route) is required to
— nor should — keep a test literal in sync; the test author has to remember to hand-edit it every
time, and forgetting is the default (this is at least the SECOND time: Round 41 in
`hardening-log/2026-07.md` already bumped this exact literal 18→19 as an aside inside an unrelated
fix, confirming the class recurs rather than being a one-off oversight).

This is over-fit **by construction** (the harden-harness over-fit detector's signal 1 —
"literal-phrase-to-matcher": a literal count appended to fit the observed instance) — the
recommended structural fix is to stop asserting a specific N at all and instead assert what the
count assertion was actually meant to guard: that the registry's rows are well-formed (no duplicate
id — the one way a row count could silently regress without `lint_registry` itself catching it) and
non-empty. Both properties are DERIVED from the loaded registry, not re-hardcoded.

## Fix Scope (Concluded)

1. Replace `assert len(registry["kpis"]) == 25` with two internally-consistent checks derived from
   the loaded registry itself, never a frozen literal: `len(registry["kpis"]) > 0` (non-empty) and
   `len(kpi_ids) == len(set(kpi_ids))` (every row has a unique id — catches an accidental
   duplicate/mis-merge, the one integrity property a bare count was standing in for).
2. Delete the now-dead ~34-line comment block that only existed to narrate historical literal
   bumps — it carries no information once the literal is gone.
3. Leave the per-id `assert "<id>" in ids` / subset checks below untouched — those are legitimate
   named-row regression guards (they pin specific KPI ids added by specific features), not the
   brittle part; they continue to catch an accidental removal of a *specific* row.
4. No production code changes — `kpi-scorecard.py`'s lint/registry contract is unaffected; this is
   test-only.
