# Implementation Phases — plan-bug Step 0.4 lacks a guard for Fixed-annotated / already-implemented SPECs

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — the entire deliverable is Python state-script routing logic + skill/component prose in claude-config (the harness repo). It has no Tauri/app or MCP-reachable surface; the behavior is verified by the state scripts' own hermetic `--test` smoke harness + `pytest tests/test_lazy_core/`, which is the bug pipeline's structural verification path in this repo. This is the "structurally outside MCP reach" class per the mcp-testing SPEC (docs/pipeline tooling, not an app surface), NOT a waiver of runtime verification.

## Validated Assumptions

All load-bearing assumptions for this plan are **code-provable** (routing logic, string parsing, on-disk file presence) — none is runtime-coupled, so the Step 2.7 runtime-assumption gate is satisfiably skipped. Recorded skip reason + the assumptions verified during the touchpoint audit:

- **`has_completion_receipt` accepts a `filename=` param** — VERIFIED by read (`lazy_core/gates.py:2046`, `filename: str = "COMPLETED.md"`), so the no-`FIXED.md`-receipt check reuses it (`filename="FIXED.md"`) rather than writing a new receipt reader.
- **`spec_status()` reads ONLY the first `**Status:**` line and never `**Fixed:**`** — VERIFIED (`lazy_core/docmodel.py:418-421`). The new `**Fixed:**` reader mirrors its read+regex shape.
- **At `bug-state.py` Step 4, the item is non-archived by construction** — VERIFIED: `load_bug_queue` returns only open `docs/bugs/<slug>/` dirs; archived `_archive/` dirs are excluded. The `not-under-_archive` condition in the predicate is therefore defensively-redundant on this path (kept for helper self-containment), not load-bearing.
- **Reachability axiom:** this harness "feature" has no user-facing app surface; its serving surface is the pipeline's *routing decision*, exercised end-to-end by the `bug-state.py --test` in-file fixture (Phase 2) and the `lazy_core` unit tests (Phase 1). No app-reachability smoke applies.

## Touchpoint Audit (verified inline — dispatch not used for this small mechanical harness batch)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core/docmodel.py` | yes | `spec_status()` @403 (first `**Status:**` line) | refactor (add) | Add `spec_fixed_annotation(spec_path)` sibling reading the first `**Fixed:**` line — reuse `spec_status`'s exact read+`re.match` shape; do NOT re-open the file with a new reader |
| `user/scripts/lazy_core/gates.py` | yes | `has_completion_receipt(spec_path, filename="COMPLETED.md")` @2046 | reuse | Reuse `has_completion_receipt(spec_dir, filename="FIXED.md")` for the no-receipt half of the predicate; add `is_fixed_unreconciled()` + `format_fixed_unreconciled_blocker()` here (receipt/evidence logic already lives in this seam) |
| `user/scripts/lazy_core/depdag.py` | yes | `format_unknown_dependency_blocker()` @443 | reuse (model) | Model `format_fixed_unreconciled_blocker()`'s canonical `BLOCKED.md` body on this existing fail-fast formatter — same shape, new `blocker_kind: fixed-unreconciled` |
| `user/scripts/bug-state.py` | yes | `compute_state` Step 4 @1701-1714 (`phases_file` / `_status` / plan-bug route) | refactor | Insert the `is_fixed_unreconciled` pre-check BEFORE the `if _status == "Concluded": return … plan-bug`; on a hit write canonical `BLOCKED.md` (`lazy_core._atomic_write`) + return `terminal_reason: blocked` + a `_diag` breadcrumb |
| `user/scripts/compute-state-routing-parity.json` | yes | routing-parity allowlist | refactor | Add a `tabulated-divergence` row (owner + reason) for the bug-only Step-4 `fixed-unreconciled` pre-gate — the feature pipeline has no `**Fixed:**`-annotation / Concluded-intermediate analog |
| `user/skills/plan-bug/SKILL.md` | yes | Step 0.4 status gate @59-73 | refactor (prose) | Add a belt-and-suspenders sub-check to the status gate: on a `**Fixed:**`-annotated, no-receipt Concluded SPEC, REFUSE the planning round with the `fixed-unreconciled` outcome instead of proceeding to Step 1/2 |
| `user/scripts/tests/test_lazy_core/test_docmodel.py` + `test_gates.py` | yes | pytest modules | extend | Unit tests for `spec_fixed_annotation` / `is_fixed_unreconciled` / `format_fixed_unreconciled_blocker` |

