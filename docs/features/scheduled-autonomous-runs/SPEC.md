# Scheduled Autonomous Runs (Overnight Builder) — Feature Specification

> Wire `/lazy-batch-cloud` to a cron trigger so the queue drains nightly in a cloud session, with the `LAZY_QUEUE.md` doc + halt notifications as the morning report. All the safety machinery (containment, budgets, coherence gates, concurrent-walker refusal) already exists; this is mostly glue.

**Status:** Draft (pre-Gemini)
**Priority:** P2
**Last updated:** 2026-07-04
**Source:** repo-exploration proposal session 2026-07-04

**Depends on:** (not yet assessed — resolve at `/spec` baseline-lock)

---

## Problem

Batch runs start only when the operator starts them; idle overnight hours are unused. The
pipeline is already built for unattended operation (honest halts, budgets, containment), but no
scheduler invokes it.

## Direction (deliberately not locked)

- **Trigger:** Claude Code remote scheduled triggers (fresh-session-per-fire) or an equivalent
  cron entry point per repo, invoking `/lazy-batch-cloud` with a bounded budget.
- **Safety:** rely on existing arbitration (`refuse_run_start_clobber`, per-repo markers) so a
  scheduled run can never clobber a live interactive run — verify, don't rebuild.
- **Report:** the run's per-cycle `LAZY_QUEUE.md` commits are the morning read; halt notifications
  (sibling proposal `operator-halt-notifications`) page anything needing a decision.
- **Scope control:** per-repo opt-in + max-cycles/budget caps as trigger parameters.

> Draft (pre-Gemini). Open questions for `/spec` baseline-lock: trigger mechanism + credentials;
> which repos opt in; failure/no-op reporting policy; interaction with the deferred-non-cloud
> item class. Solutions above are directional, not locked.
