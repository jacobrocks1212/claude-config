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

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` status lines when performing the `__mark_complete__` action (which is a documentation-level update by definition, not a source-code edit). All other `Write`/`Edit` operations — source code, test files, plan files, PHASES.md — require subagent dispatch.
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference is exclusively via `lazy-state.py`. Sentinel files MAY be read by the orchestrator to confirm a write or to drive a pseudo-skill action.
4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator actions that count as one cycle each.
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

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small sentinel-file write + commit, NOT a real skill that performs implementation work. Perform the action inline (orchestrator session) instead of dispatching a subagent. This is the spirit-preserving relaxation of HARD CONSTRAINT 1: sentinel files are documentation, and dispatching an Opus subagent to write a 10-line YAML block + run `git commit` wastes a full subagent's worth of context.

Follow `~/.claude/skills/lazy/SKILL.md` Step 3's protocol for each pseudo-skill exactly (the wrapper and orchestrator do the same thing here):

- **`__write_validated_from_skip__`** — read `<spec_path>/SKIP_MCP_TEST.md` frontmatter, write `<spec_path>/VALIDATED.md` (kind: validated, mcp_scenarios: [], result: all-passing, body note about the prior skip), then commit per the project's commit policy.
- **`__write_validated_from_results__`** — read `<spec_path>/MCP_TEST_RESULTS.md` frontmatter, extract `scenarios`, write `<spec_path>/VALIDATED.md` with those scenarios, then commit.
- **`__mark_complete__`** — update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token), delete `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` sentinels, set `<spec_path>/SPEC.md`'s `**Status:**` to `Complete`, then commit per project policy.

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: {sub_skill} on {feature_name} → <inline outcome>"`.
3. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

This saves one Opus dispatch per pseudo-skill action. On a typical feature lifecycle (workstation: 1 × `__write_validated_*` + 1 × `__mark_complete__` = 2 dispatches reclaimed; cloud: 1 × `__write_deferred_non_cloud__` minimum) the savings compound across a multi-feature queue pass.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else:

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
