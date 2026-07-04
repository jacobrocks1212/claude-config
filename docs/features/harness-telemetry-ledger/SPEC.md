# Harness Telemetry Ledger + Trends — Feature Specification

> Retros find friction qualitatively; nothing measures it. Both state scripts gain a deterministic,
> append-only JSONL telemetry ledger written at their existing chokepoints (run/cycle brackets,
> dispatch, gate refusals, halt observation, sentinel resolution, pseudo-skill completion), modeled
> byte-for-byte on the proven `lazy-deny-ledger.jsonl` writer. A pure-read trends aggregator and a
> `pipeline_visualizer` trends page derive the metrics (cycles-per-completion, gate-refusal rate,
> halt dwell, run duration) reader-side, and `/lazy-batch-retro` cites ledger deltas instead of
> narrative-only claims — so "did that harness change actually reduce coherence-recovery cycles?"
> becomes answerable with data.

**Status:** Draft
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04; fleshed out via internal desk research
2026-07-04 (Gemini research skipped by operator directive — see RESEARCH.md)

**Depends on:** (none)

> Formally no dep-block entries. Substantive dependencies are **implemented data contracts**, not
> sibling specs:
> - The state scripts' existing chokepoints: the `_state()` dispatch return (`lazy-state.py` line
>   ~111), the `--run-start`/`--run-end`/`--cycle-begin`/`--cycle-end` handlers, the exit-3 gate
>   refusals (`refuse_if_cycle_active`, `refuse_run_start_clobber`,
>   `refuse_cycle_marker_mutation_if_subagent`), the exit-1 verdict gates (`--verify-ledger`,
>   `--gate-coverage`), the `--apply-pseudo` completion path, and `--neutralize-sentinel`.
> - `lazy_core.claude_state_dir()` — the per-repo keyed state dir (`~/.claude/state/<repo_key>/`,
>   `multi-repo-concurrent-runs`) where the ledger lives.
> - `lazy_core._atomic_write` / `lazy_core._diag` — the write + diagnostics conventions.
> - `lazy_core.append_deny_ledger_entry` / `append_friction_ledger_entry` — the existing
>   append-only JSONL precedent (plain append, torn-line-tolerant reader, fail-open writer) this
>   feature clones rather than reinvents. The deny ledger itself stays untouched; the trends
>   aggregator reads it as a second source.
> - `pipeline_visualizer` (pure-read renderer; `/api/state` + `/api/queue` + TTL cache) — the
>   trends page is one more route on the same server.
> - **Downstream consumers, not dependencies:** `friction-kpi-registry`,
>   `intervention-efficacy-tracking`, and `harness-change-canary-rollback` (the self-evolution
>   cluster) resolve their signal sources to this ledger's event streams.

---

## Executive Summary

The harness self-improves via retros (`/lazy-batch-retro`), investigations, and `/harden-harness`,
but the feedback loop has no quantitative signal. There is no baseline for cycles-per-completion,
no gate-refusal rate, no halt dwell time — so a hardening change can never be verified as an
improvement against the mission's "efficient" criterion, only narrated as one. The raw facts
already flow through a handful of deterministic script-owned chokepoints (every dispatch, every
gate refusal, every run/cycle bracket passes through `lazy-state.py`/`bug-state.py`), and the repo
already proves the exact recording mechanism this needs: `lazy-deny-ledger.jsonl` is an
append-only, fail-open, torn-line-tolerant JSONL ledger in the per-repo keyed state dir, written
by the guard on every deny and by `--cycle-end`'s process-friction detector.

This feature generalizes that precedent into a sibling ledger, `lazy-telemetry.jsonl`: one shared
`lazy_core` emitter called from the existing CLI chokepoints of both state scripts (parity by
construction — one helper, two callers), gated on the run marker so read-only probes stay
side-effect-free, and fail-open so a telemetry failure can never block the pipeline. Metrics are
never computed at emit time: a pure-read aggregator in `pipeline_visualizer` derives
cycles-per-completion, refusal rates, halt dwell, and run trends from the raw events (plus the
deny ledger), serving them as a trends page — the same "script-owned facts, pure-read rendering"
split the visualizer and `lazy-queue-doc.py` already follow.

