---
kind: implemented
feature_id: build-queue-eta-marker-mojibake-on-redirected-stdout
date: 2026-07-10
provenance: pipeline-gated
derivation: message-grep
commits: []
decisions: []
---

# Implementation Ledger

**What shipped:** The `≈` prediction marker on every pre-outcome ETA surface is emitted as OEM byte `0xF7` through powershell.exe's redirected stdout, which is invalid UTF-8 — agents and the Bash tool render `eta-start�0s eta-done�?` instead of `eta-start≈0s eta-done≈?`.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: skip-mcp-test. Receipt: FIXED.md (provenance: gated).**
