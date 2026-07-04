---
kind: implemented
feature_id: stale-marker-arms-validate-deny-on-unrelated-dispatches
date: 2026-07-04
provenance: backfilled
derivation: message-grep
commits: [0cb8f6c, 4414f1b, d6920b5, e6691d0, 0907d36, 27109c0]
decisions: []
---

# Implementation Ledger

**What shipped:** A run marker that is still live for THIS repo arms the validate-deny guard against every Agent dispatch in the session — including ordinary, unrelated design/spec dispatches. Those denials accrue as hardening debt that gates `--run-end`; the inverse (a foreign session's marker) silently disarms a live run's guard. Per-repo keying closed the cross-repo leak but left the same-repo / cross-session / stale dimension open because the guard gate is **session-blind** and the deny-ledger has **no pipeline-vs-unrelated discriminator**.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Backfilled from message-grep history. Receipt: FIXED.md (provenance: gated).**
