---
kind: implemented
feature_id: adhoc-unify-merged-head-coordinator-exemptions
date: 2026-07-19
provenance: pipeline-gated
derivation: commit-brackets
commits: [4f92bd4, ef6ee26, '8868056', 7b1c05d, a0d0a47, 58a7a3e, '2370190', 37834b1]
decisions: []
---

# Implementation Ledger

**What shipped:** The `--emit-prompt` merged-head divergence guard carries two separately-computed coordinator-emission exemption booleans (`_emit_is_lane`, `_emit_is_lease_held`), duplicated verbatim across both state scripts. Generalize to one predicate before a third near-neighbor (demoted-serial-rerun) accretes its own carve-out.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
