---
kind: investigation-spec
bug_id: execute-plan-ground-truth-missing-git-dirty-assertion
---

# /execute-plan trusts a green test run without asserting the expected files are actually DIRTY (git-stash false-green) — Investigation Spec

> Spun off from the harden-harness round that fixed `lazy-cycle-containment-false-denies-reference-only-routing-mentions` (2026-07-12). SECONDARY-2: an execute-plan work-unit can pass GREEN against OLD committed code because the working tree was silently reverted.

**Status:** Fixed
**Severity:** Medium
**Discovered:** 2026-07-12
**Placement:** docs/bugs/execute-plan-ground-truth-missing-git-dirty-assertion
**Related:** `user/skills/execute-plan/SKILL.md` + the execute-plan ground-truth / verification contract; `user/skills/_components/verification-before-completion` family

---

## Observed Symptom (reported by the originating run)

In cycle-8, a WU-3 implementation agent ran `git stash`, backgrounded a monitor, and ended its turn WITHOUT popping the stash — silently reverting the working tree to the prior work-unit's state. The subsequent test run then passed GREEN against the OLD committed code: a false-green that looks fully verified. The integrator caught it ONLY by manually checking that `git status` showed the expected files dirty.

## Impact

A green test result is treated as proof a work-unit's changes are correct, but the change may not be present in the tree at all (stashed / reverted / never written). The pipeline's ground-truth verification has a gap: green ≠ "the intended edit is live AND passes."

## Investigation (root-cause trace, per `root-cause-trace-gate.md`)

**Serving path — where a green test run gets trusted as proof a WU's edit is live:**

```
"batch is done, proceed" (execute-plan Step B.6 checklist)
  → Step B.2 "Review Batch Output" gate         user/skills/execute-plan/SKILL.md:116-122 (via execution-contract.md)
      → subagent-review.md Step 1.5 "Ground-Truth Verification Gate"   user/skills/_components/subagent-review.md:33-69 (pre-fix)
          item 1: git status --short / wc -l / grep -n, freshly re-run   subagent-review.md:43-46 (pre-fix)
          item 2: "Diff your output against the subagent's pasted block"  subagent-review.md:48 (pre-fix)
          → data source consumed by the gate: the SUBAGENT'S OWN self-report,
            never the plan's declared expected-files list for the WU        write-plan/SKILL.md:307
                  ("Files to create/modify:" per-WU field)
  → Step B.4 Quality Gates (full/partial test suite)                 execution-contract.md:129-134
      → a GREEN result is trusted as "WU done" with no upstream check
        that the WU's declared files are actually present as a diff
```

**The gap, traced not asserted:** I read `subagent-review.md` Step 1.5 in full (pre-fix, lines 33-69) and `execution-contract.md`'s "Per-WU verification gate" section (pre-fix, lines 180-195) end to end. Both encode the SAME two checks: (1) re-run `git status --short`/`wc -l`/`grep -n` fresh, and (2) diff that fresh output against the subagent's own pasted `GROUND-TRUTH OUTPUT` block. That is a **self-consistency** check — it only detects *disagreement between two readings of current git state* (the subagent's paste vs. the orchestrator's fresh re-run). It never reads the WU's plan-declared `Files to create/modify:` list (`write-plan/SKILL.md:307`) or asserts those specific files show as changed. Consequently, if the working tree is silently reverted (an un-popped `git stash`, per the observed symptom) at or before the moment the subagent captures its `GROUND-TRUTH OUTPUT` block (`implementation-agent.md:58` instructs "run these commands... at the end of your work" — nothing forbids a stash occurring around that point, and nothing requires re-capturing after a *revert*, only after further *edits*, `implementation-agent.md:89`), **both** the subagent's pasted `git status --short` and the orchestrator's later fresh `git status --short` read the same reverted (clean) tree — they agree with each other, so the gate records `Ground-truth verified: yes`, even though the WU's declared files reflect zero change. The subsequent Quality Gates test run (`execution-contract.md:129-134`) then runs green against that unchanged tree, and nothing upstream ever asserted "the WU's declared files are actually dirty" — exactly the SPEC's candidate-fix framing.

This is a **static, code(prose)-readable gap** — provable by reading the two components in full and confirming the absence of any cross-check against the plan's declared file list — not a runtime-coupled claim, so no runtime artifact is required to lock it (per root-cause-trace-gate.md's runtime-coupled carve-out, which does not apply here: nothing about *when* the false-agreement occurs depends on live process behavior beyond the already-conceded fact pattern in the Observed Symptom).

**Label:** `traced` — serving-path chain cited file:line above; fix site (subagent-review.md Step 1.5 item 1/new item 2, mirrored in execution-contract.md's Per-WU verification gate) lies squarely on the traced path — it is the exact node that reads git state and renders the `Ground-truth verified:` verdict.

## Root Cause

**Classification:** `verification-gate-checks-self-consistency-not-ground-truth`. The per-WU Ground-Truth Verification Gate (`subagent-review.md` Step 1.5; duplicated in `execution-contract.md`'s "Per-WU verification gate") asserts that the subagent's self-reported `git status`/`wc -l`/`grep -n` output matches an independent fresh re-run of the same commands — but never asserts that the WU's plan-declared expected files actually appear as changes at all. Two readings of a silently-reverted (e.g., stashed-and-not-popped) tree agree with each other trivially, so a WU whose edit never landed (or was reverted before capture) still yields `Ground-truth verified: yes`, and the batch proceeds to trust a green Quality Gates run over unchanged code.

## Fix Scope (Concluded)

Add a **dirty-tree assertion against the WU's declared files**, independent of the subagent's self-report, as a new gate item in both copies of the ground-truth policy:

1. `user/skills/_components/subagent-review.md` Step 1.5 — new item 2 (renumbering items 2-6 to 3-7): for every file on the WU's plan-declared `Files to create/modify:` list (or the subagent's own prose `Files created\modified:` line as fallback), confirm it shows as a change in the fresh `git status --short`, or is present in the WU's own commit (`git show --stat HEAD -- <file>`). A declared file that is clean in both is an automatic `Ground-truth verified: no` — regardless of whether the subagent's self-report agrees.
2. `user/skills/_components/execution-contract.md`'s "Per-WU verification gate" `Default per WU` list — mirror the same check as item 2, pointing at the fuller mechanics in `subagent-review.md`.
3. Extend the "Any mismatch is a falsified report" bullet list and the `Ground-truth verified: no` outcome definition to name this new failure mode explicitly (a WU-declared file with no diff against the pre-batch baseline and absent from the WU's own commit) so it isn't confused with the pre-existing "mismatch" (disagreement-between-reports) outcome.

No hook, state-script, or test-file change is required — this is a skill/component-prose contract change entirely within `user/skills/**` (the SKILLS lane). `execute-plan/SKILL.md` itself needs no edit: it already delegates to `subagent-review.md`/`execution-contract.md` for the gate's mechanics, so fixing those two files fixes every consumer (execute-plan and any other skill that `!cat`-includes the execution contract).

## Notes

Not fixed inline in the originating round — this is an `/execute-plan` skill-contract change (distinct component from the hook fixed in the originating round) and warrants its own investigation of where in the WU lifecycle the dirty-assertion belongs. Investigation concluded and fix implemented 2026-07-12 (this pass).
