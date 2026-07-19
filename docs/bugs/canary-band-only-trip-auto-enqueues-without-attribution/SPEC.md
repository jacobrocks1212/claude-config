# Canary Band-Only Trip Auto-Enqueues Without Attribution — Investigation Spec

> `efficacy-eval.py --canary` auto-enqueues a `canary-revert-<id>` bug stub on an aggregate band swing of a high-volume SELF-EMITTED signal (e.g. `event:containment-refusal`) with ZERO surface attribution and no confound guard — generating ~11 noise stubs in one cycle. Surfacing a trip for triage is by-design (D4, never silent-revert); the DEFECT is the trip sensitivity / missing confound guard BEFORE the auto-enqueue.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-band-only-trip-auto-enqueues-without-attribution
**Related:** `user/scripts/efficacy-eval.py` (`_canary_evaluate_record` / `_canary_band_trip` / `_canary_attribute` / `run_canary`) · `user/scripts/test_efficacy_eval.py` · `docs/bugs/park-provisional-parks-claude-config-auto-generated-stubs` (batched sibling — mitigates the operator-toil symptom this defect produces)

---

## Verified Symptoms

<!-- Batch-mode: REPORTED from the first-hand harden dispatch brief (operator observed the canary
     state), plus static trace of the trip predicate. -->

1. **[REPORTED]** `efficacy-eval.py --canary` showed **20 open canaries, 728 unattributed / 0 attributed, none matured**. Every investigated canary-revert stub self-diagnosed: "band-only, confounded (noise) trip; the shipped change can only REDUCE the regressed signal on its own path; no fresh incident attributed to its surface; recommend close-as-noise + tune the D2 band for high-volume self-emitted signals." Source: harden dispatch brief.
2. **[REPORTED]** The canary auto-enqueued ~**11 noise revert-triage stubs** in one cycle on aggregate band swings of high-volume self-emitted signals with no attribution/confound guard. Source: harden dispatch brief.
3. **[VERIFIED — static]** `_canary_evaluate_record` computes `trip = bool(band.get("trip")) or incident_trip` (L1023) and `run_canary` fires the enqueue consequence on ANY `ev["trip"]` (L1124–1127) — a band-only trip with zero attributed incidents enqueues a revert stub unconditionally.

## Reproduction Steps

