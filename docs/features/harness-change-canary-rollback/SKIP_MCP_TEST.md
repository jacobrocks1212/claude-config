---
kind: skip-mcp-test
feature_id: harness-change-canary-rollback
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — the entire deliverable is stdlib Python (lazy_core.py canary registration, efficacy-eval.py --canary watcher, kpi-scorecard.py selector) plus orchestrator-prose flush wiring; nothing to boot, nothing to probe.
alternative_validation: per-phase quality gates ran during /execute-plan across all 4 phases (test_lazy_core.py -k canary, test_efficacy_eval.py -k canary, test_kpi_scorecard.py, lazy_parity_audit.py, lint-skills.py --check-projected --check-capabilities all green on each phase's commit); this workstation session re-ran the full canary fixture suites plus kpi-scorecard.py --lint (repo-wide and --spec) and confirmed all green before completion.
date: 2026-07-12
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
validated_commit: 2f1e3eda
---

# MCP Test Skip — structural (no app surface)

The PHASES.md `**MCP runtime:** not-required` declaration is re-verified structurally here: this
repo contains no `src-tauri/` and no `package.json`, so there is no MCP HTTP server / dev runtime
to drive any MCP tool against. `DEFERRED_NON_CLOUD.md` (written 2026-07-04 by the cloud
`/lazy-cloud` run) deferred exactly this step to a workstation `/lazy` pass, which structurally
grants the same no-MCP-surface waiver `park-provisional-acceptance` and `friction-kpi-registry`
were granted — no `src-tauri/` or `package.json` appeared in this repo between then and now, so
`skip_waiver_refusal()`'s re-check predicate still holds.
