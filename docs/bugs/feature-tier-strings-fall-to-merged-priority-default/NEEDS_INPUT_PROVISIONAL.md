---
kind: needs-input
feature_id: feature-tier-strings-fall-to-merged-priority-default
written_by: harden-harness
divergence: contained
audit_divergence: contained
decisions:
  - "Legacy feature-tier string -> integer priority mapping (milestone/commercialization/major-initiative/follow-up/non-audio/4a/4b) on the unified merged-priority scale — pre-release=1 is operator-locked and NOT in scope."
date: 2026-07-17
class: product
next_skill: harden-harness
---

## Decision Context

The feature-tier axis of `lazy_core.merged_priority` was unified with the bug-severity
axis onto one integer scale (feature-tier-strings-fall-to-merged-priority-default). Named
feature-tier enums now map to integer priorities exactly parallel to bug severity
(`P0/P1/P2/Low -> 0/1/2/3`). The operator LOCKED `pre-release = 1` (== P1) as load-bearing:
`merged_priority(P0 bug)=0 < pre-release feature=1 < P2 bug=2`.

The remaining legacy tier strings — `milestone`, `commercialization`, `major-initiative`,
`follow-up`, `non-audio`, `4a`, `4b` — previously ALL fell to `MERGED_PRIORITY_DEFAULT = 99`
(sorted dead-last). Assigning them coherent values is the whole point of the unification, but
the EXACT value each gets is a genuine PRODUCT decision: it reorders which real features
outrank which. Jacob explicitly asked to decide this mapping rather than have it guessed
(harden requirement 4).

**Why provisional-eligible, not a hard-park (`divergence: contained`):** the enum values live
in a single constant map (`_FEATURE_TIER_ENUM` in `depdag.py`). A wrong pick is a one-constant
redirect; `reposition_by_priority` re-sorts deterministically from the map, so no persistent
data is migrated and no architecture forks. `pre-release = 1`, backward compat for bare
ints / severity / null, the MIN-of-enums selection, and the tests are all locked and NOT
provisional — only the seven legacy-string integer VALUES below await ratification.

### 1. Legacy feature-tier string -> integer priority mapping

**Problem:** Pick the integer priority for each legacy tier string on the shared scale
(lower = higher priority), coherent with the operator-locked `pre-release = 1` and the
existing bare-int tiers (`0`, `1`, `5`, `6` observed in real queues, kept verbatim).

**Options:**

- **Recommended (implemented provisionally):**

  | Tier enum           | Int | Rationale                                                           |
  |---------------------|-----|---------------------------------------------------------------------|
  | `pre-release`       | 1   | LOCKED (== P1). Out of scope for this decision.                     |
  | `commercialization` | 2   | Revenue/commercial work — business-critical, just below pre-release.|
  | `milestone`         | 3   | A delivery milestone.                                               |
  | `major-initiative`  | 4   | Large strategic initiative, longer horizon.                        |
  | `4a`                | 4   | Legacy phase-4 sub-tier a → tier-4 band.                           |
  | `4b`                | 5   | Legacy phase-4 sub-tier b → after 4a.                             |
  | `follow-up`         | 6   | Deferred follow-up work — low.                                     |
  | `non-audio`         | 7   | Non-audio work — lowest of the named set (audio-first product).    |

- **Alternative A — commercialization below milestone:** swap so `milestone = 2`,
  `commercialization = 3` if delivery milestones should outrank commercial work.
- **Alternative B — collapse the phase-4 pair:** `4a = 4b = 4` if the a/b distinction is
  not meant to change priority (only labeling).
- **Alternative C — spread onto a sparser scale** (e.g. 10/20/30/…) so future tiers can be
  inserted between existing ones without renumbering.

**Recommendation:** Option 1 (the table above). It is the smallest coherent assignment that
subsumes every observed legacy string, keeps `pre-release` load-bearing, and slots cleanly
around the kept bare-int tiers. It is implemented and shipping provisionally; ratify to lock
it, or redirect to any alternative — the redirect is a one-map-constant change plus a
deterministic re-sort.

## Resolution

*Recorded on 2026-07-17. Provisionally auto-accepted on recommendation (`--park-provisional` divergence two-key). Ratify or redirect via the provisional-ratification affordance before completion.*

resolved_by: auto-provisional
decision_commit: c089142ab860ed32a2938e86b3aaf24316358834

### 1. 1. Legacy feature-tier string -> integer priority mapping

**Choice:** Option 1 (the table above). It is the smallest coherent assignment that
**Notes:** Provisionally accepted — divergence graded contained (producer) / contained (input-audit); pending operator ratification.
