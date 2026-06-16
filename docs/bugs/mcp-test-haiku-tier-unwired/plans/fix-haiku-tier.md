---
kind: fix-plan
feature_id: mcp-test-haiku-tier-unwired
status: Ready
created: 2026-06-16
complexity: mechanical
phases: [1]
---

> **Plan** — generated manually (operator-directed manual /lazy-bug-batch walk) on 2026-06-16.
> To execute: `/execute-plan C:\Users\Jacob\source\repos\claude-config\docs\bugs\mcp-test-haiku-tier-unwired\plans\fix-haiku-tier.md`
> This plan is fully self-contained.

# Implementation Plan — mcp-test-haiku-tier-unwired

**PHASES.md files:**
- `C:\Users\Jacob\source\repos\claude-config\docs\bugs\mcp-test-haiku-tier-unwired\PHASES.md` (1 phase)

**SPEC.md files:**
- `C:\Users\Jacob\source\repos\claude-config\docs\bugs\mcp-test-haiku-tier-unwired\SPEC.md`

**Total phases:** 1
**Plan version:** v1 (reference-based)

## Work Units

- [ ] WU-1 — emit_cycle_prompt: mcp-test → haiku base tier (loop still escalates to sonnet) + two RED-first tests in test_lazy_core.py + optional `model: haiku` frontmatter on mcp-test/SKILL.md

## EXECUTION MODEL

> **EXECUTION-CONTEXT OVERRIDE (autonomous pipeline / manual walk).** This plan is being executed by the orchestrator INLINE (no Agent split). Perform all work with Read / Edit / Write. Obey TDD (write the failing assertions before the implementation), run the quality gates, and commit. Never invoke a nested `/lazy*`.

## WU-1 — mcp-test → haiku base tier

**Files:** `user/scripts/lazy_core.py`, `user/scripts/test_lazy_core.py`, `repos/algobooth/.claude/skills/mcp-test/SKILL.md`

**TDD steps:**
1. **RED** — add to `test_lazy_core.py` (after `test_emit_cycle_prompt_loop_append_and_model_flip`):
   - `test_emit_cycle_prompt_mcp_test_cycle_model_haiku`: `_emit_state(sub_skill="/mcp-test", spec_path=<tempdir>)`; emit with `repeat_count=1` and `repeat_count=None` over `_REAL_TEMPLATE_DIR` → assert `model == "haiku"`.
   - `test_emit_cycle_prompt_mcp_test_loop_cycle_model_sonnet`: same state, `repeat_count=2` → assert `model == "sonnet"` and `"LOOP DETECTED" in prompt`.
   - Register both in the runner list (`:13977` neighborhood). Confirm RED: the haiku test fails because the non-loop case returns `opus`.
2. **GREEN** — in `emit_cycle_prompt` (`lazy_core.py`), move `norm_sub_skill = norm_skill` above the base assignment and replace `model = "opus"` with `model = "haiku" if norm_sub_skill == "mcp-test" else "opus"`. Leave the execute-plan and loop branches untouched.
3. **Optional** — add `model: haiku` to `mcp-test/SKILL.md` frontmatter.
4. **Gates** — `python user/scripts/test_lazy_core.py`; `python user/scripts/lazy-state.py --test`; `python user/scripts/bug-state.py --test`. All green.

**Acceptance:** the two new tests pass; the full regression net stays green; a `mcp-test` probe's `cycle_model` is `haiku` on the happy path and `sonnet` under a loop.
