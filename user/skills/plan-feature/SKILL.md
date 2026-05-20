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

`/write-plan` may produce a single file or multiple `-part-K` files per the 8-WU partition cap (see `~/.claude/skills/_components/sentinel-frontmatter.md` — wait, that's the sentinel file; partitioning lives in `/write-plan` Step 2.5). Either way, the script-following orchestrator picks up `plans/<plan>.md` (or `plans/<plan>-part-1.md`) on its next state-machine cycle.

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

If `<feature-dir>/NEEDS_INPUT.md` was written by either sub-skill, surface that path in the summary and STOP.

---

## Notes

- This skill is **NOT** the state script. The state script (`lazy-state.py`) decides whether to call `/plan-feature` at all. `/plan-feature` simply runs `/spec-phases` + `/write-plan` back-to-back when the feature is past the interactive gates.
- This skill does NOT call `interview_work_log_append` — its sub-skills do, and a wrapping log entry would be noise. The orchestrator (`/lazy-batch`) logs the dispatch-level view.
- This skill is safe to invoke directly by humans on a feature whose SPEC + RESEARCH_SUMMARY are ready and you want both planning steps to run in one shot.
