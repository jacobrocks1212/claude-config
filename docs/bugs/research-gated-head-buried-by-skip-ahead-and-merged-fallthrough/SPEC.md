# Research-gated head buried by default skip-ahead + merged-view fallthrough

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-07-17 (observed live during a `/lazy-batch` run on AlgoBooth)
**Related:** `docs/bugs/merged-head-diverged-stalls-on-gated-head` (Round 64 — introduced
`probe_skipped_ids`, which folds ALL gated heads incl. research-pending into the merged-head exclude
set; this bug refines that for the research subset); `feature-budget-guard-and-skip-ahead` (the
default-on skip-ahead + `--strict-research-halt`); `docs/features/unified-pipeline-orchestrator/`
(the merged-view / type-dispatch driver).

## Trigger

Orchestrator-observed friction during a live `/lazy-batch` run on AlgoBooth (2026-07-17). Two
**pre-release (P1)** features — `inspector-sample-clip-view` and `inspector-track-dashboard` — were
NEEDS_RESEARCH-gated (each carries `RESEARCH_PROMPT.md`, no `RESEARCH.md`). The default-on
dependency-aware skip-ahead advanced PAST both:

```
skip-ahead: 'inspector-sample-clip-view' is a gated head (research-pending or BLOCKED);
advancing past it to the next skip-ahead-ready item (default-on; --strict-research-halt restores
the legacy halt).
```

and the unified merged-view driver then routed to a LOWER-priority bug
(`protocol-generic-claims-drift`) at its final MCP-validation step. Net: two high-priority
pre-release features that need nothing but a research upload were buried behind a bug, and the
operator saw NO research-halt / no research prompt — they discovered the features were gated only by
asking manually.

## Reconstructed route (divergence point)

The per-pipeline `compute_state` skip-ahead (default-on) treats a **research-pending** gated head
identically to a **BLOCKED** gated head: `_is_gated_head` returns `research_pending OR BLOCKED.md`,
and both accumulate into `_GATED_HEADS`. Round 64's `lazy_core.dispatch.probe_skipped_ids` then
folds ALL of `gated_heads` (research + blocked) into the merged-head exclude set feeding
`merged_head_override` on the `--emit-prompt` path. So when a skip past a research-gated head is
REALIZED (an independent lower-priority alternative — or a cross-type bug — exists), the research
head is EXCLUDED from the merged view and the driver falls through to the lower-priority item,
surfacing NO needs-research halt.

**Divergence point:** the `--emit-prompt` merged-head exclude computation
(`lazy-state.py` merged-override block + `probe_skipped_ids`) conflates research-gated heads with
BLOCKED heads, so a HIGHER-priority research-gated head is silently skipped in favor of a
lower-priority fallthrough target.

## Root cause

**`root_cause_class: script-defect`** — research-gating is treated the same as BLOCKED-gating in the
DEFAULT skip-ahead / merged-fallthrough path. But the two are NOT equivalent: a BLOCKED head
(external gate / host) is not operator-resolvable in-session, so skipping ahead to find independent
ready work is reasonable; a **research gap is operator-resolvable in seconds** (upload the Gemini
research), so burying it behind lower-priority work defeats the entire purpose of the needs-research
halt (Step 4 of the lazy-batch SKILLs) — to SURFACE the research prompt so the operator can unblock
the higher-priority work.

Note: the single-gated-head / no-independent-alternative case ALREADY works — `compute_state`'s
`gated_head_fallback` dispatches the research head to its Step-5 `needs-research` terminal and clears
`_GATED_HEADS`. The defect is specifically the **realized-skip** case where the merged view falls
through to a lower-priority item.

## Fix scope

Treat research-gating distinctly from BLOCKED-gating in the default path, **keyed on relative merged
priority** vs the fallthrough target (NOT a blanket "always halt on any research-gated head"):

1. `compute_state` classifies gated heads by kind (`_gated_head_kind` → `research` | `blocked` |
   `None`; research-pending takes precedence when both present, aligning with the Step-1h
   research-blocked carve-out) and surfaces the research-pending subset as a new
   `research_gated_heads` probe key (mirroring `gated_heads`; absent when empty; cleared in the
   `gated_head_fallback` path). `gated_heads` is UNCHANGED (still research + blocked).
2. New pure helper `lazy_core.dispatch.research_halt_head(state, feature_items, bug_items, repo_root,
   exclude_ids)`: returns the id of a research-gated skipped head that is the HEAD of the merged
   worklist once the merely-BLOCKED / host / device / dep skips (and parked/deferred items) stay
   excluded but the research-gated skips are RE-INCLUDED — i.e. the research head OUTRANKS (full
   merged ordering, incl. the type tie-break) the item the driver would otherwise dispatch. Else
   `None`. Keyed on relative priority: when the research head is LOWER priority than genuinely
   independent ready work, the research-inclusive merged head is that ready item (not the research
   head) → returns `None` → skip-ahead proceeds (no over-halt).
3. On the `--emit-prompt` path (feature pipeline), when `research_halt_head` returns an id, re-emit
   as that head's SCOPED `needs-research` terminal (a `compute_state(scope_feature_id=<head>,
   strict_research_halt=True)` re-run, fail-safe: adopted only if it actually yields
   `terminal_reason=needs-research`). The driver's EXISTING `needs-research` (Step 4) handling then
   surfaces the research prompt and halts — loop-free (no re-dispatch, no stall). Adds
   `route_overridden_by: "research-gated-head"` for observability.

## Coupled-pair / parity note

Research gating is a **feature-pipeline** mechanic — the bug pipeline has no research gate (mirroring
the existing `strict_research_halt` PARITY-ONLY asymmetry in `bug-state.py`). After the tie-break
fix (`non-p0-bug-outranks-p1-feature-on-aged-tie`), `--next-merged` returns a bug over a P1 research
feature ONLY when the bug is a genuine P0 — which legitimately precedes a P1 research gap — so the
bug side needs no research-halt surfacing (documented parity, not a gap). `probe_skipped_ids` is
UNCHANGED (still folds all gated heads); `research_halt_head` subtracts only the research subset. The
coupled trio (`/lazy-batch`, `/lazy-bug-batch`, `/lazy-batch-cloud`) gets a focused prose note that a
feature `--emit-prompt` can now return a `needs-research` terminal for a different head than
`--next-merged` named (the research head that outranks the fallthrough).

## Design fork (park-provisional)

The precedence rule — surface iff the research head is the research-inclusive merged head (i.e.
strictly ahead in the full merged ordering incl. the type tie-break), and research-first when a head
carries both a research prompt and a BLOCKED.md — is a routing-precedence design choice. Divergence
graded **contained** (a routing-precedence change, reversible by removing the helper call; no
architecture / persistent-data / gate-weakening). Implemented under the park-provisional default with
a `NEEDS_INPUT_PROVISIONAL.md` recorded for operator ratification.
