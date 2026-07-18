# Replacing an accreting exclude-set enumeration with a single "would this dispatch?" actionability oracle in a state-machine dispatcher — design patterns, re-entrancy safety, and testing strategy

## Research Question

We maintain an autonomous work-item dispatcher (a Python state machine that walks a merged list of
two independent queues and decides which item to work next). A self-announcing guard withholds the
forward route whenever the *merged head* of the work-list diverges from the item the dispatcher is
about to emit, so it re-probes onto the true head. For that guard to fire ONLY on a genuinely
*dispatchable* divergence, the merged ordering must exclude every **non-dispatchable** item (one the
pipeline would park / defer / gate / halt rather than actually work).

Today that exclude set is built from a **pure per-item file-predicate** that has accreted **five
category facets** (parked, operator-deferred, device-deferred, dep-unready, research-skipped) — each
added reactively by its own bug after a NEW non-dispatchable category slipped through, fired the
withhold behind an undriveable head, and stalled the run with no route. We want to replace the
enumerated facet list with a **single actionability oracle**: run the item's own scoped
"compute_state" decision and classify it non-dispatchable iff that decision does not yield a real
forward dispatch. The oracle *is* the dispatch decision the guard already trusts, so behavior stays
identical for dispatchable heads and every future non-dispatchable category is auto-covered.

We want a rigorous survey of the general software-engineering patterns, correctness hazards, and
testing strategies for this class of refactor — **replacing a growing, reactively-maintained
enumeration with a single authoritative predicate derived from the system's own decision function** —
so we can pick the safest implementation and avoid re-introducing a subtler version of the same
recurring defect.

## Context

- **Language/runtime:** Python 3, standard library only. Single-process, synchronous. No async, no
  threads. The dispatcher is invoked as a CLI subprocess per cycle by an orchestrator.
- **Architecture:** Two parallel pipelines (call them "feature" and "bug"), each with its own queue
  and its own `compute_state(...)` decision function that returns a state dict — including the next
  sub-skill to run and a `terminal_reason` when no forward action is possible. A shared dispatch
  module computes a *merged* ordering across both queues and runs the divergence guard.
- **The decision function has module-level mutable accumulators.** `compute_state` RESETS several
  module-global sets/lists at entry (skip-ahead-blocked ids, gated heads, diagnostics, dep-gated
  ids, …) and mutates them as it walks the queue. The primary emit probe runs it once and captures
  the returned `state`. The oracle would need to call the SAME function repeatedly, in-process, for
  other candidate items — which risks corrupting the already-captured primary state via those shared
  globals.
- **The classification target:** an item's scoped decision is "dispatchable" iff it yields a real
  forward action — a non-empty, real sub-skill AND a `terminal_reason` that is not any
  skip/defer/park/gate/halt reason (blocked, needs-input, needs-research, deferred-*, dep-gated,
  host/device/cloud-deferred, completion-unverified, stale-upstream, budget-deferred, and the
  queue-exhaustion terminals). This is a small closed predicate over the returned state dict — the
  inverse of "would be worked right now."
- **Constraints we care about:** determinism, byte-identical behavior for the already-covered cases,
  cheapness (this runs inside the per-cycle emit path, potentially once per candidate at-or-above the
  emitted item), and never mutating shared state the primary probe already computed.

## Baseline design (what we intend to build — critique it)

1. A pure `is_dispatchable(scoped_state) -> bool` closed predicate over the returned state dict.
2. A `merged_head_nondispatchable_ids(...)` oracle that, for each cross-pipeline candidate ranked
   at-or-above the emitted item, runs that pipeline's SCOPED `compute_state` (single-item mode) with
   the SAME run flags the emit probe used, and excludes the item iff `is_dispatchable` is false.
   Short-circuit at the first dispatchable head (a lower-priority item can never be the diverging
   merged head).
3. Same-pipeline items keep using the existing probe's own skip decisions (they carry cross-item
   skip-ahead *ordering* context a per-item oracle would lose) — the oracle only replaces the
   cross-pipeline file-predicate.
4. In-process scoped calls, with snapshot/restore of the module globals around each call (or read
   ONLY the returned dict, never the globals) so the primary state is never corrupted. Subprocess
   invocation is the fallback if in-process isolation proves fragile.

## Research Areas

1. **Oracle-vs-enumeration ("derive the check from the decision function") design pattern.** Prior
   art and named patterns for replacing a hand-maintained category list with a single predicate that
   delegates to the system's own authoritative decision. Where has this succeeded / failed? What is
   the canonical failure mode when the "authoritative decision" is subtly context-dependent and the
   per-item scoped call loses context the full walk had (our same-pipeline skip-ahead ordering case)?
2. **Re-entrancy / idempotency hazards of calling a decision function with module-global side
   effects repeatedly in one process.** Idioms for safe re-entrant invocation in Python when a
   function mutates module-level accumulators: snapshot/restore, context-manager save/restore,
   dependency-injecting the accumulators, refactoring to instance/parameter state, or copying the
   returned value and treating globals as write-only-then-discarded. Tradeoffs, pitfalls (partial
   restore, exceptions mid-call, nested calls), and how to test that isolation holds.
