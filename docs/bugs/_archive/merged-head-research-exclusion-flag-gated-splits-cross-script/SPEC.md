# Merged-head research-pending exclusion is flag-gated → cross-script split-brain deadlock

**Status:** Fixed
**Severity:** P1
**Discovered:** 2026-07-18 (observed live during a `/lazy-batch-parallel` run on AlgoBooth; no-route)
**Fixed:** 2026-07-18
**Fix commit:** 981191ae
**Related:** `docs/bugs/_archive/merged-head-diverged-withholds-on-research-skipped-head` (Round 91 /
commit `baf07a6d` — the immediately-prior facet this bug is the follow-up incompleteness of);
`docs/bugs/merged-head-diverged-stalls-on-gated-head`,
`docs/bugs/_archive/merged-head-excludes-parked-not-operator-deferred-deadlocks`,
`docs/bugs/_archive/merged-head-includes-parked-items-deadlocks-park-run` (sibling facets of the
merged-head exclude-set recurring class); `docs/features/unified-pipeline-orchestrator/` (the
merged-view / type-dispatch contract). This is the **6th facet** of the merged-head exclude-set
class; the structural generalization (a single per-item actionability oracle) was already spun off
as a `/spec` handback by Round 91 — this round reinforces that handback, it does not duplicate it.

## Trigger

Orchestrator-observed no-route friction during a live `/lazy-batch-parallel` run on AlgoBooth
(2026-07-18). Two feature heads (`merged-head-actionability-oracle` and a subagent-wedge feature)
were research-pending (`NEEDS_RESEARCH.md` present, `RESEARCH.md` absent), and a bug
(`external-owner-contracts-locked-without-consultation`) was on-disk `Concluded` (dispatchable →
needs `/plan-bug`). Neither state script would emit ANY route:

```
lazy-state.py --emit-prompt --skip-needs-research   (feature side, skip-aware)
    → feature shared-hook-lib WITHHELD,
      merged_head = external-owner-contracts-locked-without-consultation (bug)
      route_overridden_by: merged-head-diverged

bug-state.py --emit-prompt   (bug side, scoped to that bug — NO --skip-needs-research flag exists)
    → bug WITHHELD,
      merged_head = merged-head-actionability-oracle (research-pending FEATURE)
      route_overridden_by: merged-head-diverged

bug-state.py --skip-needs-research   → argparse usage error (flag absent)
```

The two scripts compute **different merged heads for the same on-disk state**: the feature side
(with the skip flag) excludes the research-pending features and lands the bug at the head; the bug
side (no flag, cannot accept one) does NOT exclude them and lands a research-pending feature at the
head. Each then withholds its own emit because the head diverges from the item it would dispatch.
Cross-script split-brain deadlock — no dispatchable route from either script.

## Reconstructed route (divergence point)

Both `--emit-prompt` merged-head withholds build their exclude set from
`lazy_core.nondispatchable_item_ids(feature_items, bug_items, repo_root, ...)`. Round 91
(`baf07a6d`) added a `skip_needs_research: bool = False` kwarg that ORs the research-pending file
predicate (`docmodel.spec_dir_research_pending`) into the exclude set **only when the flag is
True**, and wired that kwarg ONLY at `lazy-state.py`'s caller (`skip_needs_research=args.skip_needs_research`).
Round 91's log explicitly left `bug-state.py`'s coupled caller "byte-identical" on the reasoning
that "research gating is a feature/bug divergence."

**Divergence point:** that reasoning was wrong for the MERGED-head computation. `bug-state.py`'s
merged-head-override reads the FEATURE queue too (`_load_feature_queue_for_merged`) to detect a
higher-priority cross-pipeline item — so it MUST exclude a research-pending FEATURE head to avoid
withholding a dispatchable bug behind it. But `bug-state.py` has no `--skip-needs-research` flag
(and cannot walk the feature queue's skip decisions, so `probe_skipped_ids(state, _mo_bugs)` — bug-
scoped — can never fold in a feature head). The exclusion is therefore reachable on the bug side
ONLY through the file predicate in `nondispatchable_item_ids`, and the flag-gate makes that
predicate inert on the bug side. Result: the exclude set (hence the merged head) diverges across
the two scripts.

