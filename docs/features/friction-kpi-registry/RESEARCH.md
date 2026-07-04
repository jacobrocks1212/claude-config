# Research — Friction KPI Registry + Scorecards

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **The un-measured systems themselves (the problem instances).** The build-queue
  (`user/scripts/build-queue.ps1` + `build-queue-runner.ps1` + `build-queue-status.ps1`) records
  rich per-build outcomes in `~/.claude/state/build-queue/results/<seq>.json` — `exit_code`,
  `ended_at`, `hygiene.{vbcscompiler_recycled, recycle_skipped_reason, quarantined_artifacts,
  result_fidelity, build_fidelity}`, test `counts` — but nothing trends them; its false-green
  fixes (`build_fidelity: no-output`, `result_fidelity: no-tests-matched`) shipped with no
  recurrence measurement. Containment (`lazy-cycle-containment.sh` + the C3 refusals) writes
  denies and `kind: process-friction` entries to `lazy-deny-ledger.jsonl` — countable today,
  never counted. Halt handling leaves a sentinel trail (`BLOCKED.md`/`NEEDS_INPUT.md` →
  `*_RESOLVED_<date>` via `--neutralize-sentinel`) with date-granularity dwell at best. These
  three are the seed's first registrants, and their differing signal maturity drove the SPEC's
  computability table and D8's honest-`provenance` design.
- **`harness-telemetry-ledger` (hard upstream, sibling spec).** Supplies the event streams
  (`halt`/`sentinel-resolved` for dwell; `run-*`/`cycle-*`/`pseudo-applied` for
  cycles-per-completion; refusal events) that the registry's `telemetry-ledger` signal source
  selects over. The registry schema's `signal.selector` is deliberately a thin string against
  that ledger's envelope, so the upstream's D4 vocabulary resolution directly bounds what v1
  rows can declare — the reason the dep is `hard`.
- **`lazy-queue-doc.py` / `LAZY_QUEUE.md` (mobile-queue-control).** The committed-markdown
  channel precedent for D5: stdlib pure-read generator, `--repo-root`/`--stdout`, no embedded
  wall-clock (freshness = git commit time — an explicit operator decision there), regenerated at
  pipeline commit boundaries, never on the state-script compute path. `kpi-scorecard.py` is
  designed as its structural sibling.
- **The gate-injection family.** `_components/phases-runtime-validation.md` (planning-time
  capability + MCP tool-existence audits, per-repo override resolution) and
  `_components/mcp-coverage-audit.md` → `lazy-state.py --gate-coverage` (a prose gate promoted
  to a deterministic subcommand it shells) together define the two-layer pattern D7 reuses: an
  injected component at the authoring moment + a deterministic validator it can shell. The
  `/spec` skill's Phase 3 finalization checkpoint already models hard refusal ("dep block fails
  validation → surface and STOP — do not write SPEC.md"), and its `--batch` Decision-
  Classification Ledger + Step 1d.5 input-audit subagent provide the audit channel D6 leans on.
- **Receipt/provenance honesty.** `--backfill-receipts` grandfathers pre-gate completions as
  `provenance: backfilled-unverified` ("honest debt, not silenced") — the direct model for
  baseline `provenance: measured | retro-derived | pending` and for PENDING/NO-DATA rendering
  instead of fabricated zeros.
- **Script-owned mutation discipline.** `reorder_queue` / `--enqueue-adhoc` (load → mutate →
  `_atomic_write`, "never an orchestrator hand-edit") is the model for `--capture-baseline`
  being the only sanctioned registry mutation beyond ordinary reviewed edits of declarations.
- **`docs/features/ROADMAP.md` — Self-evolution cluster.** Fixes this feature's role (semantics
  layer over the telemetry substrate) and its downstream consumers:
  `intervention-efficacy-tracking` registers hypotheses against KPI rows;
  `harness-change-canary-rollback` consumes regression flags under an operator-set
  flag-and-enqueue (never silent auto-revert) charter — which is why the scorecard only ever
  flags and renders.

## External prior art & concepts

(Training-knowledge, not live research.)

- **SRE SLI/SLO practice.** The KPI row is essentially an SLI declaration with an SLO band:
  named signal, unit, direction, target/threshold, and a review cadence. The D4 recommendation
  (static declared thresholds, mandatory review-by) follows SLO doctrine for low-volume signals;
  error-budget-style rolling windows were rejected as statistically dishonest at a
  few-runs-per-week volume.
- **Metric registries / semantic layers.** dbt's metrics layer, OpenMetrics, and Prometheus
  recording-rule conventions all converge on "declare the metric once, machine-readably, next to
  its computation source; derive views from the declaration" — the registry-as-single-source
  shape of D1/D2, including the closed enum of signal source types.
- **DORA / flow metrics.** Small stable KPI sets with explicit direction-of-goodness beat
  sprawling dashboards; supports seeding exactly the six declared rows rather than
  auto-generating rows for everything measurable.
- **Goodhart's law / Campbell's law.** When a measure becomes a target, it stops measuring.
  Structural mitigations here: KPI values are computed by a pure-read script from
  script-emitted signals (no LLM in the number path); band loosening is a visible registry diff
  (audit food for the `anti-overfit-design-gate` sibling); tautology detection (a system graded
  by a signal it controls) is explicitly that sibling's charter, not silently assumed solved
  here.
