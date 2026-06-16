### claude-config Quality Gates

This repo has no compiled app, no Tauri, and no MCP server. "Validation" is the repo's own
Python **test + lint suite**. Run the gates relevant to what changed; run the **full** set
before flipping any plan part or feature to Complete.

#### Determining which gates to run

- **Skill / component changes** (`user/skills/**`, `user/skills/_components/**`, `repos/*/.claude/skills/**`):
  - `python user/scripts/project-skills.py` — re-expand all `!cat` component refs; must complete with no circular-include or missing-component errors.
  - `python user/scripts/lint-skills.py --check-projected --check-capabilities` — broken injections, embedded patterns, capability mismatches. Must pass clean.

- **Python script changes** (`user/scripts/**.py`):
  - `python -m pytest user/scripts/ -q` — full script suite (lazy-state, lazy-core, parity, lint-skills, hooks, surface-resolver, stale-binary, project-skills).

- **Lazy skill-family changes** (any `lazy*` skill, `lazy-state.py`, `bug-state.py`, `lazy_core.py`, `lazy_coord.py`, or either coupled pair):
  - `python user/scripts/lazy_parity_audit.py --report` — no unexplained drift; a new canonical behavioral unit must be mirrored to every derived twin or registered as a per-pair divergence.
  - plus the pytest gate above.

- **Plugin changes** (`user/plugins/local-tools/**`):
  - `python -m pytest user/plugins/local-tools/plugins/work-logging-plugin/tests/ -q`

- **Mixed / feature completion** → run the FULL set: `project-skills.py` + `lint-skills.py --check-projected --check-capabilities` + `python -m pytest user/scripts/ -q` + `lazy_parity_audit.py --report`.

#### MCP exemption (Step 9)

There is no MCP server in this repo, so the lazy Step 9 MCP-test gate is **N/A**. A feature
that reaches Step 9 is validated by the quality gates above; the operator grants a
`SKIP_MCP_TEST.md` (frontmatter `granted_by: operator`, `spec_class: untestable-via-mcp`,
`reason:` pointing at the passing quality gates) so the pipeline promotes it to `VALIDATED.md`.
Never let the pipeline grant its own skip (the provenance gate refuses pipeline-granted skips).

#### 100% pass required

Do not triage failures as "preexisting" — all gate failures must be fixed before proceeding to
the next batch or marking a part Complete.
