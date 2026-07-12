# Implementation Phases — Run-end gate refusals emit no `gate-refusal` telemetry event

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — claude-config is a config/harness repo with no Tauri/MCP dev runtime; the entire fix is Python state-script edits verified by pytest unit/subprocess tests + the coupled-pair parity audit, structurally outside any MCP-reachable surface.

## Validated Assumptions

Recorded per `/spec-phases` Step 2.7. All load-bearing assumptions here are **code-provable** (no runtime spike needed); each is verified below and re-asserted by the Phase 1 tests.

- **`append_telemetry_event` exists and already emits `"gate-refusal"`.** Verified: `user/scripts/lazy_core.py:15812` (`def append_telemetry_event(event, *, item_id=None, data=None, now=None) -> bool`), already called with `kind="gate-refusal"` at `lazy-state.py:11618/12283/12507` and `bug-state.py:7561/7755`. Negative-evidence grep: no `unimplemented`/`todo`/rejection near the symbol. The fix REUSES it unchanged — no new telemetry code.
- **The run marker is still live at all three refusal sites.** Verified: the three run-end gates refuse with the marker **kept** ("The marker was NOT deleted"), i.e. they run BEFORE `delete_run_marker()`. Since `append_telemetry_event` is marker-gated (returns `False`/no-op when no live marker), the emission actually lands precisely because the marker is present at refusal time. This is the load-bearing reason the observability works.
- **Emission is a pure additive side-channel — zero state side effects, refusal behavior unchanged.** Verified: `append_telemetry_event` is fail-open (`try/except Exception: return False`), writes only one JSONL line to the telemetry ledger, and callers never branch on its return. Placing the call immediately before the existing `return 1` (inside the refusal branch) cannot change the refusal decision.
- **Drift correction (mechanical) — `item_id=None` (run-level), not the SPEC's `item_id=<marker feature/bug id>`.** Verified: the run marker (`write_run_marker`, `lazy_core.py:10498`) carries no `feature_id`/`bug_id` field — no item id is available at these run-end sites. Precedent: the existing run-end/run-start emissions and `refuse_run_start_clobber`'s `containment-refusal` calls pass no `item_id` (run-level events). The plan therefore emits run-level `gate-refusal` events with `item_id=None` and a descriptive `data` payload. This is a mechanical grounding correction, not a design change.

**MCP tool-existence audit:** no-op — claude-config declares no `.claude/skill-config/mcp-tool-catalog.md` (repo has no MCP surface). Skip reason recorded.

## Touchpoint Audit (verified against the live codebase — Explore agent, 2026-07-11)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy-state.py` | yes | `main()` `if args.run_end:` block @11855; refusal sites: unacked-hardening 11869–11885, efficacy-flush 11912–11929, checkpoint-auth 11957–11985 | modify | Insert one `lazy_core.append_telemetry_event("gate-refusal", item_id=None, data={...})` immediately before each of the three `return 1`s, inside the refusal branch. Reuse existing `lazy_core.append_telemetry_event` — do NOT write new telemetry code. |
| `user/scripts/bug-state.py` | yes | `main()` `if args.run_end:` block @7239; refusal sites: unacked-hardening 7252–7267, efficacy-flush 7292–7309, checkpoint-auth 7323–7344 | modify | Mirror the three insertions (coupled-pair — `bug-state.py` comments mark these "coupled-pair mirror of lazy-state.py"). Keep the `data.gate` discriminator strings identical across both scripts so aggregation sees one signal family (SPEC D1). |
| `user/scripts/lazy_core.py` | yes | `append_telemetry_event` @15812 (marker-gated, fail-open); `pending_hardening` @15564; `efficacy_breadcrumb_present`; `read_telemetry_events` (ledger read-back) | reuse | Reuse as-is. No edit expected. |
| `user/scripts/test_lazy_core.py` | yes | `_TESTS` seed @16188, extended via `_TESTS = _TESTS + [("name", fn)]` blocks; guard `test_no_orphaned_test_functions` @24399; mirror pattern `test_telemetry_append_envelope_shape_and_now_injection` @29224 (arm marker → call → `read_telemetry_events()` → assert `event`/`data`) | modify | Add subprocess-driven tests asserting each of the three run-end refusals appends a `gate-refusal` event with the right `data.gate`. Register EVERY new `def test_*` in a `_TESTS = _TESTS + [(...)]` block (the orphan guard fails otherwise). |

All planned paths exist; no net-new files. Adding 6 new call sites of `append_telemetry_event` (no signature change → no consumer migration / blast radius).

## Out of Scope (flagged, not planned)

- **Adjacent 4th refusal — the terminal-reason gate** (`lazy-state.py:11988-12009` / `bug-state.py:7346-7362`, `elif reason == "terminal": … return 1`) lives in the same `--run-end` block and also emits no telemetry. The concluded SPEC names **exactly three** gates (unacked-hardening, efficacy-flush-missing, checkpoint-auth), so this site is deliberately excluded here. If the efficacy loop later wants full run-end coverage, it is a trivial follow-up using the identical pattern — recorded so it is not silently lost.

---

### Phase 1: Emit `gate-refusal` telemetry at the three run-end refusal sites (coupled pair) + tests

**Scope:** Add an observability-only `append_telemetry_event("gate-refusal", …)` call at each of the three `--run-end` refusal sites in BOTH state scripts, mirroring the established `containment-refusal` / `--verify-ledger gate-refusal` call sites. The gates' refusal decisions and exit codes are UNCHANGED — the event is purely additive, marker-gated, and fail-open. This is the whole fix; it is one cohesive change and one coupled-pair mirror, so a single phase is correct.

