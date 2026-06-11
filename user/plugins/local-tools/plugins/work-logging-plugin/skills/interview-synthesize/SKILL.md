---
name: interview-synthesize
description: Synthesize feature-level entries from orphaned work log records
---

# /interview-synthesize

Cluster orphaned work log entries into feature-level summaries with optional topic correlation.

## Usage

```
/interview-synthesize [project-name]
```

## What it does

1. Reads work-log.jsonl for entries without a `feature` tag (orphaned)
2. Groups entries by project and overlapping file paths
3. Creates feature-level summaries in features.jsonl
4. Optionally runs two-stage topic correlation (semantic candidates + LLM judge)
5. Only Score 2 (strong match) correlations are persisted

## Options

- **project**: Filter to a specific project (default: all projects)
- **include_correlations**: Run topic correlation pipeline (default: true)

## Workflow

1. Run `/interview-synthesize` to see proposed features
2. Review the output — features are created automatically
3. Entries that were already tagged with a `feature` field are skipped
4. Re-running is safe — new entries will be synthesized, existing ones unaffected
