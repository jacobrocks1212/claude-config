# mcp-test haiku tier never wired into cycle-model selection — Investigation Spec

> `/lazy-batch` dispatches every happy-path `/mcp-test` cycle on **Opus**, even though the skill was "switched to haiku." The switch landed only as description prose; the dispatch-model selector has no haiku branch.

**Status:** Concluded
**Severity:** P2
**Discovered:** 2026-06-16
**Placement:** docs/bugs/mcp-test-haiku-tier-unwired
**Related:** `docs/specs/lazy-hardening/`, `repos/algobooth/.claude/skills/mcp-test/SKILL.md` (Informed Dispatcher rewrite, commit ae47a4d), `user/scripts/lazy_core.py::emit_cycle_prompt`

---

## Verified Symptoms

1. **[VERIFIED]** In the live AlgoBooth `/lazy-batch` run (session `deb9f0cf-…`), the `mcp-test` cycle for `d8-session-format` was dispatched as an `Agent` call with `model: "opus"`. The on-screen `disp mcp-test → d8-session-format (opus)` label is accurate, not a display bug. — confirmed by extracting the `Agent` tool_use `input.model` from the session transcript.
2. **[VERIFIED]** This is the steady-state behavior, not a one-off: every happy-path `mcp-test` dispatch in that session ran on Opus (`mcp-test AQO`, `mcp-test snapshot`, `mcp-test snapshot re-verify`, `mcp-test d8-session-format` → all `opus`). The only non-Opus `mcp-test` dispatch (`cycle 13` → `sonnet`) was a loop/mechanical downgrade. — confirmed from the same transcript.
3. **[VERIFIED]** The intended behavior is haiku: `mcp-test/SKILL.md` describes itself as "**haiku happy path, Sonnet only on failure**". — confirmed by reading the skill frontmatter.

## Reproduction Steps

1. Run `/lazy-batch` (or `/lazy-bug-batch`) in a repo whose pipeline routes a feature to the Step 9 MCP gate.
2. Observe the cycle dispatch when `sub_skill == "mcp-test"`.

**Expected:** the happy-path `mcp-test` cycle dispatches on **haiku** (per the Informed Dispatcher design — the model only runs a deterministic engine and reads a small verdict), escalating to **sonnet** on a loop and **opus** only on a recovery re-dispatch.
**Actual:** the cycle dispatches on **opus** every time (downgrading to sonnet only when the generic loop-block fires).
**Consistency:** always (every non-looping `mcp-test` cycle).

## Evidence Collected

### Source Code

The batch dispatch model is **not** chosen by the skill frontmatter — it is chosen by `emit_cycle_prompt` in `user/scripts/lazy_core.py`, whose result is surfaced as `state["cycle_model"]` in `lazy-state.py` (lines 6381–6393) and dispatched verbatim by the orchestrator.

`emit_cycle_prompt` model selection (`lazy_core.py`):
- **Line 4432** — `model = "opus"` is the unconditional base.
- **Lines 4434–4441** — the ONLY base-tier branch: an `execute-plan` cycle whose current plan part is tagged `complexity: mechanical` downgrades to `sonnet`. (`plan_complexity` returns the conservative `complex`/opus default otherwise.)
- **Lines 4443–4455** — the loop block: `repeat_count >= 2` appends the loop guidance and sets `model = "sonnet"`.
- **There is no `haiku` branch anywhere, and no `mcp-test` special-case.** So a `mcp-test` cycle takes the `opus` base and never downgrades unless it loops.

`mcp-test/SKILL.md` (frontmatter, lines 1–5): description claims "haiku happy path, Sonnet only on failure" but carries **no `model:` field** — so even an interactive `/mcp-test` (outside batch) runs on the session model, never haiku. The haiku intent is honored in **zero** code paths.

### Runtime Evidence

Windows native session `C--Users-Jacob-repos-AlgoBooth/deb9f0cf-1a14-43db-8517-7bf7a5f60ebb.jsonl`. Extracted `Agent` dispatches whose prompt/description names `mcp-test`:

```
('sonnet', 'lazy-batch cycle 13: mcp-test')              ← loop/mechanical downgrade
('opus',   'lazy-batch cycle: mcp-test AQO')
('opus',   'lazy-batch cycle: mcp-test snapshot')
('opus',   'lazy-batch cycle: mcp-test snapshot re-verify')
('opus',   'lazy-batch cycle: mcp-test d8-session-format')  ← the one in the screenshot
```

