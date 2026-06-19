# A lingering/stale run-marker arms validate-deny against unrelated (non-pipeline) dispatches → hardening debt gates run-end — Investigation Spec (stub)

> During a `/lazy-batch` run, a lingering checkpoint run-marker armed the validate-deny guard against unrelated, non-pipeline Agent dispatches in the same session. The guard denied two ordinary design/spec dispatches, those denials accrued as unacknowledged hardening debt, and that debt then gated `--run-end` — forcing an operator-only `--ack-unhardened` decision at the end of an otherwise clean run. The inverse also occurred: a second session's marker silently DISARMED a live run's guard (fast-path allow), so probe registration stopped and counters were lost. The marker's scope is still wrong in the same-repo / stale / cross-session dimension even after per-repo keying landed.

**Status:** Investigating
**Severity:** P1
**Discovered:** 2026-06-19
**Placement:** docs/bugs/stale-marker-arms-validate-deny-on-unrelated-dispatches
**Source:** `/lazy-batch` session-log audit 2026-06-19 (AlgoBooth — 19 sessions, last 2 weeks)
**Related:** `user/scripts/CLAUDE.md` "Per-repo keyed state dir"; `user/hooks/lazy-dispatch-guard.sh`; `docs/features/multi-repo-concurrent-runs/` (per-repo marker keying, COMPLETE 2026-06-16 — fixed cross-REPO leakage; this is the residual SAME-repo / same-session / stale-marker class)

---

## Verified Symptoms
1. **[OBSERVED in logs]** A lingering checkpoint-run marker armed validate-deny against two unrelated dispatches, accruing hardening debt that gates `--run-end` — session `5d4b6c93` @ `2026-06-17T04:23:23Z`: "`pending_hardening: 2` — stray debt, not from this pipeline. The two unacked deny-ledger entries are from earlier Agent dispatches in this conversation (prompt heads: 'unified lazy-batch orchestrator spec' and 'toolification framework spec') that the validate-deny guard denied while a checkpoint-run marker was lingering — not pipeline cycle failures… they will gate `--run-end`. `--ack-unhardened` is operator-only…".
2. **[OBSERVED in logs]** A second session's marker silently DISARMED a live run's dispatch guard (fast-path allow, lost counters) — session `2899da98` @ `2026-06-12T15:01:49`: "a real design flaw that this conversation triggered against your live run… from ~8:53 it is silently unenforced — the guard fast-paths every dispatch (no marker → allow), probe registration stops, counters are lost."

## Evidence Collected (from session logs)
- session `5d4b6c93` @ `2026-06-17T04:23:23Z`: "`pending_hardening: 2` — stray debt, not from this pipeline. The two unacked deny-ledger entries are from earlier Agent dispatches in this conversation (prompt heads: 'unified lazy-batch orchestrator spec' and 'toolification framework spec') that the validate-deny guard denied while a checkpoint-run marker was lingering — not pipeline cycle failures… they will gate `--run-end`. `--ack-unhardened` is operator-only…" — a stale marker turned ordinary in-session design/spec dispatches into deny-ledger entries that block run-end.
- session `2899da98` @ `2026-06-12T15:01:49`: "a real design flaw that this conversation triggered against your live run… from ~8:53 it is silently unenforced — the guard fast-paths every dispatch (no marker → allow), probe registration stops, counters are lost." — the opposite failure: a competing marker leaves a live run's guard silently disarmed.
- session `2899da98` @ `2026-06-12T19:34:57`: "Your batch run's dispatch guard is silently disarmed — its hooks pass its session id, see a marker owned by someone else, and fast-path allow." — confirms the disarm is driven by marker ownership mismatch (someone else's marker), not absence.

## Why this is friction
A run-marker that is stale, mis-owned, or shared across sessions in the same repo causes the validate-deny guard to either over-fire (denying unrelated non-pipeline dispatches, which then accrue as hardening debt that gates `--run-end` and forces an operator-only `--ack-unhardened`) or silently under-fire (a foreign marker disarms a live run's guard, halting probe registration and losing counters). Per-repo keying closed the cross-repo leak but left the same-repo / same-session / stale dimension unresolved, so an otherwise clean run still ends on operator adjudication of debt it never created.

## Open Questions (for `/spec-bug` to resolve — do NOT pre-bake answers)
- What residual marker-scope failure modes remain after per-repo keying (`multi-repo-concurrent-runs`, COMPLETE 2026-06-16), and which dimensions (same-repo, same-session, stale/lingering, cross-session ownership) does per-repo keying already cover vs. leave open?
- Should the guard distinguish pipeline dispatches from unrelated in-session dispatches before charging a denial as hardening debt?
- What is the correct lifecycle for a checkpoint-run marker such that it neither lingers to over-arm nor gets adopted/overwritten by a foreign session to disarm a live run?

> **Stub — root cause NOT yet investigated.** This spec records observed symptoms + evidence only. `/spec-bug` owns reproduction, seam analysis, root-cause confirmation, and fix scope. Do not add Theories / Proven Findings / Affected Area / fix scope here.
