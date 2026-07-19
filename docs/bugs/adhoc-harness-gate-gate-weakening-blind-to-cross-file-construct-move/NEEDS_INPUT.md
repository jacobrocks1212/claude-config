---
kind: needs-input
feature_id: adhoc-harness-gate-gate-weakening-blind-to-cross-file-construct-move
written_by: lazy-batch-input-audit
decisions:
  - Cross-file reconciliation shape for gate_weakening — content-identity move detection vs aggregate net
date: 2026-07-19
next_skill: plan-bug
class: product
---

# input-audit — Needs Input

The `/spec-bug` investigation for this defect is Concluded and its root cause (per-file
reconciliation denominator blind to a cross-file construct move) is well-traced. But the SPEC's
own `## Open Questions` flags a **PRODUCT-class** fix-approach fork — how strong the
gate-weakening detector remains after the fix — and only *defers* it to `/plan-bug` in
non-halting prose (recommending one option). "Open Questions" prose does not halt the pipeline,
so in this operator-absent batch run that fork would be auto-accepted toward the recommendation
without you ever confirming it. This surfaces it so you own the gate-strength call before
`/plan-bug` locks the fix into PHASES.

## Decision Context

### 1. Cross-file reconciliation shape for gate_weakening — content-identity move detection vs aggregate net

**Problem:** `harness-gate.py`'s `gate_weakening` detector currently reconciles removed vs added
gate-refusal constructs (`permissionDecision: deny`, `exit 3`, `refuse_*()`, and `def test_*`)
**per file** — so a behavior-preserving refactor that MOVES such a construct out of one file into
a shared sibling (the live `shared-hook-lib` case: deny boilerplate migrated into
`hook-prelude.sh`) nets `+1` on the source file and false-positives a `hit`, forcing a redundant
operator `GATE_VERDICT.md` sign-off. The fix must reconcile across the whole change's file set.
But `gate_weakening` is a **security gate** whose entire purpose is to catch a genuine gate
removal, and it "routes to operator sign-off, NEVER judgment-passable" (SPEC D4). *How* the
cross-file reconciliation is done directly sets the detector's false-NEGATIVE surface — how easily
a genuine removal can now slip through — so this is a user-visible (operator-visible) gate-strength
call, not a mechanical implementation detail. Cited at `SPEC.md` `## Open Questions` (the design
fork, labeled PRODUCT-class) and `## Proven Findings` → "Fix vector (for `/plan-bug`; not locked
here)". This decision is control-surface / gate-weakening plane — the most operator-guarded surface
in the repo — and the fix itself will additionally route to the anti-overfit sign-off because it
relaxes a detector.

**Options:**
- **(b) Content-identity move detection (Recommended)** — reconcile a removal in file A only when the *same construct text* is added in file B within the same change; anything else still counts as a removal. Precise: near-zero added false-negative surface — an unrelated deny construct added elsewhere can no longer silently mask a genuine removal. Cost: more code (must key reconciliation on normalized construct text, not just counts) and a slightly larger regression-fixture set. Best preserves the gate's strength while killing the false positive. Reversibility: high (pure function; fixtures pin behavior).
- **(a) Aggregate net across the change** — sum removed constructs across all files vs sum added across all files; flag only when the whole-change net is positive. Simplest, smallest diff, closest to today's counting logic. Risk: a genuine gate removal in file A masked by an *unrelated* deny/refusal construct added in file B nets to zero and **evades the gate** — a real false-negative hole punched into a security detector to save code. Reversibility: high, but the weakening is silent until it bites.
- **(c) Behavior-preserving-refactor exemption keyed on a net-count marker** — keep per-file counting but suppress the `hit` when a same-change signal (e.g. a recognized shared-lib target receiving the construct, or an explicit refactor marker) indicates a move. Middle ground on code size, but introduces an exemption surface — itself the kind of allow-list construct the anti-overfit `overfit` detector is designed to distrust, and more prone to overfitting to the `shared-hook-lib` shape than a general reconciliation. Reversibility: moderate (the exemption becomes a maintained special case).

**Recommendation:** (b) Content-identity move detection — it fixes the false positive without weakening the security gate's false-negative surface, matches the SPEC's own recommendation, and avoids adding an exemption/allow-list construct the anti-overfit plane distrusts.
