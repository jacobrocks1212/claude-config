---
name: plan-feature
description: Run spec-phases and write-plan as a single subagent invocation for a feature past the interactive gates (SPEC + RESEARCH_SUMMARY present). Used by /lazy-batch to consolidate planning into one orchestrator round-trip.
argument-hint: <path/to/SPEC.md>
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Write", "Edit", "Agent"]
---

# Plan Feature

Consolidates the two planning skills (`/spec-phases` and `/write-plan`) into one invocation so the autonomous orchestrator can advance a feature from "research integrated" to "ready to execute" in a single round-trip. The skill itself is just dispatch + reporting glue; the actual work is done by `/spec-phases` and `/write-plan`.

**Hard precondition:** the target feature directory MUST contain both `SPEC.md` and `RESEARCH_SUMMARY.md`. If either is missing, refuse with a clear error and STOP — those gates belong to `/spec`, not here.

This skill does NOT invoke `/execute-plan`. Execution is a separate `/lazy` step driven by the state machine, not bundled into planning.

**Post-research positioning:** `/plan-feature` requires `RESEARCH_SUMMARY.md` to exist before running. By the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`, both sub-skills it dispatches (`/spec-phases --batch` and `/write-plan` in batch context) are therefore eligible to write `NEEDS_INPUT.md` with the rich-body convention. `/plan-feature` itself never writes `NEEDS_INPUT.md` — it only surfaces sentinels written by its sub-skills.

---

## Step 0: Resolve Arguments and Preconditions

1. `$ARGUMENTS` must contain a single path to a `SPEC.md`. If not, refuse:

   > `/plan-feature` requires a SPEC.md path. Usage: `/plan-feature <path/to/SPEC.md>`.

2. Resolve:
   - `<spec-md>` = the supplied path
   - `<feature-dir>` = parent directory of `<spec-md>`
   - `<phases-md>` = `<feature-dir>/PHASES.md`
   - `<research-summary>` = `<feature-dir>/RESEARCH_SUMMARY.md`
   - `<plans-dir>` = `<feature-dir>/plans/`

3. Confirm `<spec-md>` exists. If not, refuse with the missing path and STOP.

4. Confirm `<research-summary>` exists. If not, refuse:

   > `/plan-feature` requires RESEARCH_SUMMARY.md alongside the SPEC. Run `/spec` (or `/spec --batch` for Phase 3 finalization) first.

5. Strip `--batch` from `$ARGUMENTS` if present and remember it for downstream dispatch — `/spec-phases` accepts `--batch` and so do all skills this dispatches.

---

## Step 1: Generate Phases (if missing)

Check whether `<phases-md>` exists.

**If it does not exist:** invoke `/spec-phases` in batch mode so the orchestrator does not block on the Step 3 picker:

```
Skill({ skill: "spec-phases", args: "<spec-md> --batch" })
```

After it returns:

1. Check whether `<feature-dir>/NEEDS_INPUT.md` was written. If yes, the red-flag detection in `/spec-phases` halted — print the sentinel's contents and STOP. The orchestrator (`/lazy-batch`) will see the sentinel on its next state-machine cycle and halt.
2. Otherwise confirm `<phases-md>` was created. If not, that's an unexpected failure — print whatever `/spec-phases` reported and STOP.

**If `<phases-md>` already exists:** skip ahead to Step 2 — the planning loop is idempotent.

---

## Step 2: Generate Implementation Plan (if missing)

Inspect `<plans-dir>` for existing implementation plans (files matching `all-phases-*.md` or `phase-*.md`, excluding `retro-*.md` and `realign-*.md`).

**If a plan already exists** AND `<phases-md>` still has unchecked deliverables, nothing to do here — return success with a "plan already exists" note. The next `/lazy` cycle will execute it.

**Otherwise** (no plan, or all existing plans correspond to fully-checked phases): invoke `/write-plan`:

```
Skill({ skill: "write-plan", args: "<phases-md>" })
```

`/write-plan` may produce a single file or multiple `-part-K` files per the 8-WU partition cap (partitioning lives in `/write-plan` Step 2.5). Either way, the script-following orchestrator picks up `plans/<plan>.md` (or `plans/<plan>-part-1.md`) on its next state-machine cycle.

After `/write-plan` returns:

1. Check whether `<feature-dir>/NEEDS_INPUT.md` was written. If yes, halt and surface the sentinel.
2. Otherwise enumerate the plan files that now exist in `<plans-dir>` and remember their paths for the final summary.

---

## Step 3: Summarize and Stop

Print a structured summary so the orchestrator's per-cycle log captures what advanced:

```
## /plan-feature — Done

