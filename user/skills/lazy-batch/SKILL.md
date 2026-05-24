---
name: lazy-batch
description: Autonomous orchestrator for the AlgoBooth (or any queue.json-driven) feature pipeline. Loops on lazy-state.py and spawns Opus subagents per cycle. Halts on BLOCKED.md, needs-research (strict halt by default — the first research-pending feature stops the queue; opt into batched research with --allow-research-skip), queue-blocked-on-research (only reachable under --allow-research-skip), or max-cycles cap. NEEDS_INPUT.md (design decisions) does NOT halt: Step 1g calls AskUserQuestion, dispatches a Sonnet apply-resolution subagent to propagate the choice into SPEC/PHASES, and resumes the loop. Research uploaded mid-session via chat (file attachment, pasted text, or absolute path) triggers in-session resume: /ingest-research is dispatched immediately and the loop is re-invoked — no manual re-run required.
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch — Autonomous Pipeline Orchestrator

Drives the per-feature autonomous tail (`/plan-feature` (= `/spec-phases` + `/write-plan` in one cycle) → `/execute-plan` → `/retro` → `/mcp-test` → mark-complete) by looping on `~/.claude/scripts/lazy-state.py`. Each cycle spawns an Opus subagent that invokes the named sub-skill; the orchestrator (this skill, running in the main session) never touches source code, never invokes a skill directly, and never parses sentinel files manually.

**Step ordering note:** `/retro` runs BEFORE `/mcp-test` (Step 8 retro → Step 9 MCP). `/retro` is a docs/analysis pass and runs identically in cloud and workstation; `/mcp-test` only runs on workstation (cloud defers). Behavior inside the loop is unchanged — the orchestrator dispatches whatever `lazy-state.py` returns.

This is the **workstation** orchestrator. The cloud variant is `/lazy-batch-cloud` (under `repos/algobooth/.claude/skills/lazy-batch-cloud/`); the two are coupled per CLAUDE.md.

---

## HARD CONSTRAINTS (non-negotiable)

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` status lines when performing the `__mark_complete__` action (which is a documentation-level update by definition, not a source-code edit). `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns; the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. All other `Write`/`Edit` operations — source code, test files, plan files, PHASES.md — require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference is exclusively via `lazy-state.py`. Sentinel files MAY be read by the orchestrator to confirm a write or to drive a pseudo-skill action.
4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to decision-resume mode (Step 1g) ONLY.** Outside Step 1g, the orchestrator MUST NOT call `AskUserQuestion`. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. (The legacy halt-on-needs-input behavior is gone; the user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation.)
6. **The orchestrator MUST re-print the rich `## Decision Context` to chat BEFORE calling `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print is the load-bearing context. Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` (one missing the `## Decision Context` H2 with H3 subsections matching `decisions:` 1:1) — surface the malformation as a quality issue and halt instead (see Step 1g.1).
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **The `cycle` counter is session-global and monotonic across feature transitions.** It is initialized to 0 in Step 0 *once per `/lazy-batch` invocation* and incremented at the end of every cycle (Step 1c.5 step 5, Step 1e step 5, Step 1g step 7). It MUST NOT be reset when `lazy-state.py` returns a different `feature_id` from one cycle to the next — i.e., when the queue advances from one feature to the next via `__mark_complete__` (or because the prior feature hit a terminal state and a later queue entry became current). Cycle N's status line — `"Cycle N/{max_cycles}: {sub_skill} on {feature_name} → ..."` — always refers to the N-th subagent dispatch in this `/lazy-batch` invocation, regardless of which feature it operated on. A feature transition is **not** a fresh batch; the orchestrator runs ONE cycle log across every feature it touches. The per-cycle status line's `{feature_name}` segment changes across the boundary; the `N` does not.

`$ARGUMENTS` is tokenized on whitespace. Recognized tokens:

- **Positive integer** → `max_cycles`. If absent, default to `10`. If a non-numeric / `< 1` integer is supplied, refuse with:

  > `/lazy-batch` requires a positive integer max-cycles. Usage: `/lazy-batch <N> [--allow-research-skip]`. Default: 10.

- **`--allow-research-skip`** (optional flag) → sets `allow_research_skip = true`. Default `false`. When set, the orchestrator restores the legacy "batch the research backlog" behavior: `lazy-state.py` is called with `--skip-needs-research`, Step 4 drops a `NEEDS_RESEARCH.md` sentinel for each research-pending feature without halting, and the loop halts on `queue-blocked-on-research` once every remaining feature is research-pending. This flag is for sessions where you have manually verified the remaining queue is independent — i.e., starting work on a downstream feature is safe even though an upstream feature is awaiting research. **Use case is rare.** The DEFAULT (flag absent) is to halt strictly on the FIRST `needs-research` so an ordered queue with dependencies cannot leak work onto unsafe downstream features.

Unknown tokens are an error:

> `/lazy-batch`: unrecognized argument `{token}`. Usage: `/lazy-batch <N> [--allow-research-skip]`.

