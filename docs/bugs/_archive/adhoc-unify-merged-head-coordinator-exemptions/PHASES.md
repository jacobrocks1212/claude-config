# Implementation Phases — Unify merged-head coordinator-emission exemptions

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure behavior-preserving Python refactor of state-script `--emit-prompt` dispatch logic; no app integration, no MCP-reachable surface (claude-config has no MCP server). The regression net is the state scripts' `--test` baselines, not a live runtime.

## Validated Assumptions

The Step 2.7 Runtime Assumption Validation gate is **skipped** — every load-bearing assumption is **code-provable** and the change is a behavior-preserving refactor with snapshot (baseline) coverage:

- **No user-facing surface.** This is internal state-script dispatch tooling; the reachability axiom does not apply (nothing a user reaches end-to-end).
- **Behavior preservation is baseline-asserted, not runtime-observed.** The two `--test` baselines (`tests/baselines/{lazy,bug}-state-test-baseline.txt`) are the regression net; byte-identical output before and after IS the proof, and it is a static/deterministic check, not a runtime observation.
- **The lease facet's I/O is preserved identically.** The new predicate calls the SAME `lazy_coord.has_live_lease(leases_path, feature_id)` the callers call today, with the SAME fail-safe-to-False semantics (any read error / no `leases.json` / no live lease → no exemption) — so no new runtime-coupled behavior is introduced; the existing behavior is relocated.

**SPEC-example capability audit:** the SPEC's code examples consume only already-existing symbols — `lazy_coord.has_live_lease` (`lazy_coord.py:970`, registered, no rejection path), `lazy_core.claude_state_dir()`, and the `_emit_marker`/`state["feature_id"]` locals present in both callers today. No consumed construct is explicitly rejected. `how-confirmed: grep` — all symbols resolve to live definitions.

**MCP tool-existence audit:** no-op — no `.claude/skill-config/mcp-tool-catalog.md` configured for claude-config (no MCP surface).

## Cross-feature Integration Notes

