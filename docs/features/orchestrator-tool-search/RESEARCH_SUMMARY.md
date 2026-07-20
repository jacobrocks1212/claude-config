# Research Summary — Orchestrator Tool-Search

**Skip-research path (operator-directed, 2026-07-19).** No external deep-research pass; the
feature is internal harness plumbing grounded in the claude-config codebase. This summary exists
to satisfy the Step 5 research gate and unblock PHASES decomposition (`/plan-feature`).

## Key grounding (all in-repo)

- **The gap:** no dispatch-time tool-search exists — a cycle/orchestrator hitting a missing tool
  has no in-run "find/fetch the tool" path. This feature adds the inline, mid-run analog of the
  offline toolify miner.
- **Reuse, don't fork:** the miss-path emits through the existing `--emit-dispatch` /
  `pending_hardening` route-withhold surface (`mechanize-prose-only-orchestrator-contracts`) as the
  "run waits" mechanism — never forks it.
- **Dedup:** shares the toolify promotion ledger (`unified-pipeline-orchestrator`,
  `toolify-auto-promotion`) so a runtime tool-gap never double-proposes a tool the offline miner
  already surfaced.
- **Auto-remediation:** the miss-path auto-dispatches `/harden-harness`
  (`harness-hardening-retro-fixes`), constrained by its anti-overfit reflex + depth-cap; a
  backgrounded build survives the cycle turn boundary (`long-build-and-runtime-ownership`).
- **Absent-binary case:** an absent host CLI/toolchain reuses the deterministic defer model
  (`host-capability-declaration-for-gated-features`).
- **Prior art:** modeled on Claude Code's own ToolSearch (deferred-tool query→fetch).

## Decisions deferred to PHASES/planning

- Exact miss-path emission shape + dedup key against the toolify ledger.
- The blocking vs backgrounded policy boundary for an auto-dispatched harden on a tool gap.
