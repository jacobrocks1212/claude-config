---
kind: implemented
feature_id: adhoc-audit-obligation-fires-on-zero-commit-failed-cycle
date: 2026-07-18
provenance: pipeline-gated
derivation: commit-brackets
commits: [b0889c6, 86c4f41, 33e301e, 719ec33, 53ce28f, 86ff644, ea3b700, 17af268]
decisions: []
---

# Implementation Ledger

**What shipped:** A `/spec`-kind cycle that fails with zero commits still arms the §1d.5 input-audit obligation; the pre-composed emit command then binds `cycle_commit_sha=HEAD~1`, which points at the PREVIOUS (unrelated) item's commit — dispatching a pointless ~77k-token audit against the wrong diff.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
