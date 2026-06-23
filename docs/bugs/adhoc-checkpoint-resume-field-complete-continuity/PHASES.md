# Implementation Phases — Checkpoint resume continuity is field-by-field, not field-complete

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — pure Python state-machine helper change in `user/scripts/lazy_core.py` with no app integration / MCP-reachable surface; validated by the in-file `--test` smoke harnesses + `test_lazy_core.py` (pytest), per docs/bugs/CLAUDE.md (harness self-investigation; deterministic state script, not an AlgoBooth runtime feature).

## Cross-feature Integration Notes

`**Depends on:**` is not declared in the SPEC (a harness-self bug, no upstream feature deps). No hard upstream PHASES.md to integrate against.

Prior-art the fix must preserve (from SPEC `**Related:**`, verified in source):
- **`operator-checkpoint-resume-counter-reset` (2026-06-17):** the `operator_authorized` provenance branch in `restore_checkpoint_counters` (`:12666` `if checkpoint.get("operator_authorized"): return None`). The operator-authorized path stays a no-op (fresh 0/0 budget + fresh identity). The continuity contract applies ONLY to the non-operator-authorized (carry-forward) branch.
- **hardening Round 35 (`821628e`, 2026-06-23):** added the `run_started_at` snapshot in `write_run_checkpoint` (`:12532-12546`) + the age-guarded `started_at` restore in `restore_checkpoint_counters` (`:12693-12705`). The existing regression test `test_restore_checkpoint_counters_carries_forward_run_identity` (`test_lazy_core.py:9973`, 5 cases) MUST stay green.
- **`refuse_run_start_clobber` (Round 19) / same-pipeline concurrent-walker refusal:** gate WHETHER a `--run-start` proceeds, not which fields carry. Untouched by this fix (Out of Scope).

## Audit Table (touchpoints — verified by direct Read of each file/region)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` → `write_run_marker` (`:8800-8910`) | yes | `write_run_marker(...) -> dict`; the marker dict literal at `:8861-8907` | refactor (read-only reference + new SSOT sets must agree) | The literal is the SSOT of *which keys exist* and *what their reset/fresh value is*. The new `RUN_FRESH_FIELDS` / `RUN_CONTINUITY_FIELDS` partition must cover EXACTLY this literal's run-scoped keys. Do NOT change the mint values; add the partition constants + a completeness assertion that references this literal's key set. |
| `user/scripts/lazy_core.py` → `write_run_checkpoint` (`:12487-12551`) | yes | `write_run_checkpoint(next_route, counters, now=None, operator_authorized=False) -> dict`; raw-marker read at `:12532-12540`; checkpoint dict at `:12541-12548` | refactor | Replace the ad-hoc `run_started_at` raw-read + fixed-dict snapshot with a single `continuity` block snapshotting the FULL `RUN_CONTINUITY_FIELDS` set (raw read, same age-safe non-destructive marker access — never `read_run_marker`). Keep `counters` + `operator_authorized` + `reason` + `next_route` + `ts` keys for back-compat; ADD a `continuity` block. |
| `user/scripts/lazy_core.py` → `restore_checkpoint_counters` (`:12584-12711`) | yes | `restore_checkpoint_counters(checkpoint) -> dict | None`; operator-auth no-op at `:12666`; counter carry `:12679-12680`; identity restore `:12693-12705`; watermark reset `:12708` | refactor | Re-apply the full `continuity` block as one operation in the carry-forward branch, PRESERVING all existing guards: operator-authorized no-op, `started_at` age gate (`_MARKER_STALE_SECONDS`), `last_advance_consume_count = 0` deliberate reset (it is a `RUN_FRESH_FIELD`, not carried), per-field fail-safe on missing/unparseable. Must remain back-compat with a legacy checkpoint that has the flat `run_started_at` field but no `continuity` block. |
| `user/scripts/lazy_core.py` constants region (near `_MARKER_FILENAME` `:6162`, `_CHECKPOINT_FILENAME` `:6176`, `_MARKER_STALE_SECONDS` `:6183`) | yes | module-level constants | create (net-new SSOT) | Add `RUN_CONTINUITY_FIELDS` (carried across a sanctioned same-run resume) + `RUN_FRESH_FIELDS` (reset on resume) as the enumerated partition SSOT. |
| `user/scripts/test_lazy_core.py` (near `:9973`) | yes | `test_restore_checkpoint_counters_carries_forward_run_identity()` (5 cases) + `test_restore_checkpoint_counters*` siblings | create (append tests) | Add a partition-completeness assertion + a "new continuity field round-trips through checkpoint" test + a "new field defaults to continuity-or-explicit-fresh, never silently reset" guard test. Do NOT modify existing tests except where the checkpoint shape change forces a non-behavioral update. |
| `user/scripts/lazy-state.py` (`:9475-9512`), `user/scripts/bug-state.py` (`:5516-5535`) | yes (per SPEC) | `--run-start` call sites: `write_run_marker` → `consume_run_checkpoint` → `restore_checkpoint_counters` | NO CHANGE | Continuity logic lives entirely in shared `lazy_core`; both pipelines inherit. Parity-audited but NOT a script-mirror edit. Run `lazy_parity_audit.py` to confirm it stays green. |

