# Autonomous mcp-test cycle dispatches legacy `.md` scenarios to haiku, which BLOCKs — Investigation Spec

> The autonomous `/lazy-batch` (and `-cloud` / `-bug-batch`) orchestrator fixes the mcp-test cycle model to **haiku** at dispatch time — before the subagent resolves which scenario it will run — so a scenario that exists only as a legacy `.md` (no converted `corpus/live/*.yaml` counterpart) lands on haiku, which cannot author the `.md`→v1-YAML conversion and writes `BLOCKED.md`. The `route_mcp_test_tier()` signal that *would* escalate such a scenario to Sonnet exists but is consulted only by the interactive `mcp-test` skill prose, never by the state script's cycle-model emit.

**Status:** Concluded
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/mcp-test-legacy-md-routes-to-haiku
**Related:** `user/scripts/CLAUDE.md` → "mcp-test model-tier routing (harness-hardening-retro-fixes Phase 4)"; `repos/algobooth/.claude/skills/mcp-test/SKILL.md` (Model-tier section, lines 32–55); `user/scripts/surface_resolver.py::route_mcp_test_tier`; sibling bug `docs/bugs/probe-full-read-before-dispatch/`. Complementary AlgoBooth-side content fix (bulk-migrate legacy `.md`→YAML) is OUT OF SCOPE here — it lives in the AlgoBooth repo.

---

## Verified Symptoms

1. **[VERIFIED]** During an autonomous AlgoBooth run, a haiku mcp-test cycle wrote `BLOCKED.md` because "the MCP scenario exists only as legacy `.md`, needs conversion to v1 YAML for the deterministic engine (an authoring task beyond haiku's happy-path)." — confirmed by operator screenshot (2026-06-19).
2. **[VERIFIED]** The first screenshot of the same run shows the orchestrator dispatching the cycle as `disp mcp-test → d7-mpe-input (haiku)` — i.e. haiku was selected for the mcp-test cycle without regard to the scenario's conversion state. — confirmed by operator screenshot.
3. **[VERIFIED]** The operator's preferred *content* remedy is to bulk-migrate the legacy `.md` scenarios to v1 YAML; the *harness* remedy in scope here is to stop routing un-convertible scenarios to haiku. — confirmed via AskUserQuestion (scope: "Bug 1 + Bug 2 routing").

## Reproduction Steps

1. A feature/bug reaches the Step-9 MCP gate; `lazy-state.py`/`bug-state.py` emits `sub_skill: mcp-test`.
2. `lazy_core.emit_cycle_prompt` sets `cycle_model = "haiku"` for the mcp-test cycle (the only escalation is the loop-block → sonnet downgrade at `repeat_count >= 2`).
3. The orchestrator dispatches the cycle subagent with model haiku.
4. Inside the cycle, the mcp-test skill (Step 1) resolves the scenario and finds only a legacy `.md` with no `corpus/live/*.yaml` counterpart — a first-run conversion is needed.

