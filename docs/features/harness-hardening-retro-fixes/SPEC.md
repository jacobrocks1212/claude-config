# Harness-Hardening Retro Fixes + Anti-Overfit — Feature Specification

> Fix the concrete findings from the 2026-06-16 lazy-batch retro, and give `/harden-harness` an anti-overfit reflex: fix the instance now, but spin off a generalized `/spec`/`/spec-bug` when it detects it is patching a symptom of a broader class.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-16

**Depends on:**

- unified-pipeline-orchestrator — hard — consumes the toolify framework (miner + deterministic-only bar + candidate schema) so harden-harness can auto-identify a repeated dance and spin off a `/spec-bug` to toolify it.

---

## Executive Summary

The retro graded the run A− and flagged a clear theme: the self-healing harness works, but it
treats *symptoms* of design weaknesses. Two hardening rounds patched the same verification-regex
class back-to-back; the second discovered the first's regression tests were never registered
(dead coverage). The durable fixes are structural, and the deeper fix is to give the hardening
stage itself an **anti-overfit reflex** so it stops growing whack-a-mole patches.

This feature delivers two things:

1. **The anti-overfit harden-harness mechanism.** When `/harden-harness` fixes a friction, it
   applies the immediate mechanical fix (so the run is never left broken), and *additionally*
   spins off a generalized `/spec` or `/spec-bug` — enqueued to the front — when it detects an
   over-fit smell: the fix is a narrow phrase-match patch, the class has recurred (≥2), or it
   self-flags as fitting-to-observed-data. This is also the engine that **auto-identifies
   toolification candidates** (a repeated deterministic dance) and spins off a `/spec-bug` to
   toolify it — completing the loop the `unified-pipeline-orchestrator` framework plugs into.
2. **The concrete retro fixes** that aren't owned elsewhere: the verification-section detector
   structural redesign, the `plan_complete` false-alarm, the mcp-test haiku-tier re-evaluation,
   and a dead-coverage guard.

(The `-followups` queue-trim miss and the `mcp-tests` symlink blindspot are fixed by
`unified-pipeline-orchestrator`'s enhanced `__mark_complete__` and `--gate-coverage`. The
stale-marker-arms-guard-globally finding is owned by `multi-repo-concurrent-runs`. They are
cross-referenced here, not duplicated.)

## User Experience

This is harness-internal; the "user" is the operator watching a `/lazy-batch` run and the
`/harden-harness` stage.

- **Anti-overfit in action.** A friction fires `/harden-harness`. The operator sees: (a) the
  immediate mechanical fix committed under full gates (run continues), and (b) when the
  over-fit smell trips, a `harden(spinoff):` note plus a new front-enqueued `/spec`/`/spec-bug`
  item for the general class — surfaced, not silent. The hardening-log round records both the
  patch and the spin-off.
- **Toolify auto-identification.** When harden-harness (or a retro) identifies a repeated
  deterministic dance via the toolify miner, it spins off a `/spec-bug` titled to toolify that
  action, front-enqueued, so the next run shrinks.
- **Verification gate no longer whack-a-moles.** `/spec-phases` and `/blocked-resolution` emit
  a canonical verification-only marker; the detector reads the marker instead of matching
  free-text bold headers, so a novel verification-subsection phrasing no longer gaps the gate.

## Technical Design

### 1. Anti-overfit harden-harness mechanism

Extends `/harden-harness` Step 3 (Act by decision class). Today it does a mechanical fix OR a
NEEDS_INPUT fork. New behavior: mechanical fix **always** lands first; then an **over-fit
detector** decides whether to *also* spin off a generalization spec.

- **Over-fit smell signals** (any one trips a spin-off):
  - The fix adds a literal phrase/string to a matcher (regex, header list, keyword set) — i.e.
    it fits to observed data rather than to structure.
  - The root-cause class has recurred ≥2 times in the hardening log (signature match against
    prior rounds).
  - The agent self-flags the fix as narrow ("this will gap again on the next variant").
  - The friction is a repeated deterministic dance (toolify candidate per the miner).
- **Spin-off action.** Compose a generalized problem statement (the *class*, not the instance)
  and invoke `/spec` (feature-shaped general fix) or `/spec-bug` (bug-shaped) via the
  `adhoc-enqueue` protocol, **front-enqueued** so it is worked next. The choice of `/spec` vs
  `/spec-bug`: structural redesigns and new capabilities → `/spec`; defects/regressions and
  toolify-this-dance → `/spec-bug`.
- **Generalization bound** ("most general within reason"): the spun-off spec targets the
  smallest class that *subsumes the observed instance and its near neighbors* — not a
  speculative rewrite. The problem statement must cite the concrete instance(s) as evidence and
  name the class boundary explicitly. This keeps generalization honest and reviewable.
- **No double-blocking.** Because the instance is already fixed, the spin-off never blocks the
  current run; it is queued work, surfaced via the hardening-log round + a `PushNotification`.
- **Self-recursion guard preserved.** The existing depth-1 hardening guard still applies; a
  spin-off is a `/spec`/`/spec-bug` enqueue, not a recursive hardening dispatch, so it does not
  trip the guard.

### 2. Verification-section detector — structural canonical marker

