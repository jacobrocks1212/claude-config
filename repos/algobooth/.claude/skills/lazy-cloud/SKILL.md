---
name: lazy-cloud
description: Cloud-environment variant of /lazy — advances the AlgoBooth queue with the same state machine, but defers any step that cannot run in a cloud-based Linux environment (e.g. MCP testing requiring the desktop Tauri app) and documents the deferral so a later /lazy run from a workstation picks up exactly where this run stopped. The `__mark_complete__` special action runs the MCP-coverage audit gate (Step 4.4) before the SPEC flip — uncovered SPEC Locked Decisions write NEEDS_INPUT.md and defer the flip; the audit is docs-only and runs identically in cloud
argument-hint: [optional: "status" to report, "skip" to skip current feature, or an ad-hoc task / `--adhoc "<task>"` to enqueue work at the top of the queue]
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

All sentinel files this skill reads or writes follow the canonical YAML-frontmatter schema.

**Sentinel frontmatter schema:** when you write or validate any sentinel file (NEEDS_INPUT.md / BLOCKED.md / VALIDATED.md / COMPLETED.md / DEFERRED_NON_CLOUD.md / etc.), **Read `~/.claude/skills/_components/sentinel-frontmatter.md`** for the required `kind:`/`provenance:`/field schema. (Read on demand — do not assume it is already in context.)

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

## Step 0.0: Environment Preflight (FIRST — before the start banner and before remote sync)

**Read and follow `~/.claude/skills/_components/lazy-preflight.md` as the very first action of this
invocation — before the start banner, before Step 0.4 remote sync, before the first state probe.**
Run its read-only check block (skills symlink resolves, `~/.claude/scripts/lazy-state.py` exists,
`python3` runs, node resolvable — prepending `/c/nvm4w/nodejs` if needed). If any check fails, print the
component's setup recipe and **STOP — zero cycles consumed** (do not print the banner, do not call the
state script, do not enter the loop). On success, node is on PATH for the whole session (no per-call
`export PATH`), and you continue to the banner / Step 0.4 as normal.

---

## Step 0: Load Tools and Parse Arguments

1. Load PushNotification: `ToolSearch({ query: "select:PushNotification" })`
2. Parse `$ARGUMENTS`:
   - If `"status"` → run the same logic as `/lazy-status` (read-only report) and STOP. Additionally, if any feature has a `DEFERRED_NON_CLOUD.md`, list those features and what step is deferred.
   - If `"skip"` → mark current feature as skipped (see Step 5) and STOP
   - If it starts with `--adhoc` (optionally followed by task text), OR is any other non-empty free-text that is not one of the keywords above → treat it as an **ad-hoc task**: run **Step 0.3 (Ad-hoc Enqueue)**, then proceed to Step 1. (`--adhoc` with no text infers the task from the conversation.)
   - If empty → proceed to Step 1 (normal queue order)

---

## Step 0.3: Ad-hoc Enqueue (only when an ad-hoc task was supplied)

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

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

If `terminal_reason` is set, branch exactly as `/lazy` does (Step 2a operator-resolvable vs Step 2b clean stop) — `/lazy-cloud` does not dead-end on a recoverable obstacle either.

### 2a. Operator-resolvable terminals → ask for a resolution path (do NOT bare-STOP)

For `blocked`, `needs-input`, `completion-unverified`, `needs-spec-input`, and `stale_upstream`, follow the shared operator-directed halt-resolution component (`~/.claude/skills/_components/halt-resolution.md`) exactly as `/lazy` Step 2a does: re-print the obstacle context, `AskUserQuestion` the resolution path, dispatch the Opus apply-resolution subagent to enact it (neutralize sentinels by RENAME), then STOP per the single-dispatch post-enact rule (the next `/lazy-cloud` continues). Use the matrix's `blocked` / `needs-input` rows. Cloud caveat: the apply subagent's enactment is docs-only here (no Tauri/MCP); for `needs-spec-input` (interactive only) it dispatches `/spec` via the Skill tool. **Headless detection:** attempt the `AskUserQuestion`; if the tool is unavailable / errors as not-supported (a non-interactive / headless / cron cloud run), fall back to the legacy **report + STOP** for these terminals (surface the sentinel body + recovery in the after-bookend, STOP) — the operator resolves on their next interactive run. Do NOT block waiting for input.

### 2b. Clean-stop terminals → report + STOP

PushNotify with `notify_message` and STOP, with cloud-specific after-bookends:

| `terminal_reason` | Cloud behavior |
|------|---|
| `needs-research` | Surface RESEARCH_PROMPT.md path; cloud cannot run Gemini either (re-run after upload continues) |
| `all-features-complete` | Roadmap done |
| `cloud-queue-exhausted` | Every remaining feature is cloud-saturated; workstation /lazy is needed to finalize |
| `device-queue-exhausted` | A remaining feature carries `DEFERRED_REQUIRES_DEVICE.md` (real-device-only assertions) but no `DEFERRED_NON_CLOUD.md`. Cloud has no device either — surface it and tell the user a **real-device** /lazy host is needed to certify the deferred scenarios. (Rare in cloud: cloud-saturated features normally carry `DEFERRED_NON_CLOUD.md` and hit `cloud-queue-exhausted` first.) |
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

### `__flip_plan_complete_cloud_saturated__`

`sub_skill_args` is the absolute path of a plan file with `status: In-progress`. Emitted at Step 7a when an In-progress plan's only unchecked WUs (scoped to its `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. The documented exit is to flip the plan's frontmatter `status:` from `In-progress` to `Complete` so future cloud cycles treat this plan part as cloud-saturated and proceed to Step 8 retro / Step 9 deferral / Step 2 cloud-saturated skip — instead of looping on `Step 7a: execute plan` no-ops.

1. Read the plan file. Locate the `status:` line inside the YAML frontmatter fence (`---` ... `---`).
2. Replace ONLY the value: `In-progress` → `Complete`. Leave every other frontmatter field and the markdown body untouched. If the line is already `Complete`, no-op (idempotent).
3. Derive the plan part number from `phases:` (e.g. `phases: [6]` → "part 6"); fall back to the filename's leading `part-N` / `phase-N` token if absent.
4. Stage the plan file and invoke `Skill({ skill: "commit", args: "chore({feature_id}): mark plan part N Complete (cloud-saturated)" })`.
5. Print the after-status bookend (Completed: "flipped {plan filename} status to Complete (cloud-saturated)"), call work-log, STOP.

This pseudo-skill never touches SPEC.md, ROADMAP.md, or any sentinel — it is a single-field frontmatter flip plus commit. The cloud-saturated audit trail lives in `DEFERRED_NON_CLOUD.md`; the plan's `status: Complete` is just the state-machine signal that no further cloud `/execute-plan` cycles should fire on this plan part.

### `__mark_complete__`

`sub_skill_args` is `{spec_path}`. Both VALIDATED.md AND RETRO_DONE.md exist (e.g., workstation produced VALIDATED.md while cloud has RETRO_DONE.md). Cloud CAN complete in this case — **but the MCP-coverage audit gate (Step 4.4) runs first**. The audit is docs-only (reads SPEC.md + `mcp-tests/*.md`, no Tauri / no MCP server) so it works identically in cloud and workstation. This closes the 30%-of-features Reopened-Complete gap the audit walk surfaced.

**Step 4.4: MCP-coverage audit (NEW — runs BEFORE the flip).**

!`cat ~/.claude/skills/_components/mcp-coverage-audit.md`

Run the audit per the component above with `{spec_path}` and `{feature_id}`. If the audit returns:

- `clean` — proceed to the completion-integrity gate (Step 4.5 below).
- `uncovered:N` — the audit just wrote `{spec_path}/NEEDS_INPUT.md`. Do NOT run the finalize steps. Print the after-status bookend (Completed: "MCP-coverage audit halted mark-complete — {N} locked decision(s) need coverage", Next `/lazy-cloud` will: "Surface NEEDS_INPUT.md decisions and either author MCP coverage or accept test-exempt for each"), call work-log, STOP.

**Step 4.5: Completion-integrity gate (NEW — runs after the coverage audit returns `clean`, before the flip).**

!`cat ~/.claude/skills/_components/completion-integrity-gate.md`

