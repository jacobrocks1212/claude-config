---
name: interview-generate
description: Generate the Obsidian interview prep vault from work log and features data
---

# /interview-generate

Generate (or regenerate) the full Obsidian interview prep vault.

## Usage

```
/interview-generate [output-dir]
```

## What it does

1. Reads all data sources (work-log.jsonl, features.jsonl, knowledge-bank/)
2. Generates 5 vault collections:
   - `01_Knowledge_Bank/` — 154 topic pages with correlated story links
   - `02_Work_History/` — granular work log pages linked to parent features
   - `03_Features/` — initiative-level pages with story outlinks
   - `04_Interview_Stories/` — domain-specific narratives (ISTART, ADR, Entity-Pattern, Algorithm)
   - `Meta/dashboard.md` — coverage stats and gap analysis
3. Uses managed blocks to preserve user annotations across regenerations
4. Enforces DAG link topology (Work → Feature → Story → KB Topic)

## Options

- **output_dir**: Custom output path (default: ~/.interview-prep/vault/)

## Regeneration safety

User content outside `<!-- BEGIN MANAGED -->` / `<!-- END MANAGED -->` delimiters is preserved.
SRS scheduling metadata (sr-due, sr-interval, sr-ease) in frontmatter is preserved.
