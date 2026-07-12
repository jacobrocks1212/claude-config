---
kind: investigation-spec
bug_id: execute-plan-ground-truth-missing-git-dirty-assertion
---

# /execute-plan trusts a green test run without asserting the expected files are actually DIRTY (git-stash false-green) — Investigation Spec

> Spun off from the harden-harness round that fixed `lazy-cycle-containment-false-denies-reference-only-routing-mentions` (2026-07-12). SECONDARY-2: an execute-plan work-unit can pass GREEN against OLD committed code because the working tree was silently reverted.

**Status:** Investigating
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/execute-plan-ground-truth-missing-git-dirty-assertion
**Related:** `user/skills/execute-plan/SKILL.md` + the execute-plan ground-truth / verification contract; `user/skills/_components/verification-before-completion` family

---

## Observed Symptom (reported by the originating run)

In cycle-8, a WU-3 implementation agent ran `git stash`, backgrounded a monitor, and ended its turn WITHOUT popping the stash — silently reverting the working tree to the prior work-unit's state. The subsequent test run then passed GREEN against the OLD committed code: a false-green that looks fully verified. The integrator caught it ONLY by manually checking that `git status` showed the expected files dirty.

## Impact

A green test result is treated as proof a work-unit's changes are correct, but the change may not be present in the tree at all (stashed / reverted / never written). The pipeline's ground-truth verification has a gap: green ≠ "the intended edit is live AND passes."

## Candidate Fix (to be decided by /spec-bug)

Harden the `/execute-plan` ground-truth contract to assert, BEFORE trusting a green test run for a work-unit, that the work-unit's expected target files are actually present as changes in `git status` (dirty, or committed in the WU's own commit) — i.e. that the tree reflects the intended edit. A green suite over an unchanged/reverted tree must fail the ground-truth check, not pass.

## Notes

Not fixed inline in the originating round — this is an `/execute-plan` skill-contract change (distinct component from the hook fixed in the originating round) and warrants its own investigation of where in the WU lifecycle the dirty-assertion belongs.