It is the substrate of the self-evolution cluster (ROADMAP: substrate → semantics → hypothesis →
guardrail): `friction-kpi-registry` binds KPI rows to these event streams,
`intervention-efficacy-tracking` evaluates hypotheses against them, and
`harness-change-canary-rollback` watches them for regressions. Serving the mission's **efficient**
criterion directly — and **best-practice-aligned**, because "measured, not narrated" is the
cluster's founding rule.

## Design Decisions

### D1. Event envelope: compact JSONL with `v` schema-version, epoch `ts`, and marker-derived run identity

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** What does one ledger line look like, how are future schema changes survived, and
  how are events correlated to a run?
- **Options:**
  - **A — deny-ledger-style flat compact JSON + `v` int:** one JSON object per line:
    `{"v": 1, "ts": <epoch float>, "run_id": <marker started_at | null>, "pipeline":
    "feature"|"bug", "event": "<type>", "item_id": <id | null>, "data": {…}}`. Pros: mirrors the
    proven `append_deny_ledger_entry` shape (epoch `ts`, injectable `now=` for hermetic tests);
    readers skip lines whose `v` they don't know, exactly as the deny-ledger reader skips
    unparseable lines. Cons: flat envelope means per-event payloads live in an untyped `data` map.
  - **B — typed per-event schemas, no shared envelope:** stricter, but every consumer must know
    every event type, and a new event breaks old readers.
- **Recommendation:** A — the deny ledger's corrupt-line-skipping reader convention already
  establishes "tolerate what you don't understand"; a `v` field makes that deliberate. `run_id`
  reuses the run marker's `started_at` — already the canonical stable run identity (the cycle
  marker's `run_started_at` snapshot from `hardening-blind-to-process-friction` Phase 2 set this
  precedent). Wall-clock capture is epoch `time.time()`; the byte-stability discipline of
  `lazy-queue-doc.py` does NOT apply because the ledger is append-only and (per D5 default)
  uncommitted — nothing regenerates it.
- **Resolution:** Auto-accepted A; an internal wire format with no operator-visible surface.

