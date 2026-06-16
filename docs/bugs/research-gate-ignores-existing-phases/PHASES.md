# Implementation Phases — Research gate fires on already-implemented features

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness-internal Python state machine + thin skill-wrapper prose; no AlgoBooth app surface, no Tauri/MCP HTTP server. Verification is the in-file `--test` smoke harness (`lazy-state.py --test`) + `test_lazy_core.py`, the canonical regression net per `user/scripts/CLAUDE.md`.

## Validated Assumptions

All load-bearing assumptions here are **code-provable** — verified by reading the cited source during planning (the Touchpoint Audit below), not inferred. No runtime spike is required:

- The Step-5 research gate (`lazy-state.py:1493–1534`) branches **only** on `RESEARCH.md` / `RESEARCH_SUMMARY.md` / `RESEARCH_PROMPT.md` / `NEEDS_RESEARCH.md` presence and never reads `PHASES.md`. The `PHASES.md` existence/completion check is Step 6 (`lazy-state.py:1547`), strictly **after** the research gate. (SPEC Evidence → Source Code; confirmed during planning.)
- `lazy_core.parse_phases(phases_text)` (`lazy_core.py:1384`) returns one record per phase with `status` and per-phase `unchecked`/`checked`; `count_deliverables(phases_text)` (`lazy_core.py:1218`) returns `(unchecked, checked)` whole-file. Both are fence-aware and already imported by `lazy-state.py` at Step 6/7. The implementation-evidence predicate composes these — **no new parsing surface**.
- `_diag(msg)` (`lazy_core.py:83`) appends to the per-invocation `_DIAGNOSTICS` list (reset once per `compute_state` via `reset_diagnostics`). This is the existing diagnostic channel D3 requires — the bypass emits a `_diag(...)` line, not a silent behavior change.
- `lazy-state.py --test` output is byte-pinned to `tests/baselines/lazy-state-test-baseline.txt`, normalized by `test_lazy_core.py::_normalize_smoke_output`. Adding fixtures changes this baseline; regenerate ONLY by piping live `--test` through that helper, never by hand.
- **Bug-pipeline parity not needed (SPEC Open-Q3, confirmed):** `bug-state.py` drops the research steps entirely — there is no Step-5 research gate to mirror. This fix is `lazy-state.py`-only on the state-machine side; `lazy_core.py` (shared) gains the predicate, so `bug-state.py` is unaffected but both `--test` suites still run as the shared-import gate.

## Completeness-policy resolutions applied at planning time (D7)

The SPEC's two Open Questions are scope/sizing decisions — neither diverges in user-visible product behavior — so each took the most-complete in-cycle path rather than a `NEEDS_INPUT` halt:

- ⚖ policy: skip on empty-stub PHASES.md → NO (require parsed phases + evidence). SPEC Open-Q1 + D2: a stub `PHASES.md` with zero parsed phases must NOT suppress legitimate research. The predicate returns `False` when `parse_phases` yields zero phases — a stub is treated exactly as "no PHASES.md", so research still routes.
- ⚖ policy: predicate breadth → broadest cheap signal (D2). Any phase `Status` of `Complete`/`In-progress`, OR ≥1 checked deliverable, OR an `## Implementation Notes` block present → treat as past-research. A partially-built feature is never sent back for research.

