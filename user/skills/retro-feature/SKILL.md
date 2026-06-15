---
name: retro-feature
description: Run the Step 9 retro phase end-to-end as a single subagent invocation. Loops /retro + /execute-plan until RETRO_DONE.md is on disk, a BLOCKED.md / NEEDS_INPUT.md halt fires, or max-rounds is reached. Mirrors /plan-feature's composition shape — consolidates a multi-cycle state-machine phase into one orchestrator round-trip.
argument-hint: <path/to/feature-dir-or-SPEC.md> [--max-rounds N] [--batch]
plan-mode: never
allowed-tools: ["Read", "Glob", "Grep", "Bash", "Write", "Edit", "Agent"]
---

> **DORMANT — unwired from the lazy autonomous pipeline 2026-06; retained for manual use and restore. The pipeline no longer dispatches this step.**

# Retro Feature

Composes `/retro` and `/execute-plan` into a single dispatch so the autonomous orchestrator (or a human) can drive a feature's entire retro phase (Step 9) in one round-trip instead of N state-machine cycles. The skill itself is dispatch + sentinel-check glue; the actual work is done by `/retro` (which writes a `retro-N-*.md` plan and — per its Step 6c — emits `RETRO_DONE.md` when no significant divergences remain) and `/execute-plan` (which ships any corrective work the retro identified).

**Why this exists:** `/lazy-batch`'s default Step 9 path is `/retro` → `/execute-plan retro-N.md` → `/retro` → ..., one skill per orchestrator cycle. Each cycle pays the full cost of a fresh Opus subagent dispatch and a state-script round-trip. This composed skill collapses the loop into a single subagent's context so a feature whose retro needs 2–3 internal rounds advances in 1 orchestrator dispatch instead of 3–5.

**Hard preconditions:**
- The feature dir MUST contain `SPEC.md` and `PHASES.md`.
- The Step 9 entry gate MUST be satisfied: `VALIDATED.md` OR `DEFERRED_NON_CLOUD.md` exists in the feature dir. If neither does, refuse with a clear error — Step 8 (MCP gate) hasn't been reached yet.
- If `RETRO_DONE.md` already exists, this is a no-op — return success immediately with "retro already done" in the summary.

**Not a replacement for `/retro`.** This skill exists for the multi-round case. A human running a single retrospective pass should still invoke `/retro` directly. Use `/retro-feature` when you want the entire phase resolved end-to-end (typically: `/lazy-batch` consolidation, or a human catching up after the corrective work landed in a previous session).

---

## Step 0: Resolve Arguments and Preconditions

1. **Parse `$ARGUMENTS`.** Expected shape: `<path> [--max-rounds N] [--batch]`.

   - `<path>` — either a feature directory or a `SPEC.md` inside one. Required. If empty, refuse:

     > `/retro-feature` requires a feature dir or SPEC.md path. Usage: `/retro-feature <path/to/feature-dir> [--max-rounds N] [--batch]`.

   - `--max-rounds N` — positive integer cap on retro loop iterations (one iteration = one `/retro` run + at most one `/execute-plan` run). Default: `3`. If omitted, use default; if non-numeric or `< 1`, refuse.
   - `--batch` — autonomous-mode flag. Passed through to `/retro` as `--batch`. Strip from args before parsing the positional path.

2. **Resolve paths:**
   - `<feature-dir>` — if `<path>` ends in `SPEC.md`, use its parent dir; otherwise treat `<path>` as the feature dir directly.
   - `<spec-md>` = `<feature-dir>/SPEC.md`
   - `<phases-md>` = `<feature-dir>/PHASES.md`
   - `<plans-dir>` = `<feature-dir>/plans/`
   - `<feature-id>` = basename of `<feature-dir>`

3. **Verify preconditions:**

   | Check | Action on failure |
   |-------|-------------------|
   | `<spec-md>` exists | Refuse: "no SPEC.md found at `<feature-dir>` — `/retro-feature` requires an existing feature". STOP. |
   | `<phases-md>` exists | Refuse: "no PHASES.md found — run `/spec-phases` first". STOP. |
   | `<feature-dir>/BLOCKED.md` absent | Refuse: "BLOCKED.md present — resolve the blocker before re-running retro". STOP. |
   | `<feature-dir>/NEEDS_INPUT.md` absent | Refuse: "NEEDS_INPUT.md present — resolve the decision halt before re-running retro". STOP. |
   | `<feature-dir>/VALIDATED.md` OR `<feature-dir>/DEFERRED_NON_CLOUD.md` exists | Refuse: "Step 9 entry gate not satisfied — neither VALIDATED.md nor DEFERRED_NON_CLOUD.md exists. Run `/lazy` to advance Step 8 first". STOP. |

4. **Idempotent short-circuit.** If `<feature-dir>/RETRO_DONE.md` already exists, parse its frontmatter, print:

   ```
   ## /retro-feature — Already Done
   **Feature:** {feature-id}
   **RETRO_DONE.md present:** rounds={N}, retro_plans={[...]}, mcp_validation_status={...}

   Nothing to do — retro phase already terminated cleanly.
   ```

   STOP. Do NOT delete or modify the existing sentinel.

