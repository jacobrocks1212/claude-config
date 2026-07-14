---
kind: implemented
feature_id: build-queue-runner-tests-dual-beforeall-fails-pester6
date: 2026-07-14
provenance: pipeline-gated
derivation: message-grep
commits: []
decisions: []
---

# Implementation Ledger

**What shipped:** `user/scripts/build-queue-runner.Tests.ps1` declares TWO top-level `BeforeAll` blocks. This was valid under Pester 5 but Pester 6.0.0 (this machine's installed version) rejects it AT DISCOVERY with `BeforeAll is already defined in this block`, so the entire suite — one of the five `build-queue*.Tests.ps1` suites that constitute the build-queue L6 completion gate — fails to be discovered or run. A completion-integrity suite is silently un-runnable here.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
