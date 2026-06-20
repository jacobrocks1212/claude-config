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
  - The orchestrator emits a PushNotification: `feature-budget-guard tripped — <feature-id> deferred to queue tail after <N> cycles; advancing to <next-id>`.
  - The deferral is recorded so the same feature cannot trip-and-defer in an infinite loop within one run (once deferred, it re-enters at most once at the tail; a second trip on the same feature in the same run escalates — see Open Questions).
- The ceiling is configurable per run via a flag (default applies when omitted). `TBD (pending input)` — see Open Questions / NEEDS_INPUT for the trip-signal and on-trip-action product decisions.

### Skip-ahead past a gated head

- When the queue head returns `needs-research` (or is `BLOCKED`), instead of halting the whole run, the orchestrator advances to the **next ready item** — defined as a queue item whose `**Depends on:**` block has no `hard` dependency on the gated head (or on any other currently-gated item).
- Items genuinely downstream of the gated head are NOT skipped onto — they remain correctly blocked behind it, preserving the ordered-queue dependency safety the current strict default protects.
- The gated head is surfaced (notification + end-of-run flush) so the operator still sees it needs research/unblocking; skip-ahead defers it, it does not silently drop it.
- Whether skip-ahead is default-on or stays opt-in (generalizing `--allow-research-skip`) is `TBD (pending input)` — see Open Questions / NEEDS_INPUT.

## Technical Design

### Where it lives

Per the harness's "state script is the source of truth" principle, both mechanisms are implemented in `lazy-state.py` / `lazy_core.py` (the shared state machine), with the `/lazy-batch` and `/lazy-batch-cloud` wrappers carrying only the thin dispatch/notification glue. The coupled `/lazy` ↔ `/lazy-cloud` and `/lazy-batch` ↔ `/lazy-batch-cloud` pairs are updated in lockstep.

### Per-feature budget guard

- **Counter:** extend the run marker (already keyed per repo via `claude_state_dir()`) with a `per_feature_forward_cycles: {feature_id: int}` map, advanced by the same forward-advance triggers that drive `forward_cycles` (the consume-oracle advance + the state-change advance), but keyed on the current `feature_id`. Reuses the existing advance plumbing; no new oracle.
- **Trip evaluation:** in `compute_state()` queue selection, before dispatching the current item's next sub-skill, compare its per-feature count against the ceiling. On trip, emit a new probe field / terminal-action that the orchestrator translates into a run-scoped queue reorder + notification.
- **Reorder mechanism:** run-scoped only (does NOT persist to `queue.json` — preserves the on-disk queue for the next run). Implemented as a live skip-list in `compute_state()` analogous to the existing `--park-*` skip branches, plus a marker field recording the deferral so re-trip is bounded.
- **Trip signal** (cycles vs. MCP-validation-blocks vs. corrective-phase-count vs. composite) and **on-trip action** (defer-to-tail vs. force-stop vs. escalate-to-`/investigate` vs. AskUserQuestion) are product-behavior decisions deferred to NEEDS_INPUT.

### Skip-ahead past a gated head

- **Readiness predicate:** reuse the existing `**Depends on:**` dep-block parser. A queue item is "skip-ahead-ready" iff none of its `hard` deps resolve to a currently-gated item (research-pending or BLOCKED). `soft`/`composes` deps do not block skip-ahead (they need the upstream to *exist*, not be Complete — and a gated-but-specced upstream exists).
- **Generalizes `--allow-research-skip`:** the current flag is all-or-nothing (skip ALL research-pending, halt only when the whole queue is research-pending). The new behavior is dependency-aware: skip the gated head, advance onto independent ready items, but still halt (or surface) when every remaining item is gated or downstream of a gated item.
- **Default vs. opt-in** is a product-behavior decision deferred to NEEDS_INPUT.

### Reused infrastructure (no new code where it exists)

