# Implementation Phases — Harness-Change Canary + Rollback

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this feature is stdlib-only Python scripts (`lazy_core.py`,
`efficacy-eval.py`) plus orchestrator skill-prose edits. It has no Tauri/MCP app surface, no
audio path, and no UI state — the entire deliverable is outside MCP reach (the "build-tooling /
non-app-integrated script" untestable class per `docs/features/mcp-testing/SPEC.md`). Every
behavior is runtime-observable via a runnable CLI command over on-disk fixtures and is validated
by the `test_lazy_core.py` / `test_efficacy_eval.py` fixture suites + the in-file `--test`
harnesses, not by `/mcp-test`.

## Validated Assumptions

Per the Step-2.7 Runtime Assumption Validation Gate — every load-bearing assumption here is
**code-provable** (pure stdlib logic over on-disk ledger/record/manifest files), so the gate is
satisfied by fixture tests, not a live runtime spike. Ground truth confirmed by reading the real
code during planning:

- **The intervention-record serializer accepts a `canary:` sub-map with no schema change.**
  `lazy_core._render_intervention_record` (SPEC ~L15173) walks `_INTERVENTION_FIELD_ORDER`
  (L15164) then appends **any unknown key in insertion order** — so a nested `canary:` map
  round-trips through `yaml.safe_dump` / `parse_sentinel` type-preserved. Registration is a
  post-step write on `meta`, not a serializer edit. [VERIFY: `grep -n "for key, value in meta.items()" user/scripts/lazy_core.py`]
- **Capture site is `lazy_core.record_intervention` (L15196).** It already freezes the baseline,
  sets `commit_set` (currently `= shipped_commit`, with an in-code note to enrich from the
  provenance mapping now that `code-doc-provenance-linkage` has shipped), and writes atomically via
  `_atomic_write`. The canary post-step hangs off this function's tail before the `_atomic_write`.
  [VERIFY: `grep -n "def record_intervention" user/scripts/lazy_core.py`]
- **The evaluator already accrues per-run windows off telemetry `run_id`s.** `efficacy-eval.py`
  `main()` (L489) builds `run_ids` from `lazy_core.read_intervention_telemetry`; `_post_runs` /
  `_review_record` (L388) slice post-ship windows. The `--canary` mode reuses this run-identity
  machinery — no new run-identity field is invented. [VERIFY: `grep -n "read_intervention_telemetry\|_post_runs" user/scripts/efficacy-eval.py`]
- **The enqueue consequence has a shipped, guard-safe pattern.** `_enqueue_reconsideration`
  (L314) shells `lazy-state.py --enqueue-adhoc --type bug --id … --brief …` with
  `env={**os.environ, "LAZY_ORCHESTRATOR": "1"}` (hermetic against an ambient cycle marker). The
  canary trip copies this verbatim with id `canary-revert-<intervention_id>`. [VERIFY: `grep -n "LAZY_ORCHESTRATOR" user/scripts/efficacy-eval.py`]
- **`docs/gate/control-surfaces.json` does NOT exist yet** (ships with `anti-overfit-design-gate`,
  still Draft). Phase 1 ships a canary-owned fallback surface-glob constant in `lazy_core.py` and
  documents that the manifest takes precedence when present. [VERIFY: `test ! -e docs/gate/control-surfaces.json && echo absent`]
- **Incident sources + surface mapping already have readers.** `incident-scan.py` exposes
  `read_hook_events` (L140), `read_legacy_crumbs` (L163), `collect_clusters` (L206), and
  `_first_token` (deny→hook/op signature). Phase 2's attribution REUSES these readers rather than
  re-parsing the ledger. [VERIFY: `grep -n "def read_hook_events\|def collect_clusters" user/scripts/incident-scan.py`]

## Touchpoint Audit (verified — planning-time, read-only)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `record_intervention` (L15196), `_render_intervention_record`/`_INTERVENTION_FIELD_ORDER` (L15164), `_atomic_write` (L105), `claude_state_dir` (L9845), `read_deny_ledger`, `_DENY_LEDGER_FILENAME` (L7070), `_INTERVENTIONS_DIRNAME` (L15047), `parse_intervention_hypothesis` (L15061) | refactor | Add canary post-step INSIDE `record_intervention`; add `_canary_control_surfaces()` fallback-glob constant + manifest-precedence reader, `_compute_pair_scope(touched, manifest)` over the parity manifest, and the touched-file derivation from the provenance commit-set. Reuse `_atomic_write` + the unknown-key-append serializer — do NOT edit `_INTERVENTION_FIELD_ORDER`. |
| `user/scripts/efficacy-eval.py` | yes | `main` (L489), `_review_record` (L388), `_enqueue_reconsideration` (L314), `_enumerate_records`, `_write_record`, `_parse_record` | refactor | Add a `--canary` subcommand/branch reusing `_enumerate_records` (filter `canary.status: open`), the telemetry `run_ids` accrual, `_write_record`, and the `_enqueue_reconsideration` subprocess/env pattern. Keep the two cadences behind a clean `--canary` boundary. |
| `user/scripts/incident-scan.py` | yes | `read_hook_events` (L140), `read_legacy_crumbs` (L163), `collect_clusters` (L206), `_first_token` (L187) | reuse | Phase 2 imports/reuses these readers + `lazy_core.read_deny_ledger` for the incident-source read; cluster surfaces are the preferred attribution input, raw deny/breadcrumb the fallback. Do NOT duplicate ledger parsing. |
| `user/scripts/lazy-parity-manifest.json` | yes | `{mechanic_sets, pairs}`; `pairs[i].canonical` / `pairs[i].derived` file paths (5 pairs) | read | `_compute_pair_scope` reads `pairs[].canonical`/`.derived`; a touched file matching either half yields BOTH halves in `pair_scope`. Also fold in the root `CLAUDE.md` pairs-table entries not in the manifest as data (Phase 1). |
| `docs/gate/control-surfaces.json` | **NO (absent)** | — (ships with `anti-overfit-design-gate`, Draft) | consume-if-present | Fallback glob constant in `lazy_core.py` mirrors the anti-overfit SPEC's initial set (`user/hooks/**`, `user/scripts/lazy-state.py`, `bug-state.py`, `lazy_core.py`, `lazy_guard.py`, `lazy_inject.py`, `lazy-parity-manifest.json`, `build-queue*.ps1`, `user/skills/lazy*/**`, `harden-harness/**`, gate-bearing components, hook registrations). Manifest takes precedence when the file appears. |
| `user/scripts/test_lazy_core.py` | yes | pytest suite | refactor | Add Phase 1 registration fixtures (scoped change registers canary + pair scope; non-scoped registers none; fallback-vs-manifest precedence). |
| `user/scripts/test_efficacy_eval.py` | yes | pytest suite | refactor | Add Phase 2/3 canary fixtures (band trip, incident trip, no-trip on unattributable, once-ever guard, no-data close). |
| `user/skills/lazy-batch/SKILL.md` | yes | §1c.6 flush block (L461–470: `incident-scan.py` L468, `efficacy-eval.py --json` L470) | refactor | Add `efficacy-eval.py --canary --repo-root . --json` alongside the existing flush invocations (Phase 3). |
| `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` | yes | §1c.6 flush (coupled pair) | refactor | Mirror the canary flush line (Phase 3). |
| `user/skills/lazy-batch-parallel/SKILL.md` | yes | end-of-run flush | refactor | Mirror the canary flush line (Phase 3). |
| `user/scripts/kpi-scorecard.py` | yes | `_SOURCES` registry (L64), `_sel_telemetry` (L455) | refactor | Register the `telemetry-ledger` / `canary-trip-precision` selector so the drafted registry row lints clean; wire the computation (Phase 4). |
| `docs/kpi/registry.json` | yes | KPI rows | refactor | Add the `canary-trip-precision` row (Phase 4; `provenance: pending` / `band: null`). |
| `user/skills/lazy-batch-retro/SKILL.md` | yes | Step 6e cites `efficacy-eval.py --dry-run` | refactor | Cite canary outcomes alongside efficacy verdicts (Phase 4). |
| `docs/interventions/CLAUDE.md` | yes | record schema + authoring surface | refactor | Document the `canary:` sub-map schema + lifecycle (Phase 4 surfacing). |

**Drift correction (Step D):** the SPEC's `commit_set` note ("enriched … when
code-doc-provenance-linkage ships") is now actionable — that dep is **Complete** on this branch, so
Phase 1 derives the touched-file set from the provenance commit-set rather than the single capture
commit. No genuine design fork surfaced; every path is verified-exists or the one explicitly-absent
`control-surfaces.json` (handled by the SPEC-locked fallback constant). No `NEEDS_INPUT.md`.

## Cross-feature Integration Notes

- **`intervention-efficacy-tracking` (kind=hard, Complete — has PHASES.md):** the canary IS a
  sub-map on this feature's record and a mode of its evaluator. Locked contracts consumed:
  `lazy_core.record_intervention` (the ship-time capture write, L15196) is the canary-registration
  host; `docs/interventions/<id>.md` is the record residency (atomic writes, archive survival
  inherited); `_render_intervention_record`'s unknown-key-append serializer accommodates `canary:`
  with no field-order edit; `efficacy-eval.py` (`main`/`_review_record`/`_enqueue_reconsideration`)
  is the watcher's home and supplies the run-window accrual + guard-safe enqueue pattern. Consumed
  by **all four phases**. Capture parity across both completion handlers is inherited (audited by
  `lazy_parity_audit.py`).
- **`code-doc-provenance-linkage` (kind=hard, Complete — has PHASES.md):** supplies the
  change→commit-set mapping (per-cycle commit-bracket ledger → touched-file derivation). Phase 1's
  registration computes `commit_set` and the touched-file set from this mapping (enriching the
  record's current single-commit `commit_set`), then intersects the touched set with the
  control-surface manifest to decide whether to arm. Consumed by **Phase 1**.
- **`incident-auto-capture` (kind=soft, Complete — has PHASES.md):** `incident-scan.py`'s readers
  (`read_hook_events`, `read_legacy_crumbs`, `collect_clusters`, `_first_token`) are reused as the
  fresh-incident source + surface-signature machinery. Its clustered incidents are the **preferred**
  attribution input; raw deny-ledger/breadcrumb counting is the v1 fallback (same surface-based
  attribution rule applied to cluster surfaces). Consumed by **Phase 2**.

---

### Phase 1: Registration + revertibility metadata

**Scope:** At intervention capture, if the shipped change's touched-file set intersects the
control-surface manifest, write a `canary:` sub-map onto the record carrying the window config,
surfaces, commit set, computed coupled-pair scope, and a degraded-revert note. Non-scoped changes
register no canary (byte-identical to today).

**Deliverables:**
- [x] `_canary_control_surfaces(repo_root)` in `lazy_core.py` — reads `docs/gate/control-surfaces.json`
      when present, else returns the canary-owned fallback glob constant (mirrors the anti-overfit
      SPEC's initial set); documents manifest-precedence.
- [x] Touched-file derivation from the provenance change→commit-set mapping (reuse the
      `code-doc-provenance-linkage` commit-bracket → touched-file path), and manifest intersection
      (glob-test) deciding whether to arm.
- [x] `_compute_pair_scope(touched_files, manifest_path)` over `lazy-parity-manifest.json`
      `pairs[].canonical`/`.derived` + the root `CLAUDE.md` pairs-table entries folded in as data —
      a touched file in either half yields BOTH halves.
- [x] Canary post-step inside `record_intervention`: on a scope hit, set
      `meta["canary"] = {opened, window_runs, surfaces, commit_set, pair_scope, degraded_revert_note, status: "open"}`
      before the existing `_atomic_write`; per-record overrides read from the `## Intervention
      Hypothesis` block via the existing `parse_intervention_hypothesis` precedence.
- [x] Degraded-revert-note plumbing: a static note when the change is known revert-unsafe (migrated
      on-disk state/schema); no `git revert` dry-run machinery in v1.
- [x] Tests (`test_lazy_core.py`): control-surface fixture change registers `canary:` with correct
      `pair_scope`; a non-scoped change registers NO canary; fallback-vs-present-manifest precedence;
      parity audit stays green.

**Implementation Notes (2026-07-04, cloud /execute-plan part 1):**
- Work completed: Phase 1 shipped in `user/scripts/lazy_core.py` — `_canary_control_surfaces`
  (+ `_CANARY_CONTROL_SURFACES_FALLBACK` glob constant + `_CANARY_CONTROL_SURFACES_FILE`),
  `_canary_glob_to_re` (segment-aware `**`/`*`/`?` matcher), `_canary_touched_files`
  (reuses `_git_capture_lines`, never re-shells), `_canary_intersects`, `_canary_load_parity_pairs`
  + `_CANARY_CLAUDE_MD_PAIRS` + `_compute_pair_scope`, `_maybe_arm_canary`, and the
  `record_intervention` post-step (fail-open, before `_atomic_write`). `parse_intervention_hypothesis`
  now surfaces `canary_window_runs` (int), `canary_degraded_revert_note` (str), `canary_revert_unsafe`
  (bool). Constants block: `CANARY_WINDOW_RUNS_DEFAULT = 10`, `CANARY_WINDOW_DAYS_CEILING = 30`.
- Frozen canary key set (Phase-2 contract): `opened, window_runs, surfaces, commit_set, pair_scope,
  degraded_revert_note, status`. `window_days_ceiling` is a module CONSTANT (not a sub-map key) so the
  frozen key set stays exactly the seven Integration-Notes names — Phase 2 reads the constant directly.
- `surfaces` = the matched touched files (repo-relative POSIX), the D3 attribution identity set.
- Touched-file derivation order: `derive_touched_from_brackets` → `derive_touched_from_grep` →
  single `shipped_commit` last resort; empty derivation ⇒ no canary (non-scoped byte-identical).
- Tests: 8 new `test_lazy_core.py` cases (all `_TESTS`-registered). Parity audit green; both in-file
  `--test` smoke harnesses green. NOTE: ~21 ambient `apply_pseudo`/`__mark_complete__` test failures
  observed in this cloud run are pre-existing (the live cycle-active marker makes `refuse_if_cycle_active`
  fire inside those tests) — a base-vs-branch diff under `LAZY_ORCHESTRATOR=1` confirmed ZERO new
  failures from this change.
- Files modified: `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_core.py --test` (+ the added
`test_lazy_core.py` cases) run green, AND a fixture capture of a control-surface change writes a
record whose `canary.status == open` with both pair halves in `pair_scope`, while a non-scoped
fixture writes a record with no `canary` key.

**Runtime Verification** *(checked by fixture test / manual CLI run — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Run `python3 -m pytest user/scripts/test_lazy_core.py -k canary` → registration + pair-scope + precedence fixtures pass.
- [ ] <!-- verification-only --> Run `python3 user/scripts/lazy_parity_audit.py --repo-root .` → exit 0 (capture-site parity intact after the post-step).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase beyond the
CLI/fixture assertions above (stdlib record writer; no MCP-reachable surface).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — canary post-step in `record_intervention`; `_canary_control_surfaces`, `_compute_pair_scope`, touched-file derivation helpers.
- `user/scripts/test_lazy_core.py` — registration fixtures.

**Testing Strategy:** Fixture-drive `record_intervention` with a synthetic provenance commit-set and
a synthetic manifest (present and absent). Assert record `canary` presence/absence, `surfaces`,
`pair_scope` (both halves), and honest degraded-note. Assert parity audit green.

**Integration Notes for Next Phase:**
- The `canary:` sub-map keys (`opened`, `window_runs`, `surfaces`, `commit_set`, `pair_scope`,
  `degraded_revert_note`, `status`) are the exact fields Phase 2's watcher reads/writes — freeze the
  key names here.
- `surfaces:` is the resolved file-identity set the watcher's D3 attribution matches incident
  surfaces against; keep it as repo-relative POSIX paths (the provenance-index path convention).
- `status: open` is the watcher's wake predicate; Phase 2 transitions it to `closed-clean` /
  `tripped` and never re-opens.

---

### Phase 2: Watcher — windows, attribution, tripwire

**Scope:** `efficacy-eval.py --canary` — a run-boundary mode that accrues each open canary's window,
applies the D2 bands and D3 surface-based attribution over fixture deny-ledger/breadcrumb/cluster
inputs, and detects trips. Honest no-data handling; never blocks a run.

**Deliverables:**
- [x] `--canary` branch in `efficacy-eval.py` `main()` reusing `_enumerate_records` (filtered to
      `canary.status: open`), the telemetry `run_ids` accrual, and `_write_record`.
- [x] D2 window accrual: next 10 completed runs after ship, 30-day wall-clock ceiling; defaults in
      ONE constants block, per-record overridable via the hypothesis block.
- [x] D2 tripwire: targeted-signal regression past the KPI band (else ≥25% relative with ≥3 post-ship
      occurrences) OR ≥2 attributable fresh incidents.
- [x] D3 attribution: incident attributes iff its timestamp ∈ window AND its emitting surface ∈
      `canary.surfaces`; unknown/unresolvable surfaces NEVER attribute; a shared surface counts
      against ALL matching open canaries. Reuse `incident-scan.py` readers + `_first_token`
      surface-signature; prefer clustered incidents, fall back to raw deny/breadcrumb.
- [x] Honest degradation: unreadable ledger fixture → window accrues nothing this run, never errors;
      a window closing with zero observable runs is stampable `closed-clean (no-data)`.
- [x] Tests (`test_efficacy_eval.py`): trip on band regression; trip on 2 attributable incidents;
      NO trip on 2 unattributable (unknown-surface) incidents; unattributable entries listed-but-not-counted; no-data window handling.

**Implementation Notes (2026-07-04, cloud /execute-plan part 2 — WU-4/WU-5):**
- Watcher lives behind a clean `--canary` boundary in `user/scripts/efficacy-eval.py` (separate
  helpers, separate tests): `run_canary` → `_canary_open_records` (wake predicate: `canary.status:
  open` only), `_canary_evaluate_record` (accrual + trip + no-data), `_canary_band_trip` (D2 band),
  `_canary_gather_incidents` + `_canary_entry_surface` + `_canary_attribute` (D3), and the honest
  no-data close `_canary_stamp_no_data`. Constants block: `CANARY_REGRESSION_BAND_PCT = 25`,
  `CANARY_MIN_POST_OCCURRENCES = 3`, `CANARY_INCIDENT_TRIP_COUNT = 2` (window defaults reused from
  `lazy_core.CANARY_WINDOW_RUNS_DEFAULT`/`CANARY_WINDOW_DAYS_CEILING`).
- Accrual reuses `_post_runs(meta, run_ids)` (post-ship runs off the frozen `baseline.last_run_id`)
  and takes `[:window_runs]`; maturity = run-count OR 30-day ceiling. No-data close fires only when
  matured AND zero observable window runs AND no trip.
- D3 attribution reuses the `incident-scan.py` readers (`read_hook_events`, `read_legacy_crumbs`) via
  importlib (fail-open to deny-ledger-only on import failure) + `lazy_core.read_deny_ledger`. Surface
  resolution: explicit `surface`/`source_file` fields, else a hook name → `user/hooks/<name>`;
  unresolvable → None → NEVER attributes (conservative). In-window = incident ts ≥ the canary's
  `opened` epoch; a shared surface attributes independently to every matching open canary.
- The whole `--canary` branch is wrapped fail-open in `main()` — a watcher exception degrades to an
  `error` payload, exit 0, NEVER blocks the run.
- Fixture note: ~19 ambient `test_lazy_core.py::test_apply_pseudo_*`/`test_mark_*` failures in this
  cloud run are PRE-EXISTING (the live cycle-active marker fires `refuse_if_cycle_active` inside
  those tests). Proven ambient: `lazy_core.py`/`lazy-state.py`/`bug-state.py` are byte-identical to
  the run base (empty diff), the same subset fails on the base test file, and this change touches
  ZERO files imported by `test_lazy_core.py`. New failures from this change: zero.
- Files modified: `user/scripts/efficacy-eval.py`, `user/scripts/test_efficacy_eval.py`.

**Minimum Verifiable Behavior:** `python3 user/scripts/efficacy-eval.py --canary --repo-root <fixture> --json`
over a fixture with a regressing signal emits JSON reporting a trip with the band numbers; over a
fixture with 2 same-surface breadcrumbs it reports a trip; over 2 unrelated-surface breadcrumbs it
reports no trip with the entries listed as unattributed.

**Runtime Verification** *(checked by fixture test / manual CLI run — NOT by the implementation agent):*
- [x] <!-- verification-only --> `python3 -m pytest user/scripts/test_efficacy_eval.py -k canary` → band-trip, incident-trip, no-trip-unattributable, and no-data fixtures pass. (18 canary fixtures green.)
- [x] <!-- verification-only --> `python3 user/scripts/efficacy-eval.py --canary --repo-root <fixture> --json` returns exit 0 on an unreadable-ledger fixture (never blocks the run; window notes no-data). (`test_canary_absent_telemetry_accrues_nothing_exit_zero`.)

**MCP Integration Test Assertions:** N/A — stdlib evaluator over on-disk ledger/record fixtures; no
MCP-reachable surface. All observable behavior is the CLI JSON asserted above.

**Prerequisites:**
- Phase 1: the `canary:` sub-map (`surfaces`, `window_runs`, `commit_set`, `status: open`) must
  exist on records for the watcher to accrue and attribute against.

**Files likely modified:**
- `user/scripts/efficacy-eval.py` — `--canary` mode, window/band/attribution logic, no-data handling.
- `user/scripts/test_efficacy_eval.py` — canary window/attribution fixtures.

**Testing Strategy:** Build fixture `docs/interventions/*.md` records with `canary.status: open`, a
fixture telemetry ledger (regressing / steady signal), and fixture deny-ledger/hook-event files with
matching + unrelated surfaces. Assert trip/no-trip verdicts, attribution counts, unknown-surface
exclusion, and byte-inert behavior on the read-only/no-data paths.

**Integration Notes for Next Phase:**
- The watcher's trip detection returns the trip reason (band numbers or the verbatim
  ledger/breadcrumb lines) and the attributed-incident list — Phase 3 serializes exactly these into
  `EVIDENCE.md`.
- Keep the `--canary` write surface limited to `canary.*` record fields — Phase 3 adds the enqueue +
  `EVIDENCE.md` + the `status: tripped` stamp; the watcher stays the SOLE writer of `canary.*`.
- The attribution result already knows `pair_scope` (from the record) — pass it through so Phase 3's
  evidence carries the parity-audit instruction without recomputing.

---

### Phase 3: Consequences — flag-and-enqueue

**Scope:** On a trip, enqueue an evidence-bearing `canary-revert-<id>` bug stub via the existing
enqueue path, write `EVIDENCE.md` into the seeded bug dir, stamp `canary.status: tripped` (once
ever), emit a notify line, and wire the `--canary` invocation into the end-of-run flush of the
feature orchestrators (mirrored across the coupled skill pairs). Flag-and-enqueue ONLY — no revert,
no writes outside record/evidence/queue.

**Deliverables:**
- [x] Trip consequence in `efficacy-eval.py --canary`: shell `lazy-state.py --enqueue-adhoc --type
      bug --id canary-revert-<intervention_id> --brief …` with the `LAZY_ORCHESTRATOR=1` env (copy
      the `_enqueue_reconsideration` pattern) — NEVER a `queue.json` hand-edit.
- [x] `EVIDENCE.md` written into the seeded bug dir carrying: trip reason (band numbers or verbatim
      incident lines), full `commit_set`, linked docs (SPEC / GATE_VERDICT / record path),
      `pair_scope` with the "revert must cover the pair and end with `lazy_parity_audit.py
      --repo-root .` green" instruction, and any `degraded_revert_note`.
- [x] Once-ever recurrence guard: `canary.status: tripped` + the enqueued id stamped on the record;
      repeated watcher runs produce exactly one revert item (mirror the two-layer guard shape of
      `_enqueue_reconsideration` — dir-exists check + stamp).
- [x] Notify line in the `--canary` JSON (`"notify": "canary tripped: <id>"`) for the orchestrator
      to surface, consistent with harden-harness spin-offs.
- [x] End-of-run flush wiring: add `efficacy-eval.py --canary --repo-root . --json` alongside the
      existing `incident-scan.py` / `efficacy-eval.py` invocations at §1c.6, mirrored in
      `lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, and
      `lazy-batch-parallel/SKILL.md`; NON-BLOCKING (a non-zero exit prints one warning, run-end
      continues). Stage `docs/interventions/` + any `docs/bugs/canary-revert-*` seed in the run-end commit.
- [x] Tests (`test_efficacy_eval.py`): end-to-end fixture — repeated watcher runs over a tripped
      canary produce exactly ONE `canary-revert-<id>` item with complete evidence including
      pair scope; no commit reverts; record stamped `tripped`.

**Implementation Notes (2026-07-04, cloud /execute-plan part 2 — WU-6/WU-7):**
- Trip consequence (`_canary_fire_consequence`) copies the `_enqueue_reconsideration` subprocess +
  `env={**os.environ, "LAZY_ORCHESTRATOR": "1"}` pattern verbatim with id `canary-revert-<id>`;
  writes `EVIDENCE.md` into the enqueue-seeded bug dir via `lazy_core._atomic_write`
  (`_canary_evidence_text`: trip reason verbatim, band numbers, attributed incident lines, full
  `commit_set`, `pair_scope` + the `lazy_parity_audit.py --repo-root .` instruction, degraded note,
  linked docs). NEVER a `queue.json` hand-edit; no revert; writes confined to record/evidence/queue.
- Once-ever guard mirrors `_enqueue_reconsideration`'s two layers: layer 2 = the record-level
  `canary_revert_enqueued` stamp (top-level meta field, like `reconsideration_enqueued`), layer 1 =
  an open/archived `docs/bugs/canary-revert-<id>/` dir. Primary belt: `canary.status: tripped` drops
  the record out of `_canary_open_records`, so the next run never re-evaluates it. Enqueue FAILURE
  does not stamp (retries next run).
- WU-7 flush wiring: `efficacy-eval.py --canary --repo-root . --json` added at §1c.6 alongside the
  incident-scan / efficacy-eval invocations in `lazy-batch` AND `lazy-batch-cloud` (coupled pair —
  diffed; a MIRRORED row added to the cloud "Differences" table), and by reference into
  `lazy-batch-parallel`'s main-root flush. NON-BLOCKING. Deliberately NOT added to `lazy-bug-batch`
  (feature-side flush — justified divergence). Gates green: `project-skills.py` (86 skills, no
  errors), `lint-skills.py --check-projected --check-capabilities` (clean; the one ambient
  `write-plan-cognito` planner-resolution note pre-dates this change), `lazy_parity_audit.py
  --repo-root .` exit 0.
- Files modified: `user/scripts/efficacy-eval.py`, `user/scripts/test_efficacy_eval.py`,
  `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`,
  `user/skills/lazy-batch-parallel/SKILL.md`.

**Minimum Verifiable Behavior:** over a tripped-canary fixture, running the `--canary` watcher TWICE
produces exactly one `docs/bugs/canary-revert-<id>/` seed with an `EVIDENCE.md` containing the commit
set + both pair halves + the parity-audit instruction, and the record shows `canary.status: tripped`;
`git log` shows no revert commits.

**Runtime Verification** *(checked by fixture test / manual CLI run — NOT by the implementation agent):*
- [x] <!-- verification-only --> `python3 -m pytest user/scripts/test_efficacy_eval.py -k "canary and enqueue"` → once-ever + evidence-completeness (incl. pair scope) fixtures pass. (Covered by `test_canary_trip_enqueues_revert_exactly_once` + `test_canary_evidence_is_complete`.)
- [x] <!-- verification-only --> Two consecutive `efficacy-eval.py --canary` runs over a tripped fixture yield exactly one `canary-revert-<id>` bug dir (idempotent guard observed). (`test_canary_trip_enqueues_revert_exactly_once`.)
- [x] <!-- verification-only --> Coupled-pair flush mirror audited: `efficacy-eval.py --canary` appears in `lazy-batch`, `lazy-batch-cloud`, and `lazy-batch-parallel` §1c.6 blocks (grep check). (Grep confirmed; absent from `lazy-bug-batch`.)

**MCP Integration Test Assertions:** N/A — the enqueue is a subprocess to the existing sanctioned
CLI path; observable behavior is the seeded bug dir + `EVIDENCE.md` + record stamp asserted above. No
MCP-reachable surface.

**Prerequisites:**
- Phase 2: the watcher's trip detection + the trip reason / attributed-incident payload.

**Files likely modified:**
- `user/scripts/efficacy-eval.py` — trip enqueue, `EVIDENCE.md` writer, once-ever guard, notify line.
- `user/scripts/test_efficacy_eval.py` — end-to-end trip fixtures.
- `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `user/skills/lazy-batch-parallel/SKILL.md` — §1c.6 flush wiring.

**Testing Strategy:** Fixture a tripped canary; run the watcher repeatedly; assert exactly one
enqueue subprocess effect (seed dir + queue head), full `EVIDENCE.md` content, the `tripped` stamp,
and no out-of-scope writes. Assert the flush lines are present in all three orchestrators.

**Coupled-pair discipline:** the §1c.6 flush edit touches the `lazy-batch` ↔ `lazy-batch-cloud`
coupled pair — mirror the canary line in both and diff them; the `lazy-batch-parallel` addition
composes `lazy-batch`'s flush by reference. Do NOT add the canary flush to `lazy-bug-batch` (the
feature-side flush is not present there — it is a justified divergence).

**Completion (gate-owned):** the `__mark_complete__` gate flips SPEC.md/PHASES.md `**Status:**` and
writes `COMPLETED.md` once this feature's validation passes on a workstation pass — never authored as
a checkbox here.

**Integration Notes for Next Phase:**
- The `canary.status: tripped` / `closed-clean` stamps are the inputs Phase 4's retro citation +
  handoff read; freeze their vocabulary here.
- The notify line format is what Phase 4's retro surfacing quotes.

---

### Phase 4: Steady-state handoff + surfacing + KPI

**Scope:** Window-close stamps + the `## Canary <date>` record section; retro citation of canary
outcomes alongside efficacy verdicts; the canary system's own KPI row (trip precision) registered and
its signal computed. Monitoring drops back to normal cadence (the watcher simply stops waking for a
closed record).

**Deliverables:**
- [x] Window-close handling in `--canary`: on maturity with no trip, stamp `canary.status:
      closed-clean` (or `closed-clean (no-data)`); a tripped canary keeps `tripped` + the enqueued id.
      Append a `## Canary <date>` section to the record body summarizing runs observed, signal
      movement, and incidents attributed (none/list).
- [x] Handoff invariants: a clean canary does NOT pre-judge the efficacy verdict; a tripped canary
      does NOT skip it; the watcher stops waking a `closed-clean`/`tripped` record.
- [x] `/lazy-batch-retro` Step 6e cites canary outcomes (`--canary --dry-run`) alongside the efficacy
      verdict citations.
- [x] KPI: register the `telemetry-ledger` / `canary-trip-precision` selector in `kpi-scorecard.py`
      `_SOURCES` (+ `_sel_telemetry` computation: trips whose `canary-revert-<id>` item was NOT
      closed-as-noise, over all trips in the window); add the `canary-trip-precision` row to
      `docs/kpi/registry.json` (`provenance: pending`, `band: null` — honest NO-DATA until ≥5 trips).
- [x] Document the `canary:` sub-map schema + lifecycle in `docs/interventions/CLAUDE.md`.
- [x] Tests: retro citation renders from fixture records; the KPI row lints clean
      (`kpi-scorecard.py --lint`) and renders honest NO-DATA; window-close stamps
      (`closed-clean` / `closed-clean (no-data)`) asserted in `test_efficacy_eval.py`.

**Implementation Notes (2026-07-04, cloud /execute-plan part 3 — WU-8/WU-9/WU-10):**
- WU-8 (`efficacy-eval.py`): the `run_canary` loop's matured-no-trip branch now closes the window
  — `_canary_stamp_closed(rec, ev, today, status)` stamps `canary.status: closed-clean` (or
  `closed-clean (no-data)` when the matured window observed zero runs) and appends a
  `## Canary <date>` section (`_canary_close_section`: runs observed, signal movement via the band
  reason, incidents attributed none/list, the handoff line). The close writes ONLY `canary.*` + the
  appended section — never an efficacy verdict field. New payload key `closed_clean` alongside
  `closed_no_data`. Four WU-8 tests + four pre-existing Phase-2 tests EVOLVED (they asserted the
  intermediate "matured stays in monitoring" state that this D7 close deliberately supersedes).
- WU-9 (`kpi-scorecard.py` + `docs/kpi/registry.json`): `_sel_canary_trip_precision` (wired at the
  TOP of `_sel_telemetry`, before the ledger-presence gate — its data source is intervention records
  + revert-bug outcomes, not the ledger) computes precision = trips (in the 90d window) whose
  `canary-revert-<id>` bug is NOT `Won't-fix` (archive-aware), over all trips; honest NO-DATA (None)
  until the canary has tripped. Registry row added verbatim from the SPEC KPI Declaration
  (`provenance: pending`, `band: null`) — lints clean, renders NO-DATA. Six WU-9 tests + the seeded
  registry count assertion updated 6→7.
- WU-10 (`lazy-batch-retro/SKILL.md` + `docs/interventions/CLAUDE.md`): retro Step 6e gains a
  read-only `--canary --dry-run` canary-outcomes citation block + a `**Canary outcomes:**` bookend
  line; the interventions ledger doc gains a full `canary:` sub-map schema + open→tripped/closed
  lifecycle section. Gate: `project-skills.py` clean (94 components), `lint-skills.py
  --check-projected --check-capabilities` exit 0 (the lone `write-plan-cognito` planner-resolution
  note is ambient, pre-dates this lane), one byte-inert citation-shape test.
- NOTE: ~19–21 ambient `test_lazy_core.py::test_apply_pseudo_*`/`test_mark_*` failures in the full
  `user/scripts/` run are PRE-EXISTING (intra-suite test-ordering pollution + the live cloud
  cycle-active marker; pass in isolation). Proven ambient: `lazy_core.py` AND `test_lazy_core.py`
  are byte-identical to the part-3 start (`git diff 9126dad HEAD` empty); this lane touches ZERO
  files imported by those tests. Same ambient set the Phase 1/2 notes recorded.
- Files modified: `user/scripts/efficacy-eval.py`, `user/scripts/kpi-scorecard.py`,
  `docs/kpi/registry.json`, `user/scripts/test_efficacy_eval.py`,
  `user/scripts/test_kpi_scorecard.py`, `user/skills/lazy-batch-retro/SKILL.md`,
  `docs/interventions/CLAUDE.md`.

**Minimum Verifiable Behavior:** `python3 user/scripts/kpi-scorecard.py --lint` passes with the new
row, `--stdout` renders it as NO-DATA/PENDING-BASELINE, AND a matured-no-trip fixture stamps
`canary.status: closed-clean` with a `## Canary <date>` section appended to the record.

**Runtime Verification** *(checked by fixture test / manual CLI run — NOT by the implementation agent):*
- [x] <!-- verification-only --> `python3 user/scripts/kpi-scorecard.py --lint` → exit 0 with the `canary-trip-precision` row present; `--stdout` shows honest NO-DATA. (Verified: lint exit 0; live `--stdout` renders the row `NO-DATA`.)
- [x] <!-- verification-only --> `python3 -m pytest user/scripts/test_efficacy_eval.py -k "canary and close"` → `closed-clean` + `closed-clean (no-data)` + `## Canary` section fixtures pass. (22 canary fixtures green incl. the WU-8 close/section cases.)
- [x] <!-- verification-only --> `/lazy-batch-retro` Step 6e citation renders canary outcomes from a fixture record (dry-run, read-only). (`test_canary_dry_run_citation_shape_is_byte_inert`.)

**MCP Integration Test Assertions:** N/A — KPI lint/scorecard + record-stamp + retro prose are all
stdlib/doc surfaces; no MCP-reachable behavior.

**Prerequisites:**
- Phase 3: the `tripped` / enqueue stamps (trip-precision counts closes-as-noise against trips).
- Phase 2: window accrual/close detection.

**Files likely modified:**
- `user/scripts/efficacy-eval.py` — close stamps + `## Canary` section writer.
- `user/scripts/kpi-scorecard.py` — `_SOURCES` selector + trip-precision computation.
- `docs/kpi/registry.json` — the KPI row.
- `user/skills/lazy-batch-retro/SKILL.md` — canary citation at Step 6e.
- `docs/interventions/CLAUDE.md` — `canary:` schema + lifecycle docs.
- `user/scripts/test_efficacy_eval.py`, `user/scripts/test_kpi_scorecard.py` — close + KPI fixtures.

**Testing Strategy:** Fixture matured windows (trip + no-trip + no-data); assert stamps, `## Canary`
section content, retro citation rendering, and KPI lint/scorecard NO-DATA rendering. Confirm the KPI
row's `provenance: pending` / `band: null` (never a fabricated zero).

**Integration Notes for Next Phase:** terminal phase — validation is the fixture suites +
`kpi-scorecard.py --lint`; the feature is self-applying (its own control-surface edits get canaried),
so the `no-data` vs `closed-clean` distinction is what keeps "very good harness" and "broken watcher"
distinguishable in the retro.
