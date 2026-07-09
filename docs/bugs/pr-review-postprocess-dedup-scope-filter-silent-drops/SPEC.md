# PR-review post-process dedup collapses distinct co-located findings and the scope filter drops path-mismatched findings uncounted — Investigation Spec

> `post-process.ts` step 3 dedups by exact `file:line` and keeps exactly one finding per location even when the co-located findings describe different issues (the loser is discarded, counted only as a "dedup"); step 5 drops any finding whose `file` string doesn't exactly match a manifest path (no normalization for separators, leading slash, or case) and those drops appear in **no** counter — invisible loss.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/pr-review-postprocess-dedup-scope-filter-silent-drops
**Related:** cognito-pr-review plugin (`user/plugins/local-tools/plugins/cognito-pr-review/`); `docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane` (sibling silent-loss defect in the same pipeline — same "loss without a counter" class)

---

## Verified Symptoms

1. **[VERIFIED]** `step3_deduplicate` keys findings solely on `locationKey(file, line)` (`${file}:${line}`) and retains exactly one finding per key. Nothing in the key or the tie-break compares what the findings are *about* — an investigation bug and an unrelated sweep rule hit anchored to the same line collapse to one, the other discarded. — Confirmed by source read (`scripts/post-process.ts:431-467`, key at 439, tie-breaks at 449-463).
2. **[VERIFIED]** `step5_filterOutOfScope` filters with `Set.has(f.file)` against `manifest.files[].path` verbatim — no separator/slash/case normalization — and the filtered-out findings are not tallied: the output payload carries only `dropped_count` (weight-threshold drops from step 2) and `dedup_count` (step 3); step 5's removals appear in neither. — Confirmed by source read (`scripts/post-process.ts:489-495`, payload assembly 585-596).
3. **[REPORTED]** In-the-wild frequency is uncharacterized: existing caches don't record what step 5 removed (that absence is symptom 2 itself), so how often agents emit non-manifest path spellings is unknown. Agents are prompted to echo cached manifest paths, so the mismatch arm is likely low-frequency — but when it fires it is invisible by construction.

## Reproduction Steps

Both arms reproduce deterministically with a synthetic input against any real cache manifest:

1. Pick any cache dir with a valid `manifest.json` (e.g. `user/plugins/local-tools/plugins/cognito-pr-review/.claude/pr-cache/18398/`). Note an exact manifest path, e.g. `Cognito.Core/Services/Forms/FormsService.cs`.
2. Write `combined.json` containing, in the investigation lane, TWO distinct findings at the SAME file+line (different titles/hypotheses, both `confidence: "CONFIRMED"`), plus ONE finding whose `file` is a case/separator variant of a manifest path (e.g. `cognito.core/Services/Forms/FormsService.cs` or a leading `/` form).
3. Run:
   ```bash
   npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/post-process.ts \
     --input combined.json --manifest <cacheDir>/manifest.json
   ```
4. Inspect `processed_findings`, `dropped_count`, `dedup_count`.

**Expected:** Two different issues at one location both survive (or the collapse is at least surfaced per-finding); the path-variant finding either matches after normalization or its removal is counted/warned.
**Actual:** Only one of the co-located findings survives (`dedup_count: 1` — indistinguishable from a true duplicate); the path-variant finding vanishes with all counters unchanged.
**Consistency:** Always — pure deterministic string logic.

## Evidence Collected

### Source Code — root-cause trace (`traced`)

All paths relative to `user/plugins/local-tools/plugins/cognito-pr-review/`.

**Arm 1 — distinct-issue collapse (surface: a real finding absent from `processed_findings`, tallied only as `dedup_count`):**

```
processed-findings.json: finding missing, dedup_count++
  → main(): step3_deduplicate(thresholded)                    scripts/post-process.ts:572
  → key = locationKey(file, line) = `${file}:${line}`         scripts/post-process.ts:439, 205-207   ← no issue-identity component
  → seen.get(key) hit → dedupCount++                          scripts/post-process.ts:440-447
  → tie-break: Opus-lane beats sweep; else higher weight      scripts/post-process.ts:449-463        ← loser DISCARDED, content never compared
  → survivors = Array.from(seen.values())                     scripts/post-process.ts:466
```

Fix site: the dedup key / tie-break block (`scripts/post-process.ts:439-463`) — on the path (it is the code that chooses the survivor). `traced`.

