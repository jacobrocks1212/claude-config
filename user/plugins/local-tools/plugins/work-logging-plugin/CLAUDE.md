# Work Logging Plugin

Work-log-grounded interview preparation. Passively captures engineering work, then provides on-demand tools for feature synthesis, topic correlation, and Obsidian vault generation. (Formerly `interview-prep-plugin`.)

## Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| `work_log_append` | **Active** | Called by skills via `_components/work-log.md`. Accepts optional `feature` tag. |
| `get_kb_index` | **Active** | Atomic tool: compact topic index |
| `get_kb_topic` | **Active** | Atomic tool: full KB entry by slug+domain |
| `read_work_log` | **Active** | Atomic tool: query work log with filters |
| `read_features` | **Active** | Atomic tool: query features with filters |
| `evaluate_topic_match` | **Active** | Atomic tool: LLM judge on Feature×Topic |
| `write_managed_block` | **Active** | Atomic tool: write to managed block in vault |
| `calculate_hash` | **Active** | Atomic tool: SHA-256 for import dedup |
| `import_artifacts` | **Active** | Composite: scan and import planning docs |
| `synthesize_features` | **Active** | Composite: cluster work log into features. Accepts `use_headless=True` for real LLM scoring. |
| `generate_vault` | **Active** | Composite: generate full Obsidian vault. Also generates `vault/CLAUDE.md` for study sessions. |
| `get_study_context` | **Active** | Atomic tool: bundles KB entry + correlated features + work log for a topic |
| `/interview-check` | Manual | Quick topic relevance check |
| `/interview-import` | Manual | Import planning artifacts |
| `/interview-synthesize` | Manual | Synthesize features from work log |
| `/interview-generate` | Manual | Generate Obsidian vault |
| `/interview-study` | Manual | Interactive study session for a topic, domain, or browsing |
| `SurfacingEvaluator` | **Active** | Headless haiku evaluation for passive surfacing |
| `NtfyNotifier` | **Active** | ntfy.sh notification client (stdlib urllib) |
| `SurfacingLogWriter` | **Active** | Diagnostic log for surfacing evaluations |
| PostToolUse hook | **Active** | Auto-fires `evaluate_and_notify.py` after work log append |
| `~/.local/bin/study` | **Active** | Wrapper script for surfacing-triggered study sessions |

## Setup

### Registration
The plugin is registered as a local-tools plugin via symlink:
- **Source:** `claude-config/user/plugins/local-tools/plugins/work-logging-plugin/` (tracked in the `claude-config` repo, alongside `cognito-pr-review`)
- **Symlink:** `~/.claude/plugins/local-tools/plugins/work-logging-plugin` → the claude-config source above (created by `claude-config/setup.ps1` from `manifest.psd1`)
- **Marketplace config:** `~/.claude/plugins/local-tools/.claude-plugin/marketplace.json`
- **Enabled in:** `~/.claude/settings.json` as `"work-logging-plugin@local-tools": true`

### MCP Tool Names

Plugin MCP tools are namespaced. Use these full names in ToolSearch or direct invocation:

| Short name | Full MCP tool name |
|---|---|
| `work_log_append` | `mcp__plugin_work-logging-plugin_work-logging__work_log_append` |
| `get_kb_index` | `mcp__plugin_work-logging-plugin_work-logging__get_kb_index` |
| `get_kb_topic` | `mcp__plugin_work-logging-plugin_work-logging__get_kb_topic` |
| `read_work_log` | `mcp__plugin_work-logging-plugin_work-logging__read_work_log` |
| `read_features` | `mcp__plugin_work-logging-plugin_work-logging__read_features` |
| `evaluate_topic_match` | `mcp__plugin_work-logging-plugin_work-logging__evaluate_topic_match` |
| `write_managed_block` | `mcp__plugin_work-logging-plugin_work-logging__write_managed_block` |
| `calculate_hash` | `mcp__plugin_work-logging-plugin_work-logging__calculate_hash` |
| `import_artifacts` | `mcp__plugin_work-logging-plugin_work-logging__import_artifacts` |
| `synthesize_features` | `mcp__plugin_work-logging-plugin_work-logging__synthesize_features` |
| `generate_vault` | `mcp__plugin_work-logging-plugin_work-logging__generate_vault` |
| `get_study_context` | `mcp__plugin_work-logging-plugin_work-logging__get_study_context` |

