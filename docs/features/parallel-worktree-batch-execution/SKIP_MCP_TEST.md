---
kind: skip-mcp-test
feature_id: parallel-worktree-batch-execution
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: lazy_coord.py --test (21/21 fixtures, incl. all parallel-lane fixtures — claim-shardable-conservative, lanes-ledger-lifecycle, merge-order-deterministic, budget-arithmetic, worktree-pool-generalization, zombie-lane-fenced, queue-order-merge-determinism, conflict-demotes-preserves-lane-branch, park-isolates-siblings, coordinator-death-recovery); lazy-state.py --test / bug-state.py --test smoke baselines; lazy_parity_audit.py --repo-root . (exit 0); lint-skills.py --check-projected --check-capabilities (clean); project-skills.py (clean, 88 skills / 100 components across all 3 repo projections).
date: 2026-07-12
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
validated_commit: 9c7337c5876c8ef280a0dec03b5aa4fb4f1f09cf
---

# MCP Test Skip — structural (no app surface)

Granted inline by the state machine's structural predicate: this repo contains no `src-tauri/`
and no `package.json`, so there is no MCP HTTP server / dev runtime to drive any MCP tool
against. The `**MCP runtime:** not-required` PHASES declaration is re-verified structurally here
— this feature is pure claude-config harness mechanics (a Python concurrency plane + state-script
seams + skill prose + docs), so no `/mcp-test` subagent is dispatched. `skip_waiver_refusal()`
re-checks the same structural predicate before this waiver can validate — an app repo (`src-tauri/`
or `package.json` present) would be refused.
