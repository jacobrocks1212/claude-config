# Completion / Coherence Gate Reconciliation — Feature Specification

> Make the three completion-time gates agree on ONE verification carve-out rule, so a feature whose `/mcp-test` evidence is already on disk is not refused at the finish line over un-ticked verification checkboxes — eliminating the recurring coherence-recovery meta-cycle.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-06-19
**Tier:** 1
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks). Highest-frequency friction in the corpus; operator-flagged.

**Depends on:**

- harness-hardening-retro-fixes — composes — extends the canonical `<!-- verification-only -->` marker + `remaining_unchecked_are_verification_only` detector (introduced there for the MID-feature gate) to the COMPLETION-time coherence gate it deliberately left untouched.

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

## Technical Design (LOCKED — operator-resolved 2026-06-19)

Direction A is chosen, with on-disk evidence auto-ticking the certified verification rows (Decisions 1 and 2 below, resolved via NEEDS_INPUT.md). The reconciliation is a single-repo, evidence-gated change to `_phase_completion_plan` in `lazy_core.py` plus smoke tests; no sibling-repo (`check-docs-consistency.ts`) edit is needed because the rows end up ticked.

**Direction A (chosen) — extend the carve-out to completion time, gated on on-disk evidence.** Make `_phase_completion_plan` apply the same `remaining_unchecked_are_verification_only` exemption the mid-feature gate (`lazy_core.py:1372`) and `verify_ledger.deliverables_done` already use, BUT gated on on-disk passing evidence:

- The completion gate consults `/mcp-test` evidence (`VALIDATED.md` / `MCP_TEST_RESULTS.md`). The exemption fires ONLY when that evidence certifies passing AND every remaining unchecked row is verification-marked (`<!-- verification-only -->`).
- When both conditions hold, the gate AUTO-TICKS the matching `- [ ]` verification rows to `- [x]` in PHASES.md (the same byte-stable, in-place rewrite the existing phase-Status auto-flip at `lazy_core.py:3061` already performs), then mints the receipt. PHASES.md ends fully coherent, so the downstream `check-docs-consistency.ts` (which counts every checkbox with no carve-out) is satisfied with NO sibling-repo edit.
- Evidence — not the checkbox — is the source of truth. A feature with a genuine unchecked *implementation* row (non-verification) still refuses, naming the offending phase. The gate's job is preserved; only the redundant re-demand for already-certified verification rows is removed.

The change unifies all three gates on ONE evidence-gated rule, removes the coherence-recovery meta-cycle, and is reversible (a guarded exemption, easy to tighten).

**Direction B (rejected) — keep the gate strict; make `/mcp-test` tick the rows.** Considered and rejected: it re-introduces the producer/marker-drift class `harness-hardening-retro-fixes` was fighting (a producer ticking the wrong rows, or missing rows authored by `/blocked-resolution`) and spreads the contract across more files than Direction A.

### Research-derived implementation contract (Phase 3 — RESEARCH.md integrated)

The Gemini deep-research pass (`RESEARCH.md`, summarized in `RESEARCH_SUMMARY.md`) **confirmed Direction A** and converted Open Questions 3–5 into the locked contract below. The research frame: the completion gate is an *artifact-normalization* step — it rewrites the human-readable plan to match verifiable on-disk evidence, shielding the naive downstream `check-docs-consistency.ts` (a Verification Summary Attestation / VSA model from SLSA / in-toto prior art). The exemption MUST be governed by the following evidence rules, NOT a blanket relaxation.

**Authoritative-evidence decision table (resolves Open Question 3).** The gate evaluates the *union* of `VALIDATED.md` (attestation envelope) and `MCP_TEST_RESULTS.md` (raw execution provenance) — neither file in isolation is sufficient:

