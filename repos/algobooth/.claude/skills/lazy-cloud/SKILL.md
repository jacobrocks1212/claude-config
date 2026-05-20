---
name: lazy-cloud
description: Cloud-environment variant of /lazy — advances the AlgoBooth queue with the same state machine, but defers any step that cannot run in a cloud-based Linux environment (e.g. MCP testing requiring the desktop Tauri app) and documents the deferral so a later /lazy run from a workstation picks up exactly where this run stopped
argument-hint: [optional: "status" to just report, or "skip" to skip current feature with reason]
plan-mode: never
---

# Lazy Cloud — Autonomous Feature Dispatcher (Cloud Mode)

Drop-in cloud variant of `/lazy` for the AlgoBooth roadmap. Same stateless state machine, same sentinel files, same one-skill-per-invocation rule — but aware that this session runs in an ephemeral cloud Linux container with no Tauri desktop, no audio device, and no `tauri:dev` server.

When the state machine would normally dispatch a step that requires the desktop environment (today: MCP testing via the Tauri sidecar), this skill writes a `DEFERRED_NON_CLOUD.md` sentinel describing the deferred step and **continues to the next cloud-safe step** (today: the retrospective). It deliberately avoids writing any sentinel (`VALIDATED.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) that would let the natural state machine move past the deferred step — so when `/lazy` is run later from a workstation, it sees the same state lazy-cloud saw and resumes the deferred work cleanly.

Cloud cannot mark a feature complete on its own — Step 10 still requires `VALIDATED.md`, which only the workstation `/lazy` can produce. So /lazy-cloud's terminal state for a feature is "all phases implemented, retro done, MCP testing deferred to workstation".

Once a feature reaches that terminal cloud state, subsequent /lazy-cloud invocations skip it at Step 2 and advance to the next eligible feature in the queue. /lazy-cloud only stops with "nothing to do" when every remaining feature is either workstation-complete or cloud-saturated (i.e., the entire roadmap tail is waiting on workstation MCP testing).

**HARD REQUIREMENT — ONE SKILL PER INVOCATION:** Execute at most one sub-skill (via Skill tool). After it completes, report what happened and STOP. Do not chain multiple skills. Writing a sentinel file (e.g. `DEFERRED_NON_CLOUD.md`) and then falling through to invoke the next eligible skill in the same invocation does NOT count as two skills — only Skill-tool dispatches count.

**HARD REQUIREMENT — NO PLAN MODE:** Do NOT call `EnterPlanMode` or `ExitPlanMode`. This skill dispatches directly.

**HARD REQUIREMENT — NEVER WRITE PERMANENT SKIP MARKERS FROM CLOUD:** Do not write `SKIP_MCP_TEST.md`, `VALIDATED.md`, or `MCP_TEST_RESULTS.md` for a feature whose MCP-testability was not actually evaluated against a running Tauri app in this session. Permanent decisions about test coverage require the workstation environment.

**HARD REQUIREMENT — STATUS BOOKENDS:** Every /lazy-cloud invocation must produce two status messages:

1. **Before acting** (after determining current state, before invoking any skill):
   ```
   ## /lazy-cloud — {feature_name} (Tier {tier})
   **Environment:** Cloud Linux (no Tauri/MCP)
   **State:** {detected state from state machine}
   **Action:** {what skill will be invoked, or "DEFER — {reason}" if cloud-blocked}
   ```
   No user confirmation needed — just announce and proceed.

2. **After acting** (after the dispatched skill returns or after a STOP decision):
   ```
   ## /lazy-cloud — Done
   **Completed:** {what was accomplished this invocation — include both the deferral (if any) AND the follow-on skill that ran after the fall-through}
   **Deferred:** {description of any step deferred + path to DEFERRED_NON_CLOUD.md, or "None"}
   **Issues:** {any problems encountered, or "None"}
   **Next `/lazy` (workstation) will:** {what a non-cloud /lazy invocation should pick up — usually the deferred Step 8 MCP testing}
   **Next `/lazy-cloud` will:** {what the next cloud invocation will do, or "Nothing further — awaiting workstation /lazy for deferred MCP test"}
   ```

---

## Cloud Environment Limitations

The cloud session runs in an ephemeral Linux container with:

- **No Tauri desktop runtime** — cannot launch `tauri:dev`, cannot host the Rust sidecar, cannot reach the MCP HTTP server.
- **No audio output device** — cannot validate audio pipelines via RMS metering or `load_test_tone`.
- **No Windows-only tooling** — anything requiring Windows paths, PowerShell, or Windows-specific dependencies.
- **No long-lived shared state** — the container is reclaimed after the session ends.

**Steps that this skill DEFERS to non-cloud /lazy (writes `DEFERRED_NON_CLOUD.md` and CONTINUES):**

| State machine step | Why deferred in cloud | Cloud behavior |
|---|---|---|
| Step 8b — MCP test execution (testable features only) | Requires running Tauri app + MCP HTTP server | Write `DEFERRED_NON_CLOUD.md`, fall through to Step 9 (retro) — do NOT stop |
| Step 8a — assessing testability | Filesystem read only → **NOT deferred**; evaluation still runs, but `SKIP_MCP_TEST.md` is only written for unambiguous non-testable cases | Same as /lazy when unambiguous; defer otherwise |
| Step 10 — Mark feature complete | Requires `VALIDATED.md` which cloud cannot produce | Stop with notice that workstation /lazy is needed to finalize |

**Steps that this skill STILL RUNS in cloud (same as /lazy):**

- Step 3 — Blocker presentation
- Step 4 — `/spec` for missing SPEC.md
- Step 4.5 — Stub spec detection
- Step 4.6 — Upstream reality check via `/realign-spec` (pure doc analysis; follow-on actions are SPEC/PHASES edits, `/add-phase`, or `BLOCKED.md` — all cloud-safe)
- Step 5 — `/spec` for research validation
- Step 6 — `/spec-phases` for missing PHASES.md
- Step 7 — `/write-plan` and `/execute-plan` for phase implementation (implementation work that doesn't require Tauri runtime is fine; if execute-plan hits a cloud-incompatible deliverable it must surface it via BLOCKED.md as usual)
- Step 9 — `/retro` and retro plan execution (analysis + edits only). Cloud runs this even though MCP validation has been deferred — retro is a static spec-alignment check and doesn't depend on runtime validation results.

---

## Sentinel File Format

All sentinel files this skill reads or writes follow the canonical YAML-frontmatter schema:

!`cat ~/.claude/skills/_components/sentinel-frontmatter.md`

When this skill writes a sentinel below, emit the YAML frontmatter first (with the required keys for that `kind`), then a blank line, then the existing human-readable markdown body shown in the template. When this skill reads a sentinel, parse the frontmatter per the protocol above; the markdown body is for humans only.

---

## Step 0: Load Tools and Parse Arguments

1. Load PushNotification: `ToolSearch({ query: "select:PushNotification" })`
2. Parse `$ARGUMENTS`:
   - If `"status"` → run the same logic as `/lazy-status` (read-only report) and STOP. Additionally, if any feature has a `DEFERRED_NON_CLOUD.md`, list those features and what step is deferred.
   - If `"skip"` → mark current feature as skipped (see Step 11) and STOP
   - If empty or anything else → proceed to Step 1

---

## Step 1: Load Queue

Read `docs/features/queue.json` from the project root. Extract the `queue` array.

If the file doesn't exist:
```
PushNotification({ message: "queue.json not found — /lazy-cloud cannot operate" })
```
STOP.

---

## Step 2: Find Current Feature (Cloud-Aware Skip)

Read `docs/features/ROADMAP.md`.

For each item in the queue array (in order), compute `spec_path` (= `docs/features/{spec_dir}` from queue.json) and apply both skip checks:

1. **Workstation-complete:** the feature's row in ROADMAP.md contains `~~` (strikethrough) AND `COMPLETE` → skip
2. **Cloud-saturated:** ALL THREE conditions hold → skip
   - `{spec_path}/RETRO_DONE.md` exists
   - `{spec_path}/DEFERRED_NON_CLOUD.md` exists
   - `{spec_path}/VALIDATED.md` does NOT exist
   - (Cloud has done every step it can for this feature; finalization requires workstation MCP test.)

The first feature in queue order that fails BOTH skip checks is the **current feature**.

**If every remaining feature is workstation-complete** (no features ever became cloud-saturated):
```
PushNotification({ message: "ALL FEATURES COMPLETE — AlgoBooth roadmap finished." })
```
Report this and STOP.

**If every remaining feature is either complete or cloud-saturated** (cloud has nothing left to advance, but workstation /lazy still has MCP testing to finish):
1. Build a list of cloud-saturated feature names and their `DEFERRED_NON_CLOUD.md` paths
2. Notify:
   ```
   PushNotification({ message: "Cloud queue exhausted — {N} feature(s) awaiting workstation /lazy for MCP test." })
   ```
3. Report the list in the status bookend (Next `/lazy` (workstation) will: "Run MCP tests for each deferred feature, in queue order")
4. STOP

Save for later:
- `feature_name` = current feature's `name` from queue.json
- `feature_id` = current feature's `id`
- `spec_path` = `docs/features/{spec_dir}` (prepend project root)
- `tier` = current feature's `tier`

Announce: `"Current feature: {feature_name} (Tier {tier})"` — if any features were skipped as cloud-saturated, also note the count: `"({K} feature(s) skipped — cloud-saturated, awaiting workstation MCP test)"`.

---

## Step 3: Check for Blockers

Check if `{spec_path}/BLOCKED.md` exists.

If it exists:
1. Read `BLOCKED.md` fully — parse the YAML frontmatter for `kind`, `feature_id`, `phase`, `blocked_at`, `retry_count`, and (if present) `blocker_kind` and `recovery_suggestion`. The markdown body provides additional human-readable context.
2. Analyze the blocker context (phase, details, what was tried, recovery suggestion)
3. **Do NOT retry or delete BLOCKED.md.** Present the blocker to Jacob with a recommendation:
   ```
   PushNotification({ message: "BLOCKED: {feature_name} — {first line of details}. Awaiting your input." })
   ```
4. Report:
   - The full blocker details
   - Your recommended next action (one of):
     - `/lazy-cloud skip` — skip this feature and move to the next
     - `/add-phase` — add a corrective or workaround phase
     - Manual fix needed — describe what Jacob should do
     - Research needed — suggest what to investigate
   - A copyable command for whatever you recommend
5. STOP (Jacob decides what to do next; he deletes BLOCKED.md manually or via the action he takes)

---

## Step 3.5: Note Pre-Existing Non-Cloud Deferral (Read-Only)

Check if `{spec_path}/DEFERRED_NON_CLOUD.md` exists. If it does, a prior cloud invocation already deferred a step that requires the workstation environment.

This check is **read-only and non-blocking** — do NOT stop and do NOT delete the sentinel. The natural state machine below already accounts for the deferred step:
- Step 8 will see the existing `DEFERRED_NON_CLOUD.md` and skip the re-write
- Step 9 will treat it as a valid alternative gate to enter the retrospective
- Step 10 will refuse to mark the feature complete (no `VALIDATED.md`) and explain that the workstation must run MCP testing

Just read the file to inform the status bookend ("Deferred:" line) and continue to Step 4.

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

## Step 4.5: Stub Spec Detection

SPEC.md exists, but it may be a stub auto-generated from a research summary (e.g. `docs/features/ADVANCED_FEATURE_RESEARCH.md`). A stub has the metadata header but no Executive Summary / User Experience / Technical Design / Validation Criteria sections — the spec body is still the original research blurb. Running Step 5 against a stub would generate a Phase 2 research prompt grounded in thin content instead of a refined Phase 1 baseline.

Detect a stub by checking `{spec_path}/SPEC.md` for EITHER marker:
- The metadata line `**Status:** Draft (research stub)`
- A literal trailer line near the end: `> Stub generated from advanced feature research. Run /spec to expand into a full specification.`

```bash
grep -E "^\*\*Status:\*\* Draft \(research stub\)|^> Stub generated from advanced feature research" {spec_path}/SPEC.md
```

**If a stub marker is found:** invoke /spec WITHOUT the "skip to Phase 2" argument so /spec runs from Phase 1 (brainstorm baseline spec). Pass the existing stub path as starting context — /spec is expected to overwrite the stub once the baseline is locked in:

```
Skill({ skill: "spec", args: "{feature_name} — existing stub at {spec_path}/SPEC.md is auto-generated from research summary; treat as starting context for Phase 1 brainstorming and overwrite when baseline is locked in" })
```

STOP after skill returns.

**If no stub marker is found:** Proceed to Step 4.6.

---

## Step 4.6: Upstream Reality Check

SPEC.md exists and is not a stub. Before progressing this feature any further, reality-check it against the actual state of its completed hard-dependency upstreams. Upstream PHASES.md often diverges from what the downstream SPEC assumed at authoring time — Implementation Notes, renames, descoped capabilities, and contract shifts only surface here.

This step is cloud-safe: `/realign-spec` is pure read-only analysis and writes only to `plans/realign-<date>.md`. The follow-on actions (`inline-edit`, `add-phase`, `respec`) are all documentation work, none requires the Tauri runtime or MCP server.

!`cat ~/.claude/skills/_components/dep-block-schema.md`

### 4.6a. Determine whether to run the check

1. Parse `{spec_path}/SPEC.md`'s `**Depends on:**` block per the schema above. Filter to `kind == hard`.
2. For each hard dep, resolve the upstream directory and apply the completion check (ROADMAP.md strikethrough+COMPLETE or upstream SPEC `Status: Complete`).
3. Let `hard_complete_upstreams` = the list of hard deps whose upstream is Complete.

**If `hard_complete_upstreams` is empty:** No upstream reality to check against. Proceed to Step 5.

**Skip-if-fresh gate (idempotency):** glob `{spec_path}/plans/realign-*.md`. If at least one realign plan exists AND its mtime is newer than every Complete hard upstream's `PHASES.md` mtime, the most recent realign already covered the current upstream state. Skip to Step 5.

Otherwise, proceed to 4.6b.

### 4.6b. Invoke /realign-spec

```
Skill({ skill: "realign-spec", args: "{spec_path}/SPEC.md" })
```

After /realign-spec returns, locate the plan file it wrote (newest `{spec_path}/plans/realign-*.md`).

### 4.6c. Act on the recommendation

Read the realign plan file. Find the `**Recommended:**` line under `## Recommended next step`.

**`inline-edit`:** The plan's Minor table lists local SPEC/PHASES patches.

1. Apply each row's `Suggested patch` to the named location in `{spec_path}/SPEC.md` or `{spec_path}/PHASES.md` using `Edit`. Minor patches only — never touch upstream files.
2. Commit via the standard commit policy (see Step 10 for pattern). Commit message: `docs({feature_id}): realign with upstream — minor corrections per plans/realign-<date>.md`.
3. STOP. The next /lazy-cloud invocation re-enters from Step 1; the freshness gate in 4.6a will see the new realign plan is newer than upstream PHASES and skip directly past 4.6.

**`add-phase`:** A corrective phase is needed.

1. Read the Moderate table from the realign plan to extract the proposed phase title and scope.
2. Invoke:
   ```
   Skill({ skill: "add-phase", args: "{spec_path}/PHASES.md Corrective — Realign with upstream <upstream-id>: <one-line scope from realign plan>" })
   ```
3. STOP after /add-phase returns. (Any Minor patches in the realign plan are deferred to the next /lazy-cloud cycle, which will see them as remaining drift and apply them inline.)

**`respec`:** The downstream design no longer holds. Do NOT silently rewrite it.

1. Write `{spec_path}/BLOCKED.md` (YAML frontmatter first per the Sentinel File Format section, then body):
   ```markdown
   ---
   kind: blocked
   feature_id: {feature_id}
   phase: Upstream Realignment
   blocked_at: {ISO timestamp}
   retry_count: 0
   blocker_kind: upstream-realign
   recovery_suggestion: Review plans/realign-{date}.md and run /spec or revise SPEC sections.
   ---

   # BLOCKED

   **Feature:** {feature_name} ({feature_id})
   **Phase:** Upstream Realignment
   **Blocked at:** {ISO timestamp}
   **Retry count:** 0

   ## Details
   Severe drift detected against completed upstream(s): {comma-separated upstream-ids with severe findings}.
   Foundational design assumptions no longer hold; phase rework is not sufficient.

   ## What was tried
   /realign-spec produced plans/realign-{date}.md classifying drift as severe.

   ## Recovery Suggestion
   Review plans/realign-{date}.md, then either:
   - Run /spec on this feature to redesign against the actual upstream contract, or
   - Manually revise SPEC.md sections called out in the Severe table and re-run /lazy-cloud (or /lazy from a workstation).
   ```
2. PushNotification: `"BLOCKED: {feature_name} — severe upstream drift; see plans/realign-{date}.md"`
3. STOP. (Next /lazy-cloud invocation hits Step 3's blocker handling.)

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

> Cloud note: if `/execute-plan` encounters a deliverable that genuinely cannot be implemented in the cloud Linux environment (e.g. a Windows-only build step, a Tauri-runtime-only behavior), it should write `BLOCKED.md` with `## Cloud Limitation` in the recovery section so the next workstation `/lazy` knows the unblock requires re-running the deliverable, not a fix.

### 7b. All Phases Complete (unchecked = 0, checked > 0)

Proceed to Step 8 (MCP test gate — cloud-aware).

---

## Step 8: MCP Test Gate (Cloud-Aware)

All implementation phases are complete. Normally the next step is MCP validation, but cloud cannot run the Tauri MCP server. Apply the cloud-aware decision below.

Check if `{spec_path}/VALIDATED.md` exists:
- If exists → proceed to Step 9 (retrospective)

Check if `{spec_path}/SKIP_MCP_TEST.md` exists:
- If exists → write `VALIDATED.md` (note "MCP tests skipped per prior SKIP_MCP_TEST.md") and STOP. Next invocation picks up at Step 9.

### 8a. Evaluate MCP Testability (read-only — safe in cloud)

This evaluation is filesystem-only and safe in cloud. **However**, the *output* of this evaluation determines whether we defer or write a permanent skip marker, and the permanent skip marker requires high confidence.

**Read the canonical references (MANDATORY):**
1. `{spec_path}/SPEC.md` — testable surfaces, validation criteria
2. `docs/features/mcp-testing/SPEC.md` — canonical testability matrix and available MCP tools
3. Project `CLAUDE.md` Gotchas section — known pitfalls (e.g., audio IS testable via `load_test_tone`)

Classify the feature:
- **Clearly testable** — has IPC/sidecar API, MCP tools, UI state changes, or audio output through Strudel patterns; spec defines testable behaviors → **DEFER** (see 8b)
- **Clearly NOT testable** — pure Rust DSP with no MCP surface, no observable IPC state, and the spec explicitly confirms no external surface → write `SKIP_MCP_TEST.md` as usual (this is a permanent decision, not a cloud-specific deferral). Same exact content as documented in `/lazy` Step 8a. Then STOP.
- **Ambiguous** — treat as **DEFER**. Do not gamble on writing a permanent skip marker without a running app to confirm.

### 8b. Defer MCP Test Execution and Fall Through to Retro

Cloud cannot run MCP tests. Do **not** create the `mcp-tests/` symlinks, do **not** invoke `/mcp-test`, do **not** write `MCP_TEST_RESULTS.md` or `VALIDATED.md`.

If `{spec_path}/DEFERRED_NON_CLOUD.md` does NOT already exist, write it now:
```markdown
---
kind: deferred-non-cloud
feature_id: {feature_id}
deferred_step: 8
reason: Cloud Linux environment cannot run tauri:dev or reach the MCP HTTP server.
deferred_by: lazy-cloud
date: {today}
cloud_session_id: {claude-session-id-or-n/a}
testability_assessment: {clearly-testable | ambiguous}
---

# Deferred to Non-Cloud /lazy

**Feature:** {feature_name} ({feature_id})
**Deferred step:** Step 8 — MCP Test Gate
**Reason:** Cloud Linux environment cannot run `tauri:dev` or reach the MCP HTTP server.
**Deferred by:** /lazy-cloud (cloud session)
**Date:** {today}
**Cloud session id (if available):** {claude-session-id-or-"n/a"}

## State at deferral
- All implementation phases complete (PHASES.md: 0 unchecked deliverables)
- No `mcp-tests/` symlinks created yet (deferred to workstation)
- No `MCP_TEST_RESULTS.md`, no `SKIP_MCP_TEST.md`, no `VALIDATED.md`

## Cloud testability assessment
{One-paragraph summary of why this was classified testable / ambiguous, citing SPEC.md sections.}

## How to resume
Run `/lazy` (NOT `/lazy-cloud`) from a workstation with the Tauri dev server available. The natural state machine in `/lazy` will:
1. See no VALIDATED.md and no SKIP_MCP_TEST.md
2. Re-evaluate MCP testability (Step 8a)
3. Create `mcp-tests/` symlinks and invoke `/mcp-test` (Step 8b)
4. On 100% pass → write VALIDATED.md and progress to retro

The presence of this DEFERRED_NON_CLOUD.md does NOT change /lazy's behavior — it exists purely as an audit trail. /lazy and /lazy-cloud should leave it in place until Step 10 (feature completion) cleans it up.

## Cloud follow-on
After writing this sentinel, /lazy-cloud fell through to Step 9 (retro). The retro may have already run by the time the workstation /lazy picks this up. If `RETRO_DONE.md` exists alongside this sentinel, retro is complete and the workstation /lazy only needs to handle Step 8.
```

If the file already exists from a prior cloud invocation, leave it untouched.

Then notify and **continue to Step 9** in the same invocation:
```
PushNotification({ message: "{feature_name}: MCP testing deferred to workstation /lazy. Proceeding to retro." })
```

**Do NOT stop here.** Fall through to Step 9 and run the retrospective as if `VALIDATED.md` existed. This is the one place where /lazy-cloud diverges from the strict /lazy gate ordering: retro is a static spec-alignment analysis that doesn't depend on MCP runtime evidence, so it's safe to run before the deferred validation.

---

## Step 9: Retrospective (Spec Alignment Validation)

Same as `/lazy` Step 9 — analysis + edits only, safe in cloud.

**Entry gate (cloud-aware):** Either `VALIDATED.md` OR `DEFERRED_NON_CLOUD.md` must exist. The former means MCP testing passed (normal /lazy path); the latter means MCP testing was deferred to the workstation and we're running retro early. Both are valid entry conditions for /lazy-cloud — pick whichever describes reality.

**CRITICAL:** The retro's sole responsibility is analysis — it surfaces divergences and writes a plan file. /lazy-cloud is responsible for acting on those findings:
- **Minor divergences** (naming changes, implementation details that don't affect behavior): handled by the retro plan during execution
- **Significant divergences** (missing spec requirements, behavior that contradicts spec, descoped items not documented): /lazy-cloud appends corrective phases to PHASES.md directly, forcing a new implementation cycle before the feature can be marked complete

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
  3. Force re-validation after corrective phases are implemented:
     - If `VALIDATED.md` exists (we somehow have a workstation-produced validation) → delete it
     - If only `DEFERRED_NON_CLOUD.md` exists (cloud-deferred validation, expected case) → leave it in place; the corrective phases below already force re-implementation, and the deferral marker continues to signal that MCP testing is pending workstation execution
  4. STOP (next invocations: Step 7 → implement → Step 8 → re-defer/re-validate → Step 9 → second retro)
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
    ---
    kind: retro-done
    feature_id: {feature_id}
    date: {today}
    rounds: 1
    retro_plans: [{retro-plan-filename}]
    mcp_validation_status: {complete | deferred-to-workstation}
    ---

    # Retro Complete

    **Feature:** {feature_name} ({feature_id})
    **Date:** {today}
    **Rounds:** 1 (clean — no significant divergences)
    **Retro plan:** {retro-plan-filename}
    **MCP validation status:** {"complete (VALIDATED.md)" if VALIDATED.md exists else "deferred to workstation /lazy (see DEFERRED_NON_CLOUD.md)"}
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
---
kind: retro-done
feature_id: {feature_id}
date: {today}
rounds: {retro_count}
retro_plans: [{retro-plan-filename-1}, {retro-plan-filename-2}, ...]
mcp_validation_status: {complete | deferred-to-workstation}
---

# Retro Complete

**Feature:** {feature_name} ({feature_id})
**Date:** {today}
**Rounds:** {retro_count}
**Retro plans:** {comma-separated retro plan filenames}
**MCP validation status:** {"complete (VALIDATED.md)" if VALIDATED.md exists else "deferred to workstation /lazy (see DEFERRED_NON_CLOUD.md)"}
```
STOP

---

## Step 10: Mark Feature Complete (Cloud-Halt Aware)

### 10a. Defensive cloud halt — RETRO_DONE.md exists but no VALIDATED.md

This branch should normally be unreachable: Step 2's cloud-saturated skip already advances past features with `RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md`. It exists as a defensive guard for unusual states (e.g., `RETRO_DONE.md` written but `DEFERRED_NON_CLOUD.md` deleted prematurely).

If `RETRO_DONE.md` exists AND `VALIDATED.md` does NOT exist, cloud has done everything it can for this feature. Do **NOT** mark the feature complete on ROADMAP.md. Do **NOT** delete `RETRO_DONE.md` or `DEFERRED_NON_CLOUD.md`. Do **NOT** commit a completion change.

Instead:
```
PushNotification({ message: "{feature_name}: cloud work complete (phases + retro). Awaiting workstation /lazy for deferred MCP test." })
```

Report the halt in the status bookend (Next `/lazy-cloud` will: "Skip this feature at Step 2 on next invocation and advance to the next") and STOP. The next /lazy-cloud invocation's Step 2 will skip this feature and process the next eligible one.

### 10b. Normal completion — both VALIDATED.md AND RETRO_DONE.md exist

This branch runs only when cloud somehow has both sentinels (e.g., a workstation /lazy wrote VALIDATED.md and a subsequent /lazy-cloud invocation reaches Step 10). Proceed exactly as `/lazy` does:

1. **Update ROADMAP.md:**
   - Find the feature's row by matching `feature_name` in the ROADMAP table
   - Wrap the feature name and description in strikethrough (`~~`)
   - Append `**COMPLETE**` to the description
   - Follow the pattern of existing completed features (Tier 0 items)

2. **Clean up sentinel files:**
   ```bash
   rm -f {spec_path}/VALIDATED.md
   rm -f {spec_path}/RETRO_DONE.md
   rm -f {spec_path}/DEFERRED_NON_CLOUD.md
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
   PushNotification({ message: "{feature_name} COMPLETE. Next: {next_feature_name}. Run /lazy-cloud (or /lazy on workstation) to continue." })
   ```

6. Report completion summary and STOP.

---

## Step 11: Skip Current Feature

Only triggered when `$ARGUMENTS` contains `"skip"`.

1. Find the current feature (Steps 1-2)
2. Ask why (via AskUserQuestion): "Why should {feature_name} be skipped?"
3. Update ROADMAP.md: append `(SKIPPED — {reason})` to the feature row
4. The next `/lazy-cloud` invocation will automatically pick up the following feature
5. STOP

---

## Work Log (MANDATORY — DO NOT SKIP)

Every /lazy-cloud invocation that performs meaningful work MUST call `interview_work_log_append` before producing the "After" status bookend. A pure deferral (writing `DEFERRED_NON_CLOUD.md` and stopping) DOES count as meaningful work and MUST be logged — it's the audit record of why a feature didn't progress in this session.

Load the tool: `ToolSearch({ query: "select:mcp__plugin_interview-prep-plugin_interview-prep__interview_work_log_append" })`

Call with:
- `skill`: `"lazy-cloud"`
- `project`: `"algobooth"`
- `title`: `"/lazy-cloud → {action taken or 'defer MCP test'}"`
- `summary`: 2-4 sentences. What state was detected, what skill (if any) was dispatched, whether any step was deferred to non-cloud /lazy, any issues.
- `files_modified`: files modified during this invocation (from sub-skill output, plus any sentinel files written)
- `technologies`: relevant tech stack
- `patterns`: patterns applied (include `cloud-deferral` when DEFERRED_NON_CLOUD.md was written)
- `technical_context`: architectural context of what was implemented

**Skip work-log only when:** /lazy-cloud did nothing meaningful (e.g., reported a pre-existing blocker without invoking a skill, or all features were already complete).

**The sub-skill invoked by /lazy-cloud is ALSO expected to log its own work** — both logs are required. /lazy-cloud logs the dispatch-level view; the sub-skill logs the implementation-level detail.

---

## Sentinel Files Reference

Identical to `/lazy`, plus the cloud-deferral sentinel:

| File | Created by | Purpose | Lifecycle |
|------|-----------|---------|-----------|
| `plans/*.md` | /write-plan, /retro, etc. | Colocated plan files | Persists (audit trail) |
| `BLOCKED.md` | /execute-plan or /lazy[-cloud] | Blocker details | Persists until Jacob resolves |
| `MCP_TEST_RESULTS.md` | /lazy (after mcp-test) — NEVER /lazy-cloud | Test results with pass/fail details | Persists permanently (audit trail) |
| `VALIDATED.md` | /lazy (after 100% pass) — NEVER /lazy-cloud | Validation gate | Deleted on feature completion |
| `SKIP_MCP_TEST.md` | /lazy[-cloud] (assessment) — cloud only writes for unambiguous non-testable features | Documents why MCP testing was skipped | Persists permanently |
| `RETRO_DONE.md` | /lazy[-cloud] (after retro execution) | Retro completion gate | Deleted on feature completion |
| `mcp-tests/*.md` | /lazy (symlinks) — NEVER /lazy-cloud | Links to test scenarios | Persists permanently |
| **`DEFERRED_NON_CLOUD.md`** | **/lazy-cloud (cloud-blocked step)** | **Documents step deferred to workstation /lazy** | **Deleted on feature completion (Step 10) — left in place by /lazy as audit trail until then** |

---

## State Machine Summary

Differences from `/lazy`:
- Step 2 skips cloud-saturated features (`RETRO_DONE.md` + `DEFERRED_NON_CLOUD.md` + no `VALIDATED.md`) and advances to the next eligible feature in the queue
- Step 8 writes `DEFERRED_NON_CLOUD.md` and falls through to Step 9 instead of stopping
- Step 9 accepts `DEFERRED_NON_CLOUD.md` as an alternative entry gate to `VALIDATED.md`
- Step 10 splits into a defensive cloud-halt (10a) and normal completion (10b)

```
queue.json → for each feature in order:
                skip if workstation-complete (~~COMPLETE on ROADMAP)
                skip if cloud-saturated (RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md)
             → first non-skipped feature is current → check state → invoke ONE skill → STOP
             → if every feature skipped: notify (all complete OR cloud queue exhausted) → STOP

BLOCKED.md exists?                    → present blocker + recommend action → STOP
DEFERRED_NON_CLOUD.md exists?         → note in status (read-only), CONTINUE through state machine
SPEC.md missing?                      → /spec (or notify if no research)
SPEC.md exists + stub marker present? → /spec (Phase 1 from scratch, stub becomes starting context)
Hard deps on Complete upstreams, no fresh realign plan? → /realign-spec → act on recommendation (inline-edit | /add-phase | BLOCKED) — cloud-safe
SPEC.md exists + no RESEARCH_SUMMARY? → /spec (generate research prompt or integrate results)
PHASES.md missing?                    → /spec-phases
Unchecked deliverables + no plan?     → /write-plan (writes to plans/ subdir)
Unchecked deliverables + plan exists? → /execute-plan
All checked + no VALIDATED.md + no DEFERRED_NON_CLOUD.md + not testable? → SKIP_MCP_TEST.md (only if unambiguous)
All checked + no VALIDATED.md + (testable OR ambiguous)?                 → write DEFERRED_NON_CLOUD.md (if missing), fall through to retro
(VALIDATED.md OR DEFERRED_NON_CLOUD.md) + 0 retro plans?                  → /retro --auto
(VALIDATED.md OR DEFERRED_NON_CLOUD.md) + 1 retro plan (clean)?           → /execute-plan (retro plan) → RETRO_DONE.md (annotates MCP status)
(VALIDATED.md OR DEFERRED_NON_CLOUD.md) + 1 retro plan (had divergences)? → /retro --auto (round 2); skip VALIDATED.md delete if absent
(VALIDATED.md OR DEFERRED_NON_CLOUD.md) + 2+ retro plans?                 → /execute-plan (latest retro plan) → RETRO_DONE.md
RETRO_DONE.md + no VALIDATED.md?      → DEFENSIVE HALT (Step 2 normally skips first) → STOP
RETRO_DONE.md + VALIDATED.md?         → mark complete on ROADMAP + remove DEFERRED_NON_CLOUD.md + notify
```
