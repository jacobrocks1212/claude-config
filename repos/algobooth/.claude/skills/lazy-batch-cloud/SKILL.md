---
name: lazy-batch-cloud
description: Cloud-environment variant of /lazy-batch. Loops on lazy-state.py --cloud and spawns Opus subagents per cycle, deferring any step that requires the Tauri desktop or MCP HTTP server. Halts on no-RESEARCH.md, BLOCKED.md, NEEDS_INPUT.md, cloud-queue-exhausted, or max-cycles cap.
argument-hint: <max-cycles, e.g. 10>
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write"]
---

# Lazy Batch Cloud — Autonomous Pipeline Orchestrator (Cloud Mode)

Cloud variant of `/lazy-batch`. Identical orchestration shape: loop on the state script, spawn one Opus subagent per cycle, halt on the same terminal conditions — but the state script runs in `--cloud` mode, so:

- Step 2 skips cloud-saturated features (RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md).
- Step 8 returns `__write_deferred_non_cloud__` instead of dispatching `/mcp-test`. The cycle subagent writes the deferral sentinel and the next cycle proceeds to retro.
- Step 10 (mark complete) is unreachable from cloud unless a workstation has already produced VALIDATED.md. `cloud-queue-exhausted` is the normal terminal state when every remaining feature is awaiting workstation MCP testing.

This skill is coupled to `/lazy-batch` per CLAUDE.md — their only intended divergences are documented in the "Differences from /lazy-batch" block below.

---

## HARD CONSTRAINTS (non-negotiable)

Identical to `/lazy-batch`:

1. The orchestrator MUST NOT call `Edit` or `Write` on source code or test files. Only the `NEEDS_RESEARCH.md` sentinel may be written directly by the orchestrator.
2. The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool. Every sub-skill goes through a spawned `Agent` subagent.
3. The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or sentinel files. State inference is exclusively via `lazy-state.py --cloud`.
4. One cycle = one subagent dispatch.
5. No interactive prompts. Halts via NEEDS_INPUT.md / NEEDS_RESEARCH.md only.

**Cloud-specific:** the cycle subagent operates under the same cloud-environment limitations documented in `/lazy-cloud` — no Tauri runtime, no MCP HTTP server, no audio device, no Windows-only tooling. The cycle subagent's prompt (Step 1d below) makes this explicit.

---

## Step 0: Parse Arguments

Same as `/lazy-batch`. `$ARGUMENTS` is a positive integer max-cycles, default `10`.

Print the start bookend:

```
## /lazy-batch-cloud — Starting
**Environment:** Cloud Linux (no Tauri/MCP)
**Max cycles:** {max_cycles}
**Repo root:** {cwd}
```

---

## Step 1: Cycle Loop

