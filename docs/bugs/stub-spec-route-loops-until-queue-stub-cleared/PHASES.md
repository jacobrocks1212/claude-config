# Implementation Phases — Stub-spec route loops until queue.json stub cleared

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure Python state-machine fix in `lazy-state.py` / `lazy_core.py` with no app-integration surface; validation is the in-file `--test` smoke harness + `test_lazy_core.py`, not the Tauri/MCP dev runtime. (claude-config has no MCP surface at all; matches the `docs/bugs/` harness-defect class.)

## Touchpoint Audit (verified inline against the real codebase, 2026-06-20)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `_atomic_write` (L104), `reorder_queue` (L130), `_die` (L120), `_diag` (L90) | refactor (add helper) | Add `clear_queue_stub(queue_path, feature_id)` mirroring `reorder_queue`'s load→validate-list→mutate→`_atomic_write` shape. Reuse `_die`/`_atomic_write`/`_diag`. Domain-agnostic (caller passes its own `queue_path`), so it is parity-safe even though only the feature pipeline calls it. |
| `user/scripts/lazy-state.py` | yes | `is_stub_spec` (L823, queue branch L859), Step 4.5 routing (L1980-1990), Step 5 routing (L2014+), `load_queue` (L276, `queue_path = repo_root/docs/features/queue.json`), `current["queue_entry"]` (L1708), `--test` fixtures (L~3003) + assertions (L~4483) | refactor | Insert the lone-surviving-marker discriminator + clear-and-advance at the Step-4.5 branch; add a `--test` fixture + assertion row. |
| `user/scripts/bug-state.py` | yes (coupled parity pair) | — | none (explicit) | The bug pipeline has **no stub/research/Gemini step** (`user/scripts/CLAUDE.md`: "research/Gemini/stub steps dropped"). `clear_queue_stub` is feature-only by construction; no mirror is needed and `lazy_parity_audit.py` does not require one (it lives in shared `lazy_core` but is invoked only by `lazy-state.py`). Record this as the parity rationale so a future audit does not flag a "missing" bug-side call. |
| `tests/baselines/lazy-state-test-baseline.txt` | yes | byte-pinned `--test` output | regenerate | The new fixture changes `--test` output; regenerate by piping live `--test` through `_normalize_smoke_output` (per `user/scripts/CLAUDE.md` → Testing), never by hand. |

**Drift correction:** none required — every SPEC line-number reference resolved to the real symbol. The SPEC's `is_stub_spec` queue branch is at L859 (matches), Step 4.5 at L1980 (matches), Step 5 generate-research-prompt at L2073-2081 (matches). No mechanical drift; no genuine design fork (the "lone-surviving-marker" discriminator is fully specified by SPEC §"How baseline locked is detected").

## Validated Assumptions (code-provable — no runtime spike needed)

All load-bearing assumptions here are **code-provable** (pure-logic state-machine routing over file contents + a JSON queue; no cross-boundary runtime behavior). The Runtime Assumption Validation gate is therefore satisfied by the in-file `--test` harness, which drives the REAL `compute_state()` over real temp-dir fixtures:

- **The queue flag is the lone surviving marker after a baseline-shaping `/spec` cycle.** Proven by the SPEC's live repro (Verified Symptom 2): the two SPEC-text markers (`> Draft (pre-Gemini)`, legacy `Draft (research stub)`) self-clear when `/spec` rewrites the SPEC body; only `queue_entry["stub"]` survives. Code-provable from `is_stub_spec` (L840-860): the discriminator "SPEC-text markers absent AND queue flag set" is computed entirely from `spec_text` + `queue_entry`.
- **Step 4.5 reads `current["queue_entry"]`, which is the live queue entry** (L1708, L1980). Clearing the on-disk queue flag and re-routing in the SAME `compute_state` call to Step 5 is deterministic — the fixture asserts the post-clear route AND the cleared on-disk flag.

## Decomposition note (single phase — justified)

This is a small, self-contained, deterministic state-script fix: one new shared helper + one routing-boundary insertion + one smoke fixture + one baseline regen. It does not cross any process/serialization/IPC/thread boundary (it is a synchronous Python function over local files), so the "Phase 1 must cross the boundary" full-stack rule does not apply, and there is no MCP surface to distribute verification across. Splitting it would create artificially-coupled phases (the helper is untestable in isolation from its one caller). One phase is the correct granularity.

