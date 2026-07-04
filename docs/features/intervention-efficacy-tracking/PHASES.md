# Implementation Phases — Intervention Efficacy Tracking (Hypothesis Ledger)

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Complete
<!-- All 4 phases implemented + validated 2026-07-04 (pytest 1260 + toolify + coord +
     both --test baselines + parity audit exit 0 + lint/projection clean). NOT Complete
     on the SPEC — the __mark_complete__ integrity gate owns the SPEC Complete flip +
     COMPLETED.md receipt. -->

**MCP runtime:** not-required — pure claude-config harness mechanics (Python state-script capture chokepoint + a standalone stdlib evaluator + skill prose). No Tauri app, no MCP-reachable surface; validation is `pytest` on `test_lazy_core.py` / the NEW `test_efficacy_eval.py`, the `--test` smoke baselines, `lazy_parity_audit.py`, and `lint-skills.py`. This is the `standalone — no app integration` untestable class → `SKIP_MCP_TEST.md` at the MCP gate.

## Cross-feature Integration Notes

- **`harness-telemetry-ledger` (hard dep — LANDED on this base):** `lazy_core.append_telemetry_event` / `read_telemetry_events` / `flush_cloud_telemetry_segment` ship with the D4-B v1 vocabulary (`run-start`, `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`, `gate-refusal`, `containment-refusal`) and the `{v, ts, run_id, pipeline, event, item_id, data}` envelope. Baselines and post-windows are computed over these REAL shapes; run identity is `run_id` (marker `started_at`, lexically chronological). The evaluator additionally merges committed cloud segments (`docs/telemetry/cloud/*.jsonl`) — the trends-aggregator read pattern.
- **`friction-kpi-registry` (soft dep — concurrent sibling lane):** `kpi:<system>.<kpi-id>` targets are carried verbatim on records and route through ONE resolution seam in the evaluator (`_resolve_target_signal`); in this lane the seam resolves only `event:<type>` targets and reports `kpi:` targets `unresolvable` → honest `INCONCLUSIVE (kpi-unresolvable)`. This lane never reads or writes `docs/kpi/`.
- **`anti-overfit-design-gate` (sibling consumer):** the record carries `signal_independence` verbatim from day one; the evaluator annotates (never enforces) `self-emitted` reviews.
- **`code-doc-provenance-linkage` (soft dep):** `commit_set` is v1-shaped (the capture commit); enrichment is that feature's job.

---

### Phase 1: Record + capture (`record_intervention`, hypothesis parsing, completion-gate wiring, CLI)

**Phase kind:** design

**Scope:** The capture half: `lazy_core` gains the D5 constants block, `parse_intervention_hypothesis` (the `## Intervention Hypothesis` SPEC-block reader), the intervention-record frontmatter serializer, a merged telemetry reader (state-dir + committed cloud segments), and `record_intervention` (baseline freezing + atomic record write to `docs/interventions/<id>.md`). Wire capture into the shared `__mark_complete__`/`__mark_fixed__` branch of `apply_pseudo` (after the receipt write; return key `intervention_recorded`; repo-opt-in via top-level `"interventions": true` in `docs/features/queue.json`, or a present hypothesis block when the flag is off; byte-identical output otherwise; fail-open — a capture error degrades to a `warnings` entry, never fails the completion). Add the orchestrator-only `--record-intervention` CLI to BOTH state scripts (D9 backfill overrides `--shipped-commit`/`--shipped-date` → `provenance: backfilled`; hypothesis-override flags for the no-SPEC hardening path) and extend `lazy_parity_audit.py` with the matching parity check.

