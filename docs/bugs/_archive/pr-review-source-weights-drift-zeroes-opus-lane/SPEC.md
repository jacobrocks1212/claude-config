# PR-review calibration drifts source weights below the drop threshold, silently zeroing the Opus lane — Investigation Spec

> EMA-calibrated `source_weights` in the cognito-pr-review plugin drifted below `post-process.ts`'s `MIN_EFFECTIVE_WEIGHT` (0.3), so `step2_dropBelowThreshold` discarded every investigation + intra-file finding — including CONFIRMED important ones — leaving only the sweep lane.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-09
**Placement:** docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane
**Related:** cognito-pr-review plugin (`user/plugins/local-tools/plugins/cognito-pr-review/`); calibration skills `/cognito-pr-review:weights`, `/cognito-pr-review:learn-from-pr`, `/cognito-pr-review:calibrate`

---

## Verified Symptoms

1. **[VERIFIED]** During the `/cognito-pr-review:review-pr 16960` run, deterministic post-processing dropped 13 of 14 findings (`dropped_count: 13`), keeping only the single sweep-lane finding. All investigation and intra-file findings — including two CONFIRMED important findings (the archive event/outcome split-brain and the `GuardRetainedFileReferences` scope gap) — were discarded. Confirmed by the reporter (Jacob) as the trigger for filing this bug.
2. **[VERIFIED]** The drop was silent: post-process reports only aggregate `dropped_count`, with no signal that an entire source lane was zeroed. Confirmed from the script output and source.

## Reproduction Steps

1. Ensure `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml` has `source_weights.investigation < 0.3` (pre-fix value: `0.2933`) and `source_weights.intrafile < 0.3` (pre-fix: `0.2681`).
2. Run any PR review that produces investigation and/or intra-file findings, e.g. `/cognito-pr-review:review-pr <id>`, through Step 8 (`post-process.ts`).
3. Inspect `{cacheDir}/processed-findings.json`.

**Expected:** Investigation/intra-file findings survive post-processing; a CONFIRMED important finding is never dropped by weight thresholding alone.
**Actual:** Every investigation and intra-file finding is dropped; `dropped_count` equals the full non-sweep count; only sweep findings remain.
**Consistency:** Always, whenever a non-sweep source weight is below `MIN_EFFECTIVE_WEIGHT` (0.3).

## Evidence Collected

### Source Code — root-cause trace (`traced`)

Serving path from the observed symptom (findings dropped) back to the source value the fix must change, each hop cited `file:line` in `user/plugins/local-tools/plugins/cognito-pr-review/`:

```
processed-findings.json: dropped_count=13, processed_findings=[1 sweep]
  → main() pipeline                                        scripts/post-process.ts:571   (step2_dropBelowThreshold)
  → step2_dropBelowThreshold: if (f.effective_weight
        < MIN_EFFECTIVE_WEIGHT) droppedCount++            scripts/post-process.ts:420-426
  → MIN_EFFECTIVE_WEIGHT = 0.3                             scripts/post-process.ts:171
  → effective_weight = base × confidence                  scripts/post-process.ts:232-246 (computeEffectiveWeight)
  → base = weights.source_weights[source] ?? 0.7          scripts/post-process.ts:243
  → confidence: CONFIRMED→1.0, UNVERIFIED→0.5             scripts/post-process.ts:223-229 (resolveConfidence)
  → source_weights.investigation = 0.2933,
        source_weights.intrafile = 0.2681                 knowledge/weights.yaml:17-18   ← fix-site (value on path)
```

Because `base` (0.2933 / 0.2681) is already below 0.3, even a CONFIRMED finding (confidence multiplier 1.0) yields `effective_weight < MIN_EFFECTIVE_WEIGHT` and is dropped. `UNVERIFIED` findings (×0.5) require `base ≥ 0.6` to survive, so `reuse: 0.5454` silently drops UNVERIFIED reuse findings even though it clears the CONFIRMED bar.

The fix site (`source_weights` values) is **on** the traced path — the value is read at `post-process.ts:243` on the way to the drop decision. Cause is **`traced`**, not asserted. Not runtime-coupled: the logic is deterministic and fully observable from source + the script's own output.

### Git History
`weights.yaml` header: `last_calibrated: 2026-06-01`, `calibration_prs: [16496]`, `ema_alpha: 0.25`. The low values are the product of EMA calibration writes (`/cognito-pr-review:learn-from-pr` / `calibrate`) accumulating downward with no floor.

### Related Documentation
- `post-process.ts` header documents the drop step as intended for *sweep* findings ("Drops sweep findings below minimum threshold", scripts/post-process.ts:7) — but the implementation applies the same `MIN_EFFECTIVE_WEIGHT` gate to **all** sources, including the Opus lanes, which the doc comment does not describe.