- **Producers emit the marker.** `/spec-phases` and `/blocked-resolution`, when they write a
  verification-only subsection/row, emit a single canonical annotation — `<!-- verification-only
  -->` per row (or one canonical subsection header defined in a single source of truth).
- **Detector keys off the marker.** `remaining_unchecked_are_verification_only` is computed
  from the marker presence, not from phrase-matching bold-header free text. The growing regex is
  retired (or reduced to a deprecation shim that warns when it would have matched but the marker
  is absent — surfacing un-migrated producers).
- **Single source of truth.** The canonical marker string lives in one component, referenced by
  producers and the detector, with a lockstep test asserting they agree.

### 3. `plan_complete` false-alarm

The feature-level `--verify-ledger` reports `plan_complete:false` for plan-less /
realign-plan-only features even when the plan-scoped form returns `ok:true`. Fix the ledger to
treat "no plan required" as not-a-failure (distinguish *absent-by-design* from *incomplete*),
eliminating the benign-but-noisy recovery chase. Regression test for the plan-less case.

### 4. mcp-test haiku-tier re-evaluation

The freshly-wired haiku tier (`98d00c1`) punted twice on scenarios needing `.md`→YAML
conversion / real diagnosis, each costing a wasted cycle + a sonnet override that then found a
real bug. Re-scope the tier: haiku for ready-to-run YAML happy paths; route
scenario-authoring / first-run conversion / diagnosis cycles to sonnet by **default**, not by
orchestrator override. The routing signal should be script-derived (e.g. scenario is `.md` and
unconverted, or prior verdict was non-definitive), not a per-run human call.

### 5. Dead-coverage guard

Round 24's regression tests were never registered in the runner (dead coverage), caught only
by luck in Round 25. Add a guard that fails (or warns loudly in gates) when a test file exists
under the suite directory but is not collected by the runner — so a hardening round can't land
"tests" that never execute. This is itself an anti-overfit safeguard (it makes the *evidence*
for a fix real).

## Implementation Phases

1. **Anti-overfit engine in `/harden-harness`.** Over-fit smell detector (incl. hardening-log
   signature recurrence), generalization-bound discipline, `/spec`/`/spec-bug` front spin-off
   via `adhoc-enqueue`, hardening-log + PushNotification surfacing. Wire the toolify-candidate
   trigger to the miner from `unified-pipeline-orchestrator`.
2. **Verification-detector structural redesign.** Canonical marker SSOT; `/spec-phases` +
   `/blocked-resolution` emit it; detector rekeyed; deprecation shim for un-migrated producers;
   lockstep test.
3. **`plan_complete` ledger fix** + plan-less regression test.
4. **mcp-test haiku-tier re-scope** with script-derived routing signal + tests.
5. **Dead-coverage guard** in the gate suite + test.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Fix-now + spinoff on over-fit smell | A hardening fix adds a literal phrase to a matcher | Mechanical fix committed AND a front-enqueued `/spec-bug` for the class; both in the hardening-log round | `test_lazy_core.py` / harden-harness dry-run fixture |
| No spin-off when fix is already structural | A hardening fix that changes structure, not a phrase | Mechanical fix only; no spurious spin-off | harden-harness fixture |
| Toolify candidate auto-spins a `/spec-bug` | Miner flags a repeated deterministic dance | Front-enqueued `/spec-bug` to toolify it | integration test with the miner |
| Verification gate survives a novel phrasing | A verification subsection with never-before-seen header text, marker present | Gate passes via marker; no regex growth needed | detector test with novel-header fixture |
| Un-migrated producer is surfaced | A verification subsection without the marker | Deprecation shim warns (does not silently pass) | detector test |
| `plan_complete` not false-alarmed | `--verify-ledger` on a plan-less / realign-only feature | `plan_complete` not reported as failure when plan absent by design | `test_lazy_core.py` |
| Haiku tier routes diagnosis to sonnet by default | mcp-test on an unconverted `.md` scenario | Script routes to sonnet without an orchestrator override | routing-signal test |
| Dead coverage fails gates | A test file present but not collected | Gate fails/warns naming the orphaned file | gate-suite test |

## Open Questions

- **Over-fit recurrence threshold.** Is ≥2 the right spin-off trigger, or should the first
  occurrence of a phrase-match patch already spin off? Default: phrase-match patch spins off on
  first occurrence; non-phrase recurrence needs ≥2. Confirm in `/spec-phases`. (estimated —
  verify during Phase 1)
- **Canonical marker form.** Per-row `<!-- verification-only -->` comment vs a single canonical
  subsection header — pick the one the existing `check-docs-consistency.ts` schema can validate
  most cleanly.
- **Haiku-tier routing signal source.** Exact script-observable conditions that force sonnet
  (unconverted `.md`, prior non-definitive verdict, scenario-authoring) — enumerate in Phase 4.

## Research References

None — internal harness mechanics; no external research. Evidence base:
`LAZY_BATCH_REVIEW_2026-06-16_overview_2.md` (HIGH: haiku-tier punts; MEDIUM: recurring harness
bugs + verification-detector whack-a-mole; operator question 3: over-fitting is mild and
self-flagged, durable fix is structural).
