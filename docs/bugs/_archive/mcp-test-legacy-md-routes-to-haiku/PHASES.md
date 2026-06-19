# Implementation Phases — Autonomous mcp-test cycle dispatches legacy `.md` to haiku

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — this is a pure state-script / cycle-model-emit fix in `user/scripts/`; the harness repo has no Tauri/MCP runtime and the change is covered entirely by the in-file `--test` smoke harness + `pytest` (mcp-testing SPEC class: tooling/infra outside MCP reach).

**Status:** Fixed

## Summary

`emit_cycle_prompt` (`lazy_core.py:4761`) hardcodes the mcp-test cycle model to `haiku` at dispatch time, before the subagent resolves which scenario it will run. The script-derived tier signal `route_mcp_test_tier` (`surface_resolver.py:379`) — which would escalate a legacy `.md`-only (unconverted) scenario to Sonnet — exists but is consulted ONLY by the interactive `mcp-test` SKILL.md prose, never by the autonomous cycle-model emit. The fix wires the tier signal into `emit_cycle_prompt` so the autonomous path matches the documented (Phase-4) routing intent.

The fix lives entirely in the shared `lazy_core.py`, so `bug-state.py` inherits it by construction (parity preserved, per the SPEC's Affected-Area "Mirror" row).

## Scenario-resolution-at-emit-time decision (resolved)

⚖ policy: emit-time scenario resolution → conservative escalation (option b)

The SPEC's Open Question asks how `emit_cycle_prompt` obtains a `scenario_path`/`yaml_exists` at dispatch time, when the orchestrator knows the `feature_id`/`spec_path` but not necessarily the resolved scenario. Two options:

- **(a)** Map feature/bug → candidate scenario(s) deterministically in the state script and pass `yaml_exists` precisely.
- **(b)** Escalate conservatively to Sonnet whenever ANY candidate scenario for the item lacks a converted YAML counterpart (and stay haiku only when ALL candidate scenarios are ready converted YAML, with no adverse prior verdict).

Both options produce the **same end-state product behavior** — an unconverted-`.md` mcp-test cycle escalates to Sonnet; a ready converted-YAML happy path stays haiku. They differ only in implementation precision/effort, not in user-visible behavior — this is a scope-class (D7) decision, not a product-class one. Per the completeness-first standing policy and the SPEC's own guidance ("(b) fails safe toward Sonnet and matches `route_mcp_test_tier`'s own 'unknown → Sonnet' bias"), **option (b)** is chosen: it is the most robust path, requires no new feature→scenario mapping infrastructure, and inherits `route_mcp_test_tier`'s built-in fail-safe (no scenario / no ready YAML → Sonnet). The implementation enumerates the item's candidate `mcp-tests/*.md` + `corpus/live/*.yaml` scenarios under the resolved spec/bug dir; if every candidate is a ready converted YAML (and no adverse prior verdict), stay haiku — otherwise escalate to Sonnet.

---

### Phase 1: Wire `route_mcp_test_tier` into `emit_cycle_prompt`

**Scope:** Replace the hardcoded `model = "haiku" if norm_sub_skill == "mcp-test" else "opus"` constant in `emit_cycle_prompt` with a call into the existing `surface_resolver.route_mcp_test_tier` signal, using conservative candidate-scenario enumeration (option b above). A legacy-`.md`-only (unconverted) mcp-test scenario routes to Sonnet at dispatch; a ready converted-YAML happy path stays haiku. Non-mcp-test cycles keep the `opus` base. The existing loop-block downgrade (`repeat_count >= 2` → sonnet) and the `/execute-plan` complexity tiering are untouched and continue to compose correctly (both only ever downgrade toward sonnet).

**Deliverables:**
- [x] Tests (test-first): in `test_lazy_core.py`, add a fixture asserting an mcp-test cycle whose item has a legacy `.md` scenario with NO converted `corpus/live/*.yaml` counterpart → `model == "sonnet"` (and `ok is True`). Add a sibling fixture: an mcp-test cycle whose candidate scenario(s) are all ready converted YAML → `model == "haiku"`. Register both in the `test_lazy_core.py` runner list (mirroring lines ~14376–14377). Run them first and confirm the new sonnet-escalation fixture FAILS against the current hardcoded-haiku code.
- [x] Update the existing regression `test_emit_cycle_prompt_mcp_test_cycle_model_haiku` (`test_lazy_core.py:7563`): its current fixture is a bare empty `spec_dir` with no scenarios — under option (b)'s conservative bias that is now a Sonnet escalation (no ready YAML). Reshape the fixture so the haiku assertion holds by giving it a ready converted-YAML scenario (or split into the explicit ready-YAML → haiku case from the deliverable above), so the "happy path → haiku" invariant is preserved with a fixture that actually represents the happy path. Keep `test_emit_cycle_prompt_mcp_test_loop_cycle_model_sonnet` green (loop-block escalation is orthogonal).
- [x] In `lazy_core.py` `emit_cycle_prompt`, import/call `route_mcp_test_tier` (from `surface_resolver`) for the `norm_sub_skill == "mcp-test"` branch: enumerate the item's candidate scenarios under the resolved spec/bug dir (`mcp-tests/*.md` legacy + `corpus/live/*.yaml` converted); set `model = "haiku"` iff every candidate resolves to haiku via the tier router (ready YAML, no adverse prior verdict), else `model = "sonnet"`. Fail-safe: if no candidate scenario can be resolved or enumeration errors, escalate to Sonnet (matches the router's "unknown → Sonnet" bias) — never silently fall back to haiku.
- [x] Replace the literal-`"haiku"` claim in the `model = "haiku" if ...` comment block (`lazy_core.py:~4749–4761`) with a comment documenting the tier-routed selection and the conservative-escalation rationale (cite this bug slug + the SPEC).

