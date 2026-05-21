## Sentinel File Frontmatter Schema

All sentinel files the `/lazy` and `/lazy-cloud` state machine reads or writes carry a YAML frontmatter block as their canonical contract. The markdown body that follows the frontmatter remains human-readable documentation; **only the frontmatter is parsed by consumers**. Tools (`lazy-state.py`, future lints, batch orchestrators) read the frontmatter strictly and ignore the body.

### Parsing protocol

1. Read the file as UTF-8.
2. First non-blank line MUST be exactly `---`. Otherwise the file is not a structured sentinel — treat as legacy/freeform and skip.
3. Read lines until the next line that is exactly `---` (the closing fence). Everything between the fences is YAML.
4. Parse the YAML with a standard library parser (e.g. `yaml.safe_load`). If parsing fails, surface the file path and the parser's line/column rather than silently treating the file as missing.
5. Anything after the closing `---` is the markdown body. Consumers SHOULD NOT parse the body. Producers SHOULD keep the body informative for humans reading the file directly.

The shared sentinel writer in lazy-state.py — and the skill prose that writes these files inline — both follow this contract. If you read sentinel files ad-hoc from skill prose, prefer dispatching to `python3 ~/.claude/scripts/lazy-state.py` instead of re-implementing the parse.

### Required `kind` field

Every sentinel MUST carry a `kind` field whose value identifies the sentinel type. Consumers dispatch on `kind`. Unknown kinds are treated as parse errors.

### Schemas

#### `BLOCKED.md` — `kind: blocked`

Required:

```yaml
---
kind: blocked
feature_id: <id>
phase: <human description of the phase or step that hit the blocker>
blocked_at: <ISO 8601 timestamp>
retry_count: <int>
---
```

Optional:
- `blocker_kind: <one-line classifier>` — e.g., `mcp-validation`, `upstream-realign`, `quality-gate`, `cloud-limitation`, `execute-plan`.
- `recovery_suggestion: <one-line>` — short hint surfaced in the dispatch summary.

The markdown body that follows MUST keep the existing `## Details` / `## What was tried` / `## Recovery Suggestion` sections so a human reading the file directly still sees the full context. Frontmatter values may duplicate the body content; that's fine — frontmatter is the parser's source of truth, body is the human's.

#### `DEFERRED_NON_CLOUD.md` — `kind: deferred-non-cloud`

Required:

```yaml
---
kind: deferred-non-cloud
feature_id: <id>
deferred_step: <step number, e.g. 8>
reason: <one-line>
deferred_by: lazy-cloud
date: <YYYY-MM-DD>
---
```

Optional:
- `cloud_session_id: <id-or-n/a>`
- `testability_assessment: <"clearly-testable" | "ambiguous">`

Body keeps the existing detailed `## State at deferral` / `## How to resume` sections.

#### `VALIDATED.md` — `kind: validated`

Required:

```yaml
---
kind: validated
feature_id: <id>
date: <YYYY-MM-DD>
mcp_scenarios: [<scenario-name>, ...]
result: all-passing
---
```

Body keeps the human-readable summary of which scenarios ran.

#### `RETRO_DONE.md` — `kind: retro-done`

Required:

```yaml
---
kind: retro-done
feature_id: <id>
date: <YYYY-MM-DD>
rounds: <int>
retro_plans: [<filename>, ...]
mcp_validation_status: complete  # one of: complete | deferred-to-workstation
---
```

Body keeps the per-round summary so humans can scan retro history.

#### `SKIP_MCP_TEST.md` — `kind: skip-mcp-test`

Required:

```yaml
---
kind: skip-mcp-test
feature_id: <id>
reason: <one-line>
alternative_validation: <one-line>
date: <YYYY-MM-DD>
---
```

Optional:
- `skipped_by: <"lazy" | "lazy-cloud">` — who wrote the skip.

#### `MCP_TEST_RESULTS.md` — `kind: mcp-test-results`

Required:

```yaml
---
kind: mcp-test-results
feature_id: <id>
date: <YYYY-MM-DD>
scenarios: [<scenario-name>, ...]
result: all-passing  # one of: all-passing | partial
pass_count: <int>
total_count: <int>
---
```

Body keeps the per-scenario pass/fail breakdown.

#### `NEEDS_RESEARCH.md` — `kind: needs-research`  *(new)*

Written by `/lazy-batch` or `/lazy-batch-cloud` when a feature is missing `RESEARCH.md` and the orchestrator has just ensured a `RESEARCH_PROMPT.md` exists. Halts the autonomous tail and surfaces the prompt path so a human can run Gemini and drop the results in place.

Required:

```yaml
---
kind: needs-research
feature_id: <id>
research_prompt_path: <relative path to RESEARCH_PROMPT.md>
written_by: lazy-batch  # one of: lazy-batch | lazy-batch-cloud
date: <YYYY-MM-DD>
---
```

Body should explain how to resume: run Gemini deep research against the prompt file, drop the output as `RESEARCH.md` next to the prompt, then re-run `/lazy-batch` (or `/lazy-batch-cloud`).

#### `NEEDS_INPUT.md` — `kind: needs-input`  *(new)*

Written by any batch-mode skill (`--batch`) when a decision is genuinely ambiguous and no recommended option resolves cleanly. Halts the autonomous tail and surfaces the decisions a human must make.

Required:

```yaml
---
kind: needs-input
feature_id: <id>
written_by: <skill name>  # e.g., spec, spec-phases, add-phase, retro, execute-plan
decisions:
  - <one-line decision description>
  - <one-line decision description>
date: <YYYY-MM-DD>
---
```

Optional:
- `next_skill: <skill name>` — what to re-run after the human resolves the decision (defaults to the writer).
- `partial_artifacts: [<path>, ...]` — paths to any half-finished artifacts the human should review or discard.

Body keeps the full decision context, options considered, and any chat-visible tradeoff notes the writer would have surfaced interactively.

### Lifecycle summary

| File | Written when | Cleared when |
|------|-------------|--------------|
| BLOCKED.md | A skill hits an unrecoverable obstacle | Human resolves (delete or via /add-phase / /lazy skip) |
| DEFERRED_NON_CLOUD.md | /lazy-cloud cannot run a step in cloud | /lazy Step 10 (feature completion) |
| VALIDATED.md | /lazy after 100% MCP pass | /lazy Step 10 |
| RETRO_DONE.md | /lazy after retro plan executes | /lazy Step 10 |
| SKIP_MCP_TEST.md | /lazy assessment: not testable | Persists permanently |
| MCP_TEST_RESULTS.md | /lazy after mcp-test runs | Persists permanently (audit) |
| NEEDS_RESEARCH.md | /lazy-batch when RESEARCH.md absent | Human runs research, drops RESEARCH.md, deletes this file |
| NEEDS_INPUT.md | A `--batch` skill hits an ambiguous decision | Human resolves the decisions, deletes the file, re-runs |

### Producer rules

- A skill that writes a sentinel MUST emit valid YAML frontmatter per the schema above, then a blank line, then the existing human-readable body content. Do not omit the body — humans read these files directly when /lazy-batch halts.
- All keys are lowercase with underscores. Date format is `YYYY-MM-DD` for `date` fields and ISO 8601 for `blocked_at` (which carries a time component).
- Lists use YAML inline form (`[a, b]`) or block form, parser handles both.
- Do not invent new top-level keys without updating this schema. Tools may reject unknown keys in the future.

### Consumer rules

- Prefer `python3 ~/.claude/scripts/lazy-state.py` to ad-hoc parsing — it implements this schema once and emits structured state JSON.
- If you must parse from skill prose, follow the parsing protocol above and dispatch on `kind`. Never rely on the markdown body.
- Treat a sentinel with a present file but missing or malformed frontmatter as a parse error, not a missing sentinel. Surface the path so the human can fix it.
