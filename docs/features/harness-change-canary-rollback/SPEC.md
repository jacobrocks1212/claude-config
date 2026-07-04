# Harness-Change Canary + Rollback — Feature Specification

> Self-healing for the self-improvement loop: a shipped harness change enters an observation window; if efficacy tracking shows its targeted friction regressing (or new friction appearing on its control surface), the harness flags it with evidence and auto-enqueues a revert-or-redesign item — with revertibility metadata (change → commits, via the provenance ledger) kept from day one so backing out is mechanical, not archaeology.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution batch)

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock; composes with `intervention-efficacy-tracking` (regression verdicts), `code-doc-provenance-linkage` (change → commit mapping), `incident-auto-capture` (fresh-friction signals inside the window))

---

## Problem

A bad harness change currently persists until a human notices its symptoms in a retro — the
worst-case detection latency for exactly the class of change (hooks, gates, state-script
behavior) whose failures are quiet by design (fail-OPEN hooks fail silently; an over-broad deny
just looks like agents behaving). There is no observation window, no regression tripwire, and no
prepared revert path.

## Direction (deliberately not locked)

- **Window:** each control-surface change (same scope trigger as `anti-overfit-design-gate`) gets
  a canary window (N runs or M days) during which its targeted KPI and its surface's fresh
  incident signals are watched more aggressively than steady-state.
- **Tripwire:** regression past a declared band, or a cluster of new `hook-error.json`/deny-churn
  incidents attributable to the change's surface → auto-enqueue a revert-or-redesign bug stub
  with the evidence attached. Flag-and-enqueue, not silent auto-revert — reverting a live gate
  unattended is itself a gate-weakening act; the operator (or an explicit policy) approves.
- **Revertibility metadata:** at ship time record the change's commit set + linked docs so the
  revert item is mechanically actionable; degraded-mode note if a revert is known to be unsafe.
- **Steady-state handoff:** window closes with a verdict into the efficacy ledger; monitoring
  drops back to the normal KPI-registry cadence.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: window sizing; attribution rules
> (which incidents count against which change); whether any change class ever earns true
> auto-revert; interaction with coupled-pair mirroring on revert. Solutions above are
> directional, not locked.
