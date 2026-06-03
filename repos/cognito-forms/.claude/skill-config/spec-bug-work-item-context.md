### Subagent F: ADO Work Item Context

**`/spec-bug` in this repo accepts an ADO work-item id** (a bare number, `#56565`, `AB#56565`, or an ADO work-item URL) in place of — or alongside — a prose description. When one is present, launch this subagent to gather context on the bug before any investigation begins.

**Prompt:** Use the Azure DevOps MCP to fetch the referenced work item and its related items, grounding the investigation in what was actually reported.

1. Resolve the work-item id from the user's description (bare number / `#id` / `AB#id` / ADO URL)
2. Via the Azure DevOps MCP work-item tools, fetch the bug: title, repro steps, system info, state, severity, area/iteration path, tags, and the full discussion/comment history
3. Follow the work item's relations (parent, related, duplicate-of, and linked PRs/commits) and fetch each related item's title + state for surrounding context
4. If the ADO MCP is unavailable, disconnected, or failing, fall back to `az boards work-item show --id <id>` (and `az boards work-item relation ...`) per `AGENTS.md`, telling the user you are using the CLI fallback for this session
5. Extract: reported symptoms, expected vs actual behavior, repro steps, prior triage/discussion, and the canonical `<WI_ID>` that will name the `docs/bugs/<WI_ID>-<slug>/` directory (see `docs/bugs/CLAUDE.md`)

Report format: a structured work-item summary (id, title, state, severity, reported symptoms, repro) plus a short list of related items with relevance, and the resolved `<WI_ID>` for directory naming.
