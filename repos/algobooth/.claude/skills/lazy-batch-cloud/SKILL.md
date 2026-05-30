---
name: lazy-batch-cloud
description: Cloud-environment variant of /lazy-batch. Loops on lazy-state.py --cloud and spawns Opus subagents per cycle, deferring any step that requires the Tauri desktop or MCP HTTP server. Distinguishes STUB specs (canonical `> Draft (pre-Gemini)` trailer OR queue.json `"stub": true` → Step 4.5 dispatches /spec as a normal cycle subagent that calls AskUserQuestion freely to shape the baseline) from STRUCTURED specs awaiting research (no stub markers, missing RESEARCH.md → Step 5 halts on needs-research and waits for the user's Gemini upload). HARD CONSTRAINT 5's no-AskUserQuestion-outside-Step-1g rule binds the orchestrator only, not subagents it dispatches. Halts on BLOCKED.md, needs-research (strict halt by default — the first research-pending feature stops the queue; opt into batched research with --allow-research-skip), queue-blocked-on-research (only reachable under --allow-research-skip), cloud-queue-exhausted, or max-cycles cap. NEEDS_INPUT.md (design decisions) does NOT halt: Step 1g calls AskUserQuestion, dispatches a Sonnet apply-resolution subagent to propagate the choice into SPEC/PHASES, and resumes the loop. After every /spec or plan-feature cycle, Step 1d.5 dispatches a dedicated Opus input-audit subagent that independently re-classifies the cycle's decisions and writes NEEDS_INPUT.md if any product-behavior calls were silently baked into SPEC/PHASES — Step 1g then resolves them inline on the next cycle. Mirrored with /lazy-batch. Research uploaded mid-session via chat triggers in-session resume: /ingest-research is dispatched immediately (writing the tracked RESEARCH.md + RESEARCH_SUMMARY.md — critical because docs/gemini-sprint/results/ is gitignored and bare .txt stages do not survive cloud-container reclaim) and the loop is re-invoked — no manual re-run required. --adhoc "<task>" enqueues an ad-hoc task at the TOP of the queue before the loop starts (Step 0.45, then an immediate push so it survives container reclaim) so the next cycle picks it up first; a brand-new ad-hoc feature begins at /spec Phase 1 and advances autonomously, pausing only for baseline-gating product-behavior decisions via Step 1g.
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip] [--adhoc "<task>" — enqueue an ad-hoc task at the top of the queue]
plan-mode: never
model: opus
allowed-tools: ["Bash", "Read", "Agent", "Write", "Edit", "AskUserQuestion"]
---

# Lazy Batch Cloud — Autonomous Pipeline Orchestrator (Cloud Mode)

Cloud variant of `/lazy-batch`. Identical orchestration shape: loop on the state script, spawn one Opus subagent per cycle, halt on the same terminal conditions — but the state script runs in `--cloud` mode, so:

- Step 2 skips cloud-saturated features (RETRO_DONE.md + DEFERRED_NON_CLOUD.md + no VALIDATED.md).
- **Step 8 (retro) runs in cloud** — `/retro` is a docs/analysis pass (no Tauri, no MCP). This is the gap the current ordering closes: under the old order (MCP before retro), cloud halted at the MCP deferral and never reached retro.
- Step 9 returns `__write_deferred_non_cloud__` instead of dispatching `/mcp-test`. The orchestrator writes the deferral sentinel inline (Step 1c.5 pseudo-skill handling) — the next cycle either advances to a ready feature or halts on `cloud-queue-exhausted`.
- Step 10 (mark complete) is unreachable from cloud unless a workstation has already produced VALIDATED.md. `cloud-queue-exhausted` is the normal terminal state when every remaining feature is awaiting workstation MCP testing.

**Per-cycle dispatch order:** `/spec` → `/plan-feature` (Step 6, = `/spec-phases` + `/write-plan` in one cycle) → `/execute-plan` → `/retro` (Step 8, cloud-runnable) → `/mcp-test` (Step 9, cloud defers) → mark-complete (Step 10, cloud halts).

This skill is coupled to `/lazy-batch` per CLAUDE.md — their only intended divergences are documented in the "Differences from /lazy-batch" block below.

---

## HARD CONSTRAINTS (non-negotiable)

Constraints 1-8 are identical to `/lazy-batch`; constraint 9 is cloud-only:

