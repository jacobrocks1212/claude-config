# Dispatch-Guard Deny Is Generic When the Orchestrator Improvises a Subagent-Model Skill's Internal Worker Split — Investigation Spec

> The `lazy_guard.py` workstation sub-subagent exemption (branch 2b,
> `dispatch-guard-denies-workstation-subsubagent-split`) allows a cycle worker's
> composed sub-subagent prompts ONLY when the active subagent-model cycle's own
> emission is already consumed (the "consumed fence"). When that fence is FALSE —
> the cycle is armed but its `cycle_prompt` has NOT been dispatched — an
> unregistered `Agent` prompt can only be the ORCHESTRATOR improvising the
> dispatched skill's own internal test-agent/impl-agent (or Explore) split at the
> orchestrator level, instead of dispatching the single emitted `cycle_prompt` to
> ONE subagent. The guard correctly DENIES this, but falls through to the GENERIC
> corrective recipe (`_default_deny_reason` / `_CORRECTIVE_RECIPE`), which does not
> NAME the specific, mechanically-detectable mistake — so the deny is not
> self-announcing.

**Status:** Fixed
**Severity:** P3 (latent/non-blocking — the run is not hard-blocked; the deny withholds the route and routes the hardening stage, which surfaces + drains it; the feature's real deliverable is not defeated because the emitted `cycle_prompt` is still available for the orchestrator to dispatch verbatim)
**Discovered:** 2026-07-19
**Fixed:** 2026-07-19
**Fix commit:** 66151de6 (Step-2.5 spec: 7eb5cbb7)
**Placement:** docs/bugs/dispatch-guard-improvisation-deny-not-self-announcing
**Related:** `docs/specs/turn-routing-enforcement/` (harden stage — this spec is the Step-2.5 audit trail for harden Round 112); `docs/bugs/_archive/dispatch-guard-denies-workstation-subsubagent-split/` (Rounds 9/10 — the ORIGIN of the 2b exemption + its consumed fence; this spec is the natural successor covering the exemption's DENY fall-through, not its absence); `user/scripts/lazy_guard.py` (branch 2b + `_default_deny_reason`); `user/scripts/lazy_core/dispatch.py` (`emission_consumed_by_nonce` — the consumed fence whose FALSE branch this spec self-announces)

<!-- Status lifecycle:
  - Investigating → active investigation in progress; bug-state.py routes to /spec-bug.
  - Concluded     → root cause identified, investigation done; bug-state.py routes to /plan-bug.
-->

---

## Verified Symptoms

Reconstructed from the live AlgoBooth `/lazy-batch` run (session `7e788158…`, feature
`hydra-overlay`, state dir `~/.claude/state/37850b6e…`).

1. **[VERIFIED]** Two `Agent` dispatches with `prompt_head` `"You are a TEST-WRITING
   agent for AlgoBooth …. Write FAILING tests only — NO implementation/source edits.
   …"` (`denied_sha12: bc608cd07fb0` and `cd064b69ad2b`) were DENIED by
   `lazy-dispatch-guard.sh` → `lazy_guard.py` with the generic corrective recipe
   (`reason_head` = `_CORRECTIVE_RECIPE`). Neither was recorded as
   `worker_subdispatch: true` — the 2b exemption did NOT fire for them.

2. **[VERIFIED]** These are execute-plan's OWN internal test-agent/impl-agent worker
   prompts (the exact split the 2b exemption exists to admit for an in-flight
   worker). Three sibling worker dispatches earlier the same run (`612c6e06…`,
   `a34a77ae…`, `bd998d43…`, `sub_skill: execute-plan`) WERE allowed as
   `worker_subdispatch: true` — so the exemption itself works; the two denied ones
   differ in cycle state, not in kind.

3. **[VERIFIED — the differentiator is the consumed fence]** Telemetry + registry
   reconstruction around the denials:
   - `cycle-end` (item `hydra-overlay`, cleared) at ts `1784488894.9`.
   - `--emit-prompt` registered a fresh execute-plan cycle emission `nonce
     29ef8b47cfaa4b48a3d5671274ef7f31` at `emitted_at 1784488920.2` with
     **`consumed: false`** (registry `lazy-prompt-registry.json`).
   - `cycle-begin` (`kind: real`, `sub_skill: execute-plan`) at `1784488944.3`.
   - The two TEST-WRITING denials at `1784489587.8` / `1784489608.1` — i.e. the
     execute-plan cycle was armed (marker active, `subagent_model: true`) but its own
     emission `29ef8b47…` was **never consumed** (no worker was ever dispatched for
     that cycle).
   So `emission_consumed_by_nonce("29ef8b47…") == False` at deny time → 2b's condition
   4 correctly held the line → the two prompts fell through to the generic
   `_deny_default(marker, _default_deny_reason(), …)`.

4. **[VERIFIED — the deny is CORRECT; the gap is opacity]** Per
   `emission_consumed_by_nonce`'s own docstring: requiring the cycle's own emission to
   be consumed "closes the window where the orchestrator itself could improvise an
   unregistered dispatch under its freshly-armed cycle marker." That is EXACTLY what
   happened: the orchestrator, at Step 7a, held a valid emitted execute-plan
   `cycle_prompt` (`29ef8b47…`) but instead hand-composed execute-plan's internal
   test-writer prompts at the orchestrator level. Session tool calls are serial and no
   worker can exist before the emission is consumed, so the deny is provably right.
   The two denies accrued hardening debt → the next probe withheld the forward route
   (`route_overridden_by: pending-hardening-debt`, `pending_hardening=2`) and dispatched
   the hardening stage (this Round 112).

## Root Cause

**Class: missing-contract.**

The 2b exemption (added by `dispatch-guard-denies-workstation-subsubagent-split`,
Rounds 9/10) has a precise, mechanically-detectable FALSE branch: **workstation +
bound marker + active `subagent_model: true` cycle + own emission NOT consumed +
unregistered `Agent` prompt.** That conjunction has exactly one meaning — the
orchestrator is composing the dispatched skill's INTERNAL sub-subagent worker prompt
itself, instead of dispatching the single emitted `cycle_prompt` to one subagent (the
orchestrator "dispatches exactly one Agent per cycle" per `lazy-batch/SKILL.md`; the
`/execute-plan` SUBAGENT performs the test-agent/impl-agent split internally).

The harness has NO self-announcing contract for this recognizable situation: the guard
DENIES correctly but routes through the GENERIC `_default_deny_reason()` /
`_CORRECTIVE_RECIPE`, which says only "dispatch prompt not script-emitted this turn —
re-run the Step 1a probe and dispatch its cycle_prompt verbatim." It never names the
specific mistake ("you improvised the subagent's internal worker split; dispatch the
SINGLE cycle_prompt to ONE subagent — the subagent does its own split"). This is the
`missing-contract` successor to Rounds 9/10, which classified the ABSENCE of the
exemption the same way; here the exemption exists and its DENY fall-through is silent
about the improvisation it just caught.

Prose contributor (secondary, not the fix site): `lazy-batch/SKILL.md` line 42 states
the guardrail ("it still dispatches exactly one Agent per cycle") but buries it
mid-paragraph adjacent to the enticing `e.g. /execute-plan → Sonnet test-agent +
impl-agent split` example — which the orchestrator LLM mis-attributed to itself. The
durable backstop is the mechanical self-announcing deny (fires exactly when the mistake
happens, regardless of prose), so the fix lands in the guard, not the prose.

## Fix Scope

`user/scripts/lazy_guard.py`, branch 2b: when the active subagent-model cycle exists
but `emission_consumed_by_nonce(cycle.nonce)` is FALSE (the improvisation-caught
signature), emit a self-announcing targeted deny reason that names the mistake and the
corrective ("dispatch the SINGLE emitted cycle_prompt VERBATIM to ONE subagent; the
`<sub_skill>` subagent performs its own test-agent/impl-agent split internally"),
prepended to the standard `_CORRECTIVE_RECIPE`.

- **Deny VERDICT and debt semantics UNCHANGED** (routed through the same
  `_deny_default(marker, …)` as the generic site — a bound marker still accrues
  hardening debt and routes the hardening stage). Only the human-readable REASON
  improves. This is NOT gate-weakening (Prohibition #2): nothing is allowed that was
  previously denied; the gate's teeth are unchanged.
- Regression test in `user/scripts/test_hooks.py`: an unregistered prompt under an
  armed `subagent_model: true` cycle with an UNCONSUMED emission is DENIED with the
  self-announcing reason (naming the improvisation + the single-cycle_prompt
  corrective), and the sibling ALLOW path (consumed fence true) is unaffected.
