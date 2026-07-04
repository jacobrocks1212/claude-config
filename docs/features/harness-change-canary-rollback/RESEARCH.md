# Research — Harness-Change Canary + Rollback

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The quiet-failure evidence base.** The repo's own docs establish why detection latency is
  the problem: hooks are fail-OPEN by convention (`user/hooks/CLAUDE.md`), so a broken hook
  writes a `hook-error.json` breadcrumb and allows — silence is indistinguishable from health
  without a watcher. `lazy-deny-ledger.jsonl` (guard denies + `kind: process-friction` entries,
  `lazy_core.py`) is likewise structured evidence that today only a retro reads. Both streams
  already exist in the per-repo keyed state dir; the canary is the first consumer that reads
  them *during* the damage window.
- **The coupled-pair hazard is documented, not hypothetical.** The root `CLAUDE.md` pairs table
  and `user/scripts/lazy-parity-manifest.json` + `lazy_parity_audit.py` define pairs whose
  halves must move together ("Editing one without the other silently breaks the pair's
  invariants"). A naive revert of one half is exactly such an edit — hence pair scope computed
  at ship time and carried on every revert item.
- **Flag-and-enqueue precedent.** `/harden-harness`'s spin-off protocol (fix lands, generalized
  item front-enqueued via `adhoc-enqueue`, `PushNotification`, run never blocked) is the shipped
  shape for "the harness noticed something and queued work about it." The canary's trip
  consequence copies it, including the notification and the never-blocks-the-run property.
- **Run-denominated thinking.** The budget guard (`--per-feature-cycle-cap`), max-cycles, and
  the sibling efficacy windows all count runs/cycles, not wall-clock — consistent with the
  user-level constitution's "estimate in sessions, never time." Canary windows follow suit,
  with a wall-clock ceiling only as a staleness bound.
- **Honest-degradation precedent.** `DEFERRED_*` vs `SKIP_*` semantics, `baseline: unavailable`
  in the sibling spec, `provenance: backfilled-unverified` — the house pattern for "record the
  limitation loudly, never fake or block." The canary's `closed-clean (no-data)` stamp and
  never-blocks-a-run watcher follow it.

## External prior art & concepts

(Training-knowledge, not live research.)

- **Canary deployments / automated canary analysis (Spinnaker Kayenta, Argo Rollouts, feature-
  flag canaries):** ship, observe a bounded window against a baseline, judge with declared
  metrics, roll back on regression. Two adaptations for this repo: the "traffic split" is
  temporal (before/after runs), because a single-operator harness has no parallel cohorts; and
  the rollback is a *proposed change* (flag-and-enqueue), not an automated action, because the
  deployment target is the safety system itself.
- **SRE SLO burn-rate alerts:** fast-burn windows (sensitive, short) alongside slow-burn
  windows (confirmatory, long). The canary window vs the efficacy review window is exactly this
  two-speed pattern — hair-triggered canary bands are acceptable because the consequence is an
  investigation, not a verdict.
- **GitOps revert-as-PR:** in mature GitOps practice, automation *prepares* the revert (commit
  set identified, PR opened with evidence) and a human merges. The evidence-bearing bug stub
  with commit set + pair scope is the pipeline-native equivalent; the bug pipeline under full
  gates is the "merge."
- **DORA MTTR / change-failure rate:** the canary shortens time-to-detect (the dominant term in
  MTTR for quiet failures) and its trip stream, joined with efficacy verdicts, yields a
  change-failure rate for the harness.
- **Kill switches vs safety interlocks:** industrial practice distinguishes reversible
  actuation (kill switch: safe to trip automatically) from interlock removal (never automatic).
  Reverting a live gate is interlock removal — the strongest external argument for the stub's
  no-auto-revert lean, mirrored in-repo by the sibling gate treating unattended gate-disarm as
  gate-weakening.

## Alternatives analysis

- **Registration (D1):** new registry file vs sub-map on the intervention record. The record
  already captures ship time, commit context, and target signal at the only deterministic
  chokepoint; a second registry re-derives all three and drifts. Cost: hard schema coupling to
  the sibling — accepted, the dep verdict is hard anyway.
