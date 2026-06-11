# Work Logging Plugin

A Claude Code plugin that turns daily engineering work into structured interview preparation material. (Formerly `interview-prep-plugin`.) Work is captured passively during normal development, then synthesized into features, correlated against a 154-topic knowledge bank, and rendered as an interlinked Obsidian vault for guided study.

## How It Works

```
Daily engineering ──► Work Log ──► Import ──► Synthesize ──► Correlate ──► Vault ──► Study
```

### 1. Capture: Work Logging

Every time you complete meaningful engineering work via skills like `/fix`, `/implement-phase`, or `/spec`, the plugin's `work_log_append` tool records a structured entry to `~/.interview-prep/work-log.jsonl`. Each entry captures the skill used, project, title, summary, files modified, technologies, patterns, and optional feature tags.

This happens automatically via skill hooks — no manual effort required.

### 2. Import: Planning Artifacts

The `import_artifacts` tool scans project directories for planning documents (SPEC.md, PHASES.md, RESEARCH.md) and imports them as features via content-hash deduplication. This backfills years of engineering work that predates the work log. Summaries are extracted automatically from the markdown content at import time — no separate enrichment step required.

### 3. Synthesize: Feature Clustering

The `synthesize_features` tool clusters orphaned (untagged) work log entries into feature-level summaries. Features group related work sessions into initiative-level narratives with technology stacks, patterns, and work log references.

### 4. Correlate: Topic Matching

Each feature is scored against 154 knowledge bank topics using a two-stage pipeline:

1. **Candidate retrieval** — semantic keyword overlap selects the top 10 candidate topics per feature
2. **LLM-as-a-judge** — headless Claude (haiku) evaluates each Feature x Topic pair on a strict 0-2 rubric. Only score-2 (strong match) correlations are kept.

The `correlate_headless.py` batch script runs this at scale across all features.

### 5. Generate: Obsidian Vault

The `generate_vault` tool produces an interlinked Obsidian vault with five collections:

| Collection | Content | Count |
|---|---|---|
| `01_Knowledge_Bank/{domain}/` | Topic references with Key Concepts, Interview Questions, Related Topics | 154 pages |
| `02_Work_History/` | Granular work log entries linked to parent features | 1 per log entry |
| `03_Features/` | Initiative-level summaries with technologies, patterns, story links | 1 per feature |
| `04_Interview_Stories/` | Domain-specific study artifacts with managed blocks and SRS flashcards | 1 per Feature x Topic correlation |
| `Meta/` | Coverage dashboard and gap analysis | 1 page |

The vault also includes a generated `CLAUDE.md` that teaches Claude Code how to navigate the vault during study sessions.

**Graph topology (DAG):** Work History → Features → Interview Stories → Knowledge Bank. No cross-links that would create a graph hairball.

**Domain-specific templates:**
- **System Design** — ADR format (Context, Baseline, Bottleneck, Decision, Operations)
- **Behavioral** — (I)STAR(T) format (Introduction, Situation, Task, Action, Result, Takeaway)
- **OOD** — Entity-Pattern-Extensibility format
- **Algorithms** — Problem-Approach-Complexity-Usage format

**Managed blocks:** All generated story content lives between `<!-- BEGIN MANAGED -->` delimiters. Your annotations outside the block survive vault regeneration.

### 6. Study: Interactive Sessions

Run `/interview-study <topic>` to start a guided study session. Claude loads the full topic context (KB entry, your correlated features, work log evidence) and enters a Socratic Q&A mode:

- Asks interview questions from the knowledge bank
- Coaches your answers using your real work as evidence
- Writes polished narratives into story managed blocks when you're satisfied
- Generates domain-appropriate SRS flashcards for spaced repetition

## Knowledge Bank

154 curated YAML entries across four domains:

| Domain | Entries | Examples |
|---|---|---|
| System Design | 40 | rate-limiting, caching, load-balancing, microservices |
| OOD | 40 | strategy-pattern, observer-pattern, dependency-injection |
| Algorithms | 39 | sliding-window, dynamic-programming, graph-traversal |
| Behavioral | 35 | ownership, conflict-resolution, technical-leadership |

Each entry includes a description, 3-5 Key Concepts (talking points), interview questions, related topics, tags, and difficulty level.

Stored at `~/.interview-prep/knowledge-bank/{domain}/*.yaml`.

## Installation

### As a Claude Code Plugin

```bash
# Symlink into the local-tools plugin directory
ln -s ~/source/repos/work-logging-plugin ~/.claude/plugins/local-tools/plugins/work-logging-plugin

# Enable in settings.json
# "work-logging-plugin@local-tools": true
```

