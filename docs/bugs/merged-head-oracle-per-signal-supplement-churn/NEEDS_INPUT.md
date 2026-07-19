---
kind: needs-input
feature_id: merged-head-oracle-per-signal-supplement-churn
written_by: harness-change-gate
class: product
divergence: structural
decisions:
  - "Gate-weakening sign-off: the fix REMOVES `_candidate_operator_deferred` (+ its walk-loop application) from `lazy_core/dispatch.py`. The harness-change design gate flags this as `gate_weakening` (removed an exclusion predicate), which is NEVER agent-approvable — it requires operator sign-off. Approve the removal, or decline and keep the supplement as defense-in-depth?"
date: 2026-07-19
next_skill: __mark_fixed__
---

# Harness-Change Design Gate — operator sign-off required (gate-weakening)

`bug-state.py --apply-pseudo __mark_fixed__` for this bug is blocked at the completion ship seam:
`harness-gate.py` reports **`gate_weakening_hit: True`** over the fix range (`1904e359..efb698ed`).
Per `_components/harness-change-gate.md`, a gate-weakening hit is **never judgment-passable by the
agent** — it always routes to operator sign-off (SPEC D4). The orchestrator did NOT self-approve.

## Decision Context

### Gate-weakening sign-off — approve removing `_candidate_operator_deferred`?

**What the flag is.** The fix (commits `1904e359..efb698ed`, primarily `def4…`/part-1) deleted
`def _candidate_operator_deferred(_iid)` and its walk-loop application from
`lazy_core/dispatch.py`. That helper was the churn-prone **file-predicate supplement** that made
the merged-head oracle exclude operator-deferred (`DEFERRED.md`) features. The structural detector
sees a removed exclusion predicate → `gate_weakening`.

**Why the agent believes it is a legitimate RETIRE, not a weakening** (recorded for your judgment,
NOT as self-approval):
- The exclusion did not disappear — it **moved up-stream** into the feature `compute_state`
  (`lazy-state.py`) as a first-class operator-defer branch (WU-1), so the oracle's primary
  `is_dispatchable(scoped_probe(feature))` now returns non-dispatchable for a deferred feature
  without needing the file-predicate patch.
- This is the exact durable generalization spun off from harden R102 to stop the
  `merged-head-includes-parked/deferred` deadlock class from re-recurring (R56/R57/R101/R102).
- The R102 unit regression was **re-pointed at the primary mechanism** and stays green with the
  supplement gone; a new real-serving-path subprocess regression was added (net **+1** test, **0**
  tests deleted). Full battery green: `lazy-state.py`/`bug-state.py --test`, 1280 pytest, parity
  exit 0.

**Options:**
- **(a) Approve the removal (Recommended).** Sign off that the exclusion legitimately moved to
  `compute_state` and the supplement is redundant. A future run authors `GATE_VERDICT.md` with
  `checks.gate_weakening: hit-signed` + `override: operator-approved <date> — rationale` and
  `__mark_fixed__` completes. Per-change sign-off, not standing.
- **(b) Decline — keep the supplement as defense-in-depth.** Re-add `_candidate_operator_deferred`
  as a belt-and-suspenders second exclusion path alongside the new `compute_state` branch; the fix
  is reshaped and re-verified.

**Recommendation:** (a) — the exclusion moved rather than vanished, the recurrence-prone class is
what motivated the move, and the R102 regression green-on-primary-mechanism is the evidence the
retire is safe.

## Why this is parked, not asked now

This is a park-mode run (`--park-needs-input`). A gate-weakening sign-off is a product-class
operator decision (`class: product`, `divergence: structural` — never provisional-eligible, and
gate-written sentinels never auto-accept). It is surfaced at the run-end flush for your ratification.
