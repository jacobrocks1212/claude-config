---
kind: implemented
feature_id: cycle-prompt-environment-dialect
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, c916248, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** Add a compact (<2KB), host-conditional environment-dialect section to the emitted cycle prompt (`_components/lazy-batch-prompts/cycle-base-prompt.md`) so cycle SUBAGENTS stop paying the transcript-mined Windows/environment error tax: Git-Bash trailing-backslash quoting failures (267 across 82 sessions), Bash-`/tmp`-vs-Windows-python mismatches (~119, still recurring despite a MEMORY.md note — memory notes don't reach subagents), WSL-guessed `sys.path` imports (~36), `/mnt/c` paths on Git Bash (~25), `json.load`-on-empty-stdin tracebacks from the taught marker-probe idiom (94), and oversized-PHASES.md Read failures (114) that `phases-slice.py` already exists to prevent but the cycle prompt never mandates. Anything that must bind subagent behavior must live in the emitted prompt or a hook — this puts the six killable clusters in the prompt, plus a never-throws `--marker-status` probe.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
