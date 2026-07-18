---
kind: needs-input
feature_id: merged-head-excludes-parked-not-operator-deferred-deadlocks
written_by: spec-phases
decisions:
  - Disposition of a bug whose fix already landed out-of-pipeline (via harden-harness)
date: 2026-07-17
next_skill: spec-phases
class: product
divergence: contained
---

# /plan-bug (via /spec-phases --batch) — Needs Input

The planning gate cannot author a fix plan: the touchpoint audit found the SPEC's
**entire fix scope is already implemented, committed, and passing tests** on disk.
Authoring phases here would build against a falsified premise (that the fix is
unimplemented). This is a premise-grade contradiction → HALT for an operator
disposition decision.

## Decision Context

### 1. Disposition of a bug whose fix already landed out-of-pipeline (via harden-harness)

**Problem:** This bug's investigation SPEC (`Status: Concluded`) describes a three-part
fix scope: (1) a new pure predicate `spec_dir_operator_deferred(spec_dir)` recognizing a
`DEFERRED.md` sentinel, (2) generalizing the merged-head exclusion resolver
`parked_item_ids → nondispatchable_item_ids` (ORs park + operator-defer), and (3) wiring
both state-script callers to it. The touchpoint audit found **all three already on disk
and committed**:

- `lazy_core/docmodel.py:2276` — `spec_dir_operator_deferred` exists exactly as specified
  (pure, fail-safe, `DEFERRED.md` existence check).
- `lazy_core/depdag.py:1496` — the resolver is already renamed `nondispatchable_item_ids`
  and ORs `spec_dir_operator_deferred` with `spec_dir_would_park`, with the "no-park-facet →
  empty" fast-path dropped, per the SPEC.
- Both callers wired: `lazy-state.py:12375` (`--next-merged`) and `bug-state.py:9405`
  (`--emit-prompt`), each commented with this exact bug slug.
- Regression fixtures (a) + (c) + the no-op case exist as
  `test_spec_dir_operator_deferred_predicate` / `test_merged_head_override_excludes_parked_head_no_deadlock`
  et al. — **6 passed, 0 failed** when re-run this cycle.

Git confirms the fix landed via the **harden-harness** route, not the bug pipeline:
commit `84e656ec harden(script): exclude OPERATOR-DEFERRED items from merged-head
computation`, with `bf29ed77 harden(docs): hardening-log Round 57 + intervention record`
recording it. The bug SPEC was never reconciled with that landed fix — it still sits in
the open bug queue at `Status: Concluded`, with no `PHASES.md`, no `FIXED.md` receipt, and
no queue trim. This is precisely the "Fixing a bug OUT-OF-PIPELINE" gap `docs/bugs/CLAUDE.md`
warns about: a harden round shipped the code but left the SPEC untended, so the pipeline is
now asking to re-plan a completed fix.

I cannot resolve this myself: the `**Status:** Fixed` flip + `FIXED.md` receipt are
orchestrator-only (`__mark_fixed__` gate), and the archive-on-fix move
(`bug-state.py --archive-fixed`) is orchestrator/operator-only. The options diverge in the
bug's final recorded state and its receipt provenance (data semantics), so this is a
product-class disposition call for the operator.

**Options:**
- **Reconcile as fixed-out-of-pipeline (Recommended)** — Treat the landed `84e656ec` as the
  fix. The orchestrator/operator writes a `FIXED.md` receipt (citing commit `84e656ec` as
  the fix commit and the 6 green regression tests as evidence), flips the SPEC to
  `**Status:** Fixed`, and runs `python3 user/scripts/bug-state.py --repo-root . --archive-fixed
  docs/bugs/merged-head-excludes-parked-not-operator-deferred-deadlocks` (the one script-owned
  mover — evidence header, `git mv` into `_archive/`, inbound-ref repoint, queue trim, one
  commit). This is the honest, lowest-friction path: the fix is real, committed, and
  test-verified; the only debt is the un-run pipeline bookkeeping. Provenance is
  `backfilled-unverified`-class (fix landed outside the gate), recorded honestly. Note the
  code fix carries **no MCP-reachable surface** (a pure state-script predicate), so the
  normal `/mcp-test` tail does not apply — a `SKIP_MCP_TEST.md` / no-MCP-surface disposition
  fits.
- **Re-drive validation through the pipeline** — Author a verification-only `PHASES.md` that
  asserts the already-landed predicate/resolver/callers + the 6 regression fixtures, then let
  `/execute-plan` → `__mark_fixed__` certify it. Produces a fully gated `FIXED.md` receipt
  (`provenance: gated`) rather than a backfilled one, at the cost of a redundant plan+execute
  round for code that is already done and green. Choose this only if a gated receipt for this
  specific bug is worth the extra cycles.
- **Supersede / Won't-fix as duplicate of the harden round** — Mark the SPEC `Won't-fix`
  (superseded by the `84e656ec` harden-round work), archive it, and trim the queue, without a
  fix-receipt. Cleanest bookkeeping if you consider the harden round + its Round-57 hardening
  log the authoritative record and don't want a separate bug-pipeline receipt. Loses the
  explicit bug→fix receipt linkage.

**Recommendation:** Reconcile as fixed-out-of-pipeline — the fix is real, committed
(`84e656ec`), and test-verified (6/6 green); the honest move is to write the receipt + archive
via the sanctioned `--archive-fixed` path rather than re-planning completed work or discarding
the bug→fix linkage.
