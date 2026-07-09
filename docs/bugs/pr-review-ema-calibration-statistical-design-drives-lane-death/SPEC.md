# PR-review EMA calibration's statistical design guarantees lane death — Investigation Spec

> The disposition-EMA writer (`disposition-calibration.ts`) applies an unclamped, per-disposition, binary-signal EMA (α=0.25) to a single scalar per source lane — so a lane whose findings map mostly to nits (intrafile by construction) converges to its nit keep-rate, which sits below `post-process.ts`'s 0.3 drop threshold. Lane death is the design's steady state, not an accident; the sibling threshold bug is the symptom surface, this is the generator.

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-09
**Placement:** docs/bugs/pr-review-ema-calibration-statistical-design-drives-lane-death
**Related:** `docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane` (the drop-threshold half — its Open Questions "where does the EMA write, does any clamp apply" are answered here: `disposition-calibration.ts:152-154`, and no clamp exists anywhere); `docs/bugs/pr-review-plugin-cache-split-brain-freezes-weights` (which physical file the writes land in); `docs/bugs/pr-review-pending-calibration-marker-unconsumable-nonbuddy` (the non-buddy signal path); planned feature `docs/features/pr-review-size-aware-pipeline-downshift` (changes finding volume per run, which interacts with per-disposition stepping)

---

## Verified Symptoms

1. **[VERIFIED]** Source weights drifted far below their 0.7 default within ~5 weeks of calibration going live: repo copy reached `investigation: 0.2933 / intrafile: 0.2681` by 2026-07-09 (recorded in the sibling bug), and the 2026-06-30 cache snapshot shows `investigation: 0.1919 / intrafile: 0.3707 / reuse: 0.3938` — confirmed by direct reads of both files.
2. **[VERIFIED]** The drift's downstream effect zeroed whole lanes: the cog-docs artifact audit (this session) found the intrafile lane's findings present in `combined-findings.json` but entirely absent from kept findings in **10 of 25** processed reviews (PR 16816: 34 raw intrafile findings → 0 kept while `dropped_count` reported only 12; six PRs lost the lane with `dropped_count: 0`).
3. **[VERIFIED]** Reporter (Jacob) confirmed the intent-vs-behavior gap: the system "was intended to iteratively align the review plugin's issue surfacing to my own issue surfacing, but it seems to be broken."

## Reproduction Steps

Deterministic, no live PR needed (the writer is a pure function of its three input files):

1. Create a scratch `weights.yaml` with `ema_alpha: 0.25` and `source_weights: {intrafile: 0.7}`; a `processed-findings.json` with 8 intrafile findings (files `f1.ts`…`f8.ts`, line 1 each); a `buddy-session.json` whose one chunk carries 8 dispositions `{finding_ref: "fN.ts:1", source: "intrafile", severity: "dismiss"}`.
2. Run `npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/disposition-calibration.ts --session buddy-session.json --findings processed-findings.json --weights weights.yaml`.
3. Read back `source_weights.intrafile`.

**Expected (design intent):** a bounded adjustment reflecting one PR's worth of evidence; a lane can never be silently priced below the survival threshold by one session.
**Actual:** `0.7 × 0.75⁸ ≈ 0.0751` — one dismiss-heavy chunk (exactly what the buddy escape hatch emits) prices the lane at ~0.08; anything below 0.3 means every future finding from that lane is dropped by `step2_dropBelowThreshold`, and below 0.6 every UNVERIFIED finding is dropped.
**Consistency:** Always — pure arithmetic.

## Evidence Collected

### Source Code — root-cause trace (`traced`)

Serving path from the observed symptom (lane weights drifting to lane-killing values) back to the design choices that produce it; all paths relative to `user/plugins/local-tools/plugins/cognito-pr-review/`:

```
symptom: source_weights.<lane> → 0.19–0.39 over weeks; lane zeroed downstream
  → buddy Phase 2 invokes the writer unconditionally per session   commands/review-pr-buddy.md:390-399
  → one EMA step PER DISPOSITION (loop over every disposition
        of every chunk)                                            scripts/disposition-calibration.ts:211-213, 233-259
  → signal is BINARY, severity-blind:
        toSignal = severity === "dismiss" ? 0.0 : 1.0              scripts/disposition-calibration.ts:148-150
  → update is UNCLAMPED: applyEma = α·s + (1-α)·old,
        no floor/ceiling anywhere in the file                      scripts/disposition-calibration.ts:152-154   ← fix-site 1
  → α = ema_alpha ?? 0.25 (weights.yaml sets 0.25)                 scripts/disposition-calibration.ts:209; knowledge/weights.yaml:4
  → non-sweep dispositions update ONE scalar per lane:
        source_weights[disp.source]                                scripts/disposition-calibration.ts:253-258   ← fix-site 2
  → intrafile findings are mapped to severity "nit" for the
        common verdicts (inconsistent/extend/wrap), so the lane's
        disposition mix is nit-dominated by construction           scripts/post-process.ts:373-387
  → reviewers dismiss nits at high rate (session evidence below)
        ⇒ the lane's EMA equilibrium ≈ its nit keep-rate
  → downstream, the drifted scalar is the base of
        effective_weight = base × confidence                       scripts/post-process.ts:232-246
  → base < 0.3 ⇒ every finding dropped;
        base < 0.6 ⇒ every UNVERIFIED finding dropped              scripts/post-process.ts:171, 223-229, 413-429
```