All planned source paths are `exists: yes`; the two new things are module-level constants and appended tests, both inside existing files. No genuine design fork (the SPEC's Open Question resolves the nested-`continuity`-block form as a mechanical-internal choice). No `NEEDS_INPUT.md`.

## Validated Assumptions (code-provable — Step 2.7 gate)

Every load-bearing assumption here is **code-provable** (pure Python logic over a state-dir JSON file, exercised by a hermetic `--test` harness that injects `now` / state dir). No runtime-coupled assumption requires a live-system spike. Skip-reason recorded per the gate: this is a deterministic state-script helper; the `--test` harness drives the real `write_run_marker` / `write_run_checkpoint` / `restore_checkpoint_counters` against a real temp state dir (not a mock), which is the authoritative evidence for this class.

Confirmed by Read:
- `write_run_marker`'s marker literal (`:8861-8907`) is the complete set of run-scoped keys: `pipeline`, `cloud`, `repo_root`, `session_id`, `started_at`, `max_cycles`, `nonce_seed`, `forward_cycles`, `meta_cycles`, `per_feature_forward_cycles`, `per_feature_corrective_cycles`, `last_advance_consume_count`, `attended`, `work_branch`.
- The carry-forward branch today re-applies exactly: `forward_cycles`, `meta_cycles` (`:12679-12680`), `started_at` (`:12693-12705`, age-guarded), `last_advance_consume_count = 0` (`:12708`, deliberate reset).
- `write_run_checkpoint` snapshots only `counters` (caller-supplied) + `run_started_at` (raw marker read) into the checkpoint file.

## Field-partition decision (the SSOT contract this fix introduces)

Classifying each run-scoped marker key as CARRY (continuous across a non-operator-authorized same-run pause) vs FRESH (reset on resume):

- **`RUN_CONTINUITY_FIELDS` (carried):** `forward_cycles`, `meta_cycles`, `started_at` (run identity), `per_feature_forward_cycles`, `per_feature_corrective_cycles`. These are run-scoped accumulators / identity that the SAME run accrues; resetting any mid-run violates the super-invariant (HARD CONSTRAINT 8 for counters; cycle-bracket continuity for `started_at`). The two `per_feature_*` maps are NOT carried today — including them closes the latent third whack-a-mole the SPEC names (a near-complete-feature budget map silently zeroing on resume).
- **`RUN_FRESH_FIELDS` (reset on resume — born fresh by construction):** `last_advance_consume_count` (deliberate 0 — registry is freshly cleared; SPEC Out-of-Scope), plus run-INVARIANT identity/config that `write_run_marker` re-derives identically anyway (`pipeline`, `cloud`, `repo_root`, `session_id`, `max_cycles`, `nonce_seed`, `attended`, `work_branch`). `session_id` is owner-bound by the resuming `--run-start` (Phase-1 born-owner-bound; carrying a stale one is wrong); `work_branch` is re-resolved at run-start.
- **Completeness invariant (the by-construction guarantee):** `set(RUN_CONTINUITY_FIELDS) | set(RUN_FRESH_FIELDS) == <run-scoped key set of the write_run_marker literal>`, with the two sets disjoint. A `--test`-enforced assertion makes a newly-added marker key a HARD test failure until it is explicitly placed in one set — so a new field can never silently default to the reset side.

> ⚖ policy: continuity-snapshot form (flat vs nested block) → nested `continuity` block. SPEC Open Question marks this a mechanical-internal choice with no product-behavior divergence; the nested block gives a clean one-unit restore. (D7 scope-class; disclosed, no NEEDS_INPUT.)
> ⚖ policy: scope of carried fields → carry the FULL continuity set incl. the two `per_feature_*` maps. The most-complete path; the maps are run-scoped accumulators that a sanctioned resume must continue. (D7 completeness-first.)

---

### Phase 1: Enumerated continuity/fresh partition SSOT + completeness assertion

**Scope:** Introduce the two module-level partition constants in `lazy_core.py` and a test-enforced completeness invariant binding them to the `write_run_marker` literal. This is the by-construction guarantee; it lands BEFORE the snapshot/restore rewrite so the rewrite can build on the SSOT and the completeness test fails loudly if a future field is unclassified. No behavior change yet — the existing carry-set/snapshot-set still run; this phase only adds the SSOT + its self-test.

**Deliverables:**
- [ ] `RUN_CONTINUITY_FIELDS` constant (frozenset/tuple) in `lazy_core.py` constants region = `{forward_cycles, meta_cycles, started_at, per_feature_forward_cycles, per_feature_corrective_cycles}`, with a docstring naming the carry-vs-reset contract and the super-invariant.
- [ ] `RUN_FRESH_FIELDS` constant = the remaining run-scoped keys of the `write_run_marker` literal (`last_advance_consume_count`, `pipeline`, `cloud`, `repo_root`, `session_id`, `max_cycles`, `nonce_seed`, `attended`, `work_branch`).
- [ ] A helper (e.g. `_run_marker_scoped_keys()`) or a literal-derived key set used by the completeness assertion, so the assertion checks against the ACTUAL minted key set (not a hand-copied list that could drift from the literal).
- [ ] Tests: a `test_lazy_core.py` assertion that `RUN_CONTINUITY_FIELDS | RUN_FRESH_FIELDS` exactly equals the run-scoped key set of a freshly-minted marker AND the two sets are disjoint (the "new field can't silently default to reset" guard).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` stay green; `python3 -m pytest user/scripts/test_lazy_core.py -k "partition or continuity_fields"` passes the new completeness assertion. Run as commands — this phase's slice is the SSOT + its self-test, both runnable now.

**Runtime Verification** *(checked by integration test — NOT by the implementation agent):*
- [ ] <!-- verification-only --> The completeness assertion FAILS if a new key is added to the `write_run_marker` literal without being placed in one of the two sets (proven by a test that constructs a marker-key set with an extra synthetic key and asserts the partition check raises/returns False).

**MCP Integration Test Assertions:** N/A — no runtime-observable (app/MCP) behavior in this phase; it is a pure-Python SSOT + smoke-test assertion.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `RUN_CONTINUITY_FIELDS` / `RUN_FRESH_FIELDS` + key-set helper near the `_MARKER_FILENAME` constants region.
- `user/scripts/test_lazy_core.py` — add the partition-completeness assertion.

**Testing Strategy:** Pure unit assertion over the constants and a freshly-minted marker dict (hermetic — `write_run_marker` with an injected `now` into a temp state dir). No I/O beyond the temp state dir the existing harness already provides.

**Integration Notes for Next Phase:**
- Phase 2 reads `RUN_CONTINUITY_FIELDS` as the snapshot/restore key set — it must not re-enumerate fields.
- The completeness assertion is the regression net for the whole bug class; keep it referencing the live marker literal, not a frozen copy.

---

### Phase 2: Snapshot the full continuity block at checkpoint-write + restore it as one unit

**Scope:** Rewrite `write_run_checkpoint` to snapshot the entire `RUN_CONTINUITY_FIELDS` set into a single nested `continuity` block (replacing the ad-hoc `run_started_at`-only snapshot), and rewrite `restore_checkpoint_counters`'s carry-forward branch to re-apply that block as one operation — preserving every existing guard (operator-authorized no-op, `started_at` age gate, `last_advance_consume_count` deliberate reset, per-field fail-safe). Back-compat: a legacy checkpoint with the flat `run_started_at` field and no `continuity` block still restores identity correctly.

**Deliverables:**
- [ ] `write_run_checkpoint` reads the live marker RAW (same non-destructive access as today — never `read_run_marker`) and writes a `continuity: {field: value, ...}` block covering every `RUN_CONTINUITY_FIELDS` key present on the marker. Retain `reason`/`next_route`/`counters`/`operator_authorized`/`ts` keys (back-compat; `counters` may become a derived view of the continuity counters or stay as-is — implementer's call, but no consumer breaks).
- [ ] `restore_checkpoint_counters` carry-forward branch: when a `continuity` block is present, re-apply ALL its fields to the just-minted marker in one loop, applying the per-field guards (age gate for `started_at`; coerce-to-non-negative-int for the two counters; preserve the existing `_coerce` fail-safe semantics; `per_feature_*` maps applied only when a well-formed dict). `last_advance_consume_count` stays forced to 0 (it is a `RUN_FRESH_FIELD`).
- [ ] Back-compat fallback: when NO `continuity` block exists but the legacy `counters` + flat `run_started_at` fields do, restore via the existing legacy path (so a pre-fix checkpoint file mid-flight still resumes correctly).
- [ ] Operator-authorized branch unchanged: still returns `None` (no carry — fresh budget + fresh identity).
- [ ] Tests: a round-trip test proving every `RUN_CONTINUITY_FIELDS` field (incl. both `per_feature_*` maps) survives `write_run_checkpoint` → `consume_run_checkpoint` → `restore_checkpoint_counters` in the carry-forward branch; a test proving a legacy flat-`run_started_at` checkpoint still restores identity; a test proving operator-authorized still no-ops; the existing `test_restore_checkpoint_counters_carries_forward_run_identity` (5 cases) stays green unchanged.

**Minimum Verifiable Behavior:** `python3 -m pytest user/scripts/test_lazy_core.py -k "checkpoint or continuity or restore"` passes incl. the new full-set round-trip and back-compat tests; both `--test` baselines stay byte-stable (`lazy-state.py --test`, `bug-state.py --test`). Run as commands.

**Runtime Verification** *(checked by integration test — NOT by the implementation agent):*
- [ ] <!-- verification-only --> A non-operator-authorized resume carrying non-empty `per_feature_forward_cycles` / `per_feature_corrective_cycles` maps restores those maps verbatim (proves the SPEC's named latent-third-whack-a-mole is closed — the budget-guard maps survive a sanctioned pause).
- [ ] <!-- verification-only --> A >24h-stale `started_at` in the continuity block is NOT restored (the age gate still wins, marker keeps its minted identity — the Round-35 invariant survives the rewrite).

**MCP Integration Test Assertions:** N/A — no runtime-observable (app/MCP) behavior; deterministic state-script helper validated entirely by the in-file `--test` harness + `test_lazy_core.py`.

**Prerequisites:**
- Phase 1: `RUN_CONTINUITY_FIELDS` / `RUN_FRESH_FIELDS` + the completeness assertion must exist (this phase reads the continuity set from the SSOT).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `write_run_checkpoint` (`:12487-12551`) snapshot rewrite; `restore_checkpoint_counters` (`:12584-12711`) carry-forward block rewrite + legacy fallback.
- `user/scripts/test_lazy_core.py` — full-set round-trip + back-compat + operator-auth-no-op tests.

**Testing Strategy:** Hermetic — `write_run_marker` (injected `now`) → mutate the two counter + two `per_feature_*` fields → `write_run_checkpoint` → `consume_run_checkpoint` → `restore_checkpoint_counters`, asserting the resumed marker equals the pre-pause continuity values and the fresh fields are reset. Reuse the existing test fixtures' `_set_state_dir` / `_clear_state_dir` scaffolding.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md `**Status:**` to Fixed and writes FIXED.md once this phase's validation (the `--test` suites + `test_lazy_core.py`) passes and the orchestrator's validation tail runs. The cycle subagent never flips the top-level status.

**Integration Notes for Next Phase:** none — Phase 2 is terminal. The parity audit + full test sweep is the closeout (run `lazy_parity_audit.py --repo-root .`, `lazy-state.py --test`, `bug-state.py --test`, `pytest test_lazy_core.py` after the change, per `user/scripts/CLAUDE.md` Coupling Rule).
