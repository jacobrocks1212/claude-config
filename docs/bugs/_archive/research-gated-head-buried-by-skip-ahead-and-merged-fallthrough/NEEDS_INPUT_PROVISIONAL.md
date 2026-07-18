---
kind: needs-input
feature_id: research-gated-head-buried-by-skip-ahead-and-merged-fallthrough
written_by: harden-harness
divergence: contained
audit_divergence: contained
decisions:
  - "'Outranks the fallthrough' = strictly ahead in the FULL merged ordering (priority + the feature-before-bug type tie-break), decided by next_merged — not a scalar-priority-only compare."
  - "Research-first classification when a gated head carries BOTH a live research prompt and a BLOCKED.md (aligns with the Step-1h research-blocked carve-out)."
date: 2026-07-17
class: policy
next_skill: harden-harness
---

## Decision Context

The default-on dependency-aware skip-ahead advanced PAST research-pending gated heads
and the unified merged-view driver fell through to a lower-priority bug, so the operator
never saw the needs-research halt for a high-priority (pre-release / P1) feature that a
Gemini upload would unblock in seconds. The fix treats research-gating distinctly from
BLOCKED-gating: a research-gated head that OUTRANKS the fallthrough target surfaces a
needs-research halt instead of being skipped.

The task specified the target behavior ("a research-gated head that is HIGHER
merged-priority than the item the driver would otherwise pick should trigger a
needs-research halt"), but two precedence sub-choices are genuine policy decisions worth
operator ratification. Both are IMPLEMENTED provisionally under the park-provisional
default (contained divergence — a routing-precedence change reversible by removing the
`research_halt_head` call; no architecture / persistent-data / gate-weakening).

### 1. "Outranks the fallthrough" = strictly ahead in the FULL merged ordering

**Problem:** How to decide a research head "outranks" the item the driver would otherwise
dispatch, when priorities can TIE (e.g. a P1 research feature and a P1 ready feature, or a
P1 research feature and a rank-1 aged bug).

**Options:**

- **Recommended (implemented provisionally):** Surface iff the research-gated head is the
  HEAD of the merged worklist once the merely-BLOCKED / host / device / dep skips stay
  excluded but the research-gated skips are re-included — i.e. strictly ahead in the FULL
  merged ordering, which already incorporates `merged_priority` AND the type tie-break
  (`non-p0-bug-outranks-p1-feature-on-aged-tie`: feature-before-bug at equal rank). This
  reuses the single ordering source (`next_merged`), never a second rule. At an equal
  scalar rank the merged ordering's own tie-break + stable queue order decides, so a
  research-gated head listed at the literal queue head surfaces over equal-rank work behind
  it, but a research head genuinely BELOW ready work does not (no over-halt).
- **Alternative — strict scalar priority only:** Surface iff `merged_priority(research
  head) < merged_priority(fallthrough)` (ignore the tie-break). This would NOT surface a P1
  research head over a rank-1 aged bug (equal scalar), re-burying the exact live scenario
  after the tie-break fix — rejected.
- **Alternative — always halt on any research-gated head anywhere in queue:** Over-halts
  when genuinely-independent lower-priority ready work exists (the task explicitly warns
  against this) — rejected.

**Recommendation:** the full-ordering rule (option 1) — it is the least-surprising
generalization and stays consistent with the operator-directed tie-break.

### 2. Research-first classification when a head carries BOTH a research prompt and BLOCKED.md

**Problem:** A gated head could carry BOTH a live research prompt (no RESEARCH.md) AND a
BLOCKED.md. Classify it `research` (surface-eligible) or `blocked` (skip-ahead-only)?

**Options:**

- **Recommended (implemented provisionally):** `research` takes precedence — aligning with
  the existing Step-1h research-blocked carve-out (a co-located live research gap on a
  blocked feature is routed to Step 4 research, not a corrective phase). A research gap is
  operator-resolvable; surfacing it is strictly more actionable.
- **Alternative — blocked wins:** Treat any BLOCKED.md as a hard block (skip-ahead only),
  never surfacing research. More conservative but contradicts the Step-1h carve-out and
  leaves an operator-resolvable gap buried — rejected.

**Recommendation:** research-first (option 1), consistent with Step-1h.

## Scope note

Both decisions are contained: reversible by changing the `research_halt_head` head-test
(decision 1) or the `_gated_head_kind` precedence order (decision 2), each a localized
constant/predicate. The `research_gated_heads` probe key, the feature-only asymmetry, and
the loop-free scoped-terminal re-emit are locked (not provisional).

## Resolution

*Recorded on 2026-07-17. Provisionally auto-accepted on recommendation (`--park-provisional` divergence two-key). Ratify or redirect via the provisional-ratification affordance before completion.*

resolved_by: auto-provisional
decision_commit: adb80ec79fe0cbc3194c5b9fcdefb336b2809d83

### 1. 1. "Outranks the fallthrough" = strictly ahead in the FULL merged ordering

**Choice:** the full-ordering rule (option 1)
**Notes:** Provisionally accepted — divergence graded contained (producer) / contained (input-audit); pending operator ratification.

### 2. 2. Research-first classification when a head carries BOTH a research prompt and BLOCKED.md

**Choice:** research-first (option 1), consistent with Step-1h.
**Notes:** Provisionally accepted — divergence graded contained (producer) / contained (input-audit); pending operator ratification.
