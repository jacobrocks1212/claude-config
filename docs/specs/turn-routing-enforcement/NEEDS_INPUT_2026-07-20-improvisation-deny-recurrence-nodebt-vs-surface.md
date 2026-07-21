---
kind: needs-input
feature_id: turn-routing-enforcement
written_by: harden-harness
class: harness
divergence: structural
next_skill: harden-harness
decisions:
  - "Orchestrator-improvisation deny recurrence handling: the §2b(improv) deny (armed subagent_model cycle + own emission NOT consumed + unregistered Agent prompt) is CORRECT, self-announcing (Round 112), and prose-warned (Round 114), yet the class has now recurred ≥3× — each recurrence accrues pending_hardening debt and burns a full Opus hardening round that concludes 'guard correct, no fix', despite a 100%-deterministic corrective. Keep surfacing each recurrence as hardening debt (current; preserves the misbehavior signal), reclassify it as a no-hardening-debt self-correcting deny like the transcription-slip _deny_no_ledger (stops the waste but hides recurrence), or invest in structural prevention? Touches the operator-blessed integrity-guard / hardening-debt-accrual semantics; gate-integrity stakes (a wrong reclassification hides genuine improvisation regressions). (harden Round, 2026-07-20)"
date: 2026-07-20
---

## Decision Context

An auto-triggered `validate-deny` hardening dispatch (item in flight
`inspector-track-dashboard`, AlgoBooth `/lazy-batch`, session `fc32955d`, Step 7a
`/execute-plan`, `pending_hardening=2`) claimed the dispatch guard MISFIRED against a legitimate
in-cycle worker sub-subagent split. **Forensics disprove the misfire** (full reconstruction:
`docs/bugs/improvisation-deny-recurs-despite-message-and-prose-hardening/SPEC.md`, Concluded):

- Registry (`~/.claude/state/37850b6e…/lazy-prompt-registry.json`) shows **zero** consumed
  `class==cycle` emissions with `emitted_at >= cycle-begin (1784590600.2)`. The new cycle's
  emissions `3686050e0880` / `e247c8aa845f` stayed unconsumed; the only consumed one
  (`dd71bedd0669`) belonged to the PRIOR cycle, `--cycle-end`'d at 1784590538.
- So NO worker was ever in flight. The orchestrator hand-composed `/execute-plan`'s internal
  TEST-WRITING agent prompts (`denied_sha12 7873351608d8` + `4696b9644d9c`) at the orchestrator
  level instead of dispatching the single `cycle_prompt`. The guard's §2b(improv) branch
  (`lazy_guard.py:1063-1079`, consumed-fence FALSE via `emission_consumed_by_nonce`) correctly
  denied both, with the verbatim Round-112 self-announcing reason.

**Why this is a fork and not a mechanical fix.** The three reactive levers are exhausted:

| Lever | Status |
|-------|--------|
| Guard detection + block (`lazy_guard.py` §2b, decision #4 consumed fence) | correct — denies the improvisation |
| Self-announcing deny message (Round 112, `66151de6`) | correct — names the exact mistake + corrective, verbatim in the deny |
| Orchestrator-scope prose (Round 114, `4ba985f4`, `lazy-batch/SKILL.md:42`) | maximal — leads with "EXACTLY ONE Agent per cycle", flags the enticing examples as "NOT a cue", cites the guard + rounds |

A 3rd prose iteration is over-fit (harden-harness over-fit signal 2: class recurred ≥3× at the
same guard region). The recurrence itself is the new signal: reactive message+prose hardening
does not prevent the orchestrator re-attempting the improvisation. Every recurrence is
CORRECTLY blocked but still: (a) accrues `pending_hardening` debt, (b) withholds the forward
route (`route_overridden_by: pending-hardening-debt`), and (c) burns a full Opus hardening round
that can only conclude "guard correct, no fix" — despite the corrective being 100% deterministic
("dispatch the SINGLE emitted `cycle_prompt` VERBATIM to ONE subagent").

The transcription-slip deny establishes the precedent for a deterministic-corrective deny that
owes NO hardening debt (`_deny_no_ledger`): the deny still fires, but it is not booked as a
harness gap because re-probe-and-dispatch-verbatim always fixes it. The improvisation-deny's
corrective is equally deterministic — so whether it should ALSO be no-debt is a genuine,
un-captured, operator-ownable gate-semantics fork. It is NOT baked silently because it changes
hardening-debt accrual on the integrity guard (a wrong call hides genuine improvisation
regressions).

## Options

- **A. Keep surfacing each recurrence as hardening debt (current behavior — status quo).**
  Every improvisation-deny keeps accruing `pending_hardening` and routing a hardening round.
  Pro: the recurrence stays visible; a genuine regression in the guard/prose would still surface;
  zero change to the operator-blessed guard. Con: each recurrence burns an Opus round on a
  known-cause, deterministic-corrective deny; the run's forward route is withheld each time; the
  orchestrator can (as here) inject a false "guard misfired" narrative into the resulting
  dispatch, making the round expensive.

- **B. Reclassify the improvisation-deny as a no-hardening-debt self-correcting deny
  (Recommended, but operator-owned).** Route the §2b(improv) deny through the transcription-slip
  precedent: the deny still fires and still blocks the improvised dispatch, but it is pre-acked
  (no `pending_hardening` debt, no hardening dispatch) because its corrective is deterministic —
  the orchestrator re-reads the self-announcing reason and dispatches the single `cycle_prompt`.
  Pro: stops the recurring waste; the deny message already carries the exact corrective; mirrors
  an established sanctioned no-debt class. Con: the recurrence becomes INVISIBLE to the hardening
  pipeline — if the orchestrator's improvisation frequency spikes (a genuine prose/model
  regression), no hardening round surfaces it; needs a lightweight counter/telemetry so the
  no-debt reclassification does not blind the operator (e.g. a periodic digest of
  improvisation-deny counts). This changes hardening-debt accrual on the integrity guard →
  operator sign-off required; NOT gate-weakening (the deny is unchanged; only its debt
  classification changes), but it IS a gate-semantics change the hardening prohibitions reserve
  for the operator.

- **C. Structural prevention at the orchestrator seam.** Make the improvisation
  harder-to-attempt rather than merely denied — e.g. a Step-1d checklist gate the orchestrator
  must pass (confirm the single `cycle_prompt` was dispatched-and-consumed before any
  sub-subagent prompt is composable), or a mechanical pre-dispatch assertion. Pro: attacks the
  root (orchestrator behavior), not the symptom. Con: heavier; the orchestrator seam is prose +
  model-driven, so "structural prevention" of a model-composed dispatch largely reduces back to
  prose/guard (already maximal) — likely the lowest ROI of the three.

## Recommendation

**Option B** — reclassify the improvisation-deny as a no-hardening-debt self-correcting deny
(transcription-slip precedent), PAIRED with a lightweight improvisation-deny counter/digest so
the reclassification does not blind the operator to a frequency spike. This stops three-rounds-
and-counting of waste on a deterministic-corrective deny while preserving a coarse visibility
signal. It is surfaced (not baked) because it changes hardening-debt accrual on the
operator-blessed integrity guard. Option A is the safe do-nothing (the friction is non-blocking;
the run continues on current behavior). Option C is available if the operator wants root-cause
prevention over symptom-cost reduction.

## Handback

`--ack-deny` for the two offending ledger entries (`7873351608d8`, `4696b9644d9c`,
cause-key = orchestrator-improvisation) is ORCHESTRATOR-ONLY (refused for this meta-cycle
subagent). Recommended resolution note for the ack: *"known-cause recurrence of the
orchestrator-improvises-execute-plan-split class (guard correct; Rounds 112/114 already shipped
message + prose; forensics confirm no worker in flight — genuine improvisation, correctly
denied). No harness fix; structural fork surfaced to operator."* Handed to the orchestrator via
the round's Return `reconcile:` field.
