---
kind: gate-verdict
feature_id: merged-head-oracle-blind-to-operator-deferred-cross-pipeline-feature
written_by: harden-harness
date: 2026-07-19
decision_commit: a1f98e4d
divergence: isolated
---

# Anti-overfit / gate-weakening design-gate verdict — Round 102

`harness-gate.py --repo-root . --range origin/main..HEAD --json` → `in_scope: true`,
`verdict_required: true`, `gate_weakening_hit: false`. `scope_hit`: `dispatch.py`, `depdag.py`,
`docmodel.py`.

## overfit — flag (FALSE POSITIVE)

Evidence: `dispatch.py: alternation literal appended: _op_defer_dir: dict[str, "Path | None"] = {}`.

The checker matched the `|` inside the TYPE ANNOTATION `dict[str, "Path | None"]` as if it were a
literal appended to a matcher alternation. It is not — it is a variable's type hint. The fix adds
**no** literal to any regex / keyword-set / allow-list / matcher. It adds a structural file-predicate
(`spec_dir_operator_deferred`, present since Round 57) applied to every merged-head candidate.

**Adversarial check — "construct the nearest recurrence this rule does NOT catch":** the exclusion
keys on the presence of a `DEFERRED.md` FILE in a candidate's spec dir, NOT on the incident id
(`native-android-pipeline-steering`), the pipeline (feature vs bug), or any phrase. A DIFFERENT
operator-deferred feature — any slug, any tier — is caught identically, because the predicate reads
the file, not a literal. There is no near recurrence this fix fails to catch. Overfit flag dismissed.

## gate_weakening — pass

No gate removed, threshold softened, denial deleted, or `def test_*` removed. The change STRENGTHENS
merged-head correctness (adds an exclusion) and ADDS a regression test. No operator sign-off required.

## complexity — retires: net-new

`retires: net-new` — the fix RESTORES the Round-57 (`c5a3b385`) `spec_dir_operator_deferred`
merged-head exclusion that the `merged-head-actionability-oracle` refactor dropped for the
cross-pipeline-feature case. No rule/surface is deleted; it is a supplement to the oracle's scoped
`is_dispatchable` walk, covering the one signal that walk is structurally blind to (operator-defer
on a candidate whose owning pipeline's `compute_state` does not model it). Justification: without it
the merged-head-diverged withhold deadlocks the run behind an operator-excluded feature.

## tautology — pass

Verdict: SHIP. `divergence: isolated` — a single-function file-predicate supplement at one oracle
landing site; no architecture / persistent-data / workflow fork. `/harden-harness` is never blocked;
recorded for the completion-gate ship seam (seam-deferred).