The fix sites (the EMA update rule and the one-scalar-per-lane routing) are the code that *produces* the drifting value read on the drop path — on the traced path, labeled `traced`. Not runtime-coupled: pure deterministic arithmetic over on-disk inputs.

### Supporting design-flaw inventory (each verified by read)

1. **No clamp/floor anywhere.** `applyEma` (:152-154) is unbounded on [0,1]; the only 0.0–1.0 validation in the system is `/weights` Mode-2 manual `set` (commands/weights.md:118) — which only touches `rule_weights`.
2. **Effective memory ≈ 4 events.** α=0.25 per event ⇒ half-life ln2/ln(4/3) ≈ 2.4 dispositions; from 0.7, three net dismissals cross the death line (0.7 → 0.525 → 0.3938 → 0.2953). The observed cache/repo values (0.1919…0.3938) are exactly what a handful of dismiss-heavy sessions produce.
3. **The buddy escape hatch is a drift accelerator.** "Auto-disposition all remaining findings" (commands/review-pr-buddy.md:220-224) writes an explicit disposition for every remaining finding in one shot — n dismissals = ×0.75ⁿ in one session (8 ⇒ ×0.10). The feature is otherwise correct (explicit verdicts for calibration) — it is the per-disposition stepping that turns it into a cliff.
4. **Severity is not in the signal.** Keeping a Blocking finding and keeping a Suggestion both emit 1.0; dismissing a hallucinated blocker and dismissing a taste-nit both emit 0.0 (:148-150). The scalar cannot distinguish "finds real bugs plus noise" from "wrong".
5. **One scalar per lane conflates verdict classes.** Dismissing an intrafile naming nit lowers the credibility of future CONFIRMED intrafile *duplication* findings equally (:253-258); post-process maps `refactor`/`reuse` → important but `inconsistent`/`extend`/`wrap` → nit (post-process.ts:373-387), so the lane's signal mix is structurally nit-heavy.
6. **`data_points` are tracked but never used.** Incremented for rules (:252), displayed by `/weights` (commands/weights.md:84 region), consumed by no computation; `source_weights` don't even have the field (knowledge/weights.yaml:19-22; `WeightsConfig.source_weights: Record<string, number>` at scripts/disposition-calibration.ts:50). Nobody can tell a 0.29 built on 3 events from one built on 300, and α never anneals.
7. **The most dangerous knob is invisible to the ops command.** `/weights` view/set/reset operates exclusively on `rule_weights` (commands/weights.md:77, :116, :147); `source_weights` appear nowhere in it — post-incident, the operator could not have inspected or repaired the drifted values through the sanctioned surface.
8. **`calibrate-weights.ts` is an orphaned, divergent third writer.** No command invokes it (grep across commands/ + agents/: zero hits). It updates only `category_multipliers` (:436-459) despite `/calibrate`'s prose describing per-rule updates; its `writeWeights` round-trips via `yaml.dump` (:470), which would destroy every comment in weights.yaml (including the sibling bug's warning block) — contradicting `disposition-calibration.ts`'s deliberately comment-preserving surgical writer (:158-190); and it hardcodes machine-specific paths + `REVIEWER_NAME = "Jacob Madsen"` (:19-24). A loaded footgun aimed at the weights file.
9. **A fourth, LLM-executed EMA lives in prose.** `learn-from-pr.md` §2.5.4 (:106-121) instructs the model to do the EMA arithmetic and edit weights.yaml by hand for TP/FP-classified sweep findings — a hand-rolled duplicate of the helper with LLM arithmetic reliability. Its FP definition ("no matching human comment", :103) is downward-biased by construction: humans don't comment on everything a correct finding covers, so equilibrium = human-comment match rate.
10. **Silent no-op for unknown rules.** The rule branch updates only ids already present in weights.yaml (:246); a newly added rule without a weights entry never learns (and sweep's output example uses a fictitious `rule_id`, agents/sweep.md:2115, so imitated ids default to 0.7 forever).

### Runtime Evidence

- Artifact audit (this session): intrafile lane zeroed in 10/25 processed reviews; in reviews where the lane survived (16767, 16769, 16853, 16960) kept intrafile findings carried effective weights 0.35–0.70 — the whole-lane suppression is inconsistent across runs, tracking the weights file's value at run time, not finding quality.
- Session mining: ~34 buddy sessions since 2026-06 — each closing with an unconditional recalibration pass; several used the escape hatch on dismiss-heavy chunks.

### Git History

`knowledge/weights.yaml` header: `last_calibrated: 2026-06-01`, `calibration_prs: [16496]`, `ema_alpha: 0.25` (:1-4). No decay/annealing since; the stopgap floor (repo copy) was applied 2026-07-09 by the sibling investigation.

### Related Documentation

- Plugin `CLAUDE.md` "Closed feedback loop (R2)" — describes the intended align-to-reviewer loop this design fails to implement soundly.
- `docs/specs/weight-calibration-feedback-loop/` (plugin-internal spec dir) — the feature that introduced the disposition EMA.

## Theories

### Theory 1: Lane weight converges to keep-rate, and keep-rate ≠ quality
- **Hypothesis:** With a binary per-disposition signal, EMA equilibrium = the lane's disposition keep-rate; for nit-dominated lanes that rate is naturally below the 0.3/0.6 survival thresholds, so the design converges to lane death regardless of finding correctness.
- **Supporting evidence:** Design-flaw items 4, 5; observed equilibria 0.19–0.39; the lane most nit-mapped (intrafile) is the one most often zeroed (10/25 reviews).
- **Status:** Confirmed (arithmetic + observed values agree).

### Theory 2: Per-disposition stepping (not per-PR) makes single sessions catastrophic
- **Hypothesis:** One EMA step per disposition lets one dismiss-heavy chunk apply ×0.75ⁿ; with per-PR aggregation the same session would be a single bounded step.
- **Supporting evidence:** :211-213/:233-259 loop structure; escape-hatch mechanics; 0.7→0.075 in one 8-dismissal repro.
- **Status:** Confirmed.

## Proven Findings

- **CONFIRMED:** No floor, clamp, or annealing exists on any weight-write path; the sibling bug's Open Question is answered — the writer is `disposition-calibration.ts:152-154` (plus the prose EMA in learn-from-pr.md §2.5.4 and the orphaned calibrate-weights.ts), and none clamps.
- **CONFIRMED:** The EMA's equilibrium for a nit-dominated lane sits below the survival thresholds; combined with the sibling bug's all-sources drop gate, the feedback loop *by design* prices honest lanes out of existence.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Disposition EMA writer | `scripts/disposition-calibration.ts` (:148-154, :209, :211-259) | Unclamped, per-disposition, binary, lane-scalar updates |
| Escape hatch | `commands/review-pr-buddy.md` (:220-224) | Bulk 0-signals in one session |
| Severity mapping | `scripts/post-process.ts` (:373-387) | Makes intrafile nit-dominated → low equilibrium |
| Ops surface | `commands/weights.md` | `source_weights` invisible/unmanageable |
| Orphaned writer | `scripts/calibrate-weights.ts` | Comment-destroying `yaml.dump`, hardcoded paths, uninvoked |
| Prose EMA | `commands/learn-from-pr.md` (§2.5.4, :106-121) | Third implementation, LLM arithmetic, biased FP definition |

## Candidate Root Fixes (for /plan-bug)

1. **Aggregate per PR before stepping** — derive one signal per (lane|rule, PR) = kept/total for that PR's dispositions, apply ONE EMA step per PR. Kills the escape-hatch cliff; a session becomes a bounded update.
2. **Clamp inside `applyEma`** — floor at a named constant shared with `post-process.ts`'s `MIN_EFFECTIVE_WEIGHT` (floor ≥ threshold, e.g. 0.35–0.4, or floor at 0.6 if UNVERIFIED survival is required); single implementation point covers both rule and source branches.
3. **Anneal α by sample size** — add `data_points` to `source_weights` entries and use α = max(0.05, 1/(n+1)) (or similar), so early events don't dominate and stale calibration relaxes.
4. **Split the intrafile signal by verdict class** — separate scalars (or per-verdict keys) for duplication (`refactor`/`reuse`) vs consistency (`inconsistent`) so nit dismissals stop dragging duplication credibility; alternatively weight the signal by disposition severity (Blocking=1.0 … Suggestion≈0.6, dismiss=0).
5. **Expose `source_weights` in `/weights`** — view + set + reset parity with rule_weights, with the same 0.0–1.0 validation and a floor warning.
6. **Delete or rewrite `calibrate-weights.ts`** — either remove it (its category-multiplier calibration is unreachable) or rebuild it on the surgical writer with env-derived paths; never `yaml.dump` the weights file.
7. **Retire the prose EMA** — learn-from-pr §2.5.4 should shell the single helper (serializing its TP/FP classifications into a disposition-shaped input) instead of instructing LLM arithmetic.

Fixes 1–3 are the minimal recurrence-proof set; 4–7 close the remaining soundness gaps. All interact with the sibling threshold fix (`MIN_EFFECTIVE_WEIGHT` scoping) — plan them together.

## Open Questions

- Should reviewer-authored findings (currently skipped, :220 `SKIP_SOURCES`) eventually feed a *positive-only* signal (they indicate misses, not lane quality)?
- Floor policy: shared constant with `MIN_EFFECTIVE_WEIGHT` vs per-source floors (investigation arguably deserves a higher floor than sweep rules)? Decide in /plan-bug alongside the sibling bug's threshold scoping.
