---
kind: skip-mcp-test
feature_id: adhoc-containment-denies-mandated-explore-fanout
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: hook test suite (test_hooks.py 130/131 — sole failure environmental WSL pipe test), lazy_parity_audit exit 0, doc-drift-lint 0 findings, project-skills + lint-skills clean, py_compile clean, live nested-Explore dispatch probe.
date: 2026-07-09
skipped_by: operator-directed-completion
granted_by: structural (no MCP surface in repo)
spec_class: standalone — docs/hook/prose-only harness fix, no app integration
validated_commit: 7108b2e8db9d0639c82e09029eec1040c3518ab9
---

# MCP Test Skip — structural (no app surface)

Operator-directed completion of a hook + doc-surface fix in claude-config. The repo contains no
`src-tauri/` and no `package.json`, so there is no MCP HTTP server or dev runtime to drive any
MCP tool against. Validation ran via the hook test suite, the parity audit, the doc-drift
linter, skill projection/lint, and a live nested-dispatch probe (see SPEC.md Verification).
