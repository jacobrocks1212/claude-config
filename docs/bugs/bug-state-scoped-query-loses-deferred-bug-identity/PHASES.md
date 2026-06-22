# Implementation Phases — Scoped `--bug-id` query loses a deferred bug's identity

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure CLI/tooling defect in claude-config's Python state scripts + the stdlib-only `pipeline_visualizer`/`lazy-queue-doc.py` renderers. There is no Tauri app, no MCP-reachable surface, and no audio/UI behavior. Validation is the in-file `--test` smoke harnesses (`bug-state.py --test`, `lazy-state.py --test`), `test_lazy_core.py`, the curated-stage/probe/queue-doc unit tests, and `lazy_parity_audit.py` — all deterministic CLI checks. (Per the mcp-testing SPEC's untestable classes: "build tooling / non-app CLI" is structurally outside MCP reach.)

## Cross-feature Integration Notes

No hard deps on Complete upstream features. This bug fixes existing claude-config tooling in place; the relevant invariants are the COUPLING RULE in `user/scripts/CLAUDE.md` (change the state machine in the script, keep `--test` green, keep the coupled pair + parity audit in lockstep) and the curated-stage display contract in `pipeline_visualizer/curated_stage.py`. Those are honored per-phase below, not consumed from an upstream PHASES.md.

---

### Phase 1: Identity-preserving scoped skip-branches in `bug-state.py` (primary root cause)

**Scope:** When `--bug-id` is set and the matched queue entry is a *skipped-but-matched* entry (operator-deferred via `DEFERRED.md`, cloud-saturated, device-saturated, or parked), return a **scoped** `_bug_state(...)` carrying `feature_id`/`feature_name`/`spec_path` plus a per-bug deferred `current_step`/`terminal_reason` from INSIDE the loop — instead of `continue`-ing into the global null-identity terminal in the no-actionable block. The UNSCOPED path (no `--bug-id`) keeps emitting the existing global terminals byte-for-byte, so `/lazy-bug-batch` queue-advance is unaffected.

This is the primary fix. Model the scoped early-return on the existing **completion-unverified** branch (`bug-state.py` ~642–654), which already returns a scoped `_bug_state` from inside the loop on a matched entry.

**Decisions settled here (⚖ scope-class, taken in-cycle per D7 — recorded as Open-Question resolutions, see the SPEC `## Open Questions`):**
- **New per-bug scoped terminal_reasons, not a re-used global terminal.** Introduce distinct scoped terminal_reason constants for the scoped-match case (e.g. `TR_OPERATOR_DEFERRED_SCOPED` → literal `operator-deferred`; analogous scoped reasons for cloud/device/parked). This keeps the UNSCOPED global terminals (`all-remaining-deferred`, `cloud-queue-exhausted`, `device-queue-exhausted`, `queue-exhausted-all-parked`) byte-identical, makes the curated-stage mapping in Phase 3 unambiguous (no overloading a global terminal with scoped fields), and gives the probe a real per-bug `current_step`. The exact constant names/literals are finalized in the WUs below.
- **Fix ALL FOUR skip branches, not only operator-deferred.** The cloud-saturated, device-saturated, operator-deferred, and park branches are structurally identical (`continue` on a matched entry). The SPEC recommends fixing all four for consistency; the operator-deferred path is the reproduced one, the other three are the structurally-identical latent twins. Each returns a scoped, identity-preserving `_bug_state` on a scoped match.
- **Park branches:** under `--park-blocked` / `--park-needs-input`, a scoped match that would be parked returns a scoped state naming the bug + its park reason (blocked/needs-input) rather than falling through to `queue-exhausted-all-parked`. (Park-mode is only active under explicit flags, so this is additive and unscoped behavior is unchanged.)

