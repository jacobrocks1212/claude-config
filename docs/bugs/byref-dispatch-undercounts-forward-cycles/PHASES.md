# Implementation Phases — By-ref dispatch undercounts forward_cycles

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure Python state-machine logic in `lazy_core.py` / `lazy-state.py` / `bug-state.py`; no Tauri/MCP/app surface. Validation is the hermetic in-file `--test` smoke harness + `test_lazy_core.py`, not the dev runtime. (This bug is harness-internal: there is no AlgoBooth app behavior to drive through MCP.)

## Validated Assumptions

All load-bearing assumptions here are **code-provable** (state-machine logic, pure functions, registry census arithmetic) — no runtime spike required. Confirmed against source during the touchpoint audit:

- **A1 — The real-skill probe path advances forward cycles ONLY via `advance_run_counters`.** `lazy-state.py` L6647-6648: `if args.repeat_count: lazy_core.advance_run_counters(state)` — no `advance_forward_cycle` call on this path. (Contrast: the `--apply-pseudo` path at L6546-6552 DOES call `advance_forward_cycle`.) Grounds the Phase 1 wiring gap.
- **A2 — `advance_forward_cycle` is consume-independent and monotonic-per-state-change.** `lazy_core.py` L7793-7861: gates on `last_advance_state_key == [feature_id, current_step, sub_skill]` (a JSON list), advances on a tuple change, idempotent on a re-fire, marker-gated. It does NOT read `consumed_emission_count()`. Confirmed it is the robust trigger the SPEC's Fix Scope item 1 names.
- **A3 — `consumed_emission_count()` is a non-monotonic live census.** `lazy_core.py` L7210-7232: `sum(1 for e in entries if e.get("consumed"))` over the LIVE registry; the ring cap (`_REGISTRY_RING_CAP = 64`, L5209) evicts the oldest entry on overflow (`register_emission` L7309), so the census plateaus/drops once cumulative emissions exceed 64. Grounds Contributor B.
- **A4 — `advance_meta_cycle` writes `last_advance_consume_count = consumed_emission_count() + 1`.** `lazy_core.py` L7771: the unconditional `+1` over-absorb. Grounds Contributor A.
- **A5 — `bug-state.py` inherits the advance logic via shared `lazy_core`.** It imports `lazy_core` and carries the same `--repeat-count` / `--apply-pseudo` handler sites; the fix must keep BOTH `lazy-state.py --test` and `bug-state.py --test` green.

## Touchpoint Audit (verified — Step C)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy-state.py` | yes | `--repeat-count` advance site L6647-6648 (`advance_run_counters` only); `--apply-pseudo` advance site L6546-6552 (`advance_forward_cycle`) | refactor | Add an `advance_forward_cycle(state)` call at the `--repeat-count` site, mirroring the `--apply-pseudo` wiring (reuse the SAME helper; do NOT write a new advance fn). Reconcile with the existing `advance_run_counters` call so a single real cycle is not double-counted. |
| `user/scripts/lazy_core.py` | yes | `advance_run_counters` L7664, `advance_forward_cycle` L7793, `advance_meta_cycle` L7746, `consumed_emission_count` L7210, `_REGISTRY_RING_CAP=64` L5209, ring eviction L7309 | refactor | Reuse `advance_forward_cycle` as-is for the forward count. Harden the consume watermark (Phase 2): clamp `last_advance_consume_count` so `advance_meta_cycle`'s `+1` and ring-cap eviction cannot permanently strand the gate. |
| `user/scripts/bug-state.py` | yes (parity via shared `lazy_core`) | imports `lazy_core`; same `--repeat-count` / `--apply-pseudo` handler sites | refactor | Mirror the `lazy-state.py --repeat-count` site change verbatim (parity is audited by `lazy_parity_audit.py`). |
| `user/scripts/test_lazy_core.py` | yes | `test_advance_forward_cycle_*` L18692+, `test_advance_run_counters_consume_gated` L12334, `test_registry_ring_cap` L12071, `test_fold_and_advance_run_counters` L12222 | create (extend) | New long-run / ring-cap-crossing fixture (≥65 emissions + interleaved meta) asserting `forward_cycles` keeps advancing per real-skill state change. Reuse the `_simulate_dispatch_consume()` / `register_emission` / `consume_nonce` patterns already in `test_fold_and_advance_run_counters`. |
| `user/skills/lazy-batch/SKILL.md` | yes | HARD CONSTRAINT 8 (~L87), Step 1c cap (~L441) | none (consumer) | No SKILL change — the fix is script-side; the cap it enforces becomes correct once `forward_cycles` advances monotonically. |
| `user/scripts/CLAUDE.md` | yes | "Cycle-counter advance: two orthogonal triggers" section | refactor (docs) | Update the contract prose: trigger 2 (`advance_forward_cycle`) is now ALSO wired into the `--repeat-count` real-skill probe path, not only `--apply-pseudo`. |

