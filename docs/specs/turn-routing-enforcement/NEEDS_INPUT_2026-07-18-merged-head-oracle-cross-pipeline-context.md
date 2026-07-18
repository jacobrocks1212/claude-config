---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
class: product
divergence: structural
next_skill: harden-harness
decisions:
  - "Cross-pipeline / stateless merged-head classification: replace the completed oracle's Locked-Decision-L3 per-item scoped `compute_state` + `is_dispatchable` walk (structurally blind to context-dependent cross-pipeline skips) with a mechanism that reuses each pipeline's FULL-probe context — recommended: the merged head is the higher-merged-priority of the two pipelines' actual full-probe dispatch heads. Revises a LOCKED decision of a COMPLETED feature, coupled-pair mirrored across three sites. (harden Round 95, 2026-07-18)"
  - "Spike-pipeline-role interaction: should a `blocker_kind: runtime-spike-verdict-pending` BLOCKED head EVER be classifiable as a dispatchable merged head (its scoped route is now a `spike` cycle), or is it always a gated head skip-ahead skips for merged-head ordering (matching `_gated_head_kind`)? (harden Round 95, 2026-07-18)"
date: 2026-07-18
---

## Decision Context

An observed-friction dispatch (item in flight `managed-llm-credits`, AlgoBooth, unified
`/lazy-batch` driver with both queues populated) surfaced a **total no-route deadlock**: three
inconsistent merged-head computations in the SAME cycle, each `--emit-prompt` probe WITHHOLDING its
forward route naming the OTHER pipeline's item, and `--next-merged` naming a genuinely-BLOCKED
feature that cannot be dispatched. Root cause is CONCLUDED and deterministically reproduced —
`docs/bugs/merged-head-oracle-scoped-probe-blind-to-cross-pipeline-skip-context/SPEC.md`.

The defect lives in a **completed** feature's **Locked Decision L3**
(`docs/features/merged-head-actionability-oracle/SPEC.md`): the merged-head exclude set classifies
**cross-pipeline** and **stateless `--next-merged`** candidates via a **per-item scoped
`compute_state` probe** (`is_dispatchable`), while the **same-pipeline** side (L2) correctly reuses
the full probe's own `probe_skipped_ids`. A single-item scoped probe **cannot reproduce a
context-dependent skip** the cross-pipeline FULL probe makes — so context-skipped heads are
systematically misclassified as dispatchable. Two facets reproduced live:

- **BLOCKED-spike head** (`hydra-overlay`): scoped → `sub_skill=spike`, dispatchable; full probe →
  SKIPPED (`gated_heads`). The `spike-pipeline-role` Step-3 route (`lazy-state.py:3094`) turned a
  `runtime-spike-verdict-pending` `BLOCKED.md` into a dispatchable `spike` (was
  `terminal_reason="blocked"` → non-dispatchable) — the specific regression that widened the hole.
- **Not-independent / dep-gated head** (`inspector-track-dashboard`): scoped → `realign-spec`,
  dispatchable; full probe → SKIPPED (`skip_ahead_ready` fails: `independent` not set after a gated
  head was skipped).

**File-level divergence: `structural`** — the options revise a LOCKED decision (L3) of a COMPLETED
feature, change the core cross-pipeline dispatch-routing mechanism (WHICH item the driver works
next in every mixed-queue run), and are coupled-pair mirrored across three exclude-set construction
sites in two state scripts. A wrong provisional pick silently mis-prioritizes cross-pipeline work
and is expensive to redirect. Per the `/harden-harness` park-provisional structural carve-out, this
is HARD-PARKED: nothing is implemented until the operator ratifies. This differs from the ordinary
park-provisional default precisely because it overrides a baseline the operator already ratified
(the completed oracle feature and its locked L3).

**Verified facts (reproduced in-process 2026-07-18 against the live AlgoBooth queue):**
- `--next-merged` → `{hydra-overlay, feature}`; feature `--emit-prompt` merged_head →
  `{worktree-rust-test-binary-entrypoint-not-found, bug}` (WITHHELD); bug `--emit-prompt` merged_head
  → `{hydra-overlay, feature}` (WITHHELD).
- Feature full-probe head = `managed-llm-credits` (prio 2); bug full-probe head =
  `algobooth-rust-qg-excludes-lib-tests` (prio 99). Higher-priority-of-two = `managed-llm-credits` —
  the checkpoint's intended `next_route`.
- Fixing ONLY the BLOCKED-spike facet moves the deadlock to `inspector-track-dashboard` (facet 2) —
  confirming a single structural root, not two independent patches.
