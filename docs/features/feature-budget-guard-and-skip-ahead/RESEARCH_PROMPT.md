# Per-task budget caps and dependency-aware skip-ahead in autonomous agent pipelines

## Research Question

I am designing two coupled mechanisms for an autonomous, queue-driven software-development pipeline (an LLM "batch" orchestrator that works a prioritized queue of features one at a time, fully unattended). I need authoritative prior art, conventions, and tradeoff analysis for:

1. **Per-task budget guards** that stop a single stubborn work-item from monopolizing a whole-run compute/cycle budget (the starvation / head-of-line-blocking problem), and the right *action* to take when one item exceeds its share.
2. **Dependency-aware skip-ahead** — when the queue head is blocked or gated (waiting on an external input), advancing past it onto independent, ready items instead of stranding the entire queue, without violating dependency ordering.

What do mature schedulers, CI/build systems, job-queue runtimes, and autonomous-agent frameworks actually do here, and which design choices hold up in practice?

## Context

**The system.** A deterministic Python state machine (the "state script") owns all run state; a thin LLM orchestrator loops, asking the state script "what's the next action?" and dispatching exactly one sub-skill per cycle. State lives in a per-repo run marker (a small on-disk JSON blob). The pipeline processes a `queue.json` of features in a merged-priority order; each feature advances through a fixed sub-skill tail (spec → research → plan → implement → validate → mark-complete).

**What exists today.**
- A **whole-run** budget ceiling: `max_cycles`, enforced as `forward_cycles >= max_cycles`. This caps the *entire run*, not any single item.
- A mechanical **loop tripwire**: `step_repeat_count >= 3` emits an oscillation *warning* to the orchestrator — but takes no automatic action.
- An **opt-in, all-or-nothing** research-skip flag (`--allow-research-skip`): skip ALL research-pending items, halt only when the entire queue is research-pending. It is opt-in precisely *because* it is unsafe on an ordered queue (it ignores dependencies).
- A per-feature `**Depends on:**` block in each feature's spec, classifying upstream deps as `hard` / `soft` / `composes`. A `hard` dep means the downstream design hinges on the upstream's concrete contract.

**The incident that motivates this.** One feature (`d8-live-looping`) consumed an entire extended run budget (20→32 cycles) plus ~5 validation-block retries before being force-stopped. The rest of the queue never advanced. The existing tripwire only *warned*; it never *acted*.

