# Workstation Recursive Sub-Subagent Dispatch — Feature Specification

> Lift the no-recursive-subagent constraint for WORKSTATION cycle subagents: the dispatched skill's own sub-subagent orchestration model (e.g. `/execute-plan`'s Sonnet test-agent + impl-agent split) is authoritative again, restoring the structural TDD guarantee the inline override traded away. Cloud cycles keep the inline override verbatim.

**Status:** In-progress
**Priority:** P1
**Last updated:** 2026-07-09
**Friction-reduction feature:** no

**Depends on:**

- park-provisional-acceptance — soft — Landed the same session; the park-mode cycle-prompt sections compose with the new workstation dispatch section (both are `@section`-selected; no interaction beyond file order).

---

## Executive Summary

The workstation cycle-subagent inline override ("Sub-subagent dispatch policy (INLINE OVERRIDE — LOAD-BEARING)") dates from a 2026-06-14 harness limitation: the `Agent` tool was empirically unavailable inside a dispatched subagent, so every skill's sub-subagent orchestration (test-agent/impl-agent, research fan-outs) had to be collapsed inline. That limitation is gone — harness builds were verified 2026-07-09 (live) to expose `Agent` to general-purpose subagents, and the containment hook's blanket recursive-dispatch deny was removed the same day (`docs/bugs/adhoc-containment-denies-mandated-explore-fanout`). The override survived as deliberate policy, at a known cost the `/lazy-batch` SKILL itself documents: **the structural test-first guarantee (R-EP-2/R-EP-3 agent separation) was traded away** on workstation.

This feature lifts the override for **workstation cycle subagents only**:

1. The `cycle-base-prompt.md` workstation section becomes a **dispatch-permitted policy with load-bearing guardrails** — the dispatched skill's own SKILL.md orchestration contract is authoritative again; the terminal-stop categorical ban is explicitly propagated into every sub-subagent prompt; single-writer/one-integrator discipline and the cycle's turn-end verify/commit gates stay with the cycle subagent.
2. **Cloud keeps the inline override verbatim** — the container has no persistent state, is reclaim-prone, and the zero-sub-subagent cloud cycle is a documented, retro-graded steady state.
3. Retro grading self-heals by marker: `/lazy-batch-retro`'s branch detection keys on the literal prompt marker, so historical runs keep grading under the old contract while new workstation runs return to the full R-EP-1..8 standard branch (structural TDD gradable again).

## Technical Design

- `user/skills/_components/lazy-batch-prompts/cycle-base-prompt.md`: the `inline-override` workstation section is replaced by a `workstation-dispatch` section (marker literal: `WORKSTATION DISPATCH — LOAD-BEARING`); the `cloud-override` section is byte-untouched. Header rule-inventory row R3 updated.
- `user/scripts/test_lazy_core.py::test_emit_cycle_prompt_binding_matrix_real_template`: workstation anchor assertion updated to the new marker (cloud anchor unchanged).
- `user/skills/lazy-batch/SKILL.md`: the "Cycle-subagent execution model" paragraph and the "Known limitation — TDD agent-separation is traded away" note are rewritten for the lift (workstation dispatch restored; the tradeoff note now scopes to cloud + pre-lift history).
- `user/skills/lazy-batch-parallel/SKILL.md`: lane subagents follow the same workstation cycle model (dispatch permitted); leases/containment unaffected.
- `user/skills/lazy-batch-retro/SKILL.md`: branch 2 (workstation inline-override) re-scoped as the HISTORICAL branch (fires only when the old marker is present in the captured prompt); R-O-4's named-clause list and R-O-9's parenthetical updated.
- Meta-dispatch prompts (`dispatch-input-audit`, `dispatch-apply-resolution`, `dispatch-recovery`, `dispatch-hardening`, `dispatch-coherence-recovery`, `dispatch-investigation`, `dispatch-corrective-coverage`, `dispatch-ingest-research`, `dispatch-needs-runtime-redispatch`) are UNTOUCHED — their no-Agent constraints stand (D4).

## Locked Decisions

Resolved 2026-07-09 under the operator's completeness-first standing policy (autonomous session; flagged for operator review in the session summary).

1. **Scope → workstation CYCLE subagents only.** The lift applies to the forward-work cycle dispatch (`/lazy-batch`, `/lazy-bug-batch`, and `/lazy-batch-parallel` lanes — all workstation). Cloud cycles keep the inline override verbatim: container reclaim risk, no persistent state, and a documented cloud steady state that retro grading already encodes.
2. **The dispatched skill's contract is re-authoritative.** Skills that define sub-subagent orchestration (`/execute-plan` test-agent + impl-agent, `/retro` research subagents, Explore fan-outs) are followed as written on workstation — restoring the structural R-EP-2/R-EP-3 test-first separation. Dispatch is a tool, not an obligation: small mechanical batches may still be done inline.
3. **Guardrails carried in the prompt section (load-bearing):** (a) the TERMINAL-STOP categorical ban binds the cycle subagent AND every sub-subagent, and MUST be restated in each sub-subagent's prompt (no `/lazy*` invocations, no run-lifecycle/routing ops, no second-feature commits — the containment hook remains the mechanical backstop); (b) single-writer discipline — never two concurrent sub-subagents editing the same files; the cycle subagent stays the single integrator and owns the turn-end verify/commit gates (a sub-subagent's claim is not evidence); (c) scope containment — sub-subagents work only inside the dispatched item's scope, and wholesale re-dispatch of the entire cycle is banned.
4. **Meta-dispatch subagents keep their no-Agent constraint.** Input-audit, apply-resolution, recovery, hardening, coherence-recovery, investigation, corrective-coverage, ingest-research, needs-runtime-redispatch: bounded, single-purpose dispatches whose contracts are calibrated to run alone. Out of scope by design.
5. **Retro compatibility is marker-based, not date-based.** `/lazy-batch-retro` branch 2 fires iff the captured cycle prompt carries the OLD literal (`INLINE OVERRIDE — LOAD-BEARING`) — historical runs grade unchanged; new workstation prompts carry `WORKSTATION DISPATCH — LOAD-BEARING` and grade under the full workstation-standard branch. No re-grading of past runs, no grading gap.
6. **`/lazy-batch-parallel` lanes inherit the lift.** Lane cycle subagents are ordinary workstation cycle subagents; the fencing/lease/single-writer-trio model is unaffected because sub-subagents cannot take pipeline actions (guardrail 3a + the agent-targeted containment hook).

## KPI Declaration

Classified `no` for the measurability gate — this is a capability/quality restoration (structural TDD separation) enabled by a harness capability that no longer has the original limitation, not a process-overhead-reduction system with its own KPI surface.

## MCP validation

No MCP-reachable surface (claude-config harness prose + one pytest assertion swap). Validation: `pytest test_lazy_core.py` (updated binding-matrix anchors), both state scripts' `--test` harnesses (byte-identical baselines — the template change alters no fixture output), `lazy_parity_audit.py` exit 0, projection + skill lint clean.

## Open Questions

- **vN — sub-subagent transcript retention.** R-EP-2/R-EP-3 grading depends on the cycle subagent's transcript surviving `/tmp` reclaim; a durable dispatch-evidence breadcrumb (e.g. a cycle-ledger `sub_dispatches` count) would make the restored structural guarantee retro-provable even after reclaim. Deferred — R-O-9's git+jsonl backstop already covers the runaway class.
