---
kind: needs-input
feature_id: build-queue-eta-priority-lanes
written_by: spec
decisions:
  - ETA surfacing — where predicted ETAs display (never the outcome banner)
  - Lane admission rule — explicit per-op lane class vs duration-percentile threshold
  - Lane mechanics + starvation bound — K consecutive-fast cap value
  - Preemption — may a fast op ever interrupt a running heavy build
date: 2026-07-04
next_skill: spec
class: product
---

# /spec --batch — Needs Input

The Build-Queue ETA + Priority Lanes SPEC has four OPEN product-behavior decisions (D3–D6). Research
gave each a strong recommendation, but all four change what an operator or agent sees or experiences
(display shape, config ownership, felt latency, and scheduler behavior), so they are yours to confirm.
D1, D2, and D7 were mechanical-internal and are auto-accepted (runner-recorded duration fields,
median-of-last-10 ring estimator, structural containment above the claim).

## Decision Context

### 1. ETA surfacing — where predicted ETAs display (never the outcome banner)

**Problem:** The machine-global build queue (a FIFO serializer so only one heavy Cognito build runs
at a time) shows position and elapsed wait but predicts nothing — a waiter polls blind. This feature
computes a per-op ETA and must decide **which surfaces show it**. The one hard constraint (from
research + `build-queue-outcome-opacity-and-inspect-deny`): it must NOT go on the authoritative LAST
stdout line, the "outcome banner" the skills tell agents to trust verbatim for PASS/FAIL — a
prediction there dilutes an outcome contract.

**Options:**
- **A — Three pre-outcome surfaces (Recommended)** — Show ETAs on (1) the enqueue echo
  (`enqueued as seq=641 (op=mstest, lane=fast) position=2 eta-start≈4m eta-done≈5m`), (2) the
  position lines emitted as the waiter advances (`queued at position 2 (1 build(s) ahead,
  eta-start≈3m). Waiting...`), and (3) the `/build-queue-status` view (active build gains
  `remaining≈`, each waiter row gains `eta-start≈`/`eta-done≈`). The outcome banner stays
  byte-identical. Every figure carries `≈`; cold start (<3 samples) shows `?`. Cost: touches three
  read-only display paths; reversible (display-only). Puts the prediction exactly where the waiting
  happens — in the invoking agent's own stdout, which is where the mined blind-polling friction occurs.
- **B — Status view only** — Add ETAs solely to `/build-queue-status`; leave the enqueue echo and
  position lines unchanged. Minimal surface, but the invoking agent stays blind unless it makes a
  separate status call — and the friction (blind polling) is experienced in the invoking session, not
  a separate status call. Lower value for the same core machinery.
- **C — Also suffix the outcome banner** — Everything in A plus an ETA on the final banner line.
  Rejected by research: the banner is outcome-only and agents are instructed to trust it verbatim.

**Recommendation:** A — predictions ride the pre-outcome surfaces with `≈`/`?` markers so a
prediction is never mistaken for a measurement, and the load-bearing banner contract stays untouched.

### 2. Lane admission rule — explicit per-op lane class vs duration-percentile threshold

**Problem:** The fast lane lets a cheap op (e.g. a ~20s filtered test) claim the single build slot
ahead of an older heavy op (a multi-minute solution build). This decides **what makes an op "fast"**
— a committed config declaration, or an inference from historical durations. This is a configurability
boundary: who classifies ops, and in which file.

**Options:**
- **A — Explicit per-op `lane` class (Recommended)** — Each op declares `lane: fast|heavy` in
  committed config: the `build-queue-generalization` sibling's ops manifest when it lands first (its
  schema `version` field anticipates this bump), else an interim static map in the wrapper (all four
  Cognito ops default `heavy`; the operator flags e.g. `mstest` fast deliberately). Deterministic
  forever — the same op is always in the same lane regardless of history; misclassification is a
  one-line config fix. Matches the queue's own hardening history of choosing deterministic signals
  (confirmed-dead reclaim, born-owner-bound markers) over inferred ones, and industry practice
  (Kubernetes PriorityClass, Buildkite priority).
