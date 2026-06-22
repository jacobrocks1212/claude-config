# Implementation Phases — Budget-guard defers a near-complete feature one validation cycle from done

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri app and no MCP server (per `.claude/skill-config/quality-gates.md` → "MCP exemption (Step 9)"). Validation is the repo's Python test + lint suite: `python -m pytest user/scripts/ -q`, `python user/scripts/lazy-state.py --test`, `python user/scripts/bug-state.py --test`, `python user/scripts/lazy_parity_audit.py --report`, `python user/scripts/project-skills.py`, `python user/scripts/lint-skills.py --check-projected --check-capabilities`.

## Scope decisions resolved at planning time (⚖ D7 — scope-class)

The SPEC's three Open Questions are scope-class (they pick implementation shape/generality, not user-visible product behavior; the operator already locked the *product* decision — "both grace + flush" + "broaden signal quality"). Resolved in-cycle toward the most complete path:

- ⚖ policy: define "near-complete" → reuse `remaining_unchecked_are_verification_only` + plan-part Complete + no BLOCKED.md (SPEC-recommended; keeps the grace gate consistent with the existing "ready to validate" predicate).
- ⚖ policy: composite-signal shape → discount validation-driven corrective cycles (option a) AND surface a composite trip signal (forward-cycles + validation-blocks + completion-distance), honoring the locked "broaden beyond the narrow case" scope.
- ⚖ policy: grace bound → exactly ONE grace cycle past the ceiling for a near-complete feature, then the guard re-asserts (a genuinely-stuck feature cannot exploit grace to monopolize).

## Affected scope (from SPEC)

Feature-pipeline only. `compute_per_feature_ceiling` / `budget_deferred` / `_DEFERRED_BUDGET` are referenced solely by `lazy-state.py` + `lazy_core.py` (grep-confirmed in the SPEC). `bug-state.py` has no per-feature ceiling, so this fix owes **no** coupled-pair mirror — a justified divergence to be confirmed against `lazy_parity_audit.py --report` in Phase 4. No `bug-state.py` edit is in scope.

---

### Phase 1: Near-completion predicate + corrective-cycle accounting (pure helpers, `lazy_core.py`)

**Scope:** Add the pure, side-effect-free predicates the trip site and flush will consult, characterized directly in `test_lazy_core.py` (no run marker, no state-machine wiring yet). This is the TDD seam: pure functions land first with red→green fixtures, then Phase 2 wires them in.

**Deliverables:**
- [x] `lazy_core.feature_is_near_complete(feature_dir, repo_root) -> bool` — True iff the feature is within one validation cycle of done: PHASES.md present AND `remaining_unchecked_are_verification_only(phases_text)` is True AND at least one plan part is `Complete` AND no `BLOCKED.md` on disk. Reuses the existing predicate (no re-implementation) so "near-complete" == the existing "ready to validate" definition. Tolerant of a missing PHASES.md / plans dir (returns False, never raises).
- [x] `lazy_core.count_validation_corrective_cycles(marker, feature_id) -> int` — read-only helper returning the count of forward cycles attributable to validation-driven corrective work for a feature, read from a new marker sub-map `per_feature_corrective_cycles: {feature_id: int}` (legacy/absent ⇒ 0, same tolerance pattern as `read_per_feature_forward_cycles`).
- [x] `lazy_core.record_corrective_cycle(marker, feature_id)` — increment `per_feature_corrective_cycles[feature_id]`; called at the apply-resolution / corrective-phase dispatch bracket (wired in Phase 2). Seeded as `{}` by `write_run_marker` (mirror the `per_feature_forward_cycles` seeding).
- [x] `lazy_core.budget_trip_signals(forward_count, corrective_count, ceiling, near_complete) -> dict` — the composite-signal evaluator returning `{should_defer: bool, effective_count: int, reason: str}`. `effective_count = forward_count - corrective_count` (discount validation-driven corrective work, option a, clamped ≥ 0); `should_defer` is True only when `effective_count >= ceiling` AND NOT `near_complete`. Pure — no marker I/O, no clock.
- [x] Tests: `test_lazy_core.py` fixtures for each helper, registered in `_TESTS` (the dead-coverage guard `test_no_orphaned_test_functions` FAILS any unregistered `def test_*`). Cover: near-complete true/false (verification-only vs an unchecked impl row; BLOCKED.md present; no plan-Complete), corrective-count legacy-0 + increment + seed-`{}`, composite `effective_count` clamp at 0, and the grace branch (`near_complete=True` ⇒ `should_defer=False` even when `effective_count >= ceiling`).

