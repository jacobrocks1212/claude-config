# Intervention Efficacy Tracking (Hypothesis Ledger) — Feature Specification

> Every harness change is an implicit hypothesis ("this gate/hook/contract change will reduce
> friction signal X") that is never tested. This feature records the hypothesis at ship time —
> targeted signal, frozen baseline stats, expected direction, review-by threshold — as a
> deterministic, script-owned intervention record, then evaluates it against post-ship telemetry
> and writes a CONFIRMED / REFUTED / INCONCLUSIVE verdict. A REFUTED intervention auto-enqueues a
> reconsideration bug item (evidence attached, recurrence-guarded) instead of quietly persisting
> as dead weight; INCONCLUSIVE past N reviews escalates to operator triage; CONFIRMED closes the
> hypothesis. Verdicts become inputs to `/lazy-batch-retro`, replacing narrative success claims.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution
batch); fleshed out via internal desk research 2026-07-04 (Gemini research skipped by operator
directive — see RESEARCH.md)

**Depends on:**
- `harness-telemetry-ledger` — hard — verdicts are computed by comparing baseline vs post-ship
  windows over ledger event streams; the record schema references concrete ledger events.
- `friction-kpi-registry` — soft — KPI registry entries are the preferred signal vocabulary for
  hypothesis targets, but a raw ledger-event reference suffices.
- `code-doc-provenance-linkage` — soft — the change→commit-set mapping enriches intervention
  records; a commit range captured at ship time suffices for v1.

> Substantive dependencies on ALREADY-IMPLEMENTED contracts (implemented data contracts, not
> sibling specs):
> - `lazy_core.apply_pseudo` (`user/scripts/lazy_core.py:3241`) — the `__mark_complete__` /
>   `__mark_fixed__` completion gates are the sole author of receipts and the natural
>   script-owned chokepoint for capture. Precedent for attaching extra return keys
>   (`queue_trimmed`, `warnings`) already exists.
> - `lazy_core._atomic_write` + `parse_sentinel` + `write_completed_receipt` — every record and
>   verdict write reuses the atomic-write and frontmatter-sentinel machinery; no new file-IO
>   idioms.
> - The ad-hoc enqueue path (`_components/adhoc-enqueue.md` → `bug-state.py --enqueue-adhoc`) —
>   REFUTED reconsideration items are enqueued through this existing shipped path, never a
>   reimplementation.
> - `--backfill-receipts` / `provenance: backfilled-unverified` — the honest-debt provenance
>   convention this feature's backfill option mirrors.
> - The coupled-pair parity contract (`lazy_parity_audit.py --repo-root .`) — capture lands in
>   both state scripts' completion gates and is parity-audited.

---

## Executive Summary

The harness self-improves via `/lazy-batch-retro` and `/harden-harness`, but the loop is open:
interventions ship, their `COMPLETED.md` claims success, and nothing ever checks whether the
targeted friction actually declined. The hardening log already carries dozens of rounds whose
fixes were never re-measured; interventions that did not work — or made things worse —
accumulate indefinitely because no mechanism ever concludes "this change failed." This is the
"effective" mission criterion applied to the harness itself: completions must carry real
evidence, and for a friction-reduction change the only real evidence is post-ship signal
movement.

The solution is a hypothesis ledger with three script-owned moments. **Capture:** when a
claude-config item completes (`__mark_complete__` / `__mark_fixed__`) or a `/harden-harness`
round commits, a deterministic intervention record is written — item id, targeted signal (a
`friction-kpi-registry` KPI id or a raw `harness-telemetry-ledger` event reference), frozen
baseline window stats, expected direction, signal-independence declaration, and a review-after
threshold. **Evaluation:** a standalone stdlib evaluator (`efficacy-eval.py`, read-only over the
telemetry ledger) compares the post-ship window against the frozen baseline and writes a verdict
into the record. Single-operator reality is embraced: this is before/after comparison with
confounder annotations (other interventions landing in-window are recorded on the verdict), not
pretend A/B rigor. **Consequences:** REFUTED auto-enqueues a `reconsider-<id>` bug item through
the existing ad-hoc enqueue path with the evidence attached (recurrence-guarded so a refuted
item cannot re-enqueue forever); INCONCLUSIVE past N reviews is surfaced for operator triage;
CONFIRMED closes the hypothesis. The record schema carries a `signal_independence` field from
day one — the sibling `anti-overfit-design-gate` consumes it, and the evaluator prefers
telemetry the intervention does not itself emit.

