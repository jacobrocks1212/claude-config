---
name: interview-import
description: Import planning artifacts (SPEC.md, PHASES.md) from project repos as interview features
---

# /interview-import

Import planning artifacts from project repositories into the interview prep feature log.

## Usage

```
/interview-import <directory> [project-name]
```

## What it does

1. Scans the specified directory recursively for SPEC.md, PHASES.md, and RESEARCH.md files
2. Computes content hashes for idempotent dedup (re-running is safe)
3. Extracts titles from first H1 headings
4. Creates feature entries in `~/.interview-prep/features.jsonl`
5. Records import history in `~/.interview-prep/import-index.jsonl`

## Examples

```
/interview-import ~/source/repos/algobooth/docs/features algobooth
/interview-import ~/source/repos/cognito-forms/.claude.local cognito-forms
```

## Options

- **dry_run**: Preview what would be imported without writing
- **artifact_types**: Filter to specific types (default: spec, phases, research)

## Deduplication

- Same file + same content hash → skipped (already imported)
- Same file + different hash → evolved (new version, same UUID)
- New file → created (fresh UUID)
