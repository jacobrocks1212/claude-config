---
name: lazy-bug-batch
description: Autonomous orchestrator for the bug pipeline. Loops on bug-state.py and spawns Opus subagents per cycle (one /lazy-bug-equivalent cycle each). Drives docs/bugs/ (NOT docs/features/). No research/stub/needs-research handling — N/A to bugs. Terminal action is __mark_fixed__ (archive-on-fix): FIXED.md receipt (kind: fixed, gated by the completion-integrity gate) → Status Fixed + git mv → _archive/ → repoint inbound refs → commit. Receipt is FIXED.md; Won't-fix is receipt-EXEMPT. Does NOT dead-end on recoverable obstacles: a halt for ANY reason other than max-cycles (and the genuine all-bugs-fixed success terminal) presents the operator an AskUserQuestion resolution path and continues the loop. needs-input → Step 1g (decision-resume); blocked → Step 1h (blocked-resolution: add a phase / defer to queue tail / halt-for-manual / custom); completion-unverified and stale_upstream → Step 1i (operator-directed halt-resolution per ~/.claude/skills/_components/halt-resolution.md; bug-state.py does NOT emit needs-spec-input). Each re-prints the load-bearing context, AskUserQuestions the resolution, dispatches an apply-resolution subagent to enact it (neutralizing any blocking sentinel by rename — bug-state.py keys halts on the filename), and resumes. Only max-cycles, all-bugs-fixed, all-remaining-deferred, queue-missing, and environment-exhaustion (device/cloud-queue-exhausted) remain clean stops. After every /spec-bug or spec-phases cycle, Step 1d.5 dispatches a dedicated Opus input-audit subagent that independently re-classifies the cycle's decisions and writes NEEDS_INPUT.md if any product-behavior calls were silently baked into SPEC/PHASES. (bug-state.py emits spec-bug / spec-phases / write-plan / execute-plan / retro-feature / mcp-test — never plan-feature/plan-bug.)
argument-hint: <max-cycles, e.g. 10> [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Bug Batch — Autonomous Bug Pipeline Orchestrator

Drives the per-bug autonomous tail (`/spec-bug` → `/spec-phases` → `/write-plan` → `/execute-plan`
→ `/retro-feature` → `/mcp-test` → `__mark_fixed__` archive-on-fix) by looping on
`~/.claude/scripts/bug-state.py`. Each cycle spawns an Opus subagent that invokes the named
sub-skill; the orchestrator (this skill, running in the main session) never touches source code,
never invokes a skill directly, and never parses sentinel files manually.

**Bug pipeline differences from the feature pipeline:**
- Drives `bug-state.py` (NOT `lazy-state.py`); operates on `docs/bugs/`.
- No research/Gemini steps, no stub-spec step, no realign step — N/A to bugs.
- Terminal is `__mark_fixed__` (archive-on-fix) instead of `__mark_complete__`.
- Receipt is `FIXED.md` (kind: fixed). Won't-fix is receipt-exempt.
- Status vocab: `Open | Investigating | In-progress | Fixed | Won't-fix`.

**Step ordering:** `/retro-feature` runs BEFORE `/mcp-test` (Step 8 retro → Step 9 MCP).
`/retro-feature` is a docs/analysis pass and runs identically in cloud and workstation; `/mcp-test`
only runs on workstation (cloud defers). Behavior inside the loop is unchanged — the orchestrator
dispatches whatever `bug-state.py` returns.

---

## HARD CONSTRAINTS (non-negotiable)

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`,
   `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `FIXED.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`,
   `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/bugs/`, AND on per-bug `SPEC.md`
   (Status/Fixed/Fix-commit header lines only) and `PHASES.md` status lines when performing the
   `__mark_fixed__` action (which is a documentation-level update by definition, not a source-code
   edit). `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a
   `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns; the
   orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md
   and neutralize the sentinel **by rename**. `BLOCKED.md` (Step 1h) and any obstacle sentinel
   handled by Step 1i may likewise be appended with a `## Resolution` section before the orchestrator
   dispatches an Opus subagent to enact the chosen path and neutralize the sentinel by rename
   (`bug-state.py` keys halts on the sentinel filename). All other `Write`/`Edit` operations — source
   code, test files, plan files, PHASES.md — require subagent dispatch.

2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill
   invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean
   across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per
   Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.

3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference
   is exclusively via `bug-state.py`. Sentinel files MAY be read by the orchestrator to confirm a
   write or to drive a pseudo-skill action.

4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills
   inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill
   cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator
   actions that count as one cycle each.

5. **Interactive prompts are scoped to the resolution modes — decision-resume (Step 1g),
   blocked-resolution (Step 1h), and operator-directed halt-resolution (Step 1i) — ONLY for the
   orchestrator itself.** Outside those modes the orchestrator MUST NOT call `AskUserQuestion`.
   Inside each, the orchestrator MUST re-print the load-bearing context, `AskUserQuestion` the
   resolution, dispatch the apply-resolution subagent to enact it, and then **continue the loop** —
   so a halt for any reason other than `max-cycles` (and the genuine all-done success terminal) asks
   the operator how to proceed rather than dead-ending. This constraint scopes the orchestrator, not
   subagents it dispatches.

6. **The orchestrator MUST re-print the load-bearing context to chat BEFORE calling
   `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print
   is the load-bearing context. In Step 1g this is the rich `## Decision Context` (never
   `AskUserQuestion` against a malformed `NEEDS_INPUT.md` — surface the malformation and halt). In
   Step 1h it is the `BLOCKED.md` body verbatim (no rich-body schema; a thin body is not a
   malformation halt). In Step 1i it is the obstacle context (notify_message + diagnostics + any
   relevant sentinel/dir state) per the halt-resolution component.