The alternative — leaving efficacy to retro narrative — is the status quo the self-evolution
cluster exists to end. The design's cost is one new record file per shipped harness change plus
one read-only evaluator script; it adds zero steps to non-harness repos and zero LLM-inferred
state.

## Design Decisions

### D1. Capture trigger and author — inside the completion gates, script-owned

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where is the intervention record written — inside `--apply-pseudo`'s
  `__mark_complete__` / `__mark_fixed__` handlers (script-owned), or as an orchestrator step in
  the `/lazy*` skill prose?
- **Options:**
  - **A — script-owned, inside `apply_pseudo`:** a `lazy_core.record_intervention(...)` helper
    called by both completion handlers after the receipt write; the return dict gains an
    `intervention_recorded` key (precedent: `queue_trimmed`). Plus a `--record-intervention` CLI
    action for the `/harden-harness` round path and manual capture. Pros: deterministic, single
    author, parity-auditable, cannot be skipped by wrapper drift. Cons: `apply_pseudo` grows.
  - **B — orchestrator prose step:** the batch skills instruct the cycle to write the record.
    Pros: no script change. Cons: LLM-authored state, exactly the class the mission forbids;
    coupled-pair prose drift risk across six skills.
- **Recommendation:** A — the stub already locks "deterministic, script-owned"; the repo's
  invariant is script-emitted state over LLM-inferred state, and `apply_pseudo` is the shipped
  single-author chokepoint for completion-time writes.
- **Resolution:** Auto-accepted A (operator-locked 2026-07-04); the stub locks the direction
  and the only choice is which shipped chokepoint hosts it — not a product call.

### D2. Hypothesis declaration surface, and whether an undeclared hypothesis blocks completion

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04 — recommended
  option taken)`
- **Question:** The script can freeze a baseline deterministically, but it cannot infer the
  targeted signal or expected direction. Where does the hypothesis get declared, and what
  happens at completion when it wasn't?
- **Options:**
  - **A — parseable SPEC block, degrade on absence:** SPECs for harness changes carry an
    `## Intervention Hypothesis` block (list-item fields: `target_signal`,
    `expected_direction`, `signal_independence`, `review_after_runs`) parsed by a
    `lazy_core.parse_intervention_hypothesis` helper (same idiom as `feature_tier` reading
    `**Priority:**`). Absent block → the record is still written with
    `target_signal: undeclared` and is INCONCLUSIVE-by-construction, surfaced for triage;
    completion is NOT blocked. Pros: capture never breaks the pipeline; the forcing function
    for declaring lives upstream (the `friction-kpi-registry` `/spec`-time measurability gate
    and the sibling design gate). Cons: undeclared debt can accumulate if upstream gates lag.
  - **B — fail-closed:** `__mark_complete__` refuses when the repo is intervention-enabled and
    no hypothesis block exists. Pros: no undeclared debt. Cons: blocks every doc-only or
    non-friction harness item until an exemption vocabulary is designed; a new hard gate on day
    one of an unproven subsystem.
- **Recommendation:** A for v1 — honest degradation over a new hard gate; mirrors the
  `--backfill-receipts` philosophy (debt recorded loudly, not silenced, not blocking). Revisit
  fail-closed once the sibling gate is live for control-surface changes.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Parseable
  `## Intervention Hypothesis` SPEC block; degrade-on-absence writes
  `target_signal: undeclared` and completion is NEVER blocked.

### D3. Record schema

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What fields does the intervention record carry?
- **Options:** Single serious candidate, refined: a frontmatter-sentinel markdown file
  (parseable by the existing `lazy_core.parse_sentinel`) with:
  `kind: intervention`, `intervention_id` (item slug or `harden-<YYYY-MM>-r<N>` for hardening
  rounds), `pipeline: feature|bug|hardening`, `shipped_date`, `shipped_commit` (HEAD at
  capture), `commit_set` (v1: the capture commit / known cycle range; enriched to the full
  change→commit-set mapping when `code-doc-provenance-linkage` ships), `target_signal`
  (`kpi:<system>.<kpi-id>` preferred, `event:<ledger-event-type>` accepted, or `undeclared`),
  `expected_direction: decrease|increase`, `signal_independence:
  independent|self-emitted|mixed` (justification sentence in body), `baseline:` (frozen summary
  — window bounds, event count, value), `review_after_runs`, `review_count`, `status:
  open|confirmed|refuted|inconclusive`, `escalated`, `reconsideration_enqueued`. The body holds
  the human-readable hypothesis statement and appended `## Review <date>` sections.