| Need | Existing mechanism reused |
|------|---------------------------|
| Per-repo run-marker state | `lazy_core.claude_state_dir()` / `repo_key` (multi-repo-concurrent-runs) |
| Forward-cycle advance triggers | `advance_run_counters` (consume-oracle) + `advance_forward_cycle` (state-change) |
| Loop / oscillation signal | `step_repeat_count` (already emitted; the guard is the *automatic action* the warning lacked) |
| Dependency readiness | `**Depends on:**` block parser + `merged_priority` ordering |
| Live queue skip/defer | the `--park-needs-input` / `--park-blocked` skip-list pattern in `compute_state()` |
| Research-gate terminal | `queue-blocked-on-research` / `--skip-needs-research` |

## Implementation Phases

(Indicative — finalized by `/spec-phases` after research.)

1. **Per-feature counter** — add `per_feature_forward_cycles` to the run marker; wire it into the existing forward-advance triggers keyed on `feature_id`; smoke fixtures.
2. **Guard trip + defer-to-tail** — trip evaluation in `compute_state()`; run-scoped reorder skip-branch; bounded re-trip; new probe field + orchestrator notification glue.
3. **Skip-ahead readiness predicate** — dependency-aware "ready" predicate over the dep block; generalize `--allow-research-skip` into the dependency-aware skip; halt/surface terminal when all remaining are gated/downstream.
4. **Wrapper lockstep + parity** — mirror into `/lazy-cloud`, `/lazy-batch`, `/lazy-batch-cloud`; `lazy_parity_audit.py` green; baselines regenerated.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Per-feature counter advances per forward cycle | Run a fixture where one feature takes ≥2 forward cycles | run marker `per_feature_forward_cycles[<id>]` increments | `lazy-state.py --test` fixture asserting marker state |
| Guard trips at ceiling and defers to tail | Fixture feature exceeds the per-feature ceiling | probe returns the guard-trip action; feature appears after others in queue order; next ready item dispatched | `lazy-state.py --test` fixture |
| Bounded re-trip | Deferred feature re-reached and trips again | does NOT loop indefinitely; escalation path taken | `lazy-state.py --test` fixture |
| Skip-ahead advances onto independent item | Head item research-gated, a queue item with no hard dep on it | next dispatch targets the independent item, not a halt | `lazy-state.py --test` fixture |
| Downstream item NOT skipped onto | Head gated, a queue item with a hard dep on the head | that downstream item stays blocked; not dispatched | `lazy-state.py --test` fixture |
| All-gated terminal | Every remaining item gated or downstream of a gated item | clean terminal (`queue-blocked-on-research` / equivalent), not a false completion | `lazy-state.py --test` fixture |
| Parity preserved | full `--test` suites + parity audit | `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py` all green; baselines match | smoke/baseline run |

## Open Questions

These are deferred per phase context:

- **(NEEDS_INPUT, product) Per-feature budget trip signal** — cycles consumed vs. MCP-validation-block count vs. corrective-phase count vs. a composite. Changes when/why the guard fires (operator-visible run behavior).
- **(NEEDS_INPUT, product) On-trip action** — defer-to-back-of-queue vs. force-stop vs. escalate-to-`/investigate` vs. AskUserQuestion. Changes what the operator sees happen to a stubborn feature.
- **(NEEDS_INPUT, product) Skip-ahead default vs. opt-in** — make dependency-aware skip-ahead the default when the head is research-gated, or keep it opt-in (generalizing `--allow-research-skip`). Changes the run's default behavior on a gated queue.
- **(deferred to Phase 2 research) "Independent/ready" determination** — confirm the `**Depends on:**` `hard`-dep predicate is sufficient, or whether explicit no-RESEARCH-needed metadata is also needed. (Research-answerable: how do similar autonomous pipelines determine cross-item readiness.)
- **(Phase 2 follow-up) Re-trip escalation shape** — what a second per-feature trip in the same run does (force-stop, BLOCKED, AskUserQuestion). Resolved alongside the on-trip-action decision.
- **(Phase 2 follow-up) Default per-feature ceiling value** — once the trip signal is chosen, what the default ceiling is and the flag name to override it.

## Research References

Pre-Gemini draft baseline. The Phase 2 `RESEARCH_PROMPT.md` will probe: prior art in autonomous agent/job pipelines for per-task budget caps and starvation avoidance; dependency-aware queue scheduling (topological skip-ahead) conventions; and whether composite budget signals (cycles + retries + corrective work) outperform single-signal caps in practice.
