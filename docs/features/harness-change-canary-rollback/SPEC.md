# Harness-Change Canary + Rollback — Feature Specification

> Self-healing for the self-improvement loop: a shipped control-surface change enters a canary
> observation window during which its targeted signal and its surface's fresh incident streams
> are watched every run — more aggressively than steady-state review cadence. If the tripwire
> fires (KPI regression past a declared band, or attributable fresh incidents clustering on the
> change's surface), the harness flags the change with the evidence attached and auto-enqueues a
> revert-or-redesign bug item — **flag-and-enqueue, never silent auto-revert**. Revertibility
> metadata (the change's commit set + linked docs + coupled-pair scope, via the provenance
> ledger) is recorded at ship time so backing out is mechanical, not archaeology. The window
> closes with a verdict into the efficacy ledger and monitoring drops back to normal cadence.

**Status:** Complete
**Priority:** P2
**Last updated:** 2026-07-04
**Friction-reduction feature:** yes
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:**
- `intervention-efficacy-tracking` — hard — the canary tripwire consumes the evaluator's
  regression verdicts and window machinery.
- `code-doc-provenance-linkage` — hard — revertibility metadata is the provenance ledger's
  change→commit-set mapping, recorded at ship time.
- `incident-auto-capture` — soft — fresh-incident clusters inside the window are a tripwire
  input; the canary can launch with KPI regression alone.

> Substantive dependencies on ALREADY-IMPLEMENTED contracts (implemented data contracts, not
> sibling specs):
> - `lazy-deny-ledger.jsonl` (per-repo keyed state dir; `lazy_core.py` `_DENY_LEDGER_FILENAME`)
>   — guard denies and `kind: process-friction` entries are v1 fresh-incident inputs.
> - `hook-error.json` breadcrumbs — the fail-OPEN error trail written by the enforcement hooks
>   (`long-build-ownership-guard.sh`, `lazy-dispatch-guard.sh`, `lazy-route-inject.sh`,
>   `lazy-cycle-containment.sh`, `build-queue-enforce.sh`) is the other v1 incident input.
> - `user/scripts/lazy-parity-manifest.json` + `lazy_parity_audit.py` — the machine-readable
>   coupled-pair definitions from which a revert item's pair scope is computed.
> - The ad-hoc enqueue path (`_components/adhoc-enqueue.md` → `bug-state.py --enqueue-adhoc`) —
>   revert-or-redesign items are enqueued through this shipped path.
> - The `anti-overfit-design-gate` scope trigger (`docs/gate/control-surfaces.json`, by role) —
>   the canary arms on exactly the same control-surface manifest; no second scope definition.

---

## Executive Summary

A bad harness change currently persists until a human notices its symptoms in a retro — the
worst-case detection latency for exactly the class of change (hooks, gates, state-script
behavior) whose failures are quiet by design: fail-OPEN hooks fail silently, and an over-broad
deny just looks like agents behaving. There is no observation window, no regression tripwire,
and no prepared revert path — when a revert is finally wanted, reconstructing which commits
constituted the change (and which coupled-pair siblings must revert with it) is archaeology.
This feature serves the mission's "effective" criterion (defects in the harness get concluded,
with evidence) and closes the detection-latency half that `intervention-efficacy-tracking`'s
slower review cadence leaves open.

The design deliberately builds almost nothing new. Canary state is a sub-map on the intervention
record that `intervention-efficacy-tracking` already writes at ship time; the watcher is a mode
of that feature's evaluator, run at every run boundary while any window is open; the scope
trigger is the `anti-overfit-design-gate`'s control-surface manifest (one definition, two
consumers); revertibility metadata is the provenance ledger's change→commit-set mapping plus a
pair-scope computation over `lazy-parity-manifest.json`; and the consequence is the existing
ad-hoc bug enqueue. What is genuinely new is the tripwire semantics: per-run window accrual,
surface-based incident attribution, declared regression bands tighter-triggered than the
efficacy verdict bands, and the evidence-bearing revert item.

