# Implementation Phases — completion gate deadlocks on a deferred `<!-- verification-only -->` runtime row in a no-MCP repo

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure `lazy_core` completion-gate logic, verified via pytest.
No `mcp-tool-catalog.md` in this repo; the planning-time MCP tool-existence audit no-ops.

## Validated Assumptions

- **The deadlock is the ABSENCE of a route** — an unchecked `<!-- verification-only -->` row in
  a repo with no MCP surface can never be auto-ticked (no `MCP_TEST_RESULTS.md` is producible),
  yet the completion coherence gate (`_phase_completion_plan`) counted it as blocking. The fix
  ADDS a keyword-gated exemption branch; it removes/weakens nothing on any real refusal path.
- **The relaxation is disciplined and operator-signed-off** (`GATE_VERDICT.md`, verdict
  APPROVED, `signed_off_by: operator`, 2026-07-14): the route fires ONLY when the MCP-evidence
  auto-tick is structurally impossible (a `granted_by: pipeline-structural` skip re-verifying
  no-app-surface); rows stay unchecked; `RUNTIME_GATES.md` is the honest tracker;
  `LAZY_STRICT_EVIDENCE_GATE=1` restores the byte-identical strict path.

## Cross-feature Integration Notes

No `**Depends on:**` block. Surfaced while completing `generalized-build-test-runner-skills`
(its deferred cloud-compat row hit this exact no-route). Self-contained `lazy_core` fix.

---

### Phase 1: Add the structural deferred-runtime completion route

**Scope:** Make `__mark_complete__` / `__mark_fixed__` reachable past an unchecked
`<!-- verification-only -->` row IFF the no-app-surface structural-skip predicate re-verifies,
coupled by construction to writing an honest `RUNTIME_GATES.md` ledger. Adds a keyword-only
`verification_only_exempt=` param + two pure helpers; edits no threshold, removes no test,
touches no exemption-set literal.

**TDD:** yes — the app-repo-refuses and killswitch-restores-strict cases were written to pin the
route's boundaries before wiring it into `apply_pseudo`.

**Status:** Fixed

**Deliverables:**
- [x] `lazy_core/docmodel.py` — `enumerate_deferred_verification_rows()`, the per-phase
      `unchecked_verification_only` parse sub-count, and the `verification_only_exempt=` kwarg on
      `_phase_completion_plan` (default False → byte-identical legacy behavior).
- [x] `lazy_core/gates.py` — `evaluate_deferred_runtime_exemption(feature_dir, repo_root)`
      (structural-skip re-verify) + `write_runtime_gates_ledger(...)`.
- [x] `lazy_core/pseudo.py` — exemption wired behind `_evidence_gate_killed()`
      (`LAZY_STRICT_EVIDENCE_GATE` kill-switch); exposes `result["runtime_gates_pending"]`.
- [x] `docs/bugs/completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo/GATE_VERDICT.md`
      — design-gate verdict APPROVED, operator-signed-off (gate-weakening class change).

**Minimum Verifiable Behavior:**
`python3 -m pytest user/scripts/tests/test_lazy_core -k "deferred or verification_only or exempt
or runtime_gates" ` is green, including the app-repo-refuses and killswitch-restores-strict pins.

**MCP Integration Test Assertions:** N/A — pure completion-gate logic, no MCP-observable surface.

**Prerequisites:** None (only phase).

**Files likely modified:**
- `user/scripts/lazy_core/docmodel.py`
- `user/scripts/lazy_core/gates.py`
- `user/scripts/lazy_core/pseudo.py`

**Testing Strategy:** pytest over `test_lazy_core/{test_docmodel,test_gates,test_pseudo}.py`.

**Runtime Verification** *(checked by pytest — the gate's runtime IS the test suite)*:
- [x] <!-- verification-only --> The exemption route fires only when structurally justified and
  the strict path is preserved. **Verified 2026-07-14:** the exemption-scoped selection over
  `test_lazy_core/{test_docmodel,test_gates,test_pseudo}.py` → **48 passed** (incl.
  `test_deferred_runtime_exemption_app_repo_refuses`,
  `test_apply_pseudo_deferred_runtime_killswitch_restores_strict`,
  `test_phase_completion_plan_verification_only_exempt_genuine_row_still_refuses`).

**Integration Notes for Next Phase:** None — only phase. Fixed out-of-pipeline by `harden-harness`
with operator sign-off; receipt written via the gated `__mark_fixed__` chain (which itself
exercises the newly-approved structural deferred-runtime route).

---

## Review Notes

_(Fix landed out-of-pipeline via harden-harness + operator sign-off; receipt-gated through the
structural no-MCP skip — the very route this fix introduces.)_