5. **Initialize loop state:**
   - `round = 0`
   - `max_rounds = <parsed or default 3>`
   - `batch_flag = "--batch"` if the flag was present (or the skill is invoked from another `--batch` context), else `""`. **Default to `--batch` when in doubt** — this skill is most useful in autonomous contexts, and `/retro` in interactive mode would ask `AskUserQuestion`s that defeat the purpose of consolidation. The only time `batch_flag` should be empty is an explicit human-driven multi-round retro where they want the option to bail out interactively.
   - `round_log = []` — each entry: `{round, retro_plan_written, execute_plan_run, outcome}`

---

## Step 1: Round Loop

Repeat the following until a terminal condition is reached:

### 1a. Pre-round sentinel check

Before each round, re-check sentinels (the previous round's `/retro` or `/execute-plan` may have written one):

| Sentinel | Outcome |
|----------|---------|
| `<feature-dir>/RETRO_DONE.md` exists | Loop terminates successfully — jump to Step 2 with `terminal = "retro-done"`. |
| `<feature-dir>/BLOCKED.md` exists | Halt — jump to Step 2 with `terminal = "blocked"` and surface the sentinel's `phase` / `blocker_kind` / `recovery_suggestion`. |
| `<feature-dir>/NEEDS_INPUT.md` exists | Halt — jump to Step 2 with `terminal = "needs-input"`. The sentinel was written by the inner `/retro --batch` (post-research halting rule allows it at Step 9). Surface the writer skill and decision-context path. |

### 1b. Max-rounds cap

If `round >= max_rounds`:

```
⚠️  /retro-feature hit max-rounds ({max_rounds}) without RETRO_DONE.md.
```

Jump to Step 2 with `terminal = "max-rounds"`. Surface every retro plan written across the rounds and the per-round outcomes — the human (or the orchestrator's next cycle) needs the audit trail to decide whether to extend or escalate.

### 1c. Run `/retro` (round N+1)

Invoke the retro skill:

```
Skill({ skill: "retro", args: "<feature-dir>/PHASES.md {batch_flag}" })
```

Notes on argument shape:
- Pass `PHASES.md` (not the feature dir) so `/retro`'s Step 1 resolves scope identically to its state-machine invocation in `lazy-state.py` Step 9.
- Pass `--batch` whenever `batch_flag` is set (per Step 0 default) so `/retro` skips its Step 5 clarifying-questions step and its Step 1 `AskUserQuestion` fallback.

After `/retro` returns:

1. **Check `<feature-dir>/RETRO_DONE.md`.** `/retro`'s Step 6c writes this when the round concluded with no significant divergences. If it now exists → loop terminates successfully on the next iteration's Step 1a (don't short-circuit here; the 1a re-check is the canonical decision point).
2. **Check `<feature-dir>/NEEDS_INPUT.md`.** `/retro --batch` writes this on a genuine design-choice halt. If present, the next 1a will halt — don't dispatch `/execute-plan` against an unresolved decision.
3. **Check `<feature-dir>/BLOCKED.md`.** If `/retro` itself wrote it (rare — would be a `blocker_kind: pre-research-input-required` analog), halt on next 1a.
4. **Enumerate `<plans-dir>/retro-*.md`** to find the plan `/retro` just wrote. The newest one by leading number (`retro-N-slug.md`) is the one to execute next. Record its path as `latest_retro_plan` in `round_log`.

   - If `/retro` wrote `RETRO_DONE.md` (case 1), there may or may not be a new retro plan on disk (Step 6b ran before 6c — there is one). Either way, do NOT execute it; the sentinel says we're done.
   - If neither `RETRO_DONE.md` nor a new retro plan exists, that's an unexpected `/retro` failure. Append `{round: N+1, outcome: "retro returned without writing a plan or sentinel"}` to `round_log` and jump to Step 2 with `terminal = "retro-failed"`.

### 1d. Run `/execute-plan` against the latest retro plan

If 1c did NOT result in a sentinel-driven halt (i.e. neither `RETRO_DONE.md` nor `BLOCKED.md` nor `NEEDS_INPUT.md` exists, AND a fresh retro plan was written), the retro identified Significant divergences. Ship the corrective work:

```
Skill({ skill: "execute-plan", args: "<latest_retro_plan_path>" })
```

After `/execute-plan` returns:

1. **Check for sentinels** the same way as 1c (RETRO_DONE / BLOCKED / NEEDS_INPUT). `/execute-plan` does NOT write `RETRO_DONE.md` itself — that's the next `/retro` round's job — but it can write `BLOCKED.md` if a work unit fails irrecoverably.
2. **Verify the plan's frontmatter flipped to `status: Complete`.** `/execute-plan`'s contract is to set this on success. If the plan still shows `status: Ready` or `status: In-progress`, log a warning in `round_log` but proceed — the next `/retro` round will assess whether the corrective work actually shipped.
3. Append `{round: N+1, retro_plan_written: <path>, execute_plan_run: true, outcome: "<one-line summary from execute-plan">}` to `round_log`.

### 1e. Increment and loop

Increment `round`. Return to Step 1a.

---

## Step 2: Summary and Stop

Print a structured report regardless of `terminal` value so the orchestrator's per-cycle log captures what advanced:

```
## /retro-feature — Done

**Feature:** {feature-id}
**Feature dir:** {feature-dir}
**Terminal reason:** {terminal}      # retro-done | blocked | needs-input | max-rounds | retro-failed
**Rounds run:** {round}/{max_rounds}

### Per-round log

| Round | Retro plan | /execute-plan ran? | Outcome |
|-------|-----------|--------------------|---------|
| 1 | retro-1-...md | yes | shipped fixes for D1-D4 |
| 2 | retro-2-...md | no | RETRO_DONE.md written — no significant divergences |
| ... | ... | ... | ... |

**RETRO_DONE.md:** {present | absent}
**Next step:**
  - terminal = "retro-done": feature is ready for Step 10 (mark complete). The next /lazy or /lazy-batch cycle will pick it up.
  - terminal = "blocked": resolve {feature-dir}/BLOCKED.md, then re-invoke /retro-feature or /lazy.
  - terminal = "needs-input": apply the ## Resolution to {feature-dir}/NEEDS_INPUT.md per the canonical NEEDS_INPUT lifecycle, then re-invoke.
  - terminal = "max-rounds": inspect the per-round log; if progress is being made but slowly, re-invoke /retro-feature with --max-rounds {higher}. If the same divergences keep reappearing, that's a sign /execute-plan isn't shipping the corrective work — investigate the retro plan's work units.
  - terminal = "retro-failed": /retro returned without writing a plan or sentinel — inspect its output (above) and re-run manually.
```

STOP. Do NOT chain into Step 10 or `__mark_complete__` — feature completion is the state machine's job, not this skill's.

---

## Step 3: Composition Notes

### Why this skill does NOT write sentinels directly

`/retro-feature` is pure orchestration. It dispatches `/retro` (which writes retro plans + `RETRO_DONE.md`) and `/execute-plan` (which flips plan status). It does NOT write `BLOCKED.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, or any other sentinel itself. This keeps the contract clean: every sentinel on disk has exactly one canonical writer, and the writer's identity is recoverable from the sentinel's `written_by` field (or, for `RETRO_DONE.md`, from context — it's written by `/retro`'s Step 6c).

The one exception: if both `/retro` and `/execute-plan` succeed but neither sentinel is written AND `round >= max_rounds`, this skill emits `terminal = "max-rounds"` to its caller — it does NOT write a sentinel to capture that state. Max-rounds is a `/retro-feature`-internal cap, not a state-machine condition; the next `/retro-feature` invocation gets a fresh budget.

### Relationship to `lazy-state.py` Step 9

`lazy-state.py`'s current Step 9 dispatch (lines ~972–1005) handles the retro phase one cycle at a time:

| State-script return | Equivalent `/retro-feature` round |
|---------------------|-----------------------------------|
| `Step 9: first retro` → `/retro` | round 1, `/retro` half |
| `Step 9: execute retro plan` → `/execute-plan retro-N.md` | round 1, `/execute-plan` half |
| `Step 9: second retro (verify fixes)` → `/retro` | round 2, `/retro` half |
| ... | ... |
| `Step 10: mark complete` (after `RETRO_DONE.md`) | NOT covered — that's `__mark_complete__`, outside this skill |

`/retro-feature` is a strict subset — it covers the retro loop only, not the Step 10 finalization. Wiring `lazy-state.py` to emit a single `sub_skill: retro-feature` dispatch at Step 9 entry (replacing the per-round dispatches) is a separate change; this skill is intentionally usable both as a state-machine dispatch target AND as a direct human invocation without that wiring.

### Coupling

This skill has no paired cloud variant (`/retro-feature-cloud`). The retro phase runs identically in cloud and workstation — both `/retro` and `/execute-plan` are cloud-safe (the cloud limitations affect Step 8 MCP testing, not retro analysis or its corrective implementation work). If a cloud-specific divergence emerges later, document it here and add a paired skill per the CLAUDE.md coupling rule.

---

## Notes

- This skill is safe to invoke directly by humans on a feature whose Step 9 entry gate is satisfied. The default `--batch` mode keeps it autonomous; pass an explicit `--max-rounds 1` to drive a single round interactively (useful for catching up after a manual fix).
- Plan-file frontmatter (per `~/.claude/skills/_components/plan-frontmatter.md`) is written by the dispatched `/retro` invocation — `/retro-feature` does not write any plan files of its own.
- Sentinel frontmatter (per `~/.claude/skills/_components/sentinel-frontmatter.md`) is written by `/retro` (Step 6c → `RETRO_DONE.md`) and `/execute-plan` (failure paths → `BLOCKED.md`). This skill only reads sentinels.
