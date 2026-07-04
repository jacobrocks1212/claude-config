# Research — Harness Telemetry Ledger + Trends

**Status: Gemini deep research intentionally skipped (operator directive, 2026-07-04).** This
feature was fleshed out via internal desk research instead: a survey of the in-repo prior art it
builds on, plus prior-art knowledge of comparable external systems. This file is the canonical
"research satisfied" marker for this repo (direct RESEARCH.md drop, per claude-config/CLAUDE.md),
so the pipeline routes Step 5 → /spec Phase 3 (integrate research + finalize) — which surfaces the
SPEC's OPEN product-behavior decisions to the operator via NEEDS_INPUT.md before planning starts.

## In-repo prior art

- **`lazy-deny-ledger.jsonl` (`user/scripts/lazy_core.py`, `append_deny_ledger_entry` ~line
  12592, `append_friction_ledger_entry` ~line 12645, `read_deny_ledger` ~line 12977).** The
  single most load-bearing precedent: an append-only JSONL ledger in the per-repo keyed state
  dir, written best-effort/fail-open ("a ledger write must never propagate"), read by a
  corrupt-line-skipping reader, deliberately using plain append instead of `_atomic_write`
  (documented rationale: an atomic rewrite would add a read-modify-write race on an append-only
  file whose torn final line is already tolerated). `kind: "process-friction"` entries from
  `--cycle-end` prove the multi-event-kind-in-one-file pattern. The telemetry ledger clones this
  contract wholesale; the SPEC's D1/D2 are essentially "do exactly this, again, with an
  envelope."
- **Run/cycle marker machinery (`write_run_marker` ~line 9289, `--cycle-begin`/`--cycle-end`,
  `advance_run_counters`/`advance_forward_cycle`).** Establishes (a) marker-gating as the house
  answer to "side effects only during a sanctioned run" — the SPEC's D3; (b) `started_at` as the
  stable run identity (the cycle marker's `run_started_at` snapshot from
  `hardening-blind-to-process-friction` Phase 2) — the SPEC's `run_id`; and (c) the motivating
  gap: `forward_cycles`/`meta_cycles`/`per_feature_forward_cycles` live only in the marker, which
  `--run-end` deletes — today the harness *forgets its own effort counts at the end of every
  run*. The ledger is what makes them survive.
- **Per-repo keyed state dir (`claude_state_dir()` ~line 9209, `multi-repo-concurrent-runs`).**
  Residency default, plus the read-path purity contract (`create=False`: a probe never creates
  the dir) that shapes D3. The legacy-migration list (`migrate_legacy_state_dir`) shows how
  state-dir files are inventoried; a brand-new file needs no migration entry.
- **State-script chokepoints (`user/scripts/lazy-state.py`).** `_state()` (~line 111) is the
  single output constructor for every dispatch; `terminal_reason` values are enumerated in the
  module docstring; `--apply-pseudo` (~line 9810) is the single author of completion writes;
  `--neutralize-sentinel` (~line 9805) is the single sentinel-resolution op (the natural
  halt-dwell end marker); the exit-3 (`refuse_if_cycle_active`,
  `refuse_cycle_marker_mutation_if_subagent`, `refuse_run_start_clobber`) and exit-1
  (`--verify-ledger`, `--gate-coverage`) sites are the refusal chokepoints. `bug-state.py`
  carries the same flags (`--bug-id` divergence). Every v1 event maps to one of these — no new
  inference anywhere.
