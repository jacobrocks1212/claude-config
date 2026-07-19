---
kind: gate-verdict
feature_id: merged-head-oracle-deadlocks-on-unreached-parked-same-pipeline-head
gate_version: 1
date: 2026-07-19
scope_hit:
  - user/scripts/bug-state.py
  - user/scripts/lazy-state.py
  - user/scripts/lazy_core/dispatch.py
checks:
  overfit: pass
  tautology: pass
  gate_weakening: pass
  complexity: declared
retires: the emit-path `same_ids` fast-path (`if iid in same_ids: break`) — the change removes the divergent second oracle-walk implementation so the emit path reuses the SAME scoped `is_dispatchable` re-inference the stateless `--next-merged` walk already used. Net-retire (one of two duplicate oracle walks eliminated), not net-new.
---

## Adversarial answers

### overfit
`harness-gate.py` reported `flags: null` / `gate_weakening_hit: false` over the fix range.
No literal was appended to any matcher. The fix DELETES a fast-path branch and routes every
unreached merged-head candidate through the pre-existing scoped `is_dispatchable` oracle — it
generalizes rather than fits. There is no near-neighbour recurrence the change misses because it
stops keying on "is this id in the same-pipeline set" (the buggy structural assumption that any
higher same-pipeline item is dispatchable) and instead keys on the item's actual per-item
dispatchability, which is the structural property that generates the whole class.

### tautology
Not applicable (no `## Intervention Hypothesis` tautology flag; this is a defect fix, not a
self-observing gate). If the fix were broken, its metric would NOT look identical to working: a
broken exclusion re-deadlocks the exact live repro (a parked/gated head suppressing
`cycle_prompt_ref` for every probe), caught by the new regression test added in `1b7d420f` and by
the live re-probe that now advances the merged head past the excluded item. The independent signal
is the deterministic `test_lazy_core` regression (1278/1278) + the live probe advancing.

### gate_weakening
No gate-weakening hit. The diff deletes no `def test_*`, changes no gate numeric literal, grows no
sanction/exemption set, adds no `*_BYPASS`, and removes no deny/refuse branch. It removes a
control-FLOW fast-path (`same_ids` break) that was producing WRONG dispatch decisions — tightening
correctness, not loosening a gate.

### complexity
`retires:` (frontmatter) — this eliminates one of two divergent oracle-walk implementations, so the
merged-head actionability decision now has a SINGLE code path (the scoped re-inference walk) shared
by both emit and stateless callers. The added regression test pays for the retained surface. Net
reduction in duplicated logic.