### Components
```
work-logging-plugin/
├── .claude-plugin/
│   ├── plugin.json                  # Plugin manifest (skills + hooks)
│   └── hooks.json                   # PostToolUse hook registration
├── .mcp.json                        # MCP server transport (flat format, uv run python -m servers.work_logging_mcp.server)
├── hooks/
│   └── evaluate-surfacing.sh        # PostToolUse hook: spawns background evaluation
├── servers/work_logging_mcp/
│   ├── server.py                    # FastMCP server with 12 tools (4 composite + 8 atomic)
│   ├── knowledge_bank.py            # YAML loader/query for ~/.interview-prep/knowledge-bank/
│   ├── headless_judge.py            # HeadlessJudge + BatchHeadlessJudge (claude CLI subprocess)
│   ├── surfacing.py                 # SurfacingEvaluator + SurfacingLogWriter (passive surfacing)
│   ├── ntfy.py                      # NtfyNotifier + load_ntfy_config (ntfy.sh client)
│   └── persistence.py               # WorkLogWriter + ConfigReader
├── scripts/
│   ├── enrich_features.py           # Enrich thin feature summaries from source markdown
│   ├── correlate_headless.py        # Bulk correlate features via headless Claude haiku
│   └── evaluate_and_notify.py       # Detached CLI: evaluate surfacing + send ntfy notification
├── skills/interview-check/SKILL.md  # Manual /interview-check command
├── skills/interview-study/SKILL.md  # Interactive study session skill
└── tests/                           # Tests (server, tools, persistence, knowledge bank, surfacing, ntfy)
```

### Data directory: `~/.interview-prep/`
```
~/.interview-prep/                       # Independent git repo (auto-commit on writes)
├── knowledge-bank/                  # 154 YAML entries across 4 domains
│   ├── system-design/
│   ├── behavioral/
│   ├── algorithms/
│   └── ood/
├── work-log.jsonl                   # Skill work-log (authoritative record, accepts optional feature tag)
├── surfacing-log.jsonl              # Diagnostic log for surfacing evaluations (no auto-commit)
├── surfacing-errors.log             # Error log for background evaluation failures
└── config.json                      # User preferences (includes optional ntfy config)
```

## Batch Scripts

### `scripts/enrich_features.py`
Enriches thin feature summaries (≤100 chars) by extracting text from source markdown files. Run this **before** correlating.

```bash
.venv/Scripts/python.exe scripts/enrich_features.py --dry-run          # Preview extractions
.venv/Scripts/python.exe scripts/enrich_features.py                    # Enrich and upsert
.venv/Scripts/python.exe scripts/enrich_features.py --project algobooth --force  # Re-enrich all for a project
```

### `scripts/correlate_headless.py`
Bulk-correlates features against KB topics using headless Claude (haiku). Run **after** enrichment.

```bash
.venv/Scripts/python.exe scripts/correlate_headless.py --dry-run       # Preview correlations
.venv/Scripts/python.exe scripts/correlate_headless.py                 # Correlate and upsert
.venv/Scripts/python.exe scripts/correlate_headless.py --force         # Re-correlate all
```

**Execution order:** `enrich_features.py` → `correlate_headless.py`

## Manual Check

Use `/interview-check` in any Claude Code session to force a relevance check against the knowledge bank.

## Quality Gates

```bash
.venv/Scripts/python.exe -m mypy --strict servers/ scripts/
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest tests/ -v
```
