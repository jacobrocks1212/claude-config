# No first-class queue-reorder command — operator queue mutations must round-trip through a BLOCKED.md + apply-resolution subagent — Investigation Spec

> When the operator directs a queue reorder (e.g., move features to the tail), there is no sanctioned queue-reorder command in `lazy-state.py` / `bug-state.py`, and HARD CONSTRAINT 1 bars the orchestrator from editing `queue.json` directly. So the orchestrator turns a simple deterministic state mutation into a sentinel write (BLOCKED.md) plus a fully dispatched apply-resolution subagent — a whole meta-cycle to accomplish a reorder. This is a standing capability gap between HARD CONSTRAINT 1 and the absent reorder primitive.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/no-sanctioned-queue-reorder-command
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy-state.py` (`--enqueue-adhoc` exists; no reorder / defer-to-tail / remove primitive); `user/scripts/bug-state.py` (same gap, shares `lazy_core`); `user/skills/lazy-batch/SKILL.md` HARD CONSTRAINT 1 + Step 1h blocked-resolution; `user/scripts/lazy_parity_audit.py` (coupled-pair parity guard)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

1. **[VERIFIED — session log]** A simple operator-directed queue reorder had no first-class command, so the orchestrator routed it through a BLOCKED.md sentinel + a dispatched apply-resolution subagent — session `a0eae4be` @ `2026-06-18T15:39:39.548Z`: "No sanctioned queue-reorder script command exists, and HARD CONSTRAINT 1 bars me from editing `queue.json` directly — so I'll enact this through the established Defer mechanism: record the operator directive on a BLOCKED.md and dispatch an apply-resolution subagent to … move the 3 audio-analysis features to the queue tail." The orchestrator's own reasoning attests the gap directly: a deterministic `queue.json` mutation is forced into a sentinel write plus a full subagent dispatch because no reorder primitive exists.

2. **[VERIFIED — code]** No reorder / defer-to-tail / remove / reprioritize primitive exists in either state script. A grep of `lazy-state.py` for `--reorder|--defer|--remove|reorder|defer-to-tail|move.*tail|reprioritize` and the same over `bug-state.py` returns only the unrelated `--enqueue-adhoc` (insert-at-head) and `--per-feature-cycle-cap` (run-scoped, marker-gated, internal deferral). There is no operator-facing queue-position mutation command on either pipeline.

3. **[VERIFIED — contract]** HARD CONSTRAINT 1 in `lazy-batch/SKILL.md` (line 22) enumerates the orchestrator's `Write`/`Edit` scope (sentinels + `ROADMAP.md`/`SPEC.md`/`PHASES.md` status lines) and explicitly does NOT include `queue.json`. The same line names "queue reorder" as a Step 1h blocked-resolution path enacted by a dispatched Opus subagent — i.e. the BLOCKED.md round-trip is the *currently sanctioned* path, by design, in the absence of a primitive.

## Reproduction Steps

1. During an autonomous `/lazy-batch` (or `/lazy-bug-batch`) run, the operator directs a queue reorder ("move features X, Y, Z to the tail", "skip/remove item W", "bump item V to the front").
2. The orchestrator needs to mutate `queue.json` ordering, but HARD CONSTRAINT 1 forbids it from editing `queue.json` and no `lazy-state.py` subcommand performs the mutation.
3. **Observed result:** the orchestrator writes a `BLOCKED.md` recording the operator directive (Step 1h), then dispatches a full Opus apply-resolution subagent whose only job is to hand-edit `queue.json` and rename the sentinel — a complete meta-cycle for a deterministic reorder.

**Expected:** A first-class, operator-only, out-of-cycle `lazy-state.py` / `bug-state.py` subcommand performs the queue-ordering mutation deterministically (one `Bash` call), the same shape as `--enqueue-adhoc`, with no BLOCKED.md and no subagent dispatch.
**Actual:** Reorder is forced through BLOCKED.md + a dispatched apply-resolution subagent.
**Consistency:** Always — there is no alternative path; the gap is structural, not intermittent.

## Evidence Collected

### Source Code
- `user/scripts/lazy-state.py::enqueue_adhoc` (≈ line 330) — the ONLY sanctioned `queue.json` mutator on the feature side. It loads `queue.json`, validates the `queue` array, refuses duplicate ids, `insert(0, …)`s the new entry, and `_atomic_write`s the file. This is the exact pattern a reorder primitive should mirror: load → mutate the list → atomic write. It does NOT generalize to reorder/remove.
- `user/scripts/lazy-state.py` argparse (≈ line 6788) — `--enqueue-adhoc` is gated at dispatch by `lazy_core.refuse_if_cycle_active("--enqueue-adhoc")` (≈ line 7777): an operator-only, out-of-cycle command refused (exit 3, zero side effects) for a cycle subagent. This is the precedent gating model for the new command.
- `user/scripts/bug-state.py` — same gap; it shares `lazy_core` and its own `load_bug_queue` / queue write path. A reorder primitive must be added to BOTH scripts (or to a shared `lazy_core` helper both call) to keep the coupled pair at parity.
- `--per-feature-cycle-cap` (lazy-state.py argparse ≈ line 6829) — an EXISTING run-scoped, marker-gated, *internal* defer-to-tail mechanism (the budget guard reorders a feature to the live-queue tail when its per-feature cycle count trips). It is NOT operator-facing and NOT a persistent `queue.json` edit — it confirms the reorder *operation* is already understood and implemented internally, just not exposed as an operator command.

### Runtime Evidence
- Session `a0eae4be` @ `2026-06-18T15:39:39.548Z` (AlgoBooth, captured in the originating audit): the orchestrator's verbatim reasoning is the primary attestation — it names the absent command, names HARD CONSTRAINT 1 as the bar, and chooses the BLOCKED.md + apply-resolution-subagent workaround. This is the friction in the operator's own words.

### Git History
- Recent `claude-config` work is harness self-improvement (process-ownership primitives, coherence-recovery reconciliation, MCP-skip grants — see the last ~5 commits on `main`). No prior attempt at a reorder primitive; this is net-new surface.

### Related Documentation
- `user/scripts/CLAUDE.md` "CLI surface" — documents `--enqueue-adhoc`, `--per-feature-cycle-cap`, `--park-*`, `--materialize-wi`. A reorder primitive belongs in this same documented operator/out-of-cycle CLI surface.
- `lazy-batch/SKILL.md` HARD CONSTRAINT 1 + Step 1h — the contract that (correctly) forbids direct `queue.json` edits and (currently) routes reorder through BLOCKED.md. The fix REPLACES the reorder-via-BLOCKED.md path with a cheap deterministic command; HARD CONSTRAINT 1 itself stays intact (the orchestrator still never hand-edits `queue.json` — it calls the script).
- `user/scripts/lazy_parity_audit.py` — the coupled-pair guard; a primitive added to one script must appear in the other to stay green.

## Theories

### Theory 1: Missing operator-facing queue-mutation primitive (capability gap)
- **Hypothesis:** The orchestrator's only sanctioned `queue.json` mutation is `--enqueue-adhoc` (insert-at-head). There is no command to reorder / defer-to-tail / remove / reprioritize existing entries, so any such operator intent has no cheap deterministic path and must round-trip through BLOCKED.md + a dispatched subagent.
- **Supporting evidence:** Verified Symptoms 1–3; the code grep (Symptom 2) returns no such command; HARD CONSTRAINT 1 explicitly bars the direct edit (Symptom 3); the internal `--per-feature-cycle-cap` defer-to-tail proves the operation is already implementable but is not exposed.
- **Contradicting evidence:** None. The workaround works (it is not a correctness bug), but it is pure friction — a meta-cycle per reorder.
- **Status:** **Confirmed.**

## Proven Findings

**Root cause (CONFIRMED):** A capability gap between HARD CONSTRAINT 1 (orchestrator may not edit `queue.json` directly — correct, load-bearing) and the absent operator-facing queue-mutation primitive. `--enqueue-adhoc` covers only insert-at-head; nothing covers reorder/defer-to-tail/remove/reprioritize of existing entries. The result is that routine operator queue intent costs a BLOCKED.md sentinel write plus a full Opus apply-resolution subagent dispatch (a meta-cycle), instead of a single deterministic `Bash` call.

**Fix scope (the same end-state regardless of sizing — see policy note below):** Add an operator-only, out-of-cycle `--reorder-queue` subcommand to the shared queue-mutation surface, gated exactly like `--enqueue-adhoc` (`refuse_if_cycle_active` → exit 3 for a cycle subagent), present on BOTH `lazy-state.py` (features) and `bug-state.py` (bugs) via a shared `lazy_core` helper to satisfy the coupled-pair parity guard. It loads `queue.json` (or `docs/bugs/queue.json`), applies the requested ordering mutation to existing entries, and `_atomic_write`s — mirroring `enqueue_adhoc`'s load→mutate→atomic-write shape. The four operations the symptom and open questions enumerate (defer-to-tail, move/reorder, remove/skip, reprioritize) are folded into ONE primitive (a position/operation argument), not four separate flags. The consuming contracts (`lazy-batch` / `lazy-bug-batch` Step 1h) are updated so an operator-directed reorder calls the new command inline instead of writing BLOCKED.md + dispatching a subagent; HARD CONSTRAINT 1's no-direct-`queue.json`-edit rule is preserved (the orchestrator calls the script, never hand-edits the file). Smoke fixtures (`--test`) cover each operation, the cycle-active refusal, the idempotent/no-op case, and a malformed-id/missing-entry error; `user/scripts/CLAUDE.md` "CLI surface" documents the new subcommand.

⚖ policy: reorder/defer/remove/reprioritize scope → fold all four into one primitive (D7 most-complete)
⚖ policy: feature + bug parity → add to both scripts via shared lazy_core helper (D7 most-complete)

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Feature state machine | `user/scripts/lazy-state.py` | Add `--reorder-queue` argparse + dispatch (gated by `refuse_if_cycle_active`); add `--test` fixtures. |
| Bug state machine | `user/scripts/bug-state.py` | Mirror the same subcommand (coupled pair); add `--test` fixtures. |
| Shared helpers | `user/scripts/lazy_core.py` | New `reorder_queue(...)` helper (load→mutate→atomic-write) called by both scripts. |
| Parity guard | `user/scripts/lazy_parity_audit.py` | Assert the new subcommand exists on both scripts. |
| Orchestrator contracts | `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md` (Step 1h) | Replace the reorder-via-BLOCKED.md path with an inline call to the new command; HARD CONSTRAINT 1 prose unchanged (no-direct-edit preserved). |
| CLI docs | `user/scripts/CLAUDE.md` | Document the new operator/out-of-cycle subcommand in the "CLI surface" section. |

## Open Questions

(None blocking — the three originating open questions were scope/sizing, resolved in-cycle per the completeness-first policy and recorded as `⚖ policy:` lines above.)

- *(Resolved → fold-all-four)* Which operator queue mutations are first-class: reorder, defer-to-tail, remove/skip, reprioritize are ALL folded into the one `--reorder-queue` primitive (a position/operation argument), not split across flags.
- *(Resolved → mirror `--enqueue-adhoc` gating)* The command is operator-only / out-of-cycle, gated by `refuse_if_cycle_active` exactly as `--enqueue-adhoc` and `--ack-unhardened` are.
- *(Deferred to `/plan-bug`)* The exact argument grammar (e.g. `--reorder-queue --id <id> --to {tail|head|<index>}` vs a JSON ordering spec) is an implementation-detail decision for the planning phase — it does not change the product end-state and is best fixed against the real argparse during `/write-plan`.
