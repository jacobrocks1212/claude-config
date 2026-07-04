# Friction KPI Registry + Scorecards — Feature Specification

> Every friction-reduction system (build-queue, containment hooks, halt notifications, and anything designed later) declares its canonical KPIs — what friction it exists to reduce, the signal sources, direction-of-goodness, and baseline — in a machine-readable registry. Scorecards render per-system health and regression over time, and `/spec` gains a gate: a new friction-reduction feature cannot lock its baseline without declaring how its success will be measured.

**Status:** Draft (pre-Gemini)
**Priority:** P1
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04 (operator-requested; self-evolution batch)

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock; `harness-telemetry-ledger` is the obvious raw-event substrate)

---

## Problem

Friction-reduction systems ship with narrative success criteria and are never measured again. The
build-queue has no wait-time/false-green trend; containment has no runaway-incident rate; nothing
answers "is this system still earning its complexity?" — so systems can silently stop working (or
never have worked) while the harness keeps paying their cost. Worse, new systems get designed
without any obligation to be measurable at all.

## Direction (deliberately not locked)

- **Registry:** per-system KPI declarations (machine-readable; e.g. `docs/kpi/<system>.json` or a
  single registry file): friction signal, event source(s) in the telemetry ledger, direction of
  goodness, baseline value + capture date, review cadence.
- **Scorecards:** a pure-read renderer (pipeline_visualizer page and/or committed markdown à la
  `LAZY_QUEUE.md`) showing per-system KPI trends and flagging regressions past a declared band.
- **Measurability as a gate:** a `/spec`-time injection (sibling of `phases-runtime-validation.md`)
  requiring any SPEC whose purpose is friction reduction to declare its KPI rows before
  baseline-lock — un-measurable friction claims become a planning-time halt, not a retro finding.
- **First registrants:** build-queue (wait time, false-green rate, raw-invocation deny recurrence),
  containment (runaway trips), halt handling (halt dwell time), retroactively baselined where
  history allows.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: registry schema + residency;
> which KPIs are computable from existing logs vs. need new ledger events; regression-band
> semantics; how the `/spec` gate distinguishes friction-reduction features from ordinary ones.
> Solutions above are directional, not locked.