**Feature:** {feature-id (from spec parent dir name)}
**Spec:** <spec-md>
**Phases:** <phases-md> ({phase-count} phase(s), {unchecked} unchecked deliverables)
**Plans written:**
  - <absolute-path-1> ({wu-count-1} work units)
  - <absolute-path-2> ({wu-count-2} work units)   # if partitioned
**Total work units across parts:** {sum}
**Skipped steps:** {"spec-phases (PHASES.md existed)" | "write-plan (plan existed)" | "none"}
```

**Decision-Classification Ledger (MANDATORY return — same contract as `/spec --batch`).** The cycle MUST also emit, as a structured section of this return summary, the `### Decision-Classification Ledger` that `/spec --batch` mandates — a row for EVERY decision the planning cycle considered (phase boundaries, partition cuts, helper/anchor choices, deferred-to-research items), classified `product-behavior` vs `mechanical-internal`. This makes the Step 1d.5 input-audit subagent not the only safety net: a SPEC-locked decision that quietly collapses during phase/plan authoring (the `lazy-pipeline-visualizer` retro's missing-ledger gap) is caught by the orchestrator's audit against this ledger rather than slipping past prose self-classification. Use the EXACT shape `/spec --batch` defines (see `~/.claude/skills/spec/SKILL.md` "Decision-Classification Ledger"):

```
### Decision-Classification Ledger

| # | Decision (one line) | Classification | Chosen option | Surfaced via | Rationale |
|---|---------------------|----------------|---------------|--------------|-----------|
| 1 | <decision title>    | product-behavior \| mechanical-internal | <option taken or "deferred to user"> | NEEDS_INPUT.md \| auto-accept \| Open Questions | <one-line why> |
```

- Any `product-behavior` row MUST have `Surfaced via: NEEDS_INPUT.md` (or `Open Questions`) — a `product-behavior` + `auto-accept` row is a self-declared contract violation; surface it instead.
- If the cycle made zero decisions, emit the heading + `_(no decisions surfaced this cycle — auto-finalized)_`. The empty ledger is still required.
- The ledger lives in this return summary, NOT in any committed doc — the orchestrator reads it from the response.

If `<feature-dir>/NEEDS_INPUT.md` was written by either sub-skill, surface that path in the summary and STOP.

---

## Notes

- This skill is **NOT** the state script. The state script (`lazy-state.py`) decides whether to call `/plan-feature` at all. `/plan-feature` simply runs `/spec-phases` + `/write-plan` back-to-back when the feature is past the interactive gates.
- This skill is safe to invoke directly by humans on a feature whose SPEC + RESEARCH_SUMMARY are ready and you want both planning steps to run in one shot.
- Plan-file frontmatter (per `~/.claude/skills/_components/plan-frontmatter.md`) is written by the dispatched `/write-plan` invocation — `/plan-feature` does not write any plan files of its own. The downstream lint will see the same `kind: implementation-plan` frontmatter as a direct `/write-plan` run.
- **Anchor discipline (inherited from `/write-plan`):** Every plan this skill produces must satisfy the `[VERIFY: <grep-or-path>]` annotation requirement and the Step 3.5 anchor-existence check defined in `/write-plan`. Since `/write-plan` is dispatched as a subagent, those rules apply inside that invocation — but if you review the returned plan and notice un-annotated "uses existing X" dependencies or cited symbols that look suspect, flag them before returning success. Past examples of plans that rotted because of phantom anchors: `d8-live-looping` (`SampleSource::TrackLoop`, `TrackCommandQueue`), `d8-track-pattern-interaction` (`chainParam` IPC), `transactional-eval` (per-channel `Arc<Pattern>` fields) — all zero-result greps.