The stub's central constraint is preserved as the recommendation and elevated to an explicit
operator decision: **no change class earns true auto-revert in v1**. Reverting a live gate
unattended is itself a gate-weakening act (the sibling gate would have to sign off on its own
disarmament); the canary flags, attaches evidence, enqueues, and notifies — the operator (or the
bug pipeline under full gates) approves and executes any revert.

## Design Decisions

### D1. Canary registration — a sub-map on the intervention record, armed by the shared manifest

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How does a shipped change enter observation — a new artifact, or a field on
  something that already exists?
- **Options:**
  - **A — sub-map on the intervention record (recommended):** at capture time
    (`intervention-efficacy-tracking`'s ship-time write), if the change's touched-file set
    (from the provenance change→commit-set mapping) intersects the control-surface manifest,
    the record gains `canary: {opened: <date>, window_runs: N, surfaces: [...], commit_set:
    [...], pair_scope: [...], degraded_revert_note: <str|none>, status: open}`. Pros: zero new
    state files; the canary inherits the record's residency, atomic writes, and archive
    survival; one artifact tells a change's whole epistemic story (hypothesis → gate verdict →
    canary → efficacy verdict). Cons: couples to the sibling's record schema — acceptable, the
    dep is hard.
  - **B — separate canary registry file:** a second source of truth for "what shipped when",
    guaranteed to drift from the first.
- **Recommendation:** A. The scope test reuses the sibling gate's manifest verbatim (by role) —
  two consumers, one definition, so scope disagreements are structurally impossible.
- **Resolution:** Auto-accepted A; internal state layout on an artifact whose residency is
  already an operator decision in the sibling spec.

### D2. Window sizing and tripwire bands

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, HANDOFF.md;
  recommendation A locked)`
- **Question:** How long is the canary window, and what movement trips it? Single-operator
  cadence makes run-count more meaningful than wall-clock — an idle week must not close (or
  trip) a window.
- **Options:**
  - **A — run-denominated window with a wall-clock ceiling (recommended defaults):** window =
    next 10 completed runs after ship, closing early at 30 days regardless (so a rarely-run
    repo's canaries do not stay armed forever). Tripwire, evaluated every run while open:
    (1) the targeted signal regresses past the declared band — the KPI registry's per-KPI
    regression band when one is declared, else worse than the record's frozen baseline by ≥25%
    relative with ≥3 post-ship occurrences; or (2) ≥2 attributable fresh incidents (D3) inside
    the window. Deliberately hair-triggered relative to the efficacy verdict bands (D5 of the
    sibling spec): a canary trip enqueues an *investigation*, not a verdict, so false positives
    cost one triaged bug stub while false negatives cost weeks of quiet damage.
  - **B — wall-clock window only (e.g. 14 days):** simpler, but idle periods make windows
    vacuously clean and busy days overload them.
  - **C — same window/bands as the efficacy review:** one mechanism, but forfeits the entire
    point — the canary exists to be faster and more sensitive than steady-state review.
- **Recommendation:** A with defaults 10 runs / 30-day ceiling / 25% / 2 incidents, all in one
  constants block, per-record overridable via the hypothesis block.
- **Resolution:** **A — operator-approved 2026-07-04 (HANDOFF.md, "do not re-ask").** Window =
  next 10 completed runs after ship, closing early at 30 days; tripwire = targeted-signal
  regression past the KPI band (else 25% relative with ≥3 post-ship occurrences) OR ≥2 attributable
  fresh incidents. Defaults in one constants block, per-record overridable via the hypothesis
  block.

### D3. Incident attribution rules

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, HANDOFF.md;
  recommendation A locked)`
- **Question:** Which fresh incidents count against which open canary? Wrong attribution either
  blames an innocent change (noise, operator fatigue) or misses the guilty one (silent damage).