## Theories

### Theory 1: Calibration has no lower bound on source weights
- **Hypothesis:** The EMA calibration writer can drive a `source_weight` arbitrarily low over successive PRs with no clamp, eventually crossing below the 0.3 drop threshold.
- **Supporting evidence:** Two of three source weights sit below 0.3; `ema_alpha: 0.25` compounds toward zero on repeated low-signal PRs; no floor is visible in the weights file.
- **Status:** Likely (calibration-writer source not yet read in this investigation).

### Theory 2: The drop threshold should not apply to Opus-lane sources
- **Hypothesis:** `MIN_EFFECTIVE_WEIGHT` is a sweep-lane rule (per the script's own header) mistakenly applied to investigation/intrafile/reuse findings, which are already high-signal by construction.
- **Supporting evidence:** Header comment scopes the drop to sweep; Opus-lane findings carry explicit `confidence` and rank at the top tier (`step4_rank` treats them as `critical`).
- **Status:** Likely.

## Proven Findings

- **CONFIRMED:** With `source_weights.<opus-source> < 0.3`, `step2_dropBelowThreshold` discards every finding from that source regardless of `confidence`, because `effective_weight = base × confidence ≤ base < 0.3`. This is the mechanism that zeroed the investigation and intra-file lanes in the PR #16960 review.

## Stopgap Applied

`knowledge/weights.yaml` `source_weights` manually floored to `0.7` (the script's own `?? 0.7` default) for `investigation`, `intrafile`, and `reuse`, with an inline comment referencing this bug. This restores lane survival for both CONFIRMED (0.7) and UNVERIFIED (0.35) findings. It does **not** address the underlying drift; the next calibration write can re-lower the values unless a floor is added.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Post-process drop gate | `user/plugins/local-tools/plugins/cognito-pr-review/scripts/post-process.ts` (171, 232–246, 413–429) | Applies sweep threshold to all lanes; no per-source policy; no "lane zeroed" warning |
| Calibration weights | `user/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml` (16–19) | Drifted values; stopgap-floored to 0.7 |
| Calibration writer | `/cognito-pr-review:learn-from-pr`, `calibrate`, `weights` skills/scripts | Presumed writer with no lower clamp (not yet read) |

## Candidate Root Fixes (for /plan-bug)

1. **Clamp in the calibration writer** — never let an EMA update drive a `source_weight` below `MIN_EFFECTIVE_WEIGHT` (or a configured floor above it). Prevents recurrence at the source.
2. **Exempt Opus-lane sources from the sweep drop** — apply `MIN_EFFECTIVE_WEIGHT` only to `source === "sweep"` (or give Opus lanes a separate, lower/none threshold), matching the script's documented intent.
3. **Surface a warning when a whole lane is zeroed** — emit a diagnostic from `post-process.ts` (and/or the orchestrator) when `dropped_count` accounts for 100% of any single source, so a silent lane-kill can never pass unnoticed again.

## Open Questions

- ~~Where exactly does the EMA calibration write `source_weights`, and does any existing clamp apply?~~ **ANSWERED (2026-07-09 follow-up investigation):** the writer is `scripts/disposition-calibration.ts` — `applyEma` (`new = α·signal + (1-α)·old`, α=0.25) with routing to `source_weights[source]` for non-sweep sources; **no clamp, floor, or ceiling exists anywhere** in the file. Signal is binary (`dismiss`→0, any kept severity→1). The deeper statistical-design flaws (per-disposition α compounding, one-scalar-per-lane, escape-hatch drift acceleration, unused `data_points`) are now their own investigation: `docs/bugs/pr-review-ema-calibration-statistical-design-drives-lane-death/`.
- Should the floor be a shared constant with `MIN_EFFECTIVE_WEIGHT`, or an independent per-source policy? (Fix #1 vs #2 interaction.)

## Follow-up Investigations (2026-07-09)

The plugin rethink session surfaced sibling defects that compound this bug — each has its own investigation SPEC:

- **`pr-review-plugin-cache-split-brain-freezes-weights`** — the runtime loads the plugin (agents/commands) from the versioned cache `~\.claude\plugins\cache\local-tools\cognito-pr-review\2.9.0\`, whose `weights.yaml` still carries the DRIFTED values (investigation 0.1919 / intrafile 0.3707 / reuse 0.3938) — the Stopgap Applied above never reached the copy half the runtime reads. Any fix to this bug must land in (or be resolved by relocating) BOTH copies.
- **`pr-review-ema-calibration-statistical-design-drives-lane-death`** — why the drift recurs even with fixes #1–#3.
- **`pr-review-pending-calibration-marker-unconsumable-nonbuddy`** — the non-buddy calibration path is broken by construction.
