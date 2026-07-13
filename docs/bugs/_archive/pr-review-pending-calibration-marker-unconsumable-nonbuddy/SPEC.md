# PR-review pending-calibration marker is unconsumable on the path that writes it — Investigation Spec

> `review-pr.md` Step 12.7 writes `pending-calibration.json` only on the NON-buddy path (buddy never reaches Step 12), but `learn-from-pr.md`'s marker-consume instruction runs the disposition helper against `{cacheDir}/buddy-session.json` — a file only buddy produces. On every marker the mechanism can ever fire for, the helper's first read throws ENOENT: the deferred-calibration loop is broken by construction.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-09
**Placement:** docs/bugs/pr-review-pending-calibration-marker-unconsumable-nonbuddy
**Related:** `docs/bugs/pr-review-ema-calibration-statistical-design-drives-lane-death` (the signal the marker was supposed to defer); `docs/bugs/pr-review-plugin-cache-split-brain-freezes-weights`; `docs/bugs/pr-review-source-weights-drift-zeroes-opus-lane`

---

## Verified Symptoms

1. **[VERIFIED]** The marker is written only where its consumer's input cannot exist: `review-pr.md` Step 12.7 (commands/review-pr.md:508-528) writes `{cacheDir}/pending-calibration.json` on non-buddy completion, and its own "Buddy-safe by construction" note (:524) states buddy never reaches Step 12 — confirmed by reading both command files.
2. **[VERIFIED]** The consumer runs the wrong tool for that input: `learn-from-pr.md` §2.5.7 (:160) says to consume the marker by running "the calibration command above" — the `disposition-calibration.ts --session {cacheDir}/buddy-session.json` invocation (:152-156). A non-buddy cache dir contains no `buddy-session.json`.
3. **[VERIFIED]** The helper hard-fails on that input: `disposition-calibration.ts` does `readFileSync(sessionPath, "utf-8")` unguarded as its first act (scripts/disposition-calibration.ts:197-198) — ENOENT throw, non-zero exit.
4. **[REPORTED]** No successful marker-consume has been observed in session history (the originating session's mining found buddy runs recalibrating inline; the non-buddy → learn-from-pr deferred path has no observed completion) — consistent with, but not individually proven by, the structural break.

## Reproduction Steps

1. Run a non-buddy review to completion: `/cognito-pr-review:review-pr <PR_ID>` (Steps 12.6–12.7 write `REVIEWED.md` and `{cacheDir}/pending-calibration.json`).
2. Confirm the cache dir has the marker but no session file: `ls <cogDocsItemDir>/.pr-review/pr-cache/<PR_ID>/` → `pending-calibration.json` present, `buddy-session.json` absent.
3. Run `/cognito-pr-review:learn-from-pr <PR_ID>` and let it reach §2.5.7's marker-consume instruction, which invokes:
   `npx tsx ~/.claude/plugins/local-tools/plugins/cognito-pr-review/scripts/disposition-calibration.ts --session <cacheDir>/buddy-session.json --findings <cacheDir>/processed-findings.json --weights ~/.claude/plugins/local-tools/plugins/cognito-pr-review/knowledge/weights.yaml`

**Expected:** The deferred calibration runs against whatever signal the non-buddy path produced, updates weights, deletes the marker.
**Actual:** `ENOENT: no such file or directory, open '<cacheDir>/buddy-session.json'` (helper exits 1 at its first read) — or the executing model, seeing the missing file, silently skips the step. Either way no weights update occurs; whether the marker gets deleted is left to model improvisation.
**Consistency:** Always, for every non-buddy review (the only kind that writes the marker).

## Evidence Collected

### Source Code — root-cause trace (`traced`)

Serving path from the symptom (deferred calibration never runs) to the contradiction, each hop `file:line` under `user/plugins/local-tools/plugins/cognito-pr-review/`:

```
symptom: non-buddy reviews produce no weight updates, ever
  → marker written on non-buddy completion only               commands/review-pr.md:508-522
  → buddy provably never writes it ("Buddy-safe by
        construction" — buddy stops after Step 8)             commands/review-pr.md:524; commands/review-pr-buddy.md:47
  → consumer: "run the calibration command above for that
        cache dir, then delete the marker"                    commands/learn-from-pr.md:160          ← fix-site (instruction on path)
  → "the calibration command above" =
        --session {cacheDir}/buddy-session.json               commands/learn-from-pr.md:152-156
  → buddy-session.json is created only by the buddy walk
        (Phase 1 checkpointing)                               commands/review-pr-buddy.md:72, 228-232
  → helper's first read is unguarded:
        readFileSync(sessionPath)                             scripts/disposition-calibration.ts:197-198
  ⇒ for every marker-bearing cache dir, the mandated consume
        command references a file that cannot exist
```

The fix site (learn-from-pr.md's consume instruction, and/or Step 12.7's choice of deferred signal) is on the traced path. Not runtime-coupled — the contradiction is fully visible in the three files' text plus the helper's read.

### What signal COULD the non-buddy path defer?

`learn-from-pr.md` already carries a non-buddy signal source: §2.5.2–2.5.4 (proximity + Haiku semantic judge → TP/FP classification → EMA), which needs only the review artifact `PR-{id}.md` and the exported reviewer comments — both of which exist on the non-buddy path. The marker's plausible intent was "point learn-from-pr at this completed review for §2.5 calibration"; the §2.5.7 wiring instead points it at the buddy-only helper. (Note: §2.5's own parser expectations are format-drifted — see the sibling format-drift bug filed alongside this one, `docs/bugs/pr-review-artifact-format-drift-breaks-lifespan-parsers`, if present — so fixing this marker without fixing the parser still yields zero TP/FP matches.)