- **Options:**
  - **A — surface-based, count-against-all-matching (recommended):** an incident attributes to
    a canary iff (i) its timestamp falls inside the window AND (ii) its emitting surface maps
    into the canary's `surfaces:` set. Mapping: a `hook-error.json` breadcrumb or deny-ledger
    entry names its hook/op — resolve that to the hook script / state-script file; telemetry
    gate-refusal and halt events name their gate. Incidents with no resolvable surface NEVER
    attribute (conservative). When several open canaries share a surface, the incident counts
    against ALL of them — each trip enqueues its own evidence-bearing item and the operator
    disambiguates with the evidence side by side, which is cheap because overlapping
    control-surface canaries are rare in a single-operator repo. Pros: no attribution
    heuristics beyond file identity; misattribution is visible in the evidence rather than
    hidden in a scoring function.
  - **B — most-recent-change-wins:** picks one suspect mechanically; wrong exactly when two
    changes interact, which is the interesting case.
  - **C — content matching (deny text ↔ diff hunks):** highest precision on paper, but it is a
    literal-string heuristic — the exact overfit shape the sibling gate exists to reject.
- **Recommendation:** A — conservative on unknown surfaces, transparent on shared ones. When
  `incident-auto-capture` ships, its clustered incidents replace raw breadcrumb/deny-entry
  counting as input (same attribution rule applied to cluster surfaces).
- **Resolution:** **A — operator-approved 2026-07-04 (HANDOFF.md, "do not re-ask").** Surface-based
  attribution: an incident attributes iff its timestamp falls inside the window AND its emitting
  surface maps into the canary's `surfaces:` set; unknown/unresolvable surfaces NEVER attribute; a
  shared surface counts the incident against ALL matching open canaries (each trips its own
  evidence-bearing item). Note: `incident-auto-capture` has landed on this branch (HANDOFF.md) — its
  clustered incidents are the preferred input, with the same attribution rule applied to cluster
  surfaces; raw deny-ledger/breadcrumb counting is the fallback.

