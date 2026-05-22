---
name: lazy-batch-cloud
description: Cloud-environment variant of /lazy-batch. Loops on lazy-state.py --cloud and spawns Opus subagents per cycle, deferring any step that requires the Tauri desktop or MCP HTTP server. Halts on BLOCKED.md, needs-research (strict halt by default — the first research-pending feature stops the queue; opt into batched research with --allow-research-skip), queue-blocked-on-research (only reachable under --allow-research-skip), cloud-queue-exhausted, or max-cycles cap. NEEDS_INPUT.md (design decisions) does NOT halt: Step 1g calls AskUserQuestion, dispatches a Sonnet apply-resolution subagent to propagate the choice into SPEC/PHASES, and resumes the loop. Research uploaded mid-session via chat triggers in-session resume: /ingest-research is dispatched immediately (writing the tracked RESEARCH.md + RESEARCH_SUMMARY.md — critical because docs/gemini-sprint/results/ is gitignored and bare .txt stages do not survive cloud-container reclaim) and the loop is re-invoked — no manual re-run required.
argument-hint: <max-cycles, e.g. 10> [--allow-research-skip]
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

**Per-cycle dispatch order:** `/spec` → `/spec-phases` → `/write-plan` → `/execute-plan` → `/retro` (Step 8, cloud-runnable) → `/mcp-test` (Step 9, cloud defers) → mark-complete (Step 10, cloud halts).

This skill is coupled to `/lazy-batch` per CLAUDE.md — their only intended divergences are documented in the "Differences from /lazy-batch" block below.

---

## HARD CONSTRAINTS (non-negotiable)

Identical to `/lazy-batch`:

1. The orchestrator MAY use `Write`/`Edit` ONLY on sentinel files (`BLOCKED.md`, `DEFERRED_NON_CLOUD.md`, `VALIDATED.md`, `NEEDS_RESEARCH.md`, `NEEDS_INPUT.md`, `RETRO_DONE.md`, `SKIP_MCP_TEST.md`, `MCP_TEST_RESULTS.md`) inside `docs/features/`, AND on `ROADMAP.md` / per-feature `SPEC.md` status lines when performing the `__mark_complete__` action. `NEEDS_INPUT.md` may additionally be **appended to** (not overwritten) with a `## Resolution` section by Step 1g (decision-resume mode) after `AskUserQuestion` returns; the orchestrator then dispatches a Sonnet subagent to propagate the choice into SPEC.md / PHASES.md and neutralize the sentinel. All other `Write`/`Edit` operations require subagent dispatch (the Step 1g apply-resolution subagent is the dispatch that authorizes the SPEC/PHASES edits flowing from a decision).
2. The orchestrator MUST NOT invoke any `/skill` directly via the `Skill` tool. Every sub-skill goes through a spawned `Agent` subagent. Pseudo-skills (`__*__`) are not real skills and are handled inline per Step 1c.5 — they are sentinel-file edits + commits, not skill dispatches.
3. The orchestrator MUST NOT manually parse SPEC.md, PHASES.md, or plan files. State inference is exclusively via `lazy-state.py --cloud`. Sentinel files MAY be read by the orchestrator to confirm a write or drive a pseudo-skill action.
4. One cycle = one subagent dispatch FOR REAL WORK SKILLS. Pseudo-skill cycles (sentinel writes) are inline orchestrator actions that count as one cycle each.
5. **Interactive prompts are scoped to decision-resume mode (Step 1g) ONLY.** Outside Step 1g, the orchestrator MUST NOT call `AskUserQuestion`. Inside Step 1g, the orchestrator MUST `AskUserQuestion` against a well-formed `NEEDS_INPUT.md` (rich body per `~/.claude/skills/_components/sentinel-frontmatter.md`), append a `## Resolution` section, dispatch the apply-resolution subagent, and then **continue the loop** — Step 1g no longer halts the orchestrator. The user retains decision-making autonomy via `AskUserQuestion`, the apply step is mechanical propagation.
6. **The orchestrator MUST re-print the rich `## Decision Context` to chat BEFORE calling `AskUserQuestion`.** `AskUserQuestion` truncates option descriptions in its UI; the chat re-print is the load-bearing context. Never call `AskUserQuestion` against a malformed `NEEDS_INPUT.md` — surface the malformation as a quality issue and halt instead (see Step 1g.1).
7. **NEVER actively wait for filesystem events.** The orchestrator MUST NOT use `Monitor`, `sleep`, `wait`, polling loops, or any other mechanism to block while research is uploaded. Research arrives on the user's own timeline — they may be away from their device for hours or days. When `queue-blocked-on-research` or `needs-research` fires, the orchestrator halts cleanly (Step 1f / Step 4). The resume signal is chat-driven, not filesystem-driven: if the user's next message in the same conversation supplies research (file attachment, pasted text, or absolute path), the in-session resume protocol (Step 5) fires immediately; otherwise the user's next `/lazy-batch-cloud` invocation is the resume signal. Responding to a chat message is NOT polling — it is a single-turn event, not an active wait.
8. **The `cycle` counter is session-global and monotonic across feature transitions.** Identical to `/lazy-batch` HARD CONSTRAINT 8: `cycle` is initialized to 0 in Step 0 *once per `/lazy-batch-cloud` invocation* and incremented at the end of every cycle (Step 1c.5 step 4, Step 1e, Step 1g step 7). It MUST NOT be reset when `lazy-state.py --cloud` returns a different `feature_id` from one cycle to the next — i.e., when the queue advances from one feature to the next (via `__mark_complete__`, or because the prior feature hit `cloud-queue-exhausted`'s precondition and a later queue entry became current, or because the prior feature's `__write_deferred_non_cloud__` finished and the script rolled forward). Cycle N's status line — `"Cycle N/{max_cycles}: {sub_skill} on {feature_name} → ..."` — always refers to the N-th subagent dispatch in this `/lazy-batch-cloud` invocation, regardless of which feature it operated on. A feature transition is **not** a fresh batch.

