---
kind: adhoc-brief
bug_id: decision-2-6-uncovered-row-reroute-to-mcp-test
enqueued_by: lazy-adhoc
date: 2026-07-18
---

# Ad-hoc bug: Implement decisions 2+6: Step-10 re-route to mcp-test on uncovered non-exempt verification rows (shared predicate)

RESOLVED 2026-07-18 (turn-routing-enforcement NEEDS_INPUT decisions 2+6): before routing Step 10 to __mark_complete__, an In-progress phases state with unchecked, non-exempt, non-host-deferred runtime-verification rows that recorded evidence does not cover re-routes to mcp-test instead (conservative predicate accepted: one redundant mcp-test pass on a complete-but-unticked matrix is tolerable). ONE shared predicate serves both the matrix-incomplete VALIDATED oscillation (decision 2, archived coherence loop evidence) and the newly-discovered-coverage stranding (decision 6, managed-llm-credits CTA/toggle rows). Must terminate: never re-trigger on already-exempt or host-deferred rows (interacts with decision 5's per-row requires-host marker and the observation_gap path). Full resolution text: docs/specs/turn-routing-enforcement/NEEDS_INPUT.md decisions 2 and 6.