Run the gate per the component above with `{spec_path}`, `{feature_id}`, and `{cloud}=true`. In cloud, `DEFERRED_NON_CLOUD.md` satisfies the validation-sentinel check ONLY when `VALIDATED.md` is also present (cloud completes a feature whose MCP pass was produced on a workstation); a bare deferral with no `VALIDATED.md` should never reach mark-complete (Step 2's cloud-saturated skip catches it). If the gate returns:

- `gated` — `{spec_path}/COMPLETED.md` has been written (validation evidence folded in). Proceed to the finalize steps below.
- `refused:<reason>` — the gate just wrote `{spec_path}/NEEDS_INPUT.md`. Do NOT run the finalize steps. Print the after-status bookend (Completed: "completion-integrity gate halted mark-complete — {reason}", Next `/lazy-cloud` will: "Surface NEEDS_INPUT.md and reconcile the completion gap"), call work-log, STOP.

**Finalize steps (only when BOTH gates passed — coverage `clean` AND integrity `gated`):**

On `gated`, the gate has already run `python3 ~/.claude/scripts/lazy-state.py --apply-pseudo __mark_complete__ {spec_path}` — the script is the **sole author** of the `COMPLETED.md` receipt (validation evidence folded in), the SPEC.md/PHASES.md `**Status:** Complete` flips, and the deletion of the consumed `VALIDATED.md` / `RETRO_DONE.md` / `DEFERRED_NON_CLOUD.md` sentinels (`COMPLETED.md` / `SKIP_MCP_TEST.md` / `MCP_TEST_RESULTS.md` / `plans/` are kept). Do NOT re-perform any of those writes by hand. The remaining mechanics are:

1. Update `docs/features/ROADMAP.md` — wrap the feature row in `~~ ... ~~` and append `**COMPLETE**` (the one docs write the script does not perform).
2. Invoke `Skill({ skill: "commit", args: "feat({feature_id}): complete — all phases implemented, validated, and retro done" })`.
3. PushNotification: `"{feature_name} COMPLETE. Run /lazy-cloud to continue."`
4. Print the after-status bookend, call work-log, STOP.

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
| `SKIP_MCP_TEST.md` | /lazy (assessment) — never written by /lazy-cloud | Documents why MCP testing was skipped (permanent waiver) | Persists permanently |
| `DEFERRED_REQUIRES_DEVICE.md` | /mcp-test on a no-real-device host — NEVER /lazy-cloud | Defers real-device-only assertions to a real-device host (NOT a skip) | Deleted by a real-device run after it certifies the deferred scenarios |
| `RETRO_DONE.md` | /lazy[-cloud] (after retro execution) | Retro completion gate | Deleted on feature completion |
| **`DEFERRED_NON_CLOUD.md`** | **/lazy-cloud (cloud-blocked step)** | **Documents step deferred to workstation /lazy** | **Deleted on feature completion — left in place by /lazy as audit trail until then** |
| `NEEDS_RESEARCH.md` | /lazy-batch[-cloud] | Halt: research prompt exists, awaiting human Gemini run | Deleted when RESEARCH.md is dropped in place |
| `NEEDS_INPUT.md` | any `--batch` skill | Halt: ambiguous decision encountered | Deleted when the human resolves the decision |

---

## State Machine Summary

The state machine lives in `~/.claude/scripts/lazy-state.py`. Pass `--cloud` to get the cloud-aware variants (Step 2 skip, **Step 8 retro runs in cloud**, Step 9 MCP deferral, Step 10 halt). This skill is a thin LLM wrapper that runs the script, dispatches the named sub-skill or performs the named special action, and stops.

**Current step ordering after phases complete:** Step 8 retro → Step 9 MCP test (deferred in cloud) → Step 10 mark complete. `/retro` runs FIRST so the implementation-time retrospective gate fires regardless of whether MCP testing is available. The lazy state machine does not auto-loop retro — additional rounds are triggered only by `/retro` itself writing a follow-up plan.

```
[ad-hoc task supplied?]  → Step 0.3 enqueue at top of queue (Bash, once) → fall through
lazy-state.py --cloud → JSON {sub_skill, sub_skill_args, terminal_reason}

terminal_reason set?                                       → notify + STOP
sub_skill = "__write_deferred_non_cloud__"                 → write DEFERRED_NON_CLOUD.md + STOP
sub_skill = "__write_validated_from_skip__"                → write VALIDATED.md (from SKIP_MCP_TEST) + STOP
sub_skill = "__flip_plan_complete_cloud_saturated__"       → flip plan frontmatter In-progress → Complete + commit + STOP
sub_skill = "__mark_complete__"                            → ROADMAP edit + sentinel cleanup + commit + STOP
sub_skill = real skill?                                    → Skill({skill, args}) → work-log → STOP
```

This skill and the paired `/lazy` are coupled per CLAUDE.md — their only intended divergence is whether they pass `--cloud` to lazy-state.py. Any state-machine change goes into the script, not into prose duplicated between the two skills.
