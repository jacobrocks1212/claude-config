# Research — Orchestrator Tool-Search (dispatch-time tool-gap miss-path)

**Operator-directed skip-research (2026-07-19).** No external Gemini deep-research pass is
required. Per the SPEC's Research References, the work is internal harness plumbing grounded
entirely in the claude-config codebase and the 2026-07-19 evidence pass:

- Confirmed no dispatch-time tool-search exists today (the gap this feature closes).
- The observed-friction harden trigger #5 with its `blocking` policy (`lazy-batch/SKILL.md`).
- The `pending_hardening` route-withhold surface (`mechanize-prose-only-orchestrator-contracts`)
  reused verbatim as the "run waits" mechanism.
- The toolify miner + promotion ledger (`unified-pipeline-orchestrator`, `toolify-auto-promotion`)
  the miss-path dedups against so it never double-proposes a tool the offline miner surfaced.
- Host-capability defer (`host-capability-declaration-for-gated-features`) and the hardening
  depth-cap.
- Modeled on Claude Code's own ToolSearch (deferred-tool query→fetch) pattern.

All grounding is in-repo and already captured in the SPEC; no external source synthesis is needed.
Proceed directly to PHASES decomposition and planning.
