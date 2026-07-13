---
kind: blocked
feature_id: hardening-intervention-records-unmeasurable-or-missing
phase: "Phase 4 / WU-6 — intervention-record backfill (r1-r3, r31-r32)"
blocked_at: 2026-07-13T01:38:30Z
retry_count: 0
blocker_kind: orchestrator-only-op
recovery_suggestion: "Orchestrator (LAZY_ORCHESTRATOR=1) runs the 5 --record-intervention commands below, removes the 5 deliberate-divergence markers, then re-dispatches to finish WU-6 verify + WU-7."
---

# BLOCKED — WU-6 intervention backfill requires the orchestrator-only `--record-intervention` CLI

## Details

WU-6's remaining deliverable is to create five backfill intervention records —
`harden-2026-07-r1.md`, `-r2.md`, `-r3.md` (plan scope) plus `-r31.md`, `-r32.md`
(part-1 WU-4 scope-note extension) — via the D9 backfill path
(`lazy-state.py --record-intervention --shipped-commit … --shipped-date …`).

That CLI is **orchestrator-only**: `refuse_if_cycle_active` refuses it (exit 3, zero side
effects) for any cycle subagent lacking `LAZY_ORCHESTRATOR=1`. This `/execute-plan` cycle runs
AS a contained cycle subagent (the live `lazy-cycle-active` marker for this bug is present, session
`6474bd32…`), so the backfill CLI cannot run in-cycle. Confirmed empirically this cycle:

```
REFUSED: `--record-intervention` is an orchestrator-only operation and you are a single cycle
subagent (the lazy-cycle-active marker is present for feature
'hardening-intervention-records-unmeasurable-or-missing'). … refused with zero side effects.
(exit 3)
```

This is the **same C3 containment** that deferred the r3 / r31 / r32 captures at ship time
(see those rounds' `**Intervention record (DEFERRED — cycle-contained)**` notes).

## What was tried

- **Hand-writing the records was deliberately rejected.** It bypasses the sole-writer capture
  path (`lazy_core.record_intervention` / `_render_intervention_record`) — the exact record
  integrity this bug exists to enforce — and, for the MEASURABLE r31/r32, would freeze a fake
  baseline and permanently poison the CLI's idempotent re-capture (`--record-intervention`
  never clobbers an existing record). Undeclared r1/r2/r3 are safer to hand-write but the same
  sole-writer principle applies; establishing a "cycle subagent hand-writes intervention
  records" precedent undermines the fix.
- **Spoofing `LAZY_ORCHESTRATOR=1` was rejected** — it is the forbidden integrity side-door.
- **Sub-subagent dispatch does not help** — a dispatched child is also a subagent without the
  orchestrator env and hits the same refusal.

## What WAS completed in-cycle (committed)

- **WU-5** (committed earlier): intervention-coverage lint wired into the `/lazy-batch` +
  `/lazy-bug-batch` §1c.6 end-of-run flush (coupled pair), fail-open, rooted at the
  claude-config checkout.
- **WU-6 (partial):** r5 (`event:no-route`) and r7 (`event:route-loop`) — both vocabulary-invalid
  phantom events — re-declared onto honest `undeclared` vocabulary (`baseline: not-computable`),
  each with a `## Re-declaration 2026-07-12` audit note. `doc-drift-lint.py --repo-root .` exit 0.
- **Boundary cross-reference** recorded (r14-r21 belong to the archived split-brain sibling).

## Recovery Suggestion

**Orchestrator / operator (with `LAZY_ORCHESTRATOR=1`) runs these five commands from the
claude-config root, then removes the five markers and re-dispatches.**

```bash
# r1-r3 — undeclared (no ledger event fits; explicit escape hatch, retro-visible)
python3 user/scripts/lazy-state.py --record-intervention --id harden-2026-07-r1 --pipeline hardening \
  --target-signal undeclared --shipped-commit 5ff653aa73df616d1787a50602709064ccf7f83d --shipped-date 2026-07-03 --repo-root .
python3 user/scripts/lazy-state.py --record-intervention --id harden-2026-07-r2 --pipeline hardening \
  --target-signal undeclared --shipped-commit fbc4f0edc9a842f0352e8b3c09bfc4f53c04e9d7 --shipped-date 2026-07-03 --repo-root .
python3 user/scripts/lazy-state.py --record-intervention --id harden-2026-07-r3 --pipeline hardening \
  --target-signal undeclared --shipped-commit d650926ce56a55866dcdb16e8cf4c4ca478671c1 --shipped-date 2026-07-04 --repo-root .

# r31 — measurable event:halt (command declared verbatim in Round 31's body)
python3 user/scripts/lazy-state.py --record-intervention --id harden-2026-07-r31 --pipeline hardening \
  --target-signal event:halt --expected-direction decrease \
  --signal-independence "mixed — halt is a broad proxy: the eliminated needs-input re-halt loop is one contributor to halt-event volume; a decrease is consistent with the fix but confounded by unrelated halt sources (blocked/needs-research), so the evaluator may cap at INCONCLUSIVE (confounded)." \
  --shipped-commit fc5f5371f0992184f3d32374393a3296237f899e --shipped-date 2026-07-12 --repo-root .

# r32 — measurable event:halt (command declared verbatim in Round 32's body)
python3 user/scripts/lazy-state.py --record-intervention --id harden-2026-07-r32 --pipeline hardening \
  --target-signal event:halt --expected-direction decrease \
  --signal-independence "mixed — the direct false-loop signal is not ledgered; halt is a broad, heavily-confounded proxy capturing only the tail case where a false LOOP-DETECTED would escalate a multi-cycle spec/plan to a halt. Most halts are unrelated (blocked/needs-input/needs-research), so the evaluator will likely cap at INCONCLUSIVE (confounded)." \
  --shipped-commit 879613d1c02afd20f2235fc832885cd46d7e42d7 --shipped-date 2026-07-12 --repo-root .
```

Then, in `docs/specs/turn-routing-enforcement/hardening-log/2026-07.md`, delete the five
`<!-- doc-drift:deliberate-divergence: intervention record harden-2026-07-r{1,2,3,31,32} … -->`
markers (now redundant — the rounds have real records), and re-dispatch `/execute-plan` on
`plans/all-phases-hardening-intervention-records-part-2.md` to complete WU-6 verify + WU-7
(harden-harness prose + re-projection + full gate sweep). `doc-drift-lint.py` must stay exit 0
after marker removal.

**Harness follow-up (harden-harness candidate):** a data-repair WU whose deliverable is an
orchestrator-only CLI (`--record-intervention`) was assigned to an `/execute-plan` cycle
subagent, which C3 containment structurally refuses. The dispatch prompt's TERMINAL STOP ban does
NOT list `--record-intervention`, yet the guard refuses it — a contract/guard mismatch. Options:
(a) route CLI-backfill WUs to the orchestrator (like the §1c.6 efficacy flush); (b) have
`/plan-bug` mark such WUs orchestrator-owned; (c) narrow `refuse_if_cycle_active` to permit a
planned in-scope `--record-intervention` backfill inside a data-repair cycle. Surface for
`/harden-harness` (off the main context).