Initialize counters and per-session state:
- `cycle = 0` — initialized once per `/lazy-batch` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py` returns a new `feature_id`).
- `max_cycles = <parsed>`
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `cycle_log = []` — each entry: `{cycle, feature, action, subagent_summary}`
- `research_pending = set()` — feature_ids whose `RESEARCH.md` is missing and a `NEEDS_RESEARCH.md` sentinel was dropped this session. Only used when `allow_research_skip == true`. In the default (strict-halt) path this set never accumulates because Step 4 halts on the first feature; it stays empty.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. In the default path this stays `false` for the entire session because Step 4 halts before the loop continues.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched.

Print the start bookend:

```
## /lazy-batch — Starting
**Max cycles:** {max_cycles}
**Research mode:** {strict halt on first needs-research (default) | batched (--allow-research-skip)}
**Repo root:** {cwd}
```

---

## Step 0.4: Resume-time remote sync (HARD REQUIREMENT)

**Runs once, immediately after Step 0 (arg parsing) and BEFORE Step 0.5 / the Step 1a first state probe.** This is a single-turn git reconciliation, NOT polling — it does not violate HARD CONSTRAINT 7 (no active waiting). It does NOT touch the orchestrator's `Write`/`Edit` sentinel-only scope (HARD CONSTRAINT 1) — these are `Bash` git operations, not file edits.

**Rationale:** a `/lazy-batch` session can be interrupted (machine sleep, crash, terminal close) and resumed later, or the work branch's remote may have advanced from another machine (or a cloud `/lazy-batch-cloud` run on the same branch). If the orchestrator runs `lazy-state.py` against a local tree behind the remote tip, it infers state from stale local files (plans, sentinels, SPEC) and may re-do or corrupt already-pushed work. Reconcile local to the remote tip BEFORE any local-state inference. (This guardrail is mirrored from `/lazy-batch-cloud` Step 0.4, where the same failure mode is acute because of container reclaim.)

**Algorithm:**

1. Determine the work branch:

   ```bash
   branch=$(git rev-parse --abbrev-ref HEAD)
   ```

2. Fetch the remote tip (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error — bounded retry, not an active wait):

   ```bash
   git fetch origin "$branch"
   ```

   If the branch does not exist on `origin` yet (brand-new work branch never pushed), there is nothing to reconcile: skip the rest of Step 0.4 and continue to Step 0.5.

3. Fast-forward local to the remote tip:

   ```bash
   git merge --ff-only "origin/$branch"
   ```

4. **If the fast-forward FAILS because local has DIVERGED from `origin`** (non-fast-forwardable — local has commits origin lacks AND origin has commits local lacks), **do NOT clobber.** Do NOT `git reset --hard`, do NOT force anything. Surface the divergence to chat and halt for human resolution:

   ```
   🛑 /lazy-batch — work branch diverged from origin

   Local `{branch}` and origin/{branch} have both moved independently
   (non-fast-forwardable). This may indicate concurrent edits from another
   machine or a force-push. Refusing to auto-reconcile to avoid losing work.

   Resolve manually (inspect `git log --oneline --graph {branch} origin/{branch}`),
   then re-invoke /lazy-batch.
   ```

   PushNotification with the same one-line summary, then STOP. Do NOT run `lazy-state.py`.

5. On a clean fast-forward (or when local was already up to date / the branch was unpushed), print a one-line confirmation and continue to Step 0.5:

   ```
   🔄 Synced local {branch} to origin tip ({short-sha}) before resuming.
   ```

---

## Step 0.5: Pre-loop staged-research ingest check

Before entering the main loop, check whether the user staged Gemini research uploads between sessions. This is the "resume after halt" entry point — a previous `/lazy-batch` invocation may have halted in Step 1f (research-wait), the user uploaded research in the meantime, and this invocation should pick it up automatically.

**Algorithm:**

1. Probe for staged `.txt` files:

   ```bash
   find docs/gemini-sprint/results -maxdepth 1 -name '*.txt' -type f 2>/dev/null | head -1
   ```

   If empty → no staged research, skip to Step 1.

2. If staged `.txt` files exist, dispatch `/ingest-research` as cycle 1 (counts against `max_cycles`):

   ```
   Agent({
     description: "lazy-batch pre-loop ingest-research dispatch",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <the prompt below>
   })
   ```

   **Subagent prompt:**

   ```
   You are advancing one cycle of the autonomous feature pipeline. The
   orchestrator detected staged Gemini research at session start —
   .txt file(s) are present in docs/gemini-sprint/results/.

   Working directory: {cwd}

   Action for this cycle:
     Invoke the /ingest-research skill with no arguments. It will scan
     docs/gemini-sprint/results/ for every .txt, correlate each to a feature
     via the prompt symlinks under docs/gemini-sprint/prompts/, write
     per-feature RESEARCH.md + RESEARCH_SUMMARY.md, drop the > Draft
     (pre-Gemini) trailer in SPEC.md, clear queue.json "stub": true, move
     consumed .txt files to _consumed/, and commit per feature.

   Operating mode: batch (--batch is implicit for /ingest-research — see its
   SKILL.md hard constraints).

   After the skill returns:
     1. Report the final summary block /ingest-research printed.
     2. List any ambiguous correlations (NEEDS_INPUT.md sentinels written) —
        the next orchestrator cycle will halt at decision-halt mode (Step 1g).
     3. Report which feature_ids now have RESEARCH.md on disk.

   You may NOT spawn further subagents. You MAY use Edit/Write under docs/
   per /ingest-research's hard constraints.
   ```

3. After dispatch:
   - Append to `cycle_log`: `{1, "—", "/ingest-research (pre-loop)", "<subagent summary>"}`.
   - Increment `cycle` to 1.
   - Enter the main loop (Step 1).

Direct `RESEARCH.md` drops into canonical feature directories don't require ingestion — `lazy-state.py` sees them at Step 5 and routes to `/spec` Phase 3 naturally. Step 0.5 is specifically for the staged `.txt` upload path.

If the user provided a one-off file path via `/ingest-research <path>` (run BEFORE `/lazy-batch`), that invocation handled the ingest in its own session — by the time `/lazy-batch` runs, `RESEARCH.md` already exists in the canonical location, and Step 0.5 is a no-op for that feature.

---

## Step 1: Cycle Loop

Repeat:

### 1a. Run lazy-state.py

```bash
python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]
```

Pass `--skip-needs-research` **only when `allow_research_skip == true` AND `skip_needs_research == true`**. The double-gate matters: in the default (strict-halt) path, `skip_needs_research` never flips to `true` because Step 4 halts the loop on the first `needs-research`, so the script is always called without the flag and returns `terminal_reason: needs-research` for the first research-pending feature in queue order. Only the `--allow-research-skip` path arms the legacy batching behavior.

If the script exits non-zero, surface the error, push a PushNotification, print the final batch report (see Step 2), and STOP.

Parse the JSON output. Extract: `feature_id`, `feature_name`, `spec_path`, `current_step`, `sub_skill`, `sub_skill_args`, `terminal_reason`, `notify_message`, `diagnostics`.

### 1b. Handle terminal states

If `terminal_reason` is set:

- **`blocked`**: PushNotification with `notify_message`, print final batch report, STOP. Do NOT modify the sentinel; the human resolves it manually.
- **`needs-input`**: see Step 1g (decision-resume mode). **Not a terminal state for the orchestrator anymore.** Step 1g re-prints the rich `## Decision Context`, runs `AskUserQuestion`, appends `## Resolution`, dispatches the Sonnet apply-resolution subagent (which edits SPEC.md / PHASES.md and neutralizes the sentinel), and returns to Step 1a. The loop continues; do NOT print the final batch report.
- **`needs-research`**: see Step 4 (research halt). Behavior depends on `allow_research_skip`:
  - **Default (`allow_research_skip == false`)**: Step 4 writes `NEEDS_RESEARCH.md`, prints the inline-prompt halt announcement, PushNotifications, prints the final batch report, and STOPs. The orchestrator does NOT advance past the research-pending feature — this is critical for ordered queues where downstream features depend on upstream work.
  - **Opt-in (`allow_research_skip == true`)**: legacy batching behavior — Step 4 writes `NEEDS_RESEARCH.md`, adds `feature_id` to `research_pending`, **DOES NOT increment cycle**, flips `skip_needs_research = true`, and returns to Step 1a so the next state-script call passes `--skip-needs-research` and either advances to a ready feature or returns `queue-blocked-on-research`.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode). **Only reachable when `allow_research_skip == true`** — in the default path Step 4 halts before this terminal can fire.
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
- **`__flip_plan_complete_cloud_saturated__`** — emitted only by `lazy-state.py --cloud` at Step 7a when an `In-progress` plan's only unchecked WUs (scoped to the plan's `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. `sub_skill_args` is the absolute plan-file path. Read the plan's YAML frontmatter, edit ONLY the `status:` line in place (`In-progress` → `Complete`) — leave every other field and the markdown body untouched. Derive the plan part number from the plan's `phases:` field (e.g. `phases: [6]` → part 6); fall back to the plan filename's leading `part-N` / `phase-N` token if `phases:` is missing. Stage the plan file and commit per project policy with message `chore(<feature_id>): mark plan part N Complete (cloud-saturated)`. Do NOT touch SPEC.md, ROADMAP.md, or any sentinel — this is a frontmatter-only flip. Editing style: match the conservative single-field rewrite already used by `__write_deferred_non_cloud__` (idempotent if the line is already `Complete`).

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. **Push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** The inline pseudo-skill committed a sentinel / plan-frontmatter change locally; push it now — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This backstops inline cycles the orchestrator owns directly — a `git push` of an already-committed change, NOT a Write/Edit, so HARD CONSTRAINT 1 still holds. "Up to date" is a fine result (a prior cycle's push already carried it).
3. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: {sub_skill} on {feature_name} → <inline outcome>"`.
4. Update `prev_cycle_signature = (feature_id, sub_skill, current_step)` (same uniform post-cycle update as Step 1e — keeps loop-guard accurate across mixed pseudo-skill / real-skill cycles).
5. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

