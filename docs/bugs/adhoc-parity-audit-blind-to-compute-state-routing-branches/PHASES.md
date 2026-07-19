# Implementation Phases — Parity audit blind to compute_state routing-branch asymmetry

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a pure-Python/docs harness repo with no Tauri/dev runtime and no MCP server; `lazy_parity_audit.py` is a stdlib static checker whose entire validation surface is its own pytest suite (`test_lazy_parity.py`) + the whole-repo audit exit code. This is the build-tooling / standalone-checker class in `docs/features/mcp-testing/SPEC.md` (structurally outside MCP reach).

## Runtime Assumption Validation — gate SKIPPED (recorded reason)

Every load-bearing assumption here is **code-provable**, so the Step-2.7 runtime gate is skipped per its own skip rule:

- The fix is a **pure static checker** over two `.py` files' source text — no runtime coupling (the SPEC's root cause is labeled `traced` precisely because "the audit is a pure static checker; no runtime coupling", SPEC line 128).
- **No user-facing surface** → the reachability axiom does not apply (the audit is a developer/CI CLI tool, not an app surface).
- **SPEC-example capability audit:** N/A — the SPEC carries reproduction steps, not code examples consuming an API surface; the fix uses only stdlib (`re`, `pathlib`, `json`, optionally `ast`), all present.
- **MCP tool-existence audit:** no-op — claude-config declares no `.claude/skill-config/mcp-tool-catalog.md`.
- **Data-reach audit:** N/A — no entity/data retention/deletion/migration.
- **Module-move inbound-seam audit:** N/A — no module is moved/renamed/deleted; the only net-new file is a standalone allowlist with zero inbound literal-path loaders.

Verification is therefore the pytest fixtures + the live whole-repo audit exit code, both driven at implementation time (no deferred Step-9 MCP gate exists in this repo).

## Design decision resolved in-plan (D7 — scope-class, not a product fork)

**⚖ policy: census mechanism (SPEC Open Question 1, fix-shape) → declared routing-branch allowlist + structural-token census.**

The SPEC's Open Question 1 (AST-based branch extraction vs. declared routing-predicate manifest vs. structural-token census) is **scope-class**, not product-class: the SPEC states all three "achieve the same product behavior (unmirrored branch → finding); they differ in false-negative surface and maintenance cost" (SPEC lines 148–151). Product behavior is identical, so per D7 the most-complete *maintainable* path is taken in-cycle:

- **Chosen:** a committed **declared allowlist** enumerating each coupled `compute_state` routing branch, each classified `mirrored` (a structural signature that MUST appear in both scripts) or `tabulated-divergence` (present in one script only, with a required `reason`), consumed by a **structural-token census** in `lazy_parity_audit.py`.
- **Why over AST extraction:** AST-parsing two `compute_state` functions of 1,239 / 2,144 lines (per `benchmark_lazy_core_import.py --function-sizes`, 2026-07-13 baseline) to diff branch predicates is fragile (re-breaks on every refactor) and high-maintenance for zero product-behavior gain.
- **Why over an implicit manifest:** an explicit allowlist makes the 11+ documented justified divergences (SPEC lines 92–96) *reviewable in one place* and divergence-aware **by construction** — the SPEC's core design constraint.
- **Architecture fit:** matches the existing `audit_state_script_parity` / `audit_merged_view_dispatch_parity` predicate-list-per-target loop shape exactly — the new check is a sibling, not a new engine.

**Open Question 2 (Round 92 research-pending exclusion — mirror-owed vs. correct-divergence)** is *not* a product fork — it is a factual allowlist entry the implementer determines by reading the code, scheduled as a Phase-1 deliverable (the allowlist must be seeded so the current tree passes green, which forces every real divergence to be classified). No NEEDS_INPUT is owed.

---

### Phase 1: Routing-branch symmetry census + tabulated-divergence allowlist

**Scope:** Add a `compute_state` routing-branch symmetry check to `lazy_parity_audit.py`, backed by a committed declared allowlist that classifies every coupled routing branch as `mirrored` or `tabulated-divergence`. Seed the allowlist so the *current* tree passes green (every real divergence tabulated with a reason), so that a *future* unmirrored routing branch fails the audit in the same commit that introduces it.

