---
kind: fixed
feature_id: dispatch-guard-improvisation-deny-not-self-announcing
date: 2026-07-19
provenance: backfilled-unverified
validated_via: test_hooks.py 285/285 (new test_guard_subagent_model_improvisation_deny_self_announces green — asserts the self-announcing reason + unchanged deny verdict + unchanged hardening-debt accrual); pytest user/scripts/tests/test_lazy_core/ 1328 passed; lint-skills.py --check-projected --check-capabilities OK; lazy-state.py/bug-state.py --test OK; bug-state.py --fsck clean; harness-gate.py gate_weakening_hit=false. NOT pipeline-gated (fixed OUT-OF-PIPELINE via a harden commit).
auto_ticked_rows: 0
---

# Completion Receipt

`dispatch-guard-improvisation-deny-not-self-announcing` fixed OUT-OF-PIPELINE by
`/harden-harness` Round 112 (2026-07-19). Fix commit: `66151de6`
(`harden(hook): self-announce the guard deny when the orchestrator improvises a
subagent-model split`). Step-2.5 bug spec committed first: `7eb5cbb7`. This receipt
was written by the dispatched harden subagent, not the bug pipeline's `__mark_fixed__`
gate — provenance is `backfilled-unverified`.

## Notes

`lazy_guard.py` branch 2b (the workstation sub-subagent exemption) correctly DENIES an
orchestrator that composes `/execute-plan`'s internal test-agent/impl-agent worker
prompts itself under an armed but UNCONSUMED cycle (consumed-fence FALSE — session
calls are serial, so no worker can be in flight), but fell through to the GENERIC
`_default_deny_reason()` / `_CORRECTIVE_RECIPE`, which never named the specific mistake.
Added `_subagent_model_improvisation_deny_reason(cycle)` and a new branch: when an
active `subagent_model: true` cycle's own emission is NOT consumed, the deny now
self-announces ("orchestrator-improvised sub-subagent dispatch … the orchestrator
dispatches EXACTLY ONE Agent per cycle: dispatch the SINGLE emitted cycle_prompt … the
`<sub_skill>` SUBAGENT performs its own split INTERNALLY"). The deny VERDICT and the
hardening-debt accrual are UNCHANGED (routed via the same `_deny_default`) — a message
upgrade, not a gate change (harness-gate `gate_weakening_hit: false`).

## Verification

New regression `test_guard_subagent_model_improvisation_deny_self_announces` arms a
bound workstation marker + an execute-plan (`subagent_model: true`) cycle whose emission
is NOT consumed, dispatches an unregistered worker prompt, and asserts: `deny`; the
reason contains `orchestrator-improvised` + `EXACTLY ONE Agent per cycle` + `cycle_prompt`
+ `execute-plan`; the diagnosis PREPENDS the standard recipe; and `pending_hardening() == 1`
(debt semantics preserved). test_hooks.py 285/285; the pre-existing
`test_guard_worker_subdispatch_denied_before_consume` (deny) and
`test_guard_worker_subdispatch_exemption_allows` (allow) both remain green — the sibling
consumed-fence-true ALLOW path is unaffected.