**Deliverables:**
- [x] `lazy_core.py`: constants `INTERVENTION_BASELINE_RUNS = 20`, `INTERVENTION_REVIEW_AFTER_RUNS = 20`, `INTERVENTION_MIN_SAMPLE = 5`, `INTERVENTION_BAND_PCT = 20` (one block, D5-A), `_INTERVENTIONS_DIRNAME = "interventions"`.
- [x] `lazy_core.parse_intervention_hypothesis(spec_text) -> dict | None`: parses the `## Intervention Hypothesis` block's list-item fields (`target_signal`, `expected_direction`, `signal_independence` — enum head + justification tail, `review_after_runs` + optional `baseline_runs`/`min_sample`/`band_pct` overrides); absent heading → None; malformed fields degrade (never raise).
- [x] `lazy_core.read_intervention_telemetry(repo_root) -> list[dict]`: merged read — `read_telemetry_events()` (per-repo keyed state dir) + committed `docs/telemetry/cloud/*.jsonl` segments, deduped, chronological.
- [x] `lazy_core.record_intervention(repo_root, intervention_id, *, pipeline, spec_path=None, date=None, shipped_commit=None, shipped_date=None, provenance="gated", hypothesis_overrides=None) -> dict`: freezes the baseline (trailing `baseline_runs` distinct `run_id`s; `event:` targets counted; `undeclared`/`kpi:` → honest non-frozen status; missing ledger → `unavailable`, never an error), writes the D3 frontmatter-sentinel record via `_atomic_write` to `docs/interventions/<id>.md`, idempotent (existing `kind: intervention` record → noop).
- [x] `apply_pseudo` `__mark_complete__`/`__mark_fixed__`: capture AFTER the receipt write, gated on `_interventions_capture_eligible` (queue flag OR hypothesis block); result gains `intervention_recorded` + `intervention_record` keys ONLY when capture fired (byte-identical otherwise); fail-open to `warnings`.
- [x] `--record-intervention` CLI on BOTH `lazy-state.py` and `bug-state.py` (reuses `--id`; new `--pipeline {feature,bug,hardening}`, `--shipped-commit`, `--shipped-date`, `--target-signal`, `--expected-direction`, `--signal-independence`, `--review-after-runs` flags; guarded by `refuse_if_cycle_active`; `provenance: backfilled` iff a shipped-* override is passed, else `manual`).
- [x] `lazy_parity_audit.py`: `_RECORD_INTERVENTION_RE` check added to `audit_state_script_parity` (the `--reassert-owner` pattern); audit stays exit 0.
- [x] Tests (`test_lazy_core.py`, registered in `_TESTS`): hypothesis parsing (full block / absent / malformed / overrides); record write + nested `baseline:` round-trip through `parse_sentinel`; baseline frozen from a fixture ledger; no-ledger → `unavailable`; undeclared degradation; `apply_pseudo` capture with flag on (key + record present), flag off + no block (byte-identical result keys, no record), block-without-flag capture, idempotent re-complete no re-capture; backfill provenance stamp.