**Implementation Notes (2026-06-21):**
- Added four helpers to `user/scripts/lazy_core.py` right after `read_per_feature_forward_cycles` (~line 10198): `feature_is_near_complete`, `count_validation_corrective_cycles`, `record_corrective_cycle`, `budget_trip_signals`. Seeded `per_feature_corrective_cycles: {}` in `write_run_marker` in lockstep with `per_feature_forward_cycles`.
- 14 new fixtures in `test_lazy_core.py` (helper `_write_near_complete_feature_dir`), all registered in `_TESTS` (dead-coverage guard green). Red→green confirmed (14 failed → 14 passed).
- ⚖ refinement: `budget_trip_signals` `reason` adds a fourth honest label `under-ceiling` for the genuine below-ceiling, no-discount case so a normal under-budget feature is not mislabeled `corrective-discount`. The three plan-named reasons (`near-complete-grace`/`corrective-discount`/`over-ceiling`) are unchanged. No product-behavior change — `should_defer` is what the trip site branches on.
- `feature_is_near_complete` reads plan `status:` via a frontmatter line-scan (first `status:` line per file is authoritative), reusing `remaining_unchecked_are_verification_only` for the verification check (no re-implementation).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` runs and the new `_TESTS` entries pass green (the helpers are exercised directly — no state-machine path needed for this phase).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — four new helpers near `compute_per_feature_ceiling` / `read_per_feature_forward_cycles` (~10132–10198); `write_run_marker` marker seeding.
- `user/scripts/test_lazy_core.py` — new fixtures + `_TESTS` registrations.

**Testing Strategy:** Direct characterization of pure helpers via the manual `_TESTS` runner (hermetic, no run marker). The dead-coverage guard enforces registration.

**Integration Notes for Next Phase:**
- `budget_trip_signals` is the single decision point Phase 2 substitutes for the bare `_bg_count >= _bg_ceiling` check at `lazy-state.py:1738`.
- The grace bound is enforced by `near_complete` short-circuiting the defer — Phase 2 must still allow the *second* trip (a feature that's near-complete but already used its grace cycle should not loop forever; track via the existing `budget_deferred` count so grace is one-shot per feature per run).
- `per_feature_corrective_cycles` is a NEW marker sub-map; Phase 2 wires its increment. Keep the seed in `write_run_marker` lockstep with `per_feature_forward_cycles`.

---

### Phase 2: Wire the grace gate + corrective discount into the trip site (`lazy-state.py`)

**Scope:** Replace the bare ceiling comparison at the budget-guard trip with the composite `budget_trip_signals` decision, and increment the corrective-cycle counter at the corrective-dispatch bracket. The guard now grants one grace cycle to a near-complete feature before it can defer, and discounts legitimate validation-driven corrective cycles from the trip count.

**Deliverables:**
- [x] At `lazy-state.py` ~1737–1738, compute `near_complete = lazy_core.feature_is_near_complete(spec_path, repo_root)` and `corrective = lazy_core.count_validation_corrective_cycles(_bg_marker, feature_id)`, then branch on `lazy_core.budget_trip_signals(_bg_count, corrective, _bg_ceiling, near_complete)["should_defer"]` instead of the bare `_bg_count >= _bg_ceiling`.
- [x] Grace is one-shot: a near-complete feature is granted the grace cycle (no defer) ONLY while it has not already been deferred this run for budget (`_bg_deferred_counts.get(feature_id, 0) < 1`); once it has consumed grace, the normal trip/escalation applies (prevents an indefinitely-near-complete feature monopolizing). Add a `_diag` line announcing the grace grant.
- [x] Surface the grace decision + composite signals in the `_BUDGET_GUARD` probe metadata: add `effective_count`, `corrective_count`, and `near_complete_grace_granted` keys alongside the existing `count_at_trip` / `computed_ceiling` so the orchestrator's trip notification (and `--probe` consumers) reflect the new behavior. Keep existing keys byte-stable when the guard is absent.
- [x] Increment `per_feature_corrective_cycles` at the corrective-cycle bracket: the orchestrator's apply-resolution path already records a resolution signal (`--record-resolution-signal`); add a sibling marker-write (or fold into that handler) so a validation-failure-driven corrective dispatch is counted as corrective. Marker-gated + fail-open (a write error never breaks dispatch — mirror the existing `_bg_*` persist block at ~1912).

**Implementation Notes (2026-06-21):**
- WU-4 (trip site, `lazy-state.py` ~1737): replaced the bare `_bg_count >= _bg_ceiling` with `budget_trip_signals(...)`. `_bg_grace_eligible = near_complete AND prior_defers < 1` is passed as the `near_complete` arg, so the one-shot bound is enforced inside the signal (a grace-spent near-complete feature is treated as not-near-complete → trips). The grace branch emits a `_diag` and populates `_BUDGET_GUARD` with `action: "grace"` + `near_complete_grace_granted: True` so the dispatch surfaces in the probe. Trip-time `_BUDGET_GUARD` gained `effective_count`/`corrective_count`/`near_complete_grace_granted: False`; the marker-absent path is unchanged (no `budget_guard` key).
- WU-5 (corrective increment): folded into the `--record-resolution-signal` handler (the apply-resolution bracket IS the corrective bracket) — a sibling `record_corrective_cycle` + atomic marker persist, marker-gated (no-op when `record_resolution_signal` returns None) + fail-open `(OSError, ValueError)`.
- 4 new `--test` fixtures (f–i): grace dispatch at the ceiling, one-shot bound (grace-spent → trips), corrective discount (effective < ceiling → dispatch), and `record_corrective_cycle` wiring. Baseline `tests/baselines/lazy-state-test-baseline.txt` regenerated through `_normalize_smoke_output` (never by hand).

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` is green AND a new `--test` fixture reproduces the d2 incident: a feature at `forward=ceiling`, verification-only PHASES, plan-Complete, no prior budget defer ⇒ the probe dispatches the feature (grace granted) rather than appending it to `budget_deferred_skipped`.

