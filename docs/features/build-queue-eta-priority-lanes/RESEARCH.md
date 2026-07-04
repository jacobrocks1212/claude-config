# Research — Build-Queue ETA + Priority Lanes

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

**The stub's central premise is false — verified against source.** The stub asserted
"`results/<seq>.json` already records per-op durations; use the history." It does not:

- `build-queue-runner.ps1:244-257` composes the result body as `{seq, exit_code, ended_at,
  counts, hygiene}` — no `op`, no `started_at`, no duration. The runner never even receives the
  op name (params `-Exec -Seq -StateRoot -Worktree` + passthrough).
- The two records that DO know timing are ephemeral by design: `tickets/<seq>.json` carries
  `started_wait_at` but is deleted the moment the waiter claims the slot
  (`build-queue.ps1:275`); `active.lock` carries `started_at` but is deleted at release
  (`build-queue.ps1:455-472`, runner `:267-285`).
- Consequence: duration capture is Phase 1 work (SPEC D1), not a free input. This also means no
  retroactive history exists — the estimator's cold-start behavior (SPEC D2: `?` under 3
  samples) is the launch-day norm, not an edge case.

**Machinery the feature layers over (read in full):**

- `user/scripts/build-queue.ps1` — the claim loop this feature's lane rule modifies: claim
  condition `status -eq 'absent' -and lowestSeq -eq seq` (`:237`), arbitrated by the exclusive
  `CreateNew` open of `active.lock` (only one waiter can win → the SPEC's single-writer
  justification for the fast-pass counter). Position lines emitted on change (`:284-297`) — the
  natural carrier for waiter ETAs. Release-time results **read-merge-write** (`:429-445`)
  refreshes only `exit_code`/`ended_at`, so runner-written duration fields survive by
  construction (the two-writer contract from
  `docs/bugs/build-queue-false-green-on-silent-build-failure` / root `CLAUDE.md` build-queue
  rows).
- `user/scripts/build-queue-runner.ps1` — the self-releasing detached runner (survives wrapper
  kill: `build-queue-orphaned-result-on-wrapper-kill`), which is why D1 puts duration recording
  runner-side. Atomic temp-then-`File.Replace` result write (`:259-265`) — the idiom the stats
  ring writer copies.
- `user/scripts/build-queue-hygiene.ps1` — home of the pure, Pester-testable helpers the
  estimator and claim-eligibility function join: `Test-ShouldReclaimLock` (the extracted-pure-
  function precedent, and the reclaim arbiter the lanes must NOT touch — global lowest-seq,
  confirmed-dead-only), `Get-BuildQueueOccupancy` (occupancy gate, untouched),
  `Format-BuildQueueBanner` (the authoritative-last-line outcome contract D3 keeps ETA out of),
  `Read-WithRetry`, `Get-SafeValue` fail-open idiom.
- `user/scripts/build-queue-status.ps1` — the read-only status view gaining `remaining≈` and
  per-waiter ETAs; already computes elapsed via `Format-Elapsed` and reads tickets sorted by
  seq.