7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`,
   `wait`, polling loops, or any other mechanism to block. A terminal either resolves via an
   `AskUserQuestion` resolution mode (Step 1g/1h/1i — a single-turn operator interaction, then the
   loop continues) or, when the operator chooses Halt / for a genuine stop terminal, halts cleanly —
   never an active wait. Responding to a chat message is NOT polling — it is a single-turn event.

8. **The `cycle` counter is session-global and monotonic across bug transitions.** It is initialized
   to 0 in Step 0 *once per `/lazy-bug-batch` invocation* and incremented at the end of every
   cycle. It MUST NOT be reset when `bug-state.py` returns a different `feature_id` from one cycle
   to the next. A bug transition is **not** a fresh batch; the orchestrator runs ONE cycle log
   across every bug it touches.

9. **Dispatch ONLY against the bug `bug-state.py` returned THIS cycle; never fabricate a bug.** The
   orchestrator dispatches a cycle subagent against exactly the `feature_id` + `spec_path` from the
   current cycle's `bug-state.py` output, verbatim. It MUST NOT invent, infer, or hand-edit a
   `feature_id`/slug that the state script did not emit.

**Cycle-subagent execution model (recursive dispatch is NOT available — inline edits required).**
The cycle subagent dispatched at Step 1d does **not** have the `Agent` tool: recursive
sub-subagent dispatch is not supported from inside a dispatched subagent. This forces a
load-bearing override: skills that nominally fan out to sub-subagents MUST be performed INLINE
inside the cycle subagent using `Edit`/`Write`/`Read` directly. **This override applies only at
the cycle-subagent level** — the orchestrator still dispatches exactly one `Agent` per cycle.

`$ARGUMENTS` is tokenized on whitespace. Recognized tokens:

- **Positive integer** → `max_cycles`. If absent, default to `10`. If a non-numeric / `< 1`
  integer is supplied, refuse with:

  > `/lazy-bug-batch` requires a positive integer max-cycles. Usage: `/lazy-bug-batch <N> [--adhoc "<task>"]`. Default: 10.

- **`--adhoc`** (optional flag) → sets `adhoc_task` to the remainder of `$ARGUMENTS` after the
  `--adhoc` token. If `--adhoc` is the last token with no trailing text, `adhoc_task` is empty
  and the task is inferred from the conversation. When set, the orchestrator runs **Step 0.45
  (Ad-hoc Enqueue)** before the main loop. Place `<N>` BEFORE `--adhoc`.

Unknown tokens are an error:

> `/lazy-bug-batch`: unrecognized argument `{token}`. Usage: `/lazy-bug-batch <N> [--adhoc "<task>"]`.

Initialize counters and per-session state:
- `cycle = 0` — monotonic across bug transitions (HARD CONSTRAINT 8).
- `max_cycles = <parsed>`
- `cycle_log = []` — each entry: `{cycle, bug, action, subagent_summary}`
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)`.
- `adhoc_task = <parsed>` — the ad-hoc task text from `--adhoc` (unset if flag absent).

Print the start bookend:

```
## /lazy-bug-batch — Starting
**Max cycles:** {max_cycles}
**Repo root:** {cwd}
```

---

## Step 0.4: Resume-time remote sync (HARD REQUIREMENT)

**Runs once, immediately after Step 0 (arg parsing) and BEFORE Step 0.45 / the Step 1a first
state probe.** Single-turn git reconciliation — prevents operating against a stale local tree.

**Algorithm:**

1. Determine the work branch:

   ```bash
   branch=$(git rev-parse --abbrev-ref HEAD)
   ```

2. Fetch the remote tip (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error):

   ```bash
   git fetch origin "$branch"
   ```

   If the branch does not exist on `origin` yet, skip to Step 0.45.

3. Fast-forward local to the remote tip:

   ```bash
   git merge --ff-only "origin/$branch"
   ```

4. **If the fast-forward FAILS because local has DIVERGED from `origin`** — surface the divergence
   and halt for human resolution. Do NOT clobber, do NOT force.

