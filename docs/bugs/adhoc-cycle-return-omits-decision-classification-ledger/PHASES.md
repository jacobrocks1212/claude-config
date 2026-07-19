# Implementation Phases — Cycle-subagent return omits Decision-Classification Ledger

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness skill/component prose edits only; no MCP-reachable surface (docs/config-only class per `docs/features/mcp-testing/SPEC.md` — not app behavior, stores, audio, UI, or events). Verification is deterministic (grep + `lint-skills.py` + `lazy_parity_audit.py`).

## Validated Assumptions

- **Code-provable, no runtime check needed.** This defect is a static contract omission, not runtime-coupled: the SPEC's root cause is `traced` in the serving prose (`cycle-base-prompt.md` item 4 REPORT → the subagent's return shape), and the fix is deterministic prose edits. No user-facing surface exists, so the reachability axiom does not apply. Gate skipped for cause: every load-bearing assumption is code-provable (skill-doc text + greppable presence checks).
- **Touchpoint audit (verified inline, dispatch unwarranted for a mechanical doc change):**
  - `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — exists; item 4 "REPORT" lives at L575–585 (workstation `@section hard-contract`) and L621–631 (cloud `@section hard-contract`); grep for `Ledger|classification` over the file returns zero return-contract matches. Action: refactor (add the ledger requirement to both item-4 blocks).
  - `user/skills/spec-bug/SKILL.md` — exists; 0 `ledger|classification` matches. Action: refactor (add the ledger return mandate).
  - `user/skills/plan-bug/SKILL.md` — exists; 0 `ledger|classification` matches. Action: refactor (add the ledger return mandate).
  - Reference (reuse-source, NOT modified): `user/skills/spec/SKILL.md:117-135` and `user/skills/plan-feature/SKILL.md:114-126` carry the canonical `### Decision-Classification Ledger` mandate + table shape to mirror.
- **Anchor-grade drift corrected in-plan (mechanical, silent):** the SPEC cites the cloud REPORT block at `cycle-base-prompt.md:588+`; the live cloud item-4 REPORT is at L621–631 (L588 is the cloud hard-contract heading). Phase 1 targets L621–631 for the cloud edit. No premise-grade contradiction.

## Notes on scope (⚖ completeness)

⚖ policy: fix authoritative site + close bug-axis gap → most complete deterministic path

- SPEC Recommended Fix Scope item 1 (authoritative return contract) → **Phase 1** — the load-bearing, deterministic fix; it closes the silent-drop path for the feature pipeline too (why `plan-feature`, which already has the mandate, still dropped the ledger).
- SPEC Recommended Fix Scope item 2 (bug-axis mandate gap) → **Phase 2** — defense-in-depth so `spec-bug`/`plan-bug` skill bodies match the feature axis.
- SPEC Recommended Fix Scope item 3 ("optional hardening — make the miss checkable") is **out of scope by SPEC conclusion**: the SPEC states a cross-subagent re-request is NOT feasible post-return, and the loud skill-name attribution of the diff-only fallback is already present at `lazy-batch/SKILL.md:976`. The deterministic win the SPEC itself identifies is item 1 (Phase 1). No product-behavior differs by excluding it; excluded with disclosure.

---

### Phase 1: Add the ledger to the authoritative return contract (root fix)

**Scope:** Add the Decision-Classification Ledger as a required return element of `cycle-base-prompt.md` item 4 "REPORT" in BOTH `@section hard-contract` blocks (workstation, L575–585; cloud, L621–631), scoped to the decision-bearing cycles (`/spec`, `/spec-phases`, `/write-plan`, `/add-phase`, `/plan-feature`, `/spec-bug`, `/plan-bug`). The requirement mirrors how the NEEDS_INPUT disposition is already mandated in the same item: the return summary MUST carry a `### Decision-Classification Ledger` section (or the explicit empty-ledger line `_(no decisions surfaced this cycle — auto-finalized)_`) on those cycles. This is the load-bearing fix — the base return contract, not the skill body, is authoritative for the batch return shape.

