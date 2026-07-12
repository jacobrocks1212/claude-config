# Step-9 MCP validation peels one defect seam per full pipeline loop — Investigation Spec

> When `/mcp-test` fails, the only route back to validation is BLOCKED → blocked-resolve →
> add-phase → write-plan → execute-plan → mcp-test — a 4–6-Opus-dispatch loop (usually plus a
> multi-minute Rust rebuild) — and because full seam enumeration is mandated only at
> `retry_count >= 2` while every corrective phase is scoped to the single observed failure,
> each re-validation discovers only the NEXT broken seam. Long runs pay the full pipeline
> loop once per seam. This is the dominant observed cost in every long AlgoBooth run.

**Status:** Concluded
**Priority:** P1
**Last updated:** 2026-07-11
**Related:** `docs/specs/lazy-hardening/` (Phase 11 WU-1a/b/c introduced the `retry_count >= 2` escalation this spec re-scopes); `docs/specs/investigation-step/` (owns `/investigate` + the Seam Table contract the escalation consumes); `docs/bugs/stale-runtime-health-200-false-blocked/` (sibling — stale-runtime confounds burn `retry_count` toward the escalation threshold on non-defects, compounding this bug); `docs/features/friction-kpi-registry/` (the fix's KPI home — validation round-trips per feature).

## Verified Symptom

Transcript mining of real AlgoBooth `/lazy-batch` runs (session JSONLs under
`~/.claude/projects/C--Users-Jacob-repos-AlgoBooth/`):

- **Session `e076ed30-8dcf-429a`, `d7-multi-timbral` (turns ~2965–3684, ~720 turns):** 26
  pipeline cycles and **5 corrective phases (Phases 7–11)** for ONE feature; `retry_count`
  walked 0→4; 3 `/investigate` dispatches; ~35 agent dispatches total. The orchestrator's own
  characterization (~turn 2170): *"Each round resolved one layer and revealed the next"*
  (string verified present in the JSONL).
- **Session `5c33b6ba`, `d8-live-looping`:** ~32 of the run's 38 dispatches went to this one
  feature; corrective phases 8→13 were added **one per loop**; the operator extended the cycle
  budget `max-cycles 20 → 32` (turn ~553 — string verified in the JSONL) and the feature
  STILL ended past budget (turn ~1112).
- **Session `e076ed30`, `polyphonic-parameter-modulation` (turns ~2006–2274):** retry 0→3,
  then deferred anyway — three full loops bought no completion.

Each loop is the full route: mcp-test FAIL → `BLOCKED.md` (`blocker_kind: mcp-validation`,
`retry_count` incremented) → blocked-halt resolution → apply-resolution subagent invoking
`/add-phase` → plan dispatch → `/execute-plan` dispatch → `/mcp-test` dispatch — 4–6 Opus
dispatches, usually plus a `dev:restart` Rust rebuild (~3–7 min) before re-validation.

## Root Cause

**Classification: `mis-calibrated contract` (escalation threshold + corrective-phase scoping).**
The seam-enumeration machinery EXISTS today, but it arms two loops too late, and nothing below
the escalation threshold scopes a corrective phase wider than the single observed failure.
Verified in the current tree (2026-07-11, including uncommitted changes):

1. **The escalation predicate fires only at `retry_count >= 2`.**
   `user/scripts/lazy_core.py` — `validation_escalation()` (~line 1089): returns True iff
   `blocker_kind == "mcp-validation"` AND `retry_count >= 2`; `VALIDATION_ESCALATION_SUFFIX`
   (~1083) appends *"ESCALATION: 2+ validation failures — corrective phase requires a
   full-chain seam audit, not a single-layer fix."* to the blocked terminal's notify message.
   Its own docstring concedes the pattern this spec targets: *"the d8-live-looping pattern
   showed each BLOCKED→add-phase round discovering exactly ONE more broken layer."* The
   threshold of 2 means every feature pays two full single-seam loops before enumeration is
   even requested.

2. **`## Seam Enumeration` in BLOCKED.md is authored only at `retry_count >= 2`.**
   - `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (~lines 383–392,
     R14 "SEAM ENUMERATION (escalation…)"): the cycle subagent MUST write the
     `## Seam Enumeration` section (every boundary, `probed-OK`/`probed-FAIL`/`unprobed`)
     **only** *"when writing BLOCKED.md at retry_count >= 2"*.
   - `repos/algobooth/.claude/skills/mcp-test/SKILL.md` (~lines 301–306): same gate — *"At
     `retry_count >= 2` a `BLOCKED.md` with `blocker_kind: mcp-validation` MUST carry a
     `## Seam Enumeration` section"*.
   - At retry 0/1 there is no enumeration requirement at all:
     `user/skills/_components/blocked-resolution.md` step 1 explicitly tolerates a thin body
     (*"a thin body is NOT a malformation halt"*).

3. **The corrective phase is scoped to the single observed failure below the threshold.**
   `user/skills/_components/blocked-resolution.md` ("Add a phase" path, ~lines 121–147) and
   its emitted twin `user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md`
   (~line 89): the new phase's scope is *"the blocker described in BLOCKED.md"*; the
   full-chain seam-audit deliverable (consume `INVESTIGATION.md` + BLOCKED.md's
   `## Seam Enumeration` as the checklist, "Do NOT author a single-layer fix phase") is
   gated behind *"ESCALATION (only when the orchestrator flagged validation-escalation —
   blocker_kind mcp-validation + retry_count >= 2)"*.

