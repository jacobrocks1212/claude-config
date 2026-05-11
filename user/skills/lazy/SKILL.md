---
name: lazy
description: Stateless dispatcher — infers project state from filesystem, invokes exactly ONE sub-skill per invocation to progress the current feature
argument-hint: [optional: "status" to just report, or "skip" to skip current feature with reason]
plan-mode: never
---

# Lazy — Autonomous Feature Dispatcher

Stateless state machine for mobile development workflow. Each invocation:
1. Reads `docs/features/queue.json` for feature order
2. Infers the current feature's state from filesystem sentinel files
3. Invokes exactly ONE sub-skill to advance progress
4. Stops

Designed for fresh sessions. Run `/lazy` repeatedly to progress through the entire ROADMAP.

**HARD REQUIREMENT — ONE SKILL PER INVOCATION:** Execute at most one sub-skill (via Skill tool). After it completes, report what happened and STOP. Do not chain multiple skills.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. This skill dispatches directly.

**HARD REQUIREMENT — STATUS BOOKENDS:** Every /lazy invocation must produce two status messages:

1. **Before acting** (after determining current state, before invoking any skill):
   ```
   ## /lazy — {feature_name} (Tier {tier})
   **State:** {detected state from state machine}
   **Action:** {what skill will be invoked and why}
   ```
   No user confirmation needed — just announce and proceed.

2. **After acting** (after the dispatched skill returns or after a STOP decision):
   ```
   ## /lazy — Done
   **Completed:** {what was accomplished this invocation}
   **Issues:** {any problems encountered, or "None"}
   **Next `/lazy` will:** {what the next invocation will do based on current filesystem state}
   ```
   If there were issues (partial failures, warnings, unexpected state), surface them here.

---

## Step 0: Load Tools and Parse Arguments

1. Load PushNotification: `ToolSearch({ query: "select:PushNotification" })`
2. Parse `$ARGUMENTS`:
   - If `"status"` → run the same logic as `/lazy-status` (read-only report) and STOP
   - If `"skip"` → mark current feature as skipped (see Step 11) and STOP
   - If empty or anything else → proceed to Step 1

---

## Step 1: Load Queue

Read `docs/features/queue.json` from the project root. Extract the `queue` array.

If the file doesn't exist:
```
PushNotification({ message: "queue.json not found — /lazy cannot operate" })
```
STOP.

---

## Step 2: Find Current Feature

Read `docs/features/ROADMAP.md`.

For each item in the queue array (in order):
1. Check if the feature's row in ROADMAP.md contains `~~` (strikethrough) AND `COMPLETE`
2. The first feature that is NOT marked complete is the **current feature**

If ALL features are complete:
```
PushNotification({ message: "ALL FEATURES COMPLETE — AlgoBooth roadmap finished." })
```
Report this and STOP.

Save for later:
- `feature_name` = current feature's `name` from queue.json
- `feature_id` = current feature's `id`
- `spec_path` = `docs/features/{spec_dir}` (prepend project root)
- `tier` = current feature's `tier`

Announce: `"Current feature: {feature_name} (Tier {tier})"`

---

## Step 3: Check for Blockers

Check if `{spec_path}/BLOCKED.md` exists.

If it exists:
1. Read `BLOCKED.md` fully
2. Analyze the blocker context (phase, details, what was tried, recovery suggestion)
3. **Do NOT retry or delete BLOCKED.md.** Present the blocker to Jacob with a recommendation:
   ```
   PushNotification({ message: "BLOCKED: {feature_name} — {first line of details}. Awaiting your input." })
   ```
4. Report:
   - The full blocker details
   - Your recommended next action (one of):
     - `/lazy skip` — skip this feature and move to the next
     - `/add-phase` — add a corrective or workaround phase
     - Manual fix needed — describe what Jacob should do
     - Research needed — suggest what to investigate
   - A copyable command for whatever you recommend
5. STOP (Jacob decides what to do next; he deletes BLOCKED.md manually or via the action he takes)

---

## Step 4: Check SPEC.md

Check if `{spec_path}/SPEC.md` exists.

