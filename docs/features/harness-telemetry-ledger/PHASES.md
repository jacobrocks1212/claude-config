# Implementation Phases — Harness Telemetry Ledger + Trends

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state scripts +
`pipeline_visualizer` + skill prose). No Tauri app, no MCP-reachable surface; validation is
`pytest` on `test_lazy_core.py` / `test_pipeline_visualizer.py`, the `lazy-state.py --test` /
`bug-state.py --test` smoke baselines, `lazy_parity_audit.py`, and `lint-skills.py`. This is the
`standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** (none)`. Substantive dependencies are implemented data contracts, not sibling
specs (see the SPEC dep-block):

- **Deny-ledger precedent (`hardening-blind-to-process-friction`, shipped):**
  `append_deny_ledger_entry` / `append_friction_ledger_entry` / `read_deny_ledger` are the cloned
  writer/reader contract (plain append, fail-open, torn-line tolerance). The deny ledger itself
  stays untouched; the trends aggregator reads it as a second source.
- **`multi-repo-concurrent-runs` (Complete):** `claude_state_dir()` per-repo keying is where the
  ledger lives; the `LAZY_STATE_DIR` override is the hermetic test seam every new test uses.
- **Marker machinery (`turn-routing-enforcement` + follow-ups):** `write_run_marker`'s
  `started_at` is the `run_id`; marker-gating (D3) reuses the documented "without the marker,
  registry writes / counter advances are no-ops" rule. NOTE: the emitter reads the marker RAW and
  NON-destructively (never via `read_run_marker`, whose stale-path deletes) so exit-3 refusal
  paths keep their zero-side-effects contract.
- **`pipeline_visualizer` (Complete):** `/api/trends` is one more route on the existing
  `ThreadingHTTPServer`; the trends producer is a module attribute (monkeypatch-able) exactly
  like `probe_state`; the second `TtlCache` mirrors the `/api/state` debounce.
- **Downstream consumers (not dependencies):** `friction-kpi-registry`,
  `intervention-efficacy-tracking`, `harness-change-canary-rollback` bind to this ledger's event
  streams — raw events only (D9), so their future derivations never invalidate recorded history.

---

### Phase 1: Emitter substrate in `lazy_core`

**Phase kind:** design

**Scope:** The shared telemetry writer/reader in `lazy_core.py`: envelope (D1), fail-open plain
append (D2), non-destructive marker-gating (D3), size-based rotation (D6-B), plus the D5-B cloud
flush helper and the D4-B halt-terminal vocabulary constant. No chokepoint wiring yet.

**Deliverables:**
- [x] `lazy_core.py`: `_TELEMETRY_LEDGER_FILENAME = "lazy-telemetry.jsonl"` +
  `_TELEMETRY_SCHEMA_VERSION = 1` + `_TELEMETRY_ROTATE_BYTES = 10 MB` +
  `_TELEMETRY_ROTATED_SEGMENTS = 4`, beside `_DENY_LEDGER_FILENAME`.
- [x] `lazy_core._telemetry_run_marker(now=None)` — RAW, NON-destructive marker read (parse +
  24h age-fresh check only; never unlinks, never session-gates) so emission from a refusal path
  has zero state side effects.
- [x] `lazy_core.append_telemetry_event(event, *, item_id=None, data=None, now=None) -> bool` —
  D1 envelope `{v, ts, run_id, pipeline, event, item_id, data}`; run identity + pipeline from the
  live marker; **no marker → no write, returns False** (D3); plain `open("a")` append (never
  `_atomic_write`); swallows every exception → False (D2); inline rotation (D6-B) whose own
  failure degrades to plain append. NEVER calls `_diag` (keeps every op's `diagnostics[]`
  byte-identical even on emitter failure).
- [x] `lazy_core.read_telemetry_events(paths=None, with_provenance=False) -> list[dict]` —
  default path set walks rotated segments oldest-first (`.4 → .1`) then the active file; skips
  blank/torn/non-dict lines and unknown `v`; `with_provenance=True` additionally stamps
  `_source`/`_line` (1-based) for retro citations.
- [x] `lazy_core.TELEMETRY_HALT_TERMINAL_REASONS` — frozenset {blocked, needs-input,
  needs-spec-input, needs-research, completion-unverified, blocked-misnamed} (D4-B halt set).
