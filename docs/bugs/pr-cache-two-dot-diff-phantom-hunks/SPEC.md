# PR-review cache synthesizes two-dot diffs, injecting phantom hunks from base-branch drift — Investigation Spec

> `cognito-pr-review` prep reconstructs per-file diffs against the base branch **tip** instead of the merge-base, so any change that landed on `main` after a PR branched leaks into that PR's cached diff as fabricated hunks — and the review agents emit "CONFIRMED" findings about code the PR never touched.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-16
**Placement:** docs/bugs/pr-cache-two-dot-diff-phantom-hunks/
**Related:** `user/plugins/local-tools/plugins/cognito-pr-review/` (prep-pr.ts, review-pr.md, review-pr-buddy.md); discovered during a buddy review of cognitoforms/cognito PR #17053

---

## Verified Symptoms

1. **[VERIFIED]** The cached per-file diffs for PR #17053 contained hunks that do not exist in the real PR — for `CognitoPayLayout.vue` (a `v-if="showPages"` → `v-if="hasPermission"` guard change, removal of a "No Cognito Pay accounts configured." empty state, removal of the `getOnboardedCognitoPayAccounts` import and `cognitoPayAccounts`/`showPages` computeds) and `CognitoPayPayments.vue` (an inline `cognitoPayAccounts = computed(… a.IsActive …)`, i.e. an `IsOnboarded` → `IsActive` predicate switch, plus a `props.cognitoPayAccounts` removal). — Confirmed interactively with the reviewer, then verified against ground truth via `gh pr diff 17053 --repo cognitoforms/cognito`: none of `showPages`, `v-if="hasPermission"`, `getOnboardedCognitoPayAccounts`, `IsActive`, or `"No Cognito Pay accounts configured."` appear anywhere in the real PR. The real changes to both files are telemetry tagging only.
2. **[VERIFIED]** The contamination was *interleaved*, not wholesale: the genuine telemetry hunk (`@@ -109,33 +109,39 @@`, tab `dataAttrs`) was present and correct in the same cached `.diff` alongside the phantom hunks. — Verified by comparing the cached `.diff` to the `gh pr diff` output for the same file.
3. **[VERIFIED]** Downstream review agents treated the phantom hunks as real: four findings were emitted (2 "Important" investigation, 1 intra-file nit, 1 sweep) for `CognitoPayLayout.vue:25`, `CognitoPayPayments.vue:117`, `OrdersTable.vue:214`, `OrdersTable.vue:219` — all describing the non-existent account-sourcing refactor; two were surfaced as "the most important findings in the PR." — Observed directly in the review pipeline output / findings shards.
4. **[VERIFIED]** Only files also modified by a *separate, already-merged* change on `main` were contaminated; files unique to this PR (`telemetry.ts`, `table-filter-utils.ts`, `stringUtils.ts`, `Table.vue`, `AppInsights.ts`) produced clean, accurate diffs and legitimate findings. — Consistent with the root cause below (base-branch drift only affects files the base branch also changed post-branch-point).

## Reproduction Steps

1. Pick a PR whose base branch (`main`) has advanced since the PR branched, where at least one file changed by the PR was **also** changed by a commit merged to `main` after the PR's branch point.
2. Run the `cognito-pr-review` prep on that PR (e.g. `/review-pr <id>` or the Phase-0 delegate of `/review-pr-buddy <id>`), which invokes `prep-pr.ts`.
3. Open the cached diff for such a file: `<cacheDir>/diffs/<path>.diff`.
4. Compare it to `gh pr diff <id> --repo cognitoforms/cognito` filtered to that file.

