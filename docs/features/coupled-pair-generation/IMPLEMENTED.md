---
kind: implemented
feature_id: coupled-pair-generation
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0, 7f7705b, 7678b5f, fe6fcd3]
decisions: []
---

# Implementation Ledger

**What shipped:** The five coupled skill pairs (`lazy-batch`→{`lazy-bug-batch`, `lazy-batch-cloud`}, `lazy`→{`lazy-bug`, `lazy-cloud`}, `lazy-status`→`lazy-bug-status`) are maintained by hand-duplication plus a regex-presence parity audit: of the manifest's 129 audited heading entries, 112 (~87%) are `restated` — manually duplicated prose, ~306KB across the two derived whales alone — and every canonical edit is a 3-way edit (canonical + derived + 748-line manifest). Replace hand-duplication with generation: a derived SKILL.md becomes a build output of (canonical text × the manifest's existing `token_substitutions` × an authored divergence-overlay set), the manifest becomes build input instead of audit ledger, and `lazy_parity_audit.py` demotes to a freshness verifier (generated output byte-matches the committed derived file). 112 hand-maintained restatements collapse into ~11 authored divergences.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
