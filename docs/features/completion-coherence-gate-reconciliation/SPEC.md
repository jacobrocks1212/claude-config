# Reconcile the completion/coherence gates so MCP-verification rows don't force recurring coherence-recovery cycles — Feature Spec (stub)

> Draft (pre-Gemini)

**Status:** Draft (research stub)
**Tier:** 1
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/lazy_core.py` (`__mark_complete__`/`apply_pseudo` completion gate, verification-only carve-out), AlgoBooth `scripts/check-docs-consistency.ts`, `user/skills/lazy-batch/SKILL.md` Step 1c.5

---

## Problem / Friction Observed

The highest-frequency friction across the whole corpus: fully-validated features are refused at the finish line because three independent gates disagree about how to treat MCP/runtime verification rows, and each refusal forces an extra coherence-recovery meta-cycle that does nothing but tick boxes or re-categorize a work-unit.

- Operator @ session `e076ed30` 2026-06-14T20:32 — "Seems like we frequently have recovery agents to fix issues with PHASES.md formatting? How can we improve that? Better lint rules? More instructions to run lint? Different format altogether?" (operator explicitly raised this).
- session `5c33b6ba` @ 2026-06-11T23:46:55 — "apply_pseudo **refused** — the completion-coherence gate counts unchecked boxes across 6 phases as blocking, unlike lazy-state.py's routing carve-out." A fully-validated feature with VALIDATED.md + RETRO_DONE.md on disk was refused at the finish line.
- session `5c33b6ba` @ 14:43 — "check-docs-consistency.ts counts all phase checkboxes with no verification carve-out, but lazy_core's completion gate exempts verification-only rows." Three gates disagree: `check-docs-consistency.ts`, `apply_pseudo`, and `lazy_core`.
- session `5c33b6ba` @ 15:08 — the verification carve-out is keyed on checkbox POSITION relative to a bold marker; authors place rows in the wrong spot and the gate counts them as implementation gaps.
- Recurrence: `__mark_complete__`/verify-ledger refused on unchecked verification rows in essentially every completion-bearing session (`e076ed30` ~30 such refusals; also `2f6f27dc`, `5f227442`, `18e1d3d7`, `deb9f0cf`), each forcing an extra coherence-recovery meta-cycle.

## Desired Outcome (intent, NOT design)

The completion gates agree on one verification carve-out rule. A feature with on-disk passing evidence (VALIDATED.md / MCP_TEST_RESULTS.md) is not refused at the finish line over unchecked verification rows, and the recurring coherence-recovery meta-cycle is eliminated. The operator floated three directions — better lint rules, more lint instruction, or a different PHASES.md format — but the choice is left to `/spec`.

## Open Questions / Design Forks (for `/spec` to shape — do NOT pre-bake answers)

- Should the carve-out be unified by making all three gates call one shared rule, or by changing the PHASES.md format so verification rows are unambiguous?
- Is checkbox-position-relative-to-a-bold-marker the right signal at all, or should verification rows be tagged/typed explicitly?
- Should on-disk evidence (VALIDATED.md / MCP_TEST_RESULTS.md) override unchecked verification boxes entirely, or only satisfy specific rows?
- Where does the reconciled rule live — `lazy_core.py`, `check-docs-consistency.ts`, the PHASES.md template, or a new shared validator?
- Is the recurring meta-cycle better fixed by stronger lint enforcement up front, or by relaxing the gate's blocking behavior on verification-only gaps?

> **Stub — design NOT yet shaped.** Pre-Gemini draft. `/spec` (Step 4.5) shapes the baseline interactively (AskUserQuestion), then the research gate + `/plan-feature` follow. Do not bake the solution, phases, or implementation here.