---

### Phase 1: Script-owned clear-and-advance at the Step-4.5 → Step-5 boundary

**Scope:** Close the stub→research-pending clear-owner gap by adding a script-owned, deterministic clear of the `queue.json` `"stub"` flag at the exact moment the baseline is detected as locked (the queue flag is the *lone surviving* stub marker), and advancing the route to Step 5 in the same probe — so a stub-shaping `/spec` cycle that drafts + commits the baseline no longer re-routes to Step 4.5 forever.

**Deliverables:**
- [ ] `clear_queue_stub(queue_path, feature_id)` added to `lazy_core.py`, mirroring `reorder_queue`'s shape: load `queue.json` → validate it is a list → find the entry by `id == feature_id` → pop the `"stub"` key (no-op if absent) → `_atomic_write`. A missing `feature_id` or malformed JSON calls `_die` (exit 2, zero mutation) — never a silent corrupt-write. An entry that has no `"stub"` key (already clear) returns a byte-stable no-op (`cleared: False`). Returns a JSON-serializable dict `{cleared: bool, feature_id: str, queue_length: int}`. Emits a `_diag` line on a real clear naming the feature.
- [ ] A **lone-surviving-marker discriminator** helper in `lazy-state.py` (or `lazy_core`) — `_stub_is_queue_flag_only(spec_text, queue_entry) -> bool` — returns True iff `queue_entry.get("stub") is True` AND **none** of the three SPEC-text stub markers match `spec_text` (reuse the exact same conditions as `is_stub_spec`'s first four branches: legacy `**Status:** Draft (research stub)`, `> Stub generated from advanced feature research`, anchored `**Status:** … Draft (pre-Gemini)`, anchored `> … Draft (pre-Gemini)`). This is reachable ONLY after a baseline-shaping `/spec` rewrite dropped the SPEC-text markers, so it never fires on a true pre-baseline stub (where a SPEC-text marker is still present). To avoid drift, factor the SPEC-text-marker check into a tiny shared predicate that BOTH `is_stub_spec` and this discriminator call — do NOT duplicate the four conditions inline.
- [ ] Wire the clear-and-advance into the Step 4.5 branch (`lazy-state.py` L1980): BEFORE returning the Step-4.5 `/spec` dispatch, if `_stub_is_queue_flag_only(spec_text, current["queue_entry"])` is True, call `clear_queue_stub(repo_root / "docs" / "features" / "queue.json", feature_id)`, emit a `_diag` line ("Step 4.5 clear-owner: baseline locked (queue flag is lone surviving stub marker) — cleared queue.json stub and advancing to Step 5"), and **fall through** to Step 4.6/Step 5 (do NOT return the Step-4.5 dispatch). When a SPEC-text marker IS still present (true pre-baseline stub), behavior is byte-identical to today: dispatch `/spec` at Step 4.5.
- [ ] Tests: a new `lazy-state.py --test` fixture `stub-queue-flag-lone-survivor` — queue entry `"stub": true` + a **structured** SPEC (`**Status:** Draft`, no SPEC-text stub marker) + no research files → assert (a) `current_step == "Step 5: generate research prompt"` and `sub_skill == "spec"` (advanced, NOT a Step-4.5 re-fire), and (b) the on-disk `queue.json` entry no longer carries the `"stub"` key (the clear fired). Keep the existing `stub-queue-flag-only` fixture UNCHANGED? — see authoring note below: that fixture's SPEC has no SPEC-text marker either, so it would now advance; resolve by giving the existing `stub-queue-flag-only` fixture a genuine pre-baseline SPEC-text marker (so it still asserts Step 4.5), and let the NEW fixture cover the lone-survivor advance. Add a unit test in `test_lazy_core.py` for `clear_queue_stub` (clears when present, no-op when absent, `_die` on malformed/missing-id).

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` passes with the new `stub-queue-flag-lone-survivor` fixture asserting the route advances to `Step 5: generate research prompt` AND the on-disk `queue.json` stub flag is cleared (a single deterministic command over the real `compute_state` + real temp-dir queue.json — this is the runtime-observable proof the loop is closed).

**MCP Integration Test Assertions:** N/A — no runtime-observable behavior outside the state machine; this is a pure Python state-script fix with no app/MCP surface (claude-config has no MCP server). The `--test` smoke harness driving the real `compute_state()` is the authoritative behavioral check.

**Prerequisites:** None (first and only phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — add `clear_queue_stub(queue_path, feature_id)` (mirror `reorder_queue`) + a shared SPEC-text-stub-marker predicate factored out of `is_stub_spec`'s first four branches.
- `user/scripts/lazy-state.py` — add `_stub_is_queue_flag_only` discriminator; wire the clear-and-advance at the Step-4.5 branch (L1980); refactor `is_stub_spec` to call the shared SPEC-text predicate (behavior-preserving); add the `stub-queue-flag-lone-survivor` `--test` fixture + assertion and adjust the existing `stub-queue-flag-only` fixture's SPEC to carry a real pre-baseline SPEC-text marker.
- `tests/baselines/lazy-state-test-baseline.txt` — regenerate via `_normalize_smoke_output` (NOT by hand) after the fixture lands.
- `user/scripts/test_lazy_core.py` — add `clear_queue_stub` unit coverage (present-clears / absent-no-op / `_die` on malformed-or-missing-id).

**Testing Strategy:**
- In-file hermetic smoke: `python3 user/scripts/lazy-state.py --test` — the new fixture drives the REAL `compute_state()` over a real temp-dir `queue.json` + structured SPEC, asserting both the advanced route and the cleared on-disk flag (so the fix is verified end-to-end within the state machine, not by reading the helper in isolation).
- `python3 user/scripts/test_lazy_core.py` — direct characterization of `clear_queue_stub` (and the shared SPEC-text predicate, confirming `is_stub_spec` is behavior-preserving after the refactor).
- `python3 user/scripts/bug-state.py --test` — MUST stay green (the shared `lazy_core` change must not regress the bug pipeline, even though it doesn't call the new helper).
- Regenerate `tests/baselines/lazy-state-test-baseline.txt` from live `--test` output piped through `_normalize_smoke_output` so the platform-neutral baseline matches.

**Authoring notes (carried for the executor — do NOT re-derive):**
- **Lone-surviving-marker discriminator is the SPEC's chosen clear-point** (SPEC §"How baseline locked is detected" + Proven Finding 3). Clearing at "queue flag is the lone surviving marker" advances the item to Step 5 in one pass and CANNOT fire on a true pre-baseline stub (SPEC-text marker still present). Do NOT clear unconditionally inside `is_stub_spec` — that would mutate during a true pre-baseline stub and break the Step-4.5 design.
- **HARD CONSTRAINT 1 (no orchestrator hand-edit of queue.json) is honored** by putting the mutation in `lazy_core` (the established `reorder_queue`/`enqueue_adhoc` pattern), invoked by the script — never by the orchestrator subagent (SPEC Proven Finding 2).
- **Theory 3 (legacy substring brittleness) is OUT OF SCOPE** for the loop fix (SPEC Open Questions: "do not gate the primary fix on it"). It is a separate, lower-severity robustness gap. If the one-line regex tightening of `**Status:** Draft (research stub)` → `Draft (research stub — …)` is *trivially free* while factoring the shared SPEC-text predicate, the executor MAY include it; otherwise leave it as the SPEC's logged follow-up. ⚖ policy: secondary substring tightening → in-cycle only if trivially free, else deferred per SPEC.
- **bug-state.py parity:** intentionally NOT mirrored — the bug pipeline has no stub step. This is the correct divergence, documented in the Touchpoint Audit above so a future `lazy_parity_audit.py` review does not flag a false gap.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md top-level `**Status:**` and writes `FIXED.md` once this phase's `--test` validation passes via the validation tail. This phase NEVER flips the top-level status itself.

---

## Cross-feature Integration Notes

No hard dependencies on completed upstream features (`**Depends on:**` is implicitly `(none)` — this is a harness-defect bug doc under `docs/bugs/`, not a feature with a dep block). The fix is self-contained within the `lazy-state.py` / `lazy_core.py` state machine.
