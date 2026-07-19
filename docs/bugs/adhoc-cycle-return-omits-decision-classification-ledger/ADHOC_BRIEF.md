---
kind: adhoc-brief
bug_id: adhoc-cycle-return-omits-decision-classification-ledger
enqueued_by: lazy-adhoc
date: 2026-07-19
---

# Ad-hoc bug: Cycle-subagent return summaries omit the mandatory Decision-Classification Ledger

Across this run the /lazy-batch input-audit (Step 1d.5) flagged SEVEN times that the dispatched cycle subagent's return summary carried only a one-line conclusion string and NO Decision-Classification Ledger, violating the spec/spec-bug/plan-feature --batch return contract (sentinel-frontmatter.md Producer duties). Each time the audit fell back to the weaker diff-only audit (algorithm 3c) instead of cross-checking the cycle's own classification. Observed on spec-bug, plan-feature, and plan-bug cycles alike, so the gap is in the shared cycle-return contract (cycle-base-prompt.md / the skill return templates), not one skill. Root cause + fix site to be traced by /spec-bug: either the cycle prompt does not make the ledger mandatory/inline enough, or the subagents systematically drop it under batch. Fix should make the ledger a hard, checkable return element (or have the audit degrade-detect and re-request it) so product-decision classification is not silently lost.