### Related Documentation

- Plugin `CLAUDE.md` "Closed feedback loop (R2)": "non-buddy `review-pr.md` instead writes a `{cacheDir}/pending-calibration.json` marker that a later `/learn-from-pr` consumes+clears — so dispositions feed the EMA either inline (buddy) or deferred (non-buddy)". The doc claims a closed loop; the wiring closes it only for buddy.

## Theories

### Theory 1: Copy-paste wiring error when the marker step was added
- **Hypothesis:** Step 12.7 and §2.5.7 were authored as a pair, and §2.5.7's marker paragraph reused the immediately-preceding buddy-session command instead of routing to §2.5's comment-matching calibration (the only signal a non-buddy cache can offer).
- **Supporting evidence:** The buddy-session command sits four lines above the marker paragraph (:152-156 vs :160); the marker payload (pr, cache_dir, date — review-pr.md:514-522) carries exactly what §2.5 needs and nothing the disposition helper needs.
- **Status:** Confirmed as the textual state of the files (authorial intent inferred; the contradiction itself is proven).

## Proven Findings

- **CONFIRMED:** The marker's writer and its consumer disagree on the input contract; on all reachable inputs the consume command references a nonexistent file, so the deferred half of the "closed feedback loop" has never been executable as specified.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Marker writer | `commands/review-pr.md` (:508-528) | Writes a marker no consumer can honor |
| Marker consumer | `commands/learn-from-pr.md` (:145-162, esp. :160) | Mandates the buddy-only helper for non-buddy input |
| Helper | `scripts/disposition-calibration.ts` (:197-198) | Unguarded read; crashes rather than reporting "no session" |

## Candidate Root Fixes (for /plan-bug)

1. **Re-point the consume path at the comment-matching calibration** — §2.5.7's marker paragraph should trigger §2.5.1–2.5.6 (artifact + reviewer-comment TP/FP calibration) for the marker's PR/cache dir, then delete the marker. The disposition-helper invocation stays gated on `buddy-session.json` actually existing. (Smallest fix; matches the marker's payload.)
2. **Give the non-buddy path a disposition-shaped signal** — have `review-pr.md` serialize its §2.5-equivalent output (or synthesizer keep/drop decisions) into a session-shaped file the single helper can consume, keeping "one calibration implementation" literally true for both paths. (Larger; only worth it alongside the EMA-redesign bug.)
3. **Harden the helper regardless** — a missing `--session` file should exit with a clear "no session file — nothing to calibrate (was this a non-buddy cache?)" message rather than a raw ENOENT stack, so mis-wiring surfaces as a diagnosis instead of a crash.

## Open Questions

- Should non-buddy reviews calibrate at all before a human has reacted to the review (the buddy path's signal is human dispositions; §2.5's is human PR comments — the non-buddy marker fires before any human feedback exists)? If the answer is "wait for comments", fix 1 is also the correct *semantic* choice: `/learn-from-pr` runs after review feedback lands.