**Minimum Verifiable Behavior:** In a fixture repo with `"interventions": true` and a live fixture ledger, `apply_pseudo("__mark_complete__", …)` writes `docs/interventions/<id>.md` with `kind: intervention` + a frozen `baseline:` map and reports `intervention_recorded: true`; the same completion in a fixture repo without the flag or block produces a result dict with NO intervention keys and NO record file.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Capture on completion: flagged fixture repo `__mark_complete__` → record written + `intervention_recorded: true`. *(Evidence: `SKIP_MCP_TEST.md` — `test_lazy_core.py` capture fixtures.)* <!-- verification-only -->
- [x] Byte-identical elsewhere: unflagged/no-block completion → no record, result keys unchanged from pre-feature. *(Evidence: `test_lazy_core.py` flag-off fixture.)* <!-- verification-only -->
- [x] Parity: `lazy_parity_audit.py --repo-root .` exit 0 with the new `--record-intervention` check active on both scripts. *(Evidence: gate-suite run.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface (claude-config has no Tauri/MCP app). Verification is `pytest`.

**Prerequisites:** None (first phase; telemetry substrate already landed).

**Files likely modified:** `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`, `user/scripts/bug-state.py`, `user/scripts/lazy_parity_audit.py`, `user/scripts/test_lazy_core.py`.

**Testing Strategy:** Hermetic `LAZY_STATE_DIR` temp dirs + `write_run_marker`/`append_telemetry_event` fixture ledgers (the telemetry Phase-1 discipline); temp repo roots with fixture `queue.json`. `--test` baselines expected unchanged (no smoke-fixture edits).

**Integration Notes for Next Phase:** The record's frontmatter (esp. `baseline:` map with `last_run_id`, `review_count`, `status`) is the evaluator's input contract; the serializer (`_render_intervention_record`) is shared so evaluator updates keep field order byte-stable.

---

### Phase 2: Evaluator (`efficacy-eval.py`)

**Phase kind:** design

**Scope:** The standalone stdlib evaluator: enumerate `docs/interventions/*.md`, accrue post-ship windows (distinct `run_id`s newer than the frozen `baseline.last_run_id`; review k due at `(k+1) × review_after_runs` post runs; non-overlapping consecutive windows), enforce min-sample, apply the ±band verdict arithmetic (CONFIRMED / REFUTED / INCONCLUSIVE with honest reasons: `min-sample x/y`, `no-baseline`, `undeclared`, `kpi-unresolvable`, `no-ledger-data`), scan confounders (annotate always; cap at `INCONCLUSIVE (confounded)` on same-signal overlap — D6), annotate `self-emitted` independence, append `## Review <date>` sections + update frontmatter atomically, escalate after 2 INCONCLUSIVE reviews (D8). Flags: `--repo-root`, `--json`, `--dry-run` (byte-inert), `--id` (single-record filter). Exit 0 even on REFUTED — verdicts are data.

**Deliverables:**
- [x] `user/scripts/efficacy-eval.py`: enumeration, window accrual, min-sample, verdict bands, confounder scan/cap, independence annotation, review append + frontmatter update (via the shared serializer + `_atomic_write`), escalation stamping, `--repo-root`/`--json`/`--dry-run`/`--id`, exit-0-always (except malformed input exit 2), human summary + `--json` machine shape (`reviewed`, `verdicts[]`, `needs_triage[]`, `not_due[]`, `enqueued[]`).
- [x] `user/scripts/test_efficacy_eval.py` (pytest, hermetic via `LAZY_STATE_DIR` + temp repos, `test_lazy_queue_doc.py` conventions): CONFIRMED (≥20% expected-direction movement), REFUTED (≥20% against), INCONCLUSIVE (inside band; min-sample unmet), not-due accrual, confounded cap (same-signal) + different-signal annotate-only, undeclared, no-ledger-data, kpi-unresolvable, `--dry-run` byte-inert, `--id` filter, exit codes.

**Minimum Verifiable Behavior:** Fixture ledgers with known deltas produce the D5 verdicts; `--dry-run` leaves every record byte-identical; a REFUTED verdict exits 0.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Verdict arithmetic: CONFIRMED / REFUTED / INCONCLUSIVE per D5 bands; min-sample enforced. *(Evidence: `SKIP_MCP_TEST.md` — `test_efficacy_eval.py`.)* <!-- verification-only -->
- [x] Baseline frozen: evaluation still verdicts after the state-dir ledger is deleted post-capture (record baseline used, post window from remaining/committed events). *(Evidence: `test_efficacy_eval.py` frozen-baseline fixture.)* <!-- verification-only -->
- [x] Confounder cap: two same-signal in-window records both capped `INCONCLUSIVE (confounded)` with cross-annotations. *(Evidence: `test_efficacy_eval.py`.)* <!-- verification-only -->

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface. Verification is `pytest`.

**Prerequisites:** Phase 1 (record schema + serializer + merged telemetry reader).

**Files likely modified:** `user/scripts/efficacy-eval.py` (new), `user/scripts/test_efficacy_eval.py` (new).

**Testing Strategy:** Pure-fixture temp repos: records written by the REAL `record_intervention`, ledgers written by the REAL `append_telemetry_event` under a fixture run marker (varying `started_at` per fixture run) — no hand-rolled envelope shapes.

**Integration Notes for Next Phase:** The evaluator's REFUTED path calls a seam (`_enqueue_reconsideration`) that Phase 3 binds to the sanctioned subprocess; `needs_triage[]` is the retro-citation input.

---

### Phase 3: Consequences + surfacing (REFUTED auto-enqueue, flush wiring, retro citation)

**Phase kind:** integration

**Scope:** Bind the REFUTED consequence to the shipped ad-hoc enqueue (`lazy-state.py --enqueue-adhoc --type bug --id reconsider-<id> …` subprocess with `LAZY_ORCHESTRATOR=1`, brief naming the record path + verdict + revert-or-redesign) behind the D7 two-layer recurrence guard (layer 1: `docs/bugs/reconsider-<id>/` open OR archived; layer 2: `reconsideration_enqueued` stamp — once stamped, never again). Add the end-of-run flush paragraph to `/lazy-batch` §1c.6 AND `/lazy-batch-cloud` §1c.6 (coupled-pair mirror, alongside incident-scan, BEFORE `--run-end`) + the cloud divergence-table row, and the `/lazy-batch-retro` Step 6e report-only citation step (dry-run shell + status-bookend line).

**Deliverables:**
- [x] `efficacy-eval.py`: `_enqueue_reconsideration` bound to the sanctioned subprocess; two-layer guard; `--dry-run` never enqueues; enqueue announced in output (`consequence: enqueued reconsider-<id>`).
- [x] `test_efficacy_eval.py`: end-to-end fixture — repeated evaluator runs over a REFUTED record produce EXACTLY ONE `reconsider-<id>` queue entry + brief; stamp survives bug-dir deletion (layer 2); archived-dir skip (layer 1); dry-run no-enqueue.
- [x] `user/skills/lazy-batch/SKILL.md` §1c.6: efficacy-eval flush paragraph (once per run, after incident-scan, BEFORE `--run-end`; non-blocking; relay verdict summary; commit any record updates with the run-end sequence).
- [x] `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` §1c.6: mirrored paragraph + "Differences from /lazy-batch" table row (record updates ride the final cloud push).
- [x] `user/skills/lazy-batch-retro/SKILL.md` Step 6e: report-only `efficacy-eval.py --repo-root . --dry-run --json` citation (verdicts replace narrative claims; needs-triage listed; degrade-gracefully) + status-bookend `**Intervention verdicts:**` line.
- [x] `project-skills.py` projection (lane-local output dir) + `lint-skills.py` clean after the skill edits.

**Minimum Verifiable Behavior:** An end-to-end fixture run producing a reconsideration item exactly once across repeated evaluations; skill lint green.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] REFUTED enqueues once: repeated evaluator runs → `reconsider-<id>` exists exactly once; record stamped `reconsideration_enqueued`. *(Evidence: `SKIP_MCP_TEST.md` — `test_efficacy_eval.py` end-to-end fixture.)* <!-- verification-only -->
- [x] Escalation: third evaluation of a twice-INCONCLUSIVE record → `escalated: true` + needs-triage listing. *(Evidence: `test_efficacy_eval.py`.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** live end-of-run flush observation — a real `/lazy-batch` run reaching a terminal and invoking `efficacy-eval.py` at §1c.6 (needs a live orchestrated run; the prose contract is projection-linted and the invocation is the same command the hermetic suite drives).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface. Verification is `pytest` + `lint-skills.py`.

**Prerequisites:** Phase 2 (evaluator core).

**Files likely modified:** `user/scripts/efficacy-eval.py`, `user/scripts/test_efficacy_eval.py`, `user/skills/lazy-batch/SKILL.md`, `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md`, `user/skills/lazy-batch-retro/SKILL.md`.

**Testing Strategy:** The enqueue subprocess is exercised REAL (temp repo; the child runs the actual `lazy-state.py`/`bug-state.py`), matching the `enqueue_adhoc_bug` precedent; skill-prose edits validated by lane-local projection + lint.

**Integration Notes for Next Phase:** Phase 4 reuses the same CLI with `--pipeline hardening`; nothing in the evaluator special-cases pipelines.

---

### Phase 4: Hardening-round capture + backfill + docs

**Phase kind:** integration

**Scope:** `/harden-harness` Step 4 invokes `--record-intervention --id harden-<YYYY-MM>-r<N> --pipeline hardening` (additive to the round log; hypothesis-override flags carry the round's targeted signal when known). Document the D9 manual backfill flow. Author the docs rows: root `CLAUDE.md` scripts-table row, `user/scripts/CLAUDE.md` table row + intervention-ledger section, NEW `docs/interventions/CLAUDE.md` (record schema + the `## Intervention Hypothesis` authoring surface).

**Deliverables:**
- [x] `user/skills/harden-harness/SKILL.md` Step 4: `--record-intervention` invocation block (`pipeline: hardening`, id scheme `harden-<YYYY-MM>-r<N>`, optional `--target-signal event:<type>` from the round's evidence; non-blocking).
- [x] `test_lazy_core.py`: hardening-round capture fixture — CLI-shaped `record_intervention(..., pipeline="hardening", hypothesis_overrides=…)` produces a record with `pipeline: hardening`; backfill overrides produce `provenance: backfilled`.
- [x] `docs/interventions/CLAUDE.md`: record schema, lifecycle, the `## Intervention Hypothesis` authoring block (copy-paste template), backfill flow.
- [x] Root `CLAUDE.md`: `efficacy-eval.py` scripts-table row (tightly scoped add).
- [x] `user/scripts/CLAUDE.md`: `efficacy-eval.py` table row + a short "Intervention efficacy ledger" section (capture chokepoint, opt-in flag, CLI, evaluator cadence).

**Minimum Verifiable Behavior:** A hardening-round dry run (the CLI against a fixture repo) produces a record with `pipeline: hardening`; docs lint (doc-drift-lint self-check) unaffected.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [x] Hardening-round capture: `--record-intervention --pipeline hardening` fixture → record with `pipeline: hardening`. *(Evidence: `SKIP_MCP_TEST.md` — `test_lazy_core.py` hardening fixture.)* <!-- verification-only -->
- **DEFERRED (workstation-only, not a completion blocker):** a live `/harden-harness` round performing the Step-4 invocation end-to-end (needs a real hardening dispatch; the CLI it runs is covered hermetically).

**MCP Integration Test Assertions:** N/A — no MCP-reachable surface. Verification is `pytest` + docs lint.

**Prerequisites:** Phases 1–3.

**Files likely modified:** `user/skills/harden-harness/SKILL.md`, `user/scripts/test_lazy_core.py`, `docs/interventions/CLAUDE.md` (new), `CLAUDE.md`, `user/scripts/CLAUDE.md`.

**Testing Strategy:** Fixture-repo CLI subprocess test for the hardening capture; full gate suite at the end.

**Integration Notes for Next Phase:** None — final phase. Sibling consumers (`anti-overfit-design-gate`, `friction-kpi-registry`, `harness-change-canary-rollback`) compose against the record fields (`signal_independence`, `target_signal`, the flat central dir) without further change here.
