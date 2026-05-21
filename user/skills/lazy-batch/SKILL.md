---
name: lazy-batch
description: Autonomous orchestrator for the AlgoBooth (or any queue.json-driven) feature pipeline. Loops on lazy-state.py and spawns Opus subagents per cycle. Halts only on no-RESEARCH.md, BLOCKED.md, NEEDS_INPUT.md, or max-cycles cap.
argument-hint: <max-cycles, e.g. 10>
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write"]
---

# Lazy Batch — Autonomous Pipeline Orchestrator

Drives the per-feature autonomous tail (`/spec-phases` → `/write-plan` → `/execute-plan` → `/mcp-test` → `/retro` → mark-complete) by looping on `~/.claude/scripts/lazy-state.py`. Each cycle spawns an Opus subagent that invokes the named sub-skill; the orchestrator (this skill, running in the main session) never touches source code, never invokes a skill directly, and never parses sentinel files manually.

This is the **workstation** orchestrator. The cloud variant is `/lazy-batch-cloud` (under `repos/algobooth/.claude/skills/lazy-batch-cloud/`); the two are coupled per CLAUDE.md.

---

## HARD CONSTRAINTS (non-negotiable)

1. **The orchestrator MUST NOT call `Edit` or `Write` on source code or test files.** All implementation work goes through subagents. The orchestrator may only `Write` sentinel files (specifically `NEEDS_RESEARCH.md` per Step 4) and read configuration via `Bash` / `Read`.
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or sentinel files.** State inference is exclusively via `lazy-state.py`. The only sentinel the orchestrator reads is the one it just wrote (for confirmation).
4. **One cycle = one subagent dispatch.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles.
5. **No interactive prompts.** Do not call `AskUserQuestion`. If the user needs to make a decision, the underlying sub-skill writes NEEDS_INPUT.md and the loop halts at the next state cycle.

---

## Step 0: Parse Arguments

`$ARGUMENTS` must contain a positive integer max-cycles (e.g. `5`, `10`). If empty, default to `10`. If non-numeric or `< 1`, refuse with:

> `/lazy-batch` requires a positive integer max-cycles. Usage: `/lazy-batch <N>`. Default: 10.

Initialize counters:
- `cycle = 0`
- `max_cycles = <parsed>`
- `cycle_log = []` — each entry: `{cycle, feature, action, subagent_summary}`

Print the start bookend:

```
## /lazy-batch — Starting
**Max cycles:** {max_cycles}
**Repo root:** {cwd}
```

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run lazy-state.py

```bash
python3 ~/.claude/scripts/lazy-state.py
```

If the script exits non-zero, surface the error, push a PushNotification, print the final batch report (see Step 2), and STOP.

