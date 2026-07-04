# Research Summary — Build-Queue ETA + Priority Lanes

Condensed analysis of `RESEARCH.md` (internal desk research; Gemini deep research intentionally
skipped by operator directive, 2026-07-04) against the baseline SPEC. This file gates the
downstream `/spec-phases` → `/plan-feature` workflow.

## Key findings relevant to the baseline

1. **The stub's central premise is false — verified against source.** The stub assumed
   `results/<seq>.json` "already records per-op durations." It does not: `build-queue-runner.ps1`
   writes only `{seq, exit_code, ended_at, counts, hygiene}` — no `op`, no `started_at`, no
   duration — and the runner never even receives the op name. The two records that DO know timing
   (`tickets/<seq>.json` `started_wait_at`, `active.lock` `started_at`) are deleted at claim and
   release respectively. **Consequence:** duration capture is genuine Phase 1 work, not a free
   input, and there is **no retroactive history** — the estimator's cold-start (`?` under 3
   samples) is the launch-day norm, not an edge case. This validates SPEC D1 (add the fields) and
   D2 (cold-start honesty).

2. **The runner-owns-the-durable-result split is load-bearing.** The runner is self-releasing and
   survives a wrapper kill (`build-queue-orphaned-result-on-wrapper-kill`), which is exactly why
   D1 records duration fields runner-side; the release-time read-merge-write refreshes only
   `exit_code`/`ended_at`, so runner-written fields survive by construction. Recording anywhere
   else re-opens the orphaned-result class and inverts the hardened two-writer merge direction.

3. **The outcome banner is untouchable for ETA.** `Format-BuildQueueBanner`'s authoritative-last-
   line contract is what the skills instruct agents to trust
   (`repos/cognito-forms/.claude/skills/mstest/SKILL.md:37`); `build-queue-outcome-opacity-and-
   inspect-deny` exists because outcome signals were once ambiguous. Any ETA suffix on that line
   dilutes an outcome contract with a prediction. Confirms D3's "never the banner" constraint.

4. **The lock/reclaim/occupancy machinery is the most safety-audited object in the family** and
   must not be disturbed (`build-queue-recycle-kills-concurrent-worktree-build`,
   `build-queue-false-green-on-silent-build-failure`). Confirms D7's structural-containment
   framing: lanes sit strictly above the claim; exactly one `active.lock` always.

## Ideas adopted from prior art

- **ETA from historical run durations** (GitLab CI duration prediction, Jenkins progress bars):
  both estimate from recent runs of the same job using a median-ish statistic for outlier
  robustness, and display predictions as soft/approximate — the exact "median of last N per op,
  never an outcome" shape of SPEC D2/D3.
- **Express lanes with a bounded starvation cap** (classic multilevel-queue scheduling; supermarket
  express-lane queueing theory): bounded overtaking cuts mean wait dramatically while capping
  worst-case added delay at K × (short service time). SPEC D5's "K consecutive fast passes then the
  heavy head is guaranteed the slot" is the deterministic, stateless-per-ticket variant of aging.
- **Declared priority over inferred priority** (Kubernetes PriorityClass, Buildkite priority
  attribute): priority is committed config, not derived from noisy history. Supports SPEC D4-A's
  explicit `lane` class over the duration-percentile auto-threshold (D4-B).
- **No-preemption norm for build executors** (GitHub Actions, Buildkite agents do not preempt
  running jobs on the same executor): killing a build mid-flight produces exactly the partial-
  artifact states this queue's hygiene bugs cataloged. Supports SPEC D6-A.

## Pitfalls / concerns to address

- **Prediction trusted as fact.** An agent could read `eta-done≈2m` and set a 2-minute timeout.
  Mitigation carried into the SPEC: `≈` on every figure, `?` on cold start, and Phase-4 skill prose
  stating predictions never gate anything.
- **ETA composition cost in the wait loop.** The position-line ETA sums estimates over tickets
  ahead on each position change. At observed depths (≤5 waiters) this is a handful of small JSON
  reads; a deferred empirical check re-verifies at realistic depth (fallback: compute only on
  position change — already the emission condition).
- **Counter races.** Two waiters reading `fast_passes` concurrently is harmless (the value changes
  only via the post-`CreateNew` claim winner — a single writer by the same arbiter that guarantees
  one lock holder); a stale read merely delays one overtake by one poll tick.
- **Lane misclassification.** A "fast" op that is sometimes slow (unfiltered `/mstest`) charges the
  heavy head more than expected, bounded by K. The ring data makes the misclassification visible
  (median in the stats file); reclassification is a one-line config change. This is also the
  falsifiability story — measurable from the feature's own recorded state, no new telemetry.
- **Dead weight if generalization stalls.** Phases 1–2 (durations + ETA) ship independently against
  today's Cognito-only wrapper; only Phase 3 (lanes) prefers the manifest carrier — matching the
  soft dep's "implementable against today's wrapper if sequencing changes."

## Baseline decisions the research revisits

Research **confirmed** the baseline across the board (all recommendations High / Medium-high
confidence). It changed no recommendation; it hardened the *justification* for each, especially by
verifying the false stub premise (finding 1) that reshapes D1/D2 from "reuse existing history" to
"capture it first." The four product-behavior decisions (D3 surfacing, D4 admission rule, D5
mechanics + K, D6 preemption) remain OPEN pending operator confirmation — research provides a strong
recommendation for each but the operator-visible display shape, configurability boundary, felt-
latency policy, and preemption behavior are user-authority calls, surfaced via `NEEDS_INPUT.md`.

| Decision | Class | Research recommendation | Confidence |
|----------|-------|-------------------------|------------|
| D1 duration source | mechanical-internal | Runner-recorded `op`/`started_at`/`duration_seconds` | High |
| D2 estimator + residency | mechanical-internal | Median of last 10 successes; `stats/<op>.json` ring(20); `?` under 3 | High |
| D3 ETA surfacing | **product-behavior** | Enqueue echo + position lines + status view; banner untouched | High |
| D4 admission rule | **product-behavior** | Explicit per-op `lane` class (manifest / interim static map) | High |
| D5 mechanics + bound | **product-behavior** | Claim-eligibility rule over one slot; K=3; unreadable counter → FIFO | Medium-high |
| D6 preemption | **product-behavior** | Never | High |
| D7 fidelity containment | mechanical-internal | Lanes strictly above the claim; zero edits below | High |
