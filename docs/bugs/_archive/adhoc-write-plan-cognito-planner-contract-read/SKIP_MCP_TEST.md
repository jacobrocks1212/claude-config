---
kind: skip-mcp-test
feature_id: adhoc-write-plan-cognito-planner-contract-read
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: project-skills.py projection + lint-skills.py clean (skill-prose-only change to write-plan-cognito SKILL.md).
date: 2026-07-09
skipped_by: operator-directed-completion
granted_by: structural (no MCP surface in repo)
spec_class: standalone — skill-prose-only policy codification, no app integration
validated_commit: 7108b2e8db9d0639c82e09029eec1040c3518ab9
---

# MCP Test Skip — structural (no app surface)

Operator-directed completion of a skill-prose policy codification in claude-config. No MCP
surface exists in this repo; validation ran via skill projection + lint (see SPEC.md).
