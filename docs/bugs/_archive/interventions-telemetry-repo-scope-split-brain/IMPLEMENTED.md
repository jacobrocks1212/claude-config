---
kind: implemented
feature_id: interventions-telemetry-repo-scope-split-brain
date: 2026-07-12
provenance: pipeline-gated
derivation: commit-brackets
commits: [fba244b, 5c2b13e, fba2399, 12b9d17, ed8d1b4, d1e4e6b, 6f72599, b34109c]
decisions: []
---

# Implementation Ledger

**What shipped:** Intervention records live in claude-config (`docs/interventions/`, 25 records), but the telemetry that must grade them lives in the TARGET repo's keyed state dir (AlgoBooth: 1,248 events / 32 runs). Every sanctioned vantage of `efficacy-eval.py` sees one side or the other, never both — so the now-mechanically-enforced end-of-run flush is a permanent clean no-op that still satisfies the `--run-end` breadcrumb gate. Zero verdicts have ever been produced; no review will ever come due.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
