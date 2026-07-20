# Bug: execute-plan-liveness discriminator mis-verdicts a LIVE mid-gate-commit cycle as `terminal` (plan-`Complete` branch has no liveness gate → premature recovery + one-writer collision)

**Status:** Fixed
**Fixed:** 2026-07-20
**Fix commit:** c297663f
**Reported:** 2026-07-20
**Pipeline:** claude-config harness (lazy-batch/lazy-bug-batch orchestrator — Gap-2 pause-vs-terminal discriminator)
**Origin:** harden-harness round (observed-friction), item in flight `inspector-track-dashboard` (part-2)
**Root-cause class:** script-defect (primary) + ambiguous-prose (secondary — the plan-`Complete`→`terminal` branch bypasses the verdict-routed liveness probe entirely)
**Companion:** direct OPPOSITE-DIRECTION companion to `execute-plan-liveness-blind-to-dead-lineage-stall` (harden Round 129, fix `3f2294a5`). Round 129 fixed a DEAD lineage mis-verdicted `paused` (recovery suppressed forever); THIS fixes a LIVE lineage mis-verdicted `terminal` (recovery fired prematurely).

## Symptom (verified — LIVE INCIDENT 2026-07-20, `inspector-track-dashboard` part-2, cycle `ac4df7fdc75a91be6`)

The Step 1e.4a pause-vs-terminal discriminator (`lazy-state.py --execute-plan-liveness`, i.e.
`lazy_core.execute_plan_liveness`) classified a **genuinely-alive** `/execute-plan` cycle — one
that had finalized its plan and was mid gate+commit, about to atomically commit — as
`verdict: terminal`. The orchestrator dispatched a recovery cycle to stage+commit the "residue"
while the original cycle was STILL LIVE, producing a **one-writer collision**: the recovery agent
and the still-live cycle-5 wrote the same 15 files concurrently. The two writers converged safely
ONLY because the git-safety / FIFO coordination layer serialized them (both produced the identical
commit `dba37eafa`) — the discriminator itself provided no protection.

Sequence:

1. The `/execute-plan` cycle child reached its FINALIZE step: it flipped the plan-part
   `status:` to `Complete` and ticked all WU checkboxes.
2. It THEN ran the heavy orchestrator-adjacent `qg-rust` gate (5/5 full workspace — minutes long)
   BEFORE its atomic commit. At this moment the cycle was genuinely ALIVE, mid gate+commit.
3. At that instant the tree was dirty/uncommitted, HEAD still at Batch 1, no completion
   notification had fired, and the execute-plan marker was ~50 min old (mtime unchanged — the
   marker is written ONCE at `/execute-plan` Step 1d and never refreshed).
4. The orchestrator read `{plan Complete + uncommitted tree + ~50-min-old marker + no
   notification}` as "died between finalize-writes and commit", ran the discriminator, and
   `--execute-plan-liveness` returned `{marker_present: true, plan_status: Complete,
   verdict: terminal}`.
5. `verdict: terminal` routed the orchestrator STRAIGHT to a recovery dispatch (NO liveness
   confirmation) — which then collided one-writer with the still-live cycle.

## Root cause (Concluded)

`lazy_core.execute_plan_liveness` (`user/scripts/lazy_core/markers.py`, the `status == "Complete"`
branch, currently L186–188) returns `verdict: "terminal"` **whenever** the plan reads
`status: Complete`, with **no check that the dispatched cycle lineage is actually dead**. But
plan-`Complete` is set by `/execute-plan` at its FINALIZE step — BEFORE the gate + the atomic
commit + the marker removal. So `{marker present + plan Complete}` is NOT proof the cycle is
dead; it is precisely the finalize→gate→commit→marker-removal window, during which the cycle may
be:

- **ALIVE**, running the gate, about to commit (the incident) — the orchestrator must WAIT; or
- **DEAD**, having died between finalize-writes and commit — recovery IS appropriate.

The pure function cannot distinguish these (a definitive descendant-liveness probe is a `TaskList`
ORCHESTRATOR capability, not a pure-function capability). Yet unlike the non-`Complete` +
stale-marker case — which Round 129 correctly routes through the verdict `wedge-candidate` to an
orchestrator-confirmed `TaskList` liveness probe (confirm-then-recover) — the `Complete` branch
emits a DIRECT `terminal`, which the Step 1e.4a prose routes STRAIGHT to recovery with **no
liveness confirmation at all**. This is the exact asymmetry: Round 129 gave the non-Complete stall
a confirm-then-recover path; the `Complete` branch never got one.

