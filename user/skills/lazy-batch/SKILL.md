---
name: lazy-batch
description: Autonomous orchestrator for the AlgoBooth (or any queue.json-driven) feature pipeline. Loops on lazy-state.py and spawns Opus subagents per cycle. Distinguishes STUB specs (canonical `> Draft (pre-Gemini)` trailer OR queue.json `"stub": true` → Step 4.5 dispatches /spec as a normal cycle subagent that calls AskUserQuestion freely to shape the baseline) from STRUCTURED specs awaiting research (no stub markers, missing RESEARCH.md → Step 5 halts on needs-research and waits for the user's Gemini upload — single-turn, no conversation). HARD CONSTRAINT 5's no-AskUserQuestion-outside-Step-1g rule binds the orchestrator only, not subagents it dispatches. Halts on needs-research (strict halt by default — the first research-pending feature stops the queue; opt into batched research with --allow-research-skip), queue-blocked-on-research (only reachable under --allow-research-skip), or max-cycles cap. NEEDS_INPUT.md (design decisions) does NOT halt: Step 1g calls AskUserQuestion, dispatches a Sonnet apply-resolution subagent to propagate the choice into SPEC/PHASES, and resumes the loop. BLOCKED.md ALSO does NOT halt by default: Step 1h re-prints the blocker context, calls AskUserQuestion for the resolution path (add a phase / defer to the queue tail / halt-for-manual / custom), dispatches an Opus apply-resolution subagent to enact it (neutralizing BLOCKED.md via rename), and resumes — only the operator-chosen "Halt for manual fix" path stops the run. After every /spec or plan-feature cycle, Step 1d.5 dispatches a dedicated Opus input-audit subagent that independently re-classifies the cycle's decisions and writes NEEDS_INPUT.md if any product-behavior calls were silently baked into SPEC/PHASES — Step 1g then resolves them inline on the next cycle. Research uploaded mid-session via chat (file attachment, pasted text, or absolute path) triggers in-session resume: /ingest-research is dispatched immediately and the loop is re-invoked — no manual re-run required. --adhoc "<task>" enqueues an ad-hoc task at the TOP of the queue before the loop starts (Step 0.45) so the next cycle picks it up first; a brand-new ad-hoc feature begins at /spec Phase 1 and advances autonomously, pausing only for baseline-gating product-behavior decisions via Step 1g.
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip] [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue]
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

