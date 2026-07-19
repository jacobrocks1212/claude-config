# Decision 11 — forward-advance moves to dispatch time (probe path becomes PEEK) — Investigation Spec

> Implement turn-routing-enforcement NEEDS_INPUT decision 11: `forward_cycles` must advance at the real dispatch bracket, never on the every-turn inject-hook `--repeat-count` probe. The core mechanism already landed (commit `e91bd305`); the residual is retargeting two pinned tests that still assert the retired probe-path advance, retiring the now-dead `consume_gate` trigger, and reconciling stale docs.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-07-18
**Placement:** docs/bugs/decision-11-dispatch-time-forward-advance
**Related:** `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` (decision 11 + decision 3, both RESOLVED 2026-07-18); `docs/bugs/_archive/lazy-run-marker-park-arm-and-forward-cycle-inflation/SPEC.md` (DEFECT 1, Concluded — origin symptom); `docs/bugs/_archive/byref-dispatch-undercounts-forward-cycles/` (decision-3 under-count origin); `docs/bugs/_archive/byref-forward-cycles-frozen-on-multicycle-same-step/` (origin of the two pinned tests); the `cycle-budget-counters-double-count-on-probes-and-inject-hook` fix (commit `e91bd305`, 2026-07-17) that pre-emptively landed this decision's mechanism.

<!-- Status lifecycle: Concluded → root cause traced, affected area understood; bug-state.py routes to /plan-bug. -->

---

## Verified Symptoms

<!-- This is the implementation of an operator-RESOLVED decision, not a mystery bug. The symptoms are the two SYMMETRIC counting catastrophes decision 11 names; both are documented, evidenced, and REPORTED from real runs (not independently reproduced in this cycle). -->

1. **[REPORTED — over-count]** After ONE real dispatch (`/execute-plan hydra-overlay`) the run marker showed `forward_cycles=3`, with `per_feature_forward_cycles = {hydra-overlay: 2, adhoc-hydra-sidecar-dist-esm-no-frames: 1}` — the never-dispatched bug counted 1. The increments line up 1:1 with `lazy-route-inject.sh` LAZY-ROUTE banner emissions on background-agent-completion NOTIFICATION turns (no dispatch). On a long overnight run this balloons `forward_cycles` and FALSE-hits `max_cycles`, ending the run early. Source: `NEEDS_INPUT.md` decision 11 (harden Round 55, AlgoBooth overnight `/lazy-batch 25 --park --park-provisional`). — DEFECT 1 of the archived `lazy-run-marker-park-arm-and-forward-cycle-inflation` bug.
2. **[REPORTED — under-count, mirror]** During the `algorithmic-fill-buffer` run `forward_cycles` STALLED at 2 across THREE consecutive by-ref `execute-plan` cycles (plan part-1/2/3, `cycle_header` read `fwd 2/10` each time) interleaved with meta dispatches, because `advance_meta_cycle`'s `+1` consume-absorb masked the next real by-ref dispatch's advance under the strict-greater consume gate. An unbounded under-count silently defeats `max_cycles` (run never halts). Source: `NEEDS_INPUT.md` decision 3.
3. **[VERIFIED — residual, this cycle]** Two pinned tests (`test_advance_forward_cycle_consume_gate_advances_multicycle_same_step`, `test_advance_forward_cycle_verbatim_real_skill_theory_1b`) still assert the RETIRED probe-path `advance_forward_cycle(consume_gate=…)` advance. `consume_gate=True` has ZERO production callers (grep-confirmed: only these two tests call it) — the tests are GREEN but characterize dead-in-production behavior, contradicting the operator's Option-1 resolution ("both oracles retired as forward-advance triggers on the probe path"). Confirmed by code read this cycle.

## Reproduction Steps

The over-count mechanism (symptom 1) as it existed BEFORE the mechanism fix:

1. Start a `/lazy-batch` run so a run marker is present (`forward_cycles` counter live).
2. Dispatch one real cycle (e.g. `/execute-plan`), then let a background-agent-completion NOTIFICATION turn fire (a UserPromptSubmit turn that changes the routed `(feature_id, current_step, sub_skill)` tuple but dispatches nothing).
3. On that notification turn the inject hook (`lazy_inject.py::_run_probe`) runs `--repeat-count --probe --emit-prompt`; the (pre-fix) `--repeat-count` handler called `lazy_core.advance_forward_cycle(state, consume_gate=True)`, which advances on `state_changed OR consume_rose`.
4. **Observed (pre-fix):** `state_changed` is true (route flipped) with NO consume → `forward_cycles` advances on a turn with no dispatch. Repeated notification turns balloon the counter → false `max_cycles` halt.

**Expected:** `forward_cycles` counts DISPATCHES; a notification/banner turn advances it by 0.
**Actual (pre-fix):** every notification turn whose route changed advanced `forward_cycles` by 1.
**Consistency:** systematic (notification turns are exactly the turns where the route changes without a this-turn dispatch).

**Current state (post-`e91bd305`):** the probe-path advance is REMOVED; a notification-turn probe advances `forward_cycles` by 0. The completion-gate for THIS bug binds to the existing regression test `test_inject_hook_probe_on_non_dispatch_turn_does_not_advance_forward_budget` (a notification-turn probe leaves the budget unchanged) plus `test_cycle_end_real_bracket_advances_forward_and_per_feature` (a completed real bracket advances exactly once), both already present.

## Evidence Collected

### Source Code

Three forward/meta advance functions exist in `user/scripts/lazy_core/markers.py`; the wiring determines which are LIVE:

- **`advance_cycle_bracket_counter(cycle_marker)`** (`markers.py:3220`) — "THE budget authority for bracketed Agent dispatches." Called at `--cycle-end` (`lazy-state.py:13347`, `bug-state.py:8885`) AFTER reading the cycle marker, BEFORE `clear_cycle_marker()`. Keyed on the cycle marker's `kind` (`real` → `forward_cycles` + per-feature sibling; `meta` → `meta_cycles`). Idempotent per bracket by construction (one `--cycle-begin`/`--cycle-end` bracket == one Agent dispatch; marker cleared immediately after). **This is the dispatch-time advance decision 11 mandates.**
- **`advance_forward_cycle(state, *, consume_gate=False)`** (`markers.py:3299`) — state-change–keyed (`last_advance_state_key`) advance, with an OR'd `consume_gate` census-rise second trigger. Called ONLY at `--apply-pseudo` (`lazy-state.py:13977`, `consume_gate` DEFAULT False) for forward-advancing inline pseudo-skills (`__mark_complete__` etc.) which dispatch no Agent and get no `--cycle` bracket. **The `consume_gate=True` branch has NO production caller** (grep-confirmed) — it is exercised only by the two pinned tests.
- **`advance_run_counters(state)`** (`markers.py:3078`) / **`advance_meta_cycle()`** (`markers.py:3179`) — the earlier consume-oracle path and the `--emit-dispatch` meta bump. The `--repeat-count` probe-path forward advance was REMOVED (`lazy-state.py:14560-14569` comment: "the forward budget advance formerly fired HERE … REMOVED"); `--emit-dispatch` no longer advances the budget (`lazy-state.py:13858-13864` comment: moved to the `--cycle-end` bracket).

The two advance paths are **disjoint** (no double-count): Agent dispatches advance via `advance_cycle_bracket_counter` at their `--cycle-end` bracket; inline pseudo-skills (no bracket) advance via `advance_forward_cycle` at their `--apply-pseudo` handler.

### Git History

