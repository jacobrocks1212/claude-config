# Implementation Phases — Concurrent Same-Branch Walkers Have No Arbitration

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure harness-script (`lazy_core.py` / state-machine) change with no AlgoBooth app surface; per docs/features/mcp-testing/SPEC.md it falls in the "build/tooling, no app integration" untestable class. Validation is the in-file `--test` smoke harness + `test_lazy_core.py` + `lazy_parity_audit.py`, not the Tauri/MCP runtime.

## Validated Assumptions

All load-bearing assumptions for this fix are **code-provable** (read directly from `lazy_core.py` during the Touchpoint Audit) — no runtime-coupled assumption requires a live spike:

- **`refuse_run_start_clobber`'s same-pipeline early return is at `lazy_core.py:8735–8736`** — confirmed by Read. The function reads the marker RAW, honors 24h age-staleness, and currently returns unconditionally on `existing_pipeline == incoming_pipeline`.
- **The checkpoint file is on disk at clobber-check time** — confirmed from `lazy-state.py`'s `--run-start` handler order: `refuse_run_start_clobber("feature")` runs BEFORE `consume_run_checkpoint()` (the consume-and-delete). So a non-destructive existence read of `lazy-run-checkpoint.json` is available as the resume discriminator without reordering anything.
- **Checkpoint filename + path chokepoint** — `_CHECKPOINT_FILENAME = "lazy-run-checkpoint.json"` (`lazy_core.py:5878`); the marker and checkpoint resolve through the same `claude_state_dir(create=False)` keyed dir the refuse function already uses for the marker. The existence check is `(claude_state_dir(create=False) / _CHECKPOINT_FILENAME).exists()` — no parse, no consume.
- **`consume_run_checkpoint()` is the ONLY consumer** (`lazy_core.py:10606`, read-and-DELETE); `write_run_checkpoint` (`lazy_core.py:10568`) is the ONLY producer (written exclusively by `--run-end --reason checkpoint`). A fresh second walker never has this file.
- **Shared helper → both pipelines** — `bug-state.py` calls `refuse_run_start_clobber("bug")`; the fix in the shared `lazy_core` helper lands on both pipelines and is audited by `lazy_parity_audit.py`.

## Touchpoint Audit (verified against the codebase — read-only)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `refuse_run_start_clobber(incoming_pipeline, *, now)` (8665), `_CHECKPOINT_FILENAME` (5878), `claude_state_dir`, `_MARKER_FILENAME`, `_MARKER_STALE_SECONDS` | refactor | Split the existing same-pipeline early return (`lazy_core.py:8735–8736`). Reuse `claude_state_dir(create=False) / _CHECKPOINT_FILENAME` + `.exists()` — do NOT call `consume_run_checkpoint()` (it deletes the resume signal). Mirror the existing cross-pipeline refusal's stderr/`sys.exit(3)` shape for the new same-pipeline-concurrent refusal. |
| `user/scripts/lazy-state.py` | yes | feature `--run-start` handler (~7378–7398): `refuse_if_cycle_active` → `refuse_run_start_clobber("feature")` → `write_run_marker` → (later, ~7403) `consume_run_checkpoint()` | verify-only | NO logic change. The guard call already exists and runs before the checkpoint consume — confirm only. |
| `user/scripts/bug-state.py` | yes | `refuse_run_start_clobber("bug")` call | inherits | Inherits the fix via the shared helper; verify parity via `lazy_parity_audit.py`. NO direct edit expected. |
| `user/scripts/test_lazy_core.py` | yes | `_capture_clobber_refusal(incoming_pipeline, now)` (17472), `_set_state_dir`/`_clear_state_dir`, existing clobber fixtures (17491–17569), `write_run_marker`, `write_run_checkpoint` | extend | Add same-pipeline fixtures mirroring the existing `_capture_clobber_refusal` style. Use `write_run_checkpoint(...)` to seed the resume-present case. |
| `user/scripts/CLAUDE.md` | yes | "Same-repo refusal / cross-repo concurrency" / "Same-repo second run" prose | edit | Update to state same-pipeline concurrent same-repo runs are now refused (checkpoint-discriminated); add reverse-reference to this bug. |
| `CLAUDE.md` (root) | yes | hooks/architecture prose | edit | Note the closed `multi-repo-concurrent-runs` residual gap; reverse-reference this bug. |

