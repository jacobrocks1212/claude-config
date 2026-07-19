# Cycle-subagent return summaries omit the mandatory Decision-Classification Ledger — Implementation Notes

> Per-phase Implementation Notes relocated out of PHASES.md (which stays a thin checklist).

## Phase 1 — Add the ledger to the authoritative return contract (root fix)

#### Implementation Notes (Phase 1)
**Completed:** 2026-07-19
**Work completed:**
- Added a Decision-Classification Ledger requirement to item 4 "REPORT" in BOTH `@section hard-contract` blocks of `cycle-base-prompt.md` (workstation block, item 4 at ~L575–589; cloud block, item 4 at ~L621–638 post-edit). Each addition names the seven decision-bearing cycles (`/spec`, `/spec-phases`, `/write-plan`, `/add-phase`, `/plan-feature`, `/spec-bug`, `/plan-bug`), requires a `### Decision-Classification Ledger` section in the return summary, gives the empty-ledger fallback line `_(no decisions surfaced this cycle — auto-finalized)_`, and states the purpose (lets the Step 1d.5 input-audit run its stronger diff-vs-ledger cross-check instead of the diff-only fallback).
- Placed the new sentence directly after the existing NEEDS_INPUT-disposition mandate (mirroring its shape/tone per the plan's guidance) and before the `/execute-plan`/`/retro(-feature)` test-first confirmation sentence that closes each item-4 block.
**Integration notes:**
- The ledger *table shape* itself is NOT redefined here — it already lives in the skill bodies (`spec/SKILL.md:117-135`, `plan-feature/SKILL.md:114-126`). This phase only makes the base return contract REQUIRE the section on decision-bearing cycles; Phase 2 adds the matching skill-body mandate for the bug axis (`spec-bug`, `plan-bug`), which previously had no ledger mandate at all.
- Both hard-contract blocks (`pipelines=feature,bug modes=workstation` and `pipelines=feature,bug modes=cloud`) were edited identically in substance — only the surrounding lead-in text (`work_branch` push notes) differs, as before.
**Pitfalls & guidance:**
- None encountered. This was a pure additive prose edit; no existing sentence was removed, so no other cross-references to item 4's wording broke.
**Files modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — added the ledger-return requirement to item 4 REPORT in both `@section hard-contract` blocks.