1. The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `COMPLETED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` / `PHASES.md` status lines when performing the `__mark_complete__` action. `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns; the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. All other `Write`/`Edit` operations require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool. Every sub-skill goes through a spawned `Agent` subagent. Pseudo-skills (`__*__`) are not real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files. State inference is exclusively via `lazy-state.py --cloud`. Sentinel files MAY be read by the orchestrator to confirm a write or drive a pseudo-skill action.
4. One cycle = one subagent dispatch FOR REAL WORK SKILLS. Pseudo-skill cycles (sentinel writes) are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to decision-resume mode (Step 1g) ONLY for the orchestrator itself.** Outside Step 1g, the orchestrator MUST NOT call `AskUserQuestion`. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. The user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation. **This constraint scopes the orchestrator, not subagents it dispatches.** A `/spec` subagent dispatched at state-machine Step 4.5 (stub-spec detected — see "Stub specs vs structured-research-pending specs" near Step 4) is allowed and expected to call `AskUserQuestion` during Phase 1 brainstorming; the orchestrator dispatches that cycle exactly the same way it dispatches any other real-skill cycle (one `Agent` call). Whatever the dispatched skill does internally is its own contract.
6. **The orchestrator MUST re-print the rich `## Decision Context` to chat BEFORE calling `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print is the load-bearing context. Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` — surface the malformation as a quality issue and halt instead (see Step 1g.1).
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch-cloud` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **The `cycle` counter is session-global and monotonic across feature transitions.** Identical to `/lazy-batch` HARD CONSTRAINT 8: `cycle` is initialized to 0 in Step 0 *once per `/lazy-batch-cloud` invocation* and incremented at the end of every cycle (Step 1c.5 step 5, Step 1e, Step 1g step 7). It MUST NOT be reset when `lazy-state.py --cloud` returns a different `feature_id` from one cycle to the next — i.e., when the queue advances from one feature to the next (via `__mark_complete__`, or because the prior feature hit `cloud-queue-exhausted`'s precondition and a later queue entry became current, or because the prior feature's `__write_deferred_non_cloud__` finished and the script rolled forward). Cycle N's status line — `"Cycle N/{max_cycles}: {sub_skill} on {feature_name} → ..."` — always refers to the N-th subagent dispatch in this `/lazy-batch-cloud` invocation, regardless of which feature it operated on. A feature transition is **not** a fresh batch.

9. **Dispatch ONLY against the feature `lazy-state.py --cloud` returned THIS cycle; never fabricate a feature.** Identical to `/lazy-batch` HARD CONSTRAINT 9: dispatch against exactly the `feature_id` + `spec_path` from the current cycle's state-script output, verbatim. NEVER invent/infer/hand-edit a slug the script didn't emit. The state script already skips queue entries whose `spec_dir` doesn't resolve on disk (`dangling queue entry` diagnostic), so a real feature always has an on-disk `spec_path`. The cycle subagent prompt MUST forbid CREATING a feature's `SPEC.md`/`RESEARCH.md`/`queue.json`/`ROADMAP.md` from a bare slug (only `--enqueue-adhoc` and a `/spec` dispatch against an already-seeded dir may create dirs). A `feature_id` with no on-disk `spec_path` is a bug to surface, never a cue to manufacture the feature.

10. **(CLOUD-ONLY, not in `/lazy-batch`) NEVER passively wait on a background-cycle completion notification across a container-reclaim boundary.** After ANY `SessionStart:resume` in cloud, the orchestrator MUST treat any in-flight background cycle agent as **unknown — reconcile from git + `lazy-state.py --cloud`** (Step 0.6), NEVER as "still running, awaiting its completion notification." A background-agent completion notification will NOT arrive across a container-reclaim boundary: the agent and the container it ran in are gone, so the signal can never fire. The orchestrator MUST re-probe and drive forward from the reconciled on-disk + remote state — it must never block waiting for that dead signal. **This is the OPPOSITE of HARD CONSTRAINT 7's rule, not a violation of it:** HARD CONSTRAINT 7 forbids *actively* polling/sleeping while research is in flight; HARD CONSTRAINT 9 forbids *passively* blocking on a notification that can never come. Both push the orchestrator to the same behavior — never block; reconcile and act on a single-turn signal.

**Cloud-specific:** the cycle subagent operates under the same cloud-environment limitations documented in `/lazy-cloud` — no Tauri runtime, no MCP HTTP server, no audio device, no Windows-only tooling. **Additionally, the cloud cycle subagent does NOT have the `Agent` tool — recursive sub-subagent dispatch is not supported from inside a cloud subagent.** This forces a load-bearing override of any dispatched skill's sub-subagent contract: skills that nominally dispatch sub-subagents (e.g. `/execute-plan` → Sonnet test-agent + impl-agent fanout, `/retro` → research subagents A–G) are performed INLINE inside the cycle subagent itself using `Edit`/`Write`/`Read` directly. The cycle subagent's prompt (Step 1d below) makes both limitations explicit and enumerates the per-skill inline overrides. **This override applies only at the cycle-subagent level** — the orchestrator still dispatches exactly one `Agent` per cycle, identical to `/lazy-batch`. The override never expands the orchestrator's `Write`/`Edit` scope (HARD CONSTRAINT 1 still holds — the orchestrator edits only sentinels).

> **Known cloud limitation — TDD agent-separation is traded away.** On workstation, `/execute-plan` enforces test-first discipline *structurally*: a dedicated Sonnet test-agent writes failing tests, then a separate impl-agent makes them pass (the separation `R-EP-2`/`R-EP-3` exist to enforce). The cloud override collapses this into ONE inline cycle subagent that writes both tests and implementation, so that structural test-first guarantee is GONE in cloud — it cannot be enforced from sub-subagent dispatch evidence. This is an intentional tradeoff, not a defect. The compensating controls are: (1) per-batch **quality gates** (`R-EP-6`) still run and must pass 100%; (2) the workstation **`/retro`** pass audits the landed work; (3) the deferred **MCP-validation** pass on workstation (which writes `VALIDATED.md`) gates final completion. The inline cycle subagent SHOULD still write **tests-before-impl within each batch** — read the test expectations, write the failing tests, then implement — even though the ordering can't be structurally verified. `/lazy-batch-retro` knows this: its Step 4b cloud branch grades `R-EP-2`/`R-EP-3` as `n/a (cloud-override)` rather than `fail`.

---

## Step 0: Parse Arguments

Same shape as `/lazy-batch` Step 0. `$ARGUMENTS` is tokenized:
- positive integer → `max_cycles` (default `10`)
- `--allow-research-skip` (optional) → `allow_research_skip = true` (default `false`)
- `--adhoc` (optional) → sets `adhoc_task` to the remainder of `$ARGUMENTS` after the token (empty → infer from conversation). Triggers **Step 0.45 (Ad-hoc Enqueue)** before the loop. Off by default. Place `<N>` / `--allow-research-skip` BEFORE `--adhoc` since it consumes the rest of the string.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 0 for the full flag semantics and rationale. The cloud variant inherits the same default-strict / opt-in-batched dichotomy — research-pending features halt the loop immediately by default; pass `--allow-research-skip` only when the remaining queue is known to be independent.

Print the start bookend:

```
## /lazy-batch-cloud — Starting
**Environment:** Cloud Linux (no Tauri/MCP)
**Max cycles:** {max_cycles}
**Research mode:** {strict halt on first needs-research (default) | batched (--allow-research-skip)}
**Repo root:** {cwd}
```

---

## Step 0.4: Resume-time remote sync (HARD REQUIREMENT — cloud reclaim recovery)

**Runs once, immediately after Step 0 (arg parsing) and BEFORE Step 0.5 / the Step 1a first state probe.** This is a single-turn git reconciliation, NOT polling — it does not violate HARD CONSTRAINT 7 (no active waiting). It does NOT touch the orchestrator's `Write`/`Edit` sentinel-only scope (HARD CONSTRAINT 1) — these are `Bash` git operations, not file edits.

**Rationale (cloud-acute):** a `/lazy-batch-cloud` session that resumes in a *fresh* container can check out a STALE local snapshot of the work branch — well behind the true remote tip — because the prior container (and its local commits beyond the last push) was reclaimed. The pushed history is safe on `origin`, but if the orchestrator runs `lazy-state.py --cloud` against the stale local tree it will infer state from out-of-date local files (plans, sentinels, SPEC) and either re-do or corrupt already-pushed work. The orchestrator MUST reconcile local to the remote tip BEFORE any local-state inference.

**Algorithm:**

1. Determine the work branch:

   ```bash
   branch=$(git rev-parse --abbrev-ref HEAD)
   ```

2. Fetch the remote tip (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error — this bounded retry is a single git op, not an active wait):

   ```bash
   git fetch origin "$branch"
   ```

   If the branch does not exist on `origin` yet (brand-new work branch never pushed — `fetch` reports no such ref), there is nothing to reconcile: skip the rest of Step 0.4 and continue to Step 0.5.

3. Fast-forward local to the remote tip:

   ```bash
   git merge --ff-only "origin/$branch"
   ```

4. **If the fast-forward FAILS because local has DIVERGED from `origin`** (non-fast-forwardable — local commits exist that `origin` does not have, which should never happen on a solo work branch), **do NOT clobber.** Do NOT `git reset --hard`, do NOT force anything. Surface the divergence to chat and halt for human resolution:

   ```
   🛑 /lazy-batch-cloud — work branch diverged from origin

   Local `{branch}` has commits that origin/{branch} does not, and origin has
   commits local does not (non-fast-forwardable). This should not happen on a
   solo work branch and may indicate concurrent edits from another container
   or a force-push. Refusing to auto-reconcile to avoid losing work.

   Resolve manually (inspect `git log --oneline --graph {branch} origin/{branch}`),
   then re-invoke /lazy-batch-cloud.
   ```

   PushNotification with the same one-line summary, then STOP. Do NOT run `lazy-state.py`.

5. On a clean fast-forward (or when local was already up to date / the branch was unpushed), print a one-line confirmation and continue to Step 0.5:

   ```
   🔄 Synced local {branch} to origin tip ({short-sha}) before resuming.
   ```

---

## Step 0.45: Ad-hoc Enqueue (only when `--adhoc` was supplied)

**Runs once, after Step 0.4 (remote sync) and BEFORE Step 0.5 / the first state probe.** Skipped entirely when the `--adhoc` flag was absent. It runs AFTER the remote ff-sync deliberately: enqueuing mutates `queue.json` in the working tree, so it must happen on the reconciled remote tip — acute in cloud, where the local snapshot may be stale after container reclaim.

!`cat ~/.claude/skills/_components/adhoc-enqueue.md`

**Cloud durability note (divergence from `/lazy-batch`):** the bootstrap files are tracked, but to survive container reclaim before the first cycle commits, push the work branch immediately after the enqueue — `git push origin $(git rev-parse --abbrev-ref HEAD)` (4× exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This folds into guardrail B's per-batch push discipline. The `queue.json` mutation was made by the `Bash` script (not `Write`/`Edit`), and a `git push` of committed work is not a `Write`/`Edit`, so HARD CONSTRAINT 1 still holds. (If the bootstrap files are not yet committed, stage and commit them via `Bash` git with message `chore({feature_id}): enqueue ad-hoc task at top of queue`, then push.) Continue to Step 0.5.

---

## Step 0.5: Pre-loop staged-research ingest check

**Identical to `/lazy-batch` Step 0.5** — before entering the main loop, probe for staged `.txt` files in `docs/gemini-sprint/results/` and dispatch `/ingest-research` as cycle 1 if any exist. This is the "resume after halt" entry point that lets the user upload research between sessions without any active waiting.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 0.5 for the full algorithm. Cloud-specific nuance: none — `/ingest-research`'s hard constraints already scope it to `docs/`-only writes (no Tauri / no MCP runtime required), so it runs identically in cloud and workstation.

---

## Step 0.6: Resume-reconciliation (HARD REQUIREMENT — cloud reclaim recovery)

**Runs once, after Step 0.5 and BEFORE the Step 1 main loop dispatches any real-work cycle. MANDATORY at the start of every `/lazy-batch-cloud` invocation AND treated as mandatory after any `SessionStart:resume`.** Like Step 0.4 this is single-turn git + state reconciliation, NOT polling (HARD CONSTRAINT 7 holds). It uses `Bash` git ops + the read-only state probe; the orchestrator itself performs no source `Write`/`Edit` (HARD CONSTRAINT 1 holds — the only file edits it may trigger are sentinel/SPEC/plan writes performed by a dispatched finalize subagent or by the inline pseudo-skill path, never by the orchestrator outside its sentinel scope).

**Rationale.** A cloud cycle (especially a 20-45 min `/execute-plan`) can be killed by a container reclaim mid-run. Per HARD CONSTRAINT 9 the orchestrator must NOT assume that killed cycle is "still running" and wait on its completion notification — that notification can never arrive. Instead it must reconcile the true state from git + `lazy-state.py --cloud` and drive forward. A killed cycle leaves up to three residues that MUST be handled before re-entering the loop, or the loop will redo finished work, hang, or discard correct partial work:

**Algorithm:**

1. **Push any unpushed local commits.** A same-container `SessionStart:resume` (not a fresh-container reclaim) can leave local commits that never pushed — the killed cycle committed but died before its per-WU push (Step 1d Commit + PUSH policy) or before the Step 1e backstop. Push them now so the remote is the source of truth for steps 2-4:

   ```bash
   git push origin "$(git rev-parse --abbrev-ref HEAD)"
   ```

   Retry up to 4× with exponential backoff (2s/4s/8s/16s) on network error; WORK BRANCH only, never main, never force. "Up to date" is fine. (After a true fresh-container reclaim there are no local-only commits — those died with the prior container; this step is then a no-op, and the durable state is whatever the per-WU pushes already landed on `origin`.)

2. **Probe state.** Run `python3 ~/.claude/scripts/lazy-state.py --cloud` (no `--skip-needs-research` — this is a reconciliation probe, identical invocation to Step 1a's default path). Parse the JSON. This is read-only.

3. **Detect + handle the "finished-but-not-finalized" case.** A killed cycle commonly leaves a plan part whose WUs/phases are already DONE on the remote (per-WU pushes landed) but whose finalization never ran — the plan frontmatter is still `Ready`/`In-progress`, PHASES.md per-phase status is unticked, or deliverable checkboxes are unticked. Detect it by cross-checking, for the current feature's active plan part:
   - `git log --oneline` shows the part's WU/batch commits are present, AND
   - the plan file's `- [ ]` checkboxes are all (or nearly all) `- [x]`, AND
   - the plan frontmatter `status:` is still `Ready` or `In-progress` (not `Complete`), OR PHASES.md's per-phase status / deliverable checkboxes for that phase are not yet ticked.

   When this holds, do NOT dispatch a full re-execution of the part. Dispatch a SHORT finalize cycle instead (one subagent — Sonnet is sufficient, the work is mechanical) with a bounded job:
     - verify the part's quality gates are green (run them; if RED, this is NOT finished-but-not-finalized — fall through to normal Step 1 loop execution to fix the failures);
     - flip the plan part frontmatter `status:` → `Complete`, **subject to the No-premature-Complete guard** — if `DEFERRED_NON_CLOUD.md` exists and `VALIDATED.md` does not, leave it `In-progress` and let the cloud-saturated `__flip_plan_complete_cloud_saturated__` flow carry it;
     - set PHASES.md per-phase status + tick that phase's deliverable checkboxes;
     - commit AND push each change (per the Step 1d Commit + PUSH policy).
   Record it as one cycle (append to `cycle_log`, update `prev_cycle_signature`, increment `cycle`), then return to the Step 1 loop. This converts a "redo the whole part" into a few-second finalize.

4. **Reconcile a dirty working tree.** If `git status --porcelain` is non-empty, a killed agent left uncommitted partial work. Do NOT blindly `git checkout` / `git reset` it away — discarding work as a shortcut is forbidden. Read the diff (`git diff` + `git status`) and decide: if the partial work is correct-but-uncommitted, KEEP it and finish it (dispatch a bounded continue/finalize subagent, since source edits require a subagent per HARD CONSTRAINT 1 — the orchestrator must not edit source files itself); if a hunk is genuinely corrupt/half-applied, surface that diff to chat first and revert ONLY the broken hunk, never the whole tree. When in doubt, dispatch the bounded subagent to read the diff and either complete the in-flight WU or cleanly revert just the broken portion.

After steps 1-4, print a one-line reconciliation summary and enter the Step 1 loop:

```
🔧 Resume-reconciliation: pushed {N} commit(s); {finalized plan part X | no finalize needed}; {reconciled dirty tree | clean tree}.
```

When steps 2-4 find nothing to reconcile (clean tree, no finished-but-not-finalized part), Step 0.6 is a fast no-op beyond the step-1 push — the normal fresh-start case.

---

## Step 1: Cycle Loop

Initialize per-session state — identical shape to `/lazy-batch` Step 0. **This init is logically part of Step 0 (arg parse): it happens ONCE, before Steps 0.4 / 0.5 / 0.6 run, so any pre-loop cycle they record (Step 0.5's ingest dispatch, Step 0.6's finalize dispatch) increments `cycle` / sets `prev_cycle_signature` forward from these values — the loop entry NEVER re-initializes them.**
- `cycle = 0` — initialized once per `/lazy-batch-cloud` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py --cloud` returns a new `feature_id`).
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `research_pending = set()` — feature_ids that hit `needs-research` this session. Only used when `allow_research_skip == true`; empty under the default strict-halt path.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. Stays `false` under the default path.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, sub_skill_args, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched. **`sub_skill_args` is part of the tuple deliberately** (mirrored from `/lazy-batch`): a multi-part `/execute-plan` sequence (part-1 → part-2 → part-3) returns the same `(feature_id, sub_skill, current_step)` on every part but a *different* `sub_skill_args` (the plan-part path) — real forward progress, not a loop. Omitting `sub_skill_args` made the loop-guard false-trigger on every multi-part plan.
- `adhoc_task = <parsed>` — the ad-hoc task text from `--adhoc` (empty string if the flag was present with no text; unset/`None` if absent). See Step 0.45.