- `repos/cognito-forms/.claude/skills/mstest/SKILL.md:37` — the banner-trust instruction ("trust
  that line for the outcome... do NOT `cat`/`grep` ... `results/<seq>.json`") that makes the
  banner untouchable for ETA display, and whose background path (`:39`) reads
  `results/<seq>.json` by the enqueue-echoed seq — the enqueue echo is therefore already the
  skills' canonical pre-outcome surface, supporting D3's placement.
- `docs/bugs/build-queue-outcome-opacity-and-inspect-deny` — why the banner exists and why its
  trust contract is load-bearing; also documents the blind-polling / opaque-wait friction class
  this feature reduces.
- `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build` — the occupancy/reclaim
  hardening the stub explicitly names as must-not-disturb; the SPEC answers with structural
  containment (D7: lanes sit strictly above the claim; one slot always).
- `docs/features/build-queue-generalization/SPEC.md` (sibling, drafted same date) — its D2
  manifest schema carries `version` specifically so this feature's `lane` field is an additive
  bump; its D6 delegates latency shaping here.

**House patterns reused:** deterministic script-owned scheduling signals over inferred ones (the
repo repeatedly chose recorded/explicit signals after inference misfired —
`Test-ShouldReclaimLock` confirmed-dead-only, the born-owner-bound run marker, the
`last_resolution_step_key` recorded resolution signal); atomic temp-then-replace for every state
write; fail-open advisory state (predictions and counters degrade to old behavior, never block).

## External prior art & concepts

Training-knowledge, not live research:

- **ETA from historical run durations.** GitLab CI's pipeline duration prediction and Jenkins'
  progress bars both estimate from recent runs of the same job (Jenkins: median-ish over recent
  builds) — the same "median of last N per op" shape as SPEC D2, chosen there too for outlier
  robustness over the mean. Both display predictions as soft/approximate, never as outcomes.
- **Express lanes with starvation bounds.** Classic OS scheduling: multilevel queues starve the
  low-priority class unless bounded (aging, or an admission cap). The SPEC's "K consecutive fast
  passes then the heavy head is guaranteed the slot" is the deterministic, stateless-per-ticket
  variant of aging — chosen over priority aging because it needs one small counter instead of
  per-ticket mutable priority. Supermarket express-lane queueing theory makes the same tradeoff:
  bounded overtaking cuts mean wait dramatically while capping worst-case added delay at
  K × (short service time).
- **Shortest-Job-First caution.** Pure SJF (the duration-percentile auto-threshold, SPEC D4-B)
  is throughput-optimal but starvation-prone and depends on service-time estimates — the exact
  coupling of scheduling to noisy stats the SPEC rejects in favor of an explicit class
  (Kubernetes PriorityClass / Buildkite priority attribute prior art: priority is declared
  config, not inferred from history).
- **No-preemption norm for build executors.** CI executors (GitHub Actions, Buildkite agents)
  do not preempt running jobs for higher-priority ones on the same executor; preemption is
  reserved for cancellation semantics with explicit cleanup, because killing a build mid-flight
  produces exactly the partial-artifact states this queue's hygiene bugs cataloged. Supports
  D6-A.

## Alternatives analysis

- **Duration source (D1).** Runner-recorded vs wrapper-recorded vs log-mtime reconstruction.
  The runner already owns the durable result precisely because wrappers get killed; putting the
  new fields anywhere else re-opens the orphaned-result class. Wrapper-recorded would also
  invert the release-time merge (wrapper would need to win new fields), touching a two-writer
  contract that was hardened deliberately. Cost of A: one optional `-Op` param, fully
  back-compatible.
- **Stats residency (D2).** Per-op ring file vs on-demand `results/*.json` scan. The results dir
  is unbounded (nothing prunes it) and pre-feature files lack `op`, so the scan is O(dir-size)
  for near-zero usable data at launch. The ring is O(1), bounded, atomic, and doubles as
  evidence for tuning the lane classification later. Median over mean: one cold-cache `/msbuild`
  outlier should not double the displayed ETA for a week of runs.
- **Surfacing (D3).** The genuinely contested surface was the outcome banner. Adding
  `eta`-anything to it would mean the "authoritative LAST stdout line" carries a prediction —
  and agents are explicitly instructed to trust that line verbatim. The enqueue echo + position
  lines reach the waiting agent in-stream (where the mined blind-polling friction actually
  occurs); the status view serves the operator. Status-only (B) was rejected because the
  invoking session — not a separate status call — is where waiting is experienced.
- **Admission rule (D4).** Explicit class vs percentile threshold vs per-invocation flag. The
  percentile threshold makes lane membership a function of mutable state read at claim time —
  non-reproducible across invocations, undefined at cold start, and corruptible; the queue's own
  history (confirmed-dead reclaim, born-owner-bound marker) shows the cost of inferred signals
  in this layer. The per-invocation flag invites a runaway agent to self-priority — the
  containment hooks exist because agents do exploit available levers. Explicit committed config
  is boring, reviewable, and one line to fix when wrong.
- **Lane mechanics (D5).** Eligibility rule over one slot vs two physical queues vs seq games.
  The single `active.lock` slot is the most safety-audited object in the family (atomic
  provisional write, bounded re-read, confirmed-dead reclaim, occupancy union of tickets+lock);
  duplicating it per lane doubles the audited surface, and re-numbering seqs breaks the total
  order every component (results naming, reclaim gating, occupancy, banner) assumes. The
  eligibility rule changes ~one predicate plus one advisory counter file, and its failure mode
  (unreadable counter → treat as K → pure FIFO) degrades to today's behavior.
- **Starvation bound K.** K=3 vs K=1 vs unbounded. Unbounded starves the heavy head under a
  fast-op burst (the classic MLQ failure). K=1 barely beats FIFO (one overtake per heavy
  build). K=3 lets a typical verification burst (build → test → retest) drain past a long build
  while charging the heavy head tens of seconds. It ships as a named constant; the operator
  confirms the policy in the needs-input round.
- **Preemption (D6).** The only scenario where preemption wins is a many-minute heavy build
  ahead of an urgent seconds-scale check — and the cost is discarding the heavy build's
  progress, firing crash-path hygiene on a healthy build, and breaking the
  `run_transient_build` await bracket. `BUILD_QUEUE_BYPASS=1` already exists as the sanctioned
  emergency escape for a genuinely urgent off-queue command; preemption would be a worse tool
  for the same rare case.

## Pitfalls & risks

- **Prediction trusted as fact.** An agent could read `eta-done≈2m` and set a 2-minute timeout.
  Mitigation: `≈` on every figure, `?` on cold start, skill prose (Phase 4) states predictions
  never gate anything; the Bash-timeout guidance in the skills already uses generous fixed
  ceilings.
- **ETA composition cost in the wait loop.** The position-line ETA sums estimates over tickets
  ahead each time position changes. At observed queue depths (≤5 waiters) this is a handful of
  small JSON reads; the deferred empirical check re-verifies at realistic depth before wiring
  it into every poll tick (fallback: compute only on position change — already the emission
  condition).
- **Counter races.** Two waiters observing `fast_passes` concurrently is harmless: the value
  only changes via the claim winner (post-`CreateNew`), and a stale read merely delays one
  overtake by one poll tick (1s). The dangerous variant — two writers — is excluded by the same
  arbiter that already guarantees one lock holder.
- **Lane misclassification.** A "fast" op that is sometimes slow (unfiltered `/mstest`) charges
  the heavy head more than expected, bounded by K. Mitigation: ring data makes the
  misclassification visible (median in the stats file); reclassification is a one-line config
  change. This is also the falsifiability story: the feature is working iff (a) ring data shows
  fast-lane ops' median ≪ heavy ops' median, and (b) status-view wait times for fast ops drop
  after Phase 3 — both measurable from the feature's own recorded state, no new telemetry.
- **Regression of hardened invariants.** The named risk in the stub. Answered structurally (D7:
  no edits below the claim) and mechanically (Phase 4 Pester net asserting reclaim/occupancy/
  recycle call patterns under lane scenarios, including a fast claim during a stale-lock reclaim
  window).
- **Dead weight if generalization stalls.** Phases 1-2 (durations + ETA) are valuable against
  today's Cognito-only wrapper and ship independently; only Phase 3 (lanes) prefers the manifest
  carrier — matching the soft dep's "implementable against today's wrapper if sequencing
  changes."

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 duration source | Runner-recorded `op`/`started_at`/`duration_seconds` in `results/<seq>.json` | High |
| D2 estimator + residency | Median of last 10 successes; `stats/<op>.json` ring (20), atomic, fail-open; `?` under 3 samples | High |
| D3 surfacing | Enqueue echo + position lines + status view; banner untouched | High |
| D4 admission rule | Explicit per-op `lane` class (manifest field / interim static map) | High |
| D5 mechanics + bound | Claim-eligibility rule over the single slot; K=3 consecutive-fast cap; unreadable counter → FIFO | Medium-high |
| D6 preemption | Never | High |
| D7 fidelity containment | Lanes strictly above the claim; zero edits to lock/reclaim/occupancy/hygiene/banner | High |