5. On a clean fast-forward (or already up to date / unpushed branch), print one-line confirmation
   and continue.

---

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

**Runs once, after Step 0.4 (remote sync) and BEFORE Step 0.5 / the first state probe.** Skipped
entirely when the `--adhoc` flag was absent.

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

After the enqueue returns, continue to Step 1 (the bug queue carries no pre-loop ingest step —
N/A to bugs).

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run bug-state.py

```bash
python3 ~/.claude/scripts/bug-state.py
```

If the script exits non-zero, surface the error, push a PushNotification, print the final batch
report (see Step 2), and STOP.

Parse the JSON output. Extract: `feature_id`, `feature_name`, `spec_path`, `current_step`,
`sub_skill`, `sub_skill_args`, `terminal_reason`, `notify_message`, `diagnostics`.

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`**: see Step 1h (blocked-resolution mode). **Not a terminal halt anymore.** Step 1h
  re-prints the `BLOCKED.md` body, `AskUserQuestion`s the resolution path (add a phase / defer to
  queue tail / halt-for-manual / custom), enacts it (neutralizing `BLOCKED.md` via rename), and
  resumes — UNLESS the operator chooses "Halt for manual fix".
- **`needs-input`**: see Step 1g (decision-resume mode). **Not a terminal state for the
  orchestrator.** Step 1g resolves and resumes within the same invocation.
- **`completion-unverified`**: a bug's SPEC claims Fixed but no FIXED.md receipt exists — it was
  flipped OUTSIDE the validation gate. See Step 1i (operator-directed halt-resolution): the
  orchestrator re-prints the gap and `AskUserQuestion`s the path (reopen & re-validate / grandfather
  the receipt / defer & continue / halt). Do NOT auto-flip or auto-backfill — the operator chooses.
- **`stale_upstream`**: an upstream item this bug was materialized from changed since materialize. See Step 1i (operator-directed halt-resolution) — re-print the gap and `AskUserQuestion` the path (re-materialize/absorb / reject / defer / halt). (`bug-state.py` emits this; do NOT auto-resolve.)
- **`all-bugs-fixed`**: PushNotification `"ALL BUGS FIXED — queue cleared after {cycle}
  /lazy-bug-batch cycle(s)."`, print final batch report, STOP. (Genuine success — not routed to
  Step 1i.)
- **`all-remaining-deferred`**: every open bug is operator-parked via `DEFERRED.md`. PushNotification with `notify_message`, print final batch report, STOP. (A deliberate park, not an obstacle — re-include a bug by deleting its `DEFERRED.md`. Not routed to Step 1i, per the halt-resolution exclusion list.)
- **`queue-missing`**: `docs/bugs/queue.json` missing (the queue is optional — on-disk bugs are auto-discovered, so this is informational). PushNotification with `notify_message`, print final batch report, STOP. (No queue to continue — not routed to Step 1i.)
- **`cloud-queue-exhausted`**: Unreachable for `/lazy-bug-batch` (workstation variant); treat as
  `all-bugs-fixed` defensively.
- **`device-queue-exhausted`**: Reachable only on a no-real-device workstation. PushNotification
  with `notify_message`, print final batch report, STOP. Resume on a real-device host.

> **Note — no `needs-spec-input` in the bug pipeline.** `bug-state.py` never emits `needs-spec-input` (the bug pipeline dispatches `/spec-bug` as a `sub_skill`, not a terminal). Step 1i's matrix scopes that row to the feature pipeline; the bug-batch routes only `completion-unverified` and `stale_upstream` to Step 1i.

### 1c. Check the max-cycles cap

If `cycle >= max_cycles`:

```
PushNotification({ message: "lazy-bug-batch hit max-cycles ({max_cycles}). Restart from a fresh session to continue." })
```

Print final batch report, STOP.

### 1c.5. Inline pseudo-skill handling (NO subagent dispatch)

If `sub_skill` starts with `__` (double-underscore), it is a **pseudo-skill** — a small
sentinel-file write + commit. Perform the action inline (orchestrator session) instead of
dispatching a subagent.

- **`__write_validated_from_skip__`** — read `<spec_path>/SKIP_MCP_TEST.md` frontmatter, write
  `<spec_path>/VALIDATED.md` (kind: validated, mcp_scenarios: [], result: all-passing, body note
  about the prior skip), then commit per project policy.
- **`__write_validated_from_results__`** — read `<spec_path>/MCP_TEST_RESULTS.md` frontmatter,
  extract `scenarios`, write `<spec_path>/VALIDATED.md` with those scenarios, then commit.
