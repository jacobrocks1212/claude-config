# Operator recovery of a crashed run's orphaned markers is under-served

**Status:** Concluded
**Class:** product (authority-model / lifecycle-contract fork — operator-owned)
**Date:** 2026-07-17
**Related:** `docs/specs/turn-routing-enforcement/` (containment C3 guards + the SANCTIONED_STOP_TERMINAL gate), `docs/bugs/hardening-blind-to-process-friction/` (the `refuse_run_start_clobber` sibling), `docs/bugs/single-slot-marker-ownership-race-disarms-owning-run/` (the `marker_owner_status` non-destructive ownership detect this investigation reuses).

## Symptom (verified)

A `/lazy-batch` session died on a remote-control disconnect, leaving BOTH run-scoped state
files orphaned in the state dir (`~/.claude/state/<hash>/`):
`lazy-run-marker.json` + `lazy-cycle-active.json`. An operator in a DIFFERENT, LATER session
tried to tear the corpse down and hit a cascade of misleading refusals, in sequence:

1. `--cycle-end` and `--run-end` both REFUSED as *"you are a single cycle subagent"* — even
   though the caller was provably not a subagent (fresh operator session, no dispatch in
   flight) and the owning run's process was provably dead.
2. After `export LAZY_ORCHESTRATOR=1`, `--run-end` REFUSED again on the missing efficacy-flush
   breadcrumb trio.
3. After `--efficacy-skip-authorized`, REFUSED again on a non-sanctioned terminal reason
   (the operator's honest reason, "crashed-run" / "remote-control-disconnect", is not in the
   sanctioned set).
4. Only the full stack succeeded: `LAZY_ORCHESTRATOR=1` + `--cycle-end`, then
   `--run-end --efficacy-skip-authorized --operator-authorized --terminal-reason <one-of-sanctioned>`
   (borrowing a sanctioned reason that does not describe the actual crash).

No single refusal message pointed the operator at this recovery sequence; each refusal named
only its own gate.

## Root cause (proven)

`script-defect` + `missing-contract`. The two containment guards decide subagent-vs-orchestrator
using ONLY marker-presence + two env signals, and consult NEITHER ownership NOR liveness:

- `refuse_if_cycle_active` (`user/scripts/lazy_core/markers.py:2171`) — guards `--run-end`,
  `--run-start`, `--apply-pseudo`, `--enqueue-adhoc`, `--emit-dispatch`. Priority order:
  `LAZY_ORCHESTRATOR` truthy → allow; `LAZY_CYCLE_SUBAGENT` truthy → refuse; else cycle marker
  present → refuse.
- `refuse_cycle_marker_mutation_if_subagent` (`markers.py:2233`) — guards `--cycle-end` /
  `--cycle-begin` on the same three-way decision.

Both branch on `read_cycle_marker()` PRESENCE alone. Neither reads the marker's recorded
`session_id` / `started_at`, and neither probes process liveness. The distinguishing signals
that separate *"an operator cleaning up a corpse"* from *"a live contained subagent"* already
exist:

- The **cycle marker** records `session_id`, `started_at`, and `run_started_at`
  (`write_cycle_marker`, `markers.py:1486-1513`).
- The **run marker** records `session_id` + `started_at` (`write_run_marker`).
- The dead run's `session_id` (61489c4f…) was plainly different from the operator's session,
  and the owning task-watcher parent PIDs were all gone (provably dead).

The harness already HAS non-destructive ownership machinery it does not apply here:
`marker_owner_status(session_id)` (`markers.py:1022`) returns `absent | owned-by-me |
foreign-stamped` for the RUN marker; `read_run_marker` has staleness path A (age > 24h
DELETE-on-read) and path B (session mismatch, non-destructive). But (i) a freshly-crashed run's
markers are < 24h old, so path A does not fire; (ii) `read_cycle_marker` has NO staleness logic
at all — it just parses; and (iii) the containment guards never call `marker_owner_status` or
pass a `session_id`, so a foreign-and-dead owner reads identically to a live subagent.

Downstream, once containment is bypassed, the `--run-end` handler
(`user/scripts/lazy-state.py:12613`) layers three more gates the operator must satisfy
one-by-one — pending-hardening (`--ack-unhardened`), efficacy-flush
(`--efficacy-skip-authorized`), and the terminal-reason gate against
`SANCTIONED_STOP_TERMINAL` (`markers.py:650`). The sanctioned set has NO crash/disconnect
reason, so an honest operator teardown must borrow an unrelated sanctioned reason plus
`--operator-authorized`.

## Affected area / fix scope (operator-owned)

The correct disposition grants NEW operator authority and/or changes gate semantics — squarely
operator-owned per the harden-harness decision-class tiering. Candidate designs (surfaced for a
decision, NOT baked):

- **(a) Session-liveness/ownership teardown path** — when the marker's `session_id` is present,
  differs from the caller, AND the owning session is provably stale/dead (process-liveness probe
  or an age threshold shorter than the 24h path-A window), allow an operator teardown. Reuses
  `marker_owner_status`'s non-destructive `foreign-stamped` detect + a liveness check; must not
  reintroduce the 2026-06-12 silent-disarm-by-delete a non-owner could trigger against a LIVE
  run.
- **(b) A first-class operator recovery op** — `--recover-stale-marker` / `--force-run-end` that
  performs cycle-end + run-end + records a crash/disconnect terminal reason in ONE sanctioned,
  audited step (gated on `--operator-authorized` + a provable-staleness precondition), collapsing
  the four-step cascade.
- **(c) Chain-aware refusal messages** — at minimum, make each refusal in the cascade point the
  operator at the full recovery invocation. Safe UX, but should point at whichever recovery UX
  (a)/(b) the operator picks, so it is NOT baked ahead of the decision.
- **New sanctioned terminal reason** — add `crashed-run` / `remote-control-disconnect` to
  `SANCTIONED_STOP_TERMINAL` so an operator teardown of a dead run is first-class rather than
  requiring `--operator-authorized` + a borrowed reason. This lets such a reason end a run
  WITHOUT `--operator-authorized` — a gate-semantics change the operator owns.

## Disposition

`NEEDS_INPUT` — see `docs/specs/turn-routing-enforcement/NEEDS_INPUT.md` decision #12. The
mechanical hole (an operator CAN eventually tear the corpse down) is not blocking; what is
missing is a *sanctioned, discoverable, single-step* recovery path, and every candidate grants
authority or changes gate semantics. Surfaced rather than baked.
