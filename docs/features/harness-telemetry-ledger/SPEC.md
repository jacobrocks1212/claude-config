# Harness Telemetry Ledger + Trends — Feature Specification

> Retros find friction qualitatively; nothing measures it. Have `lazy-state.py`/`bug-state.py` emit a per-cycle ledger (cycles-per-feature, gate refusals, retry counts, halt frequency, wall-time) and add a trends view to `pipeline_visualizer`, so "did that harness change actually reduce coherence-recovery cycles?" is answerable with data.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The harness self-improves via retros and `/harden-harness`, but the feedback loop has no
quantitative signal: no baseline for cycles-per-completion, gate-refusal rates, or halt dwell
time, so hardening changes can't be verified as improvements against the mission's "efficient"
criterion.

## Direction (deliberately not locked)

- **Emitter:** append-only JSONL ledger written at existing state-script chokepoints (dispatch,
  gate refusal, halt write, mark-complete) — deterministic, never LLM-authored.
- **Residency:** per-repo keyed state dir (`claude_state_dir()`), consistent with
  `multi-repo-concurrent-runs`.
- **Renderer:** a trends page in `pipeline_visualizer` (stdlib-only, pure read) aggregating across
  runs/repos.
- **Retro hook-in:** `/lazy-batch-retro` cites ledger deltas instead of narrative-only claims.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: event schema + versioning;
> retention/rotation; cloud-run ledger transport; which metrics are v1. Solutions above are
> directional, not locked.