1. **The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files** (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `COMPLETED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` / `PHASES.md` status lines when performing the `__mark_complete__` action (which is a documentation-level update by definition, not a source-code edit). `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns; the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. **`BLOCKED.md` may likewise be appended to** (not overwritten) with a `## Resolution` section by Step 1h (blocked-resolution mode) after `AskUserQuestion` returns; the orchestrator then dispatches an Opus subagent to enact the chosen resolution path (e.g. `/add-phase`, queue reorder) and neutralize the sentinel by **rename** (lazy-state.py keys the halt on the `BLOCKED.md` filename). All other `Write`/`Edit` operations — source code, test files, plan files, PHASES.md — require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. **The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool.** Every sub-skill invocation goes through a spawned `Agent` subagent. This keeps the orchestrator's context lean across many cycles. Pseudo-skills (`__*__`) are NOT real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. **The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files.** State inference is exclusively via `lazy-state.py`. Sentinel files MAY be read by the orchestrator to confirm a write or to drive a pseudo-skill action.
4. **One cycle = one subagent dispatch FOR REAL WORK SKILLS.** Do not chain multiple sub-skills inside a single cycle; the state machine drives that progression across cycles. Pseudo-skill cycles (sentinel writes) are not subagent dispatches at all — they are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to decision-resume mode (Step 1g) and blocked-resolution mode (Step 1h) ONLY for the orchestrator itself.** Outside Step 1g and Step 1h, the orchestrator MUST NOT call `AskUserQuestion`. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. Inside Step 1h, the orchestrator MUST `AskUserQuestion` for the resolution path against a `BLOCKED.md` (re-printing its body first), record the choice, dispatch the apply-resolution subagent to enact it, and **continue the loop** — `blocked` no longer halts the orchestrator either (except the operator-chosen "Halt for manual fix" path). (The legacy halt-on-needs-input behavior is gone; the user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation.) **This constraint scopes the orchestrator, not subagents it dispatches.** A `/spec` subagent dispatched at state-machine Step 4.5 (stub-spec detected) is allowed and expected to call `AskUserQuestion` during Phase 1 brainstorming — that's the legitimate design-conversation channel for a SPEC whose baseline doesn't exist yet. The orchestrator dispatches `/spec` exactly the same way it dispatches `/execute-plan` (one Agent call per cycle); whatever the dispatched skill does internally is its own contract. See "Stub specs vs structured-research-pending specs" below for the disambiguation rule.
6. **The orchestrator MUST re-print the load-bearing context to chat BEFORE calling `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print is the load-bearing context. In Step 1g this is the rich `## Decision Context` (never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` — one missing the `## Decision Context` H2 with H3 subsections matching `decisions:` 1:1 — surface the malformation as a quality issue and halt instead, see Step 1g.1). In Step 1h this is the `BLOCKED.md` body verbatim (which has no mandated rich-body schema — a thin body is NOT a malformation halt; re-print whatever is there and note in chat if it is sparse).
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **The `cycle` counter is session-global and monotonic across feature transitions.** It is initialized to 0 in Step 0 *once per `/lazy-batch` invocation* and incremented at the end of every cycle (Step 1c.5 step 5, Step 1e step 5, Step 1g step 7, Step 1h step 7). It MUST NOT be reset when `lazy-state.py` returns a different `feature_id` from one cycle to the next — i.e., when the queue advances from one feature to the next via `__mark_complete__` (or because the prior feature hit a terminal state and a later queue entry became current). Cycle N's status line — `"Cycle N/{max_cycles}: {sub_skill} on {feature_name} → ..."` — always refers to the N-th subagent dispatch in this `/lazy-batch` invocation, regardless of which feature it operated on. A feature transition is **not** a fresh batch; the orchestrator runs ONE cycle log across every feature it touches. The per-cycle status line's `{feature_name}` segment changes across the boundary; the `N` does not.

9. **Dispatch ONLY against the feature `lazy-state.py` returned THIS cycle; never fabricate a feature.** The orchestrator dispatches a cycle subagent against exactly the `feature_id` + `spec_path` from the current cycle's `lazy-state.py` output, verbatim. It MUST NOT invent, infer, or hand-edit a `feature_id`/slug that the state script did not emit. The state script (Step 2) already skips any queue entry whose `spec_dir` does not resolve on disk (emitting a `dangling queue entry` diagnostic) — so a real feature ALWAYS has an on-disk `spec_path` before dispatch. The cycle subagent prompt MUST forbid the subagent from CREATING a feature's `SPEC.md`/`RESEARCH.md`/`queue.json`/`ROADMAP.md` entries from a bare slug: the only sanctioned dir-creating paths are the `--enqueue-adhoc` bootstrap (Step 0.45) and a `/spec` dispatch against an already-seeded directory. If a cycle's `feature_id` does not correspond to an on-disk `spec_path`, that is a bug to surface (halt + report) — NEVER a cue to manufacture the feature. (This guards the observed failure where a hallucinated slug caused a subagent to fabricate an entire feature.)

**Cycle-subagent execution model (recursive dispatch is NOT available — inline edits required).** The cycle subagent dispatched at Step 1d does **not** have the `Agent` tool: recursive sub-subagent dispatch is not supported from inside a dispatched subagent, even on workstation. (This was confirmed empirically — an `/execute-plan` cycle subagent that tried to dispatch Sonnet test/impl agents found the tool unavailable and could only halt.) This forces a load-bearing override of any dispatched skill's sub-subagent contract: skills that nominally fan out to sub-subagents (e.g. `/execute-plan` → Sonnet test-agent + impl-agent, `/retro` → research subagents A–G) MUST be performed INLINE inside the cycle subagent itself using `Edit`/`Write`/`Read` directly. **This override applies only at the cycle-subagent level** — the orchestrator still dispatches exactly one `Agent` per cycle, and the override never expands the orchestrator's `Write`/`Edit` scope (HARD CONSTRAINT 1 still holds; the orchestrator edits only sentinels). This is the same execution model as `/lazy-batch-cloud`; the two orchestrators are coupled per CLAUDE.md. (Unlike cloud, workstation retains the Tauri runtime, MCP HTTP server, audio device, and Windows tooling — only the recursive-dispatch limit and its inline-edit override are shared.)

> **Known limitation — TDD agent-separation is traded away.** Collapsing `/execute-plan`'s test-agent→impl-agent split into ONE inline cycle subagent means the *structural* test-first guarantee (a separate agent writes failing tests before a separate agent implements — the `R-EP-2`/`R-EP-3` separation) is GONE: it cannot be enforced from sub-subagent dispatch evidence when there is no dispatch. This is an intentional tradeoff given the no-recursive-dispatch reality, not a defect. Compensating controls: (1) per-batch **quality gates** (`R-EP-6`) still run and must pass 100%; (2) the **`/retro`** pass audits the landed work; (3) the **MCP-validation** pass (which writes `VALIDATED.md`) gates final completion. The inline cycle subagent SHOULD still write **tests-before-impl within each batch** — read the test expectations, write the failing tests, confirm they fail for the right reason, THEN implement — even though the ordering can't be structurally verified. `/lazy-batch-retro`'s cloud branch already grades `R-EP-2`/`R-EP-3` as `n/a (cloud-override)`; the same grading applies to inline workstation cycles.

`$ARGUMENTS` is tokenized on whitespace. Recognized tokens:

- **Positive integer** → `max_cycles`. If absent, default to `10`. If a non-numeric / `< 1` integer is supplied, refuse with:

  > `/lazy-batch` requires a positive integer max-cycles. Usage: `/lazy-batch <N> [--allow-research-skip]`. Default: 10.

- **`--allow-research-skip`** (optional flag) → sets `allow_research_skip = true`. Default `false`. When set, the orchestrator restores the legacy "batch the research backlog" behavior: `lazy-state.py` is called with `--skip-needs-research`, Step 4 drops a `NEEDS_RESEARCH.md` sentinel for each research-pending feature without halting, and the loop halts on `queue-blocked-on-research` once every remaining feature is research-pending. This flag is for sessions where you have manually verified the remaining queue is independent — i.e., starting work on a downstream feature is safe even though an upstream feature is awaiting research. **Use case is rare.** The DEFAULT (flag absent) is to halt strictly on the FIRST `needs-research` so an ordered queue with dependencies cannot leak work onto unsafe downstream features.

- **`--adhoc`** (optional flag) → sets `adhoc_task` to the remainder of `$ARGUMENTS` after the `--adhoc` token (everything following it, verbatim). If `--adhoc` is the last token with no trailing text, `adhoc_task` is empty and the task is inferred from the conversation (see Step 0.45). When `adhoc_task` is set (flag present), the orchestrator runs **Step 0.45 (Ad-hoc Enqueue)** before the main loop so the referenced work is enqueued at the top of the queue. Off by default (flag absent → no ad-hoc enqueue). Because `--adhoc` consumes the rest of the string, place `<N>` and `--allow-research-skip` BEFORE it.

Unknown tokens are an error:

> `/lazy-batch`: unrecognized argument `{token}`. Usage: `/lazy-batch <N> [--allow-research-skip] [--adhoc "<task>"]`.

Initialize counters and per-session state:
- `cycle = 0` — initialized once per `/lazy-batch` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py` returns a new `feature_id`).
- `max_cycles = <parsed>`
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `cycle_log = []` — each entry: `{cycle, feature, action, subagent_summary}`
- `research_pending = set()` — feature_ids whose `RESEARCH.md` is missing and a `NEEDS_RESEARCH.md` sentinel was dropped this session. Only used when `allow_research_skip == true`. In the default (strict-halt) path this set never accumulates because Step 4 halts on the first feature; it stays empty.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. In the default path this stays `false` for the entire session because Step 4 halts before the loop continues.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched. **`sub_skill_args` is part of the tuple deliberately:** a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3) returns the same `(feature_id, sub_skill, current_step)` on every part but a *different* `sub_skill_args` (the plan-part path), which is real forward progress, not a loop. Omitting `sub_skill_args` made the loop-guard false-trigger on every multi-part plan. Including it lets the guard fire only on a genuine no-progress repeat (identical part re-returned).
- `adhoc_task = <parsed>` — the ad-hoc task text from `--adhoc` (empty string if the flag was present with no text; unset/`None` if the flag was absent). See Step 0.45.

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

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

**Runs once, after Step 0.4 (remote sync) and BEFORE Step 0.5 / the first state probe.** Skipped entirely when the `--adhoc` flag was absent. It runs AFTER the remote ff-sync deliberately: enqueuing mutates `queue.json` in the working tree, so it must happen on the reconciled remote tip, not a stale local snapshot that the Step 0.4 fast-forward would then conflict with.

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

After the enqueue returns, continue to Step 0.5. The first cycle's state probe will return the ad-hoc feature first and route it to `/spec`; its end-of-cycle commit+push carries the bootstrap files (`queue.json`, `ROADMAP.md`, the spec dir + `ADHOC_BRIEF.md`) to origin.

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

- **`blocked`**: see Step 1h (blocked-resolution mode). **Not a terminal halt anymore.** Step 1h re-prints the `BLOCKED.md` body verbatim, runs `AskUserQuestion` for the resolution path (add a phase / defer to queue tail / halt-for-manual / custom), records the choice, dispatches the Opus apply-resolution subagent to enact it (neutralizing `BLOCKED.md` via rename), and returns to Step 1a. The loop continues; do NOT print the final batch report — UNLESS the operator chooses "Halt for manual fix", which keeps `BLOCKED.md` untouched and STOPs (the legacy behavior, now one option among several).
- **`needs-input`**: see Step 1g (decision-resume mode). **Not a terminal state for the orchestrator anymore.** Step 1g re-prints the rich `## Decision Context`, runs `AskUserQuestion`, appends `## Resolution`, dispatches the Sonnet apply-resolution subagent (which edits SPEC.md / PHASES.md and neutralizes the sentinel), and returns to Step 1a. The loop continues; do NOT print the final batch report.
- **`needs-research`**: see Step 4 (research halt). Behavior depends on `allow_research_skip`:
  - **Default (`allow_research_skip == false`)**: Step 4 writes `NEEDS_RESEARCH.md`, prints the inline-prompt halt announcement, PushNotifications, prints the final batch report, and STOPs. The orchestrator does NOT advance past the research-pending feature — this is critical for ordered queues where downstream features depend on upstream work.
  - **Opt-in (`allow_research_skip == true`)**: legacy batching behavior — Step 4 writes `NEEDS_RESEARCH.md`, adds `feature_id` to `research_pending`, **DOES NOT increment cycle**, flips `skip_needs_research = true`, and returns to Step 1a so the next state-script call passes `--skip-needs-research` and either advances to a ready feature or returns `queue-blocked-on-research`.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode). **Only reachable when `allow_research_skip == true`** — in the default path Step 4 halts before this terminal can fire.
