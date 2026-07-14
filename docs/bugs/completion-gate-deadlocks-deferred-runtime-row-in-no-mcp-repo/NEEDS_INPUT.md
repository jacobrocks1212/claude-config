---
kind: needs-input
feature_id: completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo
written_by: harden-harness
decisions:
  - "Operator sign-off on relaxing the completion-integrity gate to complete a DEFERRED verification-only row in a no-MCP structural-skip repo (with a RUNTIME_GATES.md ledger, row left unchecked)"
date: 2026-07-14
---

# Decision Context

The `/harden-harness` fix for `completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo`
touches the **completion-integrity gate** (`__mark_complete__` / `__mark_fixed__`), a
load-bearing gate. `harness-gate.py` classifies the diff `in_scope: true`; `gate_weakening` is
mechanically **pass** (the fix adds a new gated branch rather than removing a check), but the
change **substantively relaxes** the gate: it makes completion reachable in a state — an unchecked
`<!-- verification-only -->` row — where the gate previously refused. Per the design gate's D7 and
the operator's standing direction, a completion-gate relaxation is surfaced for sign-off rather
than self-approved.

## The exact question for the operator

> **Do you approve relaxing the completion-coherence gate so that a legitimately-DEFERRED
> `<!-- verification-only -->` runtime row no longer blocks `__mark_complete__`/`__mark_fixed__`
> when — and only when — (a) a `granted_by: pipeline-structural` `SKIP_MCP_TEST.md` RE-VERIFIES the
> no-app-surface predicate against the live repo, (b) `VALIDATED.md` is present, and (c) the
> deferred rows are recorded in an idempotent `RUNTIME_GATES.md` ledger — with the rows left
> UNCHECKED (not auto-ticked), the strict path preserved for every real case (genuine
> implementation row, MCP-repo verification row, forged/missing attestation), and the
> `LAZY_STRICT_EVIDENCE_GATE` kill-switch restoring the byte-identical strict path?**

## What was implemented (already landed — the fix never leaves the run broken)

- `evaluate_deferred_runtime_exemption(feature_dir, repo_root)` (`gates.py`) — the confinement
  predicate (structural-skip re-verify + VALIDATED.md).
- `write_runtime_gates_ledger(...)` (`gates.py`) — idempotent `RUNTIME_GATES.md` writer mirroring
  `_components/pending-runtime-gates.md`.
- `_phase_completion_plan(..., verification_only_exempt=)` + a new per-phase
  `unchecked_verification_only` parse sub-count + `enumerate_deferred_verification_rows`
  (`docmodel.py`).
- Wiring in `apply_pseudo` behind the existing `_evidence_gate_killed()` kill-switch; shared
  `lazy_core` so `__mark_fixed__` (bug pipeline) inherits it (no script mirror owed; parity green).

## Corroborating tests (all green)

- Positive route: `test_apply_pseudo_deferred_runtime_row_completes_on_structural_skip`
  (row stays `- [ ]`, ledger written, `auto_ticked_rows == 0`).
- Bug-pipeline mirror: `test_apply_pseudo_deferred_runtime_mark_fixed_completes_on_structural_skip`.
- Non-regression: `..._genuine_impl_row_still_refuses`, `..._no_exemption_in_app_repo`,
  `..._killswitch_restores_strict`; unit guards in `test_gates.py` / `test_docmodel.py`.

## Rollback if declined

Set `LAZY_STRICT_EVIDENCE_GATE=1` (or revert the fix commit) — the completion gate returns to the
byte-identical strict path with zero deferred-runtime exemption.

**On approval:** neutralize this sentinel
(`lazy-state.py --neutralize-sentinel <path>`); the fix needs no further code change.