### 1a. Run lazy-state.py --cloud

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud
```

Parse JSON output as in `/lazy-batch`.

### 1b. Handle terminal states

Same handling as `/lazy-batch` for `blocked`, `needs-input`, `needs-spec-input`, `queue-missing`, `all-features-complete`. Cloud-specific:

- **`cloud-queue-exhausted`**: PushNotification `"Cloud queue exhausted after {cycle} cycle(s) — N feature(s) awaiting workstation /lazy for MCP test."` Print final batch report, STOP.
- **`needs-research`**: see Step 4 (research halt — same as `/lazy-batch`, but the sentinel's `written_by` is `lazy-batch-cloud`).

### 1c. Check the max-cycles cap

Same as `/lazy-batch`:

```
PushNotification({ message: "lazy-batch-cloud hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP.

### 1d. Compose and dispatch the cycle subagent

The cloud cycle subagent prompt adds an explicit reminder of cloud limitations. The prompt template:

```
You are advancing one cycle of the autonomous feature pipeline in a CLOUD
Linux session. This container has:
  - No Tauri desktop runtime
  - No MCP HTTP server
  - No audio device
  - No Windows-only tooling
  - No persistent state — the container is reclaimed after the session.

Feature: {feature_name} ({feature_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Invoke the {sub_skill} skill with args: {sub_skill_args} --batch

Operating mode: batch
  - Do NOT ask interactive questions. Skills accept --batch and either auto-accept
    a recommended option or write NEEDS_INPUT.md and halt.
  - If the skill writes NEEDS_INPUT.md, do NOT attempt to resolve the decision.
  - The state script (--cloud variant) has already guaranteed this skill is safe
    to run in cloud. If a deliverable genuinely cannot be implemented in cloud
    (e.g. Windows-only build step, Tauri-runtime-only behavior), write
    BLOCKED.md with blocker_kind: cloud-limitation per
    ~/.claude/skills/_components/sentinel-frontmatter.md and halt.

After the skill returns:
  1. Commit per .claude/skill-config/commit-policy.md (or standard pattern).
  2. Report a one-paragraph summary (under 8 lines).

You may NOT spawn further subagents. You MAY use Edit/Write on source code if
the dispatched skill requires it; follow the skill's internal subagent rules.
```

Pseudo-skill handling — `__write_deferred_non_cloud__`, `__write_validated_from_skip__`, `__mark_complete__`:

```
You are advancing one cycle of the autonomous feature pipeline in a CLOUD
Linux session.

Feature: {feature_name} ({feature_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Perform the {sub_skill} special action exactly as documented in
  repos/algobooth/.claude/skills/lazy-cloud/SKILL.md (Step 3). Do not dispatch
  a Skill tool call — the action is a small file edit + commit performed by
  you directly:

    - __write_deferred_non_cloud__: write DEFERRED_NON_CLOUD.md
    - __write_validated_from_skip__: write VALIDATED.md from prior SKIP_MCP_TEST.md
    - __mark_complete__: update ROADMAP, delete sentinels, set SPEC Status, commit
      (only reachable if VALIDATED.md and RETRO_DONE.md both already exist —
      cloud cannot produce VALIDATED.md from MCP results)

After the action, commit and push per project policy, then report a one-
paragraph summary.
```

Dispatch:

```
Agent({
  description: "lazy-batch-cloud cycle {cycle+1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <the prompt above>
})
```

### 1e. Record cycle outcome and loop

Same as `/lazy-batch`. Append to `cycle_log`, print one-line status, increment cycle, loop.

---

## Step 2: Final Batch Report

Same as `/lazy-batch`. Header is `## /lazy-batch-cloud — Done`. Cloud-specific "Next step" guidance:

```
**Next step:**
  - If terminal_reason is "blocked": resolve {spec_path}/BLOCKED.md
  - If terminal_reason is "needs-input": resolve {spec_path}/NEEDS_INPUT.md
  - If terminal_reason is "needs-research": run Gemini against {RESEARCH_PROMPT.md path}
  - If terminal_reason is "cloud-queue-exhausted": run /lazy on workstation to run MCP tests
  - If max-cycles: re-run `/lazy-batch-cloud {max_cycles}` from a fresh session
```

---

## Step 3: Status Bookend Discipline

Same as `/lazy-batch`. Per-cycle one-line status, compact for long batches.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

Same as `/lazy-batch` Step 4, except the sentinel's `written_by` is `lazy-batch-cloud`:

```yaml
---
kind: needs-research
feature_id: {feature_id}
research_prompt_path: <relative path>
written_by: lazy-batch-cloud
date: <today>
---
```

Cloud cannot run Gemini either — the user runs Gemini on their workstation and drops `RESEARCH.md` next to the prompt before re-running `/lazy-batch-cloud` (or `/lazy-batch` on workstation).

---

## Differences from `/lazy-batch`

| Aspect | `/lazy-batch` | `/lazy-batch-cloud` |
|--------|---------------|---------------------|
| State script invocation | `python3 ~/.claude/scripts/lazy-state.py` | `python3 ~/.claude/scripts/lazy-state.py --cloud` |
| `cloud-queue-exhausted` terminal | defensive (unreachable in practice) | normal halt when remaining features await workstation MCP testing |
| `__write_deferred_non_cloud__` pseudo-skill | not emitted by state script | normal Step 8 action |
| Cycle subagent prompt | bare batch-mode instructions | adds cloud-environment limitations block |
| NEEDS_RESEARCH.md `written_by` | `lazy-batch` | `lazy-batch-cloud` |

All other behavior is identical — coupling is enforced by the state script (one source of truth), not by duplicated prose between the two orchestrators.

---

## Notes

- Coupling rule from CLAUDE.md: `/lazy-batch` ↔ `/lazy-batch-cloud` are coupled the same way `/lazy` ↔ `/lazy-cloud` are. Changes to one MUST be mirrored in the other unless explicitly cloud-scoped per the table above.
- The orchestrator never invokes the work-log tool directly. Cycle subagents log their own work.
- No persistence layer — restart is free. Sentinel files capture all durable state.