**Implementation Notes (2026-06-19):**
- Landed the fix inline (dispatch-limited cycle, no Agent tool — test-first per WU).
- **Files:** `user/scripts/lazy_core.py` (new helper `_mcp_test_cycle_model(spec_path)` + the `emit_cycle_prompt` branch now calls it for `norm_sub_skill == "mcp-test"`, comment block rewritten); `user/scripts/test_lazy_core.py` (2 new fixtures + reshaped haiku fixture + runner-list registration); `user/scripts/CLAUDE.md` (mcp-test model-tier routing section amended).
- **Import seam:** lazy in-function import of `route_mcp_test_tier` from `surface_resolver` (the `validation_readiness.py` try/except + sys.path-fallback pattern) — avoids any module-load coupling/cycle and keeps non-mcp-test cycles cost-free. No circular-import wall hit.
- **Candidate-scenario dirs enumerated:** `<spec_dir>/mcp-tests/` walked recursively for `*.md` (legacy) + `*.yaml`/`*.yml` (converted) — covers both a flat `mcp-tests/*.md` and the canonical `mcp-tests/corpus/live/*.yaml` nesting.
- **Conservative escalation confirmed:** haiku ONLY when ≥1 candidate resolves AND every candidate → "haiku" via the router; zero candidates / non-dir spec_path / falsy spec_path / any exception → sonnet (fail-safe, never silent haiku). Loop-block downgrade + execute-plan complexity tiering untouched (both still only move toward sonnet).
- **RED→GREEN:** the legacy-`.md`→sonnet fixture failed (`got 'haiku'`) before the `lazy_core.py` edit, passes after. Gates: `lazy-state.py --test`, `bug-state.py --test` (both green, no baseline drift), `test_lazy_core.py` 564/564, `test_surface_resolver.py` 39/39.

**Minimum Verifiable Behavior:** `python3 user/scripts/lazy-state.py --test` and `python3 user/scripts/bug-state.py --test` both green (bug pipeline inherits the fix via shared `lazy_core`), and `pytest user/scripts/test_lazy_core.py` green — with the new legacy-`.md`→sonnet fixture passing and the reshaped happy-path→haiku fixture passing. The new fixture demonstrably failed before the `lazy_core.py` edit.

**Runtime Verification** *(checked by integration test or manual testing):*
- [x] An mcp-test cycle emitted for an item whose only scenario is an unconverted legacy `.md` reports `model: sonnet` in the `emit_cycle_prompt`/`--emit-prompt` JSON. <!-- verification-only --> <!-- verified by test_lazy_core.py::test_emit_cycle_prompt_mcp_test_legacy_md_escalates_sonnet (564/564 green); Implementation Notes: RED→GREEN confirmed -->

**Prerequisites:** None.

**Files likely modified:**
- `user/scripts/lazy_core.py` — `emit_cycle_prompt` (~4748–4761): call `route_mcp_test_tier` with conservative candidate enumeration instead of the hardcoded haiku constant; update the explanatory comment.
- `user/scripts/test_lazy_core.py` — new legacy-`.md`→sonnet + ready-YAML→haiku fixtures; reshape `test_emit_cycle_prompt_mcp_test_cycle_model_haiku`; register new fixtures in the runner list.
- `user/scripts/surface_resolver.py` — read-only consumer (`route_mcp_test_tier` already correct); no change expected unless a tiny import/helper seam is needed.

**Testing Strategy:**
Test-first: write the failing sonnet-escalation fixture, confirm it fails against current code, then implement the `lazy_core.py` wiring until green. The in-file `--test` harness for both `lazy-state.py` and `bug-state.py` (shared `lazy_core`) plus `test_lazy_core.py` are the hermetic regression net. Per the Coupling Rule, run the full set: `lazy-state.py --test`, `bug-state.py --test`, `test_lazy_core.py`, and `test_surface_resolver.py` (to confirm `route_mcp_test_tier` itself is unregressed). Baselines (`tests/baselines/lazy-state-test-baseline.txt`, `bug-state-test-baseline.txt`) are byte-pinned — regenerate ONLY via the `_normalize_smoke_output` helper if the `--test` output legitimately changes.

**Integration Notes for Next Phase:** N/A — single-phase fix. Update the `## mcp-test model-tier routing` section of `user/scripts/CLAUDE.md` (currently states the helper is consulted by the interactive SKILL.md prose only) to note that `emit_cycle_prompt` now also consults it on the autonomous path — done as a doc deliverable within this phase rather than deferred.

- [x] Update `user/scripts/CLAUDE.md` → `## mcp-test model-tier routing` to record that `emit_cycle_prompt` now consults `route_mcp_test_tier` on the autonomous cycle-model path (option-b conservative escalation), closing the SPEC's "wired into zero autonomous paths" gap.

---

## Cross-feature Integration Notes

No hard deps on Complete upstreams. Related prior art (cross-linked in the SPEC `**Related:**`): `harness-hardening-retro-fixes Phase 4` (introduced `route_mcp_test_tier`), sibling bug `docs/bugs/_archive/probe-full-read-before-dispatch/`. The complementary AlgoBooth-side content remedy (bulk-migrate legacy `.md`→YAML) is explicitly OUT OF SCOPE here — it lives in the AlgoBooth repo.
