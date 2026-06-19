# Implementation Phases — LOOP-DETECTED false positives from probe/reboot/resolution churn

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure harness state-machine fix in `user/scripts/lazy_core.py` and `user/skills/lazy-batch/SKILL.md`. There is no app surface, no Tauri/MCP-reachable behavior; validation is the in-file `--test` smoke harnesses (`lazy-state.py --test`, `bug-state.py --test`) plus `test_lazy_core.py`. Per `docs/features/mcp-testing/SPEC.md` this is the structurally-outside-MCP-reach class (harness tooling / no app integration).

## Scope summary

The investigation (SPEC.md, Status: Concluded) proved that **two of the three observed false-positive classes (symptoms 2 & 4) are already closed** by the landed F1/F2 consume-debounce, and the **sole residual defect is symptom 3 — the intervening-resolution class**: a needs-input resolution meta-cycle is an Agent dispatch, so it consumes a registry nonce, which defeats the F2 debounce's "no dispatch landed between the two probes" precondition. The HEAD-blind `step_repeat_count` therefore survives a *legitimately-resolved* blocker and keeps marching toward the LOOP-DETECTED tripwire.

The fix injects a **resolution-aware reset signal** that the counter honors — scoped exactly like the existing ordered-advance exemption (a narrow "genuine forward progress → reset to 1" branch), so the symptom-5 / d8 commit-masked-oscillation design constraint is preserved (no blanket HEAD/commit reset is added).

⚖ policy: discriminator locus (Open Question 1) → persisted marker-field signal (most-complete, deterministic), NOT probe-time inference. The two options are mechanical-internal (SPEC: "both yield identical product behavior, differing only in implementation locus"), so per D7 I take the more complete path in-cycle: the resolution meta-cycle persists an explicit signal the counter keys on, rather than the counter re-inferring "was the prior cycle a resolution?" from cleared-sentinel state at probe time. Persisted-signal is deterministic and mirrors the existing `last_advance_*` marker-field pattern; probe-time inference is racy (the sentinel may already be neutralized/renamed by the time the next probe reads). `/write-plan` may refine the exact field name; the *shape* (persisted signal, not inference) is the locked recommendation.

## Affected Area (from SPEC)

| Component | Files | Phase |
|-----------|-------|-------|
| Counter authority | `user/scripts/lazy_core.py` (`update_repeat_counts`, ~3514–3826) | Phase 2 |
| Resolution dispatch | `user/skills/lazy-batch/SKILL.md` Step 1g (+ `/lazy-bug-batch` mirror) | Phase 2 |
| Regression fixtures | `user/scripts/test_lazy_core.py`, `lazy-state.py --test` / `bug-state.py --test` baselines | Phase 1 + Phase 3 |

---

### Phase 1: Regression-confirm symptoms 2 & 4 hold under the landed F1/F2 debounce (no fix code)

**Scope:** Symptoms 2 & 4 are PROVEN already-fixed (Proven Finding 1). This phase produces the *regression-test deliverable* that locks that in — fresh fixtures that drive the exact double-probe / no-dispatch-between-probes scenarios (reboot re-probe, two `--repeat-count` probes for one cycle) through `update_repeat_counts` and assert the counters DO NOT inflate under the current debounce. No production code changes. Done first because it is independent, characterizes the current correct behavior before Phase 2 touches the function, and would catch any Phase-2 regression of the already-closed classes.

**Deliverables:**
- [ ] Fixture: two MARKED probes with the SAME step signature `(feature_id, current_step)` and UNCHANGED registry consume-count between them → assert `step_repeat_count` is HELD (symptom 2 — reboot re-probe with no dispatch).
- [ ] Fixture: two MARKED probes for one cycle with no consume between (probe-hygiene double-read) → assert neither `repeat_count` nor `step_repeat_count` inflates (symptom 4).
- [ ] Tests: both fixtures land in `user/scripts/test_lazy_core.py` alongside the existing `test_update_repeat_counts_debounce_*` characterizations, named to reference the symptom they pin (e.g. `test_symptom2_reboot_reprobe_no_inflation`, `test_symptom4_double_probe_hygiene_no_inflation`).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` passes with the two new fixtures present and green (run the command; the new test names appear in the run and pass). These exercise the real `update_repeat_counts` code path — no mock of the function under test.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/test_lazy_core.py` — add two regression fixtures.

**Testing Strategy:** Hermetic — each fixture builds a temp signature file + state dict and a stubbed/temp run marker (following the existing `test_update_repeat_counts_debounce_holds_step_count_no_consume_between` pattern), then asserts the returned counts. No production code under test changes, so these must be green against `HEAD` as-is before Phase 2 begins.

