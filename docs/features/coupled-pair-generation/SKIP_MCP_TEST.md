---
kind: skip-mcp-test
feature_id: coupled-pair-generation
reason: repo has no MCP-reachable surface (no src-tauri/, no package.json) — nothing to boot, nothing to probe; the MCP gate is structurally vacuous.
alternative_validation: pytest test_generate_coupled_skills.py (34) green; generate-coupled-skills.py --check byte-identical for all 5 pairs; --write leaves derived files byte-identical (git-clean); lazy_parity_audit.py + doc-drift-lint.py + lint-skills.py + project-skills.py all green; test_lazy_parity.py + test_doc_drift_lint.py (81) green.
date: 2026-07-12
skipped_by: subagent-orchestration
granted_by: pipeline-structural
spec_class: standalone — no app integration (no Tauri/MCP surface in claude-config)
validated_commit: 7a503f808eb9c0c7ef135078e03e9064b0a7ef9c
---

# MCP Test Skip — structural (no app surface)

claude-config contains no `src-tauri/` and no `package.json`, so there is no MCP HTTP server /
dev runtime to drive any MCP tool against. This is the `standalone — no app integration`
untestable class. Validation is the deterministic gate suite listed in `alternative_validation`,
run at this commit.

NOTE: this feature landed with a `NEEDS_INPUT_PROVISIONAL.md` recorded — it is fully implemented
(Phases 1–3) and gate-green, but NOT marked Complete. The SKIP_MCP_TEST waiver documents the
structural MCP-vacuity for whenever the provisional decision resolves and completion proceeds.
