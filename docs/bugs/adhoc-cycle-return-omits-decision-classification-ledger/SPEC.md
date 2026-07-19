# Cycle-subagent return summaries omit the mandatory Decision-Classification Ledger — Investigation Spec

> The `/lazy-batch(-bug)` cycle subagent's return summary systematically arrives WITHOUT the mandatory Decision-Classification Ledger, forcing the Step 1d.5 input-audit into its weaker diff-only fallback and silently losing the cycle's own product-decision classification.

**Status:** Fixed
**Severity:** P2
**Discovered:** 2026-07-19
**Placement:** docs/bugs/adhoc-cycle-return-omits-decision-classification-ledger
**Related:** `docs/features/lazy-pipeline-visualizer/LAZY_BATCH_REVIEW_2026-06-16.md` (missing-ledger gap origin), `docs/specs/lazy-decision-gates/`, `user/skills/_components/sentinel-frontmatter.md` (Producer responsibilities #7)

<!-- Status lifecycle:
  - Investigating → active investigation; bug-state.py routes to /spec-bug.
  - Concluded     → root cause traced, fix scope understood; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[REPORTED]** Across one `/lazy-batch` run the Step 1d.5 input-audit flagged **seven times** that the dispatched cycle subagent's return summary carried only a one-line conclusion string and NO Decision-Classification Ledger. — source: `ADHOC_BRIEF.md` (harness-auto-captured from the run).
2. **[REPORTED]** Each time, the audit fell back to the weaker **diff-only audit** (algorithm step 3c) instead of cross-checking the cycle's own classification. — source: `ADHOC_BRIEF.md`.
3. **[REPORTED]** Observed on `spec-bug`, `plan-feature`, and `plan-bug` cycles alike — including `plan-feature`, which DOES carry the ledger mandate — so the gap is in the shared cycle-return contract, not one skill. — source: `ADHOC_BRIEF.md`.

<!-- These are REPORTED (from the auto-captured brief), not independently re-run — but the CAUSAL
     trace below is `traced` in code, which is what the root-cause gate requires. -->

## Reproduction Steps

1. Run `/lazy-batch` (or `/lazy-bug-batch`) with a queue item that reaches a decision-bearing planning cycle (`/spec`, `/spec-phases`, `/plan-feature`, `/spec-bug`, or `/plan-bug`) under `--batch`.
2. The cycle subagent runs its skill, commits, and returns its one-paragraph report per `cycle-base-prompt.md` item 4 ("REPORT").
3. The orchestrator (Step 1d/1d.5) captures the return summary as `{cycle_summary}` and dispatches the input-audit subagent with it.
4. Inspect the input-audit's return: it reports "the cycle subagent's Decision-Classification Ledger was missing" and performs a diff-only audit (step 3c).

**Expected:** The cycle return summary carries the `### Decision-Classification Ledger` section (mandatory under `--batch`), so the input-audit cross-references it against the diff (step 3a/3b — the stronger audit).
**Actual:** The ledger is absent from the return summary, so the audit degrades to diff-only (step 3c) and the cycle's own product-vs-mechanical classification is never verified — it is silently lost.
**Consistency:** Systematic (7/7 on the observed run); structural, not intermittent.

## Evidence Collected

### Source Code

**The authoritative return contract omits the ledger.** `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` item 4 "REPORT" (the return template every batch cycle subagent actually follows) enumerates the required return elements — state advanced, files modified, commit status, `⚖ policy:` lines, and the NEEDS_INPUT disposition — but **never mentions the Decision-Classification Ledger**:

- `cycle-base-prompt.md:575-585` (feature/workstation `@section hard-contract`) — item 4 lists NEEDS_INPUT disposition for "/spec, /spec-phases, /write-plan, /add-phase" but no ledger.
- The cloud `@section hard-contract` variant (`cycle-base-prompt.md:588+`) has the same omission.
- A full-file grep for `Ledger|classification|Decision-Classification` over `cycle-base-prompt.md` returns **zero matches**.

**The ledger mandate lives only inside individual skill bodies** — subordinate to the base return template under batch:

- `user/skills/spec/SKILL.md:117-135` — "Decision-Classification Ledger (MANDATORY return under `--batch` — Phase 1 and Phase 3)" with the table format.
- `user/skills/plan-feature/SKILL.md:114-126` — "same contract as `/spec --batch`".

**The bug-axis planning skills carry no ledger mandate at all** — grep for `[Ll]edger|classification` returns **zero matches** in both:

- `user/skills/spec-bug/SKILL.md` — no ledger mandate.
- `user/skills/plan-bug/SKILL.md` — no ledger mandate.

**The consumer degrades silently and never re-requests.** `user/skills/_components/lazy-batch-prompts/input-audit-prompt.md:70-71` (and `dispatch-input-audit.md:71-72`) step 3c: *"If the ledger was missing or malformed entirely, perform a diff-only audit."* The orchestrator surfaces the miss only as a non-halting T6 deviation line (`user/skills/lazy-batch/SKILL.md:976`: `⚠ /spec --batch cycle returned no Decision-Classification Ledger (contract violation)`) and explicitly does NOT synthesize or re-request one (`lazy-batch/SKILL.md:941`).

### Runtime Evidence

None gathered beyond the auto-captured `ADHOC_BRIEF.md` occurrence count (7×). The causal claim is a **static contract trace** (below), not runtime-coupled — it does not require runtime evidence.

### Git History

Not central to this defect — the gap is a standing contract omission, not a regression from a specific recent commit. The `plan-feature` ledger mandate (`plan-feature/SKILL.md:114`) predates this observation, which is precisely why the "even a skill WITH the mandate drops it" symptom is diagnostic.

### Related Documentation

- `sentinel-frontmatter.md:679-689` — Producer responsibilities #6/#7 (classify every decision; never a silent skip). The ledger is the audit signal that the classification step actually ran.
- `lazy-batch/SKILL.md:941,976` — orchestrator ledger-capture + T6-deviation handling.
- `lazy-bug-batch/SKILL.md:719-746` — Step 1d.5 input-audit runs on `spec-bug`/`spec-phases` bug cycles via the SAME shared `dispatch-input-audit.md` template, so the bug pipeline inherits the identical dependency on a ledger its skills never mandate.

## Theories

### Theory 1: The ledger requirement lives below the authoritative return contract
- **Hypothesis:** The batch cycle subagent's return shape is governed by `cycle-base-prompt.md` item 4 "REPORT"; because that contract omits the ledger, the subagent drops it — even when the invoked skill (`/spec`, `/plan-feature`) mandates it internally. For bug-axis skills the mandate is absent everywhere.
- **Supporting evidence:** (a) `cycle-base-prompt.md` has zero ledger references; (b) `plan-feature` HAS the mandate yet was observed dropping the ledger; (c) `spec-bug`/`plan-bug` have zero mandate; (d) the audit's step-3c fallback proves the consumer sees no ledger.
- **Contradicting evidence:** None found.
- **Status:** **Confirmed** — cause is `traced` (see below).

### Theory 2 (ruled out): One buggy skill, not the shared contract
- **Hypothesis:** A single skill's return template is malformed.
- **Contradicting evidence:** The symptom spans three skills across both pipelines, and one of them (`plan-feature`) has a correct internal mandate. A single-skill cause cannot explain that spread.
- **Status:** **Ruled Out.**

## Proven Findings

**Root cause (`traced`).** The symptom — the input-audit's diff-only fallback — is served by the cycle subagent's return summary, whose shape is dictated by the base return contract, not by the invoked skill's internal ledger mandate. Serving-path trace of the missing-ledger surface back to its source:

```
input-audit runs diff-only (step 3c)                 input-audit-prompt.md:70-71
  → because {cycle_summary} carried no ledger         dispatch-input-audit.md:30 (audit input)
  → {cycle_summary} = the cycle subagent's REPORT     lazy-batch/SKILL.md:941 (orchestrator captures it verbatim)
  → REPORT shape is defined by item 4 "REPORT"        cycle-base-prompt.md:575-585  ← FIX SITE (contract omits the ledger)
  → for spec-bug/plan-bug, no skill-level mandate      spec-bug/SKILL.md, plan-bug/SKILL.md (0 matches)  ← FIX SITE
```

- **`traced` (not `asserted`):** each hop is read in the actual serving code; the fix sites (`cycle-base-prompt.md` item 4, and the `spec-bug`/`plan-bug` return contracts) lie **on** the path that produces the return summary the audit consumes.
- **Not runtime-coupled:** the return contract is prose the subagent follows deterministically; no timing/ordering/environment dependence — a static read certifies it.

**Why `plan-feature` (which has the mandate) still dropped it:** confirms the base contract — not the skill body — is authoritative for the batch return shape. Fixing only the bug skills would leave the feature pipeline's silent-drop path open; the fix must land at the authoritative return contract.

## Recommended Fix Scope

⚖ policy: fix authoritative site + bug skills → most complete path

1. **Primary — make the ledger a hard element of the authoritative return contract.** Add the Decision-Classification Ledger to `cycle-base-prompt.md` item 4 "REPORT" (BOTH the feature/workstation and cloud `@section hard-contract` blocks), scoped to the decision-bearing cycles (`/spec`, `/spec-phases`, `/write-plan`, `/add-phase`, `/plan-feature`, `/spec-bug`, `/plan-bug`): the return summary MUST carry a `### Decision-Classification Ledger` section (or the explicit empty-ledger line), exactly as the NEEDS_INPUT disposition is already mandated there.
2. **Secondary — close the bug-axis mandate gap.** Add the ledger return mandate to `spec-bug/SKILL.md` and `plan-bug/SKILL.md` (mirroring `spec/SKILL.md:117-135` and `plan-feature/SKILL.md:114-126`), so the bug pipeline's own skill bodies match the feature pipeline.
3. **Optional hardening — make the miss checkable, not merely flagged.** Consider having the orchestrator/input-audit treat a missing ledger on a decision-bearing cycle as a stronger signal than a non-halting T6 line — at minimum ensure the diff-only fallback (step 3c) is loudly attributed by skill name (already partially done at `lazy-batch/SKILL.md:976`). A cross-subagent re-request is NOT feasible post-return, so the deterministic win is item 1 (the ledger becomes a required return element the subagent authors before returning).

Note the **coupled-pair obligation:** `cycle-base-prompt.md` is shared across feature/cloud/bug pipelines via `@section` tags, and `spec-bug`↔`spec`, `plan-bug`↔`plan-feature` follow the bug-axis parity contract — `/plan-bug` should scope phases that keep the mirrors in sync and run `lazy_parity_audit.py` after editing.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cycle return contract (authoritative) | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (item 4 REPORT, both hard-contract sections) | Root cause — ledger omitted from the return template the batch subagent follows |
| Bug-axis planning skills | `user/skills/spec-bug/SKILL.md`, `user/skills/plan-bug/SKILL.md` | No ledger mandate at all |
| Feature-axis mandate (reference) | `user/skills/spec/SKILL.md:117-135`, `user/skills/plan-feature/SKILL.md:114-126` | Correct mandate exists but is subordinate to the base contract under batch |
| Consumer (degrades silently) | `input-audit-prompt.md:70-71`, `dispatch-input-audit.md:71-72`, `lazy-batch/SKILL.md:941,976` | Falls back to diff-only; flags T6 only; never re-requests |

## Open Questions

- None blocking. The fix approach (make the ledger a required return element at the authoritative contract site + close the bug-axis gap) is harness-internal and scope-class (no user-visible product behavior); `/plan-bug` will phase it under its Step 0.4 root-cause trace gate, which this concluded SPEC satisfies.