- **`needs-spec-input`** / **`queue-missing`**: PushNotification with `notify_message`, print final batch report, STOP. The orchestrator cannot start from nothing.
- **`completion-unverified`**: a feature's SPEC/ROADMAP claims `Complete` but no `COMPLETED.md` receipt exists — it was flipped OUTSIDE the validation gate (a cycle subagent or hand edit bypassing `/retro` + `/mcp-test`). **Halt for human reconciliation** — PushNotification with `notify_message`, print final batch report, STOP. Do NOT auto-flip, auto-reopen, or auto-backfill: the orchestrator cannot tell whether the work was genuinely validated (→ run `lazy-state.py --backfill-receipts` to grandfather it) or skipped the gate (→ reopen `**Status:** In-progress` and let the pipeline re-validate). That judgment is the operator's. (This is the terminal that makes failure mode 1 self-announcing instead of silent.)
- **`all-features-complete`**: PushNotification `"ALL FEATURES COMPLETE — roadmap finished after {cycle} /lazy-batch cycle(s)."`, print final batch report, STOP.
- **`cloud-queue-exhausted`**: Unreachable for `/lazy-batch` (workstation variant); treat as `all-features-complete` defensively.
- **`device-queue-exhausted`**: Reachable only on a **no-real-device** workstation (WSL2/CI, where the audio backend is the HeadlessPumpDriver). Every remaining feature carries `DEFERRED_REQUIRES_DEVICE.md` (real-device-only MCP assertions that cannot be certified here). PushNotification with `notify_message`, print final batch report, STOP. The honest resume is a real-device host: tell the user to set `ALGOBOOTH_REAL_AUDIO_DEVICE=1` (or run on native hardware) and re-run `/lazy-batch` — there the same features RE-OPEN (Step 9 dispatches `/mcp-test` scoped to the deferred scenario IDs as ordinary cycles) and complete. This is the device-axis mirror of `cloud-queue-exhausted`. Note: the **re-open dispatch itself needs no special handling** — on a real-device host the state script emits `sub_skill: mcp-test` for the deferred scenarios, which runs as a normal cycle.

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
- **`__mark_complete__`** — **gated by TWO inline docs-only gates, in order, BEFORE the flip runs.** **Gate 1 — MCP-coverage audit** per the shared `~/.claude/skills/_components/mcp-coverage-audit.md` component (read SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface; grep each `<spec_path>/mcp-tests/*.md` for each decision's id + keywords). If any decision is uncovered, the orchestrator (still inline, sentinel-write only — HARD CONSTRAINT 1 holds) writes `<spec_path>/NEEDS_INPUT.md` per the audit component's schema and commits it with `{feature_id}: mcp-coverage audit surfaced N uncovered locked decision(s) for user confirmation`. **Gate 2 — completion-integrity gate** per the shared `~/.claude/skills/_components/completion-integrity-gate.md` component (runs ONLY after gate 1 returns `clean`): verify phase-coherence (zero non-verification unchecked deliverables in PHASES.md) and that a validation sentinel (`VALIDATED.md`, or `SKIP_MCP_TEST.md`; workstation does NOT accept a bare `DEFERRED_NON_CLOUD.md`) plus `RETRO_DONE.md` exist. If a precondition fails, the orchestrator writes `<spec_path>/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`) describing the gap and commits it. On EITHER gate halting: append `{cycle+1, feature_name, "__mark_complete__ (gate halted)", "<reason> → NEEDS_INPUT.md"}` to `cycle_log`, increment `cycle`, return to Step 1a — the next state-script call returns `terminal_reason: needs-input`, Step 1g surfaces it, and the apply-resolution Sonnet subagent reconciles before the next mark-complete attempt. Only when BOTH gates pass does the orchestrator proceed: **first WRITE `<spec_path>/COMPLETED.md`** (`kind: completed`, `provenance: gated`, folding the validation evidence from VALIDATED.md/MCP_TEST_RESULTS.md into the receipt body — this is the durable proof the feature passed the gate, and `lazy-state.py` Step 2 hard-halts on a `Complete` claim that lacks it), then update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token), delete `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` sentinels (evidence now folded into the receipt; KEEP `COMPLETED.md`/`SKIP_MCP_TEST.md`/`MCP_TEST_RESULTS.md`), set `<spec_path>/SPEC.md` (and PHASES.md top-level) `**Status:**` to `Complete`, then commit per project policy. See the component files for the full algorithms. **Both gates are docs-only** (read SPEC.md / PHASES.md / `mcp-tests/*.md` / sentinels, no Tauri / no MCP server) — they run identically in workstation and cloud. Writing `COMPLETED.md` (a sentinel) and SPEC/ROADMAP status lines is within HARD CONSTRAINT 1's allowance.
- **`__flip_plan_complete_cloud_saturated__`** — emitted only by `lazy-state.py --cloud` at Step 7a when an `In-progress` plan's only unchecked WUs (scoped to the plan's `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. `sub_skill_args` is the absolute plan-file path. Read the plan's YAML frontmatter, edit ONLY the `status:` line in place (`In-progress` → `Complete`) — leave every other field and the markdown body untouched. Derive the plan part number from the plan's `phases:` field (e.g. `phases: [6]` → part 6); fall back to the plan filename's leading `part-N` / `phase-N` token if `phases:` is missing. Stage the plan file and commit per project policy with message `chore(<feature_id>): mark plan part N Complete (cloud-saturated)`. Do NOT touch SPEC.md, ROADMAP.md, or any sentinel — this is a frontmatter-only flip. Editing style: match the conservative single-field rewrite already used by `__write_deferred_non_cloud__` (idempotent if the line is already `Complete`).

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. **Push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** The inline pseudo-skill committed a sentinel / plan-frontmatter change locally; push it now — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This backstops inline cycles the orchestrator owns directly — a `git push` of an already-committed change, NOT a Write/Edit, so HARD CONSTRAINT 1 still holds. "Up to date" is a fine result (a prior cycle's push already carried it).
3. Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · {sub_skill}`, `**Result:**` = the inline outcome, `**Commit:**` = the sentinel/plan commit sha. Nothing else.
4. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` (same uniform post-cycle update as Step 1e — keeps loop-guard accurate across mixed pseudo-skill / real-skill cycles).
5. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

This saves one Opus dispatch per pseudo-skill action. On a typical feature lifecycle (workstation: 1 × `__write_validated_*` + 1 × `__mark_complete__` = 2 dispatches reclaimed; cloud: 1 × `__write_deferred_non_cloud__` minimum) the savings compound across a multi-feature queue pass.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), build a minimal subagent prompt. The prompt instructs the subagent to invoke ONE skill in batch mode, commit, and report — nothing else.

**Loop-guard check (BEFORE composing the prompt):** Compute the current cycle's signature as the tuple `(feature_id, sub_skill, sub_skill_args, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)`, the state script has returned the same tuple two cycles in a row — almost always a sign that a terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`) is missing or that a plan/sentinel write the previous cycle was supposed to perform did not actually land. **`sub_skill_args` MUST be part of the compared tuple** — otherwise a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3, same `feature_id`/`sub_skill`/`current_step` but a different plan-part path in `sub_skill_args`) false-triggers the guard on every part despite genuine forward progress. The orchestrator MUST append the **LOOP DETECTED** block below to the subagent prompt so the subagent diagnoses the missing sentinel rather than producing yet another plan / running the same skill against unchanged state.

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

