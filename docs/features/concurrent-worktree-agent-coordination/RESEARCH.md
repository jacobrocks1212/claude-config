# Research — Concurrent multi-agent worktree coordination

> **Deep research SKIPPED by explicit operator decision (2026-07-18).**
> During the `/lazy-batch` run the operator directed "skip research" for this
> feature. Per the pipeline's anti-exemption rule, proceeding without a Gemini
> deep-research pass is a sanctioned *explicit operator decision* (a manual
> `RESEARCH.md` drop) — it is NOT an orchestrator inference or a
> dependency-has-research waiver.

## Basis for proceeding without external research

The feature baseline is already locked. The four product-authority design forks
were surfaced at `/spec` Phase 1 and resolved by the operator to their
recommended options (see `SPEC.md` → Locked Decisions):

1. **Lock granularity** → per-queue-item lock (reuse `lazy_coord.py` lease keying).
2. **Conflict discriminator** → git-mergeability + coupled-surface heuristic
   (ambiguous → HALT, the safe direction).
3. **Merge-back lifecycle** → reuse `lazy_coord.py` lane machinery (queue-order
   merge + demote-on-conflict + audit ledger; workstation-only v1).
4. **Cross-agent comm channel** → commit-message trailer convention
   (`Concurrent-Merge-Back:`), rides the fetch/rebase the other agent must do.

Each decision reuses existing, tested harness machinery (`lazy_coord.py`,
git-as-oracle, commit trailers), so implementation proceeds from the SPEC's
Locked Decisions and the cited reuse map rather than from new external research.

## Consequence

Downstream `/spec` Phase 3 (research integration) has no external research to
integrate and should proceed directly to `/plan-feature` on the locked baseline.
Any research-informed refinement is a documented vN follow-up, not a v1 blocker.
