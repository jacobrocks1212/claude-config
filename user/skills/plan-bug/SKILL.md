---
name: plan-bug
description: Bug-pipeline analog of /plan-feature — ensure PHASES.md exists (author it from the concluded investigation SPEC if missing) and run /write-plan as a single subagent round-trip for a bug past the interactive investigation gate. Drives docs/bugs/ (NOT docs/features/). Closes the gap where a /spec-bug cycle concludes the investigation but never authors PHASES.md, causing bug-state.py to loop on spec-bug. Consumed by /lazy-bug-batch (and /lazy-bug) the way /plan-feature is consumed by /lazy-batch — one consolidating planning round-trip past the interactive gate.
argument-hint: <path/to/SPEC.md>
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Write", "Edit", "Agent"]
---

# Plan Bug

Consolidates the bug pipeline's two planning concerns — **ensure `PHASES.md` exists** and **write the implementation plan** — into one invocation so the autonomous orchestrator can advance a bug from "investigation concluded" to "ready to execute" in a single round-trip. The skill itself is just dispatch + reporting glue; the actual work is done by `/spec-phases` (to author `PHASES.md`) and `/write-plan` (to author the plan).

This is the **bug-pipeline analog of `/plan-feature`**. The mapping is exact except for one structural difference: the bug pipeline has **no research/Gemini/stub step and no separate interactive `/spec-phases` step**. The investigate step (`/spec-bug`) authors the investigation `SPEC.md` directly but **does not author `PHASES.md`** — it transitions to `/fix`. So `/plan-feature`'s `(spec-phases + write-plan)` consolidation maps, for bugs, to: **ensure `PHASES.md` exists (author it from the concluded SPEC if missing) + run `/write-plan`** — as ONE subagent round-trip.

**Why this exists (observed failure mode):** a `/spec-bug` cycle concludes the investigation (SPEC has root-cause / affected-area / proven findings) but never authors `PHASES.md`. `bug-state.py` then re-dispatches `spec-bug` forever because its Step 4 (`SPEC present, no PHASES → spec-bug`) keeps firing. `/plan-bug` closes that gap by guaranteeing a `PHASES.md` **and** a `Ready` plan land in one round-trip, so the next `bug-state.py` cycle advances to `/execute-plan`.

**Hard precondition:** the target bug directory MUST contain `SPEC.md`, and that SPEC's investigation MUST have **concluded** (see Step 0.4). There is **NO `RESEARCH_SUMMARY.md` gate** — bugs undergo no research. If the SPEC is still a bare stub with no root-cause findings, refuse with a clear error and STOP — that's `/spec-bug`'s job, not here.

This skill does NOT invoke `/execute-plan`. Execution is a separate `/lazy-bug` step driven by the state machine, not bundled into planning.

**Post-investigation positioning:** `/plan-bug` runs only once the investigation has concluded. By the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md` (which the bug pipeline reuses verbatim for its post-investigation gate), both sub-skills it dispatches (`/spec-phases --batch` and `/write-plan` in batch context) are eligible to write `NEEDS_INPUT.md` with the rich-body convention. `/plan-bug` itself never writes `NEEDS_INPUT.md` — it only surfaces sentinels written by its sub-skills.

---

## Step 0: Resolve Arguments and Preconditions

1. `$ARGUMENTS` must contain a single path to a `SPEC.md`. If not, refuse:

   > `/plan-bug` requires a SPEC.md path. Usage: `/plan-bug <path/to/SPEC.md>`.

2. Resolve:
   - `<spec-md>` = the supplied path
   - `<bug-dir>` = parent directory of `<spec-md>`
   - `<phases-md>` = `<bug-dir>/PHASES.md`
   - `<plans-dir>` = `<bug-dir>/plans/`
   - `<bug-slug>` = basename of `<bug-dir>` (the bug-directory name, e.g. `BUG-042-foo`)

3. Confirm `<spec-md>` exists. If not, refuse with the missing path and STOP.

4. **Confirm this is a bug.** `/plan-bug` is bug-specific — `<spec-md>` SHOULD live under `docs/bugs/`. If the path does NOT contain `docs/bugs/`, print a warning:

   > ⚠️  `/plan-bug` targets the bug pipeline (`docs/bugs/`), but `<spec-md>` is not under `docs/bugs/`. If this is a feature, use `/plan-feature` instead. Proceeding anyway since a SPEC + PHASES + plan flow is generic.

   Continue (do not STOP) — the planning flow itself is generic; the warning just flags a likely mis-dispatch.

5. Strip `--batch` from `$ARGUMENTS` if present and remember it for downstream dispatch — `/spec-phases` and `/write-plan` both accept `--batch`.

---

## Step 0.4: Confirm the Investigation Concluded

`/plan-bug` plans a fix off a **concluded investigation**, not a stub. Read `<spec-md>` and confirm BOTH:

- **Status gate:** the SPEC's `**Status:**` line is `Investigating` or `Open` (the pre-fix statuses). If it is already `In-progress`, `Fixed`, or `Won't-fix`, this bug is past planning — return success with a "nothing to plan; SPEC status is `{status}`" note and STOP. (`bug-state.py` would not have dispatched `/plan-bug` for a fixed bug; this guard makes the skill safe to invoke directly.)
- **Findings gate:** the SPEC contains enough root-cause / scope content to plan a fix — e.g. a populated `## Affected Area`, `## Proven Findings`, or a theory marked `Likely`/`Confirmed`. A SPEC that is only `## Verified Symptoms` with no affected-area / findings is **still investigating**.

