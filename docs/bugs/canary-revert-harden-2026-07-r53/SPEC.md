# Revert-or-redesign canary trip: harden-2026-07-r53 — Investigation Spec

> The `harden-2026-07-r53` canary tripped on a +333.8% band breach of `event:containment-refusal`, but the shipped change is not on that signal's serving path — a confounded, band-only false-positive. Triage disposition (revert / redesign / close-as-noise) is parked for the operator.

**Status:** Won't-fix
**Severity:** P2
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r53
**Related:** docs/interventions/harden-2026-07-r53.md · docs/features/harden-2026-07-r53/SPEC.md · docs/bugs/no-sanctioned-cli-for-queue-state-mutations/ · `harness-change-canary-rollback` · `intervention-efficacy-tracking`

<!-- Status lifecycle:
  - Investigating → active investigation; root cause of the SIGNAL MOVEMENT is traced, but the
    triage DISPOSITION (revert a shipped feature / redesign / close-as-noise) is a product-class
    fork parked for the operator via NEEDS_INPUT.md. Left Investigating per the /spec-bug --batch
    contract: a NEEDS_INPUT round does not conclude.
  - Concluded → set only after the operator resolves the disposition (re-run /spec-bug consumes it).
-->

---

## Verified Symptoms

1. **[VERIFIED]** The `harden-2026-07-r53` canary reached `status: tripped` on 2026-07-18 — recorded in `docs/interventions/harden-2026-07-r53.md` (`canary.status: tripped`, `canary_revert_enqueued: '2026-07-18'`) and in this dir's `EVIDENCE.md`. Confirmed by direct read of both files.
2. **[VERIFIED]** The trip cause was a targeted-signal band breach: `event:containment-refusal` regressed **+333.8%** vs the frozen baseline 72.9 ev/run (band ±25%), 1265 post-ship occurrences over 4 window runs (baseline 72.9 → post 316.25 ev/run). Verbatim from `EVIDENCE.md`.
3. **[VERIFIED]** The trip was **band-only with zero attributed fresh incidents** — `EVIDENCE.md` "Attributed fresh incidents (verbatim)" reads `(none — band-only trip)`. No incident was attributed to r53's surfaces (`bug-state.py`, `lazy-state.py`, `lazy_core/__init__.py`, `lazy_core/depdag.py`, `lazy-batch/SKILL.md`).

## Reproduction Steps

1. Read the intervention record: `docs/interventions/harden-2026-07-r53.md` — note `target_signal: event:containment-refusal`, `expected_direction: decrease`, `baseline.value: 72.9`, `band_pct: 20`, `canary.status: tripped`.
2. Read `docs/bugs/canary-revert-harden-2026-07-r53/EVIDENCE.md` — note the +333.8% relative movement and `(none — band-only trip)` attribution.
3. Confirm the sole emitter surface: `grep -rn 'append_telemetry_event(' user/scripts/lazy_core/markers.py | grep -n containment` (or read markers.py:2470/2537/2657/2683) — all `containment-refusal` emissions live in `refuse_if_cycle_active`, `refuse_cycle_marker_mutation_if_subagent`, `refuse_run_start_clobber`.
4. Confirm the revert target does NOT touch that surface: `git show --name-only 8a7bc738c9dfae0ec6079d5930086de54a558ca6 | grep markers.py` → no match.
5. Confirm co-shipped same-signal confounders: `grep -l 'event:containment-refusal' docs/interventions/*.md` and inspect ship dates — r48 (07-16), r72/r75/r89 (07-17) share the target signal inside r53's post-ship window.

**Expected:** A canary trip attributed to r53 should reflect a signal r53's commit set can actually move, with fresh incidents on r53's surfaces.
**Actual:** A band-only aggregate breach on a signal whose sole emitter (markers.py) r53 never touched, inside a window saturated with same-signal hardening rounds, with zero surface-attributed incidents.
**Consistency:** Deterministic given the frozen record + ledger (the trip is already stamped).

## Evidence Collected

### Source Code

- **Sole emitters of `event:containment-refusal`** (`grep`-verified, `user/scripts/lazy_core/markers.py`):
  - `refuse_if_cycle_active` → markers.py:2470-2474 (`data={"op": ..., "guard": "refuse_if_cycle_active"}`)
  - `refuse_cycle_marker_mutation_if_subagent` → markers.py:2537-2541
  - `refuse_run_start_clobber` → markers.py:2657-2661 and 2683-2687 (concurrent-walker `--run-start` refusal)
  These fire **per guard-hit** during pipeline activity — routing/lifecycle attempts by cycle subagents and run-start clobbers. The signal is a pipeline-activity-VOLUME aggregate, dominated by how many cycles/run-starts occurred, not by any single shipped change.
