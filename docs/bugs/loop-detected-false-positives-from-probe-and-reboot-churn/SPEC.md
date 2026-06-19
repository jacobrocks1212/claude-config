# LOOP-DETECTED tripwire fires on benign re-probes, runtime reboots, and intervening resolutions — Investigation Spec

> In real `/lazy-batch` runs, the `step_repeat_count` / HEAD-aware loop tripwire fired on benign churn — repeated probes for the same cycle, runtime reboot turns with no commits, and needs-input resolutions that don't reset the streak. Two of the three classes are already closed by the F1/F2 double-probe debounce (landed AFTER these observations); the residual gap is the intervening-resolution class, which the debounce structurally cannot catch.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/loop-detected-false-positives-from-probe-and-reboot-churn
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy_core.py` (`update_repeat_counts` — `step_repeat_count` / HEAD-aware `repeat_count`); `user/skills/lazy-batch/SKILL.md` Step 1d loop-guard + Step 1g needs-input resolution; prior fixes `lazy-pipeline-ergonomics` Phase 2 (F2 step-debounce, 973339b) and `lazy-validation-readiness` Phase 1 (F1 dispatch-tuple debounce, 774ef23).

---

## Verified Symptoms
1. **[OBSERVED in logs]** Tripwire trips on a fully-understood benign cause — session `e076ed30` @ 2026-06-12T14:38:27: "step_repeat_count has reached the tripwire — but the cause is fully understood and benign". This is the umbrella complaint; symptoms 2–4 are its concrete drivers.
2. **[OBSERVED in logs]** Re-probes across reboot turns counted as a streak though no cycle ran — session `e076ed30` @ 2026-06-13T03:13:58: "the mcp-test cycle has never actually run (I re-probed across reboot turns with no commits landing, which is exactly what the HEAD-aware streak counts)".
3. **[OBSERVED in logs]** Intervening needs-input resolution does not reset the streak — session `e076ed30` @ 2026-06-12T20:44:53: "the LOOP-DETECTED framing is a step-counter artifact (the intervening needs-input resolution didn't reset the streak)".
4. **[OBSERVED in logs]** Two `--repeat-count` probes for one cycle advance the per-step counter — session `2f6f27dc` @ ~07:23: "Spurious loop-streak from my probe hygiene. … two --repeat-count probes for one cycle with no commit between advanced the per-step repeat counter."
5. **[OBSERVED in logs — masking pattern, not a separate bug]** Forward HEAD movement (commits landing on doc fixes) masks no-progress routing loops, so the step-repeat tripwire is the only thing that catches them. This is the DESIGN CONSTRAINT the fix must preserve, not a defect.

## Reproduction Steps
The benign-churn classes reproduce against `lazy_core.update_repeat_counts` (the single counter authority). Two probes with the SAME `(feature_id, current_step)` step signature:
1. Both probes marked (run marker present), NO dispatch between them (consume-count unchanged) → **F2 debounce HOLDS `step_count`** (already fixed — covers symptoms 2 & 4).
2. Both probes marked, a DISPATCH landed between them (consume-count rose) → **`step_count` increments** — this is the genuine residual (symptom 3): a needs-input resolution IS a dispatch.

**Expected:** A benign, fully-understood cause (re-probe, reboot re-probe, or a resolution that genuinely advanced the blocked decision) does NOT advance the oscillation tripwire.
**Actual:** Symptoms 2 & 4 no longer advance it (post-fix); symptom 3 still does, because the resolution meta-cycle consumes a nonce and so defeats the debounce's "no dispatch between probes" precondition.
**Consistency:** Deterministic given the consume/step-signature conditions above.

## Evidence Collected

### Source Code
`lazy_core.update_repeat_counts` (lines 3514–3826) is the SINGLE authority for both counters:
- `step_repeat_count` (signature `(feature_id, current_step)`) is deliberately **HEAD-BLIND** — its whole purpose is catching commit-masked oscillation (symptom 5's design constraint), so it cannot reset on forward HEAD movement.
- The **F2 double-probe debounce** (lines 3786–3805): HOLDS `step_count` when (a) a marker is present, (b) the step signature is unchanged, AND (c) the registry consume-count is unchanged since the prior marked probe ("no dispatch landed between the two probes"). One guard ALLOW = one `consume_nonce` = one consume (`consumed_emission_count`, line 7271).
- The **F1 dispatch-tuple debounce** (lines 3718–3735) gives the same HOLD for `repeat_count`.
- The **ordered-advance exemption** (lines 3759–3785) already resets when `sub_skill_args` advances (multi-part execute-plan).
The debounce's precondition is "NO dispatch between the two probes." A needs-input resolution (`/lazy-batch` Step 1g `apply-resolution` meta-dispatch) IS an Agent dispatch → it consumes a nonce → `consumed_emission_count` rises → the F2 HOLD branch is NOT taken → `step_count` increments across a legitimately-resolved blocker. There is no resolution-aware reset.

### Git History
The F2 step-debounce (973339b, 2026-06-13 11:08) and F1 dispatch-tuple debounce (774ef23, 2026-06-13 19:55) both landed **AFTER** the symptom observations (06-12 14:38/20:44; 06-13 03:13). Their docstrings name precisely the failure these symptoms describe: "stops an inspection-probe-then-dispatch-probe pair from inflating either counter and tripping a false LOOP DETECTED." → Symptoms 2 & 4 are double-probe/no-dispatch cases the debounce now holds.

### Related Documentation
`user/scripts/CLAUDE.md` → "Cycle-counter advance" and the `update_repeat_counts` docstring document the two-counter design, the HEAD-aware vs HEAD-blind split, and the consume-gated debounce. They confirm the consume oracle is the only "did a dispatch happen between probes" signal available to the counter.

## Theories

### Theory 1: All three classes are one missing "benign-churn reset" in the counter
- **Hypothesis:** symptoms 2, 3, 4 share a root cause — the counter has no way to distinguish benign churn from a stall.
- **Supporting evidence:** all three are step-counter artifacts.
- **Contradicting evidence:** symptoms 2 & 4 are the NO-DISPATCH-between-probes case, already handled by the F1/F2 consume-debounce that postdates the logs. Only symptom 3 is the DISPATCH-DID-happen case.
- **Status:** Ruled Out (partially) — the classes do NOT share one open gap; two are closed.

### Theory 2: Residual gap is the intervening-resolution class only
- **Hypothesis:** symptom 3 is the sole remaining defect: a needs-input resolution dispatch defeats the consume-based debounce, so the streak does not reset across a legitimately-resolved blocker even though that resolution is forward progress.
- **Supporting evidence:** the resolution is an Agent meta-dispatch (Step 1g) → consume-count rises → F2 HOLD not taken; the step signature `(feature_id, current_step)` is unchanged across the resolution; no resolution-aware reset exists.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

## Proven Findings
1. **Symptoms 2 & 4 are ALREADY FIXED** by the F1/F2 consume-count double-probe debounce (973339b + 774ef23), which landed after the 06-12/06-13 observations. A fresh repro is the regression-test deliverable, not new fix code — confirm both no longer inflate the counters under the current debounce.
2. **Symptom 3 is the genuine residual gap.** The debounce keys on "no dispatch between probes," but a needs-input resolution IS a dispatch, so the streak survives a legitimate resolution. The fix must inject a **resolution-aware reset signal** that the HEAD-blind `step_repeat_count` honors — distinct from the consume-debounce, because here a dispatch DID land. Candidate discriminator: detect that the prior cycle was a needs-input *resolution* meta-cycle (which cleared a `NEEDS_INPUT.md` blocker) and reset the step streak to 1 on the next probe, mirroring the existing ordered-advance exemption's "genuine forward progress → reset" shape.
3. **The masking-detection design constraint (symptom 5) MUST be preserved.** Any reset added must NOT re-introduce HEAD-advance immunity for the general oscillation case — the d8 commit-masked loop must still trip. The reset must be scoped to the resolution event specifically (like the ordered-advance exemption is scoped to advanced `sub_skill_args`), never a blanket HEAD/commit reset.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Counter authority | `user/scripts/lazy_core.py` (`update_repeat_counts`, lines 3514–3826) | Add a resolution-aware `step_count` reset, scoped like the ordered-advance exemption; preserve HEAD-blindness for the general case. |
| Resolution dispatch | `user/skills/lazy-batch/SKILL.md` Step 1g (+ `/lazy-bug-batch` mirror) | Resolution meta-cycle must surface a signal the counter can key on (e.g. a persisted "prior cycle resolved a NEEDS_INPUT" marker field), so the reset is deterministic, not inferred. |
| Smoke tests | `user/scripts/test_lazy_core.py`, `lazy-state.py --test` / `bug-state.py --test` baselines | New fixtures: (a) regression-confirm symptoms 2 & 4 hold under the debounce; (b) new resolution-reset fixture for symptom 3; (c) negative fixture proving the d8 commit-masked loop still trips. |

## Open Questions
- Exact discriminator for "the prior cycle was a needs-input resolution": a new persisted marker field on the resolution meta-cycle vs. inferring it from the cleared `NEEDS_INPUT.md` / sentinel state at probe time. (Fix-planning decision — `/plan-bug`. Mechanical-internal: both yield identical product behavior, differing only in implementation locus.)
- Whether `repeat_count` (dispatch-tuple) needs the same resolution-aware reset, or whether its HEAD-aware reset already covers the resolution case (a resolution that commits advances HEAD → `repeat_count` resets; only the HEAD-blind `step_repeat_count` is exposed). Likely `step_repeat_count`-only, to confirm during planning.