If missing:
1. Check if the spec_dir contains ANY files (RESEARCH.md, RESEARCH_PROMPT.md, etc.)
2. If the directory is empty or doesn't exist:
   ```
   PushNotification({ message: "{feature_name} needs spec input — no SPEC.md or research found. Provide direction via /spec." })
   ```
   Report and STOP (needs human input)
3. If research/context files exist:
   ```
   Skill({ skill: "spec", args: "{feature_name} — see {spec_path} for prior research" })
   ```
   STOP after skill returns.

---

## Step 5: Research Validation Gate

SPEC.md exists. Before proceeding to phases, verify the spec has been validated by research.

Check for research docs in `{spec_path}/`:
- `RESEARCH.md` or `RESEARCH_SUMMARY.md` — indicates research was completed

**If neither exists:**
1. Check if `RESEARCH_PROMPT.md` exists:
   - **Yes:** Research prompt was generated but results not yet provided. Notify:
     ```
     PushNotification({ message: "{feature_name}: research prompt exists but no results. Run Gemini deep research and provide results to /spec." })
     ```
     STOP (needs Jacob to run research and feed results back)
   - **No:** No research at all. Invoke /spec to generate the research prompt (it will skip Phase 1 brainstorming since SPEC.md exists, and go to Phase 2 research prompt generation):
     ```
     Skill({ skill: "spec", args: "{feature_name} — SPEC.md already exists at {spec_path}/SPEC.md, skip to Phase 2 (research prompt generation)" })
     ```
     STOP after skill returns.

**If RESEARCH.md exists but no RESEARCH_SUMMARY.md:**
- Invoke /spec to generate the research summary (skip to Phase 3):
  ```
  Skill({ skill: "spec", args: "{feature_name} — SPEC.md and RESEARCH.md exist at {spec_path}, skip to Phase 3 (integrate research and finalize spec)" })
  ```
  STOP after skill returns.

**If RESEARCH_SUMMARY.md exists:** Research is validated. Proceed to Step 6.

---

## Step 6: Check PHASES.md

Check if `{spec_path}/PHASES.md` exists.

If missing:
```
Skill({ skill: "spec-phases", args: "{spec_path}/SPEC.md" })
```
STOP after skill returns.

---

## Step 7: Check Phase Completion

Read `{spec_path}/PHASES.md`.

Count deliverables:
- **Unchecked:** lines matching `^\s*- \[ \]` (regex)
- **Checked:** lines matching `^\s*- \[x\]` (regex, case-insensitive)

### 7a. Phases Incomplete (unchecked > 0)

Check if an implementation plan exists — look in BOTH locations (legacy and current):
1. `{spec_path}/plans/` (glob for `all-phases-*.md` or `phase-*.md` — NOT `retro-*.md`)
2. `{spec_path}/PLAN.md` (legacy location — some features created before the plans/ convention)

**No implementation plan** → generate one:
```
Skill({ skill: "write-plan", args: "{spec_path}/PHASES.md" })
```
STOP after skill returns. (write-plan will create `{spec_path}/plans/{informative-name}.md`)

**Implementation plan exists** → execute it:
```
Skill({ skill: "execute-plan", args: "{spec_path}/plans/{plan-filename}" })
```
STOP after skill returns.

### 7b. All Phases Complete (unchecked = 0, checked > 0)

Proceed to Step 8 (MCP test gate).

---

## Step 8: MCP Test Gate

All implementation phases are complete. Now validate via MCP testing.

Check if `{spec_path}/VALIDATED.md` exists:
- If exists → proceed to Step 9 (retrospective)

Check if `{spec_path}/SKIP_MCP_TEST.md` exists:
- If exists → write `VALIDATED.md` (see format below with "MCP tests skipped" note) and STOP
  - Next invocation will pick up at Step 9

### 8a. Ensure MCP Test Scenarios Exist

Check if `{spec_path}/mcp-tests/` directory exists and contains symlinks.

**No mcp-tests/ directory or empty:**

Evaluate whether this feature has MCP-testable surface:
- Features with IPC/sidecar API, MCP tools, or UI state changes → testable
- Pure Rust DSP, no API surface, no observable state via MCP → not testable

