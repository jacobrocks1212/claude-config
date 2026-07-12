# Implementation Phases — Hardening intervention records unmeasurable or unverifiably exempt

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a config/harness repo with no Tauri app or MCP HTTP server; every deliverable is Python (`lazy_core.py` / `lazy-state.py` / `bug-state.py` / `doc-drift-lint.py`), skill prose, or a data-repair edit to `docs/interventions/`. There is no MCP-reachable surface. Bug-completion evidence is the serving-path regression tests (pytest + the in-file `--test` harnesses), per `symptom-reproduction-gate.md`, not `/mcp-test`.

## Verified Touchpoint Audit (inline — dispatch not warranted for this bounded, fully-read source set)

`verified: inline (dispatch unavailable/unwarranted — orchestrator read every touchpoint directly)`

| Planned file | Exists? | Real symbols (verified `file:line`) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `record_intervention` (:16863), `_intervention_signal_event` (:16469), `parse_intervention_hypothesis` (:16406), `_HOST_CAPABILITY_REGISTRY` closed-registry precedent (:13609), `_diag` diagnostics infra | refactor | Add `_INTERVENTION_EVENT_VOCABULARY` frozenset SSOT (the D4-B closed set) + `validate_intervention_target_signal()` helper; degrade unknown `event:` → `undeclared` + `_diag` inside `record_intervention` (never a frozen bogus zero). REUSE the `_HOST_CAPABILITY_REGISTRY` closed-registry+`^[a-z0-9][a-z0-9-]*$` pattern; do NOT invent a new validation idiom. |
| `user/scripts/lazy-state.py` | yes | `--record-intervention` handler (:12469-12509), arg defs (:10947-10989), `--pipeline` choices incl. `hardening` (:10963) | refactor | On the CLI path, call the new validator BEFORE `record_intervention`; reject an unknown `event:` type and an undeclared `--pipeline hardening` (no `--target-signal`) with exit 1 + valid-set/sibling-D2 guidance. Do NOT route through `_die` (exit 2 = malformed input); use a distinct `stderr` + `return 1`. |
| `user/scripts/bug-state.py` | yes | `--record-intervention` mirror (grep-confirmed: 7 refs incl. `record_intervention`, `--target-signal`, `intervention_pipeline`) | refactor | Mirror the CLI reject/hard-fail verbatim (coupled pair — parity-audited by `lazy_parity_audit.py`). |
| `user/scripts/doc-drift-lint.py` | yes | `check_*(repo_root)` fns + `run_checks` aggregator (:624), `Finding` dataclass (:72), `_read_text` (:163) | refactor | Add `check_intervention_coverage(repo_root)` (D2 preferred home — this linter already owns committed-doc coherence); register it in `run_checks`. REUSE `Finding`/`Row`/`_read_text`; deliberate divergences carry the existing `doc-drift:deliberate-divergence` marker convention. |
| `user/skills/harden-harness/SKILL.md` | yes | Step-4 capture prose (:311-332) | refactor | Update prose to state the now-MECHANICAL vocabulary + coverage contract (reject on unknown event; explicit `--target-signal undeclared` for the genuinely-immeasurable case; coverage lint runs at `--run-end`). Re-project + lint-skills after. |
| `docs/interventions/harden-2026-07-r5.md`, `-r7.md` | yes | `target_signal: event:no-route` / `event:route-loop` (both vocabulary-invalid, grep-confirmed) | refactor (data) | D5 explicit re-declaration onto real vocabulary — never a silent edit; record the re-declaration act. |
| `docs/interventions/harden-2026-07-r{1,2,3}.md` | **NO (net-new)** | — | create (data / decide) | D4 backfill: record r1-r3 explicitly (measurable where a signal exists via the D9 `--shipped-commit/--shipped-date` path; else explicit `--target-signal undeclared`) so the coverage lint sees a record, not a hole. |
| `user/scripts/test_lazy_core.py` | yes | pytest suite (`_collect_*` AST meta-tests precedent) | refactor | Add vocab-check reject/degrade tests (Phase 1) + a test pinning `_INTERVENTION_EVENT_VOCABULARY` == the live emit vocabulary. |
| `user/scripts/test_doc_drift_lint.py` | yes | hermetic fixtures + repo-clean self-check | refactor | Add a coverage-lint fixture: a covered round, an exempt round (`**Intervention record:** none`), and a hole. |
| in-file `--test` harnesses (`lazy-state.py --test`, `bug-state.py --test`) | yes | `def test_<name>()` + `_TESTS` registration | refactor | Add CLI reject/hard-fail smoke fixtures (Phase 2); re-pin the byte-baselines only via `_normalize_smoke_output`. |

