# Feature Budget Guard + Skip-Ahead — Feature Specification

> Stop one stubborn feature from monopolizing a batch budget, and skip ahead to independent ready queue work past a blocked or research-gated head item.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-19

**Depends on:**

- unified-pipeline-orchestrator — composes — Reuses the merged-worklist ordering (`lazy_core.merged_priority` / `merged_worklist`) and the run-marker counter infrastructure (`forward_cycles` / `meta_cycles` / `max_cycles`) this feature extends with a per-item dimension.
- multi-repo-concurrent-runs — soft — Per-feature budget state must live in the per-repo keyed state dir (`claude_state_dir()` / `repo_key`); the guard reads/writes the run marker that machinery owns.

---

## Executive Summary

The `/lazy-batch` pipeline already has a **whole-run** budget ceiling (`max_cycles`, enforced as `forward_cycles >= max_cycles` at Step 1c) and a mechanical loop tripwire (`step_repeat_count >= 3` surfaces a T6 oscillation warning). What it lacks is a **per-feature** budget: a single stubborn feature can legitimately consume the entire run budget — burning every forward cycle on one item while the rest of the queue starves. Session `5c33b6ba` is the canonical incident: `d8-live-looping` consumed the entire extended 20→32 budget and ~5 MCP-validation blocks before being force-stopped, and the queue never advanced past it. The existing tripwire only *warns the orchestrator*; it takes no automatic per-feature action.

This feature adds two coupled mechanisms to the state machine (`lazy-state.py` / `lazy_core.py`, with thin orchestrator wiring in `/lazy-batch`):

1. **Per-feature budget guard** — a per-item forward-cycle counter, tracked in the run marker alongside the existing run-level counters, that trips a guard when one feature exceeds a configurable per-feature ceiling. On trip, the feature is **deferred to the back of the queue** (its progress preserved on disk) and the run advances to the next ready item, so one hard feature can no longer silently monopolize the batch.

2. **Skip-ahead past a gated head item** — when the queue head is blocked or research-gated, the orchestrator skips ahead to independent, ready queue items instead of stranding the whole queue behind it. This generalizes the existing opt-in `--allow-research-skip` (all-or-nothing batch research skip) into a default-on, dependency-aware skip that only advances onto items with **no unsatisfied upstream dependency** on the gated head.

Both mechanisms preserve the harness's deterministic-state-script-owns-state principle: the guard counter and skip-ahead readiness are computed by the state script from on-disk signals (the run marker counters + each SPEC's `**Depends on:**` block), never inferred by the orchestrator LLM.

## User Experience

The "user" here is the operator running `/lazy-batch <N>` (attended) or a scheduled unattended run. The feature is autonomous-pipeline plumbing; the user-visible surface is the run's behavior, the notifications it emits, and the new flag.

### Per-feature budget guard

- During a run, each feature accrues a per-feature forward-cycle count. When a feature's count crosses the per-feature ceiling, the guard trips:
  - The feature is **deferred to the back of the live queue** (a run-scoped reorder; its on-disk progress — SPEC/PHASES/plans/partial commits — is untouched and resumes when re-reached).
  - The orchestrator emits a PushNotification: `feature-budget-guard tripped — <feature-id> deferred to queue tail after <N> cycles (computed ceiling <L_task>); advancing to <next-id>`.
  - The deferral is recorded so the same feature cannot trip-and-defer in an infinite loop within one run (once deferred, it re-enters at most once at the tail; a second trip on the same feature in the same run escalates — see Open Questions).
- The ceiling is **computed dynamically** at run start (or when the feature reaches the queue head) via a fair-share formula `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`, where `C_global` is the run's `max_cycles` and `Q_depth` is the count of ready queue features. This bounds any single feature to ≤40% of the run budget while preserving a 6-cycle minimum execution floor, and adapts to both run size and queue depth with no new oracle (reuses `max_cycles` + queue length). The operator-facing trip notification reports the *computed* ceiling, not a fixed number. A `--per-feature-cycle-cap <N>` override flag forces a fixed ceiling when supplied. **Trip signal (locked): forward-cycles consumed (single signal)** — the guard trips when a feature's per-feature forward-cycle count crosses the computed ceiling. **On-trip action (locked): defer to back of queue** (run-scoped reorder) with bounded re-trip escalation. See Locked Decisions.

### Skip-ahead past a gated head

