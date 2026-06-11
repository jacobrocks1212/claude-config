---
name: interview-check
description: Quick interview topic relevance check against recent work using atomic KB tools
---

# /interview-check

Force a relevance check of recent engineering work against the interview knowledge bank.

## Usage

```
/interview-check
```

## What it does

1. Calls `read_work_log` to get recent entries (last 7 days)
2. Calls `get_kb_index` to load the compact topic index (~154 entries)
3. Semantically evaluates each topic against the recent work
4. For strong matches, calls `get_kb_topic` for full entry details
5. Presents relevant topics with talking points grounded in your actual work

## Atomic tools used

| Tool | Purpose |
|------|---------|
| `read_work_log` | Fetch recent work log entries |
| `get_kb_index` | Get compact topic index for scanning |
| `get_kb_topic` | Get full KB entry for matched topics |
| `evaluate_topic_match` | Score Feature×Topic relevance (0-2) |

## Silence rule

If no topics are relevant, produce ZERO output about the check. Only present results when there are genuinely relevant concepts to surface.
