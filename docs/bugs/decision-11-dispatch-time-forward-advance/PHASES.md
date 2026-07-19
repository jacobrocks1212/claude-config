# Implementation Phases — Decision 11: dispatch-time forward-advance (probe path becomes PEEK)

**Status:** In-progress

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP surface; this bug touches only Python state-script counter logic (`lazy_core.markers`), its unit-test harness, and a doc. The core mechanism already landed in `e91bd305`; the residual is deterministic (test retarget + dead-code removal + doc reconcile), verified by the `--test` harnesses + `lazy_parity_audit.py`, not by a live runtime.

## Validated Assumptions

All load-bearing assumptions here are **code-provable** (pure unit-test logic, dead-code removal, doc prose) — none are runtime-coupled, so the Step 2.7 runtime-validation gate is skipped by that rule. Ground truth confirmed by inline grep/read this planning cycle:

- `advance_forward_cycle(state, *, consume_gate=False)` lives at `markers.py:3299`; the `consume_gate` census-rise branch is at `markers.py:3378-3397, 3421-3422`. (verified — read)
- `consume_gate=True` has **zero production callers** — every reference is in `markers.py` (the def) or in `test_markers.py`. (verified — `grep -rn consume_gate user/scripts --include=*.py | grep -v tests` returns only the def + doc lines)
- The two pinned tests exist: `test_advance_forward_cycle_verbatim_real_skill_theory_1b` (`test_markers.py:5897`) and `test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` (`:5962`). A third consume_gate-only test — `test_advance_forward_cycle_consume_gate_default_off_preserves_freeze` (`:6027`) — is the "etc." the SPEC flags for drop. All three are registered in the module `TESTS` list (`:8685-8686`, plus the default-off entry). (verified — read)
- The live dispatch-time authority `advance_cycle_bracket_counter(cycle_marker)` (`markers.py:3220`, keyed on cycle-marker `kind` real/meta) is already wired at both `--cycle-end` handlers and is the mechanism the retargeted tests must assert. It is NOT modified by this bug. (verified — read)
- The existing new-behavior regression tests the SPEC binds this bug's completion to are present: `test_inject_hook_probe_on_non_dispatch_turn_does_not_advance_forward_budget` (`:6336`) and `test_cycle_end_real_bracket_advances_forward_and_per_feature` (`:6385`). (verified — read)
- The stale doc is `user/scripts/CLAUDE.md` §788 "Cycle-counter advance: two orthogonal triggers"; the stale claim ("ALSO the authoritative forward-advance on the `--repeat-count` real-skill probe path") is at lines 805-811. (verified — read)

## Touchpoint Audit (verified inline — dispatch unavailable-by-choice for a 3-file mechanical batch)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core/markers.py` | yes | `advance_forward_cycle(state, *, consume_gate=False)` @3299 (census-rise branch @3378-3397, 3421-3422); `advance_cycle_bracket_counter(cycle_marker)` @3220 | refactor | Remove the `consume_gate` keyword param and its census-rise second trigger; KEEP the `last_advance_state_key` state-change path (serves `--apply-pseudo`). Do NOT touch `advance_cycle_bracket_counter` — assert unchanged. |
| `user/scripts/tests/test_lazy_core/test_markers.py` | yes | pinned: `..._verbatim_real_skill_theory_1b` @5897, `..._consume_gate_advances_multicycle_same_step` @5962; consume_gate-only: `..._consume_gate_default_off_preserves_freeze` @6027; module `TESTS` registry @8685-8686 | refactor | Retarget the two pinned tests to assert dispatch-time advance via `advance_cycle_bracket_counter` (do NOT invert intent — each genuine dispatch bracket advances once); DROP the `consume_gate`-only default-off test; update the `TESTS` registry list to match. |
| `user/scripts/CLAUDE.md` | yes | §788 "Cycle-counter advance: two orthogonal triggers"; stale probe-path-advance text @805-811 | refactor | Reconcile: `advance_cycle_bracket_counter` at `--cycle-end` is the live budget authority; the `--repeat-count` probe path is a PEEK (no forward-advance). Keep the trigger-1/trigger-2 framing accurate to the post-`e91bd305` wiring. |

**Contradictions:** none. Every SPEC-cited line matched live code (anchor-grade — line numbers, no premise drift). No premise-grade contradiction; nothing demoted to a phase-time trace.

## Cross-feature Integration Notes

