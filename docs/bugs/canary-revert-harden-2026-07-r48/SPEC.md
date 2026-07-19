# Canary revert triage: harden-2026-07-r48 — Investigation Spec

> The harness-change canary for intervention `harden-2026-07-r48` tripped on a +334% band regression of `event:containment-refusal`, but the tripped change can only *reduce* that signal on its own path and no fresh incident was attributed to its surface — a band-only, confounded (noise) trip.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/canary-revert-harden-2026-07-r48
**Related:**
- Intervention record: `docs/interventions/harden-2026-07-r48.md`
- Shipped feature: `docs/features/harden-2026-07-r48/SPEC.md`
- Original bug the intervention fixed: `docs/bugs/lazy-cycle-containment-misparses-grouped-feature-paths/SPEC.md`
- Canary machinery: `docs/features/harness-change-canary-rollback/` · `docs/interventions/CLAUDE.md` → "The `canary:` sub-map"
- Trip evidence: `EVIDENCE.md` (this dir)

<!-- Status lifecycle:
  - Investigating → active investigation; bug-state.py routes to /spec-bug.
  - Concluded     → root cause proven, ready for /plan-bug.
  This SPEC stays Investigating: the technical root cause of the TRIP is proven
  (see Proven Findings), but the DISPOSITION of a shipped control-surface change
  (revert / redesign / close-as-noise) is an operator-owned product decision the
  canary is designed to surface for human triage (D4 — never a silent revert).
  That decision is parked in NEEDS_INPUT.md (written_by: root-cause? no — spec-bug).
-->

---

## Verified Symptoms

1. **[VERIFIED]** The canary for `harden-2026-07-r48` transitioned `status: open → tripped` and enqueued this `canary-revert-*` bug — confirmed by `docs/interventions/harden-2026-07-r48.md` frontmatter (`canary.status: tripped`, `canary_revert_enqueued: '2026-07-18'`) and the seeded `EVIDENCE.md`.
2. **[VERIFIED]** The trip is a **band-only** trip: the targeted signal `event:containment-refusal` moved +334.1% vs the frozen baseline of 72.85 ev/run (post 316.25 ev/run over 4 window runs), exceeding the ±25% band — with **zero attributed fresh incidents** (`EVIDENCE.md` "Attributed fresh incidents (verbatim): (none — band-only trip)").
3. **[VERIFIED]** The revert target is a single commit `251187c8` touching only `user/hooks/lazy-cycle-containment.sh` + `user/scripts/test_hooks.py`; **no coupled-pair scope** and a plain `git revert` is expected to apply (`EVIDENCE.md` "Coupled-pair scope" / "Degraded-revert note").

## Reproduction Steps

The trip is already recorded; the finding is reproducible from committed state:

1. Read the intervention record and its canary sub-map:
   `Read docs/interventions/harden-2026-07-r48.md` → `canary.surfaces: [user/hooks/lazy-cycle-containment.sh]`, `target_signal: event:containment-refusal`, `expected_direction: decrease`.
2. Read the trip evidence:
   `Read docs/bugs/canary-revert-harden-2026-07-r48/EVIDENCE.md` → band-only trip, `(none — band-only trip)` attributed incidents.
3. Inspect the tripped change's effect on the signal it is charged with:
   `git show 251187c8d620446d363c4477f31f89964d426f17 -- user/hooks/lazy-cycle-containment.sh`
   → the diff makes `_is_carve_out` (the *allow* predicate) group-aware and strictly MORE permissive for grouped features; ungrouped features are byte-identical; the 2nd-feature deny path denies iff `under-feature-dir AND not carve-out`.

**Expected (of a canary trip that warrants a revert):** the tripped change is attributable to the signal regression — i.e. the change plausibly *caused* the observed movement, or ≥1 fresh incident is attributed to its surface.
**Actual:** the change can only *decrease* `event:containment-refusal` on its own path (it removes false-positive denies), and **no** fresh incident was attributed to its surface — the +334% is aggregate movement with zero surface attribution.
**Consistency:** deterministic — a property of the committed diff and the recorded trip evidence.

## Evidence Collected

### Source Code
`git show 251187c8 -- user/hooks/lazy-cycle-containment.sh` (traced, each hop below):