**Deliverables:**
- [ ] New committed allowlist file (net-new — e.g. `user/scripts/compute-state-routing-parity.json`, sibling of `lazy-parity-manifest.json`) declaring each coupled `compute_state` routing branch: an id, a structural signature (token/regex the branch is recognized by, applied via the existing `apply_tokens` vocab-substitution where the two scripts legitimately differ on `--feature-id`/`--bug-id`-class vocab), a classification `mirrored | tabulated-divergence`, and a required `reason` for every `tabulated-divergence` row.
- [ ] `audit_compute_state_routing_parity(repo_root)` in `lazy_parity_audit.py`, structured exactly like `audit_merged_view_dispatch_parity` (L548): load the allowlist, read both `_STATE_SCRIPTS` (L304), and for each `mirrored` branch assert its structural signature is present in BOTH scripts' `compute_state`; emit one finding per (script, missing mirrored-branch). A `tabulated-divergence` row is asserted present in its declared owning script only. A malformed/missing allowlist is a loud finding (mirrors the `except OSError` ERROR rows), never a silent pass.
- [ ] Wire `audit_compute_state_routing_parity` into `audit_all_pairs` (L590) after the merged-view call (L617), so it runs in the default whole-repo `--repo-root .` invocation.
- [ ] Classify every existing coupled `compute_state` routing branch into the allowlist — including (a) the Round 93 Step-7 verification-only bypass (`cloud_bypass`/`workstation_bypass` conjuncts, bug-state.py ~L1729 ↔ lazy-state.py `_feature_past_implementation` L1747) as `mirrored`, and (b) the Round 92 research-pending exclusion, classified `mirrored` or `tabulated-divergence` per its code-read determination (Open Question 2) — such that the live tree audit stays exit 0.
- [ ] Tests in `test_lazy_parity.py`: a new `TestComputeStateRoutingParity` class mirroring `TestStateScriptParity` (L623) — (i) FIRES when a `mirrored` branch's signature is absent from one script (unmirrored-branch fixture), (ii) PASSES when a `tabulated-divergence` row is present in only its owning script, (iii) a `TestLiveZeroDrift`-style live-tree test asserting the real repo passes, (iv) the check is included in `audit_all_pairs` output.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0 on the current (correctly-mirrored) tree AND `python3 -m pytest user/scripts/test_lazy_parity.py -q` passes; then, with a temporary local edit deleting one `mirrored` branch's tokens from `bug-state.py`, the audit exits 1 naming that branch (revert the edit after). Both are runnable commands, not "unit tests pass".

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/compute-state-routing-parity.json` — net-new (create): the declared allowlist.
- `user/scripts/lazy_parity_audit.py` — add `audit_compute_state_routing_parity()`; wire it into `audit_all_pairs` after the L617 merged-view call. Reuse `_STATE_SCRIPTS` (L304) and `apply_tokens` (L51).
- `user/scripts/test_lazy_parity.py` — add `TestComputeStateRoutingParity` (fires / tabulated-passes / live-clean / included-in-all-pairs).

**Testing Strategy:** Pure hermetic pytest fixtures (the existing `_make_pair` / `tmp_path` pattern for the fires-and-passes cases; a `TestLiveZeroDrift`-style real-tree assertion for green-baseline). No runtime, no MCP — the checker is stdlib static analysis over two source files.

**Integration Notes for Next Phase:**
- The allowlist file path chosen here is the "allowlist location" Phase 2 documents — keep them in sync.
- Record in the allowlist header / a module comment that the census is **divergence-aware by construction**: adding a NEW justified divergence means adding a `tabulated-divergence` row (with a reason), exactly as the SKILL-pair manifest tabulates its divergences.
- Note whether the Round 92 branch resolved to `mirrored` or `tabulated-divergence` (Open Question 2 outcome) so Phase 2's doc text states it correctly.

---

### Phase 2: Document the new coverage + allowlist location

**Scope:** Document that `lazy_parity_audit.py` now covers `compute_state` routing-branch symmetry (not just named CLI/call-site literals), and where the tabulated-divergence allowlist lives, so a future contributor changing a shared routing branch knows the audit will catch an unmirrored change and knows how to tabulate a genuine divergence.

**Deliverables:**
- [ ] Update `user/scripts/CLAUDE.md` → "Coupling Rule (HARD REQUIREMENT)" (and/or the `lazy_parity_audit.py` CLI quick-reference block): state that the parity audit now asserts `compute_state` routing-branch symmetry via the declared allowlist, name the allowlist file, and explain the `mirrored` vs. `tabulated-divergence` classification + the "add a row with a reason" workflow for a new justified divergence.
- [ ] Update the root `CLAUDE.md` where the parity audit / coupled-pairs contract is described, adding a one-line note that routing-branch symmetry is now mechanically enforced (highest-churn coupled surface, per SPEC lines 88–91).
- [ ] Confirm `doc-drift-lint.py --repo-root .` stays exit 0 after the doc edits (the doc-drift linter cross-checks the script/coupled-pair tables).

**Minimum Verifiable Behavior:** `python3 user/scripts/doc-drift-lint.py --repo-root .` exits 0 after the edits, and the new allowlist file name appears verbatim in `user/scripts/CLAUDE.md`.

**Prerequisites:**
- Phase 1: the allowlist file must exist and its final path + the Round-92 classification outcome must be settled, since Phase 2 documents both.

**Files likely modified:**
- `user/scripts/CLAUDE.md` — Coupling Rule / CLI quick-reference: new coverage + allowlist location + divergence workflow.
- `CLAUDE.md` (repo root) — one-line note that routing-branch symmetry is now audited.

**Testing Strategy:** `doc-drift-lint.py --repo-root .` exit 0; a grep confirming the allowlist filename is documented. Docs-only phase — no code paths change.

**Integration Notes for Next Phase:** None — final phase. Implementation done → set the top-level `**Status:**` to `In-progress` (validation/completion is the orchestrator's `__mark_fixed__` gate, not this cycle).

---

## Cross-feature Integration Notes

No hard deps on Complete upstreams (this bug has no `**Depends on:**` block). The bug is self-contained within `lazy_parity_audit.py` + its allowlist + tests + docs; the two `compute_state` implementations are read-only audited inputs, unchanged by this fix.