If the findings gate fails, refuse:

> `/plan-bug` needs a concluded investigation: `<spec-md>` has no root-cause findings (no populated Affected Area / Proven Findings / confirmed theory). Run `/spec-bug` further to nail down the root cause before planning a fix. Do NOT fabricate phases from symptoms alone.

STOP. **Never fabricate phases from symptoms alone** — a wrong PHASES.md is worse than none.

---

## Step 1: Generate Phases (if missing)

Check whether `<phases-md>` exists.

**If it does not exist:** the investigation concluded (Step 0.4 passed) but `/spec-bug` left no `PHASES.md` — this is the exact gap `/plan-bug` closes. Invoke `/spec-phases` in batch mode against the bug SPEC so the orchestrator does not block on the interactive phase picker (a bug SPEC is a real spec; reuse `/spec-phases` rather than hand-rolling phase decomposition):

```
Skill({ skill: "spec-phases", args: "<spec-md> --batch" })
```

After it returns:

1. Check whether `<bug-dir>/NEEDS_INPUT.md` was written. If yes, the red-flag detection in `/spec-phases` halted — print the sentinel's contents and STOP. The orchestrator (`/lazy-bug-batch`) will see the sentinel on its next state-machine cycle and resolve it via decision-resume mode.
2. Otherwise confirm `<phases-md>` was created. If not, that's an unexpected failure — print whatever `/spec-phases` reported and STOP.

**If `<phases-md>` already exists:** skip ahead to Step 2 — the planning loop is idempotent.

---

## Step 2: Generate Implementation Plan (if missing)

Inspect `<plans-dir>` for existing implementation plans (files matching `all-phases-*.md`, `phase-*.md`, or `fix-*.md`, excluding `retro-*.md` and `realign-*.md`).

**If a plan already exists** AND `<phases-md>` still has unchecked deliverables, nothing to do here — return success with a "plan already exists" note. The next `/lazy-bug` cycle will execute it.

**Otherwise** (no plan, or all existing plans correspond to fully-checked phases): invoke `/write-plan`:

```
Skill({ skill: "write-plan", args: "<phases-md>" })
```

`/write-plan` may produce a single file or multiple `-part-K` files per its partition cap. Either way, the script-following orchestrator picks up `plans/<plan>.md` (or `plans/<plan>-part-1.md`) on its next state-machine cycle.

After `/write-plan` returns:

1. Check whether `<bug-dir>/NEEDS_INPUT.md` was written. If yes, halt and surface the sentinel.
2. Otherwise enumerate the plan files that now exist in `<plans-dir>` and remember their paths for the final summary.

---

## Step 3: Summarize and Stop

Print a structured summary so the orchestrator's per-cycle log captures what advanced:

```
## /plan-bug — Done

**Bug:** {bug-slug (from spec parent dir name)}
**Spec:** <spec-md>
**Phases:** <phases-md> ({phase-count} phase(s), {unchecked} unchecked deliverables)
**Plans written:**
  - <absolute-path-1> ({wu-count-1} work units)
  - <absolute-path-2> ({wu-count-2} work units)   # if partitioned
**Total work units across parts:** {sum}
**Skipped steps:** {"spec-phases (PHASES.md existed)" | "write-plan (plan existed)" | "none"}
```

If `<bug-dir>/NEEDS_INPUT.md` was written by either sub-skill, surface that path in the summary and STOP.

---

## Notes

- This skill is **NOT** the state script. The state script (`bug-state.py`) decides whether to call `/plan-bug` at all. `/plan-bug` simply ensures `PHASES.md` exists and runs `/write-plan` back-to-back when the bug is past the interactive investigation gate. (Today, `bug-state.py` dispatches `/spec-phases` and `/write-plan` as separate cycles; `/plan-bug` is the consolidating wrapper a future `bug-state.py` step — or a human — can call to collapse those two cycles into one round-trip, exactly as `/plan-feature` does for the feature pipeline.)
- This skill drives `docs/bugs/` (NOT `docs/features/`). Status vocab: `Open | Investigating | In-progress | Fixed | Won't-fix`. It NEVER sets SPEC `**Status:**` to `Fixed` or `Won't-fix` — the terminal flip is the orchestrator's `__mark_fixed__` archive-on-fix action, gated by the validation tail.
- This skill does NOT call `interview_work_log_append` — its sub-skills do, and a wrapping log entry would be noise. The orchestrator (`/lazy-bug-batch`) logs the dispatch-level view.
- This skill is safe to invoke directly by humans on a bug whose investigation has concluded and you want both planning steps to run in one shot.
- Plan-file frontmatter (per `~/.claude/skills/_components/plan-frontmatter.md`) is written by the dispatched `/write-plan` invocation — `/plan-bug` does not write any plan files of its own. For a bug, `feature_id:` is the bug-directory slug and `kind:` is `implementation-plan` (or `fix-plan` if `/write-plan` runs in fix mode); `status:` is `Ready` on a clean run. The downstream lint sees the same frontmatter contract as a direct `/write-plan` run.
