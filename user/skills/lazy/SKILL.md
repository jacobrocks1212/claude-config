---
name: lazy
description: Stateless dispatcher — infers project state from filesystem via lazy-state.py, invokes exactly ONE sub-skill per invocation to progress the current feature
argument-hint: [optional: "status" to just report, or "skip" to skip current feature with reason]
plan-mode: never
---

# Lazy — Autonomous Feature Dispatcher

Thin LLM wrapper around `~/.claude/scripts/lazy-state.py`. Each invocation:

1. Loads tools and parses arguments
2. Runs the state script to determine the next action
3. Either reports a terminal state and stops, or dispatches **exactly one** sub-skill
4. Logs work and stops

Designed for fresh sessions. Run `/lazy` repeatedly to progress through the entire ROADMAP. The state-machine logic lives in `lazy-state.py` (source of truth). This skill is dispatch glue.

**HARD REQUIREMENT — ONE SKILL PER INVOCATION:** Execute at most one sub-skill (via Skill tool). After it completes, report what happened and STOP. Do not chain multiple skills.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. This skill dispatches directly.

**HARD REQUIREMENT — STATUS BOOKENDS:** Every /lazy invocation must produce two status messages:

1. **Before acting** (after running lazy-state.py, before invoking any skill):
   ```
   ## /lazy — {feature_name} (Tier {tier})
   **State:** {current_step from state script}
   **Action:** {what skill will be invoked and why}
   ```
   No user confirmation needed — just announce and proceed.

2. **After acting** (after the dispatched skill returns or after a STOP decision):
   ```
   ## /lazy — Done
   **Completed:** {what was accomplished this invocation}
   **Issues:** {any problems encountered, or "None"}
   **Next `/lazy` will:** {best guess based on the state script's output, or "Run lazy-state.py to find out"}
   ```
   If there were issues (partial failures, warnings, unexpected state), surface them here.

---

## Sentinel File Format

All sentinel files this skill reads or writes follow the canonical YAML-frontmatter schema:

!`cat ~/.claude/skills/_components/sentinel-frontmatter.md`

When this skill writes a sentinel (Step 4 special actions), emit the YAML frontmatter first, then a blank line, then a human-readable markdown body. When this skill reads a sentinel, parse the frontmatter per the protocol above; the markdown body is for humans only.

---

## Step 0: Load Tools and Parse Arguments

1. Load PushNotification: `ToolSearch({ query: "select:PushNotification" })`
2. Parse `$ARGUMENTS`:
   - If `"status"` → run the same logic as `/lazy-status` (read-only report) and STOP
   - If `"skip"` → mark current feature as skipped (see Step 5) and STOP
   - If empty or anything else → proceed to Step 1

---

## Step 1: Run lazy-state.py

Invoke the state inference script with the project root as the working directory:

```bash
python3 ~/.claude/scripts/lazy-state.py
```

Capture stdout (a single JSON object). If the script exits non-zero, surface the error to the user and STOP — do not try to parse malformed state.

Parse the JSON. You now have:
- `feature_id`, `feature_name`, `spec_path` — current feature context (null if no current feature)
- `current_step` — human-readable description of where we are in the state machine
- `sub_skill` — the skill to dispatch (null when terminal or when a special action is needed)
- `sub_skill_args` — exact args string for the sub-skill
- `terminal_reason` — set when the state machine halts (e.g. `"blocked"`, `"needs-research"`, `"all-features-complete"`)
- `notify_message` — string for PushNotification when terminal

---

## Step 2: Handle Terminal States

If `terminal_reason` is set:

1. PushNotification with `notify_message`.
2. Print the **before** status bookend (use `current_step` as State, `"halt — {terminal_reason}"` as Action).
3. Print the **after** status bookend (Completed: "halted on {terminal_reason}"; Next `/lazy` will: "Wait for the underlying condition to be resolved before re-running.")
4. STOP. Skip the work-log step (terminal halts without dispatch are not meaningful work).

Special handling per terminal reason:

| `terminal_reason` | Operator action implied |
|------|---|
| `blocked` | Read `{spec_path}/BLOCKED.md`, present details + recovery suggestion |
| `needs-research` | Surface the RESEARCH_PROMPT.md path so the user runs Gemini |
| `needs-input` | Read `{spec_path}/NEEDS_INPUT.md`, list the decisions a `--batch` skill halted on |
| `needs-spec-input` | Tell the user to run `/spec` directly — no inputs to dispatch on |
| `all-features-complete` | Roadmap done; nothing else to do |
| `cloud-queue-exhausted` | Workstation-only path — does not occur for plain `/lazy` |
| `queue-missing` | queue.json missing — surface the expected path |