## Root cause

**`root_cause_class: script-defect`** — the research-pending exclusion in
`nondispatchable_item_ids` (`lazy_core/depdag.py:1571`) is gated on `skip_needs_research`, a flag
only `lazy-state.py` threads and `bug-state.py` cannot accept. The gate makes the two scripts'
merged-head exclude sets structurally inconsistent for the same on-disk state.

The flag-gate was over-cautious. Round 91 gated it to preserve the "WITHOUT the flag a research
head HALTS, not skips" contract — but that contract is enforced in `compute_state`'s WALK (the
Step-5 research gate), which is entirely separate from the merged-head-override exclude set. The
merged-head-override never CREATES a dispatch; it only WITHHOLDS an already-chosen forward route
when a higher-priority DISPATCHABLE item diverges. A research-pending head is by definition NOT
dispatchable this run (either it halts, or it is skipped), so excluding it from the merged-head
computation can never suppress a legitimate withhold — and on a halt state the override is not
reached at all (there is no forward route to withhold). Excluding it unconditionally is therefore
byte-identical for `lazy-state.py`'s forward routing (the head was already excluded via the file
predicate under `--skip-needs-research`, or via `probe_skipped_ids`/`gated_heads` under default
skip-ahead) and CORRECT for `bug-state.py` (the only reachable exclusion path).

The on-disk `NEEDS_RESEARCH.md` / `RESEARCH_PROMPT.md`-without-`RESEARCH*.md` sentinel IS the
deliberate research-defer decision record — no flag context is needed to know the item is
non-dispatchable this run. The sentinel file is the SSOT; the flag was a redundant second gate that
only one of the two coupled scripts could read.

## Fix scope

Make the research-pending exclusion **unconditional** in `nondispatchable_item_ids` — drop the
`skip_needs_research and` gate on the `spec_dir_research_pending` predicate so BOTH scripts'
merged-head-override computations exclude a research-pending head identically:

1. `lazy_core/depdag.py::nondispatchable_item_ids` — change
   `if skip_needs_research and spec_dir_research_pending(spec_dir):` →
   `if spec_dir_research_pending(spec_dir):`. Keep the `skip_needs_research` kwarg accepted-but-
   inert (retained for call-site signature compatibility; documented as no longer gating — the
   sentinel file is the SSOT). Update the category-list + Scope-boundary docstring.
2. `lazy_core/docmodel.py::spec_dir_research_pending` — update the docstring (remove the
   "CONDITIONAL by caller intent / flag-gating lives in the caller" paragraph; the exclusion is now
   unconditional in both callers).
3. Tests (`tests/test_lazy_core/test_dispatch.py`): update the existing research-pending fixture to
   assert unconditional exclusion (excluded with AND without the flag), and ADD the cross-script
   split-brain regression fixture: a research-pending feature head + a `Concluded` on-disk bug must
   yield the **same** merged head from BOTH `lazy_core.merged_head_override` emit-path exclude
   computations (feature-side and bug-side) and land the bug at the head.

`retires:` the flag-gating of the research-pending exclusion (a redundant second gate); the
`--skip-needs-research` CLI flag itself and its `compute_state` WALK behavior are UNTOUCHED.

No gate weakened: the merged-head-diverged withhold is a stall-detector, not a completion/integrity
gate. Excluding more genuinely-non-dispatchable items from its input makes it fire only on real
higher-priority-dispatchable divergence — the correct direction.

## Verified symptom

Cross-script split-brain reproduced structurally by the new fixture: `nondispatchable_item_ids`
without the flag returns `set()` (empty) for a research-pending feature (pre-fix) so the bug-side
exclude set omits it and the two scripts diverge; post-fix it returns the research-pending id
unconditionally so both scripts land the bug at the merged head and emit the bug route.
