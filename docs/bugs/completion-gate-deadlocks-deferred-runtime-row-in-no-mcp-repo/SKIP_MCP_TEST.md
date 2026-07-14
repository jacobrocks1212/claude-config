---
kind: skip-mcp-test
feature_id: completion-gate-deadlocks-deferred-runtime-row-in-no-mcp-repo
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: per-phase quality gates ran during /execute-plan (tests + lint green on each plan part before commit); this repo has no Tauri app or dev server to validate against.
date: 2026-07-14
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
validated_commit: 9abe05eef79d1f9b493f992ee3adfe3f7413c859
---

# MCP Test Skip — structural (no app surface)

Granted inline by the state machine: this repo contains no `src-tauri/` and no `package.json`, so there is no MCP HTTP server / dev runtime to drive any MCP tool against. The `**MCP runtime:** not-required` PHASES declaration is re-verified structurally here, so no /mcp-test subagent is dispatched. `skip_waiver_refusal()` re-checks the same structural predicate before this waiver can validate — an app repo (src-tauri/ or package.json present) would be refused.