**Arm 2 — uncounted out-of-scope drop (surface: finding absent from `processed_findings`, no counter moves):**

```
processed-findings.json: finding missing, dropped_count & dedup_count unchanged
  → main(): step5_filterOutOfScope(ranked, manifest)          scripts/post-process.ts:574
  → manifestFiles = new Set(manifest.files.map(f => f.path))  scripts/post-process.ts:493            ← verbatim strings
  → findings.filter(f => manifestFiles.has(f.file))           scripts/post-process.ts:494            ← exact match only; return value's removals not counted
  → OutputPayload = { dropped_count (step2), dedup_count (step3), lifespan_annotations } — no step-5 field
                                                              scripts/post-process.ts:585-596
```

Fix site: `step5_filterOutOfScope` + the payload assembly (`scripts/post-process.ts:489-495, 585-596`) — on the path. `traced`. Neither arm is runtime-coupled (deterministic, fully observable from source).

### Runtime Evidence

None required — both arms are static-deterministic. Note the self-masking property: because step 5 removals are uncounted, on-disk caches cannot show how often arm 2 has fired historically.

### Related Documentation

- `scripts/post-process.ts:8-10` header: "3. Deduplicates by file:line (prefers investigation over sweep) … 5. Filters out-of-scope files via manifest" — the header documents the mechanism but not the distinct-issue collapse or the uncounted removal.
- The sibling bug `pr-review-source-weights-drift-zeroes-opus-lane` (Proven Findings + its fix #3 "surface a warning when a whole lane is zeroed") established the same principle this SPEC extends: post-process must never discard findings without an attributable count.

## Theories

### Theory 1: Dedup key was designed for cross-lane duplicates and over-collapses
- **Hypothesis:** `file:line` keying assumed co-located findings are the same issue seen by two lanes (investigation + sweep double-reporting), so "keep the stronger lane" was the whole design; two genuinely different issues at one line weren't considered.
- **Supporting evidence:** Tie-break logic is entirely lane/weight-based (449-463); no title/rule/description similarity is consulted anywhere in step 3.
- **Status:** Confirmed (by source structure).

### Theory 2: Step 5 was assumed loss-free
- **Hypothesis:** Because agents are instructed to echo manifest paths, step 5 was treated as a no-op safety net and never given a counter or normalization.
- **Supporting evidence:** It is the only discard step in the pipeline with no output-payload field; steps 2 and 3 both count.
- **Status:** Likely (design intent inferred; mechanism confirmed).

## Proven Findings

- **CONFIRMED:** Two findings with identical `file:line` but different content cannot both survive `step3_deduplicate`; the discarded one is counted as a duplicate (`dedup_count`), misreporting distinct-issue loss as deduplication.
- **CONFIRMED:** A finding whose `file` differs from the manifest spelling by case, separators, or a leading slash is removed by `step5_filterOutOfScope` with no counter, no warning, and no per-finding record — invisible in every artifact.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Dedup step | `scripts/post-process.ts` (205-207, 431-467) | Distinct co-located issues collapse to one; loss mislabeled as dedup |
| Scope filter | `scripts/post-process.ts` (489-495) | Path-spelling mismatches silently deleted |
| Output payload | `scripts/post-process.ts` (147-153, 585-596) | No step-5 counter; no per-step drop attribution |

## Candidate Root Fixes (for /plan-bug)

1. **Content-aware dedup:** include an issue-identity component in the key (e.g. `rule_id` for sweep, normalized title/hypothesis hash for Opus lanes) or only collapse when titles are similar; keep the lane-preference tie-break for true duplicates.
2. **Normalize paths on both sides of step 5** (forward slashes, strip leading `/`, case-fold on Windows) before comparing — mirror `calibrate-weights.ts`'s existing `normalizePath` approach.
3. **Count and surface every discard:** add `scope_filtered_count` (and ideally a per-finding `drops[]` list with step + reason) to the output payload, and have the orchestrator/synthesizer surface non-zero values — the same diagnostic principle as the lane-zeroed warning in the related weights bug.

## Open Questions

- For arm 1, is the right v1 fix a smarter key or simply keeping both findings and letting the synthesizer group co-located items? (Keeping both is simpler and loss-free; ranking already orders them.)
- Should path normalization live in post-process only, or also in the agent output contract (agents required to emit manifest-verbatim paths, validated by aggregate-findings.ts)?
