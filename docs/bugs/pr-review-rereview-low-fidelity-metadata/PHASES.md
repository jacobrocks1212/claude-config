# Implementation Phases — PR-Review Re-Review Low-Fidelity Metadata

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress — all three phases implemented (2026-07-18); validation tail pending (gate-owned `__mark_fixed__`).

**MCP runtime:** not-required — the fix is deterministic TypeScript CLI tooling in the `cognito-pr-review` plugin (`scripts/*.ts` run via `npx tsx`, verified by `node:test` fixtures) plus a markdown command-doc schema change. No Tauri desktop / MCP HTTP surface exists to exercise; this is the "build tooling / standalone script" untestable class per `docs/features/mcp-testing/SPEC.md`. Verification is by runnable `node --test` fixture assertions, not MCP.

## Validated Assumptions

All causal findings are **`traced`** (static, deterministic; no runtime coupling) and were re-verified against the live source this planning cycle — each hop matched the SPEC's cited `file:line` exactly:

- **RC-1a/1b (lifespan)** — `post-process.ts:654-656` hard-computes `total_iterations = prevMatch.iteration + 1`; `post-process.ts:298` scrapes `maxIteration` via `/(?:Iteration|raised_in)\D*(\d+)/gi`. Confirmed. The real PR iteration count is available in `main()` at `post-process.ts:717` (`const manifest = loadJSON<Manifest>(manifestPath, "manifest")` → `manifest.pr.iterationId`), directly threadable into `step6_annotateLifespan` (`:640`) / `parsePreviousReview` (`:284`). No new data source needed.
- **RC-2a (anchor)** — `detectReReview` (`prep-pr.ts:789-823`) scrapes `previousIterationId` from journey `### Iteration N` headers (`:805`); `computeIterationDiff` (`:749`) then indexes the commit-derived `iterations[]` array (`getIterations`, `:607-614`, `id = idx+1`) with that review-round number. Two numbering spaces confirmed. `REVIEWED.md` is written at `review-pr.md` Step 12.6 (`:553-574`) and currently records `kind/pr/date/findings counts` but **no head SHA**.
- **RC-2b (three-dot)** — `computeIterationDiff` calls `GET /compare/${previousSha}...${currentSha}` (three-dot, `prep-pr.ts:757`). The correct base-relative pattern already exists in-repo at `prep-pr.ts:352` (`git diff --name-status ${baseBranch}...HEAD`). Confirmed.

**Reachability axiom:** N/A — the fixed "surface" is the emitted `processed-findings.json` / `iteration-diff.json` metadata, which is directly asserted by `node:test` fixtures. There is no user-facing app/serving path whose end-to-end reachability is a runtime-coupled unknown; the GitHub `/compare` two-dot-vs-three-dot behavior is a documented API contract, exercised in tests via recorded/mocked comparison responses.

