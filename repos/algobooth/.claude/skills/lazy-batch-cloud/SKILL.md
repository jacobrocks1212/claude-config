---
name: lazy-batch-cloud
description: Cloud-environment variant of /lazy-batch. Loops on lazy-state.py --cloud and spawns Opus subagents per cycle, deferring any step that requires the Tauri desktop or MCP HTTP server. Halts on BLOCKED.md, NEEDS_INPUT.md (post-research decision halt), cloud-queue-exhausted, or max-cycles cap. Auto-resumes after Gemini research uploads land via /ingest-research.
argument-hint: <max-cycles, e.g. 10>
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion", "Monitor"]
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

1. The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` status lines when performing the `__mark_complete__` action. `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-halt mode) after `AskUserQuestion` returns. All other `Write`/`Edit` operations require subagent dispatch.
2. The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool. Every sub-skill goes through a spawned `Agent` subagent. Pseudo-skills (`__*__`) are not real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files. State inference is exclusively via `lazy-state.py --cloud`. Sentinel files MAY be read by the orchestrator to confirm a write or drive a pseudo-skill action.
4. One cycle = one subagent dispatch FOR REAL WORK SKILLS. Pseudo-skill cycles (sentinel writes) are inline orchestrator actions that count as one cycle each. **Wait-mode time (Step 1f) is free** — it does not count against `max_cycles`; only dispatches do.
5. **Interactive prompts are scoped to decision-halt mode (Step 1g) ONLY.** Outside Step 1g, the orchestrator MUST NOT call `AskUserQuestion`. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`) and append a `## Resolution` section before halting.
6. **The orchestrator MUST re-print the rich `## Decision Context` to chat BEFORE calling `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print is the load-bearing context. Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` — surface the malformation as a quality issue and halt instead (see Step 1g.1).

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

Initialize per-session state — identical shape to `/lazy-batch` Step 0:
- `research_pending = set()` — feature_ids that hit `needs-research` this session.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle.

### 1a. Run lazy-state.py --cloud

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]
```

Pass `--skip-needs-research` whenever `skip_needs_research == true`. Parse JSON output as in `/lazy-batch`.

### 1b. Handle terminal states

Same handling as `/lazy-batch` for `blocked`, `needs-input`, `needs-spec-input`, `queue-missing`, `all-features-complete`. Cloud-specific:

- **`needs-input`**: see Step 1g (decision-halt mode — identical to `/lazy-batch` Step 1g).
- **`cloud-queue-exhausted`**: PushNotification `"Cloud queue exhausted after {cycle} cycle(s) — N feature(s) awaiting workstation /lazy for MCP test."` Print final batch report, STOP.
- **`needs-research`**: see Step 4 (research sentinel drop — same as `/lazy-batch`, but the sentinel's `written_by` is `lazy-batch-cloud`). Step 4 does NOT halt — it drops the sentinel, flips `skip_needs_research = true`, returns to Step 1a.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode — identical to `/lazy-batch` Step 1f).

### 1c. Check the max-cycles cap

Same as `/lazy-batch`:

```
PushNotification({ message: "lazy-batch-cloud hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small sentinel-file write + commit, NOT a real skill that performs implementation work. Perform the action inline (orchestrator session) instead of dispatching a subagent. Same rationale as `/lazy-batch` Step 1c.5: sentinel files are documentation, and dispatching an Opus subagent for a 10-line YAML write + commit wastes a full subagent's worth of context. On the cloud path this is especially costly because `__write_deferred_non_cloud__` fires once per feature in the normal flow.

Follow `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` Step 3's protocol for each pseudo-skill exactly (the wrapper and orchestrator do the same thing here):

- **`__write_deferred_non_cloud__`** — if `<spec_path>/DEFERRED_NON_CLOUD.md` already exists, skip (idempotent). Otherwise write it with kind: deferred-non-cloud, deferred_step: 8, reason: "Cloud Linux environment cannot run tauri:dev or reach the MCP HTTP server.", deferred_by: lazy-cloud, today's date, and the body explaining workstation resume. Commit per project policy.
- **`__write_validated_from_skip__`** — read `<spec_path>/SKIP_MCP_TEST.md` frontmatter, write `<spec_path>/VALIDATED.md` (kind: validated, mcp_scenarios: [], result: all-passing, body note about the prior skip). Commit.
- **`__mark_complete__`** — only reachable from cloud if both `VALIDATED.md` and `RETRO_DONE.md` already exist (cloud cannot produce VALIDATED.md from MCP results — workstation did). Update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token), delete `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` sentinels, set `<spec_path>/SPEC.md`'s `**Status:**` to `Complete`, then commit per project policy.

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: {sub_skill} on {feature_name} → <inline outcome>"`.
3. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), the cloud cycle subagent prompt adds an explicit reminder of cloud limitations. The prompt template:

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

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

**Identical to `/lazy-batch` Step 1f** — the wait mode is shared shape across both orchestrators. Cloud cannot run Gemini itself, but the `Monitor` until-loop watching `docs/gemini-sprint/results/` works the same way: the user (or a separate workstation session) drops `.txt` files into the staging dir, the watcher exits, `/ingest-research` runs as one cycle, and the loop resumes. Direct `RESEARCH.md` drops also trigger resume.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1f for the full algorithm. Cloud-specific nuances:

- The `/ingest-research` dispatch is the same cycle subagent shape but the cloud-environment limitations block is NOT added — `/ingest-research`'s hard constraints already scope it to `docs/`-only writes (no Tauri / no MCP runtime required), so the cycle subagent doesn't need the standard cloud preamble.
- After `/ingest-research` returns, the next state-script call `python3 ~/.claude/scripts/lazy-state.py --cloud` (with `--skip-needs-research` if `research_pending` is still non-empty) will see the newly-ingested RESEARCH.md and dispatch Step 5 ("integrate research" → `/spec` Phase 3) for each ingested feature.

### 1g. Decision-halt mode (`terminal_reason == "needs-input"`)

**Identical to `/lazy-batch` Step 1g** — the decision-halt protocol is shared. See `~/.claude/skills/lazy-batch/SKILL.md` Step 1g for the full algorithm:

1. Read and validate `NEEDS_INPUT.md` (schema check on `## Decision Context` H2 + H3 1:1).
2. Re-print the rich body to chat VERBATIM.
3. `AskUserQuestion` per decision (label, header, options).
4. Append `## Resolution` to NEEDS_INPUT.md.
5. Commit per project policy.
6. Increment `cycle`. Halt with final batch report.

Cloud has no special handling here — decision halts are filesystem-level and run identically in cloud and workstation.

---

## Step 2: Final Batch Report

Same as `/lazy-batch`. Header is `## /lazy-batch-cloud — Done`. Cloud-specific "Next step" guidance:

```
**Next step:**
  - If terminal_reason is "blocked": resolve {spec_path}/BLOCKED.md
  - If terminal_reason is "needs-input": apply the `## Resolution` in {spec_path}/NEEDS_INPUT.md to SPEC.md / PHASES.md, delete the sentinel (or neutralize its frontmatter to keep the audit trail), then re-run `/lazy-batch-cloud {max_cycles}`
  - If terminal_reason is "queue-blocked-on-research": should not appear here — Step 1f's wait mode handles it inline. If somehow reported, run Gemini against the staged prompts in docs/gemini-sprint/prompts/ and drop results in docs/gemini-sprint/results/
  - If terminal_reason is "needs-research": should not appear here — Step 4 + Step 1f handle research inline.
  - If terminal_reason is "cloud-queue-exhausted": run /lazy on workstation to run MCP tests
  - If max-cycles: re-run `/lazy-batch-cloud {max_cycles}` from a fresh session
```

---

## Step 3: Status Bookend Discipline

Same as `/lazy-batch`. Per-cycle one-line status, compact for long batches.

---

## Step 4: Research Sentinel Drop (terminal_reason == "needs-research")

**Identical to `/lazy-batch` Step 4** — does NOT halt; drops a sentinel, flips `skip_needs_research = true`, adds the feature to `research_pending`, returns to Step 1a. The only divergence is the sentinel's `written_by`:

```yaml
---
kind: needs-research
feature_id: {feature_id}
research_prompt_path: <relative path>
written_by: lazy-batch-cloud
date: <today>
---
```

Cloud cannot run Gemini itself — but the user (or a coupled workstation session) drops `RESEARCH.md` next to the prompt OR stages `.txt` results in `docs/gemini-sprint/results/`. Step 1f's `Monitor` until-loop detects either path. The same body should reference the gemini-sprint flow per `/lazy-batch` Step 4.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 4 for the full algorithm and multi-feature accumulation behavior.

---

## Differences from `/lazy-batch`

| Aspect | `/lazy-batch` | `/lazy-batch-cloud` |
|--------|---------------|---------------------|
| State script invocation | `python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]` | `python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]` |
| `cloud-queue-exhausted` terminal | defensive (unreachable in practice) | normal halt when remaining features await workstation MCP testing |
| `__write_deferred_non_cloud__` pseudo-skill | not emitted by state script | normal Step 8 action — handled INLINE in Step 1c.5, no subagent dispatch |
| `__write_validated_from_results__` pseudo-skill | normal Step 8 action — inline | not emitted (cloud cannot produce MCP results) |
| Cycle subagent prompt (real skills only) | bare batch-mode instructions | adds cloud-environment limitations block |
| NEEDS_RESEARCH.md `written_by` | `lazy-batch` | `lazy-batch-cloud` |
| Wait-mode trigger (Step 1f) | `terminal_reason: queue-blocked-on-research` — **same shape** in both | `terminal_reason: queue-blocked-on-research` — **same shape** in both |
| Decision-halt mode (Step 1g) | `terminal_reason: needs-input` — **same shape** in both | `terminal_reason: needs-input` — **same shape** in both |
| `/ingest-research` dispatch (Step 1f.7) | bare prompt (no cloud preamble) | bare prompt (no cloud preamble — skill is docs-only by hard constraint) |

All other behavior is identical — coupling is enforced by the state script (one source of truth), not by duplicated prose between the two orchestrators. Step 1c.5 (inline pseudo-skill handling) is shared shape; only the set of pseudo-skills emitted by the state script differs. Step 1f and Step 1g are also shared shape; both orchestrators reach them via the same state-script terminal reasons.

---

## Notes

- Coupling rule from CLAUDE.md: `/lazy-batch` ↔ `/lazy-batch-cloud` are coupled the same way `/lazy` ↔ `/lazy-cloud` are. Changes to one MUST be mirrored in the other unless explicitly cloud-scoped per the table above.
- The orchestrator never invokes the work-log tool directly. Cycle subagents log their own work.
- No persistence layer — restart is free. Sentinel files capture all durable state.
