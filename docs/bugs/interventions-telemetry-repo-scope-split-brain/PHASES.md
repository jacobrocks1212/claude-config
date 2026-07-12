# Implementation Phases — Interventions/telemetry repo-scope split-brain

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config harness bug: the deliverables are Python state-script logic (`lazy_core.py` / `lazy-state.py` / `bug-state.py` / `efficacy-eval.py`), coupled orchestrator-skill prose, and intervention doc records. There is no Tauri/MCP app surface (the mcp-testing "build tooling / standalone, no app integration" untestable class). Validation is the in-file `--test` smoke harnesses + `test_lazy_core.py` (pytest).

## Root-cause trace (SEAM A — carried from SPEC, `traced`)

The symptom "zero efficacy verdicts ever produced" is served by:

```
efficacy-eval.py flush  (trio §1c.6, run with --repo-root <TARGET repo>)   lazy-batch/SKILL.md:476,478
  → lazy_core.set_active_repo_root(--repo-root)                             efficacy-eval.py:1101
  → lazy_core.read_intervention_telemetry(repo_root)                        efficacy-eval.py:1002,1145 → lazy_core.py:16316
      → read_telemetry_events()  keyed by repo_key(repo_root)              lazy_core.py:7924  (state-dir ledger)
      → <repo_root>/docs/telemetry/cloud/*.jsonl                            lazy_core.py:16329 (committed cloud segments)
  → records read from <repo_root>/docs/interventions/                       (claude-config only — TARGET repo has none)
  → drop_efficacy_breadcrumb()  (unconditional on non-dry-run)             efficacy-eval.py:1114 → lazy_core.py:15832
  → --run-end gate: efficacy_breadcrumb_present()                          lazy_core.py:15864 → lazy-state.py:11898+
```

The two data planes never intersect at one `repo_root`: **records** live at `<claude-config>/docs/interventions/` (follow the FIX); **telemetry** lives in the TARGET repo's `repo_key`-keyed state dir (follows the RUN). The flush runs `--repo-root <target>` → sees telemetry, no records → clean no-op → still drops the coverage-blind breadcrumb → the `--run-end` gate is discharged. The fix sites below are ALL on this path: `read_intervention_telemetry` (the merge), `drop_efficacy_breadcrumb` / `efficacy_breadcrumb_present` (the coverage attestation), the trio flush prose (the second scope), and the 6 frozen records.

## Locked scope decisions (from SPEC `## Decisions`)

- **D1 (v1 merge set):** a claude-config-rooted evaluation merges **the current run's target repo's keyed ledger + all committed cloud segments** (the SPEC's "simplest sound v1"). Record-side provenance (a record knowing which repos' runs count toward ITS window) is deferred — if implementation shows it is required, that surfaces as a NEEDS_INPUT at `/execute-plan`, not baked here.
- **D2 (second flush location):** the orchestrator runs an ADDITIONAL `efficacy-eval.py --repo-root <claude-config>` invocation in the run-end sequence; doc-write/commit ownership is unchanged.
- **D3 (re-baseline honesty):** every re-frozen baseline carries an explicit `provenance` note (`backfilled-from-merged-ledger`, date) — never silently equal to an original capture.

---

### Phase 1: Merged cross-repo intervention-telemetry read

**Scope:** Teach `lazy_core.read_intervention_telemetry` to additionally resolve and merge the telemetry ledger(s) of the run's ORIGINATING target repo(s), so a claude-config-rooted evaluation sees the workstation runs' events that append to the AlgoBooth-keyed dir. This is the foundational data-plane fix — every later phase's evaluation depends on it. Uses the run marker's recorded `repo_root` (`write_run_marker`, `lazy_core.py:10697`) + the deterministic `repo_key` (`lazy_core.py:7924`) to compose the sibling keyed state dir path and read its `lazy-telemetry.jsonl` via the existing `read_telemetry_events(paths=...)`. The existing dedup key `(run_id, ts, event, item_id)` (`lazy_core.py:16339`) already makes the union safe.

