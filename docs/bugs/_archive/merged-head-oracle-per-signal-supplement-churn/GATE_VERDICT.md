---
kind: gate-verdict
feature_id: merged-head-oracle-per-signal-supplement-churn
gate_version: 1
date: 2026-07-19
scope_hit: [user/scripts/lazy_core/dispatch.py, user/scripts/lazy-state.py, user/scripts/lazy_core/depdag.py, user/scripts/lazy_core/docmodel.py]
checks:
  overfit: pass
  tautology: pass
  gate_weakening: hit-signed
  complexity: declared
retires: "_candidate_operator_deferred (+ its walk-loop application) in lazy_core/dispatch.py —
  superseded by a first-class operator-defer branch in feature compute_state (lazy-state.py,
  WU-1)"
override: operator-approved 2026-07-19 — the exclusion moved up-stream into compute_state rather
  than vanishing; the merged-head oracle's primary is_dispatchable(scoped_probe(feature)) now
  returns non-dispatchable for a deferred feature without the file-predicate patch, so the
  supplement was redundant, not load-bearing.
---

## Adversarial answers

### overfit
Not flagged against the scoped production diff. No literal was appended to a matcher/
alternation/allow-list; the change removes a redundant helper and relocates its exclusion to the
primary mechanism.

### tautology
No `## Intervention Hypothesis` applies — this is a bug fix (retiring per-signal supplement
churn), not a harness-behavior intervention with a self-emitted success metric. Completion
evidence is objective: `lazy-state.py`/`bug-state.py --test`, 1280 pytest, parity audit — all
green, independent of the change's own claim.

### gate_weakening
**The exact weakening flagged.** Commit `461d42d8` ("retire oracle operator-defer supplement")
deleted `def _candidate_operator_deferred(_iid)` and its walk-loop application from
`lazy_core/dispatch.py`. That helper was the file-predicate supplement that made the merged-head
oracle exclude operator-deferred (`DEFERRED.md`) features — a removed exclusion predicate, which
`harness-gate.py` (at the version live for this cycle) reported as `gate_weakening: hit` over the
fix range `1904e359..efb698ed`.

**Underlying-defect alternative considered:** re-add `_candidate_operator_deferred` as a
belt-and-suspenders second exclusion path (Option b in `NEEDS_INPUT.md`) — rejected as unnecessary
duplication, not a real defect-fix alternative, once the primary mechanism (`compute_state`) was
confirmed to cover the same exclusion.

**Operator rationale (why approved, not a real weakening):** the exclusion did not disappear —
it moved up-stream into `lazy-state.py`'s feature `compute_state` as a first-class operator-defer
branch (this bug's WU-1), so `is_dispatchable(scoped_probe(feature))` (the oracle's primary check)
now returns non-dispatchable for a deferred feature without the file-predicate patch. This is the
exact durable generalization spun off from harden R102 to stop the
`merged-head-includes-parked/deferred` deadlock class from re-recurring (R56/R57/R101/R102). The
R102 unit regression was re-pointed at the primary mechanism and stays green with the supplement
gone; a new real-serving-path subprocess regression was added (net **+1** test, **0** tests
deleted — no test-coverage weakening accompanies the code-path retirement). Full battery green:
`lazy-state.py`/`bug-state.py --test`, 1280 pytest, parity audit exit 0.

### complexity
`retires: _candidate_operator_deferred` — the churn-prone per-signal file-predicate supplement is
removed once its exclusion is proven redundant with the primary `compute_state` mechanism. Pure
retire, no added surface.
