# Merged-head oracle: model operator-defer in feature compute_state to retire per-signal file-predicate supplements — Investigation Spec

> The merged-head actionability oracle re-adds a per-signal `DEFERRED.md` file-predicate every recurrence (R56/R57/R101/R102) because the FEATURE `compute_state` has no operator-defer branch, so the oracle's `is_dispatchable` re-inference is structurally blind to operator-deferred features. Model operator-defer directly in the feature `compute_state` so the premise holds universally and the supplement retires.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-19
**Placement:** docs/bugs/merged-head-oracle-per-signal-supplement-churn
**Related:** `docs/bugs/_archive/merged-head-oracle-blind-to-operator-deferred-cross-pipeline-feature/` (R102, fix `a1f98e4d` — the immediate origin that HANDED BACK this durable generalization; re-applied the file-predicate at the oracle site); `docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks/` (R57, `c5a3b385` — the ORIGINAL file-predicate); `docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run/` (R56 — park progenitor); `docs/bugs/_archive/merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head/` (R101, `1b7d420f`); `docs/features/unified-pipeline-orchestrator/` (merged-view / type-dispatch contract)

<!-- Status lifecycle: Investigating → active; Concluded → root cause traced, ready for /plan-bug. -->

---

## Verified Symptoms

<!-- This is a preventive-generalization bug handed back by R102, not a live deadlock (R102 already
     fixed the deadlock via the supplement). "Symptoms" are the structural blindness + its recurring-
     churn cost + the still-live near-neighbor. Verified against source, not a user round (batch mode). -->

1. **[REPORTED]** Recurring per-signal churn — the merged-head oracle has re-added an operator-defer file-predicate supplement across FOUR harden rounds (R56/R57/R101/R102) because each refactor re-loses coverage of operator-deferred features. Source: `ADHOC_BRIEF.md` + the R102 origin commit `a1f98e4d` message ("re-apply the pure `spec_dir_operator_deferred` file-predicate at the ONE oracle landing site").
2. **[VERIFIED-in-source]** The FEATURE `compute_state` (`user/scripts/lazy-state.py`) has NO bare-`DEFERRED.md` (operator-excluded) branch. Confirmed by grep: the only `DEFERRED.md`-family branches on the feature side are `DEFERRED_NON_CLOUD.md` (cloud) / `DEFERRED_REQUIRES_DEVICE.md` (device) / `DEFERRED_REQUIRES_HOST.md` (host); `lazy-state.py:407` is a COMMENT explicitly documenting the absent operator-defer branch as a "JUSTIFIED divergence", with no code branch.
3. **[VERIFIED-in-source]** Near-neighbor — the feature pipeline would dispatch `/spec` on an operator-EXCLUDED feature. Because the feature `compute_state` walk loop never checks bare `DEFERRED.md`, a `Draft(stub)` feature dir carrying only a `DEFERRED.md` (`reason: operator-excluded`) falls through to the Step-4 `/spec` route instead of being skipped. (This is what made the R102 cross-pipeline oracle blind in the first place: a cross-pipeline feature scope-probes as DISPATCHABLE.)

## Reproduction Steps

**A — near-neighbor (feature pipeline dispatches /spec on an operator-excluded feature):**
1. In a feature queue (or autodiscover-on repo), create `docs/features/<slug>/SPEC.md` with `**Status:** Draft` and drop `docs/features/<slug>/DEFERRED.md` (`kind: deferred`, `reason: operator-excluded`).
2. Run `python3 user/scripts/lazy-state.py --repo-root . --feature-id <slug>` (scoped probe).
3. **Observed:** the probe routes `sub_skill: /spec` (Step 4) — the operator's DEFERRED.md is ignored.

**B — oracle blindness (the primary defect the supplement papers over):**
1. Place an operator-deferred FEATURE (`DEFERRED.md`) at the cross-pipeline MERGED head above a genuinely-dispatchable bug.
2. Probe the bug pipeline's `--emit-prompt`; observe that WITHOUT the `_candidate_operator_deferred` file-predicate at `dispatch.py:822`, `is_dispatchable(scoped_probe(feature))` returns `true` (the scoped FEATURE `compute_state` ignores `DEFERRED.md`), so the feature stays the merged head and the `merged-head-diverged` withhold suppresses `cycle_prompt_ref`.