| `VALIDATED.md` | `MCP_TEST_RESULTS.md` | `validated_commit` | Gate action | Rationale |
|----------------|-----------------------|--------------------|-------------|-----------|
| present (`kind: validated`) | present (`all-passing`, `pass==total`, `pass>0`) | `== HEAD` | **Exempt-and-tick** | VSA + provenance match, commit fresh |
| present | missing / malformed | `== HEAD` | **Refuse** | forged-attestation risk (receipt without proof) |
| missing | present | n/a | **Refuse** | policy/VSA layer never ran |
| present | present | `!= HEAD` — source/script/config delta | **Refuse-and-revalidate** | TOCTOU: validated code is not the code being promoted |
| present | present | `!= HEAD` — **docs-only** delta (`*.md`) | **Warn + exempt-and-tick** | only non-executable files changed; safe |
| `SKIP_MCP_TEST.md` | missing | `== HEAD` | **Refuse** (do NOT tick) | skip ≡ absent evidence; fail-closed unless operator override |
| `DEFERRED_*` | missing | `== HEAD` | **Refuse** (do NOT tick) | deliverables physically incomplete |
| neither | neither | n/a | **Refuse** | no evidence of verification execution |

Edge-rule details:
- **`pass>0` is mandatory** — `pass==total==0` is a known CI false-positive anti-pattern (a suite that passes zero tests). Reject it.
- **SKIP / DEFERRED fail closed** (resolves Open Question 3 skip/deferred sub-case) — the auto-tick exemption is refused for `SKIP_MCP_TEST.md` / `DEFERRED_*` unless an explicit operator-override marker is present. Because the downstream checker counts every box, the only sound paths are: run the test, or have the agent excise the deliverables from the plan.
- **HEAD-drift carve-out** — when `validated_commit != HEAD`, inspect the git diff: docs-only (`*.md`) → warn-and-proceed; any source/script/config file → refuse-and-revalidate.