**Cloud-specific:** the cycle subagent operates under the same cloud-environment limitations documented in `/lazy-cloud` — no Tauri runtime, no MCP HTTP server, no audio device, no Windows-only tooling. The cycle subagent's prompt (Step 1d below) makes this explicit.

---

## Step 0: Parse Arguments

Same shape as `/lazy-batch` Step 0. `$ARGUMENTS` is tokenized:
- positive integer → `max_cycles` (default `10`)
- `--allow-research-skip` (optional) → `allow_research_skip = true` (default `false`)

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

## Step 0.5: Pre-loop staged-research ingest check

**Identical to `/lazy-batch` Step 0.5** — before entering the main loop, probe for staged `.txt` files in `docs/gemini-sprint/results/` and dispatch `/ingest-research` as cycle 1 if any exist. This is the "resume after halt" entry point that lets the user upload research between sessions without any active waiting.

See `~/.claude/skills/lazy-batch/SKILL.md` Step 0.5 for the full algorithm. Cloud-specific nuance: none — `/ingest-research`'s hard constraints already scope it to `docs/`-only writes (no Tauri / no MCP runtime required), so it runs identically in cloud and workstation.

---

## Step 1: Cycle Loop

Initialize per-session state — identical shape to `/lazy-batch` Step 0:
- `cycle = 0` — initialized once per `/lazy-batch-cloud` invocation; monotonic across feature transitions (HARD CONSTRAINT 8 — never reset when `lazy-state.py --cloud` returns a new `feature_id`).
- `allow_research_skip = <parsed>` — see Step 4 + Step 1f for the behavior switch.
- `research_pending = set()` — feature_ids that hit `needs-research` this session. Only used when `allow_research_skip == true`; empty under the default strict-halt path.
- `skip_needs_research = false` — flips to `true` after the first `needs-research` cycle **only when `allow_research_skip == true`**. Stays `false` under the default path.
- `prev_cycle_signature = None` — tuple `(feature_id, sub_skill, current_step)` from the most recent cycle (pseudo-skill or real-skill). Drives the Step 1d loop-guard hint. `None` until at least one cycle has dispatched.

### 1a. Run lazy-state.py --cloud

```bash
python3 ~/.claude/scripts/lazy-state.py --cloud [--skip-needs-research]
```

