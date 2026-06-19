# Mechanize long-build / MCP-runtime ownership so a runtime survives the subagent turn boundary — Feature Spec (stub)

> Draft (pre-Gemini)

**Status:** Draft (research stub)
**Tier:** 1
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/skills/lazy-batch/SKILL.md` cycle-subagent execution model + "long-build-ownership rule"; `--ensure-runtime` subcommand; the orchestrator's manual rebuild→health-poll loops

---

## Problem / Friction Observed

Long-running builds and the dev/MCP runtime are owned inside the cycle subagent's process tree, which is reaped at the subagent turn boundary. `/mcp-test` then finds a dead runtime, real production edits are left orphaned, and the orchestrator compensates by hand-rolling repeated rebuild→health-poll loops.

- session `8ae22371` @ ~line 134 — "recurring lazy-batch process friction (mcp-test runtime dies at the subagent turn boundary; execute-plan loops on MCP-gate WUs)".
- session `18e1d3d7` @ ~line 198 — "the `--ensure-runtime` subcommand booted + asserted tools within its own Bash subprocess, but that process tree was torn down when the call returned (health_code: 0 was the tell). Per the long-build-ownership rule, the runtime must…"
- session `5c33b6ba` @ 2026-06-11T19:11:45 — a `tauri build` backgrounded inside a cycle subagent died with the subagent's turn, leaving real production edits uncommitted (orphaned cycle).
- session `5c33b6ba` — orchestrator hand-built repeated rebuild→health-poll→inspect-telemetry until-loops (~6+ times), each the same shape.

## Desired Outcome (intent, NOT design)

Long-running builds and the dev/MCP runtime are owned at a level that survives subagent turn boundaries (harness-tracked), so `/mcp-test` doesn't find a reaped runtime and the orchestrator stops hand-rolling rebuild/health-poll loops. The `--ensure-runtime` subcommand exists but its process tree is torn down at the subprocess boundary. The ownership mechanism is left to `/spec`.

## Open Questions / Design Forks (for `/spec` to shape — do NOT pre-bake answers)

- What level owns the runtime so it outlives a subagent turn — the orchestrator process, a detached/daemonized process, a harness-tracked sentinel, or an OS service?
- Should `--ensure-runtime` be reworked to spawn a surviving process, or replaced by a different ownership primitive?
- How is runtime liveness/health tracked across cycles without the orchestrator hand-rolling poll loops?
- How are orphaned builds and uncommitted production edits prevented or recovered when a cycle is torn down mid-build?
- Does the same mechanism cover both long builds (`tauri build`) and the persistent MCP/dev runtime, or are they owned separately?

> **Stub — design NOT yet shaped.** Pre-Gemini draft. `/spec` (Step 4.5) shapes the baseline interactively (AskUserQuestion), then the research gate + `/plan-feature` follow. Do not bake the solution, phases, or implementation here.