No net-new files. No MCP tool catalog in claude-config (MCP tool-existence audit → no-op). No entity retention/deletion (data-reach audit → N/A). No module move/rename/delete (module-move inbound-seam audit → N/A).

## Design note — halt-for-reconciliation, NOT auto-reconcile (resolved by an existing Locked contract, no fork)

The one decision that *looks* product-class — should the pre-gate **HALT** for reconciliation, or **AUTO-write `FIXED.md` + `--archive-fixed`**? — is already **determined by the Status-honesty PIPELINE-GATE**: `FIXED.md` is owned EXCLUSIVELY by the orchestrator's `__mark_fixed__` gate, which fires only after the validation tail. A routing pre-gate that autonomously wrote `FIXED.md` would have the state script vouch for validation it never ran — the exact gate bypass the harness mission calls a defect. So the only gate-respecting behavior is **DETECT + surface for reconciliation** (a canonical `BLOCKED.md` naming the remedy); the operator/harden-round then honors the `docs/bugs/CLAUDE.md` out-of-pipeline reconciliation contract deliberately (its sanctioned manual `FIXED.md` write asserts the fix is genuinely done). Auto-reconcile is not a legitimate option to weigh — it is forbidden — so this is NOT a `NEEDS_INPUT.md` fork. Recorded as a completeness disclosure, not a halt.

### Phase 1: Shared `**Fixed:**`-annotation reader + `fixed-unreconciled` detector/formatter (TDD)

**Scope:** Add the domain-agnostic building blocks in `lazy_core` that both fix sites consume: a `**Fixed:**`-annotation reader, the "already-implemented-but-unreconciled" predicate, and the canonical `BLOCKED.md` body formatter. No routing change yet — pure helpers, unit-tested in isolation.

**Deliverables:**
- [ ] `spec_fixed_annotation(spec_path)` in `lazy_core/docmodel.py` — sibling of `spec_status`, returns the first `**Fixed:**` line's value (or `None`), mirroring `spec_status`'s read + `re.match(r"^\*\*Fixed:\*\*\s*(.+?)\s*$", …)` shape.
- [ ] `is_fixed_unreconciled(spec_dir, repo_root)` in `lazy_core/gates.py` — `True` iff the SPEC's status is a pre-fix status (not `Fixed`/`Won't-fix`) AND `spec_fixed_annotation` is present AND `has_completion_receipt(spec_dir, filename="FIXED.md")` is `False` AND the dir is not under `docs/bugs/_archive/` (defensively-redundant on the Step-4 path; see Validated Assumptions).
- [ ] `format_fixed_unreconciled_blocker(bug_id, fixed_annotation)` in `lazy_core/gates.py` — canonical `BLOCKED.md` frontmatter+body (`blocker_kind: fixed-unreconciled`) modeled on `depdag.format_unknown_dependency_blocker`; body names the remedy: reconcile via the `docs/bugs/CLAUDE.md` receipt+`--archive-fixed` contract, OR clear the stray `**Fixed:**` annotation to re-plan.
- [ ] Tests: `test_docmodel.py` (annotation present / absent / multi-line-first-wins) + `test_gates.py` (`is_fixed_unreconciled` true-case, plus each false-case: status `Fixed`, no annotation, receipt present, archived) + a `format_*_blocker` shape assertion. Register in the seam `_TESTS` runners.

**Minimum Verifiable Behavior:** `python3 -m pytest user/scripts/tests/test_lazy_core/test_docmodel.py user/scripts/tests/test_lazy_core/test_gates.py` passes, with the new predicate returning `True` for a Concluded-`+`-`**Fixed:**`-`+`-no-receipt fixture and `False` for every negative fixture.

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior in this phase (pure `lazy_core` helpers, verified by unit tests).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core/docmodel.py` — add `spec_fixed_annotation`.
- `user/scripts/lazy_core/gates.py` — add `is_fixed_unreconciled` + `format_fixed_unreconciled_blocker`.
- `user/scripts/tests/test_lazy_core/test_docmodel.py`, `.../test_gates.py` — unit coverage.