**Deliverables:**
- [ ] `cycle-base-prompt.md` item 4 REPORT (workstation `@section hard-contract`, ~L575–585): append a sentence requiring the `### Decision-Classification Ledger` section on decision-bearing cycles (naming the seven skills), with the empty-ledger fallback line; keep it consistent with the existing NEEDS_INPUT-disposition mandate directly above it.
- [ ] `cycle-base-prompt.md` item 4 REPORT (cloud `@section hard-contract`, ~L621–631): the identical requirement mirrored into the cloud block (the cloud block already lists `/retro` in its NEEDS_INPUT skill set — keep the cloud's own skill enumeration convention).
- [ ] Re-project + lint: run `python ~/.claude/scripts/project-skills.py` then `python ~/.claude/scripts/lint-skills.py` — both clean (the component expands into the projected cycle prompts without a broken `!cat`/embedded-pattern finding).

**Minimum Verifiable Behavior:** `grep -c "Decision-Classification Ledger" user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` returns ≥ 2 (one per hard-contract block), where before it returned 0 for the return-contract sections.

**Runtime Verification** *(checked by manual/deterministic verification — NOT by the implementation agent):*
- [ ] <!-- verification-only --> A dispatched decision-bearing cycle subagent (`/spec`, `/plan-feature`, `/spec-bug`, or `/plan-bug`) under `--batch`, following the assembled cycle prompt, includes the `### Decision-Classification Ledger` section in its return summary (or the empty-ledger line), so the Step 1d.5 input-audit runs the stronger diff-vs-ledger cross-check (algorithm step 3a/3b) instead of the diff-only fallback (step 3c). (Observable only across a live `/lazy-batch(-bug)` run; the deterministic proxy is the MVB grep above.)

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP; this is harness prose whose effect manifests in a `/lazy-batch` cycle's return summary, not through an MCP surface.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md` — add the ledger-return requirement to item 4 REPORT in both `@section hard-contract` blocks.

**Testing Strategy:** Deterministic presence check — grep confirms the ledger requirement now appears in both hard-contract item-4 blocks; `project-skills.py` + `lint-skills.py` confirm the component still resolves cleanly into every consuming projected skill.

**Integration Notes for Next Phase:**
- The authoritative return shape now mandates the ledger; Phase 2 adds the *skill-body* mandate for the bug axis so the mandate exists at both layers (base contract + skill body), exactly as it already does on the feature axis (`spec`/`plan-feature` bodies + the now-fixed base contract).
- Use the seven-skill enumeration established here as the canonical "decision-bearing cycles" list Phase 2's spec-bug/plan-bug mandates reference.

---

### Phase 2: Close the bug-axis skill-body mandate gap

**Scope:** Add the Decision-Classification Ledger return mandate to `spec-bug/SKILL.md` and `plan-bug/SKILL.md`, mirroring the feature-axis mandates (`spec/SKILL.md:117-135` and `plan-feature/SKILL.md:114-126`) so the bug pipeline's own skill bodies match the feature pipeline. This is defense-in-depth beneath Phase 1's authoritative fix, and it satisfies the bug-axis parity contract (`spec-bug`↔`spec`, `plan-bug`↔`plan-feature`) that `lazy_parity_audit.py` enforces.

**Deliverables:**
- [ ] `user/skills/spec-bug/SKILL.md`: add a "Decision-Classification Ledger (MANDATORY return under `--batch`)" block mirroring `spec/SKILL.md:117-135` — same `### Decision-Classification Ledger` table shape (`# | Decision | Classification | Chosen option | Surfaced via | Rationale`), the product-behavior⇒`NEEDS_INPUT.md` rule, the empty-ledger fallback line, and the "ledger lives in the return summary, not a committed doc" note. Adapt vocabulary to the bug axis (investigation decisions / root-cause-scope calls; `NEEDS_INPUT.md` sentinel).
- [ ] `user/skills/plan-bug/SKILL.md`: add the analogous mandate mirroring `plan-feature/SKILL.md:114-126` ("same contract as `/spec --batch`"), covering the decisions a bug planning cycle considers (phase boundaries, partition cuts, helper/anchor choices).
- [ ] Bug-axis parity: run `python3 user/scripts/lazy_parity_audit.py --repo-root .` and confirm exit 0 (the coupled-pair obligation the SPEC flags — `spec-bug`↔`spec`, `plan-bug`↔`plan-feature`). If the audit's manifest requires the new heading to be registered as a mirrored/diverged block, update `user/scripts/lazy-parity-manifest.json` accordingly so the audit stays green.
- [ ] Re-project + lint: `python ~/.claude/scripts/project-skills.py` then `python ~/.claude/scripts/lint-skills.py` — both clean.

**Minimum Verifiable Behavior:** `grep -l "Decision-Classification Ledger" user/skills/spec-bug/SKILL.md user/skills/plan-bug/SKILL.md` lists BOTH files (was neither), and `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0.

**Runtime Verification** *(checked by deterministic verification — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `lazy_parity_audit.py --repo-root .` exits 0 after the edits (bug-axis parity intact); `lint-skills.py` reports no new findings.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior via MCP; skill-body prose plus a deterministic parity/lint gate.

**Prerequisites:**
- Phase 1: the canonical "decision-bearing cycles" enumeration and the ledger table shape are established/confirmed at the authoritative contract; Phase 2 references them for the bug-axis skill bodies. (Phases touch disjoint files — Phase 1 edits the component, Phase 2 edits the two bug skills — so they are independently landable, but Phase 2 authors its mandate to match Phase 1's wording.)

**Files likely modified:**
- `user/skills/spec-bug/SKILL.md` — add the ledger return mandate (mirror `spec/SKILL.md:117-135`).
- `user/skills/plan-bug/SKILL.md` — add the ledger return mandate (mirror `plan-feature/SKILL.md:114-126`).
- `user/scripts/lazy-parity-manifest.json` — only if the parity audit requires registering the new heading as a mirrored/diverged block (verify with the audit, do not pre-edit).

**Testing Strategy:** Deterministic — grep confirms both bug skills now carry the mandate; `lazy_parity_audit.py` exit 0 confirms the bug-axis mirrors stay in sync; `project-skills.py` + `lint-skills.py` confirm no broken injections.

**Integration Notes for Next Phase:** None — final phase. When the last phase's work lands, set the top-level PHASES `**Status:**` to `In-progress` (implementation done, validation pending); the state machine routes to the validation tail.
