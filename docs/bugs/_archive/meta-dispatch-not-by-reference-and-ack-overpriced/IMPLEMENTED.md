---
kind: implemented
feature_id: meta-dispatch-not-by-reference-and-ack-overpriced
date: 2026-07-13
provenance: pipeline-gated
derivation: message-grep
commits: [03993c0]
decisions: []
---

# Implementation Ledger

**What shipped:** The `@@lazy-ref` by-reference mechanism originally covered only CYCLE prompts, forcing the orchestrator to hand-transcribe multi-KB `--emit-dispatch` META prompts byte-exactly (12 "not script-emitted" + 4 "transcription slip" denials in one run). The by-ref half is NOW FIXED in current code (every `--emit-dispatch` class emits `dispatch_prompt_ref`). The REMAINING defect: retiring a deny-ledger entry still costs one full Opus `/harden-harness` dispatch per entry — even for explicit no-fix / already-fixed denials — with no cheap ack-only ledger operation.

**Decisions that drove it:** (none — the SPEC carries no Locked-Decision surface)

**Validated via: mcp. Receipt: FIXED.md (provenance: gated).**