- **Recommendation:** As above. Freezing baseline stats INTO the record at ship time is
  load-bearing: the raw telemetry ledger lives in the per-repo keyed state dir (untracked,
  rotation-eligible per that feature's retention decision), so the baseline must not depend on
  raw-event retention.
- **Resolution:** Auto-accepted (operator-locked 2026-07-04); field layout of a machine
  artifact with the operator-visible choices (residency, windows, consequences) carried
  separately in D4/D5/D7/D8.

### D4. Record residency — central `docs/interventions/` vs alongside `COMPLETED.md`

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04 — recommended
  option taken)`
- **Question:** Where do intervention records live? The operator reads these (GitHub mobile
  included), and the evaluator must enumerate all open hypotheses cheaply.
- **Options:**
  - **A — central `docs/interventions/<intervention_id>.md`, one file per intervention:**
    committed, human-readable, trivially enumerable by the evaluator. Pros: survives the bug
    pipeline's archive-on-fix (a record co-resident with a bug dir would be archived with it
    and the evaluator would have to chase archives); gives hardening rounds — which have no
    item dir of their own — a natural home; one `ls` enumerates open hypotheses. Cons: one more
    top-level docs dir; the record is one hop away from the item's other artifacts (mitigated:
    the record carries the item id and the item's `COMPLETED.md`/`FIXED.md` receipt is
    unchanged).
  - **B — item-dir residency (`docs/features/<slug>/INTERVENTION.md`):** co-located with the
    receipts. Pros: everything about an item in one dir. Cons: archived/moved with bug dirs;
    no home for hardening-round interventions; evaluation requires a full docs tree walk; the
    file risks being read as a pipeline sentinel by tooling that globs item dirs.
  - **C — state-dir JSONL ledger:** append-only, machine-friendly. Cons: untracked ("What's NOT
    Tracked: ephemeral state"), invisible on GitHub mobile, lost on state-dir cleanup —
    unacceptable for a durable hypothesis ledger.
- **Recommendation:** A — archive-survival and the hardening-round case are decisive, and the
  flat central dir is what the sibling `anti-overfit-design-gate` and
  `harness-change-canary-rollback` compose against (gate-verdict pointers and canary fields
  live on this record).
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Central
  `docs/interventions/<intervention_id>.md`, one committed file per intervention.

### D5. Window semantics — lengths, minimum-sample rule, and verdict bands

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04 — recommended
  option taken)`
- **Question:** How long are baseline and post-ship windows, when is a comparison allowed to
  conclude anything, and what movement earns CONFIRMED vs REFUTED?
- **Options:**
  - **A — run-count-based windows with a min-sample floor (recommended defaults):** baseline =
    the trailing 20 runs of ledger history at capture (or all available if fewer, recorded as
    such); post-ship window accrues until `review_after_runs` (default 20) runs have completed
    since `shipped_commit`; a verdict other than INCONCLUSIVE additionally requires ≥5
    occurrences of the targeted signal across the two windows combined. Verdict bands: movement
    ≥20% relative in the expected direction → CONFIRMED; ≥20% against it → REFUTED; else, or
    min-sample unmet, INCONCLUSIVE. Single-operator cadence makes run-count far more meaningful
    than wall-clock — a two-week vacation must not conclude anything.
  - **B — wall-clock windows (e.g. 14 days / 30 days):** simpler to reason about on a calendar.
    Cons: idle periods produce empty windows that read as signal; run density varies wildly.
  - **C — statistical testing (e.g. Mann-Whitney on per-run values):** more rigorous-looking.
    Cons: pretend rigor at n≈20 with autocorrelated single-operator data — exactly what the
    stub forbids; a fixed relative band with a min-sample floor is honest about its precision.
- **Recommendation:** A. All four numbers (20 / 20 / 5 / 20%) are declared defaults in one
  constants block, overridable per-record via the hypothesis block — they are starting points
  to be tuned by this feature's own ledger, not laws.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Run-count
  windows with defaults baseline 20 runs / review-after 20 runs / min-sample 5 / ±20% relative
  bands, declared in one constants block, per-record overridable via the hypothesis block.

