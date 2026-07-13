# Implementation Phases — Completion-gate refusal names the failing check but not the failing items

**Status:** Fixed

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config has no Tauri/MCP app surface; this is a pure Python
state-script change verified via `pytest user/scripts/test_lazy_core.py` (the repo's established
harness for `lazy_core.py`/state-script behavior).

## Validated Assumptions

- **`verify_ledger` already computes every diagnostic it was throwing away.** Confirmed by reading
  `user/scripts/lazy_core.py`'s `verify_ledger()` (~3845 at the time of this pass): `clean_tree`
  captures the full `git status --short` stdout before reducing to a boolean; `head_matches_origin`
  computes both shas before reducing; `plan_complete` computes `incomplete_plans` (feature-level) or
  reads `_plan_status` (scoped) before reducing; `deliverables_done` walks PHASES.md/plan-WU
  checkboxes before reducing. No new parsing surface was needed — only capturing what already
  existed instead of discarding it.
- **Surface B's `genuine` row list was already collected, just never printed.** `classify_blocking_
  unchecked_rows` (~2553) already returns `{"shim": [...], "genuine": [...]}`; the `62fdba2`
  advisory (~5185 pre-change) printed only `len(cls["genuine"])`, discarding the list itself.

## Cross-feature Integration Notes

No `**Depends on:**` block in the SPEC. D3 (scope boundary) is pre-resolved in the SPEC itself: the
shim-row migration semantics and per-row host-deferral remain owned by `turn-routing-enforcement`
NEEDS_INPUT #5 — this bug adds visibility only, never a new tick/migration path. `user/skills/**`
prose updates ("the refusal is now self-diagnosing — a second discovery probe is a deviation") are
explicitly OUT of this bug's lane (STATE-lane fix) and are deferred to a skills-lane follow-up.

---

### Phase 1: `verify_ledger` `failing_detail` enrichment + Surface B genuine-row printing + telemetry `detail_head`

**Status:** Complete

**Scope:** Add a `failing_detail` object to `verify_ledger`'s return shape (populated per-check for
every False check, not just the first), print `classify_blocking_unchecked_rows`'s `genuine` row
excerpts (with line numbers, matching the existing `shim` convention) in the `__mark_complete__`
coherence-gate advisory, and add a compact `detail_head` telemetry field to the `gate-refusal` event
in both state scripts.

**TDD:** yes — every new behavior is covered by a new pytest fixture in `test_lazy_core.py` before
being relied upon in the close-out gates below.

**Deliverables:**
- [x] `_excerpt`, `_phases_unchecked_row_detail`, `_plan_wu_unchecked_row_detail` helpers
  (`user/scripts/lazy_core.py`, just above `verify_ledger`) — fence-aware, line-numbered unchecked-row
  collectors reusing the existing `count_deliverables`/`_plan_wu_checkbox_counts`/
  `_unchecked_wus_in_plan_scope` walk conventions.
- [x] `verify_ledger` check 1 (`clean_tree`) retains the captured `git status --short` stdout
  (`_clean_tree_stdout`) instead of discarding it after the boolean reduction.
- [x] `verify_ledger` check 2 (`head_matches_origin`) retains `_head_sha`/`_upstream_sha`/
  `_no_upstream` for the failing-detail payload (short shas + an explicit no-upstream
  discriminator, distinct from a genuine divergence).
- [x] `verify_ledger` assembles `failing_detail` keyed by check name for EVERY False check (not just
  `failing_check`): `clean_tree` → `{dirty_files, total_count, git_error?}`; `head_matches_origin` →
  `{no_upstream, head_sha?, upstream_sha?, ahead?, behind?}` (ahead/behind via `git rev-list
  --left-right --count @{u}...HEAD`); `plan_complete` → scoped `{plan_file, plan_status}` /
  feature-level `{incomplete_plans: [{file, status}], total_count}`; `deliverables_done` →
  `{rows: [{line, text}], total, note?}`. Additive only — `ok`/`failing_check`/`checks`/
  `deliverables_source` byte-identical to before; `failing_detail` is `{}` when `ok` is True.
- [x] `classify_blocking_unchecked_rows` excerpts gain a `L<N>: ` line-number prefix (both `shim` and
  `genuine` classes) — backward-compatible (existing substring-based test assertions unaffected).
- [x] The `__mark_complete__` coherence-gate advisory (`apply_pseudo`, ~5185–5449) prints the
  `genuine` row excerpts (not just the count) alongside the existing `shim` excerpts.
- [x] `summarize_failing_detail(result)` (`lazy_core.py`) — a compact one-line `detail_head` string
  per failing check, used by the `gate-refusal` telemetry event in both `lazy-state.py` and
  `bug-state.py`'s `--verify-ledger` handlers. Never raises on a malformed/legacy payload (degrades
  to `""`).
- [x] Coupled-pair mirroring verified: `bug-state.py` shares `lazy_core.verify_ledger` and its
  `--verify-ledger` handler `json.dumps(result, ...)`s the WHOLE dict, so `failing_detail` passes
  through with no separate change needed; its own `gate-refusal` event gains the same `detail_head`
  field.
- [x] Tests (`user/scripts/test_lazy_core.py`): one fixture per `failing_detail` axis (clean_tree,
  head_matches_origin ahead/behind, head_matches_origin no-upstream, plan_complete feature-level,
  plan_complete scoped, deliverables_done feature-level, deliverables_done plan-wu-checkboxes,
  the `ok:true` empty-dict case), a coherence-gate-advisory test asserting both `Shim rows:` and
  `Genuine rows:` appear with line numbers, and six `summarize_failing_detail` unit tests (per-check
  shape + the `ok:true`/malformed degrade-to-`""` cases). All registered in the `_TESTS` manual
  registry (the dead-coverage guard `test_no_orphaned_test_functions` stays green).

**Implementation Notes (2026-07-12):** Landed exactly as scoped above; no design deviations. The
`docs/bugs/CLAUDE.md` "Fixing a bug OUT-OF-PIPELINE" contract and SKILL-prose updates (Fix Scope
item 4's SKILL half) are OUT of this bug's STATE lane and are not touched here — see the FIXED.md
receipt's provenance note. Files: `user/scripts/lazy_core.py`, `user/scripts/lazy-state.py`,
`user/scripts/bug-state.py`, `user/scripts/test_lazy_core.py`.

**Minimum Verifiable Behavior:** `python -m pytest user/scripts/test_lazy_core.py -k
"verify_ledger_failing_detail or summarize_failing_detail or classify_blocking_unchecked_rows or
coherence_advisory_prints_genuine or no_orphaned_test_functions" -q` is GREEN (17/17); a hand-run
`python user/scripts/lazy-state.py --repo-root . --verify-ledger <dirty-spec-dir>` on a dirty tree
prints a `failing_detail.clean_tree.dirty_files` list instead of a bare boolean.

**Runtime Verification:** N/A — pure Python state-script logic, no app runtime; verified by the
pytest fixtures above (the harness's established verification method for this file class, per
`user/scripts/CLAUDE.md`).

**MCP Integration Test Assertions:** N/A — no MCP tool surface in this repo.

**Prerequisites:** None (single phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `verify_ledger` enrichment, new helper functions, `summarize_
  failing_detail`, the coherence-gate advisory genuine-row printing.
- `user/scripts/lazy-state.py` / `user/scripts/bug-state.py` — `detail_head` on the `gate-refusal`
  telemetry event (both `--verify-ledger` handlers).
- `user/scripts/test_lazy_core.py` — new fixtures + `_TESTS` registrations.
- `user/scripts/CLAUDE.md` — no changes required (no script-table entry needed for an existing
  function's enrichment).

**Testing Strategy:** Pure pytest fixtures constructing hermetic git-repo fixtures (via the existing
`_make_git_repo_with_origin` / `_write_complete_plan` / `_write_all_checked_phases` helpers) and
asserting the enriched JSON shape.

**Integration Notes for Next Phase:** None — final phase. The `__mark_fixed__` gate (orchestrator-
owned, applied here directly per the operator-directed-interactive protocol) flips `**Status:**` and
writes `FIXED.md`.

---

## Review Notes

_(Populated by the /spec-phases Step 6 review gate and by later /execute-plan batch reviews — N/A
for this operator-directed-interactive close-out.)_