No contradictions surfaced — every SPEC line reference resolved to the real symbol. The one deferred design choice (SPEC Open Questions) is internal-mechanical (same product behavior); resolved in-plan below.

⚖ policy: retire-vs-keep advance_run_counters → KEEP both, reconcile (additive, lowest-risk)

The SPEC's Open Question — RETIRE `advance_run_counters` from forward-advance duty entirely vs. KEEP both with a reconciliation guard — is scope-class (D7): both reach the identical product behavior (`forward_cycles` advances monotonically, once per real cycle). This plan takes the more conservative KEEP-both path: wire `advance_forward_cycle` as the authoritative forward trigger on the real-skill path, and have `advance_run_counters` no longer own forward-advance on that path (its consume-gate is reduced to a harmless no-op / debounce, never the freeze authority). This is additive — it does not delete the existing consume-gated path or its tests, so the blast radius stays minimal and the ISSUE-5 inflation regression net is preserved.

## Cross-feature Integration Notes

(No `**Depends on:**` block in the SPEC — this is a harness-internal defect with no upstream feature deps. The prior fixes it builds on — ISSUE-5 consume-gating 2026-06-14, Fix-A `advance_forward_cycle` 2026-06-17 — are already landed in `lazy_core.py`, not pending upstreams.)

---

### Phase 1: Wire the monotonic state-change advance into the real-skill probe path

**Scope:** Make real-skill (by-reference) dispatch cycles advance `forward_cycles` via the consume-INDEPENDENT `advance_forward_cycle` (the `[feature_id, current_step, sub_skill]` state-change trigger) instead of depending exclusively on the non-monotonic `advance_run_counters` consume oracle. This is the SPEC Fix Scope item 1 (the primary fix) and defeats BOTH contributors at once: once the forward advance no longer reads `consumed_emission_count()`, neither the `advance_meta_cycle` `+1` over-absorb (A) nor ring-cap census regression (B) can freeze the counter.