## Touchpoint Audit (verified during planning — read-only)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `parse_phases(phases_text)` `:1384`; `count_deliverables(phases_text)` `:1218`; `_diag(msg)` `:83`; `_DIAGNOSTICS` `:80` | refactor | Add `phases_show_implementation(phases_text) -> bool` composing the existing parsers (NO new parsing). Returns `False` for zero parsed phases (stub guard); `True` when any phase `status` ∈ {Complete, In-progress} (case-insensitive), OR `count_deliverables()[1] >= 1` (≥1 checked), OR an `## Implementation Notes` heading is present. |
| `user/scripts/lazy-state.py` | yes | Step-5 research gate `:1493–1534` (the four `not research and not research_summary` branches); `phases_file = spec_path / "PHASES.md"` first read at Step 6 `:1547` | refactor | Insert a **pre-Step-5 guard**: BEFORE the research gate's `if not research.exists() and not research_summary.exists():`, if `PHASES.md` exists AND `phases_show_implementation(phases_text)` is `True`, emit a `_diag(...)` (D3) and FALL THROUGH to Step 6 (do not return a research action). Read `PHASES.md` once here and reuse the text at Step 6 (avoid a double read). The guard fires only when no RESEARCH*.md is present — when research already exists, behavior is byte-identical (the guard is a no-op on the existing path). |
| `user/scripts/test_lazy_core.py` | yes | `phases_show_implementation` characterization (new); `_normalize_smoke_output` | refactor | Add direct characterization tests for the predicate (the new fixtures below assert routing; these assert the predicate in isolation). |
| `user/scripts/tests/baselines/lazy-state-test-baseline.txt` | yes | byte-pinned `--test` output | refactor | Regenerate via `_normalize_smoke_output` after adding the new routing fixtures; the no-PHASES research path stays byte-identical. |
| `user/skills/lazy/SKILL.md` | yes | state-machine prose summary `:270`; Step-4.5-vs-5 explainer `:272–275`; `needs-research` terminal row `:132` | refactor | Lockstep prose (coupled-pair rule): note that the Step-5 research gate is skipped when `PHASES.md` already shows implementation evidence (falls through to Step 6). State-machine logic stays in the script. |
| `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md` | yes | Step-5 mentions `:133`, `:90` | refactor | Mirror the lazy/SKILL.md prose note per the coupled-pair rule; the only intended divergence remains the `--cloud` flag. Diff against lazy/SKILL.md immediately after editing. |

No path is net-new — every change extends an existing structure. No genuine design fork surfaced (both forks were scope/mechanical, resolved by D7 above).

## Cross-feature Integration Notes

No hard upstream deps — this is a self-contained harness bug. The only cross-artifact coupling is the **coupled-pair rule** from the repo `CLAUDE.md`: `/lazy` ↔ `/lazy-cloud` share a dispatch contract and their Step-5 prose must stay in lockstep (Phase 3). The state-machine change lands ONLY in `lazy-state.py` (`/lazy-cloud` is the same script with `--cloud`), and `lazy_core.py` is shared — so `bug-state.py --test` runs as part of the shared-import gate even though the bug pipeline has no research gate.

---

### Phase 1: Implementation-evidence predicate (lazy_core.phases_show_implementation) — TDD

**Scope:** Add a deterministic, fence-aware predicate that answers "does this PHASES.md show implementation evidence?" by composing the existing `parse_phases` / `count_deliverables` parsers. This is the reusable primitive the Step-5 guard (Phase 2) consults. Isolating it in `lazy_core.py` keeps the shared-helper change and its direct unit tests separate from the routing change. (SPEC D2 / Affected Area row "Implementation-evidence predicate".)