- **B — Duration-percentile threshold** — Ops whose rolling p50 < 60s auto-classify fast. Adaptive
  and zero-config, but non-deterministic across invocations (an op flips lanes when its window drifts
  over the threshold), undefined at cold start, and it couples the scheduling decision to the stats
  file — a corrupted/stale ring changes admission order. This is exactly the inference-in-the-claim-
  path the queue's history warns against.
- **C — Per-invocation flag (`-Lane fast`)** — Maximally flexible but pushes the decision to every
  caller and invites a runaway agent to self-prioritize past the queue (the containment hooks exist
  because agents do exploit available levers).

**Recommendation:** A — a human-reviewed, committed classification is trivially reasoned about under
the lock machinery ("which lane is this ticket in" never depends on runtime state).

### 3. Lane mechanics + starvation bound — K consecutive-fast cap value

**Problem:** Two logical lanes share ONE build slot. Without a bound, a burst of fast ops could
starve the oldest heavy build indefinitely (the classic multilevel-queue failure). The mechanism: a
`fast_passes` counter lets fast ops overtake, but after **K** consecutive fast claims the heavy head
is guaranteed the slot. K is the **operator-felt worst-case latency policy** — how long the oldest
heavy build may be delayed by fast overtakes (≈ K × a fast op's typical duration).

**Options:**
- **A — Claim-eligibility rule + fast-pass counter, K=3 (Recommended)** — The claim predicate becomes:
  slot absent AND (I am the lowest *fast* seq AND `fast_passes < K`) OR (I am the lowest *heavy* seq
  AND (no fast waiter exists OR `fast_passes >= K`)). A `fast-passes.count` file holds the counter,
  written ONLY by the claim winner (single-writer by the same atomic `CreateNew` arbiter that already
  picks one lock holder). K=3 lets a typical verification burst (build → test → retest) drain past a
  long build while charging the heavy head only tens of seconds (3 × seconds-scale fast ops). An
  unreadable/corrupt counter is treated as K → pure FIFO (degrades to today's behavior, never a
  livelock). Reclaim/occupancy/hygiene are untouched (D7). K ships as a named constant.
- **B — Same rule, K=1 (near-FIFO fallback)** — One overtake per heavy build. Most conservative,
  barely beats FIFO; the heavy head is charged at most one fast op. Choose this if you want minimal
  deviation from strict arrival order.
- **C — Same rule, unbounded (no cap)** — Fast ops always win while any fast waiter exists. Maximum
  fast-lane throughput but starves the heavy head under a sustained fast-op burst. Rejected by
  research (the classic MLQ starvation failure).

**Recommendation:** A with K=3 — bounds heavy-head delay to a small multiple of fast-op duration while
letting a quick verification burst drain; K=1 is the conservative fallback if you prefer near-FIFO.

### 4. Preemption — may a fast op ever interrupt a running heavy build

**Problem:** The lane rule only decides who claims the slot **once it is free**. This decides whether
a fast op may ever *interrupt a build already running* — kill/requeue a multi-minute heavy build so an
urgent seconds-scale check runs sooner. It is a distinct behavioral policy from the admission rule.

**Options:**
- **A — No preemption, ever (Recommended)** — A claim happens only when the slot is free; a running
  build is never killed, paused, or deprioritized. Every hardened invariant in this family assumes a
  build, once started, runs to its own exit; preemption converts normal operation into the crash path
  (firing quarantine sweeps and locker reaps that exist for *abnormal* death, and breaking the
  `run_transient_build` await bracket). Matches CI-executor norms (GitHub Actions, Buildkite don't
  preempt same-executor jobs). The lane rule already caps fast-op latency at "one heavy build," the
  irreducible cost of a single-slot machine; `BUILD_QUEUE_BYPASS=1` remains the sanctioned escape for
  a genuinely urgent off-queue command.
- **B — Cooperative preemption (kill + requeue the heavy build)** — Minimizes fast latency but
  discards minutes of work, triggers crash-hygiene machinery by design, and re-opens the orphaned-
  process class that `build-queue-no-artifact-or-process-hygiene-on-crash` closed. Higher risk to the
  exact invariants recent bug fixes paid for.

**Recommendation:** A — no preemption; lanes cap fast latency at one heavy build, and preemption would
convert healthy operation into the crash path the hygiene bugs closed.