**Integration Notes for Next Phase:**
- These fixtures establish the BASELINE the Phase-2 reset must not regress: the no-dispatch-between-probes HOLD must keep working after the resolution-reset branch is added.
- The fixtures also document the consume-count oracle wiring (marker present + consumed_emission_count) that Phase 2's negative fixture (d8 still-trips) reuses.

---

### Phase 2: Add the resolution-aware `step_count` reset (the residual fix — symptom 3)

**Scope:** Close the sole residual gap. Two coordinated edits:
1. **Signal production** — the needs-input *resolution* meta-cycle (lazy-batch Step 1g `apply-resolution` dispatch, and the `/lazy-bug-batch` mirror) must surface a deterministic signal that the counter can key on, so the reset is driven by a recorded fact, not inferred at probe time. Per the ⚖ policy above, this is a **persisted marker field** (e.g. a `last_resolution_*` field on the run marker, written when the resolution meta-cycle is bracketed — the `--cycle-begin --kind meta` / resolution-dispatch site already exists and already carries `kind`).
2. **Signal consumption** — `update_repeat_counts` reads that signal and, when the prior cycle was a needs-input resolution AND the step signature `(feature_id, current_step)` is unchanged across it, RESETS `step_count` to 1 on the next probe — a new branch placed alongside the existing ordered-advance exemption (same "genuine forward progress → reset" shape, same guard discipline: only fires on a KNOWN/recorded prior so a missing/legacy signal can never spuriously reset the tripwire).

The reset is scoped to the resolution event SPECIFICALLY — it adds NO head/commit reset, so the d8 commit-masked oscillation case still trips (Proven Finding 3 / symptom-5 design constraint preserved).

**Deliverables:**
- [ ] `lazy_core.py`: persist the resolution signal (marker field) at the resolution meta-cycle bracket site, written deterministically when a needs-input resolution dispatch is begun; cleared/not-reasserted on ordinary cycles so it only fires once across the resolution.
- [ ] `lazy_core.py` (`update_repeat_counts`): new `step_count` reset branch keyed on the persisted resolution signal + unchanged step signature, ordered BEFORE the F2 debounce branch and AFTER the ordered-advance exemption; guarded on a recorded prior (never resets on a missing/legacy signal). Update the function docstring to document the third reset path next to the ordered-advance exemption.
- [ ] `user/skills/lazy-batch/SKILL.md` Step 1g: surface the signal-production step in the apply-resolution dispatch path (one persisted write at the resolution bracket), with the coupled mirror in `/lazy-bug-batch` per the SPEC's "(+ `/lazy-bug-batch` mirror)" — keep the coupled batch orchestrators in lockstep.
- [ ] Confirm Open Question 2 in-cycle: verify whether `repeat_count` (dispatch-tuple, HEAD-aware) ALSO needs the resolution reset, or whether a resolution that commits already advances HEAD → `repeat_count` resets on its own (SPEC: "Likely `step_repeat_count`-only"). Record the finding in this PHASES.md Implementation Notes; only add a `repeat_count` reset if a fixture proves it is exposed.
- [ ] Tests: positive resolution-reset fixture (symptom 3) and the docstring update land WITH the code (test-first per the execute-plan contract — the failing fixture is written before the reset branch).

**Minimum Verifiable Behavior:** A fixture reproducing symptom 3 — two probes with the SAME step signature, a DISPATCH (consume-count rises) landing between them via a resolution meta-cycle that sets the persisted signal — asserts `step_repeat_count` RESETS to 1 (pre-fix it increments). Run `python3 user/scripts/test_lazy_core.py`; the new symptom-3 fixture passes. This drives the real `update_repeat_counts` path end-to-end (signal field → reset branch).

**Runtime Verification** *(checked by the in-file smoke harnesses):*
- [ ] `python3 user/scripts/lazy-state.py --test` green (regenerate the byte-pinned baseline `tests/baselines/lazy-state-test-baseline.txt` ONLY via the `_normalize_smoke_output` helper if the marker-field addition legitimately changes output; the no-marker path must stay byte-identical). <!-- verification-only -->
- [ ] `python3 user/scripts/bug-state.py --test` green (bug pipeline inherits the shared `lazy_core` change; baseline regenerated only if legitimately changed, via the helper). <!-- verification-only -->

**Prerequisites:**
- Phase 1: the symptom-2/4 HOLD fixtures must be green first, so Phase 2 can prove it preserves them.

**Files likely modified:**
- `user/scripts/lazy_core.py` — resolution signal persistence + `update_repeat_counts` reset branch + docstring.
- `user/skills/lazy-batch/SKILL.md` — Step 1g signal-production step.
- `user/skills/lazy-bug-batch/SKILL.md` — coupled mirror of the Step 1g signal-production step.
- `user/scripts/test_lazy_core.py` — symptom-3 positive fixture.