- When the queue head returns `needs-research` (or is `BLOCKED`), instead of halting the whole run, the orchestrator advances to the **next ready item** — defined as a queue item that satisfies BOTH guards: (a) its `**Depends on:**` block has no `hard` dependency on the gated head (or on any other currently-gated item), AND (b) it carries an explicit `independent: true` (a.k.a. `no_shared_state`) marker in its SPEC/queue entry. The marker is the shared-state isolation rail: research (Bazel/Buck2 evidence) shows human-declared dep blocks are routinely incomplete, and out-of-order execution on our shared, unsandboxed Git working tree risks an undeclared-dependency collision; requiring an affirmative on-disk isolation flag closes that hole deterministically (no LLM judgment).
- Items genuinely downstream of the gated head are NOT skipped onto — they remain correctly blocked behind it, preserving the ordered-queue dependency safety the current strict default protects.
- Items **without** an `independent: true` marker are likewise NOT skipped onto — absent the flag, an item behaves exactly as today's strict halt would for that item (safe degradation). Skip-ahead's reach is therefore gated on annotation coverage; a separate Phase can backfill the flag across the queue.
- The gated head is surfaced (notification + end-of-run flush) so the operator still sees it needs research/unblocking; skip-ahead defers it, it does not silently drop it.
- **Skip-ahead default (locked): default-on** — dependency-aware skip-ahead is the new default run behavior when the head is gated. A `--strict-research-halt` opt-out flag preserves the legacy halt-on-first-gated-head behavior for operators who want it. See Locked Decisions.

## Technical Design

### Where it lives

Per the harness's "state script is the source of truth" principle, both mechanisms are implemented in `lazy-state.py` / `lazy_core.py` (the shared state machine), with the `/lazy-batch` and `/lazy-batch-cloud` wrappers carrying only the thin dispatch/notification glue. The coupled `/lazy` ↔ `/lazy-cloud` and `/lazy-batch` ↔ `/lazy-batch-cloud` pairs are updated in lockstep.

### Per-feature budget guard

- **Counter:** extend the run marker (already keyed per repo via `claude_state_dir()`) with a `per_feature_forward_cycles: {feature_id: int}` map, advanced by the same forward-advance triggers that drive `forward_cycles` (the consume-oracle advance + the state-change advance), but keyed on the current `feature_id`. Reuses the existing advance plumbing; no new oracle.
- **Ceiling computation:** the per-feature ceiling is computed dynamically (not a static constant) as `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`, where `C_global = max_cycles` (the run marker already holds it) and `Q_depth` = the count of ready queue features (queue length the state machine already tracks). Computed at run start (or when the feature reaches the queue head); reuses existing counters with zero new oracle. The `max(6, …)` floor guarantees a feature can always run ≥6 cycles before tripping (so small runs/shallow queues still let a feature finish); the `⌊C_global × 0.4⌋` arm caps any single feature at ≤40% of the run budget. A `--per-feature-cycle-cap <N>` flag, when supplied, overrides the computed value with a fixed ceiling.
- **Trip evaluation:** in `compute_state()` queue selection, before dispatching the current item's next sub-skill, compare its per-feature count against the computed ceiling `L_task`. On trip, emit a new probe field / terminal-action that the orchestrator translates into a run-scoped queue reorder + notification (the notification reports the computed `L_task`, not a fixed number).
- **Reorder mechanism:** run-scoped only (does NOT persist to `queue.json` — preserves the on-disk queue for the next run). Implemented as a live skip-list in `compute_state()` analogous to the existing `--park-*` skip branches, plus a marker field recording the deferral so re-trip is bounded.
- **Trip signal (locked): forward-cycles consumed (single signal)** — trip when `per_feature_forward_cycles[<feature_id>]` crosses the ceiling. Single deterministic signal, reuses the existing forward-advance counter directly with zero new oracle, and is the most legible signal in the run log. A composite signal (cycles + validation-blocks + corrective-phase-count) may be layered on later if a single signal proves insufficient.
- **On-trip action (locked): defer to back of queue (run-scoped reorder)** with bounded re-trip escalation — the tripped feature moves to the live-queue tail (on-disk progress untouched) and the run advances to the next ready item; a second trip on the same feature in the same run escalates. Keeps the run autonomous (no interactive halt); composes with the `--park-*` skip-list pattern.

### Skip-ahead past a gated head

