# Implementation Phases — Bug pipeline missing stale-plan flip (`__flip_plan_complete_stale__` mirror)

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; verified via
`bug-state.py`'s in-file `--test` smoke harness (byte-pinned baseline) alone.

**Close-out note (2026-07-12):** the Fix Scope was found ALREADY LANDED at HEAD prior to this
close-out pass (`27b7d01a harden(script): mirror __flip_plan_complete_stale__ into bug-state.py
Step 7a`). This PHASES.md documents the pre-landed state against the SPEC's Fix Scope; no new code
was written in this pass.

---

### Phase 1: Mirror the workstation stale-flip block into `bug-state.py` Step 7a

**Status:** Complete (pre-landed, `27b7d01a`)

**Scope:** Between `plan = plans[0]` and the `execute-plan` return, evaluate whether the head
plan's referenced work is already fully checked (`finalize_stale`) and, when so, emit
`__flip_plan_complete_stale__` with `sub_skill_args=str(plan)` instead of a redundant
`/execute-plan` re-dispatch — mirroring `lazy-state.py`'s existing workstation stale-flip
(`_plan_phase_set` / `_unchecked_wus_in_plan_scope` / `_all_wus_in_plan_scope` /
`_phases_text_scoped_to` / `_plan_wu_checkbox_counts` / `_plan_unchecked_wus_are_verification_only`
/ `remaining_unchecked_are_verification_only`, all already shared in `lazy_core.py`). The
cloud-saturation gate (`_plan_cloud_saturated`) is feature/cloud-specific and deliberately NOT
mirrored (bug-state.py has no cloud-saturated flip).

**Deliverables:**
- [x] Stale-plan gate wired into `bug-state.py::compute_state` Step 7a (confirmed present: `user/scripts/bug-state.py:1509-1567` at time of this audit), between `plan = plans[0]` and the `execute-plan` fallback return.
- [x] All six shared `lazy_core` helpers imported and used (no re-implementation): `_plan_phase_set`, `_unchecked_wus_in_plan_scope`, `_all_wus_in_plan_scope`, `_phases_text_scoped_to`, `_plan_wu_checkbox_counts`, `_plan_unchecked_wus_are_verification_only`, `remaining_unchecked_are_verification_only`.
- [x] Empty-PHASES-scope guard present (mirror of the feature-side decomposition-part fix): a zero-row in-scope total falls back to the plan's OWN per-WU checkboxes so a decomposition part with unchecked plan-body WUs still executes (`:1528-1551`).
- [x] `--test` fixture `bug-stale-plan-flips` added (discriminating positive control) alongside the pre-existing `mid-fix` fixture (discriminating negative control — genuine unscoped unchecked WUs still dispatch `execute-plan`).
- [x] `bug-state-test-baseline.txt` byte-pin regenerated via `_normalize_smoke_output`; `lazy_parity_audit.py --repo-root .` exit 0.

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --test` passes, including the `bug-stale-plan-flips` fixture asserting `sub_skill == "__flip_plan_complete_stale__"` (not a redundant `execute-plan` re-dispatch), with the `mid-fix` fixture (genuine in-scope unchecked WUs) still asserting `sub_skill == "execute-plan"`.

**Runtime Verification:**
- [x] <!-- verification-only --> A bug plan part whose entire `phases:` scope is already `[x]` (frontmatter still In-progress) emits `__flip_plan_complete_stale__` rather than looping `/execute-plan`. **Verified (pre-landed):** `python user/scripts/bug-state.py --test` → `PASS [bug-stale-plan-flips] ... Step 7a: flip plan Complete (stale — all referenced implementation deliverables already checked)`.
- [x] <!-- verification-only --> A plan part with genuine in-scope unchecked WUs still dispatches `/execute-plan` (the discriminating negative control). **Verified (pre-landed):** `PASS [mid-fix] ... sub_skill=execute-plan`.

**MCP Integration Test Assertions:** N/A — no app runtime surface; the smoke harness is the verification tier.

**Prerequisites:** None (single-phase bug; all deciding helpers already existed shared in `lazy_core.py`).

**Files likely modified:** `user/scripts/bug-state.py`, `user/scripts/tests/baselines/bug-state-test-baseline.txt` (pre-landed; no edits made in this pass).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to
`Fixed`, writes the `FIXED.md` receipt, and archives the bug. Not a checkbox — done out-of-pipeline
this round per `docs/bugs/CLAUDE.md` ("Fixing a bug OUT-OF-PIPELINE").

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews.)_

Close-out audit (2026-07-12): confirmed landed at HEAD via direct code read
(`user/scripts/bug-state.py:1509-1567`) and a fresh `bug-state.py --test` run (all smoke tests
passed, including `bug-stale-plan-flips` and the `mid-fix` discriminating control).