1. Ship a control-surface change whose canary declares a high-volume SELF-EMITTED target signal (e.g. `event:containment-refusal`) with `expected_direction: decrease`.
2. Let the aggregate rate of that signal swing ≥ the band (±25%) with ≥3 post-ship occurrences in the window — driven by unrelated aggregate volume, NOT by the changed surface (no fresh incident attributes to the change's own surface).
3. Run `efficacy-eval.py --canary`.

**Expected:** A band-only trip with zero surface attribution on a non-independent (self-emitted) signal is SURFACED for triage (D4) but does NOT auto-enqueue a revert-triage bug stub — the change can only reduce the regressed signal on its own path, so an unattributed aggregate swing is a confounded (noise) trip.
**Actual:** The trip fires the enqueue consequence unconditionally; a `canary-revert-<id>` stub is created for machine triage noise.
**Consistency:** Deterministic — any qualifying aggregate band swing trips and enqueues regardless of attribution or signal independence.

## Evidence Collected

### Source Code
- `user/scripts/efficacy-eval.py` `_canary_band_trip` L605–660: the band trip is a pure aggregate-rate comparison vs the frozen baseline (`rel >= band` and `post_events >= CANARY_MIN_POST_OCCURRENCES`). No attribution or signal-independence input.
- `_canary_attribute` L750–769: computes `(attributed, unattributed)` by surface match — the confound signal EXISTS but is only consumed by `incident_trip` (≥`CANARY_INCIDENT_TRIP_COUNT`=2), never gates the BAND trip.
- `_canary_evaluate_record` L1022–1023: `incident_trip = len(attributed) >= 2`; `trip = bool(band.get("trip")) or incident_trip` — the band trip stands alone with no attribution corroboration.
- `run_canary` L1124–1139: `if ev["trip"]:` → `_canary_fire_consequence` (enqueue) unconditionally, else close/monitor.
- Records carry `signal_independence` (independent | self-emitted | mixed) — captured at `--record-intervention` — which is available on `meta` but unused by the trip decision.

### Related Documentation
- The canary D4 contract: "never silent-revert" — a trip flags-and-enqueues, nothing is reverted automatically. Preserving surfacing is required; only the auto-ENQUEUE of the revert-triage stub is the noise.

## Proven Findings

**Root cause (traced):** the band-trip detector is an aggregate-rate comparison with no confound guard. For a SELF-EMITTED signal (the changed surface emits the signal), the shipped change can only REDUCE the signal on its OWN path; an aggregate band swing with zero incidents attributed to that surface is definitionally NOT caused by the change (confounded by unrelated volume). The trip decision consumes attribution only for the separate `incident_trip`, so a band-only trip auto-enqueues without any attribution/independence corroboration.

**Serving-path trace:**
```
symptom: band-only aggregate swing auto-enqueues a canary-revert noise stub
  → run_canary fires consequence on any ev["trip"]      user/scripts/efficacy-eval.py:1124-1127
  → ev["trip"] = band.trip OR incident_trip             user/scripts/efficacy-eval.py:1023
  → band.trip = aggregate rate vs frozen baseline, NO attribution / independence input
                                                         user/scripts/efficacy-eval.py:605-660
  → attribution IS computed but only feeds incident_trip (>=2), never the band trip
                                                         user/scripts/efficacy-eval.py:750-769,1022
```
Fix-site-on-path: an enqueue-gate predicate inserted between trip detection and the consequence (in `_canary_evaluate_record` / `run_canary`) that consumes the ALREADY-COMPUTED `attributed` list + the record's `signal_independence` — this node is on the traced path (it gates the read that produces the enqueue). `traced`.

## Fix Scope

Separate **trip DETECTION** (keep surfacing — D4) from **auto-ENQUEUE** (the noisy action). Add a confound guard consumed only when a trip is detected:

- An **incident trip** (≥2 attributed fresh incidents) → always enqueues (real surface attribution).
- A **band-only trip**:
  - `signal_independence` starts with `independent` → enqueues (an independent signal's band swing is meaningful on its own — not self-emitted by the changed surface).
  - else (`self-emitted` / `mixed` / undeclared) → enqueues ONLY when ≥1 fresh incident attributes to the change's own surface. **Zero attribution ⇒ SUPPRESS the enqueue**, surface the trip in a `suppressed[]` payload bucket + diagnostic (D4 preserved — nothing reverted, the trip is still visible for triage), and leave the record OPEN (re-surfaces until attribution appears or the operator acts; never closed-clean, never auto-enqueued).

**Design choice (surfaced, not provisionalized — operator directed the fix and offered the options):** the task offered "add an attribution/confound guard OR tune the D2 band for high-volume self-emitted signals." Chose the **attribution/independence confound guard** over band-tuning: it is structural (keys on whether the shipped change could plausibly have caused the swing) rather than a magic-number band widening that would still fire on a large enough unattributed swing. Band-tuning remains an orthogonal future option if desired.

**Anti-overfit note:** the guard keys on the STRUCTURAL signals (attribution + declared independence), never on a specific signal id (`event:containment-refusal`) or id prefix (`canary-revert-*`). `efficacy-eval.py` is not on `docs/gate/control-surfaces.json`, so the change is out of the harness-gate design-gate scope; the guard is nonetheless structural by construction.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Canary trip → enqueue decision (load-bearing) | `user/scripts/efficacy-eval.py` (`_canary_evaluate_record`, `run_canary`, new `_canary_should_enqueue`) | Confound guard; suppresses band-only zero-attribution enqueues |
| Canary tests | `user/scripts/test_efficacy_eval.py` | New coverage: self-emitted band-only zero-attribution suppressed; independent still enqueues; attributed band still enqueues |

## Locked Decisions

1. **Confound guard over band-tuning** (operator offered both; chose the structural guard, 2026-07-19). A band-only trip on a non-independent signal with zero surface attribution does NOT auto-enqueue; it is surfaced (`suppressed[]`) and the record stays open. Attribution-corroborated and independent-signal band trips are unaffected.
2. **D4 preserved.** Nothing is auto-reverted; every trip — enqueued or suppressed — is surfaced in the canary payload for triage.