- **`__mark_fixed__`** — **gated by TWO inline docs-only gates, in order, BEFORE the archive
  runs.** **Gate 1 — MCP-coverage audit** per the shared component below:

  !`cat ~/.claude/skills/_components/mcp-coverage-audit.md`

  Run the audit with `{spec_path}` and `{bug_id}`. If the audit returns `uncovered:N` — the audit
  just wrote `{spec_path}/NEEDS_INPUT.md`. Do NOT run the archive steps. Append to `cycle_log`
  (gate halted), increment `cycle`, return to Step 1a — the next state-script call returns
  `terminal_reason: needs-input`, Step 1g surfaces it, and the apply-resolution Sonnet subagent
  reconciles before the next `__mark_fixed__` attempt.

  **Gate 2 — completion-integrity gate** per the shared component below (runs ONLY after gate 1
  returns `clean`):

  !`cat ~/.claude/skills/_components/completion-integrity-gate.md`

  Adapted for bugs: use `kind: fixed`, `filename: FIXED.md`. If a precondition fails, write
  `{spec_path}/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`), commit it, and return
  `refused:<reason>` — same halt-cycle-and-surface-via-Step-1g pattern as gate 1.

  Only when BOTH gates pass: **WRITE `{spec_path}/FIXED.md`** (`kind: fixed`, `provenance: gated`,
  folding validation evidence from VALIDATED.md / MCP_TEST_RESULTS.md into the receipt body —
  this is the durable proof the bug passed the gate). Then perform the **archive-on-fix procedure**
  per the component below:

  !`cat ~/.claude/skills/_components/mark-fixed-archive.md`

  Execute the mark-fixed-archive procedure (SPEC.md header updates, sentinel deletions, `git mv`
  to `_archive/`, inbound-reference repoint, queue.json update, atomic commit). Writing `FIXED.md`
  (a sentinel) and the SPEC header lines is within HARD CONSTRAINT 1's allowance.

- **`__flip_plan_complete_cloud_saturated__`** — emitted only by `bug-state.py --cloud` when an
  `In-progress` plan's only unchecked WUs are documented in `{spec_path}/DEFERRED_NON_CLOUD.md`
  as workstation-only. Read the plan's YAML frontmatter, edit ONLY the `status:` line in place
  (`In-progress` → `Complete`). Stage and commit per project policy. Do NOT touch SPEC.md or any
  sentinel.

After each inline action:

1. Append to `cycle_log`: `{cycle+1, bug_name, sub_skill, "inline: <one-line summary>"}`.
2. **Push backstop (guardrail).** Push the inline commit — `git push origin $(git rev-parse
   --abbrev-ref HEAD)` (retry up to 4× with exponential backoff; WORK BRANCH only, never main,
   never force).
3. Emit the canonical per-cycle update block (Step 3).
4. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)`.
5. Increment `cycle`. Return to Step 1a.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`),
build a minimal subagent prompt.

**Loop-guard check (BEFORE composing the prompt):** Compute the current cycle's signature as the
tuple `(feature_id, sub_skill, sub_skill_args, current_step)`. If `prev_cycle_signature is not
None` AND they are equal, the state script has returned the same tuple two cycles in a row — a
sign that a terminal sentinel is missing. Append the **LOOP DETECTED** block to the subagent
prompt (see below).

Base prompt template:

```
You are advancing one cycle of the autonomous bug pipeline.

Bug: {bug_name} ({bug_id})
Working directory: {cwd}
State script said: {current_step}

Action for this cycle:
  Invoke the {sub_skill} skill with args: {sub_skill_args} --batch

Operating mode: batch
  - Do NOT ask interactive questions. Skills accept --batch and either auto-accept
    a recommended option or write NEEDS_INPUT.md and halt.
  - If the skill writes NEEDS_INPUT.md, do NOT attempt to resolve the decision —
    that's a halt for a human.

Sub-subagent dispatch policy (INLINE OVERRIDE — LOAD-BEARING):
  This subagent does NOT have the `Agent` tool — you CANNOT spawn further
  sub-subagents from inside this cycle. Any Agent() call you attempt will fail
  (tool unavailable) and waste the cycle.

  Therefore, regardless of what the dispatched skill's SKILL.md says about
  spawning sub-subagents, you MUST perform that work INLINE in this subagent
  session using Edit / Write / Read directly.

  Per-skill inline overrides:
    • /execute-plan — perform test additions and implementation edits INLINE.
      Follow the rest of /execute-plan as written (batch ordering, commits,
      plan-file checkbox flips, sentinel emissions). Zero sub-subagent dispatches
      in an /execute-plan cycle is the EXPECTED state.
      STILL preserve test-first discipline: write failing tests first, confirm
      they fail for the right reason, THEN implement.
    • /retro-feature — perform all internal work inline: read each input serially,
      synthesize, write the retro plan + RETRO_DONE.md directly.
    • /mcp-test — perform the test work INLINE (read the MCP usage guide, run the
      MCP HTTP tools yourself, analyze session logs).
    • /spec-bug — already orchestrator-only docs pass; no sub-subagents needed.
    • /spec-phases, /write-plan — already orchestrator-only; no change.

  If you find yourself about to write Agent({...}) inside this cycle, STOP and
  replace it with the equivalent Edit / Write / Read sequence.

No premature Fixed (PIPELINE-GATE HONESTY — HARD REQUIREMENT):
  - You MUST NOT set the `**Status:**` of SPEC.md to `Fixed` or `Won't-fix`.
    That flip is reserved EXCLUSIVELY for the orchestrator's `__mark_fixed__`
    pseudo-skill, which runs ONLY after the full downstream tail: /retro-feature
    (writes RETRO_DONE.md) → /mcp-test (writes VALIDATED.md or a justified
    SKIP_MCP_TEST.md) → the __mark_fixed__ gates. If a cycle subagent flips
    SPEC **Status:** Fixed itself, the bug has NO FIXED.md receipt, so
    bug-state.py hard-halts on `completion-unverified` instead of advancing.
    Do NOT write a FIXED.md yourself either — only the orchestrator's
    __mark_fixed__ integrity gate may, after the validation tail passes.
  - What you MAY flip: the PLAN-PART frontmatter `status:` (Ready → In-progress
    → Complete) and per-PHASE checkboxes/Status line for the phase you just
    implemented. When the last phase's work lands, set the top-level PHASES
    **Status:** to `In-progress` (NOT `Complete` and NOT `Fixed`).

