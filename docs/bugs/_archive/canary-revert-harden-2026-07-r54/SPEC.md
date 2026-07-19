# Canary revert-or-redesign triage: harden-2026-07-r54 — Investigation Spec

> The harness-change canary for intervention `harden-2026-07-r54` tripped on a +59.6% rise in
> `event:gate-refusal`, but the shipped change provably does not emit that signal — this is a
> band-only confound, not damage. Triage: revert / redesign / close-as-noise.

**Status:** Won't-fix
**Severity:** P2
**Discovered:** 2026-07-19
**Placement:** docs/bugs/canary-revert-harden-2026-07-r54
**Related:** docs/interventions/harden-2026-07-r54.md · docs/features/harden-2026-07-r54/ · docs/bugs/dispatch-probe-and-inject-bypass-merged-head/ (the Concluded bug the shipped change fixed) · docs/features/intervention-efficacy-tracking/ · docs/features/harness-change-canary-rollback/

<!-- Status lifecycle: Investigating → /spec-bug; Concluded → /plan-bug. Left Investigating because
     the disposition (revert / redesign / close-as-noise) is an unresolved operator decision —
     see NEEDS_INPUT.md (stub_origin, product-class). The ROOT CAUSE of the trip is traced and
     proven below; only the human disposition is pending. -->

---

## Verified Symptoms

1. **[VERIFIED]** The canary for `harden-2026-07-r54` tripped on 2026-07-18 — `EVIDENCE.md`
   (`kind: canary-evidence`) and `docs/interventions/harden-2026-07-r54.md` frontmatter
   (`canary.status: tripped`, `canary_revert_enqueued: '2026-07-18'`).
2. **[VERIFIED]** Trip reason is a **band-only** movement: targeted signal `event:gate-refusal`
   regressed **+59.6%** vs the frozen baseline `4.7 ev/run` (band ±25%; post 7.5 ev/run; 30
   post-ship occurrences over 4 window runs). Attributed fresh incidents: **none** — `EVIDENCE.md`
   §"Attributed fresh incidents (verbatim)" is `(none — band-only trip)`.
3. **[VERIFIED]** The trip direction is OPPOSITE the hypothesis: the intervention's
   `expected_direction` is `decrease`, but the observed movement is an increase.

## Reproduction Steps

1. Read the trip evidence: `docs/bugs/_archive/canary-revert-harden-2026-07-r54/EVIDENCE.md` (band numbers,
   commit set, empty pair scope, "plain `git revert` expected to back the change out").
2. Read the intervention record: `docs/interventions/harden-2026-07-r54.md` — note
   `target_signal: event:gate-refusal`, `expected_direction: decrease`,
   `signal_independence: independent — the fix emits only dispatch/route-override telemetry
   (route_overridden_by=merged-head-diverged), never a gate-refusal`.
3. Confirm the trace (below): `git show 1af48e1d -- user/scripts/lazy-state.py user/scripts/bug-state.py`
   contains no `gate-refusal` token; the added hunks set `state["route_overridden_by"] =
   "merged-head-diverged"` (a dispatch/route-override field), never `append_telemetry_event(
   "gate-refusal", …)`.

**Expected:** A canary trip on a targeted signal should indicate the shipped change moved that
signal — i.e. the change is on the signal's serving path.
**Actual:** The change is provably NOT on the `event:gate-refusal` serving path; the band moved for
reasons unattributable to the change (a confounded / noise trip).
**Consistency:** Deterministic — the trace is static and re-derivable from the commit and the emit
sites at any time.

## Evidence Collected

### Source Code (traced serving-path analysis)