**Expected:** an unconverted-`.md` scenario routes to **Sonnet** (per `mcp-test/SKILL.md:46` and `route_mcp_test_tier`'s Sonnet-forcing condition #1), so the conversion-authoring happy path is on a capable tier.
**Actual:** the model was already fixed to haiku at dispatch; haiku cannot author the conversion and writes `BLOCKED.md`, stalling the item until a human or hardening cycle intervenes.
**Consistency:** Always, for any feature/bug whose mcp-test scenario is an unconverted legacy `.md` on a first autonomous run.

## Evidence Collected

### Source Code

- **Hardcoded tier (root cause)** — `user/scripts/lazy_core.py:4761`:
  `model = "haiku" if norm_sub_skill == "mcp-test" else "opus"`. The mcp-test cycle model is a constant, chosen with no reference to the scenario or its conversion state. The loop-block downgrade below it sets `sonnet` only on `repeat_count >= 2` (a stall escalation), not on first-run conversion need.
- **The routing signal exists but is unwired into emit** — `user/scripts/surface_resolver.py:379` `route_mcp_test_tier(scenario_path, prior_verdict=None, yaml_exists=None) -> "haiku" | "sonnet"`. Sonnet-forcing condition #1 is exactly "legacy `.md` with no converted `corpus/live/*.yaml` counterpart." Per `user/scripts/CLAUDE.md`, this helper is consulted by **`repos/algobooth/.claude/skills/mcp-test/SKILL.md`'s Model-tier section** (interactive subagent prose) — NOT by `emit_cycle_prompt`.
- **Why the subagent prose can't save the autonomous path** — the dispatch model is bound by the orchestrator BEFORE the subagent runs; a subagent cannot re-tier itself mid-turn. So on the autonomous path the documented tier routing is dead — the model is already haiku by the time Step 1 discovers the legacy `.md`.

### Runtime Evidence

Two operator screenshots from one AlgoBooth `/lazy-batch` run (2026-06-19): (a) `disp mcp-test → d7-mpe-input (haiku)`; (b) the haiku cycle writing `BLOCKED.md` with the legacy-`.md`/needs-YAML-conversion reason.

### Related Documentation

`harness-hardening-retro-fixes Phase 4` introduced `route_mcp_test_tier` and wired it into the interactive `mcp-test` skill, explicitly to keep haiku on "ready-to-run converted-YAML happy paths" and route conversion/authoring/diagnosis to Sonnet "by default — not by a per-run orchestrator override." The autonomous cycle-model emit was not updated to match, leaving the batch path on the pre-Phase-4 hardcoded haiku.

## Theories

### Theory 1: emit_cycle_prompt bypasses route_mcp_test_tier
- **Hypothesis:** the autonomous cycle-model selection hardcodes haiku and never consults the tier router, so the Phase-4 routing is honored interactively but not in batch.
- **Supporting evidence:** `lazy_core.py:4761` literal; `CLAUDE.md` states the helper is consulted by the SKILL.md prose only.
- **Contradicting evidence:** none found.
- **Status:** Confirmed.

## Proven Findings

- The mcp-test cycle model is fixed at `lazy_core.py:4761` to haiku independent of scenario state; `route_mcp_test_tier` is not in the `emit_cycle_prompt` path. **Confirmed.**
- Fixing the model at dispatch time is structurally upstream of scenario resolution (which happens inside the dispatched subagent), so the fix must give `emit_cycle_prompt` enough signal to escalate BEFORE dispatch.

## Affected Area

| Component | Files | Impact |
|-----------|-------|--------|
| Cycle-model emit | `user/scripts/lazy_core.py` (`emit_cycle_prompt`, ~4748–4761) | Hardcodes haiku for mcp-test; must consult tier signal. |
| Tier router | `user/scripts/surface_resolver.py` (`route_mcp_test_tier`) | Already correct; needs to be called from emit. |
| Tests | `user/scripts/test_lazy_core.py` (`test_emit_cycle_prompt_mcp_test_cycle_model_haiku` and siblings), `user/scripts/test_surface_resolver.py` | New fixture: unconverted-`.md` mcp-test cycle → sonnet. |
| Mirror | `bug-state.py` shares `emit_cycle_prompt`, so the bug pipeline inherits the fix automatically (no separate path). | Parity preserved by construction. |

## Open Questions

- **Scenario resolution at emit time.** `route_mcp_test_tier` needs a `scenario_path` (and `yaml_exists`). At `emit_cycle_prompt` time the orchestrator knows the `feature_id`/`spec_path` but not necessarily the resolved scenario. The fix must either (a) map feature/bug → candidate scenario(s) deterministically in the state script and pass `yaml_exists`, or (b) escalate conservatively to Sonnet whenever ANY candidate scenario for the item lacks a converted YAML counterpart. `/plan-bug` should pick between these; (b) fails safe toward Sonnet and matches `route_mcp_test_tier`'s own "unknown → Sonnet" bias.
- **Cost.** Escalating first-run mcp-test cycles to Sonnet raises per-cycle cost on the conversion path only; the converted-YAML happy path stays haiku. Confirm this matches the Phase-4 cost intent (it does, per the CLAUDE.md wording).