**Testing Strategy:** Pure-function unit tests over tmp-dir SPEC fixtures; no state machine, no I/O beyond reading fixture files. RED first (helpers absent → import/attribute error), then GREEN.

**Integration Notes for Next Phase:** `is_fixed_unreconciled(spec_dir, repo_root)` and `format_fixed_unreconciled_blocker(...)` are the exact seam Phase 2 (`bug-state.py`) and Phase 3 (`/plan-bug` prose, which names the predicate as the contract) consume. Keep the signature stable. The predicate is status-broad (any pre-fix status) so the Step-4 caller — already inside the `Concluded` branch — passes byte-clean.

---

### Phase 2: `bug-state.py` Step 4 route diversion — the primary, cheapest catch

**Scope:** Wire the Phase-1 predicate into `bug-state.py::compute_state` Step 4 so a `Concluded` + `**Fixed:**`-annotated + no-receipt SPEC is diverted to a `fixed-unreconciled` `BLOCKED.md` outcome BEFORE it can route to `plan-bug` — the item never reaches the expensive planning dispatch.

**Deliverables:**
- [ ] In `bug-state.py` Step 4 (`if not phases_file.exists():`), immediately inside the `if _status == "Concluded":` branch (before the `return … sub_skill=SKILL_PLAN_BUG`), call `lazy_core.is_fixed_unreconciled(spec_dir, repo_root)`. On a hit: write canonical `BLOCKED.md` via `lazy_core._atomic_write` using `format_fixed_unreconciled_blocker`, append a `_diag` breadcrumb ("Concluded SPEC carries a `**Fixed:**` annotation with no receipt — diverted to reconciliation, not plan-bug"), and return `_bug_state(..., terminal_reason=…blocked…)` so the next probe halts at the Step-3 `BLOCKED.md` check.
- [ ] Add a `tabulated-divergence` row to `user/scripts/compute-state-routing-parity.json` for this bug-only pre-gate (owner + reason: the feature pipeline has no out-of-pipeline `**Fixed:**` annotation / `Concluded` intermediate, so no `lazy-state.py` mirror is owed).
- [ ] Tests: a `bug-state.py --test` in-file fixture (`test_fixed_unreconciled_diverts_from_plan_bug`) asserting the Concluded+`**Fixed:**`+no-receipt fixture routes to the blocked outcome (writes `BLOCKED.md`, `sub_skill` is NOT `plan-bug`), plus a companion asserting a plain Concluded-no-annotation fixture still routes to `plan-bug` (no regression). Register in the script's test list; keep the byte-pinned baseline updated via `_normalize_smoke_output`.

**Minimum Verifiable Behavior:** `python3 user/scripts/bug-state.py --test` and `python3 user/scripts/lazy_parity_audit.py --repo-root .` both exit 0; the new fixture proves a `**Fixed:**`-annotated Concluded SPEC yields `BLOCKED.md` + no `plan-bug` route, and the plain-Concluded fixture still yields `plan-bug`.

