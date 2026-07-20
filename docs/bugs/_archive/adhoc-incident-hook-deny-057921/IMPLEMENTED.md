---
kind: implemented
feature_id: adhoc-incident-hook-deny-057921
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [2dab06d, 231432d, 3fc7668, f3998d7, 46d085c]
decisions: []
---

# Implementation Ledger

**What shipped:** `lazy-cycle-containment.sh`'s second-feature-commit tripwire sources its staged-path set from `git diff --cached --name-only` — the ENTIRE shared-worktree index. Under sanctioned concurrent same-worktree writers (parallel `/lazy-batch` lanes, a second interactive/scheduled session, a background harden dispatch), that index carries OTHER lanes' staged-but-uncommitted sentinel files (`docs/bugs/<other>/FIXED.md`, `SPEC.md`, `GATE_VERDICT.md`). Those foreign paths are not carve-outs for THIS dispatch's `feature_id`, so they land in `offending` and the tripwire denies a cycle subagent's commit as a "second-feature commit" — even when the subagent staged only its own paths. The tripwire has no notion of the commit's own pathspec; it assumes `git commit` will flush the whole index.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