**Auto-tick rewrite contract (resolves Open Question 4 + hardens Decision 2 = A).** When the table yields *exempt-and-tick*, the gate rewrites the matching verification rows and mints the receipt. The rewrite MUST be:
- **Atomic** — write-to-temp-in-same-dir → `flush()` + `os.fsync()` → `os.replace()`; never `open('r+')` / naive truncating write (mirrors the existing phase-Status auto-flip's safety posture).
- **Line-anchored + code-fence-safe** — match `^\s*-\s+\[\s+\]` with the `<!-- verification-only -->` marker required on the SAME line; skip lines inside ``` fences. NO global `.replace('- [ ]','- [x]')`.
- **Auditable** — append a byte-stable `<!-- auto-ticked: validated_commit=<sha> -->` comment to each rewritten row, and record the count of auto-ticked rows in `COMPLETED.md`, so a later auditor distinguishes gate mutations from agent/human edits.
- **Cardinality-locked (over-relaxation guard)** — assert `auto_tick_count <= pass_count` (from `MCP_TEST_RESULTS.md`); refuse if more rows are slated for ticking than tests passed (catches marker-drift hallucination / forged evidence).
- **Superseded-aware** — prune (or otherwise satisfy) unchecked boxes under phases marked `Superseded` so the downstream checker does not flag them.

**Downstream checker (resolves Open Question 4).** No `check-docs-consistency.ts` edit is needed: research's final verdict is that an exhaustive auto-tick normalization pass is fully sufficient for the naive count-everything checker, since it evaluates physical `- [x]` state, not semantic intent. This confirms the Decision 2 = A assumption.

**Lint + gate, not lint-or-gate (resolves Open Question 5).** Both layers are required ("Swiss Cheese" defense). Evidence-gating alone is unsafe — a hallucinating agent could attach `<!-- verification-only -->` to a real implementation deliverable, and the gate would auto-tick unwritten code (the cardinality lock above is the gate-side mitigation). Authoring-time lint enforcing the marker only on test-shaped rows is the complementary layer; the MID-feature lint side is partly addressed upstream by `harness-hardening-retro-fixes`. **This feature owns the completion-gate evidence side.**

**Kill-switch (research §8 — reversibility hardening).** Gate the entire relaxation behind an env flag (e.g. `LAZY_STRICT_EVIDENCE_GATE` / `LAZY_DISABLE_AUTOTICK`): when set, fall back to the legacy strict `_phase_completion_plan` and skip the mutation entirely — frictionless rollback without a code revert.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Validated feature with un-ticked verification rows completes without a recovery cycle | `__mark_complete__` with `VALIDATED.md` on disk + only verification rows unchecked | receipt minted (`COMPLETED.md`), Status → Complete, no refusal | `lazy-state.py --test` fixture; `lazy_core.py` smoke harness |
| Feature with REAL unchecked implementation rows still refuses | `__mark_complete__` with a non-verification `- [ ]` row | refusal naming the offending phase, zero writes | `lazy_core.py` smoke harness |
| Auto-ticked verification rows leave PHASES.md coherent for the downstream checker | post-completion | every checkbox ticked OR phase Superseded | parse PHASES.md; (manually) `check-docs-consistency.ts` clean |
| `verify_ledger` and `_phase_completion_plan` agree on the same input | `--verify-ledger` then `__mark_complete__` on the same feature | both pass, or both name the same blocking phase | both `--test` suites green |
| Missing `MCP_TEST_RESULTS.md` (only `VALIDATED.md`) refuses | `__mark_complete__` with `VALIDATED.md` but no/ malformed results | refusal (forged-attestation risk), no auto-tick | `lazy_core.py` smoke harness |
| Zero-test evidence (`pass==total==0`) refuses | `__mark_complete__` with `all-passing` but `total==0` | refusal (`pass>0` required) | `lazy_core.py` smoke harness |
| `SKIP_MCP_TEST.md` / `DEFERRED_*` fails closed | `__mark_complete__` with a skip/deferral receipt | refusal, rows NOT ticked | `lazy_core.py` smoke harness |
| HEAD-drift on source files refuses; docs-only drift proceeds | `validated_commit != HEAD` with (a) a `.py`/script delta vs (b) `*.md`-only delta | (a) refuse-and-revalidate; (b) warn + exempt-and-tick | `lazy_core.py` smoke harness w/ git fixture |
| Cardinality lock blocks over-tick | `__mark_complete__` where `auto_tick_count > pass_count` | refusal (marker-drift / forged-evidence guard) | `lazy_core.py` smoke harness |
| Auto-tick is atomic + audited | exempt-and-tick path | temp-file + `os.replace`; each rewritten row carries `<!-- auto-ticked: validated_commit=<sha> -->`; count logged in `COMPLETED.md` | parse PHASES.md + COMPLETED.md |
| Kill-switch restores legacy strict behavior | `LAZY_STRICT_EVIDENCE_GATE` set, un-ticked verification rows | legacy refusal, zero PHASES.md mutation | `lazy_core.py` smoke harness w/ env override |

## Open Questions (for `/spec` research + NEEDS_INPUT to resolve)

1. **Reconciliation direction (A vs B above)** — ✅ RESOLVED (operator, 2026-06-19): **A — extend the carve-out to completion time, gated on on-disk evidence.** `_phase_completion_plan` applies the verification-only exemption only when `/mcp-test` evidence certifies passing AND all remaining unchecked rows are verification-marked. Single-repo, reversible change in `lazy_core.py` + smoke tests. See Technical Design (LOCKED).
2. **On-disk evidence as override vs satisfier** — ✅ RESOLVED (completeness-policy D7, 2026-06-19): **A — auto-tick the certified verification rows.** When evidence certifies passing, the gate rewrites the matching `- [ ]` verification rows to `- [x]` (same byte-stable in-place rewrite as the phase-Status auto-flip), leaving PHASES.md coherent for the downstream `check-docs-consistency.ts` with no sibling-repo edit. Conditional on Decision 1 = A (chosen). See Technical Design (LOCKED).
3. **Which evidence is authoritative** — ✅ RESOLVED (research, 2026-06-19): require the **union** of `VALIDATED.md` (attestation envelope) AND `MCP_TEST_RESULTS.md` (raw provenance: `all-passing`, `pass==total`, `pass>0`), with `validated_commit == HEAD`. Neither file alone suffices. `SKIP_MCP_TEST.md` / `DEFERRED_*` **fail closed** (refuse, do not tick). HEAD-drift on docs-only files warns-and-proceeds; on source/script/config files refuses-and-revalidates (TOCTOU). See the authoritative-evidence decision table in Technical Design.
4. **check-docs-consistency.ts reconciliation** — ✅ RESOLVED (research, 2026-06-19): **no sibling-repo edit needed.** Auto-ticking is fully sufficient for the naive count-everything checker (it evaluates physical `- [x]` state, not semantic intent), *provided the normalization pass is exhaustive* (covers Superseded phases + variable-whitespace checkboxes). Confirms the Decision 2 = A assumption.
5. **Lint enforcement vs gate relaxation** — ✅ RESOLVED (research, 2026-06-19): **both** ("Swiss Cheese" defense). Evidence-gate alone is unsafe (a hallucinated marker on an implementation row would auto-tick unwritten code — mitigated gate-side by the cardinality lock); lint alone leaves the friction. This feature owns the completion-gate evidence side; the MID-feature lint side is partly upstream in `harness-hardening-retro-fixes`. See Technical Design.

## Research References

- **`RESEARCH.md`** — Gemini deep-research report: "Reconciling Redundant Completion Gates in Autonomous AI Pipelines." Frames the fix as CI/CD artifact-normalization governed by a Verification Summary Attestation (VSA) model (SLSA / in-toto prior art). Sources the authoritative-evidence decision table, the atomic-write contract, the cardinality lock, and the kill-switch.
- **`RESEARCH_SUMMARY.md`** — condensed analysis: confirms Direction A; resolves Open Questions 3–5; lists the implementation contracts `/spec-phases` + `/write-plan` must carry into phases.
- **`NEEDS_INPUT_RESOLVED_2026-06-19.md`** — operator resolution of Decisions 1–2 (Direction A; auto-tick).
- Upstream reality-check sources (Phase 1): `harness-hardening-retro-fixes/PHASES.md` Phase 2 (verification-only marker contract), `lazy_core.py` (`_phase_completion_plan` @ ~1824, `verify_ledger` @ ~2017, `remaining_unchecked_are_verification_only` @ ~1419, `__mark_complete__` call site @ ~3097), `user/scripts/CLAUDE.md` (verification-only canonical marker section).

**Key findings that shaped the design:**
- Require BOTH evidence files (VSA envelope + raw provenance); `pass>0`; `validated_commit == HEAD` with a docs-only-diff carve-out for TOCTOU.
- SKIP / DEFERRED fail closed — no auto-tick without passing evidence or an operator override.
- Auto-tick alone satisfies the uneditable downstream `check-docs-consistency.ts` (no sibling-repo edit) — given an exhaustive normalization pass.
- Atomic write (`os.replace`), line-anchored + code-fence-safe regex, audit-trail comment, cardinality lock, and an env-var kill-switch are mandatory safety mechanisms.

> **Research integrated (2026-06-19) — Phase 3 finalization complete.** The gating product/ownership decisions (Open Questions 1–2, operator-resolved via `NEEDS_INPUT_RESOLVED_2026-06-19.md`) and the research-answerable edge cases (Open Questions 3–5, resolved from `RESEARCH.md`) are now fully baked into Technical Design (LOCKED) → "Research-derived implementation contract." Direction A, evidence-gated, with atomic + audited auto-ticking of certified verification rows, a cardinality over-relaxation guard, and a kill-switch. `lazy_core.py` line references are spec-level anchors verified on 2026-06-19; minor drift from the live file is expected and resolved by symbol name during implementation. Ready for `/spec-phases`.