**Deliverables:**
- [ ] `lazy_core.phases_show_implementation(phases_text: str) -> bool` added near `parse_phases` / `count_deliverables`. Returns `False` when `parse_phases(phases_text)` yields **zero** phases (stub guard — SPEC Open-Q1 / D2). Otherwise returns `True` when ANY of: a parsed phase's `status` is `Complete` or `In-progress` (case-insensitive compare on the stripped value), OR `count_deliverables(phases_text)[1] >= 1` (≥1 checked deliverable), OR the text contains an `## Implementation Notes` heading (regex `^#{2,3}\s+Implementation Notes\b`, fence-awareness not required — a heading inside a fence is a non-issue for this signal, but match only at line start). Else `False`.
- [ ] Docstring documents the contract: the three OR'd signals, the zero-phase stub guard, and that it is purely a read — no side effects, no `_diag` (the diagnostic is emitted by the caller in Phase 2, so the predicate stays a pure function reusable elsewhere).
- [ ] Tests: `test_lazy_core.py` characterization — RED first. Cases: (a) zero parsed phases → `False`; (b) one phase `**Status:** Complete` → `True`; (c) one phase `**Status:** In-progress`, no checked boxes → `True`; (d) phases all `**Status:** Planned` but ≥1 `- [x]` → `True`; (e) phases all `Planned`, zero checked, but an `## Implementation Notes` block present → `True`; (f) phases parsed, all `Planned`, zero checked, no Implementation Notes → `False`; (g) checkbox inside a ```fence``` does NOT count (fence-aware via `count_deliverables`).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` passes including the new `phases_show_implementation` cases. Concretely: a PHASES.md string with one `**Status:** In-progress` phase returns `True`; an empty-stub string (no phase headings) returns `False`; a string with only `Planned` phases and no checked boxes / no Implementation Notes returns `False`.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — new `phases_show_implementation` function (composes `parse_phases` `:1384` + `count_deliverables` `:1218`).
- `user/scripts/test_lazy_core.py` — new RED-first characterization cases registered in the runner list.

**Testing Strategy:**
Pure unit characterization in `test_lazy_core.py` (the helper is domain-agnostic and directly testable). Write the seven RED assertions FIRST; confirm they fail because the function does not exist (`AttributeError`/`NameError`), not a typo. Then implement. The predicate must reuse `count_deliverables` for the checked-box signal so fence-awareness is inherited (case (g) proves this).

**Integration Notes for Next Phase:**
- Phase 2's guard reads `phases_show_implementation(phases_text)` and pairs a `True` result with a `_diag(...)` emission. The predicate itself stays side-effect-free.
- Contract locked here: `False` for zero parsed phases is the stub guard the SPEC Open-Q1 depends on — Phase 2 relies on it so a stub PHASES.md does NOT suppress research.

---

### Phase 2: Pre-Step-5 guard in lazy-state.py (skip research when phases implemented) — TDD

**Scope:** Insert the root-cause fix (SPEC D1 / Theory 1): a guard BEFORE the Step-5 research gate that, when `PHASES.md` exists with implementation evidence, emits a diagnostic and falls through to Step 6 instead of routing to `needs-research`. This is the behavioral change the whole bug is about. (SPEC Affected Area row "Research gate".)

**Deliverables:**
- [ ] In `compute_state()`, immediately BEFORE the Step-5 block (`lazy-state.py:~1493`, the `research = spec_path / "RESEARCH.md"` line / the `if not research.exists() and not research_summary.exists():` gate), add: read `phases_file = spec_path / "PHASES.md"`; if `phases_file.exists()`, read its text and, if `lazy_core.phases_show_implementation(phases_text)` is `True`, emit `_diag("Step 5 research gate skipped: PHASES.md present with implementation evidence — feature is past pre-planning research")` (D3) and DO NOT enter/return from the research gate — fall through to Step 6. (SPEC D1 / D3.)
- [ ] The guard fires ONLY when no `RESEARCH.md`/`RESEARCH_SUMMARY.md` is present (i.e. it is the only thing that would otherwise route to research). When research already exists, the existing Step-5/6 path is unchanged — the guard is a structural no-op there. This preserves byte-identical behavior on every existing path that already has research.
- [ ] **No double-read:** the `PHASES.md` text read by the guard is reused by Step 6 (`phases_text = phases_file.read_text(...)` at `:1574`) — refactor so the file is read at most once per invocation (e.g. read into a local at the guard and reuse, or guard reads only when reaching the gate-skippable branch). Do NOT introduce a second `read_text` on the same path in the same `compute_state` call.
- [ ] Tests: new `lazy-state.py --test` fixtures (see Testing Strategy) — the core anti-regression net.

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --test` passes including the new fixtures, and the no-PHASES research path stays byte-identical to the regenerated baseline. Concretely: a temp-dir feature with `SPEC.md` (Ready) + a `PHASES.md` containing an `In-progress` phase + **no** `RESEARCH.md` routes to Step 6/7 (a planning or execute-plan action — NOT `terminal_reason="needs-research"` and NOT `sub_skill="spec"` research-prompt generation). The SAME feature with NO `PHASES.md` still routes to research as before.

**Prerequisites:** Phase 1 (`phases_show_implementation` must exist and be import-callable from `lazy_core`).

**Files likely modified:**
- `user/scripts/lazy-state.py` — pre-Step-5 guard in `compute_state` (verified anchors `:1493` gate, `:1547` Step-6 PHASES read).
- `user/scripts/tests/baselines/lazy-state-test-baseline.txt` — regenerated via `_normalize_smoke_output` (new fixtures add lines; the no-PHASES research path is byte-identical).

**Testing Strategy:**
TDD against the in-file `--test` harness — the canonical hermetic check per `user/scripts/CLAUDE.md`. Add fixtures modeled on the existing research-gate fixtures:
1. **`research-gate-skipped-when-phases-implemented`** — SPEC (Ready) + PHASES.md with one `In-progress` phase (or ≥1 checked box) + no RESEARCH.md → dispatched action is Step 6/7 (plan/execute), NOT `needs-research`. The exact symptom from the SPEC (mcp-testing repro).
2. **`research-gate-fires-when-no-phases`** — SPEC (Ready) + no PHASES.md + no RESEARCH.md → still routes to research (`needs-research` / research-prompt). Guards the unchanged default.
3. **`research-gate-fires-when-phases-stub`** — SPEC (Ready) + an empty-stub PHASES.md (no phase headings parsed) + no RESEARCH.md → still routes to research (SPEC Open-Q1 / D2 — stub must not suppress research).
4. **`research-path-byte-identical-when-research-present`** — SPEC + PHASES.md (implemented) + RESEARCH_SUMMARY.md present → routes to Step 6 exactly as today (the guard is a no-op; no behavior change when research already exists).
Write each fixture's assertion FIRST and confirm it fails RED against the unmodified script for the right reason (fixture 1 currently returns `needs-research`), then implement.