### D6. Confounder annotation mechanics

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How are overlapping interventions recorded on a verdict, and do they change it?
- **Options:**
  - **A — annotate always; cap at INCONCLUSIVE only on same-signal overlap:** at evaluation
    time the evaluator lists every other intervention record whose ship date falls inside this
    record's post window as `confounders:` on the review. If any confounder targets the SAME
    `target_signal`, the verdict is capped at `INCONCLUSIVE (confounded)` — attribution is
    genuinely impossible. Different-signal confounders annotate without capping.
  - **B — annotate only, never cap:** maximal verdict throughput, but a REFUTED verdict caused
    by a sibling change would auto-enqueue a wrong reconsideration item.
- **Recommendation:** A — the stub locks the annotation; the cap is the conservative reading of
  "not pretend A/B rigor" (never let confounded data trigger an automatic consequence), and it
  errs toward inaction, which is safe because INCONCLUSIVE has its own escalation path (D8).
- **Resolution:** Auto-accepted A (operator-locked 2026-07-04); conservative verdict
  arithmetic on confounded data is an internal correctness property, not an operator-facing
  mode choice.

### D7. REFUTED consequence — auto-enqueue mechanics and recurrence guard

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How does a REFUTED verdict become a work item without looping forever?
- **Options:**
  - **A — existing ad-hoc bug enqueue + two-layer guard:** the evaluator invokes the shipped
    `bug-state.py --enqueue-adhoc --id reconsider-<intervention_id> --name ... --brief ...`
    path (the same `--type bug` route `_components/adhoc-enqueue.md` documents for
    harden-harness spin-offs; never a reimplementation). The brief names the record path, the
    verdict, and revert-or-redesign as the question. Guard layer 1: skip if a
    `docs/bugs/reconsider-<id>/` dir exists (open or archived). Guard layer 2: stamp
    `reconsideration_enqueued: <date>` on the record — once stamped, never enqueue again for
    that intervention, even if the bug dir vanishes. A refuted item gets exactly one
    reconsideration, ever; a REFUTED verdict on the *reconsideration's own* intervention record
    is a fresh id and is not blocked.
  - **B — NEEDS_INPUT-style halt for operator approval before enqueue:** safer-feeling but
    contradicts the stub's locked "REFUTED → auto-enqueue" direction and turns a queued,
    non-blocking consequence into a halt.
- **Recommendation:** A — the enqueue destination (`/spec-bug` investigation) is itself the
  review step: the reconsideration item still passes through spec, plan, and the operator's
  normal triage before anything is reverted. Nothing is reverted by the evaluator.
- **Resolution:** Auto-accepted A (operator-locked 2026-07-04); the stub locks auto-enqueue
  and the guard shape is internal plumbing on a shipped path.

### D8. INCONCLUSIVE escalation after N reviews

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04 — recommended
  option taken)`
- **Question:** An INCONCLUSIVE hypothesis re-reviews on its cadence — when and how does it
  stop silently spinning and reach the operator?
- **Options:**
  - **A — escalate after 2 INCONCLUSIVE reviews, surface passively:** the record gains
    `escalated: true`; the evaluator's summary output lists escalated records under a "needs
    triage" heading, and `/lazy-batch-retro` cites them. No sentinel, no halt — an unresolvable
    hypothesis is information, not a blocker.
  - **B — escalate via a NEEDS_INPUT.md decision round:** guarantees operator attention but
    manufactures pipeline halts for items that are already Complete, and NEEDS_INPUT is an
    item-lifecycle sentinel, not a fleet-triage channel.
  - **C — never escalate; review forever:** dead hypotheses accumulate — the exact disease this
    feature treats.
- **Recommendation:** A with N=2 — after two windows with no signal, more waiting rarely helps;
  the operator decides whether to close it `inconclusive-accepted`, refine the hypothesis, or
  treat it as refuted.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). Escalate
  after N=2 INCONCLUSIVE reviews; passive surfacing (evaluator needs-triage output + retro
  citation), never a sentinel or halt.

### D9. Backfill policy for already-shipped interventions

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04 — recommended
  option taken)`
- **Question:** Dozens of hardening rounds and completed harness items predate this feature. Do
  they get records?
