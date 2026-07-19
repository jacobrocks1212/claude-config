---
kind: implemented
feature_id: decision-2-6-uncovered-row-reroute-to-mcp-test
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [5ae3202, 3e70cda, 14ef508, 5312b9d, 84a2d71, c2bca4d, 7e2f54b, 5e1e587, 7e3bb22,
  b661477, 57b07fe, 9ce3b8f, aa056e8, 92ea330, 43a1b79, 91e811f, 193cb99, 4f6b280]
decisions: []
---

# Implementation Ledger

**What shipped:** A completion cycle that reaches Step 10 with `VALIDATED.md` present but a matrix-incomplete PHASES.md unconditionally dispatches `__mark_complete__`, which the completion-coherence gate then refuses — with NO re-route back to `mcp-test` to finish (or author) the missing coverage. This produces a VALIDATED→refuse→coherence-recovery→VALIDATED oscillation (decision 2) and strands newly-discovered-at-completion coverage (decision 6).

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
