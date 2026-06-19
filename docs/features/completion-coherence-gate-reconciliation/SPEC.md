# Completion / Coherence Gate Reconciliation — Feature Specification

> Make the three completion-time gates agree on ONE verification carve-out rule, so a feature whose `/mcp-test` evidence is already on disk is not refused at the finish line over un-ticked verification checkboxes — eliminating the recurring coherence-recovery meta-cycle.

**Status:** Draft (baseline — pre-research)
**Priority:** P1
**Last updated:** 2026-06-19
**Tier:** 1
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks). Highest-frequency friction in the corpus; operator-flagged.

**Depends on:**

- harness-hardening-retro-fixes — composes — extends the canonical `<!-- verification-only -->` marker + `remaining_unchecked_are_verification_only` detector (introduced there for the MID-feature gate) to the COMPLETION-time coherence gate it deliberately left untouched.

<!-- TODO: confirm kind for harness-hardening-retro-fixes — composes (build-atop), arguably hard (depends on the marker contract's concrete shape) -->

---

## Executive Summary

The single highest-frequency friction across the whole session corpus: fully-validated features are refused at the finish line because the completion-time gates disagree about how to treat MCP/runtime verification rows in PHASES.md. The `/mcp-test` step has already certified runtime behavior and written its evidence (`VALIDATED.md` / `MCP_TEST_RESULTS.md`) to disk — but the very next step, `__mark_complete__`'s `_phase_completion_plan` coherence gate, re-demands those same verification checkboxes be *ticked* in PHASES.md and refuses the receipt if they are not. Each refusal forces an extra coherence-recovery meta-cycle whose only job is to tick boxes — work that the on-disk evidence already proves done.

There are **two completion-time evaluations of "are the deliverables done?" that disagree on one rule**, plus a downstream third gate in a sibling repo:

1. **`verify_ledger`'s `deliverables_done` check** (`lazy_core.py:~2001`) — **EXEMPTS** verification rows via `remaining_unchecked_are_verification_only`. Passes.
2. **`_phase_completion_plan`** (`lazy_core.py:~1839`, called inside `__mark_complete__` at `lazy_core.py:~3050`) — **INCLUDES** verification rows ("the verification carve-out does not apply at completion time"). Refuses.
3. **AlgoBooth `check-docs-consistency.ts`** — runs *post-flip* under a `Complete` SPEC, counts **every** checkbox with no carve-out at all. Lives in a repo a harness agent cannot edit.

So a feature passes gate (1), gets refused by gate (2), a recovery cycle ticks the boxes, and then gate (3) is satisfied — three gates, three different rules, one redundant cycle in the middle. The reconciliation: make gate (2) honor the SAME carve-out gates (1) and the mid-feature detector already use, and treat on-disk `/mcp-test` evidence as authoritative for ticking the verification rows it certifies.

## Atomic Decomposition (load-bearing terms)

```
Terms in play:
- completion gate        → `_phase_completion_plan` refusal inside `__mark_complete__` (lazy_core.py:3050) + `verify_ledger.deliverables_done` (lazy_core.py:2001)
- coherence gate         → AlgoBooth `check-docs-consistency.ts` — runs POST-flip under a Complete SPEC, counts ALL checkboxes, no carve-out
- verification row       → a `- [ ]` PHASES.md checkbox carrying `<!-- verification-only -->` (or under a marked/regex-matched subsection); a runtime/MCP check owned by `/mcp-test`, NOT `/execute-plan`
- "the gates disagree"   → verify_ledger EXEMPTS verification rows; _phase_completion_plan INCLUDES them; check-docs counts all → one passes, the next refuses
- coherence-recovery     → an extra /lazy-batch cycle whose ONLY work is ticking verification boxes so _phase_completion_plan stops refusing
  meta-cycle
- on-disk passing        → `VALIDATED.md` (kind: validated) / `MCP_TEST_RESULTS.md` (kind: mcp-test-results, result: all-passing, pass==total, validated_commit==HEAD)
  evidence                 — the receipts `/mcp-test` already wrote BEFORE __mark_complete__ runs
```

**Reconstructed problem:** `/mcp-test` certifies runtime verification and writes its evidence to disk. The next step (`__mark_complete__`) re-demands the same verification rows be checkbox-ticked and refuses if not — even though the evidence is already on disk and the mid-feature gate already exempts those exact rows. The fix: make the completion-time coherence gate honor the verification carve-out AND treat on-disk `/mcp-test` evidence as satisfying (and auto-ticking) the verification rows it certifies, so no recovery cycle is needed.

## Problem / Friction Observed

- Operator @ session `e076ed30` 2026-06-14T20:32 — "Seems like we frequently have recovery agents to fix issues with PHASES.md formatting? How can we improve that? Better lint rules? More instructions to run lint? Different format altogether?" (operator explicitly raised this.)
- session `5c33b6ba` @ 23:46:55 — "apply_pseudo **refused** — the completion-coherence gate counts unchecked boxes across 6 phases as blocking, unlike lazy-state.py's routing carve-out." A fully-validated feature with `VALIDATED.md` + `RETRO_DONE.md` on disk was refused at the finish line.
- session `5c33b6ba` @ 14:43 — "check-docs-consistency.ts counts all phase checkboxes with no verification carve-out, but lazy_core's completion gate exempts verification-only rows." Three gates disagree.
- session `5c33b6ba` @ 15:08 — the verification carve-out is keyed on checkbox POSITION relative to a bold marker; authors place rows in the wrong spot and the gate counts them as implementation gaps. (Note: `harness-hardening-retro-fixes` Phase 2 already moved the MID-feature detector to a structural per-row marker — this position-sensitivity now only bites the completion-time gate, which never adopted the carve-out at all.)
- Recurrence: `__mark_complete__`/verify-ledger refused on unchecked verification rows in essentially every completion-bearing session (`e076ed30` ~30 such refusals; also `2f6f27dc`, `5f227442`, `18e1d3d7`, `deb9f0cf`), each forcing an extra coherence-recovery meta-cycle.

## Current Behavior (code-grounded, verified 2026-06-19)

| Gate | Location | Verification-row rule | When it fires |
|------|----------|------------------------|---------------|
| `remaining_unchecked_are_verification_only` (mid-feature) | `lazy_core.py:1372` | EXEMPT (marker-based since `harness-hardening-retro-fixes` Phase 2) | Step 7 write-plan fall-through |
| `verify_ledger.deliverables_done` | `lazy_core.py:~2001` | EXEMPT (reuses the detector above) | `--verify-ledger` ledger check |
| `_phase_completion_plan` | `lazy_core.py:1839` | **INCLUDED** — "carve-out does not apply at completion time" | `__mark_complete__` / `__mark_fixed__` pre-flip refusal (`lazy_core.py:3050`) |
| `check-docs-consistency.ts` | AlgoBooth repo (not in this workspace) | counts ALL checkboxes, no carve-out | post-flip, under a `Complete` SPEC |

The decisive line is `lazy_core.py:3041` / `:1839`: `_phase_completion_plan` refuses on "unchecked boxes incl. verification rows," and it does NOT consult `VALIDATED.md` / `MCP_TEST_RESULTS.md` to satisfy those rows. By the time it runs, the `/mcp-test` evidence is already on disk (the gate ran AT step 9, completion is step 10).

## Desired Outcome (intent, NOT design)

The completion-time gate stops refusing fully-validated features over un-ticked verification rows. The recurring coherence-recovery meta-cycle is eliminated. Crucially, this is NOT a blanket relaxation: a feature is only let through when its `/mcp-test` evidence is genuinely on disk and passing — the gate's job (refusing features with real unfinished implementation work) is preserved; only the redundant re-demand for already-certified verification rows is removed.

## Technical Design (TBD — pending research)

The shape of the reconciliation is the central open question (see Open Questions). Two candidate directions, both code-grounded:

- **Direction A — extend the carve-out to completion time (recommended-leaning).** Make `_phase_completion_plan` apply the same `remaining_unchecked_are_verification_only` exemption the mid-feature gate uses, BUT gated on on-disk passing evidence: when `VALIDATED.md` / `MCP_TEST_RESULTS.md` certify passing AND the only unchecked rows are verification-marked, auto-tick those rows (so post-flip `check-docs-consistency.ts` is satisfied too) and proceed. This unifies all three gates on one rule and removes the recovery cycle. Single-repo change (`lazy_core.py` + tests); the AlgoBooth checker needs no edit because the rows end up ticked.
- **Direction B — keep the gate strict; make `/mcp-test` tick the rows.** Leave `_phase_completion_plan` counting all rows, but make the `/mcp-test` step (which writes the evidence) ALSO tick the verification checkboxes it certifies, so the gate never sees an unchecked verification row at completion. Pushes the fix upstream into the producer; risk is the producer/marker drift the upstream feature was fighting.

**TBD (pending input):** which direction (A vs B), and whether on-disk evidence should auto-tick rows or only suppress the refusal without writing. These are scope/ownership decisions surfaced via NEEDS_INPUT.md (see below).

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Validated feature with un-ticked verification rows completes without a recovery cycle | `__mark_complete__` with `VALIDATED.md` on disk + only verification rows unchecked | receipt minted (`COMPLETED.md`), Status → Complete, no refusal | `lazy-state.py --test` fixture; `lazy_core.py` smoke harness |
| Feature with REAL unchecked implementation rows still refuses | `__mark_complete__` with a non-verification `- [ ]` row | refusal naming the offending phase, zero writes | `lazy_core.py` smoke harness |
| Auto-ticked verification rows leave PHASES.md coherent for the downstream checker | post-completion | every checkbox ticked OR phase Superseded | parse PHASES.md; (manually) `check-docs-consistency.ts` clean |
| `verify_ledger` and `_phase_completion_plan` agree on the same input | `--verify-ledger` then `__mark_complete__` on the same feature | both pass, or both name the same blocking phase | both `--test` suites green |

## Open Questions (for `/spec` research + NEEDS_INPUT to resolve)

1. **Reconciliation direction (A vs B above)** — extend the carve-out to completion time (single-repo, evidence-gated) vs push the tick upstream into `/mcp-test`. *Product/ownership decision → NEEDS_INPUT.*
2. **On-disk evidence as override vs satisfier** — should `VALIDATED.md`/`MCP_TEST_RESULTS.md` auto-TICK the verification rows (leaving PHASES.md coherent for `check-docs-consistency.ts`), or only SUPPRESS the refusal without writing (leaving the rows unchecked but the receipt minted)? The first keeps the sibling-repo checker happy; the second is a smaller change but leaves a post-flip coherence gap. *Product decision → NEEDS_INPUT.*
3. **Which evidence is authoritative** — `VALIDATED.md` alone, or also `MCP_TEST_RESULTS.md` (result: all-passing, pass==total, validated_commit==HEAD)? `SKIP_MCP_TEST.md` / `DEFERRED_*` cases? *Research-answerable + edge-case mapping.*
4. **check-docs-consistency.ts reconciliation** — it lives in a repo a harness agent cannot edit. If Direction A auto-ticks the rows, the checker needs no change. Confirm that's the full story, or whether the carve-out must also be mirrored into that script (operator-applied). *Research-answerable.*
5. **Lint enforcement vs gate relaxation** — is the recurring cycle better fixed by stronger up-front lint (force authors to mark rows correctly) or by the gate honoring evidence? (The upstream marker work already addressed the mid-feature lint side.) *Research-answerable.*

## Research References

To be populated in Phase 3 after the Gemini deep-research pass. Upstream reality-check sources read during Phase 1: `harness-hardening-retro-fixes/PHASES.md` Phase 2 (verification-only marker contract), `lazy_core.py` (`_phase_completion_plan`, `verify_ledger`, `remaining_unchecked_are_verification_only`), `user/scripts/CLAUDE.md` (verification-only canonical marker section).

> **Baseline draft — design NOT yet locked.** Pre-research. The reconciliation direction (Open Questions 1-2) is a product/ownership decision surfaced via NEEDS_INPUT.md this cycle. Do not bake the implementation, phases, or final gate code here.