- [x] `lazy_core.flush_cloud_telemetry_segment(repo_root, now=None) -> dict | None` — D5-B:
  marker-gated on `cloud: true`; filters ledger events to the live `run_id`; writes
  `docs/telemetry/cloud/<run_id colon-stripped>.jsonl` via `_atomic_write` (one-shot segment,
  not an append-only file); returns `{path, events}` or None; fail-open.
- [x] `test_lazy_core.py` (pytest; every new no-arg test registered in a `_TESTS` block):
  envelope shape + `now=` injection; marker-gating (no marker → no file, no line, False);
  fail-open on an unwritable state dir (False, no raise); torn-line + unknown-`v` + non-dict-line
  tolerance; rotation shift (cap exceeded → `.1` created, oldest `.4` dropped, reader
  oldest-first order); non-destructive marker read (stale marker NOT deleted by a failed emit);
  cloud-flush segment content/filename + non-cloud no-op.

**Minimum Verifiable Behavior:** With `LAZY_STATE_DIR` at a temp dir and a live run marker,
`append_telemetry_event("run-start")` appends one envelope-valid line with
`run_id == marker.started_at`; with no marker it writes nothing and returns False; with the state
dir replaced by a file it returns False without raising.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Envelope + gating + fail-open + rotation proven by `test_lazy_core.py` (new tests green, all prior tests unperturbed). *(Evidence: SKIP_MCP_TEST.md — pytest suite counts.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** None (first phase).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Testing Strategy:** TDD — write the pytest cases RED first (symbols absent), then implement.
Hermetic via `LAZY_STATE_DIR` temp dirs (`_set_state_dir`/`_clear_state_dir` precedent); `now=`
injection for deterministic `ts`; small rotate-bytes override via monkeypatched constant for the
rotation test (no 10 MB fixtures).

**Integration Notes for Next Phase:** Phase 2 wires ONE `append_telemetry_event(...)` call per
chokepoint in both scripts; the three exit-3 refusal helpers get their call INSIDE `lazy_core`
(one site, both scripts covered — parity by construction).

---

### Phase 2: Chokepoint wiring in both state scripts

**Phase kind:** integration

**Scope:** Emit the D4-B event set from the CLI write-path handlers of `lazy-state.py` and
`bug-state.py` (mirrored), plus the shared exit-3 refusal helpers in `lazy_core`, plus the D5-B
flush call in both `--run-end` handlers. Every existing op's exit code and JSON output stays
byte-identical for all previously-possible states (the only new output key, `telemetry_flushed`,
requires telemetry events that could not exist pre-feature).

**Deliverables:**
- [x] `lazy-state.py`: `run-start` (after `write_run_marker`, data: cloud/max_cycles/resumed),
  `run-end` (success path, BEFORE flush + `delete_run_marker`; data: reason/terminal_reason),
  `cycle-begin` (item_id=feature_id; data: kind/sub_skill), `cycle-end` (item_id from the cycle
  marker read before clear; data: cleared/process_friction reason), `dispatch` + conditional
  `halt` at `--emit-prompt` (item_id/current_step/sub_skill/terminal_reason
  (+route_overridden_by)), `pseudo-applied` / `gate-refusal` at `--apply-pseudo`, `gate-refusal`
  at `--verify-ledger` (failing_check) and `--gate-coverage` (uncovered), `sentinel-resolved` at
  `--neutralize-sentinel` success.
- [x] `bug-state.py`: the same wiring mirrored (`--bug-id` item ids; no `--gate-coverage` — the
  documented pre-existing divergence), each call commented as a coupled-pair mirror.
- [x] `lazy_core.py`: `containment-refusal` emission inside `refuse_if_cycle_active`,
  `refuse_cycle_marker_mutation_if_subagent`, `refuse_run_start_clobber` — after the refusal
  decision, before `sys.exit(3)` (append-only ledger line = observability, not state).
- [x] D5-B flush: both `--run-end` handlers call `flush_cloud_telemetry_segment` after the
  run-end emission and before `delete_run_marker`; on a written segment the output JSON gains
  `telemetry_flushed: {path, events}`.
- [x] In-file `--test` fixtures (BOTH scripts, registered in each harness): (a) full bracket
  run-start → cycle-begin → cycle-end → run-end via subprocess ⇒ ≥4 envelope-valid lines sharing
  one `run_id` (+ cloud variant asserts the committed segment + `telemetry_flushed`); (b) bare
  probe purity — no marker ⇒ no ledger/state-dir creation; marker present ⇒ probe appends
  nothing; (c) subagent `--apply-pseudo` exit-3 ⇒ one `containment-refusal` line, refusal
  semantics unchanged; (d) `--apply-pseudo` exit-1 verdict ⇒ one `gate-refusal` line (feature
  script also covers `--gate-coverage` exit-1).
- [x] Baselines regenerated ONLY via `_normalize_smoke_output` (new PASS lines are a legitimate
  fixture addition): `tests/baselines/lazy-state-test-baseline.txt` +
  `bug-state-test-baseline.txt`.
- [x] `lazy_parity_audit.py --repo-root .` exit 0 (shared helper + mirrored call sites).

**Minimum Verifiable Behavior:** In a fixture repo with `LAZY_STATE_DIR` pinned:
`--run-start` → `--cycle-begin` → `--cycle-end` → `--run-end` leaves ≥4 envelope-valid
`lazy-telemetry.jsonl` lines with the same `run_id`; a bare `--probe` appends none; a subagent
`--apply-pseudo` still exits 3 with a `containment-refusal` line as its only side effect.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Bracket emission + read-path purity + refusal capture proven by both `--test` harnesses green against regenerated baselines. *(Evidence: SKIP_MCP_TEST.md.)* <!-- verification-only -->
- [x] Parity audit clean after wiring. *(Evidence: `lazy_parity_audit.py --repo-root .` exit 0.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phase 1.

**Files likely modified:** `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`,
`user/scripts/lazy_core.py`, `user/scripts/tests/baselines/lazy-state-test-baseline.txt`,
`user/scripts/tests/baselines/bug-state-test-baseline.txt`.

**Testing Strategy:** Subprocess-driven `--test` fixtures (the `cycle-marker-mutation-guard`
precedent) with isolated `LAZY_STATE_DIR` + `LAZY_ORCHESTRATOR` env control; assert ledger line
counts/shape by parsing the JSONL directly. Deferred empirical checks from the SPEC: per-run
event volume ≈ a handful of ~200-byte lines per cycle (well under the 60 KB/50-cycle estimate);
`--emit-prompt` confirmed as the sole per-cycle real-dispatch surface; the visualizer polling
path (`--feature-id`/`--bug-id` scoped reads) routes through no write-path handler.

**Integration Notes for Next Phase:** Phase 3 consumes ONLY the on-disk ledger + deny ledger via
`read_telemetry_events` / `read_deny_ledger` — no state-script coupling. Event `data` keys
frozen by the Phase-2 fixtures: `kind`, `sub_skill`, `current_step`, `terminal_reason`, `gate`,
`failing_check`, `uncovered`, `pseudo`, `op`, `guard`, `sentinel`, `reason`, `cleared`,
`process_friction`, `cloud`, `max_cycles`, `resumed_from_checkpoint`.

---

### Phase 3: Trends aggregator + visualizer page

**Phase kind:** integration

**Scope:** `pipeline_visualizer/trends.py` (pure-read, stdlib-only aggregation + CLI),
`/api/trends` on the existing server (TtlCache-debounced), and the static Trends tab. Never
writes anything; never re-infers pipeline state.

**Deliverables:**
- [x] `pipeline_visualizer/trends.py`: pure functions over event lists — `runs(events)`,
  `cycles_per_completion(events)`, `refusal_counts(events, denies)`, `halt_dwell(events)`
  (first `halt` per item → matching later `sentinel-resolved`), `run_durations(events)`;
  loaders `load_events(repo_root)` (state-dir ledger via `lazy_core` + committed
  `docs/telemetry/cloud/*.jsonl`) and `load_denies(repo_root)`; `trends_payload(repo_root)`
  (the `/api/trends` aggregate, honest `telemetry_available: false` empty state);
  `run_summary(repo_root, run_id)` (the D8 retro view with per-figure `_source`/`_line`
  citations); `main()` CLI: `python3 -m pipeline_visualizer.trends --repo-root <r>
  [--run-id <id>]` → JSON on stdout.
- [x] `pipeline_visualizer/server.py`: `/api/trends` route served through a second `TtlCache`;
  trends producer referenced as a module attribute (monkeypatch-able like `probe_state`).
- [x] `static/`: Trends tab — `index.html` section + toggle, `app.js` fetch/render of
  `/api/trends` (per-run table: cycles forward/meta, cycles-per-completion, refusals, halt
  dwell, durations; deny-ledger unacked-debt alongside; honest empty state), `styles.css` rules.
- [x] `test_pipeline_visualizer.py`: aggregates match hand-computed values over a fixture
  ledger; empty-ledger honesty (`telemetry_available: false`); `/api/trends` server route JSON +
  cache debounce (fake clock + call counter, no sleeps); halt-dwell pairing; CLI `--run-id`
  summary shape.

**Minimum Verifiable Behavior:** Against a fixture ledger of two runs, `trends_payload` returns
hand-verifiable cycles/completions/refusal/dwell/duration numbers; `GET /api/trends` serves the
same JSON, at most one aggregation per TTL window; an absent ledger renders
`telemetry_available: false`, never fabricated zeros.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] `/api/trends` aggregates match hand-computed fixture values; empty ledger renders the honest empty state. *(Evidence: SKIP_MCP_TEST.md — `test_pipeline_visualizer.py`.)* <!-- verification-only -->
- [ ] Manual browser check of the Trends tab against a real instrumented run. *(Deferred: no browser/display in this cloud container; the tab's data path is covered by the `/api/trends` + static-serving tests. Re-open on a workstation visualizer session.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–2 (event shape frozen).

**Files likely modified:** `user/scripts/pipeline_visualizer/trends.py` (new),
`user/scripts/pipeline_visualizer/server.py`, `user/scripts/pipeline_visualizer/static/index.html`,
`user/scripts/pipeline_visualizer/static/app.js`,
`user/scripts/pipeline_visualizer/static/styles.css`, `user/scripts/test_pipeline_visualizer.py`.

**Testing Strategy:** TDD with hand-built event fixtures (deterministic `ts` values); server
tests reuse the ephemeral-port daemon-thread harness; `LAZY_STATE_DIR` pins the ledger location
for route tests.

**Integration Notes for Next Phase:** Phase 4's retro step shells
`python3 -m pipeline_visualizer.trends --run-id <id> --repo-root <repo>` — the CLI output shape
(`run_summary`) is the contract; "no telemetry for this run" is the honest miss answer.

---

### Phase 4: Consumers + residency follow-through

**Phase kind:** integration

**Scope:** `/lazy-batch-retro` "Ledger deltas" step (D8-A); `/lazy-batch-cloud` run-end prose +
"Differences from /lazy-batch" row for the D5-B committed segment; projection + skill lint.

**Deliverables:**
- [x] `user/skills/lazy-batch-retro/SKILL.md`: additive "Ledger deltas" step — shells the trends
  CLI scoped to the audited run's `run_id`, reports cycles-per-feature / gate refusals /
  containment refusals / halts + dwell in the overview artifact with per-figure ledger citations
  (CITATIONS-NOT-TRUST); missing/empty ledger → report "no telemetry for this run" honestly.
- [x] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`: run-end telemetry-segment
  commit prose (on `telemetry_flushed` in the `--run-end` JSON, `git add docs/telemetry/cloud/` +
  commit + push before STOP) + a new row in the "Differences from /lazy-batch" table (workstation
  = state-dir only, no flush).
- [x] Projection + lint: `project-skills.py` into a lane-local output dir + `lint-skills.py`
  clean.
- [ ] A retro over a real instrumented run cites ledger lines; a cloud run lands its committed
  segment. *(Deferred: needs a live batch run — this container has no completed instrumented run
  to retro. The mechanical halves are proven by the Phase-2 cloud-flush fixture and the Phase-3
  `run_summary` citation tests.)*

**Minimum Verifiable Behavior:** `lint-skills.py` clean over the edited skills; the retro skill's
new step names the exact CLI invocation and the honest-miss behavior; the cloud skill's
Differences table carries the new tabulated divergence.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Skill projection + lint green after the two skill edits. *(Evidence: SKIP_MCP_TEST.md — `lint-skills.py`.)* <!-- verification-only -->
- [ ] Live retro citation + live cloud segment landing. *(Deferred with the Phase-4 deliverable above — needs a real instrumented run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/skills/lazy-batch-retro/SKILL.md`,
`repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

**Testing Strategy:** Docs-only phase: projection into a lane-local dir (never the shared
`~/.claude/skills-projected`), `lint-skills.py`, plus a manual CLI dry-run of the exact command
the retro step names against the Phase-2 fixture ledger.
