# Implementation Phases — Recovery / LOOP-DETECTED paths can self-certify verification rows without on-disk evidence

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Open
<!-- Implementation not yet started. When the (single) phase's work lands, this moves to In-progress (implementation done, validation pending). The flip to Fixed + the FIXED.md receipt are owned EXCLUSIVELY by the orchestrator's __mark_fixed__ validation-tail gate — never set here. -->


**MCP runtime:** not-required — harness docs-consistency defect; the fix is a single static `pytest` assertion over the on-disk text of a `_components/` markdown file. Verified entirely by `python -m pytest user/scripts/test_project_skills.py`. No AlgoBooth app surface, no Tauri/MCP-reachable behavior (per docs/features/mcp-testing/SPEC.md: pure script/test tooling is outside MCP reach).

## Provenance

This bug's investigation **concluded that both evidence side-doors are already closed** (SPEC `## Proven Findings` 1–2):

- **Recovery path** (symptoms 1/2/4): `dispatch-recovery.md` carries the GREP-AND-CITE GATE landed by `3f6253f` (governed by `lazy-cycle-containment` §C5), pinned by TWO existing tests in `user/scripts/test_project_skills.py` — `test_dispatch_recovery_component_carries_grep_and_cite_gate` (on-disk) and `test_recovery_emit_carries_grep_and_cite_gate_every_variant` (assembled-prompt, all variants).
- **Loop path** (symptom 3): `loop-block.md` carries the receipt-authoring ban landed by `dfbcfa0` — the loop-breaker may author ONLY `NEEDS_INPUT.md` / `BLOCKED.md`; `VALIDATED.md` / `SKIP_MCP_TEST.md` / `COMPLETED.md` / `FIXED.md` are named-and-banned.

**Residual gap = asymmetric coverage** (SPEC `## Proven Findings` 3, `## Fix Scope`): the recovery gate has two pinning tests, but the **loop-block receipt-authoring ban has NO pinning test**. A future edit to `loop-block.md` could silently drop the receipt ban without any test failing. The entire fix is to add a single static docs-consistency regression test asserting the loop-block ban text is on disk, **mirroring the existing `test_dispatch_recovery_component_carries_grep_and_cite_gate` pattern** — so both evidence side-doors are regression-pinned symmetrically.

**Out of scope** (SPEC `## Fix Scope`): re-writing the recovery / loop / verify-ledger prose (already correct), and any runtime-enforcement hook. The prose-level grep-and-cite + receipt ban, plus the script-as-sole-author of receipts in `apply_pseudo`, are the agreed enforcement layer (see `lazy-cycle-containment` §C5).

**Scope-class decision taken in-cycle (D7 completeness-first):**
- ⚖ policy: test mechanism (static grep vs. assembled-emit) → static on-disk docs-consistency assertion. The SPEC `## Open Questions` settles this as mechanical-internal: mirror the existing on-disk recovery-gate test (`test_dispatch_recovery_component_carries_grep_and_cite_gate`). The loop-block is appended verbatim to the cycle prompt by `emit_cycle_prompt` (no per-variant transformation, unlike the recovery emit), so an on-disk assertion fully covers the seam; no assembled-emit variant test is warranted.

---

### Phase 1: Pin the loop-block receipt-authoring ban with a static regression test

**Scope:** Add a single static (`pytest`) docs-consistency test asserting `loop-block.md` carries the receipt-authoring ban on disk — symmetric with the existing recovery-gate pinning test. Co-locate it with the recovery-gate tests in `user/scripts/test_project_skills.py`. No production source / prose changes — the contract under test already exists on disk (`dfbcfa0`); this phase only prevents it from silently regressing.

**Deliverables:**
- [ ] `user/scripts/test_project_skills.py`: add a module-level path constant `_LOOP_BLOCK_PATH` resolving to `user/skills/_components/lazy-batch-prompts/loop-block.md` (mirroring `_DISPATCH_RECOVERY_PATH`'s `Path(__file__).resolve().parents[1] / "skills" / "_components" / "lazy-batch-prompts" / "loop-block.md"` form).
- [ ] `user/scripts/test_project_skills.py`: add a module-level marker tuple `_LOOP_BLOCK_RECEIPT_BAN_MARKERS` enumerating the stable substrings that prove the receipt ban is on disk: the four named-and-banned receipts (`VALIDATED.md`, `SKIP_MCP_TEST.md`, `COMPLETED.md`, `FIXED.md`) AND the two permitted-only sentinels (`NEEDS_INPUT.md`, `BLOCKED.md`). (Mirror `_RECOVERY_GATE_MARKERS`.)
- [ ] `user/scripts/test_project_skills.py`: add `test_loop_block_component_carries_receipt_authoring_ban()` — read `_LOOP_BLOCK_PATH` text and assert every marker in `_LOOP_BLOCK_RECEIPT_BAN_MARKERS` is present, with a descriptive failure message naming the missing marker (mirror `test_dispatch_recovery_component_carries_grep_and_cite_gate`).
- [ ] Confirm the new test is **test-first RED-then-GREEN against the contract**: it must FAIL if the ban text is removed from `loop-block.md` (demonstrate by transiently checking the assertion logic; do NOT commit a broken `loop-block.md`) and PASS against the current on-disk `loop-block.md`.
- [ ] Run `python -m pytest user/scripts/test_project_skills.py` (or `python user/scripts/test_project_skills.py` if run directly) — the full file passes, including the new test.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_project_skills.py::test_loop_block_component_carries_receipt_authoring_ban` passes against the current tree, and would fail if any of the four banned-receipt names or the loop-breaker's permitted-only sentinel names were dropped from `loop-block.md`.

**Prerequisites:** None (first and only phase). The contract under test already exists on disk (`dfbcfa0`).

**Files likely modified:**
- `user/scripts/test_project_skills.py` — new path constant + marker tuple + `test_loop_block_component_carries_receipt_authoring_ban` (co-located with the recovery-gate tests at ~`:657`).

**Testing Strategy:** Pure static on-disk assertion — read the component file, assert the stable ban substrings are present. No subprocess, no fixture, no marker-machine interaction. The RED proof is structural (the assertion fails when a marker is absent), mirroring the existing recovery-gate test's contract. This is the same test mechanism the SPEC `## Open Questions` settled on.

**Integration Notes for Next Phase:** Terminal phase. When this work lands, the top-level PHASES `**Status:**` moves to `In-progress` (implementation done, validation pending) — the `__mark_fixed__` flip to `Fixed` is owned exclusively by the orchestrator's validation-tail gate, never set here. With this test in place, both evidence side-doors (recovery grep-and-cite + loop-block receipt ban) are regression-pinned symmetrically, closing the SPEC's residual gap.