### Dependencies

```bash
python -m venv .venv
.venv/Scripts/pip.exe install -e ".[dev]"
```

## MCP Tools

### Composite Tools (User-Facing)

| Tool | Purpose |
|---|---|
| `work_log_append` | Append a structured work log entry (called automatically by skills) |
| `import_artifacts` | Scan a directory for planning docs, import as features with content-hash dedup |
| `synthesize_features` | Cluster orphaned work log entries into features, run topic correlation |
| `generate_vault` | Generate the full Obsidian vault with all five collections |

### Atomic Tools (LLM-Callable)

| Tool | Purpose |
|---|---|
| `get_kb_index` | Compact index of all 154 knowledge bank topics |
| `get_kb_topic` | Full KB entry by slug and domain |
| `get_study_context` | Bundle KB entry + correlated features + work log for a topic |
| `read_work_log` | Query work log with filters (project, date range, feature) |
| `read_features` | Query features with filters (project, slug, has_correlations) |
| `evaluate_topic_match` | LLM judge on a single Feature x Topic pair (0-2 score) |
| `write_managed_block` | Write content into a managed block in a vault file |
| `calculate_hash` | SHA-256 hash of a file for import deduplication |

## Skills

| Skill | Purpose |
|---|---|
| `/interview-study` | Interactive study session — Socratic Q&A grounded in your real work |
| `/interview-generate` | Generate or regenerate the Obsidian vault |
| `/interview-import` | Import planning artifacts from project directories |
| `/interview-synthesize` | Synthesize features from orphaned work log entries |
| `/interview-check` | Quick topic relevance check against recent work |

## Batch Scripts

```bash
# Correlate features against KB topics via headless Claude
.venv/Scripts/python.exe scripts/correlate_headless.py [--dry-run] [--force]

# Re-enrich feature summaries (optional — summaries are extracted at import time)
.venv/Scripts/python.exe scripts/enrich_features.py [--dry-run] [--project NAME] [--force]
```

## Data Directory

```
~/.interview-prep/                   # Independent git repo
├── knowledge-bank/                  # 154 YAML entries across 4 domains
│   ├── system-design/   (40)
│   ├── ood/             (40)
│   ├── algorithms/      (39)
│   └── behavioral/      (35)
├── work-log.jsonl                   # Append-only skill work log
├── features.jsonl                   # Feature-level synthesized entries
├── import-index.jsonl               # Content hash registry for idempotent import
├── config.json                      # User preferences
└── vault/                           # Generated Obsidian vault (gitignored)
    ├── CLAUDE.md                    # Study session guide for Claude Code
    ├── 01_Knowledge_Bank/
    ├── 02_Work_History/
    ├── 03_Features/
    ├── 04_Interview_Stories/
    └── Meta/
```

## Development

```bash
# Quality gates
.venv/Scripts/python.exe -m mypy --strict servers/ scripts/
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest tests/ -v
```

147 tests covering persistence, knowledge bank, correlation, vault generation, all MCP tools, and study context aggregation.

## Architecture

```
work-logging-plugin/
├── .claude-plugin/plugin.json       # Plugin manifest
├── .mcp.json                        # MCP server transport config
├── servers/work_logging_mcp/
│   ├── server.py                    # FastMCP server — 12 tools (4 composite + 8 atomic)
│   ├── knowledge_bank.py            # YAML loader/query, Pydantic models
│   ├── persistence.py               # WorkLogWriter, FeaturesWriter, ImportIndexWriter, ConfigReader
│   ├── correlation.py               # Two-stage topic correlation engine
│   ├── headless_judge.py            # HeadlessJudge + BatchHeadlessJudge (claude CLI subprocess)
│   ├── vault_generator.py           # Obsidian vault generation engine
│   ├── managed_blocks.py            # Managed block read/write for vault files
│   └── extract.py                   # Shared markdown summary extraction
├── scripts/
│   ├── enrich_features.py           # Optional re-enrichment of feature summaries
│   └── correlate_headless.py        # Batch headless correlation
├── skills/
│   ├── interview-study/SKILL.md     # Interactive study sessions
│   ├── interview-generate/SKILL.md  # Vault generation
│   ├── interview-import/SKILL.md    # Artifact import
│   ├── interview-synthesize/SKILL.md # Feature synthesis
│   └── interview-check/SKILL.md     # Quick relevance check
└── tests/                           # 147 tests
```