### D4. Does any change class ever earn true auto-revert?

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04, HANDOFF.md;
  recommendation A locked — standing policy, operator-owned)`
- **Question:** The stub leans no. Is there any class (e.g. pure-prose skill edits, doc-only
  changes) where a tripped canary may revert unattended?
- **Options:**
  - **A — no class, v1 (recommended, per the stub):** every trip is flag-and-enqueue. Reverting
    a live gate unattended is itself a gate-weakening act — it would have to pass the sibling
    gate's sign-off protocol, which requires the operator anyway; and an unattended revert of
    half a coupled pair breaks parity (D5). The revert-or-redesign item flows through
    `/spec-bug` → `/plan-bug` → `/execute-plan` under full gates, so an approved revert is
    still executed mechanically — just never *initiated* silently.
  - **B — auto-revert for a whitelisted low-risk class:** saves one triage step on the rare
    trip, at the cost of a second scope taxonomy ("revertible class") that is itself a gated
    control surface, plus an unattended writer to `main`. Not worth it before any efficacy
    data exists on trip precision.
- **Recommendation:** A — revisit only with ledger evidence (e.g. after N trips, if trip
  precision is high and triage latency is the dominant cost, a class could be proposed through
  the sibling gate's own sign-off).
- **Resolution:** **A — operator-approved 2026-07-04 (HANDOFF.md, "do not re-ask").** NO change
  class earns true auto-revert in v1: every trip is flag-and-enqueue. This is a standing,
  operator-owned policy — option B (a whitelisted low-risk revertible class) may only ever be
  introduced later through the sibling gate's own sign-off protocol, never silently, and only on
  accumulated trip-precision evidence.

### D5. Revert-item mechanics — evidence, commit set, and coupled-pair scope

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What exactly does the tripped canary enqueue, so the revert is mechanical
  rather than archaeology — and safe against the coupled-pair hazard?
- **Options:**
  - **A — evidence-bearing bug stub via the existing enqueue (recommended):** on trip, the
    watcher invokes the shipped `bug-state.py --enqueue-adhoc` path with id
    `canary-revert-<intervention_id>`; the brief names the record path; and the seeded bug dir
    receives an `EVIDENCE.md` written by the watcher carrying: the trip reason (band numbers or
    incident list, verbatim ledger/breadcrumb lines), the full `commit_set`, linked docs (SPEC
    / GATE_VERDICT / record), the `pair_scope`, and any `degraded_revert_note`. **Coupled-pair
    hazard, handled at ship time:** `pair_scope` is computed when the canary is registered —
    if the commit set touches any file belonging to a pair defined in
    `user/scripts/lazy-parity-manifest.json` (or the root CLAUDE.md pairs table), the scope
    lists BOTH halves and the evidence instructs that any revert must cover the pair and end
    with `lazy_parity_audit.py --repo-root .` green. Reverting one half of a parity-guarded
    pair breaks the audit — the revert item must carry the pair scope so `/plan-bug` plans the
    whole pair. **Degraded-mode note:** v1 records a static note when the change is known
    revert-unsafe (e.g. it migrated on-disk state or schema); no `git revert` dry-run machinery
    — the bug pipeline determines actual revert feasibility with the repo checked out.
    Recurrence guard: `canary.status: tripped` + the enqueued id stamped on the record; one
    revert item per canary, ever.
  - **B — the watcher prepares an actual revert branch/patch:** tempting, but it puts an
    analysis tool in the business of writing code, duplicating what `/execute-plan` does under
    gates.
- **Recommendation:** A — the canary's job ends at a mechanically-actionable, evidence-complete
  work item.
- **Resolution:** Auto-accepted A; consequence plumbing on shipped paths (enqueue shape is
  operator-visible only as an ordinary bug item, which is the stub-locked behavior).

### D6. Watcher invocation — a mode of the efficacy evaluator, run per run-boundary

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What process evaluates open canary windows, and when?
- **Options:**
  - **A — `efficacy-eval.py --canary` (recommended):** the sibling's evaluator gains a canary
    mode sharing its ledger readers, window accrual, and record-update writer; the end-of-run
    flush invokes it every run while any `canary.status: open` record exists (vs the efficacy
    review path, which only wakes records whose `review_after_runs` threshold matured). "More
    aggressively than steady-state" is thus literal: every run vs every ~20 runs. Pros: zero
    new processes or scripts; the hard dep already says the canary consumes the evaluator's
    window machinery. Cons: one script serves two cadences — mitigated by a clean `--canary`
    subcommand boundary and separate tests.
  - **B — a standalone watcher script:** duplicate ledger/window code, second writer to the
    records — violates single-writer discipline for no gain.
- **Recommendation:** A. On trip it additionally emits a `PushNotification`-worthy line in its
  JSON (`"notify": "canary tripped: <id>"`) for the orchestrator to surface, consistent with
  how harden-harness spin-offs notify.
- **Resolution:** Auto-accepted A; process placement with no operator-visible alternative
  behavior (cadence itself is fixed by the stub's "watched more aggressively" direction).

### D7. Steady-state handoff

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How does a window end, and what remains afterward?
- **Options:** Single candidate, refined: on window close the watcher stamps
  `canary.status: closed-clean` (no trip) or leaves `tripped` (with the enqueued item id), and
  appends a `## Canary <date>` section to the record body summarizing the window (runs
  observed, signal movement, incidents attributed: none/list). The efficacy review then
  proceeds on its own longer schedule against the same record — a clean canary does NOT
  pre-judge the efficacy verdict (a change can be non-damaging yet ineffective), and a tripped
  canary does not skip the verdict (the reconsideration and revert items can merge at triage if
  both fire). Monitoring drops back to the normal KPI-registry cadence — the watcher simply
  stops waking for that record.
