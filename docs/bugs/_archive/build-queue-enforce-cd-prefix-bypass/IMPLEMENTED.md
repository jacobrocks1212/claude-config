---
kind: implemented
feature_id: build-queue-enforce-cd-prefix-bypass
date: 2026-07-06
provenance: pipeline-gated
derivation: commit-brackets
commits: [9babe32, 5e1f13a, 4fdcd02]
decisions: []
---

# Implementation Ledger

**What shipped:** The `build-queue-enforce.sh` PreToolUse hook fails open whenever a heavy build is chained behind a leading command (`cd "…" && dotnet build …`), because its deny regexes are anchored to the start of the command. Agents — trained by the repo's own `AGENTS.md`/`/msbuild` examples to write exactly that form — bypass the queue and run raw `dotnet build`/`dotnet test`. A reinforcing skill-capability gap (no single-project build path) gives them a reason to.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
