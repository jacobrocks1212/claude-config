# Implementation Phases — Friction KPI Registry + Scorecards

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In Progress

**MCP runtime:** not-required — pure claude-config harness mechanics (a committed JSON registry,
a stdlib Python renderer/linter, a `/spec`-injected gate component, and orchestrator-prose regen
wiring). No Tauri app, no MCP-reachable surface; validation is `pytest` on the new
`test_kpi_scorecard.py`, the existing gate suite, and `lint-skills.py` + `project-skills.py`
after the skill/component edits. This is the `standalone — no app integration` untestable class
→ `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** harness-telemetry-ledger — hard` — and that upstream has LANDED on this base:

- **`harness-telemetry-ledger` (Complete):** owns `lazy-telemetry.jsonl` (per-repo keyed state
  dir + committed `docs/telemetry/cloud/*.jsonl` segments), the shared emitter
  `lazy_core.append_telemetry_event` / reader `read_telemetry_events`, and the D4-B event
  vocabulary (`run-start`, `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`,
  `halt`, `sentinel-resolved`, `gate-refusal`, `containment-refusal`). This feature's
  `telemetry-ledger` KPI selectors bind those exact event names, and `kpi-scorecard.py` REUSES
  `pipeline_visualizer/trends.py`'s pure aggregation functions (`halt_dwell`,
  `cycles_per_completion`, `refusal_counts`, `load_events`) rather than re-implementing them —
  one computation, two renderers (the D5 "importable functions" intent).
- **`mobile-queue-control` (Complete):** `lazy-queue-doc.py` is the structural template
  (pure-read stdlib generator, byte-stable, `--stdout`, per-cycle-commit regen wiring in
  `user/skills/lazy-batch/SKILL.md` + `.claude/skill-config/commit-policy.md`). The scorecard
  joins the SAME regen blockquote/commit step.
- **`multi-repo-concurrent-runs` (Complete):** state-dir residency is per-repo keyed;
  the scorecard resolves it via `lazy_core.set_active_repo_root` + `claude_state_dir` (the
  `trends._bind_lazy_core` pattern); hermetic tests use `LAZY_STATE_DIR`.
- **Downstream (unbuilt, no integration yet):** `intervention-efficacy-tracking` (hypotheses
  against KPI row ids) and `harness-change-canary-rollback` (consumes regression flags) — this
  feature only guarantees stable row `id`s and the OK/WARN/BREACH flag surface.
- **Operator-directed scope cut (this lane, 2026-07-04):** `build-queue-enforce.sh` and all
  `.ps1` build-queue files are NOT modified — the hook-side deny append and the runner
  queued-at/started-at timestamp add are workstation-deferred follow-ups recorded in the
  registry rows' `notes` and in Phase 2 below.

---

### Phase 1: Registry + lint

**Phase kind:** design

**Scope:** The committed declaration surface and its deterministic validator. Seed
`docs/kpi/registry.json` with the six D8 rows (honest `provenance: pending` everywhere — this
container has no signal history; `--capture-baseline` on the workstation is the sanctioned path
to `measured`), and ship `kpi-scorecard.py --lint`: schema shape, id regex + uniqueness, closed
source enum + per-source closed selector enum, direction enum, provenance enum, band
ordering/pending coherence, `review_by` rot flagging.

**Deliverables:**
- [x] `docs/kpi/registry.json` — `{"schema_version": 1, "kpis": [...]}` with the six D8 seed rows (build-queue false-green rate, build-queue queue wait time, build-queue raw-invocation deny recurrence, containment runaway-trip rate, halt dwell, cycles-per-completion), each carrying the full D2 row schema; build-queue rows `repo_scope: cognito-forms`; every baseline `provenance: pending` with `value: null`, `band: null` (no fabricated history), `notes` documenting the workstation-deferred signal gaps.
- [x] `user/scripts/kpi-scorecard.py` — module skeleton (stdlib-only; `_SCRIPTS_DIR` sys.path bootstrap) + `load_registry` + `lint_registry(registry, today)` returning `(errors, warnings)`; CLI `--lint` prints findings and exits non-zero on errors (warnings alone exit 0).
- [x] `user/scripts/test_kpi_scorecard.py` — importlib load of the dash-named module; lint green on the seeded real registry; red (named row + field) on each fixture violation: bad id, duplicate id, unknown source, unknown selector, bad direction, bad provenance, inverted band per direction, band present with pending baseline, malformed review_by; rot warning on a past `review_by`.