- **Readiness predicate (two-key):** reuse the existing `**Depends on:**` dep-block parser, but skip-ahead requires BOTH keys. A queue item is "skip-ahead-ready" iff (1) none of its `hard` deps resolve to a currently-gated item (research-pending or BLOCKED), AND (2) it carries an explicit `independent: true` (a.k.a. `no_shared_state`) marker in its SPEC frontmatter / queue entry (default absent ⇒ NOT skip-ahead-eligible). `soft`/`composes` deps do not block skip-ahead (they need the upstream to *exist*, not be Complete — and a gated-but-specced upstream exists). The `independent: true` marker is the **shared-state isolation rail**: hard-dep absence alone is insufficient on a shared, unsandboxed Git working tree (human-declared dep blocks are routinely incomplete; an under-declared dep would let skip-ahead advance onto an item that actually mutates state the gated head relies on). The marker is on-disk, deterministic state — no LLM judgment, no new oracle — and absent-flag items degrade to today's strict-halt behavior. Heavier hardening (file-touch-target validation, per-skip Git-branch isolation) is noted as Phase-N, out of scope for v1.
- **Generalizes `--allow-research-skip`:** the current flag is all-or-nothing (skip ALL research-pending, halt only when the whole queue is research-pending). The new behavior is dependency-aware: skip the gated head, advance onto independent ready items, but still halt (or surface) when every remaining item is gated or downstream of a gated item.
- **Default vs. opt-in (locked): default-on** — dependency-aware skip-ahead is the new default when the head is gated. The **two-key readiness predicate** (`hard`-dep absence AND `independent: true`) is the safety rail that makes default-on safe (unlike the legacy all-or-nothing `--allow-research-skip`, which is opt-in *because* it is unsafe on an ordered queue). The `independent: true` marker specifically closes the undeclared-dependency hole that hard-dep absence alone leaves open on a shared filesystem. A `--strict-research-halt` opt-out flag preserves the legacy halt-on-first-gated-head behavior.

### Reused infrastructure (no new code where it exists)

| Need | Existing mechanism reused |
|------|---------------------------|
| Per-repo run-marker state | `lazy_core.claude_state_dir()` / `repo_key` (multi-repo-concurrent-runs) |
| Forward-cycle advance triggers | `advance_run_counters` (consume-oracle) + `advance_forward_cycle` (state-change) |
| Loop / oscillation signal | `step_repeat_count` (already emitted; the guard is the *automatic action* the warning lacked) |
| Dependency readiness | `**Depends on:**` block parser + `merged_priority` ordering |
| Live queue skip/defer | the `--park-needs-input` / `--park-blocked` skip-list pattern in `compute_state()` |
| Research-gate terminal | `queue-blocked-on-research` / `--skip-needs-research`; new `--strict-research-halt` opt-out restores legacy halt-on-first-gated-head |

## Implementation Phases

See [`PHASES.md`](./PHASES.md) for the detailed phase breakdown.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Per-feature counter advances per forward cycle | Run a fixture where one feature takes ≥2 forward cycles | run marker `per_feature_forward_cycles[<id>]` increments | `lazy-state.py --test` fixture asserting marker state |
| Ceiling computed from formula | Fixtures varying `max_cycles` and ready-queue depth | computed `L_task` equals `max(6, min(⌊C×0.4⌋, ⌊(C/Q)×2⌋))`; floor of 6 honored on small runs; ≤40% cap honored on deep queues; `--per-feature-cycle-cap` overrides | `lazy-state.py --test` fixture |
| Guard trips at computed ceiling and defers to tail | Fixture feature exceeds the computed per-feature ceiling | probe returns the guard-trip action (reporting the computed `L_task`); feature appears after others in queue order; next ready item dispatched | `lazy-state.py --test` fixture |
| Bounded re-trip | Deferred feature re-reached and trips again | does NOT loop indefinitely; escalation path taken | `lazy-state.py --test` fixture |
| Skip-ahead advances onto independent item | Head item research-gated, a queue item with no hard dep on it AND `independent: true` | next dispatch targets the independent item, not a halt | `lazy-state.py --test` fixture |
| Unmarked item NOT skipped onto | Head gated, a queue item with no hard dep on the head but NO `independent: true` marker | that item is NOT dispatched (degrades to strict halt); skip-ahead does not advance onto it | `lazy-state.py --test` fixture |
| Downstream item NOT skipped onto | Head gated, a queue item with a hard dep on the head (even if `independent: true`) | that downstream item stays blocked; not dispatched | `lazy-state.py --test` fixture |
| All-gated terminal | Every remaining item gated, downstream of a gated item, or lacking `independent: true` | clean terminal (`queue-blocked-on-research` / equivalent), not a false completion | `lazy-state.py --test` fixture |
| Parity preserved | full `--test` suites + parity audit | `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py` all green; baselines match | smoke/baseline run |