- **Definition-of-Done gates.** The `/spec` measurability gate mirrors the industry pattern of
  requiring a success-metric declaration in design review before work is sanctioned (e.g.
  experiment-review templates: hypothesis, metric, expected direction) — moved to the earliest
  gate the harness owns, baseline-lock.

## Alternatives analysis

- **Registry residency (D1).** Committed-in-claude-config vs state dir: the state dir is
  untracked and per-machine — declarations there would be invisible to review and lost across
  hosts; declarations are exactly the kind of slow-moving, review-worthy contract git is for.
  Single file vs per-system files: with ~6 rows growing by a handful per quarter, one file wins
  on schema/lint/review simplicity; per-system sharding is a mechanical refactor later if size
  ever demands it. Per-repo registries invert ownership (harness-global systems, claude-config
  is the harness repo).
- **Band semantics (D4).** Static bands vs %-of-baseline vs rolling SPC: %-of-baseline
  re-centers alarms when baselines are re-captured (silent tautology risk); rolling bands track
  slow regressions instead of catching them; static bands are crude but deterministic, diffable,
  and auditable — and the schema leaves a `band` sub-object so richer semantics are additive vN.
- **Scorecard channel (D5).** Committed markdown vs visualizer: the decisive property is that a
  regression flag must reach the operator with zero infrastructure running; the phone/GitHub
  channel already proved itself with `LAZY_QUEUE.md`. The commit-noise objection (values change
  per run) is bounded to one honest diff per run boundary by regenerating at run-end, not
  per-cycle — unlike trend aggregates (rejected as committed docs in the telemetry sibling),
  a scorecard is a curated, windowed, rounded summary whose diffs are meaningful.
- **Gate detection (D6).** Pure heuristics are gameable and misfire both ways; pure operator
  tagging is manual and misses autodiscovered features; self-declaration alone could quietly
  classify `no`. The recommended composite (mandatory declared classification + advisory
  keyword cross-check + the existing input-audit subagent) reuses the audit machinery `/spec
  --batch` already runs rather than inventing enforcement.
- **Gate placement (D7).** In-`/spec` component vs a state-script step: baseline-lock happens
  inside `/spec` Phase 1/3, before any state-script probe would see the finalized SPEC; a
  state-script gate would fire one cycle too late (post-finalization), reproducing the
  catch-late failure mode this feature exists to end. The deterministic half still lives in a
  script (`--lint --spec`), preserving "behavior that must be deterministic belongs in a
  script."
- **Computation home (D3).** Inside `pipeline_visualizer` vs a sibling script: the committed
  channel must be producible headless at run boundaries; the visualizer imports the module later
  (one computer, two renderers) rather than owning the computation.

## Pitfalls & risks

- **Registry rot.** Rows outlive their systems or their bands drift out of relevance.
  Mitigation: mandatory `review_by` per row, surfaced as scorecard Registry-health warnings and
  `--lint` failures — rot is visible, not silent. The registry's own health is thereby one of
  its outputs.
- **Goodhart pressure on the harness's self-improvement loop.** Hardening work could chase KPI
  optics. Partially out of scope by design: tautology/overfit review belongs to
  `anti-overfit-design-gate`; this feature's obligation is to keep the number path LLM-free and
  band changes diffable, which it does structurally.
- **Gate ceremony tax.** If the `/spec` gate mis-classifies ordinary features as
  friction-reduction, every SPEC pays a declaration tax. Mitigation: classification is one line
  for `no`-features, the keyword cross-check is advisory-only, and misclassification lands in
  the NEEDS_INPUT round where the operator corrects it cheaply.
- **Pending-signal rows read as failure.** PENDING-SIGNAL rows (wait time, halt dwell,
  cycles-per-completion before the ledger lands) could look like the system is broken.
  Mitigation: distinct PENDING vs NO-DATA vs OK/WARN/BREACH statuses with explicit meaning in
  the scorecard legend.
- **Baseline dishonesty.** Retro-derived baselines from sparse history can be noise. Mitigation:
  `provenance: retro-derived` is first-class and visibly distinct from `measured`; Phase 4
  explicitly checks how much history each source supports before stamping.
- **Own falsifiability.** This feature should register itself: a KPI row for the registry
  (e.g. fraction of shipped friction-reduction features carrying a valid KPI declaration —
  direction up-is-good, signal: SPEC scan). If, two quarters in, no regression flag or scorecard
  reading has ever influenced a decision (no cited scorecard reference in any retro or
  reconsideration item), the registry is dead weight and its own review-by row should say so.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 residency + granularity (OPEN) | Single committed `docs/kpi/registry.json` in claude-config, per-row `repo_scope` | Medium-high |
| D2 row schema | Full declaration incl. `signal{source,selector}`, `direction`, `baseline{...,provenance}`, `band`, `review_by` | High |
| D3 computation home + write discipline | `kpi-scorecard.py` stdlib sibling of `lazy-queue-doc.py`; only explicit CLI writes | High |
| D4 band semantics (OPEN) | Static declared warn/breach bands + mandatory review cadence | Medium |
| D5 scorecard channel (OPEN) | Committed `docs/kpi/SCORECARD.md` in v1; visualizer tab as follow-up | Medium |
| D6 friction-feature detection (OPEN) | Self-declaration + advisory keyword cross-check, audited by the input-audit subagent | Medium |
| D7 gate mechanics | Injected `/spec` component + deterministic `--lint --spec` backstop, refuse-to-finalize | High |
| D8 first registrants + baselines | Seed set as declared; honest `provenance`; pending rows visible, never faked | High |
