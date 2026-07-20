# Implementation Phases — Dispatched harden-harness cannot record its own intervention

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a config/harness repo with no Tauri app or MCP HTTP surface. This fix is pure Python containment-guard logic (`lazy_core/markers.py` + the two state-script CLI handlers) plus coupled SKILL prose; its verification is deterministic `pytest` over `test_markers.py` (mcp-testing SPEC class: standalone tooling / no app integration).

## Validated Assumptions

- **The entire Fix Scope already landed out-of-pipeline** in commit `1cb997e0` ("harden(script,skill-prose): dispatched-harden --record-intervention exemption + flush-commit staging contract"). This was a `/harden-harness` round that fixed the containment defect but did not run the bug-pipeline `__mark_fixed__ → --archive-fixed` contract, so the SPEC remained `Concluded` and the queue entry stayed live — the documented "bug fixed OUT-OF-PIPELINE" situation (`docs/bugs/CLAUDE.md`). Ground truth verified this cycle by reading each touchpoint on disk (`git` tree clean on `main`):
  - `refuse_if_cycle_active(op_name, *, allow_hardening_subagent=False)` in `lazy_core/markers.py` carries the exemption branch `if allow_hardening_subagent and _cycle_marker_is_hardening(marker): return` (checked AFTER the subagent-identity gate, BEFORE the telemetry-emit + `sys.exit(3)`).
  - `_cycle_marker_is_hardening(marker)` keys on the marker's own `sub_skill` against `_HARDENING_CYCLE_SUBSKILLS = frozenset({"hardening"})` — unspoofable by a runaway's env (only the orchestrator writes the cycle marker).
  - Both `lazy-state.py` (`if args.record_intervention:` @13702) and `bug-state.py` (@9328, coupled mirror) pass `allow_hardening_subagent=True`; no other guarded op passes it, so `--run-end` / `--run-start` / `--emit-dispatch` / `--apply-pseudo` / `--enqueue-adhoc` stay refused for any cycle subagent.
  - The coupled SKILL prose brackets the hardening dispatch `--kind meta --sub-skill hardening` in `user/skills/lazy-batch/SKILL.md` and `user/skills/lazy-bug-batch/SKILL.md`, each with the load-bearing note that the `sub_skill` value is the marker identity signal the exemption keys on.
- **Regression evidence exists and is green:** `test_record_intervention_permitted_for_hardening_cycle_subagent` (in `user/scripts/tests/test_lazy_core/test_markers.py`) asserts exactly the SPEC's three target-signal cases — (a) hardening marker → `--record-intervention` PERMITTED (exit 0), (b) `--run-end` STILL refused under the hardening marker, (c) NON-hardening marker → `--record-intervention` STILL refused. Ran this cycle: `1 passed`. This IS the serving-path regression proving the exit-3 → exit-0 behavior change (SEAM B symptom-reproduction evidence).

This PHASES.md therefore documents the LANDED fix scope with all implementation deliverables already satisfied, so the bug pipeline routes past write-plan/execute-plan (no implementation work remains) to its validation tail. It does NOT flip `**Status:**` to Fixed and does NOT write `FIXED.md` — those remain the orchestrator's `__mark_fixed__` gate, which fires after the validation tail confirms the reproduction evidence.

### Phase 1: Exempt `--record-intervention` for a dispatched hardening-class cycle subagent

**Scope:** Permit the one capture-only op a dispatched `/harden-harness` cycle subagent is REQUIRED to run (`lazy-state.py`/`bug-state.py --record-intervention`, which writes `docs/interventions/<id>.md` — no run-marker/registry/queue mutation) while keeping every genuinely-dangerous lifecycle op refused. Keyed on the cycle marker's own `sub_skill` so only a real hardening cycle is exempted.

