## `LAZY_BATCH_REVIEW_<date>.md` — `kind: lazy-batch-review`

Written by `/lazy-batch-retro` after auditing a completed `/lazy-batch` or `/lazy-batch-cloud` run. One file per feature touched in the audited run; an additional `LAZY_BATCH_REVIEW_<date>_overview.md` is written under `docs/features/_index/` when ≥ 2 features were touched.

Lives at: `docs/features/<area>/<feat>/LAZY_BATCH_REVIEW_<YYYY-MM-DD>.md` (optionally suffixed `_2`, `_3`, ... when multiple reviews land on the same day).

### Required frontmatter

```yaml
---
kind: lazy-batch-review
feature_id: <id>
batch_invocation: <"lazy-batch" | "lazy-batch-cloud">
branch: <ref>
session_id: <basename of parent jsonl, without .jsonl>
cycles_count: <int>
headline_grade: <"A" | "B" | "C" | "D" | "F">
force_capped: <true | false>
generated_at: <ISO 8601 UTC>
---
```

### Optional frontmatter

- `cycles_unverifiable: <int>` — count of cycles graded `unverifiable` due to missing transcripts.
- `force_cap_reasons: [<rule-id>, ...]` — when `force_capped: true`, lists the rule IDs (e.g. `R-EP-1`, `R-EP-2`) that triggered the cap.
- `worst_skill: <string>` — the downstream skill with the lowest compliance percentage (e.g. `"execute-plan"`).

### Body convention

Body sections in order (see `/lazy-batch-retro` Step 6 for the canonical template):

1. Executive Summary (≤ 5 bullets)
2. Cycle Ledger (table)
3. Compliance Matrix (rule + verdict + citation)
4. Subagent Prompt Diff (full prompt vs template)
5. Tool-Call Census (per-cycle counts)
6. Artifact Delta (files / sentinels changed)
7. Findings (ordered by severity)
8. Recommendations (operator + skill authors)
9. Skill versions footer (SHA table)

### Overview file — `kind: lazy-batch-review-overview`

```yaml
---
kind: lazy-batch-review-overview
batch_invocation: <"lazy-batch" | "lazy-batch-cloud">
branch: <ref>
session_id: <basename>
features: [<id1>, <id2>, ...]
generated_at: <ISO 8601 UTC>
---
```

Body links to each per-feature artifact and surfaces cross-cutting findings.

### Lifecycle

| Event | Action |
|-------|--------|
| Audit runs | `/lazy-batch-retro` writes the artifact + commits locally (no push) |
| Re-audit later | Same skill writes a new file with a date suffix; prior artifact remains for audit trail |
| Feature completes | `__mark_complete__` does NOT delete these files — they persist as a permanent audit record alongside `MCP_TEST_RESULTS.md` |

### Producer rules

- Citations MUST point at a specific source (jsonl line, transcript tool_use offset, commit SHA, sentinel path, or skill SKILL.md line).
- Do NOT trust agent summaries alone — the audit's value is independent verification.
- When transcript availability is degraded (`/tmp/claude-0/...` reclaimed), grade missing-transcript cycles `unverifiable` and record the count in `cycles_unverifiable` — never silently pass.