**Expected:** the cached `.diff` equals the PR's authoritative three-dot diff (`base...head`, merge-base vs head) — only the changes the PR introduced.
**Actual:** the cached `.diff` additionally contains hunks reflecting the *other* changes made on `main` after the branch point (phantom hunks, interleaved with the PR's real hunks).
**Consistency:** deterministic whenever the base branch has drifted on a shared file; invisible when the base branch made no post-branch-point change to any PR file (hence easy to miss).

## Evidence Collected

### Source Code — root cause (traced)

`user/plugins/local-tools/plugins/cognito-pr-review/scripts/prep-pr.ts`:

- Diffs are **synthesized locally** with the `diff` library, not taken from the authoritative GitHub patch — `import { createTwoFilesPatch } from "diff";` (prep-pr.ts:24); emitted at `createTwoFilesPatch(a, b, targetContent, sourceContent, …)` (prep-pr.ts:458).
- `generateDiff(filePath, sourceCommit, targetCommit, …)` fetches `sourceContent = getFileContent(filePath, sourceCommit)` and `targetContent = getFileContent(filePath, targetCommit)` (prep-pr.ts:1447-1448) and diffs the two tip contents.
- The commits: `sourceCommit = pr.lastMergeSourceCommit.commitId` (= `ghPr.head.sha`) and `targetCommit = pr.lastMergeTargetCommit.commitId` (= `ghPr.base.sha`, the **base branch tip**) — prep-pr.ts:1520-1521, 543-544.
- **The defect:** `const mergeBase = targetCommit;` (prep-pr.ts:1564) assigns the base-branch *tip* to `mergeBase`, then `generateDiff(file.path, sourceCommit, mergeBase, …)` (prep-pr.ts:1635) diffs `head` vs `base-tip`. This is a **two-dot** (`base..head`) content comparison, not the **three-dot** (`base...head`, head vs merge-base/common-ancestor) diff that `gh pr diff` produces. The adjacent comment (prep-pr.ts:1633-1634) explicitly intends three-dot ("Use mergeBase (common ancestor) … only changes the PR added on top of the branch point") — the code contradicts its own comment.

Serving-path trace (each hop cited; fix site on path):
```
cached .diff with phantom hunks              <cacheDir>/diffs/<path>.diff
  → fs.writeFileSync(cachedDiffPath, diffContent)          prep-pr.ts:1639
  → diffContent = generateDiff(path, sourceCommit, mergeBase, …)   prep-pr.ts:1635
  → createTwoFilesPatch(targetContent, sourceContent)     prep-pr.ts:1447-1448, 1458
  → mergeBase = targetCommit (= ghPr.base.sha, base TIP)  prep-pr.ts:1564   ← FIX SITE (on path)
```

Cause label: **traced** (not asserted). Not runtime-coupled — it is a deterministic static defect in diff construction, fully established by reading the code + the `gh pr diff` ground-truth comparison.

### Runtime Evidence

`gh pr diff 17053 --repo cognitoforms/cognito` (1152 lines): grep for `showPages`, `v-if="hasPermission"`, `getOnboardedCognitoPayAccounts`, `IsActive`, `"No Cognito Pay accounts configured."` → **zero matches**. The real `CognitoPayLayout.vue` hunk begins at `@@ -109,33 +109,39 @@` (tab `dataAttrs` only); the real `CognitoPayPayments.vue` change is `:row-data-attrs` / `:filter-button-data-attrs` / `withFilterTracking` / `telemetry.loadMoreEventName` / `getRowDataAttrs`.

### Git History

Not a regression from a recent claude-config commit — the two-dot construction is the long-standing shape of `prep-pr.ts`. The bug is latent and only manifests under base-branch drift on a shared file.

### Related Documentation

- The buddy-review session that surfaced this: `../cog-docs/docs/bugs/57826-j/cognito-pay/click-tracking/.pr-review/pr-cache/17053/buddy-session.json` (per-finding INVALID dispositions with the `gh pr diff` verification notes).
- Curated review with the caveat recorded: `../cog-docs/docs/bugs/57826-j/cognito-pay/click-tracking/PR-17053.md`.

## Theories

### Theory 1: Two-dot vs three-dot diff base — CONFIRMED
- **Hypothesis:** `prep-pr.ts` diffs head against the base-branch tip rather than the merge-base, so post-branch-point base changes to shared files appear as phantom hunks.
- **Supporting evidence:** prep-pr.ts:1564 (`mergeBase = targetCommit` = base tip); contradicted by its own comment (1633-1634); only base-drifted files were contaminated (Symptom 4); clean files were unique to the PR.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

### Theory 2 (secondary): Auto-calibration pollution from phantom-finding dismissals — CONFIRMED
- **Hypothesis:** Buddy-mode Phase-2 auto-calibration (`disposition-calibration.ts`, run unconditionally at review close) consumed the dismissals of the four phantom findings and decayed the `investigation` / `intrafile` / `reuse-utility-duplication` source+rule weights on corrupt input.
- **Supporting evidence:** the calibration delta summary from this session decayed `investigation` 0.461→0.384, `intrafile` 0.388→0.35, `reuse-utility-duplication` 0.70→0.525, all driven partly by phantom-finding dismissals.
- **Status:** Confirmed (bounded — one EMA step per lane per PR — but still wrong-signal).

## Proven Findings

- **Root cause:** two-dot diff construction against the base-branch tip (prep-pr.ts:1564) instead of a three-dot diff against the merge-base.
- **Blast radius:** every PR review where the base branch has drifted on a file the PR also changed. The contamination is silent (no error), interleaves with genuine hunks, and drives the review agents to emit high-confidence findings about non-existent code. Local mode (`sourceCommit: "working-tree"`, `targetCommit: baseCommit`, prep-pr.ts:2047-2048) has the same shape and should be checked under the same fix.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Prep / diff synthesis | `scripts/prep-pr.ts` (1564, 1635, 1447-1458, 1520-1521; local-mode 2047-2048) | Root cause — phantom hunks in cached diffs |
| Review agents | `agents/investigation.md`, `agents/sweep.md`, `agents/cognito-intra-file-consistency.md` (consumers of cached diffs) | Emit findings on phantom code; no integrity check on their input |
| Calibration | `scripts/disposition-calibration.ts`; `review-pr-buddy.md` Phase 2 | Weight pollution from corrupt-input dismissals |

## Proposed Fix Directions (for /plan-bug)

1. **Primary — use the authoritative three-dot diff.** Prefer the PR's own patch: either the GitHub compare API `GET /repos/{o}/{r}/compare/{base}...{head}` (three-dot) `files[].patch`, or `gh pr diff`. This removes the local `createTwoFilesPatch` synthesis entirely and guarantees parity with what reviewers see on GitHub. If local synthesis must stay, compute the real merge-base (`compare` response `merge_base_commit.sha`) and diff head against **that**, not `ghPr.base.sha`.
2. **Defense-in-depth — cache integrity check.** After writing cached diffs, reconcile against `gh pr diff` (diffstat / per-file line-count or checksum). On mismatch, fail prep loudly rather than emitting phantom findings silently.
3. **Calibration gate.** Gate Phase-2 auto-calibration on cache integrity being verified, so corrupt-input dismissals cannot pollute `weights.yaml`.

## Open Questions

- Should the fix drop local diff synthesis entirely in favor of the GitHub compare-API patch (simplest, authoritative), or keep synthesis with a corrected merge-base (preserves the large-file/binary handling already in `getFileDiff`)? — a /plan-bug decision.
  - **RESOLVED (fix applied 2026-07-16):** Kept local synthesis with a corrected merge-base. `getMergeBase(baseCommit, headCommit, token)` calls the GitHub compare API `GET /compare/{base}...{head}` and returns `merge_base_commit.sha`; `prepPR` now sets `mergeBase = await getMergeBase(targetCommit, sourceCommit, token)` (was `mergeBase = targetCommit`). This preserves the existing context-line control, binary detection, and large-file diff-only handling in `generateDiff`/`createTwoFilesPatch` while making the per-file diff a true three-dot (`base...head`) comparison against GitHub's own computed common ancestor. Falls back to `baseCommit` (prior behavior) with a warning only if the compare API is unavailable.
- Does local mode (uncommitted working-tree review) exhibit an analogous base-selection issue, or is `baseCommit` there already the intended comparison point? — verify during planning.
  - **RESOLVED (verified 2026-07-16):** Local mode is **correct, no change needed.** `getBaseCommitHash` (prep-pr.ts:311-319) computes `git merge-base HEAD <baseBranch>` — the true common ancestor — and `generateLocalDiff` (prep-pr.ts:412-419) diffs the working tree against that merge-base content. The `targetCommit: baseCommit` in the local manifest (prep-pr.ts:2047-2048) is therefore already the merge-base, not the base-branch tip. Only the GitHub PR path had the two-dot defect.

## Fix directions 2 & 3 (deferred — out of scope for this defect fix)

Direction 2 (post-write reconciliation against `gh pr diff`) and Direction 3 (gate Phase-2 auto-calibration on cache integrity) are defense-in-depth against *other/future* corruption sources. Direction 1 (this fix) closes the confirmed root cause by construction: with correct three-dot diffs, no phantom hunks reach the review agents, so no phantom-finding dismissals can pollute calibration. Directions 2 & 3 remain available as follow-up hardening if a separate corruption vector is observed.