### 1a. Run lazy-state.py --cloud

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]
```

Pass `--skip-needs-research` **only when `allow_research_skip == true` AND `skip_needs_research == true`**. Under the default strict-halt path the flag is never added, so the script returns `terminal_reason: needs-research` for the first research-pending feature in queue order — see `~/.claude/skills/lazy-batch/SKILL.md` Step 1a for the double-gate rationale. Parse JSON output as in `/lazy-batch`.

### 1b. Handle terminal states

Same handling as `/lazy-batch` for `blocked`, `needs-input`, `needs-spec-input`, `queue-missing`, `all-features-complete`, `completion-unverified`. Cloud-specific:

- **`needs-input`**: see Step 1g (decision-resume mode — identical to `/lazy-batch` Step 1g). **Not a terminal state for the orchestrator anymore** — Step 1g resolves the decision via `AskUserQuestion`, dispatches the Sonnet apply-resolution subagent, and returns to Step 1a. Do NOT print the final batch report.
- **`completion-unverified`**: identical to `/lazy-batch` — a feature claims `Complete` with no `COMPLETED.md` receipt (flipped outside the validation gate). Halt for human reconciliation: PushNotification with `notify_message`, print final batch report, STOP. Do NOT auto-reopen or auto-backfill; that judgment is the operator's (`lazy-state.py --backfill-receipts` to grandfather, or reopen to `In-progress` to re-validate).
- **`cloud-queue-exhausted`**: PushNotification `"Cloud queue exhausted after {cycle} cycle(s) — N feature(s) awaiting workstation /lazy for MCP test."` Print final batch report, STOP.
- **`device-queue-exhausted`**: A remaining feature carries `DEFERRED_REQUIRES_DEVICE.md` (real-device-only assertions) but no `DEFERRED_NON_CLOUD.md`, so the cloud-saturated skip didn't catch it. Cloud has no audio device either, so cloud cannot certify it. PushNotification with `notify_message`, print final batch report, STOP — surface that a **real-device** /lazy host (`ALGOBOOTH_REAL_AUDIO_DEVICE=1` or native hardware) is needed to re-open and certify the deferred scenarios. Rare in cloud: cloud-saturated features normally carry `DEFERRED_NON_CLOUD.md` and hit `cloud-queue-exhausted` first.
- **`needs-research`**: see Step 4 (research halt — same dual-path shape as `/lazy-batch`, but the sentinel's `written_by` is `lazy-batch-cloud`). Default (strict halt) writes the sentinel, prints the inline-prompt halt announcement, PushNotifies, prints the final batch report, and STOPs. Opt-in (`--allow-research-skip`) drops the sentinel, flips `skip_needs_research = true`, returns to Step 1a.
- **`queue-blocked-on-research`**: see Step 1f (research-wait mode — identical to `/lazy-batch` Step 1f). **Only reachable when `allow_research_skip == true`.**

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
- **`__mark_complete__`** — only reachable from cloud if both `VALIDATED.md` and `RETRO_DONE.md` already exist (cloud cannot produce VALIDATED.md from MCP results — workstation did). **Hard guard (no premature Complete):** before flipping anything, confirm `<spec_path>/VALIDATED.md` exists. If `<spec_path>/DEFERRED_NON_CLOUD.md` exists AND `VALIDATED.md` does NOT, REFUSE to mark complete — the MCP-validation pass that writes `VALIDATED.md` has not run yet, so `Complete` would be a lie. In that case do NOT touch SPEC/ROADMAP status; treat the cycle as a no-op forward-progress issue (the state script should not have emitted `__mark_complete__` here — surface it) and continue. **Second gate: MCP-coverage audit** (mirrored from `/lazy-batch`, fed by the shared `~/.claude/skills/_components/mcp-coverage-audit.md` component). The orchestrator inlines the audit per the component algorithm (read SPEC.md's `## Locked Decisions` / `## Resolved by Research` / numbered key-decisions surface; grep each `<spec_path>/mcp-tests/*.md` for each decision's id + keywords). If any decision is uncovered, the orchestrator (still inline, sentinel-write only — HARD CONSTRAINT 1 holds) writes `<spec_path>/NEEDS_INPUT.md` per the audit component's schema and commits + pushes it. Append `{cycle+1, feature_name, "__mark_complete__ (audit halted)", "{N} uncovered decisions → NEEDS_INPUT.md"}` to `cycle_log`, increment `cycle`, return to Step 1a — the next state-script call returns `terminal_reason: needs-input`, Step 1g surfaces the decisions, and the apply-resolution Sonnet subagent authors `mcp-tests/*.md` coverage (or records the exemption in SPEC.md) before the next mark-complete attempt. **The audit is docs-only** (reads SPEC.md + `mcp-tests/*.md`, no Tauri / no MCP server) — it runs identically in cloud and workstation. **Third gate: completion-integrity gate** (runs only after the coverage audit returns `clean`, fed by the shared `~/.claude/skills/_components/completion-integrity-gate.md` component, with `{cloud}=true`). The orchestrator inlines it: verify phase-coherence (zero non-verification unchecked deliverables in PHASES.md) and that `RETRO_DONE.md` plus a validation sentinel exist (in cloud, `DEFERRED_NON_CLOUD.md` counts ONLY alongside `VALIDATED.md` — which the first guard already requires). If a precondition fails, write `<spec_path>/NEEDS_INPUT.md` (`written_by: completion-integrity-gate`), commit + push, append `{cycle+1, feature_name, "__mark_complete__ (gate halted)", "<reason> → NEEDS_INPUT.md"}` to `cycle_log`, increment `cycle`, return to Step 1a. Only when ALL THREE gates pass (VALIDATED.md present AND audit `clean` AND integrity `gated`): **first WRITE `<spec_path>/COMPLETED.md`** (`kind: completed`, `provenance: gated`, folding the VALIDATED.md/MCP_TEST_RESULTS.md evidence into the receipt body — the durable proof `lazy-state.py` Step 2 keys on; a `Complete` claim without it hard-halts on `completion-unverified`), then update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token), delete `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` sentinels (KEEP `COMPLETED.md`/`SKIP_MCP_TEST.md`/`MCP_TEST_RESULTS.md`), set `<spec_path>/SPEC.md` (and PHASES.md top-level) `**Status:**` to `Complete`, then commit per project policy. This closes the 30%-of-features Reopened-Complete gap the audit walk surfaced AND the un-gated-completion gap (a `Complete` with no receipt now hard-halts).
- **`__flip_plan_complete_cloud_saturated__`** — emitted by `lazy-state.py --cloud` at Step 7a when an `In-progress` plan's only unchecked WUs (scoped to the plan's `phases:` field) are documented in `<spec_path>/DEFERRED_NON_CLOUD.md` as workstation-only. This is the cloud-only common path; it fires once per saturated plan part. `sub_skill_args` is the absolute plan-file path. Read the plan's YAML frontmatter, edit ONLY the `status:` line in place (`In-progress` → `Complete`) — leave every other field and the markdown body untouched. Derive the plan part number from the plan's `phases:` field (e.g. `phases: [6]` → part 6); fall back to the plan filename's leading `part-N` / `phase-N` token if `phases:` is missing. Stage the plan file and commit per project policy with message `chore(<feature_id>): mark plan part N Complete (cloud-saturated)`. Do NOT touch SPEC.md, ROADMAP.md, or any sentinel — this is a frontmatter-only flip. Editing style: match the conservative single-field rewrite already used by `__write_deferred_non_cloud__` (idempotent if the line is already `Complete`). This pseudo-skill is what prevents the `Step 7a: execute plan` no-op loop hit on `audio-thread-panic-catching` plan part 6: previously the orchestrator would dispatch `/execute-plan` against an In-progress plan whose only remainder was workstation-gated, the cycle would correctly diagnose "no cloud work" but make no commit, and the next cycle would receive the same state — burning Opus dispatches without advancing the queue.

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. **Push backstop (HARD REQUIREMENT — cloud reclaim safety).** The inline pseudo-skill committed a sentinel / plan-frontmatter change locally; push it now so it survives container reclaim — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). This is the backstop for inline cycles that the orchestrator owns directly — a `git push` of an already-committed change, NOT a Write/Edit, so HARD CONSTRAINT 1 still holds. If the push reports "up to date," that is fine (a prior cycle's push already carried it).
3. Emit the canonical per-cycle update block (Step 3): heading `### Cycle {cycle+1}/{max_cycles} · {feature_name} · {sub_skill}`, `**Result:**` = the inline outcome, `**Commit:**` = the sentinel/plan commit sha. Nothing else.
4. Update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)` (same uniform post-cycle update as Step 1e — keeps the loop-guard accurate across mixed pseudo-skill / real-skill cycles).
5. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), the cloud cycle subagent prompt adds explicit reminders of (1) cloud runtime limitations (no Tauri / MCP / audio / Windows-only tooling) and (2) the cloud recursive-`Agent`-dispatch limit, with a per-skill inline-edit override that supersedes the dispatched skill's sub-subagent contract.

**Loop-guard check (identical shape to `/lazy-batch` Step 1d):** BEFORE composing the prompt, compute the current cycle's signature as the tuple `(feature_id, sub_skill, sub_skill_args, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, sub_skill_args, current_step)`, append the **LOOP DETECTED** block below to the subagent prompt — the state script has returned the same tuple two cycles in a row, almost always indicating a terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`) is missing. **`sub_skill_args` MUST be part of the compared tuple** — otherwise a multi-part `/execute-plan` sequence (different plan-part path per part, same other fields) false-triggers the guard on every part despite genuine forward progress.