**Expected:** an operator-deferred feature is non-dispatchable at its OWN pipeline's `compute_state` (like a bug), so the oracle's primary `is_dispatchable` re-inference excludes it without a separate file-predicate.
**Actual:** the feature `compute_state` reports it dispatchable; only the oracle-site file-predicate supplement excludes it.
**Consistency:** always (pure static state-machine logic; not runtime-coupled).

## Evidence Collected

### Source Code

**The oracle (surface — where the supplement lives):**
`user/scripts/lazy_core/dispatch.py::merged_head_nondispatchable_ids`:
- `770–774` — `_candidate_operator_deferred(iid)` helper wrapping the pure file-predicate `spec_dir_operator_deferred`.
- `816–834` — the walk loop: `822` applies `_candidate_operator_deferred(iid)` (the SUPPLEMENT) BEFORE `830` `is_dispatchable(scoped_probe(iid))` (the PRIMARY mechanism). The supplement is the churn-prone patch; the primary mechanism is the durable oracle.

**The primary mechanism (intermediate hop):**
`is_dispatchable(scoped_probe(iid))` (`dispatch.py:830`) — for a FEATURE candidate, `scoped_probe` re-runs the FEATURE `compute_state` (`lazy-state.py`).

**The source (the fix site):**
`user/scripts/lazy-state.py::compute_state` walk loop — no bare-`DEFERRED.md` branch (Verified Symptom 2). Contrast the bug-pipeline model to mirror: `user/scripts/bug-state.py:1126–1160` (the operator-deferred skip: `deferred_md = spec_dir / "DEFERRED.md"; if deferred_md.exists(): ... _OPERATOR_DEFERRED.append(...); continue`, plus the scoped-identity `TR_OPERATOR_DEFERRED_SCOPED` terminal at `1138–1150`).

**The false-premise the file-predicate docstring already documents:**
`user/scripts/lazy_core/docmodel.py::spec_dir_operator_deferred` (`2299–2334`) — its docstring notes the FEATURE `compute_state` "ignores it, so the merged-head oracle's file-predicate is the ONLY thing that excludes such a feature — do NOT re-assume 'a feature spec dir never carries the file'." That "ONLY thing" is exactly what this bug retires by making the FEATURE `compute_state` model operator-defer.

### Git History

- `a1f98e4d` (R102) — re-applied the file-predicate at the oracle site; commit body explicitly hands back the durable generalization ("model operator-defer … directly in the feature compute_state so the oracle's is_dispatchable premise holds universally and the per-signal file-predicate supplement can retire").
- `c5a3b385` (R57) — the ORIGINAL file-predicate (`spec_dir_operator_deferred` into `nondispatchable_item_ids`).
- `d831983c` — enqueued this spin-off.

### Related Documentation

- `docs/bugs/CLAUDE.md` — bug-doc lifecycle + the operator-defer parity divergence context.
- `user/scripts/CLAUDE.md` — the coupling rule (a feature `compute_state` change must be parity-checked against `bug-state.py`), the `--test` smoke-harness contract, and `lazy_parity_audit.py`.
- Root `CLAUDE.md` Scripts table — `lazy_core.dispatch` (oracle) + the merged-head bug lineage.

## Theories

### Theory 1: Feature compute_state's missing operator-defer branch forces the oracle to carry a redundant file-predicate
- **Hypothesis:** Because the FEATURE `compute_state` never skips a bare-`DEFERRED.md` dir, the oracle's `is_dispatchable(scoped_probe(feature))` reports an operator-deferred feature as dispatchable, so every refactor that trusts `is_dispatchable` as the sole mechanism re-loses operator-defer coverage and a supplement must be re-added.
- **Supporting evidence:** Verified Symptoms 2 + 3; the docmodel docstring naming the file-predicate the "ONLY" exclusion; the four-round recurrence (R56/R57/R101/R102).
- **Contradicting evidence:** None found. The bug pipeline (which HAS the branch) does not need a separate supplement for its OWN candidates — its `is_dispatchable` already surfaces `terminal_reason: operator-deferred`.
- **Status:** Confirmed.

## Proven Findings

