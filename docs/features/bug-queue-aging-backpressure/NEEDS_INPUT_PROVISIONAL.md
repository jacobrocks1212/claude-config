---
kind: needs-input
feature_id: bug-queue-aging-backpressure
written_by: spec
decisions:
  - D1 — backpressure mechanism: age-escalation in the merged comparator vs. an every-Nth-run
    aged-bug quota
date: 2026-07-13
next_skill: none
class: product
divergence: contained
audit_divergence: contained
---

# bug-queue-aging-backpressure — Needs Input

D2/D3/D4 are `mechanical-internal` and are auto-accepted per their SPEC `**Recommendation:**`
lines — see `SPEC.md`'s `## Locked Decisions` / `RESEARCH_SUMMARY.md`. D1 is the SPEC's own
explicitly-flagged `product-behavior (operator decision required)` decision, gating full
ratification.

## Decision Context

### 1. D1 — Backpressure mechanism: comparator escalation vs. run quota

**Problem:** What forces an aged, deprioritized bug to actually get worked, instead of sitting at
merged priority 99 forever?

**Options:**
- **A — age-escalation in the merged comparator (Recommended):** `merged_priority()` gains an age
  term — each 7-day quantum since the bug's `**Discovered:**` date bumps its effective priority one
  notch toward 0, capped at a P1-equivalent floor (rank 1) so a genuine P0 always outranks
  escalation. Pure function of (queue entry, `today`) — deterministic, testable with injected
  dates, zero new orchestrator prose or marker state. A pinned/deprioritized bug climbs back into
  contention by itself once its pin expires.
- **B — every-Nth-run aged-bug quota:** the `/lazy-batch` unified driver works one aged harness bug
  every N runs (or N cycles) regardless of merged order. Simple to reason about, but lives in
  SKILL prose + new marker counters — a fresh instance of the exact skippable-prose-obligation
  class `docs/bugs/efficacy-future-check-unenforced-orchestrator-prose/` already documents as a
  known failure mode, and needs new durable per-run state the marker doesn't currently carry.

**Recommendation:** A — the only shape that stays entirely inside the script-owned ordering layer
(the house invariant: deterministic state in scripts, never orchestrator hand-arithmetic or a new
skippable prose obligation).

## Resolution

resolved_by: auto-provisional
decision_commit: (recorded at the commit that lands this NEEDS_INPUT_PROVISIONAL.md)

**Provisionally accepted** under the operator's overnight park-provisional directive (this
session, 2026-07-13). Option A is adopted and IMPLEMENTED against:

- `lazy_core.age_escalated_rank(base_rank, discovered, today)` — the pure escalation formula (7-day
  quantum, floor rank 1), plus `lazy_core.pin_is_active` (D2-A pin-expiry gate) and
  `lazy_core.merged_priority`'s bug branch (age-escalates an explicit severity always; falls back
  to the SPEC's own `**Severity:**` line only past an EXPIRED pin — a bare legacy `severity: null`
  with no `pinned_at` is byte-identical to before, see SPEC's "V1 scope narrowing").
- `bug-state.py::_find_open_bug_dirs`'s sort key mirrors the same age term (Technical Design's
  "Bug-side mirror" row) so autodiscovered-dir ordering agrees with the merged view.
- `lazy_core.bug_priority_marker` + `lazy-queue-doc.py::_bug_aging_cell` (D4-A rendering) and
  `kpi-scorecard.py`'s two new `sentinel-scan` selectors (Phase 3) are independent of the A-vs-B
  choice (they read on-disk state / the comparator's OUTPUT, not its mechanism) and are unaffected
  by a future redirect to B.
- Full hermetic test coverage in `user/scripts/test_lazy_core.py` (age-escalation caps, P0
  dominance, no-Discovered/malformed-date fail-open, pin-active-suppresses,
  pin-expired-falls-back-to-SPEC-severity, legacy-null-no-pin-unchanged) — see PHASES.md Phase 1.

SPEC.md's Status stays **Draft** and NO `COMPLETED.md` is written — completion is mechanically
blocked while this unratified `NEEDS_INPUT_PROVISIONAL.md` exists. The operator ratifies or
redirects this choice (comparator escalation vs. run quota) before the feature can complete.

**Divergence graded `contained`** — a redirect to Option B touches a bounded set of sites: remove
the age term from `lazy_core.age_escalated_rank`/`merged_priority`'s bug branch and the
`_find_open_bug_dirs` mirror, and add the SKILL-prose quota + new run-marker counter fields
instead. It does NOT touch D2's pin lifecycle (`pin_bug_severity`, `pinned_at`/`pinned_until`
fields), D4's queue-doc rendering machinery (the Discovered-date column persists regardless of
mechanism; only the "⏫ escalated" marker's semantics would change), or Phase 3's KPI selectors
(both read `docs/bugs/` directly, independent of the comparator). No persistent data schema
changes hands, and no other feature's contract depends on the A-vs-B choice — a redirect is a
bounded corrective phase, not a data migration or cross-feature rework, satisfying the two-key
eligibility predicate (`divergence` + `audit_divergence` both `contained`) `park-provisional-acceptance`
is designed for.

**Choice:** A — age-escalation in the merged comparator, implemented and tested; awaiting operator
ratification.
