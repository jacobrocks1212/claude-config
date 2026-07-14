---
kind: bug-spec
bug_id: completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo
severity: P2
discovered: 2026-07-14
status: Concluded
origin: /harden-harness manual invocation (operator-directed, 2026-07-14)
---

# Completion gate deadlocks a legitimately-DEFERRED verification-only row in a no-MCP / structural-skip repo

**Status:** Fixed

## Symptom (verified — reproduced 2026-07-14)

A fully-implemented, ratified, VALIDATED feature in a **no-MCP-surface repo** (claude-config:
no `src-tauri/`, no `package.json`) CANNOT be marked complete when its PHASES.md carries a
legitimately-DEFERRED `<!-- verification-only -->` runtime row.

Concrete repro — `docs/features/generalized-build-test-runner-skills/`:

- All plan parts Complete; every PHASES deliverable checked EXCEPT one Phase-4 row:
  `- [ ] <!-- verification-only --> Cloud compatibility: a battery run in a cloud session (no
  PowerShell) … closed by the first cloud-session battery run …; mechanically proxied until then
  by the Phase 1 no-PowerShell pytest.`
- Structural `SKIP_MCP_TEST.md` present (`granted_by: pipeline-structural`,
  `spec_class: standalone — no app integration`) + `VALIDATED.md` (`kind: validated`,
  `result: all-passing`) written by `__write_validated_from_skip__`.
- `lazy-state.py --apply-pseudo __mark_complete__ …` → **refused**:
  `PHASES.md is incoherent for completion — 1 phase(s) block the receipt: ### Phase 4 …:
  1 unchecked box(es)`.

## Root cause (traced surface → source)

The completion path in `lazy_core/pseudo.py` `apply_pseudo` `__mark_complete__`/`__mark_fixed__`:

1. `evaluate_completion_evidence(feature_dir, repo_root)` (`lazy_core/gates.py:255`) requires the
   UNION of `VALIDATED.md` AND a passing `MCP_TEST_RESULTS.md`. A **structural** skip never
   produces `MCP_TEST_RESULTS.md`, and `SKIP_MCP_TEST.md` is in
   `_FAIL_CLOSED_EVIDENCE_SENTINELS` (`docmodel.py:1904`) → verdict `refuse`. So
   `autotick_verification_rows` never fires.
2. `_phase_completion_plan(parsed_phases)` (`docmodel.py:1776`) then counts the
   `<!-- verification-only -->` row as BLOCKING at completion time (by design — "the
   verification exemption's job is done by completion time", `docmodel.py:1790`) → refusal.
3. The only completion-time exemption marker is `<!-- descoped -->` (`_DESCOPED_MARKER`,
   `docmodel.py:1070`) — but "descoped/dropped" MISREPRESENTS a row that is genuinely DEFERRED
   (closed later by a cloud-session run, mechanically proxied now).

The deadlock: in a no-MCP repo the union-of-evidence auto-tick is structurally unreachable
(there is no MCP surface to produce `MCP_TEST_RESULTS.md`), yet the coherence gate still demands
those rows be ticked, and the only escape (`descoped`) is a factual misrepresentation.

## Inconsistency with the pipeline's own contract

`_components/pending-runtime-gates.md` (`/execute-plan` Step 4) already handles exactly this
situation: it KEEPS the `Complete` flip and enumerates the unchecked runtime row in an idempotent
`RUNTIME_GATES.md` ledger — i.e. the harness's own design says completion should PROCEED with a
deferred runtime row + a ledger. The lazy `__mark_complete__` gate contradicts that.

## Fix scope (concluded)

Add an honest completion-time route for a DEFERRED verification-only row when — and ONLY when —
the MCP-evidence auto-tick is structurally impossible AND the deferral is honestly tracked:

- New pure helper `evaluate_deferred_runtime_exemption(feature_dir, repo_root)` (`gates.py`): ok
  iff `VALIDATED.md` (`kind: validated`) present AND `SKIP_MCP_TEST.md` present with
  `granted_by: pipeline-structural` whose `skip_waiver_refusal(meta, repo_root)` RE-VERIFIES the
  no-app-surface predicate (an app repo re-verifies False → not ok). This is the exact guard that
  keeps the exemption from firing in an MCP repo.
- When ok AND there are unchecked canonical `<!-- verification-only -->` rows: the completion gate
  itself WRITES/updates an idempotent `RUNTIME_GATES.md` ledger (mirroring the
  pending-runtime-gates contract), then EXEMPTS those rows from the coherence blocking count via a
  new `_phase_completion_plan(..., verification_only_exempt=True)` kwarg (discounts a new
  per-phase `unchecked_verification_only` count, parallel to `unchecked_descoped`). The rows stay
  `- [ ]` — NOT auto-ticked (the deferred run genuinely has not happened); the ledger is the
  honest tracker.
- Kill-switch: gated behind the existing `_evidence_gate_killed()` strict-mode env switch (free
  rollback, consistent with the auto-tick reconciliation).

Preserved strict behavior (non-regression):
- A genuine unchecked *implementation* row (no marker) still blocks.
- A verification-only row in an MCP repo still requires real MCP evidence to auto-tick (the
  structural waiver re-verification refuses there).
- Forged / missing-VSA attestations still refuse (VALIDATED.md required).

Coupled pair: the gate surface is shared `lazy_core`, so `__mark_fixed__` (bug pipeline) inherits
the exemption identically — no script mirror owed; `lazy_parity_audit.py` stays green.

**Design-gate note:** this makes completion reachable in a state it previously refused, so
`harness-gate.py` classifies it `gate_weakening` (expected/correct). Per the anti-overfit design
gate's D7, `GATE_VERDICT.md` records the classification and routes to operator sign-off via
`NEEDS_INPUT.md` rather than self-approving.