---

## Step 3: Handle Special Actions (sentinel writes / completion)

If `sub_skill` begins with `__` (double-underscore), it is a **special action** the wrapper performs directly, not a Skill dispatch. The wrapper itself does the small file edits and commit:

### `__write_validated_from_skip__`

`sub_skill_args` is `{spec_path}`. SKIP_MCP_TEST.md exists; write VALIDATED.md so the state machine progresses to retro on the next invocation.

1. Parse `{spec_path}/SKIP_MCP_TEST.md`'s frontmatter.
2. Write `{spec_path}/VALIDATED.md` with kind `validated`, `mcp_scenarios: []`, `result: all-passing`, and a body note: "MCP tests skipped per prior SKIP_MCP_TEST.md".
3. Print the after-status bookend, call work-log, STOP.

### `__write_validated_from_results__`

`sub_skill_args` is `{spec_path}`. MCP_TEST_RESULTS.md exists with all-passing; write VALIDATED.md.

1. Parse `{spec_path}/MCP_TEST_RESULTS.md`'s frontmatter — extract `scenarios`.
2. Write `{spec_path}/VALIDATED.md` with kind `validated`, the parsed scenarios, `result: all-passing`.
3. Print the after-status bookend, call work-log, STOP.

### `__flip_plan_complete_cloud_saturated__`

`sub_skill_args` is the absolute path of a plan file with `status: In-progress`. Emitted only by `lazy-state.py --cloud` (so plain `/lazy` will essentially never see it; included here for symmetry with `/lazy-cloud` and as a defensive handler).

Conditions when emitted: the plan's only unchecked WUs (scoped to its `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. The documented exit is to flip the plan's frontmatter `status:` from `In-progress` to `Complete` so future state-script calls treat this plan part as cloud-saturated and proceed to Step 8 retro / Step 9 deferral / Step 2 cloud-saturated skip.

1. Read the plan file. Locate the `status:` line inside the YAML frontmatter fence (`---` ... `---`).
2. Replace ONLY the value: `In-progress` → `Complete`. Leave every other frontmatter field and the markdown body untouched. If the line is already `Complete`, no-op (idempotent).
3. Derive the plan part number from `phases:` (e.g. `phases: [6]` → "part 6"); fall back to the filename's leading `part-N` / `phase-N` token if absent.
4. Stage the plan file and invoke `Skill({ skill: "commit", args: "chore({feature_id}): mark plan part N Complete (cloud-saturated)" })`.
5. Print the after-status bookend, call work-log, STOP.

This pseudo-skill never touches SPEC.md, ROADMAP.md, or any sentinel — it is a single-field frontmatter flip plus commit.

### `__mark_complete__`

`sub_skill_args` is `{spec_path}`. VALIDATED.md AND RETRO_DONE.md both exist; finalize per /lazy's original Step 10:

1. Update `docs/features/ROADMAP.md` — find the feature row, wrap name+description in `~~ ... ~~`, append `**COMPLETE**`.
2. Delete sentinels: `VALIDATED.md`, `RETRO_DONE.md`, `DEFERRED_NON_CLOUD.md` if present. Keep `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`, `plans/`.
3. Update `{spec_path}/SPEC.md` — change `**Status:**` line to `Complete`.
4. Invoke `Skill({ skill: "commit", args: "feat({feature_id}): complete — all phases implemented, validated, and retro done" })`.
5. PushNotification: `"{feature_name} COMPLETE. Run /lazy to continue."`
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
1. Print the after-status bookend (Completed: "ran /<sub_skill>", Next `/lazy` will: "Re-run lazy-state.py to determine.").
2. Call the work-log step below.
3. STOP.

The sub-skill is responsible for its own internal status bookends and work-log entry. /lazy's work-log entry captures the dispatch-level view only.

---

## Step 5: Skip Current Feature

Only triggered when `$ARGUMENTS` contains `"skip"`.

1. Run `python3 ~/.claude/scripts/lazy-state.py` to find the current feature.
2. Ask why (via AskUserQuestion): "Why should {feature_name} be skipped?"
3. Update ROADMAP.md: append `(SKIPPED — {reason})` to the feature row.
4. The next `/lazy` invocation will automatically pick up the following feature.
5. STOP.

