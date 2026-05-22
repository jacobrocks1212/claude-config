---
name: lazy-cloud
description: Cloud-environment variant of /lazy — advances the AlgoBooth queue with the same state machine, but defers any step that cannot run in a cloud-based Linux environment (e.g. MCP testing requiring the desktop Tauri app) and documents the deferral so a later /lazy run from a workstation picks up exactly where this run stopped
argument-hint: [optional: "status" to just report, or "skip" to skip current feature with reason]
plan-mode: never
---

# Lazy Cloud — Autonomous Feature Dispatcher (Cloud Mode)

Thin LLM wrapper around `~/.claude/scripts/lazy-state.py --cloud`. The cloud variant of `/lazy`: same state machine, same sentinel contract, same one-skill-per-invocation rule — but aware that this session runs in an ephemeral cloud Linux container with no Tauri desktop, no audio device, and no `tauri:dev` server.

State-machine differences from `/lazy` (all encoded in `lazy-state.py --cloud`):
- Step 2 skips cloud-saturated features (RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md) and advances.
- **Step 8 (retro) runs in cloud** — `/retro` is a docs/analysis pass (no Tauri, no MCP), so cloud sessions DO run it. This is the gap the new ordering closes: under the old order, cloud halted at MCP deferral and never reached retro.
- Step 9 (MCP test) dispatches `__write_deferred_non_cloud__` (the wrapper writes the sentinel) and the loop ends — workstation `/lazy` picks up the deferral.
- Step 10 halts (cloud cannot finalize without VALIDATED.md) — terminal_reason `cloud-queue-exhausted`.

**HARD REQUIREMENT — ONE SKILL PER INVOCATION:** Execute at most one sub-skill (via Skill tool). After it completes, report what happened and STOP. Do not chain multiple skills. Writing a sentinel file (e.g. DEFERRED_NON_CLOUD.md) is part of the wrapper's special-action handling and does NOT count as a skill dispatch — but a special action and a skill dispatch in the same invocation IS still considered chaining and is disallowed.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. This skill dispatches directly.

**HARD REQUIREMENT — NEVER WRITE PERMANENT SKIP MARKERS FROM CLOUD:** Do not write `SKIP_MCP_TEST.md`, `VALIDATED.md` (from MCP results — `__write_validated_from_skip__` based on a prior SKIP_MCP_TEST is OK), or `MCP_TEST_RESULTS.md` for a feature whose MCP-testability was not actually evaluated against a running Tauri app in this session. Permanent decisions about test coverage require the workstation environment. `lazy-state.py --cloud` enforces this — it will never emit `sub_skill: "mcp-test"`.

**HARD REQUIREMENT — STATUS BOOKENDS:** Every /lazy-cloud invocation must produce two status messages:

1. **Before acting** (after running lazy-state.py, before invoking any skill):
   ```
   ## /lazy-cloud — {feature_name} (Tier {tier})
   **Environment:** Cloud Linux (no Tauri/MCP)
   **State:** {current_step from state script}
   **Action:** {what skill will be invoked, or "DEFER — {reason}" for cloud-only special actions}
   ```

2. **After acting** (after the dispatched skill returns or after a STOP decision):
   ```
   ## /lazy-cloud — Done
   **Completed:** {what was accomplished this invocation}
   **Deferred:** {description of any step deferred + path to DEFERRED_NON_CLOUD.md, or "None"}
   **Issues:** {any problems encountered, or "None"}
   **Next `/lazy` (workstation) will:** {what a non-cloud /lazy invocation should pick up — usually deferred MCP testing}
   **Next `/lazy-cloud` will:** {what the next cloud invocation will do, or "Nothing further — awaiting workstation /lazy for deferred MCP test"}
   ```

---

## Sentinel File Format

All sentinel files this skill reads or writes follow the canonical YAML-frontmatter schema:

!`cat ~/.claude/skills/_components/sentinel-frontmatter.md`

When this skill writes a sentinel (Step 3 special actions), emit the YAML frontmatter first, then a blank line, then a human-readable markdown body. When this skill reads a sentinel, parse the frontmatter per the protocol above; the markdown body is for humans only.

---

## Cloud Environment Limitations

The cloud session runs in an ephemeral Linux container with:

- **No Tauri desktop runtime** — cannot launch `tauri:dev`, cannot host the Rust sidecar, cannot reach the MCP HTTP server.
- **No audio output device** — cannot validate audio pipelines via RMS metering or `load_test_tone`.
- **No Windows-only tooling** — anything requiring Windows paths, PowerShell, or Windows-specific dependencies.
- **No long-lived shared state** — the container is reclaimed after the session ends.

When `lazy-state.py --cloud` would normally dispatch a step that requires the desktop environment (today: MCP testing, Step 9), it returns `sub_skill: "__write_deferred_non_cloud__"` instead. The wrapper writes the DEFERRED_NON_CLOUD.md sentinel and stops. **Note:** `/retro` (Step 8) runs in cloud — it's a docs/analysis pass and does not require the Tauri runtime or MCP server. The cloud-saturated skip in Step 2 (RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md) is the terminal state for a feature whose only remaining work is workstation MCP validation.

