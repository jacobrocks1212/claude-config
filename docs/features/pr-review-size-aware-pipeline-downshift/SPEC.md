# PR-Review Size-Aware Pipeline Downshift — Feature Specification

> Make `/cognito-pr-review:review-pr`'s cost scale with the PR: auto-route small PRs to a spot-check-shaped path (keeping sentinels + calibration), floor tiny PRs to one cluster per Step-5b stage, collapse the journey→triage→planner-validate tri-step, stop round-tripping agent outputs through orchestrator context, and scope re-reviews to the iteration diff.

**Status:** Complete
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** yes

**Depends on:** (none)

<!-- Downstream dependees (informational, not authored in this block): pr-review-buddy-phase0-subagent-isolation and pr-review-sweep-rule-sharding-and-read-dedup both declare hard deps on this feature (review-pr.md/sweep.md edit serialization; change (d) is buddy's prerequisite). This feature lands first among the four pr-review items. -->

---

## Executive Summary

The review pipeline's cost is dominated by fixed stage structure, not PR content. Evidence (2026-07-09, 24 full-pipeline reviews in cog-docs + ~40 mined sessions): fan-out scales sub-linearly with PR size — small PRs (<5 files) get 0.84 agents per changed file while large PRs (>16 files) get 0.29; the 39-file PR 16734 drew FEWER agents (5) than the 26-file 16816 (11); a "small" review still burns ~2.3–3.5M fresh input tokens + ~30M cache reads because nothing in `commands/review-pr.md` branches on size — a 2-file PR pays journey (Opus) + triage (Opus) + planner-validate (Opus re-invoke) + sweep (17.8k-token fixed prompt) + clusters + synthesizer. Meanwhile the lightweight `/spot-check` exists but is a separate command the operator must remember, skips the learning loop by design (no REVIEWED.md, no calibration), and routing has been inconsistent in practice (an 18-file PR spot-checked; 2–4-file PRs full-reviewed).

This feature adds six changes, all inside the plugin: **(a)** size-aware auto-routing — review-pr Step 1 reads the manifest's substantive-file count and routes small PRs down a spot-check-shaped path (prep + ≤1 conditional investigation + inline synthesis) that KEEPS the REVIEWED.md sentinel and pending-calibration marker; **(b)** a single-cluster floor for the Step-5b reuse/intrafile stages (≤4 substantive files ⇒ exactly one cluster per stage — cluster agents already handle 1–6 files); **(c)** tri-step collapse — triage's 4 mechanical validation rules move out of a third Opus journey-planner invocation into a triage self-check (+ the journey's File Change Map "Review Priority" column, which already duplicates triage's tier assignment, becomes the small-PR tier source so triage is skipped entirely below the threshold); **(d)** investigation/sweep agents write their own `agent-output/*.json` (reuse/intrafile agents already self-write) and Step 8's post-process stdout goes to a shell redirect — findings stop transiting orchestrator context twice; **(e)** re-review fan-out scopes to `iteration-diff.json` (PR 16687 reached buddy iteration 18, each iteration re-paying full-PR fan-out); **(f)** journey right-sizing — trivial PRs get a compact journey (0-finding PRs today produce 22KB+ journey files larger than their reviews).

Expected effect: small-PR reviews drop from ~7 agents / ~2.3–3.5M fresh tokens to ~2–3 agents, large-PR budget stops being spent re-validating trivia, and the learning loop finally covers small PRs.

## User Experience

- One command for all sizes: `/cognito-pr-review:review-pr <PR>` announces its route up front — e.g. "7 substantive files → full pipeline" or "3 substantive files → downshifted review (spot-check shape, sentinels + calibration kept)". A `--full` flag forces the full pipeline; `--spot` forces the downshift (operator override always wins).
- `/spot-check` remains as-is for explicitly-standalone checks (its no-sentinel/no-calibration guarantees are its identity); the downshifted route is review-pr-native and does NOT change spot-check.
- Buddy mode inherits the routing automatically (its Phase 0 delegates to review-pr Steps 1–8).
- Re-reviews announce scope: "iteration 3 — re-reviewing 4 changed files (iteration diff); 14 unchanged files carried forward."
- Review artifacts keep their formats; a downshifted review's `PR-{id}.md` carries a `**Route:** downshifted (N substantive files)` line for auditability.

## Technical Design

### (a) Size-aware routing (review-pr Step 1.7, new)

After prep, read `{cacheDir}/manifest.json`; count **substantive** files (excluding pure test files, config, generated types — the same exclusion list Step 5b already uses). Routing (locked 2026-07-09: single threshold, silent — see Locked Decisions):

- `substantive ≤ SMALL_MAX` (locked: 5) → **downshifted path**: skip Steps 2–8; run the spot-check shape (inline read of diffs + ≤1 conditional investigation agent per spot-check's Step-4 rule + inline synthesis in synthesizer-v2 format) BUT keep Step 12.6 (REVIEWED.md) and Step 12.7 (pending-calibration marker). Inline findings carry `source:"investigation"`/`"reviewer"` so disposition calibration keeps working.
- otherwise → full pipeline (Steps 2–12) with (b)–(f) applied.

The downshifted path emits a minimal `processed-findings.json` (same schema, produced inline) so buddy mode and `/learn-from-pr` operate uniformly on both routes.

### (b) Single-cluster floor (Step 5b)

Both cluster passes gain: "If ≤4 substantive eligible files, form exactly ONE cluster (per stage)." Today's text caps at 6 clusters but has no floor, so a 3-file PR spanning C#+Vue legitimately clusters into 2×2 agents (verified: `commands/review-pr.md` Step 5b "at most 6 clusters… 1–6 files each" for both passes).

### (c) Tri-step collapse

- The 4 planner-validation rules (`agents/journey-planner.md` "Validation Rules": Rule 1 core-service∧skim, Rule 2 objective-named∧<important, Rule 3 iteration-changed∧skim, Rule 4 majority-skim flag) are mechanical tier checks. Move Rules 1–3 into the **triage agent's own prompt as a mandatory self-check pass** (it has the same inputs: manifest + journey); Rule 4 becomes an orchestrator-inline check (a count over the triage JSON — no agent needed). Step 4 (planner-validate re-invoke) is deleted; Step 6 (escalation evaluation) becomes orchestrator-inline judgment (it rarely fires).
- Below the SMALL_MAX threshold, **triage is skipped entirely**: the journey's File Change Map `Review Priority` column (Critical/Important/Skim — verified duplicate of triage's tiers, `agents/journey-planner.md` File Change Map) is parsed as the tier source. (On the downshifted path neither journey nor triage runs; with the single-threshold scheme locked 2026-07-09 there is no mid band — this journey-column tier source applies only when `--full` forces the full pipeline on a ≤SMALL_MAX PR.)

### (d) Self-written agent outputs + redirected post-process

- `agents/investigation.md` + `agents/sweep.md` gain the same "write your output to `{cacheDir}/agent-output/<name>.json`; your final message is only a one-line confirmation + counts" contract the reuse/intrafile agents already carry (`commands/review-pr.md` Step 5b confirms those self-write). The orchestrator's Step-5 transcription instruction is deleted.
- Step 8 changes from "capture stdout, write to processed-findings.json" to a shell redirect: `npx tsx …/post-process.ts … > {cacheDir}/processed-findings.json`; the orchestrator reads only the summary counts it needs for Step 12 (a small `--summary` stderr line from post-process, or a `jq`-style targeted read).

### (e) Iteration-scoped re-reviews

On re-review (iteration diff present), Steps 3–5b operate on the union of: files in `iteration-diff.json` + files with unresolved threads. Unchanged-and-resolved files skip investigation/cluster passes; their prior findings carry forward via the existing `--previous-review` lifespan machinery. Triage's existing "tier boost for changed + unresolved" note becomes the *scope*, not just a boost.

### (f) Journey right-sizing

Journey-planner gains a size gate: below SMALL_MAX (when the full path was forced on a small PR) or when a PR's objectives map to ≤2 behavioral threads, emit the compact journey form (Overview + Objectives + File Change Map + a Manual Review Guide of ≤2 steps; no padded per-section prose). Guide step count should track thread count, not the ~6–7 ceiling observed regardless of size.

### Files touched

`commands/review-pr.md` (routing step, floor text, Step 4/6 removal, Step 5/8 output contracts, re-review scoping), `agents/triage.md` (self-check pass), `agents/journey-planner.md` (validation section removal, compact form), `agents/investigation.md`, `agents/sweep.md` (self-write contract), `scripts/post-process.ts` (optional `--summary` line). `commands/spot-check.md` untouched.

## Implementation Phases

1. **Phase 1 — Output-contract cleanup ((d)).** Self-write for investigation/sweep; Step-8 redirect. No routing change; verifiable on any PR immediately.
2. **Phase 2 — Tri-step collapse ((c)).** Triage self-check; delete Step 4; inline Step 6; journey compact form ((f)).
3. **Phase 3 — Size routing ((a)) + cluster floor ((b)).** Step 1.7 router + downshifted path (spot-check shape + sentinels + calibration marker + minimal processed-findings.json); floor text in both Step-5b passes. Threshold locked 2026-07-09 (SMALL_MAX=5, silent).
4. **Phase 4 — Iteration-scoped re-reviews ((e)).**

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Small PR downshifts | review-pr on a ≤SMALL_MAX-file PR | Route announcement; ≤1 investigation agent dispatched; REVIEWED.md + pending-calibration.json written | session transcript; `<cogDocsItemDir>/` |
| Large PR unaffected | review-pr on a >SMALL_MAX-file PR | Full pipeline runs; artifacts byte-compatible with today's formats | `{cacheDir}/`, `PR-{id}.md` |
| Single-cluster floor | Full pipeline on a 3–4-substantive-file PR | Exactly 1 reuse + 1 intrafile agent | `{cacheDir}/agent-output/` file count |
| Tri-step collapsed | Any full-pipeline run | No third journey-planner dispatch; triage JSON carries self-check override log | session transcript; triage output |
| No orchestrator transcription | Any full-pipeline run | investigation/sweep outputs on disk without orchestrator Write of their bodies | transcript (no agent-output Write calls) |
| Iteration scoping | Re-review with a small iteration diff | Investigation/cluster dispatch limited to changed+unresolved files | transcript + agent-output file count vs iteration 1 |
| Calibration parity | Downshifted review then /learn-from-pr or buddy dispositions | Weights update runs with no schema errors | disposition-calibration output |

## KPI Declaration

```json
{
  "id": "review-run-fresh-tokens",
  "system": "cognito-pr-review",
  "title": "Fresh input tokens per review run (parent + subagents)",
  "friction": "Fixed stage structure makes a 3-file PR cost what a 30-file PR costs (~2.3-3.5M fresh input tokens + ~30M cache reads), wasting tokens on trivia while under-serving large PRs.",
  "signal": { "source": "session-log-mining", "selector": "review-run-fresh-tokens" },
  "unit": "tokens",
  "direction": "down-is-good",
  "baseline": { "value": 3510000, "captured_at": "2026-07-09", "window": "90d", "provenance": "measured" },
  "band": { "warn": 4500000, "breach": 7000000 },
  "review_by": "2026-10-01",
  "repo_scope": "cognito-forms",
  "notes": "Baseline measured 2026-07-09 via mine-sessions: sum of input_tokens + cache_creation_input_tokens across all assistant turns of the parent session AND its subagents/*.jsonl, for review-pipeline sessions; 7 sessions fully measured, range 0.66M (1-agent buddy) to 6.96M (16-agent buddy), median 3.51M. No automated collector — compute returns NO-DATA until wired; re-measure with the same method. Post-ship, track small-PR (<5 substantive files) runs against this median specifically."
}
```

## Locked Decisions

| # | id | Decision | Decided |
|---|----|----------|---------|
| 1 | downshift-threshold-scheme | Single threshold `SMALL_MAX = 5` substantive files; silent routing (route announced up front, never prompts; `--full`/`--spot` flags override). No two-band mid scheme | 2026-07-09 — Jacob |
| 2 | downshift-calibration-source | Downshifted-path inline findings reuse `source:"investigation"` — no new weights.yaml key while the calibration machinery is under repair (three open bug SPECs) | 2026-07-09 — Jacob |
| 3 | substantive-counter-placement | `prep-pr.ts` emits `substantive_count` in the manifest (deterministic, testable) rather than orchestrator counting per the Step-5b exclusion prose | 2026-07-09 — mechanical, recommended option |

## Open Questions

(none — sequencing with the sibling pr-review features is machine-enforced: `pr-review-sweep-rule-sharding-and-read-dedup` and `pr-review-buddy-phase0-subagent-isolation` both declare hard deps on this feature, so change (d) lands before either consumes it)

## Research References

No Gemini research phase — operator-directed skip; grounded in in-session evidence (2026-07-09): cog-docs artifact corpus (31 reviewed PRs — per-PR agents/aoutKB/files table; small/mid/large buckets 0.84/0.47/0.29 agents-per-file; r(files,agents)=0.77; PR 16734 anomaly; spot-check routing inconsistencies incl. 18-file 16829), session mining (~40 runs; per-session fresh/cache-read/output token accounting incl. 13a32320 "small" = 3.51M fresh / 29.4M cache-read across 8 agents; PR 16687 buddy iteration 18), and the plugin internals audit (no size branching in review-pr.md; Step-5b cluster text; journey-planner Validation Rules 1–4 mechanical; spot-check.md Steps 1/4/5 shape and its deliberate no-sentinel/no-calibration guarantees).