**Runtime Verification** *(checked by the hermetic `--test` smoke harness):* <!-- verification-only -->
- [ ] `lazy-state.py --test` fixture: near-complete feature at the ceiling is dispatched (grace), not deferred. <!-- verification-only -->
- [ ] `lazy-state.py --test` fixture: near-complete feature that ALREADY consumed its grace this run (prior budget defer) IS deferred on the next trip (grace is one-shot). <!-- verification-only -->
- [ ] `lazy-state.py --test` fixture: a feature with `corrective=2`, `forward=ceiling+1` dispatches because `effective_count = forward - corrective < ceiling` (corrective discount). <!-- verification-only -->

**Prerequisites:**
- Phase 1: `feature_is_near_complete`, `count_validation_corrective_cycles`, `record_corrective_cycle`, `budget_trip_signals`, and the `per_feature_corrective_cycles` seed must exist.

**Files likely modified:**
- `user/scripts/lazy-state.py` — trip site (~1737–1797), `_BUDGET_GUARD` probe metadata (~1787–1795), corrective-counter increment at the corrective-dispatch bracket, marker-persist block (~1912).
- `user/scripts/test_lazy_core.py` — register any new direct fixtures (dead-coverage guard).

**Testing Strategy:** `lazy-state.py --test` fixtures pinned to the d2 reproduction; the byte-pinned baseline (`tests/baselines/lazy-state-test-baseline.txt`) is regenerated through `_normalize_smoke_output` (never by hand) since new fixtures change `--test` output.

**Integration Notes for Next Phase:**
- The grace gate prevents the FIRST-cycle defer of a near-complete feature, but a feature deferred *before* it became near-complete (e.g. tripped mid-implementation, then completed work on a re-entry) still needs the end-of-run flush — Phase 3 covers that safety net.
- The `_BUDGET_GUARD` probe now carries `near_complete_grace_granted`; the flush in Phase 3 reads near-completion at flush time (independent re-evaluation), not this flag.