Parse the JSON output. Extract: `feature_id`, `feature_name`, `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`, `notify_message`.

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`** / **`needs-input`**: PushNotification with `notify_message`, print final batch report, STOP. Do NOT modify the sentinel; the human resolves it manually.
- **`needs-research`**: see Step 4 (research halt).
- **`needs-spec-input`** / **`queue-missing`**: PushNotification with `notify_message`, print final batch report, STOP. The orchestrator cannot start from nothing.
- **`all-features-complete`**: PushNotification `"ALL FEATURES COMPLETE — roadmap finished after {cycle} /lazy-batch cycle(s)."`, print final batch report, STOP.
- **`cloud-queue-exhausted`**: Unreachable for `/lazy-batch` (workstation variant); treat as `all-features-complete` defensively.

### 1c. Check the max-cycles cap

If `cycle >= max_cycles`:

```
PushNotification({ message: "lazy-batch hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP. Do NOT try to renew the cap automatically — the cap exists to bound runaway costs.

### 1d. Compose and dispatch the cycle subagent

Build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else:

```
You are advancing one cycle of the autonomous feature pipeline.

Feature: {feature_name} ({feature_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Invoke the {sub_skill} skill with args: {sub_skill_args} --batch

Operating mode: batch
  - Do NOT ask interactive questions. Skills accept --batch and either auto-accept
    a recommended option or write NEEDS_INPUT.md and halt.
  - If the skill writes NEEDS_INPUT.md, do NOT attempt to resolve the decision —
    that's a halt for a human.

After the skill returns:
  1. If a commit policy file exists at .claude/skill-config/commit-policy.md,
     follow it. Otherwise commit per the standard pattern and push to the
     current branch. Skip commit only if the skill produced no file changes.
  2. Report a one-paragraph summary: what state was advanced, files modified,
     commit hash (or "no commit"), and any issues. Keep it under 8 lines so the
     orchestrator's per-cycle log stays compact.

You may NOT spawn further subagents. You MAY use Edit/Write on source code if
the dispatched skill requires it (e.g. /execute-plan does); follow the skill's
internal subagent-vs-orchestrator rules.
```

Special handling — pseudo-skills (`__write_validated_from_skip__`, `__write_validated_from_results__`, `__mark_complete__`) from the state script:

For these, the standard `/lazy` wrapper performs the special action inline. The orchestrator should dispatch the subagent with a slightly different prompt:

```
You are advancing one cycle of the autonomous feature pipeline.

Feature: {feature_name} ({feature_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Perform the {sub_skill} special action exactly as documented in
  ~/.claude/skills/lazy/SKILL.md (Step 3). Do not dispatch a Skill tool call —
  the action is a small file edit + commit performed by you directly:

    - __write_validated_from_skip__: write VALIDATED.md from prior SKIP_MCP_TEST.md
    - __write_validated_from_results__: write VALIDATED.md from MCP_TEST_RESULTS.md
    - __mark_complete__: update ROADMAP, delete sentinels, set SPEC Status, commit

After the action, commit and push per project policy, then report a one-
paragraph summary.
```

Dispatch:

```
Agent({
  description: "lazy-batch cycle {cycle+1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <the prompt above>
})
```

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, subagent's one-paragraph summary}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: /{sub_skill} on {feature_name} → {first-line-of-summary}"`.
3. Increment `cycle`. Return to Step 1a.

---

## Step 2: Final Batch Report

When the loop exits (terminal state or max-cycles), print:

```
## /lazy-batch — Done

**Cycles completed:** {cycle}/{max_cycles}
**Terminal reason:** {terminal_reason or "max-cycles"}
**Last notification:** {notify_message or "—"}

### Cycle log
| # | Feature | Action | Summary |
|---|---------|--------|---------|
| 1 | ... | /spec-phases | ... |
| 2 | ... | /write-plan | ... |
| ... |

**Next step:**
  - If terminal_reason is "blocked": resolve {spec_path}/BLOCKED.md
  - If terminal_reason is "needs-input": resolve {spec_path}/NEEDS_INPUT.md
  - If terminal_reason is "needs-research": run Gemini against {RESEARCH_PROMPT.md path}
  - If max-cycles: re-run `/lazy-batch {max_cycles}` from a fresh session
```

STOP.

---

## Step 3: Status Bookend Discipline (per cycle)

For each cycle, also produce a brief bookend pair (in addition to the one-line status in 1e):

**Before cycle N:**
```
### Cycle {N} — {feature_name} ({sub_skill})
```

**After cycle N:** part of the one-line status above. Keep it compact — many cycles fit in a single batch session.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

The state script returns `needs-research` when `RESEARCH.md` is missing but `RESEARCH_PROMPT.md` exists. The orchestrator's job is to:

1. Check whether `{spec_path}/NEEDS_RESEARCH.md` already exists (a prior cycle may have already dropped it).
2. If it does NOT exist, write it per `~/.claude/skills/_components/sentinel-frontmatter.md`:

   ```markdown
   ---
   kind: needs-research
   feature_id: {feature_id}
   research_prompt_path: <relative path to RESEARCH_PROMPT.md from spec_path>
   written_by: lazy-batch
   date: <today>
   ---

   # /lazy-batch — Needs Research

   Run Gemini deep research against the prompt below, then drop the result as
   RESEARCH.md alongside this file. `/lazy-batch` will then resume the
   autonomous tail (Phase 3 finalization → spec-phases → write-plan → ...).

   **Prompt file:** `{research_prompt_path}`
   ```

3. PushNotification with `notify_message`.
4. Print final batch report, STOP.

Special pre-step — if the state script returns `sub_skill: "spec"` with args that include "skip to Phase 2", the orchestrator dispatches it normally (this generates the RESEARCH_PROMPT.md). On the next cycle, the state script returns `needs-research` and this Step 4 fires. That's the intended two-cycle handoff for a feature with no research at all.

---

## Notes

- This skill never invokes the work-log MCP tool. Each sub-skill invoked by the cycle subagents logs its own work.
- The orchestrator is single-session by design — there is no persistence layer. State lives in the filesystem sentinels; restart is free.
- Commit policy is delegated to the cycle subagent (which follows the project's `.claude/skill-config/commit-policy.md` or standard pattern). The orchestrator does not commit anything itself except the NEEDS_RESEARCH.md sentinel, which is committed by the next sub-skill cycle's subagent (since the loop has already exited by the time it's written).