- **Options:**
  - **A — no bulk backfill; manual opt-in via `--record-intervention`:** the manual CLI accepts
    `--shipped-commit`/`--shipped-date` overrides and stamps
    `provenance: backfilled` (mirroring the receipt gate's `backfilled-unverified` honesty
    convention). The operator backfills the handful of changes worth measuring; everything else
    starts fresh. Pros: no flood of undeclared-hypothesis records with unreconstructable
    baselines (the telemetry ledger did not exist pre-ship, so most backfilled baselines would
    be empty anyway). Cons: pre-existing dead weight stays unmeasured unless hand-picked.
  - **B — bulk backfill every `COMPLETED.md`/`FIXED.md` in claude-config:** complete coverage
    on paper, but nearly all records would be `target_signal: undeclared` + `baseline:
    unavailable` — noise that buries the real ledger at birth.
- **Recommendation:** A — measurement starts where measurement is possible; honest provenance
  marks the exceptions.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). No bulk
  backfill; manual opt-in via `--record-intervention --shipped-commit/--shipped-date`,
  stamped `provenance: backfilled`.

### D10. Evaluator invocation cadence

- **Classification:** `product-behavior (RESOLVED — operator-approved 2026-07-04 — recommended
  option taken)`
- **Question:** When does evaluation actually run?
- **Options:**
  - **A — end-of-run flush + on-demand, retro cites:** the batch orchestrators invoke
    `efficacy-eval.py --repo-root . --json` once during the existing end-of-run flush
    (alongside the device/host-deferral flushes); it writes due verdicts and prints the
    summary. The operator can also run it any time, and `/lazy-batch-retro` shells it in
    report-only mode to cite verdicts instead of narrative claims. Pros: verdicts land exactly
    when new run data exists; zero scheduler infrastructure; not on the state-script compute
    path (the `lazy-queue-doc.py` precedent). Cons: a long gap between runs delays verdicts —
    acceptable, since no new data accrues in the gap anyway.
  - **B — a step inside `/lazy-batch-retro` only:** couples verdicts to retro cadence; retros
    are not run after every batch.
  - **C — scheduled (cron/trigger):** wall-clock scheduling contradicts run-count windows and
    adds unattended write machinery for no data gain.
- **Recommendation:** A — run-boundary evaluation matches run-count windows one-to-one.
- **Resolution:** **A** (operator-approved 2026-07-04 — recommended option taken). End-of-run
  flush in the batch orchestrators (mirrored across the coupled pair) + on-demand + a
  `/lazy-batch-retro` report-only citation step.

## User Experience

The operator's normal flow changes in three small places:

1. **Authoring:** a harness-change SPEC gains one short block (nudged by `/spec` for
   claude-config items; the `friction-kpi-registry` measurability gate is the hard forcing
   function for friction-reduction features):

   ```markdown
   ## Intervention Hypothesis

   - target_signal: kpi:containment.runaway-trips
   - expected_direction: decrease
   - signal_independence: independent — trips are counted by the containment hook's deny
     ledger, which this change does not touch
   - review_after_runs: 20
   ```

2. **Ship time:** completion output (the `apply_pseudo` JSON) reports
   `"intervention_recorded": true` and the record lands at
   `docs/interventions/<id>.md`, committed with the cycle like any other doc. No new operator
   action.

3. **Verdicts:** at the end of a batch run (and on demand):

   ```
   $ python3 user/scripts/efficacy-eval.py --repo-root . --json
   {
     "reviewed": 3,
     "verdicts": [
       {"id": "containment-tighten-denyset", "verdict": "confirmed", "delta": "-38%"},
       {"id": "adhoc-fix-probe-cache", "verdict": "refuted", "delta": "+31%",
        "consequence": "enqueued reconsider-adhoc-fix-probe-cache"},
       {"id": "spec-gate-tune", "verdict": "inconclusive", "reason": "min-sample 2/5"}
     ],
     "needs_triage": ["old-halt-tweak (escalated: 2 inconclusive reviews)"]
   }
   ```

   A REFUTED verdict announces the enqueued reconsideration item exactly like any ad-hoc
   enqueue; the item then flows through `/spec-bug` normally, where the operator decides
   revert vs redesign vs accept. Failure mode: a missing/empty telemetry ledger never errors —
   the review records `INCONCLUSIVE (no-ledger-data)` and moves on.

## Technical Design