**Integration Notes for Next Phase:**
- The behavioral fix lives entirely here + Phase 1. Phase 3 is lockstep wrapper PROSE only — no logic. After Phase 2, run the full shared-import gate: `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py` (and `lazy_coord.py --test` for completeness).
- The `_diag` string `"Step 5 research gate skipped: PHASES.md present with implementation evidence …"` is the visible-in-probe contract D3 requires — keep it stable so a retro/probe can grep for it.

---

### Phase 3: Lockstep wrapper prose — lazy/SKILL.md + lazy-cloud/SKILL.md (coupled pair)

**Scope:** Update the two paired wrappers' Step-5 state-machine PROSE so they accurately describe the new gate behavior (research is skipped when PHASES.md already shows implementation). This is the coupled-pair rule from the repo `CLAUDE.md` (`/lazy` ↔ `/lazy-cloud`): a state-machine change must keep the paired wrappers in sync. No logic lands here — the wrappers are thin and the logic is in the script.

**Deliverables:**
- [ ] `user/skills/lazy/SKILL.md`: in the state-machine prose summary (`:270`) and/or the Step-4.5-vs-5 explainer (`:272–275`), add a sentence: the Step-5 research gate is **skipped** when `PHASES.md` already exists with implementation evidence (any phase Complete/In-progress, a checked deliverable, or an Implementation Notes block) — the pipeline falls through to Step 6, because a feature with implemented phases is past the pre-planning research stage. Reference that the predicate + diagnostic live in `lazy-state.py`/`lazy_core.py` (state-machine logic stays in the script).
- [ ] `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`: mirror the same prose note at its Step-5 mention (`:133`/`:90` neighborhood). The only intended divergence remains the `--cloud` flag.
- [ ] Immediately after editing both, diff them against each other and confirm the Step-5 prose matches (modulo the documented `--cloud` divergence), per the coupling rule's "diff the other immediately afterward" directive.

**Minimum Verifiable Behavior:** Documentation/prose. Structural verification: `python ~/.claude/scripts/lint-skills.py` is clean (no broken `!cat` injections), `python ~/.claude/scripts/project-skills.py` re-projects both wrappers without errors, and a grep of both SKILL.md files shows the new "research gate skipped when PHASES.md shows implementation" prose in each. The behavioral proof lives in Phase 1–2's `--test` fixtures (the wrapper is a thin shell around the script per `user/scripts/CLAUDE.md`).

**Prerequisites:** Phase 2 (the gate behavior must exist before the prose describes it).

**Files likely modified:**
- `user/skills/lazy/SKILL.md`
- `repos/algobooth/.claude/skills/lazy-cloud/SKILL.md`

**Testing Strategy:**
No code execution. Cross-check: (1) `lint-skills.py` clean; (2) `project-skills.py` re-projects cleanly; (3) diff the two wrappers to confirm the Step-5 prose is mirrored (coupled-pair rule). The behavioral regression net is the Phase 1–2 fixtures.

**Integration Notes for Next Phase:**
- This is the terminal phase. After it, the research gate consults PHASES.md before firing, the wrappers describe it accurately, and the `--test` suite pins the behavior.

---

## Notes

- **No MCP/runtime phase.** Per the `**MCP runtime:** not-required` header, all behavioral verification is the Python `--test` harness + `test_lazy_core.py`, carried by Phases 1–2 (each with RED-first fixtures). Phase 3 is prose with structural (lint/projection) verification — correct for harness-internal skill/doc changes, not a terminal-MCP-stacking anti-pattern (there is no app surface to MCP-test).
- **Coupled-pair discipline.** Phase 3 must land the `/lazy` and `/lazy-cloud` prose together; do not commit one side of the pair without the other. Run the full gate set after Phases 1–2: `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once the validation tail passes — this PHASES.md never flips the top-level status.
