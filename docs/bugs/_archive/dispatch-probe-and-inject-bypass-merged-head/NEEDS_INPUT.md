---
kind: needs-input
feature_id: dispatch-probe-and-inject-bypass-merged-head
written_by: plan-bug
class: product
divergence: contained
next_skill: lazy-bug
decisions:
  - Fix already shipped out-of-pipeline (commit 1af48e1d) — reconcile as Fixed, or plan residual scope?
date: 2026-07-17
---

## Decision Context

### 1. Fix already shipped out-of-pipeline (commit 1af48e1d) — reconcile as Fixed, or plan residual scope?

**Problem:** `bug-state.py` routed this bug to `/plan-bug` (Step 5: "plan bug from
concluded investigation") so a `PHASES.md` + implementation plan would be authored. But the
fix this SPEC scopes is **already fully implemented and committed in-tree** — it landed as an
out-of-pipeline `harden(script)` commit, never went through the plan → execute pipeline, and the
bug doc was left at `**Status:** Concluded` (no `PHASES.md`, no `FIXED.md` receipt, not archived).
`/plan-bug` cannot proceed honestly: authoring a plan to "implement" code that already shipped
would fabricate work and write false provenance (an `IMPLEMENTED.md` claiming this pipeline run
produced code an earlier commit actually shipped). This is the `docs/bugs/CLAUDE.md`
"Fixing a bug OUT-OF-PIPELINE" reconciliation case, surfaced late.

Evidence the fix shipped (verified this cycle):
- **Git history:** `1d34797d` = the investigation (this SPEC); **`1af48e1d` = "harden(script):
  route dispatch-bound probe + inject hook by merged head, not sticky pipeline"** = the fix.
- **All five SPEC fix-scope items are present in-tree**, with code comments citing this exact bug
  slug: (1) `lazy_core/dispatch.py:358 merged_head_override(...)`; (2) `lazy-state.py:~13791` the
  `--emit-prompt` `merged-head-diverged` withhold; (3) `bug-state.py:449
  _load_feature_queue_for_merged` + the `9400/9469` mirror + withhold; (4) `lazy_inject.py:100-168`
  `_run_probe` selects the state script by `_merged_head_type()` (the `--next-merged` head), failing
  open to the marker pipeline; (5) regression fixtures in `test_hooks.py` + `tests/test_lazy_core/test_dispatch.py`.
- **Two follow-up bugs are already built on top** of this fix and still open in `docs/bugs/`
  (`merged-head-diverged-stalls-on-gated-head`, `merged-head-diverged-withholds-on-not-skip-ahead-ready-milestone`),
  proving the fix landed and was subsequently iterated.
- The SPEC's Root-Cause Trace Gate (SEAM A) **passes** — the causal finding is `traced`, not
  `asserted` (citations verified against the live serving code). So this halt is NOT a trace-gate
  failure; it is a "the traced fix already shipped" reconciliation.

The reconciliation action (write `FIXED.md`, `bug-state.py --archive-fixed`, link provenance to the
existing commit) is **orchestrator-owned** — a cycle subagent may not flip `**Status:**` to Fixed
or write `FIXED.md`. Hence this halt rather than an in-cycle resolution.

**Options:**
- **Reconcile as already-Fixed (Recommended)** — Do NOT author `PHASES.md` / a plan. Instead the
  orchestrator (or operator) closes this bug against the existing work: write the `FIXED.md`
  receipt, run `python3 user/scripts/bug-state.py --repo-root . --archive-fixed
  docs/bugs/dispatch-probe-and-inject-bypass-merged-head`, and link provenance to the fix commit
  (`python3 user/scripts/lazy-state.py --link-provenance --id
  dispatch-probe-and-inject-bypass-merged-head --commits 1af48e1d`). Cost: near-zero; matches the
  overwhelming in-tree evidence. Risk: if the shipped fix silently misses a corner of the SPEC's
  5-item scope, it is archived believed-complete — but that is recoverable (reopen), and the
  follow-up bugs already exercised this code path, lowering the risk. Reversible.
- **Plan residual scope only** — If an operator review of the shipped code against the SPEC's
  fix-scope finds a genuine gap (e.g. a fix-scope item that was NOT actually landed by
  `1af48e1d` or the merged-head follow-ups), author `PHASES.md` + a plan scoped to that gap ONLY
  — never a plan re-implementing the already-shipped items. Cost: a review pass + a bounded
  corrective plan. Use only if the review finds a real gap; otherwise it fabricates redundant work.

**Recommendation:** Reconcile as already-Fixed — the fix is committed (`1af48e1d`), all five
fix-scope items are present in-tree and attributed to this slug in code, and two follow-up bugs
already build on it; planning would fabricate work for shipped code. A quick operator confirmation
that no fix-scope item was missed is the only judgment needed before the orchestrator archives it
and links provenance to `1af48e1d`.