Pass `--skip-needs-research` **only when `allow_research_skip == true` AND `skip_needs_research == true`**. Under the default strict-halt path the flag is never added, so the script returns `terminal_reason: needs-research` for the first research-pending feature in queue order — see `~/.claude/skills/lazy-batch/SKILL.md` Step 1a for the double-gate rationale. Parse JSON output as in `/lazy-batch`.

### 1b. Handle terminal states

Same handling as `/lazy-batch` for `blocked`, `needs-input`, `needs-spec-input`, `queue-missing`, `all-features-complete`. Cloud-specific:

- **`needs-input`**: see Step 1g (decision-resume mode — identical to `/lazy-batch` Step 1g). **Not a terminal state for the orchestrator anymore** — Step 1g resolves the decision via `AskUserQuestion`, dispatches the Sonnet apply-resolution subagent, and returns to Step 1a. Do NOT print the final batch report.
- **`cloud-queue-exhausted`**: PushNotification `"Cloud queue exhausted after {cycle} cycle(s) — N feature(s) awaiting workstation /lazy for MCP test."` Print final batch report, STOP.
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
- **`__mark_complete__`** — only reachable from cloud if both `VALIDATED.md` and `RETRO_DONE.md` already exist (cloud cannot produce VALIDATED.md from MCP results — workstation did). Update `docs/features/ROADMAP.md` (strikethrough + COMPLETE token), delete `VALIDATED.md`/`RETRO_DONE.md`/`DEFERRED_NON_CLOUD.md` sentinels, set `<spec_path>/SPEC.md`'s `**Status:**` to `Complete`, then commit per project policy.

After the inline action:

1. Append to `cycle_log`: `{cycle+1, feature_name, sub_skill, "inline: <one-line summary>"}`.
2. Print a one-line cycle status: `"Cycle {cycle+1}/{max_cycles}: {sub_skill} on {feature_name} → <inline outcome>"`.
3. Update `prev_cycle_signature = (feature_id, sub_skill, current_step)` (same uniform post-cycle update as Step 1e — keeps the loop-guard accurate across mixed pseudo-skill / real-skill cycles).
4. Increment `cycle`. Return to Step 1a — DO NOT fall through to Step 1d.

### 1d. Compose and dispatch the cycle subagent (REAL SKILLS ONLY)

If Step 1c.5 did not handle this cycle (i.e. `sub_skill` is a real skill name, not `__*__`), the cloud cycle subagent prompt adds an explicit reminder of cloud limitations.

**Loop-guard check (identical shape to `/lazy-batch` Step 1d):** BEFORE composing the prompt, compute the current cycle's signature as the tuple `(feature_id, sub_skill, current_step)`. If `prev_cycle_signature is not None` AND `prev_cycle_signature == (feature_id, sub_skill, current_step)`, append the **LOOP DETECTED** block below to the subagent prompt — the state script has returned the same triple two cycles in a row, almost always indicating a terminal sentinel (`RETRO_DONE.md`, `VALIDATED.md`, `DEFERRED_NON_CLOUD.md`, `SKIP_MCP_TEST.md`) is missing.

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

After the skill returns:
  1. Commit per .claude/skill-config/commit-policy.md (or standard pattern).
  2. Report a one-paragraph summary (under 8 lines).