**`event:gate-refusal` emit sites** (the signal's producers) — completion/coverage-gate seams:
- `user/scripts/lazy-state.py:13176, 13511, 13577, 13643, 13996, 14400`
- `user/scripts/bug-state.py:9026, 9090, 9136, 9401, 9783`
- Signature vocabulary registered in `user/scripts/lazy_core/ledgers.py:2414` (`_GATE_REFUSAL_SIGNATURES`:
  `gate-coverage`, `unacked-hardening`, `efficacy-coverage-missing`, `checkpoint-auth`, `apply-pseudo`,
  `verify-ledger`).

**Commit `1af48e1d` touched files:** `bug-state.py`, `lazy-state.py`, `lazy_core/dispatch.py`,
`lazy_inject.py`, `test_hooks.py`, `tests/test_lazy_core/test_dispatch.py`.

**Commit hunk ranges** (from `git show --` hunk headers):
- `lazy-state.py` @@ +13554,28 and +13620,19 — the `--emit-prompt` merged-head withhold path.
- `bug-state.py` @@ +446,42 (`_current_head` helper) and +9325,23 / +9380,14 (`--emit-prompt` withhold).
- None of these ranges is a `gate-refusal` emit site.

**Added code (verbatim, lazy-state.py hunk):** the change sets
`state["route_overridden_by"] = "merged-head-diverged"` and `state["merged_head"] = …` when the
merged work-list head diverges — a **dispatch / route-override** telemetry field. `git show 1af48e1d`
contains **zero** `gate-refusal` tokens across the entire diff.

**Trace (fix-site-on-path check — NEGATIVE finding):**
```
symptom surface:  event:gate-refusal band (+59.6%)   telemetry ledger
  ← emitted by:   completion/coverage gate seams      lazy-state.py:13176.. / bug-state.py:9026..
  commit 1af48e1d changes:  --emit-prompt route withhold  lazy-state.py:~13554 / bug-state.py:~9325
                            + merged_head_override() helper lazy_core/dispatch.py
  → these emit:   event:dispatch / route_overridden_by  (NOT gate-refusal)
```
The commit's changed nodes are **not on** the `event:gate-refusal` serving path. The
`signal_independence: independent` claim in the intervention record is confirmed by reading the code.

### Runtime Evidence

Band-only trip with zero D3 surface-attributed fresh incidents (`EVIDENCE.md`). The efficacy
evaluator has not yet reached its ~20-run efficacy verdict window; the canary (every-run cadence)
fired first. No incident ledger entries were attributed to the change's surfaces
(`user/scripts/bug-state.py`, `lazy-state.py`, `lazy_core/dispatch.py`, `lazy_inject.py`).

### Git History

`1af48e1d655098e74019bf35b9bf0b37c58ccee5` (2026-07-16) — *"harden(script): route dispatch-bound
probe + inject hook by merged head, not sticky pipeline"* — fixed the Concluded bug
`dispatch-probe-and-inject-bypass-merged-head` (two live-2026-07-17 P0 hydra bugs were skipped for a
lower-priority feature). A correctness fix; the common path stays byte-identical.

### Related Documentation

- `docs/interventions/CLAUDE.md` §"The `canary:` sub-map" — canary is flag-and-enqueue only (D4);
  nothing is auto-reverted; triage is revert / redesign / close-as-noise, the last "itself a signal
  for tuning the canary bands." The `canary-trip-precision` KPI measures the fraction of trips whose
  revert item was NOT closed-as-noise.
- `docs/interventions/CLAUDE.md` §"Sub-signal targets" — a bare, undivided `event:gate-refusal`
  target **conservatively confounds every sub-signal of its type**; this record declares the
  undivided signal, so co-shipped hardening rounds firing any gate-refusal sub-signal inflate its
  count without being caused by this change.

## Theories

### Theory 1: Confounded / noise trip (change not on the signal's serving path)
- **Hypothesis:** The +59.6% band movement is produced by other gate seams / co-shipped hardening
  activity in the window, not by commit `1af48e1d`, which emits no `gate-refusal`.
- **Supporting evidence:** The static trace (commit changes route-override/dispatch telemetry only;
  no `gate-refusal` emit in the diff; none of its hunks is on the emit path); band-only trip with
  zero attributed fresh incidents; the undivided `event:gate-refusal` target confounds every
  co-shipped sub-signal by design.
- **Contradicting evidence:** None found. (An indirect path — the route override causing the pipeline
  to work a different item that hits more gates — is implausible: the override *withholds* a
  wrong-item route to reduce wasted work, and D3 attributed no incidents to its surfaces.)
- **Status:** Confirmed (traced).

### Theory 2: Genuine regression — the change causes more gate-refusals
- **Hypothesis:** The change actively increased gate-refusals (damage).
- **Supporting evidence:** The raw band moved the wrong way.
- **Contradicting evidence:** The change emits no `gate-refusal` and is not on its serving path
  (traced); zero attributed fresh incidents; the two changed emit-path files' hunks are the
  `--emit-prompt` withhold and a head helper, not gate seams.
- **Status:** Ruled Out.

## Proven Findings

- **[TRACED]** Commit `1af48e1d` is **not on the `event:gate-refusal` serving path**. It emits only
  route-override / dispatch telemetry (`route_overridden_by=merged-head-diverged`). Therefore the
  canary's +59.6% band movement is **not damage attributable to this change** — it is a band-only,
  confounded/noise trip. (Fix-site-on-path check applied in the inverse: the changed nodes are shown
  by code read to be off the symptom's serving path.)
- The change it shipped is a genuine correctness fix (prevented two P0 bugs from being skipped);
  `pair_scope` is empty and the commit is plain-`git revert`-safe, so a revert is *mechanically*
  cheap — but would remove a correct fix to chase a signal the change does not produce.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Canary tripwire / signal attribution | `user/scripts/efficacy-eval.py` (`--canary`), `docs/interventions/harden-2026-07-r54.md` | The trip fired on an undivided `event:gate-refusal` target the change doesn't emit — a band-only confound. Candidate for band/sub-signal tuning (close-as-noise path). |
| Shipped change under triage | `user/scripts/{lazy-state.py,bug-state.py,lazy_core/dispatch.py,lazy_inject.py}` @ `1af48e1d` | The revert target. Off the tripped signal's serving path; correct as shipped. |

## Open Questions

- **Disposition (operator decision — see `NEEDS_INPUT.md`):** revert, redesign, or close-as-noise?
  The investigation recommends **close-as-noise** (the change is correct and off the signal's serving
  path), which additionally feeds canary band/sub-signal tuning. This is a product-class choice
  (revert removes shipped behavior) on a stub-origin baseline, so it parks for the operator.

## Resolution

Operator-accepted the recommended **close-as-noise** disposition (`NEEDS_INPUT.md`, recorded via
`bug-state.py --record-decision`). The shipped merged-head route-override fix (`1af48e1d`) is
retained, not reverted — traced off the tripped `event:gate-refusal` signal's serving path;
band-only trip, zero attributed incidents. Canary/sub-signal band tuning is tracked separately,
not as a phase of this bug. Closed without a fix.
