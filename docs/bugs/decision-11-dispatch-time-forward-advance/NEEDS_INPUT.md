---
kind: needs-input
feature_id: decision-11-dispatch-time-forward-advance
written_by: harness-change-gate
class: product
divergence: structural
decisions:
  - "Gate-weakening sign-off: the fix DROPS one `def test_*` in `test_markers.py` (the test that exercised the now-retired dead `consume_gate` probe-path advance). harness-gate flags `gate_weakening` on any `def test_*` deletion — never agent-approvable. Approve (the test covered genuinely dead code that this bug retired), or decline (keep/replace the test)?"
date: 2026-07-19
next_skill: __mark_fixed__
---

# Harness-Change Design Gate — operator sign-off required (gate-weakening: dropped test)

`__mark_fixed__` is blocked at the ship seam: `harness-gate.py` reports `gate_weakening_hit: True`
over `bbb5803d..f205c2d3` (a `def test_*` deletion in `user/scripts/tests/test_lazy_core/test_markers.py`).
Per `_components/harness-change-gate.md`, a gate-weakening hit is never agent-approvable — operator
sign-off (SPEC D4). Not self-approved.

## Decision Context

### Approve dropping the dead-`consume_gate` test?

**What the flag is.** This bug (decision 11) retired the dead `consume_gate` trigger in
`advance_forward_cycle` (grep-confirmed zero production callers; the forward-advance mechanism moved
to the `--cycle-end` dispatch bracket via `advance_cycle_bracket_counter`, shipped upstream in
`e91bd305`). The test that asserted the retired probe-path advance tested code that no longer exists,
so it was dropped. Of the four test edits: 2 retargeted onto `advance_cycle_bracket_counter`, 1
renamed, **1 dropped** (this one). Net test delta **−1**, but the dropped one covered removed dead
code.

**Options:**
- **(a) Approve the drop (Recommended).** Sign off that the dropped test covered code this bug
  legitimately retired; coverage of the live mechanism is preserved by the 2 retargeted tests +
  `test_markers` 220/220 green. A future run authors `GATE_VERDICT.md` (`gate_weakening: hit-signed`
  + `override: operator-approved`) and `__mark_fixed__` completes.
- **(b) Decline — keep or replace the test.** Re-add a test (e.g. asserting the `--apply-pseudo`
  state-change path that `consume_gate`'s removal preserved) before completion.

**Recommendation:** (a) — the test exercised a genuinely-removed code path; the live dispatch-time
advance is covered by the retargeted tests + the full 1296-test suite.

## Why parked, not asked now

Park-mode run; a gate-weakening sign-off is `class: product` / `divergence: structural` (never
provisional-eligible; gate-written sentinels never auto-accept). Surfaced at the run-end flush.