3. **Actionability / "is this schedulable right now?" predicates in real schedulers and workflow
   engines.** How do mature systems (job schedulers, CI/CD DAG runners, workflow orchestrators,
   actor supervisors, Kubernetes-style controllers/reconcilers) decide whether a unit is *eligible
   to run now* vs skipped/deferred/blocked? Do they centralize this in one predicate or scatter it?
   Is there a "readiness gate" or "admission" pattern we should mirror? How do reconciler/controller
   loops avoid the "one more category slipped through" recurrence?
4. **Closed-set terminal-reason predicates that resist drift.** Our `is_dispatchable` must NOT
   re-introduce the same enumeration problem in a new location (a hand-listed set of "non-dispatch
   terminal reasons" that goes stale). Patterns for deriving the closed set exhaustively from the
   decision function's own vocabulary (e.g. tagging terminal reasons as dispatch-blocking at their
   definition site, an enum with a `blocks_dispatch` attribute, a total/exhaustive match the type
   checker enforces). How do teams keep such a predicate provably complete over time?
5. **Short-circuit / bounded-evaluation correctness.** We only need to evaluate candidates at-or-above
   the emitted item and can stop at the first dispatchable head. What correctness arguments and edge
   cases matter for this kind of "evaluate down the priority order until the first eligible item"
   scan (ties, stable ordering, empty queue, all-non-dispatchable, the emitted item itself)?
6. **Testing strategy for a decision oracle.** Characterization/golden-master testing when replacing
   an approximation with the authoritative decision it approximated; hermetic testing via injected
   scoped-probe callables; property-based testing that "oracle excludes item X iff scoped decision of
   X is non-dispatchable"; and regression-fixture design so each previously-enumerated facet stays
   covered AND a previously-uncovered category is proven auto-covered. How to test the in-process
   isolation invariant (primary state unchanged after N scoped calls) directly.
7. **In-process vs subprocess for the scoped decision.** Tradeoffs of re-invoking the decision
   in-process (cheap, but shares mutable globals) vs spawning the CLI per candidate (clean isolation,
   but interpreter-spawn cost and serialization). When is subprocess isolation worth it? Hybrid
   approaches (fork, cached interpreter, a re-entrant-safe pure core extracted from the CLI shell)?

## Specific Questions

1. Is there a named/established pattern for "replace an accreting exclude-list with a single predicate
   that calls the system's own decision function"? What is it called, and what are its documented
   failure modes?
2. What is the safest Python idiom for repeatedly calling a function that mutates module-level state,
   when you must preserve an earlier call's captured result? Rank snapshot/restore vs
   inject-the-accumulators vs return-value-only-read for correctness, testability, and blast radius.
3. In scheduler / reconciler / workflow-engine design, is "eligibility to run now" typically one
   centralized predicate or a scattered set of guards? Which approach empirically resists the "new
   category slipped through" recurrence, and why?
4. How do robust systems keep a closed-set predicate (e.g. "these terminal states block dispatch")
   from silently going stale as new states are added — at the type/enum level, at the test level, or
   architecturally (single definition site)?
5. What are the concrete correctness hazards of a "scan down priority order, stop at first eligible"
   short-circuit, and which edge cases most often produce a wrong or empty result?
6. For a refactor that must be byte-identical on the covered cases and correct on new ones, what
   testing regime gives the strongest guarantee — golden-master, property-based, mutation testing, or
   a combination? What does a good regression-fixture matrix look like here?
7. Are there known pitfalls where an "authoritative per-item oracle" is actually LESS correct than the
   approximation it replaced because the full-context computation carried information the per-item
   scoped call cannot see (our same-pipeline skip-ahead ordering concern)? How do you detect and
   bound that risk?
8. Any relevant prior art from language tooling (e.g. exhaustiveness checking, sealed/total match) or
   from controller/operator frameworks (readiness/admission predicates, requeue patterns) we should
   borrow directly?

## Output Format Request

Please return structured findings organized as:

1. **Executive summary** — the 3-5 most important recommendations for this specific refactor, each
   with a one-line rationale.
2. **Pattern catalog** — named design patterns relevant to oracle-vs-enumeration and readiness/
   admission predicates, each with: what it is, where it is used in mature systems, and its documented
   failure modes.
3. **Re-entrancy safety playbook** — a ranked, concrete recommendation for safely re-invoking a
   globals-mutating decision function in-process (with code-shaped illustrations), plus the
   subprocess-fallback decision criteria.
4. **Drift-resistant closed-predicate techniques** — how to keep `is_dispatchable`'s terminal-reason
   set from becoming the next stale enumeration.
5. **Testing regime** — a concrete recommended test matrix (characterization + isolation-invariant +
   property + regression fixtures), with the specific assertions to write.
6. **Risks & pitfalls** — especially the "per-item oracle loses full-context information" hazard and
   any other ways this refactor could be subtly *less* correct than what it replaces.
7. **Actionable recommendations** — a prioritized list mapped back to our baseline design's four
   points, saying what to keep, change, or add.

Cite sources (papers, framework docs, well-known codebases) where the guidance is non-obvious.
