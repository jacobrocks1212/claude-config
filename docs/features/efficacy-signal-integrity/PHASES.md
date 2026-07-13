# Implementation Phases — Efficacy Signal Integrity

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** In-progress (implementation complete; D2/D4 product-behavior decisions
provisionally adopted per `NEEDS_INPUT_PROVISIONAL.md` — pending ratify-or-redirect before
`__mark_complete__`)

**MCP runtime:** not-required — pure claude-config harness mechanics (evaluator/renderer script
edits + a JSON registry + a markdown doc). No Tauri app, no MCP-reachable surface; validation is
`pytest` on `test_efficacy_eval.py` / `test_kpi_scorecard.py`, `kpi-scorecard.py --lint`, and a
byte-stable double-render check. This is the `standalone — no app integration` untestable class
→ `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

`**Depends on:** interventions-telemetry-repo-scope-split-brain — hard` — that bug is FIXED and
archived (`docs/bugs/_archive/interventions-telemetry-repo-scope-split-brain/`); this feature's
KPI selectors and canary staleness computation read `lazy_core.read_intervention_telemetry`, the
merged/deduped/cross-repo-aware telemetry read the fix shipped.

- **`harness-change-canary-rollback` (Complete):** owns the `canary:` sub-map lifecycle
  (`open` → `tripped` / `closed-clean` / `closed-clean (no-data)`), `efficacy-eval.py --canary`,
  and the already-registered `canary-trip-precision` KPI selector. This feature extends
  `run_canary` (staleness alarm) and reads the SAME `canary:` sub-map read-only (never a second
  writer).
- **`intervention-efficacy-tracking` (Complete):** owns the base evaluator
  (`_review_record`/`_compute_verdict`/`_confounders_for`) this feature's D1 sub-signal seam
  extends in place (same functions, same file, no new module).
- **`friction-kpi-registry` (Complete):** owns `docs/kpi/registry.json` + `kpi-scorecard.py`'s
  lint/render/status-engine/`--capture-baseline` machinery this feature extends (`vantage` field,
  `WRONG-VANTAGE` status, the `intervention-records` source, the `## Canary health` section).