- **Window/bands (D2):** run-denominated + ceiling vs wall-clock vs efficacy-identical.
  Wall-clock lies under bursty single-operator cadence; efficacy-identical forfeits the
  fast/slow two-speed design. The specific defaults (10 runs, 30 days, 25%, 2 incidents) are
  declared tunables — trip precision is the canary's own KPI, so the numbers are falsifiable by
  the system's own ledger.
- **Attribution (D3):** surface-based vs most-recent-wins vs content matching. Content matching
  is a literal-string heuristic (the sibling gate's canonical overfit smell — disqualifying for
  a self-evolution feature). Most-recent-wins silently picks wrong under interaction. Surface
  identity is coarse but deterministic, conservative on unknowns, and transparent when shared —
  the operator sees *why* an incident counted.
- **Auto-revert (D4):** the one genuinely contestable product call. Analysis converged with the
  stub's lean for three independent reasons: (1) interlock-removal asymmetry (above); (2) the
  coupled-pair hazard makes mechanical one-shot reverts structurally unsafe without planning;
  (3) an unattended writer to `main` would need its own containment story. Carried OPEN because
  it is a standing policy question the operator owns, with the recommendation to revisit only
  on accumulated trip-precision evidence.
- **Watcher placement (D6):** standalone script vs evaluator mode. Standalone duplicates ledger
  readers, window accrual, and — worse — becomes a second writer to the intervention records,
  breaking single-writer discipline. The evaluator mode costs a subcommand boundary.
- **Revert preparation depth (D5):** evidence-bearing stub vs prepared revert patch/branch. The
  patch route puts a read-only analysis tool in the code-writing business and would still need
  `/execute-plan`'s gates to land safely; the stub route reuses the entire existing bug
  pipeline. `git revert --no-commit` dry-run feasibility probing was considered and deferred —
  it requires a clean worktree at watch time, which the end-of-run flush cannot guarantee.

## Pitfalls & risks

- **Trip noise → operator fatigue → ignored canaries.** The hair-triggered bands are safe only
  while trips stay rare and evidence stays good. Mitigation: trip precision is the system's own
  KPI row (closes-as-noise are counted), and the bands live in one constants block whose
  loosening/tightening is a gated control-surface change.
- **Attribution blind spot:** incidents with no resolvable surface never attribute, so a change
  that breaks something surface-less (e.g. corrupts a shared state file another component trips
  over) evades the incident tripwire. The KPI-regression tripwire and the slower efficacy
  review remain the backstop; the gap is documented rather than papered over with heuristics.
- **Schema coupling to two in-flight siblings.** Registration reads the provenance mapping and
  the manifest; the watcher reads the telemetry ledger. All three are being specified in
  parallel — the SPEC pins them by feature-id and role, and defers exact field names to
  phase-time empirical checks. Sequencing risk is real but bounded: this feature is P2/Tier 2
  and lands after the cluster's P1s by design.
- **Self-application:** the canary system's own changes (bands, attribution, watcher) touch the
  control-surface manifest, so they get canaried and gated themselves. A canary that never
  trips across many control-surface changes is either a very good harness or a broken watcher —
  the no-data/closed-clean distinction and the retro citation exist so those two read
  differently.
- **Revert-item staleness:** by the time the operator triages, further commits may have landed
  on the same surfaces. The evidence carries the commit set, not a patch, precisely so
  `/plan-bug` plans against current reality; the degraded-revert note flags the known-unsafe
  cases at ship time.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 registration | `canary:` sub-map on the intervention record; scope via the sibling gate's manifest | High (auto-accepted) |
| D2 window + bands | 10 runs / 30-day ceiling; KPI band else 25% relative (≥3 events); ≥2 attributable incidents | Medium (OPEN — numbers are tunables) |
| D3 attribution | Surface-based; unknown never attributes; shared surfaces count against all matching | Medium-high (OPEN) |
| D4 auto-revert | No class in v1; flag-and-enqueue always; revisit only on trip-precision evidence via the gate's sign-off | High (OPEN — standing policy, operator-owned) |
| D5 revert item | Evidence-bearing `canary-revert-<id>` bug stub with commit set + pair scope + degraded note; once ever | High (auto-accepted) |
| D6 watcher | `efficacy-eval.py --canary` at every end-of-run flush while windows are open | High (auto-accepted) |
| D7 handoff | Status stamp + record body section; efficacy review unaffected either way | High (auto-accepted) |