- `2026-07-16 15:21 74af39de` "advance forward_cycles on consume rise for same-step cycles" — added the `consume_gate` trigger to `advance_forward_cycle` on the probe path (one of the "two 2026-07-16 decisions" decision 11 supersedes); introduced the two now-pinned tests.
- `2026-07-17 11:00 e91bd305` "count cycle budget at --cycle-end bracket, not on probes" — the fix for the SEPARATE bug `cycle-budget-counters-double-count-on-probes-and-inject-hook`. **This pre-emptively landed decision 11's core mechanism:** removed the probe-path forward advance, moved the budget to `advance_cycle_bracket_counter` at `--cycle-end`, added the new-behavior regression tests. Landed ONE DAY before decision 11 was formally resolved (2026-07-18, Option 1 — the same architecture).

### Related Documentation

- `NEEDS_INPUT.md` decision 11 (line 402) + decision 3 (line 67) — both RESOLVED 2026-07-18, one root fix.
- `user/scripts/CLAUDE.md` → "Cycle-counter advance: two orthogonal triggers" — describes `advance_forward_cycle` as "the authoritative forward-advance on the `--repeat-count` real-skill probe path." **This documentation is now STALE** — the probe-path advance was removed by `e91bd305`; the live authority is `advance_cycle_bracket_counter` at `--cycle-end`. Reconciling this doc is in scope.
- `docs/bugs/CLAUDE.md` — bug-doc conventions (this dir).

## Theories

### Theory 1: The decision-11 mechanism is already implemented; residual is tests + cleanup + docs
- **Hypothesis:** `e91bd305` already moved the forward advance off the probe path to the `--cycle-end` dispatch bracket and made the probe path a budget PEEK, so the two named symptoms (over-count / under-count) are already resolved at the shared root; the outstanding decision-11 work is (a) retarget the two pinned tests to dispatch-time advance, (b) retire the now-dead `consume_gate` forward-advance trigger, (c) reconcile the stale `CLAUDE.md` doc.
- **Supporting evidence:** grep shows `consume_gate=True` has no production caller; the probe-path advance comment says "REMOVED"; `advance_cycle_bracket_counter` is wired at `--cycle-end` in both scripts; the new-behavior regression tests already exist and are registered.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

## Proven Findings

**Root cause (traced — serving path → source, fix-site-on-path shown).** The observed symptom is a wrong `forward_cycles` COUNT (over- or under-). Serving path of the count:

```
forward_cycles value on the run marker
  → advanced by advance_forward_cycle(state, consume_gate=True)   user/scripts/lazy-state.py:~13538 (PRE-e91bd305, on the --repeat-count probe path)
  → fired every UserPromptSubmit turn by the inject hook           user/scripts/lazy_inject.py::_run_probe (runs --repeat-count --probe --emit-prompt)
  → advances on `state_changed OR consume_rose`                    user/scripts/lazy_core/markers.py:3376,3399  ← the fix site
```

