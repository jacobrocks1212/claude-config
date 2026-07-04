# Anti-Overfit + Tautology Design Gate for Harness Changes — Feature Specification

> A self-improving harness has a failure mode ordinary code doesn't: it can overfit to single incidents, weaken its own gates, and grade itself with metrics it controls. Generalize the existing `/harden-harness` anti-overfit reflex into a mechanical + adversarial review gate on harness self-modifications — overfit-smell detection, tautological-metric detection, gate-weakening detection, and a complexity budget — with every verdict recorded so the gate's own judgment is auditable.

**Status:** Draft (pre-Gemini)
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution batch)

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock; composes with `intervention-efficacy-tracking` (its verdicts are the gate's ground truth) and the shipped `harness-hardening-retro-fixes` anti-overfit reflex (prose-level ancestor))

---

## Problem

The hardening loop already shows the smells this gate targets: rules keyed to one incident's
literal strings, proposals the operator had to decline as gate-weakening (e.g. the logged
"decline GAP-2 gate-weakening"), and success claims measured by the absence of a signal the
change itself suppresses (a deny-hook "working" because denies stopped — which is also what
breaking the hook looks like). Today the only defense is prose guidance plus operator vigilance;
nothing mechanical stands between a plausible-but-wrong harness change and `main`.

## Direction (deliberately not locked)

- **Scope trigger:** changes touching the harness's control surfaces — hooks, state scripts,
  gates, containment, skill contracts — get the gate; ordinary feature work does not.
- **Overfit check:** does the new rule/gate key on incident-specific literals (slug names, one
  session's paths) rather than a structural property? Adversarial reviewer prompt: "construct the
  nearest recurrence this rule does NOT catch."
- **Tautology check:** is the change's success metric produced or suppressible by the change
  itself? Require an independent observable (ties into `intervention-efficacy-tracking`'s
  signal-independence field) — a gate must be falsifiable by data it doesn't control.
- **Gate-weakening check:** diff-level detection of loosened thresholds, removed refusals,
  broadened exemptions in existing gates; such changes demand explicit operator sign-off rather
  than riding an ordinary cycle.
- **Complexity budget:** each new control surface states what it retires or why net-new
  complexity is justified; the harness should not monotonically accrete rules.
- **Audit trail:** verdicts recorded per change (the gate can itself be evaluated for overfit
  later — it is not exempt from the system it enforces).

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: mechanical vs. LLM-adversarial
> split per check; where the gate runs (harden pipeline step, pre-commit, cycle review); override
> protocol; how to avoid the gate itself becoming friction (its KPI row in the registry).
> Solutions above are directional, not locked.