## Locked Decisions

Resolved by operator via `/lazy-batch` Step 1g `AskUserQuestion` on 2026-06-19 (all three matched the SPEC recommendations). Two refinements raised by the Phase-2 Gemini research were resolved by the operator on 2026-06-19 (decisions 4 and 5 below); decision 5 REVISES decision 3.

1. **Per-feature budget trip signal → forward-cycles consumed (single signal).** The guard trips when one feature's per-feature forward-cycle count crosses the ceiling. Deterministic, reuses existing counter plumbing with zero new oracle, most legible in the run log. A composite signal may be layered on later if a single signal proves insufficient.
2. **On-trip action → defer to back of queue (run-scoped reorder)** with bounded re-trip escalation. The tripped feature moves to the live-queue tail with on-disk progress untouched; the run advances to the next ready item; a second trip on the same feature in the same run escalates. Keeps the run autonomous; composes with the `--park-*` skip-list pattern.
3. **Skip-ahead default → default-on (dependency-aware skip-ahead is the new default)**, with a `--strict-research-halt` opt-out flag preserving the legacy halt-on-first-gated-head behavior. ~~The `hard`-dep readiness predicate is the safety rail that makes default-on safe.~~ **REVISED by decision 5** — the readiness predicate is now the two-key `hard`-dep absence **AND** `independent: true` marker, not hard-dep absence alone.
4. **(research refinement) Default per-feature ceiling → dynamic fair-share formula.** The default ceiling is computed at run start (or when the feature reaches the queue head) as `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`, where `C_global = max_cycles` and `Q_depth` = count of ready queue features. Bounds any single feature to ≤40% of the run budget with a 6-cycle minimum floor; reuses `max_cycles` + queue length (no new oracle). The operator-facing trip notification reports the *computed* ceiling. A `--per-feature-cycle-cap <N>` override flag forces a fixed ceiling when supplied. (Research-recommended over a static integer default, which forces per-run hand-tuning and false-trips on large features in deep queues.)
5. **(research refinement — REVISES decision 3) Skip-ahead readiness predicate → two-key: hard-dep absence AND `independent: true` marker.** A candidate is "skip-ahead-ready" only when it passes hard-dep-absence **AND** carries an explicit `independent: true` (a.k.a. `no_shared_state`) marker in its SPEC/queue entry (default absent ⇒ NOT skip-ahead-eligible). The marker is the shared-state isolation rail that closes the undeclared-dependency hole research flagged on a shared, unsandboxed Git working tree (human-declared dep blocks are routinely incomplete). On-disk, deterministic (no LLM judgment); absent-flag items degrade to today's strict halt — a strict safety addition, not a behavior reversal. Heavier hardening (file-touch-target validation, per-skip Git-branch isolation) is Phase-N, out of scope for v1.

## Open Questions

These are deferred per phase context:

- ~~**(deferred to Phase 2 research) "Independent/ready" determination**~~ **RESOLVED (Locked Decision 5)** — hard-dep absence is NOT sufficient on a shared filesystem; the readiness predicate is two-key (`hard`-dep absence AND an explicit `independent: true` marker). Research (Bazel/Buck2) confirmed human-declared dep blocks are routinely incomplete, so an affirmative on-disk isolation marker is required.
- **(Phase 2 follow-up) Re-trip escalation shape** — what a second per-feature trip in the same run does (force-stop, BLOCKED, AskUserQuestion). Resolved alongside the on-trip-action decision.
- ~~**(Phase 2 follow-up) Default per-feature ceiling value**~~ **RESOLVED (Locked Decision 4)** — the default ceiling is computed dynamically via the fair-share formula `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`; the override flag is `--per-feature-cycle-cap <N>`.

## Research References

Pre-Gemini draft baseline. The Phase 2 `RESEARCH_PROMPT.md` will probe: prior art in autonomous agent/job pipelines for per-task budget caps and starvation avoidance; dependency-aware queue scheduling (topological skip-ahead) conventions; and whether composite budget signals (cycles + retries + corrective work) outperform single-signal caps in practice.