**Testing Strategy:** TDD — write the symptom-3 fixture (RED), then add the signal field + reset branch (GREEN). Re-run the Phase-1 fixtures to confirm the no-dispatch HOLD still holds. Because the change is in shared `lazy_core`, run BOTH `lazy-state.py --test` and `bug-state.py --test` plus `test_lazy_core.py` (Coupling Rule — any `lazy_core` change keeps both suites green). Keep the lazy-batch ↔ lazy-bug-batch edits in lockstep (coupled pair).

**Integration Notes for Next Phase:**
- The reset branch ordering matters: ordered-advance exemption → resolution reset → F2 debounce → normal increment. Phase 3's negative fixture asserts the d8 case still falls through to increment (no reset path catches it).
- The persisted-signal shape (which marker field, when written, when cleared) is what Phase 3's "signal absent on an ordinary cycle" negative fixture pins — Phase 3 must read the field name Phase 2 settled on.

---

### Phase 3: Negative fixture — the d8 commit-masked oscillation loop STILL trips

**Scope:** Lock in the design constraint (Proven Finding 3 / symptom 5). Add the negative fixture that proves the resolution-reset added in Phase 2 did NOT re-introduce HEAD-advance immunity for the general oscillation case: a genuine commit-masked loop (each spurious cycle commits a file → HEAD advances → the dispatch-tuple `repeat_count` resets every iteration) with NO resolution signal set must STILL inflate `step_repeat_count` and trip the tripwire. Also pins that an ordinary (non-resolution) cycle with the signal ABSENT does not spuriously reset.

**Deliverables:**
- [ ] Fixture: repeated probes with the SAME step signature, HEAD advancing each iteration (commits landing), NO resolution signal present → assert `step_repeat_count` KEEPS INCREMENTING (d8 commit-masked loop still trips — the reset branch is NOT taken).
- [ ] Fixture: a marked probe with the resolution signal ABSENT and unchanged step signature → assert the reset branch is not taken (signal-gated, never fires on a missing/legacy signal — mirrors the ordered-advance "known prior" guard discipline).
- [ ] Tests: both negative fixtures in `test_lazy_core.py`, named to the constraint they protect (e.g. `test_symptom5_d8_commit_masked_loop_still_trips`, `test_resolution_reset_inert_without_signal`).

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` passes with the two negative fixtures green — `step_repeat_count` still climbs in the commit-masked case. Run the command; the negative test names appear and pass.

**Prerequisites:**
- Phase 2: the reset branch and the persisted signal field must exist (the negative fixtures assert the branch is correctly NOT taken, so they need its presence and the settled field name).

**Files likely modified:**
- `user/scripts/test_lazy_core.py` — two negative regression fixtures.

**Testing Strategy:** Hermetic, same temp-fixture pattern. The commit-masked fixture drives `_current_head` movement (distinct HEAD per probe) WITHOUT setting the resolution signal and asserts continued increment — the exact inverse of Phase 2's positive fixture, isolating the reset to the resolution event. Final gate: `lazy_coord.py --test`, `lazy-state.py --test`, `bug-state.py --test`, and `test_lazy_core.py` all green (the full shared-import set per `user/scripts/CLAUDE.md`).

**Integration Notes for Next Phase:**
- Terminal phase. On landing the last fixture, set this PHASES.md top-level `**Status:**` to `In-progress` (implementation done, validation pending) — the state machine routes the validation tail; the `__mark_fixed__` gate owns the terminal `Fixed` flip + FIXED.md receipt.

---

## Implementation Notes

- **Open Question 1 (discriminator locus)** — resolved in-cycle per D7 toward a **persisted marker-field signal** (see ⚖ policy at top). The resolution meta-cycle records the signal; `update_repeat_counts` consumes it. `/write-plan` may name the exact field; the shape is locked.
- **Open Question 2 (`repeat_count` exposure)** — deferred to Phase 2 confirmation. SPEC's stated likelihood is `step_repeat_count`-only (a resolution that commits advances HEAD → the HEAD-aware `repeat_count` already resets). Phase 2 confirms with a fixture before adding any `repeat_count` reset; finding recorded here.
- **Coupling:** `lazy_core.py` is shared by `lazy-state.py` + `bug-state.py` — both `--test` suites are the regression net (Coupling Rule, `user/scripts/CLAUDE.md`). `lazy-batch` ↔ `lazy-bug-batch` are a coupled pair for the Step 1g signal-production edit — mirror both.