---

## Step 0: Load Tools and Parse Arguments

1. Load PushNotification: `ToolSearch({ query: "select:PushNotification" })`
2. Parse `$ARGUMENTS`:
   - If `"status"` → run the same logic as `/lazy-status` (read-only report) and STOP. Additionally, if any feature has a `DEFERRED_NON_CLOUD.md`, list those features and what step is deferred.
   - If `"skip"` → mark current feature as skipped (see Step 5) and STOP
   - If empty or anything else → proceed to Step 1

---

## Step 1: Run lazy-state.py --cloud

Invoke the state inference script in cloud mode with the project root as the working directory:

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud
```

Capture stdout (a single JSON object). If the script exits non-zero, surface the error and STOP — do not try to parse malformed state.

Parse the JSON. You now have the same fields as plain `/lazy`:
- `feature_id`, `feature_name`, `spec_path`
- `current_step`, `sub_skill`, `sub_skill_args`
- `terminal_reason`, `notify_message`

---

## Step 2: Handle Terminal States

If `terminal_reason` is set, PushNotify and STOP exactly as `/lazy` does. Cloud-specific reasons:

| `terminal_reason` | Cloud behavior |
|------|---|
| `blocked` | Same as workstation — read BLOCKED.md, present details, STOP |
| `needs-research` | Surface RESEARCH_PROMPT.md path; cloud cannot run Gemini either |
| `needs-input` | Surface NEEDS_INPUT.md decisions |
| `needs-spec-input` | Tell the user to run `/spec`; cloud cannot start from nothing |
| `all-features-complete` | Roadmap done |
| `cloud-queue-exhausted` | Every remaining feature is cloud-saturated; workstation /lazy is needed to finalize |
| `queue-missing` | queue.json missing |

For `cloud-queue-exhausted`, the status bookend's "Next `/lazy` (workstation) will:" line should explicitly say "Run MCP tests for each deferred feature, in queue order".

---

## Step 3: Handle Special Actions

If `sub_skill` begins with `__` (double-underscore), it is a special action the wrapper performs directly:

### `__write_deferred_non_cloud__`

`sub_skill_args` is `{spec_path}`. All implementation phases are complete but cloud cannot run MCP tests. Write the deferral sentinel and stop so the next invocation can proceed to retro.

1. If `{spec_path}/DEFERRED_NON_CLOUD.md` already exists, skip the write (idempotent).
2. Otherwise write `{spec_path}/DEFERRED_NON_CLOUD.md` with kind `deferred-non-cloud`, `deferred_step: 8`, `reason: "Cloud Linux environment cannot run tauri:dev or reach the MCP HTTP server."`, `deferred_by: lazy-cloud`, `date: <today>`, and a body explaining how the workstation /lazy resumes.
3. PushNotification: `"{feature_name}: MCP testing deferred to workstation /lazy. Run /lazy-cloud again to continue with retro."`
4. Print the after-status bookend (Deferred: "Step 8 MCP testing → {spec_path}/DEFERRED_NON_CLOUD.md"), call work-log, STOP.

### `__write_validated_from_skip__`

`sub_skill_args` is `{spec_path}`. SKIP_MCP_TEST.md exists from a prior workstation assessment — write VALIDATED.md so retro proceeds normally.

1. Parse `{spec_path}/SKIP_MCP_TEST.md`'s frontmatter.
2. Write `{spec_path}/VALIDATED.md` (kind: validated, mcp_scenarios: [], result: all-passing, body: "MCP tests skipped per prior SKIP_MCP_TEST.md").
3. Print the after-status bookend, call work-log, STOP.

### `__mark_complete__`

`sub_skill_args` is `{spec_path}`. Both VALIDATED.md AND RETRO_DONE.md exist (e.g., workstation produced VALIDATED.md while cloud has RETRO_DONE.md). Cloud CAN complete in this case:

1. Update `docs/features/ROADMAP.md` — wrap the feature row in `~~ ... ~~` and append `**COMPLETE**`.
2. Delete sentinels: `VALIDATED.md`, `RETRO_DONE.md`, `DEFERRED_NON_CLOUD.md` if present.
3. Update `{spec_path}/SPEC.md` — change `**Status:**` to `Complete`.
4. Invoke `Skill({ skill: "commit", args: "feat({feature_id}): complete — all phases implemented, validated, and retro done" })`.
5. PushNotification: `"{feature_name} COMPLETE. Run /lazy-cloud to continue."`
6. Print the after-status bookend, call work-log, STOP.

### Any other `__*__` action

Print the after-status bookend with an explanatory message ("unrecognized special action: <name>") and STOP. Do not improvise.

---

## Step 4: Dispatch the Sub-Skill

If `sub_skill` is a regular skill name (not `__*__`), invoke it exactly:

```
Skill({ skill: "<sub_skill>", args: "<sub_skill_args>" })
```

After the skill returns:
1. Print the after-status bookend.
2. Call the work-log step below.
3. STOP.

> **Cloud note:** if `/execute-plan` encounters a deliverable that genuinely cannot be implemented in the cloud Linux environment (e.g. a Windows-only build step, a Tauri-runtime-only behavior), it should write BLOCKED.md with `blocker_kind: cloud-limitation` so the next workstation `/lazy` knows the unblock requires re-running the deliverable, not a fix.

---

## Step 5: Skip Current Feature

Only triggered when `$ARGUMENTS` contains `"skip"`.

1. Run `python3 ~/.claude/scripts/lazy-state.py --cloud` to find the current feature.
2. Ask why (via AskUserQuestion): "Why should {feature_name} be skipped?"
3. Update ROADMAP.md: append `(SKIPPED — {reason})` to the feature row.
4. The next `/lazy-cloud` invocation will automatically pick up the following feature.
5. STOP.

---

## Work Log (MANDATORY — DO NOT SKIP)

Every /lazy-cloud invocation that performs meaningful work MUST call `interview_work_log_append` before producing the "After" status bookend. A pure deferral (writing `DEFERRED_NON_CLOUD.md`) DOES count as meaningful work and MUST be logged — it's the audit record of why a feature didn't progress in this session.

Load the tool: `ToolSearch({ query: "select:mcp__plugin_interview-prep-plugin_interview-prep__interview_work_log_append" })`

Call with:
- `skill`: `"lazy-cloud"`
- `project`: `"algobooth"`
- `title`: `"/lazy-cloud → {action taken or 'defer MCP test'}"`
- `summary`: 2-4 sentences.
- `files_modified`: files modified during this invocation (from sub-skill output, plus any sentinel files written)
- `technologies`: relevant tech stack
- `patterns`: patterns applied (include `cloud-deferral` when DEFERRED_NON_CLOUD.md was written)
- `technical_context`: architectural context

**Skip work-log only when:** /lazy-cloud did nothing meaningful (terminal halt without dispatch, status query, or skip command).

---

## Sentinel Files Reference

Identical to `/lazy`, plus the cloud-deferral sentinel:

| File | Created by | Purpose | Lifecycle |
|------|-----------|---------|-----------|
| `plans/*.md` | /write-plan, /retro, etc. | Colocated plan files | Persists (audit trail) |
| `BLOCKED.md` | /execute-plan or /lazy[-cloud] | Blocker details | Persists until Jacob resolves |
| `MCP_TEST_RESULTS.md` | /lazy (after mcp-test) — NEVER /lazy-cloud | Test results with pass/fail details | Persists permanently |
| `VALIDATED.md` | /lazy (after 100% pass) — NEVER /lazy-cloud from MCP results | Validation gate | Deleted on feature completion |
| `SKIP_MCP_TEST.md` | /lazy (assessment) — never written by /lazy-cloud | Documents why MCP testing was skipped | Persists permanently |
| `RETRO_DONE.md` | /lazy[-cloud] (after retro execution) | Retro completion gate | Deleted on feature completion |
| **`DEFERRED_NON_CLOUD.md`** | **/lazy-cloud (cloud-blocked step)** | **Documents step deferred to workstation /lazy** | **Deleted on feature completion — left in place by /lazy as audit trail until then** |
| `NEEDS_RESEARCH.md` | /lazy-batch[-cloud] | Halt: research prompt exists, awaiting human Gemini run | Deleted when RESEARCH.md is dropped in place |
| `NEEDS_INPUT.md` | any `--batch` skill | Halt: ambiguous decision encountered | Deleted when the human resolves the decision |

