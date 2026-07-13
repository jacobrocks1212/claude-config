---
kind: skip-mcp-test
feature_id: anti-overfit-design-gate
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous. The gate is a committed JSON manifest + a stdlib checker + a _components/ protocol + a lazy_core completion seam.
alternative_validation: pytest on test_harness_gate.py (22 fixtures incl. the two named historical regression instances), the existing gate suites, and project-skills.py + lint-skills.py after the skill/component edits; kpi-scorecard.py --lint --spec for the KPI declaration.
date: 2026-07-12
skipped_by: pipeline
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in repo)
---

# MCP Test Skip — structural (no app surface)

This repo contains no `src-tauri/` and no `package.json`, so there is no MCP HTTP server / dev
runtime to drive any MCP tool against. The `**MCP runtime:** not-required` PHASES declaration is
re-verified structurally here. Validation is `pytest` + the projection/lint gates.

**Note:** this feature is provisional-blocked (`NEEDS_INPUT_PROVISIONAL.md`, unratified) — it will
NOT reach the MCP gate or completion regardless of this waiver until the operator ratifies the four
product decisions. This sentinel documents the validation class; it is inert while completion is
mechanically refused.