- **Recommendation:** As above — the handoff is a status stamp, not a second artifact.
- **Resolution:** Auto-accepted; record-lifecycle plumbing inside the stub-locked "window
  closes with a verdict into the efficacy ledger" direction.

## User Experience

- **Ship time:** invisible. A control-surface completion's intervention record simply carries a
  `canary:` sub-map; the operator sees `"canary_opened": true` in the completion JSON.
- **During the window:** nothing, unless it trips. On a trip, the end-of-run flush output (and
  a push notification) carries:

  ```
  ⚠ canary tripped: containment-tighten-denyset
    reason: 3 fresh incidents on user/hooks/lazy-cycle-containment.sh within 6 runs
            (2 hook-error.json breadcrumbs, 1 process-friction deny-ledger entry)
    enqueued: canary-revert-containment-tighten-denyset (docs/bugs/, evidence attached)
  ```

  The enqueued item is an ordinary bug stub at the head of `docs/bugs/queue.json`; its
  `EVIDENCE.md` lets `/spec-bug` (and the operator, on GitHub mobile) see the trip evidence,
  the exact commit set, and the pair scope without any reconstruction. The operator triages it
  like any bug: revert (the plan covers the whole pair scope + parity audit), redesign, or
  close-as-noise — and a close-as-noise is itself signal for tuning the bands.
- **Window close, no trip:** the record's `## Canary` section shows a clean window; the
  efficacy review later delivers the effectiveness verdict separately.
- **Failure modes:** missing ledger data or unreadable breadcrumbs never error — the window
  simply accrues what is readable, and a window that closes with zero observable runs is
  stamped `closed-clean (no-data)` honestly. The watcher never blocks a run.

## Technical Design

```
ship time (capture in apply_pseudo, via intervention-efficacy-tracking)
  touched files (provenance commit_set) ∩ control-surface manifest ≠ ∅
      └─► record.canary = {window, surfaces, commit_set, pair_scope, note, status: open}

every run boundary (end-of-run flush)
  efficacy-eval.py --canary --repo-root . --json          (read-only over signals)
      ├─ reads: telemetry ledger (targeted signal per run)
      │         lazy-deny-ledger.jsonl + hook-error.json breadcrumbs  (fresh incidents)
      │         [incident-auto-capture clusters, when it ships]
      ├─ attribution: incident surface ∈ canary.surfaces (D3)
      ├─ no trip + window matured ─► record.canary.status = closed-clean  [handoff]
      └─ trip ─► bug-state.py --enqueue-adhoc canary-revert-<id>
                 + EVIDENCE.md into the seeded bug dir
                 + record.canary.status = tripped  (once, ever)         [flag-and-enqueue]
```

- **Registration:** implemented inside `lazy_core.record_intervention` (the sibling's capture
  helper) as a post-step: compute touched files from the provenance mapping, glob-test against
  `docs/gate/control-surfaces.json`, compute `pair_scope` from
  `lazy-parity-manifest.json` (+ the root CLAUDE.md pairs table entries not in the manifest,
  folded in as data during Phase 1), write the sub-map. All writes via
  `lazy_core._atomic_write`; capture parity across both completion handlers is inherited from
  the sibling (audited by `lazy_parity_audit.py`).
- **Watcher:** `--canary` mode in `user/scripts/efficacy-eval.py` — stdlib-only, read-only over
  every signal source, sole writer of `canary.*` record updates and of the trip-time
  `EVIDENCE.md`; enqueue is a subprocess call to the existing `bug-state.py --enqueue-adhoc`
  (never a queue.json hand-edit — HARD CONSTRAINT territory). Not on the state-script compute
  path; invoked from the batch orchestrators' end-of-run flush (mirrored across the coupled
  skill pairs) and runnable on demand.
- **Incident sources (v1):** `lazy-deny-ledger.jsonl` entries (guard denies +
  `kind: process-friction`) and `hook-error.json` breadcrumbs from the per-repo keyed state dir
  (`lazy_core.claude_state_dir` resolution), each mapped to an emitting surface file; telemetry
  ledger gate-refusal/halt events by role. Unknown-surface entries are counted in the window
  summary but never attributed (D3).