**Root cause (`script-defect`, cause label: `traced`).** The FEATURE `compute_state` (`lazy-state.py`) models no operator-defer branch, so the merged-head oracle's PRIMARY exclusion mechanism (`is_dispatchable(scoped_probe(feature))`, `dispatch.py:830`) is structurally blind to operator-deferred features and must be supplemented by a file-predicate (`_candidate_operator_deferred`, `dispatch.py:822`) that every refactor re-loses.

**Serving-path trace (surface → source; each hop `file:line`):**
```
merged-head oracle excludes operator-deferred features ONLY via the supplement
  → _candidate_operator_deferred(iid)                 user/scripts/lazy_core/dispatch.py:822  (the churn-prone patch)
  → the PRIMARY mechanism it backstops: is_dispatchable(scoped_probe(iid))
                                                        user/scripts/lazy_core/dispatch.py:830
  → scoped_probe(FEATURE candidate) re-runs the FEATURE compute_state
                                                        user/scripts/lazy-state.py::compute_state
  → FEATURE compute_state walk loop has NO bare-DEFERRED.md branch  ← the value/code the fix changes
                                                        user/scripts/lazy-state.py (absent; comment at :407)
```
**Fix-site-on-path:** the fix ADDS the operator-defer branch to the FEATURE `compute_state` walk loop — the exact node the trace terminates on and the node `scoped_probe` reads. Once present, `is_dispatchable(scoped_probe(feature))` returns false for an operator-deferred feature (surfacing an operator-deferred terminal like the bug pipeline), so the oracle's primary mechanism excludes it and the `dispatch.py:822` supplement becomes redundant and retires. Not runtime-coupled — pure static state-machine logic, verifiable by source read.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Feature state machine | `user/scripts/lazy-state.py::compute_state` (walk loop) | ADD a bare-`DEFERRED.md` operator-defer skip branch mirroring `bug-state.py:1126–1160` (skip + `_OPERATOR_DEFERRED` accumulator + scoped-identity terminal + probe key + notify message). Fixes the near-neighbor (`/spec` on an operator-excluded feature) directly. |
| Merged-head oracle | `user/scripts/lazy_core/dispatch.py:770–774, 822, 828` | RETIRE the `_candidate_operator_deferred` file-predicate supplement (and its `_op_defer_dir` map plumbing, `dispatch.py:~750–768`) ONCE the feature branch lands — the primary `is_dispatchable` re-inference now covers both pipelines. Retire-vs-keep-as-defense-in-depth is a fix-planning decision (see Open Questions). |
| Docstrings | `user/scripts/lazy_core/docmodel.py:2299–2334` (`spec_dir_operator_deferred`), `depdag.py:1443`, `depdag.py` merged-worklist | Update the "ONLY thing that excludes such a feature" / false-premise docstrings the R102 fix corrected, to reflect that the feature `compute_state` now models operator-defer. |
| Parity + tests | `bug-state.py` (parity reference), `lazy_parity_audit.py`, in-file `--test` harnesses, `tests/baselines/lazy-state-test-baseline.txt`, `tests/test_lazy_core/test_dispatch.py` | Feature-side operator-defer is a NEW feature-pipeline branch; confirm it is a justified divergence or a mirrored surface per `audit_state_script_parity`. Add a feature-side regression (operator-deferred feature → non-dispatchable / skipped) and a control (DEFERRED.md removed → dispatchable). Keep the R102 oracle regression green through the supplement retirement (the primary mechanism must now carry it). |

## Open Questions

- **Retire vs. keep-as-defense-in-depth the `dispatch.py:822` supplement.** End-state PRODUCT behavior is IDENTICAL either way (operator-deferred features excluded from the merged head + never `/spec`-dispatched), so this is a scope-class fix-planning decision, NOT a product fork. The bug's stated intent is to RETIRE the supplement (eliminate the churn); a conservative alternative keeps it as belt-and-suspenders. Recommendation for `/plan-bug`: retire it (that IS the durable generalization), but gate the retirement on the R102 oracle regression staying green with the primary `is_dispatchable` mechanism alone. Defer the final call to fix planning.
- **Scoped-identity terminal shape on the feature side.** `bug-state.py` returns a scoped `TR_OPERATOR_DEFERRED_SCOPED` identity for a `--feature-id`-targeted deferred item. Confirm the feature pipeline needs the same scoped-identity treatment (vs. a bare `continue` into a global deferred terminal) — likely yes for `--feature-id` probe symmetry; fix planning to mirror `bug-state.py:1138–1150`.