Net mechanism: the validation run is the **cheapest possible enumeration point** (the subagent
is already inside the live runtime — cycle-base-prompt.md says so verbatim), but the harness
only asks it to enumerate after two full loops have already been spent, and the corrective
phase authored at retry 0/1 is contractually single-seam. Loop count therefore scales with
seam count, and each loop costs 4–6 dispatches + a rebuild. (The prior fix at threshold 2 —
lazy-hardening Phase 11 WU-1a — was calibrated to stop the *worst* case, not to prevent the
first two peels; the field data above shows the first two peels are where most of the cost is
now paid.)

## Fix Scope (Concluded)

Enumerate at first failure; batch the corrective work; measure round-trips.

1. **Seam enumeration at `retry_count 0` for mcp-validation blockers.** Move the
   `## Seam Enumeration` authoring mandate in `cycle-base-prompt.md` (R14) and
   `repos/algobooth/.claude/skills/mcp-test/SKILL.md` from `retry_count >= 2` to EVERY
   `blocker_kind: mcp-validation` BLOCKED.md: enumerate ALL currently-failing seams **plus any
   obviously-adjacent unwired seams** (the validator is already live in the runtime — probing
   the next boundary costs one tool call, not one pipeline loop). Keep the per-seam
   `probed-OK`/`probed-FAIL`/`unprobed` + one-line-evidence format (unchanged consumers).

2. **Corrective phase batches the enumerated seam set.** In `blocked-resolution.md` +
   `dispatch-apply-resolution.md`, the "Add a phase" path scopes ONE corrective phase to the
   full enumerated seam set (all `probed-FAIL` + `unprobed` rows), not the single observed
   failure — at every retry level, not only under `validation_escalation`. The existing
   escalation clause (INVESTIGATION.md consumption, `<!-- verification-only -->` markers)
   remains as the *additional* rigor layer for repeat failures.

3. **Recalibrate / retain `validation_escalation` as the backstop.** With enumeration at
   retry 0, `retry_count >= 2` becomes the "enumeration itself missed something —
   `/investigate` is now mandatory" tier rather than the first moment enumeration happens.
   `VALIDATION_ESCALATION_SUFFIX` prose and the `validation_escalation()` docstring updated to
   match; lockstep prose==constant tests updated.

4. **Target + KPI:** ≤2 validation round-trips per feature. Register *validation round-trips
   per feature* (count of `blocker_kind: mcp-validation` BLOCKED mints per feature id) in
   `docs/features/friction-kpi-registry/` so the fix's effect is asserted against future runs,
   not assumed.

5. **Coupled-trio mirroring** (`lazy-batch` / `lazy-bug-batch` / `lazy-batch-cloud` keep their
   deltas) + `test_lazy_core.py` coverage for any threshold change + full gates.

## Decisions

- **D1 — Enumerate-at-0 vs lower-threshold-to-1:** enumerate at 0. The enumeration is nearly
  free at validation time (live runtime, one probe per seam) and the field data shows the
  first loop is as wasteful as the third; threshold 1 would still burn one full loop per
  feature to learn what the first validator already knew.
- **D2 — Keep `retry_count >= 2` as the `/investigate` tier (not delete it):** repeated
  failure after a batched seam fix indicates the enumeration was wrong, which is exactly what
  `/investigate`'s hypothesis-ledger discipline exists for. Re-pointing, not removing.
- **D3 — Interaction with the stale-runtime sibling:** land
  `docs/bugs/stale-runtime-health-200-false-blocked/` alongside or before this — stale-runtime
  confounds currently mint fake mcp-validation BLOCKEDs that both inflate `retry_count` and
  would poison a seam enumeration (every seam probes FAIL against a pre-fix binary).