This saves one Opus dispatch per pseudo-skill action. On a typical feature lifecycle (workstation: 1 × `__write_validated_*` + 1 × `__mark_complete__` = 2 dispatches reclaimed; cloud: 1 × `__write_deferred_non_cloud__` minimum) the savings compound across a multi-feature queue pass.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else.

**Loop-guard check (BEFORE composing the prompt):** Compute the current cycle's signature as the tuple `(feature_id, sub_skill, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, current_step)`, the state script has returned the same triple two cycles in a row — almost always a sign that a terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`) is missing or that a plan/sentinel write the previous cycle was supposed to perform did not actually land. The orchestrator MUST append the **LOOP DETECTED** block below to the subagent prompt so the subagent diagnoses the missing sentinel rather than producing yet another plan / running the same skill against unchanged state.

Base prompt template:

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

Sub-subagent dispatch policy (LOAD-BEARING — READ CAREFULLY):
  The dispatched skill's own SKILL.md is AUTHORITATIVE on whether/how to
  spawn sub-subagents. Follow what the skill says — do NOT impose a blanket
  prohibition on top of it. The only prohibition you carry is "no parallel
  pipeline orchestrators" (do NOT spawn another /lazy or /lazy-batch).

  Per-skill expectations (must match the skill's own contract):
    • /execute-plan — REQUIRES you (as ITS orchestrator) to dispatch Sonnet
      test-agent + impl-agent sub-subagents per batch. You MUST NOT call Edit
      or Write on source/test files yourself; compose Agent({model: "sonnet"})
      calls instead, per /execute-plan's Step 3 "Execution Model Enforcement".
      Zero sub-subagents in an /execute-plan cycle = hard contract violation.
    • /retro — REQUIRES parallel research subagents A–G (implementation
      notes, spec diff, commit history, quality, runtime, session history,
      skill compliance) per /retro's Step 3.
    • /mcp-test — REQUIRES one Sonnet test subagent (Step 5).
    • retro-feature — composed orchestrator that internally loops
      /retro + /execute-plan; its own SKILL.md governs nested dispatches.
    • plan-feature — composed orchestrator that runs /spec-phases THEN
      /write-plan via the Skill tool (in-context, not Agent dispatch); its
      own SKILL.md governs the sequence. Orchestrator-only work — no
      sub-subagent dispatch required. This is what lazy-state.py emits at
      Step 6 (replacing the separate /spec-phases dispatch).
    • /spec, /spec-phases, /write-plan, /add-phase, /ingest-research —
      orchestrator-only, no sub-subagent dispatch required.

  If your dispatch prompt (this prompt) appears to contradict the dispatched
  skill's SKILL.md, the SKILL.md wins. Re-read it from disk to confirm — do
  NOT rely on memory.

Source/test file edits:
  - /execute-plan path: you MUST dispatch Sonnet sub-subagents; never Edit/Write
    source/test files directly. The skill enumerates the source-file extensions
    (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files) that trigger this.
  - Other-skill paths: if the dispatched skill does its own internal dispatch
    and only requires you to invoke it once, just invoke it once.

Plan-part status + per-WU granularity (RESUME SAFETY):
  To make an interrupted cycle resume cleanly instead of redoing a whole plan
  part, keep the plan part's on-disk status and per-WU checkboxes accurate AS
  THE WORK LANDS, not only at end-of-cycle:
    • For /execute-plan (and any /retro / realign cycle that mutates a plan
      part): the dispatched skill MUST flip the plan part frontmatter `status:`
      `Ready` → `In-progress` and commit it BEFORE starting work-unit work, and
      tick each `- [ ]` → `- [x]` checkbox + commit as that work-unit lands. An
      interrupted session then resumes at the first still-unchecked box with
      accurate In-progress state instead of redoing the part from a stale
      `Ready`.
    • Prefer plan work-units authored as parseable `- [ ]` markdown checkboxes
      (one per WU) so resume granularity is per-WU, not per-part. If a part is
      prose-only, note it in your summary so it can be re-authored with
      checkboxes.
  (On workstation, local commits survive an interrupted session, so the
  end-of-cycle push in the commit step below is sufficient durability — pushing
  each flip/tick immediately is a cloud-only requirement in /lazy-batch-cloud.)

After the skill returns:
  1. If a commit policy file exists at .claude/skill-config/commit-policy.md,
     follow it. Otherwise commit per the standard pattern and push to the
     current branch. Skip commit only if the skill produced no file changes.
  2. Report a one-paragraph summary: what state was advanced, files modified,
     commit hash (or "no commit"), and any issues. Keep it under 8 lines so the
     orchestrator's per-cycle log stays compact. If you ran /execute-plan,
     INCLUDE the count of Sonnet sub-subagents you dispatched — this is the
     audit signal that the contract was honored.
```

**LOOP DETECTED block (append only when the loop-guard fires):**

```
⚠️  LOOP DETECTED: The state script returned this exact
(feature_id={feature_id}, sub_skill={sub_skill}, current_step={current_step})
tuple on the PREVIOUS cycle as well. This usually means a terminal sentinel
(RETRO_DONE.md / VALIDATED.md / DEFERRED_NON_CLOUD.md / SKIP_MCP_TEST.md) is
missing — the skill that was supposed to write it on the prior cycle did not.

Before invoking {sub_skill} again, DIAGNOSE THE MISSING SENTINEL:
  1. Read the canonical schemas in
     ~/.claude/skills/_components/sentinel-frontmatter.md.
  2. Inspect {spec_path}/ for existing sentinels and plan files.
  3. Determine which sentinel SHOULD exist given the feature's current state
     (e.g. all phases complete + validated + retro plan present with no
     significant divergences → RETRO_DONE.md should already exist; if it
     doesn't, the previous retro round failed to write it).
  4. If you can write the missing sentinel directly (its preconditions are
     unambiguously met), DO SO instead of re-running {sub_skill}. Then commit
     the sentinel and report the loop-break in your summary.
  5. If the preconditions are NOT unambiguously met, run {sub_skill} as
     instructed but explicitly emit the appropriate terminal sentinel as part
     of its completion (e.g. /retro Step 6c writes RETRO_DONE.md when no
     significant divergences). Report which sentinel you emitted.
  6. If no sentinel applies (genuine ambiguity), write BLOCKED.md with
     blocker_kind: loop-detected and a clear description so the next cycle
     surfaces it as a terminal halt.

The orchestrator will halt on the next cycle's max-cycles cap if this loop
persists — your job here is to break it.
```

Append the LOOP DETECTED block after the base prompt's final paragraph (after "follow the skill's internal subagent-vs-orchestrator rules.") when and ONLY when the loop-guard condition holds. Do NOT include it on the first cycle (when `prev_cycle_signature is None`) or when the signature differs from the previous cycle.

Dispatch:

```
Agent({
  description: "lazy-batch cycle {cycle+1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: <"sonnet" if LOOP DETECTED else "opus">,
  prompt: <the prompt above>
})
```

**Model selection.** Normal cycles dispatch on Opus because real-skill cycles can involve novel implementation decisions. The loop-resolution cycle (LOOP DETECTED branch) is mechanical — the prompt already contains the diagnosis (which sentinels to inspect, what conditions warrant which write) and the work is "read the canonical sentinel schema, identify which sentinel preconditions are met, write it, commit". Sonnet is sufficient at roughly 5× the cost-efficiency. Use `model: "sonnet"` when the LOOP DETECTED block was appended, `model: "opus"` otherwise.

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, subagent's one-paragraph summary}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: /{sub_skill} on {feature_name} → {first-line-of-summary}"`.
3. Update `prev_cycle_signature = (feature_id, sub_skill, current_step)` so the next cycle's Step 1d loop-guard can compare against this cycle.
4. **Post-cycle push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** Verify the work branch is pushed — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). The cycle subagent's Step 1d already commits and pushes to the current branch at end-of-cycle, so this normally reports "up to date" — it is the backstop for any cycle that did not push itself. A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 still holds.
5. Increment `cycle`. Return to Step 1a. **Cycle counter is monotonic across feature transitions (HARD CONSTRAINT 8).** If the next state-script call returns a different `feature_id` — e.g. because this cycle's `__mark_complete__` finished the prior feature, or the queue rolled forward to the next ready feature for any other reason — the cycle counter continues counting from the value just produced here. Do NOT reset to 0 or 1 on the boundary; cycle N+1 is always the next cycle regardless of which feature it lands on.

**Note:** Step 1c.5 (pseudo-skill inline handling) MUST also update `prev_cycle_signature` to the cycle's `(feature_id, sub_skill, current_step)` triple before returning to Step 1a. Otherwise a real-skill cycle following a pseudo-skill cycle would compare against a stale signature and miss loops that span both kinds. The orchestrator should treat the prev-signature update as a uniform post-cycle action regardless of whether the cycle dispatched a subagent or ran inline. The same applies to the cycle-counter increment: it is a uniform post-cycle action that happens once per cycle (real, pseudo, or decision-resume) and never resets.

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

**Reachable only when `allow_research_skip == true`.** Triggered when `lazy-state.py --skip-needs-research` reports `queue-blocked-on-research` AND `research_pending` is non-empty (the orchestrator has already dropped at least one `NEEDS_RESEARCH.md` this session). The user's Gemini deep-research step is the blocker. In the default (strict-halt) path this state is unreachable because Step 4 halts on the first `needs-research` before the loop ever reaches `queue-blocked-on-research`.

**This is a passive halt, NOT an active wait.** The orchestrator MUST NOT use `Monitor`, `sleep`, polling loops, or any other mechanism to block on filesystem events (HARD CONSTRAINT 7). Research arrives on the user's timeline — they may be away from their device for hours or days. The orchestrator announces the halt, surfaces every supported upload path, fires a PushNotification, and stops. The user's next `/lazy-batch` invocation is the implicit resume signal; Step 0.5 (pre-loop ingest check) and `lazy-state.py`'s normal flow auto-detect uploads on re-entry — no special detection is needed at resume time.

**Algorithm:**

1. **Read every pending feature's RESEARCH_PROMPT.md.** For each `feature_id` in `research_pending`, locate the prompt file (the path is recorded in the just-written `NEEDS_RESEARCH.md` sentinel's `research_prompt_path` field, resolved relative to that feature's `spec_path`). Read its content; measure its character count.

2. **Announce the halt with inline prompts.** The mobile-friendliness goal: every prompt the user needs to paste into Gemini is in chat, in a fenced code block, ready for long-press-copy. No GitHub UI navigation required. Print:

   ```
   ⏸  /lazy-batch paused — {N} feature(s) awaiting Gemini research.

   Pending: {comma-separated feature_ids from research_pending}

   ───────────────────────────────────────────────────────────────────────────
   ```

   Then, for EACH pending feature in order, print:

   ```
   ### {feature_id} — {feature_name}

   Prompt file: `{spec_path}/RESEARCH_PROMPT.md`

   **Research prompt** (copy this entire block into Gemini Deep Research):

   ```text
   {full RESEARCH_PROMPT.md content, verbatim, including the `## Project context` identity prepend if present}
   ```

   [length: {NNNN} chars — {within | over} Gemini's 24,000-char practical web-UI limit]

   ───────────────────────────────────────────────────────────────────────────
   ```

   The `[length: ...]` line is a soft indicator. When over cap, append the addendum `(may need manual trimming before paste)` so the operator notices on mobile without scrolling back. Do NOT refuse to print — over-cap prompts are still printed in full; the warning is informational.

   After all per-feature blocks, print the unified upload instructions:

   ```
   When you have research result(s), the fastest path is to upload them in your
   NEXT MESSAGE in this conversation — I will dispatch /ingest-research
   IN-SESSION and re-invoke /lazy-batch automatically (see Step 5: In-Session
   Resume Protocol). You do NOT need to re-run /lazy-batch manually.

   Supported upload shapes for your next message:
     • File attachment (Claude Code path or chat-uploaded file)
     • Pasted text — the research content in a fenced code block or quoted
     • An absolute file path on the machine running this session (e.g.
       ~/Downloads/<file>.txt or a phone-synced folder)

   Or, if you prefer to stage the file and resume later, any of these paths
   still work:

     ① Staged (gemini-sprint workflow):
        Save each Gemini output as docs/gemini-sprint/results/<feature-id>.txt
        (one file per feature). NOTE: this path is gitignored in AlgoBooth —
        fine for a workstation session that resumes locally, but a bare .txt
        stage WILL NOT persist across a cloud-container reclaim. Path ② is
        durable; the in-session resume above is durable AND immediate.

     ② Canonical drop (skip ingestion, durable):
        Write the research directly as
        docs/features/.../<feature-id>/RESEARCH.md
        On your next /lazy-batch run, lazy-state.py routes straight to Step 5
        (integrate research → /spec Phase 3) — no ingestion step needed.

     ③ One-off file path (workstation only):
        Run /ingest-research <absolute-or-relative-path-to-the-file> first.
        That skill copies the file into the staging dir, correlates it, and
        writes RESEARCH.md + RESEARCH_SUMMARY.md. Then re-run /lazy-batch
        to resume the pipeline.

   Re-invoke with /lazy-batch {max_cycles} [--allow-research-skip] when ready
   (only required if you did NOT use the in-session resume path above).
   ```

3. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {N} feature(s) awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

4. **Append to `cycle_log`:** `{cycle+1, "—", "⏸ research-wait (halt)", "{N} feature(s) pending: {feature_ids}"}`. DO NOT increment `cycle` — the halt is not a real cycle.

5. **Print the final batch report (Step 2)** with `terminal_reason = "queue-blocked-on-research"` and STOP. The orchestrator's turn ends; the user's next invocation re-enters via Step 0 → Step 0.5 → Step 1.

**Resume contract.** When the user re-invokes `/lazy-batch`, the natural flow handles every supported upload path:

| Upload path | Detected by | Handled by |
|-------------|-------------|------------|
| ① Staged `.txt` in `docs/gemini-sprint/results/` | Step 0.5's `find` probe | Step 0.5 dispatches `/ingest-research` (1 cycle) |
| ② Direct `RESEARCH.md` in feature dir | `lazy-state.py` Step 5 | normal main-loop dispatch of `/spec` Phase 3 |
| ③ One-off path | User ran `/ingest-research <path>` separately before `/lazy-batch`; that invocation copied the file to the staging dir and processed it. By the time `/lazy-batch` starts, `RESEARCH.md` is already in the canonical location | normal main-loop dispatch (path ② applies) |

No special resume detection is needed in `/lazy-batch`'s main loop — every upload path lands in a state the existing logic already handles.

**Cycle accounting at resume.** The new `/lazy-batch` invocation gets a fresh `max_cycles` budget. The previous session's cycle count is gone (no persistence layer — see Notes). This is by design: each `/lazy-batch <N>` run is a bounded budget the user authorizes.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

Triggered when `lazy-state.py` reports `needs-input`. A batch-mode sub-skill (post-research only — per the post-research halting rule in `~/.claude/skills/_components/sentinel-frontmatter.md`) wrote `NEEDS_INPUT.md` with a genuine design choice. The orchestrator surfaces the choice to the user via `AskUserQuestion`, captures the answer, persists it to disk, **dispatches a Sonnet subagent to apply the choice to SPEC.md / PHASES.md and neutralize the sentinel**, and then **continues the loop** — there is no halt. The user retains decision-making autonomy (they answered the question); the apply step is mechanical propagation of the choice into the planning docs.

**Algorithm:**

1. **Read and validate the sentinel.** The state script's `spec_path` field names the feature dir; the sentinel is at `{spec_path}/NEEDS_INPUT.md`.

   - Parse the YAML frontmatter (kind, feature_id, written_by, decisions, date).
   - Read the markdown body.
   - **Schema check:** the body MUST contain a `## Decision Context` H2 with one H3 subsection per `decisions[i]` (matching titles, 1:1). Each H3 MUST carry `**Problem:**`, `**Options:**`, and `**Recommendation:**` blocks per the rich-body convention in `sentinel-frontmatter.md`.
   - **If malformed** (missing `## Decision Context`, mismatched count, missing required subsections):

     ```
     ⚠️  NEEDS_INPUT.md missing required '## Decision Context' section (or
     subsections do not match decisions: 1:1). Writer skill: {written_by}.
     Halting without prompting — fix the skill so future halts emit the rich
     body, or supply input manually.

     File: {spec_path}/NEEDS_INPUT.md
     ```

     PushNotification with the same message, append `{cycle+1, feature_name, "🛑 needs-input (malformed)", "<writer> wrote NEEDS_INPUT.md without rich body"}` to `cycle_log`, print the final batch report, STOP. Do NOT call `AskUserQuestion` against a malformed file (HARD CONSTRAINT 6).

2. **Re-print the rich body to chat VERBATIM.** This is the load-bearing context the user needs BEFORE the truncated `AskUserQuestion` UI fires:

   ```
   ❓ /lazy-batch — Decision required (loop will resume after your answer)

   Feature: {feature_name} ({feature_id})
   Writer:  {written_by}
   File:    {spec_path}/NEEDS_INPUT.md

   ─── ## Decision Context (from NEEDS_INPUT.md) ───────────────────────────

   {entire `## Decision Context` section verbatim, including all H3 subsections,
   Problem/Options/Recommendation blocks, and any prose around them — copy/paste
   the section as-is, no summarization.}

   ─────────────────────────────────────────────────────────────────────────

   After you answer the AskUserQuestion prompts below, I will dispatch a
   Sonnet subagent to apply your choice(s) into SPEC.md / PHASES.md and
   neutralize NEEDS_INPUT.md, then immediately resume the batch loop. No
   manual re-run required.
   ```

3. **Call `AskUserQuestion` per decision.** For each `decisions[i]` (1..N, capped at 4 per HARD CONSTRAINT — see `sentinel-frontmatter.md` Producer responsibilities), build one entry in the `questions` array:

   - `question`: the H3 subsection title, exactly (matches `decisions[i]`).
   - `header`: an 8-12 char chip extracted from the title (e.g., title "Storage backend for cached voices" → header "Storage").
   - `options`: parsed from the H3's `**Options:**` list. Each `- **<name>** — <description>` bullet becomes one option:
     - `label`: the bold `<name>`.
     - `description`: the first sentence of `<description>`. AskUserQuestion will truncate longer descriptions — the full text is already above in chat (step 2), so the truncation is non-fatal.
   - `multiSelect`: `false` unless the H3 explicitly says "select all that apply" or similar (rare — most decisions are mutually exclusive). When in doubt, default to `false`.

   Call `AskUserQuestion` once with all N questions in a single `questions` array (the tool supports up to 4 questions per call). Capture the response.

4. **Append `## Resolution` to NEEDS_INPUT.md.** Construct the Resolution block:

   ```markdown

   ## Resolution

   *Recorded on <YYYY-MM-DD HH:MM:SS UTC>.*

   ### 1. <decision[0] title>

   **Choice:** <selected option label>
   **Notes:** <user's free-text note if they chose "Other", or empty string>

   ### 2. <decision[1] title>

   **Choice:** ...
   ```

   Use the `Edit` tool to append this block to the existing `NEEDS_INPUT.md` — do NOT overwrite. Use the `Write` tool only as a fallback if `Edit` cannot find a unique insertion point at end-of-file (in practice, append by reading the file, concatenating the new section, and `Write`-ing the combined content back). HARD CONSTRAINT 1 allows this specific append.

