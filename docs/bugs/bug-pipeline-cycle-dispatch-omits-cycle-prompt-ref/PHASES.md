# Implementation Phases — Bug-pipeline cycle dispatch omits `cycle_prompt_ref`

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a state-script (`bug-state.py`) emission-surfacing fix verified by the in-file `--test` smoke harness + the parity audit; no Tauri/MCP/app surface exists in claude-config (per `docs/features/mcp-testing/SPEC.md`'s "standalone tooling, no app integration" untestable class). The whole change is unit-level Python with deterministic, code-provable behavior.

## Validated Assumptions

All load-bearing assumptions for this fix are **code-provable** (read directly from source — no runtime observation needed):

- **`bug-state.py:5807-5812` discards the registry entry.** Verified by Read: the block calls `lazy_core.register_emission_if_marked(cycle_prompt, "cycle", item_id=state.get("feature_id"))` with the return value unbound, and never assigns `state["cycle_prompt_ref"]`.
- **`lazy-state.py:10036-10050` is the correct mirror to copy.** Verified by Read: it captures `_ref_entry = register_emission_if_marked(...)`, then sets `state["cycle_prompt_ref"] = f"@@lazy-ref nonce={_ref_entry['nonce']}"` when the entry is present, `None` otherwise, and `None` in the outer `else` (no `cycle_prompt`).
- **`register_emission_if_marked` already returns the entry dict (or `None`).** Both scripts call the identical shared `lazy_core` helper with identical args; only `lazy-state.py` consumes the return. No `lazy_core` change is owed — the registration already succeeds in `bug-state.py` (the prompt IS in `lazy-prompt-registry.json`); only the surfacing is missing.
- **The parity audit does NOT currently assert `cycle_prompt_ref` surfacing.** Verified by grep: `cycle_prompt_ref` has zero matches in `lazy_parity_audit.py`. This is the SPEC's "Secondary gap" — Phase 2 closes it so the mirror cannot silently drift again.
- **Consumers already prefer `cycle_prompt_ref` when present.** Per the SPEC Affected Area table, `/lazy-bug` and `/lazy-bug-batch` begin dispatching by reference for free once the field is surfaced — no consumer change owed.

This is a coupled-pair mirror (`lazy-state.py` ↔ `bug-state.py`); the change to the bug half must be parity-audited (`lazy_parity_audit.py --repo-root . --pair lazy-bug-batch`) and both `--test` suites kept green.

## Cross-feature Integration Notes

No hard deps on Complete upstream features. The archived feature-pipeline counterpart (`docs/bugs/_archive/byref-dispatch-undercounts-forward-cycles`, fixed 2026-06-19) is prior art for the `@@lazy-ref` cycle-token machinery this fix mirrors into the bug pipeline — it is reference context, not a dependency.

---

### Phase 1: Surface `cycle_prompt_ref` in `bug-state.py` (coupled-pair mirror)

**Scope:** Mirror the `cycle_prompt_ref` capture-and-surface logic from `lazy-state.py:10036-10050` into `bug-state.py:5807-5812` so the bug pipeline hands the orchestrator a `@@lazy-ref` token to dispatch by reference, exactly as the feature pipeline does. Add a `--test` fixture asserting the field is surfaced under a live marker and `None` without one.

**Deliverables:**
- [ ] In `bug-state.py` (~5807-5812): capture `_ref_entry = lazy_core.register_emission_if_marked(...)` and set `state["cycle_prompt_ref"]` — the token `f"@@lazy-ref nonce={_ref_entry['nonce']}"` when `_ref_entry is not None`, else `None`; and `None` in the outer `else` branch (no `cycle_prompt`). Match `lazy-state.py:10036-10050` exactly (modulo the bug-pipeline comment that `feature_id` holds the bug id).
- [ ] Add a `bug-state.py --test` fixture: a live run marker + a real-skill `--emit-prompt` cycle ⇒ the probe carries `cycle_prompt_ref: "@@lazy-ref nonce=…"`; no marker ⇒ `cycle_prompt_ref` is `None` (byte-identical-when-absent preserved — i.e. the field is `None`, registration is a no-op without a marker). Register the fixture in the script's `--test` list block.
- [ ] Tests: `bug-state.py --test` green (with the new fixture); `lazy-state.py --test` still green (no feature-side change, regression guard).
- [ ] Regenerate the byte-pinned `bug-state` smoke baseline (`tests/baselines/bug-state-test-baseline.txt`) ONLY by piping live `--test` output through `_normalize_smoke_output` — never by hand. (Only if the new fixture changes pinned output; if the fixture asserts in-Python without touching pinned stdout, no baseline change.)

**Minimum Verifiable Behavior:** `python3 user/scripts/bug-state.py --test` exits 0 with the new fixture asserting `state["cycle_prompt_ref"]` is the `@@lazy-ref` token under a live marker and `None` without one. This is the smallest deterministic proof the surfacing now works — runnable, not "unit tests pass" hand-waving.

**Prerequisites:** None (first phase).

**Files likely modified:**
- `user/scripts/bug-state.py` — capture+assign block (~5807-5812) + new `--test` fixture + fixture registration in the test list.
- `user/scripts/tests/baselines/bug-state-test-baseline.txt` — regenerate via `_normalize_smoke_output` ONLY if pinned output changes.

**Testing Strategy:**
In-file `--test` smoke harness (hermetic temp-dir fixtures, not pytest). The new fixture mirrors marker/queue setup from a nearby existing `--emit-prompt`/marker fixture rather than inventing scaffolding. Assert both the live-marker (token present) and no-marker (`None`) paths in the one fixture. Cross-check against the feature-side behavior by reading the equivalent `lazy-state.py` fixture if one exists.

**Integration Notes for Next Phase:**
- The token string form is `@@lazy-ref nonce=<hex>` — Phase 2's parity assertion keys on the presence of the `state["cycle_prompt_ref"] = ` assignment in BOTH scripts, not on the literal token.
- Do NOT touch `lazy_core.register_emission_if_marked` — it already returns the entry; only the caller-side surfacing was missing.

---

### Phase 2: Parity-audit assertion for `cycle_prompt_ref` surfacing

**Scope:** Add a targeted assertion to `lazy_parity_audit.py` so the audit fails if either `--emit-prompt` path surfaces `cycle_prompt_ref` while the other does not — closing the SPEC's "Secondary gap" (the audit did not catch this divergence). Targeted, not the generic "every surfaced field" sweep (SPEC Open Question: targeted is sufficient to close this bug; generic is a larger hardening, deferred).

⚖ policy: targeted-vs-generic parity assertion → targeted (sizing/completeness only — same product behavior; SPEC Open Question marks targeted sufficient and generic as separate larger hardening)

**Deliverables:**
- [ ] In `lazy_parity_audit.py`: add a check (in the state-script parity audit path, alongside the existing parity assertions) that BOTH `lazy-state.py` and `bug-state.py` assign `state["cycle_prompt_ref"]` in their `--emit-prompt` block — fail (non-zero / reported divergence) if exactly one does. Use the existing audit's reporting/diff convention; do not invent a new failure channel.
- [ ] Tests: `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-bug-batch` passes AFTER Phase 1 lands (both scripts now surface the field), and the new assertion is exercised. Confirm `lazy_parity_audit.py --repo-root .` (all pairs) stays green.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy_parity_audit.py --repo-root . --pair lazy-bug-batch` exits 0 with the new `cycle_prompt_ref` parity assertion present and passing. (Optionally demonstrable: reverting Phase 1's assignment makes the audit fail — proving the assertion is load-bearing, not inert.)

**Prerequisites:**
- Phase 1: `bug-state.py` must surface `cycle_prompt_ref` first — otherwise the new parity assertion would (correctly) fail on the unfixed bug script.

**Files likely modified:**
- `user/scripts/lazy_parity_audit.py` — add the targeted `cycle_prompt_ref` surfacing-parity assertion.

**Testing Strategy:**
Run the parity audit for the `lazy-bug-batch` pair and for all pairs; both green. Sanity-check the assertion is load-bearing by confirming it references both scripts' `cycle_prompt_ref` assignment (a missing assignment in either is a reported divergence).

**Integration Notes for Next Phase:**
- Last phase. Once both phases land, the bug pipeline dispatches real-skill cycles by reference (49-char token) instead of re-inlining 9.5–12K-char prompts, and the parity gate prevents silent re-drift.

**Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md / PHASES.md `**Status:**` to Fixed and writes `FIXED.md` once the validation tail (state-script `--test` + parity audit, in lieu of `/mcp-test` for this no-MCP-surface fix) certifies both phases. This phase authors NO status-flip / receipt / archive checkbox row.