### Git History

`git log -i --grep=haiku` returns only `ae47a4d feat(algobooth/mcp-test): rewrite to Informed Dispatcher (deterministic-runner Phase 8)` — the rewrite that introduced the "haiku happy path" prose. No commit ever touched `emit_cycle_prompt`'s model selection to add a haiku tier. The "switch to haiku" was **documentation-only**.

### Related Documentation

- `user/scripts/CLAUDE.md` — documents that the lazy skills are thin wrappers and the dispatch model is orchestrator-owned (Phase 9 per-part tiering), confirming the fix belongs in `emit_cycle_prompt`, not the skill frontmatter.
- `repos/algobooth/.claude/skills/mcp-test/SKILL.md` — the Informed Dispatcher rewrite that collapsed the model's role to: resolve scenario → ensure runtime → run engine → read small verdict → forward sentinel → reconcile PHASES. This is the justification for haiku being sufficient on the happy path.

## Theories

### Theory 1: Haiku tier was specified in prose but never implemented in the selector
- **Hypothesis:** the model-tiering in `emit_cycle_prompt` predates (and was never updated for) the mcp-test→haiku intent; it knows only `opus` base + `sonnet` downgrades.
- **Supporting evidence:** `model = "opus"` hardcoded base (4432); no `haiku` literal anywhere in the selector; no commit touched the selector for haiku; live logs show opus.
- **Contradicting evidence:** none found.
- **Status:** **Confirmed.**

## Proven Findings

1. **Root cause:** `emit_cycle_prompt` (`user/scripts/lazy_core.py:4432`) has no per-sub_skill base-model tier. `mcp-test` inherits the `opus` default and only ever downgrades via the generic loop block. The skill's "haiku happy path" is unenforced.
2. **The fix belongs in `emit_cycle_prompt`, not the skill frontmatter** — the batch cycle-model is orchestrator-owned; adding `model: haiku` to `mcp-test/SKILL.md` would not change batch dispatch (it would only affect a hypothetical direct interactive run).
3. **Escalation must be order-correct.** Today the loop block *sets* `model = "sonnet"` unconditionally — that is a downgrade from opus but would be an **upgrade** from haiku. With a haiku base, the resolver must take the **max tier** of {base, loop-required, complexity-required} so a looping mcp-test cycle still escalates haiku→sonnet rather than being pinned at haiku. The opus-on-failure case is already handled separately by the `needs-runtime-redispatch` recovery path (tagged `(opus, recovery)`), which is independent of the base tier.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cycle-model selector | `user/scripts/lazy_core.py` (`emit_cycle_prompt`, ~4419–4482) | Add a per-sub_skill base tier (`mcp-test → haiku`); make downgrade/upgrade tier-max-correct so loop still escalates to sonnet. |
| State surface | `user/scripts/lazy-state.py` (6381–6393) | No change expected — consumes `emitted["model"]` verbatim; new value flows through. |
| Smoke tests | `user/scripts/lazy_core.py` / `lazy-state.py` `--test`, baselines | Add a fixture: `sub_skill=mcp-test` non-looping → `haiku`; looping → `sonnet`. Re-pin baselines. |
| Bug pipeline parity | `bug-state.py` | Shares `emit_cycle_prompt`, so the bug pipeline inherits the same tier automatically — fixture coverage there too. |
| (Optional) skill frontmatter | `repos/algobooth/.claude/skills/mcp-test/SKILL.md` | Optionally add `model: haiku` so a direct interactive `/mcp-test` also honors the intent. Secondary — does not affect the batch path. |

## Open Questions

- **Tier-model representation:** introduce an explicit tier ordering (`haiku < sonnet < opus`) so "take the stronger of base vs. loop-required" is unambiguous, vs. a narrower special-case. (Recommend an ordered map — generalizes cleanly if other sub_skills later want a cheaper base.) — a `/plan-bug` decision.
- **Is haiku sufficient for the full cycle-subagent envelope?** The dispatched prompt also covers PHASES reconcile + sentinel forwarding + the MCP-coverage audit awareness, not just "run the engine." The Informed Dispatcher rewrite argues yes; worth a sanity check during fix verification (run one real mcp-test cycle on haiku end-to-end before pinning). — verification step, not a blocker.