- **House invariants honored:** flag-and-enqueue only — no unattended writer to `main`, no
  auto-revert (stub-locked); script-owned deterministic state (all canary fields
  script-written); atomic writes; per-repo keyed state dir; coupled-pair parity respected twice
  (capture-site parity, and pair-scope carried on every revert item); read-only over all logs
  and ledgers; receipt-gated completion untouched; stdlib-only Python. Fail-open watcher: a
  watcher error degrades to "window accrues nothing this run" and never blocks the run —
  enforcement stays with the existing gates, not with the canary.

## Implementation Phases

- **Phase 1 — Registration + revertibility metadata.** Canary sub-map written at capture:
  manifest intersection, provenance commit-set, `pair_scope` computation over
  `lazy-parity-manifest.json` + pairs-table data, degraded-revert note plumbing. Proven by:
  `test_lazy_core.py` fixtures — control-surface fixture change registers with correct pair
  scope; non-scoped change registers no canary; parity audit green.
- **Phase 2 — Watcher: windows, attribution, tripwire.** `efficacy-eval.py --canary` with
  per-run accrual, D2 bands, D3 attribution over fixture deny-ledger/breadcrumb files, honest
  no-data handling. Proven by: `test_efficacy_eval.py` canary fixtures — trip on band
  regression, trip on 2 attributable incidents, no trip on unattributable ones, window close
  stamps.
- **Phase 3 — Consequences.** Trip → enqueue via the existing bug enqueue + `EVIDENCE.md` +
  record stamp + notify line; once-ever recurrence guard; end-of-run flush wiring in the batch
  orchestrators (mirrored across coupled skill pairs). Proven by: end-to-end fixture — repeated
  watcher runs over a tripped canary produce exactly one `canary-revert-<id>` item with
  complete evidence including pair scope.
- **Phase 4 — Steady-state handoff + surfacing.** Close stamps + `## Canary` record sections;
  `/lazy-batch-retro` cites canary outcomes alongside efficacy verdicts; the canary system's
  own KPI row (trip precision: trips whose items were not closed-as-noise) registered. Proven
  by: retro citation renders from fixture records; KPI row present.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Canary arms on scope | Complete a control-surface fixture change vs a non-scoped one | `canary:` sub-map present vs absent | intervention record |
| Pair scope recorded | Fixture commit set touching one half of a manifest pair | `pair_scope` lists both halves + parity-audit instruction in evidence | record + EVIDENCE.md |
| Band tripwire | Fixture ledger regressing the targeted signal past 25% within the window | Trip with band numbers in evidence | `test_efficacy_eval.py` |
| Incident tripwire + attribution | 2 fixture breadcrumbs on the canary's surface; 2 on an unrelated surface | Trip on the former only; unattributable entries listed but not counted | watcher JSON + evidence |
| Flag-and-enqueue only | Any trip | `canary-revert-<id>` bug stub enqueued; NO commit reverts, no writes outside record/evidence/queue | git log + bug dir |
| Once-ever consequence | Repeated watcher runs over a tripped canary | Exactly one revert item; record stamped `tripped` | `docs/bugs/` + record |
| Clean close + handoff | Window matures with no trip | `closed-clean` stamp; efficacy review still fires later on its own cadence | record frontmatter + review section |
| Never blocks a run | Watcher error (unreadable ledger fixture) | Run completes; window notes no-data; exit does not halt the flush | orchestrator flush output |

## KPI Declaration

**Friction-reduction feature:** yes — the canary shortens time-to-detect for the quiet class of
harness change (fail-OPEN hooks, over-broad denies, state-script behavior), whose failures
otherwise persist until a retro. Its own success is measurable, so it declares a KPI (the
measurability gate, `/spec` Step 8.5).

