# Stale merged-view parity fixtures missing `--archive-fixed` predicate — Investigation Spec

> Two merged-view dispatch parity unit tests use stale hermetic "full" SKILL.md fixture text that omits the `--archive-fixed` predicate now required by `_MERGED_VIEW_PREDICATES`, turning `pytest user/scripts/ -q` red.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/adhoc-parity-merged-view-fixture-stale-archive-fixed
**Related:** `user/scripts/lazy_parity_audit.py` (`_MERGED_VIEW_PREDICATES`), `user/scripts/test_lazy_parity.py` (`TestMergedViewDispatchParity`); origin: `completion-coherence-gate-reconciliation` feature (its full-suite verification row was blocked behind a `| tail` pipe that masked this red test).

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED]** `test_passes_when_both_drivers_consistent` fails — its "full" fixture SKILL.md text satisfies only 5 of the 6 `_MERGED_VIEW_PREDICATES`, so `audit_merged_view_dispatch_parity` returns a finding for the missing `--archive-fixed` pattern against BOTH drivers, and the `== []` assertion fails. Confirmed by running `pytest user/scripts/test_lazy_parity.py -k test_passes_when_both_drivers_consistent` → `1 failed` with the error `missing bug archive --archive-fixed chain (pattern '--archive-fixed')`.
2. **[VERIFIED]** `pytest user/scripts/ -q` is red (`1 failed, 882 passed` per the ad-hoc brief; the single failure is symptom 1). Confirmed by running the targeted pair: `1 failed, 1 passed`.
3. **[VERIFIED]** `test_fires_when_no_regression_guard_absent` currently PASSES but carries the SAME stale "full" fixture (also omits `--archive-fixed`). Its assertion only checks that a `single-type` finding fires against the cloud driver, which it does regardless of the `--archive-fixed` gap — so the stale fixture is latent there, not failing. Confirmed: the targeted run reports this test as the `1 passed`.
4. **[VERIFIED]** The REAL SKILLs are correct — `user/skills/lazy-batch/SKILL.md` and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` both literally contain `--archive-fixed` (grep counts 1 and 2 respectively), so the real-repo whole-repo audit (`test_included_in_audit_all_pairs`) is clean. The defect is in the hermetic test fixtures ONLY, not in production prose.

## Reproduction Steps

1. From repo root, run `python -m pytest user/scripts/test_lazy_parity.py -q -k "test_passes_when_both_drivers_consistent"`.
2. Observe `1 failed`.
3. Observed result: `AssertionError` on `audit_merged_view_dispatch_parity(tmp_path) == []`; the findings list contains two `missing bug archive --archive-fixed chain (pattern '--archive-fixed')` entries (one per driver).

**Expected:** Both drivers' "full" fixtures satisfy all 6 `_MERGED_VIEW_PREDICATES`, so the consistent-fixture audit returns `[]` and the test passes; `pytest user/scripts/ -q` is fully green.
**Actual:** The "full" fixture omits the 6th predicate (`--archive-fixed`), so the audit returns findings and the test fails.
**Consistency:** Always (deterministic — pure-function audit over fixed fixture text).

## Evidence Collected

### Source Code

`user/scripts/lazy_parity_audit.py:360-377` — `_MERGED_VIEW_PREDICATES` is a 6-tuple. Predicate (f), added by the `lazy-batch-unified-driver-parity-and-accounting` Phase 3 work, requires the merged-view dispatch branch to name the `--archive-fixed` bug-archive follow-up in EACH driver:

```python
# (f) the bug __mark_fixed__ terminal chains the --archive-fixed follow-up …
(r"--archive-fixed", "bug archive --archive-fixed chain"),
```

`audit_merged_view_dispatch_parity` (`:380-414`) applies all 6 predicates to BOTH drivers in `_MERGED_VIEW_DRIVER_FILES` and emits one finding per `(driver, missing-predicate)`.

`user/scripts/test_lazy_parity.py` — the two stale "full" fixtures:
- `:812-818` (`test_passes_when_both_drivers_consistent`) — fixture names `--next-merged`, `__mark_complete__`, `bug-state.py`, `__mark_fixed__`, and "Single-type … byte-for-byte identical" but NEVER `--archive-fixed`. Both drivers write this same text, so both miss predicate (f) → 2 findings → `== []` fails.
- `:784-789` (`test_fires_when_no_regression_guard_absent`) — the `skills` (non-cloud) driver writes the same stale "full" text; the cloud driver deliberately drops the single-type phrase. The assertion targets only the single-type finding, so the latent `--archive-fixed` gap does not fail this test today.

A third fixture at `:756-761` (`test_fires_when_no_regression_guard_absent`'s sibling above it, in the `__mark_fixed__`-omission test) similarly lacks `--archive-fixed`, but its assertion checks a `__mark_fixed__` finding against the cloud driver, so it is also latent. The brief scopes the fix to the two named tests; the completeness consideration below covers whether to also touch this third one.

### Runtime Evidence

Targeted pytest run (this investigation):
```
FAILED test_lazy_parity.py::TestMergedViewDispatchParity::test_passes_when_both_drivers_consistent
1 failed, 1 passed, 27 deselected
```
Failure message: `"lazy-parity [merged-view] lazy-batch: missing bug archive --archive-fixed chain (pattern '--archive-fixed')"`.

### Git History

The `--archive-fixed` predicate was introduced by the `lazy-batch-unified-driver-parity-and-accounting` Phase 3 work (referenced in the predicate's own inline comment). The fixtures in `test_lazy_parity.py` predate that predicate addition and were never updated to the 6-predicate surface — a classic "added a predicate, missed the hermetic fixtures" gap. The red test was masked downstream behind a `| tail` pipe in the `completion-coherence-gate-reconciliation` full-suite verification row (the origin item that surfaced it).

### Related Documentation

- `user/scripts/CLAUDE.md` → Coupling Rule + the unified-driver `--next-merged` section: documents that the merged-view dispatch branch is a coupled-pair surface audited by `lazy_parity_audit.py`.
- The predicate comment block (`lazy_parity_audit.py:371-376`) explicitly cites `lazy-batch-unified-driver-parity-and-accounting Phase 3, item 2` as the source of predicate (f).

## Theories

### Theory 1: Stale hermetic fixtures, not a production drift
- **Hypothesis:** The `--archive-fixed` predicate (f) was added to `_MERGED_VIEW_PREDICATES` after the test fixtures were authored; the production SKILLs were updated to carry `--archive-fixed`, but the hermetic "full" fixture strings in the two tests were not, leaving them at 5/6 predicates.
- **Supporting evidence:** Real SKILLs contain `--archive-fixed` (grep 1 + 2); the whole-repo audit test (`test_included_in_audit_all_pairs`) is green; only the synthetic fixtures fail; the predicate comment dates (f) to a later feature phase than the fixture text style.
- **Contradicting evidence:** None found.
- **Status:** **Confirmed.**

## Proven Findings

- **Root cause (CONFIRMED):** The "full" / "consistent" hermetic SKILL.md fixture strings in `test_passes_when_both_drivers_consistent` (`test_lazy_parity.py:812-818`) and `test_fires_when_no_regression_guard_absent` (`:784-789`) satisfy only 5 of the 6 `_MERGED_VIEW_PREDICATES` — they omit the `--archive-fixed` bug-archive clause that predicate (f) now requires. Because `test_passes_when_both_drivers_consistent` asserts the audit returns `[]`, the missing predicate makes it fail. `test_fires_when_no_regression_guard_absent` does not fail today (its assertion is single-type-scoped) but carries the same stale text.
- **Fix scope (CONFIRMED):** Add an `--archive-fixed` bug-archive clause to the `full` fixture SKILL.md text in BOTH named tests so each "full"/"consistent" fixture satisfies all 6 predicates. No production SKILL.md, no `lazy_parity_audit.py` change, and no other test logic change is required. Verify `pytest user/scripts/ -q` is fully green afterward.
- **No production defect:** The audit, the predicate set, and both real SKILLs are correct. This is a test-fixture-only fix.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Merged-view parity test fixtures | `user/scripts/test_lazy_parity.py` (`test_passes_when_both_drivers_consistent` ~L812-818; `test_fires_when_no_regression_guard_absent` ~L784-789) | The "full"/"consistent" fixture strings omit `--archive-fixed`; one test fails, one is latently stale. FIX HERE. |
| Parity audit predicate set | `user/scripts/lazy_parity_audit.py` (`_MERGED_VIEW_PREDICATES`) | Correct as-is — 6 predicates including `--archive-fixed`. NO CHANGE. |
| Production drivers | `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | Already carry `--archive-fixed`. NO CHANGE. |

## Scope decision (D7 completeness)

⚖ policy: fix only-2 named or all-3 stale fixtures → fix all 3 in-cycle

The ad-hoc brief names two tests, but a third fixture (the `__mark_fixed__`-omission test at `test_lazy_parity.py:756-761`) carries the identical stale "full" text. All three are latently inconsistent with the 6-predicate surface; only one fails today, but a future predicate-scope change to any of the other two's assertions would re-expose the gap. Fixing all three "full" fixtures (adding the `--archive-fixed` clause uniformly) is the most-complete in-cycle path with no product-behavior divergence — the test intent (a "full"/consistent fixture should satisfy ALL current predicates) is identical across all three. This is a scope/completeness choice, not a product-class decision, so it is taken in-cycle and disclosed here for `/plan-bug` to carry into PHASES.md. (Decision is non-binding on the planner if it finds the third fixture's assertion genuinely depends on the omission — but inspection shows it does not.)

## Open Questions

- None. Root cause, fix scope, and verification command are all proven.