The advance was on the **every-turn banner/probe path**, not the dispatch bracket, so a notification turn (route changed, no dispatch) over-counted (`state_changed` true, no consume) and an interleaved meta+real by-ref sequence under-counted (`advance_meta_cycle`'s `+1` consume-absorb masked the next real advance under the strict-greater gate). Both are the same structural defect: the counter was coupled to the probe, not the dispatch.

**Fix (on the traced path).** Move the advance OFF the `--repeat-count` probe path (make it a budget PEEK) and onto the real dispatch bracket:
- Agent dispatches → `advance_cycle_bracket_counter(cycle_marker)` at `--cycle-end` (`lazy-state.py:13347` / `bug-state.py:8885`), keyed on the cycle marker's `kind`. **Already landed by `e91bd305`.**
- Inline forward-advancing pseudo-skills (no bracket) → `advance_forward_cycle(state)` at `--apply-pseudo` (`lazy-state.py:13977`, `consume_gate=False`). **Preserved as-is** (the resolution explicitly requires this path keep advancing at its own apply bracket).

This is a mechanism-relocation finding, not a runtime-timing claim, so it is `traced` by static reads of the wiring (call sites cited `file:line`); no runtime artifact is required. Both named symptoms are retired at the shared root because the counter now counts dispatches, not banner emissions.

## Residual Work (for /plan-bug)

1. **Retarget the two pinned tests** — `test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` and `test_advance_forward_cycle_verbatim_real_skill_theory_1b` (both in `user/scripts/tests/test_lazy_core/test_markers.py`) currently assert probe-path `advance_forward_cycle(consume_gate=…)` advances. **Retarget (do NOT invert)** them to assert the dispatch-time advance — a multi-part `/execute-plan` (same `(feature_id, current_step, sub_skill)` tuple across parts) advances `forward_cycles` once per completed `--cycle-end` real bracket via `advance_cycle_bracket_counter`; a verbatim (consume-missed) real dispatch still advances once per bracket. This preserves the intent the two tests encode (each genuine dispatch cycle advances exactly once, even at an unchanging tuple / a missed consume) while moving the assertion to the live mechanism.
2. **Retire the dead `consume_gate` forward-advance trigger** in `advance_forward_cycle` — with no production caller, the `consume_gate` parameter + census-rise branch (`markers.py:3378-3397, 3421-3422`) is dead. Removing it (and its `consume_gate`-specific tests `test_advance_forward_cycle_consume_gate_default_off_preserves_freeze` etc.) aligns with the resolution ("both oracles retired as forward-advance triggers"). Keep `advance_forward_cycle`'s state-change path — it still serves `--apply-pseudo`.
3. **Reconcile stale docs** — update `user/scripts/CLAUDE.md` → "Cycle-counter advance: two orthogonal triggers" so it describes `advance_cycle_bracket_counter` (`--cycle-end`) as the live budget authority and the probe path as PEEK, not `advance_forward_cycle` on the probe path.
4. **Parity** — both changes touch the shared `lazy_core.markers` surface and the `--cycle-end` bracket present on both state scripts; run `lazy_parity_audit.py --repo-root .` and both `--test` harnesses. Confirm the baseline `--test` outputs stay byte-stable (the change is test-file + dead-code + docs; no state-machine branch change).

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Forward-advance triggers | `user/scripts/lazy_core/markers.py` (`advance_forward_cycle` `consume_gate` branch) | Retire dead `consume_gate` trigger; keep the state-change path for `--apply-pseudo` |
| Pinned tests | `user/scripts/tests/test_lazy_core/test_markers.py` | Retarget the two named tests to dispatch-time advance; drop `consume_gate`-only tests |
| Docs | `user/scripts/CLAUDE.md` ("Cycle-counter advance") | Reconcile the stale probe-path-advance description |
| Live mechanism (verify only) | `lazy-state.py:13347` / `bug-state.py:8885` (`advance_cycle_bracket_counter`), `lazy-state.py:13977` (`--apply-pseudo`), `lazy-state.py:14560` (probe-path removal) | Already correct — assert unchanged; no production advance code change expected |

⚖ policy: advance point cycle-begin vs cycle-end → keep shipped `--cycle-end` bracket
<!-- Decision 11 lists "guard-ALLOW consume of the cycle emission, OR --cycle-begin" as acceptable advance points; `e91bd305` shipped the equivalent `--cycle-end` bracket (one bracket = one dispatch). End-state budget behavior (count dispatches, not banner emissions) is identical to the --cycle-begin variant — only the cosmetic mid-cycle cycle_header display differs. Scope-class (D7): keep the already-landed, tested --cycle-end mechanism rather than relocating to --cycle-begin. -->

⚖ policy: retire dead consume_gate vs leave orphaned param → retire it in /plan-bug scope
<!-- The resolution says both oracles are "retired as forward-advance triggers." Retiring the dead branch is the most-complete path and is included as residual work item 2 (a plan-level WU), not deferred. -->

## Open Questions

- None blocking. The operator resolved the architectural fork (Option 1) on 2026-07-18; the mechanism is landed; the residual is deterministic (tests + dead-code + docs) and needs no further product decision.