The canary's headline metric is **trip precision** — the fraction of canary trips whose enqueued
`canary-revert-<id>` items were NOT closed-as-noise. High precision means the hair-triggered bands
(D2) are earning their sensitivity rather than fatiguing the operator; low precision means the
bands are mis-tuned. It is `up-is-good`. No baseline can exist before the canary has ever tripped,
so the row is drafted `provenance: pending` / `band: null` (the honest D4-A ladder — never a
fabricated zero). The row is added to `docs/kpi/registry.json` and its signal computation wired in
**Phase 4** (the SPEC's "the canary system's own KPI row … registered" deliverable); the signal
selector `telemetry-ledger` / `canary-trip-precision` is registered in `kpi-scorecard.py` at
spec-finalization so this drafted row lints clean today and renders an honest NO-DATA until Phase 4
lands the computation.

```json
{
  "id": "canary-trip-precision",
  "system": "harness-canary",
  "title": "Canary trip precision",
  "friction": "A canary that trips on noise trains the operator to ignore it; every false trip costs a triaged bug stub and erodes trust in the tripwire. Trip precision measures whether the hair-triggered bands are catching real regressions versus crying wolf.",
  "signal": {
    "source": "telemetry-ledger",
    "selector": "canary-trip-precision"
  },
  "unit": "percent",
  "direction": "up-is-good",
  "baseline": {
    "value": null,
    "captured_at": null,
    "window": "90d",
    "provenance": "pending"
  },
  "band": null,
  "review_by": "2026-12-01",
  "notes": "Precision = trips whose canary-revert-<id> item was NOT closed-as-noise, over all trips in the window. Signal selector registered in kpi-scorecard.py _SOURCES at spec-finalization (renders NO-DATA until compute wired); computation + this registry row land in the feature's Phase 4. Baseline is unmeasurable until the canary has tripped ≥5 times — provenance stays 'pending' (honest, never a fabricated zero) and the band is set with --capture-baseline once real trip data exists."
}
```

## Open Questions

- **D2 / D3 / D4 — RESOLVED** (operator-approved 2026-07-04, HANDOFF.md — see the Design
  Decisions): D2 run-denominated window (10 runs / 30-day ceiling / 25% relative band or KPI band /
  ≥2 attributable incidents, per-record overridable); D3 surface-based attribution
  (unknown-surface-never-attributes, shared surfaces count against all matching); D4 no auto-revert
  class in v1 (flag-and-enqueue always, a standing operator-owned policy). No open product-behavior
  decisions remain.
- Deferred empirical checks: exact telemetry-ledger run-identity fields for per-run window
  accrual (verify against `harness-telemetry-ledger` once locked); the breadcrumb→surface
  mapping table for each hook's `hook-error.json` shape (enumerate during Phase 2 from the hook
  sources); whether `lazy-parity-manifest.json` covers all pairs in the root CLAUDE.md table or
  Phase 1 must fold in extras as data; the end-of-run flush insertion point (shared with the
  sibling's D10 outcome — implement once).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by
  operator directive, 2026-07-04). Key influences: canary-deployment / automated-canary-
  analysis practice reshaped for run-denominated single-operator cadence; SRE burn-rate
  tripwires; GitOps revert-as-PR as the flag-and-enqueue analog.
- `docs/features/intervention-efficacy-tracking/SPEC.md` — record, evaluator, and window
  machinery this feature extends (hard dep).
- `docs/features/code-doc-provenance-linkage/SPEC.md` — change→commit-set mapping (hard dep).
- `docs/features/anti-overfit-design-gate/SPEC.md` — shared control-surface manifest; the
  argument that unattended gate-revert is gate-weakening.
- `docs/features/incident-auto-capture/SPEC.md` — future clustered-incident input (soft dep).
- `user/scripts/lazy_parity_audit.py` + `user/scripts/lazy-parity-manifest.json` — pair-scope
  ground truth.
