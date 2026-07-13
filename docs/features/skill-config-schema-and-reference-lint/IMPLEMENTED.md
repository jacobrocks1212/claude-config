---
kind: implemented
feature_id: skill-config-schema-and-reference-lint
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 95df391, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** No schema or required-file contract exists for `repos/<name>/.claude/skill-config/` (algobooth: 21 files; cognito-forms: 16; cognito-docs: none) — missing-file semantics are per-reference prose conventions, with no way to distinguish intended-absent from broken. Field cost, transcript-mined: the #1 tool-error cluster in the entire AlgoBooth session corpus is **377 failed Reads of `.claude/skill-config/commit-policy.md` across ~100 sessions (over 10% of ALL tool errors)** — the file is referenced 29× across 17 skill files, exists in cognito-forms but NOT algobooth, so every cycle subagent burns a failed Read before falling back. Add a per-repo declared-files manifest with intended-absent markers, JSON-schema validation for the load-bearing `*.json` configs, and a `lint-skills.py` sweep of every `.claude/skill-config/<file>` mention (`!cat` AND prose) against each repo's dir — plus the immediate quick win: kill the 377-error cluster at the source.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
