---
kind: implemented
feature_id: adhoc-process-friction-detector-counts-concurrent-session-commits
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [c951f67, 14840da, 5212ce0, ad5600d]
decisions: []
---

# Implementation Ledger

**What shipped:** `detect_cycle_bracket_friction`'s unexpected-commits signal subtracts a concurrent-writer commit count that is attributed by committer-EMAIL only, so a second session sharing this box's single git identity is invisible — its commits inflate the count and trip a FALSE unexpected-commits process-friction (self-announcing hardening debt that withholds the forward route).

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
