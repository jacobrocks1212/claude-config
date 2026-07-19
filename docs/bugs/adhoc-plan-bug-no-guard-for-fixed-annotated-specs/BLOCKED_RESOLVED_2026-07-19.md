---
kind: blocked
blocker_kind: gate-verdict-authoring-no-pipeline-seam
blocked_by: harness-gap
written_by: lazy-bug-batch
---

# BLOCKED — adhoc-plan-bug-no-guard-for-fixed-annotated-specs

The fix is **implemented, tested, and live on `main`** (P1 shared `fixed-unreconciled` helpers
`66195d84`, P2 bug-state Step-4 divert `b70b0ddf`, P3 plan-bug Step 0.4 belt-and-suspenders
`39b48511`; all 3 phases Complete, `lazy_core` suite + `bug-state --test` + parity + baseline all
green). Completion is blocked at the `__mark_fixed__` ship seam by a **missing `GATE_VERDICT.md`
that the bug pipeline provides no seam to author.**

**The gap (recurring — 6th occurrence this run):**
- This bug's shipped commits touch control-surface files (`user/scripts/bug-state.py`,
  `user/scripts/lazy_core/{__init__,docmodel,gates}.py`), so `lazy_core.gate_verdict_ok`
  (`user/scripts/lazy_core/pseudo.py:1182-1188`) refuses `__mark_fixed__` with
  `scoped change missing GATE_VERDICT.md`. `harness-gate.py` reports `in_scope: true` with **0
  findings** — a *clean* verdict is owed (overfit/tautology/gate_weakening = pass; complexity =
  net-new `retires:` declaration for the new `is_fixed_unreconciled` guard).
- `harness-change-gate.md` says the verdict is authored **at the planning seam**, but `/plan-bug`
  (and `/spec-phases` in its bug flow) do NOT inject `harness-change-gate.md`, so the plan never
  carried a GATE_VERDICT.md deliverable and `/execute-plan` never authored it.
- There is **no registered completion-time authoring dispatch class**: `coherence-recovery` is
  strictly PHASES.md-scoped (correctly declined this cycle); `hardening`'s emit-context is
  guard-deny-shaped; no dedicated class exists. The orchestrator cannot author it directly
  (HARD CONSTRAINT 1 — GATE_VERDICT.md is not a sentinel; improvising the adversarial answers
  would be the "judgment laundering" the design gate explicitly forbids).

**Resolution (harness fix, deferred to run-end / next run):** close the injection gap so an
in-scope bug authors its GATE_VERDICT.md during planning — inject `harness-change-gate.md` into
`/plan-bug` (mirroring the feature-side `/spec` injection), OR add a registered completion-time
`gate-verdict` authoring dispatch class the orchestrator can route when `gate_verdict_ok` refuses.
Once a seam exists, this bug's clean verdict is authored and `__mark_fixed__` completes.

**Note:** deleting `docs/gate/control-surfaces.json` to disarm the gate is REJECTED — that is
gate-weakening (Prohibition #2), exactly what this gate exists to prevent. Parked (`--park`)
pending the harness fix.
