---
kind: implementation-plan
feature_id: toolify-auto-promotion
status: In Progress
created: 2026-07-04
complexity: complex
phases: [1, 2, 3, 4]
---

> **Plan** — generated inline on 2026-07-04.
> To execute: `/execute-plan docs/features/toolify-auto-promotion/plans/all-phases-toolify-auto-promotion-part-1.md`
> Single self-contained part covering all 4 phases.

# Implementation Plan — toolify-auto-promotion (Phases 1–4)

**PHASES.md:** `docs/features/toolify-auto-promotion/PHASES.md` (4 phases)
**SPEC.md:** `docs/features/toolify-auto-promotion/SPEC.md`

## EXECUTION MODEL

> **INLINE-EXECUTION:** This plan is executed INLINE with `Read`/`Edit`/`Write` (no `Agent`
> delegation), **test-first** for every TDD work unit — write the failing test before the
> implementation. Never invoke `/lazy` or `/lazy-batch` recursively.

**Gate suite (run after each phase; ALL green before marking a phase's WUs done):**
```
python3 -m pytest test_lazy_core.py test_hooks.py test_pipeline_visualizer.py \
  test_lazy_parity.py test_lazy_queue_doc.py test_lint_skills.py \
  test_surface_resolver.py test_stale_binary.py test_retro_ro9.py \
  test_project_skills.py -q
python3 test_toolify_miner.py
python3 test_toolify_promote.py            # from Phase 3 on
python3 lazy-state.py --test
python3 bug-state.py --test
python3 lazy_coord.py --test
python3 lazy_parity_audit.py --repo-root <repo-root>
python3 lint-skills.py --skills-dir <repo-root>/user/skills --repos-dir <repo-root>/repos
```

## Key design contract (read before WU-1.1)

- **One id derivation:** `toolify_miner.candidate_id(sig) = sha256(sig)[:12]`; the promote script
  and the ledger reuse it — nothing re-hashes.
- **Two-marker stub contract (D5):** queue `"stub": true` (Phase-2 flag) AND the in-SPEC anchored
  markers (`**Status:** Draft (pre-Gemini)` line + `> Draft (pre-Gemini)…` blockquote) from the
  template constant. Round-trip test binds the template to the REAL
  `lazy-state.py::_spec_text_has_stub_marker`, never a copied string.
- **Failure-safe promote ordering:** enqueue (routable via ADHOC_BRIEF) → stub SPEC write →
  ledger append LAST. A crash between steps degrades loudly (Step-4 brief route / duplicate-id
  refusal), never wedges.
- **Byte-identical defaults:** `--stub` absent ⇒ no `stub` key; `--at` absent ⇒ head insert; the
  `--test` baseline is regenerated ONLY via `_normalize_smoke_output` after the new fixture
  prints land. `bug-state.py` untouched (justified divergence; parity audit must stay exit 0).
- **Report-only surfaces:** retro Step 6d and `--acceptance-report` observe; they never enqueue,
  never edit the miner's constants.

---

## Phase 1 — Miner candidate identity

- [x] WU-1.1 — TEST-FIRST: add `test_candidate_id_stable_across_passes`,
  `test_candidate_id_unique_and_derivable`, `test_candidate_id_in_renders` to
  `test_toolify_miner.py`; run → RED (module lacks `candidate_id`).
- [x] WU-1.2 — Implement `candidate_id()` helper + `Candidate.candidate_id` field + `mine()`
  population + both renderers (additive column/key); run miner tests → GREEN (19 prior + new).
- [x] WU-1.3 — `toolify-bar.md` schema-table row for `candidate_id`. Commit Phase 1.

## Phase 2 — Enqueue path flags

- [x] WU-2.1 — TEST-FIRST: extend `run_smoke_tests()` with the `[enqueue-flags]` functional block
  (default entry has NO `stub` key; `stub=True` ⇒ `"stub": true`; `at="tail"` appends with honest
  `queue_position`; `--type bug` + `--stub` refused via CLI subprocess or handler check); run
  `lazy-state.py --test` → RED (TypeError/missing behavior).
- [x] WU-2.2 — Implement `enqueue_adhoc(…, stub=False, at="head")` + `--stub`/`--at` argparse +
  handler threading + the `--type bug` refusal; `lazy-state.py --test` → GREEN.
- [x] WU-2.3 — Regenerate `tests/baselines/lazy-state-test-baseline.txt` via
  `_normalize_smoke_output` (never hand-edit); `pytest test_lazy_core.py` baseline test green;
  `bug-state.py --test` green (baseline untouched); `lazy_parity_audit.py` exit 0. Commit Phase 2.

## Phase 3 — Materializer + ledger

- [x] WU-3.1 — Scaffold `test_toolify_promote.py` (self-contained runner mirroring the miner
  test): importlib load of `toolify-promote.py`, fixture builders (reuse miner corpus builders,
  scratch-repo builder, fixture ledger). First tests: module importable, template round-trip
  against the REAL `_spec_text_has_stub_marker` (True rendered / False stripped) → RED.
- [x] WU-3.2 — Implement `toolify-promote.py` skeleton: argparse (`--promote`, `--decline`,
  `--status`, `--from-json`, `--id`, `--name`, `--repo-root`, `--reason`, `--force`, `--logs`,
  `--ledger`), miner import, ledger load/append via `lazy_core._atomic_write`, the template
  constant + renderer → round-trip GREEN.
- [x] WU-3.3 — TEST-FIRST refusals: unknown id (exit 2, re-mine hint); below-bar naming the
  failed predicate (judgment / run-count / score — one fixture each); missing `--id`/`--name`;
  malformed slug; promoted-dup; declined-dup sans `--force`; `--force` sans `--reason` → then
  implement the promote guard chain → GREEN. No writes on any refusal path (asserted).
- [x] WU-3.4 — TEST-FIRST happy paths: promote (fresh-mine + `--from-json`) lands tail/tier-2/stub
  queue entry + brief + marker-bearing stub SPEC + `promoted` ledger entry (evidence embedded);
  decline records reason; `--force --reason` re-promote of a declined id records `forced: true`
  → implement enqueue shelling + spec write + ledger append → GREEN.
- [x] WU-3.5 — TEST-FIRST failure ordering: monkeypatched spec-writer failure ⇒ queue entry +
  ADHOC_BRIEF present (routable), NO ledger entry, stderr names the degraded state; re-run exits
  non-zero via the enqueue duplicate-id refusal → implement ordering → GREEN.
- [x] WU-3.6 — TEST-FIRST scratch-repo probe: after a real promote,
  `lazy-state.py --repo-root <scratch>` (hermetic `LAZY_STATE_DIR`) returns
  `current_step: "Step 4.5: stub-spec detected"` + `sub_skill: "spec"` → GREEN. `--status` join
  test (NEW / promoted / declined / shipped rows). Seed the tracked empty ledger file. Commit
  Phase 3.

## Phase 4 — Reports + docs + retro hook

- [ ] WU-4.1 — TEST-FIRST `--acceptance-report`: fixture ledger with known cohorts (promoted /
  declined / one shipped via a receipt on disk) ⇒ totals, rates, sample sizes, cohort score/run
  distributions match hand counts → implement → GREEN.
- [ ] WU-4.2 — `lazy-batch-retro/SKILL.md` Step 6d (report-only resurface; ready-to-run promote
  lines; never invokes); lane-local projection + `lint-skills.py` green.
- [ ] WU-4.3 — Doc rows: `user/scripts/CLAUDE.md` (promote script row, miner row update, CLI
  surface + justified divergence), root `CLAUDE.md` script row, `toolify-bar.md` checklist
  annotations. Commit Phase 4.
- [ ] WU-4.4 — FULL gate suite green (all suites + smokes + parity + lint); write
  `SKIP_MCP_TEST.md`; finalize PHASES/plan statuses. Final commit.
