# Implementation Phases — `__mark_complete__` ROADMAP strike & `-followups` queue-trim

> Phases for [`SPEC.md`](./SPEC.md)

**Status:** Open
<!-- No production code change is warranted — the fix shipped in commit 1b81210 (unified-pipeline-orchestrator Phase 5 WU-3) with passing regression tests. This is a confirmed-duplicate / already-fixed item: the single phase below is a no-op VERIFICATION phase that records the existing tests as the certifying evidence and routes to archive. The flip to Fixed + the FIXED.md receipt are owned EXCLUSIVELY by the orchestrator's __mark_fixed__ validation-tail gate — never set here. When the verification phase lands, the top-level Status moves to In-progress (implementation/verification done, validation pending). -->


**MCP runtime:** not-required — harness state-machine defect in `lazy_core.py` (`apply_pseudo __mark_complete__`); verified entirely by `test_lazy_core.py`. No AlgoBooth app surface, no Tauri/MCP-reachable behavior (per `docs/features/mcp-testing/SPEC.md`: pure script tooling is outside MCP reach).

## Provenance

This bug is a **confirmed duplicate of already-shipped work** (SPEC `## Proven Findings` #4). The session-log audit that filed it (2026-06-19) sampled `/lazy-batch` runs from 2026-06-16/17 that executed the **pre-WU-3** `apply_pseudo` code — basename-only queue match (missed `-followups` / divergent-`spec_dir` ids) and an orchestrator-inline ROADMAP strike (hand-edited 5×). Both failure modes were **root-caused and fixed** before the audit ran, in a single commit:

- `1b81210` — `feat(unified-pipeline-orchestrator): Phase 5 WU-1/2/3`. Folds the ROADMAP strike **into** `apply_pseudo __mark_complete__` (`_strike_roadmap_row`, idempotent, returns `roadmap_struck`) and trims the queue by the **resolved** `spec_dir` (`_resolve_under_repo` + `_entry_matches`, returns `queue_trimmed`), catching the `-followups` path-form class the legacy basename-only match missed.

Because the fix is present, correct, and covered by dedicated passing regression tests, **no source change is warranted**. The single phase below is a no-op verification phase that re-certifies the existing evidence and routes to confirm-and-archive — authoring fabricated implementation phases for an already-fixed defect would be worse than a no-op (SPEC `## Note for /plan-bug`).

**Scope-class decisions taken in-cycle (D7 completeness-first):**
- ⚖ policy: already-fixed bug → no-op verification phase, route to archive (SPEC `/plan-bug` note; re-run the cited tests as the certifying evidence rather than fabricate fix phases).

---

### Phase 1: Re-certify the existing fix & regression coverage (no source change)

**Scope:** Confirm the WU-3 fix is on disk and its dedicated regression tests are green, recording that run as the certifying evidence for a confirm-and-archive close. **No production source edit** — this phase exists solely to ground the already-fixed conclusion in a fresh, reproducible test run so the validation tail (`/mcp-test` → coverage audit → `__mark_fixed__`) has real evidence to gate on.

**Deliverables:**
- [ ] Confirm the WU-3 fix is present in `user/scripts/lazy_core.py`: `apply_pseudo __mark_complete__` calls `_strike_roadmap_row` (returns `roadmap_struck`) and trims the queue via `_resolve_under_repo` / `_entry_matches` (returns `queue_trimmed`). (Source inspection — no edit.)
- [ ] Run `python user/scripts/test_lazy_core.py`; confirm green, including the three cited regression tests:
  - `test_apply_pseudo_mark_complete_trims_by_resolved_spec_dir_followups` — the exact `-followups` path-form-`spec_dir` miss class; asserts `queue_trimmed is True` (the legacy basename-only match would have missed it).
  - `test_apply_pseudo_mark_complete_strikes_roadmap_row` — asserts `roadmap_struck is True`.
  - `test_apply_pseudo_mark_complete_no_roadmap_is_noop_strike` — no ROADMAP.md → `roadmap_struck False`, completion still succeeds.
- [ ] Record the test result (count + the three named tests passing) in this phase's Implementation Notes as the confirm-and-archive evidence.

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` exits 0 with all tests passing, including the three named `apply_pseudo __mark_complete__` regression tests — re-certifying that the ROADMAP strike and resolved-`spec_dir` queue-trim (incl. the `-followups` class) work.

**Prerequisites:** None (sole phase).

**Files likely modified:** None — verification-only. (Possible: this PHASES.md Implementation Notes; the SPEC if a status reconciliation is owed — but the top-level Fixed flip + FIXED.md are orchestrator-owned, never set here.)

**Testing Strategy:** Re-run the existing `test_lazy_core.py` suite. The three cited tests already reproduce both failure modes against the fixed code; a green run is the certifying evidence. No new test is authored — the coverage exists and is the point.

**Integration Notes for Next Phase:** This is the sole (terminal) phase. When it lands, the top-level PHASES `**Status:**` moves to `In-progress` (verification done, validation pending). The state machine routes to `/mcp-test` → coverage audit → the orchestrator's `__mark_fixed__` gate, which owns the flip to `Fixed` and the FIXED.md receipt. Because there is no app surface, `/mcp-test` resolves via the structural MCP-skip (`MCP runtime: not-required`).
