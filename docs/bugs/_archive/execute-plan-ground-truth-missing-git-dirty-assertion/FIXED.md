---
kind: fixed
bug_id: execute-plan-ground-truth-missing-git-dirty-assertion
date: 2026-07-12
provenance: operator-directed-interactive
validated_via: lint-skills.py --check-projected --check-capabilities; project-skills.py (clean re-projection, spot-checked); lazy_parity_audit.py --repo-root . ; NOT pipeline-gated (__mark_fixed__)
auto_ticked_rows: 0
---

# Completion Receipt

`execute-plan-ground-truth-missing-git-dirty-assertion` marked fixed on 2026-07-12. Root cause:
the per-WU Ground-Truth Verification Gate (`user/skills/_components/subagent-review.md` Step 1.5,
duplicated in `user/skills/_components/execution-contract.md`'s "Per-WU verification gate") only
asserted **self-consistency** — that the subagent's self-reported `git status --short`/`wc -l`/
`grep -n` output matched an independently re-run fresh copy of the same commands. It never
cross-checked either reading against the WU's **plan-declared expected files** (`write-plan/
SKILL.md`'s per-WU `Files to create/modify:` field). Two readings of a silently-reverted tree
(e.g. an un-popped `git stash`) trivially agree with each other, so a WU whose edit never actually
landed still produced `Ground-truth verified: yes`, and the subsequent Quality Gates test run was
trusted as proof-of-correctness even though it ran green against unchanged code.

## What shipped, in this single bug-subagent pass

This bug was investigated, planned, and fixed in one dispatch (no separate `/spec-bug`,
`/plan-bug`, `/execute-plan` invocation) — the SKILLS-lane bug-subagent protocol for this run.

1. **Investigation (SPEC.md):** traced the serving path from "batch proceeds on a green test run"
   back through `execute-plan/SKILL.md`'s Step B.2 delegation to `subagent-review.md` Step 1.5,
   confirmed by reading both `subagent-review.md` and `execution-contract.md` in full that neither
   file's ground-truth check ever reads the plan's per-WU `Files to create/modify:` field — each
   hop cited `file:line`. Labeled `traced` (static/prose-readable, not runtime-coupled). Flipped
   `**Status:**` Investigating → Concluded → Fixed (no provisional fork encountered; the recorded
   root cause matches the SPEC's own candidate-fix framing exactly, so there was no design choice
   to record in a `NEEDS_INPUT_PROVISIONAL.md`).
2. **PHASES.md:** authored a single phase (Phase 1) covering both component edits.
3. **Fix — `user/skills/_components/subagent-review.md` Step 1.5:** inserted a new item 2
   ("Dirty-tree assertion against the WU's DECLARED files") between the existing items 1 and 2,
   renumbering old items 2–6 to 3–7 and updating the file's own internal cross-references ("item 4
   below" → "item 5 below"; "item 1/2 disagrees" → "item 1/2/3 disagrees"). Extended the "Any
   mismatch is a falsified report" list and the `Ground-truth verified: yes`/`no` outcome
   definitions to name the new failure mode.
4. **Fix — `user/skills/_components/execution-contract.md`'s "Per-WU verification gate" → "Default
   per WU" list:** mirrored the same new check as item 2 (old item 2 renumbered to item 3),
   pointing at `subagent-review.md` Step 1.5 item 2 for the full mechanics; updated "These two
   together" → "These three together"; extended the conditional-full-suite-re-run trigger list.

No hook, state-script, or test-file edit was needed or made — this is entirely a skills-lane
(`user/skills/**`) prose-contract fix. `execute-plan/SKILL.md` itself required no edit: it
delegates the gate's mechanics to the two files above via `Read`-from-disk, so fixing them fixes
every consumer (execute-plan, and any other skill/component that pulls in the same gate).

## Symptom reproduction — the concrete before/after contract excerpt

**Before (the gap — `subagent-review.md` Step 1.5, pre-fix):**

```
1. Re-run the cheap integrity commands yourself (default — always) ... git status --short ...
2. Diff your output against the subagent's pasted block. Compare line by line.
```

A WU whose subagent stashed its edit before capturing its `GROUND-TRUTH OUTPUT` block would have
both the subagent's pasted `git status --short` and the orchestrator's later fresh re-run agree on
"clean" — item 1/2 finds no disagreement, `Ground-truth verified: yes`, no assertion anywhere that
the WU's declared files ever changed at all.

**After (the fix — `subagent-review.md` Step 1.5, post-fix, new item 2):**

```
2. Dirty-tree assertion against the WU's DECLARED files (MANDATORY, independent of the
   subagent's report — closes the git-stash false-green gap)... For every file on that list,
   confirm ... it shows as a change in the fresh `git status --short` ... OR ... present in
   the WU's own commit... A declared file showing byte-identical to the pre-batch baseline
   ... is an automatic `Ground-truth verified: no`, even when the subagent's self-report
   agrees the file is unchanged.
```

The same stashed-and-unpopped scenario now fails at item 2 regardless of self-report agreement:
the WU's plan-declared file shows clean in `git status --short` and is absent from any commit →
automatic `Ground-truth verified: no` → verdict `NEEDS-REWORK`. This is the exact class of false
green described in the SPEC's Observed Symptom (cycle-8 WU-3, caught previously only by an
integrator's manual `git status` check) — now caught mechanically by the gate itself, without
relying on a human noticing.

## Gates run

- `python user/scripts/lint-skills.py --check-projected --check-capabilities` → exit 0 ("OK — no
  broken or embedded !cat patterns found"; "OK — no unexpanded !cat patterns in projected output";
  "OK — no capability namespace pollution detected").
- `python user/scripts/project-skills.py` → clean re-projection (`Skills projected (_default): 88`,
  `Errors (_default): none`, all 3 discovered repos re-projected with 0 errors). Spot-checked
  `~/.claude/skills-projected/_default/fix/SKILL.md:928` (a consumer that `!cat`-includes
  `subagent-review.md`) — confirmed the new item 2 text expanded correctly in place, with no
  circular includes.
- `python user/scripts/lazy_parity_audit.py --repo-root .` → exit 0 (neither edited file is in the
  `/lazy*`-family parity manifest; run as a backstop per the bug-subagent workflow, confirms no
  regression to any registered coupled pair).

## Files touched

- `docs/bugs/execute-plan-ground-truth-missing-git-dirty-assertion/SPEC.md` — investigation
  findings + root cause authored; `**Status:**` Investigating → Fixed.
- `docs/bugs/execute-plan-ground-truth-missing-git-dirty-assertion/PHASES.md` — authored (new
  file); single Phase 1, ticked, `**Status:** Fixed`.
- `docs/bugs/execute-plan-ground-truth-missing-git-dirty-assertion/FIXED.md` — this receipt (new).
- `user/skills/_components/subagent-review.md` — Step 1.5 new item 2 + renumbering + outcome-
  definition updates.
- `user/skills/_components/execution-contract.md` — "Per-WU verification gate" → "Default per WU"
  new item 2 + renumbering + conditional-re-run trigger update.

## Cross-lane edits needed but not made

None. The fix is entirely within the SKILLS lane (`user/skills/**`); no hook, state-script, or
`build-queue *.ps1` change is implicated by this root cause.