No hard deps on Complete upstreams (`**Depends on:**` is effectively `(none)` for this bug — its `**Related:**` cross-links are archived prior-art, not build dependencies). Section otherwise omitted.

---

### Phase 1: Retarget pinned tests to the dispatch-time bracket, retire the dead `consume_gate` trigger, reconcile the stale doc

**Status:** Complete

**Scope:** Complete the decision-11 residual now that `e91bd305` already landed the dispatch-time mechanism. Move the two pinned tests off the retired probe-path `advance_forward_cycle(consume_gate=…)` advance and onto the live `advance_cycle_bracket_counter` dispatch-time advance (preserving their intent: each genuine dispatch bracket advances `forward_cycles` exactly once, even at an unchanging `(feature_id, current_step, sub_skill)` tuple or a missed consume); delete the now-dead `consume_gate` parameter and its census-rise branch plus its `consume_gate`-only tests; and reconcile the stale `user/scripts/CLAUDE.md` description. No production advance code path changes behavior — `consume_gate=True` has no production caller, so removing it is pure dead-code retirement.

**These three deliverables are atomic** — the two pinned tests currently *call* `advance_forward_cycle(consume_gate=True)`, so the param cannot be removed without simultaneously retargeting them; they land in one change to keep the harness green.

**Deliverables:**
- [x] Retarget `test_advance_forward_cycle_verbatim_real_skill_theory_1b` (`test_markers.py:5897`) so it asserts a verbatim (consume-missed) real dispatch advances `forward_cycles` once per completed `--cycle-end` bracket via `advance_cycle_bracket_counter` (cycle-marker `kind: "real"`), NOT via `advance_forward_cycle(consume_gate=…)`. Preserve the encoded intent (a consume-missed real dispatch still advances exactly once).
- [x] Retarget `test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` (`test_markers.py:5962`) so it asserts a multi-part `/execute-plan` (same `(feature_id, current_step, sub_skill)` tuple across parts) advances `forward_cycles` once per completed `--cycle-end` real bracket via `advance_cycle_bracket_counter`. Rename it away from `consume_gate` to reflect the dispatch-time mechanism (e.g. `test_bracket_counter_advances_once_per_multicycle_same_step_bracket`) and keep intent (same-tuple multi-cycle still advances once per bracket).
- [x] Remove the `consume_gate` keyword-only parameter from `advance_forward_cycle` (`markers.py:3299`) and delete its census-rise second-trigger branch (`markers.py:3378-3397, 3421-3422`) and any now-unreferenced locals/docstring lines describing it. KEEP the `last_advance_state_key` state-change trigger intact — it still serves `--apply-pseudo` forward-advancing pseudo-skills.
- [x] Drop the `consume_gate`-only test(s) — at minimum `test_advance_forward_cycle_consume_gate_default_off_preserves_freeze` (`test_markers.py:6027`) — and remove their entries from the module `TESTS` registry list (`test_markers.py:8685-8686` and the default-off entry). Do NOT remove `test_advance_run_counters_consume_gated` (`:2728`) — that exercises the SEPARATE `advance_run_counters` consume-oracle path, out of scope here.
- [x] Reconcile `user/scripts/CLAUDE.md` §788 "Cycle-counter advance: two orthogonal triggers" (stale text at lines 805-811): state that `advance_cycle_bracket_counter` at `--cycle-end` is the live forward-budget authority for Agent dispatches and the `--repeat-count` probe path is a PEEK (no forward-advance) — removing the "ALSO the authoritative forward-advance on the `--repeat-count` real-skill probe path" claim while keeping the trigger-1 (consume-oracle) / trigger-2 (state-change, `--apply-pseudo`) framing accurate to the post-`e91bd305` wiring.
- [x] Tests: the retargeted pair above ARE the test deliverables (this is test-centric work); they must be RED against a hypothetical un-relocated mechanism and GREEN against the shipped `advance_cycle_bracket_counter`. The existing binders `test_inject_hook_probe_on_non_dispatch_turn_does_not_advance_forward_budget` and `test_cycle_end_real_bracket_advances_forward_and_per_feature` must remain GREEN and unmodified.