- **Revert target 8a7bc738 changed set** (`git show --stat`): `docs/cli/cli-surface.json`, `user/scripts/bug-state.py`, `user/scripts/cli_surface.py`, `user/scripts/lazy-state.py`, `user/scripts/lazy_core/__init__.py`, `user/scripts/lazy_core/depdag.py`, `user/scripts/tests/test_lazy_core/test_depdag.py`, `user/skills/lazy-batch/SKILL.md`. **`markers.py` is NOT present.** The emitter is untouched.
- The new `depdag.py` ops (`set_queue_priority`, `mutate_queue_deps`, `reposition_by_priority`) and their CLI flags (`--set-tier`/`--set-severity`/`--add-deps`/`--remove-deps`/`--unpin`) each call `refuse_if_cycle_active` FIRST and require `--operator-authorized` (per commit message). They are operator-directed ops that a normal cycle subagent never invokes, so they add no emit that fires during ordinary runs.

### Runtime Evidence

- `EVIDENCE.md`: relative movement 333.8% (band ±25%); post-ship occurrences 1265; baseline 72.9 → post 316.25 ev/run; attributed fresh incidents `(none — band-only trip)`.
- Frozen record baseline window: 2026-07-09T17:17:53Z → 2026-07-17T03:21:52Z (20 runs, 1458 events). Post-ship window: the 4 window runs after ship on 2026-07-16.

### Git History

- r53 shipped 2026-07-16 (`shipped_commit: 8a7bc738…`). Its post-ship window (2026-07-16 → 2026-07-18) overlaps a dense burst of hardening rounds. **Same-signal (`event:containment-refusal`) co-shipments in-window:** r48 (07-16), r72 (07-17), r75 (07-17), r89 (07-17) — plus dozens of `event:halt` / `event:gate-refusal` rounds driving high overall pipeline activity. This is precisely the same-signal confounding population `efficacy-eval.py::_same_signal` caps at `INCONCLUSIVE (confounded)`.

### Related Documentation

- `docs/interventions/CLAUDE.md` — canary lifecycle (open → tripped → closed), the D2 tripwire (targeted-signal regression past band else ≥25% relative with ≥3 occurrences), D3 surface attribution, D4 flag-and-enqueue-only (nothing reverted automatically), and the `canary-trip-precision` KPI (fraction of trips NOT closed-as-noise) — which explicitly makes **close-as-noise a first-class, tracked outcome**.
- `docs/bugs/CLAUDE.md` — this item flows through spec → plan → normal triage under full gates; nothing was reverted automatically.

## Theories

### Theory 1: r53 caused the containment-refusal spike (REVERT warranted)
- **Hypothesis:** the shipped change increased containment refusals, so a revert of the commit set (covering the coupled pair) restores the baseline.
- **Supporting evidence:** the canary attributes the window to r53's surfaces; the change did add new `refuse_if_cycle_active` call sites.
- **Contradicting evidence:** the sole emitter (`markers.py`) is untouched by 8a7bc738; the new call sites are operator-authorized and never invoked in a normal cycle; the trip was band-only with ZERO fresh incidents attributed to r53's surfaces; a +333.8% (≈4×) aggregate swing over 4 runs is inconsistent with a handful of never-invoked operator ops.
- **Status:** Ruled Out.

### Theory 2: The trip is a confounded, band-only aggregate false-positive (CLOSE-AS-NOISE)
- **Hypothesis:** the +333.8% rise reflects window-level pipeline activity volume (many co-shipped hardening cycles firing the routing/run-start guards), not r53's change.
- **Supporting evidence:** emitter untouched; new ops non-firing in normal cycles; zero surface-attributed incidents; window saturated with same-signal (r48/r72/r75/r89) and other high-activity hardening rounds; containment-refusal is a per-guard-hit volume aggregate.
- **Contradicting evidence:** none found.
- **Status:** Confirmed (traced).