**Minimum Verifiable Behavior:** `python3 user/scripts/kpi-scorecard.py --lint --repo-root .`
exits 0 on the seeded registry; corrupting any row's `signal.source` to an unknown value makes
it exit 1 naming the row id and field.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Lint green on the seeded registry, red on each fixture violation. *(Evidence: `SKIP_MCP_TEST.md` — `test_kpi_scorecard.py` lint suite + a live `--lint` run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase).

**Files likely modified:** `docs/kpi/registry.json` (new), `user/scripts/kpi-scorecard.py` (new), `user/scripts/test_kpi_scorecard.py` (new).

**Testing Strategy:** Hermetic pytest fixtures write temp registries under `tmp_path`; the real
registry is linted as its own test. No state-dir access in Phase 1 (lint is pure).

**Integration Notes for Next Phase:** Phase 2's renderer consumes `load_registry` + the lint's
row model; selectors registered in Phase 1's closed enum get their computation in Phases 2–3.

---

### Phase 2: Scorecard over computable-today signals

**Phase kind:** design

**Scope:** The pure-read renderer for the `deny-ledger`, `build-queue-results`, and
`sentinel-scan` sources; the D4-A status semantics (OK / WARN / BREACH / NO-DATA /
PENDING-BASELINE honoring `direction`); NO-DATA/PENDING honesty (unreadable/absent source →
NO-DATA + footnote, never zero); byte-stable `docs/kpi/SCORECARD.md` (+ `--stdout`); the
queue-wait-time field verification outcome (NOT computable — row renders NO-DATA with the
documented runner follow-up).

**Deliverables:**
- [x] Signal layer: per-source readers with explicit availability (absent deny ledger / absent build-queue results dir / missing docs trees → `(None, note)`, never 0). Build-queue dir default `~/.claude/state/build-queue` with `KPI_BUILD_QUEUE_DIR` env override for hermetic tests; deny ledger via `lazy_core.read_deny_ledger` after `set_active_repo_root` (LAZY_STATE_DIR honored).
- [x] Selectors (computable-today set): `build-queue-results/false-green-rate` (`hygiene.build_fidelity ∈ {log-failure-override, no-output}` over non-`n/a` records, percent), `build-queue-results/queue-wait-p50-seconds` (returns no-data + footnote — results/<seq>.json carries no queued-at/started-at pair; runner add is a **workstation-deferred follow-up**, .ps1 untouched per operator direction), `deny-ledger/build-queue-enforce-deny-count` (reason_head signature filter; hook-side append workstation-deferred), `deny-ledger/guard-deny-count`, `deny-ledger/process-friction-count`, `sentinel-scan/open-halt-count` (BLOCKED.md/NEEDS_INPUT.md count under docs/features+bugs).
- [x] Status engine: `row_status(row, value)` — NO-DATA on `value is None`; PENDING-BASELINE on `provenance: pending` or `band: null`; else pure warn/breach comparison honoring `direction`.
- [x] Renderer: per-system tables (registry order), baseline cell with provenance + captured_at, band cell, status cell with direction glyph; `## Regressions`, `## Registry health`, `## Notes` (per-row footnotes) sections; single trailing newline; NO wall-clock embed. `main()` default writes `<repo>/docs/kpi/SCORECARD.md`; `--stdout` prints.
- [x] `docs/kpi/SCORECARD.md` committed — real render over this container's state: all six rows honestly NO-DATA/PENDING-BASELINE (no build-queue state, no run ledgers here).
- [x] Tests: fixture-driven value checks per selector (hand-computed expectations), availability-vs-zero distinction, status matrix (both directions × OK/WARN/BREACH edges at exact thresholds), byte-stability (two renders of unchanged fixtures byte-identical; injected `now`), live-render smoke over this repo.