**If NOT testable:** Write `{spec_path}/SKIP_MCP_TEST.md`:
```markdown
# MCP Test Skip

**Feature:** {feature_name} ({feature_id})
**Reason:** {why — e.g., "Pure audio-engine DSP with no IPC or MCP tool surface"}
**Alternative validation:** {e.g., "cargo test -p algobooth-audio-engine {module}"}
**Skipped by:** /lazy (automated assessment)
**Date:** {today}
```
Then STOP (next invocation will write VALIDATED.md and proceed).

**If testable:** Create the mcp-tests directory and invoke /mcp-test to create scenarios:
```bash
mkdir -p {spec_path}/mcp-tests
```
```
Skill({ skill: "mcp-test", args: "validate {feature_name} — create scenarios for all testable behavior from {spec_path}/SPEC.md" })
```
After /mcp-test returns:
1. Find any new scenario files it created in `docs/testing/mcp-tests/` that relate to this feature
2. Create symlinks from `{spec_path}/mcp-tests/` pointing to each scenario file:
   ```bash
   # Use relative path from spec_path/mcp-tests/ to docs/testing/mcp-tests/
   # Calculate the correct relative path based on directory depth
   ln -s <relative-path-to-docs/testing/mcp-tests/{scenario}.md> {spec_path}/mcp-tests/{scenario}.md
   ```
3. Proceed to Step 8b (do NOT stop — scenarios were just created, now run them)

### 8b. Run MCP Tests and Fix Until 100% Pass

**HARD REQUIREMENT:** MCP tests must reach 100% pass rate before marking validated. Do not accept partial passes.

Check if `{spec_path}/MCP_TEST_RESULTS.md` exists with `**Result:** All passing`:
- If yes → write VALIDATED.md and STOP (tests already passed in a prior invocation)

Run the linked scenarios:
```
Skill({ skill: "mcp-test", args: "{scenario-names from symlinks, space-separated}" })
```

After /mcp-test returns, evaluate results:

**100% passing:**
Write `{spec_path}/MCP_TEST_RESULTS.md`:
```markdown
# MCP Test Results

**Feature:** {feature_name} ({feature_id})
**Date:** {today}
**Scenarios:** {comma-separated scenario names}
**Result:** All passing
```
Write `{spec_path}/VALIDATED.md`:
```markdown
# Validated

**Feature:** {feature_name} ({feature_id})
**Date:** {today}
**MCP scenarios:** {comma-separated scenario names}
**Result:** All passing
```
STOP.

**Failures (not 100%):**

1. Document failures in `{spec_path}/MCP_TEST_RESULTS.md`:
   ```markdown
   # MCP Test Results

   **Feature:** {feature_name} ({feature_id})
   **Date:** {today}
   **Scenarios:** {comma-separated scenario names}
   **Result:** {pass_count}/{total_count} passing

   ## Failures
   {per-scenario failure details}
   ```

2. Assess each failure — is the fix quick and obvious?

   **Quick fix (< ~50 lines, clear root cause):**
   - Fix it directly in this session (edit the source code)
   - Add the fix details as Implementation Notes in PHASES.md
   - Re-run /mcp-test to verify the fix
   - If now 100% → write VALIDATED.md and STOP

   **Non-trivial fix (multi-file, unclear root cause, risky):**
   - Spawn a Sonnet subagent to fix it:
     ```
     Agent({
       model: "sonnet",
       description: "Fix MCP test failure for {feature_name}",
       prompt: "Fix the following MCP test failures for {feature_name}. Details: {failure details}. The implementation is in {relevant files}. Fix the root cause, don't patch the test expectations."
     })
     ```
   - After subagent returns, re-run /mcp-test
   - If now 100% → write VALIDATED.md and STOP

   **Still failing after fix attempt:**
   - Write `{spec_path}/BLOCKED.md`:
     ```markdown
     # BLOCKED

     **Feature:** {feature_name} ({feature_id})
     **Phase:** MCP Validation
     **Blocked at:** {ISO timestamp}
     **Retry count:** 0

     ## Details
     MCP test failures persist after fix attempt:
     {remaining failure details}

     ## What was tried
     {description of fix attempt}

     ## Recovery Suggestion
     Review failing scenarios in {spec_path}/mcp-tests/ and MCP_TEST_RESULTS.md.
     ```
   - STOP (next /lazy invocation will retry via Step 3 blocker handling)

---

## Step 9: Retrospective (Spec Alignment Validation)

