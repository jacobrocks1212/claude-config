# Research — Intervention Efficacy Tracking (Hypothesis Ledger)

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`/harden-harness` (`user/skills/harden-harness/SKILL.md`)** already names "hypothesis-ledger
  rigor" as its discipline and writes per-round records to
  `docs/specs/turn-routing-enforcement/hardening-log/YYYY-MM.md` — but the rounds record what was
  *done*, never whether it *worked*. This feature is the missing back half of that discipline.
  The over-fit detector's spin-off protocol (front-enqueue via `adhoc-enqueue`, cross-referenced
  both ways, never blocking the current run) is the direct template for the REFUTED
  reconsideration enqueue.
- **Receipt-gated completion (`user/scripts/CLAUDE.md` → "Completion is receipt-gated";
  `lazy_core.write_completed_receipt` at `user/scripts/lazy_core.py:749`,
  `has_completion_receipt` at `:610`).** The house pattern this feature extends: a completion
  claim needs a script-written artifact. The intervention record is the same idea applied to
  *efficacy* claims. The `provenance: backfilled-unverified` convention from
  `--backfill-receipts` is reused verbatim in spirit for D9's backfill (`provenance:
  backfilled`).
- **`lazy_core.apply_pseudo` (`lazy_core.py:3241`)** — the single-author chokepoint for
  completion-time writes, with an established pattern of attaching additive return keys
  (`queue_trimmed`, `warnings`, `flipped_phases`). Capture slots in as one more deterministic
  side effect with an `intervention_recorded` key.
- **Opt-in repo flags in `queue.json`** — the `"autodiscover": true` precedent (documented in
  `user/scripts/CLAUDE.md`) shows how a claude-config-only behavior stays byte-identical for
  every other repo. The `"interventions": true` capture flag copies it.
- **Off-compute-path analysis scripts** — `toolify-miner.py` (read-only miner, proposes never
  promotes) and `lazy-queue-doc.py` (pure-read renderer invoked at run boundaries, never on the
  state-script compute path) are the residency precedents for `efficacy-eval.py`.
- **The self-evolution cluster blockquote (`docs/features/ROADMAP.md`)** fixes this feature's
  position: substrate (`harness-telemetry-ledger`) → semantics (`friction-kpi-registry`) →
  hypothesis (this) → guardrail (`anti-overfit-design-gate`), with
  `harness-change-canary-rollback` consuming the verdict machinery.

## External prior art & concepts

(Training-knowledge, not live research.)

- **Pre-registration / registered reports (experimental science):** declaring the hypothesis,
  measure, and analysis *before* seeing outcomes prevents post-hoc rationalization. Capturing
  the hypothesis at ship time — before any post-ship data exists — is the software analog, and
  is why capture lives in the completion gate rather than in a retro.
- **Interrupted time-series / single-case experimental design:** the honest methodology for
  n=1-operator before/after data. Its core lessons adopted here: freeze the baseline, declare
  the expected direction in advance, annotate co-interventions (confounders), and refuse to
  conclude below a minimum sample. Its formal statistics are deliberately NOT adopted (the stub
  forbids pretend rigor; n≈20 autocorrelated runs cannot support them).
- **DORA metrics, esp. change-failure rate:** the industry's recognition that shipped ≠
  improved; a change stream needs a failure-verdict stream. REFUTED-rate over intervention
  records is effectively a change-failure rate for the harness.
- **Hypothesis-driven development / Lean "validated learning":** frame every change as
  hypothesis + measure + decision. Mostly practiced as prose ritual; this design makes the
  ritual machine-enforced at the only deterministic chokepoint available.
- **Goodhart's law:** a measure that is also the control surface stops measuring. Motivates the
  `signal_independence` field being present from day one even though enforcement belongs to the
  sibling gate.

## Alternatives analysis

- **Capture author (D1):** script-owned in `apply_pseudo` vs orchestrator prose. Prose capture
  is LLM-inferred state across six coupled skill files — the exact failure class the mission
  statement and `user/scripts/CLAUDE.md` prohibit. No real contest; the only open sub-question
  (which chokepoint) is settled by `apply_pseudo` being the shipped single author.
- **Residency (D4):** central `docs/interventions/` vs item-dir vs state-dir. State-dir loses
  durability (untracked, rotation). Item-dir fails on two concrete facts: `bug-state.py`'s
  archive-on-fix moves bug dirs, and hardening rounds have no item dir at all. Central wins on
  archive-survival + enumeration cost; the loss (one hop from the item's other artifacts) is
  mitigated by cross-referencing ids.
- **Windows (D5):** run-count vs wall-clock vs statistical tests. Single-operator cadence makes
  wall-clock windows lie during idle periods; statistical tests overclaim at this n. Run-count
  windows with a min-sample floor and fixed relative bands are the least dishonest option; the
  numbers are declared tunables.
- **Confounders (D6):** annotate-only vs cap-on-same-signal. Annotate-only lets a sibling
  change's regression auto-enqueue a wrong reconsideration item — an automatic consequence from
  unattributable data. The cap costs verdict throughput, which the D8 escalation path absorbs.
- **REFUTED consequence (D7):** direct auto-enqueue vs operator-gated enqueue. The stub locks
  auto-enqueue; the safety valve is that the enqueued item is a *stub investigation*
  (`/spec-bug` owns root cause and the operator owns triage), so no revert happens
  unattended. The recurrence guard is two-layer (dir existence + record stamp) because either
  alone has a failure mode (archived dirs; deleted records).
- **Cadence (D10):** end-of-run flush vs retro-only vs scheduled. Windows are denominated in
  runs, so run boundaries are the only moments a verdict can newly mature; scheduling adds
  unattended-write machinery for zero data gain, and retro-only delays consequences by an
  unbounded amount.

## Pitfalls & risks

- **Ledger-schema drift (hard dep):** the evaluator's window arithmetic depends on
  `harness-telemetry-ledger`'s run-identity and event fields, which are being specified in
  parallel. Mitigation: the SPEC defers exact field names to a Phase-1 empirical check and the
  record freezes baselines so retention decisions upstream cannot corrupt old hypotheses.
- **Undeclared-hypothesis debt:** with D2's degrade-on-absence, a lazy authoring culture could
  produce a ledger of `undeclared` records. Mitigation: the KPI-registry `/spec` gate forces
  declaration for friction-reduction features, the sibling design gate forces it for
  control-surface changes, and undeclared records surface loudly in the needs-triage output.
- **Self-reference:** this feature is itself a harness change and gets its own intervention
  record (target signal: e.g. REFUTED/CONFIRMED throughput vs retro narrative counts). If its
  ledger shows the verdicts are never consulted, it is dead weight by its own standard — that
  is the intended falsifiability, not a flaw.
- **Verdict-band gaming:** a future change could widen the ±20% band to make itself CONFIRMED.
  The bands live in one constants block on a control surface, so the sibling gate's
  gate-weakening check (and operator sign-off) covers exactly this move.
- **Enqueue loops:** REFUTED → reconsideration → its fix REFUTED → ... is bounded by fresh ids
  per intervention and one-reconsideration-per-record; a genuinely oscillating surface will
  show up as repeated reconsiderations in retro, which is signal, not noise.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 capture author | Script-owned in `apply_pseudo` + `--record-intervention` CLI | High (auto-accepted) |
| D2 declaration surface | SPEC hypothesis block; degrade on absence, never block completion (v1) | Medium-high (OPEN) |
| D3 record schema | Frontmatter-sentinel markdown, frozen baseline, `signal_independence` day one | High (auto-accepted) |
| D4 residency | Central `docs/interventions/<id>.md` | High (OPEN) |
| D5 windows/bands | Run-count 20/20, min-sample 5, ±20% relative; per-record overridable | Medium (OPEN — numbers are tunables) |
| D6 confounders | Annotate always; cap same-signal overlap at INCONCLUSIVE | High (auto-accepted) |
| D7 REFUTED consequence | Existing `--enqueue-adhoc --type bug`, two-layer recurrence guard | High (auto-accepted) |
| D8 escalation | After 2 INCONCLUSIVE reviews, passive surfacing | Medium (OPEN) |
| D9 backfill | Manual opt-in only, `provenance: backfilled` | Medium-high (OPEN) |
| D10 cadence | End-of-run flush + on-demand + retro citation | High (OPEN) |
