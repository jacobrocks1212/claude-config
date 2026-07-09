# PR-review artifact format drift breaks the lifespan and bulk-calibration parsers — Investigation Spec

> The synthesizer-v2 Standardized Issue Block (and buddy Phase 2) emit findings as `**Location:** {file}:{line}`, but `post-process.ts`'s previous-review parser and `calibrate-weights.ts`'s artifact parser still match the retired `**File:**` / numbered-bracket-header formats — so re-review lifespan tracking silently annotates 0 findings and bulk calibration would parse 0 findings, counting every human comment as a false negative.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/pr-review-artifact-format-drift-breaks-lifespan-parsers
**Related:** cognito-pr-review plugin (`user/plugins/local-tools/plugins/cognito-pr-review/`); `docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane` (sibling post-process defect); `docs/bugs/pr-review-ema-calibration-statistical-design-drives-lane-death` (calibrate-weights.ts is also implicated there)

---

## Verified Symptoms

1. **[VERIFIED]** `lifespan_annotations` is `0` in **all 25** `processed-findings.json` caches on disk under `cog-docs` (`docs/**/.pr-review/pr-cache/*/processed-findings.json`) — including re-reviewed PRs whose previous `PR-{id}.md` exists (e.g. PR 16687, whose `REVIEWED.md` body records "Buddy re-review (iteration 18)"). The "raised N iterations" lifespan feature has never produced an annotation in the current corpus. — Confirmed by scanning every cache file 2026-07-09.
2. **[VERIFIED]** The persisted review corpus is format-split: 11 reviews carry the new `**Location:**` Standardized Issue Block; 15 carry the old `**File:**` shapes (older reviews and spot-checks). New-format reviews contain no `**File:** path:line` tokens for the parser to match. — Confirmed by grep across `cog-docs/docs/**/PR-*.md` 2026-07-09.

## Reproduction Steps

1. Pick a re-reviewed PR whose previous review is new-format, e.g. `C:\Users\JacobMadsen\source\repos\cog-docs\docs\bugs\<item>\PR-16687.md` (contains `**Location:**`, no `**File:**`).
2. Run post-processing with the previous review supplied:
   ```bash
   npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/post-process.ts \
     --input <cacheDir>/combined-findings.json \
     --manifest <cacheDir>/manifest.json \
     --previous-review <cogDocsItemDir>/PR-16687.md
   ```
3. Inspect the output payload's `lifespan_annotations` field.

**Expected:** Findings that recur at the same file/line (±20 lines) as a previous-review finding are annotated with `lifespan.raised_in_iteration`, and `lifespan_annotations > 0` when overlaps exist.
**Actual:** `lifespan_annotations: 0` — `parsePreviousReview` extracts zero refs from a new-format review, so nothing can match.
**Consistency:** Always, for any previous review written in the Standardized Issue Block format (every buddy/synthesizer-v2 review since the block shipped).

## Evidence Collected

### Source Code — root-cause trace (`traced`)

All paths relative to `user/plugins/local-tools/plugins/cognito-pr-review/`.

**Serving path A — lifespan annotation (surface: `lifespan_annotations: 0` in processed-findings.json):**

```
processed-findings.json: lifespan_annotations = 0
  → main(): step6 gated on previousReviewPath                scripts/post-process.ts:577-583
  → step6_annotateLifespan → parsePreviousReview(path)       scripts/post-process.ts:497-501
  → Pattern 1: /\*\*File:\*\*\s*`?([^:`\n]+):(\d+)`?/        scripts/post-process.ts:270-279  ← misses `**Location:**`
  → Pattern 2: /\[([^\]]+?):(\d+)\]/ (bracket refs)          scripts/post-process.ts:281-290  ← new format emits no [path:line]
  → Pattern 3: /###\s+(.+)…\*\*File:\*\*…/ (titles)          scripts/post-process.ts:292-302  ← keyed on **File:** again
  → refs = [] → matchesPreviousFinding never fires           scripts/post-process.ts:307-318, 501-515
  → lifespan_annotations stays 0                             scripts/post-process.ts:503, 590
```

The emitting side writes a shape none of those three patterns match:

```
synthesizer-v2 Standardized Issue Block:
  **Severity:** … **Source:** … **Location:** {file}:{line} …   agents/synthesizer-v2.md:75 (and 132/144/156/168 per-section templates)
buddy Phase 2 emits the same block                               commands/review-pr-buddy.md:173, 338
```

Fix site (the three regexes at `scripts/post-process.ts:271`, `:282`, `:293` — or the emitters above) is **on** the traced path: the refs list those patterns produce is exactly what `matchesPreviousFinding` consumes. Cause is **`traced`**; not runtime-coupled (deterministic string parsing, fully observable from source + on-disk artifacts).

**Serving path B — bulk calibration (surface: `→ 0 plugin finding(s) parsed` per artifact; every human comment counted FN):**

```
calibration report FN column inflated / findings=0
  → main loop: parseReviewArtifact(artifact.filePath)         scripts/calibrate-weights.ts:653-654
  → Pattern A: /^###\s+\d+\.\s+\[([^\]]+)\]\s+(.+)/           scripts/calibrate-weights.ts:264   ← new block's `### {Issue title}` has no `{num}. [{category}]`
  →   look-ahead /\*\*File:\*\*\s*`?([^`\n]+)`?/              scripts/calibrate-weights.ts:276   ← new block emits **Location:**, not **File:**
  → Pattern B: /^\d+\.\s+\*{0,2}\[([^\]]+)\]…`?path:line`?/   scripts/calibrate-weights.ts:307-308 ← numbered-bullet shape, also absent
  → findings=[] → proximity match has nothing to hit
  → "FN: human comments not matched by any finding"           scripts/calibrate-weights.ts:417
  → FN drives category-multiplier EMA downward                scripts/calibrate-weights.ts:433, 525-541
```

