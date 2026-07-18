# PR-Review Re-Review Path Emits Low-Fidelity Metadata — Investigation Spec

> On re-reviews, `/cognito-pr-review:review-pr` produces an iteration-diff that omits genuinely-changed files (and includes unrelated merge churn) and lifespan counters that are numerically absurd — both forcing downstream agents/humans to distrust and manually compensate for the re-review metadata.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-13
**Fixed:** 2026-07-18
**Fix commit:** c3b46699
**Placement:** docs/bugs/pr-review-rereview-low-fidelity-metadata
**Related:** `user/plugins/local-tools/plugins/cognito-pr-review/` (review-pr command + prep-pr.ts, post-process.ts)

<!-- On main at spec time (claude-config default branch); no p/* work branch yet — Branch line omitted per /spec-bug Step 5. -->

---

## Verified Symptoms

Both symptoms were observed directly in this session's live re-review of GitHub PR
`cognitoforms/cognito#16960` (iteration 15; previous reviewed iteration 4). Artifacts persisted at
`cog-docs/docs/features/57077-cognito-pay-account-deletion/.pr-review/pr-cache/16960/`.

1. **[VERIFIED] Bogus lifespan counters.** `processed-findings.json` annotated 16 carried-forward
   findings with `lifespan: { raised_in: 777, total_iterations: 778 }` on a PR that has only 15
   iterations. The synthesizer had to caveat every finding ("counter looks anomalous — treat as
   'recurring', not the literal ratio"). — Confirmed by reading the emitted `processed-findings.json`
   this session; reproduced in the code trace below.

2. **[VERIFIED] Incomplete / mis-scoped incremental iteration-diff.** `iteration-diff.json` for the
   4→15 range **omitted the entire `Cognito/` project** (including `Cognito/CoreService.cs`, rewritten
   +249/−22; `Cognito/Model/Organization.cs`; the net-new `Cognito/Helpers/Attributes/RetainOnArchiveAttribute.cs`;
   `Cognito/Tasks/PurgeOrganizationQueueMessage.cs`) **and all frontend files**, while **including
   unrelated main-branch churn** (billing test-clock, AI form-gen, marketing templates) pulled in by
   merge commit `6af64865706`. The triage agent detected this, declared the diff "demonstrably
   incomplete," and abandoned the documented `reReviewScope` formula (iteration-diff ∪ unresolved-threads),
   re-scoping against the full manifest with `carriedForward: []`. — Confirmed by the prep-script console
   output and the emitted `iteration-diff.json` this session.

3. **[VERIFIED — downstream consequence]** Because the scope signal was untrustworthy, stale
   iteration-4-era findings leaked into the review against rewritten code (e.g. findings referencing the
   old `IsArchived` bool since renamed to `DateArchived`, and findings assuming a lifecycle-event path the
   PR removed). — Observed in `processed-findings.json` (see finding `CoreService.cs:559` referencing
   `!o.IsArchived`; the event-decision finding cluster). This is a *consequence* of symptoms 1+2, not an
   independent root cause.

**Non-impact (bounds the severity):** the review itself still covered every file. `manifest.files` (the
36 reviewed files) is computed from the **base-branch** compare (`prep-pr.ts:351`), which was correct and
did include `Cognito/` + frontend. Only the *re-review scoping* and *lifespan* metadata were wrong, and
triage compensated. Hence P2, not P1.

## Reproduction Steps

### Symptom 1 (lifespan counters)

1. Run `/cognito-pr-review:review-pr <PR>` once. The synthesizer writes `PR-<PR>.md` containing a findings
   JSON footer and/or `raised_in:` lifespan markers.
2. Re-run `/cognito-pr-review:review-pr <PR>` (any re-review), passing `--previous-review PR-<PR>.md` to
   `post-process.ts` (the command does this automatically on re-reviews).
3. Inspect the emitted `processed-findings.json`.

**Expected:** `lifespan.total_iterations` equals the PR's real iteration count; `raised_in ≤ total_iterations`.
**Actual:** `raised_in` is a large number scraped from the previous review's own `raised_in:` markers, and
`total_iterations = raised_in + 1` (e.g. `777 / 778`), unrelated to the real iteration count.
**Consistency:** Always, on any re-review where the previous review file contains a `raised_in:` token or an
"Iteration N" string with N larger than the true iteration.

### Symptom 2 (iteration-diff)

1. On a PR branch whose **latest commit is a merge commit** (branch caught up with `main`), with an existing
   `PR-<PR>-journey.md` carrying `### Iteration N` headers.
2. Run `/cognito-pr-review:review-pr <PR>` (re-review). `computeIterationDiff` resolves
   `previousSha = iterations[N-1]`, `currentSha = iterations[last]`, then calls
   `GET /repos/.../compare/{previousSha}...{currentSha}` (three-dot).
3. Inspect `iteration-diff.json`.

**Expected:** the file set genuinely changed on the PR branch between the last-reviewed state and the current
head.
**Actual:** unrelated main-branch files (merged-in churn) appear; genuinely-changed branch files are omitted.
**Consistency:** Deterministic whenever the head iteration is a merge commit and/or the journey's review-round
number does not coincide with the commit index.

## Evidence Collected

### Source Code

All causal findings below are **`traced`** (static, deterministic; no runtime coupling), each hop cited
`file:line` in `user/plugins/local-tools/plugins/cognito-pr-review/scripts/`.

**Symptom 1 — lifespan trace**

```
processed-findings.json  lifespan: { raised_in: 777, total_iterations: 778 }
  → post-process.ts:654-656   f.lifespan = { raised_in: prevMatch.iteration,
                                             total_iterations: prevMatch.iteration + 1 }
  → post-process.ts:311/322/333  iteration: maxIteration   (every PreviousFindingRef gets maxIteration)
  → post-process.ts:298          maxIteration = max digit from  /(?:Iteration|raised_in)\D*(\d+)/gi
                                 scanned over the PREVIOUS review markdown
```

- **RC-1a (fabricated total).** `total_iterations` is hard-computed as `prevMatch.iteration + 1`
  (`post-process.ts:656`). It is never sourced from the real PR iteration count, which is available at
  `manifest.pr.iterationId` (= 15 here) / `pr-context.json`. The denominator is fiction.
- **RC-1b (self-amplifying scrape).** `maxIteration` (`post-process.ts:298`) is the max integer matched by
  `/(?:Iteration|raised_in)\D*(\d+)/gi` over the previous review file. That regex matches the previous
  review's own embedded `raised_in: N` lifespan markers (and any stray "Iteration N" / large number in the
  synthesizer's JSON footer). Each re-review therefore reads back the *inflated* value it wrote last time and
  writes `raised_in+1` — a monotonic feedback loop divorced from the true iteration number. `777` is that
  accumulated artifact, not a real count.

**Symptom 2 — iteration-diff trace**

```
iteration-diff.json  (Cognito/* + frontend omitted; main churn included)
  → prep-pr.ts:1618-1620  computeIterationDiff(prId, iterationId, previousIterationId, ...)
  → prep-pr.ts:757        comparison = GET /compare/{previousSha}...{currentSha}   (THREE-DOT)
  → prep-pr.ts:749-750    previousSha = iterations[previousIterationId-1].sourceRefCommit.commitId
                          currentSha  = iterations[currentIterationId-1].sourceRefCommit.commitId
  → prep-pr.ts:607-614    getIterations: iterations = /pulls/{pr}/commits mapped to {id: idx+1, sha}
  → prep-pr.ts:805-812    previousIterationId scraped from journey  /### Iteration (\d+)/  (max)
```

- **RC-2a (numbering-space mismatch).** `getIterations` (`prep-pr.ts:607-614`) synthesizes "iterations" from
  the GitHub **commit list** (`/pulls/{pr}/commits`), `id = idx+1`. GitHub PRs have no native iterations. But
  `previousIterationId` is scraped from the journey's `### Iteration N` **review-round** headers
  (`detectReReview`, `prep-pr.ts:805-812`) — an independent counter written by the journey-planner. These two
  numbering spaces are then both used to index the same commit array (`iterations[previousIterationId-1]`,
  `prep-pr.ts:749`). "Review iteration 4" ≠ "4th commit", so the "previously-reviewed commit" anchor is
  mis-identified whenever the two counters diverge (they almost always do once commits ≠ review rounds).
- **RC-2b (three-dot merge-base compare).** Even given correct endpoints, `/compare/a...b` (`prep-pr.ts:757`)
  is GitHub's **three-dot** semantics: it diffs `merge-base(a,b) → b`, not `a → b`. When the head iteration
  (`currentSha`) is a **merge commit** that pulled `main` into the branch (here `6af64865706`), the merge-base
  reaches back before the main merge, so the result is dominated by unrelated main-branch churn and can drop
  genuine branch-only changes that had already "settled" relative to that base. This is the direct mechanism
  for "Cognito/ + frontend omitted, main churn included."

### Runtime Evidence

This session's persisted artifacts (the observed instance):
- `.../16960/iteration-diff.json` — the mis-scoped diff (25 added / 6 removed / 269 modified, dominated by
  merge churn; `Cognito/*` + frontend absent).
- `.../16960/processed-findings.json` — 16 findings carrying `raised_in: 777, total_iterations: 778`.
- prep console output this session: `Computing iteration diff: iteration 4 → 15...`, `Previous iteration from
  journey: 4`, head `Source: p/57077-cog-pay-account-deletion (6af64865)`.

### Git History

Not implicated. The defects are in the long-standing re-review code path, not a recent regression; no fix
attempt precedes this spec.

### Related Documentation

- `docs/bugs/CLAUDE.md` — harness-defect investigation-spec contract (this file follows it).
- `commands/review-pr.md` — documents the intended `reReviewScope = (iteration-diff ∪ unresolved-threads)` and
  the lifespan/`--previous-review` machinery that both root causes undermine.

## Theories

### Theory 1: Lifespan counters are self-amplifying scrape + fabricated denominator — **Confirmed**
- **Hypothesis:** `raised_in` is scraped (via a regex that matches prior `raised_in:` markers) and
  `total_iterations` is fabricated as `+1`, so re-reviews compound.
- **Supporting evidence:** `post-process.ts:298, 654-656`; the real iteration id (15) is available but unused.
- **Contradicting evidence:** none.
- **Status:** Confirmed (traced).

### Theory 2: Iteration-diff is wrong from BOTH a bad anchor and three-dot merge semantics — **Confirmed**
- **Hypothesis:** `previousIterationId` (journey review-round) mis-indexes the commit array (RC-2a), and the
  three-dot compare across a merge commit pollutes/omits the file set (RC-2b).
- **Supporting evidence:** `prep-pr.ts:607-614, 749-757, 805-812`; head commit `6af64865706` is a merge; the
  observed diff contained main churn and omitted branch files.
- **Contradicting evidence:** none; the two root causes are independent and both contribute.
- **Status:** Confirmed (traced).

## Proven Findings

- **RC-1a** `post-process.ts:656` — `total_iterations = prevMatch.iteration + 1` is fabricated; should derive
  from the real PR iteration count (`manifest.pr.iterationId`).
- **RC-1b** `post-process.ts:298` — `/(?:Iteration|raised_in)\D*(\d+)/gi` conflates prior `raised_in:` markers
  with iteration numbers, creating a monotonic feedback loop; `raised_in` is also unbounded by
  `total_iterations`.
- **RC-2a** `prep-pr.ts:749` + `:805-812` — journey review-round number is used to index a commit-derived
  `iterations[]` array (two different numbering spaces); the previously-reviewed commit is mis-identified.
- **RC-2b** `prep-pr.ts:757` — three-dot `/compare/a...b` uses merge-base semantics; wrong when the head
  iteration is a merge commit. Genuine branch changes are dropped; merged-in main churn is included.

## Convergence Targets (existing correct sources the fix should build on)

*(claude-config, not Cognito Forms — no formal Cognito reuse ledger applies. These are the in-repo authoritative
values the buggy code should converge to instead of inventing.)*

| Buggy code | Correct source already available | Verdict |
|---|---|---|
| `total_iterations = iteration+1` (`post-process.ts:656`) | `manifest.pr.iterationId` (real PR iteration = 15) | refactor to read real count |
| `previousIterationId` from journey `### Iteration N` header (`prep-pr.ts:805`) | the actually-reviewed **commit SHA** — persistable in `REVIEWED.md`/journey at review time (REVIEWED.md sentinel already exists; it currently records `pr`+`date` but not the head SHA) | extend the sentinel to record reviewed SHA, anchor the diff on it |
| `/compare/a...b` three-dot (`prep-pr.ts:757`) | GitHub two-dot `a..b`, or a base-relative file-set delta analogous to the correct base-branch compare at `prep-pr.ts:351` | refactor to two-dot / base-relative delta |

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Lifespan annotation | `scripts/post-process.ts:284-335, 643-662` | Absurd `raised_in`/`total_iterations`; self-amplifying across re-reviews |
| Iteration-diff compute | `scripts/prep-pr.ts:607-614, 739-787` | Mis-scoped diff (omits changed files, includes merge churn) |
| Previous-iteration anchor | `scripts/prep-pr.ts:789-823` | Review-round number mis-used as commit index |
| Downstream (not modified) | `agents/triage`, `agents/synthesizer-v2`, `commands/review-pr.md` | Forced to detect and compensate for bad metadata |

## Open Questions (fix-shape decisions — for /plan-bug or /fix)

1. **Previous-reviewed anchor:** persist the reviewed head SHA in `REVIEWED.md` (durable, robust) vs. resolve
   the previous iteration's SHA from the timeline by review-submission time (no schema change, but softer)?
2. **Merge-commit diffs:** two-dot `a..b` is a one-line fix but still diffs *through* a merge; a base-relative
   delta (mirroring `prep-pr.ts:351`) is more robust but larger. Which fidelity bar?
3. **Lifespan semantics:** is per-finding lifespan tracking worth keeping at all, or should it be simplified to
   a boolean "carried-forward" flag given the counters have never been trustworthy?
4. **Regression guard:** add unit tests to `post-process.test.ts` (lifespan) and a fixture-based test for
   `computeIterationDiff` over a merge-commit head, so both root causes are pinned.