**Minimum Verifiable Behavior:** With a fixture results dir containing 4 build records (1
`no-output`), `false-green-rate` renders `25%`; deleting the dir renders NO-DATA with a footnote
— never `0%`. Two consecutive renders are byte-identical.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Scorecard values match hand-computed fixture expectations; missing sources render NO-DATA, `pending` baselines render PENDING-BASELINE (never 0). *(Evidence: `SKIP_MCP_TEST.md` — `test_kpi_scorecard.py` selector + honesty suites.)* <!-- verification-only -->
- [x] Byte-stable regen: re-render with unchanged inputs is byte-identical (no wall-clock diff). *(Evidence: `test_kpi_scorecard.py` byte-stability test + live double-render diff.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** a real build-queue render over live `~/.claude/state/build-queue/results/*.json` history (this container has no build-queue state; the rows correctly render NO-DATA here — the live-value render happens on the workstation after merge).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (registry + row model).

**Files likely modified:** `user/scripts/kpi-scorecard.py`, `user/scripts/test_kpi_scorecard.py`, `docs/kpi/SCORECARD.md` (new).

**Testing Strategy:** Hermetic fixtures: temp registry + temp build-queue results dir
(`KPI_BUILD_QUEUE_DIR`) + `LAZY_STATE_DIR` for the deny ledger + temp docs trees for
sentinel-scan. Value assertions are exact (fixed rounding). Injected `now`/`today` for
windowing and rot.

**Integration Notes for Next Phase:** Phase 3 adds the `telemetry-ledger` selectors on the same
signal-layer shape and the Regressions flags over the Phase 2 status engine.

---

### Phase 3: Ledger-backed rows + regression flags + run-boundary regen wiring

**Phase kind:** integration

**Scope:** The `telemetry-ledger` source (containment trips, halt dwell, cycles-per-completion)
reusing `pipeline_visualizer/trends.py`; the `## Regressions` section flags WARN/BREACH rows;
the regen wiring lands at the same orchestrator commit step that regenerates `LAZY_QUEUE.md`
(per-cycle commit blockquote in `/lazy-batch` + `.claude/skill-config/commit-policy.md`), with
the coupled-pair record mirrored into `/lazy-batch-cloud`'s Differences table.

**Deliverables:**
- [x] Telemetry selectors over `trends` functions: `containment-refusal-count` (windowed event count), `halt-dwell-p50-seconds` (median of resolved `halt`→`sentinel-resolved` dwells; unresolved halts excluded, empty → no-data note), `cycles-per-completion` (`trends.cycles_per_completion`; zero completions → no-data note, never a fabricated ratio). Availability = any ledger segment or cloud segment file exists (absent → NO-DATA).
- [x] Regressions section: WARN/BREACH rows rendered `⚠ <system>/<id> <STATUS>: <current> vs band <threshold> (baseline <value>)`; `- (none)` otherwise. Fixture crossing warn then breach (both directions) renders the right flag.
- [x] Regen wiring (prose, orchestrator-invoked only, fail-open): extend the `/lazy-batch` per-cycle regen blockquote + commit-policy bullet to also run `python user/scripts/kpi-scorecard.py --repo-root <repo_root>` when `docs/kpi/registry.json` exists (registry-gated no-op elsewhere; a scorecard failure never blocks the commit); add the mirrored "Differences from `/lazy-batch`" table row in `/lazy-batch-cloud` covering the committed-doc regen (also retro-recording the `LAZY_QUEUE.md` wiring the pair table omitted).
- [x] Tests: fixture telemetry ledgers (hermetic `LAZY_STATE_DIR`) produce hand-computed dwell/ratio/count values; band-crossing fixtures render WARN and BREACH flags in Regressions; ledger-absent → NO-DATA.

**Minimum Verifiable Behavior:** A fixture ledger with one resolved halt (dwell 3600s) renders
`halt-dwell-p50` = 3600 seconds; a fixture containment-trip count past the row's `breach`
renders a `## Regressions` BREACH line naming the row.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Fixture ledger produces expected values; a band-crossing fixture renders a BREACH flag. *(Evidence: `SKIP_MCP_TEST.md` — `test_kpi_scorecard.py` telemetry + regression suites.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** observing the regen ride a real `/lazy-batch` per-cycle commit (requires a live orchestrator run on the workstation; the wiring is prose consumed by the orchestrator, mirrored from the proven `LAZY_QUEUE.md` block).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2 (registry, signal layer, status engine).

**Files likely modified:** `user/scripts/kpi-scorecard.py`, `user/scripts/test_kpi_scorecard.py`, `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `.claude/skill-config/commit-policy.md`.

**Testing Strategy:** Hermetic `LAZY_STATE_DIR` telemetry fixtures (JSONL lines with injected
`ts`); reuse `trends`' own event-envelope shape so the scorecard and `/api/trends` can never
disagree on parsing. Skill-prose edits verified by projection + `lint-skills.py` (Phase 4 runs
the full pass).

**Integration Notes for Next Phase:** Phase 4's `--lint --spec` reuses `load_registry` + the
row-level lint; the gate component shells the CLI this phase completed.

---

### Phase 4: `/spec` measurability gate + baseline capture

**Phase kind:** integration

**Scope:** The planning-time gate: `user/skills/_components/spec-friction-kpi-gate.md`
(classification line contract, `## KPI Declaration` format, D6-B advisory keyword cross-check,
batch NEEDS_INPUT vs interactive refuse-to-finalize), injected into `/spec` Phase 3 as a
BLOCKING Step 8.5 beside the dep-block checkpoint (+ a Phase 1 `--batch` contract reference +
the classification line added to the Phase 3 SPEC template); the deterministic
`--lint --spec <path>` validator backstop; `--capture-baseline <kpi-id>`
(`_atomic_write`-backed, `provenance: measured`, refuses on no-data); projection + skill lint;
docs rows.

**Deliverables:**
- [x] `user/skills/_components/spec-friction-kpi-gate.md` — new component (mcp-coverage-audit style): why/inputs/algorithm (classify → declare → shell `kpi-scorecard.py --lint --spec` → route), batch vs interactive table, advisory keyword cross-check (non-blocking), registry-residency note for non-claude-config repos (`--registry` / full-schema drafts), coupling note naming the `/spec` injection.
- [x] `user/skills/spec/SKILL.md` — Phase 3 Step 8.5 injection (per-repo override form) beside the Step 8 dep-block checkpoint; `**Friction-reduction feature:** {yes|no}` line added to the Phase 3 SPEC template; Phase 1 `--batch` contract references the classification duty.
- [x] `kpi-scorecard.py --lint --spec <path> [--registry <path>]` — validates the classification line (missing → error), `no` + advisory keyword hit → non-blocking warning, `yes` → `## KPI Declaration` must exist and every `- kpi: <id>` reference resolve to the registry and every fenced-JSON draft row pass row-level lint (else exit 1 naming the miss).
- [x] `kpi-scorecard.py --capture-baseline <kpi-id>` — computes the row's current windowed value; no-data → refusal exit 1 (a baseline is never fabricated); else stamps `baseline {value, captured_at (UTC today), window, provenance: measured}` via `lazy_core._atomic_write`.
- [x] Projection + lint: `project-skills.py` into a lane-local output dir + `lint-skills.py` clean after the skill/component edits.
- [x] Docs: root `CLAUDE.md` (scripts table row + key-components bullet), `user/scripts/CLAUDE.md` (script table row).
- [x] Tests: `--lint --spec` fixtures (friction SPEC w/o declaration → exit 1; ordinary SPEC w/ `no` line → exit 0 untouched; `no` + friction keywords → advisory warning exit 0; declaration w/ resolving ids → exit 0; unresolved id / invalid draft → exit 1); `--capture-baseline` provenance + refusal tests; registry file after capture remains lint-green.

**Minimum Verifiable Behavior:** `--lint --spec` on a fixture friction SPEC lacking
`## KPI Declaration` exits 1 naming the missing section; on an ordinary `no` SPEC exits 0 with
no demands; `--capture-baseline` over a fixture signal stamps `provenance: measured` and
refuses (exit 1) when the signal has no data.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Fixture friction-SPEC without a declaration fails the validator; an ordinary SPEC passes untouched; captured baselines carry correct provenance. *(Evidence: `SKIP_MCP_TEST.md` — `test_kpi_scorecard.py` gate-validator + capture suites.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** a live `/spec --batch` run on a fixture friction feature observing the NEEDS_INPUT round end-to-end (requires a live orchestrator + AskUserQuestion session; the injected prose + the deterministic validator it shells are both fully covered by projection/lint + pytest here).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/skills/_components/spec-friction-kpi-gate.md` (new), `user/skills/spec/SKILL.md`, `user/scripts/kpi-scorecard.py`, `user/scripts/test_kpi_scorecard.py`, `CLAUDE.md`, `user/scripts/CLAUDE.md`.

**Testing Strategy:** SPEC fixtures as tmp_path markdown files; registry fixtures for
resolution; capture tests over the Phase 2 fixture signals. Projection into
`/tmp/proj-friction-kpi-registry` (lane-local; never the shared projected dir).
