# Implementation Phases — mcp-test haiku tier never wired into cycle-model selection

> Phases for [`SPEC.md`](./SPEC.md)

**MCP runtime:** not-required — harness-internal Python (`lazy_core.emit_cycle_prompt`) + its in-file/`test_lazy_core.py` regression net; no AlgoBooth app surface, no Tauri/MCP HTTP server. Verification is `python user/scripts/test_lazy_core.py` + `lazy-state.py --test` / `bug-state.py --test`, the canonical regression net per `user/scripts/CLAUDE.md`.

## Validated Assumptions

All load-bearing assumptions are **code-provable** — verified by reading the cited source during investigation (SPEC Evidence), not inferred. No runtime spike is required:

- `emit_cycle_prompt` (`lazy_core.py:4432`) sets `model = "opus"` as an unconditional base; the ONLY downgrades are `execute-plan` + `complexity: mechanical` → sonnet (`:4434–4441`) and the loop block `repeat_count >= 2` → sonnet (`:4443–4455`). There is no haiku branch and no `mcp-test` case. (SPEC Proven Finding 1.)
- The loop block sets `model = "sonnet"` **unconditionally** (`:4455`). From an `opus` base this is the existing cost-saving downgrade; from a `haiku` base the SAME literal target is the correct escalation (a stuck mechanical cycle gets a stronger model). So the single `"sonnet"` literal is correct for both bases — no tier-max arithmetic is needed (resolves SPEC Open-Q "tier-model representation": the narrow per-sub_skill base is sufficient).
- `mcp-test` and `execute-plan` are mutually-exclusive `sub_skill` values, so the haiku base never collides with the execute-plan mechanical/complex branch.
- The opus-on-failure recovery for mcp-test is a SEPARATE emit path (`emit_dispatch_prompt`, `needs-runtime-redispatch`, `dispatch_model` always opus — tagged `(opus, recovery)`); it is unaffected by this change.
- `bug-state.py` and `lazy-state.py` both call the shared `emit_cycle_prompt`, so the bug pipeline inherits the tier automatically (no separate path).
- `test_emit_cycle_prompt_binding_matrix_real_template` (`test_lazy_core.py:7236`) asserts `model == "opus"` for `["/execute-plan", "/retro", "/retro-feature", "/spec"]` — `mcp-test` is NOT in that list, and `test_emit_cycle_prompt_mcp_test_variant_anchors_real_template` (`:7263`) asserts only anchors, not model. So a `mcp-test → haiku` base breaks no existing assertion.

## Touchpoint Audit (verified during planning — read-only)

| Planned file | Exists? | Real symbols (verified) | Action | Reuse / refactor directive |
|--------------|---------|-------------------------|--------|----------------------------|
| `user/scripts/lazy_core.py` | yes | `emit_cycle_prompt` base `model = "opus"` `:4432`; `norm_sub_skill = norm_skill` `:4433`; execute-plan mechanical→sonnet `:4434–4441`; loop block →sonnet `:4443–4455` | refactor | Define `norm_sub_skill` BEFORE the base assignment; set `model = "haiku" if norm_sub_skill == "mcp-test" else "opus"`. Leave both downgrade branches untouched (the loop `"sonnet"` literal is correct for both bases). |
| `user/scripts/test_lazy_core.py` | yes | `emit_cycle_prompt` model-tier tests `:7364–7505`; runner list `:13977–13983` | refactor | Add two RED-first tests: `mcp-test` non-looping → `haiku`; `mcp-test` looping (`repeat_count=2`) → `sonnet` (escalation). Register both in the runner list. |
| `repos/algobooth/.claude/skills/mcp-test/SKILL.md` | yes | frontmatter `:1–5` (no `model:` field); description "haiku happy path" `:3` | refactor (optional) | Add `model: haiku` frontmatter so a direct interactive `/mcp-test` also honors the intent. Secondary — does not affect the orchestrator batch path (which is the root-cause surface). |

No path is net-new — the fix extends an existing, well-tested selector. No design fork surfaced (the one SPEC open question — tier representation — is resolved by the Validated Assumptions above: the narrow base suffices).

---

### Phase 1: Wire the mcp-test → haiku base tier into emit_cycle_prompt — TDD

**Scope:** Give `emit_cycle_prompt` a per-`sub_skill` base model tier so a happy-path `mcp-test` cycle dispatches on **haiku**, escalating to **sonnet** on the loop block. Root-cause fix (SPEC Proven Findings 1–3).

**Deliverables:**
- [ ] `emit_cycle_prompt` selects `model = "haiku"` when `norm_sub_skill == "mcp-test"`, else `"opus"` (the existing base). `norm_sub_skill` is computed before the base assignment. The execute-plan mechanical→sonnet branch and the loop→sonnet branch are unchanged.
- [ ] Two RED-first tests in `test_lazy_core.py`, registered in the runner list:
  - `test_emit_cycle_prompt_mcp_test_cycle_model_haiku` — `sub_skill="/mcp-test"`, `repeat_count` 1 and None → `model == "haiku"`.
  - `test_emit_cycle_prompt_mcp_test_loop_cycle_model_sonnet` — `sub_skill="/mcp-test"`, `repeat_count=2` → `model == "sonnet"` AND `"LOOP DETECTED"` present (escalation composes with the loop block).
- [ ] (Optional, same phase) `mcp-test/SKILL.md` frontmatter gains `model: haiku` so an interactive `/mcp-test` honors the intent too.

**Minimum Verifiable Behavior:** `python user/scripts/test_lazy_core.py` passes including the two new tests; the new tests fail RED against the unmodified selector (model `opus` for the non-loop case) for the right reason before the fix. `lazy-state.py --test` and `bug-state.py --test` stay green (the byte-pinned baselines are unaffected — the `--test` harnesses never emit a `mcp-test` cycle_model line).

**Prerequisites:** None (single phase).

**Files likely modified:**
- `user/scripts/lazy_core.py` — `emit_cycle_prompt` base-tier line (verified `:4432–4433`).
- `user/scripts/test_lazy_core.py` — two new tests + runner registration.
- `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — optional `model: haiku` frontmatter.

**Testing Strategy:** TDD against `test_lazy_core.py` (the selector is directly unit-testable via `emit_cycle_prompt(..., template_dir=_REAL_TEMPLATE_DIR)`). Write both assertions FIRST; confirm RED (the non-loop case returns `opus`); then make the one-line base change. Run the full shared-import gate set: `test_lazy_core.py`, `lazy-state.py --test`, `bug-state.py --test`.

---

## Notes

- **No MCP/runtime phase.** Per the `**MCP runtime:** not-required` header, all verification is the Python regression net. There is no app surface to MCP-test.
- **Completion (gate-owned):** the `__mark_fixed__` gate flips SPEC.md **Status:** to Fixed and writes FIXED.md once the validation tail passes — this PHASES.md never flips the top-level status.