Plan-part status + per-WU granularity (RESUME SAFETY):
  Flip the plan part frontmatter `status:` to `In-progress` and commit it BEFORE
  starting work-unit work; tick each `- [ ]` → `- [x]` checkbox + commit as that
  work-unit lands. An interrupted session resumes at the first unchecked box.

After the skill returns:
  1. If a commit policy file exists at .claude/skill-config/commit-policy.md,
     follow it. Otherwise commit per the standard pattern and push to the current
     branch.
  2. Report a one-paragraph summary: what state was advanced, files modified,
     commit hash (or "no commit"), and any issues. Under 8 lines.
```

**LOOP DETECTED block (append only when the loop-guard fires):**

```
⚠️  LOOP DETECTED: The state script returned this exact
(feature_id={feature_id}, sub_skill={sub_skill}, sub_skill_args={sub_skill_args}, current_step={current_step})
tuple on the PREVIOUS cycle as well. This usually means a terminal sentinel
(RETRO_DONE.md / VALIDATED.md / SKIP_MCP_TEST.md) is missing — the skill that
was supposed to write it on the prior cycle did not.

Before invoking {sub_skill} again, DIAGNOSE THE MISSING SENTINEL:
  1. Read the canonical schemas in ~/.claude/skills/_components/sentinel-frontmatter.md.
  2. Inspect {spec_path}/ for existing sentinels and plan files.
  3. Determine which sentinel SHOULD exist given the bug's current state.
  4. If you can write the missing sentinel directly (preconditions unambiguously
     met), DO SO instead of re-running {sub_skill}. Commit and report.
  5. If preconditions are NOT met, run {sub_skill} and explicitly emit the
     appropriate terminal sentinel as part of its completion.
  6. If no sentinel applies, write BLOCKED.md with blocker_kind: loop-detected.
```

Dispatch:

```
Agent({
  description: "lazy-bug-batch cycle {cycle+1}: {sub_skill} for {bug_name}",
  subagent_type: "general-purpose",
  model: <"sonnet" if LOOP DETECTED else "opus">,
  prompt: <the prompt above>
})
```

**Model selection:** Normal cycles → Opus. Loop-resolution cycles → Sonnet (mechanical diagnosis,
5× cost-efficiency).

### 1d.5. Post-cycle input audit (Opus — runs only on `/spec-bug` and `spec-phases` cycles)

**Skip when ANY of:**
- `sub_skill` is NOT in {`spec-bug` (the bug analog of the feature pipeline's `/spec`), `spec-phases` (PHASES authoring — where product-behavior decisions can also be baked)}. bug-state.py emits no `plan-feature`/`plan-bug`; `spec-bug` + `spec-phases` are the SPEC/PHASES-authoring cycles.
- The cycle was a pseudo-skill (Step 1c.5 already ran inline).
- The cycle subagent already wrote `NEEDS_INPUT.md` for this bug this cycle.
- The cycle subagent returned a hard failure with no SPEC/PHASES delta.

**Why:** The dispatched cycle subagent self-classifies its own decisions. An independent Opus
second-opinion catches product-behavior calls silently baked into SPEC.md / PHASES.md.

**Dispatch:**

```
Agent({
  description: "lazy-bug-batch cycle {cycle+1}: input-audit for {bug_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <audit prompt>
})
```

**Audit prompt:**

```
You are the lazy-bug-batch INPUT-AUDIT subagent — an independent Opus second-opinion
that runs after a /spec-bug cycle. Your sole job is to verify that no product-behavior
decision was silently baked into SPEC.md / PHASES.md without surfacing to the user via
NEEDS_INPUT.md.

