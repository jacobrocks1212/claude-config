# Mechanize Prose-Only Orchestrator Contracts — Feature Specification

> Convert the four highest-risk `/lazy-batch` contracts that exist only as SKILL.md prose into
> mechanical enforcement points: (a) the guard pins the script-selected `model` tier onto every
> registered Agent dispatch instead of trusting the orchestrator to copy `cycle_model`; (b) the
> §1d.5 post-cycle input-audit becomes a state-recorded obligation that withholds the next cycle
> until discharged; (c) mid-run AskUserQuestion answers become a script-owned decision record
> that the emitted apply-resolution prompt embeds mechanically; (d) script-side push
> notification extends beyond halts to parks, budget events, and flushes. The transcript-mined
> meta-pattern is unambiguous: prose contracts fail under autonomous load and only mechanical
> gates stick.

**Status:** Draft
**Priority:** P1
**Last updated:** 2026-07-11
**Source:** repo-exploration proposal session 2026-07-11 (completed review inventorying the
`/lazy-batch` contracts with no hook/gate/script enforcement)
**Friction-reduction feature:** yes

> Substantive (non-block) dependencies are **implemented mechanisms this feature extends**, not
> sibling specs:
> - The prompt registry + validate-deny guard (`lazy_core.register_emission` ~12516,
>   `user/scripts/lazy_guard.py`) — (a) extends the registry entry schema and the guard's allow
>   paths.
> - The pending-hardening route-withhold (`lazy-state.py` `--emit-prompt`, ~12570–12597:
>   `route_overridden_by: "pending-hardening-debt"`) — the exact precedent (b) mirrors for the
>   audit obligation.
> - `--emit-dispatch apply-resolution` + `dispatch-apply-resolution.md` — (c) re-plumbs its
>   `chosen_path`/`resolution_summary` bindings from a script-owned record.
> - `lazy_core.notify_halt` (~17624; ntfy channel seam, fail-OPEN) — (d) generalizes it to
>   non-halt event points.

---

## Executive Summary

A completed review inventoried every `/lazy-batch` contract whose only enforcement is SKILL.md
prose. The transcript-mined meta-pattern: **prose contracts fail under autonomous load — the
same user correction recurs 3–4 runs in a row for the same prose contract — and only mechanical
gates stick.** The harness's own history proves both halves: the validate-deny guard ended
hand-composed dispatch drift the day it landed, while the prose contracts around it kept
regressing.

Four highest-risk unenforced contracts, each becoming one mechanical enforcement point:

- **(a) Model-tier pinning.** Per-step model selection is script-owned —
  `lazy_core.emit_cycle_prompt` / `emit_dispatch_prompt` return `{"ok", "prompt", "model"}`
  (`lazy_core.py:7221`, `:7491`; per-sub_skill tiering + loop-block downgrade at ~7140–7195) and
  the probe surfaces it as `cycle_model` — but **nothing verifies the orchestrator copies it
  into the Agent `model:` field**. The guard's by-ref allow path rewrites only `prompt`
  (`lazy_guard.py` `_allow_json_with_updated_input`, ~130–160: "all other fields — ``model``,
  ``subagent_type``, ``description`` — are preserved from the original input"), and
  `register_emission` does not even store the emitted model. Historical incident, memorialized
  in the dispatch-template prose itself: "41% of post-compaction spawns in the 2026-06-10 audit
  dropped the `model:` field" (`user/skills/lazy-batch/SKILL.md:576`). Field evidence: "Is MCP
  test still using an Opus agent? I thought we switched it to haiku" (session 2ef687dd).
- **(b) Post-cycle input-audit trigger.** §1d.5 exists because self-audit silently failed:
  "Across ~75 observed lazy-batch cycles, zero `NEEDS_INPUT.md` sentinels fired from `/spec`'s
  self-audit despite multiple cycles having surfaceable product-behavior calls"
  (`user/skills/lazy-batch/SKILL.md:820`). Yet the audit **dispatch itself** is unenforced prose
  — an orchestrator that skips §1d.5 is corrected only by retro grading, after the decision
  already shipped unaudited.
- **(c) Decision write-back.** Mid-run AskUserQuestion answers evaporate between the answer and
  the apply-resolution dispatch: "The orchestrator sets resolution_kind and chosen_path from
  probe output + user answer before calling emit_dispatch_prompt"
  (`dispatch-apply-resolution.md` header) — a hand-carry across a compaction-prone context.
  Field evidence: "Why was the plan not updated after my decision?" (session e49b226c); "My
  answers didn't go through" (session 8f85b393).
- **(d) Push-notification policy.** §1c.6 names four canonical notification points, all
  orchestrator-owned prose ("`PushNotification` is always called by the **orchestrator** —
  state scripts never call it", `SKILL.md:469`). Script-side notification exists but covers
  halts only (`lazy_core.notify_halt`, wired at `lazy-state.py:12722`); parks,
  budget-extensions/trips, and flushes notify only if the orchestrator remembers.

This feature serves the same **effective** criterion as the guard family: contracts must be
enforced by deterministic machinery, with prose demoted to explanation. Each of (a)–(d) is a
small, separable mechanization of an already-decided contract — no new policy is being designed,
only enforcement.

## Design Decisions

### D1. (a) Guard-side model pinning: rewrite vs deny

- **Classification:** `product-behavior (open — recommendation below)`
- **Question:** When a registered dispatch reaches the guard with a `model:` that differs from
  (or omits) the script-selected tier, does the guard silently rewrite it or deny the dispatch?
- **Options:**
  - **A — pin-by-rewrite (recommended):** `register_emission` gains a `model` field (populated
    from the emitter's return value at every `--emit-prompt` / `--emit-dispatch` registration
    site); every guard ALLOW path that already returns `updatedInput` (by-ref resolution, and a
    new updatedInput on the fresh-consumption + auto-readmit paths) sets `model` from the
    registry entry alongside `prompt`. A mismatch is corrected in place and the
    `permissionDecisionReason` notes the rewrite (`model pinned: opus→haiku per registry`), so
    the transcript shows the correction. Pros: zero new deny/retry loops; the 41%-drop failure
    mode (missing field) is healed, not punished; composes with the existing
    updatedInput plumbing. Cons: an orchestrator that *intended* a different model is silently
    overridden — acceptable, because model selection is script-owned by contract and any
    intentional override is itself a contract violation.
  - **B — deny on mismatch:** stricter, but converts a transcription slip into a
    deny→re-probe→re-dispatch cycle (~1 wasted meta-turn each), and the guard's deny vocabulary
    is reserved for unregistered/stale prompts today.
- **Recommendation:** A. The guard already replaces the entire tool_input dict via
  `updatedInput`; pinning `model` is a one-field add on an existing mechanism, and rewrite
  matches the field's ownership (script-owned, like `queue.json` deps). Entries missing a
  `model` field (older registrations mid-migration) pass through unpinned — fail-open on the
  new field, never on the dispatch.

### D2. (b) Audit-obligation mechanics

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** How does the state machine make the §1d.5 input-audit dispatch unskippable?
- **Options:**
  - **A — run-marker obligation + route withhold (recommended):** the orchestrator-gated
    `--cycle-end` (env-gated pair at `lazy-state.py` ~9858) records
    `audit_obligation: {item_id, cycle_kind}` in the run marker when the ending cycle's
    sub_skill ∈ {`spec`, `plan-feature`}. The next `--emit-prompt` probe (and `--cycle-begin`)
    refuses to emit/register a forward cycle prompt while an undischarged obligation exists —
    exactly the pending-hardening-debt withhold precedent (`route_overridden_by:
    "pending-hardening-debt"`, `lazy-state.py` ~12570): instead of `cycle_prompt`, the probe
    surfaces the ready-to-run `--emit-dispatch input-audit` command. The obligation is
    discharged by the `--emit-dispatch input-audit` registration itself (same marker
    transaction), so the only way forward is through the audit dispatch.
  - **B — PreToolUse hook check:** a hook denying the next cycle Agent dispatch while the
    obligation stands — but the guard would then need marker-schema knowledge, and the withhold
    belongs where the route is computed (the probe), not where it is validated.
- **Recommendation:** A — reuses a proven withhold mechanism verbatim; the SKILL.md §1d.5 text
  demotes to describing what the probe now enforces. Ordering nuance preserved: the audit fires
  before the next probe routes to `needs-input`/`blocked` (the Deliverable-A ordering rule at
  `SKILL.md:822`) because the withhold triggers on the *probe*, before any routing.

### D3. (c) Decision-record surface

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** Where does a mid-run AskUserQuestion answer live so it cannot fail to reach the
  apply-resolution worker?
- **Options:**
  - **A — `--record-decision` → state file, consumed by `--emit-dispatch apply-resolution`
    (recommended):** new subcommand `lazy-state.py --record-decision --sentinel <path>
    --chosen "<option label(s)>" [--summary "<text>"]` (no such subcommand exists today —
    verified) writes an atomic decision record keyed to the sentinel (state-dir file or a
    run-marker `decisions[]` entry). `--emit-dispatch apply-resolution` then *reads*
    `chosen_path`/`resolution_summary` from the record instead of accepting them as
    orchestrator-typed emit arguments; absent a record for the named sentinel, the emit refuses
    with the exact `--record-decision` command to run. The emitted prompt therefore embeds the
    operator's answer mechanically — an answered decision cannot evaporate between the
    AskUserQuestion and the worker, and the record survives compaction because it is on disk.
  - **B — orchestrator embeds the answer in the emit args (status quo, tightened prose):**
    the observed failure mode; rejected by the feature's premise.
- **Recommendation:** A. The record also gives the retro a durable answered-decisions ledger
  (today the answer exists only in the conversation). The apply-resolution *worker* contract is
  untouched — only where its bindings come from changes.

### D4. (d) Script-side notification coverage

- **Classification:** `mechanical-internal (recommendation below)`
- **Question:** Which §1c.6 event points move from orchestrator prose to script-fired
  notification, and how is double-notification avoided?
- **Options:**
  - **A — extend `notify_halt`'s seam to a general `notify_event` (recommended):** the ntfy
    channel seam + fail-OPEN posture (`lazy_core.py` ~17247–17278) generalizes to
    park (fired from the probe's park-walk when `parked[]` gains a new id — the dedup set moves
    script-side into the marker, ending the post-compaction duplicate carve-out), budget-guard
    trip/extension (fired where the guard trips), flush (fired from the flush-protocol's state
    transition), and provisional-accept (fired inside `--provisionalize-sentinel`). Each site
    fires at the state transition it observes, so the notification can no longer be forgotten;
    the orchestrator's §1c.6 calls for these points are retired (halt/run-end notification
    wiring stays as-is — already script-fired on the halt path).
  - **B — orchestrator keeps firing, script verifies after the fact:** detection without
    prevention; the operator still misses the event in real time.
- **Recommendation:** A. All new sites inherit `notify_halt`'s contract: complete no-op without
  the channel config, zero writes on failure, never on a compute path that can block a probe.

### D5. Scope guard — mechanize, don't redesign

- **Classification:** `mechanical-internal (auto-accepted)`
- The four contracts' *policies* are already decided and field-tested; this feature changes
  only their enforcement locus. Any behavioral delta discovered during implementation (e.g. an
  edge where §1d.5 prose and the withhold disagree on ordering) resolves in favor of the
  existing prose semantics, recorded in the SKILL.md text it replaces.

## User Experience

- **Operator:** phone notifications now arrive for parks, budget events, flushes, and
  provisional-accepts even when the orchestrator forgets §1c.6; a mid-run answer produces a
  visible `--record-decision` acknowledgment and provably reaches SPEC/PHASES (the record is
  committed evidence); model-tier drift disappears from retro findings.
- **Orchestrator:** probe output withholds the forward route behind an
  `audit_obligation` (mirroring the familiar pending-hardening withhold, with the ready-to-run
  emit command in the probe JSON); `--emit-dispatch apply-resolution` refuses without a
  recorded decision and names the exact recording command; dispatch composition is otherwise
  unchanged — the guard quietly corrects the `model:` field when it drifts.
- **Failure states:** guard pin is fail-open on missing registry `model` (legacy entries);
  notification failures log and continue (fail-OPEN); an orphaned `audit_obligation` (crashed
  run) is cleaned by the existing marker staleness sweep.

## Technical Design

```
(a) emit_cycle_prompt / emit_dispatch_prompt ──model──▶ register_emission entry {+ model}
        guard ALLOW paths (fresh / by-ref / auto-readmit)
        └─ updatedInput: {prompt: resolved, model: entry.model, …}   ← pin
(b) --cycle-end (spec|plan-feature) ──▶ marker.audit_obligation
        next --emit-prompt: obligation pending → WITHHOLD forward route,
        surface input-audit emit command; --emit-dispatch input-audit → discharge
(c) AskUserQuestion answer ──▶ lazy-state.py --record-decision (atomic state write)
        --emit-dispatch apply-resolution: bindings READ from record (refuse if absent)
(d) probe park-walk / budget guard / flush / --provisionalize-sentinel
        └─ lazy_core.notify_event(kind, …)   (notify_halt seam, fail-OPEN)
```

- All state writes ride `lazy_core._atomic_write`; all four points are covered by the existing
  pytest suites' fixtures (`lazy-state` self-tests + `lazy_guard` tests).
- Parity: `bug-state.py` shares `emit_cycle_prompt` (its `cycle_model` wiring at
  `bug-state.py:7844–7865`) — (a) and (b) land pipeline-symmetric via `lazy_parity_audit.py`.
- SKILL.md edits demote the four prose contracts to descriptions of the mechanism
  (re-project + `lint-skills.py` after, per house rule).

## KPI Declaration

Drafted rows (full schema). Signal honesty: both rows point at the live `deny-ledger`
`process-friction-count` channel — the ledger where guard denies and operator-correction
friction incidents are recorded today (and where `/incident-scan` clusters them). Dedicated
selectors (e.g. `prose-contract-violation-count`, `decision-loss-count`) are registered in
`kpi-scorecard.py` `_SOURCES` at implementation and the rows re-pointed — the
`canary-trip-precision` / `session-log-mining` registration precedent.

```json
{
  "id": "prose-contract-violation-recurrence",
  "system": "lazy-orchestrator-contracts",
  "title": "Recurrence of violations of the four mechanized orchestrator contracts",
  "friction": "Prose-only contracts (model-tier copy, input-audit dispatch, decision write-back, notification policy) fail under autonomous load — the same user correction repeated 3-4 runs in a row for the same prose contract.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "incidents/30d",
  "direction": "down-is-good",
  "baseline": { "value": 4, "captured_at": "2026-07-11", "window": "30d", "provenance": "retro-derived" },
  "band": null,
  "review_by": "2026-10-15",
  "notes": "Baseline = the four contract classes each with at least one observed violation in the 2026-07-11 review window (model drop incl. the memorialized 41% post-compaction audit; skipped/late 1d.5 audits; decision loss; missed notifications). Retro-graded via /lazy-batch-retro until the dedicated selector lands."
}
```

```json
{
  "id": "decision-loss-incidents",
  "system": "lazy-orchestrator-contracts",
  "title": "Mid-run operator decisions that failed to reach SPEC/PHASES",
  "friction": "AskUserQuestion answers hand-carried into the apply-resolution emit args evaporate across compaction — the operator re-answers or discovers the plan unchanged.",
  "signal": { "source": "deny-ledger", "selector": "process-friction-count" },
  "unit": "incidents/30d",
  "direction": "down-is-good",
  "baseline": { "value": 2, "captured_at": "2026-07-11", "window": "30d", "provenance": "retro-derived" },
  "band": null,
  "review_by": "2026-10-15",
  "notes": "Baseline = the two mined field incidents (sessions e49b226c 'Why was the plan not updated after my decision?', 8f93b393-class 'My answers didn't go through'). Post-fix expectation: structurally zero — the emit refuses without a recorded decision."
}
```

## Implementation Phases

- **Phase 1 — (a) model pinning (~1 session).** `register_emission` `+model` field (all emit
  registration sites); guard pin-by-rewrite on every ALLOW path (updatedInput added to
  fresh-consumption + auto-readmit); reason-string notes the rewrite; fail-open on entries
  without `model`. Proven done: guard tests — mismatched/missing `model` corrected; legacy
  entry passes through; deny paths untouched.
- **Phase 2 — (b) audit obligation (~1 session).** `--cycle-end` records the obligation
  (spec/plan-feature cycles, both pipelines); probe withhold + surfaced emit command;
  discharge on `--emit-dispatch input-audit`; marker staleness cleanup covers it. Proven done:
  state-script self-tests — obligated probe withholds; discharged probe routes forward.
- **Phase 3 — (c) `--record-decision` (~1 session).** Subcommand + atomic record;
  `--emit-dispatch apply-resolution` binding re-plumb + refusal path; SKILL.md Step 1g/1h
  updated to the record-then-emit sequence. Proven done: emit without record refuses naming the
  command; recorded answer appears verbatim in the emitted prompt.
- **Phase 4 — (d) notification coverage (~1 session).** `notify_event` generalization + the
  four new fire sites + script-side park dedup; §1c.6 prose retired for covered points. Proven
  done: fixture state transitions fire exactly-once notifications; no-channel config is a
  complete no-op.

## Validation Criteria

| Behavior | Trigger | Expected Evidence | Where to Check |
|----------|---------|-------------------|----------------|
| Model pinned on drift | Registered dispatch with wrong/missing `model:` | updatedInput carries registry model; reason notes rewrite | lazy_guard tests |
| Legacy entry fail-open | Registry entry without `model` | ALLOW, no pin, no error | lazy_guard tests |
| Audit unskippable | `--cycle-end` after a spec cycle, then `--emit-prompt` | forward route withheld; input-audit emit command surfaced | lazy-state self-tests |
| Obligation discharge | `--emit-dispatch input-audit` | next probe routes forward | lazy-state self-tests |
| Decision cannot evaporate | `--emit-dispatch apply-resolution` with no record | refusal naming `--record-decision` | lazy-state self-tests |
| Answer reaches worker | record then emit | chosen option embedded verbatim in emitted prompt | lazy-state self-tests |
| Park/budget/flush notify | fixture transitions | exactly-once `notify_event` per event | lazy_core tests |
| Fail-OPEN notification | channel unconfigured/unreachable | zero writes, probe unaffected | lazy_core tests |
| Pipeline parity | bug-state equivalents | parity audit green | `lazy_parity_audit.py` |

## Open Questions

- D1 rewrite-vs-deny is the one operator-facing call (recommended: rewrite) — surface at `/spec`
  finalization.
- Whether the (c) decision record lives in the run marker vs a sibling state file (survives
  `--run-end` for retro evidence) — implementation detail, biased toward a sibling file so the
  answered-decisions ledger outlives the run.

## Research References

- `user/skills/lazy-batch/SKILL.md:576` (41% post-compaction model-drop), `:820` (~75-cycle
  zero-NEEDS_INPUT quote), `:467–502` (§1c.6 policy), `:818–867` (§1d.5).
- `user/scripts/lazy_core.py` — emit model tiering ~7140–7195 (`:7221`, `:7491` return shape);
  `register_emission` ~12516 (no `model` field today); `notify_halt` ~17624 (seam design notes
  ~17247–17278).
- `user/scripts/lazy_guard.py` ~130–160 (`_allow_json_with_updated_input` — prompt-only
  rewrite); `user/scripts/lazy-state.py` ~12570–12597 (pending-hardening withhold precedent),
  `:12722` (halt-path notify wiring), ~9858 (env-gated `--cycle-begin`/`--cycle-end`).
- `user/skills/_components/lazy-batch-prompts/dispatch-apply-resolution.md` (orchestrator
  hand-carry of `chosen_path`).
- Field sessions: 2ef687dd (model drift), e49b226c + 8f85b393 (decision loss).