**Drift correction:** none required — every SPEC-cited path/symbol resolved to reality (the SPEC's own frontmatter sweep was accurate). The one net-new artifact (r1-r3 records) is a deliberate create, stamped above.

## Validated Assumptions (Step 2.7 gate)

All load-bearing assumptions are **code-provable** — skip the runtime-spike path:
- The D4-B event vocabulary is a fixed closed set (`run-start`, `run-end`, `cycle-begin`, `cycle-end`, `pseudo-applied`, `dispatch`, `halt`, `sentinel-resolved`, `gate-refusal`, `containment-refusal`) — confirmed against `docs/interventions/CLAUDE.md:115-118` and the `append_telemetry_event(` emit sites (SPEC-verified). A pytest lock (Phase 1) pins the constant to the live emit set so it can never silently drift.
- `record_intervention`'s reject/degrade behavior, the CLI hard-fail, and the coverage lint are pure functions of on-disk inputs — verified by pytest + hermetic fixtures, no runtime observation needed.
- **SPEC-example capability audit:** the SPEC's "code examples" are CLI invocations (`--record-intervention …`) and the vocabulary list — every construct confirmed present (`record_intervention` :16863, the `--target-signal`/`--pipeline` flags :10963-10989, the vocabulary constant-to-be). No explicitly-rejected capability consumed. Clean.
- **MCP tool-existence audit:** no `.claude/skill-config/mcp-tool-catalog.md` in claude-config → audit no-ops (recorded skip: `no mcp-tool-catalog.md configured for this repo`).

---

### Phase 1: Vocabulary SSOT + authoring-time validation in `record_intervention`

**Scope:** Introduce the single-source-of-truth event-vocabulary constant and enforce it at record-authoring time. An unknown `event:<type>` target degrades to `undeclared` with a loud diagnostic on the completion-gate path (never a silently-frozen bogus zero baseline), and a reusable validator is exposed for the CLI path (Phase 2) to reject on.

**Deliverables:**
- [x] `lazy_core._INTERVENTION_EVENT_VOCABULARY` — a `frozenset` of the D4-B event types, placed beside `_intervention_signal_event`, modeled on the `_HOST_CAPABILITY_REGISTRY` closed-registry precedent.
- [x] `lazy_core.validate_intervention_target_signal(target_signal) -> str | None` — returns `None` for a valid target (`kpi:*` verbatim-passthrough, `event:<known>`, or `undeclared`) and a human-readable error string (naming the valid set) for an unknown `event:<type>`. Pure, no I/O.
- [x] `record_intervention` change: when the resolved `target_signal` is an unknown `event:<type>`, degrade it to `undeclared` (so the baseline records `not-computable`, not a frozen zero) AND append a `_diag` naming the rejected type — the fail-open completion-gate path (D2-A) never errors, but never silently ships a measurable-looking zero either.
- [x] Tests: `test_lazy_core.py` — (a) `validate_intervention_target_signal` accepts each known event / a `kpi:` target / `undeclared`, rejects `event:no-route` naming the valid set; (b) `record_intervention` with `event:bogus` writes `target_signal: undeclared` + `baseline.status: not-computable` and emits the diagnostic; (c) a lock test pinning `_INTERVENTION_EVENT_VOCABULARY` == the live `append_telemetry_event` emit set (mirrors the `_collect_*` AST/meta-test precedent).

**Implementation Notes (2026-07-12):**
- **Work completed:** WU-1 landed — `_INTERVENTION_EVENT_VOCABULARY` (frozenset, `lazy_core.py:16491`), `validate_intervention_target_signal` (`:16506`), and the `record_intervention` degrade branch (`:17000`). TDD: 6 RED tests authored first (`test_lazy_core.py:33877-34062`), then made green.
- **Vocabulary scope discovery (⚖):** the live `append_telemetry_event(` emit set is **11 events**, not the 10 the SPEC's Verified-Symptom-(a) grep claimed — the SPEC missed `sentinel-provisionalized` (emitted at `lazy-state.py:12312` / `bug-state.py:7592`). The lock test (Group C) asserts SET-EQUALITY constant == live emit set, so the constant is defined as all 11. Symptom fix intact: `event:no-route`/`event:route-loop` still rejected. **Follow-up for part-2/Phase-5:** `docs/interventions/CLAUDE.md`'s D4-B vocabulary list (10 events, `:115-118`) is now stale — it should gain `sentinel-provisionalized` to match the SSOT constant. (doc-drift-lint does not check this list, so it is not a lint failure — a coherence note only.)
- **Review verdict:** PASS (ground-truth verified: yes; assertion-vs-intent clean; `_KNOWN_INTERVENTION_EVENTS` test list is an independent hardcoded 10, and the Group-C collector is independent of the constant — neither tautological).
- **Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** `python3 -c "import lazy_core; print(lazy_core.validate_intervention_target_signal('event:no-route'))"` prints a non-None error naming the valid set; the same call with `event:gate-refusal` prints `None`.

**Runtime Verification** *(checked by test/manual — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `record_intervention(..., hypothesis_overrides={"target_signal": "event:no-route"})` on a temp repo writes a record whose `target_signal` is `undeclared` and whose `baseline.status` is `not-computable` (observed on disk), with the rejection diagnostic present.

**MCP Integration Test Assertions:** N/A — no runtime-observable MCP surface in this repo.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — new constant + validator + `record_intervention` degrade-on-unknown-event branch.
- `user/scripts/test_lazy_core.py` — the three test groups above.

**Testing Strategy:** pytest against `lazy_core` directly (hermetic temp repo for the `record_intervention` write); the vocabulary-lock test guarantees the SSOT can't drift from the emit sites.

**Integration Notes for Next Phase:** `validate_intervention_target_signal` is the shared reject helper Phase 2's CLI path calls. Its error string is the exact text the CLI surfaces on exit 1. The degrade branch here is the completion-gate half of D1 (fail-open); the CLI half (hard reject) is Phase 2.

---

### Phase 2: CLI hard-fail — reject unknown vocabulary + undeclared hardening records

**Scope:** On the interactive/orchestrator CLI path (`--record-intervention`), reject an unknown `event:<type>` target and refuse an undeclared `--pipeline hardening` capture, so a hardening author is forced to declare a measurable signal (or opt in explicitly). The completion-gate path (Phase 1's degrade) is unchanged. Mirror on `bug-state.py` (coupled pair).

**Deliverables:**
- [ ] `lazy-state.py` `--record-intervention` handler: after assembling `overrides`, call `validate_intervention_target_signal` on the resolved target; on error, write the message to stderr and `return 1` (exit 1 per SPEC D1 — NOT `_die`, which is exit 2 = malformed-input).
- [ ] Hardening hard-fail: when `--pipeline hardening` AND the resolved `target_signal` is `undeclared` (no `--target-signal` and no SPEC block), refuse with exit 1 + the sibling-D2 guidance ("declare the friction's own recurrence signal; pass `--target-signal undeclared` to record the genuinely-immeasurable diagnostic deliberately").
- [ ] Escape hatch: an EXPLICIT `--target-signal undeclared` is accepted (typed, retro-visible) — it must NOT trip the hard-fail. (Distinguish "flag omitted" from "flag explicitly `undeclared`".)
- [ ] `bug-state.py` mirror: identical reject + hard-fail in its `--record-intervention` handler (parity-audited).
- [ ] Tests: in-file `--test` fixtures on BOTH scripts — (a) `--record-intervention --pipeline hardening` with no target → exit 1, no record written; (b) `--pipeline hardening --target-signal undeclared` → record written (`undeclared`); (c) `--target-signal event:bogus` → exit 1 naming the valid set. Re-pin the `--test` byte-baselines via `_normalize_smoke_output` only.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --record-intervention --id harden-test --pipeline hardening --repo-root <tmp>` exits 1 and writes no `docs/interventions/harden-test.md`; adding `--target-signal undeclared` exits 0 and writes the record.

**Runtime Verification** *(checked by test/manual):*
- [ ] <!-- verification-only --> Running the CLI with `--pipeline hardening` and no `--target-signal` in a temp repo exits 1, prints the sibling-D2 guidance, and leaves `docs/interventions/` empty (observed).
- [ ] <!-- verification-only --> The same with `--target-signal event:route-loop` exits 1 naming the valid vocabulary set (the exact r7 mistake, now blocked at the CLI).

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 (`validate_intervention_target_signal`).

**Files likely modified:**
- `user/scripts/lazy-state.py` — reject + hardening hard-fail in the `--record-intervention` handler.
- `user/scripts/bug-state.py` — coupled-pair mirror.
- `user/scripts/lazy-state.py` / `bug-state.py` in-file `--test` blocks; `tests/baselines/*.txt` re-pinned.

**Testing Strategy:** in-file `--test` smoke fixtures (the state-script convention) drive `main()` in-process and assert exit code + on-disk effect. Run `lazy_parity_audit.py --repo-root .` after — the mirror is a coupled-pair edit.

**Integration Notes for Next Phase:** After Phase 2, no NEW poisoned or undeclared hardening record can be authored via the CLI. Phase 3 adds the coverage lint that catches a MISSING record (an undisciplined round with no capture at all) — the orthogonal gap Phase 2 does not cover.

---

### Phase 3: Mechanical round-vs-record coverage lint (D2 — doc-drift-lint extension)

**Scope:** Add a mechanical check that every post-contract `Mechanical fix applied:` round in the current month's hardening-log has a matching `docs/interventions/harden-<YYYY-MM>-rN.md`, recognizing the explicit `**Intervention record:** none` marker as a valid exemption. Lives in `doc-drift-lint.py` (D2-preferred home) and is additionally shelled at the `--run-end` flush (fail-open).

**Deliverables:**
- [ ] `doc-drift-lint.py::check_intervention_coverage(repo_root)` — parses `docs/specs/turn-routing-enforcement/hardening-log/<current-month>.md` (round format `## Round N — <date> — <kind>`), and for each round whose Action is the `Mechanical fix applied:` form, asserts either `docs/interventions/harden-<YYYY-MM>-rN.md` exists OR the round carries a `**Intervention record:** none` line. A `Mechanical fix applied:` round with neither → a `Finding` (drift). Registered in `run_checks`.
- [ ] Run-end wiring: the `/lazy-batch(-cloud)` end-of-run flush (alongside `incident-scan.py` / `efficacy-eval.py`, §1c.6) shells the coverage check FAIL-OPEN (a lint failure warns, never blocks `--run-end`). Prefer surfacing via the existing flush prose rather than a state-script compute-path change.
- [ ] Tests: `test_doc_drift_lint.py` hermetic fixture with three rounds — one covered (record present), one exempt (`**Intervention record:** none`), one hole (mechanical-fix round, no record, no exemption) — asserting exactly the hole is flagged; plus the existing repo-clean self-check stays green (or is reconciled if the live tree has a real hole — see Phase 4).

**Minimum Verifiable Behavior:** `python3 user/scripts/doc-drift-lint.py --repo-root .` runs the new check; on the fixture with a hole it reports the missing `harden-<YYYY-MM>-rN.md` and exits 1.

**Runtime Verification** *(checked by test/manual):*
- [ ] <!-- verification-only --> `doc-drift-lint.py` over a fixture hardening-log with a deliberate hole prints a coverage finding naming the round + expected record path and exits 1; over the all-covered/exempt fixture it is clean (exit 0).

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** None structurally (independent of Phases 1-2), but ordered here so Phase 4's data repair can be verified against a working lint. May be implemented in parallel with Phases 1-2 (disjoint files).

**Files likely modified:**
- `user/scripts/doc-drift-lint.py` — new `check_intervention_coverage` + `run_checks` registration.
- `user/scripts/test_doc_drift_lint.py` — three-round coverage fixture.
- `user/skills/lazy-batch/SKILL.md` (+ `lazy-bug-batch`, coupled) — §1c.6 flush prose adds the fail-open coverage-lint call.

**Testing Strategy:** hermetic fixtures in `test_doc_drift_lint.py` (the linter's established pattern). Because `doc-drift-lint.py` carries a self-check asserting THIS repo is clean, the live tree must be coverage-clean by end of Phase 4 (r1-r3 recorded, r5/r7 valid) or the self-check documents the known holes — reconcile in Phase 4.

**Integration Notes for Next Phase:** The coverage lint will FLAG the live r1-r3 holes (pre-contract rounds, never backfilled) the moment it runs against the real tree. Phase 4 closes those holes so the repo-clean self-check passes.

---

### Phase 4: Data repair — re-declare r5/r7, backfill r1-r3 (D4, D5)

**Scope:** Fix the existing poisoned/missing records so the ledger is gradeable and the Phase-3 coverage lint passes against the live tree. Re-declare r5/r7's vocabulary-invalid targets onto real vocabulary (explicit act, never a silent edit); record r1-r3 (pre-contract mechanical rounds) explicitly so the coverage lint sees a record, not a hole.

**Deliverables:**
- [ ] r5 re-declaration: change `harden-2026-07-r5.md` `target_signal` from the invalid `event:no-route` to the closest real event today (or explicit `undeclared` if no real signal fits), via a deliberate documented re-declaration (mirror D3 of the split-brain sibling — record the act, e.g. a `## Re-declaration <date>` note or commit body). Baseline re-frozen honestly.
- [ ] r7 re-declaration: same for `harden-2026-07-r7.md` (`event:route-loop` → real vocabulary or explicit `undeclared`).
- [ ] r1-r3 backfill: create `harden-2026-07-r1.md`, `-r2.md`, `-r3.md` via the D9 manual path (`--record-intervention --shipped-commit <sha> --shipped-date <date>` → `provenance: backfilled`), each with a measurable `--target-signal` where one exists (r3 was `event:process-friction`-flavored; r1/r2 per their commits) or explicit `--target-signal undeclared` for the genuinely-immeasurable.
- [ ] Cross-reference note: the poisoned r14-r21 re-baselining belongs to the split-brain sibling (`interventions-telemetry-repo-scope-split-brain`), NOT here — record that boundary in this dir's Implementation Notes so it is not double-fixed.
- [ ] Verify: `doc-drift-lint.py --repo-root .` (Phase 3) is coverage-clean over the live tree after the repair.

**Minimum Verifiable Behavior:** after the repair, `python3 user/scripts/doc-drift-lint.py --repo-root .` reports zero intervention-coverage findings, and `grep target_signal docs/interventions/harden-2026-07-r5.md docs/interventions/harden-2026-07-r7.md` shows only valid-vocabulary (or explicit `undeclared`) targets.

**Runtime Verification** *(checked by test/manual):*
- [ ] <!-- verification-only --> Post-repair `doc-drift-lint.py --repo-root .` exit 0 on the intervention-coverage check (live tree); r1/r2/r3 records exist and validate against the Phase-1 vocabulary.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phase 1 (vocabulary validator — the re-declared targets must be valid), Phase 2 (the D9 backfill CLI now enforces the vocabulary), Phase 3 (the coverage lint to verify against).

**Files likely modified:**
- `docs/interventions/harden-2026-07-r5.md`, `-r7.md` — re-declared targets + re-declaration note.
- `docs/interventions/harden-2026-07-r1.md`, `-r2.md`, `-r3.md` — net-new backfill records.
- `IMPLEMENTATION_NOTES` / this PHASES.md — the r14-r21 boundary cross-reference.

**Testing Strategy:** the repair is verified by the Phase-3 coverage lint going clean over the live tree and by the Phase-1 validator accepting the re-declared targets. No new unit test (data act), but the `doc-drift-lint.py` repo-clean self-check now transitively covers it.

**Integration Notes for Next Phase:** With the data clean, Phase 5 updates the skill prose to describe the now-mechanical contract and runs the full gate sweep.

---

### Phase 5: harden-harness prose update + re-projection + full gate sweep

**Scope:** Update `harden-harness/SKILL.md`'s Step-4 capture prose to state the now-mechanical contract (vocabulary reject, hardening hard-fail, explicit-`undeclared` escape hatch, coverage lint at run-end), re-project skills, and run the full gate sweep so the whole change lands coherent.

**Deliverables:**
- [ ] `harden-harness/SKILL.md:311-332` prose: replace the "prose-only ALSO capture" framing with the mechanical contract — an unknown `event:` type is rejected at the CLI (name the valid set), an undeclared hardening capture is refused unless `--target-signal undeclared` is passed explicitly, and the round↔record coverage is now lint-enforced (runs standalone + at `--run-end`, fail-open).
- [ ] Re-project + lint: `python3 ~/.claude/scripts/project-skills.py` then `python3 ~/.claude/scripts/lint-skills.py` — both clean.
- [ ] Full gate sweep: `test_lazy_core.py`, `test_doc_drift_lint.py`, `lazy-state.py --test`, `bug-state.py --test`, `lazy_parity_audit.py --repo-root .` — all green.
- [ ] `doc-drift-lint.py --repo-root .` — clean (incl. the new coverage check + the repo-clean self-check).

**Minimum Verifiable Behavior:** `python3 ~/.claude/scripts/lint-skills.py` is clean and the full gate sweep (the five commands above) all pass.

**Runtime Verification** *(checked by test/manual):*
- [ ] <!-- verification-only --> The full gate sweep passes: `test_lazy_core.py` green, `test_doc_drift_lint.py` green, both `--test` harnesses OK, `lazy_parity_audit.py` exit 0, `doc-drift-lint.py` exit 0.

**MCP Integration Test Assertions:** N/A.

**Prerequisites:** Phases 1-4 (the prose describes their shipped behavior; the gates cover them all).

**Files likely modified:**
- `user/skills/harden-harness/SKILL.md` — Step-4 capture-contract prose.
- `skills-projected/**` — regenerated (not hand-edited).

**Testing Strategy:** the gate sweep IS the test. `lint-skills.py` catches broken injections; `lazy_parity_audit.py` guarantees the Phase-2 coupled-pair mirror stayed in lockstep; `doc-drift-lint.py`'s self-check confirms the whole repo is coherence-clean.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md/PHASES.md `**Status:**` and writes `FIXED.md` once the bug's serving-path regression evidence (the Phase 1-3 tests reproducing the original symptoms — silently-accepted bad vocabulary, ungradeable undeclared record, missing-round hole) is green. Do NOT author a status-flip or receipt checkbox row.

---

## Cross-feature Integration Notes

No hard deps on Complete upstreams (this is a standalone claude-config bug). Sibling relationships (prose SSOT in SPEC `**Related:**`, not machine deps):
- `interventions-telemetry-repo-scope-split-brain` (archived) — owns the r14-r21 re-baselining; this bug must NOT touch those records (Phase 4 records the boundary).
- `efficacy-future-check-unenforced-orchestrator-prose` (fixed `7d49490`) and `no-mid-run-observed-friction-harden-dispatch` (fixed `c46ed80`) — their D2/§6 made the dispatch PROMPT for a measurable signal; this bug adds the mechanical VALIDATION that prompt lacks. Complementary, no code overlap.