Fix site (Patterns A/B at `:264`/`:276`/`:307`) is on the path. Also `traced`. (Note: `calibrate-weights.ts` is currently invoked by **no command** — see the sibling EMA-design bug — so path B is latent, but any future wiring of `/calibrate` inherits it.)

### Runtime Evidence

- All 25 `processed-findings.json` files under cog-docs report `lifespan_annotations: 0` (scan 2026-07-09). Corroborating, with a caveat: the artifact set does not record whether `--previous-review` was passed on each run, so the universal zero is consistent with (but not solely provable from) the parser miss; the structural source trace above carries the conclusion.
- PR 16687: `REVIEWED.md` records iteration 18; its `PR-16687.md` is new-format (`**Location:**`, zero `**File:**` tokens); its cache still shows `lifespan_annotations: 0`.

### Related Documentation

- `agents/synthesizer-v2.md:71` documents the Standardized Issue Block as **superseding** "the older heterogeneous per-source shapes (investigation's `**File:** …` subsection and the sweep/reuse/intrafile one-line bullets)" — i.e. the emitters were deliberately migrated while both consumers kept the superseded grammar.
- Plugin `CLAUDE.md` (Scripts section) describes post-process as owning "lifespan annotations" — the feature is advertised but structurally dead on new-format re-reviews.

## Theories

### Theory 1: Emitter format migrated; consumers never updated
- **Hypothesis:** The Standardized Issue Block migration (synthesizer-v2 + buddy Phase 2) changed the on-disk review grammar; `parsePreviousReview` and `parseReviewArtifact` were not in the blast radius checklist and still parse the retired grammar.
- **Supporting evidence:** synthesizer-v2.md:71 explicitly names the old shapes as superseded; both parsers' regexes match exactly those superseded shapes and nothing in the new block.
- **Status:** Confirmed (by source trace).

## Proven Findings

- **CONFIRMED:** `parsePreviousReview` (`post-process.ts:250-305`) cannot extract a single ref from a review written in the Standardized Issue Block format — none of its three patterns match `**Location:** {file}:{line}` — so `step6_annotateLifespan` always reports 0 on new-format re-reviews.
- **CONFIRMED:** `parseReviewArtifact` (`calibrate-weights.ts:231-330`) parses 0 findings from a new-format review (Pattern A requires `### {num}. [{category}]` + `**File:**`; Pattern B requires a numbered bullet with backticked `path:line`), which makes every matched-PR human comment a false negative at `:417` if the script is ever wired up.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Previous-review parser | `scripts/post-process.ts` (250-305, consumed at 497-519, surfaced at 590) | Lifespan/"raised N iterations" tracking silently dead for new-format re-reviews |
| Bulk-calibration parser | `scripts/calibrate-weights.ts` (231-330, FN derivation 417, report 525-541) | Latent: 0 findings parsed → FN-flooded, downward-biased calibration if wired |
| Emitters (grammar owners) | `agents/synthesizer-v2.md` (75, 87, 132-168), `commands/review-pr-buddy.md` (173, 338) | Define the new grammar the parsers don't speak |

## Candidate Root Fixes (for /plan-bug)

1. **Add the `**Location:**` grammar to both parsers** — a fourth pattern in `parsePreviousReview` (`\*\*Location:\*\*\s*`?([^:`\n]+):(\d+)`?` plus `### {Issue title}` title association) and a Pattern C in `parseReviewArtifact`. Cheap, keeps markdown as the interface, but stays regex-fragile against the next format change.
2. **Emit a machine-readable `findings.json` beside `PR-{id}.md`** (synthesizer-v2 + buddy Phase 2 both write it; parsers prefer it and fall back to markdown). Removes the whole drift class; recommended.
3. **Contract test** — a fixture round-trip (emit a Standardized Issue Block review → parse it → assert refs > 0) in the plugin's script tests, so a future grammar migration fails loudly.

## Open Questions

- Should the old `**File:**` patterns be retired once a `findings.json` sidecar exists, or kept for the 15 legacy artifacts still on disk?
- `calibrate-weights.ts` is orphaned (no command invokes it) — fix its parser, or delete the script and fold bulk calibration into the disposition-calibration path? (Decision belongs to the sibling EMA-design bug; keep the two fixes coherent.)