### Theory 3: The intervention hypothesis was mis-specified (REDESIGN the record, not the feature)
- **Hypothesis:** r53 declared `target_signal: event:containment-refusal` / `expected_direction: decrease`, but hand-editing `queue.json` (the friction r53 removes) does not emit `containment-refusal` at all — that event is emitted by routing/run-start guards, not by queue-edit denies. The change can neither decrease nor (in normal cycles) increase this signal; the hypothesis and its `signal_independence` justification conflate queue-edit friction with a different telemetry event.
- **Supporting evidence:** the markers.py emitter set (routing/lifecycle/run-start guards only) vs. r53's queue-mutation scope; the "decrease" direction is architecturally unreachable by this change.
- **Contradicting evidence:** none — this is a corollary of the traced emitter analysis.
- **Status:** Confirmed (traced). Implies the canary/hypothesis pairing for r53 was mis-declared, a canary-tuning input regardless of the disposition chosen.

## Proven Findings

**Causal finding (label: `traced`).** The observed symptom (the +333.8% `event:containment-refusal` band breach) is **not produced by commit 8a7bc738**. Serving-path trace:

```
event:containment-refusal (telemetry ledger event)
  → append_telemetry_event("containment-refusal", …)   user/scripts/lazy_core/markers.py:2470, 2537, 2657, 2683
  → emitted by refuse_if_cycle_active / refuse_cycle_marker_mutation_if_subagent / refuse_run_start_clobber
       (fires per routing/lifecycle/run-start guard-hit during pipeline activity)
  ← revert target 8a7bc738 touches NONE of these  (git show --name-only 8a7bc738 ∌ markers.py)
```

The fix-site-on-path rule fails for a revert: the commit set is not read on the symptom's serving path. The +333.8% aggregate is explained by window-level activity volume + same-signal co-shipments (r48/r72/r75/r89), the exact confounding population the efficacy evaluator caps as `INCONCLUSIVE (confounded)`. **Evidence-supported disposition: close-as-noise** (do not revert; do not redesign the shipped `no-sanctioned-cli-for-queue-state-mutations` feature), with a secondary canary-tuning signal (Theory 3: the r53 target-signal/direction was mis-declared).

**Why the disposition is nonetheless parked (not auto-concluded):** "revert" and "redesign" diverge in user-visible product behavior — a revert removes the sanctioned queue-mutation CLI across a parity-guarded coupled pair (`lazy-batch` / `lazy-bug-batch` / `lazy-batch-cloud`) and requires a green `lazy_parity_audit.py`. That is a structural, product-class fork the operator owns (they may prefer to remove an unmeasurable feature even given the noise finding). Under park-mode + stub-origin baseline, it is surfaced via `NEEDS_INPUT.md` with a close-as-noise recommendation rather than routed to `/plan-bug`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Canary tripwire / attribution | `user/scripts/efficacy-eval.py` (`--canary`), `docs/interventions/harden-2026-07-r53.md` | Band-only aggregate trip with no surface attribution fired on a signal the change can't move — a canary trip-precision (false-positive) input. |
| Intervention hypothesis record | `docs/interventions/harden-2026-07-r53.md` | `target_signal`/`expected_direction` mis-declared for the change's actual scope (script-owned; corrected only via `efficacy-eval.py --rebaseline`/evaluator, never hand-edited). |
| Shipped feature under revert consideration | `user/scripts/lazy_core/depdag.py`, `bug-state.py`, `lazy-state.py`, `cli_surface.py`, `user/skills/lazy-batch/SKILL.md` (+ pair `lazy-bug-batch`, `lazy-batch-cloud`) | The revert target; evidence says leave it in place. |

## Open Questions

- Operator disposition: close-as-noise (recommended) vs. revert vs. redesign — surfaced in `NEEDS_INPUT.md`.
- Follow-up (independent of the disposition): should the r53 intervention record be re-based / re-declared (Theory 3) via `efficacy-eval.py --rebaseline`, and should the canary band for volume-aggregate `event:*` signals be tuned to suppress band-only, zero-attribution trips? These are canary-tuning items, not part of this bug's fix scope; noted here for the operator.

## Resolution

Operator-accepted the recommended **close-as-noise** disposition (`NEEDS_INPUT.md`, recorded via
`bug-state.py --record-decision`). The shipped queue-mutation CLI (`8a7bc738`) is retained,
not reverted — its sole emitter path (`markers.py`) is untouched, so the change is provably not
on the regressed signal's serving path; band-only trip, zero surface-attributed incidents.
Canary/record re-baseline tuning is tracked separately, not as a phase of this bug. Closed
without a fix.
