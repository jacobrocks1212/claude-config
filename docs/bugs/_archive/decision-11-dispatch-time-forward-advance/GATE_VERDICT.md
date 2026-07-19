---
kind: gate-verdict
feature_id: decision-11-dispatch-time-forward-advance
gate_version: 1
date: 2026-07-19
scope_hit: [user/scripts/lazy_core/markers.py, user/scripts/tests/test_lazy_core/test_markers.py]
checks:
  overfit: pass
  tautology: pass
  gate_weakening: hit-signed
  complexity: declared
retires: consume_gate probe-path forward-advance in advance_forward_cycle (superseded by the
  dispatch-time advance_cycle_bracket_counter bracket-counter mechanism, shipped upstream in
  e91bd305)
override: operator-approved 2026-07-19 — the dropped test exercised the retired consume_gate
  probe-path advance, which has zero production callers; the live dispatch-time advance mechanism
  is covered by 2 retargeted tests + the full 220/220-green test_markers suite, so no coverage was
  lost.
---

## Adversarial answers

### overfit
Not flagged against the scoped production diff (`markers.py`). No literal was appended to any
matcher/alternation/allow-list; the change is a structural retirement of a dead trigger.

### tautology
No `## Intervention Hypothesis` block applies (this is a bug fix retiring dead code, not a
harness-behavior intervention) — the completion evidence is the 1296-test full suite + parity
audit, not a self-emitted signal.

### gate_weakening
**The exact weakening flagged:** `harness-gate.py --range bbb5803d..f205c2d3` reported a
`def test_*` deletion in `user/scripts/tests/test_lazy_core/test_markers.py`
(`test_advance_forward_cycle_consume_gate_advances_multicycle_same_step` and
`test_advance_forward_cycle_consume_gate_default_off_preserves_freeze`) — 2 of 4 touched tests in
that file were dropped, 2 retargeted, net test delta −1 in the file (net +1 across the whole fix
per the PR description).

**Underlying-defect alternative considered:** re-add the dropped tests against a code path that no
longer exists — not viable; the `consume_gate` trigger itself was retired (grep-confirmed zero
production callers) as this bug's own root-cause fix (the dispatch-time bracket counter,
`advance_cycle_bracket_counter` at `--cycle-end`, replaced it). Keeping dead tests alive against
deleted code is not a real alternative.

**Operator rationale (why approved, not a real weakening):** the dropped test's ONLY subject was
the dead `consume_gate` probe-path advance this bug legitimately retires. Coverage of the LIVE
dispatch-time mechanism is preserved by the 2 retargeted tests (now asserting
`advance_cycle_bracket_counter`) plus the full `test_markers.py` suite (220/220 green) and the
repo-wide 1296-test battery. No genuine detection surface was lost — a gate-strength check on a
mechanism that no longer exists is not gate strength.

**Note on re-derivation:** `harness-gate.py`'s structural detectors were later scoped to
manifest-glob-matching hunks only (`45804283`, landed 2026-07-19 06:09, AFTER this bug's fix
commit `f205c2d3` at 05:50) — a re-run of the checker today against the same range no longer flags
this test-file deletion (test files are not on the control-surface manifest). This verdict is
recorded against the CONTEMPORANEOUS flag the cycle actually saw, per the harness-change-gate
contract (a per-change verdict, never re-litigated by a later detector-precision fix).

### complexity
`retires: consume_gate probe-path advance` — the dead trigger in `advance_forward_cycle` (zero
production callers) is removed; the forward-advance authority moved to the dispatch-time bracket
counter shipped upstream in `e91bd305`. Net-retire, not net-new surface.