Sub-subagent dispatch policy (INLINE OVERRIDE — LOAD-BEARING):
  This subagent does NOT have the `Agent` tool — you CANNOT spawn further
  sub-subagents from inside this cycle. Any Agent() call you attempt will fail
  (tool unavailable) and waste the cycle. (Recursive sub-subagent dispatch is
  not supported from inside a dispatched subagent, on workstation as in cloud.)

  Therefore, regardless of what the dispatched skill's SKILL.md says about
  spawning sub-subagents (test-agent, impl-agent, research subagents A–G,
  etc.), you MUST perform that work INLINE in this subagent session using
  Edit / Write / Read directly. The cycle subagent SUPERSEDES the dispatched
  skill's sub-subagent dispatch contract — this is the documented inline
  override, not a hard contract violation. The only prohibition you still
  carry is "no parallel pipeline orchestrators" (do NOT invoke another /lazy
  or /lazy-batch).

  Per-skill inline overrides (override the SKILL.md dispatch contract):
    • /execute-plan — IGNORE Step 3's "Execution Model Enforcement". Do NOT
      attempt Agent({model: "sonnet"}) test-agent / impl-agent dispatches.
      Perform each batch's test additions and implementation edits INLINE
      with Edit / Write / Read on source/test files directly
      (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files included).
      Follow the rest of /execute-plan as written (batch ordering, commits,
      plan-file checkbox flips, sentinel emissions). Zero sub-subagent
      dispatches in an /execute-plan cycle is the EXPECTED state — NOT a
      contract violation.
      SKIP THE GROUND-TRUTH RE-RUN: subagent-review.md Step 1.5 exists to
      detect a *separate* untrusted subagent falsifying its report by
      re-running every command (git status / wc -l / grep / test runner) and
      diffing. In this inline path YOU wrote both the tests and the
      implementation in this same session — there is no separate subagent
      report to police, so that mechanical re-run is pure redundant work. Do
      NOT re-run-and-diff your own commands. Still perform the SUBSTANTIVE
      correctness review (spec alignment, deliverable coverage, logic/edge-case
      check, propagation check per subagent-review.md Step 2.5) and still run
      the quality gates — only the falsification-detection re-run is dropped.
      KNOWN LIMITATION: collapsing the test-agent/impl-agent split into one
      inline session trades away the STRUCTURAL test-first guarantee. You MUST
      still preserve test-first DISCIPLINE within each batch: write the failing
      tests FIRST (per the plan's test expectations), confirm they fail for the
      right reason, THEN implement until they pass.
    • /retro — IGNORE Step 3's parallel research-subagent fanout (A–G). Do the
      research INLINE: read each input serially, synthesize, and write the
      retro plan + RETRO_DONE.md directly. The deliverable is identical; only
      the parallelism is dropped.
    • /mcp-test — perform the Step 5 test work INLINE (read the MCP usage
      guide, run the MCP HTTP tools yourself, analyze the session logs) rather
      than dispatching a Sonnet test subagent. Workstation retains the Tauri
      runtime + MCP HTTP server, so the runtime work itself is unchanged — only
      the sub-subagent dispatch is replaced with inline execution.
    • retro-feature — composed orchestrator; same override — perform all
      internal work inline rather than dispatching nested sub-subagents.
    • plan-feature — composed orchestrator; runs /spec-phases THEN /write-plan
      via the Skill tool (in-context, NOT Agent dispatch). Both sub-skills are
      docs-only (PHASES.md + plan files) and orchestrator-only, so no recursive
      Agent dispatch is needed — invoke /plan-feature once and let it run its
      two sub-skills in your context. This is what lazy-state.py emits at
      Step 6 (replacing the separate /spec-phases dispatch).
    • /spec, /spec-phases, /write-plan, /add-phase, /ingest-research —
      already orchestrator-only; no change.

  If you find yourself about to write Agent({...}) inside this cycle, STOP and
  replace it with the equivalent Edit / Write / Read sequence. Do NOT write
  BLOCKED.md because of the recursive-dispatch limit — that limit is exactly
  what this override exists to handle.

  The dispatched skill's own SKILL.md remains authoritative for everything
  else: batch ordering, sentinel emissions, commit policy, file-shape
  invariants, plan-checkbox semantics. Re-read it from disk if any
  non-dispatch detail is unclear — do NOT rely on memory.

Source/test file edits:
  - All paths: perform Edit / Write on source/test files
    (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files) DIRECTLY in this
    subagent session. The inline override above removes the /execute-plan
    sub-subagent dispatch requirement and replaces it with inline edits.

No premature Complete (PIPELINE-GATE HONESTY — HARD REQUIREMENT):
  - You MUST NOT set the top-level `**Status:**` of SPEC.md or PHASES.md to
    `Complete`. That flip is reserved EXCLUSIVELY for the orchestrator's
    `__mark_complete__` pseudo-skill, which runs ONLY after the feature has
    passed the full downstream tail: /retro (writes RETRO_DONE.md) → /mcp-test
    (writes VALIDATED.md or a justified SKIP_MCP_TEST.md) → the __mark_complete__
    MCP-coverage audit. If a phase-implementation cycle flips SPEC/PHASES
    `**Status:** Complete` itself, the feature has NO COMPLETED.md receipt, so
    lazy-state.py Step 2 now HARD-HALTS on `completion-unverified` instead of
    advancing — your rogue flip does not skip the tail, it stops the whole loop
    until a human reconciles. (Previously this silently skipped /retro +
    /mcp-test + the coverage audit; the receipt gate is the mechanism that makes
    this guard self-enforcing rather than honor-system.) Do NOT write a
    COMPLETED.md yourself either — only the orchestrator's __mark_complete__
    integrity gate may, after the validation tail passes.
  - What you MAY flip when an /execute-plan part finishes: the PLAN-PART
    frontmatter `status:` (Ready → In-progress → Complete) and the per-PHASE
    checkboxes/`Status:` line for the phase you just implemented (e.g. Phase 3
    deliverables → checked, that phase → Complete). When the last phase's work
    lands, set the top-level PHASES `**Status:**` to `In-progress` (NOT
    `Complete`) — implementation is done but validation is still pending. The
    feature reaches `Complete` only through __mark_complete__.
  - If you believe the feature is genuinely finished and validated, STILL do not
    flip the top-level Status — let the state machine route to /retro and
    /mcp-test next. Those passes are cheap insurance, and __mark_complete__'s
    coverage audit is the single authorized place the SPEC flips to Complete.

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
     CONFIRM you performed the test + implementation edits INLINE (zero Agent()
     calls) — this is the inline-override audit signal, and note for each batch
     that you wrote the failing tests before implementing (test-first
     discipline).
```

**LOOP DETECTED block (append only when the loop-guard fires):**

```
⚠️  LOOP DETECTED: The state script returned this exact
(feature_id={feature_id}, sub_skill={sub_skill}, sub_skill_args={sub_skill_args}, current_step={current_step})
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

### 1d.5. Post-cycle input audit (Opus — runs only on `/spec` and `plan-feature` cycles)

**Why this step exists.** The dispatched cycle subagent that ran `/spec` (or `plan-feature`, which composes `/spec-phases` + `/write-plan`) self-classifies its own decisions as product-behavior vs mechanical-internal and self-decides whether to halt via `NEEDS_INPUT.md`. In practice that self-classification gets short-shrift — the subagent juggles competing pressures (integrate research, draft updates, finalize SPEC, produce summary) and the classification step is biased toward "make progress". Across ~75 observed lazy-batch cycles, zero `NEEDS_INPUT.md` sentinels fired from `/spec`'s self-audit despite multiple cycles having surfaceable product-behavior calls. This step is the independent Opus second-opinion focused on one question: did any product-behavior decision get baked into SPEC.md / PHASES.md without surfacing to the user?

**Skip when ANY of:**
- `sub_skill` is NOT in {`/spec`, `plan-feature`}. (Most cycles — `/execute-plan`, `/retro`, `/mcp-test`, pseudo-skills — skip the audit; they don't author SPEC content.)
- The cycle was a pseudo-skill (Step 1c.5 already ran inline; no `/spec`-shaped decisions to audit).
- The cycle subagent already wrote `NEEDS_INPUT.md` for this feature this cycle (the cycle correctly surfaced; re-auditing would double-fire). Probe: `test -f {spec_path}/NEEDS_INPUT.md` AND `git diff HEAD~1 --name-only` lists it.
- The cycle subagent returned a hard failure with no SPEC/PHASES delta (nothing to audit).

**Inputs to gather before dispatch:**
1. `spec_path` from this cycle's state-script result.
2. `feature_id`, `feature_name`, `sub_skill` from the same result.
3. The cycle subagent's one-paragraph summary, including its **Decision-Classification Ledger** section (mandatory under `/spec --batch` — see `~/.claude/skills/spec/SKILL.md`). If the ledger is missing or malformed, capture that fact for the audit prompt; do not synthesize one.
4. The SPEC/PHASES delta: `git diff HEAD~1 -- {spec_path}/SPEC.md {spec_path}/PHASES.md` (or against the cycle's commit sha if known).

**Dispatch:**

```
Agent({
  description: "lazy-batch cycle {cycle+1}: input-audit for {feature_name}",
  subagent_type: "general-purpose",
  model: "opus",
  prompt: <audit prompt below>
})
```

**Audit prompt:**

```
You are the lazy-batch INPUT-AUDIT subagent — an independent Opus second-opinion
that runs after a /spec or plan-feature cycle. Your sole job is to verify that
no product-behavior decision was silently baked into SPEC.md / PHASES.md
without surfacing to the user via NEEDS_INPUT.md.

Scope (HARD): you MUST NOT edit source code, tests, plan files, or any file
except {spec_path}/NEEDS_INPUT.md. You MAY commit that sentinel and push the
work branch. You MUST NOT call the Skill tool, MUST NOT dispatch further
subagents, and MUST NOT modify SPEC.md / PHASES.md (the cycle subagent's
content stands until the user resolves the surfaced decisions via Step 1g).

Inputs:
  - Feature: {feature_name} ({feature_id})
  - Spec path: {spec_path}
  - Sub-skill that just ran: {sub_skill}
  - Cycle commit (for diff): {cycle_commit_sha or "HEAD~1"}
  - Cycle subagent's return summary, INCLUDING its Decision-Classification
    Ledger section (or a note that the ledger was missing/malformed):
    ---
    {cycle_summary}
    ---

Bias: AGGRESSIVE — when in doubt, surface. Any decision that even *touches* a
user-visible surface is `product-behavior` unless it has an unambiguous single
defensible answer that the user could not reasonably want to override. The
canonical product-behavior smells checklist lives in
~/.claude/skills/spec/SKILL.md ("Product-behavior smells — concrete
checklist"); read it and apply each smell to every decision visible in this
cycle's diff. Examples that ALWAYS qualify as product-behavior regardless of
recommendation strength:
  - v1 default values the user sees on first run.
  - "Ship continuous vs quantized" / "configurable vs fixed" toggles.
  - Scope-of-v1 calls (ship subfeature now vs defer).
  - Workflow shape and surface placement.
  - Copy / labels / names visible to the user.
  - Research-surfaced multi-option calls at the user-visible level.

Audit algorithm:
1. Read SPEC.md (and RESEARCH.md if it exists) from {spec_path}.
2. Read the diff: `git show {cycle_commit_sha} -- {spec_path}/SPEC.md
   {spec_path}/PHASES.md` (or `git diff HEAD~1 -- ...` if no sha was given).
3. Cross-reference the cycle subagent's Decision-Classification Ledger against
   the diff:
   a. For each ledger row: independently re-classify per the smells checklist.
      Flag any row classified `mechanical-internal` by the cycle subagent that
      your independent classification says is `product-behavior`.
   b. For each user-visible change in the diff NOT covered by a ledger row:
      treat it as a hidden decision the cycle subagent failed to disclose;
      classify and flag accordingly.
   c. If the ledger was missing or malformed entirely, perform a diff-only
      audit: identify every user-visible change in the diff, classify each.
4. Compile the list of `product-behavior` decisions that were baked in without
   surfacing (i.e. `Surfaced via: auto-accept` rather than `NEEDS_INPUT.md`).
   These are the misclassifications you must surface.
5. If the list is EMPTY: return a one-line summary
   `clean — no product-behavior decisions baked in; cycle subagent's
   auto-accepts were all mechanical-internal`. Write nothing. STOP.
6. If the list is NON-EMPTY:
   a. Cap at the top 4 by user-visibility impact (the sentinel schema's
      `AskUserQuestion` 4-question cap). Note the rest in the body as
      "## Open Questions" for a follow-up audit cycle.
   b. Write {spec_path}/NEEDS_INPUT.md per the canonical schema in
      ~/.claude/skills/_components/sentinel-frontmatter.md:
        ---
        kind: needs-input
        feature_id: {feature_id}
        written_by: lazy-batch-input-audit
        decisions:
          - <one-line decision 1>
          - ...
        date: <today>
        next_skill: spec
        ---
      Body MUST follow the rich-body convention (## Decision Context H2,
      one H3 per decision). For EACH surfaced decision:
        - **Problem:** cite the exact SPEC.md section / line where it was
          baked in, and (if Phase 3) the RESEARCH.md finding that frames the
          tradeoff.
        - **Options:** list (at minimum) the baked-in answer labeled
          "Auto-accepted by cycle subagent: <option>" PLUS at least 2
          alternatives the user might reasonably prefer (drawn from research
          where possible). Include concrete tradeoffs per option.
        - **Recommendation:** <strongest option, often the baked-in one if
          it's defensible> — <one-sentence justification>. The user can
          confirm the baked-in answer in one click via AskUserQuestion.
   c. Commit the sentinel with a clear message:
        git add {spec_path}/NEEDS_INPUT.md
        git commit -m "{feature_id}: input-audit surfaced N product-behavior
        decision(s) for user confirmation"
      Push the work branch (`git push origin $(git rev-parse --abbrev-ref
      HEAD)`, 4× backoff retry on network error; never main, never force).
7. Return a one-paragraph summary (≤ 8 lines) covering:
   - Decisions reviewed (count) and how many you classified as
     product-behavior.
   - Whether the cycle subagent's Decision-Classification Ledger was present
     and well-formed; if missing/malformed, flag the contract violation by
     skill name.
   - The one-line titles of the surfaced decisions.
   - Whether you wrote NEEDS_INPUT.md (and the commit sha if so).

Do NOT halt the loop. The NEEDS_INPUT.md sentinel you write is picked up by
lazy-state.py on the next cycle and resolved via Step 1g (decision-resume
mode) inline — no orchestrator-side halt fires.
```

**After the audit subagent returns:**
1. If it wrote `NEEDS_INPUT.md`, append a `**Audit:**` bullet to the per-cycle output block (Step 3): `**Audit:** {N} product-behavior decision(s) surfaced` (one line, no further prose).
2. If it returned "clean — no product-behavior decisions baked in", append no audit bullet — the audit is silent on clean cycles to keep cycle output lean.
3. If it flagged a missing/malformed Decision-Classification Ledger, append a `**Note:**` bullet: `**Note:** /spec --batch cycle returned no Decision-Classification Ledger (contract violation)`. This surfaces the contract issue without halting.
4. Audit costs are NOT separate cycles — the audit shares the cycle's slot in `cycle_log` and does not increment the cycle counter. The audit subagent is bounded (read SPEC/RESEARCH/diff, classify, optionally write one sentinel), so its context footprint is small.
5. Proceed to Step 1e. The next state-script call at Step 1a will surface `needs-input` if the audit wrote `NEEDS_INPUT.md`, and Step 1g handles resolution inline (no loop halt).

### 1e. Record cycle outcome and loop

After the subagent returns:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, subagent's one-paragraph summary}`.
2. Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · {sub_skill}`, `**Result:**` = the first line of the subagent summary, `**Commit:**` = the cycle's commit sha (or `—`). For an `/execute-plan` cycle, add the `**Inline:**` bullet confirming the subagent performed the edits inline (zero Agent() calls) with test-first discipline per batch — the inline-override audit signal. No other prose.
3. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` so the next cycle's Step 1d loop-guard can compare against this cycle.
4. **Post-cycle push backstop (guardrail C — mirrored from `/lazy-batch-cloud`).** Verify the work branch is pushed — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). The cycle subagent's Step 1d already commits and pushes to the current branch at end-of-cycle, so this normally reports "up to date" — it is the backstop for any cycle that did not push itself. A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 still holds.
5. Increment `cycle`. Return to Step 1a. **Cycle counter is monotonic across feature transitions (HARD CONSTRAINT 8).** If the next state-script call returns a different `feature_id` — e.g. because this cycle's `__mark_complete__` finished the prior feature, or the queue rolled forward to the next ready feature for any other reason — the cycle counter continues counting from the value just produced here. Do NOT reset to 0 or 1 on the boundary; cycle N+1 is always the next cycle regardless of which feature it lands on.

**Note:** Step 1c.5 (pseudo-skill inline handling) MUST also update `prev_cycle_signature` to the cycle's `(feature_id, sub_skill, sub_skill_args, current_step)` tuple before returning to Step 1a. Otherwise a real-skill cycle following a pseudo-skill cycle would compare against a stale signature and miss loops that span both kinds. The orchestrator should treat the prev-signature update as a uniform post-cycle action regardless of whether the cycle dispatched a subagent or ran inline. The same applies to the cycle-counter increment: it is a uniform post-cycle action that happens once per cycle (real, pseudo, or decision-resume) and never resets.

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
        terminal_reason=needs-input on the next cycle. You MUST RENAME the file
        (`git mv {spec_path}/NEEDS_INPUT.md {spec_path}/NEEDS_INPUT_RESOLVED.md`,
        preserving the audit trail at the new path). If NEEDS_INPUT_RESOLVED.md
        already exists (a prior resolved decision on this feature), use a
        decision-specific suffix, e.g. NEEDS_INPUT_RESOLVED_<slug>.md.
        DO NOT merely edit the frontmatter `kind:` field — lazy-state.py keys
        the needs-input halt on the FILENAME `NEEDS_INPUT.md`, so a `kind:` flip
        leaves the file named NEEDS_INPUT.md and the halt FIRES AGAIN next cycle
        (this is a real bug that was hit in practice; it also leaves a
        `sentinel-kind-matches-filename` docs-consistency violation). The
        Decision Context + Resolution body MUST be preserved verbatim under the
        new filename.
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
   - Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · needs-input`, `**Result:**` = "decision(s) resolved + applied — {first-line-of-subagent-summary}". No other prose.
   - Update `prev_cycle_signature = (feature_id, "__apply_needs_input__", sub_skill_args, current_step)`. The synthetic sub_skill token distinguishes this from any real-skill cycle so the Step 1d loop-guard treats it as its own kind of cycle.
   - Increment `cycle`. Return to Step 1a. **DO NOT halt, DO NOT print the final batch report.** The next state-script call should see the neutralized sentinel and route to the natural next step for the feature (typically resuming the skill that wrote NEEDS_INPUT.md — `/write-plan` or `/execute-plan` — now that the design ambiguity is resolved).

This eliminates the legacy "answer → halt → manual SPEC/PHASES edit → re-run /lazy-batch" friction. The user's autonomy is preserved in step 3 (the choice itself); steps 6–7 are bounded mechanical work delegated to Sonnet so the orchestrator's Opus context stays lean.

---

### 1h. Blocked-resolution mode (`terminal_reason == "blocked"`)

Triggered when `lazy-state.py` reports `blocked` — a cycle subagent (or a hand edit) wrote `BLOCKED.md` because it hit a genuine blocker it could not resolve autonomously (a missing upstream surface, an ambiguous failure, a real bug needing a planning decision). **`blocked` is no longer a terminal halt.** Modeled on Step 1g: the orchestrator surfaces the blocker to the operator via `AskUserQuestion`, captures the chosen resolution path, records it, dispatches an Opus apply-resolution subagent to ENACT that path (neutralizing `BLOCKED.md`), and **continues the loop**. The sole exception is the explicit **Halt for manual fix** choice, which preserves the legacy stop-for-human behavior.

This replaces the old **zero-context halt** (a bare `PushNotification` + STOP that handed the operator a one-line `notify_message` and nothing actionable). The operator now sees the full blocker context in chat and directs how the pipeline proceeds.

**Algorithm:**

1. **Read the sentinel.** `{spec_path}/BLOCKED.md`. Parse the YAML frontmatter (`kind`, `feature_id`, `phase`, `blocked_at`, `retry_count`, and `blocker_kind` if present) and read the markdown body. Unlike `NEEDS_INPUT.md`, `BLOCKED.md` has no mandated rich-body schema — a thin body is NOT a malformation halt; proceed, noting in chat if the blocker context is sparse.

2. **Re-print the blocker context to chat VERBATIM** (HARD CONSTRAINT 6 applies to Step 1h too — the load-bearing context BEFORE the truncated `AskUserQuestion` UI; this is the antidote to the old zero-context halt):

   ```
   🚧 /lazy-batch — Blocked (loop resumes after you choose a resolution path)

   Feature: {feature_name} ({feature_id})
   Phase:   {phase}   ·   retry_count: {retry_count}   ·   blocker_kind: {blocker_kind or "—"}
   File:    {spec_path}/BLOCKED.md

   ─── BLOCKED.md body (verbatim) ──────────────────────────────────────────

   {entire markdown body — blocker description, evidence, and any recovery
   suggestion the cycle subagent recorded — copy/paste as-is, no summarization.}

   ─────────────────────────────────────────────────────────────────────────

   Choose how the pipeline should proceed. After you answer, I dispatch an Opus
   subagent to enact your choice (and neutralize BLOCKED.md), then resume the
   loop — unless you choose "Halt for manual fix".
   ```

3. **Call `AskUserQuestion` with ONE question — the resolution path.** `header`: "Resolution". Where the `BLOCKED.md` body names a concrete recovery (e.g. "add an `/add-phase` Phase N for X"), adapt the matching option's `description` to reference it so the recommended path is specific to this blocker. The archetype options:

   - **Add a phase to resolve the blocker** — dispatch `/add-phase` against this feature with the blocker as the new phase's motivation, then neutralize `BLOCKED.md`. The pipeline re-plans → implements → re-validates the feature. *Recommended when the blocker is missing / under-scoped work (the common case — e.g. a missing MCP surface a validation step needs).*
   - **Defer this feature; continue the rest of the queue** — move this feature's `queue.json` entry to the END of the queue (`BLOCKED.md` kept in place) so the next actionable feature becomes current. The blocked feature resurfaces only after the rest of the queue is worked.
   - **Halt for manual fix** — keep `BLOCKED.md` untouched, `PushNotification`, print the final batch report, STOP. The legacy escape hatch for blockers you want to handle by hand.

   The auto-provided **Other** lets the operator type a custom directive, enacted verbatim by the apply subagent. Capture the choice + any free-text note. (`multiSelect: false` — the paths are mutually exclusive.)

4. **If the choice is "Halt for manual fix":** do NOT modify `BLOCKED.md`. Append `{cycle+1, feature_name, "🛑 blocked (operator chose manual halt)", "{phase}"}` to `cycle_log`, `PushNotification` with `notify_message`, print the final batch report (Step 2), and **STOP**. This is the ONLY Step 1h path that halts.

5. **Otherwise, append a `## Resolution` section to `BLOCKED.md`** recording the chosen path, the operator's note (if any), and a timestamp — same `Edit`-append pattern as Step 1g step 4 (HARD CONSTRAINT 1 permits appending `## Resolution` to `BLOCKED.md`):

   ```markdown

   ## Resolution

   *Recorded on <YYYY-MM-DD HH:MM:SS UTC>.*

   **Chosen path:** <option label>
   **Notes:** <operator's free-text note, or empty>
   ```

   Commit `BLOCKED.md` with message `docs({feature_id}): record blocker resolution path`. Do NOT push (consistent with other orchestrator-inline commits; the apply subagent pushes).

6. **Dispatch the Opus apply-resolution subagent to ENACT the chosen path.** Prompt:

   ```
   You are enacting an operator-chosen resolution for a BLOCKED feature in the
   autonomous pipeline, then neutralizing the blocker so the loop can resume.

   Feature: {feature_name} ({feature_id})
   Working directory: {cwd}
   Sentinel:          {spec_path}/BLOCKED.md  (read its body + the appended
                      `## Resolution` for the chosen path + operator notes)

   CHOSEN PATH: {option label}   NOTES: {operator note or "—"}

   Enact EXACTLY the chosen path:

   • "Add a phase to resolve the blocker":
       Invoke the /add-phase skill (via the Skill tool — you MAY use it; you may
       NOT use Agent) against {feature_id}, authoring a new phase whose scope is
       the blocker described in BLOCKED.md (and any recovery the cycle subagent
       suggested). /add-phase appends the phase to PHASES.md (In-progress, with
       unchecked deliverables) per its own contract. Then NEUTRALIZE BLOCKED.md
       (see below). The next loop cycle's lazy-state.py routes the feature to
       plan/implement the new phase.

   • "Defer this feature; continue the rest of the queue":
       Edit docs/features/queue.json: move this feature's entry to the END of the
       `queue` array (preserve valid JSON; the queue.topo-order rule may emit an
       advisory warning for a deferred hard-upstream — acceptable for an
       operator-chosen defer). LEAVE BLOCKED.md IN PLACE (the feature stays
       blocked; it simply no longer heads the queue). Do NOT neutralize.

   • "Other" (custom directive): enact the operator's NOTES as faithfully as you
     can with Edit/Write/Read/Bash and (if a skill fits) the Skill tool. If the
     directive resolves the blocker, neutralize BLOCKED.md; if it only changes
     course, follow the note's intent and say so in your summary.

   NEUTRALIZING BLOCKED.md (for every path EXCEPT "Defer"): lazy-state.py keys the
   `blocked` halt on the FILENAME `BLOCKED.md` (NOT a frontmatter field), so a
   `kind:` edit does NOT clear the halt. RENAME the file:
   `git mv {spec_path}/BLOCKED.md {spec_path}/BLOCKED_RESOLVED_<YYYY-MM-DD>.md`
   (preserves the audit trail including the `## Resolution`). If that name already
   exists, add a short disambiguating suffix. NEVER just flip a frontmatter field
   (this is a real bug that was hit in practice — the rename is mandatory).

   Then commit per .claude/skill-config/commit-policy.md (or the standard
   pattern); message `docs({feature_id}): enact blocker resolution (<path>)`.
   Push the work branch (never main-force; standard push).

   Report a one-paragraph summary (≤ 8 lines): what you enacted (the new phase
   title / the queue move / the custom edits), whether BLOCKED.md was neutralized
   (and to what filename) or deliberately kept, files touched, and the commit hash.

   You may NOT spawn further subagents (no Agent). You MAY use the Skill tool for
   /add-phase, and Edit/Write/Read/Bash for everything else.
   ```

   Dispatch:

   ```
   Agent({
     description: "lazy-batch blocked-resolve: {feature_name}",
     subagent_type: "general-purpose",
     model: "opus",
     prompt: <the prompt above>
   })
   ```

7. **Record and continue the loop.**
   - Append to `cycle_log`: `{cycle+1, feature_name, "▶ blocked (resolved + enacted: <path>)", "<one-line subagent summary>"}`.
   - Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · blocked`, `**Result:**` = "<path> enacted — {first line of subagent summary}". No other prose.
   - Update `prev_cycle_signature = (feature_id, "__resolve_blocked__", sub_skill_args, current_step)`. The synthetic sub_skill token distinguishes a blocked-resolution cycle from any real-skill cycle for the Step 1d loop-guard.
   - Increment `cycle`. Return to Step 1a. **DO NOT halt, DO NOT print the final batch report** (except the "Halt for manual fix" path at step 4). The next state-script call sees `BLOCKED.md` neutralized (Add-a-phase / Other) and routes the feature onward, or — for "Defer" — selects the next actionable feature now that the blocked one sits at the queue tail.

**Re-prompt note (Defer path).** If "Defer" is chosen and the blocked feature is the ONLY remaining actionable entry, the next probe returns `blocked` for it again and Step 1h re-prompts immediately — that is correct (there is nothing else to work). The operator breaks the cycle by choosing Add-a-phase, Other, or Halt. `max_cycles` bounds it regardless.

This eliminates the legacy zero-context blocked halt: the operator gets the full blocker context in chat and directs the pipeline (add a phase / defer / hand off), and the orchestrator enacts the choice and keeps going.

---

## Step 1.5: Forward-Progress Verification (informally "Step 2.5"; runs after loop exit, before the Step 2 batch report)

After the cycle loop exits with any terminal reason **other than** `blocked`, `needs-input`, or `queue-missing`, run a final read-only state probe to confirm the loop actually advanced the queue. This is cheap insurance against the silent-no-op failure mode where a cycle subagent reports success but does not write the sentinel that would let the next invocation move on.

Skip this step entirely when `terminal_reason in {"blocked", "needs-input", "queue-missing"}` — those halts describe states the orchestrator already cannot resolve, and the user will be looking at the sentinel / config directly. (Note: a `blocked` loop-exit now occurs ONLY when the operator chose "Halt for manual fix" in Step 1h — every other Step 1h path resumes the loop, so it never reaches loop-exit as `blocked`.) For every other exit (including `all-features-complete`, `needs-research`, `queue-blocked-on-research`, `cloud-queue-exhausted`, and max-cycles), execute the probe.

**Algorithm:**

1. Run the state script ONE more time, identically to Step 1a:

   ```bash
   python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]
   ```

   Pass `--skip-needs-research` under the same double-gate condition as Step 1a (`allow_research_skip == true AND skip_needs_research == true`). Parse the JSON.

2. Compute the probe tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the new output (any field may be `null` for terminal exits — that is fine, the comparison still works).

3. Compare against `prev_cycle_signature` (the signature of the last real-skill or pseudo-skill cycle run during THIS invocation). Three cases:

   **(a) Forward-progress confirmed.** Probe tuple differs from `prev_cycle_signature`, OR the probe returned a terminal reason. Print one line at the top of the Step 2 final batch report:

   ```
   ✅ Next /lazy-batch invocation will: <human-readable summary>
   ```

   Construct `<human-readable summary>` from the probe output:
     - Terminal reason set → `"halt on {terminal_reason} ({notify_message})"`.
     - Pseudo-skill (`__*__`) → `"perform {sub_skill} on {feature_name} ({current_step})"`.
     - Real skill → `"dispatch /{sub_skill} on {feature_name} ({current_step})"`.

   **(b) Forward-progress WARNING.** Probe tuple equals `prev_cycle_signature` (same `feature_id`, same `sub_skill`, same `sub_skill_args`, same `current_step`, no terminal reason). This means the next `/lazy-batch` invocation would re-issue the cycle this run just finished — the queue did not advance. Print this block at the top of the Step 2 final batch report:

   ```
   ⚠ FORWARD-PROGRESS WARNING: the next /lazy-batch invocation will return
   the same state as the cycle we just finished
   (feature_id={feature_id}, sub_skill={sub_skill},
   sub_skill_args={sub_skill_args}, current_step={current_step}).

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
  - If terminal_reason is "blocked": this is reached ONLY when the operator chose "Halt for manual fix" in Step 1h (every other Step 1h path resumes the loop). Resolve {spec_path}/BLOCKED.md by hand, then re-run `/lazy-batch {max_cycles}` — the next run re-enters Step 1h if BLOCKED.md is still present.
  - If terminal_reason is "needs-research" (DEFAULT path, strict halt): the fastest resume path is to upload Gemini research in your NEXT MESSAGE in this conversation — the in-session resume protocol (Step 5) will dispatch /ingest-research and re-invoke /lazy-batch automatically. Otherwise, stage/drop the research per Step 4's halt announcement and re-run `/lazy-batch {max_cycles}` manually.
  - If terminal_reason is "queue-blocked-on-research" (only reachable under --allow-research-skip): same as needs-research — upload research in chat for fastest resume, or use one of the staged/drop paths and re-run `/lazy-batch {max_cycles} [--allow-research-skip]`.
  - (needs-input is no longer a terminal state — Step 1g resolves and resumes within the same /lazy-batch invocation.)
  - If max-cycles: re-run `/lazy-batch {max_cycles}` from a fresh session
```

STOP.

---

## Step 3: Cycle Output Discipline (lean · consistent · scannable)

Every cycle — real-skill (Step 1e), inline pseudo-skill (Step 1c.5), decision-resume (Step 1g), or blocked-resolution (Step 1h) — emits **EXACTLY ONE update block** in this shape, and nothing else:

```
### Cycle {N}/{max_cycles} · {feature_name} · {sub_skill}
- **Result:** {one-line outcome}
- **Commit:** {short-sha | "—"}
```

`{sub_skill}` is the real skill name, the `__pseudo_skill__` token, or `needs-input` for a decision-resume cycle. `**Result:**` is the first line of the subagent summary, the inline action's effect, or the resolved decision — ONE line. `**Commit:**` is the cycle's commit sha (or `—` when nothing was committed).

**Rules (so many cycles stay scannable on a phone):**

- **ONE block per cycle.** The heading + bullets ARE the cycle's entire chat footprint. Do not precede or follow it with prose.
- **No dispatch narration.** Do NOT write "dispatching the subagent", "running in the background", "waiting on the completion notification before advancing", or similar. The loop mechanics are a fixed contract, not per-cycle news.
- **No commit-strategy narration.** Do NOT explain commit ownership or in-flight races ("these uncommitted changes are the agent's in-flight work", "committing now would race the agent", "I'll let it own the commits"). Commits are owned by the cycle subagent (real skills) or by the inline action (pseudo-skills) — a fixed rule, never re-explained per cycle.
- **Ignore commit prompts silently.** If a Stop hook or any other prompt asks whether to commit between cycles, do NOT answer with prose. The commit policy is already fixed; proceed to the next state probe without narration.
- **At most 2–3 bullets, one line each.** Add a third bullet ONLY for a genuinely notable signal — e.g. `**Inline:** edits performed inline, test-first per batch` on an `/execute-plan` cycle (the inline-override audit signal), `**Audit:** {N} product-behavior decision(s) surfaced` on a `/spec` or `plan-feature` cycle whose Step 1d.5 input-audit fired, or `**Note:** {flag}` for an issue worth surfacing.
- **Halt/terminal announcements are exempt.** The Step 4 research halt, Step 1f research-wait, Step 1g malformed-sentinel halt, the Step 1h blocked-resolution prompt (rich blocker re-print + AskUserQuestion) and its "Halt for manual fix" stop, and the Step 2 final report keep their own templated shapes — those are functional (copy-paste prompts, decision context, next-step guidance), not per-cycle narration.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

The state script returns `needs-research` when `RESEARCH.md` is missing but `RESEARCH_PROMPT.md` exists. This step has **two paths**, gated by the `allow_research_skip` flag parsed in Step 0.

The default path (strict halt) is the safer choice for ordered queues with cross-feature dependencies: the FIRST research-pending feature in queue order halts the loop, so downstream features that may depend on the in-flight one never start work prematurely. The opt-in path (`--allow-research-skip`) restores the legacy "batch all pending research, halt once" behavior — only safe when the operator has verified the remaining queue is independent.

### Stub specs vs structured-research-pending specs (disambiguation rule)

`needs-research` fires ONLY for structured-but-research-pending specs — the baseline is locked, only deep research hasn't landed. Stub specs (no baseline yet) go through a different path: Step 4.5 of `lazy-state.py` dispatches `/spec` interactively to shape the baseline via `AskUserQuestion` rounds, and the orchestrator runs that as a normal cycle.

Detection happens inside `lazy-state.py::is_stub_spec(spec_text, queue_entry)`. A SPEC is a stub iff ANY of:
- SPEC body contains `Draft (pre-Gemini)` (canonical marker per AlgoBooth `docs/CLAUDE.md`).
- `queue_entry.get("stub") is True` (queue.json cross-check per AlgoBooth `docs/CLAUDE.md`).
- SPEC body contains a legacy marker (`**Status:** Draft (research stub)` or `> Stub generated from advanced feature research`).

| State | Signal | State-machine route | What the orchestrator does | User action needed |
|-------|--------|---------------------|-----------------------------|--------------------|
| Stub spec | `> Draft (pre-Gemini)` OR `queue.json "stub": true` OR legacy marker | Step 4.5 | Dispatch `/spec` as a normal cycle subagent; the subagent calls `AskUserQuestion` during Phase 1 brainstorming | Answer design questions inside the cycle (conversation) |
| Structured + research-pending | No stub markers; `RESEARCH.md` / `RESEARCH_SUMMARY.md` missing; `RESEARCH_PROMPT.md` present | Step 5 → terminal `needs-research` | Halt per Step 4 below (or batch per `--allow-research-skip`); the orchestrator does NOT dispatch `/spec` interactively | Upload Gemini research (single-turn action) |

HARD CONSTRAINT 5 scopes the orchestrator's `AskUserQuestion` to Step 1g — that constraint does NOT bind subagents the orchestrator dispatches. A `/spec` cycle subagent at Step 4.5 is allowed and expected to call `AskUserQuestion` during Phase 1; that's the legitimate design-conversation channel.

The `--allow-research-skip` flag described below applies to the STRUCTURED-research-pending case only. Stub specs never reach this step (they're dispatched at Step 4.5 before Step 5 fires).

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