Base prompt template:

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

Sub-subagent dispatch policy (CLOUD OVERRIDE — LOAD-BEARING):
  This subagent runs in a cloud Linux session and does NOT have the `Agent`
  tool — you CANNOT spawn further sub-subagents from inside this cycle. Any
  Agent() call you attempt will fail (tool unavailable) and waste the cycle.

  Therefore, regardless of what the dispatched skill's SKILL.md says about
  spawning sub-subagents (test-agent, impl-agent, research subagents A–G,
  etc.), you MUST perform that work INLINE in this subagent session using
  Edit / Write / Read directly. The cloud cycle subagent SUPERSEDES the
  dispatched skill's sub-subagent dispatch contract — this is the documented
  cloud override, not a hard contract violation.

  Per-skill cloud overrides (override the workstation SKILL.md contract):
    • /execute-plan — IGNORE Step 3's "Execution Model Enforcement". Do NOT
      attempt Agent({model: "sonnet"}) test-agent / impl-agent dispatches.
      Perform each batch's test additions and implementation edits INLINE
      with Edit / Write / Read on source/test files directly
      (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files included).
      Follow the rest of /execute-plan as written (batch ordering, commits,
      plan-file checkbox flips, sentinel emissions). Zero sub-subagent
      dispatches in a cloud /execute-plan cycle is the EXPECTED state —
      NOT a contract violation.
      SKIP THE GROUND-TRUTH RE-RUN: subagent-review.md Step 1.5 exists to
      detect a *separate* untrusted subagent falsifying its report by re-running
      every command (git status / wc -l / grep / test runner) from the
      orchestrator's shell and diffing. In this inline path YOU wrote both the
      tests and the implementation in this same session — there is no separate
      subagent report to police, so that mechanical command re-run is pure
      redundant work. Do NOT re-run-and-diff your own commands; you already have
      ground truth from having just run them. Still perform the SUBSTANTIVE
      correctness review (spec alignment, deliverable coverage, logic/edge-case
      check, propagation check per subagent-review.md Step 2.5) and still run
      the quality gates — only the falsification-detection re-run is dropped.
      (This matches /lazy-batch-retro, which already grades R-EP-4 — the
      subagent-review step — as `n/a (cloud-override)` for cloud cycles.)
      KNOWN CLOUD LIMITATION: collapsing the test-agent/impl-agent split into
      one inline session trades away the STRUCTURAL test-first guarantee.
      You MUST still preserve test-first DISCIPLINE within each batch: write
      the failing tests FIRST (per the plan's test expectations), confirm they
      fail for the right reason, THEN implement until they pass. The
      compensating controls are quality gates (run + pass per the right-sized
      cadence — targeted on intermediate batches, full workspace gate at
      plan-part end + on any escalation trigger; see quality-gates.md), the
      workstation /retro pass, and the deferred MCP-validation pass — none of
      which substitute for writing tests before implementation here.
    • /retro — IGNORE Step 3's parallel research-subagent fanout (A–G). Do
      the research INLINE: read each input serially, synthesize, and write
      the retro plan + RETRO_DONE.md directly. The deliverable is identical;
      only the parallelism is dropped.
    • retro-feature — composed orchestrator; same override — perform all
      internal work inline rather than dispatching nested sub-subagents.
    • plan-feature — composed orchestrator; runs /spec-phases THEN
      /write-plan via the Skill tool (in-context, NOT Agent dispatch). Both
      sub-skills are docs-only (PHASES.md + plan files) and orchestrator-only
      in cloud, so no recursive Agent dispatch is needed — invoke /plan-feature
      once and let it run its two sub-skills in your context. This is what
      lazy-state.py --cloud emits at Step 6 (replacing the separate
      /spec-phases dispatch).
    • /spec, /spec-phases, /write-plan, /add-phase, /ingest-research —
      already orchestrator-only; no change.
    • /mcp-test — cloud cannot run this (Step 8 deferral); should not appear
      in a cloud cycle's sub_skill.

  If you find yourself about to write Agent({...}) inside this cycle, STOP
  and replace it with the equivalent Edit / Write / Read sequence. Do NOT
  write BLOCKED.md because of the recursive-dispatch limit — that limit is
  exactly what this override exists to handle. BLOCKED.md is still correct
  for genuine cloud-RUNTIME limitations (Tauri, MCP, audio, Windows-only
  tooling) per blocker_kind: cloud-limitation.

  The dispatched skill's own SKILL.md remains authoritative for everything
  else: batch ordering, sentinel emissions, commit policy, file-shape
  invariants, plan-checkbox semantics. Re-read it from disk if any non-
  dispatch detail is unclear — do NOT rely on memory.

Source/test file edits:
  - All cloud-cycle paths: perform Edit / Write on source/test files
    (.ts, .js, .cs, .vue, .py, .rs, .tsx, .jsx, test files) DIRECTLY in
    this subagent session. The cloud override above removes the
    /execute-plan dispatch requirement and replaces it with inline edits.

No premature Complete (PIPELINE-GATE + CLOUD HONESTY — HARD REQUIREMENT):
  - You MUST NEVER set the top-level `**Status:**` of SPEC.md or PHASES.md to
    `Complete` — under ANY condition. That flip is reserved EXCLUSIVELY for the
    orchestrator's __mark_complete__ pseudo-skill, which runs only after the
    full downstream tail (/retro → MCP-validation → the __mark_complete__
    MCP-coverage audit) and itself refuses to fire without VALIDATED.md. If a
    phase-implementation cycle flips SPEC/PHASES `**Status:** Complete` itself,
    the feature has NO COMPLETED.md receipt, so lazy-state.py Step 2 now
    HARD-HALTS on `completion-unverified` instead of rolling the queue forward —
    the rogue flip stops the loop until a human reconciles rather than silently
    skipping /retro + the coverage audit + the deferred workstation MCP pass.
    The receipt gate makes this guard self-enforcing. Do NOT write a
    COMPLETED.md yourself either — only the orchestrator's __mark_complete__
    integrity gate writes it, after the validation tail passes.
  - This is doubly true in cloud: MCP validation is DEFERRED to a workstation
    pass that writes VALIDATED.md; until that runs, `Complete` asserts something
    that has not happened. The honest terminal cloud state is `In-progress` (work
    implemented + pushed, validation pending). What you MAY flip when a phase's
    work lands: the PLAN-PART frontmatter `status:` and the per-PHASE
    checkboxes/`Status:` for the phase you implemented; set the top-level PHASES
    `**Status:**` to `In-progress` (NOT `Complete`). Let the deferral sentinel +
    cloud-saturated flow + __mark_complete__ carry it to `Complete`.

Plan-part status + per-WU granularity (RESUME SAFETY — HARD REQUIREMENT):
  A cloud cycle can be killed mid-run by a container reclaim. To make a killed
  cycle resume CLEANLY instead of redoing the whole part, you MUST keep the
  plan part's on-disk status and per-WU checkboxes accurate AS THE WORK LANDS —
  not only at end-of-cycle:

  - For /execute-plan (and any /retro / realign cycle that mutates a plan part):
    BEFORE starting any work-unit work, flip the plan part's YAML frontmatter
    `status:` from `Ready` → `In-progress`, then commit AND push that single
    change immediately (per the Commit + PUSH policy below). A mid-run kill then
    leaves an accurate `In-progress` marker that resumes cleanly, instead of a
    stale `Ready` that makes the resume redo the entire part.
  - As EACH work-unit lands, tick its `- [ ]` → `- [x]` checkbox in the plan
    file, then commit AND push that tick immediately — folded into the same
    per-WU commit as the WU's code, or as its own small commit. This makes
    resume granularity PER-WU: a kill loses at most the in-flight WU, and the
    next run's Step 0.6 probe resumes at the first still-unchecked box.
  - Prefer plan work-units authored as parseable `- [ ]` markdown checkboxes
    (one per WU) so the resume probe can read per-WU completion straight from
    the plan file. If a plan part is authored as prose without checkboxes,
    resume granularity collapses to per-part — flag this in your summary so the
    plan can be re-authored with checkboxes next time.
  - Do NOT flip the plan part to `Complete` from inside the cycle when
    DEFERRED_NON_CLOUD.md exists and VALIDATED.md does not (see "No premature
    Complete" above) — `In-progress` is the honest cloud terminal; the
    orchestrator's pseudo-skills own the `Complete` flip.

Commit + PUSH policy (CLOUD DURABILITY — HARD REQUIREMENT):
  This is a cloud container with NO persistent state — it is reclaimed on
  inactivity, and a long-running cycle (20-45 min) looks idle to the
  reclaimer. ANY local commit you make that has not been pushed is
  PERMANENTLY LOST if the container is reclaimed mid-cycle. Therefore:

  - After EACH batch / work-unit commit, IMMEDIATELY push it — do NOT defer
    pushing to the end of the plan part or the end of the cycle:

      git push origin <work-branch>

    where <work-branch> is the current branch (git rev-parse --abbrev-ref
    HEAD). Retry up to 4× with exponential backoff (2s/4s/8s/16s) on a
    NETWORK error only. This shrinks the reclaim-loss window from "the entire
    cycle runtime" to "a single batch".
  - This applies per /execute-plan batch (push after every per-batch commit),
    and to any other skill that commits incrementally. If the skill makes a
    single commit, push that one commit immediately after it lands.
  - You are authorized to push to the WORK BRANCH ONLY (the branch you are
    already on). NEVER push to main / master. NEVER force-push. If the push
    is rejected as non-fast-forward, STOP and report it — do not force.
  - This does NOT change WHO owns source edits: you (the cycle subagent)
    already own all source/test edits and commits per the cloud override
    above. Adding `git push` is a git operation on work you already authored;
    it does not touch the orchestrator's sentinel-only Write/Edit scope.

After the skill returns:
  1. Commit per .claude/skill-config/commit-policy.md (or standard pattern)
     for any final uncommitted changes, then push per the Commit + PUSH
     policy above. By this point every batch commit should ALREADY be pushed.
  2. Report a one-paragraph summary (under 8 lines). If you ran /execute-plan
     or /retro, CONFIRM that you performed all source/test edits and research
     INLINE (zero Agent() calls) — this is the cloud-override audit signal,
     mirroring the sub-subagent-count signal /lazy-batch uses on workstation.
     Also CONFIRM each batch commit was pushed as it landed (the reclaim-safety
     audit signal).
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
     (e.g. all phases complete + deferred-non-cloud + retro plan present
     with no significant divergences → RETRO_DONE.md should already exist;
     if it doesn't, the previous retro round failed to write it).
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

Append the LOOP DETECTED block after the base prompt's final paragraph when and ONLY when the loop-guard condition holds. Do NOT include it on the first cycle (when `prev_cycle_signature is None`) or when the signature differs from the previous cycle.

Dispatch:

```
Agent({
  description: "lazy-batch-cloud cycle {cycle+1}: {sub_skill} for {feature_name}",
  subagent_type: "general-purpose",
  model: <"sonnet" if LOOP DETECTED else "opus">,
  prompt: <the prompt above>
})
```

**Model selection (mirrored with `/lazy-batch`).** Normal cycles dispatch on Opus because real-skill cycles can involve novel implementation decisions. The loop-resolution cycle (LOOP DETECTED branch) is mechanical — the prompt already contains the diagnosis and the work is "read the canonical sentinel schema, identify which sentinel preconditions are met, write it, commit". Sonnet is sufficient at roughly 5× the cost-efficiency. Use `model: "sonnet"` when the LOOP DETECTED block was appended, `model: "opus"` otherwise.

### 1d.5. Post-cycle input audit (Opus — runs only on `/spec` and `plan-feature` cycles)

**MIRRORED with `/lazy-batch` Step 1d.5.** See `~/.claude/skills/lazy-batch/SKILL.md` Step 1d.5 for the full algorithm, dispatch shape, audit prompt, and post-return handling. The audit subagent's contract is identical in cloud and workstation: docs-only writes (only `{spec_path}/NEEDS_INPUT.md`), no source/test edits, no recursive dispatch, no Skill-tool calls. The cycle subagent that just ran was forbidden from using the `Agent` tool (cloud-override per Step 1d), but the audit subagent is dispatched by the orchestrator (main session, which retains `Agent`), so dispatch works identically.

**Cloud-specific nuance: none.** The audit subagent does not require the Tauri desktop, the MCP HTTP server, or any cloud-restricted capability — it reads files in `{spec_path}/`, classifies decisions, and (optionally) writes one sentinel file. The sentinel commit + push folds into the cycle's normal post-cycle push (guardrail B end-of-cycle push catches it; guardrail C backstop at Step 1e verifies). Cloud-reclaim safety is preserved: NEEDS_INPUT.md is committed and pushed before the orchestrator returns to Step 1a.

**Skip conditions, dispatch, audit prompt, post-return bullet rules:** verbatim from `/lazy-batch` Step 1d.5. The product-behavior smells checklist the auditor applies lives in `~/.claude/skills/spec/SKILL.md` ("Product-behavior smells — concrete checklist"); the Decision-Classification Ledger contract the auditor verifies against also lives there.

### 1e. Record cycle outcome and loop

Same as `/lazy-batch`. Append to `cycle_log`, emit the canonical per-cycle update block (Step 3 — heading + `**Result:**` / `**Commit:**` bullets, no other prose; add the `**Sub-agents:**` audit bullet on `/execute-plan` cycles, and the `**Audit:**` bullet on `/spec` / `plan-feature` cycles whose Step 1d.5 surfaced product-behavior decisions), update `prev_cycle_signature = (feature_id, sub_skill, sub_skill_args, current_step)`, increment cycle, loop. **Post-cycle push backstop (HARD REQUIREMENT — cloud reclaim safety):** after the cycle subagent returns, the orchestrator verifies the work branch is pushed — `git push origin $(git rev-parse --abbrev-ref HEAD)` (retry up to 4× with exponential backoff 2s/4s/8s/16s on network error; WORK BRANCH only, never main, never force). Under guardrail B the cycle subagent already pushed every batch commit, so this normally reports "up to date" — it is the backstop for any cycle (or future skill) that did not push itself. A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 still holds. The prev-signature update is the uniform post-cycle action that keeps the Step 1d loop-guard accurate across both real-skill and pseudo-skill cycles. **The cycle-counter increment is also a uniform post-cycle action that NEVER resets on feature transitions (HARD CONSTRAINT 8) — when the next `lazy-state.py --cloud` call returns a different `feature_id` (e.g. after `__mark_complete__`, after `__write_deferred_non_cloud__` rolls the queue to the next ready feature, or any other queue-advance), `cycle` continues incrementing from where it was.**

### 1f. Research-wait mode (`terminal_reason == "queue-blocked-on-research"`)

**Reachable only when `allow_research_skip == true`.** Identical shape to `/lazy-batch` Step 1f — passive halt with inline RESEARCH_PROMPT.md content for every pending feature (fenced ```text block for mobile long-press-copy into Gemini), char-count over/under indicator against the 24,000-char Gemini web-UI cap, all three upload paths, PushNotification, final batch report, STOP.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 1f for the full algorithm and the announcement template — replace "/lazy-batch" with "/lazy-batch-cloud" in the chat text. Cloud-specific upload nuance:

- **FASTEST RESUME (cloud-recommended): in-session upload via chat.** Upload the research in your NEXT MESSAGE — file attachment, pasted text, or any chat-uploaded file. The orchestrator (per Step 5) dispatches `/ingest-research` in-session, which writes the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` into the feature directory BEFORE the cloud container is reclaimed. This is the only fully-durable cloud resume path that does not require leaving the conversation.
- **Upload path ① (staged .txt, gitignored — non-durable in cloud):** save each Gemini output as `docs/gemini-sprint/results/<feature-id>.txt`. **The `docs/gemini-sprint/results/` path is gitignored**, so a bare `.txt` stage from a cloud session will NOT survive container reclaim — it only works if you also commit/push the staged file from a workstation (GitHub UI push), or if `/ingest-research` runs in-session to convert the staged .txt into the tracked RESEARCH.md + RESEARCH_SUMMARY.md before the container goes away. The in-session resume above does exactly that.
- **Upload path ② (direct RESEARCH.md drop, durable):** write the research directly to `docs/features/.../<feature_id>/RESEARCH.md`. This file IS tracked, so it survives cloud reclaim. From cloud, you still need to commit the file inside the container (the cycle subagent on the next run will commit it as part of normal work, or you can commit it explicitly). The next `/lazy-batch-cloud` run routes straight to `/spec` Phase 3.
- **Upload path ③ (`/ingest-research <path>`)** is workstation-only — it operates on absolute file paths the cloud container cannot see. If you're working from a phone via the cloud branch, use the in-session resume path or path ②.

The user can mix environments: drop `RESEARCH.md` directly from workstation, then resume from cloud; or upload research via chat in the cloud session and let the in-session resume protocol handle it end-to-end.

### 1g. Decision-resume mode (`terminal_reason == "needs-input"`)

**Identical to `/lazy-batch` Step 1g** — the decision-resume protocol is shared, and **does not halt**. See `~/.claude/skills/lazy-batch/SKILL.md` Step 1g for the full algorithm:

1. Read and validate `NEEDS_INPUT.md` (schema check on `## Decision Context` H2 + H3 1:1).
2. Re-print the rich body to chat VERBATIM.
3. `AskUserQuestion` per decision (label, header, options).
4. Append `## Resolution` to NEEDS_INPUT.md.
5. Commit the resolved sentinel per project policy.
6. Dispatch the **Sonnet apply-resolution subagent** to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel (rename to `NEEDS_INPUT_RESOLVED.md` OR change frontmatter `kind:` to `needs-input-resolved`).
7. Append to `cycle_log`, update `prev_cycle_signature = (feature_id, "__apply_needs_input__", current_step)`, increment `cycle`. **Return to Step 1a — do NOT halt.**

Cloud has no special handling here — decision resolution is filesystem-level and runs identically in cloud and workstation. The Sonnet subagent's SPEC/PHASES edits are docs-only (no source code, no Tauri runtime, no MCP), so cloud limitations do not apply. **Replace `/lazy-batch` with `/lazy-batch-cloud` in the chat heading and any re-invoke references** when reproducing the announcement in a cloud session.

---

## Step 1.5: Forward-Progress Verification (informally "Step 2.5"; runs after loop exit, before the Step 2 batch report)

**Identical algorithm to `/lazy-batch` Step 1.5** — see `~/.claude/skills/lazy-batch/SKILL.md` Step 1.5 for the full protocol. Cloud variant uses `python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]` for the probe, identical to Step 1a.

Skip the probe entirely when `terminal_reason in {"blocked", "needs-input", "queue-missing"}`. For every other exit — including `all-features-complete`, `cloud-queue-exhausted`, `needs-research`, `queue-blocked-on-research`, and max-cycles — run the probe, compare its `(feature_id, sub_skill, sub_skill_args, current_step)` tuple against `prev_cycle_signature`, and prepend ONE of these blocks to the Step 2 final batch report:

- **Forward-progress confirmed** (probe differs from prev_cycle_signature OR probe terminal):

  ```
  ✅ Next /lazy-batch-cloud invocation will: <human-readable summary>
  ```

- **Forward-progress WARNING** (probe matches prev_cycle_signature; no terminal reason):

  ```
  ⚠ FORWARD-PROGRESS WARNING: the next /lazy-batch-cloud invocation will
  return the same state as the cycle we just finished
  (feature_id={feature_id}, sub_skill={sub_skill},
  sub_skill_args={sub_skill_args}, current_step={current_step}).

  This run did not advance the queue. Likely causes (cloud-specific):
    • A sentinel that should have been written wasn't (RETRO_DONE.md,
      DEFERRED_NON_CLOUD.md, VALIDATED.md, SKIP_MCP_TEST.md).
    • A plan-frontmatter status flip the last cycle was supposed to perform
      did not land — most commonly, the cloud-saturated In-progress →
      Complete flip that __flip_plan_complete_cloud_saturated__ exists to
      perform. Inspect {spec_path}/plans/ frontmatter for any
      `status: In-progress` plan whose unchecked WUs are all listed in
      DEFERRED_NON_CLOUD.md.
    • lazy-state.py --cloud is stuck on a condition no cloud-runnable skill
      is resolving.

  Inspect {spec_path}/ sentinels and plan frontmatter before re-invoking.
  ```

  Plus PushNotification `"lazy-batch-cloud forward-progress WARNING — queue did not advance; inspect {feature_name} sentinels."`.

The probe is read-only — never mutates `cycle`, `cycle_log`, or sentinels. A non-zero probe exit prints `⚠ FORWARD-PROGRESS PROBE FAILED: lazy-state.py exited non-zero — re-invoke /lazy-batch-cloud to retry.` and the loop's already-produced final report still prints. The cloud-specific WARNING block adds the cloud-saturated-flip bullet because that is the failure mode most likely to silently strand a `/lazy-batch-cloud` run.

---

## Step 2: Final Batch Report

Same as `/lazy-batch`. Header is `## /lazy-batch-cloud — Done`. Cloud-specific "Next step" guidance:

```
**Next step:**
  - If terminal_reason is "blocked": resolve {spec_path}/BLOCKED.md
  - If terminal_reason is "needs-research" (DEFAULT path, strict halt): the fastest (and only fully-durable cloud) resume path is to upload Gemini research in your NEXT MESSAGE in this conversation — the in-session resume protocol (Step 5) will dispatch /ingest-research and re-invoke /lazy-batch-cloud automatically, writing the tracked RESEARCH.md before container reclaim. Otherwise, drop RESEARCH.md directly (path ②) and re-run `/lazy-batch-cloud {max_cycles}` from a fresh session.
  - If terminal_reason is "queue-blocked-on-research" (only reachable under --allow-research-skip): same as needs-research — upload research in chat for fastest resume, or use path ② and re-run `/lazy-batch-cloud {max_cycles} [--allow-research-skip]`.
  - (needs-input is no longer a terminal state — Step 1g resolves and resumes within the same /lazy-batch-cloud invocation.)
  - If terminal_reason is "cloud-queue-exhausted": run /lazy on workstation to run MCP tests
  - If max-cycles: re-run `/lazy-batch-cloud {max_cycles}` from a fresh session
```

---

## Step 3: Cycle Output Discipline (lean · consistent · scannable)

**Identical to `/lazy-batch` Step 3** — every cycle emits EXACTLY ONE update block (`### Cycle {N}/{max_cycles} · {feature_name} · {sub_skill}` heading + `**Result:**` / `**Commit:**` bullets) and nothing else. All suppression rules carry over verbatim: no dispatch narration, no commit-strategy narration, ignore between-cycle commit prompts silently, at most 2–3 one-line bullets, halt/terminal announcements exempt. See `~/.claude/skills/lazy-batch/SKILL.md` Step 3 for the full template and rules.

**Cloud nuance (background dispatch).** A cloud cycle subagent may be dispatched to run in the background (HARD CONSTRAINT 9 references in-flight background cycle agents). When it is, the ONLY output permitted before the result block is a SINGLE terse line — `▶ Cycle {N}/{max_cycles} · {feature_name} · {sub_skill} (dispatched)` — with no following prose. Specifically do NOT narrate "running in the background", "waiting on the completion notification", or any commit-race reasoning while it runs (this is exactly the noise the discipline removes). When the cycle completes, emit the canonical result block.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

**Identical dual-path shape to `/lazy-batch` Step 4.** Two paths gated by `allow_research_skip`: default (strict halt on first `needs-research`, inline-prompt announcement, STOP) and opt-in (`--allow-research-skip`, drop sentinel, advance loop, halt later on `queue-blocked-on-research`). See `~/.claude/skills/lazy-batch/SKILL.md` Step 4 for the full algorithm.

### Stub specs vs structured-research-pending specs (disambiguation rule)

Identical to `/lazy-batch` Step 4's disambiguation block (mirrored per the CLAUDE.md coupling rule — see `~/.claude/skills/lazy-batch/SKILL.md` Step 4 for the full rationale and the two-row table). Summary: `needs-research` fires ONLY for structured-but-research-pending specs (baseline locked, deep research missing). Stub specs (no baseline yet — detected by `is_stub_spec(spec_text, queue_entry)` in `lazy-state.py`: canonical `> Draft (pre-Gemini)` trailer, queue.json `"stub": true`, or a legacy marker) are routed at Step 4.5 instead and dispatched as a normal `/spec` cycle. The dispatched `/spec` subagent can call `AskUserQuestion` during Phase 1 brainstorming — HARD CONSTRAINT 5 binds the orchestrator only, not subagents it dispatches. **Cloud parity note:** the docs-only stub detection works identically in cloud (no Tauri / no MCP server required); the dispatched `/spec` cycle inherits the cloud cycle-subagent limitations documented in HARD CONSTRAINT 9 (no recursive `Agent` dispatch — `/spec` runs inline edits inside the cycle subagent itself).

**Cloud divergences:**

- **`written_by` in the sentinel frontmatter is `lazy-batch-cloud`** (not `lazy-batch`). The rest of the YAML matches:

  ```yaml
  ---
  kind: needs-research
  feature_id: {feature_id}
  research_prompt_path: <relative path>
  written_by: lazy-batch-cloud
  date: <today>
  ---
  ```

- **Default-path halt announcement uses `/lazy-batch-cloud` in the chat heading and re-invoke line.** Replace every `/lazy-batch` token in the announcement template with `/lazy-batch-cloud`. The fenced ```text prompt block and char-count over/under indicator (against the 24,000-char Gemini cap) are unchanged. The "FASTEST RESUME" block (in-session chat upload → /ingest-research → re-invoke) is identical, only the re-invoke command name differs.

- **The cloud announcement reorders the alternative upload paths to reflect cloud reality.** In cloud:
  - **Path ① (staged .txt)** is gitignored and therefore NON-DURABLE across container reclaim unless ingested in-session. Surface this with the prefix `(gitignored — non-durable unless ingested in-session; in-session resume above does that automatically)`.
  - **Path ② (direct RESEARCH.md drop)** is durable. Recommended fallback when not using the in-session resume.
  - **Path ③ (`/ingest-research <path>`)** is workstation-only — cloud cannot reach file paths outside the container's repo working tree. Surface as `(workstation only)`.

- **In-session resume is the primary cloud-recommended path.** The default-path announcement's "FASTEST RESUME" block (per Step 5) is the load-bearing cloud durability guarantee: `/ingest-research` runs in-session and writes the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` BEFORE the cloud container is reclaimed. Without this protocol, a cloud user uploading a `.txt` to the gitignored staging dir would lose the file on reclaim.

Cloud cannot run Gemini itself — but the user provides research via any of the upload paths the announcement lists. Step 5 (in-session resume), Step 0.5's pre-loop check, and the natural state-script flow handle each path appropriately.

---

## Step 5: In-Session Resume Protocol (research uploaded via chat)

**Identical to `/lazy-batch` Step 5** — see `~/.claude/skills/lazy-batch/SKILL.md` Step 5 for the full algorithm. Summary:

1. User uploads research in their NEXT MESSAGE after a Step 4 / Step 1f halt (file attachment, pasted text, or absolute path).
2. Assistant correlates each upload to a pending feature (single AskUserQuestion permitted at this boundary if multi-feature ambiguity exists).
3. Materialize content into `docs/gemini-sprint/results/<feature_id>.txt`.
4. Dispatch `/ingest-research` as a Sonnet subagent. This writes the tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` into the feature directory, clears the `> Draft (pre-Gemini)` SPEC trailer, clears `queue.json "stub": true`, moves consumed `.txt` to `_consumed/`, and commits per feature.
5. Re-invoke `/lazy-batch-cloud <N>` automatically (where `<N>` is the original `max_cycles`).
6. Print a brief resume status line so the user sees the bridge.

**Cloud-specific load-bearing rationale.** The `docs/gemini-sprint/results/` staging dir is gitignored. A bare `.txt` stage in cloud does NOT survive container reclaim. Step 5's in-session ingestion converts the non-durable staged `.txt` into the durable tracked `RESEARCH.md` + `RESEARCH_SUMMARY.md` BEFORE the container can be reclaimed — that is the cloud durability guarantee for the chat-upload path. Workstation users get the same convenience but without the durability stakes (their staged `.txt` survives between sessions on local disk).

**Cycle accounting at resume.** Same as `/lazy-batch` — each `/lazy-batch-cloud <N>` invocation is an independent bounded run. The re-invocation starts with a fresh `max_cycles` budget.

HARD CONSTRAINT 7 (no active waiting) still holds: the halt is clean, the resume is single-turn-event-driven (the user's next chat message), and nothing polls the filesystem between halt and resume.

---

## Differences from `/lazy-batch`

| Aspect | `/lazy-batch` | `/lazy-batch-cloud` |
|--------|---------------|---------------------|
| State script invocation | `python3 ~/.claude/scripts/lazy-state.py [--skip-needs-research]` | `python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]` |
| `cloud-queue-exhausted` terminal | defensive (unreachable in practice) | normal halt when remaining features await workstation MCP testing |
| `__write_deferred_non_cloud__` pseudo-skill | not emitted by state script | normal Step 8 action — handled INLINE in Step 1c.5, no subagent dispatch |
| `__write_validated_from_results__` pseudo-skill | normal Step 8 action — inline | not emitted (cloud cannot produce MCP results) |
| `__flip_plan_complete_cloud_saturated__` pseudo-skill | listed in Step 1c.5 handlers as defensive (rare under workstation execution; included so any future state-script change that emits it under `--cloud=false` is still handled). | normal Step 7a action — emitted by `lazy-state.py --cloud` when an In-progress plan's only unchecked WUs are documented as workstation-only in `DEFERRED_NON_CLOUD.md`. Handled INLINE in Step 1c.5, no subagent dispatch. Prevents the `Step 7a: execute plan` no-op loop. |
| No-premature-Complete guard (SPEC/PHASES `**Status:**`) | **NOW MIRRORED (was a divergence).** Workstation's Step 1d cycle prompt carries a "No premature Complete (PIPELINE-GATE HONESTY)" guard: the cycle subagent MUST NOT flip top-level SPEC/PHASES `**Status:**` to `Complete` — reserved for `__mark_complete__` after /retro → /mcp-test (VALIDATED.md) → coverage audit. Added because an `/execute-plan` cycle flipping `Complete` itself was observed to roll the queue forward and SILENTLY SKIP the /retro + /mcp-test + coverage-audit tail. | both the cycle subagent prompt (Step 1d "No premature Complete") and the `__mark_complete__` inline handler (Step 1c.5) FORBID the cycle subagent flipping SPEC/PHASES top `**Status:**` to `Complete` under ANY condition; doubly enforced when `DEFERRED_NON_CLOUD.md` exists and `VALIDATED.md` is absent — MCP validation is deferred to a workstation pass in cloud, so `Complete` before it runs is dishonest. Honest terminal cloud state is `In-progress`. `/lazy-batch-retro` adds matching low-severity rule **R-C-4**. |
| Cycle subagent prompt (real skills only) | bare batch-mode instructions; cycle subagent honors each dispatched skill's sub-subagent contract (e.g. /execute-plan → Sonnet test-agent + impl-agent fanout, /retro → research subagents A–G) | adds cloud-environment limitations block AND a cloud-override block: cycle subagent has NO `Agent` tool (no recursive dispatch), so it performs all source/test edits and research INLINE using Edit / Write / Read, SUPERSEDING each dispatched skill's sub-subagent contract. Per-skill overrides (/execute-plan, /retro, retro-feature) are enumerated in the prompt template. **Known cloud limitation:** collapsing /execute-plan's test-agent→impl-agent split into one inline subagent trades away the STRUCTURAL test-first guarantee (the cycle subagent must still write tests-before-impl by discipline). Compensating controls: per-batch quality gates + workstation /retro + deferred MCP-validation pass. `/lazy-batch-retro` Step 4b cloud branch grades the corresponding R-EP-2/R-EP-3 as `n/a (cloud-override)`, not `fail`. |
| Ground-truth re-run (subagent-review.md Step 1.5) | **performed** — the orchestrator/review subagent re-runs each Sonnet sub-subagent's reported commands (git status / wc -l / grep / test runner) and diffs to detect falsified reports. Valuable because the implementer is a *separate* untrusted subagent. | **CLOUD-SCOPED DIVERGENCE — skipped.** In the inline path the cycle subagent wrote both tests and implementation itself, so there is no separate subagent report to police — the mechanical re-run is pure redundant work. The cloud /execute-plan override drops it (substantive correctness + propagation review still run). Consistent with `/lazy-batch-retro` already grading R-EP-4 as `n/a (cloud-override)` for cloud cycles. |
| Cycle subagent prompt — loop-guard (LOOP DETECTED block) | appended when prev_cycle_signature matches current (feature_id, sub_skill, sub_skill_args, current_step). **Same shape** in both. | appended on same condition; same block text — both orchestrators share the loop-break protocol. |
| Cycle subagent model selection | normal cycles → `model: "opus"`. LOOP DETECTED branch → `model: "sonnet"`. **Same in both** — the loop-resolution work is mechanical (read sentinel schema, identify which sentinel preconditions are met, write it, commit), and the diagnosis is already in the prompt. Sonnet handles it at ~5× the cost-efficiency. | same as workstation. |
| Cycle output discipline (Step 3) | **MIRRORED** — every cycle emits exactly ONE `### Cycle N/{max} · {feature} · {sub_skill}` heading + `**Result:**` / `**Commit:**` bullet block; no dispatch- or commit-strategy narration; between-cycle commit prompts ignored silently; halt/terminal announcements exempt. **Same shape** in both. | same block + rules, PLUS one cloud-only allowance: a backgrounded cycle may print a SINGLE terse `▶ Cycle N/{max} · {feature} · {sub_skill} (dispatched)` line before its result block — still no "running in the background" / "waiting on notification" / commit-race prose. |
| Forward-progress verification (Step 1.5 / "Step 2.5") | after loop exit, before final batch report. One additional read-only `lazy-state.py` invocation; compares probe tuple to `prev_cycle_signature`; prepends ✅ or ⚠ block to Step 2 report. Skipped on `blocked` / `needs-input` / `queue-missing`. **Same shape** in both. | same as workstation, but the WARNING block lists cloud-specific likely-cause bullets (notably the cloud-saturated In-progress → Complete plan-flip that `__flip_plan_complete_cloud_saturated__` exists to perform). |
| NEEDS_RESEARCH.md `written_by` | `lazy-batch` | `lazy-batch-cloud` |
| `--allow-research-skip` argument | parsed in Step 0; gates Step 4 path + Step 1a `--skip-needs-research` flag. **Same semantics** in both. | same as workstation — strict halt on first `needs-research` by default; opt in to batched-research via the flag. |
| Step 4 — default path (strict halt) | reads RESEARCH_PROMPT.md, prints fenced ```text inline halt announcement, PushNotifications, halts. **Same shape** in both. | same as workstation, but the announcement says `/lazy-batch-cloud` and upload path ③ is labeled `(workstation only)`. |
| Step 4 — opt-in path (`--allow-research-skip`) | drops sentinel, flips `skip_needs_research = true`, returns to loop. **Same shape** in both. | same as workstation; sentinel `written_by: lazy-batch-cloud`. |
| Research-wait mode (Step 1f) | passive halt — `terminal_reason: queue-blocked-on-research`. Reachable only under `--allow-research-skip`. Prints inline RESEARCH_PROMPT.md content for every pending feature, announces upload paths including in-session resume, PushNotification, STOP. Resume on next chat message (Step 5) OR next `/lazy-batch` invocation. **Same shape** in both. | passive halt — same as workstation, with cloud-specific path reordering: in-session resume primary, ② durable fallback, ① gitignored/non-durable, ③ workstation-only. |
| Decision-resume mode (Step 1g) | `terminal_reason: needs-input` — **NOT a halt** in either variant. AskUserQuestion → append Resolution → commit → dispatch Sonnet apply-resolution subagent (edits SPEC/PHASES, neutralizes sentinel) → return to Step 1a. **Same shape** in both. | same shape as workstation. SPEC/PHASES edits are docs-only, no cloud limitations apply. |
| Post-cycle input audit (Step 1d.5) | **MIRRORED** — after every `/spec` or `plan-feature` cycle, dispatch a dedicated Opus input-audit subagent that reads SPEC.md / RESEARCH.md / cycle diff, independently re-classifies every decision against the product-behavior smells checklist (aggressive bias), verifies the cycle subagent's Decision-Classification Ledger, and writes `{spec_path}/NEEDS_INPUT.md` if any product-behavior calls were baked in silently. The auditor is scope-restricted to writing the sentinel — no source/test edits, no recursive dispatch. Surfaced decisions resolve inline on the next cycle via Step 1g (no loop halt). **Same shape** in both. | same as workstation — auditor is docs-only and dispatched by the orchestrator (which retains `Agent` even though the cycle subagent's cloud-override removes it). Sentinel commit + push folds into guardrail B / C. |
| In-Session Resume Protocol (Step 5) | chat-driven resume path for research uploads. User uploads research in next message → assistant materializes into staging dir → dispatches `/ingest-research` Sonnet subagent in-session → re-invokes `/lazy-batch` automatically. **Same shape** in both. | same shape as workstation, with the cloud-durability framing: in-session ingestion is the only path that writes tracked files (RESEARCH.md + RESEARCH_SUMMARY.md) before cloud-container reclaim. Re-invocation uses `/lazy-batch-cloud`. |
| Pre-loop ingest check (Step 0.5) | probes `docs/gemini-sprint/results/` at session start; dispatches `/ingest-research` as cycle 1 if staged `.txt` exists. **Same shape** in both. | same as workstation — `/ingest-research`'s hard constraints make it docs-only and cloud-safe. |
| Ad-hoc enqueue (Step 0.45, `--adhoc`) | **MIRRORED (shared component `_components/adhoc-enqueue.md`)** — when `--adhoc` is supplied, a one-time pre-loop bootstrap calls `lazy-state.py --enqueue-adhoc` (Bash) to prepend the referenced work to `queue.json`, seed `ADHOC_BRIEF.md`, and add a ROADMAP row; the first cycle's commit+push carries the bootstrap files. | same shared component + trigger, PLUS an immediate `git push` of the bootstrap right after enqueue (folds into guardrail B's per-batch push) so the new queue entry + brief survive container reclaim before the first cycle commits. |
| Resume-time remote sync (Step 0.4, guardrail A) | **MIRRORED** — `git fetch origin <branch>` + `git merge --ff-only` before the first state probe; halt-on-divergence (no clobber). Workstation framing: a resumed/interrupted session, or a remote advanced by another machine, can leave local behind. **Same shape** in both. | same algorithm; cloud framing is container-reclaim → stale local snapshot. This is the load-bearing recovery for the reclaim-mid-cycle data-loss mode. |
| In-cycle batch-level push (guardrail B) | **CLOUD-SCOPED DIVERGENCE — not mirrored.** Workstation cycle subagents already push at end-of-cycle (Step 1d "commit … and push to the current branch"), and local commits survive an interrupted workstation session, so per-batch (vs per-cycle) push granularity buys no durability on a persistent disk. | cycle subagent prompt (Step 1d) requires `git push origin <work-branch>` after EACH batch / work-unit commit (4× backoff retry, work-branch only, never main/force) — including the per-WU checkbox-tick commits (see "Early + granular plan-part status" row). Shrinks reclaim-loss exposure from "entire cycle runtime" to "one batch" — acute only because the cloud container is ephemeral and reclaim-prone. |
| Post-cycle push backstop (guardrail C) | **MIRRORED** — after every cycle (real-skill Step 1e AND inline pseudo-skill Step 1c.5) the orchestrator pushes / verifies-up-to-date the work branch (4× backoff, work-branch only). A `git push` of already-committed work is not a Write/Edit, so HARD CONSTRAINT 1 holds. **Same shape** in both. | same as workstation; on cloud it is the backstop behind guardrail B's per-batch pushes (normally a no-op "up to date"). |
| Early + granular plan-part status (Ready → In-progress before WU work; per-WU checkbox ticks; prefer parseable `- [ ]` WUs) | **MIRRORED (shared)** — `/lazy-batch` Step 1d cycle prompt requires the dispatched skill to flip the plan part `status:` `Ready` → `In-progress` and commit BEFORE starting WU work, tick + commit each `- [ ]` → `- [x]` checkbox as the WU lands, and prefer parseable checkbox-per-WU authoring so an interrupted session resumes per-WU. Helps both environments. **The per-commit PUSH of each flip/tick is cloud-only** (workstation relies on end-of-cycle push + local-commit survival). | same shared status-flip + checkbox-tick discipline, PLUS each flip/tick is pushed immediately (folds into guardrail B's per-WU push) so the granularity survives container reclaim, not just interruption. |
| Resume-reconciliation step (Step 0.6) | **CLOUD-SCOPED DIVERGENCE — not mirrored.** A killed/interrupted workstation session keeps its local commits and dirty tree on persistent disk, and Step 0.4's ff-sync covers the remote-advanced case; there is no reclaim residue to reconcile. | new Step 0.6, mandatory every invocation and after any `SessionStart:resume`: (a) push unpushed commits; (b) read-only `lazy-state.py --cloud` probe; (c) detect "finished-but-not-finalized" (WUs committed/pushed but frontmatter still Ready/In-progress) and handle with a SHORT finalize dispatch instead of full re-execution; (d) reconcile a killed agent's dirty working tree (keep + finish correct partial work, never wholesale-discard). |
| No waiting on dead notifications (HARD CONSTRAINT 9) | **CLOUD-SCOPED DIVERGENCE — not mirrored.** No container-reclaim boundary exists on workstation, so a background cycle agent's completion notification is never lost; the concept does not apply. | new HARD CONSTRAINT 9: after any `SessionStart:resume` the orchestrator MUST treat an in-flight background cycle agent as "unknown — reconcile from git + lazy-state" (Step 0.6), never "still running, awaiting notification." A completion notification cannot cross a reclaim boundary. This is the OPPOSITE of HARD CONSTRAINT 7 (forbids passively blocking on a dead signal), not a violation of it. |

All other behavior is identical — coupling is enforced by the state script (one source of truth), not by duplicated prose between the two orchestrators. Step 1c.5 (inline pseudo-skill handling) is shared shape; only the set of pseudo-skills emitted by the state script differs. Step 1f and Step 1g are also shared shape; both orchestrators reach them via the same state-script terminal reasons.

---

## Notes

- Coupling rule from CLAUDE.md: `/lazy-batch` ↔ `/lazy-batch-cloud` are coupled the same way `/lazy` ↔ `/lazy-cloud` are. Changes to one MUST be mirrored in the other unless explicitly cloud-scoped per the table above.
- The orchestrator never invokes the work-log tool directly. Cycle subagents log their own work.
- No persistence layer — restart is free. Sentinel files capture all durable state.
