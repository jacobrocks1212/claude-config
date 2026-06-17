# Implementation Phases — /lazy-batch unified-driver parity & cycle-accounting gaps

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is the harness repo itself: no `src-tauri/`, no app `package.json`, no MCP-reachable runtime surface. All three defects live in Python state-machine code (`lazy_core.py` / `lazy-state.py`) and SKILL.md prose. Validation is the hermetic `--test` smoke harnesses (`lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`) + `lazy_parity_audit.py` + `lint-skills.py` — not a live dev runtime. (Per `docs/features/mcp-testing/SPEC.md` this is the "build-tooling / no-app-integration" untestable class.)

## Validated Assumptions

All load-bearing assumptions for these phases are **code-provable** (read directly from the named source during the /spec-phases Touchpoint Audit, 2026-06-17) — none are runtime-coupled, so no runtime spike is scheduled:

- **Item 1 — the `--apply-pseudo` handler advances no counter.** `lazy-state.py:6519–6531` calls `lazy_core.apply_pseudo(...)`, writes the JSON result, and returns — with NO call to `advance_run_counters`/`advance_meta_cycle`. The only counter advance in the file (`6621`) is in the `--repeat-count`/probe path, which a forward-advancing pseudo-skill (inline, no Agent, no guard ALLOW, no consume) never trips. `advance_run_counters` (`lazy_core.py:7651`) gates on `current_consume <= prior_consume` → no consume → no advance. CONFIRMED.
- **Item 2 — the unified driver omits the `--archive-fixed` chain.** `/lazy-batch` Step 1c.5 (`lazy-batch/SKILL.md:466–499`) lists ONLY feature pseudo-skills and carries **no `__mark_fixed__` block at all**; its cloud twin (`lazy-batch-cloud/SKILL.md:377+`) likewise omits it. By contrast `/lazy-bug-batch` Step 1c.5 (`lazy-bug-batch/SKILL.md:378–430`) explicitly chains `--apply-pseudo __mark_fixed__` → `bug-state.py --archive-fixed`. The trim predicate (`lazy_core.apply_pseudo` `is_fixed` gate, `lazy_core.py:3203`) and `archive_fixed` CLI (`bug-state.py:3979/4463`) are already correct — the gap is purely the missing chained call in the driver prose. CONFIRMED.
- **Item 3 — merged head is ordering-only; bug-load bridge swallows errors.** `merged_worklist`/`next_merged` (`lazy_core.py:5302–5369`) are pure ordering — no `compute_state`, no per-item state re-inference, so a resolved (Complete/Fixed) item is returned as a head. `_load_bug_queue_for_merged` (`lazy-state.py:256–282`) wraps the dynamic `load_bug_queue` call in a bare `except Exception: return []` at line 281 (silent features-only degrade). The on-disk bug fallback IS plumbed: `load_bug_queue` (`bug-state.py:~290`) appends `_find_open_bug_dirs(...)` (line 353); `_find_open_bug_dirs` (`bug-state.py:416`) returns open on-disk dirs not in the queue, skipping `_`-prefixed, queued ids, no-`SPEC.md`, Won't-fix, and Fixed-with-receipt. CONFIRMED.

## SPEC-example capability audit

The SPEC carries no foreign-API code examples — its "examples" are quoted real symbols from this repo's own scripts, every one of which was verified to exist during the Touchpoint Audit (`advance_meta_cycle`, `apply_pseudo`, `merged_worklist`, `_load_bug_queue_for_merged`, `bug-state.py --archive-fixed`, `audit_merged_view_dispatch_parity`). No construct consumes an unimplemented/rejected capability. Gate satisfied — no planning-time halt.

## Resolved Open Questions (completeness-first / D7 — scope-class, taken in-cycle)

Both SPEC Open Questions are **scope-class** (they differ in robustness / contract-purity, not in user-visible product behavior), so per the standing completeness-first policy the more-complete path is taken in-plan and disclosed:

- ⚖ **policy: item-1 counter fix shape → Fix-A** (advance on `(feature_id, current_step, sub_skill)` change). Fix-A is consume-independent and additionally closes Theory 1b (verbatim real-skill dispatch can also miss a consume); Fix-B (`advance_forward_cycle()` from `--apply-pseudo` only) fixes pseudo-skills alone. Same end-state (accurate counters); Fix-A is strictly more complete. SPEC recommendation honored.
- ⚖ **policy: item-3 masking fix → option (b)** (unified-driver-loop fallthrough past a single-type queue-exhausted terminal). Option (b) keeps `--next-merged`/`merged_worklist` PURE (honoring the documented "ordering-only, NEVER re-infers per-item state" contract in `user/scripts/CLAUDE.md`); option (a) (resolved-filter inside `merged_worklist`) would violate that contract. Same end-state (actionable bug surfaces); (b) is both more correct and the lighter change. SPEC recommendation honored.

## Phase ordering rationale

The three items are independent defects with no cross-dependencies, so they are phased one-per-item for isolated testability. Item 1 (Phase 1) is the counter-accounting fix (pure `lazy_core` + `lazy-state` Python, hermetic tests). Item 3 (Phase 2) is the merged-view pickup fix (the bare-except breadcrumb is pure Python; the driver-loop fallthrough is SKILL prose mirrored across the coupled pair). Item 2 (Phase 3) is the archive-on-fix parity fix (SKILL prose across the coupled pair + one parity-audit predicate — no `lazy_core` change). Each phase is independently verifiable and committable.

---

### Phase 1: Item 1 — forward-cycle counter advances for inline pseudo-skills (Fix-A)

**Scope:** Make the run-marker `forward_cycles` / `meta_cycles` counters advance correctly for forward-advancing inline pseudo-skill cycles (`__mark_complete__`, `__mark_fixed__`, `__write_validated_from_skip__`, `__write_validated_from_results__`, `__grant_skip_no_mcp_surface__`, `__flip_plan_complete_cloud_saturated__`), which run via `--apply-pseudo` and trigger no Agent dispatch / no guard ALLOW / no registry consume. Implements **Fix-A** (per the ⚖ policy above): advance keyed on a change in the marker-recorded `(feature_id, current_step, sub_skill)` tuple — independent of the consume oracle — so the counter is robust regardless of dispatch style (also closing the Theory-1b verbatim-real-skill miss). The consume-oracle path is preserved as the existing fast-path; the state-change key is the additional, consume-independent advance trigger. Keep both `lazy-state.py --test` and `test_lazy_core.py` green (the shared `lazy_core` change is pipeline-agnostic — `bug-state.py` inherits it).

