---
kind: investigation-spec
bug_id: lazy-batch-prose-entices-orchestrator-subagent-split
---

# `/lazy-batch` execution-model prose entices the orchestrator to improvise the cycle skill's internal sub-subagent split — Investigation Spec

> A validate-deny recurrence: during the `hydra-overlay` `/execute-plan` run the orchestrator,
> holding a freshly-armed `subagent_model: true` cycle marker whose OWN emitted `cycle_prompt`
> was NOT yet consumed, hand-composed `/execute-plan`'s INTERNAL work-unit worker prompt
> ("You are an implementation subagent executing ONE work unit (WU-1) of a mechanical cleanup
> plan …") instead of dispatching the single emitted cycle_prompt to ONE subagent. The dispatch
> guard's 2b(improv) branch (consumed-fence FALSE) correctly DENIED it with the **self-announcing**
> reason shipped by hardening Round 112 (`dispatch-guard-improvisation-deny-not-self-announcing`).
> The guard is working — but this is the SECOND such improvisation in the SAME run/feature
> (Round 112 was the test-agent split; this is the WU-1 impl split), proving the reactive
> self-announcing deny does not by itself PREVENT the improvisation. The still-open contributor is
> the one Round 112 explicitly identified and DEFERRED: the `/lazy-batch` "Cycle-subagent execution
> model" prose buries the orchestrator's "dispatches exactly one Agent per cycle" rule inside a
> paragraph whose header and worked examples advertise the sub-subagent split, enticing the
> orchestrator to set that split up itself.

**Status:** Concluded
**Severity:** Low
**Discovered:** 2026-07-19
**Placement:** docs/bugs/lazy-batch-prose-entices-orchestrator-subagent-split
**Related:** `docs/bugs/_archive/dispatch-guard-improvisation-deny-not-self-announcing` (Round 112 — shipped the self-announcing guard deny, but DEFERRED this prose fix, betting the mechanical deny would suffice); `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md` Rounds 9/10 (added the workstation sub-subagent exemption + consumed fence) + Round 112 + this Round 114; `user/scripts/lazy_guard.py` (the 2b(improv) branch — CORRECT, not a fix site); `user/skills/lazy-batch/SKILL.md` line 42 "Cycle-subagent execution model" paragraph (the fix site); `user/skills/lazy-bug-batch/SKILL.md` lines 85–91 (coupled-pair reference)

---

## Reconstructed route (Step 1)

**Divergence point:** `/lazy-batch` Step 7a (probe `step=Step 7a: execute plan`,
`sub_skill=execute-plan`, `feature_id=hydra-overlay`, `pending_hardening=1`). At a
freshly-armed `execute-plan` cycle-begin (marker `subagent_model: true`, its own emitted
`cycle_prompt` **not yet consumed** — no worker in flight, session calls serial), the
orchestrator dispatched an `Agent` whose prompt was `/execute-plan`'s INTERNAL WU-1
implementation worker prompt rather than the single emitted cycle_prompt.

**Evidence (AlgoBooth state dir `37850b6e…/lazy-deny-ledger.jsonl`, entry `denied_sha12:
4c0d7fde8b86`, `ts 1784494818.76`, `run_started_at 2026-07-19T14:59:57Z`, `acked: true`):**

- `prompt_head`: `"You are an implementation subagent executing ONE work unit (WU-1) of a
  mechanical cleanup plan in the AlgoBooth repo … This is a deletion + reference-migration task …"`
- `reason_head`: `"orchestrator-improvised sub-subagent dispatch — an active 'execute-plan'
  cycle (feature 'hydra-overlay') declares a sub-subagent model but its OWN emitted cycle_prompt
  has NOT been dispatched/consumed"` — the verbatim Round-112 self-announcing message
  (`lazy_guard._subagent_model_improvisation_deny_reason`, `lazy_guard.py:306-318`).
- Immediately-prior ledger entries in the SAME run: `bc608cd07fb0` / `cd064b69ad2b`
  (`"You are a TEST-WRITING agent for AlgoBooth …"`) — the Round-112 improvisation. Same
  feature, same run, DIFFERENT worker-prompt kind → a genuine recurrence, not a re-surface.

## Root cause (Step 2) — `ambiguous-prose`

The guard is NOT the fix site: `lazy_guard.py`'s 2b(improv) branch (line 1063-1079) denied
correctly and self-announced (Round 112). The still-open cause is the ORCHESTRATOR-facing prose
that entices the improvisation in the first place. `user/skills/lazy-batch/SKILL.md` line 42
("Cycle-subagent execution model") leads with **"sub-subagent dispatch PERMITTED with
guardrails"** and worked examples (`/execute-plan → Sonnet test-agent + impl-agent`,
`/retro → research subagents A–G`), then states the orchestrator's own constraint — "it still
dispatches exactly one `Agent` per cycle" — only as a mid-paragraph subordinate clause buried
inside a bold sentence about `/lazy-batch-cloud`. An orchestrator reading that paragraph can
conflate the CYCLE SUBAGENT's internal split (which the paragraph is about) with its OWN
dispatch, and set up the split itself. Round 112's own analysis named this exact contributor
("`lazy-batch/SKILL.md` line 42 … buries it beside the enticing `e.g. /execute-plan → …
split` example") and DEFERRED it, betting the mechanical self-announcing deny was a sufficient
durable backstop. The same-run recurrence refutes that bet: the deny is REACTIVE (announces +
routes hardening AFTER the improvisation); the prose is what shapes the orchestrator's plan
BEFORE it dispatches.

This is over-fit signal 2 (root-cause CLASS recurred ≥2 in the hardening log: Rounds 9/10 the
absence of the exemption, Round 112 the deny-not-self-announcing, now the recurrence-despite-
announcing). The durable complement to the reactive guard deny is a PREVENTIVE prose
clarification — and it is STRUCTURAL, not instance-fitted: it states the orchestrator's
"exactly one Agent per cycle → the SUBAGENT does the internal split" rule for ALL
`subagent_model` skills, not for "WU-1 impl" or "test-agent" specifically. So it lands as the
mechanical fix here, with no over-fit spin-off.

## Fix scope

- **`user/skills/lazy-batch/SKILL.md` line 42:** surface the orchestrator-scope rule as a
  crisp, prominent leading clause of the "Cycle-subagent execution model" paragraph — the
  ORCHESTRATOR dispatches EXACTLY ONE `Agent` per cycle (the single emitted `cycle_prompt`),
  and NEVER composes the cycle skill's internal sub-subagent worker prompts (test-agent /
  impl-agent / Explore fan-out) itself; the SUBAGENT performs that split INTERNALLY once
  running. Cross-reference the self-announcing guard deny so the prose and the mechanical
  backstop point at each other.
- **`user/skills/lazy-bug-batch/SKILL.md` lines 85–91 (coupled-pair mirror):** keep the
  by-reference passage consistent — restate the same one-line orchestrator-scope crispness so
  the coupled pair does not drift.
- **`/lazy-batch-cloud`** (repo-scoped, `repos/algobooth/.claude/skills/`): NO change — cloud
  KEEPS the inline-override (zero sub-subagent dispatch; the orchestrator/subagent both run
  inline), so the improvisation hazard is structurally absent there. Noted for lockstep, not
  edited.
- **Guard / scripts:** NO change — the 2b(improv) branch is correct.

## Verified symptom

`git grep` at `lazy-batch/SKILL.md:42` confirms the "exactly one `Agent` per cycle" clause is
buried mid-paragraph beside the enticing examples; the live ledger entry `4c0d7fde8b86` (acked)
confirms the recurrence carried Round 112's self-announcing reason. No test regression is
implicated (prose-only fix); the mechanical backstop (guard deny + `test_hooks.py`
`test_guard_subagent_model_improvisation_deny_self_announces`) already covers the runtime
behavior and stays green.
