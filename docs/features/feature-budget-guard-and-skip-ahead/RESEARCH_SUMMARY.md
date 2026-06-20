# Research Summary — Feature Budget Guard + Skip-Ahead

Source: `RESEARCH.md` (Gemini Deep Research — "Per-Task Budget Caps and Dependency-Aware Skip-Ahead in Autonomous Agent Pipelines"). Surveyed Kubernetes Jobs, Temporal, Celery, Slurm, RabbitMQ/SQS dead-letter queues, Bazel/Buck2 hermetic build DAGs, LangGraph, and CrewAI.

## Headline

Research **confirms the deterministic-state-machine foundation** and the three operator-locked decisions as *directionally* correct, but raises **three substantive FLAGs** that refine — not overturn — the locked baseline. All three map onto Open Questions the SPEC already deferred to research, plus one challenge to a locked decision (skip-ahead predicate sufficiency).

## Key findings vs. our locked baseline

| Locked decision | Research verdict | What changes |
|---|---|---|
| **Trip signal = forward-cycles (single)** | FLAG: every mature scheduler (K8s, Temporal, Celery) pairs attempt/cycle count with a wall-clock limit. Single-signal is blind to silent hangs (network/LLM latency burns wall-clock at zero cycles) and over-trips legitimately-large features (false positives). | Core single-signal choice stays (locked), but research strongly recommends the composite layer "added immediately"; if deferred, the ceiling MUST be a **dynamic** calc, not a static integer, to mitigate false trips. Recorded as a Phase-N follow-up + the dynamic-ceiling recommendation (see Decision 2). |
| **On-trip = defer to tail, bounded re-trip** | CONFIRMED as a native cooldown (the rest of the queue's work-time *is* the backoff). But unbounded requeue = livelock on a "poison pill". | Pins the re-trip escalation shape: **max 1 requeue; 2nd trip on the same feature = terminal eviction for the rest of the run** (DLQ-equivalent — feature is marked dead-letter and removed from the live queue, on-disk progress preserved for human audit). Resolves the deferred "re-trip escalation shape" Open Question. |
| **Skip-ahead = default-on, hard-dep-absence predicate** | FLAG: Bazel/Buck2 prove that *declared* deps are routinely incomplete; out-of-order execution on a **shared, unsandboxed filesystem** (our case — no Linux-namespace hermeticity) risks an undeclared-dependency collision: a skipped feature mutates shared state the gated head implicitly relied on → merge conflicts / silent logic regressions. | hard-dep absence alone is "fundamentally insufficient for autonomous safety on a shared filesystem." Research recommends an additional rail: explicit `no_shared_state`/independent flag, file-touch-target validation, or branch isolation. **Challenges the locked "predicate is the safety rail" claim → surfaced for operator decision (Decision 3).** |

## Ideas to adopt from prior art

- **Dead-letter eviction on 2nd trip** (SQS `maxReceiveCount`, K8s `backoffLimit`): the canonical bounded-re-trip ladder. Adopt directly as the escalation shape.
- **Dynamic per-task ceiling** (Slurm fair-share, CrewAI 150–200%-of-median heuristic): `L_task = max(6, min(⌊C_global × 0.4⌋, ⌊(C_global / Q_depth) × 2⌋))`. For a 32-cycle run / 10 features → ceiling 6. Guarantees no single feature consumes >40% of the run while preserving a 6-cycle execution floor. Strongly preferred over a static integer.
- **VOQ framing** (Virtual Output Queueing): our dependency-aware skip-ahead is exactly a VOQ that bypasses a head-of-line-blocked "port" — validates the default-on direction.
- **Rich audit metadata** (LangSmith checkpointing, DLQ metadata): a trip must log cycle-count-at-trip + sub-skill phase + git commit hash; a skip-ahead must log gated-head id + skipped-to id + the evaluated dep array that justified the bypass. Adopt into the run-marker audit.

## Pitfalls we must address

- **Livelock / poison pill** — mitigated by the max-1-requeue eviction ladder (above).
- **Undeclared-dependency collision on shared FS** — the central skip-ahead risk; drives Decision 3.
- **Priority inversion** — high-priority feature with a hard dep on a low-priority feature that gets deferred is indefinitely starved. Mitigation: when a feature is deferred, recursively degrade priority of its downstream dependents to match. Noted as a Phase-N hardening item (not blocking v1).
- **Silent wall-clock starvation** — the single-signal blind spot; mitigated long-term by the composite layer / an OS-level deadline wrapper. Recorded as the composite-signal follow-up.

## Baseline decisions to revisit (→ NEEDS_INPUT)

1. **Default per-feature ceiling: static integer vs. the dynamic fair-share formula.** Research strongly favors dynamic. This is a user-visible run default (changes *when* the guard trips across run/queue sizes) → operator decision.
2. **Skip-ahead readiness predicate: hard-dep-absence alone (as locked) vs. add an isolation/independence rail.** Research flags the locked predicate as unsafe on a shared FS → operator decision (it challenges a locked decision).

The two decisions above are surfaced via `NEEDS_INPUT.md`. The re-trip escalation shape (max-1-requeue → terminal eviction) is taken in-cycle per the completeness-first policy because the locked on-trip decision already constrained it to an autonomous, non-interactive shape — research only pins the exact bound.
