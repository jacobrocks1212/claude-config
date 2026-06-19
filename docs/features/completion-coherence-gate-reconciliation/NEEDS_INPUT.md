---
kind: needs-input
feature_id: completion-coherence-gate-reconciliation
written_by: spec
decisions:
  - Reconciliation direction — extend the carve-out to completion time vs push the tick into /mcp-test
  - On-disk evidence — auto-tick the verification rows vs only suppress the refusal
date: 2026-06-19
next_skill: spec
class: product
---

# /spec --batch — Needs Input

## Decision Context

### 1. Reconciliation direction — extend the carve-out to completion time vs push the tick into /mcp-test

**Problem:** Today three gates disagree about un-ticked *verification rows* (PHASES.md `- [ ]` checkboxes carrying the `<!-- verification-only -->` marker — runtime/MCP checks owned by the `/mcp-test` step, NOT by implementation). The mid-feature gate (`remaining_unchecked_are_verification_only`) and the ledger gate (`verify_ledger.deliverables_done`) both EXEMPT these rows. But the completion-time gate (`_phase_completion_plan`, run inside `__mark_complete__` at `lazy_core.py:3050`) INCLUDES them — it refuses the completion receipt if any verification row is unchecked, "the verification carve-out does not apply at completion time" (`lazy_core.py:1839`). So a fully-`/mcp-test`-validated feature (evidence already on disk as `VALIDATED.md`) is refused at the finish line, forcing an extra coherence-recovery meta-cycle whose only job is to tick those boxes. This is the single highest-frequency friction in the corpus (~30 such refusals in one session). The reconciliation needs ONE rule across the gates — but WHICH subsystem owns the fix is a product/ownership call that changes what the harness does at completion. This affects the Executive Summary, Technical Design (Direction A vs B), and Implementation Phases of SPEC.md.

**Options:**
- **A. Extend the carve-out to completion time, gated on on-disk evidence (Recommended)** — Make `_phase_completion_plan` apply the same verification-only exemption the mid-feature gate uses, but ONLY when `/mcp-test` evidence (`VALIDATED.md` / `MCP_TEST_RESULTS.md`) certifies passing AND the remaining unchecked rows are all verification-marked. The completion gate stops re-demanding rows whose evidence is already on disk; a feature with REAL unchecked implementation work still refuses (the gate's job is preserved). Single-repo change (`lazy_core.py` + smoke tests); reversible (it is a guarded exemption, easy to tighten). Risk: the exemption logic must be evidence-gated so it cannot let a genuinely-unvalidated feature through.
- **B. Keep the completion gate strict; make /mcp-test tick the verification rows it certifies** — Leave `_phase_completion_plan` counting every row, but make the `/mcp-test` step (the producer that writes the evidence) ALSO tick the verification checkboxes when it certifies them, so the completion gate never sees an unchecked verification row. Pushes the fix into the producer. Risk: re-introduces the producer/marker-drift class that `harness-hardening-retro-fixes` was fighting (a producer that ticks the wrong rows, or misses rows authored by `/blocked-resolution`); spreads the contract across more files than Direction A.

**Recommendation:** A — it unifies all three gates on the SAME evidence-gated rule with a single-repo, reversible change, and keeps the evidence (not a checkbox) as the source of truth for "is verification done"; it also leaves PHASES.md coherent for the downstream `check-docs-consistency.ts` checker (see Decision 2) without spreading the fix across producers.

### 2. On-disk evidence — auto-tick the verification rows vs only suppress the refusal

**Problem:** Once the completion gate honors on-disk `/mcp-test` evidence (Decision 1), there is a second product call: when the evidence is present and passing, should the gate AUTO-TICK the verification checkboxes in PHASES.md (rewriting `- [ ]` → `- [x]` for the certified rows), or only SUPPRESS its own refusal and mint the receipt while LEAVING the rows unchecked? This matters because a THIRD gate lives downstream in a sibling repo — AlgoBooth's `check-docs-consistency.ts` — which runs AFTER the SPEC is flipped to `Complete` and counts EVERY checkbox with no carve-out at all. A harness agent cannot edit that sibling-repo script. If the rows are left unchecked, that downstream checker will flag the now-`Complete` feature as incoherent (un-ticked boxes under a Complete SPEC) — re-creating the friction one repo over. This decision determines whether the user later sees a clean docs-consistency check or a residual coherence complaint, so it is product-visible.

**Options:**
- **A. Auto-tick the certified verification rows (Recommended)** — When evidence certifies passing, the completion gate rewrites the matching `- [ ]` verification rows to `- [x]` in PHASES.md (the same in-place, byte-stable rewrite the existing auto-flip logic at `lazy_core.py:3061` already does for phase Status lines), then mints the receipt. PHASES.md ends fully coherent, so `check-docs-consistency.ts` is satisfied with NO sibling-repo edit. Slightly larger change (a row-rewrite pass), but it makes the on-disk record honest: the rows the evidence certifies ARE marked done. Reversible.
- **B. Suppress the refusal only; leave the rows unchecked** — The gate stops refusing and mints the receipt, but does not modify PHASES.md. Smaller, lower-risk change inside `lazy_core.py`. Cost: the downstream `check-docs-consistency.ts` (uneditable from the harness) will flag the Complete feature's un-ticked verification boxes — so the friction reappears in the sibling repo unless that script is ALSO changed (operator-applied, out of this feature's reach). Leaves a permanent coherence gap between "evidence says done" and "PHASES.md says unchecked".

**Recommendation:** A — auto-ticking makes the certified rows match their on-disk evidence and leaves PHASES.md coherent for the uneditable downstream checker, fully closing the friction within the single repo this feature can change; B only half-fixes the problem and pushes a required edit into a repo the harness cannot touch.