**MCP Integration Test Assertions:** N/A — routing behavior is verified by the hermetic `--test` fixture (the bug pipeline's structural verification in this repo), not an MCP surface.

**Prerequisites:**
- Phase 1: `is_fixed_unreconciled` + `format_fixed_unreconciled_blocker` exist and are unit-green.

**Files likely modified:**
- `user/scripts/bug-state.py` — the Step-4 pre-check + `_diag` + in-file `--test` fixture.
- `user/scripts/compute-state-routing-parity.json` — the tabulated-divergence row.
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerated via `_normalize_smoke_output` if the fixture output shifts the baseline.

**Testing Strategy:** The `bug-state.py --test` smoke harness builds tmp-dir bug-dir fixtures and asserts the computed state — the fast hermetic regression net. Run `bug-state.py --test`, `lazy-state.py --test` (shared `lazy_core` unchanged-behavior check), `pytest tests/test_lazy_core/`, and the parity audit.

**Integration Notes for Next Phase:** After this phase, the *autonomous* path is fully covered — a Fixed-annotated Concluded bug never routes to `plan-bug`. Phase 3 covers the residual *direct-invocation* path (`/plan-bug <spec>` run by hand or by a future caller that bypasses the Step-4 divert). The BLOCKED.md is the canonical name (never trips `block-noncanonical-blocker-write.sh`) and is already in the notify attention set (`blocked`) + `--park-blocked`-able.

---

### Phase 3: `/plan-bug` Step 0.4 belt-and-suspenders gate (direct-invocation safety)

**Scope:** Add the completion-defense-in-depth pre-gate to `/plan-bug`'s Step 0.4 status gate so the skill is safe even when invoked directly on a Fixed-annotated Concluded SPEC (bypassing the Phase-2 `bug-state.py` divert) — it refuses to plan and names the reconciliation remedy instead of burning a `/spec-phases` + `/write-plan` dispatch.

**Deliverables:**
- [ ] Extend `user/skills/plan-bug/SKILL.md` Step 0.4: after the status gate confirms a pre-fix status, add a sub-check — if the SPEC carries a `**Fixed:**` annotation (status not yet `Fixed`) AND no valid `FIXED.md` receipt (the `lazy_core.is_fixed_unreconciled` predicate, named as the contract), REFUSE the planning round with a distinct `fixed-unreconciled` note: "this bug appears already-implemented out-of-pipeline (`**Fixed:**` annotation present, no receipt) — reconcile via the `docs/bugs/CLAUDE.md` receipt + `--archive-fixed` contract, or clear the stray `**Fixed:**` annotation to re-plan. Do NOT author `PHASES.md` / a plan." Return success with the note and STOP; do NOT proceed to Step 1/2.
- [ ] Re-project + lint: `python ~/.claude/scripts/project-skills.py` then `python ~/.claude/scripts/lint-skills.py` (no broken injections; the added prose references the shared predicate by name — no new `!cat` component needed).

**Minimum Verifiable Behavior:** `python ~/.claude/scripts/lint-skills.py` exits clean after re-projection; the Step 0.4 prose visibly refuses a `**Fixed:**`-annotated Concluded SPEC before Step 1.

**Runtime Verification** *(checked by manual review / the skill's own contract — NOT by the implementation agent):*
- [ ] <!-- verification-only --> The updated Step 0.4, read end-to-end, refuses a Fixed-annotated no-receipt Concluded SPEC (names the reconciliation remedy) and still proceeds normally for a plain Concluded SPEC — confirmed by reading the projected `skills-projected/_default/plan-bug/SKILL.md`.

**MCP Integration Test Assertions:** N/A — `/plan-bug` is prose; its behavior is verified by lint + projection review, not an MCP surface.

**Prerequisites:**
- Phase 1: the `is_fixed_unreconciled` predicate exists (the prose names it as the mechanical contract).
- Phase 2: establishes the canonical `fixed-unreconciled` vocabulary + remedy wording this phase mirrors, so the two surfaces speak with one voice.

**Files likely modified:**
- `user/skills/plan-bug/SKILL.md` — the Step 0.4 belt-and-suspenders sub-check.
- `skills-projected/_default/plan-bug/SKILL.md` — regenerated by `project-skills.py` (generated output; not hand-edited).

**Testing Strategy:** Skill prose — verified by `project-skills.py` (clean expansion) + `lint-skills.py` (no broken injections / embedded patterns) + a read-through of the projected output. No coupled-pair mirror is owed: `/plan-bug` is a bug-axis skill; the parity manifest audits its bug-axis siblings, not `/plan-feature` (the feature pipeline has no `**Fixed:**`-annotation analog). Run `lazy_parity_audit.py --repo-root .` to confirm the audit stays green.

**Integration Notes for Next Phase:** Final phase. Both the autonomous route (Phase 2) and the direct-invocation route (Phase 3) now recognize the already-implemented signal cheaply, before any planning dispatch — closing the gap left open by commit 38144ada (which added the reconciliation path but no pre-gate in the routing/planning path).

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md/PHASES.md `**Status:**` to `Fixed` and writes `FIXED.md` once this bug's validation tail passes — never authored as a checkbox row here.
