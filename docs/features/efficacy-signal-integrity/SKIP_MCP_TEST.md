---
kind: skip-mcp-test
feature_id: efficacy-signal-integrity
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: pytest on test_efficacy_eval.py (50 tests) + test_kpi_scorecard.py (109 tests), kpi-scorecard.py --lint (registry OK), and a byte-stable double-render check — all green this session.
date: 2026-07-12
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
validated_commit: a547c716d1dfae64cf5f344cb7cabfce13f4bac5
---

# MCP Test Skip — structural (no app surface)

Granted inline by the state machine: this repo contains no `src-tauri/` and no `package.json`,
so there is no MCP HTTP server / dev runtime to drive any MCP tool against. The
`**MCP runtime:** not-required` PHASES declaration is re-verified structurally here, so no
`/mcp-test` subagent is dispatched. `skip_waiver_refusal()` re-checks the same structural
predicate before this waiver can validate — an app repo (`src-tauri/` or `package.json` present)
would be refused.