**Design constraints (non-negotiable).**
- The state script is the single source of truth — readiness, counters, and trip evaluation must be computed deterministically from on-disk signals (run-marker counters + each spec's dep block), never inferred by the LLM.
- Runs must stay autonomous — the preferred on-trip action avoids an interactive halt.
- Changes are mirrored across coupled skill pairs (workstation/cloud variants); minimize new state.

## Baseline Spec Summary (decisions already locked — validate, don't re-litigate)

The following three decisions are already locked by the operator. I want research to *pressure-test* them and inform the still-open parameters, not reopen them:

1. **Trip signal = forward-cycles consumed (single signal).** The per-feature guard trips when one feature's per-feature forward-cycle count crosses a ceiling. Chosen for determinism, reuse of the existing counter, and run-log legibility. A composite signal (cycles + validation-blocks + corrective-phase-count) is explicitly held as a *possible later layer*.
2. **On-trip action = defer to back of queue (run-scoped reorder), with bounded re-trip escalation.** The tripped feature moves to the live-queue tail (on-disk progress untouched, resumes when re-reached); the run advances to the next ready item. A *second* trip on the same feature in the same run escalates. The reorder is run-scoped only — it does not rewrite `queue.json`.
3. **Skip-ahead = default-on, dependency-aware.** When the head is gated, advance onto items whose `**Depends on:**` block has no `hard` dep on a currently-gated item. A `--strict-research-halt` opt-out preserves the legacy halt-on-first-gated-head behavior.

**Still open (research should directly inform these):**
- The **default per-feature ceiling value** and how to express it relative to the whole-run `max_cycles`.
- The exact **re-trip escalation shape** (what a second trip in one run should do).
- Whether the `hard`-dep predicate **alone** is a sufficient "independent/ready" test, or whether an explicit "no-external-input-needed" readiness flag is also required.
- Whether the locked **single-signal** trip will prove insufficient in practice (i.e., is the held-back composite signal likely to be needed soon).

## Research Areas

**1. Per-task / per-tenant budget caps and starvation avoidance (prior art).**
- How do job-queue runtimes and schedulers prevent one task from starving the rest: per-task timeouts/attempt-caps, fair-share / weighted fair queuing, DRF (dominant resource fairness), token/leaky buckets, cgroup-style quotas. Map each to the "per-feature forward-cycle ceiling" analog.
- Concrete systems to examine: Kubernetes (pod `activeDeadlineSeconds`, Job `backoffLimit`, ResourceQuota, priority/preemption), CI systems (GitHub Actions / GitLab CI per-job timeouts, retry caps), Celery/Sidekiq/Temporal (max-retries, task time limits, activity heartbeats), HPC schedulers (Slurm wall-clock limits, fair-share), and Airflow/Dagster/Prefect (task retries, SLAs, pool slots).
- For each: what is the *trip signal* (wall-clock, attempt count, resource units), and what is the *on-trip action* (kill, requeue-to-tail, dead-letter, escalate, pause)?

**2. The "defer to tail" vs. alternatives tradeoff.**
- When a runtime decides a task has consumed its share, what are the canonical responses and their failure modes: requeue-to-tail (our locked choice), dead-letter queue, exponential-backoff re-schedule, hard-kill/abandon, escalate-to-human. Where does requeue-to-tail cause livelock or unbounded churn, and what bounds prevent it (max-requeues, backoff, dead-letter after N)?
- Specifically: best-practice **bounded re-trip / escalation** patterns. After a task is requeued once and fails its budget *again*, what do mature systems do? Compare dead-letter, circuit-breaker, and operator-escalation. This directly informs our open "re-trip escalation shape."

**3. Setting the per-task ceiling relative to the whole-run budget.**
- Conventions for choosing per-task caps as a function of the global cap and the expected number of tasks. E.g., should a per-feature ceiling be an absolute constant, a fraction of `max_cycles`, or `max_cycles / expected_queue_depth` with a floor? What do fair-share schedulers compute, and what's a sane *default* that avoids both premature deferral of legitimately-large items and runaway monopolization?
- Any published heuristics for "Nx the median task cost" style caps.

**4. Dependency-aware skip-ahead / out-of-order scheduling.**
- Topological / dataflow scheduling: how do DAG runtimes (Airflow, Dagster, Prefect, Bazel, Buck2, Nx, Make/Ninja, Gradle) decide a node is "ready" when an earlier node is blocked? Confirm whether "no unsatisfied *hard* upstream dependency" is the standard readiness predicate, or whether real systems also gate on additional signals (resource availability, explicit ready-state, external-input presence).
- Head-of-line blocking mitigations from networking/queueing (HOL blocking, virtual output queues, work-stealing) — which transfer to an ordered work-queue with declared inter-item dependencies?
- Risk analysis: when is it *unsafe* to skip past a blocked head even if the next item has no declared hard dep (hidden/implicit coupling, shared mutable state, ordering assumptions)? How do systems guard against undeclared dependencies?

**5. Single-signal vs. composite budget signals (empirical).**
- Is a single trip signal (cycle count) generally sufficient in practice, or do mature systems converge on composite signals (e.g., attempts + wall-clock + error-rate)? What evidence exists that single-signal caps misfire (false trips on legitimately-large work; missed trips on cheap-but-looping work)? This informs whether our held-back composite signal is likely needed soon.

**6. Pitfalls, accessibility, observability.**
- Observability conventions: what should be logged/emitted when a budget guard trips or a skip-ahead occurs, so an operator can audit the run after the fact? (We emit a push notification + end-of-run flush.)
- Common foot-guns: livelock from requeue loops, priority inversion, starvation of the *deferred* item itself (it never gets re-reached), and silent dependency violations from skip-ahead.

## Specific Questions

1. Across job-queue/scheduler/CI systems, what is the most common **per-task trip signal**, and the most common **on-trip action**? Is "requeue to tail" a recognized pattern, and what bounds do systems put on it to prevent livelock?
2. What is the canonical **bounded re-trip / escalation** ladder after a task exceeds its budget a *second* time? (dead-letter vs. circuit-breaker vs. operator-escalation — with the conditions favoring each.)
3. Is there a published or widely-used **heuristic for setting a per-task cap as a function of the global run budget** and expected task count? What default would you recommend for a per-feature cycle ceiling given a typical whole-run cap of ~20–32 cycles and a queue of ~5–15 features?
4. In DAG/build runtimes, is **"no unsatisfied hard upstream dependency"** the complete readiness predicate for out-of-order execution, or do production systems require additional readiness signals? If additional, which ones — and would they apply to a declared-dependency work-queue like ours?
5. What are the documented **risks of skipping past a blocked head** onto a nominally-independent item, and how do mature systems detect/prevent **undeclared (implicit) dependencies** from causing incorrect out-of-order execution?
6. Does prior art support keeping a **single-signal** budget cap, or does it strongly favor **composite signals**? What concrete failure modes of single-signal caps should we expect, and at what point should we add the composite layer?
7. How do autonomous-agent / LLM-agent frameworks (AutoGPT-style loops, LangGraph, CrewAI, multi-agent orchestrators) handle **per-task budget exhaustion and starvation** today, if at all? Are there agent-specific conventions distinct from classical schedulers?
8. What **observability / audit signals** should a budget-guard trip and a skip-ahead emit so an unattended run is auditable after the fact?

## Output Format Request

Please structure the findings as:

- **Executive summary** (½ page): the 3–5 most decision-relevant conclusions for this design.
- **Section per Research Area (1–6 above)** with concrete prior-art examples (named systems, specific mechanisms), and an explicit "applies to our design as…" mapping line for each.
- **Direct answers to Specific Questions 1–8**, each with a recommendation and the evidence/citation behind it.
- **Recommended defaults table** for the still-open parameters: per-feature ceiling (with the formula/heuristic), re-trip escalation shape, and whether the `hard`-dep readiness predicate is sufficient alone.
- **Pitfalls checklist** — the foot-guns we should explicitly guard against, each with the mitigation.
- Where prior art contradicts one of our three locked decisions, **flag it explicitly** with the tradeoff — but treat the locked decisions as the default unless the evidence is strong.
- Cite sources (docs, papers, well-known engineering writeups) inline.