**Deliverables:**
- [x] `read_intervention_telemetry(repo_root)` resolves the set of originating target-repo keyed ledgers to merge (v1 per D1: the live/most-recent run marker's `repo_root` → `repo_key` → `~/.claude/state/<key>/lazy-telemetry.jsonl` and its rotated segments), in addition to the current-repo state-dir ledger + committed cloud segments it reads today.
- [x] Merge is a pure read, fail-open (an unreadable/absent sibling ledger contributes nothing, never raises — matching the existing `except OSError: pass` posture), deduped on the existing `(run_id, ts, event, item_id)` key, and chronologically sorted by `(run_id, ts)`.
- [x] Resolution is via `repo_key` + a RAW marker read (never `read_run_marker`, whose age gate deletes a stale marker as a side effect — the `fleet.py` / `write_run_checkpoint` precedent); no state-dir creation on the read path.
- [x] A claude-config-rooted read with NO originating target-repo marker degrades to today's behavior byte-identically (empty extra set).
- [x] Tests: `test_lazy_core.py` — a two-keyed-dir fixture (records-bearing repo + a separate telemetry-bearing keyed dir) asserts the merged read surfaces the target-repo events under a claude-config `repo_root`; dedup across overlapping cloud-segment + keyed-ledger events; fail-open on an unreadable sibling; byte-identical no-op when no originating marker exists.

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py`-run (pytest) new merged-read test is RED before the change (target-repo events absent from a claude-config-rooted read) and GREEN after.

**Status:** Complete

**Implementation Notes (2026-07-12):** Added `lazy_core._originating_telemetry_paths(current_repo_root, *, now=None)` just above `read_intervention_telemetry`, and wired a fail-open merge of its result into `read_intervention_telemetry` (after the cloud-segment merge, before the dedup/sort). The resolver: state base = `LAZY_STATE_DIR` if set else `~/.claude/state`; enumerates keyed subdirs, RAW-reads each `lazy-run-marker.json` (never `read_run_marker` — no delete side effect), skips stale (>`_MARKER_STALE_SECONDS`) and self (`repo_key`-equal) markers, picks the MOST-RECENT live FOREIGN marker (= "the current run's target repo", D1 v1), and returns its `lazy-telemetry.jsonl` + rotated segments oldest-first. Whole body try/except → `[]` (fail-open, absolute). Dedup/sort unchanged. Tests: 4 new `test_read_intervention_telemetry_*` in `test_lazy_core.py` (merge, dedup+unique, fail-open, byte-identical no-op) — RED→GREEN verified. **Pre-existing red baseline:** `test_lazy_core.py` has 75 failures on clean `main` (all `test_mark_complete_*`/`test_mark_fixed_*` receipt/completion tests — sampled-confirmed via `git stash` that they fail on HEAD without this change; causally unrelated to the telemetry read). WU-1 introduces zero new failures (clean 922 passed → 926 with the 4 new tests). Parity audit exit 0; `bug-state.py --test` green; `lazy-state.py --test`'s lone `[apply-pseudo-provisional-refusal] SystemExit:3` is the C3 containment refusal fired by the active cycle marker, not a WU-1 regression.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — extend `read_intervention_telemetry` (16316); add a keyed-ledger-path resolver helper if the marker-read/`repo_key` composition warrants it.
- `user/scripts/test_lazy_core.py` — merged-read fixtures + assertions.

**Testing Strategy:** Hermetic pytest with `LAZY_STATE_DIR`-independent keyed dirs constructed under a temp HOME (or the existing state-dir fixture helpers); assert the merged/deduped/sorted event list. No runtime, no network.

**Integration Notes for Next Phase:** The merged read is what makes a `--repo-root <claude-config>` flush (Phase 3) actually see originating telemetry. Phase 4's re-baseline reads real windows THROUGH this merged read — do not re-implement resolution there.

---

### Phase 2: Coverage-bearing efficacy breadcrumb + scope-checking `--run-end` gate

**Scope:** Close the "gate verifies INVOCATION, not COVERAGE" hole. `drop_efficacy_breadcrumb` (`lazy_core.py:15832`) records WHICH repo-scopes (repo keys / roots) the flush evaluated; `efficacy_breadcrumb_present` / the `--run-end` efficacy gate (`lazy-state.py:11898+`, coupled `bug-state.py`) refuses when the interventions-bearing scope (claude-config) is not among the covered scopes — mirroring how the sibling unacked-hardening gate refuses on missing debt discharge. Fail-open posture preserved on every non-gate path; the operator override (`--efficacy-skip-authorized`) still discharges deliberately.

**Deliverables:**
- [ ] `drop_efficacy_breadcrumb(...)` accepts and records the covered repo-scope(s) in the breadcrumb payload (extends the current `{run_started_at, ts}` with a `covered_scopes: [<repo_key|root>]` field), written via `_atomic_write`, still marker-gated + fail-open (a write error → `False`, never wedges the flush).
- [ ] `efficacy-eval.py` passes the scope it evaluated (its `--repo-root` → `repo_key`) into `drop_efficacy_breadcrumb` at `efficacy-eval.py:1114`; a two-scope run accumulates BOTH scopes across the trio invocations (breadcrumb read-merge-writes coverage, or the run-end gate reads the union of same-run breadcrumbs — implementation detail for `/write-plan`).
- [ ] `efficacy_breadcrumb_present` (or a new coverage-aware sibling) returns satisfied ONLY when the interventions-bearing scope (`repo_key(<claude-config>)`) is covered for the CURRENT run (`run_started_at` match preserved); an invocation that covered only the target repo does NOT discharge the gate.
- [ ] The `--run-end` gate (`lazy-state.py` + coupled `bug-state.py`) refuses (exit 1, marker + registry LEFT IN PLACE) with a corrective message naming the uncovered interventions scope when coverage is incomplete, exactly parallel to the unacked-hardening refusal; `--efficacy-skip-authorized` still overrides.
- [ ] No-live-marker / on-demand invocation still leaves no residue and the gate stays moot (existing `_raw_marker_started_at is None → True/False` semantics preserved).
- [ ] COUPLED PAIR: the `--run-end` gate change is mirrored in `lazy-state.py` and `bug-state.py`; run `python3 user/scripts/lazy_parity_audit.py --repo-root .` (exit 0).
- [ ] Tests: `test_lazy_core.py` coverage for the coverage-bearing breadcrumb write/read; each script's in-file `--test` harness for the tightened `--run-end` gate (refuses on target-only coverage; passes on two-scope coverage; `--efficacy-skip-authorized` overrides; no-marker moot).

**Minimum Verifiable Behavior:** A `--run-end` after a flush that covered ONLY the target repo scope returns the refusal JSON (`run_marker_deleted: false`) naming the uncovered interventions scope; a `--run-end` after a flush that additionally covered claude-config passes — asserted in the in-file `--test` fixtures (byte-pinned baselines regenerated via `_normalize_smoke_output`).

**Prerequisites:** None structurally, but authored AFTER Phase 1 so the coverage semantics reflect the merged read. (Phase 2 does not consume Phase 1 symbols; ordering is for coherent review.)

**Files likely modified:**
- `user/scripts/lazy_core.py` — `drop_efficacy_breadcrumb` (15832) + `efficacy_breadcrumb_present` (15864) coverage fields.
- `user/scripts/efficacy-eval.py` — pass covered scope at the breadcrumb-drop call (1114).
- `user/scripts/lazy-state.py` — `--run-end` efficacy gate (11898+) coverage check + refusal message.
- `user/scripts/bug-state.py` — coupled `--run-end` gate mirror.
- `user/scripts/test_lazy_core.py` + both scripts' in-file `--test` harnesses + `tests/baselines/*.txt`.

**Testing Strategy:** pytest for the shared `lazy_core` breadcrumb helpers; hermetic in-file `--test` fixtures for the gate refusal/pass/override paths; parity audit green.

**Integration Notes for Next Phase:** Phase 3's two-scope flush is what PRODUCES the claude-config coverage this gate now demands — the two ship together (a tightened gate with no second flush would refuse every run-end). Keep the coverage field name/shape stable; Phase 3 prose references it only conceptually.

---

### Phase 3: Two-scope end-of-run flush in the coupled orchestrator trio

**Scope:** Wire the additional claude-config-scoped flush into the §1c.6 end-of-run sequence of all three orchestrators (per D2), so records and the telemetry that grades them meet in one evaluation, and the Phase-2 coverage gate is satisfiable. Prose-only (state-machine logic lives in the scripts already changed in Phases 1–2). Coupled-trio mirror: `lazy-batch` ↔ `lazy-bug-batch` ↔ `lazy-batch-cloud`.

**Deliverables:**
- [ ] `user/skills/lazy-batch/SKILL.md` §1c.6: the end-of-run flush additionally runs the trio (`efficacy-eval.py` review + `--canary`, and — where applicable — the interventions-bearing evaluation) with `--repo-root <claude-config>` (path resolvable from the skill's config table), NOT only `--repo-root .` in the target repo. State the two-scope contract explicitly (the claude-config-rooted evaluation sees originating telemetry via the Phase-1 merged read; both scopes are attested in the breadcrumb per Phase 2). Doc-write/commit ownership unchanged; NON-BLOCKING failure posture (`⚠ efficacy-eval failed`) preserved.
- [ ] Mirror the identical two-scope flush prose into `user/skills/lazy-bug-batch/SKILL.md` and `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, honoring each sibling's tabulated divergences (cloud's committed-segment path; the bug orchestrator's §1c.6 analog).
- [ ] Update each skill's coupled-pair "Differences" / State Machine notes if the flush shape changed the dispatch surface.
- [ ] Re-project + lint: `python3 ~/.claude/scripts/project-skills.py` then `python3 ~/.claude/scripts/lint-skills.py` (clean); `python3 user/scripts/doc-drift-lint.py --repo-root .` (exit 0) if the Hooks/Coupled-pairs tables are touched.

**Minimum Verifiable Behavior:** `doc-drift-lint.py --repo-root .` exits 0 and `lint-skills.py` reports no broken injections after the trio edit; the three §1c.6 blocks state the same two-scope flush (manual diff confirms mirror).

**Prerequisites:**
- Phase 1: the merged read (so the claude-config-rooted flush sees originating telemetry).
- Phase 2: the coverage-bearing breadcrumb + gate (so the second flush is what discharges the tightened gate — they must ship together).

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` (§1c.6, ~476–480).
- `user/skills/lazy-bug-batch/SKILL.md`.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`.

**Testing Strategy:** Prose review + `project-skills.py`/`lint-skills.py`/`doc-drift-lint.py`; a manual three-way diff of the §1c.6 flush blocks confirms the coupled-trio mirror.

**Integration Notes for Next Phase:** Phase 4 (re-baseline) is data repair independent of the prose; it depends only on Phase 1's merged read.

---

### Phase 4: Re-baseline the six poisoned gate-refusal records

**Scope:** Repair the six `event:gate-refusal` records (r14, r15, r16, r18, r20, r21) frozen at the stale `runs:1/events:15/value:15.0` single-cloud-run baseline. Re-freeze each baseline from the REAL merged ledger (Phase 1) via an explicit evaluator/CLI re-baseline act (D9 manual-backfill path — `record_intervention` is never-clobbering by existence, so re-baselining is a deliberate write, not a re-capture), carrying the D3 provenance note (`backfilled-from-merged-ledger`, date). r5/r7 are EXCLUDED — their target signals are vocabulary-invalid (owned by the sibling capture-defects bug).

**Deliverables:**
- [ ] A re-baseline act (extend `efficacy-eval.py` with an explicit re-baseline path, or a `--record-intervention`-adjacent CLI act — mechanism chosen at `/write-plan`) that recomputes an EXISTING record's frozen `baseline` from the merged ledger and overwrites it through the shared `_render_intervention_record` serializer (`lazy_core.py:16359`, diff-stable field order), stamping `provenance: backfilled-from-merged-ledger` + the date. NEVER silently equal to an original capture (D3).
- [ ] Apply it to r14, r15, r16, r18, r20, r21 (`docs/interventions/harden-2026-07-r*.md`); confirm each new baseline reflects real merged-ledger runs/events (not the frozen `runs:1/events:15`), with `window_start_run`/`window_end_run`/`last_run_id` re-derived.
- [ ] r5/r7 explicitly left untouched with a one-line note pointing at the sibling capture-defects bug (`hardening-intervention-records-unmeasurable-or-missing`).
- [ ] The re-baseline is idempotent-safe (re-running does not double-stamp or corrupt); a record whose merged window is still empty gets an HONEST no-data/pending baseline, never a fabricated value (the evaluator's existing no-data honesty ladder).
- [ ] Tests: `test_efficacy_eval.py` (or `test_lazy_core.py`) coverage for the re-baseline act — reads a fixture merged ledger, overwrites a poisoned baseline, asserts the new value + `provenance` note + no-clobber-without-the-act.

**Minimum Verifiable Behavior:** After the re-baseline act runs against a fixture merged ledger, a poisoned record's `baseline` no longer reads `runs:1/events:15/value:15.0` and carries `provenance: backfilled-from-merged-ledger` — asserted in `test_efficacy_eval.py`.

**Prerequisites:**
- Phase 1: the merged read supplies the real baseline window.

**Files likely modified:**
- `user/scripts/efficacy-eval.py` — the re-baseline act.
- `docs/interventions/harden-2026-07-r{14,15,16,18,20,21}.md` — re-frozen baselines + provenance.
- `user/scripts/test_efficacy_eval.py` — re-baseline coverage.

**Testing Strategy:** Hermetic pytest with a fixture merged ledger; assert the overwritten baseline, the provenance stamp, the never-clobber-by-existence invariant, and the no-data honesty fallback.

**Integration Notes for Next Phase:** Terminal phase. When this phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) — the state machine routes to the validation tail; `__mark_fixed__` (gate-owned) writes `FIXED.md` and flips SPEC `**Status:**` to `Fixed`.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to `Fixed` and writes `FIXED.md` once the fix is validated — never authored as a checkbox row here.

---

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC (a standalone harness bug) — no upstream reality-check owed. `--sync-deps` skipped (nothing to project).

## Verification

This bug has no MCP/app surface; validation is:
- `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` (byte-pinned baselines).
- `python3 user/scripts/test_lazy_core.py` and `python3 user/scripts/test_efficacy_eval.py` (pytest).
- `python3 user/scripts/lazy_parity_audit.py --repo-root .` (exit 0 — Phase 2 touches both state scripts).
- `python3 ~/.claude/scripts/project-skills.py` + `lint-skills.py` + `doc-drift-lint.py --repo-root .` (Phase 3 prose).
- Symptom-reproduction (SEAM B, completion gate): a claude-config-rooted efficacy flush over the real merged ledger produces ≥1 DUE verdict where zero were ever produced before (the SPEC's `## Verified Symptom` — "zero `## Review <date>` sections across all 25 records").
