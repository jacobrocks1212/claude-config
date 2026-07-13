---
kind: skip-mcp-test
feature_id: lazy-batch-skill-deflation
reason: 'pure claude-config harness mechanics — skill-prose diet, a stdlib Python ratchet lint + baseline JSON, and coupled-pair overlay regeneration; no Tauri app, no MCP-reachable surface (same untestable class as friction-kpi-registry and execute-plan-skill-diet)'
alternative_validation: 'pytest (test_skill_size_ratchet.py, test_generate_coupled_skills.py) + lint-skills.py + project-skills.py + lazy_parity_audit.py + doc-drift-lint.py, all run and green this session; skill-prose rule-preservation verified by manual side-by-side diff review per the execute-plan-skill-diet precedent'
date: 2026-07-12
skipped_by: operator
granted_by: operator
spec_class: standalone — no app integration (claude-config harness has no MCP-reachable surface)
---

# lazy-batch-skill-deflation — MCP Test Skip

This feature's entire deliverable set (skill-prose excisions, a lint script + baseline JSON, a
`HISTORY.md` sidecar, coupled-pair mirroring) is claude-config harness mechanics with no
Tauri/MCP-reachable runtime surface — the same class already granted for
`friction-kpi-registry` and `execute-plan-skill-diet`. This skip is written now (mid-feature,
per this session's operator-directed-interactive work) so the feature's eventual completion
path is unblocked at Step 9 without a separate MCP-classification round; it does NOT imply the
feature is otherwise complete — `PHASES.md` still has unchecked deliverables (the three
deferred Phase-1 hotspots + Phase 2), and `NEEDS_INPUT_PROVISIONAL.md` (D2) mechanically blocks
completion until ratified regardless of MCP status.
