---
kind: needs-input
feature_id: generic-execution-surfaces-lack-turn-end-gate
written_by: spec-phases
decisions:
  - Bug's entire fix scope already landed out-of-pipeline — how to disposition
date: 2026-07-18
next_skill: plan-bug
class: product
divergence: contained
---

# /spec-phases --batch — Needs Input

The Touchpoint Audit Gate (Step D, premise-grade contradiction) halted before any
PHASES.md was drafted. The SPEC's core PROVEN premise is now **falsified by the codebase**:
every one of the five fix sites its `## Affected Area / Fix Scope` table prescribes is already
fully implemented — landed by commit `6d2361df` ("harden(skill-prose): add canonical
turn-end-gate component; inject into generic execution surfaces") on **2026-07-13T18:20:55**,
the same day the bug was discovered/concluded, evidently by a `harden-harness` round that never
completed the `__mark_fixed__` → `--archive-fixed` contract. Later commits (`8ce9aa0e` 2026-07-16,
`4197e5d8` 2026-07-17) hardened the same component further.

## Decision Context

### 1. Bug's entire fix scope already landed out-of-pipeline — how to disposition

**Problem:** This bug ("Generic execution surfaces lack a turn-end gate") reported that the
shared/generic execution contracts carried no turn-end gate, unlike the already-covered Cognito
build-queue and lazy-cycle surfaces. Its SPEC PROVEN finding was: *"No generic-contract text
forbids ending a turn on a backgrounded job or an un-consumed inner-agent dispatch."* That is no
longer true. Verified on disk (all five SPEC-scoped fix sites):

- **`user/skills/_components/turn-end-gate.md`** — SPEC marks it `(NEW)`; it **exists** (57 lines),
  the canonical role-neutral gate covering backgrounded jobs, un-consumed inner-agent dispatches,
  bare `enqueued as seq=N`, dispatch-and-AWAIT, and the honest-INCOMPLETE fallback.
- **`execution-contract.md`** — line 181 "Turn-end gate (MANDATORY — RULE 13's policy home)";
  line 185 injects the component via `!cat`; line 168 replaced the stale `results/<seq>.json`
  hand-read with `build-queue-await.ps1` ("Do NOT hand-read `results/<seq>.json`", exit 124 ≠ success).
- **`subagent-launch.md`** — line 33 stale-idiom fixed (build-queue-await, exit-124 echo);
  line 37 turn-end pointer to the component.
- **`execute-plan/SKILL.md` Step 4 item 3** — line 226 generalized past the completion seam to
  inner-agent dispatches + names the component.
- **`subagent-review.md`** — line 7 one-line "dispatch-and-AWAIT / turn-end gate" reinforcement + names the component.

Authoring PHASES.md now would be implementing a falsified spec (planning-time BANNED per the
Touchpoint Audit Gate). I (a cycle subagent) cannot resolve this myself: flipping `**Status:**`
and writing `FIXED.md` are owned exclusively by the orchestrator's `__mark_fixed__` gate, and a
Won't-fix/superseded disposition is an operator judgment. Hence this halt.

**Options:**
- **Complete as Fixed via the out-of-pipeline archive path (Recommended)** — Confirm the landed
  turn-end-gate work resolves the reported symptom (it maps 1:1 to the SPEC's fix scope and its
  Reproduction Steps), then finish the interrupted contract: the orchestrator/operator writes the
  `FIXED.md` receipt and runs `python3 user/scripts/bug-state.py --repo-root . --archive-fixed
  docs/bugs/generic-execution-surfaces-lack-turn-end-gate` (the sanctioned single mover — evidence
  header, `git mv`, queue trim, one commit). Cheapest, honest audit trail, and exactly the remedy
  the `docs/bugs/CLAUDE.md` "Fixing a bug OUT-OF-PIPELINE" section prescribes for a harden-harness
  round that fixed a defect without archiving. No new phases. Reversible.
- **Route through the normal pipeline with a thin verification-only PHASES.md** — Author a single
  phase whose only deliverable is a runtime-verification row asserting the turn-end gate is present
  and injected across the five surfaces, then let `/execute-plan` → the validation tail complete it.
  Preserves "everything completes through the pipeline" uniformity, but manufactures near-empty
  implementation work (the code already exists) and is heavier for no additional correctness.
- **Disposition as Won't-fix (superseded by the harden-harness round)** — Record that commit
  `6d2361df` superseded this bug and close it Won't-fix. Same end state as option A but a weaker
  provenance record — the fix genuinely shipped, so "Fixed" is the more accurate disposition than
  "Won't-fix."

**Recommendation:** Complete as Fixed via the out-of-pipeline archive path — the fix demonstrably
shipped and maps exactly to the SPEC's scope; finishing the receipt + `--archive-fixed` contract is
the honest, lowest-cost close and matches the documented remedy for exactly this "fixed out-of-pipeline,
never archived" case. (Cycle-subagent boundary: I am not permitted to flip `**Status:**` or write
`FIXED.md` — the `__mark_fixed__` gate owns that; hence this is surfaced rather than done.)
