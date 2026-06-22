# Lazy Queue — claude-config   (run active 🔒)

## Features (0)


## Bugs (1)

| # | item | state | sev |
|---|------|-------|------|
| 1 | [mcp-tooling-not-predetermined-at-planning](docs/bugs/mcp-tooling-not-predetermined-at-planning/SPEC.md) | Validate | P2 |
| | status: Validate · phase 4/4 · next: run mcp-test · The lazy feature pipeline never enumerates the MCP tool surface a feature's own `/mcp-test` scenario will call, so a missing tool is only discovered at Step 9 (pipeline end) — after full planning and implementation — forcing a corrective add-phase or `adhoc-mcp-*` spin-off and 3–6 wasted Step-9 cycles. | | |