```
SPEC.md hypothesis block          __mark_complete__ / __mark_fixed__ / --record-intervention
  (target, direction,      ──►      lazy_core.record_intervention(...)            [capture]
   independence, window)            freezes baseline from telemetry ledger
                                    └─► docs/interventions/<id>.md   (atomic, committed)

~/.claude/state/<repo_key>/       efficacy-eval.py  (stdlib, read-only over ledger)
  telemetry ledger (JSONL)  ──►     post-window vs frozen baseline, confounder scan  [evaluate]
                                    └─► record updated: status/reviews (atomic)
                                    └─► REFUTED: bug-state.py --enqueue-adhoc
                                        reconsider-<id>  (recurrence-guarded)      [consequence]
```

- **Capture (`lazy_core.record_intervention`):** shared helper; called from both scripts'
  completion handlers inside `apply_pseudo` (coupled-pair parity, audited by
  `lazy_parity_audit.py`) and from a new `--record-intervention` CLI action (present on both
  state scripts for parity; `/harden-harness` invokes it after a round's commit, replacing
  nothing — additive to its Step 4 log). Capture is repo-opt-in via a top-level
  `"interventions": true` flag in `docs/features/queue.json` (the `"autodiscover": true`
  precedent — only claude-config sets it; every other repo is byte-identical). With the flag
  on, every completion is captured (undeclared hypotheses degrade per D2); with it off, capture
  fires only when a SPEC carries the hypothesis block. Baseline stats are computed by a
  read-only scan of the telemetry ledger at the moment of capture and frozen into the record;
  ledger absent → `baseline: unavailable` recorded honestly, never an error. All writes go
  through `lazy_core._atomic_write`.
- **Records:** frontmatter-sentinel markdown per D3/D4, parsed with the existing
  `lazy_core.parse_sentinel`. Records are committed docs — durable, diffable, readable on
  GitHub mobile — never state-dir ephemera.
- **Evaluator (`user/scripts/efficacy-eval.py`):** standalone stdlib script (the
  `toolify-miner.py` / `lazy-queue-doc.py` precedent: analysis tools stay OFF the state-script
  compute path). Read-only over the telemetry ledger; sole writer of record updates; invokes
  the existing enqueue subprocess for consequences. `--repo-root`, `--json`, `--dry-run`
  (report verdicts without writing), `--id <intervention_id>` (single-record review). Exit 0
  even when verdicts are REFUTED — verdicts are data, not errors. Tests in
  `test_efficacy_eval.py` (pytest, hermetic via `LAZY_STATE_DIR` and temp repos, matching
  `test_lazy_queue_doc.py` conventions).
- **Signal resolution:** `kpi:<system>.<kpi-id>` targets resolve through the
  `friction-kpi-registry` registry (by feature-id role: its machine-readable KPI declarations
  name the ledger event sources); `event:<type>` targets filter the ledger directly. Both
  reduce to "count/aggregate matching ledger events per run window", so the evaluator works
  with or without the registry (soft dep).
