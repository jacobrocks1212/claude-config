# A non-P0 bug outranks a P1 feature at an age-escalated priority tie

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-17 (observed live during a `/lazy-batch` run on AlgoBooth)
**Related:** `docs/bugs/feature-tier-strings-fall-to-merged-priority-default` (Round 63 — unified
feature-tier enums onto the bug-severity scale, establishing the `pre-release == 1 == P1`
load-bearing ordering); `docs/features/unified-pipeline-orchestrator/` (the merged-view ordering
contract); `bug-queue-aging-backpressure` (the age-escalation this bug interacts with).

## Trigger

Operator directive (Jacob, 2026-07-17, verbatim): **"I only want P0 bugs to sort ahead of P1
features."** Observed live: `lazy-state.py --next-merged` returned the P2 bug
`protocol-generic-claims-drift` as the merged head OVER the P1 (pre-release) feature `hydra-overlay`.

## Reconstructed route (divergence point)

`lazy_core.merged_worklist` (`depdag.py`) sorts on `(merged_priority, _MERGED_TYPE_ORDER[type], seq)`.
The tie-break `_MERGED_TYPE_ORDER = {"bug": 0, "feature": 1}` makes a **bug win** at an equal
effective rank. Combined with bug age-escalation this produces the violation:

- Bug `protocol-generic-claims-drift`: severity **P2** (`_MERGED_SEVERITY_RANK` = 2),
  `**Discovered:** 2026-07-09` (8 days before 2026-07-17).
- `age_escalated_rank(2, "2026-07-09", today=2026-07-17)` → **1**: one escalation notch per
  `_AGE_ESCALATION_QUANTUM_DAYS = 7`, capped at `_AGE_ESCALATION_FLOOR_RANK = 1` (P1-equivalent).
- Feature `hydra-overlay`: tier `["non-audio", "pre-release"]` → `merged_priority` = **1** (MIN of
  the resolved enum values; `pre-release` = 1).
- At the rank-1 tie, `_MERGED_TYPE_ORDER["bug"] (0) < _MERGED_TYPE_ORDER["feature"] (1)` → **bug
  wins**.

**Divergence point:** the equal-rank tie-break in `merged_worklist` / `next_merged` — an aged
non-P0 bug reaches P1-equivalent rank and then beats a genuine P1 feature, violating the operator's
rule.

## Root cause

**`root_cause_class: missing-contract`** — the tie-break policy (`bug` before `feature`) was
specified before the aging feature existed and before the operator's "only P0 ahead of P1" rule was
stated. The age-escalation floor is already `_AGE_ESCALATION_FLOOR_RANK = 1` ("a genuine P0 always
outranks a merely-aged bug" — no aged bug ever reaches rank 0). So the ONLY way a non-P0 bug can
precede a P1 feature is the equal-rank tie-break resolving in the bug's favor.

## Fix scope

Flip `_MERGED_TYPE_ORDER` to `{"feature": 0, "bug": 1}` (**feature wins ties**). Because the
age-escalation floor is rank 1, this yields EXACTLY the operator's rule:

- P0 bug (rank 0) vs P1 feature (rank 1): `0 < 1` → **bug wins** (P0 ahead of P1 — intended).
- P1 bug / aged-P2 bug (rank 1) vs P1 feature (rank 1): tie → **feature wins** (only P0 ahead of P1).
- Any other equal-rank bug/feature pair (e.g. P2 bug vs a rank-2 `commercialization` feature): the
  feature wins the tie. This is the coherent generalization ("at an equal effective rank the feature
  is worked first"); it is the least-collateral faithful implementation of the directive (a narrower
  P1-only guard would be an over-fit literal, and lowering the age floor alone would NOT fix a
  genuine P1 *bug* tying a P1 feature).

The scalar `merged_priority` VALUES are unchanged (P0=0, pre-release=1, P2=2), so the Round-63
"load-bearing ordering" statement `merged_priority(P0 bug)=0 < pre-release feature=1 < P2 bug=2`
still holds for the SCALAR; only the EQUAL-RANK tie-break flips. The load-bearing comment block and
the `merged_worklist` seed-order comment are reconciled to state the new invariant: **at an equal
effective rank the FEATURE wins; only a strictly-lower-rank bug (a genuine P0) precedes a P1
feature.**

## Coupled-pair / parity note

`_MERGED_TYPE_ORDER` is the single ordering source consumed by BOTH the workstation driver
(`/lazy-batch`) and its cloud mirror (`/lazy-batch-cloud`), plus `/lazy-bug-batch`. No SKILL prose
re-implements the ordering (the drivers only CONSUME the merged head), so the trio stays consistent
by construction; the `lazy_parity_audit.py` "bugs break ties" comment is updated to the new
invariant. This is operator-directed (the design fork is resolved by the verbatim directive), so it
ships as a mechanical fix — no provisional sentinel.