**Deliverables:**
- [ ] In `lazy_core.py`, add a consume-independent forward/meta advance keyed on a change in the marker-persisted `(feature_id, current_step, sub_skill)` tuple. Implement as a new `advance_forward_cycle(state)` (mirroring `advance_meta_cycle()` at `lazy_core.py:7672`) OR by extending `advance_run_counters` (`lazy_core.py:7590`) to also advance when the recorded last-advance tuple differs from the current `(feature_id, current_step, sub_skill)` even when the consume-count did not rise. Persist the new `last_advance_state_key` (or equivalent) field in the marker; classify `__`-prefixed/falsy `sub_skill` → `meta_cycles`, real → `forward_cycles` (same rule as the existing classifier at `lazy_core.py:7657–7663`). Preserve the existing consume-oracle no-op behavior for bare probe/inject re-fires (no state change AND no consume → no advance, no write).
- [ ] Call the new advance from the `lazy-state.py` `--apply-pseudo` handler (`lazy-state.py:6519–6531`) for forward-advancing pseudo-skills — the handler today advances no counter. Pass the resolved `state` (or the `(feature_id, current_step, sub_skill)` it implies) so a `__mark_complete__`/`__mark_fixed__`/`__write_validated_*`/`__grant_skip_no_mcp_surface__`/`__flip_plan_complete_cloud_saturated__` apply increments `forward_cycles`. Marker-gated (no-op when no run marker), matching `advance_meta_cycle`.
- [ ] Tests: in `test_lazy_core.py`, add hermetic tests (registered via a new `_TESTS = _TESTS + [...]` block, named in the orphan-guard's coverage) asserting: (a) a forward-advancing pseudo-skill apply with NO consume increment still advances `forward_cycles` by 1 (the item-1 regression); (b) a repeated identical `(feature_id, current_step, sub_skill)` with no consume does NOT advance (idempotent across re-fires — preserves the `test_advance_run_counters_consume_gated` invariant at `test_lazy_core.py:12277`); (c) a `__`-prefixed pseudo-skill that is cleanup-class still routes to `meta_cycles`, not `forward_cycles`; (d) a real-skill `sub_skill` change advances `forward_cycles` once even on a verbatim (consume-missed) dispatch (Theory-1b closure).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/test_lazy_core.py` both exit 0 with the new tests included; the new test for case (a) FAILS against the pre-fix `advance_run_counters` (RED-for-the-right-reason: pre-fix it returns the marker unchanged because `current_consume <= prior_consume`) and PASSES after.

**Runtime Verification** *(checked by the hermetic test harness — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python3 user/scripts/test_lazy_core.py` exits 0 with the four new advance tests registered and passing.
- [ ] <!-- verification-only --> `python3 user/scripts/lazy-state.py --test` exits 0 (state-machine smoke harness still green; regenerate `tests/baselines/lazy-state-test-baseline.txt` via `_normalize_smoke_output` ONLY if the byte-pinned output legitimately changed).
- [ ] <!-- verification-only --> `python3 user/scripts/bug-state.py --test` exits 0 (shared `lazy_core` change preserves bug-pipeline behavior).

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; counter correctness is fully covered by the hermetic `--test` harnesses (state-machine code, not an MCP surface).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `advance_forward_cycle()` (or extend `advance_run_counters`) with the consume-independent `(feature_id, current_step, sub_skill)`-change advance + `last_advance_state_key` marker field. REUSE the existing `advance_meta_cycle` (7672) shape and the classifier at 7657–7663; do NOT write a new marker reader/writer (reuse `read_run_marker` + `_atomic_write` already used at 7637/7667).
- `user/scripts/lazy-state.py` — call the new advance from the `--apply-pseudo` handler at 6519–6531 for forward-advancing pseudo-skills.
- `user/scripts/test_lazy_core.py` — new tests in a `_TESTS = _TESTS + [...]` block (follow the existing `test_advance_run_counters_consume_gated` pattern at 12277).

**Testing Strategy:** Pure hermetic unit tests over `lazy_core` with an injected/temp `LAZY_STATE_DIR` (the existing advance tests at 12162–12366 set the marker dir this way). No live runtime, no Agent dispatch — the whole point is that the inline pseudo-skill path is consume-free.

**Integration Notes for Next Phase:**
- The marker gains a `last_advance_state_key` field — any future code reading the marker must treat it as optional (legacy markers lack it; default to None → first state-change always advances, consistent with the legacy-`-1`-consume treatment in `advance_run_counters`).
- This is a shared `lazy_core` change, so BOTH `lazy-state.py --test` and `bug-state.py --test` are acceptance gates (the Coupling Rule in `user/scripts/CLAUDE.md`).

---

### Phase 2: Item 3 — on-disk bugs surface in the unified driver (bare-except breadcrumb + driver-loop fallthrough, option b)

**Scope:** Make `/lazy-batch` (the unified driver) pick up an on-disk bug that is absent from `docs/bugs/queue.json` the way `/lazy-bug-batch` does (bugs-only — features stay strictly queue.json-driven, explicitly out of scope per the operator decision in SPEC Verified Symptom 4). Two seams: (1) replace the silent `except Exception: return []` in `_load_bug_queue_for_merged` (`lazy-state.py:281`) with a guard that emits a `_diag(...)` breadcrumb before degrading, so a bug-side load failure is visible in merged-view diagnostics; (2) implement **option (b)** (per the ⚖ policy above): the unified-driver loop, when the merged head's type-state-script returns a single-type queue-exhausted terminal (e.g. `all-features-complete`), FALLS THROUGH to probe the OTHER type before declaring the whole run done — keeping `--next-merged`/`merged_worklist` PURE (no state inference). Mirrored across the coupled pair (`/lazy-batch` ↔ `/lazy-batch-cloud`).

**Deliverables:**
- [ ] In `lazy-state.py` `_load_bug_queue_for_merged` (256–282): replace the bare `except Exception: return []` at line 281 with a handler that emits a `_diag(f"merged-view bug-side load failed ({exc}) — degrading to features-only")` breadcrumb (so the silent features-only degrade becomes observable) and THEN returns `[]`. Preserve fail-open (a load error must still degrade, never crash the merged view). Keep the existing `not bug_state_path.exists() → return []` early-out (that is an expected no-op, not an error — no breadcrumb needed there).
- [ ] In `lazy-batch/SKILL.md` Step 1 driver loop: add prose for the option-(b) fallthrough — when the merged head is `type==feature` and `lazy-state.py` returns `terminal_reason: all-features-complete` (or `type==bug` and `bug-state.py` returns `all-bugs-fixed`) while the OTHER type's queue (including on-disk bugs via `load_bug_queue`) still has an actionable item, the driver probes the other type before declaring the run terminal. Only when BOTH types are exhausted does the run stop. This keeps `--next-merged` ordering-only; the fallthrough lives entirely in the driver loop.
- [ ] Mirror the option-(b) fallthrough prose into `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` (coupled-pair rule) — adapted for the cloud terminal vocabulary (`cloud-queue-exhausted` stays the cloud-defensive stop; the fallthrough is the same shape with `--cloud` on both state scripts).
- [ ] Tests: in `test_lazy_core.py`, add a test asserting `_load_bug_queue_for_merged` emits a `_diag` breadcrumb on a forced load failure (e.g. point it at a `bug-state.py` that raises on import, or monkeypatch `load_bug_queue` to raise) and still returns `[]`. Add/extend a merged-view fixture asserting that a queue with a stale-Complete feature head AND an on-disk bug surfaces the bug (the existing `test_next_merged_cli_*` family at `test_lazy_core.py:15966+` is the pattern — note ordering is unchanged; this test documents that masking is a DRIVER-loop concern, so it primarily asserts the bug is loadable in `bug_items`).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` exits 0 with the new breadcrumb test; a manual `python3 user/scripts/lazy-state.py --next-merged` over a fixture with an on-disk-only bug returns the bug in the merged list (proving the bug side loads), and the new `_diag` breadcrumb appears in diagnostics when the bug loader is forced to fail.

**Runtime Verification** *(checked by the hermetic test harness — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python3 user/scripts/test_lazy_core.py` exits 0 with the `_load_bug_queue_for_merged` breadcrumb test + the on-disk-bug merged-view test registered and passing.
- [ ] <!-- verification-only --> `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both exit 0.
- [ ] <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py --repo-root <repo> --merged-view` exits 0 (the option-(b) fallthrough prose is mirrored across `/lazy-batch` ↔ `/lazy-batch-cloud` — existing `_MERGED_VIEW_PREDICATES` still satisfied).
- [ ] <!-- verification-only --> `python3 user/scripts/lint-skills.py --check-projected` exits clean (the two SKILL prose edits introduce no broken injections / embedded patterns).

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; merged-view pickup is fully covered by the hermetic `--test` harness and `lazy_parity_audit.py`.

**Prerequisites:** None (independent of Phase 1).

**Files likely modified:**
- `user/scripts/lazy-state.py` — `_load_bug_queue_for_merged` bare-except → `_diag` breadcrumb (line 281). REUSE the existing `_diag(...)` helper already used throughout the file; do NOT add a new logging surface.
- `user/skills/lazy-batch/SKILL.md` — Step 1 driver-loop option-(b) fallthrough prose.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — mirrored fallthrough prose (coupled-pair).
- `user/scripts/test_lazy_core.py` — breadcrumb test + on-disk-bug merged-view test (`_TESTS = _TESTS + [...]`; follow `test_next_merged_cli_*` at 15966+).

**Testing Strategy:** Hermetic unit tests for the bare-except breadcrumb (force a load failure, assert the `_DIAGNOSTICS` entry + `[]` return) and for the merged-view loadability of an on-disk-only bug. The SKILL prose fallthrough is validated structurally by `lazy_parity_audit.py --merged-view` (asymmetry across the coupled pair = a finding) + `lint-skills.py`; the prose is not a code path the `--test` harness executes.

**Integration Notes for Next Phase:**
- Features stay strictly queue.json-driven — do NOT add an on-disk feature fallback (explicitly out of scope, SPEC Verified Symptom 4 + Proven Findings item 3.3).
- `merged_worklist`/`next_merged` stay PURE ordering — option (b) was chosen precisely so no state-inference leaks into them. Any future temptation to filter resolved heads there must re-open the "ordering-only" contract decision, not silently add it.
- The two stale-Complete FEATURE entries that lingered in the motivating run are a separate one-time residue (a hand trim), NOT a code defect — out of scope for this phase (noted in SPEC Proven Findings item 2).

---

### Phase 3: Item 2 — unified driver archives fixed bugs (wire the `--archive-fixed` chain + parity predicate)

**Scope:** Wire the `--archive-fixed` follow-up into the unified `/lazy-batch` so a `type==bug` cycle that reaches `__mark_fixed__` archives the fixed bug with full parity to `/lazy-bug-batch` (`git mv` to `docs/bugs/_archive/` + inbound-ref repoint + `docs/bugs/queue.json` trim + atomic commit). Today `/lazy-batch` Step 1c.5 has **no `__mark_fixed__` block at all** — it lists only feature pseudo-skills, so a bug terminal under the unified driver flips the receipt but never archives/de-queues (the hand-trim workaround this bug exists to remove). The fix is SKILL prose + orchestration wiring only — NO `lazy_core.py` change (the `apply_pseudo` `is_fixed` trim predicate at `lazy_core.py:3203` and the `archive_fixed` function/CLI at `bug-state.py:3979/4463` are already correct). Mirror into `/lazy-batch-cloud` (coupled-pair rule) and extend `lazy_parity_audit.py` to assert the chain is present.

**Deliverables:**
- [ ] In `lazy-batch/SKILL.md` Step 1c.5 (466–499): add a `__mark_fixed__` pseudo-skill block mirroring `/lazy-bug-batch` Step 1c.5 (`lazy-bug-batch/SKILL.md:378–430`) — the two inline docs-only gates (Gate 1 MCP-coverage audit, Gate 2 completion-integrity, adapted `kind: fixed` / `filename: FIXED.md`), then `python3 ~/.claude/scripts/bug-state.py --apply-pseudo __mark_fixed__ {spec_path}` (script-owned receipt + status flip + sentinel cleanup), then the chained `python3 ~/.claude/scripts/bug-state.py --repo-root {repo_root} --archive-fixed {spec_path}` (script-owned `git mv` + ref repoint + queue trim + commit), with the `ok: false` → `BLOCKED.md (blocker_kind: archive-failure)` handling and the push backstop — exactly as the bug-batch block specifies. Add `__mark_fixed__` to the Step-1c.5 forward-cycle counter list (step 5, line 497) so the bug terminal advances `forward_cycles` (consistent with Phase 1).
- [ ] Mirror the same `__mark_fixed__` block into `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` Step 1c.5 (377+), adapted for cloud (`bug-state.py --cloud` for the gates' state probes where applicable; bug validation is docs-only and reachable in cloud per the cloud twin's own Differences table line 945, so `__mark_fixed__` + `--archive-fixed` run identically in cloud).
- [ ] In `lazy_parity_audit.py`, add a predicate `(r"--archive-fixed", "bug archive --archive-fixed chain")` to `_MERGED_VIEW_PREDICATES` (360–371) so `audit_merged_view_dispatch_parity` (374) asserts BOTH the workstation driver AND its cloud mirror chain `--archive-fixed` for the bug terminal — the parity the SPEC Coupling/parity row requires (a driver missing the chain becomes a finding).
- [ ] Tests: in `test_lazy_core.py`, add a `lazy_parity_audit` test asserting the new `--archive-fixed` predicate is enforced — over a fixture (or the real repo paths) where a driver missing the `--archive-fixed` mention produces a finding, and the corrected drivers produce none. (Follow the existing parity-audit test pattern if present; otherwise call `lazy_core`/`lazy_parity_audit` directly against a temp SKILL fixture.)

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py --repo-root <repo> --merged-view` exits 0 AFTER both SKILL files carry the `__mark_fixed__` / `--archive-fixed` chain, and exits 1 (naming the missing driver) if either driver drops it — RED-for-the-right-reason: against the pre-fix `/lazy-batch` (no `__mark_fixed__` block) the new predicate FAILS.

**Runtime Verification** *(checked by the parity audit + lint — NOT by the implementation agent):*
- [ ] <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py --repo-root <repo> --merged-view` exits 0 (both drivers chain `--archive-fixed`; the new predicate is satisfied).
- [ ] <!-- verification-only --> `python3 user/scripts/lazy_parity_audit.py --repo-root <repo>` exits 0 (full audit — the manifest pairs + state-script + merged-view checks all pass; the new `__mark_fixed__` block did not break the existing `lazy-batch` ↔ `lazy-bug-batch` / `lazy-batch-cloud` parity).
- [ ] <!-- verification-only --> `python3 user/scripts/test_lazy_core.py` exits 0 with the new `--archive-fixed` parity-predicate test registered and passing.
- [ ] <!-- verification-only --> `python3 user/scripts/lint-skills.py --check-projected` exits clean (the two SKILL `__mark_fixed__` blocks introduce no broken injections / embedded-pattern violations).

**MCP Integration Test Assertions:** N/A — no runtime-observable app behavior; archive-chain parity is fully covered by `lazy_parity_audit.py` + `lint-skills.py` (SKILL-prose + orchestration wiring, no MCP surface).

**Prerequisites:** None functionally (independent of Phases 1–2). Logically reads `/lazy-bug-batch` Step 1c.5 as the verbatim parity reference.

**Files likely modified:**
- `user/skills/lazy-batch/SKILL.md` — new `__mark_fixed__` block in Step 1c.5 (mirror of `lazy-bug-batch/SKILL.md:378–430`) + add `__mark_fixed__` to the forward-cycle list at line 497.
- `repos/algobooth/.claude/skills/lazy-batch-cloud/SKILL.md` — mirrored `__mark_fixed__` block (coupled-pair).
- `user/scripts/lazy_parity_audit.py` — new `(r"--archive-fixed", ...)` entry in `_MERGED_VIEW_PREDICATES`. REUSE the existing predicate loop in `audit_merged_view_dispatch_parity`; do NOT add a new audit function.
- `user/scripts/test_lazy_core.py` — parity-predicate test (`_TESTS = _TESTS + [...]`).

**Testing Strategy:** Structural — `lazy_parity_audit.py --merged-view` is the acceptance gate (it greps both driver SKILLs for the `--archive-fixed` chain; an asymmetry is a finding). The hermetic test exercises the new predicate over a positive (chain present) and negative (chain absent) fixture. No `lazy_core.py` behavior change, so no new `lazy_core` unit test for the archive mechanics themselves (already covered by the existing `archive_fixed` tests).

**Integration Notes for Next Phase:**
- No `lazy_core.py` / `bug-state.py` change — resist any temptation to "fix" the trim in `apply_pseudo`'s `is_fixed` branch; it is correct BY DESIGN (the bug queue trim lives in `archive_fixed` step 6, per the `lazy_core.py:3187` comment). The ONLY gap was the missing chained call in the driver prose.
- REVERSE-REFERENCE: no spin-off bug/feature was created this cycle — all three items are in-scope and planned here. The two stale-Complete feature residue entries (SPEC Proven Findings item 2) are a one-time hand trim, explicitly NOT a code defect, so no spin-off doc.

---

**Completion (gate-owned):** the `__mark_fixed__` gate (orchestrator-owned, after the validation tail: `/mcp-test` → coverage audit) flips SPEC.md/PHASES.md `**Status:**` to `Fixed`, writes `FIXED.md`, and archives this bug dir to `docs/bugs/_archive/`. This plan NEVER authors those — they are not checkbox rows here.