Scope (HARD): you MUST NOT edit source code, tests, plan files, or any file except
{spec_path}/NEEDS_INPUT.md. You MUST NOT call the Skill tool or dispatch further
subagents. You MUST NOT modify SPEC.md / PHASES.md.

Inputs:
  - Bug: {bug_name} ({bug_id})
  - Spec path: {spec_path}
  - Sub-skill that just ran: {sub_skill}
  - Cycle commit (for diff): {cycle_commit_sha or "HEAD~1"}
  - Cycle subagent's return summary (including any Decision-Classification Ledger):
    ---
    {cycle_summary}
    ---

Bias: AGGRESSIVE — when in doubt, surface. Any decision that even touches a
user-visible surface is `product-behavior` unless it has an unambiguous single
defensible answer. Examples that ALWAYS qualify:
  - Root-cause determination scope (what is in scope vs out of scope for this fix).
  - Fix approach when multiple technically-valid approaches exist.
  - Regression-test surface (what behavior the regression tests cover).
  - User-visible behavior changes (however subtle) introduced by the fix.

Audit algorithm:
1. Read SPEC.md from {spec_path}.
2. Read the diff: `git show {cycle_commit_sha} -- {spec_path}/SPEC.md {spec_path}/PHASES.md`
   (or `git diff HEAD~1 -- ...` if no sha was given).
3. Cross-reference the cycle subagent's Decision-Classification Ledger (if present)
   against the diff. Flag product-behavior decisions the subagent auto-accepted.
4. If any uncovered product-behavior decisions exist, write {spec_path}/NEEDS_INPUT.md
   per the canonical schema in ~/.claude/skills/_components/sentinel-frontmatter.md.
5. Return a one-paragraph summary (≤ 8 lines) covering decisions reviewed, any
   surfaced product-behavior calls, and whether NEEDS_INPUT.md was written.

Do NOT halt the loop. NEEDS_INPUT.md is picked up by bug-state.py on the next
cycle and resolved via Step 1g (decision-resume mode).
```

**After the audit subagent returns:**
1. If it wrote `NEEDS_INPUT.md`, append a `**Audit:**` bullet to the per-cycle output block.
2. If clean, append no audit bullet.
3. Audit costs are NOT separate cycles — the audit shares the cycle's slot.
4. Proceed to Step 1e.

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{cycle+1, bug_name, sub_skill, subagent's one-paragraph summary}`.
2. Emit the canonical per-cycle update block (Step 3).
3. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)`.
4. **Post-cycle push backstop.** Verify the work branch is pushed — `git push origin
   $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff; WORK BRANCH
   only, never main, never force).
5. Increment `cycle`. Return to Step 1a. **Cycle counter is monotonic across bug transitions
   (HARD CONSTRAINT 8).**

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

Triggered when `bug-state.py` reports `needs-input`. A batch-mode sub-skill wrote `NEEDS_INPUT.md`
with a genuine design choice. The orchestrator surfaces the choice to the user via
`AskUserQuestion`, captures the answer, persists it, dispatches a Sonnet subagent to apply the
choice to SPEC.md / PHASES.md, and then **continues the loop** — there is no halt.

**Algorithm:**

1. **Read and validate the sentinel.** Parse `{spec_path}/NEEDS_INPUT.md` frontmatter (kind,
   feature_id, written_by, decisions, date). Check for the `## Decision Context` H2 with one H3
   per `decisions[i]` (1:1). If malformed, surface the malformation, push notification, append to
   `cycle_log`, print final batch report, STOP.

2. **Re-print the rich body to chat VERBATIM** (the `## Decision Context` section).

3. **Call `AskUserQuestion` per decision** (capped at 4 per call). Build one entry in `questions`
   for each `decisions[i]`: question title, header chip, parsed options from the H3's
   `**Options:**` list, `multiSelect: false`.

4. **Append `## Resolution` to NEEDS_INPUT.md.** Record chosen option labels per decision.

5. **Commit the resolved sentinel.** Commit message: `docs({bug_id}): record decision resolution`.

6. **Dispatch the Sonnet apply-resolution subagent.** Prompt instructs it to: read NEEDS_INPUT.md,
   propagate choices into SPEC.md / PHASES.md surgically, neutralize the sentinel **by RENAME**
   (`git mv` → `NEEDS_INPUT_RESOLVED.md`, decision-specific suffix if taken — NOT a `kind:` flip,
   which leaves the halt firing since bug-state.py keys on the filename), commit per policy, report a
   one-paragraph summary.

7. **Record and continue the loop.** Append to `cycle_log`, emit the per-cycle block, update
   `prev_cycle_signature`, increment `cycle`, return to Step 1a. DO NOT halt.