No hard deps on Complete upstreams (this is a bug-pipeline refactor). Related prior art is read-context only: `parallel-worktree-batch-execution` / `lazy-batch-parallel-run-harness-gaps` (the two rounds that accreted the lane and lease exemptions), `merged-head-actionability-oracle`, and `docs/bugs/dispatch-probe-and-inject-bypass-merged-head` (the guard's origin). None constrains a phase boundary here.

---

### Phase 1: Extract the `coordinator_arbitrated_emission` predicate (pure addition)

**Status:** Fixed

**Scope:** Add a new predicate `coordinator_arbitrated_emission(marker, feature_id, leases_path) -> None | str` to `user/scripts/lazy_core/dispatch.py`, next to `merged_head_override`. It answers the single question the two ad-hoc booleans express today — *"is this a coordinator-arbitrated emission the serial merged-head divergence premise does not apply to?"* — and returns the exemption **reason** (a stable short string) or `None`:

- `"lane"` — `marker` is a dict with a truthy `parent_run` (coordinator-authorized lane probe; round-1 gap 1). Pure marker read.
- `"lease"` — not a lane, `feature_id` is set, AND `feature_id` holds a live coordinator lease (serial-tail in-flight completion; round-2 gap 8). Delegates the liveness I/O to `lazy_coord.has_live_lease(leases_path, feature_id)`.
- `None` — neither exemption applies; the caller runs the merged-head guard exactly as before.

The single return value drives BOTH the caller's skip decision AND its observability diagnostic (the caller maps the reason string to its existing per-reason diag line), collapsing the two-boolean fragmentation into one predicate. This phase is a **pure addition** — no caller is switched yet, so the state scripts' output is unchanged and the baselines cannot move.

**Deliverables:**
- [x] `coordinator_arbitrated_emission(marker, feature_id, leases_path)` added to `lazy_core/dispatch.py` (adjacent to `merged_head_override`), returning `None | "lane" | "lease"`. Lane precedence over lease (a lane never also evaluates the lease branch — matches the current `not _emit_is_lane` guard on the lease compute).
- [x] Fail-safe by construction, mirroring the current callers and `merged_head_override`'s contract: a `parent_run`/marker read error → not a lane; a lease-check exception / unavailable `lazy_coord` / no `leases.json` / no live lease → not a lease → `None`. The predicate must NEVER raise into the base probe. The `lazy_coord` dependency is obtained via a local (lazy) import inside a `try/except` so `dispatch.py` keeps its current top-level-import-light shape and the predicate is testable without a hard module coupling (see Integration Notes).
- [x] A module-level docstring recording that this predicate is the single home for coordinator-arbitration exemptions and that a future third exemption (the anticipated demoted-serial-rerun carve-out) is a one-line addition HERE, in ONE place, returning a new reason string — the anti-accretion contract this bug delivers.
- [x] Tests: unit cases in `user/scripts/tests/test_lazy_core/test_dispatch.py` covering all four outcomes — lane (`parent_run` set) → `"lane"`; live lease (no `parent_run`, `feature_id` leased) → `"lease"`; neither → `None`; and the fail-safe paths (marker `None`, missing `feature_id`, `has_live_lease` raising / no `leases.json`) → `None`. Include a case asserting lane takes precedence when both a `parent_run` and a live lease would qualify.

**Implementation Notes (2026-07-19):**
- Added `coordinator_arbitrated_emission(marker, feature_id, leases_path) -> str | None` + `coordinator_exemption_diag(reason)` + the `_COORDINATOR_EXEMPTION_DIAGS` map to `user/scripts/lazy_core/dispatch.py`, immediately after `merged_head_override`. Lane check (`marker.get("parent_run")`) is evaluated first (precedence); the lease branch does a LOCAL `import lazy_coord` inside a `try/except` (ImportError / any read error → `None`), delegating to `lazy_coord.has_live_lease(leases_path, feature_id)`. No top-level `import lazy_coord` added.
- The diag map stores the two historical messages VERBATIM (`"lane"`/`"lease"`); an unrecognized reason resolves to a generic `coordinator-arbitrated emission (exemption reason: <reason>)` diag — the forward-compat contract for the future demoted-serial-rerun exemption.
- 6 unit tests added to `test_dispatch.py` (registered in `_TESTS`): lane / lease / none / lane-precedes-lease / fail-safe / diag-map. Lease tests seed a live lease via `lazy_coord.acquire_lease(...)` in a `tempfile.TemporaryDirectory`.
- Pure addition — no caller switched, so both `--test` baselines are byte-unchanged (verified: `lazy-state.py --test` / `bug-state.py --test` exit 0; parity exit 0; full `test_dispatch.py` 186 passed).

**Minimum Verifiable Behavior:** `python3 -m pytest user/scripts/tests/test_lazy_core/test_dispatch.py -k coordinator_arbitrated -q` runs GREEN — the new predicate returns the correct reason (or `None`) for lane / lease / neither / fail-safe inputs, driven through the real function.

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior in this phase (pure predicate; verified by unit test).

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core/dispatch.py` — add `coordinator_arbitrated_emission` next to `merged_head_override` (@358); reuse the same pure/fail-safe idiom (local import of the one external dependency, like `from .depdag import next_merged`).
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — add the four-outcome unit cases; reuse the file's existing `tempfile`/`json` helpers to seed a `leases.json` for the `"lease"` case (or pass `now=` to `has_live_lease` via a seeded lease dict).

**Testing Strategy:** The predicate is pure w.r.t. its inputs except the single `has_live_lease` I/O, which is exercised by writing a real temp `leases.json` (live vs. expired vs. absent). No state-script invocation needed; the predicate is tested directly. Because no caller uses it yet, the `--test` baselines are untouched this phase (assert them unchanged as a sanity check).

**Integration Notes for Next Phase:**
- **`lazy_coord` layering.** `lazy_coord` is a top-level script module, NOT under `lazy_core/`. To keep `dispatch.py` decoupled and unit-testable, obtain `has_live_lease` via a local `import lazy_coord` inside the lease branch's `try/except` (fail-safe to no-lease on `ImportError` or any read error) — do NOT add a top-level `import lazy_coord` to `dispatch.py`. This preserves the exact 3-arg SPEC signature `(marker, feature_id, leases_path)` while the callers keep passing `lazy_core.claude_state_dir() / "leases.json"` as `leases_path`.
- **Reason-string contract.** The two reason strings `"lane"` / `"lease"` are the caller's map keys for the existing diagnostic lines. Phase 2 depends on these exact values; keep them stable and covered by a test so a future rename can't silently drop a diagnostic.
- **Reason completeness for the future third exemption.** The predicate's shape (return a reason or `None`) is what makes demoted-serial-rerun a one-line add later — Phase 2's caller diag-map should be written so an unrecognized/new reason still skips the guard and emits a generic "coordinator-arbitrated emission" diag rather than silently dropping observability.

---

### Phase 2: Switch both state-script callers to the predicate (behavior-preserving swap)

**Status:** Complete

**Scope:** Replace the two separately-computed booleans (`_emit_is_lane`, `_emit_is_lease_held`), their inline AND in the guard condition, and the two observability `elif` branches — in BOTH `lazy-state.py` (~14803-14965) and `bug-state.py` (~10062-10225) — with a single `coordinator_arbitrated_emission(...)` call. The caller computes the exemption reason ONCE, skips the merged-head guard when the reason is non-`None`, and emits the matching observability diagnostic from a small reason→message map (preserving today's two diag lines verbatim in substance). The coupled pair stays byte-parallel: both callers get the identical unified shape. This is a **pure refactor** — the `--emit-prompt`/`--probe` JSON and terminal routing MUST be byte-identical before and after.

**Deliverables:**
- [x] `lazy-state.py` guard prologue rewritten to a single `_emit_exempt_reason = lazy_core.dispatch.coordinator_arbitrated_emission(_emit_marker, state.get("feature_id"), lazy_core.claude_state_dir() / "leases.json")`; the guard becomes `if _emit_marker is not None and _emit_exempt_reason is None:`; the two `elif _emit_is_lane` / `elif _emit_is_lease_held` observability branches become a single `elif _emit_exempt_reason is not None:` that selects the existing per-reason diag text (lane vs. lease) — preserving both messages' content.
- [x] `bug-state.py` given the byte-parallel identical replacement (coupled-pair mirror), including its mirror comments updated to point at the shared predicate as the single home.
- [x] The two mirror-comment blocks and the `lazy_coord` import annotations (`lazy-state.py:77-82`, `bug-state.py:97-100`) updated to reflect that the exemptions now live in one shared predicate. ⚖ The top-level `import lazy_coord` became DEAD (its only consumer moved into the predicate's local import in `dispatch.py`); it was REMOVED from both scripts (annotation records the move) — behavior-preserving, proven by the byte-unchanged `--test` baselines.
- [x] `lazy_parity_audit.py --repo-root .` re-run to exit 0; the parity manifest does NOT pin the content of the changed mirrored blocks, so no `lazy-parity-manifest.json` reconciliation was needed.
- [x] Tests: the Phase-1 predicate unit tests continue GREEN; a `test_dispatch.py` assertion (`test_coordinator_exemption_diag_maps_reason_to_text`) covers the caller-facing reason→diagnostic mapping for `"lane"`/`"lease"` + the generic unrecognized-reason fallback (diag-preservation contract). No new baseline rows.

**Implementation Notes (2026-07-19):**
- Both callers' guard prologues (`lazy-state.py` ~14803, `bug-state.py` ~10062) rewritten byte-parallel: the two ad-hoc booleans (`_emit_is_lane`, `_emit_is_lease_held`) + inline AND + two observability `elif`s collapsed into one `_emit_exempt_reason = lazy_core.dispatch.coordinator_arbitrated_emission(...)` call, guard `if _emit_marker is not None and _emit_exempt_reason is None:`, and a single `elif _emit_exempt_reason is not None:` emitting `lazy_core.dispatch.coordinator_exemption_diag(_emit_exempt_reason)`.
- The two historical diagnostic strings are preserved VERBATIM inside `_COORDINATOR_EXEMPTION_DIAGS` (dispatch.py), so `--emit-prompt`/`--probe` output — including the diag lines — is byte-identical.
- Dead-import removal (⚖ scope-class, most-complete path): the now-orphaned top-level `import lazy_coord` retired from both scripts (nothing pins it — parity manifest/audit don't reference it; tests import it locally).
- Regression net GREEN: `test_markers.py` byte-identical baseline tests (2 passed), `lazy_parity_audit.py --repo-root .` exit 0, the 4 end-to-end merged-head exemption subprocess tests (lane-skip / lease-skip / no-lease-withhold / p0-bug-withhold) pass through the REAL state scripts, `test_dispatch.py` 186 passed, plus the full `test_lazy_core/` suite (644 + batch-3).
- Anti-accretion outcome delivered: a future third exemption (demoted-serial-rerun) is now a one-line reason branch in `coordinator_arbitrated_emission` + one `_COORDINATOR_EXEMPTION_DIAGS` entry, not a fourth ad-hoc boolean re-accreted at each caller.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both PASS with their committed baselines **unchanged** (byte-identical) — the refactor preserved every `--emit-prompt`/`--probe` output. `python3 user/scripts/lazy_parity_audit.py --repo-root .` exits 0.

**MCP Integration Test Assertions:** N/A — behavior-preserving refactor; correctness is proven by the unchanged `--test` baselines and the parity audit, not a runtime MCP assertion.

**Prerequisites:**
- Phase 1: `coordinator_arbitrated_emission` exists in `lazy_core/dispatch.py` with the stable `"lane"`/`"lease"` reason strings and passing unit tests.

**Files likely modified:**
- `user/scripts/lazy-state.py` — replace the guard prologue booleans + inline AND + two observability elifs with one predicate call + reason→diag map (~14803-14965).
- `user/scripts/bug-state.py` — identical parity-mirrored replacement (~10062-10225).
- `user/scripts/lazy-parity-manifest.json` — reconcile only if it pins the changed block content (run the audit first; edit only if it flags).
- `user/scripts/tests/test_lazy_core/test_dispatch.py` — extend caller-facing reason→diag coverage if not already covered.

**Testing Strategy:** The load-bearing proof is the two `--test` baselines remaining byte-identical (behavior preserved) plus `lazy_parity_audit.py` exit 0 (coupled pair still parallel). Run both state scripts' `--test` under the ~10-min cap individually (they are separate under-cap commands — never background them). If a baseline moves, the refactor changed behavior and must be corrected until the baselines match the committed net exactly.

**Integration Notes for Next Phase:** None — Phase 2 is terminal. On landing, the anticipated demoted-serial-rerun exemption becomes a one-line addition inside `coordinator_arbitrated_emission` (a new reason branch) plus one diag-map entry in each caller — the anti-accretion outcome this bug delivers.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to `Fixed` and writes `FIXED.md` once this phase's regression net (both `--test` baselines unchanged + parity audit green) passes through the validation tail. This plan never flips the top-level status itself.
