# Build-Queue ETA + Priority Lanes — Feature Specification

> Waiters on the machine-global build queue poll blind: the enqueue line and
> `build-queue-status.ps1` show position and elapsed wait, but no prediction of when a queued op
> will start or finish, and a 20-second filtered test run pays worst-case latency behind a full
> solution build. This feature (1) records per-op run durations into the queue's existing result
> files (they are NOT recorded today — the runner writes only `{seq, exit_code, ended_at, counts,
> hygiene}`), (2) computes deterministic rolling per-op ETAs surfaced in the enqueue echo, the
> waiting lines, and the status view — never in the authoritative outcome banner — and (3) adds a
> bounded two-lane admission rule over the SAME single `active.lock` slot (fast ops may claim
> ahead of heavy ops, with a deterministic consecutive-passes starvation bound), leaving the
> lock/reclaim/hygiene/occupancy machinery untouched.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:**

- build-queue-generalization — soft — ETA/lane mechanics should land once on the manifest-driven generalized queue rather than be built twice against the Cognito-only wrapper; the ETA half is implementable against today's wrapper if sequencing changes.

> Substantive non-block dependencies are **implemented contracts**, not sibling specs:
> - `user/scripts/build-queue.ps1` / `build-queue-runner.ps1` — the ticket → claim → detached-run
>   → self-releasing-result lifecycle this feature annotates (tickets carry `started_wait_at`;
>   `active.lock` carries `started_at` but is deleted at release; `results/<seq>.json` carries
>   `ended_at` only — hence Phase 1's duration capture).
> - `Format-BuildQueueBanner` (`build-queue-hygiene.ps1`) — the authoritative-LAST-line outcome
>   contract the skills tell agents to trust; this feature deliberately does NOT touch it.
> - `Get-BuildQueueOccupancy` + occupancy-gated `Reset-CompilerServer` + the results
>   read-merge-write — hardened invariants
>   (`docs/bugs/build-queue-recycle-kills-concurrent-worktree-build`,
>   `build-queue-false-green-on-silent-build-failure`) that lanes must not disturb.
> - If `build-queue-generalization` lands first, its ops manifest is where the per-op `lane`
>   class lives (D4 option B's preferred carrier).

---

## Executive Summary

The queue is strict FIFO with no wait-time visibility. An agent that enqueues `/mstest` behind a
full `/msbuild` sees `build-queue: queued at position 2 (1 build(s) ahead). Waiting...` and then
silence until the slot frees; `build-queue-status.ps1` shows the active build's elapsed time but
cannot say "roughly how much longer," because the queue keeps no duration history — the stub's
premise that `results/<seq>.json` "already records per-op durations" is **wrong** (verified:
`build-queue-runner.ps1:244-257` writes `seq/exit_code/ended_at/counts/hygiene`; no `op`, no
`started_at`, no duration — and the two files that do know the start time, the ticket and
`active.lock`, are deleted at claim and release respectively). Cheap ops also pay worst-case
latency: a seconds-scale filtered test run waits behind a minutes-scale solution build purely by
arrival order, which in an autonomous run means an idle agent turn burning wall-clock and context
on polling.

The fix has three independent layers. **Duration capture:** the runner records `op`,
`started_at`, and `duration_seconds` into `results/<seq>.json` (additive fields; the wrapper's
read-merge-write already preserves runner-written fields) and appends to a small per-op rolling
stats file. **ETA:** a deterministic estimator (median of the last N completed runs per op) is
surfaced where a waiter already looks — the enqueue echo, the position lines, and the status view
— and explicitly NOT in the result banner, whose authoritative-last-line trust contract
(`Format-BuildQueueBanner`, `build-queue-outcome-opacity-and-inspect-deny`) must stay
outcome-only. **Lanes:** a `lane ∈ {fast, heavy}` op class adds an admission rule to the claim
loop — the lowest fast-lane waiter may claim ahead of an older heavy waiter, bounded by a
consecutive-fast-passes counter so the heavy head waits at most K fast builds — while everything
below the claim (single slot, reclaim, hygiene, occupancy, results) is byte-identical.

Mission criterion: **efficient** — less blind polling, fewer wasted agent turns, and small
verification ops stop paying big-build latency; with a hard **effective** constraint: zero
regression of the fidelity/hygiene invariants the recent bug fixes paid for.

## Design Decisions

### D1. Duration capture: add `op`/`started_at`/`duration_seconds` to `results/<seq>.json`

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where run-duration history comes from, given it does not exist today. The runner
  never receives the op name (`build-queue-runner.ps1` params: `-Exec -Seq -StateRoot -Worktree`
  + passthrough), so results cannot even be grouped per-op retroactively.
- **Options:**
  - **A — Runner-recorded:** wrapper threads a new `-Op` param to the runner; the runner stamps
    its own start instant at launch and writes `op`, `started_at`, `duration_seconds` into the
    result body it already composes. Survives a wrapper kill (the self-releasing-runner
    property from `build-queue-orphaned-result-on-wrapper-kill`); the wrapper's release-time
    read-merge-write (`build-queue.ps1:429-445`, which refreshes only `exit_code`/`ended_at`)
    preserves the fields by construction.
  - **B — Wrapper-recorded:** the wrapper knows `$Op` and `started_at` already (it writes them
    into `active.lock`). But a killed wrapper loses the enrichment — exactly the failure class
    the runner exists to survive — and the merge direction inverts (the wrapper would need to
    win fields against the runner).
  - **C — Reconstruct from `logs/` mtimes:** fragile, flush-dependent, and silent about op.
- **Recommendation:** A. It follows the established writer split (runner owns the durable
  result; wrapper refreshes only its two fields), costs one param, and makes every future
  consumer (ETA here, the pipeline-visualizer or a retro miner later) read one canonical file.
  `duration_seconds` measures exec-run time (runner start → exit), not queue wait — wait is
  derivable from the enqueue timestamp and is not what ETA needs.
- **Resolution:** Auto-accepted A; an additive internal schema change invisible to the operator
  (legacy result files without the fields are simply ignored by the estimator).

### D2. ETA estimator: median of a rolling per-op window, stored in a small stats file

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How the estimate is computed and where its inputs live, under the constraint
  that every consumer (wrapper enqueue path, status script) must read it cheaply and
  deterministically.
- **Options:**
  - **A — Per-op stats ring file:** after writing its result, the runner appends
    `{seq, duration_seconds, exit_code, ended_at}` to
    `~/.claude/state/build-queue/stats/<op>.json` (ring-capped at 20 entries, atomic
    temp-then-`File.Replace` like every other queue write, fail-open — a stats failure never
    affects the build result). Estimator: median of the last 10 successful (`exit_code == 0`)
    entries; fewer than 3 samples → no estimate (cold start shows `eta=?`). Median over mean:
    robust to the occasional cold-cache outlier build; a percentile knob (p90 "worst case") is
    derivable later from the same ring without schema change.
  - **B — Scan `results/*.json` on demand:** no new file, but the results dir grows without
    bound (nothing prunes it today), the scan cost grows with it, and pre-feature results lack
    `op` anyway — the scan would mostly read useless files.
- **Recommendation:** A. O(1) reads for both consumers, bounded state, atomic writes per house
  convention, and the ring doubles as the lane feature's evidence base. Keyed by op name —
  under the generalization manifest op names are already per-repo-scoped, so cross-repo ops
  never pollute each other's window.
- **Resolution:** Auto-accepted A; internal state layout with no operator-visible surface
  beyond the ETA strings D3 covers.

### D3. ETA surfacing: enqueue echo + waiting lines + status view — never the outcome banner

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** Where a human or agent reads the ETA. The stub asks explicitly about "ETA
  display in the skills' banner contract" — and the banner is the one place it must NOT go: the
  skills instruct agents to trust the LAST stdout line as the authoritative outcome
  (`repos/cognito-forms/.claude/skills/mstest/SKILL.md:37`), and
  `build-queue-outcome-opacity-and-inspect-deny` exists because outcome signals were once
  ambiguous. An ETA suffix on that line dilutes an outcome contract with a prediction.
- **Options:**
  - **A — Three pre-outcome surfaces:**
    1. Enqueue echo: `build-queue: enqueued as seq=641 (op=mstest) position=2 eta-start≈4m
       eta-done≈5m` (today: `build-queue: enqueued as seq=641 (op=mstest)`).
    2. Position lines (emitted on position change in the wait loop):
       `build-queue: queued at position 2 (1 build(s) ahead, eta-start≈3m). Waiting...`.
    3. `build-queue-status.ps1`: active build gains `remaining≈` beside `elapsed:` (estimate
       minus elapsed, floored at `0s`, `?` with no history); each waiter row gains
       `eta-start≈/eta-done≈`. The result banner is untouched.
  - **B — Status view only:** minimal, but the agent's own invocation stays blind — the mined
    friction (blind polling) happens in the invoking session, not in a separate status call.
  - **C — Also suffix the outcome banner:** rejected per above; the banner is outcome-only.
- **Recommendation:** A. It puts the prediction exactly where the waiting already happens, uses
  `≈` and `?` so a prediction is never mistaken for a measurement, and leaves the banner
  contract byte-identical (asserted by the existing `Format-BuildQueueBanner` Pester cases).
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (this is the
  operator/agent-visible display shape).

### D4. Lane admission rule: explicit per-op lane class, not a duration-percentile threshold

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** What makes an op "fast"? The stub offers duration-percentile ("ops with small
  historical duration") vs an explicit op class.
- **Options:**
  - **A — Explicit op class:** `lane: fast|heavy` declared per op — in the generalization
    manifest's op entry when that feature lands first (its schema `version` field anticipates
    the bump), else an interim static map in the wrapper (all four Cognito ops default
    `heavy`; the operator flags e.g. `mstest` fast deliberately). Deterministic forever: the
    same op is always in the same lane, regardless of history contents.
  - **B — Duration-percentile threshold:** ops whose rolling p50 < 60s auto-classify fast.
    Adaptive, zero config — but non-deterministic across invocations (an op flips lanes when
    its window drifts over the threshold), undefined at cold start, and it couples the
    scheduling decision to the stats file, so a corrupted/stale ring changes admission order.
    The queue's own hardening history (`Test-ShouldReclaimLock` moving to confirmed-dead-only;
    born-owner-bound markers) consistently chose deterministic signals over inferred ones.
  - **C — Per-invocation flag (`-Lane fast`):** maximally flexible, but pushes the decision to
    every caller (skills, agents) and invites gaming by a runaway agent wanting to jump the
    queue.
- **Recommendation:** A. A human-reviewed, committed classification is trivially reasoned about
  under the lock machinery ("which lane is this ticket in" never depends on runtime state), and
  misclassification is a one-line manifest fix. Note `mstest` is only *usually* fast (an
  unfiltered full run is minutes) — lane assignment is a policy statement about typical use,
  and the starvation bound (D5) caps the damage of an occasional slow fast-lane op.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (configurability
  boundary: who classifies ops, and in which file).

### D5. Lane mechanics + starvation bound: two logical lanes over ONE slot, K consecutive-fast cap

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** How fast-lane admission works without touching the safety machinery, and how
  much extra latency the heavy head may be charged (operator-experienced worst case).
- **Options:**
  - **A — Claim-eligibility rule + fast-pass counter, K=3:** tickets gain a `lane` field
    (defaulted `heavy` when absent — legacy tickets unaffected). The claim condition in the
    wrapper's poll loop (`build-queue.ps1:237`, today `status -eq 'absent' -and lowestSeq -eq
    seq`) becomes: slot absent AND (I am the lowest *fast* seq AND `fast_passes < K`) OR (I am
    the lowest *heavy* seq AND (no fast waiter exists OR `fast_passes >= K`)). A
    `fast-passes.count` file in the state root holds the consecutive-fast counter; ONLY the
    claim winner writes it (increment on a fast claim, reset to 0 on a heavy claim) —
    single-writer by construction, because the atomic `CreateNew` open of `active.lock` already
    arbitrates exactly one winner. Worst case for the heavy head: K fast runs (~K × the fast
    ops' typical duration — with K=3 and seconds-scale fast ops, tens of seconds against a
    multi-minute build). Reclaim is untouched: `Test-ShouldReclaimLock` keeps its GLOBAL
    lowest-seq arbiter (reclaim is about deleting a dead holder's lock, where a total order
    avoids thundering herds — lanes only shape who claims after the slot is free).
  - **B — Two physical queues (separate state subdirs):** cleaner conceptually, but doubles the
    lock surface the reclaim/occupancy hardening was proven against, and `Get-BuildQueueOccupancy`
    /`build-queue-status.ps1` would need multi-root reads. Rejected on risk.
  - **C — Priority by seq re-numbering (fast ops get low seqs):** corrupts the monotonic seq
    invariant every component assumes (results naming, reclaim ordering, banner attribution).
- **Recommendation:** A with K=3 as the shipped default (a named constant beside
  `$staleThreshold`). K=3 bounds heavy-head delay to a small multiple of fast-op duration while
  letting a burst of quick verification ops drain; K=1 is the conservative fallback if the
  operator prefers near-FIFO. The counter file is advisory scheduling state — if it is missing
  or corrupt, readers treat it as `K` (i.e. fast-lane privilege suspended, pure FIFO), so the
  failure mode is the old behavior, never a livelock.
- **Resolution:** OPEN — recommendation is A with K=3; awaiting operator confirmation (the
  starvation bound is the operator-felt latency policy).

### D6. Preemption: never

- **Classification:** `product-behavior (OPEN — operator confirmation required via the
  pipeline's needs-input round before implementation)`
- **Question:** May a fast op ever interrupt a running heavy build? The stub leans no; it is
  still a product call (the alternative buys minimum fast-lane latency).
- **Options:**
  - **A — No preemption, ever:** a claim happens only when the slot is free. A running build is
    never killed, paused, or deprioritized.
  - **B — Cooperative preemption (kill + requeue the heavy build):** minimizes fast latency but
    discards minutes of work, triggers the crash-hygiene machinery by design (quarantine
    sweeps, locker reaps exist for *abnormal* death), fights the ownership contracts
    (`run_transient_build` awaits its build; killing it mid-await breaks the takeover bracket),
    and re-opens the orphaned-process class `build-queue-no-artifact-or-process-hygiene-on-crash`
    closed.
- **Recommendation:** A. Every hardened invariant in this family assumes a build, once started,
  runs to its own exit; preemption converts normal operation into the crash path. The lane rule
  already caps fast-op latency at "one heavy build," which is the irreducible cost of a
  single-slot machine.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation (per the stub,
  respected as a recommendation, not silently locked).

### D7. No-fidelity-regression constraint: lanes are admission-order-only

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How the feature guarantees it cannot disturb the hardened machinery.
- **Options:**
  - **A — Structural containment:** every change sits strictly above the claim: ticket
    annotation (`lane`), claim-eligibility predicate, and the advisory counter. At any instant
    there is still exactly ONE `active.lock`, written/released/reclaimed by unchanged code;
    `Get-BuildQueueOccupancy`, the occupancy-gated recycle, `Remove-PoisonedArtifacts`,
    `Read-WithRetry`, and the results read-merge-write are not edited. Pester asserts the
    containment (the claim-rule unit is extracted as a pure function à la
    `Test-ShouldReclaimLock` so it is table-testable).
  - **B — Weave lane awareness into occupancy/recycle:** no motivation exists; rejected.
- **Recommendation:** A. The recent bug history is precisely a record of what happens when this
  layer's invariants are assumed rather than preserved; structural containment makes the
  regression class unreachable rather than merely tested-against.
- **Resolution:** Auto-accepted A; an internal architectural constraint, not an operator
  choice.

## User Experience

**Enqueueing (agent's own stdout, the primary surface):**

```
build-queue: enqueued as seq=641 (op=mstest, lane=fast) position=2 eta-start≈4m eta-done≈5m
build-queue: queued at position 2 (1 build(s) ahead, eta-start≈3m). Waiting...
build-queue: build started (pid=18324, seq=641, log=...)
...
build-queue: seq=641 op=mstest RESULT=PASS tests=312 failed=0 (result_fidelity=verified)
```

The last line is byte-identical to today — the banner contract is untouched. `≈` marks every
prediction; `eta-start≈?` / `eta-done≈?` on cold start (fewer than 3 samples for an op ahead).

**Status view (`/build-queue-status`):**

```
=== Active Build ===
  op:      msbuild
  elapsed: 2m 41s   remaining≈ 1m 10s
  ...
=== Waiters ===
  [1] seq=641 op=mstest lane=fast waiting=35s eta-start≈1m eta-done≈2m
```

**Lanes in practice:** a fast-lane `/mstest` enqueued behind two `/msbuild` waiters claims the
slot next (one fast pass consumed); after K consecutive fast passes the oldest heavy waiter is
guaranteed the slot. Ops are classified once, in config (manifest `lane` field or the interim
static map), never per-invocation.

**Failure modes:** stats file missing/corrupt → ETAs degrade to `?`, builds unaffected;
fast-pass counter missing/corrupt → pure FIFO (old behavior); a slow build overrunning its
estimate simply shows `remaining≈ 0s` then keeps running — predictions never gate anything.

## Technical Design

```
enqueue                      claim (changed)                 run (runner)            release
tickets/<seq>.json    ──▶  slot absent AND lane-eligible ──▶ -Op threaded;      ──▶ results/<seq>.json
 {..., op, lane}            (D5 rule over live tickets       records op,             + wrapper refresh
                             + fast-passes.count)             started_at,             (read-merge-write,
                            winner updates counter            duration_seconds        preserves new fields)
                            (single-writer: CreateNew                │
                             arbiter unchanged)                      ▼
                                                          stats/<op>.json (ring 20, atomic, fail-open)
                                                                     │
                              ┌──────────────────────────────────────┘
                              ▼
        ETA reads: wrapper enqueue/position lines + build-queue-status.ps1 (both read-only)
```

- **Runner (`build-queue-runner.ps1`).** New optional `-Op` param (absent → fields omitted;
  legacy invocations byte-identical). Start instant captured before `Start-Process`; result body
  gains `op`, `started_at`, `duration_seconds`. After the atomic result write, append to
  `stats/<op>.json` via the same temp-then-`File.Replace` idiom, wrapped in `Get-SafeValue`
  (fail-open: a stats failure never changes the exit code or the result file).
- **Estimator (shared).** `Get-BuildQueueEta -StateRoot <root> -Op <op>` in
  `build-queue-hygiene.ps1` (the existing shared dot-sourced module — pure-function style like
  `Test-ShouldReclaimLock`/`Format-BuildQueueBanner`, Pester-testable): read the ring, filter
  `exit_code == 0`, median of last 10, `$null` under 3 samples. Consumers format `$null` as `?`.
- **Wrapper (`build-queue.ps1`).** Enqueue echo and position lines gain the D3 strings (ETA for
  a waiter = active build's estimated remaining + sum of estimates of eligible waiters ahead in
  lane order; any unknown term collapses the total to `?`). Ticket body gains `lane` (from the
  manifest op entry or interim map). Claim condition per D5-A; `fast-passes.count` updated only
  by the claim winner immediately after the `CreateNew` open succeeds (single-writer), atomic
  write, treat-unreadable-as-`K`.
- **Status (`build-queue-status.ps1`).** `remaining≈` on the active build (estimate minus
  `Format-Elapsed` input, floored); `lane`/`eta-start≈`/`eta-done≈` per waiter row. Read-only,
  as today.
- **Untouched by construction (D7):** `Set-LockFileAtomic`, `Get-ActiveLockStatus*`,
  `Test-ShouldReclaimLock` (global lowest-seq reclaim arbiter), `Get-BuildQueueOccupancy`, the
  occupancy-gated `Reset-CompilerServer`, all sweeps/reaps, `Format-BuildQueueBanner`, the
  results read-merge-write direction.
- **House invariants:** all new writes atomic temp-then-replace; every new read/write fail-open
  (`Get-SafeValue`); predictions are advisory and never gate a build; scheduling state is
  script-owned and deterministic (explicit lane class + counter file — no inference from
  history on the claim path); no Python pipeline state is touched, so `lazy_core` parity is not
  in play. Coordination with the generalization sibling: the `lane` field rides its manifest
  (schema `version` bump) when that lands first; otherwise the interim static map is deleted
  during that feature's Phase 1.

## Implementation Phases

- **Phase 1 — Duration capture (additive, ships alone).** `-Op` threading; `op`/`started_at`/
  `duration_seconds` in results; `stats/<op>.json` ring writer. Proven done: Pester cases for
  the ring writer + field preservation across the wrapper's release-time merge; a live queued
  run shows the new fields; legacy invocation (no `-Op`) byte-identical.
- **Phase 2 — ETA computation + surfacing.** `Get-BuildQueueEta`; enqueue/position line strings;
  status-view `remaining≈` + waiter ETAs. Proven done: Pester table tests (cold start → `?`;
  median math; unknown-term collapse); banner Pester cases untouched and green; manual status
  check against a live queue.
- **Phase 3 — Lane admission (after the generalization manifest, per the soft dep).** Ticket
  `lane` field; extracted pure claim-eligibility function + Pester truth table (fast ahead of
  heavy; K-cap hands the slot to the heavy head; counter reset on heavy claim; unreadable
  counter → FIFO; legacy laneless tickets → heavy); wrapper claim-loop wiring;
  `fast-passes.count` single-writer update.
- **Phase 4 — Fidelity-regression net + docs.** Pester assertions that reclaim/occupancy/
  recycle-gate call patterns are unchanged under lane scenarios (incl. a fast claim during a
  stale-lock reclaim window); root `CLAUDE.md` build-queue rows + skill prose (the skills'
  "trust the banner" text gains one line noting ETA strings are predictions, not outcomes).

Estimate: ~3 sessions (1: Phases 1-2; 2: Phase 3; 3: Phase 4 + live verification).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Durations recorded | Any queued op completes | `op`/`started_at`/`duration_seconds` in `results/<seq>.json`; ring entry appended | Result + `stats/<op>.json` |
| Fields survive wrapper merge | Normal foreground completion | Runner-written duration fields present after release-time refresh | `results/<seq>.json` post-release |
| Cold-start honesty | Fresh op with <3 samples | `eta-start≈?` / `eta-done≈?`; no crash, no fabricated number | Enqueue echo + status view |
| ETA where waiting happens | Enqueue behind an active build | Position line carries `eta-start≈`; status shows `remaining≈` | Wrapper stdout; `/build-queue-status` |
| Banner contract untouched | Any completion | Last stdout line byte-identical to pre-feature `Format-BuildQueueBanner` output | Existing Pester banner cases |
| Fast-lane overtake | fast ticket enqueued behind heavy waiters, slot frees | Fast seq claims first; counter incremented | Claim-rule Pester truth table; live tickets |
| Starvation bound | K consecutive fast claims with a heavy waiter present | Heavy head claims next; counter resets | Pester truth table |
| No preemption | Fast ticket arrives mid-heavy-build | Active build runs to exit; no kill/requeue | Live check; absence of kill paths in diff |
| Fidelity invariants intact | Lane scenarios incl. reclaim window | Reclaim still global-lowest-seq; occupancy/recycle gating call pattern unchanged | Phase 4 Pester net |
| Degraded-state safety | Delete/corrupt `stats/` or `fast-passes.count` mid-queue | ETAs → `?`; admission → pure FIFO; builds complete normally | Manual fault injection |

## Open Questions

- **D3 — ETA surfacing:** enqueue echo + waiting lines + status view, never the outcome banner.
  Standing recommendation: yes (option A) — predictions ride the pre-outcome surfaces with `≈`/`?`
  markers; the authoritative last-line banner stays outcome-only.
- **D4 — Lane admission rule:** explicit per-op `lane` class (manifest field / interim static
  map) vs a duration-percentile auto-threshold. Standing recommendation: explicit class —
  deterministic across invocations, defined at cold start, immune to stats-file state.
- **D5 — Lane mechanics + starvation bound:** two logical lanes over the single slot with a
  consecutive-fast-passes cap; K=3 default (K=1 = near-FIFO fallback). Standing recommendation:
  A with K=3.
- **D6 — Preemption:** never interrupt a running build. Standing recommendation: no preemption
  (lanes cap fast latency at one heavy build; preemption converts normal operation into the
  crash path the hygiene bugs closed).
- **Deferred empirical checks (implementation-time, not decisions):** measure real per-op
  duration spread from the first weeks of ring data before considering a p90 "worst case"
  display; confirm the position-line ETA composition reads tickets cheaply enough at realistic
  queue depths (≤5 waiters observed historically); verify the `lane` field's manifest carrier
  once `build-queue-generalization`'s D1/D2 resolve (schema `version` bump vs interim map
  deletion timing).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: verified absence of duration data in today's result
  schema; OS-scheduler starvation-bound prior art (bounded express-lane / aging models) and CI
  duration-prediction practice.
- `docs/features/build-queue-generalization/SPEC.md` — the soft-dep sibling whose ops manifest
  carries the `lane` class (its D2 schema anticipates the bump).
- `docs/bugs/build-queue-outcome-opacity-and-inspect-deny/SPEC.md` — the banner trust contract
  D3 protects.
- `docs/bugs/build-queue-recycle-kills-concurrent-worktree-build/SPEC.md` +
  `docs/bugs/build-queue-false-green-on-silent-build-failure/SPEC.md` — the hardened
  lock/occupancy/fidelity invariants behind D7's structural containment.
- `user/scripts/build-queue.ps1`, `build-queue-runner.ps1`, `build-queue-hygiene.ps1`,
  `build-queue-status.ps1`; `user/scripts/build-queue-hygiene.Tests.ps1`.