**TDD:** yes. Tests assert the ledger append on each refusal path (they are RED before the emissions exist — the ledger has no `gate-refusal` line after a run-end refusal — and GREEN after).

**Deliverables:**
- [ ] `lazy-state.py` — insert `lazy_core.append_telemetry_event("gate-refusal", item_id=None, data={"gate": "unacked-hardening", "op": "--run-end", "reason": "<short>"})` immediately before the `return 1` in the unacked-hardening refusal branch (@~11869–11885).
- [ ] `lazy-state.py` — same, `data.gate = "efficacy-flush-missing"`, before the efficacy-flush refusal `return 1` (@~11912–11929).
- [ ] `lazy-state.py` — same, `data.gate = "checkpoint-auth"`, before the checkpoint-authorization refusal `return 1` (@~11957–11985).
- [ ] `bug-state.py` — mirror all three insertions at the corresponding refusal branches (@~7252–7267, ~7292–7309, ~7323–7344). Identical `data.gate` discriminator strings and call shape (coupled-pair mirror).
- [ ] Tests (`test_lazy_core.py`): a subprocess-driven test per refusal path **per script** (or a parametrized pair) that arms an isolated state dir + live run marker, sets up state to reach the target gate, invokes `--run-end` on the script, confirms exit code 1 + marker kept (behavior unchanged), and asserts the telemetry ledger's last event is `gate-refusal` with the expected `data.gate`. Register every new `def test_*` in a `_TESTS = _TESTS + [(...)]` block.
- [ ] Tests: one assertion that a *successful* `--run-end` (all gates passing / overrides supplied) still emits the existing `run-end` event and NO spurious `gate-refusal` (guards against over-emission).

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` (the repo's pytest-style runner) passes, with the new run-end-refusal telemetry tests going red→green — i.e. after a real `--run-end` that refuses on each gate, `read_telemetry_events()` shows a `gate-refusal` event carrying the matching `data.gate`. This is a runnable command whose observable is the actual ledger append, not "unit tests pass" in the abstract.

**Gate-reachability note for the test author (ordering matters):** the three gates fire in sequence inside the `--run-end` block. To exercise a later gate you must satisfy the earlier ones:
- **unacked-hardening** is first → seed the deny ledger with ≥1 unacked entry (`pending_hardening() > 0`), pass NO `--ack-unhardened`.
- **efficacy-flush-missing** → pass `--ack-unhardened` (or zero pending) to clear gate 1, ensure no efficacy breadcrumb is present, pass NO `--efficacy-skip-authorized`.
- **checkpoint-auth** → clear gates 1 and 2 (`--ack-unhardened`, `--efficacy-skip-authorized`), invoke `--run-end --reason checkpoint` against an ATTENDED marker, pass NO `--operator-authorized`.
The in-script `telemetry-ledger-chokepoints` `--test` fixture (`lazy-state.py:10190-10380` / `bug-state.py:5599-5771`) is the reference for subprocess-driving a run-end refusal and asserting the appended event; the new tests may extend that fixture per script instead of / in addition to `test_lazy_core.py` if that proves cleaner, as long as the SPEC's "assert the event is appended on each refusal path" intent is met.

**Prerequisites:** None (single phase).

**Files likely modified:**
- `user/scripts/lazy-state.py` — three insertions before existing `return 1`s in the run-end block.
- `user/scripts/bug-state.py` — three mirrored insertions.
- `user/scripts/test_lazy_core.py` — new registered tests.

**Testing Strategy:**
Subprocess-driven, mirroring `test_telemetry_append_envelope_shape_and_now_injection` (arm marker → act → `read_telemetry_events()` → assert `event`/`data`) and the `telemetry-ledger-chokepoints` refusal fixture. Each test isolates the state dir, arms a live run marker (so the marker-gated append fires), drives one gate to refusal, and asserts BOTH the unchanged refusal (exit 1, marker kept) AND the new `gate-refusal` ledger line. Fail-open is inherent to `append_telemetry_event`; no additional error-path test is required beyond confirming the emission is additive.

**Quality gates (orchestrator, before marking fixed):**
- `python user/scripts/lazy_parity_audit.py --repo-root .` → exit 0 (the coupled-pair mirror across `lazy-state.py`/`bug-state.py` and the SKILL parity must stay green).
- `python user/scripts/test_lazy_core.py` → all pass (incl. the new tests and the orphan-guard).
- `python user/scripts/doc-drift-lint.py --repo-root .` → exit 0 (no doc claims changed; sanity check).

**Integration Notes:**
- The emission MUST sit INSIDE each refusal branch, immediately before `return 1` — not before the `if`, or it would fire on the pass path too.
- Use `item_id=None` (run-level) — no feature/bug id exists on the run marker at these sites (see Validated Assumptions). Matches existing run-level emissions.
- Keep the three `data.gate` discriminator strings byte-identical between `lazy-state.py` and `bug-state.py` so the efficacy loop / `kpi-scorecard.py` / `pipeline_visualizer/trends.py` aggregate one `gate-refusal` family (SPEC D1).
- **Completion (gate-owned):** the `__mark_fixed__` gate flips `SPEC.md` **Status:** to `Fixed`, writes `FIXED.md`, and archives — do NOT author a status-flip / receipt checkbox row here.

---

## State Machine / Loop Closure

This bug supplies the **measurement half** for run-end refusals: once these events emit, the efficacy-flush gate (commit `7d49490`) and the observed-friction / efficacy interventions can declare a real `target_signal: event:gate-refusal` (`--expected-direction decrease`) instead of degrading to `undeclared` / INCONCLUSIVE-by-construction. No gate behavior changes; the deliverable is the countable signal.