- **Allow path** — `_is_carve_out(path, feature_id)` (`user/hooks/lazy-cycle-containment.sh:~521`): previously returned True only when `_FEATURE_DIR_RE.group(1) == feature_id`; now delegates to the new group-aware `_path_under_feature` (`~350`), which matches BOTH `docs/(features|bugs)/<feature_id>/…` (ungrouped) AND `docs/(features|bugs)/<group>/<feature_id>/…` (grouped). This makes the carve-out (allow) set a **superset** of the old one for grouped features and **identical** for ungrouped.
- **Deny path** — the 2nd-feature tripwire comprehension (`~659`): now `offending = [p for p in staged if _FEATURE_DIR_RE.search(p) and not _is_carve_out(p, feature_id)]`. Because `_is_carve_out` only grew (never shrank), `offending` can only shrink or stay equal → **fewer or equal denies**, never more.
- Denies are what emit `event:containment-refusal` (the hook writes its own deny events to `hook-events.jsonl`, per the intervention record's `signal_independence: self-emitted`). Fewer denies ⇒ fewer, not more, of the targeted signal from this surface.

### Runtime Evidence
- Intervention frontmatter: baseline frozen at 72.85 ev/run (20 runs, 1457 events, window `2026-07-09 → 2026-07-16`); canary opened `2026-07-16`, `window_runs: 10`.
- `EVIDENCE.md` band numbers: relative movement 334.1% (band ±25%), 1265 post-ship occurrences over 4 window runs (316.25 ev/run), attributed fresh incidents: none.
- `efficacy-eval.py --canary --dry-run --id harden-2026-07-r48` reports 0 open (the record is already `status: tripped`; the watcher wakes on `open` only) — consistent, no re-trip.

### Git History
- `251187c8` (2026-07-16) "harden(hook): make lazy-cycle-containment 2nd-feature tripwire group-aware" — the sole revert target; +100/−9 across the hook and its tests.
- The commit carries two registered regression tests: `test_containment_allows_same_feature_commit_grouped` (the false-deny this fixed) and `test_containment_denies_second_feature_commit_grouped` (a no-weakening guard proving genuine 2nd-feature commits still deny).

### Related Documentation
- `docs/interventions/CLAUDE.md` → the D2 tripwire is `targeted-signal regression past the KPI band / else ≥25% relative with ≥3 post-ship occurrences, OR ≥2 attributable fresh incidents`, and D3 surface-based attribution keys fresh incidents on the `surfaces` set. A band-only trip fires on the D2 aggregate condition even when D3 attribution is empty — a known low-precision mode for a high-volume, self-emitted signal.
- `docs/kpi/registry.json` → `canary-trip-precision` measures the fraction of trips whose revert item is NOT closed-as-noise; a close-as-noise disposition here is the intended feedback that tunes the D2 band.

## Theories

### Theory 1: The change caused the containment-refusal regression (revert-warranted)
- **Hypothesis:** the group-aware rewrite introduced a defect that denies more, inflating `event:containment-refusal`.
- **Supporting evidence:** the raw signal rose +334% during the canary window.
- **Contradicting evidence:** the diff makes the *allow* predicate strictly more permissive (deny set can only shrink); ungrouped features are byte-identical; a no-weakening regression test guards the genuine-deny path; **zero** fresh incidents were attributed to the change's surface.
- **Status:** Ruled Out.

### Theory 2: Band-only, confounded (noise) trip (close-as-noise-warranted)
- **Hypothesis:** the +334% aggregate movement of a high-volume self-emitted signal is driven by unrelated in-window activity (more runs / more *legitimate* containment denials working as designed), not by this change, which is mechanically deny-reducing and drew zero surface attribution.
- **Supporting evidence:** band-only trip with `(none)` attributed incidents; the change can only reduce the signal on its path; `event:containment-refusal` is a self-emitted, volume-sensitive signal whose ±25% band is easily exceeded by run-mix variance.
- **Contradicting evidence:** none identified — the aggregate did move, but attribution places none of it on this surface.
- **Status:** Confirmed (technical), pending operator disposition.

## Proven Findings

- **The tripped change is mechanically incapable of increasing `event:containment-refusal` on its own serving path** (traced: `_is_carve_out` grew → `offending` deny set can only shrink → fewer emitted deny events). Cause label: **`traced`** — serving-path chain cited `file:line`; the "fix site" (the deny-emitting comprehension) is on the signal's emission path and moves it the *opposite* direction from the regression.
- **The trip is band-only with empty surface attribution** — a confounded (noise) signal, not evidence of harm from `251187c8`.
- **Reverting would re-introduce a real, tested defect** (`lazy-cycle-containment-misparses-grouped-feature-paths`): grouped-feature (`docs/features/<group>/<slug>/`) cycle-subagent commits would again be false-denied, breaking AlgoBooth's grouped-queue runs. A revert would *increase* false-positive containment denies — the opposite of the intervention's goal.
- Therefore the technically-correct disposition is **close-as-noise** (keep the fix) + tune the canary D2 band for high-volume self-emitted signals. The **choice among revert / redesign / close-as-noise on a shipped control-surface change is operator-owned** (canary D4 is human-triage by design) — parked in `NEEDS_INPUT.md`.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Containment hook (revert target) | `user/hooks/lazy-cycle-containment.sh`, `user/scripts/test_hooks.py` | The change under triage; correct and tested — reverting re-breaks grouped features. |
| Intervention/canary ledger | `docs/interventions/harden-2026-07-r48.md` | Records the trip; a close-as-noise disposition is a `canary-trip-precision` signal. |
| Canary tripwire tuning | `user/scripts/efficacy-eval.py` (D2 band logic), `docs/kpi/registry.json` (`canary-trip-precision`) | A band-only zero-attribution trip on a deny-reducing change indicates the ±25% band is too tight for high-volume self-emitted signals — candidate follow-up if the operator confirms close-as-noise. |

## Open Questions

- **Operator disposition (parked in `NEEDS_INPUT.md`):** revert / redesign / close-as-noise for `251187c8`.
- If close-as-noise is confirmed: should the D2 tripwire require **non-empty D3 surface attribution** (not band-movement alone) before tripping for a self-emitted signal, or widen the band for high-volume signal classes? (A candidate `--enqueue-adhoc` harden follow-up, not in this bug's scope.)