## Touchpoint Audit (verified: inline — dispatch not used for a read-only 5-file audit)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `scripts/post-process.ts` | yes | `parsePreviousReview()`:284, `step6_annotateLifespan()`:640, `main()`:712 (`manifest` at :717) | refactor | Thread `manifest.pr.iterationId` through `main`→`step6_annotateLifespan`→`parsePreviousReview`; source `total_iterations` from it (`:656`); replace the `maxIteration` scrape (`:298`) so prior `raised_in:` markers no longer feed back; bound `raised_in ≤ total_iterations`. Do NOT invent a new count source. |
| `scripts/post-process.test.ts` | yes | `node:test` suite; `test-fixtures/phase1-*` | extend | Add lifespan regression tests; reuse the existing fixture convention (`test-fixtures/`), add a previous-review fixture containing an inflated `raised_in:` marker. |
| `scripts/prep-pr.ts` | yes | `getIterations()`:607, `computeIterationDiff()`:739, `detectReReview()`:789, base-branch compare :352, call site :1614-1621 | refactor | `detectReReview`: read the reviewed head SHA from `REVIEWED.md` and resolve it to a commit anchor (fall back to today's journey-scrape only when the SHA is absent — older reviews). `computeIterationDiff`: replace the three-dot `/compare/a...b` (`:757`) with a base-relative delta mirroring `:352`. |
| `commands/review-pr.md` | yes | Step 12.6 `REVIEWED.md` write, `:553-574` | refactor | Extend the `REVIEWED.md` frontmatter template to persist the reviewed head SHA (`reviewed_sha:`), sourced from the manifest/prep source commit already in scope at synthesis time. |
| `scripts/prep-pr.test.ts` | **NO (net-new)** | — | create | No prep-pr test exists (only `post-process.test.ts` + `disposition-calibration.test.ts`). Create a fixture-based test for `computeIterationDiff` over a merge-commit head, asserting branch files present / merged-in main churn absent. |

All planned paths are `exists: yes` except `scripts/prep-pr.test.ts` (net-new). No contradiction (anchor- or premise-grade) surfaced — every trace matched live code.

## Fix-shape decisions (from SPEC Open Questions — resolved in-cycle, no product-surface change)

The SPEC's four Open Questions are fix-shape sizing decisions, not user-visible product forks. Each resolves to the most-complete path that preserves the current output surface (completeness-first D7):

- **Q1 anchor** → persist the reviewed head SHA in `REVIEWED.md` (durable; the SPEC's own Convergence-Targets verdict). Phase 2.
- **Q2 merge diffs** → base-relative delta mirroring `prep-pr.ts:352`, not merely two-dot `a..b` (two-dot still diffs *through* a merge). Most-complete correctness bar. Phase 3.
- **Q3 lifespan semantics** → KEEP the existing `{raised_in, total_iterations}` structure and correct its values to real, bounded numbers. Retaining + fixing the field is strictly more complete than dropping to a boolean and changes no consumer contract (the synthesizer keeps rendering the same shape). Simplify-to-boolean would be the product change and is explicitly NOT taken. Phase 1.
- **Q4 regression guards** → each phase ships its own regression test (distributed, not a terminal test phase). Phases 1–3.

## Phase 1: Lifespan Counter Fidelity (RC-1a, RC-1b)

**Scope:** Make `processed-findings.json` lifespan counters real and bounded. Source `total_iterations` from the actual PR iteration count and stop the self-amplifying `raised_in` scrape, so re-reviews no longer compound (`777/778` → real values ≤ the PR's true iteration count). Structure of the `lifespan` object is unchanged.

**Deliverables:**
- [x] Thread `manifest.pr.iterationId` from `main()` (`post-process.ts:717`) into `step6_annotateLifespan` (`:640`) and `parsePreviousReview` (`:284`).
- [x] `total_iterations` sourced from `manifest.pr.iterationId` (real count), replacing `prevMatch.iteration + 1` at `:656`.
- [x] Replace the `maxIteration` derivation (`:298`) so the previous review's own emitted `raised_in:` markers no longer feed back into a new `raised_in` (RC-1b feedback loop broken). `raised_in` is clamped to `≤ total_iterations`.
- [x] Guard the no-previous / missing-`iterationId` paths (existing empty-refs early return at `:645` preserved; a missing `iterationId` degrades to the prior behavior without throwing).
- [x] Tests: `post-process.test.ts` cases — (a) a carried-forward finding gets `total_iterations` equal to the fixture manifest's `pr.iterationId` and `raised_in ≤ total_iterations`; (b) a previous-review fixture containing an inflated `raised_in: 777` marker does NOT produce `raised_in: 777` on the new run (feedback loop closed).

**Implementation Notes (2026-07-18):**
- `Manifest` interface extended with an optional `pr?: { iterationId?: number }`; `main()` passes `manifest.pr?.iterationId` into `step6_annotateLifespan`, which threads it to `parsePreviousReview`.
- `total_iterations = iterationId ?? prevMatch.iteration + 1` (legacy fallback preserved but now bounded); `raised_in = Math.min(prevMatch.iteration, total)` — always ≤ total.
- **RC-1b root fix:** the scrape regex changed from `/(?:Iteration|raised_in)\D*(\d+)/gi` to `/^#{1,6}\s*Iteration\s+(\d+)/gim` — it now reads ONLY structural `Iteration N` round headers, never the review's own emitted `raised_in:`/`total_iterations:` markers (the old alternation also caught `total_iterations` via the `Iteration` substring — both feedback variants closed). Clamped to `≤ total_iterations`.
- **Fixture gotcha (for Phase 2/3 authors):** `parsePreviousReview`'s `titleFilePattern` (`/###\s+(.+)\n.../`) lazily associates the nearest **preceding `###` (h3)** heading as a finding's title. A round header must therefore be `## Iteration N` (h2) so it is not mis-read as a finding title and does not break the title-based match for the first finding. Each finding carries its real `### {title}` (h3) heading in the fixture.
- Files: `scripts/post-process.ts` (Manifest, `parsePreviousReview`, `step6_annotateLifespan`, `main`); tests `scripts/post-process.test.ts` (+3 cases); fixtures `test-fixtures/phase1-manifest-iter.json`, `test-fixtures/phase1-previous-review.md`. Gate: `npx tsx --test post-process.test.ts` → 19 pass / 0 fail.

**Minimum Verifiable Behavior:** `npx tsx --test scripts/post-process.test.ts` (or `node --test`) passes, including the two new lifespan cases; running `post-process.ts` against a fixture whose previous review carries `raised_in: 777` emits a `lifespan` with `total_iterations = <fixture iterationId>` and `raised_in ≤` that value.

**Prerequisites:** None.

**Files likely modified:**
- `scripts/post-process.ts` — thread real iteration count; fix `:298`, `:654-656`.
- `scripts/post-process.test.ts` — lifespan regression cases.
- `scripts/test-fixtures/` — add a previous-review markdown fixture with an inflated `raised_in:` marker (+ a manifest fixture carrying a small real `pr.iterationId`).

**Testing Strategy:** Pure deterministic unit tests over recorded fixtures; no network, no runtime. The RED state is the current `total_iterations = raised_in + 1` behavior; the test asserts real-count semantics and non-amplification.

**Integration Notes for Next Phase:** `manifest.pr.iterationId` is the authoritative real PR iteration count and is available wherever the manifest is loaded — Phase 2 uses the same manifest for the current source commit.

---

## Phase 2: Re-Review Anchor via Persisted Reviewed SHA (RC-2a)

**Scope:** Stop using the journey `### Iteration N` review-round number as a commit-array index. Persist the actually-reviewed head SHA in `REVIEWED.md` at review time, and anchor the incremental diff on that SHA on the next re-review — eliminating the numbering-space mismatch. Journey-scrape remains only as a fallback for pre-existing reviews with no persisted SHA.

**Deliverables:**
- [x] Extend the `REVIEWED.md` frontmatter template in `review-pr.md` Step 12.6 (`:562-573`) with `reviewed_sha: "<head commit SHA>"`, sourced from the source/head commit already resolved during prep/synthesis.
- [x] `detectReReview` (`prep-pr.ts:789`) reads `REVIEWED.md` (sibling of the journey in `cogDocsItemDir`) and returns the persisted `reviewed_sha` as the previous-review anchor when present.
- [x] `computeIterationDiff` / its call site (`prep-pr.ts:1614-1621`) uses the persisted SHA directly as `previousSha` when available, bypassing the `iterations[previousIterationId - 1]` index (`:749`) that mixes numbering spaces. When no `reviewed_sha` is present (legacy `REVIEWED.md`, or none), fall back to the existing journey-scrape path unchanged.
- [x] `ReReviewInfo` (`prep-pr.ts:172-174` / `:278-279`) carries the reviewed SHA alongside `previousIterationId`.
- [x] Tests: `prep-pr.test.ts` (net-new) — a `REVIEWED.md` fixture with `reviewed_sha` makes `detectReReview` return that SHA as the anchor; a legacy `REVIEWED.md` without it falls back to the journey `### Iteration N` scrape (behavior preserved).

**Implementation Notes (2026-07-18):**
- New exported `readReviewedSha(cogDocsItemDir)` parses `reviewed_sha:` from REVIEWED.md's YAML frontmatter (regex, 7–40 hex chars, quote-tolerant; scoped to the leading `---`…`---` block). `detectReReview` is now exported and calls it; `ReReviewInfo` carries `reviewedSha: string | null`.
- Call site (`prepPR`) admits the iteration diff on EITHER the persisted SHA OR a journey `previousIterationId`, and threads `reReviewInfo.reviewedSha` into `computeIterationDiff` as the new optional `previousShaOverride` param — `previousSha = previousShaOverride ?? iterations[previousIterationId - 1]?.…` (legacy index preserved as fallback).
- `review-pr.md` Step 12.6 template now writes `reviewed_sha: "{manifest.pr.sourceCommit}"` (the real reviewed head commit).
- **Enabling refactor:** the CLI entry point (bottom of `prep-pr.ts`) is wrapped in an `isMainModule` guard (`import.meta.url === pathToFileURL(process.argv[1]).href`) so `prep-pr.test.ts` can `import` `detectReReview`/`readReviewedSha` without the module executing its CLI dispatch / `process.chdir` / `process.exit`. Phase 3's `computeIterationDiff` test relies on the same guard.
- Files: `scripts/prep-pr.ts`, `commands/review-pr.md`; net-new `scripts/prep-pr.test.ts`; fixtures `test-fixtures/rereview-with-sha/{REVIEWED.md,PR-101-journey.md}`, `test-fixtures/rereview-legacy/{REVIEWED.md,PR-102-journey.md}`. Gate: `npx tsx --test prep-pr.test.ts` → 5 pass / 0 fail; `tsc --noEmit` clean.

**Minimum Verifiable Behavior:** `npx tsx --test scripts/prep-pr.test.ts` passes: given a fixture `REVIEWED.md` carrying `reviewed_sha: <sha>`, `detectReReview` resolves the previous anchor to `<sha>` (not a journey round number); given one without it, the journey fallback still yields the max `### Iteration N`.

**Prerequisites:** None (independent of Phase 1; shares the manifest but not the lifespan code). Ordered before Phase 3 because Phase 3's diff correctness is only end-to-end meaningful once the anchor is correct, and both touch `prep-pr.ts`.

**Files likely modified:**
- `commands/review-pr.md` — `REVIEWED.md` frontmatter template (add `reviewed_sha`).
- `scripts/prep-pr.ts` — `detectReReview` reads the SHA; `ReReviewInfo` type; call-site anchor selection at `:1614-1621`.
- `scripts/prep-pr.test.ts` — net-new; anchor-resolution cases.
- `scripts/test-fixtures/` — `REVIEWED.md` fixtures (with and without `reviewed_sha`).

**Testing Strategy:** Fixture-driven unit tests exercising `detectReReview`'s file parse and anchor selection; the GitHub `/compare` call itself is mocked/injected (see Phase 3). No live network.

**Integration Notes for Next Phase:** Phase 3 receives a correct `previousSha` from this phase; it must not re-derive the anchor. The two changes compose to produce a correct incremental diff (correct endpoints × correct compare semantics).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` and writes `FIXED.md` once the validation tail passes — this phase never flips status.

---

## Phase 3: Merge-Safe Iteration Diff (RC-2b)

**Scope:** Replace the three-dot `/compare/a...b` merge-base semantics (`prep-pr.ts:757`) — which, when the head iteration is a merge commit that pulled `main`, is dominated by unrelated main-branch churn and drops genuine branch-only changes — with a base-relative file-set delta that reports what actually changed on the PR branch between the previously-reviewed state and the current head.

**Deliverables:**
- [x] Refactor `computeIterationDiff` (`prep-pr.ts:739-787`) to compute a base-relative delta: the set of files changed on the branch up to `currentSha` minus those already changed up to `previousSha`, mirroring the correct base-branch compare pattern at `prep-pr.ts:352`. Merged-in `main` churn (present relative to base at BOTH endpoints) cancels out; genuine branch-only changes are retained.
- [x] Preserve the emitted `IterationDiffData` shape (`filesAdded` / `filesRemoved` / `filesModified`) and the `iteration-diff.json` write (`:782-783`) so downstream `reReviewScope` / triage consumers are unchanged.
- [x] Preserve the existing empty-diff guard (`:752-755`) when either endpoint SHA is unresolved.
- [x] Tests: `prep-pr.test.ts` — a fixture where the head iteration is a merge commit that pulled `main`; assert genuine branch files (e.g. the `Cognito/*` rewrite class from the SPEC repro) appear in the delta and unrelated main-branch churn does NOT.

**Implementation Notes (2026-07-18):**
- `computeIterationDiff` refactored to a base-relative delta. New optional `opts: { baseRef?, fetchCompare? }` param. When `baseRef` is set (call site passes the PR base commit `targetCommit`), it fetches `base...current` and `base...previous` changed-file sets and keeps files whose branch change DIFFERS between the endpoints — compared by per-file blob `sha` (a re-modified file with a changed blob is retained; a file identical at both endpoints, including merged-in `main` churn which a base-relative compare excludes entirely, is dropped). Absent `sha` (older API shape) falls back to presence-at-both-endpoints = unchanged.
- `fetchCompare` is an injectable `(base, head) => Promise<CompareFile[]>` defaulting to a `ghFetch('/compare/base...head')` wrapper — this is the test seam (no live network). `computeIterationDiff` is now exported.
- Legacy fallback (no `baseRef`) preserves the original direct three-dot `previous...current` compare. Empty-diff guard (unresolved endpoint SHA) unchanged. Emitted `IterationDiffData` shape + `iteration-diff.json` write unchanged.
- **Known fidelity bound (accepted, PHASES Q2):** the delta is a changed-file-set difference by blob sha, not a full content re-diff; a file modified identically at both endpoints is treated as unchanged. This is the chosen bar — it excludes merged-in main churn (the reported symptom) while retaining genuine branch re-modifications.
- Files: `scripts/prep-pr.ts` (`computeIterationDiff`, call site); tests `scripts/prep-pr.test.ts` (+3 cases, injected compare stub). Gate: `npx tsx --test *.test.ts` → 37 pass / 0 fail; `tsc --noEmit` clean.

**Minimum Verifiable Behavior:** `npx tsx --test scripts/prep-pr.test.ts` passes the merge-commit-head case: the computed delta includes the branch-only changed files and excludes the merged-in `main` churn that the three-dot compare previously surfaced.

**Prerequisites:** Phase 2 complete (`computeIterationDiff` receives a correct `previousSha` anchor; both endpoints must be right for the base-relative delta to be meaningful).

**Files likely modified:**
- `scripts/prep-pr.ts` — `computeIterationDiff` compare logic (`:757`, endpoint handling).
- `scripts/prep-pr.test.ts` — merge-commit-head fixture case (extends the Phase 2 test file).
- `scripts/test-fixtures/` — recorded/mocked `/compare` responses (branch delta + a merge-polluted three-dot response) to drive the assertion.

**Testing Strategy:** Fixture-driven: inject recorded GitHub `/compare` responses (or a thin fetch shim) so the base-relative computation is asserted deterministically without a live API call. The RED state is the current three-dot behavior surfacing main churn; GREEN is the base-relative delta.

**Integration Notes for Next Phase:** None — this is the last phase. Once it lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending); the state machine routes to the validation tail.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed` and writes `FIXED.md` after the symptom-reproduction gate (SEAM B) confirms the original symptoms — bogus counters and mis-scoped diff — are gone at their reported surfaces (`processed-findings.json`, `iteration-diff.json`).

## Symptom-Reproduction Binding (SEAM B — for completion)

The bug's `## Reproduction Steps` map to the phase tests, so the completion gate has a serving-path regression to bind to:

- **Symptom 1 (bogus lifespan counters)** → Phase 1 tests over `post-process.ts` (the actual serving path that writes `processed-findings.json`).
- **Symptom 2 (mis-scoped iteration-diff)** → Phase 2 + Phase 3 tests over `prep-pr.ts`'s `detectReReview` + `computeIterationDiff` (the actual serving path that writes `iteration-diff.json`).
- **Symptom 3** is a documented *consequence* of 1+2 (stale findings leaking once the scope signal is untrustworthy) — no independent fix; it resolves when 1+2 land.