**Minimum Verifiable Behavior:** `python3 user/scripts/tests/test_lazy_core/test_markers.py` (or the repo test runner for that module) passes with the two retargeted tests present and the `consume_gate`-only test(s) removed; `grep -rn "consume_gate" user/scripts/lazy_core/markers.py` returns no `advance_forward_cycle` param/branch hits; `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior; claude-config has no MCP surface. Verification is the deterministic `--test` harness + parity audit named in Minimum Verifiable Behavior.

**Prerequisites:** None. The dispatch-time mechanism (`advance_cycle_bracket_counter` wired at both `--cycle-end` handlers) already shipped in `e91bd305`; this phase consumes it, does not build it.

**Files likely modified:**
- `user/scripts/lazy_core/markers.py` — remove the `consume_gate` param + census-rise branch from `advance_forward_cycle`; keep the state-change path; leave `advance_cycle_bracket_counter` untouched.
- `user/scripts/tests/test_lazy_core/test_markers.py` — retarget the two pinned tests to the bracket-counter mechanism; drop the `consume_gate`-only test(s); update the `TESTS` registry list.
- `user/scripts/CLAUDE.md` — reconcile the §788 "two orthogonal triggers" stale probe-path-advance description.

**Testing Strategy:**
Unit-level, fully deterministic. Run the `test_markers.py` module directly and confirm: (a) the two retargeted tests pass asserting `advance_cycle_bracket_counter` behavior; (b) the removed `consume_gate` test(s) are gone from both the file and the `TESTS` registry (no dangling reference); (c) the two existing binder tests still pass unchanged. Then run both state-script `--test` harnesses (`python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test`) and confirm their baseline outputs stay byte-stable (this change is test-file + dead-code + docs; no state-machine branch changes). Finally `lazy_parity_audit.py --repo-root .` must stay exit 0 (the change touches the shared `lazy_core.markers` surface both scripts import, and the `--cycle-end` bracket present on both).

**Integration Notes for Next Phase:**
- Terminal phase — no next phase. When this phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending) and let the state machine route to the validation tail. The top-level `Fixed` flip + `FIXED.md` receipt are gate-owned (`__mark_fixed__`), never authored here.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md/PHASES.md `**Status:**` to `Fixed` and writes `FIXED.md` after the validation tail passes — not a checkbox in this plan.

## Implementation Notes — Phase 1 (2026-07-19)

**Work completed (WU-1 + WU-2, executed INLINE — mechanical 3-file batch, zero Agent dispatches, test-first):**
- `user/scripts/lazy_core/markers.py` — removed the `consume_gate` keyword-only param from `advance_forward_cycle`, deleted both census-rise branches (the `if consume_gate:` census/clamp block and the `last_advance_consume_count` watermark write) and the docstring lines describing the retired trigger. The `last_advance_state_key` state-change path is preserved intact (still serves `--apply-pseudo`). `advance_cycle_bracket_counter` is byte-untouched. `grep consume_gate markers.py` → 0 hits.
- `user/scripts/tests/test_lazy_core/test_markers.py` — retargeted `test_advance_forward_cycle_verbatim_real_skill_theory_1b` to assert via `advance_cycle_bracket_counter` (real cycle marker) that a consume-missed real dispatch advances `forward_cycles` once per closed bracket; retargeted + renamed `test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` → `test_bracket_counter_advances_once_per_multicycle_same_step_bracket` (N real brackets at an unchanging tuple ⇒ `forward_cycles == N`); dropped `test_advance_forward_cycle_consume_gate_default_off_preserves_freeze` and updated the `TESTS` registry (renamed the retargeted entry, removed the dropped entry). Module suite: 220/220 pass. The two binder tests (`..._inject_hook_probe_...`, `..._cycle_end_real_bracket_...`) left unmodified and green; `test_advance_run_counters_consume_gated` (separate `advance_run_counters` oracle) untouched.
- `user/scripts/CLAUDE.md` §788 — removed the stale "ALSO the authoritative forward-advance on the `--repeat-count` real-skill probe path" claim; now states `advance_cycle_bracket_counter` at `--cycle-end` is the live dispatch-time budget authority for real Agent dispatches, `advance_forward_cycle` (state-change) serves ONLY `--apply-pseudo`, and the `--repeat-count` probe path is a PEEK (advances no forward budget). No `consume_gate` mention survives.

**Gotchas:** none. Pure dead-code retirement — `consume_gate=True` had zero production callers (only the two pinned tests + the retired one). Gates: `test_markers.py` 220/220, both state-script `--test` harnesses byte-stable, `lazy_parity_audit.py` exit 0, `lint-skills.py` clean (run at commit).