---

### Phase 3: End-of-run resume flush for near-complete deferred features (`lazy-state.py`)

**Scope:** As the documented safety net, when the queue exhausts to only budget-deferred items, auto-resume any deferred feature that is *now* near-complete so it validates before the run terminates — rather than leaving it parked for a future run (and at risk of 2nd-trip eviction). Targets Theory 3 (no end-of-run resume flush).

**Deliverables:**
- [x] Before returning the `queue-exhausted-budget-deferred` terminal (`lazy-state.py:1937–1951`), re-scan `budget_deferred_skipped` for any feature where `lazy_core.feature_is_near_complete(spec_path, repo_root)` is True. If one exists, dispatch it (resume to validation) instead of returning the terminal — the deferred-because-budget state does not block a near-complete resume at end-of-run.
- [x] Surface the resumed feature in a `_diag` audit line and a probe field (`budget_resumed_near_complete: <feature_id>`) so the orchestrator reports the auto-resume.
- [x] If MULTIPLE deferred features are near-complete, resume them in queue order (one dispatch per probe — the next probe resumes the next). The terminal fires only when NO deferred feature is near-complete (the honest "all parked, none resumable" stop).
- [x] Evicted features (`_bg_evicted`) are NEVER auto-resumed (terminal eviction is intentional dead-lettering) — the flush considers deferred-only.

**Implementation Notes (2026-06-21):**
- Flush added at the top of the `current is None` block in `user/scripts/lazy-state.py` (~line 2022), BEFORE the `queue-exhausted-budget-deferred` terminal. Iterates `queue` IN ORDER, resumes the FIRST feature whose id is in this-probe `budget_deferred_skipped`, NOT in `_bg_evicted`, on-disk, and `lazy_core.feature_is_near_complete` is True — sets `current` to it (one resume per probe; `break`). Marker-gated (the whole guard is). Surfaced via a new `_BUDGET_RESUMED` module global → the `budget_resumed_near_complete` probe key in `_state()` (absent when no resume → byte-identical default output, same discipline as `budget_guard`/`gated_heads`).
- ⚖ policy: near-complete escalation reachability → trip site no longer evicts a near-complete feature. The Phase-2 one-shot grace means a near-complete feature with grace spent (`prior_defers>=1`) would otherwise escalate to `evict` and be unreachable by the flush (which excludes evicted). Added a surgical trip-site branch: when `_bg_action == "evict" and _bg_near_complete`, hold it as `defer` (never dead-letter a feature at the finish line) so the end-of-run flush can rescue it. Monopoly protection is UNCHANGED for NON-near-complete features (they still evict on the 2nd trip). This is the reconciliation that makes the flush genuinely reachable and the d2 incident's resume work end-to-end.
- 3 new `--test` fixtures (j/k/l) in the ncg block: (j) deferred-then-near-complete is auto-resumed (`budget_resumed_near_complete=feat-nc`, no terminal); (k) all-deferred-NOT-near-complete ⇒ `queue-exhausted-budget-deferred` still fires (terminal unchanged, no resume key); (l) an EVICTED near-complete feature is NEVER resumed. Baseline `tests/baselines/lazy-state-test-baseline.txt` regenerated through `_normalize_smoke_output` (one new print line; never by hand).

**Minimum Verifiable Behavior:** A `lazy-state.py --test` fixture where a feature was budget-deferred earlier in the run and is now verification-only/plan-Complete ⇒ the terminal probe dispatches it (`budget_resumed_near_complete` set) instead of returning `queue-exhausted-budget-deferred`.

**Runtime Verification** *(checked by the hermetic `--test` smoke harness):* <!-- verification-only -->
- [ ] `lazy-state.py --test` fixture: a deferred-then-near-complete feature is auto-resumed at flush (not left parked). <!-- verification-only -->
- [ ] `lazy-state.py --test` fixture: when all deferred features are NOT near-complete, `queue-exhausted-budget-deferred` still fires (terminal unchanged for the genuine case). <!-- verification-only -->
- [ ] `lazy-state.py --test` fixture: an evicted feature is never resumed by the flush. <!-- verification-only -->

