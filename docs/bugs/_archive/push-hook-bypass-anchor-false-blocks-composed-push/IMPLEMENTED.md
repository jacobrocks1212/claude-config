---
kind: implemented
feature_id: push-hook-bypass-anchor-false-blocks-composed-push
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [56aa9bb, 45b384b]
decisions: []
---

# Implementation Ledger

**What shipped:** The work-repo push hook only honors the `CLAUDE_PUSH_APPROVED=1` bypass when it *leads the whole command string*, so an approved push prefixed with `cd …&&` (or any other command/env) is falsely blocked.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