5. **Commit the resolved sentinel.** Stage `NEEDS_INPUT.md` (with the new `## Resolution`) and commit per the project's commit policy:

   - First try `.claude/skill-config/commit-policy.md`; if absent, follow the standard pattern.
   - Commit message: `docs({feature_id}): record decision resolution`

   Do NOT push (consistent with other orchestrator-inline commits).

6. **Dispatch the Sonnet apply-resolution subagent.** Build the prompt:

   ```
   You are applying a user-resolved design decision back into the feature docs.

   Feature: {feature_name} ({feature_id})
   Working directory: {cwd}
   Sentinel file:    {spec_path}/NEEDS_INPUT.md

   The user just answered the decision(s) in NEEDS_INPUT.md's `## Decision
   Context` section. Their answers are in the appended `## Resolution` section
   at the bottom of that file (date, per-decision Choice + optional Notes).
   Your job is to propagate those choices into the feature's planning docs and
   neutralize the sentinel so the orchestrator's next /lazy-state.py call does
   not halt on it again.

   Steps:
     1. Read NEEDS_INPUT.md fully (frontmatter + Decision Context + Resolution).
     2. For EACH decision, locate the section(s) of {spec_path}/SPEC.md and/or
        {spec_path}/PHASES.md that the choice impacts. Apply the choice
        surgically: update the design narrative, the implementation plan, API
        shape, schema choice, dependency selection — whatever the decision
        touches. Keep edits scoped; the choice is the user's, your job is
        mechanical propagation. If a decision has no impact on either doc
        (rare — e.g., the question was about future-phase scaffolding not
        drafted yet), record that in your summary and move on.
     3. Neutralize NEEDS_INPUT.md so lazy-state.py stops returning
        terminal_reason=needs-input on the next cycle. Do EITHER:
          (a) Rename the file to NEEDS_INPUT_RESOLVED.md (preserves audit
              trail at a new path), OR
          (b) Edit the frontmatter to change `kind: needs-input` to
              `kind: needs-input-resolved` (preserves audit trail in place).
        Prefer (b) — it keeps the file's git history continuous. Either way,
        the Decision Context + Resolution body MUST be preserved verbatim.
     4. Commit per .claude/skill-config/commit-policy.md (or standard pattern).
        Commit message: `docs({feature_id}): apply decision resolution to
        SPEC/PHASES`.
     5. Report a one-paragraph summary (under 8 lines): which files were
        edited, which sections changed, how each choice was applied, commit
        hash. If any decision was a no-op against SPEC/PHASES, say so
        explicitly so the orchestrator's cycle log is accurate.

   You may NOT spawn further subagents. You MAY use Edit/Write on SPEC.md,
   PHASES.md, and the sentinel — this dispatch exists to authorize exactly
   those edits.
   ```

   Dispatch:

   ```
   Agent({
     description: "lazy-batch decision-apply: {feature_name}",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <the prompt above>
   })
   ```

7. **Record and continue the loop.**
   - Append to `cycle_log`: `{cycle+1, feature_name, "▶ needs-input (resolved + applied)", "<N> decision(s); <one-line subagent summary>"}`.
   - Print one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: needs-input resolved → {first-line-of-subagent-summary}"`.
   - Update `prev_cycle_signature = (feature_id, "__apply_needs_input__", current_step)`. The synthetic sub_skill token distinguishes this from any real-skill cycle so the Step 1d loop-guard treats it as its own kind of cycle.
   - Increment `cycle`. Return to Step 1a. **DO NOT halt, DO NOT print the final batch report.** The next state-script call should see the neutralized sentinel and route to the natural next step for the feature (typically resuming the skill that wrote NEEDS_INPUT.md — `/write-plan` or `/execute-plan` — now that the design ambiguity is resolved).

