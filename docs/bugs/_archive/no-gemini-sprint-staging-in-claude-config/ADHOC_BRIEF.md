---
kind: adhoc-brief
bug_id: no-gemini-sprint-staging-in-claude-config
enqueued_by: lazy-adhoc
date: 2026-06-20
---

# Ad-hoc bug: No docs/gemini-sprint/ staging structure in claude-config

The claude-config harness repo has no docs/gemini-sprint/ staging structure (no results/, no prompts/ symlinks, no _consumed/), so when claude-config is itself the pipeline-driven repo a needs-research halt cannot use the staged-.txt ingest path (the /lazy* Step 0.5 find probe) or /ingest-research's prompt-symlink correlation. Observed 2026-06-20: the long-build-and-runtime-ownership needs-research resume had to fall back to a direct RESEARCH.md drop because /ingest-research was inapplicable. Investigate whether claude-config should gain a gemini-sprint staging structure, whether the direct-RESEARCH.md-drop path should be the documented blessed path for self-edit repos, or whether /ingest-research and Step 0.5 should degrade gracefully when no staging dir exists.