**Deliverables:**
- [x] Add scoped per-bug terminal_reason constant(s) for the deferred/cloud/device/parked scoped-match cases (named beside the existing `TR_*` constants in `bug-state.py`).
- [x] In `compute_state`'s queue loop, when `scope_bug_id` is set AND the current entry matches AND it would be skipped by the operator-deferred branch (`DEFERRED.md` present), return a scoped `_bug_state(feature_id=bug_id, feature_name=bug_name, spec_path=str(spec_dir), current_step=<per-bug deferred step>, terminal_reason=<scoped deferred reason>, notify_message=…)` instead of `continue`.
- [x] Mirror the same scoped-return treatment in the cloud-saturated skip branch (~666–675), the device-saturated skip branch (~682–696), and the two park branches (~782–824) for a scoped match.
- [x] Preserve the UNSCOPED path exactly: when `scope_bug_id is None`, every branch still `continue`s into the existing global terminals. Add an explicit guard (`if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):`) so the early-return fires ONLY for the scoped-match case.
- [x] Tests: add `bug-state.py --test` fixtures asserting `--bug-id <deferred-bug>` returns `feature_id == <bug-id>` + a non-null `spec_path` + the scoped deferred `terminal_reason` (NOT `feature_id: null` / `all-remaining-deferred`); plus a regression fixture asserting the UNSCOPED query against the same fixture still returns the global `all-remaining-deferred` terminal.

#### Implementation Notes (Phase 1 — landed 2026-06-22, Part 1)

**Status:** Implemented (validation runtime: not-required — pure CLI; `--test` trio is the gate).
**Review verdict:** PASS (inline review — 1 file `bug-state.py` + 1 baseline; unscoped path byte-identical via Fixture B; every scoped guard wraps `if scope_bug_id is not None and str(bug_id) == str(scope_bug_id):` BEFORE the unchanged append/continue; no branch lost its unscoped `continue`).

**Scoped terminal_reason literals introduced (Parts 2/3 consume these VERBATIM):**
- `TR_OPERATOR_DEFERRED_SCOPED = "operator-deferred"` → curated `Deferred`
- `TR_CLOUD_DEFERRED_SCOPED = "cloud-queue-exhausted-scoped"` → curated `Deferred`
- `TR_DEVICE_DEFERRED_SCOPED = "device-queue-exhausted-scoped"` → curated `Deferred`
- `TR_BLOCKED_SCOPED = "blocked-scoped"` → curated `Blocked`
- `TR_NEEDS_INPUT_SCOPED = "needs-input-scoped"` → curated `Needs-input`

**Scoped current_step literals (generic — curated stage resolves from terminal, which dominates):** `STEP_OPERATOR_DEFERRED_SCOPED`, `STEP_CLOUD_DEFERRED_SCOPED`, `STEP_DEVICE_DEFERRED_SCOPED`, `STEP_BLOCKED_PARKED_SCOPED`, `STEP_NEEDS_INPUT_PARKED_SCOPED`.

**Files modified:** `user/scripts/bug-state.py` (5 new `TR_*` + 5 new `STEP_*` constants; new shared `_scoped_skip_state(...)` helper modeled on the completion-unverified scoped return; scoped early-returns added to ALL FOUR skip-branch clusters — operator-deferred, cloud-saturated, device-saturated, and the three park sites [BLOCKED.md / mis-named-blocker / NEEDS_INPUT.md]; 4 new `--test` fixtures: scoped-operator-deferred-identity (A), unscoped-operator-deferred-regression (B), scoped-cloud-saturated-identity (C1), scoped-device-saturated-identity (C2)). `user/scripts/tests/baselines/bug-state-test-baseline.txt` re-byte-pinned via `_normalize_smoke_output` (+4 PASS lines).

**Gates:** `bug-state.py --test` green, `lazy-state.py --test` green (shared `lazy_core`, no regression), `test_lazy_core.py` 764/764, `lazy_parity_audit.py --repo-root .` exit 0 (Phase 1 is bug-state-only; feature-side mirror is Part 2). Real CLI MVB confirmed: `--bug-id <DEFERRED.md-bug>` emits `feature_id=<bug-id>`, non-null `spec_path`, `terminal_reason=operator-deferred`.

**Part 2/3 contract:** the curated-stage mapping table above is the verbatim source for Part 3's `_SIDE_STATE_BY_TERMINAL` additions; Part 2 mirrors the cloud/device scoped literals onto `lazy-state.py` (the feature pipeline has NO operator `DEFERRED.md` branch — justified divergence).