This eliminates the legacy "answer → halt → manual SPEC/PHASES edit → re-run /lazy-batch" friction. The user's autonomy is preserved in step 3 (the choice itself); steps 6–7 are bounded mechanical work delegated to Sonnet so the orchestrator's Opus context stays lean.

---

## Step 1.5: Forward-Progress Verification (informally "Step 2.5"; runs after loop exit, before the Step 2 batch report)

After the cycle loop exits with any terminal reason **other than** `blocked`, `needs-input`, or `queue-missing`, run a final read-only state probe to confirm the loop actually advanced the queue. This is cheap insurance against the silent-no-op failure mode where a cycle subagent reports success but does not write the sentinel that would let the next invocation move on.

Skip this step entirely when `terminal_reason in {"blocked", "needs-input", "queue-missing"}` — those halts describe states the orchestrator already cannot resolve, and the user will be looking at the sentinel / config directly. For every other exit (including `all-features-complete`, `needs-research`, `queue-blocked-on-research`, `cloud-queue-exhausted`, and max-cycles), execute the probe.

**Algorithm:**

1. Run the state script ONE more time, identically to Step 1a:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]
   ```

   Pass `--skip-needs-research` under the same double-gate condition as Step 1a (`allow_research_skip == true AND skip_needs_research == true`). Parse the JSON.

2. Compute the probe tuple `(feature_id, sub_skill, current_step)` from the new output (any field may be `null` for terminal exits — that is fine, the comparison still works).

3. Compare against `prev_cycle_signature` (the signature of the last real-skill or pseudo-skill cycle run during THIS invocation). Three cases:

   **(a) Forward-progress confirmed.** Probe tuple differs from `prev_cycle_signature`, OR the probe returned a terminal reason. Print one line at the top of the Step 2 final batch report:

   ```
   ✅ Next /lazy-batch invocation will: <human-readable summary>
   ```

   Construct `<human-readable summary>` from the probe output:
     - Terminal reason set → `"halt on {terminal_reason} ({notify_message})"`.
     - Pseudo-skill (`__*__`) → `"perform {sub_skill} on {feature_name} ({current_step})"`.
     - Real skill → `"dispatch /{sub_skill} on {feature_name} ({current_step})"`.

   **(b) Forward-progress WARNING.** Probe tuple equals `prev_cycle_signature` (same `feature_id`, same `sub_skill`, same `current_step`, no terminal reason). This means the next `/lazy-batch` invocation would re-issue the cycle this run just finished — the queue did not advance. Print this block at the top of the Step 2 final batch report:

   ```
   ⚠ FORWARD-PROGRESS WARNING: the next /lazy-batch invocation will return
   the same state as the cycle we just finished
   (feature_id={feature_id}, sub_skill={sub_skill},
   current_step={current_step}).

   This run did not advance the queue. Likely causes:
     • A sentinel that should have been written wasn't (RETRO_DONE.md,
       VALIDATED.md, DEFERRED_NON_CLOUD.md, SKIP_MCP_TEST.md).
     • A plan-frontmatter status flip the last cycle was supposed to perform
       did not land (e.g. cloud-saturated In-progress → Complete).
     • lazy-state.py is stuck on a condition no skill is resolving.

   Inspect {spec_path}/ sentinels and plan frontmatter before re-invoking.
   ```

   PushNotification with `"lazy-batch forward-progress WARNING — queue did not advance; inspect {feature_name} sentinels."` so the user sees the issue even if they only read the notification.

   **(c) `prev_cycle_signature is None`.** No real cycles ran this invocation (e.g. Step 0.5 ingest was the only action, or the very first state-script call was already terminal). Skip the comparison and print only the case-(a) "Next invocation will" line based on the probe.

4. The probe is **read-only**: do NOT mutate `cycle`, do NOT append to `cycle_log`, do NOT touch sentinels. Its sole output is the WARNING / NEXT line at the top of the Step 2 report.

5. If the probe itself exits non-zero (the script crashed), print `⚠ FORWARD-PROGRESS PROBE FAILED: lazy-state.py exited non-zero — re-invoke /lazy-batch to retry.` at the top of the Step 2 report and continue. Do NOT halt — the loop already finished; the probe failure is information, not a fatal error.

This step is the orchestrator's cheap end-of-run sanity check: it costs one extra `lazy-state.py` invocation (microseconds) and surfaces silent loop-perpetuation bugs at the moment they happen, instead of on the user's next `/lazy-batch` invocation.

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
| 1 | ... | /plan-feature | ... |
| 2 | ... | /execute-plan | ... |
| ... |

**Next step:**
  - If terminal_reason is "blocked": resolve {spec_path}/BLOCKED.md
  - If terminal_reason is "needs-research" (DEFAULT path, strict halt): the fastest resume path is to upload Gemini research in your NEXT MESSAGE in this conversation — the in-session resume protocol (Step 5) will dispatch /ingest-research and re-invoke /lazy-batch automatically. Otherwise, stage/drop the research per Step 4's halt announcement and re-run `/lazy-batch {max_cycles}` manually.
  - If terminal_reason is "queue-blocked-on-research" (only reachable under --allow-research-skip): same as needs-research — upload research in chat for fastest resume, or use one of the staged/drop paths and re-run `/lazy-batch {max_cycles} [--allow-research-skip]`.
  - (needs-input is no longer a terminal state — Step 1g resolves and resumes within the same /lazy-batch invocation.)
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

The state script returns `needs-research` when `RESEARCH.md` is missing but `RESEARCH_PROMPT.md` exists. This step has **two paths**, gated by the `allow_research_skip` flag parsed in Step 0.

The default path (strict halt) is the safer choice for ordered queues with cross-feature dependencies: the FIRST research-pending feature in queue order halts the loop, so downstream features that may depend on the in-flight one never start work prematurely. The opt-in path (`--allow-research-skip`) restores the legacy "batch all pending research, halt once" behavior — only safe when the operator has verified the remaining queue is independent.

### Step 4 — shared sentinel write (both paths)

Both paths write the same `NEEDS_RESEARCH.md` sentinel:

1. Check whether `{spec_path}/NEEDS_RESEARCH.md` already exists (a prior cycle / session may have dropped it). If it exists, skip the write — sentinel writes are idempotent.
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

   Run Gemini deep research against the prompt at `{research_prompt_path}`,
   then provide the result via any of these upload paths:

   ① Staged .txt (gemini-sprint workflow): save the output as
     `docs/gemini-sprint/results/{feature_id}.txt`. /lazy-batch's Step 0.5
     pre-loop check will auto-dispatch /ingest-research on the next run.

   ② Direct RESEARCH.md drop: write the result directly to RESEARCH.md
     alongside this file. lazy-state.py Step 5 will route to /spec Phase 3
     on the next /lazy-batch run.

   ③ One-off file path: if the file lives outside the repo (e.g.
     ~/Downloads/<file>.txt), run /ingest-research <path> before re-invoking
     /lazy-batch. That skill stages and ingests it into the canonical
     location, then /lazy-batch picks it up via path ②.

   /lazy-batch waits passively while research is in flight — re-invoke when
   ready. The orchestrator does NOT poll the filesystem.

   **Prompt file:** `{research_prompt_path}`
   ```

