---
kind: implemented
feature_id: park-provisional-acceptance
date: 2026-07-09
provenance: pipeline-gated
derivation: message-grep
commits: [4015bb7, 239a1a9]
decisions: []
---

# Implementation Ledger

**What shipped:** A third decision tier between the D2 two-key mechanical auto-accept and the plain product-class park: in `--park --park-provisional` mode, a low-divergence product-class `NEEDS_INPUT.md` whose every decision carries a recommendation is PROVISIONALLY accepted (recommended option taken, pipeline continues implementing), durably marked `NEEDS_INPUT_PROVISIONAL.md`, and re-surfaced to the operator for ratify-or-redirect before the feature can ever complete.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: COMPLETED.md (provenance: gated).**
