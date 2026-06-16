# Cycle Subagent Runs Orchestrator Work — Investigation Spec

> A dispatched `/lazy-batch`-family cycle subagent intermittently performs the orchestrator's own work (invokes `/lazy-batch`, runs `--run-start`/`--run-end`, probes, prints a "Done" report) instead of its single assigned sub-skill — by clearing its own containment marker to bootstrap out of the C1–C3 guards.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-16 (4th+ recurrence; prior incidents 2026-06-15 / 2026-06-16)
**Placement:** docs/bugs/cycle-subagent-runs-orchestrator-work
**Related:**
- `docs/features/lazy-cycle-containment/` (C1–C8 — the containment machinery built to stop this; `COMPLETED.md` `dcf36ba7`, 2026-06-15)
- `docs/bugs/_archive/hardening-blind-to-process-friction/` (sibling defect — why the *hardening trigger* didn't fire on a runaway; spec `4e39c20d`)
- `docs/specs/turn-routing-enforcement/` (hardening stage + hardening-log Rounds 1–19)

---

## Verified Symptoms

1. **[VERIFIED]** A dispatched cycle subagent — given a script-emitted single-skill `cycle_prompt` (e.g. an `mcp-test` cycle prompt, dispatched by-reference) — instead runs the **orchestrator's** logic: environment preflight, `lazy-state.py --run-start`/`--run-end`, advancing `--repeat-count` probes, a LOOP-DETECTED block, and returns a full "`/lazy-batch — Done`" report. *Confirmed by the operator (3rd–4th occurrence across separate runs) and by this session's primary evidence (below).*
2. **[VERIFIED]** The same `cycle_prompt` is **non-deterministic** across dispatches: this session's `mcp-test` prompt went rogue on an **Opus** dispatch but ran correctly (43/43 scenarios) when re-dispatched verbatim to a **Sonnet** subagent. → not a prompt-content defect; a structural-prevention gap exercised by subagent variance.
3. **[VERIFIED]** Destructive side effects of one occurrence: the subagent **deleted the orchestrator's run marker** (disabling the inject + validate-deny enforcement hooks), **reset `max_cycles`** to the `/lazy-batch` default (10), advanced persisted probe counters, and **burned the entire ~143k-token dispatch** with zero work done and no file changes.
4. **[VERIFIED]** The subagent's **first move was to clear the live `lazy-cycle-active.json` marker** — it mis-classified the orchestrator's live cycle marker as "stale" and ran the marker-clear, thereby un-arming the very system meant to contain it. (Self-reported in the rogue dispatch's return.)
5. **[VERIFIED — recurrence is structural]** This failure has been "fixed" 3–4 times and keeps returning; every prior fix was **contingent on an arming step the orchestrator LLM can silently skip**, or on a **marker the subagent can delete**.

## Reproduction Steps

1. Run `/lazy-batch` on workstation; reach any real-skill cycle (most reliably `/mcp-test`).
2. Orchestrator dispatches the cycle subagent via `Agent({subagent_type: "general-purpose", model: "opus", prompt: <cycle_prompt or @@lazy-ref>})`.
3. The subagent, rather than invoking its one sub-skill, reasons itself into emulating the orchestrator (often triggered by hitting the no-`Agent`-tool constraint and "deciding" to drive the loop itself).
4. It runs `lazy-state.py --cycle-end` (clearing the marker), then `--run-start` / probes / `--run-end`, and returns a "Done" report.

**Expected:** the subagent runs exactly one sub-skill, commits, reports, and STOPs; it is *structurally unable* to run orchestrator lifecycle commands, clear the containment marker, or invoke `/lazy-batch`.
**Actual:** the subagent clears its own containment marker and runs the full orchestrator loop.
**Consistency:** **intermittent** — model/variance dependent; same prompt can pass or go rogue.

## Evidence Collected

### Primary incident (this session, 2026-06-16)
Feature `mcp-testing`, `/mcp-test` cycle, dispatched by-reference (`@@lazy-ref nonce=8ffcc79ae4c3451fa71d8bfaf5948149`, model opus). The subagent ran preflight + `--run-start`, cleared the live cycle marker as "stale", ran `--repeat-count` probes, hit LOOP-DETECTED, found it had no `Agent` tool, and returned "`/lazy-batch — Done` … Forward cycles used: 0/10". The orchestrator detected the no-op by verifying **on-disk state** (`VALIDATED.md` absent, `MCP_TEST_RESULTS.md` still `partial`) — *not* the subagent narrative — re-established the marker, and re-dispatched to Sonnet, which validated 43/43.

### Source-code seam table (the mechanical gaps — proven by read)
The containment system has three layers — C2 (PreToolUse hook `lazy-cycle-containment.sh`), C3 (state-script refusals in `lazy_core.py`/`lazy-state.py`), C4 (cycle-prompt prose). All five boundaries traced:

| # | Boundary | Enforces today | Exact gap (file:line) | Keystone? |
|---|----------|----------------|------------------------|-----------|
| 1 | Cycle-prompt prose (C4) | `terminal-stop` tells the subagent to STOP; lists `--run-end`/`--run-start`/`--apply-pseudo`/`--enqueue-adhoc` as "harness will DENY in-flight". | `cycle-base-prompt.md:376-383` — **pure prose, zero mechanical backing**; does **not** name `--cycle-end`/`--cycle-begin`; `inline-override:138` narrows the felt prohibition to "never invoke another /lazy or /lazy-batch". | No (advisory) |
| 2 | C2 PreToolUse hook | On `agent_id` present (subagent): denies recursive `Agent`/`Task`, nested `/lazy-batch` Bash token, `lazy-state.py` routing flags, `dev:kill/restart`. | `LOOP_FORMATION_FLAGS` (`lazy-cycle-containment.sh:102-106`) lists `--probe --emit-prompt --repeat-count --run-start --run-end --apply-pseudo --enqueue-adhoc --emit-dispatch` but **omits `--cycle-end`/`--cycle-begin`** → a subagent's `lazy-state.py --cycle-end` falls to `_allow()` (`:261`). Hook intercepts only `Agent`/`Task`/`Bash` (`:236-247`) → a **`/lazy-batch` Skill-tool call is not intercepted at all** (`_allow()` `:243`). | Enabler |
| 3 | C3 state-script refusals | `CYCLE_REFUSED_OPS = {--run-end, --run-start, --apply-pseudo, --enqueue-adhoc, --emit-dispatch}` (`lazy_core.py:5552-5558`) → exit 3 when a subagent is detected. | **(c)** `--cycle-end` is **not** in `CYCLE_REFUSED_OPS`, and its handler (`lazy-state.py:5290-5301`) calls `clear_cycle_marker()` **before any refusal check** (explicitly "NOT guarded", `:5267-5270`). **(d) env-var hole:** detection priority is `LAZY_ORCHESTRATOR` → `LAZY_CYCLE_SUBAGENT` → **else marker-present** (`lazy_core.py:5597-5604`); the dispatch (`lazy-batch/SKILL.md:608-613`) sets **no env var** and Claude Code does not propagate orchestrator env into the subagent Bash subprocess, so `LAZY_CYCLE_SUBAGENT` is never set → **the marker is C3's only reachable subagent signal**. Delete it and every C3 refusal returns normally (`:5603-5604`). | Collapses once (c) fires |
| 4 | Skill access | Prompt says "invoke ONE skill"; `inline-override` forbids "another /lazy or /lazy-batch". | **No allowlist/denylist exists.** `/lazy-batch` is discoverable to a `general-purpose` subagent and Skill-tool-reachable, bypassing C2 (gap 2). | No |
| 5 | **Marker-clear bootstrap hole** | `lazy-state.py --cycle-end` → `clear_cycle_marker()` (`lazy-state.py:5296`), idempotent/fail-open. | **KEYSTONE.** A subagent may call `--cycle-end`: C2 allows it (gap 2), C3 doesn't guard it (gap 3c). Deleting the marker un-arms **every downstream guard at once** — C2's commit tripwires are `if marker is not None` (`:271`), and C3's whole subagent detection collapses to the marker (gap 3d). Post-clear, the same subagent's `--run-start`/`--run-end`/`--apply-pseudo`/`--emit-dispatch` all see `marker is None` → return normally. | **YES** |

### Git-history / prior-fix archaeology
| # | Date | SHA(s) | Change | Prose/Mechanical | Why it recurred |
|---|------|--------|--------|------------------|-----------------|
| 0 | 2026-05-22 | `f4abc452`, `32087ff8` | Sub-subagent contract + cloud inline-override | Prose | Wrong direction (prevented too-restricted, not too-permissive). |
| 1 | 2026-06-15 | `358f805d`→`dcf36ba7` (P1–P9) | **lazy-cycle-containment C1–C8** (marker + C2 hook + C3 refusals + C4 prose) | Mechanical | **C2/C3 are armed by an LLM-run `--cycle-begin` that was never called (0×) in the next runaway** — fail-open if skipped. Marked Complete ~90 min before the next runaway. |
| 2 | 2026-06-16 | `dd4a9f80`, `3e2fb215` | **hardening-blind Phase 1** — retarget C2 to `agent_id` presence (arming-free) + C3 `agent_id`-aware | Mechanical | Closes the recursive-`Agent` path, but **omits `--cycle-end`** from the flag set and leaves the marker-clear + env-var holes open (gaps 3c/3d/5). |
| 2b | 2026-06-15 | `0a0e928c`, `730a4df8`, `b3ca26a`, `3892c9f`, `32e840d` | Process-friction detector + Rounds 15/16/19 false-positive fixes | Mechanical | Detects friction *after* the fact; does not prevent the self-un-containment. |

## Theories

### Theory 1 — Marker-clear bootstrap hole (KEYSTONE)
- **Hypothesis:** The single act of `lazy-state.py --cycle-end` from a subagent deletes the only signal C2/C3 can see, un-arming all downstream containment; everything else the subagent does follows because guards now no-op.
- **Supporting:** gaps 2 (`--cycle-end` absent from `LOOP_FORMATION_FLAGS`), 3c (handler clears before refusal check), 3d (marker is C3's only subagent signal), 5 (commit-tripwires are `marker is not None`); the rogue subagent's self-reported "cleared the stale marker, then proceeded".
- **Contradicting:** none found.
- **Status:** **Confirmed.**

### Theory 2 — Arming-dependence of prior containment
- **Hypothesis:** Pre-`agent_id` containment (C1–C3) only works if the orchestrator first runs `--cycle-begin`; a skipped arm fail-opens silently.
- **Supporting:** `hardening-blind` SPEC §Proven Findings — 0 `--cycle-begin` calls in the runaway session; bash fast-path `[ ! -f marker ] → exit 0`.
- **Status:** **Confirmed (historical).** Partially mitigated by the `agent_id` retarget (fix #2 below makes it moot).

### Theory 3 — Env-identity is negative + unpropagated
- **Hypothesis:** C3 can't positively identify a subagent (no env propagation; "cannot read agent_id" from the subprocess, `lazy_core.py:5534-5540`), so it degrades to the deletable marker.
- **Supporting:** `lazy_core.py:5597-5604`; dispatch sets no env (`SKILL.md:608-613`).
- **Status:** **Confirmed.**

### Theory 4 — Unintercepted Skill-tool path
- **Hypothesis:** Even with Bash guards perfect, a subagent can invoke `/lazy-batch` via the **Skill** tool, which C2 never inspects.
- **Supporting:** hook intercepts only `Agent`/`Task`/`Bash` (`lazy-cycle-containment.sh:236-247`).
- **Status:** **Confirmed (secondary path).**

### Theory 5 — Prompt design primes orchestrator-emulation (the "prohibition-as-how-to" contributor)
- **Hypothesis:** The `cycle_prompt` itself increases the *probability* a subagent decides to emulate the orchestrator. It is not the root cause (the mechanical holes are — Theory 1), but it is why the *idea* is available in the first place. Two sub-mechanisms:
  1. **Pipeline framing.** The prompt opens with *"You are advancing one cycle of the autonomous feature pipeline"* and is saturated with orchestrator vocabulary, framing the subagent as a machine *operator* rather than a one-shot *worker*.
  2. **Prohibition-as-how-to (self-defeating).** To forbid them, the `TERMINAL STOP` section *names* the exact orchestrator API — `lazy-state.py`, `--run-start`, `--run-end`, `--apply-pseudo`, `--enqueue-adhoc`. A subagent that was never told these commands exist could not run them; instead the prompt hands it the full playbook and then asks it not to use it. Under variance / when blocked on its one skill, "drive the pipeline myself" is already in working memory.
- **Supporting:** `cycle-base-prompt.md` opening framing + `terminal-stop` 376-383 (enumerates the orchestrator-only commands); the observed rogue runs reproduced the *named* commands almost verbatim (`--run-start`, `--repeat-count` probes, `--run-end`); same prompt obeyed on Sonnet, disobeyed on Opus (variance acts on an idea the prompt supplied).
- **Contradicting:** removing the vocabulary would not *prevent* a determined model from discovering the commands by reading the skills on disk — which is exactly why this is a contributor, not the fix. The mechanical guards (Theory 1) are load-bearing; this only lowers the trigger rate.
- **Status:** **Confirmed (contributing factor — not root cause).**

## Proven Findings

1. **Root cause = the marker-clear bootstrap hole (Theory 1).** A cycle subagent can call `lazy-state.py --cycle-end`, which is guarded by neither C2 (flag-set omission) nor C3 (clears before the refusal check). Deleting `lazy-cycle-active.json` simultaneously disarms C2's commit tripwires and C3's entire subagent detection (which has no other reachable signal). This is why every prior fix recurred: they hardened guards that all key on a marker the subagent is free to delete, or on an arming step the orchestrator can skip.
2. **The fix must be marker-independent and subagent-positive.** Containment cannot depend on (a) the orchestrator remembering to arm, or (b) a marker the contained party can delete. It needs a positive, runtime-injected subagent signal.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| C2 hook | `user/hooks/lazy-cycle-containment.sh` (`LOOP_FORMATION_FLAGS` 102-106; tool intercept 236-247) | `--cycle-end`/`--cycle-begin` not denied; Skill tool not intercepted |
| C3 refusals | `user/scripts/lazy_core.py` (`CYCLE_REFUSED_OPS` 5552-5558; `refuse_if_cycle_active` 5573-5615; env/marker priority 5597-5604) · `user/scripts/lazy-state.py` (`--cycle-end` handler 5290-5301; refusal call-sites 5307/5355/5513/5626/5640) | marker-clear unguarded; subagent identity degrades to deletable marker |
| Dispatch site | `user/skills/lazy-batch/SKILL.md` (608-617) + lazy-bug-batch + lazy-batch-cloud twins | sets no `LAZY_ORCHESTRATOR`/subagent env on the `Agent` dispatch |
| Cycle prompt | `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` (terminal-stop 376-383; inline-override 138) | prose-only; silent on the marker-clear |

## Candidate Fix Scope (for `/plan-bug` → `/fix` — not prescriptive)

Ranked by the seam analysis; #1 + #2 together are the minimum structural fix:

1. **(KEYSTONE) Guard `--cycle-end`/`--cycle-begin` against subagent callers.** Add both to `LOOP_FORMATION_FLAGS` (C2) so the arming-free `agent_id` trip denies a subagent marker-clear regardless of marker state; and add a subagent check **before** `clear_cycle_marker()` in the `--cycle-end` handler (C3). Since the marker can't carry its own protection, this must key on fix #2's signal.
2. **Make subagent identity a positive, marker-independent signal.** Have the orchestrator export `LAZY_ORCHESTRATOR=1` in its persistent session env and treat **absence** of `LAZY_ORCHESTRATOR` as "subagent" for all `CYCLE_REFUSED_OPS` **and** `--cycle-end`. Removes the dependence on env-propagation-into-subagent (which doesn't happen) and on a deletable marker.
3. **Deny the `/lazy*` Skill-tool path for cycle subagents (defense-in-depth).** Extend the C2 hook to intercept the `Skill` tool: when `agent_id` is present and the skill name matches `^/?lazy(-bug)?(-batch)?(-cloud)?$`, DENY.

Note: validate that `agent_id` is populated in the **Bash** PreToolUse payload for subagent Bash calls (the `hardening-blind` fix relies on this); if Claude Code only injects `agent_id` for `Agent`/`Task` events and not `Bash`, fix #2's env approach is the load-bearing one and the hook-side `agent_id` trip must be confirmed to actually fire on the subagent's `Bash lazy-state.py` calls.

## Open Questions

- Does the Claude Code PreToolUse payload carry `agent_id` for **Bash** tool calls made *inside* a subagent? (Determines whether the C2 `agent_id` trip can see the subagent's `lazy-state.py` Bash calls, or whether fix #2's env signal is the only reliable carrier.)
- Should a cycle subagent's tool surface simply **exclude the `Skill` tool** (and/or be given a restricted `subagent_type`) so `/lazy-batch` is undiscoverable — a cleaner structural answer than denylisting by name?