`VALIDATED.md` exists — the feature is implemented and validated. Now run a retrospective that validates spec alignment before marking complete.

**CRITICAL:** The retro's sole responsibility is analysis — it surfaces divergences and writes a plan file. /lazy is responsible for acting on those findings:
- **Minor divergences** (naming changes, implementation details that don't affect behavior): handled by the retro plan during execution
- **Significant divergences** (missing spec requirements, behavior that contradicts spec, descoped items not documented): /lazy appends corrective phases to PHASES.md directly, forcing a new implementation cycle before the feature can be marked complete

### 9a. Determine retro state

Count retro plan files: glob `{spec_path}/plans/retro-*.md` → `retro_count`

---

**`RETRO_DONE.md` exists** → Proceed to Step 10 (mark complete)

---

**retro_count == 0 (first retro needed):**

Invoke /retro with --auto flag:
```
Skill({ skill: "retro", args: "{spec_path}/PHASES.md --auto" })
```
/retro writes a plan file to `{spec_path}/plans/retro-1-{feature-slug}.md`

**After /retro returns:** Check its output for significant spec divergences (look for "SIGNIFICANT SPEC DIVERGENCES FOUND"):
- **If divergences found:**
  1. Read the retro plan file to understand the divergences
  2. Append a corrective phase directly to `{spec_path}/PHASES.md`:
     ```markdown
     ### Phase N+1: Corrective — Spec Alignment
     
     **Scope:** Address significant spec divergences identified during retrospective.
     
     **Prerequisites:** All prior phases
     
     **Deliverables:**
     - [ ] {divergence 1 — what needs to be fixed/added}
     - [ ] {divergence 2 — what needs to be fixed/added}
     ```
  3. Delete `VALIDATED.md` (forces re-validation after corrective phases are implemented)
  4. STOP (next invocations: Step 7 → implement → Step 8 → re-validate → Step 9 → second retro)
- **If clean (no significant divergences):** STOP (next invocation executes the retro plan)

---

**retro_count == 1 AND no `RETRO_DONE.md`:**

Read the existing retro plan. Check if it reported significant divergences (has non-empty "Significant" table in `## Spec Divergences` section):

- **First retro was clean (no significant divergences):**
  - Execute the retro plan:
    ```
    Skill({ skill: "execute-plan", args: "{retro-plan-path}" })
    ```
  - After /execute-plan returns, write `{spec_path}/RETRO_DONE.md`:
    ```markdown
    # Retro Complete

    **Feature:** {feature_name} ({feature_id})
    **Date:** {today}
    **Rounds:** 1 (clean — no significant divergences)
    **Retro plan:** {retro-plan-filename}
    ```
  - STOP

- **First retro had divergences (second retro needed to verify fixes):**
  - Invoke /retro again:
    ```
    Skill({ skill: "retro", args: "{spec_path}/PHASES.md --auto" })
    ```
  - /retro writes `{spec_path}/plans/retro-2-{feature-slug}.md`
  - STOP (next invocation: retro_count == 2, executes latest plan)

---

**retro_count >= 2 AND no `RETRO_DONE.md`:**

Execute the latest retro plan (highest numbered):
```
Skill({ skill: "execute-plan", args: "{latest-retro-plan-path}" })
```
After /execute-plan returns, write `{spec_path}/RETRO_DONE.md`:
```markdown
# Retro Complete

**Feature:** {feature_name} ({feature_id})
**Date:** {today}
**Rounds:** {retro_count}
**Retro plans:** {comma-separated retro plan filenames}
```
STOP

---

## Step 10: Mark Feature Complete

`VALIDATED.md` AND `RETRO_DONE.md` exist — the feature is fully implemented, validated, and reviewed.

1. **Update ROADMAP.md:**
   - Find the feature's row by matching `feature_name` in the ROADMAP table
   - Wrap the feature name and description in strikethrough (`~~`)
   - Append `**COMPLETE**` to the description
   - Follow the pattern of existing completed features (Tier 0 items)

2. **Clean up sentinel files:**
   ```bash
   rm -f {spec_path}/VALIDATED.md
   rm -f {spec_path}/RETRO_DONE.md
   ```
   (Keep SKIP_MCP_TEST.md, MCP_TEST_RESULTS.md, and plans/ — they document decisions)

3. **Update SPEC.md status:**
   - Change `**Status:**` line to `Complete`

4. **Commit all changes:**
   ```
   Skill({ skill: "commit", args: "feat({feature_id}): complete — all phases implemented, validated, and retro done" })
   ```

5. **Notify:**
   - Determine the next feature in queue (next non-complete item)
   ```
   PushNotification({ message: "{feature_name} COMPLETE. Next: {next_feature_name}. Run /lazy to continue." })
   ```

6. Report completion summary and STOP.

---

## Step 11: Skip Current Feature

Only triggered when `$ARGUMENTS` contains `"skip"`.

1. Find the current feature (Steps 1-2)
2. Ask why (via AskUserQuestion): "Why should {feature_name} be skipped?"
3. Update ROADMAP.md: append `(SKIPPED — {reason})` to the feature row
4. The next `/lazy` invocation will automatically pick up the following feature
5. STOP

---

## Work Log (MANDATORY — DO NOT SKIP)

Every /lazy invocation that performs meaningful work MUST call `interview_work_log_append` before producing the "After" status bookend. This is non-negotiable — it is the authoritative record of all autonomous progress.

Load the tool: `ToolSearch({ query: "select:mcp__plugin_interview-prep-plugin_interview-prep__interview_work_log_append" })`

Call with:
- `skill`: `"lazy"`
- `project`: `"algobooth"`
- `title`: `"/lazy → {action taken}"` (e.g., "/lazy → /execute-plan phase 3")
- `summary`: 2-4 sentences. What state was detected, what skill was dispatched, what it accomplished, any issues.
- `files_modified`: files modified during this invocation (from sub-skill output)
- `technologies`: relevant tech stack
- `patterns`: patterns applied
- `technical_context`: architectural context of what was implemented

**Skip work-log only when:** /lazy did nothing meaningful (e.g., reported a blocker without invoking a skill, or all features were already complete).

**The sub-skill invoked by /lazy is ALSO expected to log its own work** — both logs are required. /lazy logs the dispatch-level view; the sub-skill logs the implementation-level detail.

---

## Sentinel Files Reference

| File | Created by | Purpose | Lifecycle |
|------|-----------|---------|-----------|
| `plans/*.md` | /write-plan, /retro, etc. | Colocated plan files | Persists (audit trail) |
| `BLOCKED.md` | /execute-plan or /lazy | Blocker details | Persists until Jacob resolves (manual delete or via chosen action) |
| `MCP_TEST_RESULTS.md` | /lazy (after mcp-test) | Test results with pass/fail details | Persists permanently (audit trail) |
| `VALIDATED.md` | /lazy (after 100% pass) | Validation gate | Deleted on feature completion |
| `SKIP_MCP_TEST.md` | /lazy (assessment) | Documents why MCP testing was skipped | Persists permanently |
| `RETRO_DONE.md` | /lazy (after retro execution) | Retro completion gate | Deleted on feature completion |
| `mcp-tests/*.md` | /lazy (symlinks) | Links to test scenarios | Persists permanently |

---

## State Machine Summary

```
queue.json → find current feature → check state → invoke ONE skill → STOP

BLOCKED.md exists?                    → present blocker + recommend action → STOP
SPEC.md missing?                      → /spec (or notify if no research)
SPEC.md exists + no RESEARCH_SUMMARY? → /spec (generate research prompt or integrate results)
PHASES.md missing?                    → /spec-phases
Unchecked deliverables + no plan?     → /write-plan (writes to plans/ subdir)
Unchecked deliverables + plan exists? → /execute-plan
All checked + no VALIDATED.md?        → /mcp-test (with symlink creation)
VALIDATED.md + 0 retro plans?         → /retro --auto (round 1; adds corrective phases if divergences)
VALIDATED.md + 1 retro plan (clean)?  → /execute-plan (retro plan) → RETRO_DONE.md
VALIDATED.md + 1 retro plan (had divergences)? → /retro --auto (round 2; verify fixes)
VALIDATED.md + 2+ retro plans?        → /execute-plan (latest retro plan) → RETRO_DONE.md
RETRO_DONE.md exists?                 → mark complete on ROADMAP + notify
```