### D2. Emitter: one shared fail-open `lazy_core.append_telemetry_event`, plain append, never atomic-rewrite

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Where does the writer live and what is its failure contract?
- **Options:**
  - **A — clone `append_deny_ledger_entry` into `lazy_core.append_telemetry_event(event, *,
    item_id=None, data=None, now=None) -> bool`:** plain `open(..., "a")` append to
    `claude_state_dir() / "lazy-telemetry.jsonl"`, swallow every exception, return `False` on
    failure (at most a `lazy_core._diag(...)` breadcrumb). Pros: fail-open is proven ("a ledger
    write must never propagate"); plain append avoids the read-modify-write race an
    `_atomic_write` rewrite would introduce on an append-only file (the deny ledger documents this
    exact reasoning); one shared helper gives `lazy-state.py` ↔ `bug-state.py` parity by
    construction (like the checkpoint-continuity machinery). Cons: a torn final line is possible —
    tolerated by the reader, per the deny-ledger contract.
  - **B — per-script emitters:** duplicates the writer into both scripts; the parity audit then has
    to police drift that construction could have prevented.
- **Recommendation:** A — reuses the exact hardened deny-ledger write path and adds zero new state
  machinery; `_atomic_write` stays the rule for queue/marker/sentinel rewrites, and append-only
  ledgers stay the documented exception. Telemetry failure must never block the pipeline: the
  emitter cannot raise, and no caller branches on its return value.
- **Resolution:** Auto-accepted A; invisible helper placement with a house-invariant-preserving
  failure contract.

### D3. Emission chokepoints are the CLI write-path handlers, marker-gated — bare probes never emit

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Which code paths call the emitter? The trap: `compute_state()` runs on every
  read-only probe — the visualizer polls it, `/lazy-status` and `lazy-queue-doc.py` shell it —
  and read paths are contractually side-effect-free (`claude_state_dir(create=False)`: "a probe
  that finds no marker never creates `~/.claude/state/`").
- **Options:**
  - **A — hook the CLI handlers, not `compute_state()`:** emit from `--run-start`, `--run-end`,
    `--cycle-begin`, `--cycle-end`, `--apply-pseudo`, `--neutralize-sentinel`, the exit-3/exit-1
    refusal sites, and the `--emit-prompt` dispatch surface (marker-gated, like registry writes
    and counter advances — `write_run_marker`'s documented gating rule). Bare `--probe` /
    `--repeat-count-peek` / scoped `--feature-id` reads emit nothing. Pros: deterministic,
    enumerable, keeps every read path byte-identical; a visualizer poll during a live run cannot
    pollute the ledger. Cons: interactive single-step `/lazy` invocations without a run marker go
    unrecorded — acceptable, v1 trends measure batch runs.
  - **B — emit from `compute_state()` whenever a marker is present:** captures more, but a
    visualizer poll against a repo with a live run would masquerade as dispatch activity —
    double-counting by construction.
- **Recommendation:** A — the marker-gating discipline already exists for exactly this reason
  ("without it, registry writes, counter advances, and hook injections are all no-ops"), and
  option B is unfixable double-counting. The exact set of hooked handlers is D4's (operator)
  call; the *gating mechanism* is this decision.
- **Resolution:** Auto-accepted A; an internal purity constraint that preserves the existing
  read-path contract.

### D4. v1 event vocabulary — which chokepoints emit

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Which events exist in v1? This determines which trends the operator can see and
  which KPI rows `friction-kpi-registry` can bind — the ledger's public vocabulary.
- **Options:**
  - **A — minimal brackets:** `run-start`, `run-end`, `cycle-begin`, `cycle-end`,
    `pseudo-applied`. Pros: tiny wiring surface. Cons: cannot compute gate-refusal rate or halt
    dwell — two of the three headline metrics in the seed problem statement.
  - **B — brackets + gates + halts (recommended):** A plus `dispatch` (at `--emit-prompt`:
    item_id, current_step, sub_skill, terminal_reason), `halt` (a dispatch whose
    `terminal_reason` ∈ {blocked, needs-input, needs-spec-input, needs-research,
    completion-unverified, blocked-misnamed}), `sentinel-resolved` (at `--neutralize-sentinel`
    success — the halt-dwell end marker), `gate-refusal` (`--verify-ledger` / `--gate-coverage` /
    `--apply-pseudo` exit-1 verdicts, with `failing_check`/`uncovered`), and
    `containment-refusal` (the exit-3 refusal sites, with the refused op). Pros: covers every
    metric named in the seed (cycles-per-feature, gate refusals, halt frequency + dwell,
    wall-time) with ~10 event types; guard denies and process-friction stay in the deny ledger
    (no duplication — the aggregator reads both files). Cons: ~9 wiring sites across two scripts.
  - **C — B plus per-probe and per-diagnostic events:** maximal, but re-creates option B of D3's
    double-counting problem and bloats the ledger with noise the session JSONLs already hold
    (`toolify-miner.py` territory).
- **Recommendation:** B — it is the smallest set that makes the stub's motivating question
  answerable, and every event maps to an already-deterministic code site (no new inference).
  Explicit non-goals either way: token counts, per-tool telemetry, subagent wall-time — the
  session logs own those and `toolify-miner.py` already mines them read-only.
- **Resolution:** OPEN — recommendation is B; awaiting operator confirmation.

### D5. Residency + cloud transport

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Where does the ledger live — and what happens to events emitted by
  `/lazy-batch-cloud` runs, whose container (and its `~/.claude/state/`) is destroyed after the
  run?
- **Options:**
  - **A — per-repo keyed state dir only:** `~/.claude/state/<repo_key>/lazy-telemetry.jsonl`,
    consistent with every other run-scoped file (`multi-repo-concurrent-runs`). Pros: zero commit
    noise; no secrets/noise ever lands in a repo; matches the deny ledger exactly. Cons: cloud-run
    telemetry dies with the container — AlgoBooth's cloud batches (a large share of batch
    activity) become invisible to trends.
  - **B — A + cloud run-end flush (recommended):** workstation runs use A unchanged; a `--cloud`
    run's `--run-end` additionally copies the run's ledger segment (lines matching this
    `run_id`) into the repo at `docs/telemetry/cloud/<run_id>.jsonl`, riding the run's existing
    final commit+push to `main` — the `LAZY_QUEUE.md` ride-the-commit precedent
    (mobile-queue-control Decision 6). The workstation trends aggregator reads state-dir ledgers
    plus any committed `docs/telemetry/cloud/*.jsonl`. Pros: cloud runs become measurable; one
    small append-only file per cloud run; no byte-stability concern (segments are written once,
    never regenerated). Cons: telemetry artifacts become repo-visible; adds a flush step to the
    cloud wrapper (a coupled-pair-tabulated divergence).
  - **C — fully committed in-repo ledger for all runs:** maximal durability, but every
    workstation cycle would generate commit traffic in repos that do not push to `main`, and the
    work-branch/push-blocked concern that shaped mobile-queue-control applies in full.
- **Recommendation:** B — losing cloud runs undermines "measured, not narrated" for the exact
  environment where autonomous batches run longest, and the flush mechanism is a solved pattern
  (cloud runs already commit generated docs per cycle). Scope the flush to the two main-pushing
  repos (claude-config, AlgoBooth), like `LAZY_QUEUE.md`.
- **Resolution:** OPEN — recommendation is B; awaiting operator confirmation (what lands committed
  in his repos is an operator call).

### D6. Retention / rotation policy

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Does the ledger grow forever, and if not, how much trend history does the operator
  keep? (Estimate: ~250 bytes/line, a 50-cycle batch run ≈ 150–300 events ≈ ~60 KB — years of
  heavy use fit in tens of MB. Estimated — verify during Phase 2.)
- **Options:**
  - **A — no rotation (deny-ledger precedent):** simplest; growth is slow. Cons: unbounded reads
    make the trends aggregation slower over years; no explicit history contract.
  - **B — size-based rollover (recommended):** at emit time, if the active file exceeds a cap
    (default 10 MB), rename `lazy-telemetry.jsonl` → `lazy-telemetry.jsonl.1` (shifting `.1`→`.2`,
    keeping N=4 segments); the reader walks rotated segments oldest-first then the active file.
    Pros: bounded worst-case read; deterministic, stdlib-only, ~20 lines; ≈160 MB ceiling ≈
    multi-year history at estimated volume. Cons: history beyond N segments is discarded — a
    trends-horizon choice the operator should own.
  - **C — per-run segment files:** one file per `run_id`; clean semantics, but hundreds of small
    files in the state dir and a directory-scan reader for every aggregation.
- **Recommendation:** B — bounded and simple, and the cap/segment-count are config constants a
  later decision can raise without schema change. Rotation happens inside the fail-open emitter
  (a rename failure degrades to plain append, never raises).
- **Resolution:** OPEN — recommendation is B; awaiting operator confirmation (retention length is
  an operator-visible history guarantee).

### D7. Trends rendering channel

- **Classification:** `product-behavior (OPEN — operator confirmation required via the pipeline's
  needs-input round before implementation)`
- **Question:** Where does the operator read the trends?
- **Options:**
  - **A — `pipeline_visualizer` trends page only (recommended):** a new pure-read
    `pipeline_visualizer/trends.py` aggregator, an `/api/trends` route on the existing
    `ThreadingHTTPServer` (served through the same `TtlCache` debounce as `/api/state`), and a
    Trends tab in `static/`. Pros: the visualizer is already the desktop analysis surface
    (graph/queues/fleet); zero commit noise; aggregates recompute freely. Cons: not readable from
    the phone.
  - **B — committed `TRENDS.md` à la `LAZY_QUEUE.md`:** mobile-readable, but trend aggregates
    change on nearly every cycle, so regeneration is never byte-stable — the exact spurious-commit
    problem `lazy-queue-doc.py` was designed to avoid. Constant diff churn on `main`.
  - **C — both.**
- **Recommendation:** A for v1 — trends are an analysis surface, not a steering surface; the
  mobile steering doc (`LAZY_QUEUE.md`) already covers on-the-go needs, and
  `friction-kpi-registry`'s scorecard (its own decision) is the committed-markdown candidate for
  a curated mobile-readable health view. B/C stay open as vN follow-ups.
- **Resolution:** OPEN — recommendation is A; awaiting operator confirmation.

### D8. Retro hook-in: `/lazy-batch-retro` cites ledger deltas

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** How do retros consume the ledger? (The seed direction explicitly names this:
  "retro cites ledger deltas instead of narrative-only claims.")
- **Options:**
  - **A — an additive retro step:** `user/skills/lazy-batch-retro/SKILL.md` gains a step that
    filters the ledger to the audited run's `run_id` window and reports the counts
    (cycles-per-feature, gate refusals, containment refusals, halts + dwell) in the overview
    artifact, each figure citing its ledger line numbers — satisfying the skill's existing
    CITATIONS-NOT-TRUST hard requirement with a deterministic source.
  - **B — a separate retro-metrics script the skill shells.**
- **Recommendation:** A, with the aggregation functions imported from
  `pipeline_visualizer/trends.py` via a small CLI (`python3 -m pipeline_visualizer.trends
  --run-id <id> --repo-root <repo>`) so the skill shells a deterministic tool rather than
  hand-counting JSONL in prose — behavior that must be deterministic belongs in a script, not a
  skill. Missing/empty ledger → the retro reports "no telemetry for this run" honestly (older
  runs predate the ledger).
- **Resolution:** Auto-accepted A; an additive evidence source inside an existing read-only skill,
  directed by the seed — no behavioral mode change.

### D9. Metrics are derived reader-side; emitters never aggregate

- **Classification:** `mechanical-internal (auto-accepted)`
- **Question:** Does the ledger store raw events or computed metrics?
- **Options:**
  - **A — raw events only (recommended):** cycles-per-completion, refusal rate, halt dwell, run
    duration are pure functions in `pipeline_visualizer/trends.py` over the event stream (plus
    the deny ledger). Pros: one writer of facts, N derivations; a metric-definition change never
    invalidates recorded history; mirrors the probe's "state is NEVER re-inferred here" split.
  - **B — emit pre-computed metrics:** bakes today's metric definitions into immutable history.
- **Recommendation:** A — the whole cluster (KPIs, efficacy verdicts, canaries) will define new
  derivations over the same facts; raw events are the only future-proof substrate.
- **Resolution:** Auto-accepted A; internal layering with no operator-visible surface.

## User Experience

The "users" are the operator and the autonomous pipeline itself.

- **Nothing changes about running the pipeline.** Emission is a silent, fail-open side effect of
  the existing CLI ops. No new flags are required on the happy path; exit codes and JSON output
  of every existing op are byte-identical (telemetry adds no keys to `_state()` output).
- **Reading trends (D7 recommendation):**

  ```bash
  python -m pipeline_visualizer --repo-root ~/source/repos/claude-config
  # browser → Trends tab: per-run cycles (forward/meta), cycles-per-completion,
  # gate refusals + containment trips per run, halt dwell, run durations —
  # trended across runs, with the deny ledger's unacked-debt trend alongside.
  ```

- **Reading raw events** (debugging, spot checks):

  ```bash
  tail ~/.claude/state/<repo_key>/lazy-telemetry.jsonl
  {"v": 1, "ts": 1783600001.2, "run_id": "2026-07-04T09:12:03Z", "pipeline": "feature",
   "event": "gate-refusal", "item_id": "doc-drift-linter",
   "data": {"gate": "verify-ledger", "failing_check": "clean_tree"}}
  ```

- **Retro output (D8):** the `/lazy-batch-retro` overview gains a "Ledger deltas" section, e.g.
  "feature X: 6 forward + 3 meta cycles, 2 gate refusals (`verify-ledger:clean_tree`), halt dwell
  41 min (ledger lines 118–160)" — every figure cited, per the skill's citation rule.
- **On failure:** a telemetry write failure is invisible to the run — the op succeeds normally; a
  `diagnostics[]` breadcrumb (`telemetry: append failed (<err>)`) is the only trace. The trends
  page renders an honest empty/partial state ("no telemetry recorded for this window") rather
  than fabricating zeros.

## Technical Design

```
state-script chokepoints (write paths, marker-gated)          per-repo keyed state dir
 --run-start / --run-end            ─┐
 --cycle-begin / --cycle-end         │  lazy_core.append_telemetry_event()
 --emit-prompt dispatch (+halt)      ├──(plain append, fail-open)──▶  lazy-telemetry.jsonl
 --apply-pseudo (+refusal)           │                                (+ .1..N rotated, D6)
 --verify-ledger / --gate-coverage   │
 exit-3 containment refusals         │        lazy-deny-ledger.jsonl  (existing, untouched)
 --neutralize-sentinel              ─┘                 │
                                                       ▼
                              pipeline_visualizer/trends.py (pure read, stdlib)
                               reads telemetry + deny ledgers (+ docs/telemetry/cloud/*.jsonl
                               committed segments, D5-B) → derives metrics (D9)
                                        │                        │
                                        ▼                        ▼
                              /api/trends (TtlCache)      /lazy-batch-retro
                              → static Trends tab          "Ledger deltas" citations
```

- **Emitter (`lazy_core`):** `_TELEMETRY_LEDGER_FILENAME = "lazy-telemetry.jsonl"` beside
  `_DENY_LEDGER_FILENAME`; `append_telemetry_event(event, *, item_id=None, data=None, now=None)
  -> bool` with the D1 envelope, run identity read from the live marker
  (`read_run_marker()` → `started_at`; no marker → no emit, per D3), and D6 rotation inline.
  `read_telemetry_events(paths=None) -> list[dict]` skips unparseable lines and unknown `v`,
  mirroring `read_deny_ledger()`. No legacy-migration entry is needed — the file never existed
  un-keyed, so `migrate_legacy_state_dir()` is untouched.
- **Chokepoint wiring (both scripts):** each D4-B event is one `append_telemetry_event(...)` call
  inside the existing handler in `lazy-state.py` and `bug-state.py` (`--bug-id` scripts pass
  their own item ids — the documented arg-name divergence stands). Shared helper + mirrored call
  sites keep `lazy_parity_audit.py --repo-root .` green; the refusal-site emissions fire after
  the refusal decision and before exit, so a refused op still has ZERO state side effects beyond
  the append-only ledger line (the ledger is observability, not state — same standing the deny
  ledger already has at guard-deny time).
- **Aggregator (`pipeline_visualizer/trends.py`):** stdlib-only pure functions —
  `runs(events)`, `cycles_per_completion(events)`, `refusal_counts(events, denies)`,
  `halt_dwell(events)` (first `halt` per item/sentinel → matching `sentinel-resolved`),
  `run_durations(events)` — plus a `__main__`-style CLI for D8. It never writes anything and
  never re-infers pipeline state (it aggregates recorded facts; `probe.py` remains the state
  authority).
- **Server:** `server.py` `make_server` gains `/api/trends`, cached by the existing `TtlCache`
  pattern so a polling frontend never re-reads ledgers more than once per TTL; `static/` gains
  the Trends tab (`index.html` + `app.js`).
- **House invariants honored:** script-owned deterministic emission (never LLM-authored events);
  fail-open writer (never blocks, never raises); per-repo keyed state dir residency; coupled-pair
  parity via a shared `lazy_core` helper + parity audit; pure-read aggregation; stdlib-only
  Python; `_atomic_write` untouched for its domain (this file is the documented append-only
  exception, like the deny ledger); read paths (`--probe` et al.) byte-identical and
  side-effect-free.

## Implementation Phases

- **Phase 1 — Emitter substrate in `lazy_core` (~1 session).** `append_telemetry_event` +
  `read_telemetry_events` + rotation, with pytest coverage in `test_lazy_core.py`: envelope shape,
  `now=` injection, marker-gating (no marker → no file, no line), fail-open on an unwritable dir,
  torn-line + unknown-`v` tolerance, rotation shift. Proven done: pytest green; no existing test
  perturbed.
- **Phase 2 — Chokepoint wiring in both state scripts (~1–2 sessions).** Wire the D4-resolved
  event set into `lazy-state.py` and `bug-state.py`; in-file `--test` fixtures assert one event
  per chokepoint, byte-identical JSON output and exit codes for every existing op, and zero
  emission from bare `--probe`. Proven done: both `--test` harnesses green +
  `lazy_parity_audit.py --repo-root .` clean.
- **Phase 3 — Trends aggregator + visualizer page (~1–2 sessions).** `trends.py`, `/api/trends`,
  static Trends tab; `test_pipeline_visualizer.py` fixtures assert aggregates match hand-computed
  values over a fixture ledger, empty-ledger honesty, and cache debounce. Proven done: pytest
  green + a manual browser check against a real instrumented run.
- **Phase 4 — Consumers + residency follow-through (~1 session).** `/lazy-batch-retro` "Ledger
  deltas" step (skill edit + re-project + `lint-skills.py`); cloud run-end flush if D5 resolves
  to B (coupled-pair divergence tabulated in `/lazy-batch-cloud`'s Differences block). Proven
  done: a retro over an instrumented run cites ledger lines; a cloud run lands its committed
  segment.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Chokepoints emit | Marker-gated `--run-start` → `--cycle-begin` → `--cycle-end` → `--run-end` in a fixture repo | Four envelope-valid lines with the same `run_id` | in-file `--test` fixture |
| Read-path purity | Bare `--probe` with and without a marker | No ledger line appended; no state dir created when absent | `--test` fixture + pytest |
| Fail-open | Unwritable state dir during an op | Op exit code + JSON byte-identical; emitter returns False | `test_lazy_core.py` |
| Refusal capture | Subagent `--apply-pseudo` (exit 3) and `--verify-ledger` on a dirty tree (exit 1) | One `containment-refusal` / `gate-refusal` line each; refusal semantics unchanged | `--test` fixtures |
| Halt dwell derivable | `halt` event then `--neutralize-sentinel` | `halt_dwell` = ts delta between the pair | `test_pipeline_visualizer.py` |
| Parity | Any emitter change | Parity audit clean | `lazy_parity_audit.py --repo-root .` |
| Trends page | Visualizer over a fixture ledger | `/api/trends` aggregates match hand-computed values; empty ledger renders honest empty state | `test_pipeline_visualizer.py` + browser |
| Retro citations | `/lazy-batch-retro` over an instrumented run | Overview "Ledger deltas" with per-figure ledger line citations | Manual retro run |
| Rotation | Active file pushed past the cap in a fixture | `.1` segment created; reader walks segments oldest-first | `test_lazy_core.py` |

## Open Questions

- **D4 — v1 event vocabulary:** minimal brackets vs brackets+gates+halts vs maximal.
  Recommendation: B (brackets + dispatch/halt + gate/containment refusals + sentinel-resolved) —
  the smallest set covering every seed metric.
- **D5 — residency + cloud transport:** state-dir-only vs state-dir + committed cloud run-end
  segment flush vs fully committed. Recommendation: B (workstation state dir; cloud flushes
  `docs/telemetry/cloud/<run_id>.jsonl` riding the final push, LAZY_QUEUE.md precedent).
- **D6 — retention/rotation:** none vs size-based rollover (10 MB × 4 segments) vs per-run files.
  Recommendation: B (size-based rollover; bounded reads, multi-year history at estimated volume).
- **D7 — trends channel:** visualizer page only vs committed `TRENDS.md` vs both. Recommendation:
  A (visualizer page; committed trend aggregates would never be byte-stable).
- **Deferred empirical checks (implementation, not decisions):** measure real per-run event volume
  against the ~60 KB/50-cycle estimate (Phase 2); confirm `--emit-prompt` is the sole
  orchestrator per-cycle dispatch surface across all three batch wrappers before binding the
  `dispatch` event to it (Phase 2); confirm the visualizer's polling path never routes through a
  write-path handler (Phase 2).

## Research References

- `RESEARCH.md` — internal desk research (Gemini deep research intentionally skipped by operator
  directive, 2026-07-04). Key influences: the `lazy-deny-ledger.jsonl` writer/reader contract and
  the raw-events-vs-derived-metrics split from OpenTelemetry/structured-logging practice.
- `user/scripts/lazy_core.py` — `append_deny_ledger_entry` / `append_friction_ledger_entry` /
  `claude_state_dir` / `write_run_marker` (the cloned contracts).
- `user/scripts/pipeline_visualizer/` — server/probe/cache split the trends page extends.
- `docs/features/mobile-queue-control/SPEC.md` — ride-the-commit publication precedent (D5-B).
- `docs/features/ROADMAP.md` "Self-evolution cluster" — the substrate role this feature plays.