After the sentinel write, branch on `allow_research_skip`.

### Step 4 — DEFAULT path (`allow_research_skip == false`): immediate halt

This is the new default. The orchestrator halts on the FIRST `needs-research` it encounters — no `--skip-needs-research`, no accumulation, no advancing past the feature.

1. **Read the prompt content.** Open `{spec_path}/RESEARCH_PROMPT.md` and measure its character count. (If the file is somehow missing — the state script should never emit `needs-research` without it — print a defensive warning and fall through to the announcement with `<RESEARCH_PROMPT.md not found at expected path>` as the body.)

2. **Print the halt announcement to chat.** Same shape as Step 1f's per-feature block but for a single feature:

   ```
   ⏸  /lazy-batch paused — {feature_name} needs Gemini research.

   Feature: {feature_id}
   Prompt file: `{spec_path}/RESEARCH_PROMPT.md`

   **Research prompt** (copy this entire block into Gemini Deep Research):

   ```text
   {full RESEARCH_PROMPT.md content, verbatim, including the `## Project context` identity prepend if present}
   ```

   [length: {NNNN} chars — {within | over} Gemini's 24,000-char practical web-UI limit]

   FASTEST RESUME — upload the research in your NEXT MESSAGE in this
   conversation (file attachment, pasted text, or absolute path). I will
   dispatch /ingest-research IN-SESSION (writing the tracked RESEARCH.md +
   RESEARCH_SUMMARY.md into the feature directory) and re-invoke /lazy-batch
   automatically. No manual re-run required. See Step 5: In-Session Resume
   Protocol.

   Alternative upload paths (use these if you prefer to stage and resume
   later):
     ① Save as docs/gemini-sprint/results/{feature_id}.txt. The next
        /lazy-batch run auto-ingests via Step 0.5. NOTE: this path is
        gitignored — a bare .txt stage is non-durable across cloud-container
        reclaim. Use the in-session path above or path ② if cloud durability
        matters.
     ② Drop directly as {spec_path}/RESEARCH.md (skips ingestion;
        lazy-state.py routes to /spec Phase 3 on next run). This file IS
        tracked, so it survives cloud reclaim.
     ③ /ingest-research <path> for a one-off file outside the repo
        (workstation only — cloud cannot see file paths outside the
        container's repo working tree). Then re-run /lazy-batch.

   Re-invoke with /lazy-batch {max_cycles} when ready (only required if you
   did NOT use the in-session resume path above).
   ```

   `{within | over}` is chosen by comparing the measured char count to 24,000 (Gemini's practical web-UI character cap; see `~/.claude/skills/spec/SKILL.md` Phase 2 for source notes). When over, append `(may need manual trimming before paste)` to that line — informational only, do NOT refuse to print.

3. **PushNotification:**

   ```
   PushNotification({ message: "lazy-batch paused — {feature_name} awaiting Gemini research. Upload research and re-invoke /lazy-batch." })
   ```

4. **Append to `cycle_log`:** `{cycle+1, feature_name, "⏸ needs-research (strict halt)", "NEEDS_RESEARCH.md written; prompt printed inline ({NNNN} chars)"}`. DO NOT increment `cycle` — the halt is not a real cycle.

5. **Print the final batch report (Step 2)** with `terminal_reason = "needs-research"` and STOP. Do NOT call the state script again. Do NOT touch `skip_needs_research` — it stays `false`. Do NOT add the feature to `research_pending` — it stays empty. The user's next `/lazy-batch` invocation re-enters via Step 0 → Step 0.5 → Step 1 and either ingests the uploaded research or hits this same halt again.

### Step 4 — OPT-IN path (`allow_research_skip == true`): legacy batch

This restores the pre-default-flip behavior. The orchestrator drops a sentinel, records the feature, flips `skip_needs_research = true`, and returns to Step 1a so the loop advances past this feature. The actual wait happens in Step 1f when `queue-blocked-on-research` fires.

1. Add `feature_id` to `research_pending`. Set `skip_needs_research = true`.
2. Append to `cycle_log`: `{cycle+1, feature_name, "needs-research (sentinel drop, --allow-research-skip)", "NEEDS_RESEARCH.md written; flagging for Step 1f research-wait"}`. **DO NOT increment `cycle`** — this is a no-op state transition, not a real cycle. Sentinel writes here don't count against `max_cycles` either; cost discipline is preserved because the actual work of generating the prompt and running Gemini happens elsewhere.
3. Return to Step 1a. The next `lazy-state.py --skip-needs-research` call will either advance to the next feature in the queue (if any are ready) or return `queue-blocked-on-research` — at which point Step 1f's research-wait fires.

**Special pre-step (both paths):** if the state script returns `sub_skill: "spec"` with args that include "skip to Phase 2", the orchestrator dispatches it normally (this generates the RESEARCH_PROMPT.md). On the next cycle, the state script returns `needs-research` and this Step 4 fires. That's the intended two-cycle handoff for a feature with no research at all.

**Multi-feature accumulation (opt-in path only):** under `--allow-research-skip`, Steps 1a → 4 → 1a (skip) → 4 (next feature) ... can fire repeatedly during the first pass through the queue, each time appending another `feature_id` to `research_pending` and dropping another `NEEDS_RESEARCH.md`. The pass terminates when the state script returns `queue-blocked-on-research` (every remaining feature is research-pending) OR when a ready feature is found (the loop dispatches it normally). Under the default path this cannot happen because Step 4 halts on the first `needs-research`.

---

## Step 5: In-Session Resume Protocol (research uploaded via chat)

**When this protocol fires.** `/lazy-batch` halted (Step 4 default-path or Step 1f) on a research-pending state and printed the "Done" report. The user's NEXT MESSAGE in the same conversation contains research content for one or more pending features. This protocol is the chat-driven counterpart to Step 0.5's filesystem-driven pre-loop ingest — the user's upload IS the resume signal, and `/lazy-batch` re-enters immediately without the user typing `/lazy-batch` again.

**Why this exists.**

- **Eliminates the "rerun the skill" step.** The screenshot-canonical pre-change flow was: halt → user uploads research → assistant says "I'll stage this for the next /lazy-batch run" → user manually types /lazy-batch. The new flow collapses that to: halt → user uploads research → assistant ingests + re-invokes inline.
- **Resolves the cloud-gitignore friction.** `docs/gemini-sprint/results/` is gitignored in AlgoBooth (and other consumers following the gemini-sprint pattern). A bare `.txt` stage in a cloud container does not survive container reclaim — only the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` produced by `/ingest-research` are durable. Dispatching `/ingest-research` IN-SESSION guarantees the durable files exist before the container goes away.
- **HARD CONSTRAINT 7 still holds.** Responding to a single chat message is NOT polling. The orchestrator did not actively wait — it halted cleanly, the user took whatever time they needed (minutes, hours, days), and only when the user's next message arrives does this protocol activate. There is no `Monitor`/`sleep`/loop in the halt path.

**Protocol — what to do on the user's next-message research upload.**

This protocol is read by Claude on the turn AFTER the halt, with the halted `/lazy-batch` skill no longer loaded. The protocol lives here (and is surfaced verbatim in each halt announcement) so that Claude has clear instructions for the resume turn.

1. **Identify the research content and target feature(s).** The user's message may carry research as:
   - A file attachment (Claude Code-uploaded file path under `/root/.claude/uploads/...` or similar).
   - Pasted text — typically inside a fenced code block, but free-form prose is also valid.
   - An absolute file path (e.g. `~/Downloads/<file>.txt`, a phone-synced folder path).
   - Multiple of the above mixed in one message (e.g., one file per feature).

   Correlate each piece of content to a pending feature via the most recently halted invocation's pending list (the `Pending: <feature_ids>` line from Step 1f, or the single `feature_id` from Step 4). When the upload is unambiguously for one feature (only one was pending, or the user named the feature in the message), proceed directly. When multiple features were pending and the correlation is ambiguous, ask ONE `AskUserQuestion` clarifying "which feature does this research belong to?" before continuing — this is the only AskUserQuestion call permitted outside Step 1g, and only at the in-session resume boundary.

2. **Materialize the research into the staging dir.**
   - For file attachments / absolute paths: copy the file to `docs/gemini-sprint/results/<feature_id>.txt` (rename to match the feature_id for clean correlation by `/ingest-research`). Use `Bash` `cp` — do NOT move (the source file may be in a synced folder).
   - For pasted text: `Write` the pasted content to `docs/gemini-sprint/results/<feature_id>.txt` verbatim. Preserve any `## Project context` header or other framing the user provided.
   - For multi-feature uploads: repeat per feature.

3. **Dispatch `/ingest-research` IN-SESSION.** This is exactly the call Step 0.5 makes at the start of a fresh `/lazy-batch` invocation — running it now produces the same tracked outputs (`RESEARCH.md` + `RESEARCH_SUMMARY.md` per feature, `> Draft (pre-Gemini)` trailer cleared in SPEC.md, `queue.json "stub": true` cleared, consumed `.txt` moved to `_consumed/`, per-feature commits) before any container reclaim. Dispatch as a Sonnet subagent (matching `/ingest-research`'s model):

   ```
   Agent({
     description: "in-session resume: ingest uploaded research",
     subagent_type: "general-purpose",
     model: "sonnet",
     prompt: <prompt below>
   })
   ```

   Subagent prompt:

   ```
   The user has just uploaded Gemini deep-research result(s) mid-session,
   resuming a /lazy-batch run that halted on needs-research (or
   queue-blocked-on-research). The research file(s) have already been
   materialized into docs/gemini-sprint/results/ as <feature-id>.txt.

   Working directory: {cwd}
   Staged files (relative to repo root):
     - docs/gemini-sprint/results/{feature_id_1}.txt
     - docs/gemini-sprint/results/{feature_id_2}.txt  (if multiple)
     ...

   Action: Invoke /ingest-research with no arguments. It will scan the
   staging dir, correlate each .txt to a feature, write per-feature
   RESEARCH.md + RESEARCH_SUMMARY.md, drop the > Draft (pre-Gemini) SPEC
   trailer, clear queue.json "stub": true, move consumed .txt to
   _consumed/, and commit per feature.

   Cloud-durability note: docs/gemini-sprint/results/ is gitignored, so the
   staged .txt itself does NOT persist across container reclaim — but the
   RESEARCH.md + RESEARCH_SUMMARY.md files /ingest-research writes into
   docs/features/<.../>/{feature_id}/ ARE tracked and DO persist. That is
   the load-bearing durability guarantee of this resume path.

   After /ingest-research returns:
     1. Report its final summary block.
     2. Confirm which feature_ids now have RESEARCH.md on disk.
     3. Flag any ambiguous correlations (NEEDS_INPUT.md sentinels written) —
        the next /lazy-batch cycle will reach Step 1g (decision-resume mode)
        on them and AskUserQuestion the user.

   You may NOT spawn further subagents.
   ```

4. **Re-invoke `/lazy-batch` automatically.** After the subagent reports success, immediately invoke `/lazy-batch <N>` where `<N>` is the original `max_cycles` from the halted invocation (or the remaining budget if the user prefers — default to the original cap; surface the choice in the resume status line so the user can interject before the next halt). The re-invocation re-enters via Step 0 → Step 0.5 (which is now a no-op because the .txt has been moved to `_consumed/` by `/ingest-research`) → Step 1, and the previously research-pending feature is now ready for `/spec` Phase 3.

5. **Print a brief resume status line BEFORE the re-invocation, so the user sees the bridge:**

   ```
   ▶ In-session resume — ingested research for {comma-separated feature_ids}.
   Re-invoking /lazy-batch {max_cycles}...
   ```

   Then call `/lazy-batch`. No further user action required.

**What the in-session resume protocol does NOT do.**

- It does NOT skip `/ingest-research` (path ② — direct RESEARCH.md drop). Even if the user pastes content that looks like a finished `RESEARCH.md`, the standardized ingestion produces the matching `RESEARCH_SUMMARY.md`, drops the SPEC trailer, and clears the stub flag — those are mechanical chores worth doing every time.
- It does NOT auto-resume on a `needs-input` halt. `needs-input` is no longer a halt (Step 1g resumes inline); the in-session resume protocol is specifically for the research-pending halt classes (`needs-research` and `queue-blocked-on-research`).
- It does NOT preserve cycle accounting across the halt. The new `/lazy-batch <N>` invocation gets a fresh budget — each `/lazy-batch <N>` is an independent bounded run, consistent with the cycle-accounting note in Step 1f.

---

## Notes

- This skill never invokes the work-log MCP tool. Each sub-skill invoked by the cycle subagents logs its own work.
- The orchestrator is single-session by design — there is no persistence layer. State lives in the filesystem sentinels; restart is free.
- Commit policy is delegated to the cycle subagent (which follows the project's `.claude/skill-config/commit-policy.md` or standard pattern). The orchestrator does not commit anything itself except the NEEDS_RESEARCH.md sentinel, which is committed by the next sub-skill cycle's subagent (since the loop has already exited by the time it's written) — under the default strict-halt path, the user's next `/lazy-batch` run is what commits it (the first subagent dispatched against the now-research-ready feature picks up the unstaged sentinel and stages it alongside its own work, or the sentinel becomes stale and is overwritten when ingestion happens).