---

## State Machine Summary

The state machine lives in `~/.claude/scripts/lazy-state.py`. Pass `--cloud` to get the cloud-aware variants (Step 2 skip, **Step 8 retro runs in cloud**, Step 9 MCP deferral, Step 10 halt). This skill is a thin LLM wrapper that runs the script, dispatches the named sub-skill or performs the named special action, and stops.

**Current step ordering after phases complete:** Step 8 retro → Step 9 MCP test (deferred in cloud) → Step 10 mark complete. `/retro` runs FIRST so the implementation-time retrospective gate fires regardless of whether MCP testing is available. The lazy state machine does not auto-loop retro — additional rounds are triggered only by `/retro` itself writing a follow-up plan.

```
lazy-state.py --cloud → JSON {sub_skill, sub_skill_args, terminal_reason}

terminal_reason set?                       → notify + STOP
sub_skill = "__write_deferred_non_cloud__" → write DEFERRED_NON_CLOUD.md + STOP
sub_skill = "__write_validated_from_skip__"→ write VALIDATED.md (from SKIP_MCP_TEST) + STOP
sub_skill = "__mark_complete__"            → ROADMAP edit + sentinel cleanup + commit + STOP
sub_skill = real skill?                    → Skill({skill, args}) → work-log → STOP
```

This skill and the paired `/lazy` are coupled per CLAUDE.md — their only intended divergence is whether they pass `--cloud` to lazy-state.py. Any state-machine change goes into the script, not into prose duplicated between the two skills.
