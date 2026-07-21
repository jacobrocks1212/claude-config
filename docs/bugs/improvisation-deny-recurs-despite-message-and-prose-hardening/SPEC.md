# Bug: orchestrator-improvisation deny recurs despite message + prose hardening

**Status:** Concluded
**Discovered:** 2026-07-20 (harden-harness Round, AlgoBooth `inspector-track-dashboard`
`/lazy-batch` run, session `fc32955d`, Step 7a `/execute-plan`, `pending_hardening=2`)
**Root-cause class:** `missing-contract` (recurrence-handling gap; guard/message/prose are correct)
**Origin:** `turn-routing-enforcement` dispatch guard §2b(improv); harden Rounds 112 (`66151de6`)
and 114 (`4ba985f4`).

## Verified symptom

A `validate-deny` hardening dispatch was auto-triggered claiming the dispatch guard MISFIRED
against a legitimate in-cycle worker sub-subagent split: *"its cycle_prompt WAS consumed and it
WAS the in-flight worker … but that predicate misfired: the worker WAS the consumed
cycle_prompt."*

**This narrative is forensically FALSE.** The guard behaved correctly; it denied genuine
orchestrator improvisation. No worker was ever in flight.

## Forensic reconstruction (AlgoBooth per-repo state dir `~/.claude/state/37850b6e…/`)

Timeline (telemetry `lazy-telemetry.jsonl`):

| ts | event |
|----|-------|
| 1784590500.2 | dispatch (Step 7a execute-plan) — **prior** cycle |
| 1784590531.5 | `containment-refusal` (`--cycle-end`, `refuse_cycle_marker_mutation_if_subagent`) — prior worker tried to end its own cycle |
| 1784590538.0 | `cycle-end` (cleared: true) — orchestrator closed prior cycle |
| 1784590551.9 | dispatch → emission `3686050e0880` (class cycle, **unconsumed**) |
| 1784590573.7 | dispatch → emission `e247c8aa845f` (class cycle, **unconsumed**) |
| 1784590600.2 | `cycle-begin` (kind real, execute-plan) — NEW cycle |
| 1784590988.7 | **DENY** test-writing agent `denied_sha12 7873351608d8` |
| 1784591023.9 | **DENY** test-writing agent `denied_sha12 4696b9644d9c` |

Registry (`lazy-prompt-registry.json`, 33 entries) proves **no worker ever ran for the
1784590600 cycle**:

- The ONLY consumed `class==cycle` emission near the window is `dd71bedd0669` (`emitted_at
  1784590500.2`, `consumed True`) — it belongs to the PRIOR cycle that was `--cycle-end`'d at
  1784590538.
- **Zero** consumed cycle emissions have `emitted_at >= 1784590600.2` (the new cycle-begin).
  The new cycle's emissions `3686050e0880` / `e247c8aa845f` (both registered BEFORE cycle-begin)
  stayed **unconsumed** all cycle.

`resolve_cycle_worker_nonce` at cycle-begin bound the marker to the newest unconsumed cycle
emission (`e247c8aa845f`); that emission was never consumed because the orchestrator never
dispatched the single `cycle_prompt` to a worker. Instead it hand-composed `/execute-plan`'s
INTERNAL test-writing agent prompts at the orchestrator level and dispatched THOSE — the exact
improvisation the guard's §2b(improv) branch (`lazy_guard.py:1063-1079`, consumed-fence FALSE)
is designed to catch. Both denies carry the verbatim self-announcing reason shipped by Round
112: *"orchestrator-improvised sub-subagent dispatch — an active 'execute-plan' cycle (feature
'inspector-track-dashboard') declares a sub-subagent model but its OWN emitted cycle_prompt has
NOT been dispatched/consumed yet…"*.

The same run recorded MANY earlier `worker_subdispatch: true` (pre-acked) ALLOWs for
execute-plan — the exemption works here in general; these two denies are the anomalous
improvisation, not an exemption failure.

This is NOT decision-#8's re-emit-after-cycle-begin fence-death variant: that variant leaves a
CONSUMED cycle emission with `emitted_at` AFTER cycle-begin (a worker did run, under a nonce the
marker didn't hold). Here there is no consumed cycle emission after cycle-begin at all.

## Root cause (harness gap)

The guard, its self-announcing deny message (Round 112), and the orchestrator-scope prose
(Round 114, `lazy-batch/SKILL.md:42`, now maximally explicit) are all CORRECT and cannot be
improved without over-fit. The gap is in **recurrence handling**:

1. This is the **≥3rd occurrence** of the orchestrator-improvises-the-cycle-skill's-internal-split
   class (Round 112 = execute-plan test-agent split; Round 114 = execute-plan WU-1 impl split;
   this = execute-plan test-agent split for inspector-track-dashboard). The reactive
   message+prose hardening demonstrably does NOT prevent recurrence.
2. Every recurrence accrues `pending_hardening` debt and burns a full Opus hardening round whose
   only honest conclusion is "guard correct, no fix" — even though the cause is fully known and
   the corrective is 100% deterministic ("dispatch the SINGLE emitted cycle_prompt VERBATIM to
   ONE subagent"). Contrast the transcription-slip deny, which is classified no-hardening-debt
   (`_deny_no_ledger`) precisely because its corrective is deterministic.
3. The resulting hardening dispatch's evidence is orchestrator-composed: the orchestrator wrapped
   the factual script-emitted `reason_head` in a false "the guard misfired" rebuttal, forcing the
   hardening agent to re-derive forensic truth to discover the deny was correct.

## Fix scope (operator-owned — see NEEDS_INPUT)

No mechanical fix ships this round: a 3rd prose iteration is over-fit (Prohibition), and the
durable structural options touch the operator-blessed integrity-guard / hardening-debt-accrual
semantics. The fork — keep surfacing each recurrence as hardening debt (current; noisy but
preserves the signal) vs. reclassify the improvisation-deny as a no-hardening-debt
self-correcting deny (stops the waste but hides the recurrence) vs. structural prevention — is
surfaced to the operator in
`docs/specs/turn-routing-enforcement/NEEDS_INPUT_2026-07-20-improvisation-deny-recurrence-nodebt-vs-surface.md`.

## Cross-reference

- harden-harness hardening-log Round (2026-07): `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`
- Predecessors (both archived-fixed): `docs/bugs/_archive/dispatch-guard-improvisation-deny-not-self-announcing/`
  (Round 112), `docs/bugs/_archive/lazy-batch-prose-entices-orchestrator-subagent-split/` (Round 114)