**Deliverables:**
- [x] In `lazy-state.py`, at the `--repeat-count` dispatch-bound probe site (~L6647), call `lazy_core.advance_forward_cycle(state)` so a real-skill cycle advances on its `[feature_id, current_step, sub_skill]` change — mirroring the existing `--apply-pseudo` wiring at ~L6546-6552. The `state` dict already carries `feature_id` / `current_step` / `sub_skill` (compute_state output).
- [x] Reconcile with the existing `advance_run_counters(state)` call so a single real cycle is NOT double-counted: `advance_forward_cycle` becomes the authoritative forward-advance trigger on this path. Per the ⚖ KEEP-both decision, retain `advance_run_counters` only as a debounce/no-op (it must not also advance `forward_cycles` for the same state change). Document the reconciliation inline (which trigger owns the forward count on the probe path, and why the other no longer double-counts).
- [x] Mirror the identical change into `bug-state.py`'s `--repeat-count` handler (parity is mandatory — `lazy_parity_audit.py` audits the two scripts' advance wiring).
- [x] Tests: extend `test_lazy_core.py` (or the in-file `--test` harness) with a fixture proving a real-skill state change advances `forward_cycles` WITHOUT a consume increment on the probe path (the exact gap — a real cycle whose consume the census no longer reflects still advances).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both pass, including a new/updated fixture where a real-skill `--repeat-count` probe with a changed state tuple and a FROZEN `consumed_emission_count()` still advances `forward_cycles` by exactly 1.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python3 user/scripts/lazy-state.py --test` exits 0 and matches `tests/baselines/lazy-state-test-baseline.txt` (regenerate the baseline only via the `_normalize_smoke_output` helper if the fixture set legitimately changed).
- [ ] <!-- verification-only --> `python3 user/scripts/bug-state.py --test` exits 0 and matches `tests/baselines/bug-state-test-baseline.txt`.

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior in this phase (pure Python state-machine wiring; verified by hermetic `--test` fixtures, not MCP).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — add `advance_forward_cycle(state)` at the `--repeat-count` site (~L6647); reconcile with `advance_run_counters`.
- `user/scripts/bug-state.py` — mirror the same change in its `--repeat-count` handler.
- `user/scripts/lazy_core.py` — only if the reconciliation needs a shared-helper tweak (prefer keeping `advance_forward_cycle` unchanged — reuse it as-is).
- `user/scripts/test_lazy_core.py` — new fixture for the real-skill no-consume advance.

**Testing Strategy:** Hermetic temp-dir fixtures (the established `_set_state_dir` / `write_run_marker` / `register_emission` / `consume_nonce` harness). Assert forward advance occurs on a state-tuple change with a frozen census; assert idempotence on a re-fire (no double-count). Run the FULL set after the change: `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`, `lazy_coord.py --test`.

**Integration Notes for Next Phase:**
- After Phase 1 the forward count no longer DEPENDS on the consume census — so Phase 2's hardening is defense-in-depth, not the primary fix. Sequence Phase 2 after Phase 1 so the regression fixture in Phase 3 can assert the primary fix alone already keeps the counter advancing across the ring cap.
- The reconciliation decision (which trigger owns forward-advance on the probe path) is the load-bearing detail Phase 3's long-run fixture exercises — record exactly how `advance_run_counters` and `advance_forward_cycle` co-exist on this path in the `lazy-state.py` inline comment.

#### Implementation Notes (Part 1 / Phase 1 — 2026-06-19)

**Status:** Implementation complete (validation tail pending — top-level Status stays In-progress; `__mark_fixed__` is orchestrator-owned).

**Reconciliation form chosen: form 1 (replace, not keep-both-guarded).** At the `--repeat-count` real-skill probe site in BOTH `lazy-state.py` (was L6648) and `bug-state.py` (was L4537), the consume-gated `lazy_core.advance_run_counters(state)` call was **replaced** with `lazy_core.advance_forward_cycle(state)`. `advance_forward_cycle` is now the sole, authoritative forward-advance trigger on the by-reference probe path; it keys on the consume-INDEPENDENT `[feature_id, current_step, sub_skill]` state change, so a by-ref dispatch that does not bump the consume census (the frozen-census / Theory-1b case) still advances `forward_cycles`. `advance_run_counters` no longer runs on this path at all, so there is no double-count and no residual dependence on the non-monotonic `consumed_emission_count()` oracle. Meta accounting via `--emit-dispatch` / `advance_meta_cycle` is untouched. Form 1 was preferred over the plan's PHASES-level KEEP-both prose because nothing on this probe path required a meta-accounting side effect uniquely provided by `advance_run_counters`; the inline code comment at each site records this. (Note: this supersedes the PHASES "⚖ KEEP-both" line — the plan's WU-1 explicitly authorized form 1 as the default when no unique side effect is lost; both forms yield identical product behavior, so this is scope-class.)

**Files modified:**
- `user/scripts/lazy-state.py` — `--repeat-count` block: `advance_run_counters` → `advance_forward_cycle` + reconciliation comment (WU-1).
- `user/scripts/bug-state.py` — `--repeat-count` block: identical verbatim mirror (WU-2).
- `user/scripts/test_lazy_core.py` — two new CLI-driving wiring-regression tests: `test_repeat_count_real_skill_frozen_census_advances_forward` (feature path) and `..._bug_state` (bug parity). Both drive the real `--repeat-count` subprocess over a temp repo at the `execute-plan` step with a marker present and a FROZEN census, asserting `forward_cycles` advances to 1 (RED pre-fix: stayed 0) and is idempotent on re-fire (WU-3).

**Gate results (all green):** `lazy-state.py --test`, `bug-state.py --test`, `pytest test_lazy_core.py` (571 passed), `lazy_coord.py --test`, `lazy_parity_audit.py --repo-root .` (exit 0). Byte-pinned `--test` baselines were NOT touched (WU-3 added pytest fixtures, not in-file `--test` fixtures — as the plan anticipated).

**Review verdict:** PASS — inline review (2 source sites + 1 test file, form-1 replacement is mechanical and verified by the RED→GREEN of the new wiring tests; the helper itself was already characterized by the pre-existing `test_advance_forward_cycle_*` suite).

**Deferred to Part 2:** the `user/scripts/CLAUDE.md` "two orthogonal triggers" prose update is scheduled in Part 2 (Phase 3) per the plan — NOT edited in this part.

---

### Phase 2: Harden the consume watermark against the non-monotonic oracle (defense-in-depth)

**Scope:** Even though Phase 1 removes the consume census from forward-advance duty, the watermark machinery (`advance_meta_cycle`'s `+1`, `advance_run_counters`'s `last_advance_consume_count` gate) still reads a non-monotonic oracle and could strand other consumers. Make the watermark robust so a one-time downward step (ring-cap eviction) or the meta `+1` over-absorb can never PERMANENTLY strand the gate. This is SPEC Fix Scope item 2.

**Deliverables:**
- [x] In `lazy_core.py`, clamp `last_advance_consume_count` so it never exceeds the live `consumed_emission_count()` it was last observed against — i.e. when `advance_run_counters` (or `advance_meta_cycle`) writes the watermark, store `min(intended_watermark, current_live_census)` OR, equivalently, make the gate compare defensively so a census that has dropped below the persisted watermark re-arms rather than strands. Pick the clamp form that keeps the ISSUE-5 inflation fix intact (the gate must still no-op a bare re-probe). Document the chosen invariant in the function docstring. **DONE — re-arm-on-drop clamp (see Implementation Notes for the chosen form).**
- [x] Re-evaluate `advance_meta_cycle`'s unconditional `+1` (L7771): keep the absorb of the meta dispatch's own forthcoming consume, but ensure it cannot ratchet the watermark permanently past the live count when meta dispatches outpace forward consumes (Contributor A). The clamp above should subsume this; if not, bound the `+1` to the live census. **DONE — `+1` retained (load-bearing for no-double-count); the census-drop clamp subsumes its permanent-strand tail; docstring updated.**
- [x] Update the `consumed_emission_count` docstring (L7210) — its current note reasons only about the F2 double-probe debounce, NOT the run-lifetime `last_advance_consume_count` watermark. Add the caveat that a one-time downward census step is now clamped, so the watermark cannot strand. **DONE.**
- [x] Tests: a fixture where the census is forced DOWN below the persisted watermark (simulating ring-cap eviction of consumed entries) and asserts the watermark does not permanently strand any consumer that still reads it. **DONE — `test_advance_run_counters_census_regression_does_not_strand` (RED pre-clamp, GREEN post; ISSUE-5 inflation invariant re-asserted in the same fixture).**

**Minimum Verifiable Behavior:** A `test_lazy_core.py` fixture drives `consumed_emission_count()` below a previously-persisted `last_advance_consume_count` (by evicting consumed entries past the ring cap) and asserts the watermark/gate no longer strands — `--test` passes for both state machines.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both exit 0 with the hardening fixture green.

**MCP Integration Test Assertions:** N/A — pure Python census/watermark arithmetic; no app surface.

**Prerequisites:**
- Phase 1: the forward-advance no longer depends on the watermark, so this phase can change watermark behavior without risk of regressing the forward count (Phase 1's `advance_forward_cycle` is the forward authority).

**Files likely modified:**
- `user/scripts/lazy_core.py` — clamp logic in `advance_run_counters` / `advance_meta_cycle`; docstring updates on `consumed_emission_count`.
- `user/scripts/test_lazy_core.py` — census-regression fixture.

**Testing Strategy:** Hermetic fixtures that over-fill the registry past `_REGISTRY_RING_CAP` (64) with consumed entries, evicting older consumed entries so `consumed_emission_count()` drops, then assert the watermark clamp prevents a permanent strand. Keep the ISSUE-5 inflation regression (`test_advance_run_counters_consume_gated`) green — the clamp must NOT re-introduce inflation (a bare re-probe must still no-op).

**Integration Notes for Next Phase:**
- Phase 3's long-run fixture combines BOTH contributors (ring-cap crossing + interleaved meta). Phase 2's clamp is the safety net it asserts as secondary; the primary assertion (forward keeps advancing) is satisfied by Phase 1 alone. Author the Phase 3 fixture to assert BOTH: forward advances (Phase 1) AND the watermark never strands (Phase 2).

#### Implementation Notes (Part 2 / Phase 2 — 2026-06-19)

**Status:** Implementation complete (validation tail pending — top-level Status stays In-progress).

**Clamp form chosen: re-arm-on-drop (defensive gate), NOT min()-on-write.** In `advance_run_counters` (`lazy_core.py`), BEFORE the existing `current_consume <= prior_consume` no-op gate, a new guard fires: when `current_consume < prior_consume` (the live census has stepped strictly BELOW the persisted watermark — ring-cap eviction of consumed entries, Contributor B), the persisted watermark is stale, so `prior_consume` is clamped to `current_consume - 1`. That makes the very observation that crossed the eviction boundary re-advance EXACTLY ONCE (`current_consume > prior_consume` now holds), after which the gate resumes its normal strict-greater comparison. The re-arm-on-drop form was chosen over rewriting every watermark write to `min(intended, live_census)` because it is the minimal, single-site change and it provably preserves the ISSUE-5 inflation no-op: a bare re-probe with NO census change leaves `current_consume == prior_consume` (the equality branch, untouched) → no advance. Only a census that actually MOVED (rose normally, or dropped from eviction) can advance.

**`advance_meta_cycle` `+1`:** retained verbatim (load-bearing for the no-double-count invariant that `test_advance_meta_cycle_increments_meta` pins). Its only permanent-strand tail — meta dispatches outpacing forward consumes, then a later eviction dropping the census below the inflated watermark — is now subsumed by the `advance_run_counters` census-drop clamp. Docstring updated to record this.

**`consumed_emission_count` docstring:** extended with the NON-MONOTONIC CAVEAT — the live census steps down on ring-cap eviction, the run-lifetime watermark is now clamped against that one-time downward step, and the forward COUNT no longer depends on this oracle at all (Phase 1 routed it through `advance_forward_cycle`).

**Files modified:**
- `user/scripts/lazy_core.py` — `advance_run_counters` re-arm-on-drop clamp + comment (WU-1); `advance_meta_cycle` docstring note (WU-1); `consumed_emission_count` docstring caveat (WU-1).
- `user/scripts/test_lazy_core.py` — `test_advance_run_counters_census_regression_does_not_strand` fixture + `_TESTS` registration (WU-2).

**Gate results (all green):** `lazy-state.py --test` (exit 0), `bug-state.py --test` (exit 0), `lazy_coord.py --test` (exit 0), `lazy_parity_audit.py --repo-root .` (exit 0), `pytest test_lazy_core.py` (572 passed). Byte-pinned `--test` baselines NOT touched (WU-2 added a pytest fixture, not an in-file `--test` fixture).

**Review verdict:** PASS — inline review (single-site clamp + one fixture; the RED→GREEN of the new test pins the strand-fix, the in-fixture inflation re-assertion + the unchanged `test_advance_run_counters_consume_gated` pin that the clamp did not regress ISSUE-5).

---

### Phase 3: Long-run / ring-cap-crossing regression fixture

**Scope:** Add the regression net the current hermetic single-advance fixtures miss: a fixture simulating a long `/lazy-batch` run that CROSSES the 64-entry ring cap (≥65 emissions) with interleaved meta dispatches, asserting `forward_cycles` keeps advancing for each real-skill state change. This is SPEC Fix Scope item 3 — the fixture that would have caught this bug originally. Keep BOTH `lazy-state.py --test` and `bug-state.py --test` green (shared `lazy_core`).

**Deliverables:**
- [ ] Add a `test_lazy_core.py` fixture (`test_forward_cycles_survive_ring_cap_crossing_with_meta_interleave` or similar) that: writes a run marker; drives ≥65 emissions through `register_emission` + `consume_nonce` (crossing `_REGISTRY_RING_CAP`); interleaves meta dispatches (`advance_meta_cycle` calls) between real-skill cycles; advances real cycles via the Phase-1 probe path; and asserts `forward_cycles` advanced once per real-skill state change (NOT frozen at a plateau) — reproducing the SPEC's "stuck at 16 / frozen at 50" signature and proving it no longer occurs.
- [ ] Assert the dual property: forward count is correct (Phase 1) AND the consume watermark did not strand (Phase 2).
- [ ] Run the full smoke set and regenerate the byte-pinned baselines ONLY via the `_normalize_smoke_output` helper if (and only if) the `--test` fixture set legitimately changed: `tests/baselines/lazy-state-test-baseline.txt`, `tests/baselines/bug-state-test-baseline.txt`.
- [ ] Confirm `python3 user/scripts/lazy_parity_audit.py` (if it asserts advance-wiring parity) passes for the mirrored `bug-state.py` change from Phase 1.

**Minimum Verifiable Behavior:** The new long-run fixture FAILS against pre-Phase-1 code (forward freezes at a plateau once past the ring cap) and PASSES after Phases 1–2 (forward advances per real cycle across ≥65 emissions). `lazy-state.py --test`, `bug-state.py --test`, and `test_lazy_core.py` all exit 0.

**Runtime Verification** *(checked by integration test or manual testing — NOT by the implementation agent):*
- [ ] <!-- verification-only --> Full smoke set green: `python3 user/scripts/lazy-state.py --test`, `python3 user/scripts/bug-state.py --test`, `python3 -m pytest user/scripts/test_lazy_core.py`, `python3 user/scripts/lazy_coord.py --test` — all exit 0.
- [ ] <!-- verification-only --> Both byte-pinned baselines match (or were regenerated only via `_normalize_smoke_output`).
- [ ] <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py` passes (advance-wiring parity between `lazy-state.py` and `bug-state.py`).

