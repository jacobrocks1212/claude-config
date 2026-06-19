# Two autonomous queue-walkers on the same branch have no arbitration → operator must adjudicate; push collisions force manual merges — Investigation Spec (stub)

> When two autonomous `/lazy-batch` queue-walkers run against the same branch (same git account), there is no deterministic arbitration between them. The orchestrator detected a concurrent walker committing and pushing to the same `main` and had to stop and ask the operator whether to continue. In a separate run, overlapping parallel edits to the same files surfaced as an 8-commit remote advance that required a careful hand-reconciliation. The "one writer per file" hazard manifests across sessions sharing one branch, with no automatic coordination.

**Status:** Investigating
**Severity:** P2
**Discovered:** 2026-06-19
**Placement:** docs/bugs/concurrent-same-branch-walkers-no-arbitration
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/CLAUDE.md`; `docs/features/multi-repo-concurrent-runs/` (addressed the cross-repo case, NOT the same-repo / same-branch case)

---

## Verified Symptoms
1. **[OBSERVED in logs]** The orchestrator detected a second autonomous session committing+pushing to the same branch and, lacking arbitration, had to ask the operator — session `5c33b6ba` @ `2026-06-11 15:49` (AskUserQuestion): "A second autonomous Claude session is actively committing + pushing to this same main branch (same git account, 3 claude.exe processes live) … Two autonomous queue-walkers on one branch risk colliding on feature selection and push ordering." (operator response: "Continue full run. The other session is finished.").
2. **[OBSERVED in logs]** Overlapping parallel edits from another session surfaced as an 8-commit remote advance requiring manual merge reconciliation — session `f2437fdb` @ `2026-06-08T20:34:34`: "The remote advanced with 8 commits from another session, and they overlap heavily with my files — including … the exact Step 1g region I just componentized." (manual two-session merge reconciliation, 20:35–20:43).

## Evidence Collected (from session logs)
- session `5c33b6ba` @ `2026-06-11 15:49` (AskUserQuestion): "A second autonomous Claude session is actively committing + pushing to this same main branch (same git account, 3 claude.exe processes live) … Two autonomous queue-walkers on one branch risk colliding on feature selection and push ordering." — orchestrator detects the concurrent walker but has no deterministic arbitration, so it escalates to the operator.
- session `f2437fdb` @ `2026-06-08T20:34:34`: "The remote advanced with 8 commits from another session, and they overlap heavily with my files — including … the exact Step 1g region I just componentized." — parallel edits to the same files collided on push and required a hand-reconciliation merge (20:35–20:43).

## Why this is friction
Two autonomous queue-walkers sharing one branch can collide on feature selection and push ordering, but the orchestrator has no deterministic arbitration mechanism — it must interrupt the run to ask the operator, and when edits overlap it falls to a manual multi-commit merge. The cross-repo concurrency case was addressed, but the same-repo / same-branch case leaves the "one writer per file" invariant unenforced across sessions.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- What deterministic arbitration (e.g., branch/feature claim, lease, or queue-item lock) could coordinate two walkers on one branch without operator intervention?
- Should two walkers on the same branch be detected and refused/serialized up front, rather than detected mid-run and escalated?
- How does this relate to what `multi-repo-concurrent-runs` already solved for the cross-repo case, and what is reusable for the same-branch case?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
