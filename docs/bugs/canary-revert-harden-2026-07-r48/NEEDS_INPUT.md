---
kind: needs-input
feature_id: canary-revert-harden-2026-07-r48
written_by: spec-bug
next_skill: spec-bug
class: product
stub_origin: true
divergence: contained
decisions:
  - Disposition of shipped change 251187c8 (canary harden-2026-07-r48) — close-as-noise, revert, or redesign
date: 2026-07-18
---

## Decision Context

### 1. Disposition of shipped change 251187c8 (canary harden-2026-07-r48) — close-as-noise, revert, or redesign

**Problem:** The harness-change **canary** for intervention `harden-2026-07-r48` tripped and enqueued this bug. A canary watches a shipped control-surface change for one observation window and, if a targeted friction signal regresses, *flags and enqueues* a revert-triage item for a human — it never reverts automatically (D4). The tripped change is commit `251187c8`, which made the `lazy-cycle-containment.sh` 2nd-feature tripwire **group-aware** so it stops false-denying a grouped feature's own commits (`docs/features/<group>/<slug>/…`, the layout AlgoBooth's queue produces). The canary is charged with the signal `event:containment-refusal` (each containment deny the hook emits) and expected it to **decrease**. It instead tripped on a **+334% band regression** (72.85 → 316.25 events/run over 4 window runs, band ±25%) — but this is a **band-only** trip: **zero** fresh incidents were attributed to the change's own surface. Investigation (`SPEC.md`, cause-traced) proves the change is *mechanically incapable* of increasing that signal: it makes the *allow* predicate strictly more permissive (deny set can only shrink), leaving ungrouped features byte-identical, and a no-weakening regression test guards the genuine-deny path. The +334% is unrelated in-window volume (more runs / more *legitimate* containment denials), not harm from this change. This decision is operator-owned because it forks a shipped harness behavior and closing a canary trip as noise is human-triage by design.

**Options:**
- **Close-as-noise — keep the fix, tune the canary band (Recommended)** — Accept that the trip is a confounded band-only signal and do **not** revert. `251187c8` is correct and tested; keeping it preserves the grouped-feature false-deny fix. Record the trip as noise (feeds the `canary-trip-precision` KPI) and, as a separate follow-up, consider tightening the D2 tripwire to require non-empty D3 surface attribution (or a wider band) for high-volume self-emitted signals like `event:containment-refusal`. Cost: near-zero; reversible; leaves the real bug fixed. Risk: none identified — the change cannot produce the observed regression.
- **Revert 251187c8** — `git revert` the commit (plain revert applies; no coupled-pair scope). **This re-introduces a real, tested defect** (`lazy-cycle-containment-misparses-grouped-feature-paths`): grouped-feature cycle-subagent commits would again be **false-denied**, breaking AlgoBooth's grouped-queue runs, and would *increase* false-positive containment denies — the opposite of the intervention's goal. Rework blast radius: bounded (one commit + its tests). Recommended against — it undoes a correct fix on the strength of a signal the fix cannot have caused.
- **Redesign the fix** — Re-implement the group-aware carve-out differently. There is no identified defect in the current implementation (it is correct, minimal, and regression-tested), so this is effort with no target. Recommended against unless the operator has a specific concern with the `_path_under_feature` approach not surfaced by this investigation.

**Recommendation:** Close-as-noise — the change is cause-traced as mechanically deny-*reducing* and drew zero surface attribution; reverting would re-break grouped features, and redesign has no defect to target. The trip is best used as a signal to tune the canary's D2 band for high-volume self-emitted signals.