**MCP Integration Test Assertions:** N/A — the entire deliverable is a hermetic test fixture + baseline regeneration; no app surface.

**Prerequisites:**
- Phase 1: the fixture asserts the primary fix (forward advances via state change).
- Phase 2: the fixture also asserts the watermark hardening (no strand).

**Files likely modified:**
- `user/scripts/test_lazy_core.py` — the long-run ring-cap-crossing fixture.
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — only if the in-file `--test` fixture set changed.
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — only if the in-file `--test` fixture set changed.
- `user/scripts/CLAUDE.md` — update the "Cycle-counter advance: two orthogonal triggers" section to note trigger 2 is now also wired into the `--repeat-count` real-skill path (docs parity with the code change).

**Testing Strategy:** The fixture is the deliverable. It must be RED against current code (proving it catches the bug) and GREEN after the fix. Cross-check that the ISSUE-5 inflation test and the existing `advance_forward_cycle` tests stay green — this fixture adds coverage, it does not replace them.

**Integration Notes for Next Phase:** None — terminal phase. After this phase lands, `bug-state.py` routes to `/mcp-test`; the validation tail / `__mark_fixed__` gate (orchestrator-owned) handles the terminal flip. Do NOT flip SPEC/PHASES top-level `**Status:**` to Fixed here.

---

## Phase Ordering Rationale

- **Phase 1 is the primary fix** (SPEC Fix Scope item 1) — it must land first because it removes the dependency on the non-monotonic oracle; everything else is defense-in-depth or verification on top of it.
- **Phase 2 hardens the watermark** (item 2) — sequenced after Phase 1 so the forward count is already safe (via `advance_forward_cycle`) before touching the consume-gate machinery, keeping the ISSUE-5 inflation regression net intact.
- **Phase 3 is the regression net** (item 3) — terminal, asserts both prior phases together against the exact long-run signature the original hermetic fixtures missed.

Each phase carries its own hermetic `--test` verification (verification distributed per-phase, not terminal-only). No phase introduces a new user-facing API surface (no reachability-smoke rows needed — this is internal harness logic with no MCP surface).