**Deliverables:**
- [x] `refuse_if_cycle_active` gains keyword-only `allow_hardening_subagent: bool = False`; in the refuse path, when set AND the cycle marker's `sub_skill` is a hardening class, RETURN silently (permit) instead of `exit(3)`. Placed AFTER the subagent-identity gate, BEFORE telemetry-emit + exit. (`lazy_core/markers.py`)
- [x] `_cycle_marker_is_hardening(marker)` helper + `_HARDENING_CYCLE_SUBSKILLS = frozenset({"hardening"})` — keyed on the orchestrator-written `sub_skill`, returns False for a missing/None or non-hardening marker. (`lazy_core/markers.py`)
- [x] `lazy-state.py --record-intervention` handler passes `allow_hardening_subagent=True`; no other guarded handler passes it. (`user/scripts/lazy-state.py`)
- [x] `bug-state.py --record-intervention` handler passes `allow_hardening_subagent=True` (coupled-pair mirror). (`user/scripts/bug-state.py`)
- [x] Coupled SKILL prose makes the hardening dispatch bracket explicit — `--kind meta --sub-skill hardening` — in `/lazy-batch` §1d.1 and `/lazy-bug-batch` §1d.1, with the load-bearing note that `--sub-skill hardening` is the marker identity the exemption keys on. (`user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md`)
- [x] Tests: `test_record_intervention_permitted_for_hardening_cycle_subagent` covering the permit/refuse-lifecycle/refuse-non-hardening cases. (`user/scripts/tests/test_lazy_core/test_markers.py`)

**Minimum Verifiable Behavior:** A dispatched harden's `lazy-state.py --record-intervention --id <id>` under a `sub_skill: hardening` cycle marker (`LAZY_ORCHESTRATOR` unset) exits 0 and writes the record; the SAME invocation under a `sub_skill: execute-plan` marker exits 3; `--run-end` under a hardening marker exits 3. Proven by `test_record_intervention_permitted_for_hardening_cycle_subagent` (green this cycle).

**Runtime Verification** *(checked by the validation tail — NOT by the implementer):*
- [ ] <!-- verification-only --> The exit-3 → exit-0 behavior change on the `--record-intervention` false-refusal subset is proven by the serving-path regression test `test_record_intervention_permitted_for_hardening_cycle_subagent` (cases a/b/c) passing, AND the guarded-lifecycle ops (`--run-end` etc.) still refuse under a hardening marker (case b). SEAM-B symptom-reproduction: the original symptom (containment refuses the mandated capture op) is gone at its reported surface while no genuinely-dangerous op was un-gated.

**Prerequisites:** None.

**Files likely modified (verified — all `exists: yes`, already modified in `1cb997e0`):**
- `user/scripts/lazy_core/markers.py` — `refuse_if_cycle_active` exemption param + branch; `_cycle_marker_is_hardening` + `_HARDENING_CYCLE_SUBSKILLS`.
- `user/scripts/lazy-state.py` — `--record-intervention` handler passes the flag.
- `user/scripts/bug-state.py` — coupled-pair mirror.
- `user/skills/lazy-batch/SKILL.md`, `user/skills/lazy-bug-batch/SKILL.md` — `--kind meta --sub-skill hardening` bracket + load-bearing note.
- `user/scripts/tests/test_lazy_core/test_markers.py` — the exemption regression test.

**Testing Strategy:** Deterministic `pytest` over `test_markers.py` exercising the real `refuse_if_cycle_active` with a temp state dir and a synthesized hardening / non-hardening cycle marker; asserts exit behavior for the permit and both refuse cases. No runtime/MCP surface involved.

#### Implementation Notes

- The fix landed in a single commit (`1cb997e0`) via a `/harden-harness` round that ran during a live lazy run but could not itself record the intervention through the pipeline (the very defect this bug documents), so the fix was hand-committed rather than routed through `__mark_fixed__`. This PHASES.md is the pipeline's catch-up: it records the landed scope so `bug-state.py` advances from the perpetual `spec-bug`/`plan-bug` re-dispatch loop (SPEC present, no PHASES) straight to the validation/completion gate.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to Fixed, writes `FIXED.md`, and runs `--archive-fixed` once the validation tail confirms the reproduction evidence above. This phase does not perform any of those.
- **No plan file needed:** all implementation deliverables are already satisfied on disk, so there is no unchecked implementation work for `/write-plan` to schedule; the only outstanding row is verification-only (owned by the validation tail). Authoring an implementation plan for zero remaining work would be fabrication.