### Two root gaps (per the observed-friction evidence)

1. **The `plan_status == Complete` terminal-branch has no lineage-liveness gate.** plan-`Complete`
   is set at finalize, BEFORE the gate+commit, so it is not proof the cycle is dead. (THIS fix's
   scope.)
2. **The execute-plan marker mtime is written once at cycle START and never heartbeated**, so
   marker-age measures elapsed cycle time, not staleness-since-death — making any age-based
   inference (including Round 129's 1800s wedge threshold) a false-positive risk on a
   legitimately-long (>30 min) Rust cycle. This is NEUTRALIZED-by-routing here (see below) but is
   the deeper structural root — spun off to the generalized class (see Fix scope §Generalization).

### Why routing (not the marker mtime) is the correct signal

The fix does not try to make the pure function decide liveness. It makes the pure function STOP
emitting a recovery-triggering `terminal` for a case where the cycle might still be alive, and
instead route the orchestrator to the SAME confirm-then-recover `TaskList` probe Round 129
established. After the fix, the only DIRECT `terminal`→recovery paths are marker-ABSENT (the cycle
genuinely cleaned up its marker at completion → safe) and read-error (fail-safe to legacy
recovery). Every "marker present + cycle-might-be-alive" case now routes through the liveness
probe — so **marker mtime alone never drives recovery** (gap 2's false-positive is neutralized: a
legit long cycle is found ALIVE by the probe and waited on).

## Fix scope

1. **`lazy_core.execute_plan_liveness`** — the `status == "Complete"` branch returns a new verdict
   `verdict: "commit-pending"` (marker present + plan `Complete`: the cycle has finalized its plan
   but not yet removed its marker — it is in the gate→commit→marker-removal window; live-vs-dead is
   indeterminate to the pure function). Marker-ABSENT → `terminal` (unchanged; genuinely cleaned
   up) and any read error → `terminal` (unchanged; fail-safe). Purely additive: the non-`Complete`
   `paused`/`wedge-candidate` branches are untouched.
2. **`lazy-batch/SKILL.md` Step 1e.4a** (+ coupled `lazy-bug-batch` overlay, regenerated) — route
   `verdict == "commit-pending"` to the SAME genuine-wedge / confirm-then-recover fallback as
   `wedge-candidate` (the `TaskList` lineage-alive probe per `dispatched-agent-liveness.md`): lineage
   DEAD → route recovery; still LIVE → treat as `paused` (WAIT — it is mid-commit). Remove
   "OR plan `Complete`" from the `terminal` bullet (Complete now routes to `commit-pending`).
   `commit-pending` NEVER tears down the marker (that authority stays HARD-PARKED as
   turn-routing-enforcement decision #12). A false-positive (a legit mid-commit cycle) is SAFE —
   the probe finds it live and waits, so no premature recovery / one-writer collision.
3. **Regression tests** — a `Complete`-plan fixture asserting `verdict == "commit-pending"`
   (fresh AND stale marker — completion routes to the probe regardless of marker age); update the
   two existing tests that asserted `Complete ⇒ terminal`.

### Generalization (over-fit spin-off — the structural root, gap 2)

This is the SECOND consecutive harden round patching a single branch of
`execute_plan_liveness`'s verdict-vs-liveness (Round 129 = non-Complete stall; Round 130 =
Complete mid-commit). The recurring class: the discriminator derives every recovery-triggering
verdict from marker-presence + plan-status + write-once marker-mtime — NONE of which is a true
liveness signal — and each dead/live corner is patched branch-by-branch. The durable structural
fix (a real liveness signal: a marker heartbeat that makes mtime-since-activity meaningful,
and/or folding the confirm-then-recover `TaskList` contract into a single discriminator seam
instead of per-branch verdicts) is spun off to a generalized `/spec-bug`, cited from the Round-130
hardening-log entry.

## Non-goals

- Reinventing the HARD-PARKED (decision #12) mechanical marker-teardown / `--force-run-end`
  authority — `commit-pending` escalates to the existing prose fallback, it does not tear down.
- A `TaskList` probe inside the pure function (an orchestrator-only capability).
- Implementing the marker heartbeat here (gap 2 structural fix) — spun off, not in this round's
  scope.

Fix shipped OUT-OF-PIPELINE via a `harden(...)` commit (see the round in
`docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`).