You may NOT spawn further subagents. You MAY use Edit/Write on source code if
the dispatched skill requires it; follow the skill's internal subagent rules.
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
  model: "opus",
  prompt: <the prompt above>
})
```

### 1e. Record cycle outcome and loop

Same as `/lazy-batch`. Append to `cycle_log`, print one-line status, update `prev_cycle_signature = (feature_id, sub_skill, current_step)`, increment cycle, loop. The prev-signature update is the uniform post-cycle action that keeps the Step 1d loop-guard accurate across both real-skill and pseudo-skill cycles. **The cycle-counter increment is also a uniform post-cycle action that NEVER resets on feature transitions (HARD CONSTRAINT 8) — when the next `lazy-state.py --cloud` call returns a different `feature_id` (e.g. after `__mark_complete__`, after `__write_deferred_non_cloud__` rolls the queue to the next ready feature, or any other queue-advance), `cycle` continues incrementing from where it was.**

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

## Step 3: Status Bookend Discipline

Same as `/lazy-batch`. Per-cycle one-line status, compact for long batches.

---

## Step 4: Research Halt (terminal_reason == "needs-research")

**Identical dual-path shape to `/lazy-batch` Step 4.** Two paths gated by `allow_research_skip`: default (strict halt on first `needs-research`, inline-prompt announcement, STOP) and opt-in (`--allow-research-skip`, drop sentinel, advance loop, halt later on `queue-blocked-on-research`). See `~/.claude/skills/lazy-batch/SKILL.md` Step 4 for the full algorithm.

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
| Cycle subagent prompt (real skills only) | bare batch-mode instructions | adds cloud-environment limitations block |
| Cycle subagent prompt — loop-guard (LOOP DETECTED block) | appended when prev_cycle_signature matches current (feature_id, sub_skill, current_step). **Same shape** in both. | appended on same condition; same block text — both orchestrators share the loop-break protocol. |
| NEEDS_RESEARCH.md `written_by` | `lazy-batch` | `lazy-batch-cloud` |
| `--allow-research-skip` argument | parsed in Step 0; gates Step 4 path + Step 1a `--skip-needs-research` flag. **Same semantics** in both. | same as workstation — strict halt on first `needs-research` by default; opt in to batched-research via the flag. |
| Step 4 — default path (strict halt) | reads RESEARCH_PROMPT.md, prints fenced ```text inline halt announcement, PushNotifications, halts. **Same shape** in both. | same as workstation, but the announcement says `/lazy-batch-cloud` and upload path ③ is labeled `(workstation only)`. |
| Step 4 — opt-in path (`--allow-research-skip`) | drops sentinel, flips `skip_needs_research = true`, returns to loop. **Same shape** in both. | same as workstation; sentinel `written_by: lazy-batch-cloud`. |
| Research-wait mode (Step 1f) | passive halt — `terminal_reason: queue-blocked-on-research`. Reachable only under `--allow-research-skip`. Prints inline RESEARCH_PROMPT.md content for every pending feature, announces upload paths including in-session resume, PushNotification, STOP. Resume on next chat message (Step 5) OR next `/lazy-batch` invocation. **Same shape** in both. | passive halt — same as workstation, with cloud-specific path reordering: in-session resume primary, ② durable fallback, ① gitignored/non-durable, ③ workstation-only. |
| Decision-resume mode (Step 1g) | `terminal_reason: needs-input` — **NOT a halt** in either variant. AskUserQuestion → append Resolution → commit → dispatch Sonnet apply-resolution subagent (edits SPEC/PHASES, neutralizes sentinel) → return to Step 1a. **Same shape** in both. | same shape as workstation. SPEC/PHASES edits are docs-only, no cloud limitations apply. |
| In-Session Resume Protocol (Step 5) | chat-driven resume path for research uploads. User uploads research in next message → assistant materializes into staging dir → dispatches `/ingest-research` Sonnet subagent in-session → re-invokes `/lazy-batch` automatically. **Same shape** in both. | same shape as workstation, with the cloud-durability framing: in-session ingestion is the only path that writes tracked files (RESEARCH.md + RESEARCH_SUMMARY.md) before cloud-container reclaim. Re-invocation uses `/lazy-batch-cloud`. |
| Pre-loop ingest check (Step 0.5) | probes `docs/gemini-sprint/results/` at session start; dispatches `/ingest-research` as cycle 1 if staged `.txt` exists. **Same shape** in both. | same as workstation — `/ingest-research`'s hard constraints make it docs-only and cloud-safe. |

All other behavior is identical — coupling is enforced by the state script (one source of truth), not by duplicated prose between the two orchestrators. Step 1c.5 (inline pseudo-skill handling) is shared shape; only the set of pseudo-skills emitted by the state script differs. Step 1f and Step 1g are also shared shape; both orchestrators reach them via the same state-script terminal reasons.

---

## Notes

- Coupling rule from CLAUDE.md: `/lazy-batch` ↔ `/lazy-batch-cloud` are coupled the same way `/lazy` ↔ `/lazy-cloud` are. Changes to one MUST be mirrored in the other unless explicitly cloud-scoped per the table above.
- The orchestrator never invokes the work-log tool directly. Cycle subagents log their own work.
- No persistence layer — restart is free. Sentinel files capture all durable state.