**Step 1g neutralization (HARD).** The apply-resolution subagent MUST neutralize
`NEEDS_INPUT.md` by RENAME (`git mv` → `NEEDS_INPUT_RESOLVED.md`, or a
decision-specific suffix if that name is taken), NOT by editing the `kind:`
frontmatter field — `bug-state.py` keys the needs-input halt on the FILENAME
`NEEDS_INPUT.md`, so a `kind:` flip leaves the halt firing next cycle (and trips
`sentinel-kind-matches-filename`). Preserve the Decision Context + Resolution body
verbatim under the new name.

---

### 1h. Blocked-resolution mode (`terminal_reason == "blocked"`)

Triggered when `bug-state.py` reports `blocked` — a cycle subagent (or a hand edit) wrote
`BLOCKED.md` because it hit a genuine blocker it could not resolve autonomously. **`blocked` is no
longer a terminal halt.** Modeled on Step 1g: the orchestrator re-prints the blocker context, asks
the operator for a resolution path via `AskUserQuestion`, dispatches an Opus apply-resolution
subagent to ENACT it (neutralizing `BLOCKED.md`), and **continues the loop**. Only the operator's
explicit "Halt for manual fix" choice stops the run. This replaces the old zero-context halt (a bare
`PushNotification` + STOP).

**Algorithm:**

1. **Read the sentinel** `{spec_path}/BLOCKED.md` (frontmatter `kind`, `feature_id`/`bug_id`,
   `phase`, `blocked_at`, `retry_count`, optional `blocker_kind`; + body). A thin body is NOT a
   malformation halt — proceed, noting if context is sparse.

2. **Re-print the `BLOCKED.md` body to chat VERBATIM** (HARD CONSTRAINT 6 applies — the load-bearing
   context before the truncated `AskUserQuestion` UI):

   ```
   🚧 /lazy-bug-batch — Blocked (loop resumes after you choose a resolution path)

   Bug:   {feature_name} ({bug_id})   ·   phase {phase}   ·   retry_count {retry_count}
   File:  {spec_path}/BLOCKED.md

   ─── BLOCKED.md body (verbatim) ───
   {entire body — blocker description, evidence, any recovery the cycle subagent suggested}
   ───
   ```

3. **`AskUserQuestion` with ONE question — the resolution path** (`header`: "Resolution";
   `multiSelect: false`; adapt option `description`s to the specific blocker when the body names a
   concrete recovery):

   - **Add a phase to resolve the blocker** — dispatch `/add-phase` (or `/plan-bug` if `PHASES.md`
     is absent) with the blocker as the new phase's motivation, then neutralize `BLOCKED.md`. The
     pipeline re-plans → fixes → re-validates. *Recommended when the blocker is missing work.*
   - **Defer this bug; continue the rest of the queue** — move this bug's `queue.json` entry to the
     END of the queue (keep `BLOCKED.md`) so the next actionable bug becomes current.
   - **Halt for manual fix** — keep `BLOCKED.md` untouched, `PushNotification`, print the final
     batch report, STOP. The legacy escape hatch. (Auto-provided **Other** = custom directive.)

4. **If "Halt for manual fix":** do NOT modify `BLOCKED.md`. Append a `cycle_log` halt entry,
   `PushNotification` with `notify_message`, print the final batch report, STOP. The ONLY Step 1h
   path that halts.

5. **Otherwise, append a `## Resolution` block** (chosen path + notes + timestamp) to `BLOCKED.md`
   and commit (`docs({bug_id}): record blocker resolution path`; do NOT push).