- **Signal independence:** the `signal_independence` field is declared at hypothesis time and
  carried verbatim on the record. The evaluator does not enforce it (that is the sibling
  `anti-overfit-design-gate`'s check, by feature-id role); it annotates reviews of
  `self-emitted` signals so a confirmed-by-its-own-signal verdict is visibly weaker.
- **House invariants honored:** script-owned deterministic state (capture and verdicts are
  script-written; no LLM-inferred fields); atomic writes throughout; per-repo keyed state dir
  respected (ledger reads via `lazy_core.claude_state_dir` resolution); coupled-pair parity
  (capture in both completion gates, CLI on both scripts); read-only miner discipline (the
  evaluator never mutates the ledger it reads); receipt-gated completion untouched (the record
  is written after, and never gates, the receipt in v1 per D2); stdlib-only Python.

## Implementation Phases

- **Phase 1 — Record + capture.** `lazy_core.record_intervention` +
  `parse_intervention_hypothesis`; capture wired into both completion handlers in
  `apply_pseudo` (return-key `intervention_recorded`); `--record-intervention` CLI on both
  state scripts; queue-flag opt-in; baseline freezing against the telemetry ledger with honest
  degradation. Proven by: `test_lazy_core.py` fixtures (declared, undeclared, no-ledger,
  flag-off byte-identical) + `lazy_parity_audit.py` green.
- **Phase 2 — Evaluator.** `efficacy-eval.py` with window accrual, min-sample, verdict bands,
  confounder scan/cap, record updates, `--dry-run`/`--json`/`--id`. Proven by:
  `test_efficacy_eval.py` covering CONFIRMED/REFUTED/INCONCLUSIVE, confounded cap, undeclared,
  and no-data paths.
- **Phase 3 — Consequences + surfacing.** REFUTED auto-enqueue via the existing bug enqueue
  with the two-layer recurrence guard; INCONCLUSIVE escalation stamping; end-of-run flush
  invocation added to the batch orchestrators (mirrored across the coupled skill pairs) and a
  `/lazy-batch-retro` citation step. Proven by: an end-to-end fixture run producing a
  reconsideration item exactly once across repeated evaluations.
- **Phase 4 — Hardening-round capture + optional backfill.** `/harden-harness` Step 4 invokes
  `--record-intervention` for mechanical-fix rounds; manual backfill flow per the D9 outcome
  (`provenance: backfilled`). Proven by: a hardening-round dry run producing a record with
  `pipeline: hardening`.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Capture on completion | `--apply-pseudo __mark_complete__` on a flagged repo | `docs/interventions/<id>.md` written; JSON carries `intervention_recorded: true` | apply_pseudo output + record file |
| Byte-identical elsewhere | Completion in a repo without the queue flag or hypothesis block | No record written; output unchanged from pre-feature | apply_pseudo output diff |
| Baseline frozen | Capture, then delete/rotate the telemetry ledger | Later evaluation still uses the recorded baseline | record `baseline:` vs review body |
| Verdict arithmetic | Fixture ledgers with known deltas | CONFIRMED / REFUTED / INCONCLUSIVE per D5 bands; min-sample enforced | `test_efficacy_eval.py` |
| Confounder cap | Two records shipping same-signal changes in-window | Both reviews capped `INCONCLUSIVE (confounded)` with cross-annotations | record review sections |
| REFUTED enqueues once | Repeated evaluator runs over a REFUTED record | `reconsider-<id>` exists exactly once; record stamped `reconsideration_enqueued` | `docs/bugs/` + record frontmatter |
| Escalation | Third evaluation of a twice-INCONCLUSIVE record | `escalated: true`; listed under needs-triage output | evaluator JSON |
| Parity | Change to either completion handler | `lazy_parity_audit.py --repo-root .` green | parity audit output |

## Open Questions

All open decisions were resolved 2026-07-04 (operator-approved; every recommendation taken —
see D2/D4/D5/D8/D9/D10 above). The formerly-deferred empirical checks were verified during
Phase 1 implementation:

- **Telemetry-ledger run identity + v1 signal set:** verified against the SHIPPED
  `harness-telemetry-ledger` code (not just its SPEC) — run identity is the envelope's
  `run_id` field (the run marker's `started_at`, an ISO-8601 `%Y-%m-%dT%H:%M:%SZ` string, so
  lexical order == chronological order); the D4-B v1 event vocabulary is `run-start`,
  `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`,
  `sentinel-resolved`, `gate-refusal`, `containment-refusal`. `event:<type>` targets filter on
  the envelope's `event` field.
- **Nested `baseline:` map:** `lazy_core.parse_sentinel` delegates to `yaml.safe_load`, which
  parses nested mappings natively — the record keeps the nested `baseline:` map per D3 (no
  flattening needed; round-trip covered by a Phase-1 test).
- **End-of-run flush insertion point:** §1c.6 of `/lazy-batch` and `/lazy-batch-cloud` — the
  same once-per-run end-of-run flush where the incident-scan invocation sits (BEFORE
  `--run-end`), mirrored across the coupled pair.

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by
  operator directive, 2026-07-04). Key influences: the `/harden-harness` hypothesis-ledger
  discipline and receipt-gated completion as in-repo prior art; pre-registration,
  interrupted-time-series honesty, and DORA change-failure thinking as external frames.
- `docs/features/harness-telemetry-ledger/SPEC.md` — event substrate (hard dep).
- `docs/features/friction-kpi-registry/SPEC.md` — signal vocabulary + measurability gate (soft
  dep).
- `docs/features/anti-overfit-design-gate/SPEC.md` — consumer of `signal_independence` and of
  these verdicts as its ground truth.
- `user/skills/harden-harness/SKILL.md` — the hardening-round path captured in Phase 4.
- `user/scripts/CLAUDE.md` — receipt-gated completion, `apply_pseudo`, parity conventions.