- `--park-blocked` breaks the deadlock (parks `hydra-overlay` consistently, un-blocks
  `inspector-track-dashboard`'s skip-ahead → driver dispatches `inspector-track-dashboard`). This is
  a valid operator interim workaround; the dispatched item differs from `managed-llm-credits`.

### 1. Cross-pipeline / stateless merged-head classification mechanism

**Problem:** L3's per-item scoped classification is structurally blind to context-dependent
cross-pipeline skips. The same-pipeline side (L2) already solved this by reusing the full probe's
own skip decisions; the cross-pipeline side needs the equivalent full-probe context, which a
per-item scoped probe cannot provide.

**Options:**
- **Higher-priority-of-two-full-probe-heads (Recommended).** Compute each pipeline's ACTUAL
  full-probe dispatch head once (both apply all skip-ahead / defer / gating context), and define the
  merged head as the higher-merged-priority of the two. A `--emit-prompt` merged-head-diverged
  withhold fires only when the OTHER pipeline's actual full-probe head genuinely out-prioritizes the
  current item (its true purpose — a P0 bug jumping the queue). Verified to yield
  `managed-llm-credits` here — the checkpoint's intent. Cost: replaces the merged-worklist-walk +
  L5 short-circuit machinery with a two-head comparison; each merged-head computation runs the OTHER
  pipeline's full probe once (bounded, not per-item); retires L3's scoped-probe walk; must be
  coupled-pair mirrored (`lazy-state.py` + `bug-state.py`, three sites) with `lazy_parity_audit.py`
  exit 0, and re-baselined against the completed oracle feature's characterization tests
  (`test_dispatch.py`).
- **Thread cross-pipeline full-probe skip context into the existing oracle walk.** Keep the
  merged-worklist-walk but feed it the cross-pipeline queue's FULL-probe skip set (run the other
  pipeline's full `compute_state` once, take its `probe_skipped_ids` + everything below its actual
  head) in place of the per-item scoped `is_dispatchable` classification. Preserves the L5
  short-circuit and partial-exclusion semantics. Cost: larger surface than option A for the same
  result; still runs the other pipeline's full probe.
- **Narrow patch: make a spike-pending BLOCKED head scoped-classify non-dispatchable (facet 1
  only).** Rejected as a standalone fix — VERIFIED insufficient (deadlock moves to
  `inspector-track-dashboard`); would give false confidence and over-fit one symptom of a structural
  root.

**Recommendation:** Option A (higher-priority-of-two-full-probe-heads). It is state-machine-correct
(each pipeline's full probe is the authority on its own next dispatch), matches the checkpoint
intent, and ends the 7-facet recurring class by construction. Requires operator ratification because
it revises the completed oracle feature's Locked Decision L3.

### 2. Spike-pipeline-role interaction: is a spike-pending BLOCKED head a dispatchable merged head?

**Problem:** `spike-pipeline-role` made a `runtime-spike-verdict-pending` `BLOCKED.md` route to a
dispatchable `spike` cycle at Step-3 (per-item), but `_gated_head_kind` still classifies any
`BLOCKED.md` as a gated head skip-ahead skips. So the SAME head is "dispatchable" (per-item /
scoped) and "gated/skipped" (full-probe skip-ahead) — the classifier disagreement feeding facet 1.
Under option A the merged head reflects each pipeline's full-probe head, so a spike-BLOCKED head is
merged-non-dispatchable whenever skip-ahead skips it and merged-dispatchable only when it is the
pipeline's actual full-probe head (the last-workable-item gated_head_fallback case) — which is the
consistent behavior. This decision only needs an explicit operator ruling if the operator wants a
spike-BLOCKED head to be able to PRE-EMPT other pipelines' work as a merged head even while
skip-ahead would skip it.

**Options:**
- **Spike-BLOCKED is merged-dispatchable iff it is the pipeline's actual full-probe head
  (Recommended, and automatic under decision-1 option A).** Consistent with `_gated_head_kind` and
  the full-probe skip-ahead; no separate code path. A spike-BLOCKED head pre-empts cross-pipeline
  work only when it is genuinely the pipeline's next dispatch (nothing independent ahead of it).
- **Spike-BLOCKED always pre-empts as a merged head (special-case it dispatchable everywhere).**
  Cost: reintroduces the classifier disagreement in the opposite direction (skip-ahead skips it, but
  the merged head names it) — the same deadlock shape. Not recommended.

**Recommendation:** Option A — resolved automatically by decision-1 option A; ratify together.

## Out of scope (verified, not a decision)

- **`spike-pipeline-role`'s Step-3 dispatchable-spike route itself** is correct and stays — a
  spike-BLOCKED head SHOULD dispatch its `spike` when it is the pipeline's actual next work. The
  defect is only that the merged-head oracle trusted a per-item scoped probe of it as a
  cross-pipeline head. No change to `compute_state`'s own routing is proposed.
- **AlgoBooth queue ordering / `queue.json`** is target-repo DATA, outside the harness's edit scope.
  The bug-queue severity-vs-position ordering (`worktree` P1 at the tail) is not changed by this fix;
  option A honors each pipeline's own head (the bug pipeline dispatches in queue order).
