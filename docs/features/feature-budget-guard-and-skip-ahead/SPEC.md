# Stop one hard feature from monopolizing a batch; skip ahead to independent queue work past a blocked or research-gated head item — Feature Spec (stub)

> Draft (pre-Gemini)

**Status:** Draft (research stub)
**Tier:** 1
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy-state.py` queue selection, `--skip-needs-research` / `--allow-research-skip`, validation_escalation / `/investigate` gate; `user/skills/lazy-batch/SKILL.md`

---

## Problem / Friction Observed

A single stubborn feature can silently consume an entire batch budget, and when the head item is blocked or research-gated the strict default strands the whole queue behind it rather than advancing to independent, ready work.

- session `5c33b6ba` — one feature (d8-live-looping) consumed ~10h / the entire extended 20→32 budget and ~5 MCP-validation blocks, then was force-stopped; the queue never advanced past it.
- session `18e1d3d7` (AskUserQuestion) — "clap-plugin-host-chain-slot (spun off this run, now queue-top) needs Gemini research before it can proceed. The strict default halts the whole run here, stranding 59 independent front-loaded features + poly-mod behind it, with 3 forward cycles left."
- session `61d6ddcf` — d7-wavetable looped ~20 cycles producing 6 corrective phases with shifting/contradictory root causes (predates the investigate-first gate, which now helps, but the queue-monopoly shape remains).

## Desired Outcome (intent, NOT design)

A single stubborn feature cannot silently consume an entire batch budget. When the head item is blocked or research-gated, the orchestrator can skip ahead to independent, ready queue items instead of stranding the whole queue. Note `--allow-research-skip` already exists but is non-default and opt-in. The policy/heuristic design is left to `/spec`.

## Open Questions / Design Forks (for `/spec` to shape — do NOT pre-bake answers)

- What per-feature budget signal triggers a guard — cycles consumed, MCP-validation blocks, wall-clock, corrective-phase count, or a composite?
- When the guard trips, what happens to the monopolizing feature — force-stop, defer-to-back-of-queue, escalate to `/investigate`, or AskUserQuestion?
- Should skip-ahead become the default behavior when the head item is research-gated, or remain opt-in (`--allow-research-skip`)?
- How is "independent / ready" determined for skip-ahead — explicit dependency metadata, no-RESEARCH-needed status, or something else?
- Does skip-ahead reorder the queue persistently, or only for the current batch run?

> **Stub — design NOT yet shaped.** Pre-Gemini draft. `/spec` (Step 4.5) shapes the baseline interactively (AskUserQuestion), then the research gate + `/plan-feature` follow. Do not bake the solution, phases, or implementation here.