**Drift correction:** none required — every SPEC-named path verified `exists: yes` with the SPEC's cited line numbers matching reality (`refuse_run_start_clobber` ≈ 8665; same-pipeline return 8735–8736). No design fork (both Open Questions are pre-resolved scope-class per SPEC §Open Questions).

## Phase 1: Checkpoint-discriminated same-pipeline concurrent-walker refusal

**Scope:** Extend `refuse_run_start_clobber` (`lazy_core.py`) so the same-pipeline branch no longer returns unconditionally. Before allowing the overwrite, check whether `lazy-run-checkpoint.json` is present (non-destructively). A live, age-fresh, same-pipeline marker WITH the checkpoint file present is a sanctioned resume → allow (current behavior). The SAME marker WITHOUT the checkpoint file is a genuinely-concurrent second walker → REFUSE (exit 3, zero side effects), naming the in-flight run's `started_at`/`forward_cycles`. The fix lands on BOTH pipelines via the shared helper. This is a single, self-contained, fully-testable phase — the SPEC scopes exactly one fix site with four enumerated test cases and no cross-component seams.

**Deliverables:**
- [x] In `lazy_core.py::refuse_run_start_clobber`, replace the unconditional `existing_pipeline == incoming_pipeline` early return (lines ~8735–8736) with a checkpoint-discriminated split: read `(claude_state_dir(create=False) / _CHECKPOINT_FILENAME).exists()` (existence only — NEVER `consume_run_checkpoint`, which deletes the resume signal the handler consumes later); if the checkpoint file is present → `return` (sanctioned resume, allow overwrite); if absent → fall through to a same-pipeline-concurrent refusal.
- [x] Add the same-pipeline-concurrent refusal branch: write a diagnostic to `sys.stderr` naming the in-flight run (`started_at`, `forward_cycles` if present in the marker, `session_id`) and the operator instruction (the other walker is live on this branch; STOP, do not start a second walker; if the run is genuinely dead `--run-end` it from its own orchestrator), then `sys.exit(3)`. Mirror the message shape + zero-side-effects guarantee of the existing cross-pipeline refusal so both refusals read consistently and match the `multi-repo-concurrent-runs` "Same-repo second run" UX promise.
- [x] Update the `refuse_run_start_clobber` docstring: the same-pipeline branch is now checkpoint-discriminated (not an unconditional allow); spell out the checkpoint-file-absence discriminator and the non-destructive read requirement (must not consume the resume signal it gates on). Remove/correct the stale "A SAME-pipeline re-`--run-start` … is ALLOWED to overwrite" wording that asserts the unconditional allow.
- [x] Preserve all existing allow paths unchanged: missing/corrupt/unparseable marker → fail-open allow; >24h age-stale marker → allow (presumed-dead reclaim); blank/absent pipeline field → fail-open allow; cross-pipeline live marker → unchanged exit-3 refusal.
- [x] Tests (`test_lazy_core.py`): add same-pipeline fixtures mirroring `_capture_clobber_refusal` style — (a) same-pipeline live marker + NO checkpoint → exit-3 refusal (assert code 3, marker untouched, message names the in-flight run); (b) same-pipeline live marker + checkpoint present (seed via `write_run_checkpoint(...)`) → allow (`code is None`, resume preserved); (c) same-pipeline >24h-stale marker → allow (reclaim preserved); (d) confirm cross-pipeline behavior is unchanged (existing fixture still green). Assert the existing `test_run_start_clobber_allows_same_pipeline_resume` fixture is updated to seed a checkpoint file (its name now means "resume WITH checkpoint" — without a checkpoint it would now correctly refuse).
- [x] Docs: update `user/scripts/CLAUDE.md` ("Same-repo refusal / cross-repo concurrency" + "Same-repo second run") to state same-pipeline concurrent same-repo runs are now refused (checkpoint-discriminated), closing the `multi-repo-concurrent-runs` residual gap; add a reverse-reference to this bug (`docs/bugs/concurrent-same-branch-walkers-no-arbitration`). Update root `CLAUDE.md` where it describes the run-start clobber refusal to note the same-pipeline-concurrent leg + reverse-reference this bug.
- [x] Tests: run the full coupled set per the SPEC Coupling Rule — `python3 lazy-state.py --test`, `python3 bug-state.py --test`, `python3 test_lazy_core.py`, `python3 lazy_parity_audit.py` — all green (the helper is shared/coupled; both pipelines must stay byte-pinned against their baselines).

#### Implementation Notes (2026-06-20)