- **Cross-lane, STATE half APPLIED (state-batch-5):** `lazy_core.validate_intervention_target_signal`
  now parses the `event:<type>/<signature>` sub-signal grammar (accepts a KNOWN `<signature>` for
  an event type that declares a sub-signal vocabulary — v1: `gate-refusal` only, via a
  `_GATE_REFUSAL_SIGNATURES` set DUPLICATED from `efficacy-eval.py`'s own set of the same name per
  that module's own comment naming this exact seam; rejects an unknown signature or a signature on
  a type with no declared vocabulary; bare `event:<type>` targets are byte-unaffected).
  `_intervention_signal_event` now resolves a sub-signal target to the bare `<type>` (mirroring
  `efficacy-eval.py`'s `_resolve_target_signal` contract) instead of leaking the `/<signature>`
  suffix into the ledger event-type counting key. A DELTA beyond the literally-named two functions:
  the capture-time BASELINE FREEZE in `record_intervention` was ALSO sub-signal-aware-ified (a new
  `_intervention_signal_signature` helper + a `data.gate`-matching count), since without it a
  sub-signal record's frozen baseline would have silently counted every bare-type event
  (`gate-refusal` of ANY signature) rather than just its own signature — a correctness gap the
  capture-time vocabulary fix alone would not have closed. `test_lazy_core.py`: 6 new fixtures
  (`test_validate_intervention_target_signal_{accepts_known_sub_signal,rejects_unknown_sub_signal,
  rejects_sub_signal_on_unsupported_type,still_accepts_bare_event}`,
  `test_intervention_signal_event_resolves_sub_signal_to_bare_type`,
  `test_record_intervention_sub_signal_baseline_counts_matching_signature_only`).
  **Still cross-lane, NOT landed:** `user/skills/lazy-batch/SKILL.md` §1c.6 scorecard-regen-point
  wiring (SKILLS lane, out of the STATE lane's file ownership).

---

### Phase 1: Sub-signal seam

**Phase kind:** integration

**Scope:** `event:gate-refusal/<signature>` sub-signal targets inside `efficacy-eval.py`: the
resolver split, the signature-aware counting predicate (verdict arithmetic + canary band trip +
`--rebaseline`), and the D6 same-signal confounder predicate treating two different sub-signals
as disjoint while a bare declaration still conservatively confounds every sub-signal of its type.

**Deliverables:**
- [x] `_GATE_REFUSAL_SIGNATURES` — the closed `data.gate` set (`gate-coverage`,
  `unacked-hardening`, `efficacy-coverage-missing`, `checkpoint-auth`, `apply-pseudo`,
  `verify-ledger`), verified by grepping every live `append_telemetry_event("gate-refusal", ...)`
  call site.
- [x] `_target_signature(target_signal)` — parses the `<signature>` component of
  `event:<type>/<signature>`; `_resolve_target_signal` strips the same suffix so its `(kind,
  event_type)` contract is unchanged for existing callers.
- [x] `_event_matches_target(event, ev_type, signature)` — the sub-signal-aware counting
  predicate (event-type match AND, when a signature is declared, `data.gate` match); wired into
  `_compute_verdict`, `_canary_band_trip`, and `_rebaseline_record`.
- [x] `_same_signal(a, b)` — the D6 predicate: same event type + no signature on either side (a
  bare declaration) → overlap; same type + matching signatures → overlap; same type + different
  signatures → DISJOINT; wired into `_review_record`'s confounder cap (replacing the prior exact
  string equality).
- [x] Tests: `test_sub_signal_targets_grade_disjointly` (two sub-signal records with overlapping
  post windows both grade CONFIRMED, no cap), `test_bare_target_still_confounds_sub_signal` (a
  bare declaration caps a sub-signal record that would otherwise CONFIRM).

**Minimum Verifiable Behavior:** A fixture ledger with two records on `event:gate-refusal/gate-coverage`
and `event:gate-refusal/apply-pseudo` (overlapping post windows) both grade CONFIRMED with no
confounder cap; a fixture record on bare `event:gate-refusal` sharing the window with either
sub-signal record caps BOTH to `INCONCLUSIVE (confounded)`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Fixture ledgers reproduce both Validation-Criteria rows (disjoint grading; bare-target
  conservative overlap). *(Evidence: `SKIP_MCP_TEST.md` — `test_efficacy_eval.py`'s two
  sub-signal tests, green.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** None (first phase; the bug dependency is already Fixed).

**Files likely modified:** `user/scripts/efficacy-eval.py`, `user/scripts/test_efficacy_eval.py`.

**Testing Strategy:** Hermetic `LAZY_STATE_DIR` + temp-repo fixtures (existing `_seed_runs`/
`_capture` helpers); a new `_set_target_signal` fixture helper mirrors the existing `_add_canary`
pattern to inject a sub-signal `target_signal` past the capture-time vocabulary gate the STATE
lane has not yet closed (see the report) — real record IO throughout via
`lazy_core._render_intervention_record`, never a hand-rolled shape beyond that one field.

**Integration Notes for Next Phase:** Phase 2 extends the SAME `run_canary` function this
resolver leaves untouched (canary band-trip counting was updated in Phase 1 for signature
awareness; Phase 2 adds the staleness aggregate alongside the existing trip/close logic).

---

### Phase 2: Canary health

**Phase kind:** integration

**Scope:** The staleness alarm (D2): a continuous open-canary gauge computed at every
`--canary` invocation (open count, oldest age, projected no-data-close count), surfaced as
`staleness`/`staleness_notify` in the JSON payload and the plain-text flush output; a mirrored
`## Canary health` committed-channel section in `docs/kpi/SCORECARD.md`.

**Deliverables:**
- [x] `CANARY_STALENESS_LOOKAHEAD_DAYS = 7` + `_canary_age_days` in `efficacy-eval.py`.
- [x] `run_canary`'s still-open (monitoring) population now also aggregates `staleness`
  (`open_count`, `oldest_age_days`, `projected_no_data_close_count`, `lookahead_days`) and a
  `staleness_notify` one-liner (`"⚠ N canaries open, oldest Xd, M will no-data-close within
  7d"`), rendered whenever `open_count > 0`; the degraded (`except Exception`) fallback payload
  carries honest all-zero staleness fields too.
- [x] `kpi-scorecard.py::_canary_health_summary` — a pure-read mirror over
  `docs/interventions/*.md` (open canaries only) + `lazy_core.read_intervention_telemetry` (for
  the "zero observed post-ship runs" leg of the projection), deliberately duplicated rather than
  importing `efficacy-eval.py` (kpi-scorecard.py stays a standalone pure-read renderer, the
  `lazy_coord.py`/`lazy_core.py` small-helper-duplication precedent).
- [x] `render_scorecard`'s new `## Canary health` section (accepts an optional `canary_health`
  dict; omitted → honest `(none open)`, byte-identical to pre-D2 renders).
- [x] Tests: `test_canary_staleness_alarm_precedes_ceiling`, `test_canary_staleness_notify_zero_projected_when_not_near_ceiling`,
  `test_canary_staleness_silent_when_no_open_canaries` (efficacy-eval.py); `TestCanaryHealthSummary`
  (kpi-scorecard.py: open-count/age/projection arithmetic + the render section, both the
  populated and `(none open)` cases).

**Minimum Verifiable Behavior:** A fixture canary opened 25 days ago (window far from
run-matured, zero post-ship runs observed) surfaces `staleness.projected_no_data_close_count ==
1` and a non-`None` `staleness_notify` naming `"will no-data-close within 7d"` — BEFORE the
30-day ceiling closes it. `docs/kpi/SCORECARD.md`'s `## Canary health` section renders the same
three numbers from a pure read over `docs/interventions/*.md`.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Fixture canary within the lookahead window (zero observed runs) renders the alarm; a fresh
  canary renders a zero projected count with no false alarm; zero open canaries render silent.
  *(Evidence: `SKIP_MCP_TEST.md` — `test_efficacy_eval.py` staleness suite + `test_kpi_scorecard.py`
  `TestCanaryHealthSummary`, green.)* <!-- verification-only -->
- [x] A live render over this repo's real `docs/interventions/*.md` produced a real `## Canary
  health` line (`28 canaries open, oldest 7d, 0 will no-data-close within 7d` as of 2026-07-12 —
  the current population is fresh, not yet in the lookahead window). *(Evidence:
  `docs/kpi/SCORECARD.md`, this commit.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phase 1 (shares `efficacy-eval.py`'s canary-evaluation loop; no hard code
dependency, sequenced for review clarity).

**Files likely modified:** `user/scripts/efficacy-eval.py`, `user/scripts/test_efficacy_eval.py`,
`user/scripts/kpi-scorecard.py`, `user/scripts/test_kpi_scorecard.py`, `docs/kpi/SCORECARD.md`.

**Testing Strategy:** `efficacy-eval.py`: existing `_add_canary`/`_run_canary` fixture helpers,
computing `opened` relative to real wall-clock `datetime.date.today()` (matching the production
`today` derivation, so the relative day-count assertions are deterministic regardless of actual
test-run date — the same convention the pre-existing `_CANARY_OPENED_PAST` fixture documents).
`kpi-scorecard.py`: hand-written minimal intervention-record fixtures (mirrors the existing
`_write_intervention` helper) + `LAZY_STATE_DIR` telemetry fixtures for the observed-run leg.

**Integration Notes for Next Phase:** Phase 3's `intervention-records` source selectors read the
SAME `docs/interventions/*.md` tree this phase's `_canary_health_summary` reads — both are
pure-read, no shared mutable state, safe to add independently.

---

### Phase 3: Vantage + freshness

**Phase kind:** integration

**Scope:** Registry `vantage` field (D3) + the `WRONG-VANTAGE` status classification; the three
new `intervention-records`-sourced KPI selectors (`conclusive-verdict-count`,
`confounded-verdict-ratio`, `canary-closure-latency-p50-days`) and their registry rows; the
scorecard-regeneration-point decision (D4) — code-side readiness landed here, orchestrator-prose
wiring reported as a cross-lane seam (see the completion report; NOT landed in this phase).

**Deliverables:**
- [x] `_VANTAGE_HOSTS` closed enum (`workstation`/`cloud`/`any`) + `lint_row`'s `vantage`
  validation (object shape, non-empty `repo`, closed `host` enum).
- [x] `_vantage_match(row, repo_root, host)` + `row_status(row, value, *, repo_root=None,
  host=None)` — a `None` value renders `WRONG-VANTAGE` instead of `NO-DATA` when the current
  (repo, host) cannot observe the row's declared vantage; omitting `repo_root`/`host` (every
  pre-D3 caller, `--lint`) is byte-identical to before (no vantage dimension is ever checked
  unless the caller supplies a value for it).
- [x] `--host {workstation,cloud}` CLI flag (`--repo-root`-shaped; default `$LAZY_HOST_KIND` env,
  else `workstation`) threaded through `_cmd_render` → `render_scorecard`.
- [x] `_SOURCES["intervention-records"]` (`conclusive-verdict-count`,
  `confounded-verdict-ratio`, `canary-closure-latency-p50-days`) + `_sel_intervention_records`
  dispatcher wired into `compute_reading`. Each selector is a pure read over
  `docs/interventions/*.md` frontmatter + `## Review <date>` / `## Canary <date>` body sections —
  never a re-implementation of the evaluator's own arithmetic.
- [x] Three new `docs/kpi/registry.json` rows (`efficacy-verdicts-produced`,
  `confounded-verdict-ratio`, `canary-closure-latency-p50`), all honest `provenance: pending` /
  `band: null` — flipped from the SPEC's fenced-json drafts to full lint-clean rows now that
  `kpi-scorecard.py` registers the selectors.
- [x] Tests: `TestVantageLint`, `TestVantageStatus` (incl. the omitted-args backward-compat
  case), `TestConclusiveVerdictCount`, `TestConfoundedVerdictRatio`, `TestCanaryClosureLatency`.

**Minimum Verifiable Behavior:** A registry row declaring `vantage: {repo: "some-other-repo",
host: "any"}` with a `None` reading renders `WRONG-VANTAGE` (not `NO-DATA`) when rendered against
a DIFFERENT repo; a fixture with two `closed-clean` canary closures (5 and 10 opened-to-closed
days) renders `canary-closure-latency-p50-days == 7.5`, excluding any `closed-clean (no-data)`
fixture in the same window.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Vantage classification + all three new selectors verified against hand-written fixtures
  (incl. window exclusion, no-data honesty, confounded-ratio arithmetic, tripped-vs-closed-clean
  closure-date resolution). *(Evidence: `SKIP_MCP_TEST.md` — `test_kpi_scorecard.py`'s
  vantage/intervention-records suites, green.)* <!-- verification-only -->
- [x] `kpi-scorecard.py --lint --repo-root .` exits 0 on the real registry (11 rows incl. the 3
  new ones); a live `--stdout` double-render is byte-identical. *(Evidence: this session's
  terminal output, reproducible via the same two commands.)* <!-- verification-only -->
- **DEFERRED (cross-lane, not a completion blocker for the in-lane work above):** the D4
  scorecard-regeneration-point orchestrator-prose wiring
  (`user/skills/lazy-batch/SKILL.md` §1c.6 + the `lazy-batch-cloud` Differences table) is a
  SKILLS-lane edit this feature's file ownership excludes — named exactly in the completion
  report for the owning lane to apply. The code side (`kpi-scorecard.py --repo-root <path>`) is
  unconditionally ready to be invoked from wherever that wiring lands.

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface.

**Prerequisites:** Phases 1–2 (the `intervention-records` selectors read the same tree Phase
2's canary-health summary reads; no hard code dependency).

**Files likely modified:** `user/scripts/kpi-scorecard.py`, `user/scripts/test_kpi_scorecard.py`,
`docs/kpi/registry.json`, `docs/kpi/SCORECARD.md`, `docs/interventions/CLAUDE.md`.

**Testing Strategy:** Hand-written minimal intervention-record fixtures (mirrors the existing
`_write_intervention`/`_canary_row` precedent) for the three new selectors; `tmp_path`-scoped
registry-row fixtures for vantage lint/status; a real-registry `--lint` + byte-stable
double-render smoke as the live integration check.

**Integration Notes for Next Phase:** None — this is the feature's final phase. The two
cross-lane seams (capture-side sub-signal vocabulary in `lazy_core.py`; the D4 orchestrator-prose
regen wiring) are the feature's only open threads, both named in the completion report.