---

## Work Log (MANDATORY — DO NOT SKIP)

Every /lazy invocation that performs meaningful work MUST call `interview_work_log_append` before producing the "After" status bookend.

Load the tool: `ToolSearch({ query: "select:mcp__plugin_interview-prep-plugin_interview-prep__interview_work_log_append" })`

Call with:
- `skill`: `"lazy"`
- `project`: project root basename
- `title`: `"/lazy → {action taken}"` (e.g., "/lazy → /execute-plan phase 3")
- `summary`: 2-4 sentences. What state was detected, what skill was dispatched (or what special action ran), what it accomplished, any issues.
- `files_modified`: files modified during this invocation (from sub-skill output, plus any sentinel writes the wrapper performed)
- `technologies`: relevant tech stack
- `patterns`: patterns applied
- `technical_context`: architectural context of what was implemented

**Skip work-log only when:** /lazy did nothing meaningful (terminal halt without dispatch, status query, or skip command).

**The sub-skill invoked by /lazy is ALSO expected to log its own work** — both logs are required when a dispatch happened. /lazy logs the dispatch-level view; the sub-skill logs the implementation-level detail.

---

## Sentinel Files Reference

| File | Created by | Purpose | Lifecycle |
|------|-----------|---------|-----------|
| `plans/*.md` | /write-plan, /retro, etc. | Colocated plan files | Persists (audit trail) |
| `BLOCKED.md` | /execute-plan or /lazy | Blocker details | Persists until Jacob resolves |
| `MCP_TEST_RESULTS.md` | /lazy (after mcp-test) | Test results with pass/fail details | Persists permanently (audit trail) |
| `VALIDATED.md` | /lazy (after 100% pass) | Validation gate | Deleted on feature completion |
| `SKIP_MCP_TEST.md` | /lazy (assessment) | Documents why MCP testing was skipped | Persists permanently |
| `RETRO_DONE.md` | /lazy (after retro execution) | Retro completion gate | Deleted on feature completion |
| `NEEDS_RESEARCH.md` | /lazy-batch | Halt: research prompt exists, awaiting human Gemini run | Deleted when RESEARCH.md is dropped in place |
| `NEEDS_INPUT.md` | any `--batch` skill | Halt: ambiguous decision encountered | Deleted when the human resolves the decision |
| `mcp-tests/*.md` | /lazy (symlinks) | Links to test scenarios | Persists permanently |

---

## State Machine Summary

The state machine lives in `~/.claude/scripts/lazy-state.py`. This skill is a thin LLM wrapper that runs the script, dispatches the named sub-skill, and stops. See the script's docstring for the full per-step dispatch table; the high-level shape is:

```
lazy-state.py → JSON {sub_skill, sub_skill_args, terminal_reason}

terminal_reason set?     → notify + STOP
sub_skill = "__*__"?     → wrapper performs special action (sentinel write / mark complete) + STOP
sub_skill = real skill?  → Skill({skill, args}) → work-log → STOP
```

The script mirrors the state machine documented in earlier revisions of this file (Step 3 blocker, Step 4 SPEC, Step 4.5 stub, Step 4.6 realign, Step 5 research gate, Step 6 phases, Step 7 plan, **Step 8 retro, Step 9 MCP**, Step 10 mark-complete). When the state machine needs to change, update `lazy-state.py` — and keep this skill's wrapper logic + the paired `/lazy-cloud` skill (per CLAUDE.md coupling rule) in sync.

**Step 8 / Step 9 ordering (current):** `/retro` runs BEFORE `/mcp-test`. Rationale: cloud halts at the MCP-test deferral point, so under the old (MCP → retro) order, cloud runs never reached retro and workstation runs lacked an implementation-time retrospective gate. `/retro` is a docs/analysis pass — no Tauri, no MCP — so it runs identically in cloud and workstation. Step 8 is gated on `PHASES.md` all-phases-Complete AND no open BLOCKED/NEEDS_INPUT, and it runs **once per round** (additional rounds are triggered only by `/retro` itself writing a follow-up plan; the lazy state machine does not auto-loop retro). Step 9 (MCP test) is gated on `RETRO_DONE.md` presence — `lazy-state.py` will never dispatch `/mcp-test` until retro has concluded. Cloud Step 9 writes `DEFERRED_NON_CLOUD.md`; workstation Step 9 runs `/mcp-test`.
