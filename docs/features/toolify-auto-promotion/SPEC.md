# Auto-Promotion Pipeline for Toolify Candidates — Feature Specification

> `toolify-miner.py` proposes but promotion is fully manual. Add a step that auto-drafts `/spec` stubs (with the miner's evidence attached) for above-bar candidates into the feature queue, and track proposal→promotion acceptance rate so the bar itself can be tuned.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

The miner's output (ranked, evidence-backed toolification candidates) dead-ends in a report; each
promotion requires the operator to hand-author a feature stub. The deliberate-promotion bar
(`docs/features/unified-pipeline-orchestrator/toolify-bar.md`) is right, but the *mechanics* of
promotion are friction, so above-bar candidates rot.

## Direction (deliberately not locked)

- **Materializer:** a script step that converts an above-bar miner entry into a pre-Gemini stub
  (SPEC.md + queue entry + ROADMAP row) with the miner's occurrence/token evidence embedded —
  reusing the existing `--enqueue-adhoc` / stub conventions, never bypassing them.
- **Operator gate preserved:** stubs still route through `/spec` Step 4.5 interactive
  baseline-lock; auto-drafting ≠ auto-approval, keeping the deliberate-promotion bar intact.
- **Feedback:** record promoted/declined per candidate so the bar's thresholds are tunable from
  acceptance data.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: invocation cadence (retro step vs.
> standalone); dedup against already-promoted/declined candidates; where acceptance stats live.
> Solutions above are directional, not locked.