**Prerequisites:**
- Phase 1: `feature_is_near_complete`.
- Phase 2: the grace gate (so the flush only handles features that were deferred BEFORE becoming near-complete — the two mechanisms are complementary, not redundant).

**Files likely modified:**
- `user/scripts/lazy-state.py` — the `current is None` budget terminal block (~1929–1951) gains a near-complete resume pre-pass.
- `user/scripts/test_lazy_core.py` — flush fixtures registered in `_TESTS`.

**Testing Strategy:** `lazy-state.py --test` flush fixtures; baseline regenerated through `_normalize_smoke_output`.

**Integration Notes for Next Phase:**
- All behavior change is feature-pipeline only; Phase 4 confirms the no-mirror divergence and runs the full gate set before completion.

---

### Phase 4: Parity confirmation, full-suite gate, and docs

**Scope:** Confirm the feature-only divergence carries no owed `bug-state.py` mirror, run the FULL claude-config gate set, and update the harness docs that describe the budget guard. No new behavior — this phase certifies the change and records it.

**Deliverables:**
- [ ] `python user/scripts/lazy_parity_audit.py --report` passes clean — confirm the budget-guard helpers (`feature_is_near_complete`, `budget_trip_signals`, corrective-cycle map) are recognized as a feature-pipeline divergence (no owed mirror), or register them as such if the audit expects an explicit divergence entry. (The SPEC asserts grep-confirmed feature-only scope; this phase is the certification.)
- [ ] Update `user/scripts/CLAUDE.md` — extend the `--per-feature-cycle-cap` / budget-guard CLI prose and the relevant section to document the near-completion grace gate, the corrective-cycle discount (`per_feature_corrective_cycles`), and the end-of-run near-complete resume flush.
- [ ] Update the root `CLAUDE.md` budget-guard description if it references the trip behavior (verify by grep first; edit only if a stale description exists).
- [ ] Re-run `python user/scripts/project-skills.py` and `python user/scripts/lint-skills.py --check-projected --check-capabilities` (no skill/component edits expected, but the gate doc requires the full set on feature completion).

**Minimum Verifiable Behavior:** The FULL gate set runs clean: `python -m pytest user/scripts/ -q` (incl. dead-coverage guard) + `lazy-state.py --test` + `bug-state.py --test` + `lazy_parity_audit.py --report` + `project-skills.py` + `lint-skills.py --check-projected --check-capabilities`.

**Runtime Verification** *(checked by the full quality-gate suite):* <!-- verification-only -->
- [ ] `python -m pytest user/scripts/ -q` green (dead-coverage guard included). <!-- verification-only -->
- [ ] `python user/scripts/lazy_parity_audit.py --report` green — no unexplained drift; feature-only divergence confirmed. <!-- verification-only -->
- [ ] `python user/scripts/bug-state.py --test` green — confirms no incidental `lazy_core` regression on the bug side (shared module). <!-- verification-only -->

**Prerequisites:**
- Phases 1–3 complete (the behavior is fully implemented and unit/smoke-green).

**Files likely modified:**
- `user/scripts/CLAUDE.md` — budget-guard prose.
- `CLAUDE.md` (root) — only if a stale budget-guard description exists.
- `user/scripts/lazy_parity_audit.py` — only if an explicit divergence registration is required.

**Testing Strategy:** Full quality-gate suite per `.claude/skill-config/quality-gates.md` "Mixed / feature completion" row. 100% pass required — no "preexisting" triage.

**Completion (gate-owned):** The SPEC/PHASES top-level `**Status:**` flip to `Fixed` and the `FIXED.md` receipt are owned exclusively by the orchestrator's `__mark_fixed__` validation tail — never authored as a checkbox here.

**Integration Notes for Next Phase:** Terminal phase — on completion the state machine routes to the validation tail (`/mcp-test` is N/A in this repo; the operator grants `SKIP_MCP_TEST.md` per the MCP-exemption clause once the quality gates pass).
