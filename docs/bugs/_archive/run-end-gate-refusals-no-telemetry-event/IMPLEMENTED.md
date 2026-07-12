---
kind: implemented
feature_id: run-end-gate-refusals-no-telemetry-event
date: 2026-07-12
provenance: pipeline-gated
derivation: commit-brackets
commits: [50cb29d]
decisions: []
---

# Implementation Ledger

**What shipped:** The state scripts' `--run-end` gates refuse (exit 1, marker kept) — unacked-hardening-debt, the new efficacy-flush-missing gate, and checkpoint-authorization — WITHOUT emitting a telemetry event, so those refusals are invisible to the efficacy loop that measures harness health. The mechanism already exists (`append_telemetry_event`, already emitted for `containment-refusal` and the `--verify-ledger` `gate-refusal`); the run-end refusal sites just don't call it — so a fix targeting run-end refusals has no countable signal to grade against.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