- **`pipeline_visualizer` (`user/scripts/pipeline_visualizer/`).** `server.py` (ThreadingHTTPServer,
  `/api/state` + `/api/queue`, `TtlCache` debounce) and `probe.py` ("State is NEVER re-inferred
  here") define the pure-read rendering plane the trends page joins. `test_pipeline_visualizer.py`
  is the test home.
- **`lazy-queue-doc.py` (mobile-queue-control).** Two lessons: the ride-the-commit publication
  pattern for main-pushing repos (reused by D5-B's cloud segment flush), and the byte-stability
  discipline for *regenerated committed* docs — which is why D7 recommends against a committed
  `TRENDS.md` (trend aggregates are never regeneration-stable) while the append-only ledger
  itself is exempt (nothing regenerates it).
- **`toolify-miner.py`.** The read-only-miner precedent (hash-before/hash-after tests, "the miner
  proposes") — the trends aggregator inherits the same never-mutates posture. Also the reason
  per-tool/token telemetry is a non-goal: session JSONLs already carry it.
- **`/lazy-batch-retro` (`user/skills/lazy-batch-retro/SKILL.md`).** Its CITATIONS-NOT-TRUST hard
  requirement ("Do NOT trust agent summaries alone… every grading assertion MUST cite a specific
  source") is exactly the consumer contract D8 plugs into: ledger lines are the citable,
  deterministic source that retro friction claims currently lack.
- **`docs/features/ROADMAP.md` — Self-evolution cluster.** Frames this feature as the substrate
  of substrate → semantics → hypothesis → guardrail. The downstream consumers
  (`friction-kpi-registry`, `intervention-efficacy-tracking`, `harness-change-canary-rollback`)
  constrain the design toward raw immutable events (D9): their derivations are not knowable yet.

## External prior art & concepts

(Training-knowledge, not live research.)

- **Structured event logging / OpenTelemetry.** The envelope shape (schema-version field,
  timestamp, correlation id, event name, attribute bag) is standard OTel/structured-logging
  practice; `run_id` plays the trace-id role, `cycle` events the span role. Deliberately NOT
  adopting an OTel SDK or wire format — stdlib-only is a house rule and the consumer set is
  in-repo.
- **Append-only JSONL as a metrics substrate.** ndjson event logs with reader-side aggregation
  (the "events, not metrics" school — also Kafka/event-sourcing doctrine: store facts, derive
  views) supports D9. Pre-aggregated metrics (statsd-style) were rejected: definitions evolve,
  history shouldn't.
- **logrotate conventions.** Size-triggered rename-shift rotation with a bounded segment count is
  the D6-B model; chosen over time-based rotation because run cadence, not calendar time, drives
  volume here.
- **DORA metrics practice.** The insight that a small stable set of flow metrics
  (frequency, lead time, failure rate, recovery time) beats a large ad-hoc set maps onto D4-B's
  restraint: cycles-per-completion, refusal rate, halt dwell, run duration — and no more in v1.
- **Observer effect / Goodhart's law.** Known failure mode of self-measuring systems; mitigated
  structurally here because emission is script-owned at deterministic chokepoints (the LLM cannot
  choose to emit or suppress events), and metric *interpretation* is deferred to the
  `friction-kpi-registry` / `anti-overfit-design-gate` siblings.

## Alternatives analysis

- **Emit site: CLI handlers vs `compute_state()` (D3).** `compute_state()` sees everything but is
  shared by read-only probes (visualizer polls every TTL window; `lazy-queue-doc.py` and
  `/lazy-status` shell it) — emitting there double-counts dispatch activity and violates the
  probe-purity contract. CLI write-path handlers are fewer, enumerable, and already marker-gated
  in spirit. Tipping factor: the visualizer polling a repo *during a live run* is a common state;
  option B is wrong precisely when the data matters most.
- **One ledger vs extending the deny ledger.** Folding telemetry into `lazy-deny-ledger.jsonl`
  (more `kind:` values) was considered — one file, one reader. Rejected: the deny ledger is
  load-bearing *state*, not just observability — `pending_hardening()` gates `--run-end` and the
  `--emit-prompt` forward route on unacked entries. High-volume telemetry appends would bloat
  every `pending_hardening()` scan and risk perturbing a hardened contract. A sibling file keeps
  the blast radius zero; the aggregator reads both.
- **Committed vs state-dir residency (D5).** Fully committed gives durability + cross-machine
  visibility but generates per-cycle commit traffic and breaks on work-branch/push-blocked repos
  (the exact analysis mobile-queue-control did). State-dir-only loses cloud runs entirely. The
  hybrid (state dir + cloud run-end segment flush into main-pushing repos) buys cloud coverage
  for one small write-once file per run — the tipping factor is that write-once segments have no
  byte-stability problem, unlike regenerated docs.
- **Metric-bearing events vs raw events (D9).** Pre-computing "cycles_per_feature" at emit time
  would freeze today's definition into history and force emitter changes for every new question.
  Raw events cost slightly more reader-side code once, in one aggregator module.
- **Rotation now vs never (D6).** Volume estimates say "never" would survive years — but an
  explicit bounded contract is cheap (~20 lines) and avoids a future migration decision under
  pressure. Kept OPEN because the segment count is a history guarantee the operator owns.

## Pitfalls & risks

- **Double-counting.** Retried/re-invoked ops (e.g. an orchestrator re-running `--emit-prompt`
  after a transient) will emit multiple `dispatch` events. Mitigation: aggregation derives
  cycles from `cycle-begin` (nonce-carrying, one per Agent dispatch by construction), not from
  `dispatch` counts; `dispatch` events are corroborating detail. Phase 3 tests must pin this.
- **Silent non-emission.** Fail-open means a persistently broken emitter records nothing and
  nothing complains. Mitigation: `_diag` breadcrumb on failure + the trends page rendering
  honest gaps ("no telemetry for this window") so absence is visible, not invisible.
- **Vocabulary churn.** Downstream KPI rows bind to event names; renaming events orphans them.
  Mitigation: `v` field + treat event names as an append-only vocabulary (deprecate, don't
  rename) — noted for the `friction-kpi-registry` schema.
- **Becoming the tautology the cluster warns about.** A harness change could "improve" a metric
  by suppressing its events (e.g. removing a refusal site). Structural mitigations: emission
  lives at gate sites owned by the same parity-audited scripts, and the
  `anti-overfit-design-gate` sibling exists precisely to review changes that touch measurement
  surfaces. This feature's own falsifiability: its success criterion is that the next
  `/harden-harness` round can cite a before/after delta from the ledger for at least one shipped
  change — if retros still argue from narrative six weeks after Phase 4, the ledger is dead
  weight and should be flagged in its own scorecard row.
- **Ledger reads slowing the visualizer.** Bounded by D6 rotation + the existing TtlCache
  debounce; the aggregator reads at most cap × segments bytes per TTL window.

## Recommendations summary

| Decision | Recommendation | Confidence |
|----------|----------------|------------|
| D1 envelope + versioning + run identity | Deny-ledger-style compact JSONL, `v: 1`, epoch `ts`, `run_id` = marker `started_at` | High |
| D2 emitter placement + failure contract | Shared `lazy_core.append_telemetry_event`, plain append, fail-open | High |
| D3 chokepoint gating | CLI write-path handlers only, marker-gated; probes never emit | High |
| D4 v1 vocabulary (OPEN) | B — brackets + dispatch/halt + gate/containment refusals + sentinel-resolved | Medium-high |
| D5 residency + cloud (OPEN) | B — per-repo state dir + cloud run-end committed segment flush | Medium |
| D6 retention (OPEN) | B — size-based rollover, 10 MB × 4 segments | Medium |
| D7 trends channel (OPEN) | A — visualizer trends page only in v1 | Medium-high |
| D8 retro hook-in | Additive "Ledger deltas" step shelling the trends CLI | High |
| D9 raw events, reader-side derivation | Raw events only | High |