**Minimum Verifiable Behavior:** `python user/scripts/bug-state.py --repo-root <fixture-or-AlgoBooth> --bug-id <DEFERRED.md-bug>` emits `{"feature_id": "<bug-id>", "spec_path": "…/<bug-id>", "terminal_reason": "operator-deferred", …}` with a non-null id (today it emits `feature_id: null`, `terminal_reason: all-remaining-deferred`). Verified by the new `bug-state.py --test` fixture and a direct CLI run.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/bug-state.py` — the four scoped skip branches in `compute_state` + the new scoped `TR_*` constant(s) + new `--test` fixtures.

**Testing Strategy:** In-file `bug-state.py --test` smoke fixtures (hermetic temp-dir). Add: (a) scoped `--bug-id` on a `DEFERRED.md` bug returns its own id + scoped deferred terminal; (b) scoped queries on cloud/device/parked-matched entries likewise return scoped identity; (c) the UNSCOPED baseline-regression fixture still emits the global terminals byte-identically. Re-byte-pin `tests/baselines/bug-state-test-baseline.txt` via `_normalize_smoke_output` (never by hand).

**Integration Notes for Next Phase:**
- Phase 3 (curated-stage) must map every NEW scoped terminal_reason literal introduced here → `Deferred`. Record the exact literal strings chosen here so Phase 3's `_SIDE_STATE_BY_TERMINAL` additions match them verbatim.
- The scoped `current_step` chosen here flows through the probe to `lazy-queue-doc.py`; pick a literal that the curated-stage `current_step` rollup does NOT need to special-case (terminal_reason dominates, so the curated stage resolves from the terminal, not the step).
- Keep the scoped early-return adjacent to / modeled on the completion-unverified branch so a future reader sees the pattern is "scoped match in a skip branch returns scoped state."

---

### Phase 2: Feature-side parity twin in `lazy-state.py` (COUPLING RULE — HARD)

**Scope:** Mirror Phase 1's identity-preserving scoped-return onto the feature pipeline's `--feature-id` scoped query for its global-deferral skip branches (`cloud-queue-exhausted`, `device-queue-exhausted`, `host-capability-saturated`, park). `lazy-state.py`'s loop (`compute_state` ~1666–2330) has the structurally-identical `continue`-into-global-terminal pattern for cloud/device/host-capability/park skips; a `--feature-id` scoped query against any of those states loses the feature's identity exactly as the bug side does. Per the COUPLING RULE in `user/scripts/CLAUDE.md` ("change the state machine in the script; keep the coupled pair in lockstep"), this is mirrored in the SAME change, not filed separately.

**Settled (⚖ scope-class):** feature-side has NO operator `DEFERRED.md` branch (that is a bug-pipeline construct) — its deferral axes are cloud / device / host-capability. The mirror covers exactly the feature-side skip branches that `continue` on a scoped match; it does NOT invent a feature-side operator-deferred branch. The feature pipeline orders by int `tier` (the bug pipeline by severity string) — this JUSTIFIED divergence is unchanged.

**Deliverables:**
- [ ] In `lazy-state.py::compute_state`, when `scope_feature_id` is set AND the current entry matches AND it would be skipped by the cloud-saturated branch (~1701–1713), return a scoped `_state(feature_id=…, feature_name=…, spec_path=…, current_step=<per-feature cloud-deferred>, terminal_reason=<scoped cloud-deferred>)` instead of `continue`.
- [ ] Mirror the scoped-return in the device-saturated skip branch (~1714+) and the host-capability-miss DEFER branch (the `DEFERRED_REQUIRES_HOST.md` skip → `host-capability-saturated`) and the feature-side park branches.
- [ ] Add the scoped per-feature terminal_reason constant(s) (feature-side analogs of Phase 1's, literal strings chosen for parity / curated-stage mapping in Phase 3).
- [ ] Preserve the UNSCOPED feature path byte-identically (the `baseline-regression-default` smoke fixtures guard this — keep them green).
- [ ] Tests: add `lazy-state.py --test` fixtures asserting `--feature-id <cloud-deferred-feature>` (and device / host-capability) returns the feature's own id + scoped deferred terminal, NOT `feature_id: null` / the global exhausted terminal.

**Minimum Verifiable Behavior:** `python user/scripts/lazy-state.py --repo-root <fixture> --feature-id <DEFERRED_NON_CLOUD-feature> --cloud` emits a scoped state carrying that feature's id + a Deferred-mapping terminal (not a null-identity `cloud-queue-exhausted`). Verified by the new `lazy-state.py --test` fixture.

**Prerequisites:**
- Phase 1: the scoped-return pattern + scoped terminal_reason naming convention is established on the bug side; this phase mirrors it (literals chosen for parity).

**Files likely modified:**
- `user/scripts/lazy-state.py` — the cloud/device/host-capability/park scoped skip branches + scoped `TR_*` analog constants + `--test` fixtures.

**Testing Strategy:** In-file `lazy-state.py --test` fixtures (cloud/device/host-capability scoped-match identity preserved; unscoped baseline-regression unchanged). Re-byte-pin `tests/baselines/lazy-state-test-baseline.txt` via `_normalize_smoke_output`.

**Integration Notes for Next Phase:**
- Phase 3 maps the feature-side scoped terminal literals → `Deferred` too. Record them alongside the bug-side literals.
- Run `lazy_parity_audit.py` after this phase — the scoped-skip behavior is a coupled-pair surface; if the audit needs a manifest entry for the new scoped terminal symmetry, add it here (or record a justified divergence if the feature/bug terminal names legitimately differ).

---

### Phase 3: Curated-stage `Deferred` rollup mapping (`curated_stage.py`)

**Scope:** Add the missing `_SIDE_STATE_BY_TERMINAL` entries so every deferred terminal_reason rolls up to the `Deferred` curated node. Today only `cloud-queue-exhausted` / `device-queue-exhausted` map to `Deferred`; the global `all-remaining-deferred` and the new scoped per-bug/per-feature deferred terminals from Phases 1–2 are missing, so even with a scoped id the curated stage falls through to `Pending` (Rule-3 default) instead of `Deferred`.

**Deliverables:**
- [ ] Add `"all-remaining-deferred": "Deferred"` to `_SIDE_STATE_BY_TERMINAL` (the global unscoped bug terminal — fixes the rollup even for the unscoped display path).
- [ ] Add each NEW scoped deferred terminal_reason literal introduced in Phases 1 & 2 → `"Deferred"` (verbatim string match to the constants chosen there).
- [ ] Confirm the host-capability-saturated / park scoped terminals (if any new literals) also map to `Deferred` (or the correct side-state — a parked-blocked scoped terminal may roll to `Blocked`/`Needs-input` rather than `Deferred`; settle per the side-state the bug is actually in).
- [ ] Tests: extend the curated-stage unit tests asserting each new terminal_reason → its correct curated node.

**Minimum Verifiable Behavior:** A unit-test call `curated_stage(...)` (or the module's mapping) returns `"Deferred"` for `terminal_reason="all-remaining-deferred"` and for each new scoped deferred terminal — today `all-remaining-deferred` is unmapped and rolls to `Pending`.

**Prerequisites:**
- Phase 1 & Phase 2: the exact scoped terminal_reason literal strings must be finalized so this phase maps them verbatim.

**Files likely modified:**
- `user/scripts/pipeline_visualizer/curated_stage.py` — `_SIDE_STATE_BY_TERMINAL` additions.
- The curated-stage test module — new mapping assertions.

**Testing Strategy:** Pure-function unit tests over `_SIDE_STATE_BY_TERMINAL` / the curated rollup. No runtime needed.

**Integration Notes for Next Phase:**
- Phase 4's end-to-end render assertion depends on this mapping being present — without it the queue-doc row would still show `Pending` even with a correct scoped id from Phases 1–2.

---

### Phase 4: End-to-end regression guard (`lazy-queue-doc.py` emits no `unknown` row for a deferred bug)

**Scope:** Add the SPEC-required regression guard: a repo whose `docs/bugs/` contains a `DEFERRED.md` bug renders that bug as `[<bug-id>](docs/bugs/<bug-id>/SPEC.md)` with state `⏸ Deferred` and a WORKING SPEC link — NOT `[unknown](docs/bugs/unknown/SPEC.md)` / `Pending`. This closes the loop across all three layers (bug-state scoped identity → curated Deferred rollup → generator render) and asserts the downstream (`probe.py` + `lazy-queue-doc.py`) — which needs NO change — now renders correctly given the fixed upstream data.

**Deliverables:**
- [ ] Add a `test_lazy_queue_doc.py` (or probe-test) fixture: a temp repo with one `DEFERRED.md` bug, generate via the `probe_state` → `curated_stage` → `_render_table` path, and assert the rendered output contains the real `docs/bugs/<bug-id>/SPEC.md` link + the `⏸` Deferred glyph and contains NO `docs/bugs/unknown/SPEC.md` substring.
- [ ] Confirm the `_item_id` / `_rel_spec_path` `"unknown"` fallback is RETAINED (defensive last resort) but is no longer reached for the deferred case — assert via the absence of `unknown` in the rendered output for the fixture.
- [ ] (If feasible in-fixture) assert the feature-side scoped deferral renders its feature id likewise, exercising Phase 2's mirror through the generator.

**Minimum Verifiable Behavior:** `python user/scripts/lazy-queue-doc.py --repo-root <DEFERRED.md-fixture> --stdout` output contains `docs/bugs/<bug-id>/SPEC.md` and the `⏸` Deferred glyph, and contains zero occurrences of `docs/bugs/unknown/SPEC.md`. (Today it renders the `unknown` broken link.) Verified by the new generator/probe test fixture.

**Prerequisites:**
- Phase 1 (scoped id), Phase 3 (Deferred rollup) — both must land for the render to be correct. (Phase 2 is exercised opportunistically for the feature side.)

**Files likely modified:**
- `user/scripts/test_lazy_queue_doc.py` (and/or the probe test module) — new regression fixture.
- No production change to `probe.py` / `lazy-queue-doc.py` (the SPEC proves these are already correct given good upstream data; the `unknown` fallback stays as defensive code).

**Testing Strategy:** Generator/probe unit test over a hermetic temp-repo fixture carrying a `DEFERRED.md` bug. Deterministic, no runtime.

**Integration Notes for Next Phase:**
- Final phase. **Completion (gate-owned):** the SPEC `**Status:**` flip to `Fixed` + the `FIXED.md` receipt are owned EXCLUSIVELY by the orchestrator's `__mark_fixed__` gate after the validation tail (`/mcp-test` → coverage audit) — NOT authored as a checkbox here. When the last phase's implementation lands, the top-level PHASES `**Status:**` is set to `In-progress` (implementation done, validation pending), and the state machine routes onward.

---

## Implementation Notes

- **Root cause is two-part + a latent parity twin** (per SPEC `## Proven Findings`): (1) `bug-state.py` scoped skip-branches fall through to a global null-identity terminal (Phase 1, PRIMARY); (2) `curated_stage._SIDE_STATE_BY_TERMINAL` lacks an `all-remaining-deferred → Deferred` entry (Phase 3); (3) the feature-side `lazy-state.py --feature-id` twin (Phase 2, COUPLING RULE — mirror in the same change). Downstream `probe.py` + `lazy-queue-doc.py` are correct and need no production change (Phase 4 only adds the regression guard).
- **Coupling discipline (HARD):** change the state machines in the scripts (not in any wrapper skill), keep BOTH `--test` suites green, re-byte-pin both baselines via `_normalize_smoke_output` (never by hand), and run `lazy_parity_audit.py` after Phase 2 — the scoped-skip identity behavior is a coupled-pair surface.
- **Sibling defect:** `docs/bugs/feature-queue-lacks-on-disk-autodiscovery` was discovered the same session via the same `mobile-queue-control` mobile read surface (cross-linked in the SPEC `**Related:**`).
- **D7 Open-Question resolutions taken in-cycle (scope-class — end-state product behavior is identity-preserving either way; choices are mechanism/completeness/sizing):**
  - ⚖ policy: new scoped terminal vs reuse global → new per-bug/feature scoped terminal_reasons
  - ⚖ policy: fix only operator-deferred vs all four → fix all four skip branches
  - ⚖ policy: feature-side twin same change vs filed separately → mirror in same change (coupling rule)