**Work completed:** Split the unconditional same-pipeline early return in `refuse_run_start_clobber` (`lazy_core.py`) into a checkpoint-discriminated branch. Same-pipeline + `lazy-run-checkpoint.json` present → allow (sanctioned resume, unchanged); same-pipeline + checkpoint absent + marker live + age-fresh → refuse (exit 3, zero side effects) with a diagnostic naming the in-flight run's `started_at`/`forward_cycles`/`session_id`. The checkpoint is read existence-only via `(claude_state_dir(create=False) / _CHECKPOINT_FILENAME).exists()` — NEVER `consume_run_checkpoint()`. Docstring corrected. All prior allow paths (missing/corrupt marker, >24h age-stale, blank pipeline) and the cross-pipeline refusal are unchanged.

**Tests:** 4 new fixtures in `test_lazy_core.py` (`..._refuses_same_pipeline_concurrent_no_checkpoint`, `..._allows_same_pipeline_with_checkpoint_present`, `..._allows_same_pipeline_age_stale`, `..._cross_pipeline_unchanged_with_checkpoint`) + the existing `test_run_start_clobber_allows_same_pipeline_resume` updated to seed a checkpoint. Confirmed RED-before-GREEN: fixture 1 failed with "got None" against the pre-fix unconditional-allow code, passes after the discriminator landed.

**Review verdict:** PASS — diff scoped to the one function + its tests + 2 doc files; `consume_run_checkpoint` appears in the diff ONLY in docstring/comment "never call this" warnings, never as a call; cross-pipeline branch byte-unchanged.

**Files modified:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`, `user/scripts/CLAUDE.md`, `CLAUDE.md` (root), this PHASES.md, the plan file.

**Gates:** all four coupled gates green — `test_lazy_core.py` 687/687, `lazy-state.py --test` all passed, `bug-state.py --test` all passed, `lazy_parity_audit.py` exit 0 (the shared helper lands on both pipelines for free).

**Pitfall note (carry forward):** the checkpoint read in the refuse path MUST stay an existence check. NEVER call `consume_run_checkpoint()` from `refuse_run_start_clobber` — it deletes the resume signal the `--run-start` handler legitimately consumes at a LATER step (~`lazy-state.py:7403`). If a future change reorders the handler to consume before the clobber guard, this discriminator breaks.

**Minimum Verifiable Behavior:** `python3 user/scripts/test_lazy_core.py` runs green with the new same-pipeline fixtures, AND a manual hermetic check: write a live feature marker via `write_run_marker(pipeline="feature", ...)` with NO checkpoint file, then `refuse_run_start_clobber("feature")` exits 3 with the marker file untouched; seed a checkpoint via `write_run_checkpoint(...)` and the same call returns without exiting. This is runnable today against the helper — no app runtime needed.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — split the same-pipeline branch in `refuse_run_start_clobber`; checkpoint-absence discriminator + new refusal + docstring correction.
- `user/scripts/test_lazy_core.py` — four same-pipeline fixtures; update the existing same-pipeline-resume fixture to seed a checkpoint.
- `user/scripts/CLAUDE.md` — document the closed gap + reverse-reference.
- `CLAUDE.md` (root) — note the same-pipeline-concurrent refusal leg + reverse-reference.
- (verify-only, no edit expected) `user/scripts/lazy-state.py`, `user/scripts/bug-state.py` — confirm the guard call + handler order; parity inherited via the shared helper.

**Testing Strategy:** Pure hermetic unit testing via the in-file `--test` smoke harnesses + `test_lazy_core.py`, using `_set_state_dir` temp-dir fixtures and injected `now` for deterministic age comparison (the existing clobber fixtures already establish this pattern). No mocks beyond the existing state-dir override. The discriminator (checkpoint-file presence) is seeded with the real `write_run_checkpoint` producer, so the test exercises the genuine resume signal, not a fabricated stand-in. Parity across both pipelines is asserted mechanically by `lazy_parity_audit.py` rather than by a duplicated bug-state fixture.

**Integration Notes for Next Phase:** None — single-phase fix. For any follow-on: the non-destructive checkpoint read MUST stay an existence check; never call `consume_run_checkpoint()` from the refuse path (it deletes the resume signal the `--run-start` handler consumes at ~line 7403, AFTER this guard). If a future change reorders the handler to consume the checkpoint before the clobber guard, this discriminator breaks — re-verify the handler order if that path is ever touched.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed` and writes `FIXED.md` once this phase's work lands and the validation tail certifies it. This plan never flips the top-level status or writes the receipt.

---