6. **Dispatch the Opus apply-resolution subagent to ENACT the path.** It: for "Add a phase" invokes
   `/add-phase` (Skill tool; bugs live in `docs/bugs/`) authoring a phase scoped to the blocker, then
   neutralizes `BLOCKED.md`; for "Defer" reorders `queue.json` (entry → tail), keeps `BLOCKED.md`;
   for "Other" enacts the operator's notes. **NEUTRALIZE BY RENAME** (`git mv BLOCKED.md
   BLOCKED_RESOLVED_<YYYY-MM-DD>.md`) — `bug-state.py` keys the halt on the FILENAME, so a
   frontmatter flip does NOT clear it. Commit + push the work branch; report a one-paragraph summary.
   Dispatch `Agent({ description: "lazy-bug-batch blocked-resolve: {feature_name}", subagent_type:
   "general-purpose", model: "opus", prompt: <above> })`.

7. **Record and continue the loop.** Append `{cycle+1, feature_name, "▶ blocked (resolved: <path>)",
   "<summary>"}` to `cycle_log`; emit the per-cycle block (`### Cycle {cycle+1}/{max_cycles} ·
   {feature_name} · blocked`); update `prev_cycle_signature = (feature_id, "__resolve_blocked__",
   sub_skill_args, current_step)`; increment `cycle`; return to Step 1a. **DO NOT halt** (except the
   Halt path at step 4).

---

### 1i. Operator-directed halt-resolution (other non-max-cycles problem-terminals)

For every remaining problem-terminal that previously bare-`STOP`ed — `completion-unverified` and
`stale_upstream` (the bug pipeline's two Step 1i terminals; `bug-state.py` does NOT emit
`needs-spec-input`) — the orchestrator routes to the shared operator-directed halt-resolution handler
instead of halting. It re-prints the obstacle context, `AskUserQuestion`s a resolution path (reopen &
re-validate / re-materialize / defer & continue / halt), enacts the choice via an Opus subagent, and
continues the loop. Follow the shared component:

!`cat ~/.claude/skills/_components/halt-resolution.md`

`max-cycles` (cost bound), `all-bugs-fixed` (success), and `device-queue-exhausted` /
`cloud-queue-exhausted` (environment — re-run on the right host) keep their existing clean stops per
that component's exclusion list.

---

## Step 1.5: Forward-Progress Verification

After the cycle loop exits with any terminal reason **other than** `blocked`, `needs-input`, run a
final read-only state probe (a `blocked` loop-exit now occurs ONLY when the operator chose "Halt for
manual fix" in Step 1h; every other Step 1h/1i path resumes the loop):

```bash
python3 ~/.claude/scripts/bug-state.py
```

Compare the probe tuple `(feature_id, sub_skill, sub_skill_args, current_step)` against
`prev_cycle_signature`:

- **Forward-progress confirmed** (probe differs OR probe returned a terminal reason): print
  `✅ Next /lazy-bug-batch invocation will: <human-readable summary>` at the top of the Step 2
  report.
- **Forward-progress WARNING** (probe equals `prev_cycle_signature`, no terminal): print a
  warning block identifying the stuck state and push a PushNotification. Do NOT mutate state.
- **`prev_cycle_signature is None`** (no real cycles ran): print only the "Next invocation" line
  from the probe.

---

## Step 2: Final Batch Report

When the loop exits (terminal state or max-cycles), print:

```
## /lazy-bug-batch — Done

**Cycles completed:** {cycle}/{max_cycles}
**Terminal reason:** {terminal_reason or "max-cycles"}
**Last notification:** {notify_message or "—"}

### Cycle log
| # | Bug | Action | Summary |
|---|-----|--------|---------|
| 1 | ... | /spec-bug | ... |
| 2 | ... | /execute-plan | ... |
| ... |

**Next step:**
  - If terminal_reason is "blocked": reached ONLY when the operator chose "Halt for manual fix" in Step 1h (every other path resumes). Resolve {spec_path}/BLOCKED.md by hand, then re-run `/lazy-bug-batch {max_cycles}`.
  - If terminal_reason is "all-bugs-fixed": all bugs fixed or retired
  - If terminal_reason is "completion-unverified": reconcile the receipt gap
  - If max-cycles: re-run `/lazy-bug-batch {max_cycles}` from a fresh session
  - (needs-input is no longer a terminal state — Step 1g resolves inline.)
```

STOP.

---

## Step 3: Cycle Output Discipline (lean · consistent · scannable)

Every cycle — real-skill (Step 1e), inline pseudo-skill (Step 1c.5), decision-resume (Step 1g), blocked-resolution (Step 1h), or halt-resolution (Step 1i)
— emits **EXACTLY ONE update block** in this shape:

```
### Cycle {N}/{max_cycles} · {bug_name} · {sub_skill}
- **Result:** {one-line outcome}
- **Commit:** {short-sha | "—"}
```

**Rules:**
- **ONE block per cycle.** The heading + bullets ARE the cycle's entire chat footprint.
- **No dispatch narration.** Do NOT write "dispatching the subagent" or similar.
- **At most 2–3 bullets, one line each.** Add a third bullet ONLY for a genuinely notable signal:
  `**Inline:** edits performed inline, test-first per batch` on an `/execute-plan` cycle;
  `**Audit:** {N} product-behavior decision(s) surfaced` on a `/spec-bug` cycle where Step 1d.5
  fired; `**Note:** {flag}` for an issue worth surfacing.
- **Halt/terminal announcements are exempt** — they keep their own templated shapes.

---

## Notes

- This skill never invokes the work-log MCP tool. Each sub-skill invoked by the cycle subagents
  logs its own work.
- The orchestrator is single-session by design — no persistence layer. State lives in the
  filesystem sentinels; restart is free.
- Commit policy is delegated to the cycle subagent (which follows the project's
  `.claude/skill-config/commit-policy.md` or standard pattern).
- **No research/ingest steps.** Unlike `/lazy-batch`, this skill has no Step 0.5 pre-loop ingest
  check, no `needs-research` halt path, no `--allow-research-skip` flag, and no in-session
  resume protocol for research uploads. Bugs do not undergo Gemini deep research.
